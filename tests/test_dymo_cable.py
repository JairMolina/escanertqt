"""v1.3.83: etiqueta de cable (número solo en la mitad izquierda de la etiqueta rectangular)."""
import _aislamiento  # noqa: F401  (debe ser lo primero)
import unittest
import xml.etree.ElementTree as ET

from app.database import db
from app.main import app
from app.services import usuarios
from app.services.dymo_service import DymoService, caja_cable, obtener_formato

from _aislamiento import cliente_sin_sesion, verificar_aislamiento


class TestDymoCable(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        verificar_aislamiento()
        db.init_db()
        usuarios.sembrar(iteraciones=1000)

    def setUp(self):
        self.c = cliente_sin_sesion(app)
        self.c.cookies.set(usuarios.COOKIE, usuarios.emitir_sesion("developer@skyguardian.mx"))

    def test_xml_con_solo_el_numero(self):
        for tipo in ("label", "dymo"):
            r = self.c.get(f"/api/dymo/cable/xml?numero=0021&tipo={tipo}")
            self.assertEqual(r.status_code, 200, r.text)
            ET.fromstring(r.text.encode("utf-8"))
            self.assertIn("0021", r.text)
            self.assertNotIn("TQT-", r.text)
            self.assertIn("TQT", r.text)   # v1.3.92: «TQT» arriba del número

    def test_numero_en_la_mitad_izquierda(self):
        f = obtener_formato("30334")
        c = caja_cable(f)
        self.assertLessEqual(c.x + c.w, f.ancho_mm / 2)
        self.assertLessEqual(c.x + c.w, f.ancho_mm / 4 + 1)   # v1.3.93: pegado a la izquierda, lejos del doblez
        self.assertIn('Center', DymoService.generate_cable_label_xml("0007"))
        for xml in (DymoService.generate_cable_label_xml("0007"), DymoService.generate_cable_dcd_xml("0007")):
            self.assertIn('<Rotation>Rotation90</Rotation>', xml)   # v1.3.84: número vertical
            self.assertIn('<Name>LINEA</Name>', xml)                # v1.3.90: línea punteada al centro
        from app.services.dymo_service import caja_linea_cable
        ln = caja_linea_cable(f)
        self.assertAlmostEqual(ln.x + ln.w / 2, f.ancho_mm / 2)

    def test_numero_invalido_y_archivo(self):
        self.assertEqual(self.c.get("/api/dymo/cable/xml?numero=12a").status_code, 422)
        r = self.c.get("/api/dymo/cable/xml?numero=0021%2F0034&tipo=label")   # v1.3.92: R1/R2 con número diferente
        self.assertEqual(r.status_code, 200)
        self.assertIn("TQT", r.text); self.assertIn("0021/0034", r.text)
        r = self.c.get("/api/dymo/cable/archivo?numero=0021%2F0034&tipo=label")
        self.assertIn("TQT_cable_0021-0034.label", r.headers.get("content-disposition", ""))
        r = self.c.get("/api/dymo/cable/archivo?numero=0005&tipo=label")
        self.assertEqual(r.status_code, 200)
        self.assertIn("TQT_cable_0005.label", r.headers.get("content-disposition", ""))

    def test_cable_r3(self):   # v1.4.5: «TQT: 0000» arriba y «R3: 0000» abajo
        for tipo in ("label", "dymo"):
            r = self.c.get(f"/api/dymo/cable/xml?numero=0011&r3=0073&tipo={tipo}")
            self.assertEqual(r.status_code, 200, r.text)
            ET.fromstring(r.text.encode("utf-8").lstrip(b"\xef\xbb\xbf"))
            self.assertIn("TQT: 0011", r.text); self.assertIn("R3: 0073", r.text)
        r = self.c.get("/api/dymo/cable/svg?numero=0011&r3=0073")
        self.assertEqual(r.status_code, 200); self.assertIn("R3: 0073", r.text)
        r = self.c.get("/api/dymo/cable/archivo?numero=0011&r3=0073&tipo=label")
        self.assertIn("TQT_cable_0011_R3_0073.label", r.headers.get("content-disposition", ""))
        self.assertEqual(self.c.get("/api/dymo/cable/xml?numero=0011&r3=7a").status_code, 422)
        self.assertEqual(self.c.get("/api/dymo/cable/xml?numero=0011%2F0012&r3=0073").status_code, 422)


if __name__ == "__main__":
    unittest.main()
