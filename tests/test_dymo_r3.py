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
        self.assertIn('TQT_R3_0007.label', r.headers["content-disposition"])

    def test_dos_r3_por_etiqueta(self):
        """v1.3.44: dos R3 por etiqueta, una en cada mitad; con una sola queda en la mitad izquierda."""
        from app.services.dymo_service import calcular_diseno_r3, obtener_formato
        f = obtener_formato("30334")
        a, b = calcular_diseno_r3(f, ["TQT-R3-V30-0001", "TQT-R3-V30-0002"])
        mitad = f.alto_mm / 2   # mitades horizontales: arriba y abajo (57 x 16 mm)
        for md, y0 in ((a, 0), (b, mitad)):   # QR a la izquierda y texto a la derecha, dentro de su tira con margen
            self.assertGreaterEqual(md.qr.y, y0 + 1.5 - 1e-6); self.assertLessEqual(md.qr.abajo, y0 + mitad - 1.5 + 1e-6)
            self.assertGreater(md.texto.x, md.qr.derecha); self.assertLessEqual(md.texto.derecha, f.ancho_mm - 1.5 + 1e-6)
            self.assertGreaterEqual(md.puntos_por_modulo, 4)
        self.assertEqual(len(calcular_diseno_r3(f, ["TQT-R3-V30-0001"])), 1)
        for tipo in ("label", "dymo"):
            r = self.c.get(f"/api/dymo/r3/xml?nombre=TQT-R3-V30-0001&nombre=TQT-R3-V30-0002&tipo={tipo}")
            self.assertEqual(r.status_code, 200)
            self.assertIn("QR2", r.text); self.assertIn("TQT-R3-V30-0002", r.text)
            r1 = self.c.get(f"/api/dymo/r3/xml?nombre=TQT-R3-V30-0001&tipo={tipo}")
            self.assertIn("QR1", r1.text); self.assertNotIn("QR2", r1.text)
        tres = "&".join(f"nombre=TQT-R3-V30-000{i}" for i in (1, 2, 3))
        self.assertEqual(self.c.get(f"/api/dymo/r3/xml?{tres}").status_code, 400)
        r = self.c.get("/api/dymo/r3/archivo?nombre=TQT-R3-V30-0001&nombre=TQT-R3-V30-0002&tipo=dymo")
        self.assertIn("TQT_R3_0001_0002.dymo", r.headers["content-disposition"])


if __name__ == "__main__":
    unittest.main()
