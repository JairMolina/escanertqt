import _aislamiento  # noqa: F401  (debe ser lo primero)
"""v1.4.91: la luna Pruebas automáticas tiene su propia pantalla de acceso (antes heredaba /login de Escáner TQT)."""
import unittest

from app.main import app
from app.modulos import login_de_ruta

from _aislamiento import cliente_sin_sesion

ACCESO = "/pruebas-automaticas/acceso"


class TestPruebasAutoAcceso(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c = cliente_sin_sesion(app)

    def test_login_de_ruta(self):
        for ruta in ("/pruebas-automaticas", "/static/pruebas_auto.html", "/static/js/pruebas_auto.js", "/api/pruebas-auto/estado"):
            self.assertEqual(login_de_ruta(ruta), ACCESO, ruta)
        self.assertEqual(login_de_ruta(ACCESO), "/login")   # la propia pantalla es pública: nunca se redirige a sí misma en bucle
        self.assertEqual(login_de_ruta("/monitor"), "/login")
        self.assertEqual(login_de_ruta("/caiquen"), "/caiquen/acceso")

    def test_sin_sesion_redirige_al_acceso_de_la_luna(self):
        r = self.c.get("/pruebas-automaticas", follow_redirects=False)
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.headers["location"].startswith(ACCESO + "?next="), r.headers["location"])
        self.assertEqual(self.c.get("/monitor", follow_redirects=False).headers["location"].split("?")[0], "/login")

    def test_pagina_publica_con_su_identidad(self):
        r = self.c.get(ACCESO)
        self.assertEqual(r.status_code, 200)
        self.assertIn("Pruebas automáticas", r.text)
        self.assertEqual(r.headers["cache-control"], "no-store")
        self.assertEqual(self.c.get("/api/pruebas-auto/estado").status_code, 401)   # la API sigue protegida


if __name__ == "__main__":
    unittest.main()
