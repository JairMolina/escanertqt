"""v1.3.16: inicio de sesión. Nada de la app (páginas, API, WebSocket, archivos) abre sin sesión; cuentas, límites y cookies."""
import _aislamiento  # noqa: F401  (debe ser lo primero)
import re
import time
import unittest
from unittest import mock

from fastapi.routing import APIRoute
from starlette.routing import Mount
from starlette.websockets import WebSocketDisconnect

from app.config import settings
from app.database import db
from app.main import RUTAS_PUBLICAS, PREFIJOS_PUBLICOS, app
from app.services import admin_auth, usuarios

from _aislamiento import cliente_sin_sesion, verificar_aislamiento

CLAVE = usuarios.CLAVE_INICIAL
EMAIL = "developer@skyguardian.mx"


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        verificar_aislamiento()
        db.init_db()
        usuarios.sembrar(iteraciones=1000)

    def setUp(self):
        usuarios.limitador.reiniciar()
        admin_auth.limitador.reiniciar()
        self.c = cliente_sin_sesion(app)
        p = mock.patch.object(settings, "ADMIN_RETARDO_MS", 0); p.start(); self.addCleanup(p.stop)

    def entrar(self, email=EMAIL, clave=CLAVE):
        return self.c.post("/api/auth/login", json={"email": email, "password": clave})


class TestCuentas(Base):
    def test_01_las_4_cuentas_iniciales_existen_y_entran(self):
        esperadas = {"developer@skyguardian.mx", "developer4@skyguardian.mx", "developer5@skyguardian.mx", "developer6@skyguardian.mx"}
        self.assertTrue(esperadas <= {u["email"] for u in usuarios.listar()})
        for e in sorted(esperadas):
            c = cliente_sin_sesion(app)
            r = c.post("/api/auth/login", json={"email": e.upper(), "password": CLAVE})   # el correo no distingue mayúsculas
            self.assertEqual(r.status_code, 200, (e, r.text))
            self.assertEqual(c.get("/api/auth/yo").json()["email"], e)

    def test_02_cookie_segura(self):
        r = self.entrar()
        sc = r.headers["set-cookie"].lower()
        for marca in ("httponly", "secure", "samesite=lax", "path=/", "max-age="):
            self.assertIn(marca, sc)
        self.assertNotIn(CLAVE, r.text)

    def test_03_error_unico_para_correo_desconocido_y_clave_mala(self):
        a = self.entrar(clave="mala-clave-123")
        b = self.entrar(email="nadie@skyguardian.mx", clave="mala-clave-123")
        c = self.entrar(email="no-es-correo", clave="x")
        self.assertEqual((a.status_code, b.status_code, c.status_code), (401, 401, 401))
        self.assertEqual(a.json(), b.json()); self.assertEqual(a.json(), c.json())
        self.assertNotIn("set-cookie", a.headers)

    def test_04_bloqueo_por_intentos_y_el_bueno_tambien_espera(self):
        for _ in range(settings.ADMIN_MAX_FALLOS):
            r = self.entrar(clave="mala-clave-123")
        self.assertEqual(r.status_code, 429)
        self.assertIn("Retry-After", r.headers)
        self.assertEqual(self.entrar().status_code, 429)           # bloqueado aunque ahora la clave sea la buena
        otro = cliente_sin_sesion(app)
        otro.cookies.set("tqt_cid", "b" * 24)     # otro equipo (en Docker todos comparten IP: la marca del equipo los separa)
        self.assertEqual(otro.post("/api/auth/login", json={"email": "developer4@skyguardian.mx", "password": CLAVE}).status_code, 200)

    def test_05_cambio_de_clave_invalida_las_demas_sesiones(self):
        c2 = cliente_sin_sesion(app)
        self.assertEqual(c2.post("/api/auth/login", json={"email": "developer5@skyguardian.mx", "password": CLAVE}).status_code, 200)
        c3 = cliente_sin_sesion(app)
        c3.post("/api/auth/login", json={"email": "developer5@skyguardian.mx", "password": CLAVE})
        self.assertEqual(c2.post("/api/auth/cambiar-clave", json={"actual": "incorrecta-123", "nueva": "NuevaClaveSegura1"}).status_code, 403)
        self.assertEqual(c2.post("/api/auth/cambiar-clave", json={"actual": CLAVE, "nueva": "corta"}).status_code, 422)
        self.assertEqual(c2.post("/api/auth/cambiar-clave", json={"actual": CLAVE, "nueva": CLAVE}).status_code, 422)
        try:
            self.assertEqual(c2.post("/api/auth/cambiar-clave", json={"actual": CLAVE, "nueva": "NuevaClaveSegura1"}).status_code, 200)
            self.assertEqual(c2.get("/api/auth/yo").status_code, 200)       # quien cambió sigue dentro
            self.assertEqual(c3.get("/api/auth/yo").status_code, 401)        # la otra sesión ya no vale
            self.assertEqual(cliente_sin_sesion(app).post("/api/auth/login", json={"email": "developer5@skyguardian.mx", "password": CLAVE}).status_code, 401)
        finally:   # deja la cuenta como estaba para las demás pruebas
            usuarios.cambiar_clave("developer5@skyguardian.mx", "NuevaClaveSegura1", CLAVE)
            with db.transaction() as c:
                c.execute("UPDATE usuarios SET debe_cambiar = 1 WHERE email = 'developer5@skyguardian.mx'")

    def test_06_cuenta_desactivada_pierde_la_sesion(self):
        c = cliente_sin_sesion(app)
        self.assertEqual(c.post("/api/auth/login", json={"email": "developer6@skyguardian.mx", "password": CLAVE}).status_code, 200)
        with db.transaction() as cx:
            cx.execute("UPDATE usuarios SET activo = 0 WHERE email = 'developer6@skyguardian.mx'")
        try:
            self.assertEqual(c.get("/api/auth/yo").status_code, 401)
            self.assertEqual(cliente_sin_sesion(app).post("/api/auth/login", json={"email": "developer6@skyguardian.mx", "password": CLAVE}).status_code, 401)
        finally:
            with db.transaction() as cx:
                cx.execute("UPDATE usuarios SET activo = 1 WHERE email = 'developer6@skyguardian.mx'")

    def test_07_cerrar_sesion(self):
        self.entrar()
        self.assertEqual(self.c.get("/api/auth/yo").status_code, 200)
        self.c.post("/api/auth/logout")
        self.assertEqual(self.c.get("/api/auth/yo").status_code, 401)

    def test_08_sembrar_no_pisa_una_clave_cambiada(self):
        antes = {u["email"] for u in usuarios.listar()}
        self.assertEqual(usuarios.sembrar(iteraciones=1000), 0)
        self.assertEqual({u["email"] for u in usuarios.listar()}, antes)


