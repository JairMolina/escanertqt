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
        # v1.4.52: ocupación del banco por usuario (sesiones separadas)
        cols = {r[1] for r in c.execute("PRAGMA table_info(tqt_resistencia_banco)")}
        for col, ddl in (("ocupado_por", "TEXT"), ("ocupado_desde", "REAL"), ("ocupado_visto", "REAL")):
            if col not in cols:
                c.execute(f"ALTER TABLE tqt_resistencia_banco ADD COLUMN {col} {ddl}")


BANCO = "raspberry"   # el submódulo trabaja con UN solo banco: la Raspberry de la DYMO
LOG_MAX = 300 * 1024
LIBERAR_S = 120       # v1.4.52: sin campaña, el banco se libera solo si su usuario deja la página 2 min


class Ocupado(ValueError):
    """v1.4.52: la Raspberry la está usando otra cuenta. `info` va a la web para la pantalla de «Raspberry ocupada»."""
    def __init__(self, info):
        super().__init__(f"La Raspberry está ocupada por {info['por']}.")
        self.info = info


def _ocupacion(c, now=None):
    """Quién usa el banco: el dueño de una campaña activa/pausada manda; si no hay, quien tomó el banco y sigue en la
    página (latido de la web en los últimos LIBERAR_S s). None = libre."""
    now = now or time.time()
    camp = c.execute("SELECT * FROM tqt_resistencia WHERE estado IN ('activa','pausada') ORDER BY creado DESC LIMIT 1").fetchone()
    b = c.execute("SELECT ocupado_por,ocupado_desde,ocupado_visto FROM tqt_resistencia_banco WHERE clave=?", (BANCO,)).fetchone()
    if camp:
        k = _conteo(c, camp["id"])
        return {"por": camp["operador"], "desde": camp["creado"], "motivo": "campana",
                "campana": {"id": camp["id"], "nombre": camp["nombre"], "firmware": camp["firmware"], "estado": camp["estado"],
                            "hechos": k["hechos"], "ciclos": camp["ciclos"], "en_curso": k["en_curso"]}}
    if b and b["ocupado_por"] and now - (b["ocupado_visto"] or 0) < LIBERAR_S:
        return {"por": b["ocupado_por"], "desde": b["ocupado_desde"], "motivo": "sesion", "campana": None}
    return None


def tomar(c, email, admin=False):
    """Reserva el banco para `email` (o renueva su reserva). Si lo usa otra cuenta lanza Ocupado (ni el admin lo toma:
    primero debe liberarlo con «Detener y liberar»)."""
    now = time.time()
    occ = _ocupacion(c, now)
    if occ and occ["por"] != email:
        raise Ocupado(occ)
    c.execute("UPDATE tqt_resistencia_banco SET ocupado_por=?,ocupado_desde=CASE WHEN ocupado_por=? THEN ocupado_desde ELSE ? END,"
              "ocupado_visto=? WHERE clave=?", (email, email, now, now, BANCO))


def _ver(c, email, admin):
    """Lectura de datos del banco (log del agente): solo quien lo usa, o cualquiera si está libre; el admin siempre."""
    occ = _ocupacion(c)
    if occ and occ["por"] != email and not admin:
        raise Ocupado(occ)


def liberar(email, admin=False):
    """Suelta el banco. Su dueño solo sin campaña activa/pausada; el administrador puede forzarlo: detiene la campaña."""
    init()
    with db.transaction() as c:
        occ = _ocupacion(c)
        if occ and occ["por"] != email and not admin:
            raise Ocupado(occ)
        if occ and occ["campana"]:
            if not admin and occ["por"] == email:
                raise ValueError("Detén tu campaña antes de liberar la Raspberry.")
            c.execute("UPDATE tqt_resistencia SET estado='detenida',motivo=?,actualizado=? WHERE id=?",
                      (f"Detenida por {email} (administrador) para liberar la Raspberry.", time.time(), occ["campana"]["id"]))
        c.execute("UPDATE tqt_resistencia_banco SET ocupado_por=NULL,ocupado_desde=NULL,ocupado_visto=NULL WHERE clave=?", (BANCO,))
    return {"ok": True}


def banco_station(c):
    r = c.execute("SELECT b.station FROM tqt_resistencia_banco b JOIN stm32_stations s ON s.id=b.station "
                  "WHERE b.clave=? AND s.revoked_at IS NULL", (BANCO,)).fetchone()
    return r["station"] if r else None


