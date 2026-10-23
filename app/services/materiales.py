"""Inventario de materiales por módulo (v1.4.35), con el criterio de Inventario TQTR: existencias = entradas − salidas −
consumo, y cada tarjeta realizada descuenta su lista de materiales (la de Costos, `costeo_componentes` tipo producción).

- Tarjeta realizada = placa programada (`<modulo>_pcb.programada_en`). Si se desprograma o se elimina, su consumo se
  devuelve (estado 'devuelto'); si se vuelve a programar, se reactiva. Conciliación idempotente antes de cada lectura.
- El consumo solo cuenta desde que se activa el inventario del módulo (`consumo_desde`): las placas programadas antes no
  descuentan, igual que en TQT. Sin activar, el módulo queda preparado (lista de materiales y existencias en cero).
- Cada QR es una tarjeta. En módulos de una sola tarjeta se asigna sola; en AntiJammer (RX/TX) la placa queda
  «por asignar» hasta indicar si es RX o TX (`costeo_pcb_tarjeta`).
- El consumo guarda la cantidad del momento: cambiar la lista de materiales después no altera lo ya descontado.
"""
import re
from datetime import date
from typing import Any, Dict, List, Optional

from app.database import db
from app.services.costeo import CosteoError, NoEncontrado, _asegurar as _asegurar_costeo, _conf, _num

TIPOS_MOV = ("entrada", "salida", "ajuste")
_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_listo = False


