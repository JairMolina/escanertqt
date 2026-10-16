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

    def evidence(self, d=None, pb2=True, errs=(13, 14), **over):
        d = d or self.d
        lines = [s29(**self.ident(d, **over))]
        if pb2:
            lines += [s29(**self.ident(d, PB=2, MOV=3, **over)), s29(**self.ident(d, PB=2, MOV=4, **over))]
        lines += [s29(**self.ident(d, err=e, **over)) for e in errs]
        items = [{"seq": 1, "data": {"kind": "card", "args": [d["nombre"].replace("-", "_")]}}]
        items += [{"seq": i + 2, "data": {"kind": "status", "args": [{"fields": {}, "raw": raw}]}}
                  for i, raw in enumerate(lines)]
        return items

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