def registrar_banco(operador, admin=False, nuevo=False):
    """Credencial del agente de la Raspberry fijada como EL banco. v1.4.64: si el banco vigente no está revocado y es
    del operador (o el operador es administrador) se REUTILIZA con token nuevo (mismo id: campañas, ciclos y presencia
    siguen ligados; los tokens anteriores siguen valiendo, ver station_rotate). Si no, o con nuevo=True, se crea otra."""
    init()
    with db.get_db() as c:
        if c.execute("SELECT 1 FROM tqt_resistencia_banco WHERE clave=?", (BANCO,)).fetchone():
            occ = _ocupacion(c)
            if occ and occ["por"] != operador:
                raise Ocupado(occ)
        if c.execute("SELECT 1 FROM tqt_resistencia WHERE estado IN ('activa','pausada')").fetchone():
            raise ValueError("Hay una campaña activa o pausada: deténla antes de reinstalar el agente.")
        previo = c.execute("SELECT s.id,s.owner FROM tqt_resistencia_banco b JOIN stm32_stations s ON s.id=b.station "
                           "WHERE b.clave=? AND s.revoked_at IS NULL", (BANCO,)).fetchone()
    st = None
    if previo and not nuevo and (admin or str(previo["owner"]).lower() == str(operador).lower()):
        st = stm.station_rotate(previo["id"], previo["owner"])
    if st is None:
        st = stm.station_create(ts.RASPBERRY, operador)
    with db.transaction() as c:
        c.execute("INSERT INTO tqt_resistencia_banco(clave,station,creado,operador) VALUES(?,?,?,?) "
                  "ON CONFLICT(clave) DO UPDATE SET station=excluded.station,creado=excluded.creado,operador=excluded.operador,"
                  "log_pedido=NULL,log_texto=NULL,log_ts=NULL", (BANCO, st["id"], time.time(), operador))
    return st


def banco(email=None):
    """Estado del banco para la página: registro, presencia (puertos, versión del agente, plataforma), log del agente y
    ocupación (v1.4.52). La consulta de su dueño es el latido que mantiene la reserva."""
    init()
    with db.transaction() as c:
        occ = _ocupacion(c)
        if email and occ and occ["por"] == email:
            c.execute("UPDATE tqt_resistencia_banco SET ocupado_visto=? WHERE clave=? AND ocupado_por=?", (time.time(), BANCO, email))
        b = c.execute("SELECT b.*,s.name,s.revoked_at FROM tqt_resistencia_banco b JOIN stm32_stations s ON s.id=b.station "
                      "WHERE b.clave=?", (BANCO,)).fetchone()
        if not b or b["revoked_at"]:
            return {"registrado": False, "ocupacion": occ}
        p = c.execute("SELECT seen,state FROM tqt_test_presence WHERE station=?", (b["station"],)).fetchone()
    estado = json.loads(p["state"]) if p else {}
    estado.pop("fields", None)
    return {"registrado": True, "station": b["station"], "nombre": b["name"], "creado": b["creado"],
            "visto": p["seen"] if p else None, "en_linea": bool(p and time.time() - p["seen"] < 15), "estado": estado,
            "log_pedido": b["log_pedido"], "log_ts": b["log_ts"], "log_bytes": len(b["log_texto"] or ""),
            "ocupacion": dict(occ, mio=occ["por"] == email) if occ else None}


def instalacion(progreso, servidor_version, email=None, admin=False):
    """v1.4.64: avance del instalador .sh de la estación del banco + presencia/versión de su agente. Lo ve quien puede
    ver el banco (si otra cuenta lo ocupa → Ocupado, como el log). `progreso` = dict sid → {etapa, mensaje, ts}."""
    init()
    with db.get_db() as c:
        if email:
            _ver(c, email, admin)
        sid = banco_station(c)
        p = c.execute("SELECT seen,state FROM tqt_test_presence WHERE station=?", (sid,)).fetchone() if sid else None
    st = json.loads(p["state"]) if p else {}
    en_linea = bool(p and time.time() - p["seen"] < 15)
    version = st.get("agent_version") or ""
    d = (progreso.get(sid) if sid else None) or {"etapa": "", "mensaje": "", "ts": 0}
    return {"etapa": d["etapa"], "mensaje": d["mensaje"], "ts": d["ts"], "en_linea": en_linea, "agent_version": version,
            "servidor_version": servidor_version, "listo": en_linea and bool(version) and version == servidor_version}


