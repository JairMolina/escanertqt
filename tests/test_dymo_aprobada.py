"""v1.4.0: etiqueta de tarjeta con la leyenda «Aprobada» (opcional, apagada por defecto) y SVG de cable."""
import _aislamiento  # noqa: F401  (debe ser lo primero)
import unittest
import xml.etree.ElementTree as ET

from app.database import db
from app.main import app
from app.services import usuarios
from app.services.dymo_service import DymoService, LEYENDA_APROBADA

from _aislamiento import cliente_sin_sesion, verificar_aislamiento

T = {"id": 1, "id_tarjeta_num": "0021", "nombre_r1": "TQT-R1-V30-0021", "mac_r1": "70:4B:CA:5B:9F:6E",
     "nombre_r2": "TQT-R2-V30-0010", "mac_r2": "70:4B:CA:5B:9C:A2"}


class TestDymoAprobada(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        verificar_aislamiento()
        db.init_db()
        usuarios.sembrar(iteraciones=1000)

    def test_leyenda_exacta(self):
        self.assertEqual(LEYENDA_APROBADA, "Aprobada")

    def test_apagada_por_defecto(self):
        for xml in (DymoService.generate_dymo_xml(T), DymoService.generate_dcd_xml(T), DymoService.generate_svg_preview(T)):
            self.assertNotIn("Aprobada", xml)

    def test_encendida_agrega_leyenda_sin_cambiar_qr(self):
        for f in ("30334", "30252"):
            self.assertEqual(DymoService.lineas_texto(T, True)[:4], DymoService.trama_lineas(T))
            self.assertEqual(DymoService.lineas_texto(T, True)[-1], "Aprobada")
            v8 = DymoService.generate_dymo_xml(T, f, True)
            dcd = DymoService.generate_dcd_xml(T, f, aprobada=True)
            ET.fromstring(v8.encode()); ET.fromstring(dcd.encode())
            self.assertIn("Aprobada", v8); self.assertIn("Aprobada", dcd)
            self.assertIn("Aprobada", DymoService.generate_svg_preview(T, f, aprobada=True))
            # el QR (payload de 4 líneas) no cambia
            self.assertEqual(DymoService.format_qr_payload(T), "\n".join(DymoService.trama_lineas(T)))
            self.assertNotIn("<DataString>" + "Aprobada", dcd)

    def test_leyenda_cabe_en_la_zona_de_texto(self):
        from app.services.dymo_service import alto_texto_mm
        for f in ("30334", "30252"):
            d = DymoService.diseno(T, f)
            self.assertLessEqual(alto_texto_mm(5, d.fuente_pt), d.texto.h)

    def test_endpoints(self):
        c = cliente_sin_sesion(app)
        c.cookies.set(usuarios.COOKIE, usuarios.emitir_sesion("developer@skyguardian.mx"))
        r = c.get("/api/dymo/cable/svg?numero=0021")
        self.assertEqual(r.status_code, 200); self.assertIn("0021", r.text); ET.fromstring(r.text.encode())
        self.assertEqual(c.get("/api/dymo/cable/svg?numero=ab").status_code, 422)
        self.assertEqual(c.get("/api/dymo/label/999999/xml?aprobada=1").status_code, 404)


if __name__ == "__main__":
    unittest.main()
