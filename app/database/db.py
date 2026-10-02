"""Acceso y operaciones de base de datos SQLite nativa para Escaner TQT (esquema v2).

Modelo v2 (docs/SPEC_v2.md): inventario GLOBAL de PCB (`pcb_inventario`) y tarjetas de producción por lote
con tres ranuras (R1/R2/R3) que apuntan a ese inventario. Nombres y MAC de una tarjeta se DERIVAN de sus PCB.
Las operaciones del inventario viven en `app/database/inventario.py`.
"""
import logging
import re
import sqlite3
import unicodedata
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple

from app.config import settings
from app.database.models import (
    DDL_PCB_INVENTARIO,
    FIRMWARE_CATALOGO_INICIAL,
    ESTADOS_GENERALES,
    ETAPA_KEYS,
    MESES_ES,
    SCHEMA,
    SCHEMA_LEGACY,
    VERSION_DEFAULT,
    ddl_tarjetas,
    derivar_estado_general,
    estado_pcb_desde_prueba,
    extract_mac,
    normalizar_estado_prueba,
    normalizar_etapa,
    normalize_mac,
    parse_tarjeta_code,
)

logger = logging.getLogger(__name__)

# Avisos generados por la migración (p. ej. MACs duplicadas heredadas que no se pudieron conservar)
MIGRATION_WARNINGS: List[str] = []


class ConflictoError(ValueError):
    """Regla de negocio violada por el estado actual de los datos (duplicado, ocupado...): HTTP 409."""


class NoEncontradoError(LookupError):
    """El registro pedido no existe: HTTP 404."""