def pedir_log(email=None, admin=False):
    init()
    with db.transaction() as c:
        if not banco_station(c):
            raise ValueError("Primero instala el agente de la Raspberry.")
        if email:
            _ver(c, email, admin)
        c.execute("UPDATE tqt_resistencia_banco SET log_pedido=? WHERE clave=?", (time.time(), BANCO))
    return banco(email)


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


def log_agente(email=None, admin=False):
    init()
    with db.get_db() as c:
        if email:
            _ver(c, email, admin)
        r = c.execute("SELECT log_texto,log_ts FROM tqt_resistencia_banco WHERE clave=?", (BANCO,)).fetchone()
    return (r["log_texto"] or "", r["log_ts"]) if r else ("", None)


def log_campana(cid, texto_ciclo, email=None, admin=False):
    """LOG de todos los ciclos de una campaña en un solo .txt, con encabezado por ciclo."""
    d = leer(cid, email, admin)
    motivo = " · " + d["motivo"] if d["motivo"] else ""
    partes = [f"Campaña: {d['nombre']}\nFirmware: {d['firmware']}\nTarjeta: {(d['tarjeta'] or {}).get('id_tarjeta_num', '?')}\n"
              f"Estado: {d['estado']}{motivo}\n"]
    for x in sorted(d["ciclos_detalle"], key=lambda x: x["n"]):
        inicio = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(x["created"]))
        partes.append(f"\n===== Ciclo {x['n']} · {x['result'] or x['state']} · {inicio} =====\n")
        partes.append(texto_ciclo(x["run"]) or "(sin LOG)\n")
    return d, "".join(partes)


def crear(nombre, firmware, tid, ciclos, pausa_s, detener_en_falla, operador, confirmado, admin=False):
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
        tomar(c, operador, admin)
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


def resultado_ciclo(result, report):
    """v1.4.70 (decisión del usuario, SOLO campañas): un ciclo «no_verificado» con las 14 etapas aprobadas, identidad que
    coincide con el inventario y cuyo único problema de comunicación fueron reintentos de ACK (sin tramas dañadas/parciales
    ni errores de escritura) cuenta como «aprobado_con_advertencias» para la campaña. El resultado guardado de la prueba
    (tqt_test_runs.result, el que usa Pruebas TQT para certificar/liberar) no cambia."""
    if result != "no_verificado" or not report:
        return result
    try:
        d = json.loads(report) if isinstance(report, str) else report
    except ValueError:
        return result
    src = d.get("source_report") or {}
    steps = src.get("steps") or []
    h = src.get("serial_health") or {}
    if (len(steps) == 14 and all(isinstance(x, dict) and x.get("state") == "aprobado" for x in steps)
            and (d.get("inventory_check") or {}).get("state") == "coincide" and src.get("mac_comparison") != "no_coincide"
            and int(h.get("retries", 0) or 0) > 0 and not int(h.get("partial_warnings", 0) or 0)
            and not int(h.get("ack_errors", 0) or 0) and not int(h.get("corrupt_frames", 0) or 0)):
        return "aprobado_con_advertencias"
    return result


def _conteo(c, cid):
    k = {"aprobados": 0, "fallidos": 0, "no_verificados": 0, "en_curso": 0}
    for r in c.execute("SELECT r.state,r.result,r.report FROM tqt_resistencia_ciclos x JOIN tqt_test_runs r ON r.id=x.run WHERE x.campana=?", (cid,)):
        res = resultado_ciclo(r["result"], r["report"])
        if r["state"] in ("queued", "running"):
            k["en_curso"] += 1
        elif res in APROBADOS:
            k["aprobados"] += 1
        elif res == "fallido":
            k["fallidos"] += 1
        else:
            k["no_verificados"] += 1
    k["hechos"] = k["aprobados"] + k["fallidos"] + k["no_verificados"]
    return k