def _asegurar() -> None:
    global _listo
    _asegurar_costeo()
    if _listo:
        return
    with db.transaction() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS costeo_movimientos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            modulo TEXT NOT NULL,
            descripcion TEXT NOT NULL,
            tipo TEXT NOT NULL,
            cantidad REAL NOT NULL,
            nota TEXT NOT NULL DEFAULT '',
            operador TEXT NOT NULL DEFAULT '',
            creado_en TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS costeo_consumos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            modulo TEXT NOT NULL,
            pcb_id INTEGER NOT NULL,
            pcb_nombre TEXT NOT NULL DEFAULT '',
            tarjeta TEXT NOT NULL,
            descripcion TEXT NOT NULL,
            cantidad REAL NOT NULL,
            estado TEXT NOT NULL DEFAULT 'activo',
            creado_en TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            actualizado_en TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            UNIQUE (modulo, pcb_id, descripcion)
        );
        CREATE TABLE IF NOT EXISTS costeo_pcb_tarjeta (modulo TEXT NOT NULL, pcb_id INTEGER NOT NULL, tarjeta TEXT NOT NULL,
                                                       PRIMARY KEY (modulo, pcb_id));
        CREATE TABLE IF NOT EXISTS costeo_minimos (modulo TEXT NOT NULL, descripcion TEXT NOT NULL, minimo REAL NOT NULL DEFAULT 0,
                                                   PRIMARY KEY (modulo, descripcion));
        CREATE INDEX IF NOT EXISTS ix_costeo_mov ON costeo_movimientos(modulo, descripcion);
        CREATE INDEX IF NOT EXISTS ix_costeo_cons ON costeo_consumos(modulo, pcb_id);
        """)
    _listo = True


def _meta(c, modulo: str, clave: str) -> Optional[str]:
    r = c.execute("SELECT valor FROM costeo_meta WHERE modulo=? AND clave=?", (modulo, clave)).fetchone()
    return r["valor"] if r else None


def _tabla_existe(c, nombre: str) -> bool:
    return c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (nombre,)).fetchone() is not None


def _bom(c, modulo: str) -> Dict[str, List[Dict[str, Any]]]:
    """Lista de materiales por tarjeta (solo producción; las cantidades de un mismo material se suman)."""
    out: Dict[str, Dict[str, float]] = {}
    for r in c.execute("SELECT tarjeta, descripcion, cantidad FROM costeo_componentes WHERE modulo=? AND tipo='produccion' AND cantidad>0",
                       (modulo,)):
        t = out.setdefault(r["tarjeta"], {})
        t[r["descripcion"]] = t.get(r["descripcion"], 0.0) + r["cantidad"]
    return {t: [{"descripcion": k, "cantidad": v} for k, v in m.items()] for t, m in out.items()}


def _sincronizar(c, conf: Dict[str, Any]) -> Dict[str, int]:
    modulo, tabla = conf["modulo"], conf["tabla_pcb"]
    cambios = {"creados": 0, "reactivados": 0, "devueltos": 0}
    desde = _meta(c, modulo, "consumo_desde")
    pcbs: Dict[int, Dict[str, Any]] = {}
    if desde and _tabla_existe(c, tabla):
        pcbs = {r["id"]: dict(r) for r in c.execute(
            f"SELECT id, nombre FROM {tabla} WHERE programada_en IS NOT NULL AND substr(programada_en,1,10) >= ?", (desde,))}
    unica = conf["tarjetas"][0] if len(conf["tarjetas"]) == 1 else None
    asignadas = {r["pcb_id"]: r["tarjeta"] for r in c.execute("SELECT pcb_id, tarjeta FROM costeo_pcb_tarjeta WHERE modulo=?", (modulo,))}
    bom = _bom(c, modulo)
    filas: Dict[int, List[Dict[str, Any]]] = {}
    for r in c.execute("SELECT * FROM costeo_consumos WHERE modulo=?", (modulo,)):
        filas.setdefault(r["pcb_id"], []).append(dict(r))

    def estado(f: Dict[str, Any], nuevo: str) -> None:
        c.execute("UPDATE costeo_consumos SET estado=?, actualizado_en=datetime('now','localtime') WHERE id=?", (nuevo, f["id"]))

    for pid in set(pcbs) | set(filas):
        p, lista = pcbs.get(pid), filas.get(pid, [])
        tarjeta = (unica or asignadas.get(pid)) if p else None
        if not tarjeta:   # ya no realizada (desprogramada, eliminada) o sin tarjeta asignada: su material vuelve
            for f in lista:
                if f["estado"] == "activo":
                    estado(f, "devuelto"); cambios["devueltos"] += 1
            continue
        if lista and lista[0]["tarjeta"] != tarjeta:   # se corrigió RX↔TX: se rehace el consumo con la otra lista
            c.execute("DELETE FROM costeo_consumos WHERE modulo=? AND pcb_id=?", (modulo, pid)); lista = []
        if lista:   # ya descontada: solo se reactiva lo devuelto (no se recalcula con la lista actual)
            for f in lista:
                if f["estado"] != "activo":
                    estado(f, "activo"); cambios["reactivados"] += 1
            continue
        for m in bom.get(tarjeta, []):
            c.execute("INSERT INTO costeo_consumos (modulo, pcb_id, pcb_nombre, tarjeta, descripcion, cantidad) VALUES (?,?,?,?,?,?)",
                      (modulo, pid, p["nombre"], tarjeta, m["descripcion"], m["cantidad"]))
            cambios["creados"] += 1
    return cambios


def _pendientes(c, conf: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Placas realizadas (desde la activación) que aún no dicen qué tarjeta son (solo módulos con varias tarjetas)."""
    desde = _meta(c, conf["modulo"], "consumo_desde")
    if len(conf["tarjetas"]) == 1 or not desde or not _tabla_existe(c, conf["tabla_pcb"]):
        return []
    return [dict(r) for r in c.execute(
        f"SELECT p.id, p.nombre, p.programada_en FROM {conf['tabla_pcb']} p LEFT JOIN costeo_pcb_tarjeta a "
        "ON a.modulo=? AND a.pcb_id=p.id WHERE p.programada_en IS NOT NULL AND substr(p.programada_en,1,10) >= ? "
        "AND a.tarjeta IS NULL ORDER BY p.programada_en DESC LIMIT 500", (conf["modulo"], desde))]


