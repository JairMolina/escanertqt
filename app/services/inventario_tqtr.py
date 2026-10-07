"""Inventario TQTR: réplica en SQLite del libro `INVENTARIO_TQTR_26_v.xlsx`.

Hojas del Excel → tablas propias (prefijo `inv_tqtr_`):
- "Registro_inventario"      → inv_tqtr_movimientos (entradas, salidas, devoluciones, garantías).
- "Componentes" (BOM)        → inv_tqtr_componentes + inv_tqtr_productos + inv_tqtr_bom (cantidad por producto final).
- "Configuración"            → inv_tqtr_catalogo (categorías, tipos de movimiento con su efecto, condiciones, unidades, reglas).
- "Dashboard de inventario"  → `dashboard()`: se calcula en Python con las mismas reglas que las fórmulas SUMIFS del Excel.

Reglas del dashboard (fórmulas F/G/H/K/L del Excel):
- Disponible(componente) = Σ efecto·cantidad de los movimientos de ese modelo
  + Σ efecto·cantidad de los movimientos de cada producto final × cantidad del componente en su BOM.
- Consumida = lo mismo pero solo con movimientos de efecto negativo (salidas).
- Ensambles posibles = INT(disponible / cantidad por ensamble), 0 si no hay existencia.
- PCBA posibles R1/R2/R3 = mínimo de los ensambles de su grupo; producto final posible = mínimo de los tres.
- Quintalock / Translock = mínimo entre su caja y el actuador.
El efecto de cada tipo de movimiento es configurable (Entrada +1, Salida −1, Devolución/Garantía +1 según la hoja Configuración).

La primera vez (tablas vacías) se carga la semilla `app/data_seed/inventario_tqtr.json`, generada desde el Excel original.
"""
from __future__ import annotations

import io
import json
import logging
import re
import threading
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.database import db
from app.database.db import _TARJETA_COMPLETA, ConflictoError, NoEncontradoError

SEMILLA = Path(__file__).resolve().parent.parent / "data_seed" / "inventario_tqtr.json"
SEMILLA_COSTOS = Path(__file__).resolve().parent.parent / "data_seed" / "inventario_tqtr_costos.json"
GRUPOS_COSTO = ("R1", "R2", "R3", "Otros")
VARIANTES = ("Quintalock", "Translock")
MONEDAS = ("MXN", "USD")
TIPOS_CATALOGO = ("categoria", "movimiento", "condicion", "unidad", "regla")
GRUPOS = {"R1": "Tarjeta R1", "R2": "Tarjeta R2", "R3": "Tarjeta R3", "A": "Actuador y accesorios", "G": "Gabinete"}
CAJA_QUINTALOCK = "Caja Quintalock Metal Reforzada"
CAJA_TRANSLOCK = "Caja Translock Metal Reforzada"
ACTUADOR = "Actuador lineal de 12 VCD"
_EPS = 1e-9

_lock = threading.Lock()
_listas: set = set()

_DDL = """
CREATE TABLE IF NOT EXISTS inv_tqtr_meta (clave TEXT PRIMARY KEY, valor TEXT);
CREATE TABLE IF NOT EXISTS inv_tqtr_componentes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    grupo TEXT NOT NULL DEFAULT '',
    categoria TEXT NOT NULL DEFAULT '',
    descripcion TEXT NOT NULL UNIQUE,
    cantidad_lote REAL NOT NULL DEFAULT 0,
    unidad_lote TEXT NOT NULL DEFAULT '',
    cantidad_ensamble REAL NOT NULL DEFAULT 0,
    unidad TEXT NOT NULL DEFAULT '',
    proveedor TEXT NOT NULL DEFAULT '',
    unidad_inventario TEXT NOT NULL DEFAULT '',
    notas TEXT NOT NULL DEFAULT '',
    stock_minimo REAL NOT NULL DEFAULT 0,
    en_dashboard INTEGER NOT NULL DEFAULT 1,
    orden INTEGER NOT NULL DEFAULT 0,
    creado_en TEXT NOT NULL DEFAULT (datetime('now')),
    actualizado_en TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS inv_tqtr_productos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL UNIQUE,
    orden INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS inv_tqtr_bom (
    producto_id INTEGER NOT NULL REFERENCES inv_tqtr_productos(id) ON DELETE CASCADE,
    componente_id INTEGER NOT NULL REFERENCES inv_tqtr_componentes(id) ON DELETE CASCADE,
    cantidad REAL NOT NULL,
    PRIMARY KEY (producto_id, componente_id)
);
CREATE TABLE IF NOT EXISTS inv_tqtr_catalogo (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo TEXT NOT NULL,
    valor TEXT NOT NULL,
    efecto REAL,
    descripcion TEXT NOT NULL DEFAULT '',
    orden INTEGER NOT NULL DEFAULT 0,
    UNIQUE (tipo, valor)
);
CREATE TABLE IF NOT EXISTS inv_tqtr_movimientos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT NOT NULL DEFAULT '',
    fecha_entrada TEXT,
    categoria TEXT NOT NULL DEFAULT '',
    modelo TEXT NOT NULL,
    condicion TEXT NOT NULL DEFAULT '',
    movimiento TEXT NOT NULL,
    cantidad REAL NOT NULL,
    unidad TEXT NOT NULL DEFAULT '',
    fecha_salida TEXT,
    destino TEXT NOT NULL DEFAULT '',
    notas TEXT NOT NULL DEFAULT '',
    creado_en TEXT NOT NULL DEFAULT (datetime('now')),
    actualizado_en TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS inv_tqtr_costos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    componente_id INTEGER REFERENCES inv_tqtr_componentes(id) ON DELETE SET NULL,
    descripcion TEXT NOT NULL,
    categoria TEXT NOT NULL DEFAULT '',
    grupo TEXT NOT NULL DEFAULT 'Otros',
    costo_unitario REAL NOT NULL DEFAULT 0,
    unidad TEXT NOT NULL DEFAULT '',
    moneda TEXT NOT NULL DEFAULT 'MXN',
    cantidad_armado REAL NOT NULL DEFAULT 0,
    proveedor TEXT NOT NULL DEFAULT '',
    variante TEXT NOT NULL DEFAULT '',
    incluido INTEGER NOT NULL DEFAULT 1,
    cantidad_consumo REAL,
    notas TEXT NOT NULL DEFAULT '',
    orden INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS inv_tqtr_consumos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tarjeta_id INTEGER NOT NULL,
    tarjeta_num TEXT NOT NULL DEFAULT '',
    lote_id INTEGER,
    componente_id INTEGER REFERENCES inv_tqtr_componentes(id) ON DELETE SET NULL,
    costo_id INTEGER REFERENCES inv_tqtr_costos(id) ON DELETE SET NULL,
    descripcion TEXT NOT NULL DEFAULT '',
    origen TEXT NOT NULL,
    variante TEXT NOT NULL DEFAULT '',
    devolvible INTEGER NOT NULL DEFAULT 0,
    cantidad_estandar REAL NOT NULL DEFAULT 0,
    cantidad_real REAL NOT NULL DEFAULT 0,
    estado TEXT NOT NULL DEFAULT 'activo',
    nota TEXT NOT NULL DEFAULT '',
    creado_en TEXT NOT NULL DEFAULT (datetime('now')),
    actualizado_en TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (tarjeta_id, componente_id)
);
CREATE TABLE IF NOT EXISTS inv_tqtr_tarjetas_borradas (
    tarjeta_id INTEGER PRIMARY KEY,
    id_tarjeta_num TEXT NOT NULL DEFAULT '',
    lote_id INTEGER,
    fecha_finalizado TEXT,
    gabinete TEXT,
    borrada_en TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_inv_tqtr_cons_tarjeta ON inv_tqtr_consumos(tarjeta_id);
CREATE INDEX IF NOT EXISTS ix_inv_tqtr_mov_modelo ON inv_tqtr_movimientos(modelo);
CREATE INDEX IF NOT EXISTS ix_inv_tqtr_mov_fecha ON inv_tqtr_movimientos(fecha_entrada);
"""

# Efecto en la existencia de cada tipo de movimiento (hoja Configuración, "Reglas de inventario").
_EFECTOS_SEMILLA = {"entrada": 1.0, "salida": -1.0, "devolución por defecto": 0.0, "desinstalado o garantía": 0.0}
# v1.3.40: las devoluciones y garantías NO suman a disponible; quedan "Devueltas / en revisión" (columna `revision` del catálogo:
# +1 entra a revisión, −1 sale) hasta reclasificarlas con "Pasar a disponible" (efecto +1) o "Dar de baja" (efecto 0).
MOV_A_DISPONIBLE = "Reclasificado a disponible"
MOV_BAJA = "Baja de devueltas"


# ----------------------------------------------------------------------------- esquema y semilla
def asegurar(db_path: Optional[Path] = None) -> None:
    """Crea las tablas si faltan y carga la semilla del Excel cuando están vacías (idempotente)."""
    clave = str(db_path or "")
    if clave in _listas:
        return
    with _lock:
        if clave in _listas:
            return
        with db.transaction(db_path) as c:
            for stmt in [s.strip() for s in _DDL.split(";") if s.strip()]:
                c.execute(stmt)
            vacio = not c.execute("SELECT 1 FROM inv_tqtr_componentes LIMIT 1").fetchone() \
                and not c.execute("SELECT 1 FROM inv_tqtr_movimientos LIMIT 1").fetchone()
            sembrado = c.execute("SELECT valor FROM inv_tqtr_meta WHERE clave='semilla'").fetchone()
            if vacio and not sembrado and SEMILLA.exists():
                _cargar_semilla(c, json.loads(SEMILLA.read_text(encoding="utf-8")))
            vacio_c = not c.execute("SELECT 1 FROM inv_tqtr_costos LIMIT 1").fetchone()
            sembrado_c = c.execute("SELECT valor FROM inv_tqtr_meta WHERE clave='semilla_costos'").fetchone()
            if vacio_c and not sembrado_c and SEMILLA_COSTOS.exists():
                _cargar_semilla_costos(c, json.loads(SEMILLA_COSTOS.read_text(encoding="utf-8")))
            _migrar_consumo(c)
            _migrar_1339(c)
            _migrar_1340(c)
            _asegurar_trigger(c)
        _listas.add(clave)


def _asegurar_trigger(c) -> None:
    """Registra cada tarjeta completada que se borre, aunque nadie abra el inventario (la concilia `sincronizar_consumos`)."""
    if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='tarjetas_produccion'").fetchone():
        c.execute("CREATE TRIGGER IF NOT EXISTS inv_tqtr_trg_tarjeta_borrada AFTER DELETE ON tarjetas_produccion "
                  "WHEN OLD.fecha_finalizado IS NOT NULL BEGIN "
                  "INSERT OR REPLACE INTO inv_tqtr_tarjetas_borradas (tarjeta_id, id_tarjeta_num, lote_id, fecha_finalizado, gabinete) "
                  "VALUES (OLD.id, OLD.id_tarjeta_num, OLD.lote_id, OLD.fecha_finalizado, OLD.gabinete); END")


def _migrar_consumo(c) -> None:
    """v1.3.38: cantidad de consumo por armado. Si es NULL se usa `cantidad_armado` (estándar del Excel de costos). El catalizador
    se excluye: Costos lo cuenta en ml (5 y 4 por armado) pero el stock se registra en piezas (0.27 / 0.06 por ensamble en el inventario)."""
    cols = {r[1] for r in c.execute("PRAGMA table_info(inv_tqtr_costos)")}
    if "cantidad_consumo" not in cols:
        c.execute("ALTER TABLE inv_tqtr_costos ADD COLUMN cantidad_consumo REAL")
    if not c.execute("SELECT 1 FROM inv_tqtr_meta WHERE clave='migr_consumo_1338'").fetchone():
        c.execute("UPDATE inv_tqtr_costos SET cantidad_consumo = (SELECT cantidad_ensamble FROM inv_tqtr_componentes WHERE id = componente_id), "
                  "notas = TRIM(notas || ' Consumo por armado tomado del inventario (el stock está en piezas, Costos usa ml).') "
                  "WHERE cantidad_consumo IS NULL AND componente_id IS NOT NULL AND descripcion LIKE 'Catalizador%'")
        c.execute("INSERT OR REPLACE INTO inv_tqtr_meta (clave, valor) VALUES ('migr_consumo_1338', '1')")


