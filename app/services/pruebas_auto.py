"""v1.4.51 · Pruebas automáticas (luna de Escáner TQT): campañas de resistencia de firmware.

Una campaña deja una tarjeta armada conectada a un agente de Pruebas TQT (p. ej. la Raspberry de la DYMO) y repite la
MISMA secuencia de 14 etapas de Pruebas TQT N veces. Cada ciclo es una ejecución normal de `tqt_test_runs` (mismo
snapshot, cotejo, veredicto, LOG y reporte); aquí solo se agrupan y se encadenan.

El servidor encadena: `programar()` corre dentro del `claim` del agente y, si la estación está libre, el puerto serie
conectado y pasó la pausa, encola el siguiente ciclo. Reglas de seguridad:
- Un ciclo interrumpido/no verificado DETIENE la campaña (Pruebas TQT exige revisar físicamente antes de repetir).
- Un fallido la detiene si `detener_en_falla`; si no, sigue contando fallas.
- Nunca libera ni cambia el estado de fabricación de la tarjeta (`release_authorized` sigue en False)."""

import json
import secrets
import time

from app.database import db
from app.services import stm32_programming as stm
from app.services import test_station as ts

ACTIVAS = ("activa", "pausada")
APROBADOS = ("aprobado", "aprobado_con_advertencias")
MAX_CICLOS = 1000
MAX_PAUSA_S = 3600


def init():
    ts.init()
    with db.get_db() as c:
        c.executescript(
            """
        CREATE TABLE IF NOT EXISTS tqt_resistencia(
          id TEXT PRIMARY KEY, nombre TEXT NOT NULL, firmware TEXT NOT NULL,
          station TEXT NOT NULL REFERENCES stm32_stations(id),
          tarjeta_id INTEGER NOT NULL REFERENCES tarjetas_produccion(id),
          ciclos INTEGER NOT NULL, pausa_s INTEGER NOT NULL, detener_en_falla INTEGER NOT NULL,
          estado TEXT NOT NULL, motivo TEXT, operador TEXT NOT NULL, creado REAL NOT NULL, actualizado REAL NOT NULL);
        CREATE UNIQUE INDEX IF NOT EXISTS tqt_resistencia_estacion ON tqt_resistencia(station) WHERE estado IN ('activa','pausada');
        CREATE UNIQUE INDEX IF NOT EXISTS tqt_resistencia_tarjeta ON tqt_resistencia(tarjeta_id) WHERE estado IN ('activa','pausada');
        CREATE TABLE IF NOT EXISTS tqt_resistencia_banco(
          clave TEXT PRIMARY KEY, station TEXT NOT NULL REFERENCES stm32_stations(id), creado REAL NOT NULL,
          operador TEXT NOT NULL, log_pedido REAL, log_texto TEXT, log_ts REAL);
        CREATE TABLE IF NOT EXISTS tqt_resistencia_ciclos(
          campana TEXT NOT NULL REFERENCES tqt_resistencia(id), n INTEGER NOT NULL,
          run TEXT NOT NULL UNIQUE REFERENCES tqt_test_runs(id), PRIMARY KEY(campana, n));
        """
        )


BANCO = "raspberry"   # el submódulo trabaja con UN solo banco: la Raspberry de la DYMO
LOG_MAX = 300 * 1024


def banco_station(c):
    r = c.execute("SELECT b.station FROM tqt_resistencia_banco b JOIN stm32_stations s ON s.id=b.station "
                  "WHERE b.clave=? AND s.revoked_at IS NULL", (BANCO,)).fetchone()
    return r["station"] if r else None


def registrar_banco(operador):
    """Crea la credencial del agente de la Raspberry y la fija como EL banco. La anterior queda registrada (sin uso aquí);
    se puede eliminar en Programación STM32 → agentes."""
    init()
    st = stm.station_create("Raspberry · Pruebas automáticas", operador)
    with db.transaction() as c:
        if c.execute("SELECT 1 FROM tqt_resistencia WHERE estado IN ('activa','pausada')").fetchone():
            raise ValueError("Hay una campaña activa o pausada: deténla antes de reinstalar el agente.")
        c.execute("INSERT INTO tqt_resistencia_banco(clave,station,creado,operador) VALUES(?,?,?,?) "
                  "ON CONFLICT(clave) DO UPDATE SET station=excluded.station,creado=excluded.creado,operador=excluded.operador,"
                  "log_pedido=NULL,log_texto=NULL,log_ts=NULL", (BANCO, st["id"], time.time(), operador))
    return st


