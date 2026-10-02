"""Bloqueo de login por EQUIPO (dentro de Docker todos comparten IP) con tope global."""
import _aislamiento  # noqa: F401  (debe ser lo primero)
import os
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from app.config import settings
from app.database import db
from app.main import app
from app.services import admin_auth

from _aislamiento import verificar_aislamiento

CLAVE = "ClaveDePrueba-123"


def equipo(cid):
    c = TestClient(app, base_url="https://testserver")          # todos comparten la misma IP ('testclient'), como dentro de Docker
    c.cookies.set("tqt_cid", cid)
    return c


class TestBloqueoPorEquipo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        verificar_aislamiento()
        db.init_db()
        cls._env = mock.patch.dict(os.environ, {"TQT_ADMIN_PASSWORD": CLAVE})
        cls._env.start()

    @classmethod
    def tearDownClass(cls):
        admin_auth.limitador.reiniciar()
        cls._env.stop()

    def setUp(self):
        admin_auth.limitador.reiniciar()

    def _fallar(self, c, n):
        return [c.post("/api/admin/login", json={"password": "mala"}).status_code for _ in range(n)]

    def test_los_fallos_de_un_equipo_no_bloquean_a_los_demas(self):
        a, b = equipo("aaaaaaaaaaaaaaaaaaaaaaaa"), equipo("bbbbbbbbbbbbbbbbbbbbbbbb")
        self.assertEqual(self._fallar(a, settings.ADMIN_MAX_FALLOS)[-1], 429)         # el equipo A queda bloqueado
        self.assertEqual(a.post("/api/admin/login", json={"password": CLAVE}).status_code, 429)
        self.assertEqual(b.post("/api/admin/login", json={"password": CLAVE}).status_code, 200)   # B entra normal

    def test_sin_marca_de_equipo_comparten_cubo_por_ip(self):
        a, b = TestClient(app, base_url="https://testserver"), TestClient(app, base_url="https://testserver")
        self._fallar(a, settings.ADMIN_MAX_FALLOS)
        self.assertEqual(b.post("/api/admin/login", json={"password": CLAVE}).status_code, 429)   # sin marca: cubo compartido (más estricto)

    def test_cambiar_de_marca_no_evita_el_tope_global(self):
        tope = settings.ADMIN_MAX_FALLOS * 6
        for i in range(tope):
            equipo(f"marca{i:020d}").post("/api/admin/login", json={"password": "mala"})      # cada intento con una marca distinta
        r = equipo("cccccccccccccccccccccccc").post("/api/admin/login", json={"password": CLAVE})
        self.assertEqual(r.status_code, 429)                                                     # bloqueo global: nadie entra hasta que expire

    def test_una_marca_invalida_se_ignora(self):
        c = equipo("../../etc")                                                                  # no alfanumérica: cae al cubo de la IP
        self.assertEqual(self._fallar(c, settings.ADMIN_MAX_FALLOS)[-1], 429)

    def test_la_pagina_de_administracion_entrega_la_marca(self):
        c = TestClient(app, base_url="https://testserver")
        r = c.get("/admin")
        sc = r.headers.get("set-cookie", "").lower()
        for marca in ("tqt_cid=", "httponly", "secure", "samesite=strict"):
            self.assertIn(marca, sc)
        self.assertNotIn("set-cookie", equipo("dddddddddddddddddddddddd").get("/admin").headers)   # ya la tiene: no se cambia

    def test_entrar_bien_limpia_solo_los_fallos_de_ese_equipo(self):
        a, b = equipo("eeeeeeeeeeeeeeeeeeeeeeee"), equipo("ffffffffffffffffffffffff")
        self._fallar(a, settings.ADMIN_MAX_FALLOS - 1)
        self._fallar(b, settings.ADMIN_MAX_FALLOS - 1)
        self.assertEqual(a.post("/api/admin/login", json={"password": CLAVE}).status_code, 200)   # A entra: se limpia A
        self.assertEqual(self._fallar(b, 1)[-1], 429)                                             # B conserva sus fallos y se bloquea


if __name__ == "__main__":
    unittest.main()
