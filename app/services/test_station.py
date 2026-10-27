"""Durable test runs; inventory is authoritative. Never releases or alters a card."""

import hashlib, json, re, secrets, sqlite3, time
from app.database import db
from app.services import stm32_programming as stm

STAGES = ("queued", "running")


# v1.4.54: el agente de la Raspberry (Pruebas automáticas) también se anuncia como puente BLE y agente; Pruebas TQT
# no debe elegirlo ni usar su Bluetooth/serial. Solo pruebas_auto lo maneja.
RASPBERRY = "Raspberry · Pruebas automáticas"
# station_create guarda «<cuenta> · <nombre[:29]>»: se reconoce por este fragmento (y por el banco vigente).
RASPBERRY_LIKE = "%Raspberry · Pruebas autom%"


def es_raspberry(c, sid):
    if c.execute("SELECT 1 FROM stm32_stations WHERE id=? AND name LIKE ?", (sid, RASPBERRY_LIKE)).fetchone():
        return True
    banco = c.execute("SELECT 1 FROM sqlite_master WHERE name='tqt_resistencia_banco'").fetchone()
    return bool(banco and c.execute("SELECT 1 FROM tqt_resistencia_banco WHERE station=?", (sid,)).fetchone())


def no_raspberry(c, sid):
    if es_raspberry(c, sid):
        raise ValueError("Ese agente es la Raspberry de Pruebas automáticas; Pruebas TQT usa el banco o puente de Windows.")


def propia(c, sid, operator):
    """v1.4.56: cada cuenta usa solo SUS agentes/puentes (serial y Bluetooth) y nunca la Raspberry."""
    no_raspberry(c, sid)
    r = c.execute("SELECT owner FROM stm32_stations WHERE id=?", (sid,)).fetchone()
    if r and str(r["owner"]).lower() != str(operator).lower():
        raise ValueError("Ese agente pertenece a otra cuenta; instala o abre el de tu laptop.")


def agente_actual():
    """AGENT_VERSION del agente que se descarga hoy (station/test_station/agent.py)."""
    from pathlib import Path
    f = Path(__file__).resolve().parents[2] / "station/test_station/agent.py"
    m = re.search(r'^AGENT_VERSION = "([^"]+)"', f.read_text(encoding="utf-8"), re.M) if f.exists() else None
    return m.group(1) if m else ""


def desactualizados(operator, dias=7):
    """v1.4.57: agentes/puentes de la cuenta vistos en los últimos días con una versión distinta de la actual
    (sin la Raspberry, que se actualiza aparte). Pruebas TQT avisa con instrucciones hasta que se reinstalen."""
    init()
    actual = agente_actual()
    with db.get_db() as c:
        filas = c.execute(
            "SELECT p.seen,p.state,s.name FROM tqt_test_presence p JOIN stm32_stations s ON s.id=p.station "
            "WHERE s.revoked_at IS NULL AND lower(s.owner)=lower(?) AND s.name NOT LIKE ? AND p.seen>?",
            (operator, RASPBERRY_LIKE, time.time() - dias * 86400)).fetchall()
    # Uno viejo apagado ya no cuenta si la cuenta tiene otro actualizado (lo reemplazó); uno viejo en línea siempre cuenta.
    hay_nuevo = any(json.loads(r["state"]).get("agent_version") == actual for r in filas)
    out = []
    for r in filas:
        st = json.loads(r["state"])
        if actual and st.get("agent_version") != actual and (time.time() - r["seen"] < 15 or not hay_nuevo):
            out.append(dict(nombre=r["name"], version=st.get("agent_version") or "anterior a 1.4.51",
                            solo_ble=bool(st.get("ble_only")), en_linea=time.time() - r["seen"] < 15))
    return {"actual": actual, "estaciones": out}