# ============================================================================
# Conexión y transacciones
# ============================================================================
def connect(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Conexión SQLite en autocommit (isolation_level=None) con WAL y timeout de 10s.
    Las transacciones se abren de forma explícita con get_db()/transaction()."""
    target_path = str(db_path or settings.DB_PATH)
    conn = sqlite3.connect(target_path, timeout=settings.SQLITE_TIMEOUT, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA busy_timeout = 10000;")
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    return conn


def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Alias para connect()."""
    return connect(db_path)


def _commit(conn: sqlite3.Connection) -> None:
    if conn.in_transaction:
        conn.execute("COMMIT")


def _rollback(conn: sqlite3.Connection) -> None:
    if conn.in_transaction:
        conn.execute("ROLLBACK")


@contextmanager
def get_db(db_path: Optional[Path] = None) -> Generator[sqlite3.Connection, None, None]:
    """Transacción atómica (BEGIN diferido) con commit/rollback seguro."""
    conn = connect(db_path)
    try:
        conn.execute("BEGIN")
        yield conn
        _commit(conn)
    except BaseException:
        _rollback(conn)
        raise
    finally:
        conn.close()


@contextmanager
def get_conn(db_path: Optional[Path] = None) -> Generator[sqlite3.Connection, None, None]:
    """Alias para get_db()."""
    with get_db(db_path) as conn:
        yield conn


@contextmanager
def transaction(db_path: Optional[Path] = None) -> Generator[sqlite3.Connection, None, None]:
    """BEGIN IMMEDIATE: toma el candado de escritura al inicio, de modo que dos celulares
    no puedan registrar la misma PCB/MAC en paralelo (el segundo espera y luego ve el duplicado)."""
    conn = connect(db_path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        _commit(conn)
    except BaseException:
        _rollback(conn)
        raise
    finally:
        conn.close()


def nombre_lote(anio: int, mes: int) -> str:
    """Devuelve el nombre legible de un lote mensual (ej. 'Septiembre 2026')."""
    return f"{MESES_ES[mes - 1]} {anio}"


# ============================================================================
# Inicialización y migraciones
# ============================================================================
_DDL_PRUEBAS_NUEVA = """
CREATE TABLE pruebas_historial_nueva (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tarjeta_id INTEGER NOT NULL UNIQUE REFERENCES tarjetas_produccion(id) ON DELETE CASCADE,
    soldadura TEXT NOT NULL DEFAULT 'PENDIENTE',
    programacion TEXT NOT NULL DEFAULT 'PENDIENTE',
    prueba_pcb TEXT NOT NULL DEFAULT 'PENDIENTE',
    integracion TEXT NOT NULL DEFAULT 'PENDIENTE',
    prueba_final TEXT NOT NULL DEFAULT 'PENDIENTE',
    estado_general TEXT NOT NULL DEFAULT 'PENDIENTE',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""


def _migrar_v1(conn: sqlite3.Connection) -> None:
    """Migración v1: vocabulario canónico de estados, defaults PENDIENTE, sin tablas de
    compatibilidad y catálogo sin duplicados. Idempotente (usa PRAGMA user_version)."""
    if conn.execute("PRAGMA user_version").fetchone()[0] >= 1:
        return

    conn.execute("BEGIN IMMEDIATE")
    try:
        # a) Tablas de compatibilidad antiguas (nunca tuvieron datos productivos)
        for tabla in ("pruebas", "tarjetas", "pcb", "meses_lote"):
            conn.execute(f"DROP TABLE IF EXISTS {tabla}")

        # b) pruebas_historial: mapear estados heredados, recalcular general y quitar defaults APROBADO
        filas = conn.execute(
            "SELECT id, tarjeta_id, soldadura, programacion, prueba_pcb, integracion, prueba_final, updated_at "
            "FROM pruebas_historial"
        ).fetchall()
        conn.execute("DROP TABLE IF EXISTS pruebas_historial_nueva")
        conn.execute(_DDL_PRUEBAS_NUEVA)
        for f in filas:
            etapas = [normalizar_estado_prueba(f[k], default="PENDIENTE") for k in ETAPA_KEYS]
            conn.execute(
                "INSERT INTO pruebas_historial_nueva (id, tarjeta_id, soldadura, programacion, prueba_pcb, "
                "integracion, prueba_final, estado_general, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (f["id"], f["tarjeta_id"], *etapas, derivar_estado_general(etapas), f["updated_at"]),
            )
        conn.execute("DROP TABLE pruebas_historial")
        conn.execute("ALTER TABLE pruebas_historial_nueva RENAME TO pruebas_historial")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pruebas_tarjeta ON pruebas_historial(tarjeta_id)")

        # c) catalogo_pcb: estados heredados y duplicados (misma PCB repetida por importaciones)
        conn.execute("UPDATE catalogo_pcb SET estado_pcb='FALLA' WHERE estado_pcb='DEFECTUOSA'")
        conn.execute("UPDATE catalogo_pcb SET estado_pcb='PENDIENTE' WHERE estado_pcb='EN_REVISION'")
        conn.execute(
            "DELETE FROM catalogo_pcb WHERE id NOT IN ("
            "  SELECT COALESCE(MAX(CASE WHEN asignada_a_id IS NOT NULL THEN id END), MAX(id)) "
            "  FROM catalogo_pcb GROUP BY lote_id, tipo_pcb, nombre_pcb)"
        )

        conn.execute("PRAGMA user_version = 1")
        _commit(conn)
    except BaseException:
        _rollback(conn)
        raise


def _aviso_migracion(texto: str) -> None:
    MIGRATION_WARNINGS.append(texto)
    logger.warning(texto)


def _migrar_v2(conn: sqlite3.Connection) -> None:
    """Migración v2: par R1+R2 con MAC obligatoria -> inventario global de PCB + tarjetas con ranuras.
    Conserva TODOS los datos (mismos ids de tarjeta, pruebas intactas). Idempotente (user_version >= 2).
    Datos heredados que no caben (MAC repetida, PCB compartida entre lotes) no rompen el arranque:
    se quedan sin MAC / sin ranura y se avisa en MIGRATION_WARNINGS."""
    if conn.execute("PRAGMA user_version").fetchone()[0] >= 2:
        return

    conn.execute("PRAGMA foreign_keys = OFF")  # no puede cambiarse dentro de una transacción
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(DDL_PCB_INVENTARIO)
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_pcbinv_mac ON pcb_inventario(mac) WHERE mac IS NOT NULL")
        conn.execute("CREATE TABLE IF NOT EXISTS ajustes (clave TEXT PRIMARY KEY, valor TEXT NOT NULL, "
                     "updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime')))")
        conn.execute("DROP TABLE IF EXISTS tarjetas_nueva")
        conn.execute(ddl_tarjetas("tarjetas_nueva"))

        catalogo = {(r["lote_id"], r["tipo_pcb"], r["nombre_pcb"]): r["estado_pcb"]
                    for r in conn.execute("SELECT lote_id, tipo_pcb, nombre_pcb, estado_pcb FROM catalogo_pcb")}
        macs_usadas: set = set()
        asignadas: set = set()

        def _digitos_finales(txt: str) -> str:
            m = re.search(r"(\d{1,4})\D*$", txt or "")
            return m.group(1).zfill(4) if m else ""

        def pcb_para(tipo: str, nombre_raw: str, mac_raw: str, ciclo: str, estado: str, id_num: str, etiqueta: str) -> Optional[int]:
            t = parse_tarjeta_code(nombre_raw, tipo)
            if t and t["tipo"] == tipo:
                version, serie = t["version"], t["numero"]
            else:  # nombre no canónico (p. ej. 'PCB-R1-0011'): se conserva la serie que traía
                version, serie = VERSION_DEFAULT, _digitos_finales(nombre_raw) or _digitos_finales(id_num)
            if not serie:
                _aviso_migracion(f"Migración: PCB '{nombre_raw}' ({etiqueta}) sin número de serie; se dejó la ranura vacía.")
                return None
            nombre = f"TQT-{tipo}-V{version}-{serie}"
            fila = conn.execute("SELECT id, mac FROM pcb_inventario WHERE tipo=? AND version=? AND serie=?",
                                (tipo, version, serie)).fetchone()
            if fila:
                if fila["id"] in asignadas and ciclo == "ASIGNADA":
                    _aviso_migracion(f"Migración: {nombre} estaba en más de una tarjeta ({etiqueta}); la ranura quedó vacía.")
                    return None
                return fila["id"]
            mac = extract_mac(mac_raw) if tipo in ("R1", "R2") else None
            if mac and mac in macs_usadas:
                _aviso_migracion(f"Migración: la MAC {mac} estaba repetida ({etiqueta}, {nombre}); esa PCB quedó sin MAC.")
                mac = None
            if mac:
                macs_usadas.add(mac)
            return conn.execute(
                "INSERT INTO pcb_inventario (tipo, version, serie, nombre, mac, estado_ciclo, estado_pcb, origen, confirmada_en) "
                "VALUES (?,?,?,?,?,?,?,'MANUAL', datetime('now','localtime'))",
                (tipo, version, serie, nombre, mac, ciclo,
                 estado if estado in ("PENDIENTE", "FUNCIONAL", "FALLA") else "PENDIENTE"),
            ).lastrowid

        for t in conn.execute("SELECT * FROM tarjetas_produccion ORDER BY id").fetchall():
            prueba = conn.execute("SELECT prueba_pcb FROM pruebas_historial WHERE tarjeta_id = ?", (t["id"],)).fetchone()
            derivado = estado_pcb_desde_prueba(prueba["prueba_pcb"] if prueba else None)
            ids: List[Optional[int]] = []
            for tipo, col_n, col_m in (("R1", "nombre_r1", "mac_r1"), ("R2", "nombre_r2", "mac_r2")):
                if not t[col_n]:
                    ids.append(None)
                    continue
                est = catalogo.get((t["lote_id"], tipo, t[col_n])) or derivado
                pid = pcb_para(tipo, t[col_n], t[col_m] or "", "ASIGNADA", est, t["id_tarjeta_num"],
                               f"tarjeta {t['id_tarjeta_num']}")
                if pid:
                    asignadas.add(pid)
                ids.append(pid)
            conn.execute(
                "INSERT INTO tarjetas_nueva (id, lote_id, id_tarjeta_num, pcb_r1_id, pcb_r2_id, firmware_r1, firmware_r2, "
                "semana_produccion, fecha_proyectada, fecha_real, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (t["id"], t["lote_id"], t["id_tarjeta_num"], ids[0], ids[1], t["firmware_r1"], t["firmware_r2"],
                 t["semana_produccion"], t["fecha_proyectada"], t["fecha_real"], t["created_at"], t["updated_at"]),
            )
        for pid in asignadas:
            conn.execute("UPDATE pcb_inventario SET estado_ciclo='ASIGNADA' WHERE id=?", (pid,))

        # PCB del catálogo que no estaban en ninguna tarjeta: quedan DISPONIBLES (conservan MAC/estado)
        for r in conn.execute("SELECT lote_id, tipo_pcb, nombre_pcb, mac_address, estado_pcb FROM catalogo_pcb ORDER BY id").fetchall():
            if not parse_tarjeta_code(r["nombre_pcb"], r["tipo_pcb"]):
                continue
            pcb_para(r["tipo_pcb"], r["nombre_pcb"], r["mac_address"] or "", "DISPONIBLE", r["estado_pcb"], "", "catálogo")

        conn.execute("DROP TABLE tarjetas_produccion")
        conn.execute("ALTER TABLE tarjetas_nueva RENAME TO tarjetas_produccion")
        conn.execute("DROP TABLE IF EXISTS catalogo_pcb")
        rotas = conn.execute("PRAGMA foreign_key_check").fetchall()
        if rotas:
            raise RuntimeError(f"La migración v2 dejó {len(rotas)} referencias rotas; se revierte.")
        conn.execute("PRAGMA user_version = 2")
        _commit(conn)
    except BaseException:
        _rollback(conn)
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")


_TARJETA_COMPLETA = ("pcb_r1_id IS NOT NULL AND pcb_r2_id IS NOT NULL AND pcb_r3_id IS NOT NULL "
                     "AND (SELECT mac FROM pcb_inventario WHERE id = pcb_r1_id) IS NOT NULL "
                     "AND (SELECT mac FROM pcb_inventario WHERE id = pcb_r2_id) IS NOT NULL")


def _asegurar_fechas_entrega(conn: sqlite3.Connection) -> None:
    """Fechas de llegada / finalizado y gabinete de la tarjeta (la entrega es `fecha_real`). Se llenan solas con disparadores:
      * llegada    = fecha en que se confirmó la recepción de sus placas (la más antigua; hoy si no hay);
      * finalizado = el día en que la tarjeta queda completa (R1+R2+R3 y MAC de R1 y R2).
    Después se pueden corregir a mano (PATCH /api/tarjetas/{id}). Idempotente; conserva los datos."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(tarjetas_produccion)")}
    if not cols:
        return
    nuevas = False
    for col in ("fecha_llegada", "fecha_finalizado", "gabinete"):
        if col not in cols:
            conn.execute(f"ALTER TABLE tarjetas_produccion ADD COLUMN {col} TEXT")
            nuevas = True
    sellar = (f"UPDATE tarjetas_produccion SET fecha_finalizado = date('now','localtime') "
              f"WHERE id = {{id}} AND fecha_finalizado IS NULL AND {_TARJETA_COMPLETA}")
    conn.execute("CREATE TRIGGER IF NOT EXISTS trg_tarjeta_fechas_alta AFTER INSERT ON tarjetas_produccion BEGIN "
                 "UPDATE tarjetas_produccion SET fecha_llegada = COALESCE(fecha_llegada, (SELECT date(MIN(confirmada_en)) FROM pcb_inventario "
                 "WHERE id IN (NEW.pcb_r1_id, NEW.pcb_r2_id, NEW.pcb_r3_id)), date('now','localtime')) WHERE id = NEW.id; "
                 + sellar.format(id="NEW.id") + "; END")
    conn.execute("CREATE TRIGGER IF NOT EXISTS trg_tarjeta_fechas_placas AFTER UPDATE OF pcb_r1_id, pcb_r2_id, pcb_r3_id ON tarjetas_produccion "
                 "BEGIN " + sellar.format(id="NEW.id") + "; END")
    conn.execute("CREATE TRIGGER IF NOT EXISTS trg_tarjeta_fechas_mac AFTER UPDATE OF mac ON pcb_inventario BEGIN "
                 "UPDATE tarjetas_produccion SET fecha_finalizado = date('now','localtime') WHERE fecha_finalizado IS NULL "
                 f"AND (pcb_r1_id = NEW.id OR pcb_r2_id = NEW.id) AND {_TARJETA_COMPLETA}; END")
    if nuevas:   # tarjetas que ya existían: llegada = recepción más antigua de sus placas; finalizado = último cambio si ya están completas
        conn.execute("UPDATE tarjetas_produccion SET fecha_llegada = COALESCE((SELECT date(MIN(confirmada_en)) FROM pcb_inventario "
                     "WHERE id IN (pcb_r1_id, pcb_r2_id, pcb_r3_id)), date(created_at)) WHERE fecha_llegada IS NULL")
        conn.execute(f"UPDATE tarjetas_produccion SET fecha_finalizado = date(updated_at) WHERE fecha_finalizado IS NULL AND {_TARJETA_COMPLETA}")


