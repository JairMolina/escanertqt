"""Durable test runs; inventory is authoritative. Never releases or alters a card."""

import json, re, secrets, time
from app.database import db
from app.services import stm32_programming as stm

STAGES = ("queued", "running")


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
        r = c.execute("SELECT * FROM tqt_test_runs WHERE id=?", (jid,)).fetchone()
    if not r:
        raise ValueError("Prueba no encontrada.")
    d = dict(r)
    d["inventory"] = json.loads(d["inventory"])
    d["report"] = json.loads(d["report"]) if d["report"] else None
    return d


def create(sid, tid, operator, confirmed):
    init()
    if confirmed is not True:
        raise ValueError(
            "Confirma la tarjeta física y el banco libre antes de iniciar; la secuencia restablece ajustes y mueve el perno."
        )
    with db.transaction() as c:
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
    return {"ok": True}


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
        steps = report.get("steps", [])
        health = report.get("serial_health", {})
        passed = (
            report.get("result") == "aprobado"
            and len(steps) == 14
            and all(s.get("state") == "aprobado" for s in steps)
            and health.get("frames", 0) > 0
        )
        result = (
            "fallido"
            if report.get("result") == "fallido"
            or any(s.get("state") == "fallido" for s in steps)
            else "no_verificado"
        )
        if (
            passed
            and checks["state"] == "coincide"
            and report.get("communication_quality", {}).get("state") != "no_verificable"
            and not any(
                health.get(k, 0) for k in ["retries", "partial_warnings", "ack_errors"]
            )
        ):
            result = (
                "aprobado_con_advertencias"
                if report.get("warnings")
                or report.get("communication_quality", {}).get("state")
                == "advertencias"
                else "aprobado"
            )
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
