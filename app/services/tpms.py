"""v1.4.27: módulo TPMS. Alta de placas PCB TPMS por QR (versión, serie, lote de texto libre y quién/cuándo la recibió).

Tabla propia `tpms_pcb` (se crea sola). No escribe en `escaneos` ni en el inventario TQT: los tableros de Escáner TQT no
deben contar placas TPMS. El QR se interpreta con `models.parse_tpms` (el mismo que hace que Escáner TQT las rechace).
"""
from typing import Any, Dict, List, Optional

from app.database import db
from app.database.models import parse_tpms


def _asegurar() -> None:
    """Crea la tabla si falta (idempotente)."""
    with db.get_db() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS tpms_pcb(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              nombre TEXT NOT NULL UNIQUE,          -- 'TPMS-V1-0004'
              version TEXT NOT NULL,
              serie TEXT NOT NULL,
              codigo_qr TEXT NOT NULL DEFAULT '',   -- texto leído tal cual (las V1 traen la plantilla de la R3 Timer)
              lote TEXT NOT NULL DEFAULT '',
              operador TEXT,
              recibida_en TEXT NOT NULL DEFAULT (datetime('now','localtime'))
            );
            CREATE INDEX IF NOT EXISTS ix_tpms_pcb_lote ON tpms_pcb(lote);
            """
        )


def escanear(codigo: str, lote: str = "", operador: Optional[str] = None) -> Dict[str, Any]:
    """Alta idempotente: AGREGADA | REPETIDA | INVALIDA (nunca lanza por negocio)."""
    p = parse_tpms(codigo)
    if not p:
        return {"resultado": "INVALIDA", "mensaje": f"'{(codigo or '')[:40]}' no es un QR de placa TPMS (ej. TPMS_V1_0004).", "pcb": None}
    _asegurar()
    with db.transaction() as c:
        fila = c.execute("SELECT * FROM tpms_pcb WHERE nombre = ?", (p["nombre"],)).fetchone()
        if fila:
            return {"resultado": "REPETIDA", "mensaje": f"{p['nombre']} ya estaba registrada.", "pcb": dict(fila)}
        c.execute("INSERT INTO tpms_pcb(nombre, version, serie, codigo_qr, lote, operador) VALUES (?,?,?,?,?,?)",
                  (p["nombre"], p["version"], p["serie"], (codigo or "").strip()[:120], (lote or "").strip()[:60], operador))
        fila = c.execute("SELECT * FROM tpms_pcb WHERE nombre = ?", (p["nombre"],)).fetchone()
    return {"resultado": "AGREGADA", "mensaje": f"{p['nombre']} registrada.", "pcb": dict(fila)}


def listar(lote: Optional[str] = None, limit: int = 500) -> Dict[str, Any]:
    _asegurar()
    sql, args = "SELECT * FROM tpms_pcb", []
    if lote is not None:
        sql, args = sql + " WHERE lote = ?", [lote]
    with db.get_db() as c:
        items: List[Dict[str, Any]] = [dict(r) for r in c.execute(sql + " ORDER BY id DESC LIMIT ?", (*args, limit))]
        total = c.execute("SELECT COUNT(*) FROM tpms_pcb").fetchone()[0]
    return {"items": items, "total": total}
