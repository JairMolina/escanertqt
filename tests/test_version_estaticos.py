import _aislamiento  # noqa: F401  (debe ser lo primero)
"""v1.4.27: las páginas sirven sus JS/CSS con ?v=<versión> (el ?v= manual se quedaba viejo y Cloudflare servía JS anterior)
y cada lote cuenta también las placas que tiene (las sueltas movidas con «Mover a lote» no son tarjetas)."""
import re
import unittest

from app.config import settings
from app.database import db
from app.main import app
from app.services import usuarios

from _aislamiento import cliente_sin_sesion, nuevo_lote, verificar_aislamiento


class TestVersionEstaticos(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        verificar_aislamiento()
        db.init_db()
        usuarios.sembrar(iteraciones=1000)
        usuarios.limitador.reiniciar()
        cls.c = cliente_sin_sesion(app)
        r = cls.c.post("/api/auth/login", json={"email": "developer@skyguardian.mx", "password": usuarios.CLAVE_INICIAL})
        assert r.status_code == 200, r.text

    def test_paginas_con_version_actual(self):
        for ruta in ("/monitor", "/login", "/inicio", "/"):
            html = self.c.get(ruta).text
            vs = set(re.findall(r"/static/[\w./-]+\.(?:js|css)\?v=([\w.]+)", html))
            self.assertEqual(vs, {settings.APP_VERSION}, ruta)
        self.assertIn("image/", self.c.get("/favicon.ico").headers["content-type"])   # los binarios no se reescriben

    def test_lote_cuenta_placas(self):
        lote = nuevo_lote(activar=False)["id"]
        pid = self.c.post("/api/pcb/manual", json={"tipo": "R3", "version": "10", "serie": "0971"}).json()["pcbs"][0]["id"]
        self.assertEqual(self.c.post("/api/pcb/mover-lote", json={"ids": [pid], "lote_id": lote}).status_code, 200)
        fila = next(l for l in self.c.get("/api/lotes").json() if l["id"] == lote)
        self.assertEqual((fila["tarjetas"], fila["placas"]), (0, 1))


if __name__ == "__main__":
    unittest.main()