def norm(value):
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def init():
    stm.init()
    with db.get_db() as c:
        c.executescript(
            """
        CREATE TABLE IF NOT EXISTS tqt_test_runs(
          id TEXT PRIMARY KEY, station TEXT NOT NULL REFERENCES stm32_stations(id),
          requested_card INTEGER NOT NULL REFERENCES tarjetas_produccion(id),
          tarjeta_id INTEGER REFERENCES tarjetas_produccion(id), operator TEXT NOT NULL,
          state TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL,
          inventory TEXT NOT NULL, report TEXT, result TEXT, cancel INTEGER NOT NULL DEFAULT 0);
        CREATE UNIQUE INDEX IF NOT EXISTS tqt_test_busy_station ON tqt_test_runs(station) WHERE state IN ('queued','running');
        CREATE UNIQUE INDEX IF NOT EXISTS tqt_test_busy_card ON tqt_test_runs(requested_card) WHERE state IN ('queued','running');
        CREATE INDEX IF NOT EXISTS tqt_test_history ON tqt_test_runs(requested_card,created DESC);
        CREATE TABLE IF NOT EXISTS tqt_test_events(run TEXT NOT NULL REFERENCES tqt_test_runs(id), seq INTEGER NOT NULL, data TEXT NOT NULL, PRIMARY KEY(run,seq));
        CREATE TABLE IF NOT EXISTS tqt_test_commands(id TEXT PRIMARY KEY, station TEXT NOT NULL REFERENCES stm32_stations(id), action TEXT NOT NULL, body TEXT NOT NULL, state TEXT NOT NULL, created REAL NOT NULL, result TEXT);
        CREATE TABLE IF NOT EXISTS tqt_test_presence(station TEXT PRIMARY KEY REFERENCES stm32_stations(id), seen REAL NOT NULL, state TEXT NOT NULL);
        """
        )
        # v1.4.0: origen de la ejecución (agent/web), contexto fijo y cambio de identidad confirmado.
        cols = {r[1] for r in c.execute("PRAGMA table_info(tqt_test_runs)")}
        for name, ddl in (
            ("origin", "ALTER TABLE tqt_test_runs ADD COLUMN origin TEXT NOT NULL DEFAULT 'agent'"),
            ("context", "ALTER TABLE tqt_test_runs ADD COLUMN context TEXT"),
            ("identity", "ALTER TABLE tqt_test_runs ADD COLUMN identity TEXT"),
        ):
            if name not in cols:
                c.execute(ddl)


def snapshot(tid, c):
    r = c.execute(
        """SELECT t.id,t.id_tarjeta_num,p.id r1_id,p.nombre nombre,p.serie r1_serie,p.mac mac_r1,
      p.firmware firmware,q.nombre r2_nombre,q.serie r2_serie,q.mac mac_r2
      FROM tarjetas_produccion t JOIN pcb_inventario p ON p.id=t.pcb_r1_id
      LEFT JOIN pcb_inventario q ON q.id=t.pcb_r2_id WHERE t.id=?""",
        (tid,),
    ).fetchone()
    if not r:
        raise ValueError(
            "Tarjeta registrada no encontrada. Usa la recepción y emparejamiento del inventario."
        )
    d = dict(r)
    if not d["mac_r1"] or not d["mac_r2"]:
        raise ValueError(
            "La tarjeta necesita R1 y R2 emparejadas y sus MAC registradas."
        )
    for key in ["mac_r1", "mac_r2"]:
        rows = c.execute(
            "SELECT id FROM pcb_inventario WHERE UPPER(REPLACE(mac,':',''))=?",
            (norm(d[key]),),
        ).fetchall()
        if len(rows) != 1:
            raise ValueError("MAC duplicada o ambigua en inventario.")
    return d


def compare(d, r):
    expected = {
        "card": norm(d["nombre"]),
        "card_id": str(int(d["r1_serie"])),
        "reported_mac": norm(d["mac_r1"]),
        "r1_ble_address": norm(d["mac_r1"]),
        "reported_mac_r2": norm(d["mac_r2"]),
        "r2_ble_address": norm(d["mac_r2"]),
        "reported_id_r2": str(int(d["r2_serie"])),
    }
    checks = {}
    for key, value in expected.items():
        actual = (
            r.get(key)
            if key != "reported_id_r2"
            else r.get("status_final", {}).get("IDR")
        )
        if key in ("card_id", "reported_id_r2"):
            try:
                actual = str(int(actual))
            except (TypeError, ValueError):
                actual = ""
        else:
            actual = norm(actual)
        checks[key] = (
            "coincide"
            if actual and actual == value
            else "no_coincide" if actual else "no_verificado"
        )
    checks["state"] = (
        "coincide" if all(v == "coincide" for v in checks.values()) else "no_verificado"
    )
    return checks


