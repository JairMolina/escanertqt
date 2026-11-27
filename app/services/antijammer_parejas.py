"""Parejas Skudo AntiJammer (v1.4.104): cada equipo lleva una placa RX y una TX, sin R1/R2/R3, unidas por un NÚMERO de pareja.

El número se le da a la placa al programarla (Programar: RX/TX + número) y la pareja se forma sola cuando la RX y la TX
comparten número; también se puede emparejar a mano (Emparejar). Una pareja puede estar incompleta (solo RX o solo TX)
mientras se programa la otra. El RX/TX se guarda también en Materiales (`costeo_pcb_tarjeta`) para que el consumo use su lista
de Costos. Deshacer la pareja suelta ambas placas y cada una conserva su RX/TX. Las placas eliminadas sueltan su lado.
"""
from typing import Any, Dict, List, Optional

from app.database import db
from app.services import antijammer as aj
from app.services import materiales

NUMERO_MAX = 9999
LADO = {"RX": "rx_id", "TX": "tx_id"}


def _asegurar(c) -> None:
    cols = [r[1] for r in c.execute("PRAGMA table_info(antijammer_parejas)")]
    if cols and "numero" not in cols:   # tabla de 1.4.103 (sin número): el número de cada pareja es su id
        c.execute("ALTER TABLE antijammer_parejas RENAME TO antijammer_parejas_1403")
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS antijammer_parejas(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          numero INTEGER NOT NULL UNIQUE,
          rx_id INTEGER UNIQUE,
          tx_id INTEGER UNIQUE,
          operador TEXT,
          creada_en TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        )
        """
    )
    if cols and "numero" not in cols:
        c.execute("INSERT INTO antijammer_parejas(id, numero, rx_id, tx_id, operador, creada_en) "
                  "SELECT id, id, rx_id, tx_id, operador, creada_en FROM antijammer_parejas_1403")
        c.execute("DROP TABLE antijammer_parejas_1403")
    for col in ("rx_id", "tx_id"):
        c.execute(f"UPDATE antijammer_parejas SET {col}=NULL WHERE {col} IS NOT NULL AND {col} NOT IN (SELECT id FROM antijammer_pcb)")
    c.execute("DELETE FROM antijammer_parejas WHERE rx_id IS NULL AND tx_id IS NULL")


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


def _numero(v: Any) -> int:
    try:
        n = int(v)
    except (TypeError, ValueError):
        raise aj.Invalida("El número de pareja debe ser un número entero.")
    if not 1 <= n <= NUMERO_MAX:
        raise aj.Invalida(f"El número de pareja va de 1 a {NUMERO_MAX}.")
    return n


def _tipo(v: Any) -> str:
    t = str(v or "").strip().upper()
    if t not in LADO:
        raise aj.Invalida("Indica si la placa es RX o TX.")
    return t


def _tipos(c) -> Dict[int, str]:
    try:
        return {r["pcb_id"]: r["tarjeta"] for r in c.execute(
            "SELECT pcb_id, tarjeta FROM costeo_pcb_tarjeta WHERE modulo='skudo-antijammer'")}
    except Exception:   # Materiales aún no creó su tabla
        return {}


def _fila_de(c, pcb_id: int):
    return c.execute("SELECT * FROM antijammer_parejas WHERE rx_id=? OR tx_id=?", (pcb_id, pcb_id)).fetchone()


def _soltar(c, pcb_id: int) -> None:
    c.execute("UPDATE antijammer_parejas SET rx_id = CASE WHEN rx_id=? THEN NULL ELSE rx_id END, "
              "tx_id = CASE WHEN tx_id=? THEN NULL ELSE tx_id END WHERE rx_id=? OR tx_id=?", (pcb_id,) * 4)
    c.execute("DELETE FROM antijammer_parejas WHERE rx_id IS NULL AND tx_id IS NULL")


def _poner(c, p: Dict[str, Any], tipo: str, numero: int, operador: Optional[str], mover: bool) -> bool:
    """Pone la placa `p` como `tipo` en la pareja `numero`. True si cambió algo."""
    col, otro = LADO[tipo], LADO["TX" if tipo == "RX" else "RX"]
    ya = _fila_de(c, p["id"])
    if ya and ya["numero"] == numero and ya[col] == p["id"]:
        return False
    if ya and not mover:
        raise aj.Duplicada(f"{p['nombre']} ya está en la pareja {ya['numero']}. Deshazla primero.")
    fila = c.execute("SELECT * FROM antijammer_parejas WHERE numero=?", (numero,)).fetchone()
    if fila and fila[col] is not None and fila[col] != p["id"]:
        dueno = c.execute("SELECT nombre FROM antijammer_pcb WHERE id=?", (fila[col],)).fetchone()
        raise aj.Duplicada(f"La pareja {numero} ya tiene {tipo}: {dueno['nombre'] if dueno else fila[col]}.")
    if ya:
        _soltar(c, p["id"])
        fila = c.execute("SELECT * FROM antijammer_parejas WHERE numero=?", (numero,)).fetchone()
    if fila:
        c.execute(f"UPDATE antijammer_parejas SET {col}=? WHERE id=?", (p["id"], fila["id"]))
        socio = fila[otro]
    else:
        c.execute(f"INSERT INTO antijammer_parejas(numero, {col}, operador) VALUES (?,?,?)", (numero, p["id"], operador))
        socio = None
    s = c.execute("SELECT nombre FROM antijammer_pcb WHERE id=?", (socio,)).fetchone() if socio else None
    aj._evento(c, p["id"], p["nombre"], "emparejada",
               f"Pareja {numero}: {tipo}" + (f" con {s['nombre']}" if s else " (falta su pareja)"), operador)
    return True


def _materiales(pares: List[tuple]) -> None:
    for pid, tipo in pares:
        materiales.asignar_tarjeta("antijammer", [pid], tipo)


def _salida(c, fila) -> Dict[str, Any]:
    ver = lambda i: _placa(c, int(i)) if i else None   # noqa: E731
    return {"id": fila["id"], "numero": fila["numero"], "rx": ver(fila["rx_id"]), "tx": ver(fila["tx_id"]),
            "completa": bool(fila["rx_id"] and fila["tx_id"]), "operador": fila["operador"], "creada_en": fila["creada_en"]}


def listar(mes: Optional[str] = None) -> Dict[str, Any]:
    """Parejas (completas e incompletas, por número) y placas sin pareja. `mes` = 'AAAA-MM' (fecha de recepción) filtra."""
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
        parejas, usadas = [], set()
        for p in c.execute("SELECT * FROM antijammer_parejas ORDER BY numero"):
            usadas.update(x for x in (p["rx_id"], p["tx_id"]) if x)
            if mes and not (placas.get(p["rx_id"]) or placas.get(p["tx_id"])):
                continue
            parejas.append(_salida(c, p))
        siguiente = (c.execute("SELECT MAX(numero) FROM antijammer_parejas").fetchone()[0] or 0) + 1
        sueltas = [dict(v, tipo=tipos.get(k, "")) for k, v in placas.items() if k not in usadas]
    return {"parejas": parejas, "sin_pareja": sueltas, "meses": meses, "mes": mes or "", "siguiente": min(siguiente, NUMERO_MAX)}


def asignar(pcb: Any, tipo: Any, numero: Any, operador: Optional[str] = None) -> Dict[str, Any]:
    """Al programar: la placa es `tipo` (RX/TX) de la pareja `numero`. Si su compañera ya tiene ese número, la pareja queda
    completa. Si la placa estaba en otra pareja, se cambia a esta (lo programado manda)."""
    t, n = _tipo(tipo), _numero(numero)
    aj._asegurar()
    materiales._asegurar()
    with db.transaction() as c:
        _asegurar(c)
        p = _placa(c, pcb)
        antes = _fila_de(c, p["id"])
        _poner(c, p, t, n, operador, mover=True)
        fila = c.execute("SELECT * FROM antijammer_parejas WHERE numero=?", (n,)).fetchone()
        out = _salida(c, fila)
    try:
        _materiales([(p["id"], t)])
    except Exception:
        with db.transaction() as c:   # deja la placa como estaba
            _soltar(c, p["id"])
            if antes:
                lado = "rx_id" if antes["rx_id"] == p["id"] else "tx_id"
                if c.execute("SELECT id FROM antijammer_parejas WHERE numero=?", (antes["numero"],)).fetchone():
                    c.execute(f"UPDATE antijammer_parejas SET {lado}=? WHERE numero=?", (p["id"], antes["numero"]))
                else:
                    c.execute(f"INSERT INTO antijammer_parejas(numero, {lado}, operador, creada_en) VALUES (?,?,?,?)",
                              (antes["numero"], p["id"], antes["operador"], antes["creada_en"]))
        raise
    return out


def emparejar(rx: Any, tx: Any, operador: Optional[str] = None, numero: Any = None) -> Dict[str, Any]:
    """A mano: une una placa RX con una TX (por id o código) con el número dado (o el siguiente libre)."""
    aj._asegurar()
    materiales._asegurar()
    with db.transaction() as c:
        _asegurar(c)
        a, b = _placa(c, rx), _placa(c, tx)
        if a["id"] == b["id"]:
            raise aj.Invalida("La RX y la TX deben ser placas distintas.")
        n = _numero(numero) if numero not in (None, "") else (c.execute("SELECT MAX(numero) FROM antijammer_parejas").fetchone()[0] or 0) + 1
        _numero(n)
        _poner(c, a, "RX", n, operador, mover=False)
        _poner(c, b, "TX", n, operador, mover=False)
        out = _salida(c, c.execute("SELECT * FROM antijammer_parejas WHERE numero=?", (n,)).fetchone())
    try:   # RX/TX en Materiales (rehace el consumo con la lista correcta); si falla, la pareja no queda a medias
        _materiales([(a["id"], "RX"), (b["id"], "TX")])
    except Exception:
        with db.transaction() as c:
            _soltar(c, a["id"]); _soltar(c, b["id"])
        raise
    return out


def deshacer(pareja_id: int, operador: Optional[str] = None) -> Dict[str, Any]:
    """Deshace la pareja (por id); cada placa conserva su RX/TX."""
    aj._asegurar()
    with db.transaction() as c:
        _asegurar(c)
        p = c.execute("SELECT * FROM antijammer_parejas WHERE id=?", (int(pareja_id),)).fetchone()
        if not p:
            raise aj.NoEncontrada(f"La pareja #{pareja_id} no existe.")
        out = _salida(c, p)
        c.execute("DELETE FROM antijammer_parejas WHERE id=?", (p["id"],))
        for x, y in ((out["rx"], out["tx"]), (out["tx"], out["rx"])):
            if x:
                aj._evento(c, x["id"], x["nombre"], "desemparejada",
                           f"Pareja {p['numero']} deshecha" + (f" (con {y['nombre']})" if y else ""), operador)
    return out


def renumerar(pareja_id: int, numero: Any, operador: Optional[str] = None) -> Dict[str, Any]:
    """v1.4.105: cambia a mano el número de una pareja (el número de emparejado no siempre es el real del equipo).
    Si el número nuevo es de otra pareja INCOMPLETA cuyo lado libre coincide (una tiene solo RX y la otra solo TX), se unen
    en una sola; si chocan, 409 sin tocar nada. La etiqueta toma el número nuevo al imprimirse."""
    n = _numero(numero)
    aj._asegurar()
    with db.transaction() as c:
        _asegurar(c)
        p = c.execute("SELECT * FROM antijammer_parejas WHERE id=?", (int(pareja_id),)).fetchone()
        if not p:
            raise aj.NoEncontrada(f"La pareja #{pareja_id} no existe.")
        viejo = p["numero"]
        if viejo == n:
            return _salida(c, p)
        otra = c.execute("SELECT * FROM antijammer_parejas WHERE numero=?", (n,)).fetchone()
        if otra:
            choque = [k for k in ("rx_id", "tx_id") if p[k] and otra[k]]
            if choque:
                lado = "RX" if choque[0] == "rx_id" else "TX"
                d = c.execute("SELECT nombre FROM antijammer_pcb WHERE id=?", (otra[choque[0]],)).fetchone()
                raise aj.Duplicada(f"El número {n} ya es de otra pareja que tiene {lado}: {d['nombre'] if d else otra[choque[0]]}.")
            c.execute("DELETE FROM antijammer_parejas WHERE id=?", (p["id"],))
            for k in ("rx_id", "tx_id"):
                if p[k]:
                    c.execute(f"UPDATE antijammer_parejas SET {k}=? WHERE id=?", (p[k], otra["id"]))
            fila_id = otra["id"]
        else:
            c.execute("UPDATE antijammer_parejas SET numero=? WHERE id=?", (n, p["id"]))
            fila_id = p["id"]
        fila = c.execute("SELECT * FROM antijammer_parejas WHERE id=?", (fila_id,)).fetchone()
        out = _salida(c, fila)
        for k in ("rx", "tx"):
            if out[k]:
                aj._evento(c, out[k]["id"], out[k]["nombre"], "renumerada",
                           f"Pareja {viejo} → {n}" + (" (unida con la pareja que ya tenía ese número)" if otra else ""), operador)
    return out


def de_placa(pcb_id: int) -> Optional[Dict[str, Any]]:
    """{numero, tipo, socio} de la pareja de una placa (etiquetas, fichas); None si no tiene número."""
    with db.transaction() as c:
        _asegurar(c)
        f = _fila_de(c, pcb_id)
        if not f:
            return None
        tipo = "RX" if f["rx_id"] == pcb_id else "TX"
        socio = f["tx_id"] if tipo == "RX" else f["rx_id"]
        s = c.execute("SELECT nombre FROM antijammer_pcb WHERE id=?", (socio,)).fetchone() if socio else None
        return {"numero": f["numero"], "tipo": tipo, "socio": s["nombre"] if s else None}


def pareja_de(pcb_id: int) -> Optional[Dict[str, Any]]:
    """Fila de la pareja de una placa; None si no tiene."""
    with db.transaction() as c:
        _asegurar(c)
        p = _fila_de(c, pcb_id)
        return dict(p) if p else None
