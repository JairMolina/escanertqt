"""v1.3.37: enviar por correo los Excel que exporta la app (lo genera el servidor; cuentas + correos externos)."""
import _aislamiento  # noqa: F401  (debe ser lo primero)
import unittest
from unittest import mock

from app.database import db
from app.main import app
from app.services import correo, usuarios

from _aislamiento import cliente_sin_sesion, verificar_aislamiento


class TestCorreoExcel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        verificar_aislamiento()
        db.init_db()
        usuarios.sembrar(iteraciones=1000)

    def setUp(self):
        self.c = cliente_sin_sesion(app)
        self.c.cookies.set(usuarios.COOKIE, usuarios.emitir_sesion("developer@skyguardian.mx"))
        p = mock.patch.object(correo, "configurado", return_value=True); p.start(); self.addCleanup(p.stop)

    def test_destinatarios_son_cuentas_activas(self):
        d = self.c.get("/api/correo/destinatarios").json()
        self.assertIn("developer@skyguardian.mx", [x["email"] for x in d["items"]])
        self.assertEqual(d["max"], 10)

    def test_envia_reporte_del_dia_con_adjunto_a_cada_destinatario(self):
        with mock.patch.object(correo, "enviar", return_value="<id>") as env:
            r = self.c.post("/api/correo/excel", json={"tipo": "reporte_dia", "fecha": "2031-03-10", "para": ["Externo@Otra.com", "developer4@skyguardian.mx"], "mensaje": "Hola"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["enviados"], ["developer4@skyguardian.mx", "externo@otra.com"])
        self.assertEqual(env.call_count, 2)
        nombre, datos, mime = env.call_args[0][5][0]
        self.assertEqual(nombre, "Tarjetas_2031-03-10.xlsx")
        self.assertTrue(datos.startswith(b"PK"))
        self.assertIn("Hola", env.call_args[0][2])

    def test_inventario_y_validaciones(self):
        with mock.patch.object(correo, "enviar", return_value="<id>"):
            self.assertEqual(self.c.post("/api/correo/excel", json={"tipo": "inventario_tqtr", "para": ["a@b.com"]}).status_code, 200)
        self.assertEqual(self.c.post("/api/correo/excel", json={"tipo": "otro", "para": ["a@b.com"]}).status_code, 422)
        self.assertEqual(self.c.post("/api/correo/excel", json={"tipo": "inventario_tqtr", "para": ["no-es-correo"]}).status_code, 422)
        self.assertEqual(self.c.post("/api/correo/excel", json={"tipo": "reporte_dia", "fecha": "mal", "para": ["a@b.com"]}).status_code, 400)
        muchos = [f"p{i}@b.com" for i in range(11)]
        self.assertEqual(self.c.post("/api/correo/excel", json={"tipo": "inventario_tqtr", "para": muchos}).status_code, 422)

    def test_lote_exige_sesion_de_administracion(self):
        self.assertIn(self.c.post("/api/correo/excel", json={"tipo": "lote", "para": ["a@b.com"]}).status_code, (401, 503))

    def test_smtp_caido_y_sin_configurar(self):
        with mock.patch.object(correo, "enviar", side_effect=OSError("red")):
            self.assertEqual(self.c.post("/api/correo/excel", json={"tipo": "inventario_tqtr", "para": ["a@b.com"]}).status_code, 502)
        with mock.patch.object(correo, "configurado", return_value=False):
            self.assertEqual(self.c.post("/api/correo/excel", json={"tipo": "inventario_tqtr", "para": ["a@b.com"]}).status_code, 503)


if __name__ == "__main__":
    unittest.main()
