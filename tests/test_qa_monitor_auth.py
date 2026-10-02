"""La contraseña de supervisor protege SOLO la zona de administración (/admin y /api/admin/*: borrar, vaciar, exportar).
La consola de PC (/monitor) y las acciones de lote NO piden contraseña."""
import _aislamiento  # noqa: F401  (debe ser lo primero)
import os
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from app.database import db
from app.main import app
from app.services import admin_auth

from _aislamiento import verificar_aislamiento

CLAVE = "ClaveDePrueba-123"


class TestSoloAdminPideClave(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        verificar_aislamiento()
        db.init_db()
        cls._env = mock.patch.dict(os.environ, {"TQT_ADMIN_PASSWORD": CLAVE})
        cls._env.start()
        admin_auth.limitador.reiniciar()

    @classmethod
    def tearDownClass(cls):
        admin_auth.limitador.reiniciar()
        cls._env.stop()

    def cliente(self):
        return TestClient(app, base_url="https://testserver", follow_redirects=False)

    def test_la_consola_y_las_pantallas_abren_sin_contrasena(self):
        c = self.cliente()
        for ruta in ("/", "/monitor", "/emparejar", "/programar", "/consultar", "/dymo"):
            self.assertEqual(c.get(ruta).status_code, 200, ruta)
        self.assertEqual(c.get("/monitor").headers["cache-control"], "no-store")

    def test_las_acciones_de_lote_y_de_taller_no_piden_contrasena(self):
        c = self.cliente()
        r = c.post("/api/lotes", json={"codigo_lote": "2027-01", "mes": 1, "anio": 2027, "crear_excel": False})
        self.assertEqual(r.status_code, 201, r.text)
        self.assertEqual(c.post("/api/lotes/9999/activar").status_code, 404)      # llega al handler: no hay 401
        self.assertNotEqual(c.post("/api/sync/excel").status_code, 401)
        self.assertEqual(c.post("/api/pcb/escanear", json={"codigo": "TQT-R1-V30-0001"}).status_code, 200)

    def test_la_zona_de_administracion_si_pide_contrasena(self):
        c = self.cliente()
        self.assertEqual(c.get("/admin").status_code, 200)                         # la página abre y muestra el login
        for metodo, ruta, cuerpo in (("get", "/api/admin/resumen", None), ("get", "/api/admin/movimientos", None),
                                     ("get", "/api/admin/export/excel", None),
                                     ("delete", "/api/admin/tarjetas", {"ids": [1]}), ("delete", "/api/admin/pcb", {"ids": [1]}),
                                     ("post", "/api/admin/lote/1/vaciar", {"confirmar": "VACIAR"}),
                                     ("post", "/api/admin/reset", {"confirmar": "BORRAR TODO"}),
                                     ("get", "/api/export/excel", None),
                                     ("post", "/api/excel/import", {"excel_path": "x.xlsx"})):
            r = c.request(metodo.upper(), ruta, json=cuerpo) if cuerpo is not None else c.request(metodo.upper(), ruta)
            self.assertEqual(r.status_code, 401, ruta)

    def test_login_fija_cookie_segura_y_logout_la_borra(self):
        c = self.cliente()
        r = c.post("/api/admin/login", json={"password": CLAVE})
        self.assertEqual(r.status_code, 200)
        sc = r.headers["set-cookie"].lower()
        for marca in ("tqt_admin=", "httponly", "secure", "samesite=strict", "path=/"):
            self.assertIn(marca, sc)
        self.assertEqual(c.get("/api/admin/resumen").status_code, 200)             # la cookie basta dentro de la zona de administración
        self.assertEqual(c.post("/api/admin/logout").status_code, 200)
        c.cookies.clear()
        self.assertEqual(c.get("/api/admin/resumen").status_code, 401)


if __name__ == "__main__":
    unittest.main()