def read(jid):
    init()
    with db.get_db() as c:
        # A disconnected run is retained, never automatically retried.
        now = time.time()
        c.execute(
            "UPDATE tqt_test_runs SET state='interrupted',result='no_verificado',updated=? WHERE id=? AND state IN ('queued','running') AND updated<?",
            (now, jid, now - 120),
        )
        r = c.execute("SELECT r.*,s.name station_name,s.owner station_owner FROM tqt_test_runs r JOIN stm32_stations s ON s.id=r.station WHERE r.id=?", (jid,)).fetchone()
    if not r:
        raise ValueError("Prueba no encontrada.")
    d = dict(r)
    d["inventory"] = json.loads(d["inventory"])
    d["report"] = json.loads(d["report"]) if d["report"] else None
    d["identity"] = json.loads(d["identity"]) if d.get("identity") else None
    return d


def create(sid, tid, operator, confirmed):
    init()
    if confirmed is not True:
        raise ValueError(
            "Confirma la tarjeta física y el banco libre antes de iniciar; la secuencia restablece ajustes y mueve el perno."
        )
    with db.transaction() as c:
        stm.require_station(c, sid)
        propia(c, sid, operator)
        p = c.execute(
            "SELECT seen,state FROM tqt_test_presence WHERE station=?", (sid,)
        ).fetchone()
        if not p or time.time() - p["seen"] > 15:
            raise ValueError("El agente de pruebas está desconectado.")
        if not json.loads(p["state"]).get("serial_connected"):
            raise ValueError("Conecta el puerto COM antes de iniciar.")
        if c.execute("SELECT 1 FROM sqlite_master WHERE name='r2_programming_attempts'").fetchone():
            if c.execute("SELECT 1 FROM r2_programming_attempts WHERE station=? AND state IN ('flashing','queued','running') AND created>?",(sid,time.time()-600)).fetchone():
                raise ValueError('La estación está programando o verificando una R2.')
        if c.execute(
            "SELECT 1 FROM stm32_jobs WHERE station=? AND state IN ('queued','running')",
            (sid,),
        ).fetchone():
            raise ValueError("La estación está programando firmware.")
        if c.execute(
            "SELECT 1 FROM tqt_test_runs WHERE (station=? OR requested_card=?) AND state IN ('queued','running')",
            (sid, tid),
        ).fetchone():
            raise ValueError("La tarjeta o estación ya tiene una prueba activa.")
        if c.execute(
            "SELECT 1 FROM tqt_test_commands WHERE station=? AND state IN ('queued','running')",
            (sid,),
        ).fetchone():
            raise ValueError("Espera a que termine el comando manual.")
        d = snapshot(tid, c)
        now = time.time()
        jid = secrets.token_hex(16)
        c.execute(
            "INSERT INTO tqt_test_runs(id,station,requested_card,operator,state,created,updated,inventory) VALUES(?,?,?,?,?,?,?,?)",
            (jid, sid, tid, operator, "queued", now, now, json.dumps(d)),
        )
    return read(jid)


def command(sid, action, body):
    init()
    if action not in (
        "ports",
        "connect_serial",
        "disconnect_serial",
        "scan_ble",
        "connect_ble",
        "disconnect_ble",
        "serial",
        "ble",
    ):
        raise ValueError("Acción no permitida.")
    with db.transaction() as c:
        stm.require_station(c, sid)
        p = c.execute(
            "SELECT seen FROM tqt_test_presence WHERE station=?", (sid,)
        ).fetchone()
        if not p or time.time() - p["seen"] > 15:
            raise ValueError("Estación desconectada.")
        if c.execute(
            "SELECT 1 FROM tqt_test_runs WHERE station=? AND state IN ('queued','running')",
            (sid,),
        ).fetchone():
            raise ValueError("Comando manual bloqueado durante la prueba automática.")
        if c.execute(
            "SELECT 1 FROM tqt_test_commands WHERE station=? AND state IN ('queued','running')",
            (sid,),
        ).fetchone():
            raise ValueError("Hay un comando en curso.")
        if c.execute(
            "SELECT 1 FROM stm32_jobs WHERE station=? AND state IN ('queued','running')",
            (sid,),
        ).fetchone():
            raise ValueError("La estación está programando firmware.")
        if c.execute("SELECT 1 FROM sqlite_master WHERE name='r2_programming_attempts'").fetchone():
            if c.execute("SELECT 1 FROM r2_programming_attempts WHERE station=? AND state IN ('flashing','queued','running') AND created>?",(sid,time.time()-600)).fetchone():
                raise ValueError('La estación está programando o verificando una R2.')
        if action in ("serial", "ble") and body.get("command") in ("PPON", "POFF"):
            body["inventory"] = snapshot(body.get("tarjeta_id"), c)
        jid = secrets.token_hex(16)
        c.execute(
            "INSERT INTO tqt_test_commands VALUES(?,?,?,?,?,?,NULL)",
            (jid, sid, action, json.dumps(body), "queued", time.time()),
        )
    return {"id": jid}