def _cargar_semilla(c, s: Dict[str, Any]) -> None:
    for tipo, valores in (s.get("catalogos") or {}).items():
        for i, v in enumerate(valores):
            ef = _EFECTOS_SEMILLA.get(str(v).strip().lower(), 1.0) if tipo == "movimiento" else None
            c.execute("INSERT OR IGNORE INTO inv_tqtr_catalogo (tipo, valor, efecto, orden) VALUES (?,?,?,?)", (tipo, v, ef, i))
    for i, r in enumerate(s.get("reglas") or []):
        c.execute("INSERT OR IGNORE INTO inv_tqtr_catalogo (tipo, valor, descripcion, orden) VALUES ('regla',?,?,?)", (r["clave"], r.get("descripcion") or "", i))
    ids: Dict[str, int] = {}
    for comp in s.get("componentes") or []:
        cur = c.execute(
            "INSERT INTO inv_tqtr_componentes (grupo, categoria, descripcion, cantidad_lote, unidad_lote, cantidad_ensamble, unidad, proveedor,"
            " unidad_inventario, notas, en_dashboard, orden) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (comp.get("grupo") or "", comp.get("categoria") or "", comp["descripcion"], comp.get("cantidad_lote") or 0, comp.get("unidad_lote") or "",
             comp.get("cantidad_ensamble") or 0, comp.get("unidad") or "", comp.get("proveedor") or "", comp.get("unidad_inventario") or "",
             comp.get("notas") or "", 1 if comp.get("en_dashboard", True) else 0, comp.get("orden") or 0))
        ids[comp["descripcion"]] = cur.lastrowid
    for i, p in enumerate(s.get("productos") or []):
        pid = c.execute("INSERT INTO inv_tqtr_productos (nombre, orden) VALUES (?,?)", (p, i)).lastrowid
        for desc, q in ((s.get("bom") or {}).get(p) or {}).items():
            if desc in ids and q:
                c.execute("INSERT INTO inv_tqtr_bom (producto_id, componente_id, cantidad) VALUES (?,?,?)", (pid, ids[desc], q))
    for m in s.get("movimientos") or []:
        c.execute(
            "INSERT INTO inv_tqtr_movimientos (codigo, fecha_entrada, categoria, modelo, condicion, movimiento, cantidad, unidad, fecha_salida, destino, notas)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (m.get("codigo") or "", m.get("fecha_entrada"), m.get("categoria") or "", m["modelo"], m.get("condicion") or "", m["movimiento"],
             m["cantidad"], m.get("unidad") or "", m.get("fecha_salida"), m.get("destino") or "", m.get("notas") or ""))
    c.execute("INSERT OR REPLACE INTO inv_tqtr_meta (clave, valor) VALUES ('semilla', ?)", (s.get("origen") or "semilla",))


def _cargar_semilla_costos(c, s: Dict[str, Any]) -> None:
    """Hoja Componentes + Dashboard de Costos de `Costos_Produccion_TQTR.xlsx` (mismo orden de filas que el inventario)."""
    ids = {r["descripcion"]: r["id"] for r in c.execute("SELECT id, descripcion FROM inv_tqtr_componentes")}
    for it in s.get("costos") or []:
        c.execute(
            "INSERT INTO inv_tqtr_costos (componente_id, descripcion, categoria, grupo, costo_unitario, unidad, moneda, cantidad_armado, proveedor,"
            " variante, incluido, notas, orden) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (ids.get(it.get("componente") or ""), it["descripcion"], it.get("categoria") or "", it.get("grupo") or "Otros", it.get("costo_unitario") or 0,
             it.get("unidad") or "", it.get("moneda") or "MXN", it.get("cantidad_armado") or 0, it.get("proveedor") or "", it.get("variante") or "",
             1 if it.get("incluido", True) else 0, it.get("notas") or "", it.get("orden") or 0))
    par = s.get("parametros") or {}
    for k, v in (("tipo_cambio", par.get("tipo_cambio", 18.5)), ("producto_costeo", par.get("producto", "Translock"))):
        c.execute("INSERT OR IGNORE INTO inv_tqtr_meta (clave, valor) VALUES (?, ?)", (k, str(v)))
    c.execute("INSERT OR REPLACE INTO inv_tqtr_meta (clave, valor) VALUES ('semilla_costos', ?)", (s.get("origen") or "semilla",))


# ----------------------------------------------------------------------------- utilidades
def _num(v: Any) -> float:
    return float(v) if v not in (None, "") else 0.0


def _r(x: float) -> float:
    """Redondeo para quitar el ruido de coma flotante (3.6300000000000003 → 3.63) y enteros limpios."""
    v = round(x, 4)
    return int(v) if v == int(v) else v


