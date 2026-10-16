import _aislamiento as iso
import time
import unittest
from fastapi.testclient import TestClient
from app.main import app
from app.database import db, inventario as inv
from app.services import test_station as s, stm32_programming as stm

OP = "operador@test.mx"


def s29(**over):
    """Trama S29 real (gramática de protocol.py) con separador | y valores ':'."""
    v = {k: "0" for k in s.S29_FIELDS}
    v.update(VER="4.3", HW="3.0", Mensaje="1.0", OFF="1")
    v.update({k: str(x) for k, x in over.items()})
    return 'AT$POST=1,0,"S29|' + "|".join(k + ":" + v[k] for k in s.S29_FIELDS) + '"'


class WebRuns(unittest.TestCase):
    """v1.4.0: ejecuciones del navegador con las mismas reglas que el agente."""

    @classmethod
    def setUpClass(cls):
        db.init_db()

    def card(self):
        t = iso.crear_par(iso.nuevo_lote()["id"], version="30")
        with db.get_db() as c:
            return t, s.snapshot(t["id"], c)

    def setUp(self):
        self.t, self.d = self.card()

    def tearDown(self):
        # Cada prueba deja cerradas sus ejecuciones del banco lógico del navegador.
        with db.get_db() as c:
            c.execute("UPDATE tqt_test_runs SET state='interrupted' WHERE origin='web' AND state='running'")

    def ident(self, d=None, **over):
        d = d or self.d
        base = dict(ID=d["r1_serie"], MAC=d["mac_r1"], MACR=d["mac_r2"], IDR=d["r2_serie"])
        base.update(over)
        return base

    def evidence(self, d=None, pb2=True, errs=(13, 14), etapa_err=12, **over):
        d = d or self.d
        lines = [s29(**self.ident(d, **over))]
        if pb2:
            lines += [s29(**self.ident(d, PB=2, MOV=3, **over)), s29(**self.ident(d, PB=2, MOV=4, **over))]
        datos = [{"kind": "card", "args": [d["nombre"].replace("-", "_")]}]
        datos += [{"kind": "status", "args": [{"fields": {}, "raw": raw}]} for raw in lines]
        # v1.4.0: los err=13/14 solo cuentan en S29 posteriores a la etapa 11 (conexión R2).
        datos.append({"kind": "step", "args": [etapa_err, "ejecutando", ""]})
        datos += [{"kind": "status", "args": [{"fields": {}, "raw": s29(**self.ident(d, err=e, **over))}]} for e in errs]
        return [{"seq": i + 1, "data": x} for i, x in enumerate(datos)]

    def report(self, d=None, **over):
        d = d or self.d
        r = dict(
            report_schema="tqt-station/0.6.3-web", origin="web", result="aprobado",
            card=d["nombre"], card_id=d["r1_serie"], reported_mac=d["mac_r1"], reported_mac_r2=d["mac_r2"],
            r1_ble_address=None, r2_ble_address=None, r1_ble_name=d["nombre"], r2_ble_name=d["r2_nombre"],
            ble_identity={"r1": {}, "r2": {"mac_declarada_r2": None}},
            steps=[{"name": str(i), "state": "aprobado"} for i in range(14)],
            communication_quality={"state": "limpia"},
            serial_health={"frames": 50, "retries": 0, "partial_warnings": 0, "ack_errors": 0},
            warnings=[], status_final={"IDR": d["r2_serie"]},
        )
        r.update(over)
        return r

    def start(self, d=None):
        return s.web_create((d or self.d)["id"], OP)

    def test_web_run_approved_only_with_server_side_evidence(self):
        j = self.start()
        self.assertEqual(j["origin"], "web")
        self.assertEqual(j["context"], s.WEB_CONTEXT)
        self.assertEqual(j["state"], "running")
        s.web_events(OP, j["id"], self.evidence())
        r = s.web_finish(OP, j["id"], self.report())
        self.assertEqual(r["result"], "aprobado")
        self.assertEqual(r["tarjeta_id"], self.d["id"])
        self.assertFalse(r["report"]["release_authorized"])
        self.assertEqual(r["report"]["inventory_check"]["ble_metodo"]["r1"], "vinculo_funcional_pb2")
        # Idempotente con el mismo informe; no se reemplaza por otro.
        s.web_finish(OP, j["id"], self.report())
        with self.assertRaises(ValueError):
            s.web_finish(OP, j["id"], self.report(result="fallido"))

    def test_client_aprobado_without_raw_s29_is_not_approved(self):
        j = self.start()
        r = s.web_finish(OP, j["id"], self.report())
        self.assertEqual(r["result"], "no_verificado")
        self.assertIsNone(r["tarjeta_id"])

    def test_report_mac_must_match_raw_evidence(self):
        j = self.start()
        s.web_events(OP, j["id"], self.evidence())
        r = s.web_finish(OP, j["id"], self.report(reported_mac="AA:BB:CC:DD:EE:01"))
        self.assertEqual(r["result"], "no_verificado")

    def test_ble_link_requires_pb2_and_r2_events(self):
        j = self.start()
        s.web_events(OP, j["id"], self.evidence(pb2=False))
        self.assertEqual(s.web_finish(OP, j["id"], self.report())["result"], "no_verificado")
        j = self.start()
        s.web_events(OP, j["id"], self.evidence(errs=(13,)))
        r = s.web_finish(OP, j["id"], self.report())
        self.assertEqual(r["result"], "no_verificado")
        self.assertEqual(r["report"]["inventory_check"]["ble_metodo"]["r2"], "no_verificado")

    def test_r2_declared_mac_must_be_macr(self):
        j = self.start()
        s.web_events(OP, j["id"], self.evidence())
        r = self.report(ble_identity={"r2": {"mac_declarada_r2": "00:11:22:33:44:55"}})
        self.assertEqual(s.web_finish(OP, j["id"], r)["result"], "no_verificado")

    def test_legacy_r2_name_requires_native_agent_mac_evidence(self):
        from app.services import native_ble
        import secrets
        old_name = 'TQT_R2_V2_0_0039'
        j = self.start()
        s.web_events(OP, j['id'], self.evidence())
        forged = self.report(r2_ble_name=old_name, ble_identity={'r2': {'observed_address': self.d['mac_r2']}})
        self.assertEqual(s.web_finish(OP, j['id'], forged)['result'], 'no_verificado')
        j = self.start()
        sid = stm.station_create('BLE-only test', OP)['id']
        s.claim(sid, dict(ble_bridge=1, serial_connected=False, running=False))
        body = dict(station_id=sid, request_id=secrets.token_hex(16), tarjeta_id=self.d['id'],
                    run_id=j['id'], role='R2', operation='connect', mac=self.d['mac_r2'])
        cmd = native_ble.prepare(OP, body)['id']
        s.claim(sid, dict(ble_bridge=1))
        native_ble.authorize(sid, cmd)
        import json
        with db.get_db() as c:
            c.execute("UPDATE tqt_test_commands SET state='done',result=? WHERE id=?", (json.dumps(dict(ok=True,data=dict(address=self.d['mac_r2'],name=old_name))), cmd))
        s.web_events(OP, j['id'], self.evidence())
        result = s.web_finish(OP, j['id'], self.report(r2_ble_name=old_name))
        self.assertEqual(result['result'], 'aprobado')
        self.assertEqual(result['report']['inventory_check']['ble_metodo']['r2'], 'mac_windows_y_err13_14')

    def test_same_rules_partial_steps_and_ack_retries(self):
        j = self.start()
        s.web_events(OP, j["id"], self.evidence())
        r = self.report()
        r["steps"] = r["steps"][:13]
        self.assertEqual(s.web_finish(OP, j["id"], r)["result"], "no_verificado")
        j = self.start()
        s.web_events(OP, j["id"], self.evidence())
        r = self.report()
        r["serial_health"]["retries"] = 1
        self.assertEqual(s.web_finish(OP, j["id"], r)["result"], "no_verificado")
        j = self.start()
        s.web_events(OP, j["id"], self.evidence())
        r = self.report()
        r["steps"][5]["state"] = "fallido"
        self.assertEqual(s.web_finish(OP, j["id"], r)["result"], "fallido")

    def test_owner_busy_and_cancel_flag(self):
        j = self.start()
        with self.assertRaises(ValueError):
            s.web_events("otro@test.mx", j["id"], [])
        with self.assertRaises(ValueError):
            s.web_finish("otro@test.mx", j["id"], self.report())
        with self.assertRaises(ValueError):
            self.start()  # misma tarjeta y mismo banco lógico
        self.assertFalse(s.web_events(OP, j["id"], [])["cancel"])
        with db.get_db() as c:
            c.execute("UPDATE tqt_test_runs SET cancel=1 WHERE id=?", (j["id"],))
        self.assertTrue(s.web_events(OP, j["id"], [])["cancel"])
        s.web_finish(OP, j["id"], self.report(result="no_verificado", cancelled=True))
        self.assertTrue(s.read(j["id"])["report"]["cancelada"])

    def test_stale_tab_is_interrupted_and_rejects_evidence(self):
        j = self.start()
        with db.get_db() as c:
            c.execute("UPDATE tqt_test_runs SET updated=? WHERE id=?", (time.time() - 300, j["id"]))
        t2, d2 = self.card()
        k = s.web_create(d2["id"], OP)
        self.assertEqual(s.read(j["id"])["state"], "interrupted")
        with self.assertRaises(ValueError):
            s.web_events(OP, j["id"], [])
        with self.assertRaises(ValueError):
            s.web_finish(OP, j["id"], self.report())
        self.assertEqual(s.read(k["id"])["state"], "running")

    def test_identity_switch_confirmed_keeps_trace_and_results_under_detected(self):
        t2, d2 = self.card()
        j = self.start()
        det = {"mac": d2["mac_r1"], "macr": d2["mac_r2"], "id": d2["r1_serie"], "nombre": ""}
        preview = s.web_identity(OP, j["id"], det, False)
        self.assertEqual(preview["detectada"]["tarjeta_id"], d2["id"])
        self.assertEqual(s.read(j["id"])["requested_card"], self.d["id"])
        out = s.web_identity(OP, j["id"], det, True)
        self.assertEqual(out["inventory"]["id"], d2["id"])
        run = s.read(j["id"])
        self.assertEqual(run["requested_card"], d2["id"])
        self.assertEqual(run["identity"]["seleccionada_inicial"]["tarjeta_id"], self.d["id"])
        self.assertTrue(run["identity"]["consentimiento"])
        with self.assertRaises(ValueError):
            s.web_identity(OP, j["id"], det, True)  # solo una vez
        s.web_events(OP, j["id"], self.evidence(d2))
        r = s.web_finish(OP, j["id"], self.report(d2))
        self.assertEqual(r["result"], "aprobado")
        self.assertEqual(r["tarjeta_id"], d2["id"])
        self.assertEqual(r["report"]["identity_change"]["detectada"]["tarjeta_id"], d2["id"])

    def test_identity_unknown_or_contradictory_is_rejected(self):
        t2, d2 = self.card()
        j = self.start()
        with self.assertRaises(ValueError):
            s.web_identity(OP, j["id"], {"mac": "0A0B0C0D0E0F", "macr": d2["mac_r2"]}, False)
        with self.assertRaises(ValueError):
            s.web_identity(OP, j["id"], {"mac": d2["mac_r1"], "macr": self.d["mac_r2"]}, True)
        with self.assertRaises(ValueError):
            s.web_identity(OP, j["id"], {"mac": d2["mac_r1"], "macr": d2["mac_r2"], "id": "99999"}, True)
        self.assertEqual(s.read(j["id"])["requested_card"], self.d["id"])

    def test_r2_errs_before_stage_12_do_not_count(self):
        j = self.start()
        s.web_events(OP, j["id"], self.evidence(etapa_err=10))
        r = s.web_finish(OP, j["id"], self.report())
        self.assertNotEqual(r["result"], "aprobado")
        self.assertEqual(r["report"]["inventory_check"]["ble_metodo"]["r2"], "no_verificado")

    def test_web_create_hides_inventory_macs(self):
        j = self.start()
        inv_pub = j["inventory"]
        self.assertNotIn("mac_r1", inv_pub)
        self.assertNotIn("mac_r2", inv_pub)
        self.assertEqual(inv_pub["huella_sal"], j["id"])
        self.assertEqual(inv_pub["mac_r1_h"], s.huella_mac(j["id"], self.d["mac_r1"]))
        self.assertEqual(inv_pub["mac_r2_h"], s.huella_mac(j["id"], self.d["mac_r2"].lower()))
        self.assertNotIn(s.norm(self.d["mac_r1"]), s.norm(str(inv_pub)))
        # el servidor conserva el inventario completo para el cotejo
        self.assertEqual(s.read(j["id"])["inventory"]["mac_r1"], self.d["mac_r1"])
        t2, d2 = self.card()
        det = {"mac": d2["mac_r1"], "macr": d2["mac_r2"], "id": d2["r1_serie"], "nombre": ""}
        prev = s.web_identity(OP, j["id"], det, False)
        self.assertNotIn("mac_r1", prev["seleccionada"])
        out = s.web_identity(OP, j["id"], det, True)
        self.assertNotIn("mac_r1", out["inventory"])
        self.assertNotIn("mac_r1", out["identity_change"]["seleccionada_inicial"])

    def test_web_create_unique_index_race_is_value_error(self):
        orig = s.snapshot

        def carrera(tid, c):
            d = orig(tid, c)
            sid = s.web_station(c, OP)
            c.execute("INSERT INTO tqt_test_runs(id,station,requested_card,operator,state,created,updated,inventory,origin)"
                      " VALUES('carrera',?,?,?,'running',?,?,'{}','web')", (sid, tid, OP, time.time(), time.time()))
            return d
        s.snapshot = carrera
        try:
            with self.assertRaises(ValueError):
                self.start()
        finally:
            s.snapshot = orig
        with db.get_db() as c:
            self.assertIsNone(c.execute("SELECT 1 FROM tqt_test_runs WHERE id='carrera'").fetchone())

    def test_verdict_non_numeric_frames_is_400(self):
        with self.assertRaises(ValueError):
            s.verdict({"result": "aprobado", "serial_health": {"frames": "50"}}, {"state": "coincide"})
        client = TestClient(app, base_url="https://testserver")
        jid = client.post("/api/validacion/tqt/web/runs", json={"tarjeta_id": self.d["id"]}).json()["id"]
        r = client.post("/api/validacion/tqt/web/runs/" + jid + "/result",
                        json={"result": "aprobado", "steps": [], "serial_health": {"frames": [1]}})
        self.assertEqual(r.status_code, 400, r.text)

    def test_parse_s29_matches_protocol(self):
        f = s.parse_s29(s29(MAC="AA:BB:CC:DD:EE:FF", MOV=7))
        self.assertEqual(f["MAC"], "AA:BB:CC:DD:EE:FF")
        self.assertEqual(f["MOV"], "7")
        self.assertIsNone(s.parse_s29(s29()[:-10]))
        self.assertIsNone(s.parse_s29('AT$POST=1,0,"TQT_R1 - Lista para usarse"'))

    def test_http_endpoints_and_agent_station_list_untouched(self):
        client = TestClient(app, base_url="https://testserver")
        r = client.post("/api/validacion/tqt/web/runs", json={"tarjeta_id": self.d["id"]})
        self.assertEqual(r.status_code, 200, r.text)
        jid = r.json()["id"]
        r = client.post("/api/validacion/tqt/web/runs/" + jid + "/events",
                        json={"items": [{"seq": 1, "data": {"kind": "log", "args": ["x"]}}]})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(client.post("/api/validacion/tqt/runs/" + jid + "/cancel").status_code, 200)
        self.assertTrue(client.post("/api/validacion/tqt/web/runs/" + jid + "/events", json={"items": []}).json()["cancel"])
        r = client.post("/api/validacion/tqt/web/runs/" + jid + "/result", json={"result": "aprobado", "steps": []})
        self.assertEqual(r.json()["result"], "no_verificado")
        hist = client.get("/api/validacion/tqt/runs?tarjeta_id=" + str(self.d["id"])).json()
        self.assertEqual(hist[0]["origin"], "web")
        self.assertFalse(any(x["id"].startswith("web-") for x in stm.stations()))
        no = iso.cliente_sin_sesion(app)
        self.assertEqual(no.post("/api/validacion/tqt/web/runs", json={"tarjeta_id": self.d["id"]}).status_code, 401)


if __name__ == "__main__":
    unittest.main()