def claim(sid, state):
    init()
    with db.transaction() as c:
        stm.require_station(c, sid)
        now = time.time()
        c.execute(
            "INSERT INTO tqt_test_presence VALUES(?,?,?) ON CONFLICT(station) DO UPDATE SET seen=excluded.seen,state=excluded.state",
            (sid, now, json.dumps(state)),
        )
        c.execute(
            "UPDATE tqt_test_commands SET state='error',result=? WHERE station=? AND state IN ('queued','running') AND created<?",
            (json.dumps({"error": "Comando expirado; no se repite."}), sid, now - 90),
        )
        r = c.execute(
            "SELECT * FROM tqt_test_runs WHERE station=? AND state='running'", (sid,)
        ).fetchone()
        if r:
            if state.get("run_id") != r["id"]:
                c.execute(
                    "UPDATE tqt_test_runs SET state='interrupted',result='no_verificado',updated=? WHERE id=?",
                    (now, r["id"]),
                )
                return {}
            c.execute("UPDATE tqt_test_runs SET updated=? WHERE id=?", (now, r["id"]))
            return {"cancel": bool(r["cancel"]), "run_id": r["id"]}
        r = c.execute(
            "SELECT * FROM tqt_test_commands WHERE station=? AND state='queued' ORDER BY created LIMIT 1",
            (sid,),
        ).fetchone()
        if r:
            c.execute(
                "UPDATE tqt_test_commands SET state='running' WHERE id=?", (r["id"],)
            )
            return {"command": dict(r)}
        from app.services import pruebas_auto   # v1.4.51: campañas de resistencia (import tardío: pruebas_auto usa este módulo)
        pruebas_auto.programar(c, sid, state, now)
        r = c.execute(
            "SELECT * FROM tqt_test_runs WHERE station=? AND state='queued' ORDER BY created LIMIT 1",
            (sid,),
        ).fetchone()
        if r:
            if r["cancel"]:
                c.execute(
                    "UPDATE tqt_test_runs SET state='interrupted',result='no_verificado',updated=? WHERE id=?",
                    (now, r["id"]),
                )
                return {}
            old = json.loads(r["inventory"])
            current = snapshot(r["requested_card"], c)
            if current != old:
                c.execute(
                    "UPDATE tqt_test_runs SET state='interrupted',result='no_verificado',updated=? WHERE id=?",
                    (now, r["id"]),
                )
                return {}
            c.execute(
                "UPDATE tqt_test_runs SET state='running',updated=? WHERE id=?",
                (now, r["id"]),
            )
            return {"run": {"id": r["id"], "inventory": old}}
    return {}


def events(sid, jid, items):
    with db.transaction() as c:
        r = c.execute(
            "SELECT * FROM tqt_test_runs WHERE id=? AND station=?", (jid, sid)
        ).fetchone()
        if not r:
            raise ValueError("La prueba no pertenece a esta estación.")
        _store_events(c, jid, items)
    return {"ok": True}


def _store_events(c, jid, items):
    """Idempotente por seq: repetir un lote no duplica; nunca reemplaza evidencia."""
    for item in items:
        old = c.execute(
            "SELECT data FROM tqt_test_events WHERE run=? AND seq=?",
            (jid, item["seq"]),
        ).fetchone()
        data = json.dumps(item["data"], ensure_ascii=False)
        if old and old["data"] != data:
            raise ValueError("No se permite reemplazar evidencia.")
        if not old:
            c.execute(
                "INSERT INTO tqt_test_events VALUES(?,?,?)",
                (jid, item["seq"], data),
            )
    c.execute("UPDATE tqt_test_runs SET updated=? WHERE id=?", (time.time(), jid))