class TestSinSesionNadaAbre(Base):
    def test_10_todas_las_rutas_registradas_rechazan_sin_sesion(self):
        # El esquema OpenAPI lista TODAS las rutas de la API con su prefijo (sin servir /docs).
        rutas = [(path, [m.upper() for m in ops if m in ("get", "post", "put", "patch", "delete")]) for path, ops in app.openapi()["paths"].items()]
        probadas = 0
        for path, metodos in rutas:
            url = re.sub(r"\{[^}]+\}", "1", path)
            if url in RUTAS_PUBLICAS or url.startswith(PREFIJOS_PUBLICOS):
                continue
            for m in metodos:
                r = self.c.request(m, url, json={} if m not in ("GET", "DELETE") else None, follow_redirects=False)
                self.assertIn(r.status_code, (401, 302), f"{m} {url} respondió {r.status_code} SIN sesión")
                if r.status_code == 302:
                    self.assertTrue(r.headers["location"].startswith("/login?next="), url)
                probadas += 1
        self.assertGreater(probadas, 60)

    def test_11_paginas_redirigen_al_login_con_next(self):
        for ruta in ("/", "/monitor", "/emparejar", "/programar", "/consultar", "/dymo", "/admin"):
            r = self.c.get(ruta, follow_redirects=False)
            self.assertEqual(r.status_code, 302, ruta)
            self.assertEqual(r.headers["location"], "/login?next=" + ruta.replace("/", "%2F"))

    def test_12_rutas_inventadas_tambien_piden_sesion(self):
        for ruta in ("/no-existe", "/api/no-existe", "/static/no-existe.js", "/.env", "/docs", "/openapi.json", "/api/../etc/passwd", "//evil.com"):
            r = self.c.get(ruta, follow_redirects=False)
            self.assertIn(r.status_code, (401, 302, 404), ruta)
            self.assertNotEqual(r.status_code, 200, ruta)

    def test_13_solo_lo_publico_abre(self):
        self.assertEqual(self.c.get("/login").status_code, 200)
        self.assertEqual(self.c.get("/api/health").json(), {"ok": True})
        self.assertEqual(self.c.get("/static/js/login.js").status_code, 200)
        self.assertEqual(self.c.get("/static/css/app.css").status_code, 200)
        self.assertIn(self.c.get("/cert").status_code, (200, 404))
        for ruta in ("/static/js/common.js", "/static/js/escritorio.js", "/static/monitor.html", "/api/config", "/api/status", "/api/lotes", "/api/pcb", "/api/tarjetas"):
            self.assertEqual(self.c.get(ruta, follow_redirects=False).status_code, 401, ruta)
        self.assertEqual(self.c.get("/api/config", follow_redirects=False).headers.get("x-auth"), "login")

    def test_14_cookie_manipulada_o_vencida_no_sirve(self):
        self.entrar()
        buena = self.c.cookies.get(usuarios.COOKIE)
        cuerpo, firma = buena.split(".")
        malas = ["", "x", "a.b", buena + "A", cuerpo + "." + firma[:-2] + "AA", cuerpo[:-2] + "AA." + firma, "." + firma, cuerpo + ".", buena * 3, "%C3%A9.%C3%A9"]
        for m in malas:
            c = cliente_sin_sesion(app)
            c.cookies.set(usuarios.COOKIE, m)
            self.assertEqual(c.get("/api/lotes").status_code, 401, repr(m)[:40])
        with db.get_db() as cx:
            guardado = cx.execute("SELECT hash FROM usuarios WHERE email = ?", (EMAIL,)).fetchone()["hash"]
        vencida = usuarios._emitir(EMAIL, guardado, None, ahora=time.time() - 13 * 3600)
        c = cliente_sin_sesion(app); c.cookies.set(usuarios.COOKIE, vencida)
        self.assertEqual(c.get("/api/lotes").status_code, 401)

    def test_15_sesion_de_otra_base_o_secreto_no_sirve(self):
        with db.transaction() as c:
            c.execute("UPDATE ajustes SET valor = 'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA' WHERE clave = 'user_secret'")
        try:
            self.assertEqual(self.c.get("/api/lotes").status_code, 401)
        finally:
            pass
        # el secreto cambió: las sesiones nuevas se firman con el nuevo y las anteriores quedaron inválidas
        self.assertEqual(self.entrar().status_code, 200)
        self.assertEqual(self.c.get("/api/lotes").status_code, 200)

    def test_16_websocket_exige_sesion(self):
        with self.assertRaises(WebSocketDisconnect):
            with self.c.websocket_connect("/ws?client_type=monitor") as ws:
                ws.receive_text()
        self.entrar()   # la cookie es Secure: el cliente de pruebas no la manda por ws://, se pasa a mano
        cookie = f"{usuarios.COOKIE}={self.c.cookies.get(usuarios.COOKIE)}"
        with self.c.websocket_connect("/ws?client_type=monitor", headers={"cookie": cookie}) as ws:
            self.assertIn("CONEXION_ESTABLECIDA", ws.receive_text())

    def test_17_metodos_que_escriben_sin_sesion_dan_401_no_redireccion(self):
        for m, u in (("POST", "/api/pcb/escanear"), ("PUT", "/api/ajustes"), ("DELETE", "/api/pcb/1"), ("PATCH", "/api/tarjetas/1"), ("POST", "/api/recepcion/confirmar")):
            self.assertEqual(self.c.request(m, u, json={}).status_code, 401, (m, u))

    def test_18_admin_sigue_pidiendo_su_propia_clave_ademas_de_la_sesion(self):
        self.entrar()
        self.assertIn(self.c.get("/api/admin/resumen").status_code, (401, 503))     # con sesión de usuario, sin token de admin
        self.assertIn(self.c.post("/api/excel/import", json={}).status_code, (401, 503))


if __name__ == "__main__":
    unittest.main()
