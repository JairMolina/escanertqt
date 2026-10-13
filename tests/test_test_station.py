import _aislamiento as iso
import unittest, json
from fastapi.testclient import TestClient
from app.main import app
from app.database import db, inventario as inv
from app.services import test_station as s, stm32_programming as stm


class TestStationAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init_db()

    def setUp(self):
        self.t = iso.crear_par(iso.nuevo_lote()["id"], version="30")
        inv.set_mac(self.t["r1"]["id"], iso.mac_unica())
        inv.set_mac(self.t["r2"]["id"], iso.mac_unica())
        self.st = stm.station_create("Banco simulado", "operador@test.mx")
        s.claim(self.st["id"], {"serial_connected": True})
        with db.get_db() as c:
            self.d = s.snapshot(self.t["id"], c)

    def report(self):
        return dict(
            result="aprobado",
            card=self.d["nombre"].replace("-", "_"),
            card_id=self.d["r1_serie"],
            reported_mac=self.d["mac_r1"],
            r1_ble_address=self.d["mac_r1"],
            reported_mac_r2=self.d["mac_r2"],
            r2_ble_address=self.d["mac_r2"],
            steps=[{"name": str(i), "state": "aprobado"} for i in range(14)],
            communication_quality={"state": "limpia"},
            serial_health={
                "frames": 50,
                "retries": 0,
                "partial_warnings": 0,
                "ack_errors": 0,
            },
            warnings=[],
            status_final={"IDR": self.d["r2_serie"]},
        )

    def run_job(self):
        j = s.create(self.st["id"], self.t["id"], "operador@test.mx", True)
        s.claim(self.st["id"], {"serial_connected": True})
        return j

    def test_two_runs_distinct_and_original_inventory_unchanged(self):
        before = inv.get_pcb(self.t["r1"]["id"])
        a = self.run_job()
        r = s.finish(self.st["id"], a["id"], self.report())
        self.assertEqual(r["result"], "aprobado")
        self.assertFalse(r["report"]["release_authorized"])
        b = self.run_job()
        self.assertNotEqual(a["id"], b["id"])
        s.finish(self.st["id"], b["id"], self.report())
        self.assertEqual(before, inv.get_pcb(self.t["r1"]["id"]))

    def test_mac_mismatch_not_associated(self):
        j = self.run_job()
        r = self.report()
        r["reported_mac_r2"] = "00:00:00:00:00:01"
        result = s.finish(self.st["id"], j["id"], r)
        self.assertEqual(result["result"], "no_verificado")
        self.assertIsNone(result["tarjeta_id"])

    def test_missing_partial_evidence_never_approved(self):
        j = self.run_job()
        r = self.report()
        r["steps"] = r["steps"][:2]
        self.assertEqual(s.finish(self.st["id"], j["id"], r)["result"], "no_verificado")

    def test_retry_ack_and_warnings_distinct(self):
        j = self.run_job()
        r = self.report()
        r["serial_health"]["retries"] = 1
        self.assertEqual(s.finish(self.st["id"], j["id"], r)["result"], "no_verificado")
        j = self.run_job()
        r = self.report()
        r["warnings"] = ["Aviso RX"]
        self.assertEqual(
            s.finish(self.st["id"], j["id"], r)["result"], "aprobado_con_advertencias"
        )

    def test_command_lock_cancel_and_restart(self):
        j = self.run_job()
        with self.assertRaises(ValueError):
            s.command(self.st["id"], "ports", {})
        s.claim(self.st["id"], {"serial_connected": True, "run_id": None})
        self.assertEqual(s.read(j["id"])["state"], "interrupted")

    def test_authenticated_and_full_log_immutable(self):
        j = self.run_job()
        text = "<script>alert(1)</script>\r\nCOM RX   \n"
        with self.assertRaises(ValueError):
            s.events("other", j["id"], [])
        items = [{"seq": 1, "data": {"kind": "full_log", "text": text}}]
        s.events(self.st["id"], j["id"], items)
        s.events(self.st["id"], j["id"], items)
        with self.assertRaises(ValueError):
            s.events(
                self.st["id"],
                j["id"],
                [{"seq": 1, "data": {"kind": "full_log", "text": "changed"}}],
            )
        client = TestClient(app, base_url="https://testserver")
        self.assertEqual(
            client.get("/api/validacion/tqt/runs/" + j["id"] + "/log").text, text
        )
        no = iso.cliente_sin_sesion(app)
        self.assertEqual(no.get("/api/validacion/tqt/runs/" + j["id"]).status_code, 401)
        self.assertEqual(
            no.post("/api/stm32/agent/tests/claim", json={}).status_code, 401
        )

    def test_snapshot_has_different_r2_serial(self):
        self.assertEqual(self.d["r1_serie"], self.t["r1"]["serie"])
        self.assertEqual(self.d["r2_serie"], self.t["r2"]["serie"])

    def test_final_result_cannot_be_replaced(self):
        j = self.run_job()
        r = self.report()
        s.finish(self.st["id"], j["id"], r)
        s.finish(self.st["id"], j["id"], r)
        with self.assertRaises(ValueError):
            s.finish(self.st["id"], j["id"], {"result": "fallido"})

    def test_r2_identifier_is_required(self):
        j = self.run_job()
        r = self.report()
        r["status_final"]["IDR"] = "9999"
        self.assertEqual(s.finish(self.st["id"], j["id"], r)["result"], "no_verificado")

    def test_programming_and_physical_test_exclude_each_other(self):
        j = self.run_job()
        d, _ = stm.preview(self.t["r1"]["id"])
        with self.assertRaises(ValueError):
            stm.create_job(
                self.t["r1"]["id"], self.st["id"], d["hex_sha256"], "test", True
            )

    def test_unknown_card_does_not_create_inventory(self):
        with db.get_db() as c:
            before = c.execute("SELECT COUNT(*) FROM tarjetas_produccion").fetchone()[0]
            with self.assertRaises(ValueError):
                s.snapshot(99999999, c)
            self.assertEqual(
                before,
                c.execute("SELECT COUNT(*) FROM tarjetas_produccion").fetchone()[0],
            )


if __name__ == "__main__":
    unittest.main()