def _salud_numerica(health):
    """v1.4.0: los contadores de serial_health deben ser numéricos (400, no TypeError/500)."""
    for k in ("frames", "retries", "partial_warnings", "ack_errors"):
        v = health.get(k, 0) if isinstance(health, dict) else 0
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ValueError("serial_health." + k + " debe ser numérico.")


def verdict(report, checks):
    """Reglas de aprobación únicas para agente y navegador (no se acepta un booleano del cliente)."""
    steps = report.get("steps", []) if isinstance(report.get("steps"), list) else []
    health = report.get("serial_health", {}) if isinstance(report.get("serial_health"), dict) else {}
    quality = report.get("communication_quality", {})
    quality = quality if isinstance(quality, dict) else {}
    _salud_numerica(health)
    passed = (
        report.get("result") == "aprobado"
        and len(steps) == 14
        and all(isinstance(s, dict) and s.get("state") == "aprobado" for s in steps)
        and health.get("frames", 0) > 0
    )
    result = (
        "fallido"
        if report.get("result") == "fallido"
        or any(isinstance(s, dict) and s.get("state") == "fallido" for s in steps)
        else "no_verificado"
    )
    if (
        passed
        and checks["state"] == "coincide"
        and quality.get("state") != "no_verificable"
        and not any(
            health.get(k, 0) for k in ["retries", "partial_warnings", "ack_errors"]
        )
    ):
        result = (
            "aprobado_con_advertencias"
            if report.get("warnings")
            or quality.get("state") == "advertencias"
            else "aprobado"
        )
    return result


def finish(sid, jid, report):
    init()
    with db.transaction() as c:
        row = c.execute(
            "SELECT * FROM tqt_test_runs WHERE id=? AND station=?", (jid, sid)
        ).fetchone()
        if not row:
            raise ValueError("Prueba ajena a la estación.")
        if row["report"]:
            if json.loads(row["report"]).get("source_report") == report:
                return {"id": jid, "state": row["state"]}
            raise ValueError("La prueba ya tiene un resultado permanente.")
        d = json.loads(row["inventory"])
        checks = compare(d, report)
        result = verdict(report, checks)
        combined = {
            "source_report": report,
            "inventory_check": checks,
            "inventory": d,
            "result": result,
            "release_authorized": False,
        }
        # Unverified identity never links automatically to a different physical card.
        tid = row["requested_card"] if checks["state"] == "coincide" else None
        c.execute(
            "UPDATE tqt_test_runs SET state='finished',tarjeta_id=?,updated=?,report=?,result=? WHERE id=?",
            (tid, time.time(), json.dumps(combined, ensure_ascii=False), result, jid),
        )
    return read(jid)


# ---------------------------------------------------------------------------
# v1.4.0: ejecuciones de origen navegador (Web Serial + Web Bluetooth).
# El navegador del operador autenticado ejecuta las 14 etapas; el servidor guarda
# eventos, aplica las MISMAS reglas de aprobación/cotejo (verdict/compare) y además
# reconstruye la identidad desde las tramas S29 crudas recibidas. Límite de confianza:
# el servidor no observa el hardware; el informe no es una atestación criptográfica.
WEB_CONTEXT = "banco de pruebas · modo seguro"
S29_FIELDS = (
    "BLK", "OUT1", "OUT2", "OUT3", "INT1", "INT2", "INT3", "EST1", "EST2", "EST3",
    "MOTOR", "SEN_MOT", "TIEMPO", "DBG", "VIVA", "TQT", "ON", "OFF", "PB", "err",
    "RESET", "VER", "HW", "MOV", "Mensaje", "IDR", "MACR", "ID", "MAC",
)
_POST_RE = re.compile(r'AT\$POST=1,0,"(?P<body>[^"]*)"')


def parse_s29(line):
    """Misma gramática que tqtstation.protocol.parse_status; None si la trama no es S29 completa."""
    found = _POST_RE.search(str(line or ""))
    if not found:
        return None
    body = found.group("body")
    m = re.match(r"S29(?P<sep>[^\w\s])", body)
    if not m:
        return None
    entries = body[4:].split(m.group("sep"))
    if len(entries) != 29:
        return None
    values = {}
    for expected, entry in zip(S29_FIELDS, entries):
        if not entry.startswith(expected) or len(entry) <= len(expected):
            return None
        v = entry[len(expected):]
        if v[0] not in ":;=,":
            return None
        values[expected] = v[1:]
    return values