def banco():
    """Estado del banco para la página: registro, presencia (puertos, versión del agente, plataforma) y log del agente."""
    init()
    with db.get_db() as c:
        b = c.execute("SELECT b.*,s.name,s.revoked_at FROM tqt_resistencia_banco b JOIN stm32_stations s ON s.id=b.station "
                      "WHERE b.clave=?", (BANCO,)).fetchone()
        if not b or b["revoked_at"]:
            return {"registrado": False}
        p = c.execute("SELECT seen,state FROM tqt_test_presence WHERE station=?", (b["station"],)).fetchone()
    estado = json.loads(p["state"]) if p else {}
    estado.pop("fields", None)
    return {"registrado": True, "station": b["station"], "nombre": b["name"], "creado": b["creado"],
            "visto": p["seen"] if p else None, "en_linea": bool(p and time.time() - p["seen"] < 15), "estado": estado,
            "log_pedido": b["log_pedido"], "log_ts": b["log_ts"], "log_bytes": len(b["log_texto"] or "")}


def pedir_log():
    init()
    with db.transaction() as c:
        if not banco_station(c):
            raise ValueError("Primero instala el agente de la Raspberry.")
        c.execute("UPDATE tqt_resistencia_banco SET log_pedido=? WHERE clave=?", (time.time(), BANCO))
    return banco()


def pide_log(sid):
    """Para el claim del agente: True si la web pidió su agent.log y aún no lo ha subido."""
    with db.get_db() as c:
        if not c.execute("SELECT 1 FROM sqlite_master WHERE name='tqt_resistencia_banco'").fetchone():
            return False
        r = c.execute("SELECT log_pedido,log_ts FROM tqt_resistencia_banco WHERE station=?", (sid,)).fetchone()
    return bool(r and r["log_pedido"] and (not r["log_ts"] or r["log_ts"] < r["log_pedido"]))


def guardar_log(sid, texto):
    init()
    with db.transaction() as c:
        n = c.execute("UPDATE tqt_resistencia_banco SET log_texto=?,log_ts=? WHERE station=?",
                      (str(texto)[-LOG_MAX:], time.time(), sid)).rowcount
    if not n:
        raise ValueError("Este agente no es el banco de Pruebas automáticas.")
    return {"ok": True}


def log_agente():
    init()
    with db.get_db() as c:
        r = c.execute("SELECT log_texto,log_ts FROM tqt_resistencia_banco WHERE clave=?", (BANCO,)).fetchone()
    return (r["log_texto"] or "", r["log_ts"]) if r else ("", None)


def log_campana(cid, texto_ciclo):
    """LOG de todos los ciclos de una campaña en un solo .txt, con encabezado por ciclo."""
    d = leer(cid)
    motivo = " · " + d["motivo"] if d["motivo"] else ""
    partes = [f"Campaña: {d['nombre']}\nFirmware: {d['firmware']}\nTarjeta: {(d['tarjeta'] or {}).get('id_tarjeta_num', '?')}\n"
              f"Estado: {d['estado']}{motivo}\n"]
    for x in sorted(d["ciclos_detalle"], key=lambda x: x["n"]):
        inicio = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(x["created"]))
        partes.append(f"\n===== Ciclo {x['n']} · {x['result'] or x['state']} · {inicio} =====\n")
        partes.append(texto_ciclo(x["run"]) or "(sin LOG)\n")
    return d, "".join(partes)