def _fecha(v: Any, campo: str) -> Optional[str]:
    if v in (None, ""):
        return None
    if isinstance(v, (date, datetime)):
        return v.strftime("%Y-%m-%d")
    s = str(v).strip()[:10]
    try:
        return datetime.strptime(s, "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        raise ValueError(f"La {campo} no es válida; usa el formato AAAA-MM-DD.")


def _texto(v: Any, maximo: int = 200) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip()[:maximo]


def _catalogo_map(c) -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = {t: [] for t in TIPOS_CATALOGO}
    for r in c.execute("SELECT id, tipo, valor, efecto, descripcion, orden FROM inv_tqtr_catalogo ORDER BY tipo, orden, id"):
        out.setdefault(r["tipo"], []).append(dict(r))
    return out


def _migrar_1340(c) -> None:
    _columnas(c, "inv_tqtr_catalogo", {"revision": "REAL NOT NULL DEFAULT 0"})
    if c.execute("SELECT 1 FROM inv_tqtr_meta WHERE clave='migr_1340_devueltas'").fetchone():
        return
    c.execute("UPDATE inv_tqtr_catalogo SET efecto=0, revision=1, descripcion='No suma a disponible: queda en Devueltas / en revisión' "
              "WHERE tipo='movimiento' AND (valor LIKE 'Devoluci%' OR valor LIKE 'Desinstalado%')")
    orden = c.execute("SELECT COALESCE(MAX(orden),-1)+1 FROM inv_tqtr_catalogo WHERE tipo='movimiento'").fetchone()[0]
    for i, (valor, ef, desc) in enumerate(((MOV_A_DISPONIBLE, 1.0, "Devueltas que pasan a disponible"), (MOV_BAJA, 0.0, "Devueltas dadas de baja"))):
        c.execute("INSERT OR IGNORE INTO inv_tqtr_catalogo (tipo, valor, efecto, revision, descripcion, orden) VALUES ('movimiento',?,?,-1,?,?)",
                  (valor, ef, desc, orden + i))
    c.execute("INSERT OR IGNORE INTO inv_tqtr_catalogo (tipo, valor, descripcion, orden) VALUES ('regla', 'Devueltas / en revisión', "
              "'Devolución y garantía no suman a disponible; se reclasifican a disponible o se dan de baja', 99)")
    c.execute("INSERT OR REPLACE INTO inv_tqtr_meta (clave, valor) VALUES ('migr_1340_devueltas', '1')")


def _revision(c) -> Dict[str, float]:
    """Existencia "Devueltas / en revisión" por modelo (solo movimientos directos del modelo)."""
    try:
        return {r[0]: r[1] for r in c.execute(
            "SELECT m.modelo, SUM(m.cantidad * k.revision) FROM inv_tqtr_movimientos m JOIN inv_tqtr_catalogo k "
            "ON k.tipo='movimiento' AND k.valor=m.movimiento WHERE k.revision <> 0 GROUP BY m.modelo")}
    except Exception:  # catálogo sin la columna (antes de migrar)
        return {}


def reclasificar_devueltas(comp_id: int, accion: str, cantidad: float, nota: str = "", db_path: Optional[Path] = None) -> Dict[str, Any]:
    """Saca devueltas de revisión: 'disponible' (suma a existencia) o 'baja' (no suma). Genera el movimiento en el Registro."""
    asegurar(db_path)
    if accion not in ("disponible", "baja"):
        raise ValueError("Acción no válida: usa 'disponible' o 'baja'.")
    try:
        q = float(cantidad)
    except (TypeError, ValueError):
        raise ValueError("La cantidad debe ser un número.")
    if q <= 0:
        raise ValueError("La cantidad debe ser mayor que cero.")
    with db.transaction(db_path) as c:
        comp = _comp(c, comp_id)
        hay = _num(_revision(c).get(comp["descripcion"]))
        if q > hay + _EPS:
            raise ValueError(f"Solo hay {_r(hay)} en revisión de «{comp['descripcion']}».")
        hoy = date.today().isoformat()
        c.execute("INSERT INTO inv_tqtr_movimientos (fecha_entrada, categoria, modelo, condicion, movimiento, cantidad, unidad, fecha_salida, destino, notas) "
                  "VALUES (?,?,?,?,?,?,?,?,?,?)",
                  (hoy, comp["categoria"], comp["descripcion"], "Reacondiconado" if accion == "disponible" else "Usado",
                   MOV_A_DISPONIBLE if accion == "disponible" else MOV_BAJA, int(q) if q == int(q) else q, comp["unidad_inventario"],
                   hoy if accion == "baja" else None, "", _texto(nota, 500) or ("Devuelta revisada: pasa a disponible" if accion == "disponible" else "Devuelta dada de baja")))
    revisar_alertas(db_path)
    return next(f for f in dashboard(db_path)["componentes"] if f["id"] == comp_id)


def _efectos(c) -> Dict[str, float]:
    return {r["valor"]: _num(r["efecto"]) for r in c.execute("SELECT valor, efecto FROM inv_tqtr_catalogo WHERE tipo='movimiento'")}


# ----------------------------------------------------------------------------- dashboard
def _calcular(c) -> Dict[str, Any]:
    efectos = _efectos(c)
    comps = [dict(r) for r in c.execute("SELECT * FROM inv_tqtr_componentes ORDER BY orden, id")]
    productos = [dict(r) for r in c.execute("SELECT * FROM inv_tqtr_productos ORDER BY orden, id")]
    bom: Dict[int, Dict[int, float]] = {}
    for r in c.execute("SELECT producto_id, componente_id, cantidad FROM inv_tqtr_bom"):
        bom.setdefault(r["producto_id"], {})[r["componente_id"]] = r["cantidad"]
    # Σ por modelo: neto (efecto·cantidad), entradas (+) y salidas (−)
    neto: Dict[str, float] = {}; ent: Dict[str, float] = {}; sal: Dict[str, float] = {}
    por_tipo: Dict[str, Dict[str, float]] = {}; por_mes: Dict[str, Dict[str, float]] = {}
    total_mov = 0
    for m in c.execute("SELECT modelo, movimiento, cantidad, fecha_entrada FROM inv_tqtr_movimientos"):
        total_mov += 1
        e = efectos.get(m["movimiento"], 0.0); q = _num(m["cantidad"])
        neto[m["modelo"]] = neto.get(m["modelo"], 0.0) + e * q
        if e > 0:
            ent[m["modelo"]] = ent.get(m["modelo"], 0.0) + e * q
        elif e < 0:
            sal[m["modelo"]] = sal.get(m["modelo"], 0.0) - e * q
        t = por_tipo.setdefault(m["movimiento"], {"movimientos": 0, "cantidad": 0.0}); t["movimientos"] += 1; t["cantidad"] += q
        mes = (m["fecha_entrada"] or "")[:7] or "sin fecha"
        pm = por_mes.setdefault(mes, {"entradas": 0, "salidas": 0, "otros": 0})
        pm["entradas" if e > 0 else "salidas" if e < 0 else "otros"] += 1

    nombres_prod = {p["id"]: p["nombre"] for p in productos}
    en_revision = _revision(c)
    por_tarjetas = {r[0]: r[1] for r in c.execute(
        "SELECT componente_id, SUM(cantidad_real) FROM inv_tqtr_consumos WHERE estado IN ('activo','disuelta') AND componente_id IS NOT NULL GROUP BY componente_id")}
    filas = []
    por_desc: Dict[str, Dict[str, Any]] = {}
    for comp in comps:
        d = comp["descripcion"]
        tarj = _num(por_tarjetas.get(comp["id"]))
        disp = neto.get(d, 0.0) - tarj; cons = sal.get(d, 0.0) + tarj; entr = ent.get(d, 0.0)
        for pid, items in bom.items():
            q = items.get(comp["id"])
            if q:
                pn = nombres_prod.get(pid)
                disp += neto.get(pn, 0.0) * q; cons += sal.get(pn, 0.0) * q; entr += ent.get(pn, 0.0) * q
        por_ens = _num(comp["cantidad_ensamble"])
        ensambles = None if por_ens <= 0 else (0 if disp <= 0 else int(disp / por_ens + _EPS))
        minimo = _num(comp["stock_minimo"])
        if disp <= 0:
            estado = "agotado"
        elif ensambles is not None and ensambles < 1:
            estado = "insuficiente"
        elif minimo > 0 and disp <= minimo:
            estado = "bajo"
        else:
            estado = "ok"
        f = {"id": comp["id"], "grupo": comp["grupo"], "categoria": comp["categoria"], "descripcion": d, "proveedor": comp["proveedor"],
             "unidad": comp["unidad_inventario"] or comp["unidad"], "notas": comp["notas"], "en_dashboard": bool(comp["en_dashboard"]),
             "entradas": _r(entr), "consumida": _r(cons), "disponible": _r(disp), "cantidad_ensamble": _r(por_ens),
             "ensambles": ensambles, "stock_minimo": _r(minimo), "estado": estado, "acumulado_directo": _r(neto.get(d, 0.0)), "consumo_tarjetas": _r(tarj),
             "en_revision": _r(_num(en_revision.get(d)))}
        filas.append(f); por_desc[d] = f

    def min_grupo(g: str) -> Optional[int]:
        vals = [f["ensambles"] for f in filas if f["grupo"] == g and f["en_dashboard"] and f["ensambles"] is not None]
        return min(vals) if vals else None

    def min_de(*descs: str) -> Optional[int]:
        vals = [por_desc[x]["ensambles"] for x in descs if x in por_desc and por_desc[x]["ensambles"] is not None]
        return min(vals) if len(vals) == len(descs) else None

    pcba = {g: min_grupo(g) for g in ("R1", "R2", "R3")}
    final = min(v for v in pcba.values() if v is not None) if all(v is not None for v in pcba.values()) else None
    # Productos finales posibles según la BOM completa (incluye accesorios que el dashboard del Excel no cruza)
    prod_bom = []
    for p in productos:
        items = bom.get(p["id"], {})
        mejor = None; limita = None
        for cid, q in items.items():
            f = next((x for x in filas if x["id"] == cid), None)
            if not f or q <= 0:
                continue
            n = 0 if f["disponible"] <= 0 else int(f["disponible"] / q + _EPS)
            if mejor is None or n < mejor:
                mejor, limita = n, f["descripcion"]
        prod_bom.append({"id": p["id"], "producto": p["nombre"], "posibles": mejor, "limitante": limita, "componentes": len(items),
                         "movidos": _r(sal.get(p["nombre"], 0.0))})

    conocidos = set(por_desc) | set(nombres_prod.values())
    sin_match = sorted({m for m in neto if m not in conocidos} | {m for m in sal if m not in conocidos})
    alertas = [f for f in filas if f["estado"] != "ok"]
    return {
        "componentes": filas,
        "grupos": GRUPOS,
        "pcba_posibles": pcba,
        "producto_final_posible": final,
        "quintalock": min_de(CAJA_QUINTALOCK, ACTUADOR),
        "translock": min_de(CAJA_TRANSLOCK, ACTUADOR),
        "productos": prod_bom,
        "alertas": alertas,
        "sin_coincidencia": sin_match,
        "por_tipo": [{"movimiento": k, "movimientos": v["movimientos"], "cantidad": _r(v["cantidad"]), "efecto": efectos.get(k, 0.0)} for k, v in sorted(por_tipo.items())],
        "por_mes": [{"mes": k, **v} for k, v in sorted(por_mes.items())],
        "kpis": {"movimientos": total_mov, "componentes": len(filas), "alertas": len(alertas),
                 "entradas": sum(v["movimientos"] for k, v in por_tipo.items() if efectos.get(k, 0) > 0),
                 "salidas": sum(v["movimientos"] for k, v in por_tipo.items() if efectos.get(k, 0) < 0)},
    }


def dashboard(db_path: Optional[Path] = None) -> Dict[str, Any]:
    sincronizar_consumos(db_path)
    with db.get_db(db_path) as c:
        out = _calcular(c)
        out["recientes"] = [dict(r) for r in c.execute("SELECT * FROM inv_tqtr_movimientos ORDER BY COALESCE(fecha_entrada,'') DESC, id DESC LIMIT 10")]
        cos = _calcular_costos(c, out)
        out["costos"] = {k: v for k, v in cos.items() if k != "items"}
        out["consumo"] = _resumen_consumos(c)["totales"]
        stk = _calcular_stock(c)
        out["stock"] = {"a_comprar": len(stk["a_comprar"]), "items": stk["a_comprar"][:8]}
    return out


# ----------------------------------------------------------------------------- registro (movimientos)
_ORDENES = {"fecha": "COALESCE(fecha_entrada,'') {d}, id {d}", "modelo": "modelo {d}, id", "cantidad": "cantidad {d}, id", "id": "id {d}",
            "movimiento": "movimiento {d}, id", "categoria": "categoria {d}, id"}


def listar_registros(q: str = "", movimiento: str = "", categoria: str = "", modelo: str = "", condicion: str = "", desde: str = "", hasta: str = "",
                     orden: str = "fecha", desc: bool = True, limit: int = 200, offset: int = 0, db_path: Optional[Path] = None) -> Dict[str, Any]:
    asegurar(db_path)
    where, args = [], []
    for col, v in (("movimiento", movimiento), ("categoria", categoria), ("modelo", modelo), ("condicion", condicion)):
        if v:
            where.append(f"{col} = ?"); args.append(v)
    if desde:
        where.append("fecha_entrada >= ?"); args.append(_fecha(desde, "fecha inicial"))
    if hasta:
        where.append("fecha_entrada <= ?"); args.append(_fecha(hasta, "fecha final"))
    if q:
        like = f"%{q.strip()}%"
        where.append("(codigo LIKE ? OR modelo LIKE ? OR categoria LIKE ? OR destino LIKE ? OR notas LIKE ? OR movimiento LIKE ?)"); args += [like] * 6
    w = (" WHERE " + " AND ".join(where)) if where else ""
    ob = _ORDENES.get(orden, _ORDENES["fecha"]).format(d="DESC" if desc else "ASC")
    limit = max(1, min(int(limit), 5000)); offset = max(0, int(offset))
    with db.get_db(db_path) as c:
        total = c.execute(f"SELECT COUNT(*) FROM inv_tqtr_movimientos{w}", args).fetchone()[0]
        items = [dict(r) for r in c.execute(f"SELECT * FROM inv_tqtr_movimientos{w} ORDER BY {ob} LIMIT ? OFFSET ?", args + [limit, offset])]
    return {"total": total, "limit": limit, "offset": offset, "items": items}


_CAMPOS_MOV = ("codigo", "fecha_entrada", "categoria", "modelo", "condicion", "movimiento", "cantidad", "unidad", "fecha_salida", "destino", "notas")


def _validar_mov(c, d: Dict[str, Any], parcial: bool) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k in _CAMPOS_MOV:
        if k not in d or (parcial and d[k] is None and k in ("modelo", "movimiento", "cantidad")):
            continue
        v = d[k]
        if k in ("fecha_entrada", "fecha_salida"):
            out[k] = _fecha(v, "fecha de entrada" if k == "fecha_entrada" else "fecha de salida")
        elif k == "cantidad":
            try:
                n = float(v)
            except (TypeError, ValueError):
                raise ValueError("La cantidad debe ser un número.")
            if n <= 0:
                raise ValueError("La cantidad debe ser mayor que cero.")
            out[k] = int(n) if n == int(n) else n
        else:
            out[k] = _texto(v, 500 if k == "notas" else 200)
    if not parcial:
        for k in ("modelo", "movimiento"):
            if not out.get(k):
                raise ValueError("Falta el Tipo / Modelo." if k == "modelo" else "Falta el tipo de movimiento.")
        if "cantidad" not in out:
            raise ValueError("Falta la cantidad.")
        out.setdefault("fecha_entrada", date.today().isoformat())
    if "modelo" in out and not out["modelo"]:
        raise ValueError("Falta el Tipo / Modelo.")
    if out.get("movimiento") is not None:
        validos = [r["valor"] for r in c.execute("SELECT valor FROM inv_tqtr_catalogo WHERE tipo='movimiento'")]
        if out["movimiento"] not in validos:
            raise ValueError(f"Tipo de movimiento desconocido. Usa: {', '.join(validos)}.")
    if out.get("modelo") and not out.get("categoria") and not parcial:
        r = c.execute("SELECT categoria, unidad_inventario FROM inv_tqtr_componentes WHERE descripcion=?", (out["modelo"],)).fetchone()
        if r:
            out["categoria"] = r["categoria"]
            out.setdefault("unidad", r["unidad_inventario"])
        elif c.execute("SELECT 1 FROM inv_tqtr_productos WHERE nombre=?", (out["modelo"],)).fetchone():
            out["categoria"] = "Producto final"
    return out


def obtener_registro(mov_id: int, db_path: Optional[Path] = None) -> Dict[str, Any]:
    asegurar(db_path)
    with db.get_db(db_path) as c:
        r = c.execute("SELECT * FROM inv_tqtr_movimientos WHERE id=?", (mov_id,)).fetchone()
    if not r:
        raise NoEncontradoError("Ese movimiento no existe.")
    return dict(r)


def crear_registro(datos: Dict[str, Any], db_path: Optional[Path] = None) -> Dict[str, Any]:
    asegurar(db_path)
    with db.transaction(db_path) as c:
        d = _validar_mov(c, datos, parcial=False)
        cols = list(d)
        mid = c.execute(f"INSERT INTO inv_tqtr_movimientos ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", [d[k] for k in cols]).lastrowid
    revisar_alertas(db_path)
    return obtener_registro(mid, db_path)


def editar_registro(mov_id: int, datos: Dict[str, Any], db_path: Optional[Path] = None) -> Dict[str, Any]:
    asegurar(db_path)
    with db.transaction(db_path) as c:
        if not c.execute("SELECT 1 FROM inv_tqtr_movimientos WHERE id=?", (mov_id,)).fetchone():
            raise NoEncontradoError("Ese movimiento no existe.")
        d = _validar_mov(c, datos, parcial=True)
        if d:
            c.execute(f"UPDATE inv_tqtr_movimientos SET {', '.join(f'{k}=?' for k in d)}, actualizado_en=datetime('now') WHERE id=?", [*d.values(), mov_id])
    revisar_alertas(db_path)
    return obtener_registro(mov_id, db_path)


def eliminar_registro(mov_id: int, db_path: Optional[Path] = None) -> None:
    asegurar(db_path)
    with db.transaction(db_path) as c:
        if not c.execute("DELETE FROM inv_tqtr_movimientos WHERE id=?", (mov_id,)).rowcount:
            raise NoEncontradoError("Ese movimiento no existe.")
    revisar_alertas(db_path)


# ----------------------------------------------------------------------------- componentes (BOM)
_CAMPOS_COMP = ("grupo", "categoria", "descripcion", "cantidad_lote", "unidad_lote", "cantidad_ensamble", "unidad", "proveedor",
                "unidad_inventario", "notas", "stock_minimo", "en_dashboard", "orden")
_NUM_COMP = ("cantidad_lote", "cantidad_ensamble", "stock_minimo")


def listar_componentes(db_path: Optional[Path] = None) -> Dict[str, Any]:
    sincronizar_consumos(db_path)
    with db.get_db(db_path) as c:
        productos = [dict(r) for r in c.execute("SELECT id, nombre, orden FROM inv_tqtr_productos ORDER BY orden, id")]
        bom: Dict[int, Dict[str, float]] = {}
        for r in c.execute("SELECT b.componente_id, p.nombre, b.cantidad FROM inv_tqtr_bom b JOIN inv_tqtr_productos p ON p.id=b.producto_id"):
            bom.setdefault(r["componente_id"], {})[r["nombre"]] = _r(r["cantidad"])
        calc = {f["id"]: f for f in _calcular(c)["componentes"]}
        items = []
        for r in c.execute("SELECT * FROM inv_tqtr_componentes ORDER BY orden, id"):
            d = dict(r)
            q = _num(d["cantidad_ensamble"])
            d["rendimiento_lote"] = _r(_num(d["cantidad_lote"]) / q) if q > 0 else None
            d["en_dashboard"] = bool(d["en_dashboard"])
            d["bom"] = bom.get(d["id"], {})
            f = calc.get(d["id"], {})
            d["acumulado"] = f.get("acumulado_directo"); d["disponible"] = f.get("disponible"); d["estado"] = f.get("estado")
            d["en_revision"] = f.get("en_revision", 0)
            items.append(d)
    return {"productos": productos, "grupos": GRUPOS, "items": items}


def _validar_comp(d: Dict[str, Any], parcial: bool) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k in _CAMPOS_COMP:
        if k not in d or d[k] is None:
            continue
        v = d[k]
        if k in _NUM_COMP:
            try:
                n = float(v)
            except (TypeError, ValueError):
                raise ValueError("Las cantidades deben ser números.")
            if n < 0:
                raise ValueError("Las cantidades no pueden ser negativas.")
            out[k] = n
        elif k == "en_dashboard":
            out[k] = 1 if v else 0
        elif k == "orden":
            out[k] = int(v)
        else:
            out[k] = _texto(v, 500 if k == "notas" else 200)
    if (not parcial or "descripcion" in out) and not out.get("descripcion"):
        raise ValueError("Falta la descripción del material.")
    return out


def _guardar_bom(c, comp_id: int, bom: Dict[str, Any]) -> None:
    for nombre, q in (bom or {}).items():
        p = c.execute("SELECT id FROM inv_tqtr_productos WHERE nombre=?", (nombre,)).fetchone()
        if not p:
            raise ValueError(f"No existe el producto final «{nombre}».")
        q = _num(q)
        if q < 0:
            raise ValueError("Las cantidades de la BOM no pueden ser negativas.")
        if q == 0:
            c.execute("DELETE FROM inv_tqtr_bom WHERE producto_id=? AND componente_id=?", (p["id"], comp_id))
        else:
            c.execute("INSERT INTO inv_tqtr_bom (producto_id, componente_id, cantidad) VALUES (?,?,?) "
                      "ON CONFLICT(producto_id, componente_id) DO UPDATE SET cantidad=excluded.cantidad", (p["id"], comp_id, q))


def _comp(c, comp_id: int) -> Dict[str, Any]:
    r = c.execute("SELECT * FROM inv_tqtr_componentes WHERE id=?", (comp_id,)).fetchone()
    if not r:
        raise NoEncontradoError("Ese componente no existe.")
    return dict(r)


def crear_componente(datos: Dict[str, Any], db_path: Optional[Path] = None) -> Dict[str, Any]:
    asegurar(db_path)
    with db.transaction(db_path) as c:
        d = _validar_comp(datos, parcial=False)
        if c.execute("SELECT 1 FROM inv_tqtr_componentes WHERE descripcion=?", (d["descripcion"],)).fetchone():
            raise ConflictoError("Ya existe un componente con esa descripción.")
        if "orden" not in d:
            d["orden"] = (c.execute("SELECT COALESCE(MAX(orden),0) FROM inv_tqtr_componentes").fetchone()[0] or 0) + 1
        cols = list(d)
        cid = c.execute(f"INSERT INTO inv_tqtr_componentes ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", [d[k] for k in cols]).lastrowid
        _guardar_bom(c, cid, datos.get("bom") or {})
        return _comp(c, cid)


def editar_componente(comp_id: int, datos: Dict[str, Any], db_path: Optional[Path] = None) -> Dict[str, Any]:
    """Edita un componente; si cambia la descripción, los movimientos que la usaban se renombran (el match es por texto, como en el Excel)."""
    asegurar(db_path)
    with db.transaction(db_path) as c:
        antes = _comp(c, comp_id)
        d = _validar_comp(datos, parcial=True)
        nueva = d.get("descripcion")
        if nueva and nueva != antes["descripcion"]:
            if c.execute("SELECT 1 FROM inv_tqtr_componentes WHERE descripcion=? AND id<>?", (nueva, comp_id)).fetchone():
                raise ConflictoError("Ya existe un componente con esa descripción.")
            c.execute("UPDATE inv_tqtr_movimientos SET modelo=? WHERE modelo=?", (nueva, antes["descripcion"]))
        if d:
            c.execute(f"UPDATE inv_tqtr_componentes SET {', '.join(f'{k}=?' for k in d)}, actualizado_en=datetime('now') WHERE id=?", [*d.values(), comp_id])
        if "bom" in datos:
            _guardar_bom(c, comp_id, datos.get("bom") or {})
        return _comp(c, comp_id)


def eliminar_componente(comp_id: int, db_path: Optional[Path] = None) -> None:
    asegurar(db_path)
    with db.transaction(db_path) as c:
        comp = _comp(c, comp_id)
        n = c.execute("SELECT COUNT(*) FROM inv_tqtr_movimientos WHERE modelo=?", (comp["descripcion"],)).fetchone()[0]
        if n:
            raise ConflictoError(f"«{comp['descripcion']}» tiene {n} movimiento{'s' if n != 1 else ''} en el registro. Elimínalos antes de dar de baja el componente.")
        c.execute("DELETE FROM inv_tqtr_componentes WHERE id=?", (comp_id,))


# ----------------------------------------------------------------------------- configuración (catálogos y productos finales)
def configuracion(db_path: Optional[Path] = None) -> Dict[str, Any]:
    asegurar(db_path)
    with db.get_db(db_path) as c:
        cat = _catalogo_map(c)
        modelos = [r["descripcion"] for r in c.execute("SELECT descripcion FROM inv_tqtr_componentes ORDER BY orden, id")]
        productos = [dict(r) for r in c.execute("SELECT id, nombre, orden FROM inv_tqtr_productos ORDER BY orden, id")]
        desde = _param(c, "consumo_desde", "")
        conv = _conversiones(c)
    return {"conversiones": conv, "catalogos": cat, "modelos": modelos + [p["nombre"] for p in productos], "productos": productos, "grupos": GRUPOS, "consumo_desde": desde}


def crear_catalogo(tipo: str, valor: str, efecto: Optional[float] = None, descripcion: str = "", db_path: Optional[Path] = None) -> Dict[str, Any]:
    asegurar(db_path)
    if tipo not in TIPOS_CATALOGO:
        raise ValueError(f"Tipo de catálogo desconocido. Usa: {', '.join(TIPOS_CATALOGO)}.")
    valor = _texto(valor)
    if not valor:
        raise ValueError("Falta el valor.")
    if tipo == "movimiento" and efecto not in (-1, 0, 1, -1.0, 0.0, 1.0):
        raise ValueError("El efecto de un movimiento es 1 (suma), -1 (resta) o 0 (no afecta).")
    with db.transaction(db_path) as c:
        if c.execute("SELECT 1 FROM inv_tqtr_catalogo WHERE tipo=? AND valor=?", (tipo, valor)).fetchone():
            raise ConflictoError("Ese valor ya está en el catálogo.")
        orden = (c.execute("SELECT COALESCE(MAX(orden),-1) FROM inv_tqtr_catalogo WHERE tipo=?", (tipo,)).fetchone()[0]) + 1
        cid = c.execute("INSERT INTO inv_tqtr_catalogo (tipo, valor, efecto, descripcion, orden) VALUES (?,?,?,?,?)",
                        (tipo, valor, efecto if tipo == "movimiento" else None, _texto(descripcion, 500), orden)).lastrowid
        return dict(c.execute("SELECT * FROM inv_tqtr_catalogo WHERE id=?", (cid,)).fetchone())


def editar_catalogo(cat_id: int, datos: Dict[str, Any], db_path: Optional[Path] = None) -> Dict[str, Any]:
    asegurar(db_path)
    with db.transaction(db_path) as c:
        r = c.execute("SELECT * FROM inv_tqtr_catalogo WHERE id=?", (cat_id,)).fetchone()
        if not r:
            raise NoEncontradoError("Ese valor del catálogo no existe.")
        sets: Dict[str, Any] = {}
        if datos.get("valor") is not None:
            nuevo = _texto(datos["valor"])
            if not nuevo:
                raise ValueError("Falta el valor.")
            if nuevo != r["valor"]:
                if c.execute("SELECT 1 FROM inv_tqtr_catalogo WHERE tipo=? AND valor=? AND id<>?", (r["tipo"], nuevo, cat_id)).fetchone():
                    raise ConflictoError("Ese valor ya está en el catálogo.")
                col = {"movimiento": "movimiento", "categoria": "categoria", "condicion": "condicion", "unidad": "unidad"}.get(r["tipo"])
                if col:  # renombrar también en el registro para no romper el match
                    c.execute(f"UPDATE inv_tqtr_movimientos SET {col}=? WHERE {col}=?", (nuevo, r["valor"]))
                sets["valor"] = nuevo
        if "efecto" in datos and r["tipo"] == "movimiento":
            if datos["efecto"] not in (-1, 0, 1, -1.0, 0.0, 1.0):
                raise ValueError("El efecto de un movimiento es 1 (suma), -1 (resta) o 0 (no afecta).")
            sets["efecto"] = float(datos["efecto"])
        if datos.get("descripcion") is not None:
            sets["descripcion"] = _texto(datos["descripcion"], 500)
        if sets:
            c.execute(f"UPDATE inv_tqtr_catalogo SET {', '.join(f'{k}=?' for k in sets)} WHERE id=?", [*sets.values(), cat_id])
        return dict(c.execute("SELECT * FROM inv_tqtr_catalogo WHERE id=?", (cat_id,)).fetchone())


def eliminar_catalogo(cat_id: int, db_path: Optional[Path] = None) -> None:
    asegurar(db_path)
    with db.transaction(db_path) as c:
        r = c.execute("SELECT * FROM inv_tqtr_catalogo WHERE id=?", (cat_id,)).fetchone()
        if not r:
            raise NoEncontradoError("Ese valor del catálogo no existe.")
        if r["tipo"] == "movimiento":
            n = c.execute("SELECT COUNT(*) FROM inv_tqtr_movimientos WHERE movimiento=?", (r["valor"],)).fetchone()[0]
            if n:
                raise ConflictoError(f"Hay {n} movimiento{'s' if n != 1 else ''} de tipo «{r['valor']}»; no se puede quitar.")
        c.execute("DELETE FROM inv_tqtr_catalogo WHERE id=?", (cat_id,))


def crear_producto(nombre: str, db_path: Optional[Path] = None) -> Dict[str, Any]:
    asegurar(db_path)
    nombre = _texto(nombre)
    if not nombre:
        raise ValueError("Falta el nombre del producto final.")
    with db.transaction(db_path) as c:
        if c.execute("SELECT 1 FROM inv_tqtr_productos WHERE nombre=?", (nombre,)).fetchone() or \
                c.execute("SELECT 1 FROM inv_tqtr_componentes WHERE descripcion=?", (nombre,)).fetchone():
            raise ConflictoError("Ya existe un producto o componente con ese nombre.")
        orden = c.execute("SELECT COALESCE(MAX(orden),-1)+1 FROM inv_tqtr_productos").fetchone()[0]
        pid = c.execute("INSERT INTO inv_tqtr_productos (nombre, orden) VALUES (?,?)", (nombre, orden)).lastrowid
        return dict(c.execute("SELECT * FROM inv_tqtr_productos WHERE id=?", (pid,)).fetchone())


def eliminar_producto(prod_id: int, db_path: Optional[Path] = None) -> None:
    asegurar(db_path)
    with db.transaction(db_path) as c:
        r = c.execute("SELECT nombre FROM inv_tqtr_productos WHERE id=?", (prod_id,)).fetchone()
        if not r:
            raise NoEncontradoError("Ese producto final no existe.")
        n = c.execute("SELECT COUNT(*) FROM inv_tqtr_movimientos WHERE modelo=?", (r["nombre"],)).fetchone()[0]
        if n:
            raise ConflictoError(f"«{r['nombre']}» tiene {n} movimiento{'s' if n != 1 else ''} en el registro; no se puede quitar.")
        c.execute("DELETE FROM inv_tqtr_productos WHERE id=?", (prod_id,))


# ----------------------------------------------------------------------------- costos (Costos_Produccion_TQTR.xlsx)
# Un "armado" = juego de 3 tarjetas (R1 + R2 + R3) con sus consumibles, el actuador y el gabinete del producto de costeo.
# Costo por armado = Σ costo_unitario × cantidad_armado × (tipo de cambio si la moneda es USD), solo filas "incluido" y cuya
# variante esté vacía o sea el producto (Quintalock / Translock). Con la semilla da 4426.284 MXN, igual que G44 del Excel.
def _param(c, clave: str, defecto: str) -> str:
    r = c.execute("SELECT valor FROM inv_tqtr_meta WHERE clave=?", (clave,)).fetchone()
    return r["valor"] if r and r["valor"] not in (None, "") else defecto


def _parametros(c) -> Dict[str, Any]:
    try:
        tc = float(_param(c, "tipo_cambio", "18.5"))
    except ValueError:
        tc = 18.5
    return {"tipo_cambio": tc, "producto": _param(c, "producto_costeo", "Translock"), "monedas": list(MONEDAS), "variantes": list(VARIANTES), "grupos": list(GRUPOS_COSTO)}


def _costo_armado(items: List[Dict[str, Any]], variante: str) -> Dict[str, Any]:
    por_grupo = {g: 0.0 for g in GRUPOS_COSTO}
    for it in items:
        if it["incluido"] and it["variante"] in ("", variante):
            por_grupo[it["grupo"] if it["grupo"] in por_grupo else "Otros"] += it["costo_armado_mxn"]
    return {"producto": variante, "total": round(sum(por_grupo.values()), 4), "por_grupo": {k: round(v, 4) for k, v in por_grupo.items()}}


def _calcular_costos(c, dash: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    par = _parametros(c); tc = par["tipo_cambio"]
    dash = dash or _calcular(c)
    inv = {f["id"]: f for f in dash["componentes"]}
    items = []
    for r in c.execute("SELECT * FROM inv_tqtr_costos ORDER BY orden, id"):
        d = dict(r)
        factor = tc if d["moneda"] == "USD" else 1.0
        d["incluido"] = bool(d["incluido"])
        d["costo_unitario_mxn"] = round(d["costo_unitario"] * factor, 4)
        d["costo_armado_original"] = round(d["costo_unitario"] * d["cantidad_armado"], 4)
        d["costo_armado_mxn"] = round(d["costo_unitario"] * d["cantidad_armado"] * factor, 4)
        f = inv.get(d["componente_id"])
        d["componente"] = f["descripcion"] if f else None
        d["disponible"] = f["disponible"] if f else None
        d["unidad_inventario"] = f["unidad"] if f else ""
        d["valor_existencia"] = round(max(0.0, f["disponible"]) * d["costo_unitario_mxn"], 2) if f else None
        items.append(d)
    armado = _costo_armado(items, par["producto"])
    variantes = {v: _costo_armado(items, v) for v in VARIANTES}
    con_costo = {d["componente_id"] for d in items if d["componente_id"]}
    valor = round(sum(d["valor_existencia"] or 0 for d in items), 2)
    # Armados posibles con el stock: producto final (mínimo de las PCBA R1/R2/R3) acotado por el gabinete + actuador del producto
    gab = dash.get("translock") if par["producto"] == "Translock" else dash.get("quintalock")
    vals = [v for v in (dash.get("producto_final_posible"), gab) if v is not None]
    posibles = min(vals) if vals else None
    # Costo de lo producido: tarjetas completas de la app (fecha_finalizado no nula), cada una con el costo de su gabinete
    producidas: Dict[str, int] = {}
    try:
        for r in c.execute("SELECT COALESCE(gabinete,'') AS g, COUNT(*) AS n FROM tarjetas_produccion WHERE fecha_finalizado IS NOT NULL GROUP BY 1"):
            g = r["g"] if r["g"] in VARIANTES else par["producto"]
            producidas[g] = producidas.get(g, 0) + r["n"]
    except Exception:  # BD sin la tabla de producción (p. ej. pruebas aisladas)
        producidas = {}
    costo_prod = round(sum(n * variantes[g]["total"] for g, n in producidas.items()), 2)
    return {
        "parametros": par, "items": items, "armado": armado, "por_variante": variantes,
        "valor_existencia": valor,
        "armados_posibles": {"cantidad": posibles, "costo": round((posibles or 0) * armado["total"], 2)},
        "producido": {"tarjetas": sum(producidas.values()), "por_gabinete": producidas, "costo": costo_prod},
        "sin_componente": [d["descripcion"] for d in items if not d["componente_id"]],
        "componentes_sin_costo": [f["descripcion"] for f in dash["componentes"] if f["id"] not in con_costo],
    }


def costos(db_path: Optional[Path] = None) -> Dict[str, Any]:
    sincronizar_consumos(db_path)
    with db.get_db(db_path) as c:
        out = _calcular_costos(c)
        out["diferencias"] = diferencias_excel(c)
        out["consumo"] = _resumen_consumos(c)["totales"]
        return out


_CAMPOS_COSTO = ("componente_id", "descripcion", "categoria", "grupo", "costo_unitario", "unidad", "moneda", "cantidad_armado", "proveedor",
                 "variante", "incluido", "notas", "orden")


def _validar_costo(c, d: Dict[str, Any], parcial: bool) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k in _CAMPOS_COSTO:
        if k not in d:
            continue
        v = d[k]
        if k in ("costo_unitario", "cantidad_armado"):
            try:
                n = float(v if v not in (None, "") else 0)
            except (TypeError, ValueError):
                raise ValueError("El costo y la cantidad deben ser números.")
            if n < 0:
                raise ValueError("El costo y la cantidad no pueden ser negativos.")
            out[k] = n
        elif k == "componente_id":
            if v in (None, "", 0):
                out[k] = None
            else:
                if not c.execute("SELECT 1 FROM inv_tqtr_componentes WHERE id=?", (int(v),)).fetchone():
                    raise ValueError("Ese componente del inventario no existe.")
                out[k] = int(v)
        elif k == "incluido":
            out[k] = 1 if v else 0
        elif k == "orden":
            out[k] = int(v or 0)
        elif k == "moneda":
            m = _texto(v).upper() or "MXN"
            if m not in MONEDAS:
                raise ValueError(f"Moneda no válida. Usa: {', '.join(MONEDAS)}.")
            out[k] = m
        elif k == "grupo":
            g = _texto(v) or "Otros"
            if g not in GRUPOS_COSTO:
                raise ValueError(f"Tarjeta no válida. Usa: {', '.join(GRUPOS_COSTO)}.")
            out[k] = g
        elif k == "variante":
            vv = _texto(v)
            if vv and vv not in VARIANTES:
                raise ValueError(f"Variante no válida. Usa vacío, {' o '.join(VARIANTES)}.")
            out[k] = vv
        else:
            out[k] = _texto(v, 500 if k == "notas" else 200)
    if (not parcial or "descripcion" in out) and not out.get("descripcion"):
        if not parcial and out.get("componente_id"):
            out["descripcion"] = c.execute("SELECT descripcion FROM inv_tqtr_componentes WHERE id=?", (out["componente_id"],)).fetchone()[0]
        else:
            raise ValueError("Falta la descripción.")
    return out


def _costo(c, cid: int) -> Dict[str, Any]:
    r = c.execute("SELECT * FROM inv_tqtr_costos WHERE id=?", (cid,)).fetchone()
    if not r:
        raise NoEncontradoError("Ese costo no existe.")
    return dict(r)


def crear_costo(datos: Dict[str, Any], db_path: Optional[Path] = None) -> Dict[str, Any]:
    asegurar(db_path)
    with db.transaction(db_path) as c:
        d = _validar_costo(c, datos, parcial=False)
        d.setdefault("orden", (c.execute("SELECT COALESCE(MAX(orden),0) FROM inv_tqtr_costos").fetchone()[0] or 0) + 1)
        cols = list(d)
        cid = c.execute(f"INSERT INTO inv_tqtr_costos ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", [d[k] for k in cols]).lastrowid
        return _costo(c, cid)


def editar_costo(cid: int, datos: Dict[str, Any], db_path: Optional[Path] = None) -> Dict[str, Any]:
    asegurar(db_path)
    with db.transaction(db_path) as c:
        _costo(c, cid)
        d = _validar_costo(c, datos, parcial=True)
        if d:
            c.execute(f"UPDATE inv_tqtr_costos SET {', '.join(f'{k}=?' for k in d)} WHERE id=?", [*d.values(), cid])
        return _costo(c, cid)


def eliminar_costo(cid: int, db_path: Optional[Path] = None) -> None:
    asegurar(db_path)
    with db.transaction(db_path) as c:
        if not c.execute("DELETE FROM inv_tqtr_costos WHERE id=?", (cid,)).rowcount:
            raise NoEncontradoError("Ese costo no existe.")


def editar_parametros_costos(datos: Dict[str, Any], db_path: Optional[Path] = None) -> Dict[str, Any]:
    asegurar(db_path)
    with db.transaction(db_path) as c:
        if datos.get("tipo_cambio") is not None:
            try:
                tc = float(datos["tipo_cambio"])
            except (TypeError, ValueError):
                raise ValueError("El tipo de cambio debe ser un número.")
            if tc <= 0:
                raise ValueError("El tipo de cambio debe ser mayor que cero.")
            c.execute("INSERT OR REPLACE INTO inv_tqtr_meta (clave, valor) VALUES ('tipo_cambio', ?)", (str(tc),))
        if datos.get("producto") is not None:
            if datos["producto"] not in VARIANTES:
                raise ValueError(f"Producto no válido. Usa {' o '.join(VARIANTES)}.")
            c.execute("INSERT OR REPLACE INTO inv_tqtr_meta (clave, valor) VALUES ('producto_costeo', ?)", (datos["producto"],))
        return _parametros(c)


# ----------------------------------------------------------------------------- consumo por tarjeta (v1.3.38)
# Al quedar COMPLETA una tarjeta (R1+R2+R3 y MAC de R1/R2, `fecha_finalizado` sellada) se consumen los materiales estándar de
# R1+R2+R3 (origen 'placas'); con gabinete asignado, además caja + actuador + accesorios (origen 'gabinete'). Cambiar de gabinete
# devuelve una caja y consume la otra. Si la tarjeta deja de estar completa o se borra, solo vuelven al inventario la caja y el
# actuador ('devuelto'); lo demás queda como "consumo de tarjeta disuelta" ('disuelta', sigue restando existencia).
# Solo cuentan las tarjetas con fecha_finalizado >= meta `consumo_desde` (se fija la primera vez con la fecha de hoy).
ESTADOS_CONSUMO = ("activo", "disuelta", "devuelto")
NOTA_DISUELTA = "Consumo de tarjeta disuelta"
NOTA_DEVUELTO = "Devuelto al inventario"


def _estandar(c) -> List[Dict[str, Any]]:
    """Materiales estándar por armado: filas de costos ligadas a un componente con cantidad > 0."""
    out = []
    for r in c.execute("SELECT k.*, comp.descripcion AS comp_desc FROM inv_tqtr_costos k JOIN inv_tqtr_componentes comp ON comp.id = k.componente_id "
                       "ORDER BY k.orden, k.id"):
        q = r["cantidad_consumo"] if r["cantidad_consumo"] is not None else r["cantidad_armado"]
        if not q or q <= 0:
            continue
        out.append({"componente_id": r["componente_id"], "costo_id": r["id"], "descripcion": r["comp_desc"], "cantidad": q,
                    "origen": r["origen_consumo"] or ("placas" if r["grupo"] in ("R1", "R2", "R3") else "gabinete"), "variante": r["variante"] or "",
                    "devolvible": 1 if (r["variante"] or r["comp_desc"] == ACTUADOR) else 0})
    return out


def _tabla_existe(c, nombre: str) -> bool:
    return bool(c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (nombre,)).fetchone())


def _consumo_desde(c) -> str:
    desde = _param(c, "consumo_desde", "")
    if not desde:
        desde = date.today().isoformat()
        c.execute("INSERT OR REPLACE INTO inv_tqtr_meta (clave, valor) VALUES ('consumo_desde', ?)", (desde,))
    return desde


def _tarjetas(c) -> Dict[int, Dict[str, Any]]:
    if not _tabla_existe(c, "tarjetas_produccion"):
        return {}
    return {r["id"]: dict(r) for r in c.execute(
        f"SELECT id, id_tarjeta_num, lote_id, gabinete, fecha_finalizado, CASE WHEN {_TARJETA_COMPLETA} THEN 1 ELSE 0 END AS completa "
        "FROM tarjetas_produccion")}


def _sincronizar(c) -> Dict[str, int]:
    _asegurar_trigger(c)  # por si la BD de producción se creó después de preparar el inventario
    desde = _consumo_desde(c)
    tarjetas = _tarjetas(c)
    est = _estandar(c)
    filas: Dict[int, List[Dict[str, Any]]] = {}
    for r in c.execute("SELECT * FROM inv_tqtr_consumos"):
        filas.setdefault(r["tarjeta_id"], []).append(dict(r))
    cambios = {"creados": 0, "reactivados": 0, "devueltos": 0, "disueltos": 0, "excluidos": 0}

    def poner(fila, estado, nota=None):
        c.execute("UPDATE inv_tqtr_consumos SET estado=?, nota=CASE WHEN ? IS NULL THEN nota ELSE ? END, actualizado_en=datetime('now') WHERE id=?",
                  (estado, nota, nota, fila["id"]))
        fila["estado"] = estado

    def crear(t, e):
        c.execute("INSERT INTO inv_tqtr_consumos (tarjeta_id, tarjeta_num, lote_id, componente_id, costo_id, descripcion, origen, variante, devolvible,"
                  " cantidad_estandar, cantidad_real) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                  (t["id"], t["id_tarjeta_num"] or "", t["lote_id"], e["componente_id"], e["costo_id"], e["descripcion"], e["origen"], e["variante"],
                   e["devolvible"], e["cantidad"], e["cantidad"]))
        cambios["creados"] += 1

    def disolver(lista):
        for f in lista:
            if f["estado"] == "activo":
                if f["devolvible"]:
                    poner(f, "devuelto", NOTA_DEVUELTO); cambios["devueltos"] += 1
                else:
                    poner(f, "disuelta", f["nota"] or NOTA_DISUELTA); cambios["disueltos"] += 1

    # Tarjetas completadas y borradas sin conciliar (las anota el trigger): sus placas ya se usaron
    for b in [dict(r) for r in c.execute("SELECT * FROM inv_tqtr_tarjetas_borradas")]:
        tid = b["tarjeta_id"]
        if tid not in tarjetas and not filas.get(tid) and b["fecha_finalizado"] and b["fecha_finalizado"] >= desde:
            tb = {"id": tid, "id_tarjeta_num": b["id_tarjeta_num"], "lote_id": b["lote_id"]}
            for e in est:
                if e["origen"] == "placas":
                    crear(tb, e)
            filas[tid] = [dict(r) for r in c.execute("SELECT * FROM inv_tqtr_consumos WHERE tarjeta_id=?", (tid,))]
        c.execute("DELETE FROM inv_tqtr_tarjetas_borradas WHERE tarjeta_id=?", (tid,))
    for tid in set(tarjetas) | set(filas):
        t = tarjetas.get(tid); lista = filas.get(tid, [])
        if t is None:  # tarjeta borrada (disuelta): sus consumos huérfanos son la señal
            disolver(lista)
            continue
        if t["fecha_finalizado"] and t["fecha_finalizado"] < desde:  # anterior a la activación: no cuenta
            if lista:
                c.execute("DELETE FROM inv_tqtr_consumos WHERE tarjeta_id=?", (tid,)); cambios["excluidos"] += len(lista)
            continue
        if not (t["completa"] and t["fecha_finalizado"]):
            if not lista and t["fecha_finalizado"]:
                # Se completó (fecha sellada) y se desarmó entre dos sincronizaciones: sus materiales de placas ya se usaron.
                for e in est:
                    if e["origen"] == "placas":
                        crear(t, e)
                lista = [dict(r) for r in c.execute("SELECT * FROM inv_tqtr_consumos WHERE tarjeta_id=?", (tid,))]
            disolver(lista)
            continue
        por_comp = {f["componente_id"]: f for f in lista}
        gab = t["gabinete"] if t["gabinete"] in VARIANTES else None
        deseados = [e for e in est if e["origen"] == "placas" or (gab and e["variante"] in ("", gab))]
        ids_deseados = {e["componente_id"] for e in deseados}
        for e in deseados:
            f = por_comp.get(e["componente_id"])
            if f is None:
                crear(t, e)
            elif f["estado"] != "activo":
                poner(f, "activo", ""); cambios["reactivados"] += 1
        for f in lista:  # cambio o retiro de gabinete: vuelven la caja anterior y (sin gabinete) el actuador
            if f["origen"] == "gabinete" and f["estado"] == "activo" and f["componente_id"] not in ids_deseados and f["devolvible"]:
                poner(f, "devuelto", NOTA_DEVUELTO); cambios["devueltos"] += 1
    return cambios


