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
        self.assertEqual(self.c.get("/api/dymo/r3/xml?nombre=TQT-R1-V30-0001").status_code, 200)   # v1.3.53: R1/R2 sueltas
        self.assertEqual(self.c.get("/api/dymo/r3/xml?nombre=TQT-R4-V30-0001").status_code, 422)
        self.assertEqual(self.c.get("/api/dymo/r3/xml?nombre=TQT-R3-V30-84").status_code, 422)
        r = self.c.get("/api/dymo/r3/archivo?nombre=TQT-R3-V30-0007&tipo=label")
        self.assertEqual(r.status_code, 200)
        self.assertIn('TQT_R3_0007.label', r.headers["content-disposition"])

    def test_r3_arriba_y_r3_repetido_abajo(self):
        """v1.4.92: una R3 arriba (QR + nombre) y abajo «R3 0001» GIRADO dos veces (izquierda y derecha)."""
        from app.services.dymo_service import calcular_diseno_r3, caja_num_r3_der, obtener_formato
        f = obtener_formato("30334")
        mitades = calcular_diseno_r3(f, ["TQT-R3-V30-0001", "TQT-R3-V30-0002"])
        self.assertEqual(len(mitades), 1)   # solo la primera
        md, mitad = mitades[0], f.alto_mm / 2
        self.assertGreaterEqual(md.qr.y, 1.5 - 1e-6); self.assertLessEqual(md.qr.abajo, mitad - 1.5 + 1e-6)
        self.assertGreater(md.texto.x, md.qr.derecha); self.assertGreaterEqual(md.puntos_por_modulo, 4)
        cc = caja_num_r3_der(f)
        self.assertGreaterEqual(cc.y, mitad); self.assertLessEqual(cc.abajo, f.alto_mm - 1.5 + 1e-6)
        from app.services.dymo_service import caja_num_r3, caja_linea_r3, DymoService
        cn, ln = caja_num_r3(f), caja_linea_r3(f)   # v1.4.91: R3 al borde izquierdo, R3 repetido al derecho, línea al centro
        self.assertAlmostEqual(cn.x, 1.5); self.assertAlmostEqual(cc.derecha, f.ancho_mm - 1.5)
        self.assertLess(cn.derecha, ln.x); self.assertLess(ln.derecha, cc.x)
        self.assertAlmostEqual(ln.x + ln.w / 2, f.ancho_mm / 2); self.assertGreaterEqual(ln.y, mitad)
        self.assertIn("stroke-dasharray", DymoService.generate_r3_svg(["TQT-R3-V30-0001"], "30334"))
        for tipo in ("label", "dymo"):
            r = self.c.get(f"/api/dymo/r3/xml?nombre=TQT-R3-V30-0001&tipo={tipo}")
            self.assertEqual(r.status_code, 200)
            self.assertIn("0001", r.text); self.assertIn("QR1", r.text); self.assertNotIn("QR2", r.text)
            self.assertIn("Rotation90", r.text); self.assertIn("NUMR3", r.text); self.assertIn("LINEA", r.text)
            self.assertIn("NUMR3D", r.text); self.assertNotIn("CABLE", r.text); self.assertNotIn("----", r.text)
        dos = "nombre=TQT-R3-V30-0001&nombre=TQT-R3-V30-0002"
        self.assertEqual(self.c.get(f"/api/dymo/r3/xml?{dos}").status_code, 400)
        r = self.c.get("/api/dymo/r3/archivo?nombre=TQT-R3-V30-0001&tipo=dymo")
        self.assertIn("TQT_R3_0001.dymo", r.headers["content-disposition"])


if __name__ == "__main__":
    unittest.main()