def _int(v):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def web_station(c, operator):
    """Banco lógico por operador (FK de tqt_test_runs.station). Sin token utilizable ni presencia."""
    sid = "web-" + hashlib.sha256(str(operator).lower().encode()).hexdigest()[:20]
    c.execute(
        "INSERT OR IGNORE INTO stm32_stations(id,name,token_hash,owner) VALUES(?,?,?,?)",
        (sid, "Navegador · " + str(operator)[:40], hashlib.sha256(secrets.token_bytes(32)).hexdigest(), operator),
    )
    return sid


def _summary(d):
    return {"tarjeta_id": d["id"], "nombre": d["nombre"], "numero": d.get("id_tarjeta_num"),
            "r2_nombre": d.get("r2_nombre"), "mac_r1": d.get("mac_r1"), "mac_r2": d.get("mac_r2")}


def huella_mac(sal, mac):
    """SHA-256(sal|MAC normalizada); igual que huellaMac() de validacion_web.js."""
    return hashlib.sha256((str(sal) + "|" + re.sub(r"[^0-9A-F]", "", str(mac or "").upper())).encode()).hexdigest()


def _publico(d, sal):
    """v1.4.0: inventario para el navegador sin MAC (solo huellas); el cotejo real lo hace el servidor."""
    out = {k: v for k, v in d.items() if k not in ("mac_r1", "mac_r2")}
    out.update(huella_sal=sal, mac_r1_h=huella_mac(sal, d.get("mac_r1")), mac_r2_h=huella_mac(sal, d.get("mac_r2")))
    return out


def _sin_mac(resumen):
    return {k: v for k, v in resumen.items() if k not in ("mac_r1", "mac_r2")}


def web_create(tid, operator):
    init()
    with db.transaction() as c:
        sid = web_station(c, operator)
        now = time.time()
        # Una pestaña cerrada sin informe queda interrumpida, nunca se reanuda.
        # v1.4.1: también la de otro operador sobre esta tarjeta (si no, la bloquea hasta que alguien la abra).
        c.execute(
            "UPDATE tqt_test_runs SET state='interrupted',result='no_verificado',updated=? WHERE (station=? OR (requested_card=? AND origin='web')) AND state IN ('queued','running') AND updated<?",
            (now, sid, tid, now - 120),
        )
        if c.execute(
            "SELECT 1 FROM tqt_test_runs WHERE (station=? OR requested_card=?) AND state IN ('queued','running')",
            (sid, tid),
        ).fetchone():
            raise ValueError("La tarjeta ya tiene una prueba activa o ya tienes una prueba en curso.")
        d = snapshot(tid, c)
        jid = secrets.token_hex(16)
        try:
            c.execute(
                "INSERT INTO tqt_test_runs(id,station,requested_card,operator,state,created,updated,inventory,origin,context) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (jid, sid, tid, operator, "running", now, now, json.dumps(d), "web", WEB_CONTEXT),
            )
        except sqlite3.IntegrityError:  # v1.4.0: carrera con los índices únicos de ejecución activa
            raise ValueError("La tarjeta ya tiene una prueba activa o ya tienes una prueba en curso.")
    out = read(jid)
    out["inventory"] = _publico(out["inventory"], jid)
    return out


def _web_row(c, jid, operator, states=("running",)):
    row = c.execute("SELECT * FROM tqt_test_runs WHERE id=?", (jid,)).fetchone()
    if not row or row["origin"] != "web":
        raise ValueError("Prueba web no encontrada.")
    if row["station"] != web_station(c, operator):
        raise ValueError("La prueba pertenece a otro operador.")
    if states and row["state"] not in states:
        raise ValueError("La prueba ya no está en curso (" + row["state"] + "); no se acepta más evidencia.")
    return row


def web_events(operator, jid, items):
    init()
    with db.transaction() as c:
        row = _web_row(c, jid, operator)
        _store_events(c, jid, items)
        return {"ok": True, "cancel": bool(row["cancel"])}