def _fila(c, r):
    d = dict(r)
    d["detener_en_falla"] = bool(d["detener_en_falla"])
    d["conteo"] = _conteo(c, d["id"])
    t = c.execute("SELECT t.id_tarjeta_num,t.lote_id,l.codigo_lote lote_codigo,p.nombre FROM tarjetas_produccion t JOIN pcb_inventario p ON p.id=t.pcb_r1_id JOIN lotes_mensuales l ON l.id=t.lote_id WHERE t.id=?",
                  (d["tarjeta_id"],)).fetchone()
    d["tarjeta"] = dict(t) if t else None
    s = c.execute("SELECT name FROM stm32_stations WHERE id=?", (d["station"],)).fetchone()
    d["estacion"] = s["name"] if s else None
    return d


def motivo_ciclo(report):
    """v1.4.68: por qué falló o no se verificó un ciclo: etapa (número y nombre) y detalle, o el `issue` del reporte."""
    try:
        r = json.loads(report) if isinstance(report, str) else (report or {})
    except ValueError:
        return None
    r = r.get("source_report") or r   # tqt_test_runs.report guarda el del agente dentro de source_report
    for i, st in enumerate(r.get("steps") or []):
        if st.get("state") in ("fallido", "no_verificado"):
            return {"etapa": i + 1, "nombre": st.get("name") or "", "detalle": st.get("detail") or r.get("issue") or ""}
    return {"etapa": None, "nombre": "", "detalle": r["issue"]} if r.get("issue") else None


def _ultimo_fallo(c, cid):
    r = None
    for f in c.execute("SELECT x.n,r.result,r.state,r.report FROM tqt_resistencia_ciclos x JOIN tqt_test_runs r ON r.id=x.run "
                       "WHERE x.campana=? AND (r.result IN ('fallido','no_verificado') OR r.state='interrupted') ORDER BY x.n DESC",
                       (cid,)):
        if resultado_ciclo(f["result"], f["report"]) not in APROBADOS:
            r = f
            break
    if not r:
        return None
    m = motivo_ciclo(r["report"]) or {"etapa": None, "nombre": "", "detalle": "Ciclo interrumpido (el agente se reinició o perdió la conexión)."}
    return dict(m, n=r["n"], resultado=r["result"] or r["state"])


def lista(email=None, admin=False):
    """v1.4.77: el historial de campañas es compartido por todas las cuentas (solo lectura para quien no es dueño).
    `mia` indica si la campaña es de esta cuenta o si es administrador (solo ellos pausan, detienen o eliminan)."""
    init()
    with db.get_db() as c:
        w, a = db.clausula_lote(c, "t.lote_id")
        filas = c.execute("SELECT r.* FROM tqt_resistencia r JOIN tarjetas_produccion t ON t.id=r.tarjeta_id WHERE 1=1" + w + " ORDER BY r.creado DESC LIMIT 200", a)
        out = [_fila(c, r) for r in filas]
        for d in out:   # v1.4.68: por qué falló (último ciclo fallido o no verificado)
            d["ultimo_fallo"] = _ultimo_fallo(c, d["id"])
            d["mia"] = bool(admin or (email and d["operador"] == email))
        return out


def leer(cid, email=None, admin=False):
    """v1.4.77: cualquier cuenta puede leer la campaña (historial compartido); `mia` marca si puede actuar sobre ella."""
    init()
    with db.get_db() as c:
        r = c.execute("SELECT * FROM tqt_resistencia WHERE id=?", (cid,)).fetchone()
        if not r or not db.get_tarjeta_by_id(r["tarjeta_id"], c):
            raise ValueError("Campaña no encontrada.")
        d = _fila(c, r)
        d["mia"] = bool(admin or (email and r["operador"] == email))
        d["ciclos_detalle"] = [dict(x) for x in c.execute(
            "SELECT x.n,r.id run,r.state,r.result,r.created,r.updated,r.report FROM tqt_resistencia_ciclos x "
            "JOIN tqt_test_runs r ON r.id=x.run WHERE x.campana=? ORDER BY x.n DESC", (cid,))]
        for x in d["ciclos_detalle"]:   # v1.4.68: motivo por ciclo (sin mandar el reporte completo)
            rep = x.pop("report")
            x["result_prueba"] = x["result"]
            x["result"] = resultado_ciclo(x["result"], rep)   # v1.4.70: reintentos de ACK solos = con advertencias
            x["motivo"] = (motivo_ciclo(rep) if x["result"] not in APROBADOS else
                           {"etapa": None, "nombre": "", "detalle": "14 etapas aprobadas; reintentos de ACK en el serial (advertencia)."}
                           if x["result_prueba"] == "no_verificado" else None)
    return d