def _asegurar_columnas(conn: sqlite3.Connection) -> None:
    """Bases anteriores: agrega pcb_inventario.firmware y siembra el catálogo de firmware con el de la plantilla Excel
    (idempotente, conserva datos). El firmware pasa de la tarjeta a cada PCB; el valor antiguo de la tarjeta se sigue
    mostrando mientras la PCB no tenga uno propio."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(pcb_inventario)")}
    if cols and "firmware" not in cols:
        conn.execute("ALTER TABLE pcb_inventario ADD COLUMN firmware TEXT")
    if cols and "sesion" not in cols:
        conn.execute("ALTER TABLE pcb_inventario ADD COLUMN sesion TEXT")
    _asegurar_fechas_entrega(conn)
    if conn.execute("SELECT name FROM sqlite_master WHERE name='firmware_catalogo'").fetchone()             and conn.execute("SELECT COUNT(*) FROM firmware_catalogo").fetchone()[0] == 0:
        for rol, versiones in FIRMWARE_CATALOGO_INICIAL.items():
            for i, v in enumerate(versiones, 1):
                conn.execute("INSERT OR IGNORE INTO firmware_catalogo (rol, version, orden) VALUES (?,?,?)", (rol, v, i))


def init_db(db_path: Optional[Path] = None) -> None:
    """Inicializa esquema, migra bases existentes (v0/v1 -> v2) y crea el lote del mes actual si no hay ninguno."""
    target_path = Path(db_path or settings.DB_PATH)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    conn = connect(target_path)
    try:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        tablas = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")} - {"sqlite_sequence"}
        if not tablas:  # base nueva: directo al esquema v2
            conn.executescript(SCHEMA)
            conn.execute("PRAGMA user_version = 2")
        else:
            if version < 2:
                conn.executescript(SCHEMA_LEGACY)  # completa tablas faltantes de una BD heredada antes de migrar
                _migrar_v1(conn)
                _migrar_v2(conn)
            conn.executescript(SCHEMA)
        _asegurar_columnas(conn)
    finally:
        conn.close()

    with get_db(target_path) as conn:
        if not conn.execute("SELECT id FROM lotes_mensuales LIMIT 1").fetchone():
            now = datetime.now()
            conn.execute(
                "INSERT INTO lotes_mensuales (codigo_lote, mes, anio, activo) VALUES (?, ?, ?, 1)",
                (f"{now.year}-{now.month:02d}", now.month, now.year),
            )


# ============================================================================
# Operaciones de Lotes Mensuales
# ============================================================================
def _con_conn(conn: Optional[sqlite3.Connection], db_path: Optional[Path], fn, escribe: bool = False):
    """Ejecuta fn(conn) reutilizando la conexión dada o abriendo una (transacción si escribe)."""
    if conn is not None:
        return fn(conn)
    with (transaction(db_path) if escribe else get_db(db_path)) as c:
        return fn(c)


def get_active_lote(conn: Optional[sqlite3.Connection] = None, db_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Obtiene el lote que se encuentra marcado como activo actualmente."""
    def _q(c):
        row = c.execute("SELECT * FROM lotes_mensuales WHERE activo = 1 ORDER BY id DESC LIMIT 1").fetchone()
        return dict(row) if row else None
    return _con_conn(conn, db_path, _q)