def sincronizar_consumos(db_path: Optional[Path] = None) -> Dict[str, int]:
    """Concilia tarjetas completas / gabinetes con los consumos (idempotente). Se llama antes de cada lectura del inventario."""
    asegurar(db_path)
    with db.transaction(db_path) as c:
        cambios = _sincronizar(c)
    revisar_alertas(db_path)  # las tarjetas completas mueven existencias: aviso de stock mínimo una vez por cruce
    return cambios


def _filas_costeadas(c, where: str = "", args: tuple = ()) -> List[Dict[str, Any]]:
    tc = _parametros(c)["tipo_cambio"]
    out = []
    for r in c.execute("SELECT x.*, k.costo_unitario, k.moneda, comp.unidad_inventario, comp.unidad AS comp_unidad FROM inv_tqtr_consumos x "
                       "LEFT JOIN inv_tqtr_costos k ON k.id = x.costo_id LEFT JOIN inv_tqtr_componentes comp ON comp.id = x.componente_id "
                       f"{where} ORDER BY x.tarjeta_id, x.origen DESC, x.id", args):
        d = dict(r)
        unit = _num(d.pop("costo_unitario")) * (tc if d.pop("moneda") == "USD" else 1.0)
        cuenta = d["estado"] in ("activo", "disuelta")
        d["unidad"] = d.pop("unidad_inventario") or d.pop("comp_unidad") or ""
        d.pop("comp_unidad", None)
        d["costo_unitario_mxn"] = round(unit, 4)
        d["costo_estandar"] = round(unit * d["cantidad_estandar"], 4) if cuenta else 0.0
        d["costo_real"] = round(unit * d["cantidad_real"], 4) if cuenta else 0.0
        d["merma"] = _r(d["cantidad_real"] - d["cantidad_estandar"]) if cuenta else 0
        d["devolvible"] = bool(d["devolvible"])
        out.append(d)
    return out