def web_identity(operator, jid, detected, confirm):
    """Punto 12: la tarjeta conectada no es la elegida. Resuelve por MAC R1 exacta y exige
    pareja/ID/nombre coherentes; con confirm=True cambia atómicamente la ejecución."""
    init()
    detected = detected if isinstance(detected, dict) else {}
    mac = norm(detected.get("mac"))
    if not re.fullmatch(r"[0-9A-F]{12}", mac):
        raise ValueError("La R1 no informó una MAC válida; no se puede identificar la tarjeta.")
    with db.transaction() as c:
        row = _web_row(c, jid, operator)
        if row["identity"]:
            raise ValueError("La identidad ya se confirmó una vez en esta ejecución.")
        rows = c.execute(
            """SELECT t.id FROM tarjetas_produccion t JOIN pcb_inventario p ON p.id=t.pcb_r1_id
            WHERE REPLACE(REPLACE(UPPER(p.mac),':',''),'-','')=?""",
            (mac,),
        ).fetchall()
        if not rows:
            raise ValueError("La MAC R1 " + detected.get("mac", "") + " no está registrada en ninguna tarjeta del inventario.")
        if len(rows) > 1:
            raise ValueError("La MAC R1 detectada aparece en varias tarjetas; identidad ambigua.")
        new = snapshot(rows[0]["id"], c)
        if norm(new["mac_r2"]) != norm(detected.get("macr")):
            raise ValueError("La MACR informada por R1 no coincide con la R2 emparejada de " + new["nombre"] + ".")
        if detected.get("id") not in (None, "") and _int(detected.get("id")) != _int(new["r1_serie"]):
            raise ValueError("El ID informado por R1 contradice el número de " + new["nombre"] + ".")
        if detected.get("nombre") and norm(detected.get("nombre")) != norm(new["nombre"]):
            raise ValueError("El nombre informado por R1 contradice el inventario de " + new["nombre"] + ".")
        old = json.loads(row["inventory"])
        if new["id"] == row["requested_card"]:
            raise ValueError("La tarjeta detectada es la seleccionada; revisa nombre/MAC en inventario.")
        out = {"seleccionada": _sin_mac(_summary(old)), "detectada": _sin_mac(_summary(new))}
        if confirm is not True:
            return out
        change = {
            "seleccionada_inicial": _summary(old), "detectada": _summary(new),
            "evidencia": {k: str(detected.get(k, ""))[:64] for k in ("nombre", "id", "mac", "macr", "idr")},
            "operador": operator, "consentimiento": True, "fecha": time.time(),
        }
        try:
            c.execute(
                "UPDATE tqt_test_runs SET requested_card=?,inventory=?,identity=?,updated=? WHERE id=?",
                (new["id"], json.dumps(new), json.dumps(change, ensure_ascii=False), time.time(), jid),
            )
        except Exception as exc:  # índice único: la detectada ya tiene otra prueba activa
            if "UNIQUE" in str(exc).upper():
                raise ValueError("La tarjeta detectada ya tiene una prueba activa.")
            raise
        out.update(inventory=_publico(new, jid), identity_change=dict(
            change, seleccionada_inicial=_sin_mac(change["seleccionada_inicial"]), detectada=_sin_mac(change["detectada"])))
        return out


def _web_evidence(c, jid):
    """S29 crudas y nombres de tarjeta tal como llegaron en los eventos de la ejecución.
    v1.4.0: cada S29 se anota con la etapa en curso (evento 'step') en el campo interno '_etapa'."""
    statuses, cards, etapa = [], [], -1
    for r in c.execute("SELECT data FROM tqt_test_events WHERE run=? ORDER BY seq", (jid,)):
        try:
            e = json.loads(r["data"])
        except ValueError:
            continue
        args = e.get("args") or []
        if e.get("kind") == "status" and args and isinstance(args[0], dict):
            f = parse_s29(args[0].get("raw"))
            if f:
                f["_etapa"] = etapa
                statuses.append(f)
        elif e.get("kind") == "step" and args and isinstance(args[0], int) and not isinstance(args[0], bool):
            etapa = max(etapa, args[0])
        elif e.get("kind") == "card" and args:
            cards.append(str(args[0]))
    return statuses, cards