def cambiar(cid, accion, operador, admin=False):
    """pausar | reanudar | detener | detener_ahora. Pausar/detener dejan terminar el ciclo en curso y no encolan otro;
    detener_ahora (v1.4.65) además pide cancelar el ciclo en curso (el firmware termina el movimiento actual)."""
    init()
    destino = {"pausar": ("activa", "pausada"), "reanudar": ("pausada", "activa"), "detener": (None, "detenida"),
               "detener_ahora": (None, "detenida")}
    if accion not in destino:
        raise ValueError("Acción no válida.")
    desde, hacia = destino[accion]
    with db.transaction() as c:
        r = c.execute("SELECT estado,operador,tarjeta_id FROM tqt_resistencia WHERE id=?", (cid,)).fetchone()
        if not r or (r["operador"] != operador and not admin) or not db.get_tarjeta_by_id(r["tarjeta_id"], c):
            raise ValueError("Campaña no encontrada.")
        if r["estado"] not in ACTIVAS or (desde and r["estado"] != desde):
            raise ValueError("La campaña no está en un estado que permita esa acción.")
        motivo = f"Detenida por {operador}." if accion == "detener" else f"Detenida al instante por {operador}." if accion == "detener_ahora" else None
        c.execute("UPDATE tqt_resistencia SET estado=?,motivo=COALESCE(?,motivo),actualizado=? WHERE id=?",
                  (hacia, motivo, time.time(), cid))
        if accion == "detener_ahora":
            c.execute("UPDATE tqt_test_runs SET cancel=1 WHERE state IN ('queued','running') AND id IN "
                      "(SELECT run FROM tqt_resistencia_ciclos WHERE campana=?)", (cid,))
    return leer(cid, operador, admin)


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
    ult = c.execute("SELECT x.n,r.state,r.result,r.updated,r.report FROM tqt_resistencia_ciclos x JOIN tqt_test_runs r ON r.id=x.run "
                    "WHERE x.campana=? ORDER BY x.n DESC LIMIT 1", (cid,)).fetchone()
    if ult:
        ult = dict(ult, result=resultado_ciclo(ult["result"], ult["report"]))
    n = ult["n"] if ult else 0
    if ult and ult["state"] in ("queued", "running"):
        return None
    if ult:
        if ult["result"] not in APROBADOS and ult["result"] != "fallido":
            # v1.4.67: un ciclo no verificado/interrumpido ya no corta siempre la campaña: solo si se pidió detener en falla
            # o si se repite 3 veces seguidas (banco o tarjeta con un problema que no se corrige solo).
            seguidos = 0
            for r in c.execute("SELECT r.result,r.report FROM tqt_resistencia_ciclos x JOIN tqt_test_runs r ON r.id=x.run "
                               "WHERE x.campana=? ORDER BY x.n DESC LIMIT 3", (cid,)):
                if resultado_ciclo(r["result"], r["report"]) in APROBADOS or r["result"] == "fallido":
                    break
                seguidos += 1
            if camp["detener_en_falla"] or seguidos >= 3:
                _cerrar(c, cid, "detenida", f"Ciclo {n} no verificado o interrumpido" + (" (3 seguidos)" if seguidos >= 3 else "")
                        + ": revisa la tarjeta y el banco antes de repetir.", now)
                return None
            if n >= camp["ciclos"]:
                k = _conteo(c, cid)
                _cerrar(c, cid, "terminada" if not (k["fallidos"] or k["no_verificados"]) else "fallida",
                        f"{k['aprobados']} de {n} ciclos aprobados.", now)
                return None
            if now - ult["updated"] < camp["pausa_s"]:
                return None
        if ult["result"] == "fallido" and camp["detener_en_falla"]:
            m = motivo_ciclo(c.execute("SELECT report FROM tqt_test_runs WHERE id=(SELECT run FROM tqt_resistencia_ciclos "
                                       "WHERE campana=? AND n=?)", (cid, n)).fetchone()["report"])
            _cerrar(c, cid, "fallida", f"Ciclo {n} fallido" + (f" en la etapa {m['etapa']} «{m['nombre']}»: {m['detalle']}" if m and m.get("etapa")
                    else f": {m['detalle']}" if m else "."), now)
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
        w, a = db.clausula_lote(c, "t.lote_id")
        return [dict(r) for r in c.execute(
            "SELECT t.id,t.id_tarjeta_num,t.lote_id,l.codigo_lote lote_codigo,p.nombre r1,q.nombre r2,p.firmware FROM tarjetas_produccion t "
            "JOIN lotes_mensuales l ON l.id=t.lote_id "
            "JOIN pcb_inventario p ON p.id=t.pcb_r1_id JOIN pcb_inventario q ON q.id=t.pcb_r2_id "
            "WHERE p.mac IS NOT NULL AND p.mac<>'' AND q.mac IS NOT NULL AND q.mac<>'' "
            "AND (CAST(t.id_tarjeta_num AS TEXT) LIKE ? OR p.nombre LIKE ? OR q.nombre LIKE ?) "
            + w + " ORDER BY t.id DESC LIMIT 20", [like, like, like, *a])]