def _estado_tarjeta(t: Optional[Dict[str, Any]], filas: List[Dict[str, Any]], desde: str) -> str:
    if t is None:
        return "borrada"
    if t["fecha_finalizado"] and t["fecha_finalizado"] < desde:
        return "anterior"
    if t["completa"] and t["fecha_finalizado"]:
        return "activa"
    return "disuelta" if filas else "pendiente"


def _totales(filas: List[Dict[str, Any]]) -> Dict[str, float]:
    e = round(sum(f["costo_estandar"] for f in filas), 2); r = round(sum(f["costo_real"] for f in filas), 2)
    return {"costo_estandar": e, "costo_real": r, "merma_costo": round(r - e, 2)}


def _resumen_consumos(c) -> Dict[str, Any]:
    desde = _param(c, "consumo_desde", "")
    tarjetas = _tarjetas(c)
    por: Dict[int, List[Dict[str, Any]]] = {}
    for f in _filas_costeadas(c):
        por.setdefault(f["tarjeta_id"], []).append(f)
    items = []
    for tid, filas in por.items():
        t = tarjetas.get(tid)
        items.append({"tarjeta_id": tid, "tarjeta_num": (t or {}).get("id_tarjeta_num") or filas[0]["tarjeta_num"], "lote_id": (t or filas[0]).get("lote_id"),
                      "gabinete": (t or {}).get("gabinete"), "fecha_finalizado": (t or {}).get("fecha_finalizado"),
                      "estado": _estado_tarjeta(t, filas, desde), "materiales": len(filas),
                      "con_merma": sum(1 for f in filas if f["merma"]), **_totales(filas)})
    items.sort(key=lambda x: (x["fecha_finalizado"] or "", x["tarjeta_num"]), reverse=True)
    todas = [f for fs in por.values() for f in fs]
    tot = _totales(todas)
    tot.update({"tarjetas": sum(1 for i in items if i["estado"] == "activa"), "disueltas": sum(1 for i in items if i["estado"] in ("disuelta", "borrada")),
                "consumo_desde": desde})
    return {"consumo_desde": desde, "items": items, "totales": tot}