def web_finish(operator, jid, report):
    init()
    from app.services import native_ble
    native_ble.init()
    if not isinstance(report, dict):
        raise ValueError("Informe inválido.")
    _salud_numerica(report.get("serial_health"))
    with db.transaction() as c:
        row = _web_row(c, jid, operator, states=None)
        if row["report"]:
            if json.loads(row["report"]).get("source_report") == report:
                return {"id": jid, "state": row["state"]}
            raise ValueError("La prueba ya tiene un resultado permanente.")
        if row["state"] != "running":
            raise ValueError("La prueba ya no está en curso (" + row["state"] + "); el informe no se acepta.")
        d = json.loads(row["inventory"])
        statuses, cards = _web_evidence(c, jid)
        steps = report.get("steps") if isinstance(report.get("steps"), list) else []
        ok = lambda idx: len(steps) == 14 and isinstance(steps[idx], dict) and steps[idx].get("state") == "aprobado"
        # Identidad: sólo cuenta si los valores del informe aparecen en una S29 cruda recibida.
        ident = next((f for f in statuses if norm(f.get("MAC")) == norm(report.get("reported_mac"))
                      and norm(f.get("MACR")) == norm(report.get("reported_mac_r2"))
                      and _int(f.get("ID")) is not None and _int(f.get("ID")) == _int(report.get("card_id"))), None)
        last = statuses[-1] if statuses else {}
        # R1 BLE: la MAC no es observable en el navegador; el vínculo se acepta solo si R1
        # registró movimientos por Bluetooth (PB=2) con al menos dos MOV distintos.
        pb2 = {f.get("MOV") for f in statuses if _int(f.get("PB")) == 2 and _int(f.get("TQT")) == 0}
        r1_link = bool(ident) and all(ok(i) for i in (6, 7, 8, 9, 10)) and len(pb2) >= 2
        # R2 BLE: nombre exacto del inventario + err=13 y err=14 observados por R1 en S29
        # posteriores a la etapa 11 (conexión R2); si la R2 declaró su MAC (info OTA) debe ser la MACR.
        errs = {_int(f.get("err")) for f in statuses if f.get("_etapa", -1) > 11}
        ble = report.get("ble_identity") if isinstance(report.get("ble_identity"), dict) else {}
        r2info = ble.get("r2") if isinstance(ble.get("r2"), dict) else {}
        declared = r2info.get("mac_declarada_r2")
        observed = native_ble.connections(c, jid)
        r2_link = (bool(ident) and all(ok(i) for i in (11, 12, 13)) and {13, 14} <= errs
                   and (norm(report.get("r2_ble_name")) == norm(d.get("r2_nombre")) or norm(observed.get('R2')) == norm(d['mac_r2']))
                   and (not declared or norm(declared) == norm(report.get("reported_mac_r2"))))
        effective = dict(report)
        effective.update(
            card=cards[-1] if cards else None,
            reported_mac=ident.get("MAC") if ident else None,
            reported_mac_r2=ident.get("MACR") if ident else None,
            card_id=ident.get("ID") if ident else None,
            r1_ble_address=ident.get("MAC") if r1_link else None,
            r2_ble_address=ident.get("MACR") if r2_link else None,
            status_final={"IDR": last.get("IDR")},
        )
        if not statuses:
            effective["serial_health"] = dict(report.get("serial_health") or {}, frames=0)
        checks = compare(d, effective)
        checks["ble_metodo"] = {
            "r1": ("mac_windows_y_pb2" if observed.get('R1') else "vinculo_funcional_pb2") if r1_link else "no_verificado",
            "r2": ("mac_windows_y_err13_14" if observed.get('R2') else "mac_declarada_r2" if declared else "vinculo_funcional_err13_14") if r2_link else "no_verificado",
        }
        checks["evidencia_s29"] = len(statuses)
        result = verdict(effective, checks)
        combined = {
            "source_report": report,
            "inventory_check": checks,
            "inventory": d,
            "result": result,
            "release_authorized": False,
            "origin": "web",
            "context": row["context"] or WEB_CONTEXT,
            "identity_change": json.loads(row["identity"]) if row["identity"] else None,
            "cancelada": bool(report.get("cancelled")) or bool(row["cancel"]),
            "trust_note": "Informe construido por el navegador del operador; el servidor validó estructura, "
                          "tramas S29 crudas e inventario, sin observación directa del hardware.",
        }
        tid = row["requested_card"] if checks["state"] == "coincide" else None
        c.execute(
            "UPDATE tqt_test_runs SET state='finished',tarjeta_id=?,updated=?,report=?,result=? WHERE id=?",
            (tid, time.time(), json.dumps(combined, ensure_ascii=False), result, jid),
        )
    return read(jid)