def get_lote_by_id(lote_id: int, conn: Optional[sqlite3.Connection] = None, db_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Busca un lote por ID."""
    def _q(c):
        row = c.execute("SELECT * FROM lotes_mensuales WHERE id = ?", (lote_id,)).fetchone()
        return dict(row) if row else None
    return _con_conn(conn, db_path, _q)


def get_lote_by_codigo(codigo: str, conn: Optional[sqlite3.Connection] = None, db_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Busca un lote por su código único (ej. '2026-09')."""
    def _q(c):
        row = c.execute("SELECT * FROM lotes_mensuales WHERE codigo_lote = ?", (codigo,)).fetchone()
        return dict(row) if row else None
    return _con_conn(conn, db_path, _q)


def list_lotes(conn: Optional[sqlite3.Connection] = None, db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Lista todos los lotes ordenados por año y mes descendente."""
    def _q(c):
        return [dict(r) for r in c.execute("SELECT l.*, (SELECT COUNT(*) FROM tarjetas_produccion t WHERE t.lote_id = l.id) AS tarjetas FROM lotes_mensuales l ORDER BY l.anio DESC, l.mes DESC, l.id DESC").fetchall()]
    return _con_conn(conn, db_path, _q)


def create_lote(
    codigo_lote: str,
    mes: int,
    anio: int,
    ruta_excel: Optional[str] = None,
    activo: bool = True,
    conn: Optional[sqlite3.Connection] = None,
    db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Crea un nuevo lote mensual. Si activo=True, desactiva los demás."""
    def _exec(c):
        if activo:
            c.execute("UPDATE lotes_mensuales SET activo = 0")
        lote_id = c.execute(
            "INSERT INTO lotes_mensuales (codigo_lote, mes, anio, ruta_excel, activo) VALUES (?, ?, ?, ?, ?)",
            (codigo_lote, mes, anio, ruta_excel, 1 if activo else 0),
        ).lastrowid
        return dict(c.execute("SELECT * FROM lotes_mensuales WHERE id = ?", (lote_id,)).fetchone())
    return _con_conn(conn, db_path, _exec, escribe=True)


def crear_lote(conn: sqlite3.Connection, anio: int, mes: int, activar: bool = True) -> int:
    """Crea o retorna el lote por año y mes (compatibilidad)."""
    row = conn.execute("SELECT id FROM lotes_mensuales WHERE anio = ? AND mes = ?", (anio, mes)).fetchone()
    if row:
        lote_id = row["id"]
    else:
        lote_id = conn.execute(
            "INSERT INTO lotes_mensuales (codigo_lote, mes, anio, activo) VALUES (?, ?, ?, ?)",
            (f"{anio}-{mes:02d}", mes, anio, 1 if activar else 0),
        ).lastrowid
    if activar:
        conn.execute("UPDATE lotes_mensuales SET activo = (id = ?)", (lote_id,))
    return lote_id


def set_active_lote(lote_id: int, conn: Optional[sqlite3.Connection] = None, db_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Activa un lote específico y desactiva todos los demás."""
    def _exec(c):
        if not c.execute("SELECT id FROM lotes_mensuales WHERE id = ?", (lote_id,)).fetchone():
            return None
        c.execute("UPDATE lotes_mensuales SET activo = (id = ?)", (lote_id,))
        return dict(c.execute("SELECT * FROM lotes_mensuales WHERE id = ?", (lote_id,)).fetchone())
    return _con_conn(conn, db_path, _exec, escribe=True)


def set_ruta_excel(lote_id: int, ruta: str, conn: Optional[sqlite3.Connection] = None, db_path: Optional[Path] = None) -> None:
    """Asocia el archivo Excel mensual a un lote."""
    _con_conn(conn, db_path, lambda c: c.execute("UPDATE lotes_mensuales SET ruta_excel = ? WHERE id = ?", (ruta, lote_id)), escribe=True)


def log_evento(
    evento: str,
    lote_id: Optional[int] = None,
    valor: Optional[str] = None,
    detalle: Optional[str] = None,
    operador: Optional[str] = None,
    paso: Optional[int] = None,
    conn: Optional[sqlite3.Connection] = None,
    db_path: Optional[Path] = None,
) -> None:
    """Registra un evento en la bitácora `escaneos` (altas, ediciones, fallas, MAC, pruebas...)."""
    def _ins(c):
        # Un lote inexistente (p. ej. cliente con lote borrado) no debe romper la bitácora por la FK
        lote_ok = lote_id if lote_id and c.execute("SELECT 1 FROM lotes_mensuales WHERE id = ?", (lote_id,)).fetchone() else None
        c.execute(
            "INSERT INTO escaneos (lote_id, evento, paso, valor, detalle, operador) VALUES (?,?,?,?,?,?)",
            (lote_ok, evento, paso, (valor or "")[:200], (detalle or "")[:500], operador),
        )
    _con_conn(conn, db_path, _ins, escribe=True)


def resolver_lote_id(c: sqlite3.Connection, lote_id: Optional[int]) -> int:
    """`lote_id` explícito (validado) o el lote activo."""
    if lote_id:
        if not c.execute("SELECT 1 FROM lotes_mensuales WHERE id = ?", (lote_id,)).fetchone():
            raise NoEncontradoError(f"Lote con ID {lote_id} no encontrado.")
        return lote_id
    active = get_active_lote(c)
    if not active:
        raise ValueError("No hay un lote mensual activo configurado en el sistema.")
    return active["id"]


_resolver_lote_id = resolver_lote_id  # nombre histórico


# ============================================================================
# Consultas de Tarjetas
# ============================================================================
_ALIAS_ESTADO_GENERAL = {
    "FUNCIONAL": "LIBERADO", "APROBADO": "LIBERADO", "OK": "LIBERADO",
    "DEFECTUOSA": "DETENIDO", "DEFECTUOSO": "DETENIDO", "FALLA": "DETENIDO",
    "EN_REVISION": "RETRABAJO", "EN REVISION": "RETRABAJO",
}


def normalizar_estado_general(valor: Optional[str]) -> Optional[str]:
    """Acepta el vocabulario canónico y alias heredados (FUNCIONAL, DEFECTUOSA...) para filtros."""
    if not valor:
        return None
    limpio = "".join(c for c in unicodedata.normalize("NFD", valor.strip().upper()) if unicodedata.category(c) != "Mn")
    limpio = _ALIAS_ESTADO_GENERAL.get(limpio, limpio)
    return limpio if limpio in ESTADOS_GENERALES else limpio


def _cols_pcb(alias: str, ranura: str) -> str:
    """Columnas del inventario que se exponen por ranura (nombre, mac, estado, y datos para armar el objeto)."""
    r = ranura.lower()
    return (f"{alias}.nombre AS nombre_{r}, {alias}.mac AS mac_{r}, {alias}.estado_pcb AS estado_pcb_{r}, "
            f"{alias}.version AS _{r}_version, {alias}.serie AS _{r}_serie, {alias}.estado_ciclo AS _{r}_ciclo")


_SELECT_TARJETA = f"""
    SELECT
        t.id, t.lote_id, t.id_tarjeta_num,
        t.pcb_r1_id, t.pcb_r2_id, t.pcb_r3_id,
        COALESCE(p1.firmware, t.firmware_r1) AS firmware_r1, COALESCE(p2.firmware, t.firmware_r2) AS firmware_r2,
        t.semana_produccion, t.fecha_proyectada, t.fecha_real, t.fecha_llegada, t.fecha_finalizado, t.gabinete,
        t.created_at, t.updated_at,
        {_cols_pcb('p1', 'R1')},
        {_cols_pcb('p2', 'R2')},
        {_cols_pcb('p3', 'R3')},
        COALESCE(pr.soldadura, 'PENDIENTE') AS soldadura,
        COALESCE(pr.programacion, 'PENDIENTE') AS programacion,
        COALESCE(pr.prueba_pcb, 'PENDIENTE') AS prueba_pcb,
        COALESCE(pr.integracion, 'PENDIENTE') AS integracion,
        COALESCE(pr.prueba_final, 'PENDIENTE') AS prueba_final,
        COALESCE(pr.estado_general, 'PENDIENTE') AS estado_general
    FROM tarjetas_produccion t
    LEFT JOIN pcb_inventario p1 ON p1.id = t.pcb_r1_id
    LEFT JOIN pcb_inventario p2 ON p2.id = t.pcb_r2_id
    LEFT JOIN pcb_inventario p3 ON p3.id = t.pcb_r3_id
    LEFT JOIN pruebas_historial pr ON t.id = pr.tarjeta_id
"""


def _fila_a_tarjeta(row: sqlite3.Row) -> Dict[str, Any]:
    """Fila SQL -> tarjeta enriquecida: objetos r1/r2/r3, `completa` (R1 y R2 presentes) y `sin_mac`."""
    d = dict(row)
    for r in ("r1", "r2", "r3"):
        pid = d.get(f"pcb_{r}_id")
        version, serie, ciclo = d.pop(f"_{r}_version"), d.pop(f"_{r}_serie"), d.pop(f"_{r}_ciclo")
        d[r] = None if not pid else {
            "id": pid, "tipo": r.upper(), "version": version, "serie": serie, "nombre": d.get(f"nombre_{r}"),
            "mac": d.get(f"mac_{r}"), "estado_ciclo": ciclo, "estado_pcb": d.get(f"estado_pcb_{r}"),
            "firmware": d.get(f"firmware_{r}"),
        }
    d["completa"] = bool(d["r1"] and d["r2"])
    d["sin_mac"] = [r.upper() for r in ("r1", "r2") if d[r] and not d[r]["mac"]]
    return d


def list_tarjetas(
    lote_id: Optional[int] = None,
    limit: int = 50,
    offset: int = 0,
    search: Optional[str] = None,
    estado: Optional[str] = None,
    estado_general: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None,
    db_path: Optional[Path] = None,
) -> Tuple[List[Dict[str, Any]], int]:
    """Lista tarjetas con sus 5 etapas + estado_general, ranuras R1/R2/R3, búsqueda, filtro y paginación.
    `estado` es el parámetro heredado; `estado_general` el canónico (ambos aceptan alias antiguos)."""
    def _query(c):
        effective_lote_id = lote_id
        if effective_lote_id is None:
            active = get_active_lote(c)
            effective_lote_id = active["id"] if active else None
        if effective_lote_id is None:
            return [], 0

        params: List[Any] = [effective_lote_id]
        where = ["t.lote_id = ?"]
        if search:
            # % y _ del usuario son literales (ESCAPE), no comodines
            lit = search.strip().replace("!", "!!").replace("%", "!%").replace("_", "!_")
            like = f"%{lit}%"
            where.append("(t.id_tarjeta_num LIKE ? ESCAPE '!' OR p1.nombre LIKE ? ESCAPE '!' OR p1.mac LIKE ? ESCAPE '!' "
                         "OR p2.nombre LIKE ? ESCAPE '!' OR p2.mac LIKE ? ESCAPE '!' OR p3.nombre LIKE ? ESCAPE '!')")
            params.extend([like] * 6)
        filtro = normalizar_estado_general(estado_general or estado)
        if filtro:
            if filtro == "PENDIENTE":
                where.append("COALESCE(pr.estado_general, 'PENDIENTE') = 'PENDIENTE'")
            else:
                where.append("pr.estado_general = ?")
                params.append(filtro)
        where_sql = " AND ".join(where)

        joins = ("LEFT JOIN pcb_inventario p1 ON p1.id = t.pcb_r1_id LEFT JOIN pcb_inventario p2 ON p2.id = t.pcb_r2_id "
                 "LEFT JOIN pcb_inventario p3 ON p3.id = t.pcb_r3_id LEFT JOIN pruebas_historial pr ON t.id = pr.tarjeta_id")
        total = c.execute(f"SELECT COUNT(*) AS total FROM tarjetas_produccion t {joins} WHERE {where_sql}", params).fetchone()["total"]
        rows = c.execute(
            f"{_SELECT_TARJETA} WHERE {where_sql} ORDER BY t.id DESC LIMIT ? OFFSET ?", params + [limit, offset]
        ).fetchall()
        return [_fila_a_tarjeta(r) for r in rows], total
    return _con_conn(conn, db_path, _query)


def get_tarjeta_by_id(tarjeta_id: int, conn: Optional[sqlite3.Connection] = None, db_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Obtiene una tarjeta con su historial de pruebas por su ID primario."""
    def _q(c):
        row = c.execute(f"{_SELECT_TARJETA} WHERE t.id = ?", (tarjeta_id,)).fetchone()
        return _fila_a_tarjeta(row) if row else None
    return _con_conn(conn, db_path, _q)


def get_tarjeta_por_numero(lote_id: int, id_tarjeta_num: str, conn: Optional[sqlite3.Connection] = None,
                           db_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Tarjeta de un lote por su número ('0011')."""
    def _q(c):
        row = c.execute(f"{_SELECT_TARJETA} WHERE t.lote_id = ? AND t.id_tarjeta_num = ?", (lote_id, id_tarjeta_num)).fetchone()
        return _fila_a_tarjeta(row) if row else None
    return _con_conn(conn, db_path, _q)


def find_tarjeta_by_mac(mac: str, conn: Optional[sqlite3.Connection] = None, db_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Tarjeta (de cualquier lote) cuya PCB R1 o R2 tiene esa MAC. None si la MAC no existe o su PCB está suelta."""
    limpia = extract_mac(mac) or normalize_mac(mac)

    def _q(c):
        row = c.execute(
            f"{_SELECT_TARJETA} WHERE t.pcb_r1_id = (SELECT id FROM pcb_inventario WHERE mac = ?) "
            f"OR t.pcb_r2_id = (SELECT id FROM pcb_inventario WHERE mac = ?) LIMIT 1", (limpia, limpia)).fetchone()
        if not row:
            return None
        d = _fila_a_tarjeta(row)
        d["codigo_lote"] = c.execute("SELECT codigo_lote FROM lotes_mensuales WHERE id = ?", (d["lote_id"],)).fetchone()[0]
        d["match_tipo"] = "R1" if d["mac_r1"] == limpia else "R2"
        return d
    return _con_conn(conn, db_path, _q)


# ============================================================================
# Pruebas de calidad
# ============================================================================
def sincronizar_estado_pcb(c: sqlite3.Connection, tarjeta_id: int) -> None:
    """El estado de las PCB de la tarjeta se deriva de su etapa 'Prueba PCB' (FUNCIONAL / FALLA / PENDIENTE)."""
    fila = c.execute("SELECT prueba_pcb FROM pruebas_historial WHERE tarjeta_id = ?", (tarjeta_id,)).fetchone()
    estado = estado_pcb_desde_prueba(fila["prueba_pcb"] if fila else None)
    c.execute(
        "UPDATE pcb_inventario SET estado_pcb = ?, updated_at = datetime('now','localtime') WHERE id IN ("
        " SELECT pcb_r1_id FROM tarjetas_produccion WHERE id = ? UNION SELECT pcb_r2_id FROM tarjetas_produccion WHERE id = ?"
        " UNION SELECT pcb_r3_id FROM tarjetas_produccion WHERE id = ?)",
        (estado, tarjeta_id, tarjeta_id, tarjeta_id),
    )


def recalcular_general(c: sqlite3.Connection, tarjeta_id: int) -> str:
    """Deriva y guarda estado_general. Una tarjeta incompleta (sin R1 o sin R2) nunca puede quedar LIBERADA."""
    fila = c.execute(
        "SELECT pr.soldadura, pr.programacion, pr.prueba_pcb, pr.integracion, pr.prueba_final, "
        "t.pcb_r1_id, t.pcb_r2_id FROM tarjetas_produccion t "
        "LEFT JOIN pruebas_historial pr ON pr.tarjeta_id = t.id WHERE t.id = ?", (tarjeta_id,)).fetchone()
    general = derivar_estado_general([fila[k] for k in ETAPA_KEYS])
    if general == "LIBERADO" and not (fila["pcb_r1_id"] and fila["pcb_r2_id"]):
        general = "EN PROCESO"
    c.execute("UPDATE pruebas_historial SET estado_general = ? WHERE tarjeta_id = ?", (general, tarjeta_id))
    return general


def _aplicar_prueba(c: sqlite3.Connection, tarjeta: sqlite3.Row, etapa: str, estado: str, operador: Optional[str]) -> None:
    """Actualiza una etapa, recalcula estado_general y estado de las PCB. Sin commit."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("INSERT OR IGNORE INTO pruebas_historial (tarjeta_id, updated_at) VALUES (?, ?)", (tarjeta["id"], now_str))
    anterior = c.execute(f"SELECT {etapa} FROM pruebas_historial WHERE tarjeta_id = ?", (tarjeta["id"],)).fetchone()[0]
    c.execute(f"UPDATE pruebas_historial SET {etapa} = ?, updated_at = ? WHERE tarjeta_id = ?", (estado, now_str, tarjeta["id"]))  # etapa viene de la lista blanca ETAPA_KEYS
    general = recalcular_general(c, tarjeta["id"])
    sincronizar_estado_pcb(c, tarjeta["id"])
    log_evento("PRUEBA", tarjeta["lote_id"], tarjeta["id_tarjeta_num"], f"{etapa}: {anterior} -> {estado} (general: {general})",
               operador, conn=c)


def get_pruebas(tarjeta_id: int, conn: Optional[sqlite3.Connection] = None, db_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Devuelve las 5 etapas y el estado general de una tarjeta."""
    t = get_tarjeta_by_id(tarjeta_id, conn, db_path)
    if not t:
        return None
    return {"tarjeta_id": t["id"], "id_tarjeta_num": t["id_tarjeta_num"],
            **{k: t[k] for k in ETAPA_KEYS}, "estado_general": t["estado_general"]}


def set_prueba(
    tarjeta_id: int, etapa: str, estado: str, operador: Optional[str] = None,
    conn: Optional[sqlite3.Connection] = None, db_path: Optional[Path] = None,
) -> Optional[Dict[str, Any]]:
    """Registra el estado de UNA etapa. Devuelve la tarjeta actualizada o None si no existe.
    Lanza ValueError si la etapa o el estado son inválidos."""
    etapa_k = normalizar_etapa(etapa)
    estado_n = normalizar_estado_prueba(estado)

    def _exec(c):
        t = c.execute("SELECT id, lote_id, id_tarjeta_num FROM tarjetas_produccion WHERE id = ?", (tarjeta_id,)).fetchone()
        if not t:
            return None
        _aplicar_prueba(c, t, etapa_k, estado_n, operador)
        return get_tarjeta_by_id(tarjeta_id, c)
    return _con_conn(conn, db_path, _exec, escribe=True)


# ============================================================================
# Estadísticas para Monitor
# ============================================================================
def get_stats(lote_id: Optional[int] = None, conn: Optional[sqlite3.Connection] = None, db_path: Optional[Path] = None) -> Dict[str, Any]:
    """Estadísticas del lote (activo por defecto). funcionales=LIBERADO, defectuosas=DETENIDO,
    en_revision=RETRABAJO, pendientes=PENDIENTE, en_proceso=EN PROCESO. `inventario` = PCB DISPONIBLES por tipo."""
    def _query(c):
        disponibles = {"R1": 0, "R2": 0, "R3": 0}
        for r in c.execute("SELECT tipo, COUNT(*) n FROM pcb_inventario WHERE estado_ciclo = 'DISPONIBLE' GROUP BY tipo"):
            disponibles[r["tipo"]] = r["n"]
        target = get_lote_by_id(lote_id, c) if lote_id else get_active_lote(c)
        if not target:
            return {"lote_id": None, "codigo_lote": "Sin Lote", "total_tarjetas": 0, "funcionales": 0, "defectuosas": 0,
                    "en_revision": 0, "pendientes": 0, "en_proceso": 0, "porcentaje_aprobacion": 0.0,
                    "total_r1_escaneados": 0, "total_r2_escaneados": 0, "total_r3_escaneados": 0,
                    "incompletas": 0, "inventario": disponibles}
        row = c.execute(
            """
            SELECT
                COUNT(t.id) AS total,
                SUM(CASE WHEN p.estado_general = 'LIBERADO' THEN 1 ELSE 0 END) AS liberadas,
                SUM(CASE WHEN p.estado_general = 'DETENIDO' THEN 1 ELSE 0 END) AS detenidas,
                SUM(CASE WHEN p.estado_general = 'RETRABAJO' THEN 1 ELSE 0 END) AS retrabajo,
                SUM(CASE WHEN p.estado_general = 'EN PROCESO' THEN 1 ELSE 0 END) AS en_proceso,
                SUM(CASE WHEN p.estado_general IS NULL OR p.estado_general = 'PENDIENTE' THEN 1 ELSE 0 END) AS pendientes,
                SUM(CASE WHEN t.pcb_r1_id IS NOT NULL THEN 1 ELSE 0 END) AS r1,
                SUM(CASE WHEN t.pcb_r2_id IS NOT NULL THEN 1 ELSE 0 END) AS r2,
                SUM(CASE WHEN t.pcb_r3_id IS NOT NULL THEN 1 ELSE 0 END) AS r3,
                SUM(CASE WHEN t.pcb_r1_id IS NULL OR t.pcb_r2_id IS NULL THEN 1 ELSE 0 END) AS incompletas
            FROM tarjetas_produccion t LEFT JOIN pruebas_historial p ON t.id = p.tarjeta_id
            WHERE t.lote_id = ?
            """,
            (target["id"],),
        ).fetchone()
        total = row["total"] or 0
        liberadas = row["liberadas"] or 0
        return {
            "lote_id": target["id"], "codigo_lote": target["codigo_lote"], "total_tarjetas": total,
            "funcionales": liberadas, "defectuosas": row["detenidas"] or 0, "en_revision": row["retrabajo"] or 0,
            "pendientes": row["pendientes"] or 0, "en_proceso": row["en_proceso"] or 0,
            "porcentaje_aprobacion": round(liberadas / total * 100.0, 2) if total else 0.0,
            "total_r1_escaneados": row["r1"] or 0, "total_r2_escaneados": row["r2"] or 0,
            "total_r3_escaneados": row["r3"] or 0, "incompletas": row["incompletas"] or 0, "inventario": disponibles,
        }
    return _con_conn(conn, db_path, _query)
