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

    def test_aprobada_exige_ultima_prueba_aprobada(self):
        """v1.4.0: ?aprobada=1 solo con la última ejecución TQT de la tarjeta en 'aprobado' (si no, 403)."""
        import time
        import _aislamiento as iso
        from app.services import test_station
        t = iso.crear_par(iso.nuevo_lote()["id"])
        c = cliente_sin_sesion(app)
        c.cookies.set(usuarios.COOKIE, usuarios.emitir_sesion("developer@skyguardian.mx"))
        urls = ["/api/dymo/svg/%d" % t["id"], "/api/dymo/label/%d/xml" % t["id"], "/api/dymo/label/%d/archivo" % t["id"]]
        for u in urls:
            self.assertEqual(c.get(u, params={"aprobada": "true"}).status_code, 403, u)
            self.assertEqual(c.get(u).status_code, 200, u)  # sin leyenda sigue igual
        test_station.init()

        def ejecucion(jid, result, creada):
            with db.get_db() as cx:
                sid = test_station.web_station(cx, "op@test.mx")
                cx.execute("INSERT INTO tqt_test_runs(id,station,requested_card,tarjeta_id,operator,state,created,updated,inventory,result,origin)"
                           " VALUES(?,?,?,?,?,'finished',?,?,'{}',?,'web')",
                           (jid, sid, t["id"], t["id"] if result == "aprobado" else None, "op@test.mx", creada, creada, result))
        ahora = time.time()
        ejecucion("apr-%d" % t["id"], "aprobado", ahora)
        for u in urls:
            r = c.get(u, params={"aprobada": "true"})
            self.assertEqual(r.status_code, 200, u)
        self.assertIn("Aprobada", c.get(urls[0], params={"aprobada": "true"}).text)
        # una prueba posterior no aprobada vuelve a bloquear la leyenda
        ejecucion("fal-%d" % t["id"], "fallido", ahora + 1)
        self.assertEqual(c.get(urls[0], params={"aprobada": "true"}).status_code, 403)


if __name__ == "__main__":
    unittest.main()