def consumos(db_path: Optional[Path] = None) -> Dict[str, Any]:
    sincronizar_consumos(db_path)
    with db.get_db(db_path) as c:
        return _resumen_consumos(c)


def materiales_tarjeta(tarjeta_id: int, db_path: Optional[Path] = None) -> Dict[str, Any]:
    """Ficha de materiales de una tarjeta: estándar vs real, costo estándar vs real y merma."""
    sincronizar_consumos(db_path)
    with db.get_db(db_path) as c:
        desde = _param(c, "consumo_desde", "")
        t = _tarjetas(c).get(tarjeta_id)
        filas = _filas_costeadas(c, "WHERE x.tarjeta_id = ?", (tarjeta_id,))
        if t is None and not filas:
            raise NoEncontradoError("Esa tarjeta no existe.")
        estado = _estado_tarjeta(t, filas, desde)
        return {"tarjeta": {"id": tarjeta_id, "id_tarjeta_num": (t or {}).get("id_tarjeta_num") or (filas[0]["tarjeta_num"] if filas else ""),
                            "gabinete": (t or {}).get("gabinete"), "fecha_finalizado": (t or {}).get("fecha_finalizado"), "estado": estado},
                "consumo_desde": desde, "editable": estado == "activa", "items": filas, "totales": _totales(filas)}


def editar_materiales_tarjeta(tarjeta_id: int, items: List[Dict[str, Any]], db_path: Optional[Path] = None) -> Dict[str, Any]:
    """Cantidad real (merma) y nota de los materiales de una tarjeta completa."""
    sincronizar_consumos(db_path)
    with db.transaction(db_path) as c:
        t = _tarjetas(c).get(tarjeta_id)
        if not t or _estado_tarjeta(t, [1], _param(c, "consumo_desde", "")) != "activa":
            raise ValueError("Solo se editan los materiales de una tarjeta completa.")
        for it in items or []:
            f = c.execute("SELECT * FROM inv_tqtr_consumos WHERE tarjeta_id=? AND (id=? OR componente_id=?)",
                          (tarjeta_id, it.get("id") or -1, it.get("componente_id") or -1)).fetchone()
            if not f:
                raise NoEncontradoError("Ese material no está en la ficha de la tarjeta.")
            if f["estado"] != "activo":
                raise ValueError(f"«{f['descripcion']}» ya se devolvió al inventario; no se edita.")
            sets: Dict[str, Any] = {}
            if it.get("cantidad_real") is not None:
                try:
                    q = float(it["cantidad_real"])
                except (TypeError, ValueError):
                    raise ValueError("La cantidad real debe ser un número.")
                if q < 0:
                    raise ValueError("La cantidad real no puede ser negativa.")
                sets["cantidad_real"] = q
            if it.get("nota") is not None:
                sets["nota"] = _texto(it["nota"], 500)
            if sets:
                c.execute(f"UPDATE inv_tqtr_consumos SET {', '.join(f'{k}=?' for k in sets)}, actualizado_en=datetime('now') WHERE id=?", [*sets.values(), f["id"]])
    return materiales_tarjeta(tarjeta_id, db_path)


def editar_consumo_desde(fecha: str, db_path: Optional[Path] = None) -> Dict[str, Any]:
    asegurar(db_path)
    f = _fecha(fecha, "fecha de inicio del consumo")
    if not f:
        raise ValueError("Falta la fecha de inicio del consumo.")
    with db.transaction(db_path) as c:
        c.execute("INSERT OR REPLACE INTO inv_tqtr_meta (clave, valor) VALUES ('consumo_desde', ?)", (f,))
    return consumos(db_path)


def diferencias_excel(c) -> List[Dict[str, Any]]:
    """Cantidades por armado distintas entre el Excel de costos (estándar) y el de inventario (cantidad por ensamble)."""
    out = []
    for r in c.execute("SELECT k.descripcion, k.cantidad_armado, k.cantidad_consumo, k.unidad, comp.descripcion AS componente, comp.cantidad_ensamble, "
                       "comp.unidad_inventario FROM inv_tqtr_costos k JOIN inv_tqtr_componentes comp ON comp.id = k.componente_id ORDER BY k.orden"):
        usada = r["cantidad_consumo"] if r["cantidad_consumo"] is not None else r["cantidad_armado"]
        if abs(_num(r["cantidad_armado"]) - _num(r["cantidad_ensamble"])) > _EPS or r["cantidad_consumo"] is not None:
            out.append({"componente": r["componente"], "costos": _r(_num(r["cantidad_armado"])), "unidad_costos": r["unidad"],
                        "inventario": _r(_num(r["cantidad_ensamble"])), "unidad_inventario": r["unidad_inventario"], "consumo": _r(_num(usada))})
    return out


# ----------------------------------------------------------------------------- v1.3.39: unidades del silicón / catalizador
# Silicón en gramos y catalizador en ml. Estándar por armado indicado por el usuario: silicón 400 g (R1+R2, se usa al montar en
# gabinete Translock/Quintalock) y 100 g (R3); catalizador 6 ml (gabinete) y 1.5 ml (R3).
# Conversión de lo ya registrado (litros / piezas): el registro siempre da de alta silicón y catalizador en pares 1:1 (6 y 6, 18 y 18,
# 2 y 2, 4 y 4), así que cada "litro" o "pieza" se toma como UN envase del kit: silicón 1 envase = 1000 g (presentación de 1 kg,
# densidad ≈ 1 que usa el Excel al llamarlo "1 l") y catalizador 1 envase = 15 ml (1000 g × 6 ml / 400 g, la proporción indicada).
# Ambos factores son editables (PATCH /conversiones) y recalculan los movimientos desde su cantidad original.
SILICON = ("Silicón P-53%", "gramos", "g")
CATALIZADOR = ("Catalizador para silicón P-53%", "mililitros", "ml")
# (patrón de componente, cantidad por armado, origen del consumo)
ESTANDAR_1339 = (("Silicón P-53%R1+R2", 400.0, "gabinete"), ("Silicón P-53%R3", 100.0, "placas"),
                 ("Catalizador para silicón P-53%R1+R2", 6.0, "gabinete"), ("Catalizador para silicón P-53%R3", 1.5, "placas"))
CONV_DEFECTO = {"conv_silicon_g_por_envase": 1000.0, "conv_catalizador_ml_por_envase": 15.0, "precio_silicon_envase": 226.0}
NOTA_SENSORES = "Ajuste v1.3.39 indicado por el usuario"


def _columnas(c, tabla: str, cols: Dict[str, str]) -> None:
    hay = {r[1] for r in c.execute(f"PRAGMA table_info({tabla})")}
    for col, ddl in cols.items():
        if col not in hay:
            c.execute(f"ALTER TABLE {tabla} ADD COLUMN {col} {ddl}")


def _conversiones(c) -> Dict[str, float]:
    out = {}
    for k, v in CONV_DEFECTO.items():
        try:
            out[k] = float(_param(c, k, str(v)))
        except ValueError:
            out[k] = v
    return out


def _aplicar_conversion(c) -> None:
    """Recalcula movimientos (desde su cantidad original), lote del componente y precio por gramo con los factores vigentes."""
    f = _conversiones(c)
    for patron, unidad, corta in (SILICON, CATALIZADOR):
        factor = f["conv_silicon_g_por_envase"] if patron == SILICON[0] else f["conv_catalizador_ml_por_envase"]
        for m in c.execute("SELECT id, cantidad_original, unidad_original FROM inv_tqtr_movimientos WHERE modelo LIKE ? AND cantidad_original IS NOT NULL",
                           (patron,)).fetchall():
            u = (m["unidad_original"] or "").strip().lower()
            q = m["cantidad_original"] if u in (unidad, corta) else m["cantidad_original"] * factor
            c.execute("UPDATE inv_tqtr_movimientos SET cantidad=?, unidad=? WHERE id=?", (round(q, 4), unidad, m["id"]))
        c.execute("UPDATE inv_tqtr_componentes SET cantidad_lote=?, unidad_lote=? WHERE descripcion LIKE ?", (factor, corta, patron))
    c.execute("UPDATE inv_tqtr_costos SET costo_unitario=?, unidad='g' WHERE componente_id IN (SELECT id FROM inv_tqtr_componentes WHERE descripcion LIKE ?)",
              (round(f["precio_silicon_envase"] / f["conv_silicon_g_por_envase"], 6), SILICON[0]))


