"""v1.4.88: el backend entrega al Centro de administración (centro_admin.js) lo que lee, y sigue protegido."""
import _aislamiento  # noqa: F401  (debe ser lo primero)
import os
import re
import unittest
from pathlib import Path
from unittest import mock

from app.config import settings
from app.database import db
from app.main import app
from app.services import admin_auth, usuarios

from _aislamiento import cliente_sin_sesion, crear_par, nuevo_lote, verificar_aislamiento

CLAVE = "ClaveCentro-12345"
ADMIN = "developer@skyguardian.mx"
OTRA = "developer6@skyguardian.mx"
RAIZ = Path(__file__).resolve().parent.parent


class TestCentroAdminBackend(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        verificar_aislamiento()
        db.init_db()
        usuarios.sembrar(iteraciones=1000)
        cls._parches = [mock.patch.dict(os.environ, {"TQT_ADMIN_PASSWORD": CLAVE}),
                        mock.patch.object(settings, "ADMIN_RETARDO_MS", 0), mock.patch.object(settings, "ADMIN_PBKDF2_ITER", 1000)]
        for p in cls._parches:
            p.start()

    @classmethod
    def tearDownClass(cls):
        for p in reversed(cls._parches):
            p.stop()
        admin_auth.limitador.reiniciar()

    def setUp(self):
        admin_auth.limitador.reiniciar()
        usuarios.limitador.reiniciar()
        usuarios.actualizar_cuenta(ADMIN, rol="administrador")
        usuarios.actualizar_cuenta(OTRA, rol="general", modulos=["escaner-tqt"])
        self.addCleanup(usuarios.actualizar_cuenta, OTRA, "administrador", None, None, ["escaner-tqt"])
        with db.transaction() as c:
            c.execute("DELETE FROM ajustes WHERE clave LIKE 'admin_%'")

    def entrar(self, email):
        c = cliente_sin_sesion(app)
        self.assertEqual(c.post("/api/auth/login", json={"email": email, "password": usuarios.CLAVE_INICIAL}).status_code, 200)
        return c

    def token(self, c):
        r = c.post("/api/admin/login", json={"password": CLAVE})
        self.assertEqual(r.status_code, 200, r.text)
        return {"X-Admin-Token": r.json()["token"]}

    # ------------------------------------------------------------ forma de los datos
    def test_resumen_y_listados_tienen_la_forma_que_lee_el_centro(self):
        lote = nuevo_lote()
        t = crear_par(lote["id"], r3=True)
        c = self.entrar(ADMIN)
        h = self.token(c)
        d = c.get("/api/admin/resumen", headers=h).json()
        self.assertTrue({"totales", "lotes", "inventario", "respaldos", "bd_bytes"} <= set(d))
        self.assertTrue({"tarjetas", "pcb", "bitacora"} <= set(d["totales"]))
        l = next(x for x in d["lotes"] if x["id"] == lote["id"])
        self.assertTrue({"codigo_lote", "activo", "tarjetas", "por_estado", "mes", "anio", "tipo_lote"} <= set(l))
        self.assertEqual(l["tarjetas"], 1)
        self.assertIsInstance(d["bd_bytes"], int)
        # el Centro pide el resumen con X-TQT-Lote: id de lote y 'all'
        un = c.get("/api/admin/resumen", headers={**h, "X-TQT-Lote": str(lote["id"])}).json()
        self.assertEqual([x["id"] for x in un["lotes"]], [lote["id"]])
        self.assertEqual(un["totales"]["tarjetas"], 1)
        self.assertGreaterEqual(c.get("/api/admin/resumen", headers={**h, "X-TQT-Lote": "all"}).json()["totales"]["tarjetas"], 1)

        r = c.get("/api/tarjetas", params={"limit": 500, "lote_id": lote["id"]}, headers={"X-TQT-Lote": str(lote["id"])})
        self.assertEqual(r.status_code, 200, r.text)
        j = r.json()
        self.assertEqual(j["total"], 1)
        it = j["items"][0]
        for k in ("id", "id_tarjeta_num", "nombre_r1", "nombre_r2", "nombre_r3", "mac_r1", "mac_r2", "sin_mac", "skytec", "validada",
                  "firmware_r1", "firmware_r2", "r1", "r2", "r3"):
            self.assertIn(k, it, k)
        self.assertEqual(it["id"], t["id"])
        # 'all' sin lote_id: todas las tarjetas, sin 400
        self.assertEqual(c.get("/api/tarjetas", params={"limit": 500}, headers={"X-TQT-Lote": "all"}).status_code, 200)

        p = c.get("/api/pcb", params={"limit": 5000}, headers={"X-TQT-Lote": str(lote["id"])}).json()
        self.assertGreaterEqual(p["total"], 3)
        for k in ("id", "tipo", "nombre", "mac", "serie", "estado_ciclo", "id_tarjeta_num", "firmware"):
            self.assertIn(k, p["items"][0], k)
        self.assertEqual(c.get("/api/pcb", params={"limit": 5000}, headers={"X-TQT-Lote": "all"}).status_code, 200)
        self.assertEqual(c.get("/api/pcb", params={"limit": 5001}).status_code, 422)   # el tope real del servidor
        self.assertEqual(c.get("/api/tarjetas", params={"limit": 501}).status_code, 422)

    def test_movimientos_acepta_lote_0_que_envia_todos_los_lotes(self):
        """El selector 'Todos los lotes' del Centro vale '0' y mvQuery lo manda como lote_id=0 (antes: 422 y la lista quedaba vacía)."""
        lote = nuevo_lote()
        crear_par(lote["id"])
        c = self.entrar(ADMIN)
        h = self.token(c)
        r = c.get("/api/admin/movimientos", params={"limite": 50, "desplazamiento": 0, "lote_id": 0}, headers={**h, "X-TQT-Lote": "all"})
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        for k in ("items", "total", "conteo", "categorias"):
            self.assertIn(k, d)
        self.assertEqual(d["total"], c.get("/api/admin/movimientos", headers=h).json()["total"])
        if d["items"]:
            for k in ("fecha", "categoria", "titulo", "evento", "valor", "detalle", "operador", "lote"):
                self.assertIn(k, d["items"][0], k)
        # con lote concreto en cabecera y consulta: coherente
        r = c.get("/api/admin/movimientos", params={"lote_id": lote["id"]}, headers={**h, "X-TQT-Lote": str(lote["id"])})
        self.assertEqual(r.status_code, 200, r.text)

    def test_lote_distinto_entre_cabecera_y_consulta_da_400(self):
        a, b = nuevo_lote(), nuevo_lote(activar=False, mes=8)
        c = self.entrar(ADMIN)
        r = c.get("/api/tarjetas", params={"lote_id": b["id"]}, headers={"X-TQT-Lote": str(a["id"])})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(c.get("/api/tarjetas", headers={"X-TQT-Lote": "99999999"}).status_code, 404)
        self.assertEqual(c.get("/api/tarjetas", headers={"X-TQT-Lote": "abc"}).status_code, 400)

    # ------------------------------------------------------------ acciones destructivas
    def test_acciones_destructivas_devuelven_las_claves_que_lee_el_centro(self):
        lote = nuevo_lote()
        a, b = crear_par(lote["id"], r3=True), crear_par(lote["id"], r3=True)
        c = self.entrar(ADMIN)
        h = self.token(c)
        r = c.request("DELETE", "/api/admin/tarjetas", json={"ids": [a["id"]], "liberar_pcb": True}, headers=h)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["tarjetas_borradas"], 1)
        self.assertTrue(r.json()["respaldo"])
        r = c.request("DELETE", "/api/admin/pcb", json={"ids": [b["pcb_r3_id"]]}, headers=h)
        self.assertEqual(r.json()["pcb_eliminadas"], 1)
        self.assertEqual(c.post(f"/api/admin/lote/{lote['id']}/vaciar", json={"confirmar": "vaciar"}, headers=h).status_code, 400)
        self.assertEqual(c.post(f"/api/admin/lote/{lote['id']}/vaciar", json={"confirmar": "VACIAR"}, headers=h).status_code, 200)
        self.assertEqual(c.post("/api/admin/reset", json={"confirmar": "x"}, headers=h).status_code, 400)

    # ------------------------------------------------------------ seguridad
    def test_admin_api_exige_token_y_rol_aunque_se_llame_desde_el_centro(self):
        rutas = [("GET", "/api/admin/resumen", None), ("GET", "/api/admin/movimientos", None), ("GET", "/api/admin/respaldo/descargar", None),
                 ("GET", "/api/admin/dymo/cable-r3-auto", None), ("DELETE", "/api/admin/tarjetas", {"ids": [1]}),
                 ("DELETE", "/api/admin/pcb", {"ids": [1]}), ("POST", "/api/admin/lote/1/vaciar", {"confirmar": "VACIAR"}),
                 ("POST", "/api/admin/reset", {"confirmar": "BORRAR TODO"}), ("POST", "/api/admin/cambiar-clave", {"actual": "a", "nueva": "b" * 10})]
        admin = self.entrar(ADMIN)           # sesión de usuario administrador, SIN token de /admin
        for m, u, j in rutas:
            with self.subTest(ruta=u):
                self.assertEqual(admin.request(m, u, json=j).status_code, 401)
                self.assertEqual(admin.request(m, u, json=j, headers={"X-Admin-Token": "falso"}).status_code, 401)
                self.assertEqual(cliente_sin_sesion(app).request(m, u, json=j).status_code, 401)
        # un usuario que no es administrador no llega ni con un token válido de admin (robado/compartido)
        h = self.token(admin)
        for rol in ("general", "consultor"):
            usuarios.actualizar_cuenta(OTRA, rol=rol)
            otro = self.entrar(OTRA)
            for m, u, j in rutas:
                with self.subTest(rol=rol, ruta=u):
                    self.assertEqual(otro.request(m, u, json=j, headers=h).status_code, 403)
            if rol == "consultor":
                self.assertEqual(otro.post("/api/correo/excel", json={"tipo": "lote", "para": ["a@b.mx"]}).status_code, 403)
            self.assertEqual(otro.post("/api/plataforma/correo/prueba", json={"para": "a@b.mx"}).status_code, 403)
            self.assertEqual(otro.request("DELETE", f"/api/plataforma/cuentas/{ADMIN}").status_code, 403)
            self.assertEqual(otro.patch(f"/api/plataforma/cuentas/{ADMIN}", json={"activo": False}).status_code, 403)

    def test_plataforma_exige_sesion_de_usuario(self):
        sin = cliente_sin_sesion(app)
        self.assertEqual(sin.request("DELETE", f"/api/plataforma/cuentas/{OTRA}").status_code, 401)
        self.assertEqual(sin.patch(f"/api/plataforma/cuentas/{OTRA}", json={"activo": False}).status_code, 401)
        self.assertEqual(sin.post("/api/plataforma/correo/prueba", json={"para": "a@b.mx"}).status_code, 401)

    def test_js_publico_del_centro_no_expone_secretos(self):
        js = (RAIZ / "app" / "static" / "js" / "centro_admin.js").read_text(encoding="utf-8")
        for patron in (r"TQT_ADMIN", r"password\s*[:=]\s*['\"][^'\"]+['\"]", r"SMTP_PASS", r"secret", r"Bearer\s+[A-Za-z0-9]"):
            self.assertIsNone(re.search(patron, js, re.I), patron)
        sin = cliente_sin_sesion(app)
        self.assertEqual(sin.get("/static/js/centro_admin.js").status_code, 200)
        self.assertEqual(sin.get("/static/js/admin.js").status_code, 401)           # el viejo sigue tras la sesión
        self.assertNotEqual(sin.get("/static/js/centro_admin.js/../admin.js").status_code, 200)   # httpx ya normaliza el ..; el middleware cubre el resto

    def test_admin_redirige_al_centro_y_next_solo_admite_destinos_del_monitor(self):
        c = self.entrar(ADMIN)
        r = c.get("/admin", follow_redirects=False)
        self.assertEqual((r.status_code, r.headers["location"]), (302, "/inicio?centro=1"))
        r = c.get("/admin", params={"next": "/monitor"}, follow_redirects=False)
        self.assertEqual(r.headers["location"], "/inicio?centro=1&next=%2Fmonitor")
        for malo in ("https://evil.example", "//evil.example", "/monitor/../x", "javascript:alert(1)", "/inicio"):
            with self.subTest(next=malo):
                self.assertEqual(c.get("/admin", params={"next": malo}, follow_redirects=False).headers["location"], "/inicio?centro=1")
        # un general/consultor no ve ni el redirect: el rol lo frena antes
        usuarios.actualizar_cuenta(OTRA, rol="general")
        r = self.entrar(OTRA).get("/admin", follow_redirects=False)
        self.assertNotEqual(r.headers.get("location"), "/inicio?centro=1")

    # ------------------------------------------------------------ cuentas desde el Centro
    def test_cuentas_activar_desactivar_eliminar_y_proteger_al_ultimo_admin(self):
        c = self.entrar(ADMIN)
        d = c.patch(f"/api/plataforma/cuentas/{OTRA}", json={"activo": False}).json()
        fila = next(x for x in d["cuentas"] if x["email"] == OTRA)
        self.assertFalse(fila["activo"])
        for k in ("email", "rol", "modulos", "activo", "pendiente", "ultimo_acceso", "inv_exp"):
            self.assertIn(k, fila)
        self.assertNotIn("hash", " ".join(fila))   # nunca viajan hashes de contraseña
        d = c.patch(f"/api/plataforma/cuentas/{OTRA}", json={"activo": True}).json()
        self.assertTrue(next(x for x in d["cuentas"] if x["email"] == OTRA)["activo"])
        # un administrador no puede eliminarse ni desactivarse a sí mismo desde el Centro
        self.assertEqual(c.request("DELETE", f"/api/plataforma/cuentas/{ADMIN}").status_code, 422)
        self.assertEqual(c.patch(f"/api/plataforma/cuentas/{ADMIN}", json={"activo": False}).status_code, 422)
        self.assertEqual(c.request("DELETE", "/api/plataforma/cuentas/nadie@tqt.mx").status_code, 404)
        r = c.post("/api/plataforma/invitaciones", json={"email": "baja.centro@tqt.mx", "rol": "consultor", "modulos": ["tpms"]})
        self.assertEqual(r.status_code, 200, r.text)
        d = c.request("DELETE", "/api/plataforma/cuentas/Baja.Centro@tqt.mx").json()
        self.assertNotIn("baja.centro@tqt.mx", {x["email"] for x in d["cuentas"]})

    def test_correo_prueba_valida_el_destinatario(self):
        from app.services import correo
        c = self.entrar(ADMIN)
        for malo in ("", "no-es-correo", "a@b.mx\r\nBcc: x@y.mx", "a@b.mx, c@d.mx"):
            with self.subTest(para=malo):
                self.assertEqual(c.post("/api/plataforma/correo/prueba", json={"para": malo}).status_code, 422)
        with mock.patch.object(correo, "enviar", return_value="<id@x>") as env:
            r = c.post("/api/plataforma/correo/prueba", json={"para": " Dest@Tqt.mx "})
        self.assertEqual((r.status_code, r.json()["ok"]), (200, True))
        self.assertEqual(env.call_args[0][0], "dest@tqt.mx")
        with mock.patch.object(correo, "enviar", side_effect=correo.CorreoNoConfigurado("sin SMTP")):
            self.assertEqual(c.post("/api/plataforma/correo/prueba", json={"para": "a@tqt.mx"}).status_code, 503)


if __name__ == "__main__":
    unittest.main()
