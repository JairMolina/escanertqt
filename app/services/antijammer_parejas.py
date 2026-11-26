"""Parejas Skudo AntiJammer (v1.4.103): cada equipo lleva una placa RX y una TX, sin R1/R2/R3.

Emparejar dice cuál es RX y cuál TX (lo guarda también en Materiales, `costeo_pcb_tarjeta`, para que el consumo use su
lista de Costos) y las une en una pareja numerada. Deshacer la pareja conserva el RX/TX de cada placa.
Una placa solo puede estar en una pareja; las placas eliminadas sueltan su pareja.
"""
from typing import Any, Dict, List, Optional

from app.database import db
from app.services import antijammer as aj
from app.services import materiales


def _asegurar(c) -> None:
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS antijammer_parejas(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          rx_id INTEGER NOT NULL UNIQUE,
          tx_id INTEGER NOT NULL UNIQUE,
          operador TEXT,
          creada_en TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        )
        """
    )
    c.execute("DELETE FROM antijammer_parejas WHERE rx_id NOT IN (SELECT id FROM antijammer_pcb) "
              "OR tx_id NOT IN (SELECT id FROM antijammer_pcb)")


def _placa(c, codigo: Any) -> Dict[str, Any]:
    """Placa por id numérico (int) o por QR / nombre / serie (texto)."""
    if isinstance(codigo, int):
        r = c.execute("SELECT id, nombre, recibida_en, lote, estado FROM antijammer_pcb WHERE id=?", (codigo,)).fetchone()
        if not r:
            raise aj.NoEncontrada(f"La placa {codigo} no existe.")
        return dict(r)
    n = aj._nombre_de_codigo(str(codigo or ""))
    if not n:
        raise aj.NoEncontrada(f"'{str(codigo or '')[:40]}' no corresponde a una placa Skudo AntiJammer.")
    r = c.execute("SELECT id, nombre, recibida_en, lote, estado FROM antijammer_pcb WHERE nombre=?", (n,)).fetchone()
    if not r:
        raise aj.NoEncontrada(f"{n} no está registrada.")
    return dict(r)


def _tipos(c) -> Dict[int, str]:
    try:
        return {r["pcb_id"]: r["tarjeta"] for r in c.execute(
            "SELECT pcb_id, tarjeta FROM costeo_pcb_tarjeta WHERE modulo='skudo-antijammer'")}
    except Exception:   # Materiales aún no creó su tabla
        return {}


def listar(mes: Optional[str] = None) -> Dict[str, Any]:
    """Parejas y placas sin pareja. `mes` = 'AAAA-MM' (fecha de recepción) filtra; vacío = todas."""
    aj._asegurar()
    materiales._asegurar()
    with db.transaction() as c:
        _asegurar(c)
        tipos = _tipos(c)
        filtro, args = ("", ())
        if mes:
            filtro, args = (" WHERE substr(recibida_en,1,7)=?", (mes[:7],))
        placas = {r["id"]: dict(r) for r in c.execute(
            f"SELECT id, nombre, recibida_en, lote, estado FROM antijammer_pcb{filtro} ORDER BY nombre", args)}
        meses = [r[0] for r in c.execute(
            "SELECT DISTINCT substr(recibida_en,1,7) FROM antijammer_pcb ORDER BY 1 DESC") if r[0]]
        parejas = []
        for p in c.execute("SELECT * FROM antijammer_parejas ORDER BY id DESC"):
            rx, tx = placas.get(p["rx_id"]), placas.get(p["tx_id"])
            if mes and not (rx or tx):
                continue
            if not rx:
                rx = _placa(c, int(p["rx_id"]))
            if not tx:
                tx = _placa(c, int(p["tx_id"]))
            parejas.append({"id": p["id"], "rx": rx, "tx": tx, "operador": p["operador"], "creada_en": p["creada_en"]})
        todas_usadas = {x for r in c.execute("SELECT rx_id, tx_id FROM antijammer_parejas") for x in r}
        sueltas = [dict(v, tipo=tipos.get(k, "")) for k, v in placas.items() if k not in todas_usadas]
    return {"parejas": parejas, "sin_pareja": sueltas, "meses": meses, "mes": mes or ""}


def emparejar(rx: Any, tx: Any, operador: Optional[str] = None) -> Dict[str, Any]:
    """Une una placa RX con una TX (por id o código) y guarda su RX/TX en Materiales."""
    aj._asegurar()
    materiales._asegurar()
    with db.transaction() as c:
        _asegurar(c)
        a, b = _placa(c, rx), _placa(c, tx)
        if a["id"] == b["id"]:
            raise aj.Invalida("La RX y la TX deben ser placas distintas.")
        for p in (a, b):
            ya = c.execute("SELECT id FROM antijammer_parejas WHERE rx_id=? OR tx_id=?", (p["id"], p["id"])).fetchone()
            if ya:
                raise aj.Duplicada(f"{p['nombre']} ya está en la pareja #{ya['id']}. Deshazla primero.")
        cur = c.execute("INSERT INTO antijammer_parejas(rx_id, tx_id, operador) VALUES (?,?,?)", (a["id"], b["id"], operador))
        pid = cur.lastrowid
        aj._evento(c, a["id"], a["nombre"], "emparejada", f"Pareja #{pid}: RX con {b['nombre']} (TX)", operador)
        aj._evento(c, b["id"], b["nombre"], "emparejada", f"Pareja #{pid}: TX con {a['nombre']} (RX)", operador)
    try:   # RX/TX en Materiales (rehace el consumo con la lista correcta); si falla, la pareja no queda a medias
        materiales.asignar_tarjeta("antijammer", [a["id"]], "RX")
        materiales.asignar_tarjeta("antijammer", [b["id"]], "TX")
    except Exception:
        with db.transaction() as c:
            c.execute("DELETE FROM antijammer_parejas WHERE id=?", (pid,))
        raise
    return {"id": pid, "rx": a, "tx": b}


def deshacer(pareja_id: int, operador: Optional[str] = None) -> Dict[str, Any]:
    """Deshace la pareja; cada placa conserva su RX/TX."""
    aj._asegurar()
    with db.transaction() as c:
        _asegurar(c)
        p = c.execute("SELECT * FROM antijammer_parejas WHERE id=?", (int(pareja_id),)).fetchone()
        if not p:
            raise aj.NoEncontrada(f"La pareja #{pareja_id} no existe.")
        a, b = _placa(c, int(p["rx_id"])), _placa(c, int(p["tx_id"]))
        c.execute("DELETE FROM antijammer_parejas WHERE id=?", (p["id"],))
        for x, y in ((a, b), (b, a)):
            aj._evento(c, x["id"], x["nombre"], "desemparejada", f"Pareja #{p['id']} deshecha (con {y['nombre']})", operador)
    return {"id": p["id"], "rx": a, "tx": b}


def pareja_de(pcb_id: int) -> Optional[Dict[str, Any]]:
    """Pareja de una placa (para fichas/etiquetas); None si no tiene."""
    with db.transaction() as c:
        _asegurar(c)
        p = c.execute("SELECT * FROM antijammer_parejas WHERE rx_id=? OR tx_id=?", (pcb_id, pcb_id)).fetchone()
        return dict(p) if p else None
