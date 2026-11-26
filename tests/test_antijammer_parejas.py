import _aislamiento  # noqa: F401  (debe ser lo primero)
"""Parejas Skudo AntiJammer: una RX + una TX, sin repetir placa; RX/TX queda en Materiales; deshacer conserva RX/TX."""
import unittest

from app.database import db
from app.main import app
from app.services import antijammer_etiqueta as etq
from app.services import usuarios

from _aislamiento import cliente_sin_sesion, verificar_aislamiento


class TestAntijammerParejas(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        verificar_aislamiento()
        db.init_db()
        usuarios.sembrar(iteraciones=1000)
        usuarios.limitador.reiniciar()
        cls.sin = cliente_sin_sesion(app)
        cls.c = cliente_sin_sesion(app)
        r = cls.c.post("/api/auth/login", json={"email": "developer@skyguardian.mx", "password": usuarios.CLAVE_INICIAL})
        assert r.status_code == 200, r.text
        for s in ("7101", "7102", "7103", "7104", "7105"):
            assert cls.c.post("/api/antijammer/pcb/manual", json={"version": "1", "serie": s}).status_code == 201

    def _sueltas(self):
        return {p["nombre"] for p in self.c.get("/api/antijammer/parejas").json()["sin_pareja"]}

    def test_01_sin_sesion(self):
        self.assertIn(self.sin.get("/api/antijammer/parejas").status_code, (401, 403))

    def test_02_emparejar_y_reglas(self):
        r = self.c.post("/api/antijammer/parejas", json={"rx": "SJ-V1-7101", "tx": "7102"})
        self.assertEqual(r.status_code, 201, r.text)
        pid = r.json()["id"]
        d = self.c.get("/api/antijammer/parejas").json()
        par = next(p for p in d["parejas"] if p["id"] == pid)
        self.assertEqual((par["rx"]["nombre"], par["tx"]["nombre"]), ("SJ-V1-7101", "SJ-V1-7102"))
        self.assertNotIn("SJ-V1-7101", self._sueltas())
        self.assertIn("SJ-V1-7103", self._sueltas())
        # RX/TX en Materiales y en la etiqueta
        self.assertEqual(etq.datos_de("SJ-V1-7101")["tipo"], "RX")
        self.assertEqual(etq.datos_de("SJ-V1-7102")["tipo"], "TX")
        # una placa no puede estar en dos parejas, ni ser RX y TX a la vez, ni ser de otro producto
        self.assertEqual(self.c.post("/api/antijammer/parejas", json={"rx": "7101", "tx": "7103"}).status_code, 409)
        self.assertEqual(self.c.post("/api/antijammer/parejas", json={"rx": "7103", "tx": "7103"}).status_code, 422)
        self.assertEqual(self.c.post("/api/antijammer/parejas", json={"rx": "7103", "tx": "TPMS_V1_0004"}).status_code, 404)
        self.assertEqual(self.c.post("/api/antijammer/parejas", json={"rx": "7103", "tx": "SJ-V1-9988"}).status_code, 404)
        # deshacer: vuelven a estar sueltas y conservan su RX/TX
        self.assertEqual(self.c.delete(f"/api/antijammer/parejas/{pid}").status_code, 200)
        self.assertTrue({"SJ-V1-7101", "SJ-V1-7102"} <= self._sueltas())
        self.assertEqual(etq.datos_de("SJ-V1-7101")["tipo"], "RX")
        self.assertEqual(self.c.delete(f"/api/antijammer/parejas/{pid}").status_code, 404)
        # se pueden volver a emparejar al revés y queda en movimientos
        self.assertEqual(self.c.post("/api/antijammer/parejas", json={"rx": "7102", "tx": "7101"}).status_code, 201)
        self.assertEqual(etq.datos_de("SJ-V1-7101")["tipo"], "TX")
        ev = self.c.get("/api/antijammer/pcb/por-codigo", params={"codigo": "SJ-V1-7101"}).json()["eventos"]
        self.assertTrue({"emparejada", "desemparejada"} <= {e["accion"] for e in ev})

    def test_03_filtro_por_mes_y_placa_eliminada(self):
        r = self.c.post("/api/antijammer/parejas", json={"rx": "7104", "tx": "7105"})
        self.assertEqual(r.status_code, 201, r.text)
        d = self.c.get("/api/antijammer/parejas").json()
        self.assertTrue(d["meses"])
        vacio = self.c.get("/api/antijammer/parejas", params={"mes": "1999-01"}).json()
        self.assertEqual((vacio["parejas"], vacio["sin_pareja"]), ([], []))
        self.assertEqual(self.c.get("/api/antijammer/parejas", params={"mes": "mal"}).status_code, 422)
        tx = r.json()["tx"]["id"]
        self.assertEqual(self.c.delete(f"/api/antijammer/pcb/{tx}").status_code, 200)
        ids = {p["id"] for p in self.c.get("/api/antijammer/parejas").json()["parejas"]}
        self.assertNotIn(r.json()["id"], ids)          # la pareja se suelta al eliminar la placa
        self.assertIn("SJ-V1-7104", self._sueltas())


if __name__ == "__main__":
    unittest.main()
