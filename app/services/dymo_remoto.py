"""v1.4.2: DYMO compartida. Cola de etiquetas que imprime un agente remoto (Raspberry Pi con la LabelWriter por USB).

El agente solo hace conexiones salientes: latido, long-poll de `siguiente`, descarga del SVG y resultado. Un trabajo se
entrega UNA vez; si el agente lo vuelve a pedir (se reinició) recibe el mismo id y no lo reimprime. Lo que no se toma en
PENDIENTE_TTL se cancela (evita que salgan etiquetas viejas cuando la Raspberry vuelve) y lo tomado sin resultado en
ENVIADA_TTL queda «desconocido» (nunca se reimprime solo)."""

import hashlib, json, secrets, time
from app.database import db

TIPOS = ("tarjeta", "aprobada", "cable", "r3")
FINALES = ("impresa", "error", "desconocido", "cancelada")
EN_LINEA_S = 45          # latido cada 15 s
PENDIENTE_TTL = 600
ENVIADA_TTL = 600


def init():
    with db.get_db() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS dymo_agentes(id TEXT PRIMARY KEY, nombre TEXT NOT NULL, token_hash TEXT NOT NULL UNIQUE,
              creado REAL NOT NULL, last_seen REAL NOT NULL DEFAULT 0, estado TEXT);
            CREATE TABLE IF NOT EXISTS dymo_trabajos(id TEXT PRIMARY KEY, tipo TEXT NOT NULL, params TEXT NOT NULL,
              copias INTEGER NOT NULL, descripcion TEXT NOT NULL, operador TEXT NOT NULL, estado TEXT NOT NULL,
              agente TEXT, creado REAL NOT NULL, actualizado REAL NOT NULL, detalle TEXT, cups_id TEXT);
            CREATE INDEX IF NOT EXISTS dymo_trabajos_estado ON dymo_trabajos(estado, creado);
            """
        )


def _h(token):
    return hashlib.sha256(token.encode()).hexdigest()


def agente_crear(nombre):
    """Alta de un agente (la ejecuta un administrador en el servidor). Devuelve el token una sola vez."""
    init()
    aid, token = secrets.token_hex(8), secrets.token_urlsafe(32)
    with db.get_db() as c:
        c.execute("INSERT INTO dymo_agentes(id,nombre,token_hash,creado) VALUES(?,?,?,?)", (aid, nombre[:60], _h(token), time.time()))
    return {"id": aid, "nombre": nombre, "token": token}


def agente_auth(token):
    init()
    with db.get_db() as c:
        r = c.execute("SELECT id,nombre FROM dymo_agentes WHERE token_hash=?", (_h(token),)).fetchone()
    if not r:
        raise ValueError("Credencial de agente DYMO inválida.")
    return dict(r)


def _vencer(c, now):
    c.execute("UPDATE dymo_trabajos SET estado='cancelada',detalle='La DYMO compartida no lo tomó a tiempo; no se imprimió.',actualizado=? "
              "WHERE estado='pendiente' AND creado<?", (now, now - PENDIENTE_TTL))
    c.execute("UPDATE dymo_trabajos SET estado='desconocido',detalle='La Raspberry no confirmó la impresión.',actualizado=? "
              "WHERE estado='enviada' AND actualizado<?", (now, now - ENVIADA_TTL))


def latido(aid, estado):
    with db.get_db() as c:
        _vencer(c, time.time())   # v1.4.9: vencer también aquí; antes solo en tomar() y un agente atorado lo frenaba
        c.execute("UPDATE dymo_agentes SET last_seen=?,estado=? WHERE id=?", (time.time(), json.dumps(estado, ensure_ascii=False)[:2000], aid))
    return {"ok": True}


def estado():
    """Para la web: si hay una DYMO compartida en línea y lista."""
    init()
    now = time.time()
    with db.get_db() as c:
        _vencer(c, now)
        ags = [dict(r) for r in c.execute("SELECT id,nombre,last_seen,estado FROM dymo_agentes ORDER BY last_seen DESC")]
        cola = c.execute("SELECT COUNT(*) n FROM dymo_trabajos WHERE estado IN ('pendiente','enviada')").fetchone()["n"]
    out = []
    for a in ags:
        st = json.loads(a["estado"]) if a["estado"] else {}
        out.append({"nombre": a["nombre"], "en_linea": now - a["last_seen"] < EN_LINEA_S,
                    "impresora_ok": bool(st.get("impresora_ok")), "detalle": str(st.get("detalle") or "")[:200]})
    lista = any(a["en_linea"] and a["impresora_ok"] for a in out)
    return {"disponible": lista, "agentes": out, "en_cola": cola}


def encolar(tipo, params, copias, descripcion, operador):
    if tipo not in TIPOS:
        raise ValueError("Tipo de etiqueta inválido.")
    if not estado()["disponible"]:
        raise ValueError("La DYMO compartida no está en línea o la impresora no está lista; no se envió la etiqueta.")
    jid, now = secrets.token_hex(12), time.time()
    with db.get_db() as c:
        c.execute("INSERT INTO dymo_trabajos(id,tipo,params,copias,descripcion,operador,estado,creado,actualizado) VALUES(?,?,?,?,?,?,?,?,?)",
                  (jid, tipo, json.dumps(params), copias, descripcion[:120], operador, "pendiente", now, now))
    return trabajo(jid)


def trabajo(jid):
    init()
    with db.get_db() as c:
        _vencer(c, time.time())
        r = c.execute("SELECT id,tipo,copias,descripcion,operador,estado,creado,actualizado,detalle FROM dymo_trabajos WHERE id=?", (jid,)).fetchone()
        pos = c.execute("SELECT COUNT(*) n FROM dymo_trabajos WHERE estado='pendiente' AND creado<(SELECT creado FROM dymo_trabajos WHERE id=?)", (jid,)).fetchone()["n"] if r else 0
    if not r:
        raise ValueError("Trabajo de impresión no encontrado.")
    return dict(r, delante=pos)


def cancelar(jid):
    with db.get_db() as c:
        n = c.execute("UPDATE dymo_trabajos SET estado='cancelada',detalle='Cancelada por el operador.',actualizado=? WHERE id=? AND estado='pendiente'",
                      (time.time(), jid)).rowcount
    if not n:
        raise ValueError("Solo se cancela una etiqueta que aún no se envió a la impresora.")
    return trabajo(jid)


def tomar(aid):
    """El siguiente trabajo para el agente: primero el que ya tenía sin resultado (se reinició), luego el pendiente más viejo."""
    init()
    now = time.time()
    with db.transaction() as c:
        _vencer(c, now)
        r = c.execute("SELECT * FROM dymo_trabajos WHERE estado='enviada' AND agente=? ORDER BY creado LIMIT 1", (aid,)).fetchone()
        if not r:
            r = c.execute("SELECT * FROM dymo_trabajos WHERE estado='pendiente' ORDER BY creado LIMIT 1").fetchone()
            if not r:
                return None
            c.execute("UPDATE dymo_trabajos SET estado='enviada',agente=?,actualizado=? WHERE id=?", (aid, now, r["id"]))
    return {"id": r["id"], "tipo": r["tipo"], "params": json.loads(r["params"]), "copias": r["copias"], "descripcion": r["descripcion"]}


def del_agente(aid, jid):
    with db.get_db() as c:
        r = c.execute("SELECT * FROM dymo_trabajos WHERE id=? AND agente=?", (jid, aid)).fetchone()
    if not r:
        raise ValueError("El trabajo no está asignado a este agente.")
    return dict(r, params=json.loads(r["params"]))


def resultado(aid, jid, estado_, detalle, cups_id):
    if estado_ not in ("impresa", "error", "desconocido"):
        raise ValueError("Estado de resultado inválido.")
    with db.transaction() as c:
        r = c.execute("SELECT estado FROM dymo_trabajos WHERE id=? AND agente=?", (jid, aid)).fetchone()
        if not r:
            raise ValueError("El trabajo no está asignado a este agente.")
        if r["estado"] == "enviada" or (r["estado"] == "desconocido" and estado_ != "desconocido"):
            c.execute("UPDATE dymo_trabajos SET estado=?,detalle=?,cups_id=?,actualizado=? WHERE id=?",
                      (estado_, str(detalle or "")[:500], str(cups_id or "")[:64], time.time(), jid))
    return {"ok": True}


if __name__ == "__main__":   # alta del agente desde el servidor: python -m app.services.dymo_remoto "Raspberry DYMO"
    import sys
    print(json.dumps(agente_crear(" ".join(sys.argv[1:]) or "Raspberry DYMO"), ensure_ascii=False))
