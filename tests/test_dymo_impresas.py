"""POST /api/dymo/impresas: la firma se calcula en el servidor con el estado actual de la tarjeta."""
import _aislamiento  # noqa: F401  (debe ser lo primero)
import unittest

from starlette.testclient import TestClient

from app.database import db
from app.main import app

from _aislamiento import crear_par, nuevo_lote, verificar_aislamiento


class TestDymoImpresas(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        verificar_aislamiento()
        db.init_db()
        cls.client = TestClient(app)

    def test_firma_del_servidor_ignora_firma_vieja_del_cliente(self):
        t = crear_par(nuevo_lote()["id"])
        r = self.client.post("/api/dymo/impresas", json={"marcas": [{"id": t["id"], "firma": "IDENTIFICACION|viejo|viejo"}]})
        self.assertEqual(r.status_code, 200)
        esperada = f"FINAL|{t['nombre_r1']}|{t['nombre_r2']}"
        self.assertEqual(r.json()["firmas"][str(t["id"])], esperada)
        self.assertEqual(db.get_tarjeta_by_id(t["id"])["etiqueta_firma"], esperada)

    def test_id_inexistente_no_falla(self):
        r = self.client.post("/api/dymo/impresas", json={"marcas": [{"id": 99999999, "firma": "FINAL|a|b"}]})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["n"], 0)


if __name__ == "__main__":
    unittest.main()
