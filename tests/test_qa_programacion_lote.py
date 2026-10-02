"""QA de la programación por lote (POST /api/programacion/lote): simular, parcial, repetidas, R3, inexistentes, límites, concurrencia."""
import _aislamiento  # noqa: F401  (debe ser lo primero)
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi.testclient import TestClient

from app.database import db, inventario as inv
from app.main import app

from _aislamiento import verificar_aislamiento


class Base(unittest.TestCase):
    def setUp(self):
        verificar_aislamiento()
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "lote.db"
        db.init_db(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def placas(self, tipo, *series):
        ids = {}
        for s in series:
            ids[s] = inv.registrar_manual(tipo, "30", s, db_path=self.path)["pcbs"][0]["id"]
        inv.confirmar_recepcion(list(ids.values()), db_path=self.path)
        return ids

    def lote(self, items, simular=False):
        return inv.programar_lote(items, simular=simular, db_path=self.path)

    def pcb(self, pid):
        return inv.get_pcb(pid, db_path=self.path)


class TestLogica(Base):
    def test_simular_no_guarda(self):
        ids = self.placas("R1", "0021", "0022")
        r = self.lote([{"pcb_id": ids["0021"], "mac": "70:4b:ca:5b:9f:6e", "firmware": "4.1"},
                       {"pcb_id": ids["0022"], "mac": "704bca5b9f6f"}], simular=True)
        self.assertTrue(r["simulado"])
        self.assertEqual((r["total"], r["guardadas"], r["fallidas"]), (2, 2, 0))
        self.assertTrue(all(f["ok"] for f in r["resultados"]))
        for pid in ids.values():
            self.assertIsNone(self.pcb(pid)["mac"])
            self.assertIsNone(self.pcb(pid)["firmware"])

    def test_guarda_parcial_con_errores_por_fila(self):
        ids = self.placas("R1", "0021", "0022", "0023")
        r = self.lote([{"pcb_id": ids["0021"], "mac": "70:4b:ca:5b:9f:6e", "firmware": "4.1"},
                       {"pcb_id": ids["0022"], "mac": "basura"},
                       {"pcb_id": ids["0023"], "mac": "01:00:5e:00:00:01"}])   # multicast
        self.assertEqual((r["guardadas"], r["fallidas"]), (1, 2))
        self.assertEqual([f["ok"] for f in r["resultados"]], [True, False, False])
        self.assertEqual([f.get("codigo") for f in r["resultados"]], [None, 400, 400])
        self.assertEqual(self.pcb(ids["0021"])["mac"], "70:4B:CA:5B:9F:6E")
        self.assertEqual(self.pcb(ids["0021"])["firmware"], "4.1")
        self.assertIsNone(self.pcb(ids["0022"])["mac"])

    def test_mac_repetida_dentro_del_mismo_lote(self):
        ids = self.placas("R1", "0021", "0022")
        r = self.lote([{"pcb_id": ids["0021"], "mac": "704bca5b9f6e"}, {"pcb_id": ids["0022"], "mac": "70-4B-CA-5B-9F-6E"}])
        self.assertEqual([f["ok"] for f in r["resultados"]], [True, False])
        self.assertEqual(r["resultados"][1]["codigo"], 409)
        self.assertIn("TQT-R1-V30-0021", r["resultados"][1]["error"])
        self.assertIsNone(self.pcb(ids["0022"])["mac"])

    def test_mac_repetida_contra_la_base(self):
        ids = self.placas("R1", "0021", "0022")
        inv.set_mac(ids["0021"], "70:4B:CA:5B:9F:6E", db_path=self.path)
        r = self.lote([{"pcb_id": ids["0022"], "mac": "704bca5b9f6e"}], simular=True)
        self.assertEqual((r["resultados"][0]["ok"], r["resultados"][0]["codigo"]), (False, 409))

    def test_r3_rechazada(self):
        ids = self.placas("R3", "0021")
        r = self.lote([{"pcb_id": ids["0021"], "mac": "704bca5b9f6e"}])
        self.assertFalse(r["resultados"][0]["ok"])
        self.assertEqual(r["resultados"][0]["codigo"], 400)
        self.assertIn("R3", r["resultados"][0]["error"])
        self.assertIsNone(self.pcb(ids["0021"])["mac"])

    def test_placa_inexistente_y_sin_identificar(self):
        r = self.lote([{"nombre": "TQT-R1-V30-0999", "mac": "704bca5b9f6e"}, {"pcb_id": 987654, "mac": "704bca5b9f6e"},
                       {"mac": "704bca5b9f6e"}, {"nombre": "hola", "mac": "704bca5b9f6e"}])
        self.assertEqual([f["codigo"] for f in r["resultados"]], [404, 404, 400, 400])
        self.assertEqual(r["guardadas"], 0)

    def test_nombre_tolerante(self):
        ids = self.placas("R2", "0010")
        r = self.lote([{"nombre": "  tqt r2 v30 0010 ", "mac": "MAC: 70:4b:ca:5b:9c:a2", "firmware": "2.1"}])
        f = r["resultados"][0]
        self.assertTrue(f["ok"], f)
        self.assertEqual((f["nombre"], f["pcb_id"], f["mac"]), ("TQT-R2-V30-0010", ids["0010"], "70:4B:CA:5B:9C:A2"))
        self.assertEqual(self.pcb(ids["0010"])["firmware"], "2.1")

    def test_firmware_invalido_no_guarda_la_mac(self):
        ids = self.placas("R1", "0021")
        r = self.lote([{"pcb_id": ids["0021"], "mac": "704bca5b9f6e", "firmware": "4.1; DROP TABLE"}])
        self.assertEqual((r["resultados"][0]["ok"], r["resultados"][0]["codigo"]), (False, 400))
        self.assertIsNone(self.pcb(ids["0021"])["mac"])   # una sola operación: nada a medias

    def test_baja_no_admite_mac(self):
        ids = self.placas("R1", "0021")
        inv.marcar_falla(ids["0021"], "x", db_path=self.path)
        inv.eliminar_pcb(ids["0021"], db_path=self.path)   # pasa a BAJA o se borra
        r = self.lote([{"pcb_id": ids["0021"], "mac": "704bca5b9f6e"}])
        self.assertFalse(r["resultados"][0]["ok"])

    def test_lista_pcb_admite_limit_5000(self):
        self.placas("R1", "0021")
        self.assertEqual(len(inv.listar_pcb(sin_mac=True, limit=5000, db_path=self.path)["items"]), 1)


class TestApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        verificar_aislamiento()
        db.init_db()
        cls.c = TestClient(app)

    def test_500_items_y_501_da_422(self):
        items = [{"nombre": f"TQT-R1-V30-{n:04d}", "mac": "704bca5b9f6e"} for n in range(1, 501)]
        r = self.c.post("/api/programacion/lote", json={"items": items, "simular": True})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["total"], 500)
        r = self.c.post("/api/programacion/lote", json={"items": items + items[:1], "simular": True})
        self.assertEqual(r.status_code, 422)
        self.assertEqual(self.c.post("/api/programacion/lote", json={"items": [], "simular": True}).status_code, 422)

    def test_resultado_por_fila_sin_pcb_completo(self):
        inv.registrar_manual("R1", "30", "7001")
        r = self.c.post("/api/programacion/lote", json={"items": [{"nombre": "TQT-R1-V30-7001", "mac": "02:11:22:33:44:01"}], "simular": True})
        f = r.json()["resultados"][0]
        self.assertTrue(f["ok"])
        self.assertNotIn("pcb", f)


class TestConcurrencia(Base):
    def test_misma_mac_desde_dos_lotes_simultaneos(self):
        ids = self.placas("R1", *[f"{n:04d}" for n in range(1, 21)])
        lista = list(ids.values())
        A = [{"pcb_id": p, "mac": f"02:AA:00:00:00:{i:02X}"} for i, p in enumerate(lista[:10])]
        B = [{"pcb_id": p, "mac": f"02:AA:00:00:00:{i:02X}"} for i, p in enumerate(lista[10:])]   # mismas 10 MAC
        with ThreadPoolExecutor(2) as ex:
            ra, rb = list(ex.map(lambda it: self.lote(it), (A, B)))
        self.assertEqual(ra["guardadas"] + rb["guardadas"], 10, (ra["guardadas"], rb["guardadas"]))
        macs = [p["mac"] for p in inv.listar_pcb(limit=5000, db_path=self.path)["items"] if p["mac"]]
        self.assertEqual(len(macs), 10)
        self.assertEqual(len(set(macs)), 10)


if __name__ == "__main__":
    unittest.main()
