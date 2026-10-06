"""v1.3.36: etiquetas DYMO sueltas de R3 (solo el nombre TQT-R3-Vxx-0000, en texto y QR)."""
import _aislamiento  # noqa: F401  (debe ser lo primero)
import unittest

from app.database import db
from app.main import app
from app.services import usuarios
from app.services.dymo_service import DymoService

from _aislamiento import cliente_sin_sesion, verificar_aislamiento


class TestDymoR3(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        verificar_aislamiento()
        db.init_db()
        usuarios.sembrar(iteraciones=1000)

    def setUp(self):
        self.c = cliente_sin_sesion(app)
        self.c.cookies.set(usuarios.COOKIE, usuarios.emitir_sesion("developer@skyguardian.mx"))

    def test_xml_con_solo_el_nombre(self):
        for tipo in ("label", "dymo"):
            r = self.c.get(f"/api/dymo/r3/xml?nombre=TQT-R3-V31-0084&tipo={tipo}")
            self.assertEqual(r.status_code, 200)
            self.assertIn("TQT-R3-V31-0084", r.text)
            self.assertNotIn("TQT-R1", r.text)
        self.assertEqual(DymoService.trama_lineas({"_lineas": ["TQT-R3-V30-0001"]}), ["TQT-R3-V30-0001"])

    def test_nombre_invalido_y_archivo(self):
        self.assertEqual(self.c.get("/api/dymo/r3/xml?nombre=TQT-R1-V30-0001").status_code, 422)
        self.assertEqual(self.c.get("/api/dymo/r3/xml?nombre=TQT-R3-V30-84").status_code, 422)
        r = self.c.get("/api/dymo/r3/archivo?nombre=TQT-R3-V30-0007&tipo=label")
        self.assertEqual(r.status_code, 200)
        self.assertIn('TQT-R3-V30-0007.label', r.headers["content-disposition"])


if __name__ == "__main__":
    unittest.main()
