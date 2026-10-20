"""v1.4.10: portal de módulos (/inicio). Escáner TQT es un módulo más; sin sesión, "/" lleva al portal."""
import _aislamiento  # noqa: F401  (debe ser lo primero)
import unittest

from app.config import settings
from app.database import db
from app.main import app
from app.services import usuarios

from _aislamiento import cliente_sin_sesion, verificar_aislamiento


class TestPortalModulos(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        verificar_aislamiento()
        db.init_db()
        usuarios.sembrar(iteraciones=1000)

    def setUp(self):
        usuarios.limitador.reiniciar()
        self.c = cliente_sin_sesion(app)

    def test_portal_y_sus_archivos_abren_sin_sesion(self):
        r = self.c.get("/inicio")
        self.assertEqual(r.status_code, 200)
        self.assertIn(settings.APP_VERSION, r.text)
        self.assertNotIn("__VERSION__", r.text)
        for url in ("/static/js/inicio.js", "/static/css/inicio.css", "/api/health"):
            self.assertEqual(self.c.get(url).status_code, 200, url)

    def test_raiz_sin_sesion_va_al_portal_y_lo_demas_al_login(self):
        r = self.c.get("/", follow_redirects=False)
        self.assertEqual((r.status_code, r.headers["location"]), (302, "/inicio"))
        r = self.c.get("/monitor", follow_redirects=False)
        self.assertEqual(r.headers["location"], "/login?next=%2Fmonitor")
        self.assertEqual(self.c.get("/static/js/common.js").status_code, 401)   # solo inicio.js se abre

    def test_api_modulos_lista_escaner_tqt_disponible(self):
        d = self.c.get("/api/modulos").json()
        self.assertEqual(d["version"], settings.APP_VERSION)
        tqt = next(m for m in d["modulos"] if m["id"] == "escaner-tqt")
        self.assertEqual((tqt["estado"], tqt["url"]), ("disponible", "/"))
        for m in d["modulos"]:
            self.assertIn(m["estado"], ("disponible", "proximamente", "mantenimiento"))
        self.assertEqual(self.c.post("/api/modulos").status_code, 405)

    def test_rutas_de_agentes_siguen_publicas(self):
        for url in ("/api/stm32/agent/x", "/api/dymo/remoto/agente/x"):
            self.assertNotEqual(self.c.get(url).headers.get("X-Auth"), "login", url)

    def test_con_sesion_la_raiz_sigue_igual(self):
        r = self.c.post("/api/auth/login", json={"email": "developer@skyguardian.mx", "password": usuarios.CLAVE_INICIAL})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.c.get("/", follow_redirects=False).status_code, 200)
        self.assertEqual(self.c.get("/inicio").status_code, 200)


if __name__ == "__main__":
    unittest.main()
