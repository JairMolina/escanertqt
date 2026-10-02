"""Inventario global de PCB y armado de tarjetas (docs/SPEC_v2.md §2 y §3).

Flujo: recepción por QR (RECIBIDA, borrador) -> confirmar lote (DISPONIBLE) -> emparejar en una tarjeta (ASIGNADA)
-> programar (MAC de R1/R2, tecleada; firmware de las tres) -> pruebas. Una PCB fallada se marca FALLA y se reemplaza por otra suelta.

Todas las escrituras usan BEGIN IMMEDIATE (db.transaction): varios celulares escaneando a la vez no pueden
duplicar una PCB ni una MAC. Las funciones aceptan `conn` (para componer transacciones) o `db_path`.
"""
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.database import db
from app.database.db import ConflictoError, NoEncontradoError
from app.database.models import (
    ETAPA_KEYS,
    RANURAS,
    TIPOS_CON_MAC,
    TIPOS_PCB,
    VERSION_DEFAULT,
    extract_mac,
    parse_tarjeta_code,
)

_COL_RANURA = {"R1": "pcb_r1_id", "R2": "pcb_r2_id", "R3": "pcb_r3_id"}
MAX_SERIE = 9999

_SELECT_PCB = """
    SELECT p.id, p.tipo, p.version, p.serie, p.nombre, p.mac, p.firmware, p.estado_ciclo, p.estado_pcb, p.origen, p.operador,
           p.nota, p.recibida_en, p.confirmada_en, p.updated_at,
           t.id AS tarjeta_id, t.id_tarjeta_num, t.lote_id AS tarjeta_lote_id,
           CASE WHEN t.pcb_r1_id = p.id THEN 'R1' WHEN t.pcb_r2_id = p.id THEN 'R2'
                WHEN t.pcb_r3_id = p.id THEN 'R3' END AS ranura
    FROM pcb_inventario p
    LEFT JOIN tarjetas_produccion t ON t.pcb_r1_id = p.id OR t.pcb_r2_id = p.id OR t.pcb_r3_id = p.id
"""


# ============================================================================
# Normalización
# ============================================================================
def normalizar_version(valor: Optional[str]) -> str:
    """'V30' / 'v30' / '30' -> '30'. Solo 1 a 3 dígitos."""
    s = str(valor or "").strip().upper()
    if s.startswith("V"):
        s = s[1:]
    if not re.fullmatch(r"[0-9]{1,3}", s) or int(s) == 0:
        raise ValueError(f"Versión inválida: '{valor}'. Usa solo números del 1 al 999 (ej. 30 para V30).")
    return str(int(s))  # 'V030' y 'V30' son la misma versión


def normalizar_serie(valor: Optional[str]) -> str:
    """'84' -> '0084'. Solo 1 a 4 dígitos."""
    s = str(valor or "").strip()
    if not re.fullmatch(r"[0-9]{1,4}", s) or int(s) == 0:
        raise ValueError(f"Serie inválida: '{valor}'. Debe ser un número de 1 a 4 dígitos mayor que 0 (ej. 0084).")
    return s.zfill(4)


def normalizar_tipo(valor: Optional[str]) -> str:
    t = str(valor or "").strip().upper()
    if t not in TIPOS_PCB:
        raise ValueError(f"Tipo de PCB inválido: '{valor}'. Debe ser R1, R2 o R3.")
    return t


def nombre_pcb(tipo: str, version: str, serie: str) -> str:
    return f"TQT-{tipo}-V{version}-{serie}"


def _ahora() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def parsear_qr(codigo: Optional[str], tipo_forzado: Optional[str] = None, version: Optional[str] = None,
               version_defecto: str = VERSION_DEFAULT) -> Optional[Dict[str, str]]:
    """Interpreta el contenido del QR de una PCB ('TQT-R3-V30-0084', tolerando mayúsculas, espacios y guiones bajos).
    Un código con solo el número ('0084') únicamente vale si viene `tipo_forzado`.
    Devuelve {tipo, version, serie, nombre} canónicos o None."""
    raw = (codigo or "").strip()
    t = parse_tarjeta_code(raw)
    if t:  # versión y serie pasan por la misma normalización que las altas manuales (V030 == V30; serie 0000 no existe)
        ver, serie = normalizar_version(t["version"]), normalizar_serie(t["numero"])
        return {"tipo": t["tipo"], "version": ver, "serie": serie, "nombre": nombre_pcb(t["tipo"], ver, serie)}
    if tipo_forzado and re.fullmatch(r"[0-9]{1,4}", raw):
        tipo = normalizar_tipo(tipo_forzado)
        ver = normalizar_version(version) if version else version_defecto
        serie = normalizar_serie(raw)
        return {"tipo": tipo, "version": ver, "serie": serie, "nombre": nombre_pcb(tipo, ver, serie)}
    return None


# ============================================================================
# Ajustes
# ============================================================================
def get_version_defecto(conn: Optional[sqlite3.Connection] = None, db_path: Optional[Path] = None) -> str:
    def _q(c):
        r = c.execute("SELECT valor FROM ajustes WHERE clave = 'version_defecto'").fetchone()
        return r["valor"] if r else VERSION_DEFAULT
    return db._con_conn(conn, db_path, _q)


def set_version_defecto(version: str, conn: Optional[sqlite3.Connection] = None, db_path: Optional[Path] = None) -> str:
    v = normalizar_version(version)

    def _e(c):
        c.execute("INSERT INTO ajustes (clave, valor, updated_at) VALUES ('version_defecto', ?, datetime('now','localtime')) "
                  "ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor, updated_at = excluded.updated_at", (v,))
        db.log_evento("AJUSTE", None, "version_defecto", v, conn=c)
        return v
    return db._con_conn(conn, db_path, _e, escribe=True)


def get_ajustes(conn: Optional[sqlite3.Connection] = None, db_path: Optional[Path] = None) -> Dict[str, Any]:
    return {"version_defecto": get_version_defecto(conn, db_path)}


# ============================================================================
# Consultas
# ============================================================================
def pcb_a_dict(row: Optional[sqlite3.Row]) -> Optional[Dict[str, Any]]:
    return dict(row) if row is not None else None


def _pcb_por_id(c: sqlite3.Connection, pcb_id: int) -> Optional[Dict[str, Any]]:
    return pcb_a_dict(c.execute(f"{_SELECT_PCB} WHERE p.id = ?", (pcb_id,)).fetchone())


def _pcb_o_error(c: sqlite3.Connection, pcb_id: int) -> Dict[str, Any]:
    p = _pcb_por_id(c, pcb_id)
    if not p:
        raise NoEncontradoError(f"PCB con ID {pcb_id} no encontrada.")
    return p