def _migrar_1339(c) -> None:
    _columnas(c, "inv_tqtr_movimientos", {"cantidad_original": "REAL", "unidad_original": "TEXT"})
    _columnas(c, "inv_tqtr_costos", {"origen_consumo": "TEXT"})
    _columnas(c, "inv_tqtr_componentes", {"punto_reorden": "REAL NOT NULL DEFAULT 0", "armados_objetivo": "INTEGER", "entrega_dias": "INTEGER NOT NULL DEFAULT 0",
                                          "entrega_nota": "TEXT NOT NULL DEFAULT ''", "alerta_minimo": "INTEGER NOT NULL DEFAULT 0"})
    if not c.execute("SELECT 1 FROM inv_tqtr_meta WHERE clave='migr_1339_unidades'").fetchone():
        for k, v in CONV_DEFECTO.items():
            c.execute("INSERT OR IGNORE INTO inv_tqtr_meta (clave, valor) VALUES (?, ?)", (k, str(v)))
        r = c.execute("SELECT k.costo_unitario FROM inv_tqtr_costos k JOIN inv_tqtr_componentes comp ON comp.id=k.componente_id "
                      "WHERE comp.descripcion LIKE ? AND k.unidad IN ('l','litros') LIMIT 1", (SILICON[0],)).fetchone()
        if r:  # precio del envase tal como estaba (MXN por litro = por envase de 1 kg)
            c.execute("INSERT OR REPLACE INTO inv_tqtr_meta (clave, valor) VALUES ('precio_silicon_envase', ?)", (str(r["costo_unitario"]),))
        for patron, unidad, corta in (SILICON, CATALIZADOR):
            c.execute("UPDATE inv_tqtr_movimientos SET cantidad_original=cantidad, unidad_original=unidad, "
                      "notas=TRIM(notas || ' [v1.3.39: ' || cantidad || ' ' || unidad || ' convertidos a ' || ?  || ']') "
                      "WHERE modelo LIKE ? AND cantidad_original IS NULL AND LOWER(unidad) NOT IN (?, ?)", (unidad, patron, unidad, corta))
            c.execute("UPDATE inv_tqtr_componentes SET unidad=?, unidad_inventario=? WHERE descripcion LIKE ?", (corta, unidad, patron))
        for patron, q, origen in ESTANDAR_1339:
            comp = c.execute("SELECT id, cantidad_ensamble FROM inv_tqtr_componentes WHERE descripcion LIKE ?", (patron,)).fetchone()
            if not comp:
                continue
            c.execute("UPDATE inv_tqtr_componentes SET cantidad_ensamble=? WHERE id=?", (q, comp["id"]))
            c.execute("UPDATE inv_tqtr_bom SET cantidad=? WHERE componente_id=? AND cantidad > 0", (q, comp["id"]))
            unidad = "g" if patron.startswith("Silicón") else "ml"
            c.execute("UPDATE inv_tqtr_costos SET cantidad_armado=?, cantidad_consumo=NULL, unidad=?, origen_consumo=?, "
                      "notas='Estándar v1.3.39 indicado por el usuario' WHERE componente_id=?", (q, unidad, origen, comp["id"]))
            for x in c.execute("SELECT id, cantidad_estandar, cantidad_real FROM inv_tqtr_consumos WHERE componente_id=?", (comp["id"],)).fetchall():
                proporcion = (x["cantidad_real"] / x["cantidad_estandar"]) if x["cantidad_estandar"] else 1.0
                c.execute("UPDATE inv_tqtr_consumos SET cantidad_estandar=?, cantidad_real=?, origen=? WHERE id=?", (q, round(q * proporcion, 4), origen, x["id"]))
        orden = c.execute("SELECT COALESCE(MAX(orden),-1)+1 FROM inv_tqtr_catalogo WHERE tipo='unidad'").fetchone()[0]
        c.execute("INSERT OR IGNORE INTO inv_tqtr_catalogo (tipo, valor, orden) VALUES ('unidad', 'gramos', ?)", (orden,))
        _aplicar_conversion(c)
        c.execute("INSERT OR REPLACE INTO inv_tqtr_meta (clave, valor) VALUES ('migr_1339_unidades', '1')")
    if not c.execute("SELECT 1 FROM inv_tqtr_meta WHERE clave='migr_1339_sensores'").fetchone():
        comp = c.execute("SELECT * FROM inv_tqtr_componentes WHERE descripcion LIKE 'Sensor magn%' ORDER BY id LIMIT 1").fetchone()
        if not comp:
            cid = c.execute("INSERT INTO inv_tqtr_componentes (grupo, categoria, descripcion, cantidad_lote, unidad_lote, cantidad_ensamble, unidad, "
                            "unidad_inventario, orden) VALUES ('A','Actuador y accesorios','Sensor magnético CS1-U',4,'pza',3,'pza','piezas',99)").lastrowid
            comp = c.execute("SELECT * FROM inv_tqtr_componentes WHERE id=?", (cid,)).fetchone()
        hoy = date.today().isoformat()
        # 73 sensores de los cuales se descuentan 33 (stock 40). Las salidas de producto final ya descuentan 3 sensores por armado
        # (11 "Translock completa" × 3 = 33 en el registro original): solo se registra como salida lo que falte para llegar a 33.
        ya = next((f["consumida"] for f in _calcular(c)["componentes"] if f["id"] == comp["id"]), 0)
        movs = [("Entrada", 73)] + ([("Salida", _r(33 - ya))] if ya < 33 else [])
        for mov, q in movs:
            c.execute("INSERT INTO inv_tqtr_movimientos (fecha_entrada, categoria, modelo, condicion, movimiento, cantidad, unidad, fecha_salida, destino, notas) "
                      "VALUES (?,?,?,?,?,?,?,?,?,?)", (hoy, comp["categoria"] or "Actuador y accesorios", comp["descripcion"], "Nuevo", mov, q, "piezas",
                                                     hoy if mov == "Salida" else None, "I+D", NOTA_SENSORES))
        c.execute("INSERT OR REPLACE INTO inv_tqtr_meta (clave, valor) VALUES ('migr_1339_sensores', '1')")


def conversiones(db_path: Optional[Path] = None) -> Dict[str, Any]:
    asegurar(db_path)
    with db.get_db(db_path) as c:
        f = _conversiones(c)
    return {**f, "nota": "Cada litro o pieza registrados antes de v1.3.39 se toma como un envase del kit P-53: silicón en gramos por envase y "
                         "catalizador en ml por envase (15 ml = 1000 g × 6 ml / 400 g). Cámbialos si la presentación real es otra."}


def editar_conversiones(datos: Dict[str, Any], db_path: Optional[Path] = None) -> Dict[str, Any]:
    asegurar(db_path)
    with db.transaction(db_path) as c:
        for k in CONV_DEFECTO:
            if datos.get(k) is not None:
                try:
                    v = float(datos[k])
                except (TypeError, ValueError):
                    raise ValueError("Los factores de conversión deben ser números.")
                if v <= 0:
                    raise ValueError("Los factores de conversión deben ser mayores que cero.")
                c.execute("INSERT OR REPLACE INTO inv_tqtr_meta (clave, valor) VALUES (?, ?)", (k, str(v)))
        _aplicar_conversion(c)
    revisar_alertas(db_path)
    return conversiones(db_path)


# ----------------------------------------------------------------------------- v1.3.39: stock mínimo y materiales a comprar
ARMADOS_OBJETIVO = 10
DIAS_RITMO = 30
logger = logging.getLogger("escaner_tqt.inventario_tqtr")


def _consumo_diario(c, dash: Dict[str, Any]) -> Dict[int, float]:
    """Ritmo de consumo de los últimos 30 días: salidas del registro (con productos finales desglosados) + consumos de tarjetas."""
    desde = (date.today().toordinal() - DIAS_RITMO)
    desde_iso = date.fromordinal(desde).isoformat()
    efectos = _efectos(c)
    ids = {f["descripcion"]: f["id"] for f in dash["componentes"]}
    bom: Dict[str, Dict[int, float]] = {}
    for r in c.execute("SELECT p.nombre, b.componente_id, b.cantidad FROM inv_tqtr_bom b JOIN inv_tqtr_productos p ON p.id=b.producto_id"):
        bom.setdefault(r["nombre"], {})[r["componente_id"]] = r["cantidad"]
    total: Dict[int, float] = {}
    for m in c.execute("SELECT modelo, movimiento, cantidad FROM inv_tqtr_movimientos WHERE fecha_entrada >= ?", (desde_iso,)):
        if efectos.get(m["movimiento"], 0) >= 0:
            continue
        if m["modelo"] in ids:
            total[ids[m["modelo"]]] = total.get(ids[m["modelo"]], 0.0) + m["cantidad"]
        for cid, q in bom.get(m["modelo"], {}).items():
            total[cid] = total.get(cid, 0.0) + m["cantidad"] * q
    for r in c.execute("SELECT componente_id, SUM(cantidad_real) AS q FROM inv_tqtr_consumos WHERE estado IN ('activo','disuelta') "
                       "AND date(creado_en) >= ? AND componente_id IS NOT NULL GROUP BY componente_id", (desde_iso,)):
        total[r["componente_id"]] = total.get(r["componente_id"], 0.0) + r["q"]
    return {k: v / DIAS_RITMO for k, v in total.items()}


def _bajo_minimo(f: Dict[str, Any]) -> bool:
    return (f["stock_minimo"] > 0 and f["disponible"] <= f["stock_minimo"]) or (f["punto_reorden"] > 0 and f["disponible"] <= f["punto_reorden"])


def _calcular_stock(c) -> Dict[str, Any]:
    dash = _calcular(c)
    objetivo_global = int(float(_param(c, "armados_objetivo", str(ARMADOS_OBJETIVO))))
    extra = {r["id"]: dict(r) for r in c.execute("SELECT id, punto_reorden, armados_objetivo, entrega_dias, entrega_nota, alerta_minimo, cantidad_ensamble "
                                                 "FROM inv_tqtr_componentes")}
    ritmo = _consumo_diario(c, dash)
    items = []
    for f in dash["componentes"]:
        e = extra.get(f["id"], {})
        objetivo = e.get("armados_objetivo") or objetivo_global
        por_armado = _num(e.get("cantidad_ensamble"))
        diario = ritmo.get(f["id"], 0.0)
        cobertura = None if diario <= 0 else round(max(0.0, f["disponible"]) / diario, 1)
        dias = int(e.get("entrega_dias") or 0)
        x = {"id": f["id"], "grupo": f["grupo"], "descripcion": f["descripcion"], "unidad": f["unidad"], "proveedor": f["proveedor"],
             "disponible": f["disponible"], "stock_minimo": f["stock_minimo"], "punto_reorden": _r(_num(e.get("punto_reorden"))),
             "armados_objetivo": objetivo, "objetivo_propio": bool(e.get("armados_objetivo")), "cantidad_por_armado": _r(por_armado),
             "entrega_dias": dias, "entrega_nota": e.get("entrega_nota") or "", "consumo_diario": _r(round(diario, 4)), "dias_cobertura": cobertura,
             "alerta_enviada": bool(e.get("alerta_minimo"))}
        x["sugerida"] = _r(max(0.0, objetivo * por_armado + max(x["stock_minimo"], x["punto_reorden"]) - max(0.0, f["disponible"])))
        x["bajo_minimo"] = _bajo_minimo(x)
        x["margen_dias"] = None if cobertura is None else round(cobertura - dias, 1)
        items.append(x)

    def urgencia(x):  # agotados primero; luego el menor margen entre días de cobertura y tiempo de entrega
        return (0 if x["disponible"] <= 0 else 1, x["margen_dias"] if x["margen_dias"] is not None else 10 ** 6, -x["entrega_dias"])
    comprar = sorted([x for x in items if x["bajo_minimo"]], key=urgencia)
    return {"armados_objetivo": objetivo_global, "dias_ritmo": DIAS_RITMO, "items": items, "a_comprar": comprar}


def stock_minimo(db_path: Optional[Path] = None) -> Dict[str, Any]:
    sincronizar_consumos(db_path)
    with db.get_db(db_path) as c:
        return _calcular_stock(c)


def editar_stock_minimo(comp_id: int, datos: Dict[str, Any], db_path: Optional[Path] = None) -> Dict[str, Any]:
    asegurar(db_path)
    sets: Dict[str, Any] = {}
    for k in ("stock_minimo", "punto_reorden"):
        if datos.get(k) is not None:
            v = _num(datos[k])
            if v < 0:
                raise ValueError("El stock mínimo y el punto de reorden no pueden ser negativos.")
            sets[k] = v
    if "armados_objetivo" in datos:
        v = datos["armados_objetivo"]
        sets["armados_objetivo"] = None if v in (None, "", 0) else int(v)
        if sets["armados_objetivo"] is not None and sets["armados_objetivo"] < 0:
            raise ValueError("Los armados objetivo no pueden ser negativos.")
    if datos.get("entrega_dias") is not None:
        v = int(_num(datos["entrega_dias"]))
        if v < 0:
            raise ValueError("El tiempo de entrega no puede ser negativo.")
        sets["entrega_dias"] = v
    for k in ("entrega_nota", "proveedor"):
        if datos.get(k) is not None:
            sets[k] = _texto(datos[k], 500 if k == "entrega_nota" else 200)
    with db.transaction(db_path) as c:
        _comp(c, comp_id)
        if sets:
            c.execute(f"UPDATE inv_tqtr_componentes SET {', '.join(f'{k}=?' for k in sets)}, actualizado_en=datetime('now') WHERE id=?", [*sets.values(), comp_id])
    revisar_alertas(db_path)
    return next(x for x in stock_minimo(db_path)["items"] if x["id"] == comp_id)