def crear(nombre, firmware, tid, ciclos, pausa_s, detener_en_falla, operador, confirmado):
    init()
    if confirmado is not True:
        raise ValueError("Confirma la tarjeta física y el banco libre: cada ciclo restablece ajustes y mueve el perno.")
    nombre, firmware = (nombre or "").strip(), (firmware or "").strip()
    if not nombre or not firmware:
        raise ValueError("Escribe el nombre de la campaña y el firmware que se valida.")
    if not 1 <= int(ciclos) <= MAX_CICLOS:
        raise ValueError(f"Los ciclos van de 1 a {MAX_CICLOS}.")
    if not 0 <= int(pausa_s) <= MAX_PAUSA_S:
        raise ValueError(f"La pausa entre ciclos va de 0 a {MAX_PAUSA_S} s.")
    with db.transaction() as c:
        sid = banco_station(c)
        if not sid:
            raise ValueError("Primero instala el agente de la Raspberry (paso 1).")
        ts.snapshot(tid, c)   # misma validación que Pruebas TQT: tarjeta emparejada y MAC únicas
        if c.execute("SELECT 1 FROM tqt_resistencia WHERE (station=? OR tarjeta_id=?) AND estado IN ('activa','pausada')",
                     (sid, tid)).fetchone():
            raise ValueError("La Raspberry o la tarjeta ya tienen una campaña activa o pausada.")
        now = time.time()
        cid = secrets.token_hex(12)
        c.execute("INSERT INTO tqt_resistencia VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  (cid, nombre[:80], firmware[:80], sid, tid, int(ciclos), int(pausa_s), 1 if detener_en_falla else 0,
                   "activa", None, operador, now, now))
    return leer(cid)


def _conteo(c, cid):
    k = {"aprobados": 0, "fallidos": 0, "no_verificados": 0, "en_curso": 0}
    for r in c.execute("SELECT r.state,r.result FROM tqt_resistencia_ciclos x JOIN tqt_test_runs r ON r.id=x.run WHERE x.campana=?", (cid,)):
        if r["state"] in ("queued", "running"):
            k["en_curso"] += 1
        elif r["result"] in APROBADOS:
            k["aprobados"] += 1
        elif r["result"] == "fallido":
            k["fallidos"] += 1
        else:
            k["no_verificados"] += 1
    k["hechos"] = k["aprobados"] + k["fallidos"] + k["no_verificados"]
    return k


def _fila(c, r):
    d = dict(r)
    d["detener_en_falla"] = bool(d["detener_en_falla"])
    d["conteo"] = _conteo(c, d["id"])
    t = c.execute("SELECT t.id_tarjeta_num,p.nombre FROM tarjetas_produccion t JOIN pcb_inventario p ON p.id=t.pcb_r1_id WHERE t.id=?",
                  (d["tarjeta_id"],)).fetchone()
    d["tarjeta"] = dict(t) if t else None
    s = c.execute("SELECT name FROM stm32_stations WHERE id=?", (d["station"],)).fetchone()
    d["estacion"] = s["name"] if s else None
    return d


def lista():
    init()
    with db.get_db() as c:
        return [_fila(c, r) for r in c.execute("SELECT * FROM tqt_resistencia ORDER BY creado DESC LIMIT 200")]


def leer(cid):
    init()
    with db.get_db() as c:
        r = c.execute("SELECT * FROM tqt_resistencia WHERE id=?", (cid,)).fetchone()
        if not r:
            raise ValueError("Campaña no encontrada.")
        d = _fila(c, r)
        d["ciclos_detalle"] = [dict(x) for x in c.execute(
            "SELECT x.n,r.id run,r.state,r.result,r.created,r.updated FROM tqt_resistencia_ciclos x "
            "JOIN tqt_test_runs r ON r.id=x.run WHERE x.campana=? ORDER BY x.n DESC", (cid,))]
    return d


def cambiar(cid, accion, operador):
    """pausar | reanudar | detener. Pausar/detener no cortan el ciclo en curso: termina y no se encola otro."""
    init()
    destino = {"pausar": ("activa", "pausada"), "reanudar": ("pausada", "activa"), "detener": (None, "detenida")}
    if accion not in destino:
        raise ValueError("Acción no válida.")
    desde, hacia = destino[accion]
    with db.transaction() as c:
        r = c.execute("SELECT estado FROM tqt_resistencia WHERE id=?", (cid,)).fetchone()
        if not r:
            raise ValueError("Campaña no encontrada.")
        if r["estado"] not in ACTIVAS or (desde and r["estado"] != desde):
            raise ValueError("La campaña no está en un estado que permita esa acción.")
        motivo = f"Detenida por {operador}." if accion == "detener" else None
        c.execute("UPDATE tqt_resistencia SET estado=?,motivo=COALESCE(?,motivo),actualizado=? WHERE id=?",
                  (hacia, motivo, time.time(), cid))
    return leer(cid)


def _cerrar(c, cid, estado, motivo, now):
    c.execute("UPDATE tqt_resistencia SET estado=?,motivo=?,actualizado=? WHERE id=?", (estado, motivo, now, cid))


