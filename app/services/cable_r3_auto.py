"""v1.4.6: impresión automática de la etiqueta «Cable R3» (TQT: 0000 / R3: 0000) en la DYMO compartida (Raspberry).

Se activa en Administración (ajuste `dymo_cable_r3_auto`). Cada vez que el servidor notifica una tarjeta (emparejar, armar,
asignar o reemplazar placas), si la tarjeta tiene una R3 que todavía no se imprimió con esa tarjeta, se encola una etiqueta.
La pareja (tarjeta, R3) se registra en `dymo_cable_r3_hechas` para no repetir; al activar el interruptor, las parejas que ya
existían se marcan como hechas (solo se imprimen las asignaciones nuevas). Si la DYMO compartida no está en línea, no se
encola y la pareja queda pendiente: se reintenta en la siguiente actualización de esa tarjeta.
"""
import logging
import re
from typing import Any, Dict, Optional

from app.database import db
from app.services import dymo_remoto

logger = logging.getLogger(__name__)
CLAVE = "dymo_cable_r3_auto"
OPERADOR = "Automático (R3 asignada)"


def _init(c) -> None:
    c.execute("CREATE TABLE IF NOT EXISTS dymo_cable_r3_hechas (tarjeta_id INTEGER NOT NULL, r3 TEXT NOT NULL, "
              "creado TEXT NOT NULL DEFAULT (datetime('now','localtime')), PRIMARY KEY (tarjeta_id, r3))")


def numero_r3(tarjeta: Dict[str, Any]) -> str:
    if "r3" in tarjeta:   # tarjeta enriquecida: r3 = None si no tiene R3
        nombre = (tarjeta["r3"] or {}).get("nombre") or ""
    else:
        nombre = tarjeta.get("nombre_r3") or ""
    m = re.search(r"(\d{4})$", str(nombre))
    return m.group(1) if m else ""


def numero_tarjeta(tarjeta: Dict[str, Any]) -> str:
    return re.sub(r"\D", "", str(tarjeta.get("id_tarjeta_num") or "")).zfill(4)[-6:]


def activo() -> bool:
    with db.get_db() as c:
        r = c.execute("SELECT valor FROM ajustes WHERE clave = ?", (CLAVE,)).fetchone()
    return bool(r and r["valor"] == "1")


def set_activo(on: bool) -> Dict[str, Any]:
    marcadas = 0
    with db.get_db() as c:
        _init(c)
        antes = c.execute("SELECT valor FROM ajustes WHERE clave = ?", (CLAVE,)).fetchone()
        if on and not (antes and antes["valor"] == "1"):   # al encender: lo ya emparejado no se imprime
            for r in c.execute("SELECT t.id, p.nombre FROM tarjetas_produccion t JOIN pcb_inventario p ON p.id = t.pcb_r3_id").fetchall():
                n = numero_r3({"nombre_r3": r["nombre"]})
                if n:
                    marcadas += c.execute("INSERT OR IGNORE INTO dymo_cable_r3_hechas (tarjeta_id, r3) VALUES (?, ?)", (r["id"], n)).rowcount
        c.execute("INSERT INTO ajustes (clave, valor, updated_at) VALUES (?, ?, datetime('now','localtime')) "
                  "ON CONFLICT(clave) DO UPDATE SET valor = excluded.valor, updated_at = excluded.updated_at", (CLAVE, "1" if on else "0"))
    return {"activo": on, "marcadas": marcadas}


def estado() -> Dict[str, Any]:
    d = dymo_remoto.estado()
    return {"activo": activo(), "dymo_disponible": bool(d.get("disponible")), "dymo": d}


def al_notificar(tarjeta: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Encola la etiqueta si la tarjeta trae una R3 nueva. Devuelve {ok, mensaje} o None si no aplica. Nunca lanza."""
    try:
        if not tarjeta or not activo():
            return None
        r3, num = numero_r3(tarjeta), numero_tarjeta(tarjeta)
        if not r3 or not re.fullmatch(r"[0-9]{1,6}", num):
            return None
        with db.get_db() as c:
            _init(c)
            if not c.execute("INSERT OR IGNORE INTO dymo_cable_r3_hechas (tarjeta_id, r3) VALUES (?, ?)", (tarjeta["id"], r3)).rowcount:
                return None   # ya se imprimió (o ya existía al encender el interruptor)
        desc = f"Cable TQT {num} · R3 {r3} (automático)"
        try:
            dymo_remoto.encolar("cable", {"numero": num, "r3": r3}, 1, desc, OPERADOR)
        except ValueError as e:   # DYMO compartida fuera de línea: queda pendiente para el siguiente aviso de la tarjeta
            with db.get_db() as c:
                c.execute("DELETE FROM dymo_cable_r3_hechas WHERE tarjeta_id = ? AND r3 = ?", (tarjeta["id"], r3))
            db.log_evento("CABLE_R3_SIN_DYMO", tarjeta.get("lote_id"), f"TQT {num} · R3 {r3}", str(e)[:200], OPERADOR)
            return {"ok": False, "mensaje": f"Cable R3 de TQT {num} no impreso: {e}"}
        db.log_evento("CABLE_R3_AUTO", tarjeta.get("lote_id"), f"TQT {num} · R3 {r3}", "Encolada en la DYMO compartida", OPERADOR)
        return {"ok": True, "mensaje": f"Cable R3 enviado a la DYMO compartida: TQT {num} · R3 {r3}"}
    except Exception:   # la impresión automática nunca debe romper el emparejamiento
        logger.exception("Impresión automática de cable R3")
        return None