def ciclo_permitido(jid, email, admin=False):
    """v1.4.77: el LOG de un ciclo lo puede bajar cualquier cuenta (historial compartido de campañas)."""
    with db.get_db() as c:
        r = c.execute("SELECT r.operador,r.tarjeta_id FROM tqt_resistencia_ciclos x JOIN tqt_resistencia r ON r.id=x.campana WHERE x.run=?",
                      (jid,)).fetchone()
        if not r or not db.get_tarjeta_by_id(r["tarjeta_id"], c):
            raise ValueError("Ciclo no encontrado.")


def vivo(cid, email=None, admin=False):
    """v1.4.65: estado en vivo para la página: ciclo actual, las 14 etapas (estado y detalle), última lectura S29
    (posición, MOV, err, PB, TQT) y las últimas líneas del log del ciclo. Solo lectura."""
    d = leer(cid, email, admin)
    ciclos = d["ciclos_detalle"]
    actual = next((x for x in ciclos if x["state"] in ("queued", "running")), ciclos[0] if ciclos else None)
    out = {"estado": d["estado"], "ciclos": d.get("ciclos"), "hechos": len([x for x in ciclos if x["state"] not in ("queued", "running")]),
           "ciclo": None, "pasos": {}, "sensores": None, "log": [], "motivo": d.get("motivo")}
    if not actual:
        return out
    out["ciclo"] = {"n": actual["n"], "run": actual["run"], "state": actual["state"], "result": actual["result"],
                    "created": actual["created"], "updated": actual["updated"]}
    with db.get_db() as c:
        filas = c.execute("SELECT data FROM tqt_test_events WHERE run=? ORDER BY seq", (actual["run"],)).fetchall()
    lineas = []
    for f in filas:
        e = json.loads(f["data"])
        k, a = e.get("kind"), e.get("args") or []
        if k == "step" and len(a) >= 2:
            out["pasos"][str(a[0])] = {"estado": a[1], "detalle": a[2] if len(a) > 2 else ""}
        elif k == "status" and a and isinstance(a[0], dict):
            campos = a[0].get("fields") or {}
            out["sensores"] = {x: campos.get(x) for x in ("ON", "OFF", "TQT", "MOV", "err", "PB")}
        elif k == "log" and a:
            lineas.append(str(a[0]))
        elif k == "full_log" and e.get("text"):
            lineas = e["text"].splitlines()
    out["log"] = [x for x in lineas if "TX SERIAL: $OK" not in x][-14:]
    return out


def eliminar(cid, email, admin=False):
    """v1.4.68: borra una campaña terminada/detenida/fallida del historial (solo su dueño o un administrador). Los ciclos
    siguen como pruebas normales en el historial de Pruebas TQT de la tarjeta; solo se quita la campaña y su relación."""
    init()
    with db.transaction() as c:
        r = c.execute("SELECT estado,operador,tarjeta_id FROM tqt_resistencia WHERE id=?", (cid,)).fetchone()
        if not r or (r["operador"] != email and not admin) or not db.get_tarjeta_by_id(r["tarjeta_id"], c):
            raise ValueError("Campaña no encontrada.")
        if r["estado"] in ACTIVAS:
            raise ValueError("Detén la campaña antes de eliminarla.")
        c.execute("DELETE FROM tqt_resistencia_ciclos WHERE campana=?", (cid,))
        c.execute("DELETE FROM tqt_resistencia WHERE id=?", (cid,))
    return {"ok": True}