def _estacion_libre(c, sid):
    if c.execute("SELECT 1 FROM tqt_test_runs WHERE station=? AND state IN ('queued','running')", (sid,)).fetchone():
        return False
    if c.execute("SELECT 1 FROM tqt_test_commands WHERE station=? AND state IN ('queued','running')", (sid,)).fetchone():
        return False
    if c.execute("SELECT 1 FROM stm32_jobs WHERE station=? AND state IN ('queued','running')", (sid,)).fetchone():
        return False
    if c.execute("SELECT 1 FROM sqlite_master WHERE name='r2_programming_attempts'").fetchone() and c.execute(
            "SELECT 1 FROM r2_programming_attempts WHERE station=? AND state IN ('flashing','queued','running') AND created>?",
            (sid, time.time() - 600)).fetchone():
        return False
    return True


def programar(c, sid, state, now):
    """Dentro de la transacción del claim: cierra o avanza la campaña activa de la estación. Devuelve el run encolado o None."""
    if not c.execute("SELECT 1 FROM sqlite_master WHERE name='tqt_resistencia'").fetchone():
        return None
    camp = c.execute("SELECT * FROM tqt_resistencia WHERE station=? AND estado='activa'", (sid,)).fetchone()
    if not camp:
        return None
    cid = camp["id"]
    ult = c.execute("SELECT x.n,r.state,r.result,r.updated FROM tqt_resistencia_ciclos x JOIN tqt_test_runs r ON r.id=x.run "
                    "WHERE x.campana=? ORDER BY x.n DESC LIMIT 1", (cid,)).fetchone()
    n = ult["n"] if ult else 0
    if ult and ult["state"] in ("queued", "running"):
        return None
    if ult:
        if ult["result"] not in APROBADOS and ult["result"] != "fallido":
            _cerrar(c, cid, "detenida", f"Ciclo {n} no verificado o interrumpido: revisa la tarjeta y el banco antes de repetir.", now)
            return None
        if ult["result"] == "fallido" and camp["detener_en_falla"]:
            _cerrar(c, cid, "fallida", f"Ciclo {n} fallido.", now)
            return None
        if n >= camp["ciclos"]:
            k = _conteo(c, cid)
            _cerrar(c, cid, "terminada" if not k["fallidos"] else "fallida",
                    f"{k['aprobados']} de {n} ciclos aprobados.", now)
            return None
        if now - ult["updated"] < camp["pausa_s"]:
            return None
    if state.get("running") or not state.get("serial_connected") or not _estacion_libre(c, sid):
        return None
    try:
        d = ts.snapshot(camp["tarjeta_id"], c)
    except ValueError as e:
        _cerrar(c, cid, "detenida", "Inventario cambiado: " + str(e), now)
        return None
    jid = secrets.token_hex(16)
    c.execute("INSERT INTO tqt_test_runs(id,station,requested_card,operator,state,created,updated,inventory,context) "
              "VALUES(?,?,?,?,?,?,?,?,?)",
              (jid, sid, camp["tarjeta_id"], camp["operador"], "queued", now, now, json.dumps(d),
               json.dumps({"campana": cid, "ciclo": n + 1, "firmware": camp["firmware"]}, ensure_ascii=False)))
    c.execute("INSERT INTO tqt_resistencia_ciclos VALUES(?,?,?)", (cid, n + 1, jid))
    c.execute("UPDATE tqt_resistencia SET actualizado=? WHERE id=?", (now, cid))
    return jid


def buscar_tarjetas(q):
    q = (q or "").strip()[:40]
    like = "%" + q.replace("%", "").replace("_", "") + "%"
    with db.get_db() as c:
        return [dict(r) for r in c.execute(
            "SELECT t.id,t.id_tarjeta_num,p.nombre r1,q.nombre r2,p.firmware FROM tarjetas_produccion t "
            "JOIN pcb_inventario p ON p.id=t.pcb_r1_id JOIN pcb_inventario q ON q.id=t.pcb_r2_id "
            "WHERE p.mac IS NOT NULL AND p.mac<>'' AND q.mac IS NOT NULL AND q.mac<>'' "
            "AND (CAST(t.id_tarjeta_num AS TEXT) LIKE ? OR p.nombre LIKE ? OR q.nombre LIKE ?) "
            "ORDER BY t.id DESC LIMIT 20", (like, like, like))]