def get_pcb(pcb_id: int, conn: Optional[sqlite3.Connection] = None, db_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    return db._con_conn(conn, db_path, lambda c: _pcb_por_id(c, pcb_id))


def _filtro_sesion(sesion: Optional[str], alias: str = "") -> Tuple[str, list]:
    """Cada equipo ve solo su propio borrador de recepción (marca anónima `sesion`). Sin marca (API directa) ve todo;
    las RECIBIDA anteriores a la marca (sesion NULL) las ven todos para que no queden huérfanas."""
    if not sesion:
        return "", []
    return f" AND ({alias}sesion = ? OR {alias}sesion IS NULL)", [sesion]


def conteos_recepcion(c: sqlite3.Connection, sesion: Optional[str] = None) -> Dict[str, int]:
    """PCB del borrador de recepción (RECIBIDA) por tipo; con `sesion`, solo las de ese equipo."""
    r = {"R1": 0, "R2": 0, "R3": 0}
    w, a = _filtro_sesion(sesion)
    for f in c.execute(f"SELECT tipo, COUNT(*) n FROM pcb_inventario WHERE estado_ciclo = 'RECIBIDA'{w} GROUP BY tipo", a):
        r[f["tipo"]] = f["n"]
    r["total"] = r["R1"] + r["R2"] + r["R3"]
    return r


def conteos_disponibles(c: sqlite3.Connection) -> Dict[str, int]:
    r = {"R1": 0, "R2": 0, "R3": 0}
    for f in c.execute("SELECT tipo, COUNT(*) n FROM pcb_inventario WHERE estado_ciclo = 'DISPONIBLE' GROUP BY tipo"):
        r[f["tipo"]] = f["n"]
    r["total"] = r["R1"] + r["R2"] + r["R3"]
    return r


def _desbalance(conteos: Dict[str, int]) -> Optional[str]:
    if not conteos.get("total"):
        return None
    if len({conteos["R1"], conteos["R2"], conteos["R3"]}) > 1:
        return f"Desbalance: R1 {conteos['R1']} · R2 {conteos['R2']} · R3 {conteos['R3']}"
    return None


def _huecos_recepcion(c: sqlite3.Connection, limite: int = 200, sesion: Optional[str] = None) -> Dict[str, List[str]]:
    """Series que faltan dentro del rango min–max del borrador, por tipo (no existen en ningún estado del inventario)."""
    huecos: Dict[str, List[str]] = {"R1": [], "R2": [], "R3": []}
    for tipo in TIPOS_PCB:
        w, a = _filtro_sesion(sesion)
        r = c.execute("SELECT MIN(CAST(serie AS INTEGER)) a, MAX(CAST(serie AS INTEGER)) b FROM pcb_inventario "
                      f"WHERE tipo = ? AND estado_ciclo = 'RECIBIDA'{w}", [tipo] + a).fetchone()
        if r["a"] is None or r["b"] - r["a"] < 1:
            continue
        existentes = {int(x[0]) for x in c.execute(
            "SELECT DISTINCT serie FROM pcb_inventario WHERE tipo = ? AND CAST(serie AS INTEGER) BETWEEN ? AND ?",
            (tipo, r["a"], r["b"]))}
        faltan = [f"{n:04d}" for n in range(r["a"], r["b"] + 1) if n not in existentes]
        huecos[tipo] = faltan[:limite]
    return huecos


def listar_recepcion(conn: Optional[sqlite3.Connection] = None, db_path: Optional[Path] = None,
                     sesion: Optional[str] = None) -> Dict[str, Any]:
    """Borrador de recepción: PCB RECIBIDA (las más nuevas primero) + conteos, huecos y avisos (de este equipo si hay `sesion`)."""
    def _q(c):
        w, a = _filtro_sesion(sesion, "p.")
        items = [pcb_a_dict(r) for r in c.execute(f"{_SELECT_PCB} WHERE p.estado_ciclo = 'RECIBIDA'{w} ORDER BY p.id DESC", a)]
        conteos = conteos_recepcion(c, sesion)
        huecos = _huecos_recepcion(c, sesion=sesion)
        avisos = []
        d = _desbalance(conteos)
        if d:
            avisos.append(d)
        for tipo, faltan in huecos.items():
            if faltan:
                mas = "+" if len(faltan) >= 200 else ""   # la lista se recorta a 200
                avisos.append(f"{tipo}: faltan {len(faltan)}{mas} serie(s) en el rango recibido ({faltan[0]}…{faltan[-1]})")
        return {"items": items, "conteos": conteos, "huecos": huecos, "avisos": avisos}
    return db._con_conn(conn, db_path, _q)


def listar_pcb(
    tipo: Optional[str] = None, estado_ciclo: Optional[str] = None, q: Optional[str] = None,
    sin_mac: bool = False, sin_tarjeta: bool = False, limit: int = 100, offset: int = 0,
    conn: Optional[sqlite3.Connection] = None, db_path: Optional[Path] = None,
) -> Dict[str, Any]:
    def _q(c):
        where, params = [], []
        if tipo:
            where.append("p.tipo = ?")
            params.append(normalizar_tipo(tipo))
        if estado_ciclo:
            ec = estado_ciclo.strip().upper()
            where.append("p.estado_ciclo = ?")
            params.append(ec)
        if q and q.strip():
            like = f"%{q.strip()}%"
            plano = "%" + re.sub(r"[:\-\s]", "", q.strip()).upper() + "%"
            where.append("(p.nombre LIKE ? OR p.serie LIKE ? OR p.mac LIKE ? OR REPLACE(p.mac, ':', '') LIKE ?)")
            params.extend([like, like, like, plano])
        if sin_mac:
            where.append("p.tipo IN ('R1','R2') AND p.mac IS NULL AND p.estado_ciclo IN ('RECIBIDA','DISPONIBLE','ASIGNADA')")
        if sin_tarjeta:
            where.append("t.id IS NULL")
        w = ("WHERE " + " AND ".join(where)) if where else ""
        total = c.execute(f"SELECT COUNT(*) FROM pcb_inventario p LEFT JOIN tarjetas_produccion t "
                          f"ON t.pcb_r1_id = p.id OR t.pcb_r2_id = p.id OR t.pcb_r3_id = p.id {w}", params).fetchone()[0]
        rows = c.execute(f"{_SELECT_PCB} {w} ORDER BY p.tipo, p.serie, p.version, p.id LIMIT ? OFFSET ?",
                         params + [max(1, min(limit, 5000)), max(0, offset)]).fetchall()
        return {"total": total, "items": [pcb_a_dict(r) for r in rows]}
    return db._con_conn(conn, db_path, _q)


def pcb_por_codigo(codigo: str, conn: Optional[sqlite3.Connection] = None, db_path: Optional[Path] = None) -> Dict[str, Any]:
    """Resuelve un QR (nombre de PCB) o una MAC a su PCB + tarjeta. NoEncontradoError si no existe."""
    def _q(c):
        try:
            p = parsear_qr(codigo)
        except ValueError:  # serie 0000 / versión 0: no puede existir
            p = None
        fila = None
        if p:
            fila = c.execute(f"{_SELECT_PCB} WHERE p.tipo = ? AND p.version = ? AND p.serie = ?",
                             (p["tipo"], p["version"], p["serie"])).fetchone()
        else:
            mac = extract_mac(codigo)
            if mac:
                fila = c.execute(f"{_SELECT_PCB} WHERE p.mac = ?", (mac,)).fetchone()
        if not fila:
            raise NoEncontradoError(f"No hay ninguna PCB registrada con el código '{(codigo or '')[:60]}'.")
        d = pcb_a_dict(fila)
        d["tarjeta"] = db.get_tarjeta_by_id(d["tarjeta_id"], c) if d["tarjeta_id"] else None
        return d
    return db._con_conn(conn, db_path, _q)


def _consulta_por_numero(valor: str, conn: Optional[sqlite3.Connection], db_path: Optional[Path]) -> Dict[str, Any]:
    """Consulta por número: la tarjeta con ese número (la del lote activo si hay varias) o, si aún no existe, las placas
    sueltas o montadas con esa serie (`serie`: r1, r2, r3)."""
    num = _normalizar_num_tarjeta(valor)

    def _q(c):
        activo = db.get_active_lote(c)
        fila = c.execute("SELECT id FROM tarjetas_produccion WHERE id_tarjeta_num = ? ORDER BY (lote_id = ?) DESC, id DESC LIMIT 1",
                         (num, activo["id"] if activo else 0)).fetchone()
        if fila:
            return {"encontrado": True, "origen": "tarjeta", "tarjeta": db.get_tarjeta_by_id(fila["id"], c), "pcb": None, "leidas": [], "avisos": []}
        placas: Dict[str, Optional[Dict[str, Any]]] = {"r1": None, "r2": None, "r3": None}
        for r in c.execute(f"{_SELECT_PCB} WHERE p.serie = ? AND p.estado_ciclo <> 'BAJA' ORDER BY p.tipo, p.id DESC", (num,)):
            d = pcb_a_dict(r)
            placas.setdefault(d["tipo"].lower(), None)
            if placas[d["tipo"].lower()] is None:
                placas[d["tipo"].lower()] = d
        hay = [d for d in placas.values() if d]
        if not hay:
            raise NoEncontradoError(f"No hay ninguna tarjeta ni placa con el número {num}.")
        avisos = [f"Todavía no hay una tarjeta con el número {num}: estas son las placas que tienen ese número."]
        avisos += [f"{d['nombre']} está en la tarjeta {d['id_tarjeta_num']}." for d in hay if d["tarjeta_id"]]
        return {"encontrado": True, "origen": "serie", "tarjeta": None, "pcb": None, "serie": {"numero": num, **placas},
                "leidas": [], "avisos": avisos}
    return db._con_conn(conn, db_path, _q)


def consulta(codigo: str, conn: Optional[sqlite3.Connection] = None, db_path: Optional[Path] = None) -> Dict[str, Any]:
    """Ficha completa a partir de lo que se escanea: la etiqueta DYMO (4 líneas: R1, MAC, R2, MAC), el QR de una PCB
    o una MAC. Devuelve la tarjeta con su pareja (R1/R2/R3: versión, serie, MAC, firmware, estado) y avisos cuando
    la etiqueta ya no coincide con lo registrado. NoEncontradoError si nada de lo leído existe; ValueError si no se reconoce."""
    texto = (codigo or "")[:2000]
    solo_numero = re.fullmatch(r"\s*#?\s*(\d{1,6})\s*", texto)
    if solo_numero:                              # «0011», «11» o «#11»: número de tarjeta / de serie
        return _consulta_por_numero(solo_numero.group(1), conn, db_path)
    leidas: List[Dict[str, Any]] = []            # cada nombre leído con la MAC que lo sigue en la etiqueta
    for linea in re.split(r"[\r\n]+", texto):
        linea = linea.strip()
        if not linea:
            continue
        try:
            q = parsear_qr(linea)
        except ValueError:                       # serie 0000 / versión 0: no puede existir
            q = None
        if q:
            leidas.append({"nombre": q["nombre"], "tipo": q["tipo"], "version": q["version"], "serie": q["serie"], "mac": None})
            continue
        mac = extract_mac(linea)
        if mac:
            if leidas and leidas[-1]["mac"] is None and leidas[-1]["tipo"] in TIPOS_CON_MAC:
                leidas[-1]["mac"] = mac
            else:
                leidas.append({"nombre": None, "tipo": None, "version": None, "serie": None, "mac": mac})
    if not leidas:
        raise ValueError("No reconozco el código. Escanea la etiqueta de la tarjeta, el QR de una PCB o una MAC (XX:XX:XX:XX:XX:XX).")
    origen = "etiqueta" if sum(1 for x in leidas if x["nombre"]) >= 2 else ("mac" if not leidas[0]["nombre"] else "pcb")

    def _q(c):
        avisos: List[str] = []
        encontradas: List[Dict[str, Any]] = []
        for x in leidas:
            if x["nombre"]:
                fila = c.execute(f"{_SELECT_PCB} WHERE p.tipo = ? AND p.version = ? AND p.serie = ?",
                                 (x["tipo"], x["version"], x["serie"])).fetchone()
            else:
                fila = c.execute(f"{_SELECT_PCB} WHERE p.mac = ?", (x["mac"],)).fetchone()
            x["pcb"] = pcb_a_dict(fila) if fila else None
            if not fila:
                avisos.append(f"{x['nombre'] or 'La MAC ' + x['mac']} no está registrada en el sistema.")
            else:
                encontradas.append(x)
                if x["mac"] and x["pcb"]["mac"] and x["mac"] != x["pcb"]["mac"]:
                    avisos.append(f"{x['nombre']}: la MAC de la etiqueta ({x['mac'].lower()}) no coincide con la registrada ({x['pcb']['mac'].lower()}).")
        if not encontradas:
            raise NoEncontradoError("Ninguna de las PCB leídas está registrada: " + ", ".join(x["nombre"] or x["mac"] for x in leidas) + ".")
        principal = next((x["pcb"] for x in encontradas if x["pcb"]["tarjeta_id"]), encontradas[0]["pcb"])
        tarjeta = db.get_tarjeta_by_id(principal["tarjeta_id"], c) if principal["tarjeta_id"] else None
        if tarjeta:
            for x in encontradas:
                tid = x["pcb"]["tarjeta_id"]
                if tid != tarjeta["id"]:
                    avisos.append(f"{x['nombre'] or x['pcb']['nombre']} ya no está en la tarjeta {tarjeta['id_tarjeta_num']}"
                                  + (f" (ahora está en la {x['pcb']['id_tarjeta_num']})." if tid else " (quedó suelta)."))
            for x in leidas:
                if x["nombre"] and x["pcb"] is None and origen == "etiqueta":
                    avisos.append("La etiqueta puede ser de una placa que se reemplazó: revisa la ficha de la tarjeta.")
                    break
        elif principal:
            avisos.append(f"{principal['nombre']} todavía no está en ninguna tarjeta.")
        return {"encontrado": True, "origen": origen, "tarjeta": tarjeta, "pcb": principal, "leidas": [
            {"nombre": x["nombre"], "mac": x["mac"], "registrada": x["pcb"] is not None} for x in leidas], "avisos": avisos}
    return db._con_conn(conn, db_path, _q)


# ============================================================================
# Recepción
# ============================================================================
def _duplicada(c: sqlite3.Connection, fila: sqlite3.Row, sesion: Optional[str] = None) -> Dict[str, Any]:
    p = pcb_a_dict(fila)
    detalle = {"RECIBIDA": "en el lote de recepción actual", "DISPONIBLE": "ya recibida y suelta",
               "ASIGNADA": f"en la tarjeta {p['id_tarjeta_num']}", "FALLA": "marcada como FALLA",
               "BAJA": "dada de baja"}.get(p["estado_ciclo"], p["estado_ciclo"])
    return {"resultado": "DUPLICADA", "mensaje": f"{p['nombre']} ya está registrada ({detalle})", "pcb": p,
            "conteos": conteos_recepcion(c, sesion)}


def escanear_pcb(codigo: str, operador: Optional[str] = None, tipo_forzado: Optional[str] = None,
                 version: Optional[str] = None, db_path: Optional[Path] = None, sesion: Optional[str] = None) -> Dict[str, Any]:
    """Alta automática desde el visor de cámara. Idempotente y barata: primero lee sin candado; solo si la PCB
    no existe abre BEGIN IMMEDIATE, revalida (otro celular pudo ganarle) e inserta. Nunca lanza por negocio."""
    conn = db.connect(db_path)
    try:
        try:
            parsed = parsear_qr(codigo, tipo_forzado, version, get_version_defecto(conn))
        except ValueError as e:
            return {"resultado": "INVALIDA", "mensaje": str(e), "pcb": None, "conteos": conteos_recepcion(conn, sesion)}
        if not parsed:
            return {"resultado": "INVALIDA",
                    "mensaje": f"'{(codigo or '')[:40]}' no es un QR de PCB TQT (ej. TQT-R1-V30-0011)",
                    "pcb": None, "conteos": conteos_recepcion(conn, sesion)}

        busca = f"{_SELECT_PCB} WHERE p.tipo = ? AND p.version = ? AND p.serie = ?"
        args = (parsed["tipo"], parsed["version"], parsed["serie"])
        fila = conn.execute(busca, args).fetchone()
        if fila:
            return _duplicada(conn, fila, sesion)

        conn.execute("BEGIN IMMEDIATE")
        try:
            fila = conn.execute(busca, args).fetchone()
            if fila:
                conn.execute("ROLLBACK")
                return _duplicada(conn, fila, sesion)
            pid = conn.execute(
                "INSERT INTO pcb_inventario (tipo, version, serie, nombre, origen, operador, estado_ciclo, sesion) "
                "VALUES (?,?,?,?, 'QR', ?, 'RECIBIDA', ?)",
                (parsed["tipo"], parsed["version"], parsed["serie"], parsed["nombre"], operador, sesion)).lastrowid
            db.log_evento("PCB_ALTA", None, parsed["nombre"], "QR", operador, conn=conn)
            conn.execute("COMMIT")
        except BaseException:
            db._rollback(conn)
            raise
        return {"resultado": "AGREGADA", "mensaje": f"{parsed['nombre']} agregada", "pcb": _pcb_por_id(conn, pid),
                "conteos": conteos_recepcion(conn, sesion)}
    finally:
        conn.close()


def registrar_manual(tipo: str, version: Optional[str] = None, serie: Optional[str] = None, cantidad: int = 1,
                     operador: Optional[str] = None, conn: Optional[sqlite3.Connection] = None,
                     db_path: Optional[Path] = None, sesion: Optional[str] = None) -> Dict[str, Any]:
    """Alta de PCB sin QR. Sin `serie` toma la siguiente libre del tipo (máximo de TODAS las versiones + 1, para que
    el número siga siendo único por tipo y sirva para emparejar por serie). Todo o nada."""
    tipo_n = normalizar_tipo(tipo)
    if not 1 <= cantidad <= 200:
        raise ValueError("La cantidad debe estar entre 1 y 200.")

    def _e(c):
        ver = normalizar_version(version) if version else get_version_defecto(c)
        if serie and str(serie).strip():
            inicio = int(normalizar_serie(serie))
        else:
            inicio = (c.execute("SELECT MAX(CAST(serie AS INTEGER)) FROM pcb_inventario WHERE tipo = ?", (tipo_n,)).fetchone()[0] or 0) + 1
        if inicio + cantidad - 1 > MAX_SERIE:
            raise ValueError(f"Las series de {tipo_n} llegarían a {inicio + cantidad - 1}; el máximo es {MAX_SERIE}.")
        series = [f"{n:04d}" for n in range(inicio, inicio + cantidad)]
        ocupadas = [nombre_pcb(tipo_n, ver, s) for s in series if c.execute(
            "SELECT 1 FROM pcb_inventario WHERE tipo=? AND version=? AND serie=?", (tipo_n, ver, s)).fetchone()]
        if ocupadas:
            raise ConflictoError("Ya existen: " + ", ".join(ocupadas[:10]) + ("…" if len(ocupadas) > 10 else "") + ". No se agregó ninguna.")
        ids = [c.execute("INSERT INTO pcb_inventario (tipo, version, serie, nombre, origen, operador, estado_ciclo, sesion) "
                         "VALUES (?,?,?,?, 'MANUAL', ?, 'RECIBIDA', ?)",
                         (tipo_n, ver, s, nombre_pcb(tipo_n, ver, s), operador, sesion)).lastrowid for s in series]
        db.log_evento("PCB_ALTA", None, nombre_pcb(tipo_n, ver, series[0]),
                      f"MANUAL x{cantidad} ({series[0]}–{series[-1]})", operador, conn=c)
        return {"pcbs": [_pcb_por_id(c, i) for i in ids], "conteos": conteos_recepcion(c, sesion)}
    return db._con_conn(conn, db_path, _e, escribe=True)


def confirmar_recepcion(ids: Optional[List[int]] = None, nota: Optional[str] = None, operador: Optional[str] = None,
                        conn: Optional[sqlite3.Connection] = None, db_path: Optional[Path] = None,
                        sesion: Optional[str] = None) -> Dict[str, Any]:
    """RECIBIDA -> DISPONIBLE (todo el borrador de este equipo si no se indican ids). Los ids que no están RECIBIDA se reportan en `omitidas`."""
    def _e(c):
        if ids is not None:
            # Lista explícita: solo esas. Una lista VACÍA no confirma nada (evita confirmar todo el borrador por un error del cliente).
            if ids:
                ph = ",".join("?" * len(ids))
                recibidas = [r["id"] for r in c.execute(f"SELECT id FROM pcb_inventario WHERE estado_ciclo='RECIBIDA' AND id IN ({ph})", list(ids))]
            else:
                recibidas = []
            omitidas = [i for i in ids if i not in set(recibidas)]
        else:
            w, a = _filtro_sesion(sesion)
            recibidas = [r["id"] for r in c.execute(f"SELECT id FROM pcb_inventario WHERE estado_ciclo='RECIBIDA'{w}", a)]
            omitidas = []
        resumen = {"R1": 0, "R2": 0, "R3": 0}
        for i in recibidas:
            t = c.execute("SELECT tipo FROM pcb_inventario WHERE id = ?", (i,)).fetchone()[0]
            resumen[t] += 1
            c.execute("UPDATE pcb_inventario SET estado_ciclo='DISPONIBLE', confirmada_en=?, updated_at=? WHERE id=?",
                      (_ahora(), _ahora(), i))
        resumen["total"] = len(recibidas)
        avisos = [a for a in (_desbalance(resumen),) if a]
        if recibidas:
            db.log_evento("RECEPCION_CONFIRMADA", None, str(len(recibidas)),
                          f"R1 {resumen['R1']} · R2 {resumen['R2']} · R3 {resumen['R3']}" + (f" | {nota}" if nota else ""),
                          operador, conn=c)
        return {"confirmadas": len(recibidas), "ids": recibidas, "omitidas": omitidas, "resumen": resumen,
                "avisos": avisos, "disponibles": conteos_disponibles(c), "conteos": conteos_recepcion(c, sesion)}
    return db._con_conn(conn, db_path, _e, escribe=True)


# ============================================================================
# Edición / baja
# ============================================================================
def editar_pcb(pcb_id: int, tipo: Optional[str] = None, version: Optional[str] = None, serie: Optional[str] = None,
               operador: Optional[str] = None, liberar: bool = False,
               conn: Optional[sqlite3.Connection] = None, db_path: Optional[Path] = None) -> Dict[str, Any]:
    """Corrige tipo, versión y/o serie (con `liberar`, una placa montada se saca antes de su tarjeta para poder cambiar el tipo). El nombre se recalcula y, si la PCB está en una tarjeta, la tarjeta y el
    Excel lo reflejan (los nombres de la tarjeta se derivan del inventario)."""
    def _e(c):
        p = _pcb_o_error(c, pcb_id)
        if p["estado_ciclo"] == "BAJA":
            raise ConflictoError(f"{p['nombre']} está dada de baja y no se puede editar.")
        n_tipo = normalizar_tipo(tipo) if tipo else p["tipo"]
        n_ver = normalizar_version(version) if version else p["version"]
        n_serie = normalizar_serie(serie) if serie else p["serie"]
        if (n_tipo, n_ver, n_serie) == (p["tipo"], p["version"], p["serie"]):
            return p
        if n_tipo != p["tipo"]:
            if p["tarjeta_id"] and not liberar:
                raise ConflictoError(f"{p['nombre']} está en la tarjeta {p['id_tarjeta_num']} ({p['ranura']}); "
                                     "libérala antes de cambiar su tipo.")
            if n_tipo not in TIPOS_CON_MAC and p["mac"]:
                raise ValueError("Una R3 no tiene MAC: borra primero la MAC de esta PCB.")
            if p["tarjeta_id"]:
                _asignar_tx(c, p["tarjeta_id"], p["ranura"], None, False, False, operador)
                p = dict(p, tarjeta_id=None)
        nuevo = nombre_pcb(n_tipo, n_ver, n_serie)
        otra = c.execute("SELECT id, estado_ciclo FROM pcb_inventario WHERE tipo=? AND version=? AND serie=? AND id<>?",
                         (n_tipo, n_ver, n_serie, pcb_id)).fetchone()
        if otra:
            raise ConflictoError(f"Ya existe {nuevo} ({otra['estado_ciclo']}).")
        c.execute("UPDATE pcb_inventario SET tipo=?, version=?, serie=?, nombre=?, updated_at=? WHERE id=?",
                  (n_tipo, n_ver, n_serie, nuevo, _ahora(), pcb_id))
        if p["tarjeta_id"]:
            c.execute("UPDATE tarjetas_produccion SET updated_at=? WHERE id=?", (_ahora(), p["tarjeta_id"]))
        db.log_evento("PCB_EDITADA", p["tarjeta_lote_id"], nuevo, f"{p['nombre']} -> {nuevo}", operador, conn=c)
        return _pcb_por_id(c, pcb_id)
    return db._con_conn(conn, db_path, _e, escribe=True)


def cambiar_version_masiva(ids: List[int], version: str, operador: Optional[str] = None,
                           conn: Optional[sqlite3.Connection] = None, db_path: Optional[Path] = None) -> Dict[str, Any]:
    """Cambia la versión de varias PCB a la vez. Todo o nada: si una choca con otra existente, no se cambia ninguna."""
    ver = normalizar_version(version)

    def _e(c):
        cambiadas, faltan, conflictos = [], [], []
        for pid in dict.fromkeys(ids):
            p = _pcb_por_id(c, pid)
            if not p:
                faltan.append(str(pid))
                continue
            if p["estado_ciclo"] == "BAJA":
                conflictos.append(f"{p['nombre']} (dada de baja)")
                continue
            if p["version"] == ver:
                continue
            nuevo = nombre_pcb(p["tipo"], ver, p["serie"])
            if c.execute("SELECT 1 FROM pcb_inventario WHERE tipo=? AND version=? AND serie=? AND id<>?",
                         (p["tipo"], ver, p["serie"], pid)).fetchone():
                conflictos.append(f"{p['nombre']} -> {nuevo} ya existe")
                continue
            c.execute("UPDATE pcb_inventario SET version=?, nombre=?, updated_at=? WHERE id=?", (ver, nuevo, _ahora(), pid))
            if p["tarjeta_id"]:
                c.execute("UPDATE tarjetas_produccion SET updated_at=? WHERE id=?", (_ahora(), p["tarjeta_id"]))
            cambiadas.append(pid)
        if faltan:
            raise NoEncontradoError("No existen las PCB con ID: " + ", ".join(faltan) + ". No se cambió ninguna.")
        if conflictos:
            raise ConflictoError("No se cambió ninguna PCB: " + "; ".join(conflictos[:8]))
        if cambiadas:
            db.log_evento("VERSION_MASIVA", None, f"V{ver}", f"{len(cambiadas)} PCB", operador, conn=c)
        return {"actualizadas": len(cambiadas), "version": ver, "pcbs": [_pcb_por_id(c, i) for i in cambiadas]}
    return db._con_conn(conn, db_path, _e, escribe=True)


def eliminar_pcb(pcb_id: int, operador: Optional[str] = None, conn: Optional[sqlite3.Connection] = None,
                 db_path: Optional[Path] = None) -> Dict[str, Any]:
    """RECIBIDA/DISPONIBLE se borra; FALLA pasa a BAJA (conserva su rastro y su MAC); ASIGNADA es 409."""
    def _e(c):
        p = _pcb_o_error(c, pcb_id)
        if p["tarjeta_id"]:
            raise ConflictoError(f"{p['nombre']} está en la tarjeta {p['id_tarjeta_num']} ({p['ranura']}); "
                                 "sácala de la tarjeta antes de eliminarla.")
        if p["estado_ciclo"] in ("RECIBIDA", "DISPONIBLE"):
            c.execute("DELETE FROM pcb_inventario WHERE id = ?", (pcb_id,))
            accion = "ELIMINADA"
        else:
            c.execute("UPDATE pcb_inventario SET estado_ciclo='BAJA', updated_at=? WHERE id=?", (_ahora(), pcb_id))
            accion = "BAJA"
        db.log_evento("PCB_ELIMINADA", None, p["nombre"], accion, operador, conn=c)
        return {"id": pcb_id, "nombre": p["nombre"], "tipo": p["tipo"], "accion": accion, "conteos": conteos_recepcion(c)}
    return db._con_conn(conn, db_path, _e, escribe=True)


# ============================================================================
# MAC (se teclea después de programar; solo R1 y R2)
# ============================================================================
def set_mac(pcb_id: int, mac: Optional[str], operador: Optional[str] = None, conn: Optional[sqlite3.Connection] = None,
            db_path: Optional[Path] = None) -> Dict[str, Any]:
    def _e(c):
        p = _pcb_o_error(c, pcb_id)
        if p["estado_ciclo"] == "BAJA":
            raise ConflictoError(f"{p['nombre']} está dada de baja.")
        if mac is None or not str(mac).strip():
            nueva = None
        else:
            if p["tipo"] not in TIPOS_CON_MAC:
                raise ValueError(f"{p['nombre']} es R3: las R3 no tienen MAC.")
            nueva = extract_mac(mac)
            if not nueva and re.fullmatch(r"[0-9A-Fa-f\s:.\-]+", str(mac)):
                nueva = extract_mac(re.sub(r"\s+", "", str(mac)))  # '70 4b ca 5b 9f 6e' (octetos separados por espacios)
            if not nueva:
                raise ValueError(f"MAC inválida: '{str(mac)[:40]}'. Usa el formato XX:XX:XX:XX:XX:XX (12 dígitos hexadecimales, sin 00:… ni FF:… de relleno).")
            if int(nueva[:2], 16) & 1:
                raise ValueError(f"MAC inválida: {nueva} es una dirección multicast (el primer octeto no puede ser impar). "
                                 "Revisa que la hayas copiado completa.")
            dueno = c.execute("SELECT nombre FROM pcb_inventario WHERE mac = ? AND id <> ?", (nueva, pcb_id)).fetchone()
            if dueno:
                raise ConflictoError(f"La MAC {nueva} ya pertenece a {dueno['nombre']}.")
        if nueva == p["mac"]:
            return p
        try:
            c.execute("UPDATE pcb_inventario SET mac=?, updated_at=? WHERE id=?", (nueva, _ahora(), pcb_id))
        except sqlite3.IntegrityError as ex:  # red de seguridad: índice único
            raise ConflictoError(f"La MAC {nueva} ya está registrada ({ex}).")
        if p["tarjeta_id"]:
            c.execute("UPDATE tarjetas_produccion SET updated_at=? WHERE id=?", (_ahora(), p["tarjeta_id"]))
        db.log_evento("MAC_GUARDADA", p["tarjeta_lote_id"], p["nombre"], nueva or "(borrada)", operador, conn=c)
        return _pcb_por_id(c, pcb_id)
    return db._con_conn(conn, db_path, _e, escribe=True)


# ============================================================================
# Tarjetas: alta, asignación, reemplazo, disolución
# ============================================================================
def _pcb_para_ranura(c: sqlite3.Connection, pcb_id: int, ranura: str) -> Dict[str, Any]:
    p = _pcb_o_error(c, pcb_id)
    if p["tipo"] != ranura:
        raise ValueError(f"{p['nombre']} es {p['tipo']}: no puede ir en la ranura {ranura}.")
    if p["estado_ciclo"] != "DISPONIBLE":
        donde = f" (ya está en la tarjeta {p['id_tarjeta_num']})" if p["tarjeta_id"] else ""
        extra = " Confirma primero el lote de recepción." if p["estado_ciclo"] == "RECIBIDA" else ""
        raise ConflictoError(f"{p['nombre']} no está disponible: {p['estado_ciclo']}{donde}.{extra}")
    return p


def _liberar_pcb(c: sqlite3.Connection, pcb_id: int, falla: bool) -> None:
    if falla:
        c.execute("UPDATE pcb_inventario SET estado_ciclo='FALLA', estado_pcb='FALLA', updated_at=? WHERE id=?", (_ahora(), pcb_id))
    else:
        c.execute("UPDATE pcb_inventario SET estado_ciclo='DISPONIBLE', estado_pcb='PENDIENTE', updated_at=? WHERE id=?",
                  (_ahora(), pcb_id))


def _reset_pruebas(c: sqlite3.Connection, tarjeta_id: int) -> None:
    c.execute("INSERT OR IGNORE INTO pruebas_historial (tarjeta_id) VALUES (?)", (tarjeta_id,))
    c.execute("UPDATE pruebas_historial SET soldadura='PENDIENTE', programacion='PENDIENTE', prueba_pcb='PENDIENTE', "
              "integracion='PENDIENTE', prueba_final='PENDIENTE', estado_general='PENDIENTE', updated_at=? WHERE tarjeta_id=?",
              (_ahora(), tarjeta_id))


def _normalizar_num_tarjeta(valor: Optional[str]) -> str:
    s = str(valor or "").strip()
    if not re.fullmatch(r"\d{1,4}", s):
        raise ValueError(f"Número de tarjeta inválido: '{valor}'. Debe tener de 1 a 4 dígitos.")
    return s.zfill(4)


def _crear_tarjeta_tx(c: sqlite3.Connection, lote_id: int, id_num: Optional[str], r1: Optional[int], r2: Optional[int],
                      r3: Optional[int], operador: Optional[str]) -> Dict[str, Any]:
    pcbs = {}
    for ranura, pid in (("R1", r1), ("R2", r2), ("R3", r3)):
        if pid:
            pcbs[ranura] = _pcb_para_ranura(c, pid, ranura)
    if not pcbs:
        raise ValueError("Indica al menos una PCB (R1, R2 o R3) para armar la tarjeta.")
    if id_num:
        numero = _normalizar_num_tarjeta(id_num)
    elif "R1" in pcbs:
        numero = pcbs["R1"]["serie"]
    else:
        raise ValueError("Indica id_tarjeta_num o una PCB R1 (el número de la tarjeta sale de la serie de su R1).")
    if c.execute("SELECT 1 FROM tarjetas_produccion WHERE lote_id=? AND id_tarjeta_num=?", (lote_id, numero)).fetchone():
        raise ConflictoError(f"Ya existe la tarjeta {numero} en este lote.")
    tid = c.execute("INSERT INTO tarjetas_produccion (lote_id, id_tarjeta_num, pcb_r1_id, pcb_r2_id, pcb_r3_id) VALUES (?,?,?,?,?)",
                    (lote_id, numero, r1 or None, r2 or None, r3 or None)).lastrowid
    c.execute("INSERT INTO pruebas_historial (tarjeta_id) VALUES (?)", (tid,))
    for p in pcbs.values():
        c.execute("UPDATE pcb_inventario SET estado_ciclo='ASIGNADA', updated_at=? WHERE id=?", (_ahora(), p["id"]))
    db.recalcular_general(c, tid)
    db.sincronizar_estado_pcb(c, tid)
    db.log_evento("TARJETA_CREADA", lote_id, numero, " | ".join(f"{k}: {v['nombre']}" for k, v in pcbs.items()), operador, conn=c)
    return db.get_tarjeta_by_id(tid, c)


def crear_tarjeta(lote_id: Optional[int] = None, id_tarjeta_num: Optional[str] = None, r1_id: Optional[int] = None,
                  r2_id: Optional[int] = None, r3_id: Optional[int] = None, operador: Optional[str] = None,
                  conn: Optional[sqlite3.Connection] = None, db_path: Optional[Path] = None) -> Dict[str, Any]:
    """Alta manual de una tarjeta (permite tarjetas impares: R1 0021 + R2 0010)."""
    def _e(c):
        lid = db.resolver_lote_id(c, lote_id)
        return _crear_tarjeta_tx(c, lid, id_tarjeta_num, r1_id, r2_id, r3_id, operador)
    return db._con_conn(conn, db_path, _e, escribe=True)


# ============================================================================
# Firmware (versión con la que se programó cada R1/R2; la R3 no lleva firmware) y su catálogo
# ============================================================================
_FW_RE = re.compile(r"^[A-Za-z0-9._+ -]{1,40}$")


def _validar_firmware(valor: Optional[str]) -> Optional[str]:
    v = (valor or "").strip()
    if not v:
        return None
    if not _FW_RE.match(v):
        raise ValueError("Firmware inválido: usa letras, números, punto, guion o + (hasta 40 caracteres), por ejemplo 4.1.")
    return v


def _set_firmware_tx(c: sqlite3.Connection, pcb_id: int, firmware: Optional[str], operador: Optional[str]) -> Dict[str, Any]:
    p = _pcb_o_error(c, pcb_id)
    if p["tipo"] not in TIPOS_CON_MAC:
        raise ValueError(f"{p['nombre']} es R3: la R3 no lleva firmware.")
    if p["estado_ciclo"] == "BAJA":
        raise ConflictoError(f"{p['nombre']} está dada de baja.")
    fw = _validar_firmware(firmware)
    if fw == p.get("firmware"):
        return p
    c.execute("UPDATE pcb_inventario SET firmware=?, updated_at=? WHERE id=?", (fw, _ahora(), pcb_id))
    if fw:  # una versión nueva queda disponible en el catálogo (y en las listas del Excel al sincronizar)
        c.execute("INSERT OR IGNORE INTO firmware_catalogo (rol, version, orden) VALUES (?,?,"
                  "COALESCE((SELECT MAX(orden) FROM firmware_catalogo WHERE rol = ?), 0) + 1)", (p["tipo"], fw, p["tipo"]))
    if p["tarjeta_id"]:
        c.execute("UPDATE tarjetas_produccion SET updated_at=? WHERE id=?", (_ahora(), p["tarjeta_id"]))
    db.log_evento("FIRMWARE_GUARDADO", p["tarjeta_lote_id"], p["nombre"], f"FW {fw}" if fw else "FW borrado", operador, conn=c)
    return _pcb_por_id(c, pcb_id)


def set_firmware(pcb_id: int, firmware: Optional[str], operador: Optional[str] = None,
                 conn: Optional[sqlite3.Connection] = None, db_path: Optional[Path] = None) -> Dict[str, Any]:
    return db._con_conn(conn, db_path, lambda c: _set_firmware_tx(c, pcb_id, firmware, operador), escribe=True)


def contar_macs_hoy(conn: Optional[sqlite3.Connection] = None, db_path: Optional[Path] = None) -> int:
    """MAC guardadas HOY (hora local) por cualquier operador o equipo. Sale de la bitácora: una MAC borrada no cuenta.
    La bitácora guarda la hora en UTC, por eso se convierte a hora local antes de comparar el día."""
    def _q(c):
        return c.execute("SELECT COUNT(*) FROM escaneos WHERE evento = 'MAC_GUARDADA' AND COALESCE(detalle, '') <> '(borrada)' "
                         "AND date(creado_en, 'localtime') = date('now', 'localtime')").fetchone()[0]
    return db._con_conn(conn, db_path, _q)


def guardar_programacion(pcb_id: int, mac: str, firmware: Optional[str] = None, operador: Optional[str] = None,
                         conn: Optional[sqlite3.Connection] = None, db_path: Optional[Path] = None) -> Dict[str, Any]:
    """MAC + firmware de una R1/R2 recién programada, en una sola transacción (si algo falla no se guarda nada)."""
    def _e(c):
        set_mac(pcb_id, mac, operador, conn=c)
        if firmware is not None:
            _set_firmware_tx(c, pcb_id, firmware, operador)
        return _pcb_por_id(c, pcb_id)
    return db._con_conn(conn, db_path, _e, escribe=True)


class _Simulacion(Exception):
    """Para revertir la transacción de una simulación."""


def programar_lote(items: List[Dict[str, Any]], simular: bool = False, operador: Optional[str] = None,
                   db_path: Optional[Path] = None) -> Dict[str, Any]:
    """MAC (+ firmware) de muchas R1/R2 de una vez, con resultado POR FILA: las que están bien se guardan y las que fallan
    (MAC repetida, placa inexistente, R3, formato) se reportan sin frenar a las demás. Una MAC repetida dentro del mismo lote
    también se detecta. Con `simular=True` no se guarda nada (vista previa)."""
    resultados: List[Dict[str, Any]] = []
    try:
        with db.transaction(db_path) as c:
            for n, it in enumerate(items):
                fila: Dict[str, Any] = {"indice": n, "ok": False, "nombre": it.get("nombre"), "pcb_id": it.get("pcb_id"), "mac": it.get("mac")}
                c.execute("SAVEPOINT fila_prog")   # si algo de la fila falla (p. ej. firmware inválido) no queda la MAC a medias
                try:
                    pid = it.get("pcb_id")
                    if not pid:
                        try:
                            q = parsear_qr(it.get("nombre"))
                        except ValueError:
                            q = None
                        if not q:
                            raise ValueError("Indica la placa (TQT-R1-V30-0021) o su id.")
                        r = c.execute("SELECT id FROM pcb_inventario WHERE tipo=? AND version=? AND serie=?",
                                      (q["tipo"], q["version"], q["serie"])).fetchone()
                        if not r:
                            raise NoEncontradoError(f"{q['nombre']} no está registrada.")
                        pid = r["id"]
                    pcb = guardar_programacion(pid, it.get("mac") or "", it.get("firmware"), operador, conn=c)
                    fila.update(ok=True, pcb_id=pid, nombre=pcb["nombre"], mac=pcb["mac"], firmware=pcb.get("firmware"), pcb=pcb)
                except NoEncontradoError as e:
                    fila.update(error=str(e), codigo=404)
                except ConflictoError as e:
                    fila.update(error=str(e), codigo=409)
                except ValueError as e:
                    fila.update(error=str(e), codigo=400)
                if fila["ok"]:
                    c.execute("RELEASE fila_prog")
                else:
                    c.execute("ROLLBACK TO fila_prog")
                    c.execute("RELEASE fila_prog")
                resultados.append(fila)
            if simular:
                raise _Simulacion()
    except _Simulacion:
        pass
    ok = sum(1 for r in resultados if r["ok"])
    return {"simulado": simular, "total": len(resultados), "guardadas": ok, "fallidas": len(resultados) - ok, "resultados": resultados}


def listar_firmware(conn: Optional[sqlite3.Connection] = None, db_path: Optional[Path] = None) -> Dict[str, List[str]]:
    """Catálogo de versiones de firmware: {'R1': [...Principal...], 'R2': [...Respaldo...]}."""
    def _q(c):
        r: Dict[str, List[str]] = {"R1": [], "R2": []}
        for f in c.execute("SELECT rol, version FROM firmware_catalogo ORDER BY rol, orden, id"):
            r[f["rol"]].append(f["version"])
        return r
    return db._con_conn(conn, db_path, _q)


def agregar_firmware(rol: str, version: str, conn: Optional[sqlite3.Connection] = None, db_path: Optional[Path] = None) -> Dict[str, List[str]]:
    rol = (rol or "").strip().upper()
    if rol not in TIPOS_CON_MAC:
        raise ValueError("El rol del firmware debe ser R1 (Principal) o R2 (Respaldo).")
    v = _validar_firmware(version)
    if not v:
        raise ValueError("Escribe la versión de firmware.")

    def _e(c):
        c.execute("INSERT OR IGNORE INTO firmware_catalogo (rol, version, orden) VALUES (?,?,"
                  "COALESCE((SELECT MAX(orden) FROM firmware_catalogo WHERE rol = ?), 0) + 1)", (rol, v, rol))
        db.log_evento("FIRMWARE_CATALOGO", None, rol, f"Versión {v} agregada al catálogo", conn=c)
        return listar_firmware(c)
    return db._con_conn(conn, db_path, _e, escribe=True)


def quitar_firmware(rol: str, version: str, conn: Optional[sqlite3.Connection] = None, db_path: Optional[Path] = None) -> Dict[str, List[str]]:
    rol = (rol or "").strip().upper()

    def _e(c):
        n = c.execute("DELETE FROM firmware_catalogo WHERE rol = ? AND version = ?", (rol, (version or "").strip())).rowcount
        if not n:
            raise NoEncontradoError(f"La versión {version} no está en el catálogo de {rol}.")
        db.log_evento("FIRMWARE_CATALOGO", None, rol, f"Versión {version} quitada del catálogo", conn=c)
        return listar_firmware(c)
    return db._con_conn(conn, db_path, _e, escribe=True)


_CAMPOS_DATOS = ("firmware_r1", "firmware_r2", "semana_produccion", "fecha_proyectada", "fecha_real",
                 "fecha_llegada", "fecha_finalizado", "gabinete")
GABINETES = ("Quintalock", "Translock")


def actualizar_datos_tarjeta(tarjeta_id: int, datos: Dict[str, Any], operador: Optional[str] = None,
                             conn: Optional[sqlite3.Connection] = None, db_path: Optional[Path] = None) -> Dict[str, Any]:
    """Firmware, semana y fechas de la tarjeta (las columnas de captura del Excel). Solo cambia las claves presentes en
    `datos`; una cadena vacía borra el valor. Las fechas deben ser YYYY-MM-DD."""
    def _e(c):
        t = db.get_tarjeta_by_id(tarjeta_id, c)
        if not t:
            raise NoEncontradoError(f"Tarjeta con ID {tarjeta_id} no encontrada.")
        cambios: Dict[str, Any] = {}
        for k in _CAMPOS_DATOS:
            if k not in datos or datos[k] is None:
                continue
            v = datos[k]
            if k in ("firmware_r1", "firmware_r2"):
                pid = t["pcb_r1_id" if k == "firmware_r1" else "pcb_r2_id"]
                if pid:   # el firmware vive en la PCB de esa ranura; se limpia el dato heredado de la tarjeta
                    _set_firmware_tx(c, pid, None if v == "" else v, operador)
                    cambios[k] = None
                    continue
                v = _validar_firmware(v)
            if k == "gabinete" and v != "":
                v = next((g for g in GABINETES if g.lower() == str(v).strip().lower()), None)
                if v is None:
                    raise ValueError(f"gabinete: usa {' o '.join(GABINETES)}.")
            if k.startswith("fecha_") and v != "":
                try:
                    datetime.strptime(str(v), "%Y-%m-%d")
                except ValueError:
                    raise ValueError(f"{k}: fecha inválida '{v}'. Usa el formato YYYY-MM-DD.")
            cambios[k] = None if v == "" else v
        if cambios:
            sets = ", ".join(f"{k} = ?" for k in cambios)  # las claves salen de la lista blanca _CAMPOS_DATOS
            c.execute(f"UPDATE tarjetas_produccion SET {sets}, updated_at = ? WHERE id = ?",
                      [*cambios.values(), _ahora(), tarjeta_id])
            db.log_evento("TARJETA_DATOS", t["lote_id"], t["id_tarjeta_num"], ", ".join(f"{k}={v}" for k, v in cambios.items()),
                          operador, conn=c)
        return db.get_tarjeta_by_id(tarjeta_id, c)
    return db._con_conn(conn, db_path, _e, escribe=True)


def _asignar_tx(c: sqlite3.Connection, tarjeta_id: int, ranura: str, pcb_id: Optional[int], marcar_falla: bool,
                conservar_pruebas: bool, operador: Optional[str]) -> Dict[str, Any]:
    t = db.get_tarjeta_by_id(tarjeta_id, c)
    if not t:
        raise NoEncontradoError(f"Tarjeta con ID {tarjeta_id} no encontrada.")
    col = _COL_RANURA[ranura]
    actual = t[col]
    if pcb_id and pcb_id == actual:
        return t
    nueva = _pcb_para_ranura(c, pcb_id, ranura) if pcb_id else None

    if actual:
        _liberar_pcb(c, actual, marcar_falla)
    if nueva:
        c.execute("UPDATE pcb_inventario SET estado_ciclo='ASIGNADA', updated_at=? WHERE id=?", (_ahora(), nueva["id"]))
    c.execute(f"UPDATE tarjetas_produccion SET {col} = ?, updated_at = ? WHERE id = ?", (pcb_id or None, _ahora(), tarjeta_id))

    reiniciadas = False
    if nueva and not conservar_pruebas:
        # Se montó una PCB distinta (reemplazo o ranura vacía que se llena): hay que soldar, programar y probar de nuevo.
        # Solo liberar una ranura NO borra pruebas (la tarjeta queda incompleta y nunca LIBERADA).
        previas = c.execute("SELECT soldadura, programacion, prueba_pcb, integracion, prueba_final FROM pruebas_historial "
                            "WHERE tarjeta_id = ?", (tarjeta_id,)).fetchone()
        if previas and any(previas[k] != "PENDIENTE" for k in ETAPA_KEYS):
            _reset_pruebas(c, tarjeta_id)
            reiniciadas = True
    db.recalcular_general(c, tarjeta_id)
    db.sincronizar_estado_pcb(c, tarjeta_id)

    anterior = t[f"nombre_{ranura.lower()}"]
    if actual and nueva:
        evento, det = "PCB_REEMPLAZO", f"{ranura}: {anterior} -> {nueva['nombre']}" + (" (falla)" if marcar_falla else "")
    elif nueva:
        evento, det = "PCB_ASIGNADA", f"{ranura}: {nueva['nombre']}"
    else:
        evento, det = "PCB_LIBERADA", f"{ranura}: {anterior}" + (" (falla)" if marcar_falla else "")
    if reiniciadas:
        det += " | pruebas reiniciadas"
    db.log_evento(evento, t["lote_id"], t["id_tarjeta_num"], det, operador, conn=c)
    return db.get_tarjeta_by_id(tarjeta_id, c)


def asignar_pcb(tarjeta_id: int, ranura: str, pcb_id: Optional[int], marcar_falla: bool = False,
                conservar_pruebas: bool = False, operador: Optional[str] = None,
                conn: Optional[sqlite3.Connection] = None, db_path: Optional[Path] = None) -> Dict[str, Any]:
    """Asigna, reemplaza o libera (pcb_id=None) la PCB de una ranura. La PCB anterior vuelve a DISPONIBLE (o FALLA si
    `marcar_falla`). Al MONTAR una PCB distinta las pruebas de la tarjeta se reinician (salvo `conservar_pruebas`), porque la
    PCB nueva hay que soldarla, programarla y probarla otra vez; solo liberar una ranura conserva las pruebas."""
    rn = str(ranura or "").strip().upper()
    if rn not in RANURAS:
        raise ValueError(f"Ranura inválida: '{ranura}'. Debe ser R1, R2 o R3.")
    return db._con_conn(conn, db_path, lambda c: _asignar_tx(c, tarjeta_id, rn, pcb_id, marcar_falla, conservar_pruebas, operador),
                        escribe=True)


def marcar_falla(pcb_id: int, motivo: Optional[str] = None, reemplazo_id: Optional[int] = None,
                 conservar_pruebas: bool = False, operador: Optional[str] = None,
                 conn: Optional[sqlite3.Connection] = None, db_path: Optional[Path] = None) -> Dict[str, Any]:
    """Marca una PCB como FALLA, la saca de su tarjeta y, si se indica, monta el reemplazo en la misma ranura."""
    def _e(c):
        p = _pcb_o_error(c, pcb_id)
        if p["estado_ciclo"] == "BAJA":
            raise ConflictoError(f"{p['nombre']} está dada de baja.")
        if reemplazo_id and reemplazo_id == pcb_id:
            raise ValueError("El reemplazo no puede ser la misma PCB que falló.")
        tarjeta = None
        if p["tarjeta_id"]:
            tarjeta = _asignar_tx(c, p["tarjeta_id"], p["ranura"], reemplazo_id, True, conservar_pruebas, operador)
        else:
            if reemplazo_id:
                raise ValueError(f"{p['nombre']} no está en ninguna tarjeta: no hay dónde montar el reemplazo.")
            c.execute("UPDATE pcb_inventario SET estado_ciclo='FALLA', estado_pcb='FALLA', updated_at=? WHERE id=?", (_ahora(), pcb_id))
        db.log_evento("PCB_FALLA", p["tarjeta_lote_id"], p["nombre"], motivo or "sin motivo", operador, conn=c)
        return {"pcb": _pcb_por_id(c, pcb_id), "tarjeta": tarjeta,
                "reemplazo": _pcb_por_id(c, reemplazo_id) if reemplazo_id else None}
    return db._con_conn(conn, db_path, _e, escribe=True)


def disolver_tarjeta(tarjeta_id: int, forzar: bool = False, operador: Optional[str] = None,
                     conn: Optional[sqlite3.Connection] = None, db_path: Optional[Path] = None) -> Dict[str, Any]:
    """Deshace la tarjeta y devuelve sus PCB a DISPONIBLE. 409 si ya tiene pruebas avanzadas (salvo `forzar`)."""
    def _e(c):
        t = db.get_tarjeta_by_id(tarjeta_id, c)
        if not t:
            raise NoEncontradoError(f"Tarjeta con ID {tarjeta_id} no encontrada.")
        avanzadas = [k for k in ETAPA_KEYS if t[k] != "PENDIENTE"]
        if avanzadas and not forzar:
            raise ConflictoError(f"La tarjeta {t['id_tarjeta_num']} ya tiene pruebas registradas ({', '.join(avanzadas)}). "
                                 "Confirma para disolverla de todos modos.")
        liberadas = []
        for r in ("r1", "r2", "r3"):
            if t[r]:
                _liberar_pcb(c, t[r]["id"], False)
                liberadas.append(t[r]["nombre"])
        c.execute("DELETE FROM tarjetas_produccion WHERE id = ?", (tarjeta_id,))
        db.log_evento("TARJETA_DISUELTA", t["lote_id"], t["id_tarjeta_num"], ", ".join(liberadas), operador, conn=c)
        return {"id": tarjeta_id, "id_tarjeta_num": t["id_tarjeta_num"], "lote_id": t["lote_id"], "liberadas": liberadas}
    return db._con_conn(conn, db_path, _e, escribe=True)


def disolver_masivo(ids: Optional[List[int]] = None, todas: bool = False, lote_id: Optional[int] = None,
                    forzar: bool = False, operador: Optional[str] = None,
                    conn: Optional[sqlite3.Connection] = None, db_path: Optional[Path] = None) -> Dict[str, Any]:
    """Desempareja varias tarjetas a la vez (las elegidas o todas las del lote). Sus placas vuelven a DISPONIBLE. Las tarjetas
    con pruebas registradas se omiten (y se reportan) salvo `forzar`."""
    if not todas and not ids:
        raise ValueError("Indica las tarjetas a desemparejar o todas=true.")

    def _e(c):
        if todas:
            lid = db.resolver_lote_id(c, lote_id)
            objetivo = [r[0] for r in c.execute("SELECT id FROM tarjetas_produccion WHERE lote_id = ? ORDER BY id", (lid,))]
        else:
            objetivo = list(dict.fromkeys(ids))
        disueltas, omitidas, liberadas = [], [], 0
        for tid in objetivo:
            try:
                r = disolver_tarjeta(tid, forzar, operador, conn=c)
            except (ConflictoError, NoEncontradoError) as ex:
                omitidas.append({"id": tid, "motivo": str(ex.detail if hasattr(ex, "detail") else ex)})
                continue
            disueltas.append(r)
            liberadas += len(r["liberadas"])
        return {"disueltas": disueltas, "omitidas": omitidas, "liberadas": liberadas}
    return db._con_conn(conn, db_path, _e, escribe=True)


# ============================================================================
# Emparejado por serie
# ============================================================================
def _agrupar_disponibles(c: sqlite3.Connection) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
    por_serie: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
    for r in c.execute(f"{_SELECT_PCB} WHERE p.estado_ciclo = 'DISPONIBLE' ORDER BY p.serie, p.id"):
        d = pcb_a_dict(r)
        por_serie.setdefault(d["serie"], {"R1": [], "R2": [], "R3": []})[d["tipo"]].append(d)
    return por_serie


def _planificar(c: sqlite3.Connection, lid: int, r3_auto: bool = False) -> Dict[str, Any]:
    """Plan de emparejado en orden numérico: 1) parejas (R1+R2 del mismo número; con su R3 si hay); 2) con lo que sobra,
    R1 y R2 en orden (la más baja con la más baja: tarjetas impares, p. ej. R1 0018 + R2 0021); 3) R3 sueltas, del mismo número
    o, si no hay, las que sobran en orden, a las tarjetas del plan que aún no tienen R3."""
    existentes = {r[0] for r in c.execute("SELECT id_tarjeta_num FROM tarjetas_produccion WHERE lote_id = ?", (lid,))}
    grupos = _agrupar_disponibles(c)
    completas, ocupadas, usados = [], [], set()
    for serie in sorted(grupos):
        g = grupos[serie]
        if g["R1"] and g["R2"]:
            if serie in existentes:
                ocupadas.append(serie)
                continue
            r3 = g["R3"][0] if g["R3"] else None
            completas.append({"serie": serie, "id_tarjeta_num": serie, "r1": g["R1"][0], "r2": g["R2"][0], "r3": r3})
            usados.update(x["id"] for x in (g["R1"][0], g["R2"][0]) + ((r3,) if r3 else ()))
    todas = {t: sorted((x for g in grupos.values() for x in g[t] if x["id"] not in usados), key=lambda x: (x["serie"], x["id"]))
             for t in TIPOS_PCB}
    reservados = existentes | {x["serie"] for x in completas}
    impares, sin_numero = [], []
    for r1, r2 in zip(todas["R1"], todas["R2"]):
        num = next((n for n in (r1["serie"], r2["serie"]) if n not in reservados), None)
        if not num:
            sin_numero.append((r1, r2))
            continue
        reservados.add(num)
        impares.append({"serie": num, "id_tarjeta_num": num, "r1": r1, "r2": r2, "r3": None, "impar": True})
    usados_r3 = {x["r3"]["id"] for x in completas if x["r3"]}
    r3_libres = [x for x in todas["R3"] if x["id"] not in usados_r3]
    for it in impares:
        mismo = next((x for x in r3_libres if x["serie"] == it["serie"]), None)
        if mismo:
            it["r3"] = mismo
            r3_libres.remove(mismo)
    for it in impares:
        if not it["r3"] and r3_libres:
            it["r3"] = r3_libres.pop(0)
    r1_sob = todas["R1"][len(impares) + len(sin_numero):]
    r2_sob = todas["R2"][len(impares) + len(sin_numero):]
    r3_por_serie = {x["serie"]: x for x in reversed(r3_libres)}
    r3_pendientes = []
    for t in c.execute("SELECT id, id_tarjeta_num FROM tarjetas_produccion WHERE lote_id = ? AND pcb_r3_id IS NULL "
                       "ORDER BY id_tarjeta_num", (lid,)):
        x = r3_por_serie.get(t["id_tarjeta_num"])
        if x:
            r3_pendientes.append({"tarjeta_id": t["id"], "id_tarjeta_num": t["id_tarjeta_num"], "r3": x})
    if not r3_auto:  # R3 manual: el emparejado automático solo une R1 + R2; la R3 se asigna a mano en cada tarjeta
        for it in completas + impares:
            it["r3"] = None
        r3_pendientes = []
    return {"completas": completas, "impares": impares, "ocupadas": ocupadas, "sin_numero": sin_numero, "r3_pendientes": r3_pendientes,
            "sobran": {"R1": r1_sob, "R2": r2_sob, "R3": r3_libres}}


def sugerencias(lote_id: Optional[int] = None, r3_auto: bool = False, conn: Optional[sqlite3.Connection] = None,
                db_path: Optional[Path] = None) -> Dict[str, Any]:
    """Qué se puede emparejar hoy: `completas` (R1+R2 del mismo número, R3 si hay), `impares` (R1 y R2 de distinto número que
    sobran, en orden), `incompletas` (falta R1 o R2), `ocupadas` (series cuya tarjeta ya existe en el lote) y las `sueltas` por tipo."""
    def _q(c):
        lid = db.resolver_lote_id(c, lote_id)
        plan = _planificar(c, lid, r3_auto)
        incompletas = []
        sueltas: Dict[str, List[Dict[str, Any]]] = {"R1": [], "R2": [], "R3": []}
        for serie, g in sorted(_agrupar_disponibles(c).items()):
            for tipo in TIPOS_PCB:
                sueltas[tipo].extend(g[tipo])
            r1, r2, r3 = (g[t][0] if g[t] else None for t in TIPOS_PCB)
            if not (r1 and r2):
                incompletas.append({"serie": serie, "faltan": [t for t, x in (("R1", r1), ("R2", r2)) if not x],
                                    "r1": r1, "r2": r2, "r3": r3})
        return {"lote_id": lid, "completas": plan["completas"], "impares": plan["impares"], "incompletas": incompletas,
                "r3_pendientes": plan["r3_pendientes"], "ocupadas": plan["ocupadas"], "sueltas": sueltas}
    return db._con_conn(conn, db_path, _q)


def emparejar_auto(lote_id: Optional[int] = None, series: Optional[List[str]] = None, operador: Optional[str] = None,
                   r3_auto: bool = False, conn: Optional[sqlite3.Connection] = None, db_path: Optional[Path] = None) -> Dict[str, Any]:
    """Sin `series`: crea primero las tarjetas de las parejas (mismo número) y después las impares con lo que sobra, todo en
    orden numérico. Con `series`: solo esas parejas. La R3 va aparte: con `r3_auto` (par e impar por número, y montando las que
    llegaron después) o, por defecto, a mano. Lo que no se puede emparejar se reporta en `omitidas` con su motivo."""
    def _e(c):
        lid = db.resolver_lote_id(c, lote_id)
        plan = _planificar(c, lid, r3_auto)
        por_serie = {x["serie"]: x for x in plan["completas"]}
        pedidas = [normalizar_serie(s) for s in dict.fromkeys(series)] if series else list(por_serie)
        creadas, omitidas = [], []
        for s in pedidas:
            x = por_serie.get(s)
            if not x:
                motivo = ("ya existe una tarjeta con ese número en el lote" if s in plan["ocupadas"]
                          else "faltan R1 o R2 disponibles con ese número")
                omitidas.append({"serie": s, "motivo": motivo})
                continue
            creadas.append(_crear_tarjeta_tx(c, lid, s, x["r1"]["id"], x["r2"]["id"], x["r3"]["id"] if x["r3"] else None, operador))
        if not series:
            for x in plan["impares"]:
                creadas.append(_crear_tarjeta_tx(c, lid, x["id_tarjeta_num"], x["r1"]["id"], x["r2"]["id"],
                                                 x["r3"]["id"] if x["r3"] else None, operador))
            for r1, r2 in plan["sin_numero"]:
                omitidas.append({"serie": r1["serie"], "motivo": f"{r1['nombre']} + {r2['nombre']}: sus números ya tienen tarjeta"})
        r3_asignadas = []
        if not series:
            # R3 que llegaron después: se montan en la tarjeta del mismo número (sin borrar sus pruebas)
            for x in plan["r3_pendientes"]:
                _asignar_tx(c, x["tarjeta_id"], "R3", x["r3"]["id"], False, True, operador)
                r3_asignadas.append({"id_tarjeta_num": x["id_tarjeta_num"], "r3": x["r3"]["nombre"]})
        return {"lote_id": lid, "creadas": creadas, "omitidas": omitidas, "r3_asignadas": r3_asignadas}
    return db._con_conn(conn, db_path, _e, escribe=True)


# ============================================================================
# Utilidad de importación (Excel) y pruebas
# ============================================================================
def asegurar_pcb(c: sqlite3.Connection, tipo: str, version: str, serie: str, mac: Optional[str] = None,
                 estado_pcb: str = "PENDIENTE", origen: str = "MANUAL") -> int:
    """Devuelve el id de la PCB (tipo, versión, serie); si no existe la crea DISPONIBLE. Si trae MAC y la PCB no
    tenía, se la pone (ConflictoError si esa MAC es de otra PCB). No toca el ciclo de una PCB que ya existe."""
    fila = c.execute("SELECT id, mac FROM pcb_inventario WHERE tipo=? AND version=? AND serie=?", (tipo, version, serie)).fetchone()
    nombre = nombre_pcb(tipo, version, serie)
    if mac and tipo in TIPOS_CON_MAC:
        dueno = c.execute("SELECT id, nombre FROM pcb_inventario WHERE mac = ?", (mac,)).fetchone()
        if dueno and (not fila or dueno["id"] != fila["id"]):
            raise ConflictoError(f"La MAC {mac} ya pertenece a {dueno['nombre']}.")
    else:
        mac = None
    if fila:
        if mac and not fila["mac"]:
            c.execute("UPDATE pcb_inventario SET mac=?, updated_at=? WHERE id=?", (mac, _ahora(), fila["id"]))
        return fila["id"]
    return c.execute(
        "INSERT INTO pcb_inventario (tipo, version, serie, nombre, mac, estado_ciclo, estado_pcb, origen, confirmada_en) "
        "VALUES (?,?,?,?,?, 'DISPONIBLE', ?, ?, ?)", (tipo, version, serie, nombre, mac, estado_pcb, origen, _ahora())).lastrowid