def editar_armados_objetivo(n: int, db_path: Optional[Path] = None) -> Dict[str, Any]:
    asegurar(db_path)
    if n is None or int(n) <= 0:
        raise ValueError("Los armados objetivo deben ser un número mayor que cero.")
    with db.transaction(db_path) as c:
        c.execute("INSERT OR REPLACE INTO inv_tqtr_meta (clave, valor) VALUES ('armados_objetivo', ?)", (str(int(n)),))
    return stock_minimo(db_path)


def _admins(c) -> List[str]:
    try:
        return [r[0] for r in c.execute("SELECT email FROM usuarios WHERE rol='administrador' AND activo=1 ORDER BY email")]
    except Exception:  # BD sin tabla de usuarios
        return []


def revisar_alertas(db_path: Optional[Path] = None) -> List[str]:
    """Marca los materiales que CRUZAN el mínimo (una vez por cruce) y avisa por correo a los administradores.
    Al recuperarse por encima del mínimo, la marca se limpia para avisar en el siguiente cruce. Nunca lanza."""
    try:
        with db.transaction(db_path) as c:
            st = _calcular_stock(c)
            nuevos = [x for x in st["items"] if x["bajo_minimo"] and not x["alerta_enviada"]]
            recuperados = [x["id"] for x in st["items"] if not x["bajo_minimo"] and x["alerta_enviada"]]
            for x in nuevos:
                c.execute("UPDATE inv_tqtr_componentes SET alerta_minimo=1 WHERE id=?", (x["id"],))
            for i in recuperados:
                c.execute("UPDATE inv_tqtr_componentes SET alerta_minimo=0 WHERE id=?", (i,))
            destinos = _admins(c) if nuevos else []
            comprar = st["a_comprar"]
    except Exception as e:  # noqa: BLE001
        logger.error("Inventario TQTR: no se pudo revisar el stock mínimo: %s", e)
        return []
    if nuevos:
        _avisar_minimo(nuevos, comprar, destinos)
    return [x["descripcion"] for x in nuevos]


def _avisar_minimo(nuevos: List[Dict[str, Any]], comprar: List[Dict[str, Any]], destinos: List[str]) -> None:
    try:
        from app.services import correo
        if not destinos or not correo.configurado():
            logger.info("Inventario TQTR: %d material(es) bajo mínimo; correo no enviado (sin configurar o sin administradores).", len(nuevos))
            return
        def linea(x):
            entrega = f"{x['entrega_dias']} días" + (f" ({x['entrega_nota']})" if x["entrega_nota"] else "") if x["entrega_dias"] else "sin tiempo de entrega"
            cob = f"{x['dias_cobertura']} días de cobertura" if x["dias_cobertura"] is not None else "sin consumo reciente"
            return (f"- {x['descripcion']}: quedan {x['disponible']} {x['unidad']} (mínimo {x['stock_minimo']}, reorden {x['punto_reorden']}); "
                    f"comprar {x['sugerida']} {x['unidad']} a {x['proveedor'] or 'proveedor sin definir'}; entrega {entrega}; {cob}.")
        texto = ("Estos materiales del Inventario TQTR acaban de llegar a su stock mínimo:\n\n" + "\n".join(linea(x) for x in nuevos)
                 + "\n\nLista completa de materiales a comprar (por urgencia):\n\n" + "\n".join(linea(x) for x in comprar)
                 + "\n\nConsola de escritorio: /monitor#/inventario_tqtr?tab=stock\n")
        asunto = f"Inventario TQTR: {len(nuevos)} material{'es' if len(nuevos) != 1 else ''} en stock mínimo"
        cab = ["Material", "Quedan", "Mínimo", "Comprar", "Proveedor", "Entrega"]
        fila = lambda x: [x["descripcion"], f"{x['disponible']} {x['unidad']}", x["stock_minimo"], f"{x['sugerida']} {x['unidad']}",
                          x["proveedor"] or "Sin definir", f"{x['entrega_dias']} días" if x["entrega_dias"] else "—"]
        tablas = [("Llegaron a su stock mínimo", cab, [fila(x) for x in nuevos])]
        if comprar:
            tablas.append(("Lista completa de materiales a comprar (por urgencia)", cab, [fila(x) for x in comprar]))
        html = correo.plantilla(asunto, ["Estos materiales del Inventario TQTR acaban de llegar a su stock mínimo."],
                                kpis=[("Llegaron al mínimo", len(nuevos), "bad"), ("Materiales a comprar", len(comprar), "warn")],
                                tablas=tablas, aviso=("info", "Consúltalo en la consola de escritorio: Inventario TQTR › Stock Mínimo."))
        for d in destinos:
            try:
                correo.enviar(d, asunto, texto, html)
            except Exception as e:  # noqa: BLE001
                logger.error("Inventario TQTR: no se pudo enviar el aviso de stock mínimo a %s: %s", d, e)
    except Exception as e:  # noqa: BLE001
        logger.error("Inventario TQTR: fallo al preparar el aviso de stock mínimo: %s", e)


# ----------------------------------------------------------------------------- exportación .xlsx
def exportar_xlsx(db_path: Optional[Path] = None) -> bytes:
    """Libro con las mismas cuatro hojas del Excel original (valores calculados, sin fórmulas)."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter

    dash = dashboard(db_path)
    comps = listar_componentes(db_path)
    conf = configuracion(db_path)
    regs = listar_registros(orden="fecha", desc=False, limit=5000, db_path=db_path)["items"]

    wb = Workbook()
    neg = Font(bold=True, color="FFFFFF"); fondo = PatternFill("solid", fgColor="1F2A44")

    def hoja(ws, titulo, cab, filas, anchos=None):
        ws.append([titulo]); ws["A1"].font = Font(bold=True, size=14); ws.append([])
        ws.append(cab)
        for celda in ws[3]:
            celda.font = neg; celda.fill = fondo
        for f in filas:
            ws.append(f)
        for i, w in enumerate(anchos or [], start=1):
            ws.column_dimensions[get_column_letter(i)].width = w
        ws.freeze_panes = "A4"

    ws = wb.active; ws.title = "Dashboard de inventario"
    hoja(ws, "INVENTARIO DISPONIBLE", ["Tarjeta", "Código del Producto / Material", "Proveedor", "Unidad", "Cantidad disponible", "Cantidad consumida",
                                       "Ensambles posibles", "Stock mínimo", "Estado", "Notas"],
         [[f["grupo"], f["descripcion"], f["proveedor"], f["unidad"], f["disponible"], f["consumida"], f["ensambles"], f["stock_minimo"], f["estado"], f["notas"]]
          for f in dash["componentes"]], [10, 42, 20, 12, 18, 18, 18, 14, 14, 36])
    ws.append([])
    for etiqueta, v in (("PCBA posibles | R1", dash["pcba_posibles"]["R1"]), ("PCBA posibles | R2", dash["pcba_posibles"]["R2"]),
                        ("PCBA posibles | R3", dash["pcba_posibles"]["R3"]), ("Producto final posible (R1 + R2 + R3)", dash["producto_final_posible"]),
                        ("Quintalock", dash["quintalock"]), ("Translock", dash["translock"])):
        ws.append(["", etiqueta, v])
    ws.append([]); ws.append(["", "Producto final (según BOM)", "Posibles", "Componente limitante"])
    for p in dash["productos"]:
        ws.append(["", p["producto"], p["posibles"], p["limitante"]])

    ws = wb.create_sheet("Registro_inventario")
    hoja(ws, "REGISTRO Y CONTROL DE INVENTARIO", ["ID / Código", "Fecha Entrada", "Categoría", "Tipo / Modelo", "Condición", "Tipo Movimiento", "Cantidad",
                                                   "Unidad", "Fecha Salida", "Ubicación / Destino", "Notas"],
         [[r["codigo"], r["fecha_entrada"], r["categoria"], r["modelo"], r["condicion"], r["movimiento"], r["cantidad"], r["unidad"], r["fecha_salida"],
           r["destino"], r["notas"]] for r in regs], [16, 14, 26, 42, 12, 22, 10, 10, 14, 24, 30])

    prods = [p["nombre"] for p in comps["productos"]]
    ws = wb.create_sheet("Componentes")
    hoja(ws, "LISTA DE COMPONENTES", ["Grupo", "Categoría", "Descripción del Material", "Cantidad por caja/bobina/lote", "Unidad de medida",
                                      "Cantidad por ensamble", "Rendimiento por caja/bobina/lote", "Acumulado", "Unidad", "Stock mínimo", *prods],
         [[c["grupo"], c["categoria"], c["descripcion"], c["cantidad_lote"], c["unidad_lote"], c["cantidad_ensamble"], c["rendimiento_lote"], c["acumulado"],
           c["unidad"], c["stock_minimo"], *[c["bom"].get(p, 0) for p in prods]] for c in comps["items"]], [8, 28, 42, 14, 10, 14, 14, 12, 8, 12] + [18] * len(prods))

    ws = wb.create_sheet("Configuración")
    cat = conf["catalogos"]
    cols = [("Categoría", [x["valor"] for x in cat.get("categoria", [])]), ("Tipo / Modelo", conf["modelos"]),
            ("Tipo de movimiento", [f"{x['valor']} ({'+' if _num(x['efecto']) > 0 else '−' if _num(x['efecto']) < 0 else '0'})" for x in cat.get("movimiento", [])]),
            ("Condición", [x["valor"] for x in cat.get("condicion", [])]), ("Unidades", [x["valor"] for x in cat.get("unidad", [])])]
    alto = max(len(v) for _, v in cols)
    hoja(ws, "PANEL DE CONFIGURACIÓN Y PARÁMETROS", [t for t, _ in cols],
         [[v[i] if i < len(v) else None for _, v in cols] for i in range(alto)], [30, 42, 30, 18, 14])
    ws.append([]); ws.append(["Reglas de inventario"])
    for r in cat.get("regla", []):
        ws.append([r["valor"], r["descripcion"]])

    cos = costos(db_path)
    ws = wb.create_sheet("Costos")
    par = cos["parametros"]
    hoja(ws, f"COSTOS DE PRODUCCIÓN · producto {par['producto']} · tipo de cambio {par['tipo_cambio']} MXN/USD",
         ["Tarjeta", "Descripción (Excel de costos)", "Componente del inventario", "Proveedor", "Costo unitario", "Moneda", "Unidad", "Cantidad por armado",
          "Costo original", "Costo convertido (MXN)", "Variante", "Incluido", "Disponible", "Valor en existencia (MXN)", "Notas"],
         [[d["grupo"], d["descripcion"], d["componente"] or "(sin componente)", d["proveedor"], d["costo_unitario"], d["moneda"], d["unidad"], d["cantidad_armado"],
           d["costo_armado_original"], d["costo_armado_mxn"], d["variante"], "Sí" if d["incluido"] else "No", d["disponible"], d["valor_existencia"], d["notas"]]
          for d in cos["items"]], [8, 40, 40, 20, 12, 8, 8, 12, 12, 14, 12, 9, 12, 16, 40])
    ws.append([])
    for g, v in cos["armado"]["por_grupo"].items():
        ws.append([f"Total {g}", "", "", "", "", "", "", "", "", v])
    ws.append(["COSTO TOTAL POR ARMADO (MXN)", "", "", "", "", "", "", "", "", cos["armado"]["total"]])
    for v, x in cos["por_variante"].items():
        ws.append([f"Costo por armado {v}", "", "", "", "", "", "", "", "", x["total"]])
    ws.append(["Valor del inventario en existencia (MXN)", "", "", "", "", "", "", "", "", cos["valor_existencia"]])
    ws.append([f"Armados posibles con el stock ({cos['armados_posibles']['cantidad']})", "", "", "", "", "", "", "", "", cos["armados_posibles"]["costo"]])
    ws.append([f"Producido: {cos['producido']['tarjetas']} tarjetas completas", "", "", "", "", "", "", "", "", cos["producido"]["costo"]])

    stk = stock_minimo(db_path)
    ws = wb.create_sheet("Stock mínimo")
    hoja(ws, f"STOCK MÍNIMO · armados objetivo {stk['armados_objetivo']}", ["Material", "Disponible", "Unidad", "Stock mínimo", "Punto de reorden",
         "Comprar (sugerido)", "Proveedor", "Entrega (días)", "Nota de entrega", "Días de cobertura", "A comprar"],
         [[x["descripcion"], x["disponible"], x["unidad"], x["stock_minimo"], x["punto_reorden"], x["sugerida"], x["proveedor"], x["entrega_dias"],
           x["entrega_nota"], x["dias_cobertura"], "Sí" if x["bajo_minimo"] else ""] for x in stk["items"]], [42, 12, 10, 12, 14, 16, 20, 12, 30, 14, 10])

    buf = io.BytesIO(); wb.save(buf)
    return buf.getvalue()


def _reiniciar_cache() -> None:
    """Solo para pruebas: olvida qué BD ya se preparó."""
    _listas.clear()