def _estado(c, conf: Dict[str, Any]) -> Dict[str, Any]:
    modulo = conf["modulo"]
    bom = _bom(c, modulo)
    mats: Dict[str, Dict[str, Any]] = {}
    for r in c.execute("SELECT descripcion, MIN(categoria) AS categoria, MIN(unidad) AS unidad, GROUP_CONCAT(DISTINCT tarjeta) AS tarjetas "
                       "FROM costeo_componentes WHERE modulo=? AND tipo='produccion' GROUP BY descripcion ORDER BY MIN(orden)", (modulo,)):
        mats[r["descripcion"]] = {"descripcion": r["descripcion"], "categoria": r["categoria"], "unidad": r["unidad"],
                                  "tarjetas": sorted((r["tarjetas"] or "").split(",")), "entradas": 0.0, "salidas": 0.0,
                                  "consumido": 0.0, "minimo": 0.0, "en_bom": True}

    def mat(desc: str) -> Dict[str, Any]:   # material con movimientos que ya no está en la lista de materiales
        return mats.setdefault(desc, {"descripcion": desc, "categoria": "", "unidad": "", "tarjetas": [], "entradas": 0.0,
                                      "salidas": 0.0, "consumido": 0.0, "minimo": 0.0, "en_bom": False})
    for r in c.execute("SELECT descripcion, tipo, SUM(cantidad) AS n FROM costeo_movimientos WHERE modulo=? GROUP BY 1, 2", (modulo,)):
        m = mat(r["descripcion"])
        if r["tipo"] == "salida":
            m["salidas"] += r["n"]
        else:   # entrada y ajuste (el ajuste lleva signo)
            m["entradas"] += r["n"]
    for r in c.execute("SELECT descripcion, SUM(cantidad) AS n FROM costeo_consumos WHERE modulo=? AND estado='activo' GROUP BY 1", (modulo,)):
        mat(r["descripcion"])["consumido"] += r["n"]
    for r in c.execute("SELECT descripcion, minimo FROM costeo_minimos WHERE modulo=?", (modulo,)):
        if r["descripcion"] in mats:
            mats[r["descripcion"]]["minimo"] = r["minimo"]
    for m in mats.values():
        m["disponible"] = round(m["entradas"] - m["salidas"] - m["consumido"], 4)
        m["bajo_minimo"] = m["minimo"] > 0 and m["disponible"] <= m["minimo"]
        for k in ("entradas", "salidas", "consumido"):
            m[k] = round(m[k], 4)
    posibles = {}
    for t in conf["tarjetas"]:   # tarjetas que alcanzan con lo disponible: el material más escaso manda
        lista = bom.get(t, [])
        posibles[t] = int(max(0, min(mats[x["descripcion"]]["disponible"] // x["cantidad"] for x in lista))) if lista else None
    realizadas = {t: 0 for t in conf["tarjetas"]}
    for r in c.execute("SELECT tarjeta, COUNT(DISTINCT pcb_id) AS n FROM costeo_consumos WHERE modulo=? AND estado='activo' GROUP BY 1", (modulo,)):
        realizadas[r["tarjeta"]] = r["n"]
    return {
        "modulo": modulo, "nombre": conf["nombre"], "tarjetas": list(conf["tarjetas"]),
        "activo": bool(_meta(c, modulo, "consumo_desde")), "consumo_desde": _meta(c, modulo, "consumo_desde"),
        "materiales": list(mats.values()), "posibles": posibles, "realizadas": realizadas,
        "bajo_minimo": sum(1 for m in mats.values() if m["bajo_minimo"]),
        "pendientes": _pendientes(c, conf),
        "movimientos": [dict(r) for r in c.execute("SELECT * FROM costeo_movimientos WHERE modulo=? ORDER BY id DESC LIMIT 100", (modulo,))],
        "consumos": [dict(r) for r in c.execute(
            "SELECT pcb_id, pcb_nombre, tarjeta, estado, MIN(creado_en) AS creado_en, COUNT(*) AS materiales FROM costeo_consumos "
            "WHERE modulo=? GROUP BY pcb_id, estado ORDER BY MAX(id) DESC LIMIT 100", (modulo,))],
    }


def estado(slug: str) -> Dict[str, Any]:
    conf = _conf(slug); _asegurar()
    with db.transaction() as c:
        _sincronizar(c, conf)
        return _estado(c, conf)


def activar(slug: str, desde: Optional[str] = None) -> Dict[str, Any]:
    """Empieza a descontar las tarjetas programadas desde esa fecha (por omisión, hoy). Cambiarla reconcilia todo."""
    conf = _conf(slug); _asegurar()
    desde = (desde or date.today().isoformat()).strip()
    if not _FECHA.match(desde):
        raise CosteoError("Fecha inválida: usa AAAA-MM-DD.")
    with db.transaction() as c:
        c.execute("INSERT INTO costeo_meta (modulo, clave, valor) VALUES (?, 'consumo_desde', ?) "
                  "ON CONFLICT(modulo, clave) DO UPDATE SET valor=excluded.valor", (conf["modulo"], desde))
        # placas anteriores a la nueva fecha: su consumo deja de contar (se borra, nunca existió para este inventario)
        if _tabla_existe(c, conf["tabla_pcb"]):
            c.execute(f"DELETE FROM costeo_consumos WHERE modulo=? AND pcb_id IN (SELECT id FROM {conf['tabla_pcb']} "
                      "WHERE programada_en IS NOT NULL AND substr(programada_en,1,10) < ?)", (conf["modulo"], desde))
        _sincronizar(c, conf)
        return _estado(c, conf)


def registrar_movimiento(slug: str, datos: Dict[str, Any], operador: str = "") -> Dict[str, Any]:
    conf = _conf(slug); _asegurar()
    desc = str(datos.get("descripcion") or "").strip()
    tipo = str(datos.get("tipo") or "").strip()
    if tipo not in TIPOS_MOV:
        raise CosteoError("Tipo inválido: entrada, salida o ajuste.")
    if tipo == "ajuste":
        try:
            cant = float(datos.get("cantidad"))
        except (TypeError, ValueError):
            raise CosteoError("«cantidad» debe ser un número.")
    else:
        cant = _num(datos.get("cantidad"), "cantidad")
    if not cant:
        raise CosteoError("La cantidad no puede ser cero.")
    with db.transaction() as c:
        if not c.execute("SELECT 1 FROM costeo_componentes WHERE modulo=? AND descripcion=?", (conf["modulo"], desc)).fetchone():
            raise CosteoError("Ese material no está en la lista de materiales de este módulo (agrégalo en Costos).")
        c.execute("INSERT INTO costeo_movimientos (modulo, descripcion, tipo, cantidad, nota, operador) VALUES (?,?,?,?,?,?)",
                  (conf["modulo"], desc, tipo, cant, str(datos.get("nota") or "").strip()[:300], operador or ""))
        _sincronizar(c, conf)
        return _estado(c, conf)


def eliminar_movimiento(slug: str, mid: int) -> Dict[str, Any]:
    conf = _conf(slug); _asegurar()
    with db.transaction() as c:
        if not c.execute("DELETE FROM costeo_movimientos WHERE id=? AND modulo=?", (mid, conf["modulo"])).rowcount:
            raise NoEncontrado("Ese movimiento no existe en este módulo.")
        _sincronizar(c, conf)
        return _estado(c, conf)


def fijar_minimo(slug: str, descripcion: str, minimo: Any) -> Dict[str, Any]:
    conf = _conf(slug); _asegurar()
    m = _num(minimo, "mínimo")
    with db.transaction() as c:
        c.execute("INSERT INTO costeo_minimos (modulo, descripcion, minimo) VALUES (?,?,?) "
                  "ON CONFLICT(modulo, descripcion) DO UPDATE SET minimo=excluded.minimo", (conf["modulo"], str(descripcion).strip(), m))
        _sincronizar(c, conf)
        return _estado(c, conf)


def asignar_tarjeta(slug: str, pcb_ids: List[int], tarjeta: str) -> Dict[str, Any]:
    """Dice qué tarjeta es cada placa (AntiJammer: RX o TX). Al corregirla, el consumo se rehace con la otra lista."""
    conf = _conf(slug); _asegurar()
    if tarjeta not in conf["tarjetas"]:
        raise CosteoError(f"Tarjeta inválida: usa {', '.join(conf['tarjetas'])}.")
    with db.transaction() as c:
        for pid in pcb_ids:
            c.execute("INSERT INTO costeo_pcb_tarjeta (modulo, pcb_id, tarjeta) VALUES (?,?,?) "
                      "ON CONFLICT(modulo, pcb_id) DO UPDATE SET tarjeta=excluded.tarjeta", (conf["modulo"], int(pid), tarjeta))
        _sincronizar(c, conf)
        return _estado(c, conf)
