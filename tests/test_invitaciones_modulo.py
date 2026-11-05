"""v1.4.14: invitaciones por módulo desde el núcleo I+D y permiso por módulo de cada ruta."""
import _aislamiento  # noqa: F401  (debe ser lo primero)
import unittest
from unittest import mock

from app import modulos as modulos_cat
from app.database import db
from app.main import app
from app.services import correo, usuarios

from _aislamiento import cliente_sin_sesion, verificar_aislamiento

ADMIN = "developer@skyguardian.mx"
OTRA = "developer5@skyguardian.mx"


class TestInvitacionesModulo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        verificar_aislamiento()
        db.init_db()
        usuarios.sembrar(iteraciones=1000)

    def setUp(self):
        usuarios.limitador.reiniciar()
        usuarios.actualizar_cuenta(ADMIN, rol="administrador")
        self.addCleanup(usuarios.actualizar_cuenta, OTRA, "administrador", None, None, ["escaner-tqt"])

    def entrar(self, email):
        c = cliente_sin_sesion(app)
        self.assertEqual(c.post("/api/auth/login", json={"email": email, "password": usuarios.CLAVE_INICIAL}).status_code, 200)
        return c

    def borrar(self, email):
        try:
            usuarios.eliminar_cuenta(email)
        except LookupError:
            pass

    def test_invitar_a_un_modulo_sin_smtp_devuelve_el_enlace(self):
        c = self.entrar(ADMIN)
        self.addCleanup(self.borrar, "nueva.impresora@tqt.mx")
        with mock.patch.object(correo, "enviar", side_effect=correo.CorreoNoConfigurado("Correo sin configurar.")):
            r = c.post("/api/plataforma/invitaciones", json={"email": "Nueva.Impresora@tqt.mx", "rol": "general", "modulos": ["impresora"]})
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertFalse(d["enviado"])
        self.assertIn("/invitacion#", d["enlace"])
        fila = next(x for x in d["cuentas"] if x["email"] == "nueva.impresora@tqt.mx")
        self.assertEqual((fila["modulos"], bool(fila["pendiente"])), (["impresora"], True))

    def test_correo_de_invitacion_lista_los_modulos(self):
        c = self.entrar(ADMIN)
        self.addCleanup(self.borrar, "con.correo@tqt.mx")
        with mock.patch.object(correo, "enviar") as env:
            d = c.post("/api/plataforma/invitaciones", json={"email": "con.correo@tqt.mx", "rol": "consultor", "modulos": ["impresora", "tpms"]}).json()
        self.assertTrue(d["enviado"])
        texto = env.call_args[0][2]
        self.assertIn("plataforma I+D", texto)
        self.assertIn("TPMS, Impresora", texto)

    def test_reenviar_cancelar_y_errores(self):
        c = self.entrar(ADMIN)
        self.addCleanup(self.borrar, "pendiente@tqt.mx")
        with mock.patch.object(correo, "enviar"):
            c.post("/api/plataforma/invitaciones", json={"email": "pendiente@tqt.mx", "rol": "general", "modulos": ["impresora"]})
            self.assertTrue(c.post("/api/plataforma/invitaciones/pendiente@tqt.mx/reenviar").json()["enviado"])
            self.assertEqual(c.post("/api/plataforma/invitaciones", json={"email": "pendiente@tqt.mx", "modulos": []}).status_code, 422)
            self.assertEqual(c.post("/api/plataforma/invitaciones", json={"email": "otro@tqt.mx", "modulos": ["nada"]}).status_code, 422)
        self.assertEqual(c.delete(f"/api/plataforma/invitaciones/{ADMIN}").status_code, 422)   # una cuenta activa no se cancela
        d = c.delete("/api/plataforma/invitaciones/pendiente@tqt.mx").json()
        self.assertNotIn("pendiente@tqt.mx", {x["email"] for x in d["cuentas"]})

    def test_solo_administradores_invitan(self):
        usuarios.actualizar_cuenta(OTRA, rol="general", modulos=["escaner-tqt"])
        r = self.entrar(OTRA).post("/api/plataforma/invitaciones", json={"email": "x@tqt.mx", "modulos": []})
        self.assertEqual(r.status_code, 403)

    def test_cada_ruta_exige_su_modulo(self):
        self.assertEqual(modulos_cat.modulo_de_ruta("/api/activos"), "impresora")
        self.assertEqual(modulos_cat.modulo_de_ruta("/monitor"), "escaner-tqt")
        self.assertIsNone(modulos_cat.modulo_de_ruta("/api/escaner/abc/codigo"))
        usuarios.actualizar_cuenta(OTRA, rol="general", modulos=["impresora"])
        c = self.entrar(OTRA)
        self.assertEqual(c.get("/monitor", follow_redirects=False).headers["location"], "/inicio?denegado=escaner-tqt")
        self.assertEqual(c.get("/api/activos").status_code, 200)
        self.assertNotEqual(c.get("/api/escaner/no-existe").status_code, 403)   # compartida: basta un módulo
        for js in ("ws_client.js", "common.js", "visor.js", "scanner.js", "qrcode-generator.js", "dymo_connect.js", "impresora.js"):
            self.assertEqual(c.get("/static/js/" + js).status_code, 200, js)   # lo que carga /impresora y el celular escáner
        usuarios.actualizar_cuenta(OTRA, modulos=["escaner-tqt"])
        r = c.get("/api/activos")
        self.assertEqual((r.status_code, r.json()["modulo"]), (403, "impresora"))
        self.assertEqual(c.get("/impresora", follow_redirects=False).headers["location"], "/inicio?denegado=impresora")


    def test_impresora_tiene_su_propia_pantalla_de_acceso(self):
        """v1.4.17: sin sesión, Impresora lleva a /impresora/acceso (no al login de Escáner TQT)."""
        c = cliente_sin_sesion(app)
        r = c.get("/impresora?activo=ACT-0001", follow_redirects=False)
        self.assertEqual(r.headers["location"], "/impresora/acceso?next=%2Fimpresora%3Factivo%3DACT-0001")
        self.assertEqual(c.get("/monitor", follow_redirects=False).headers["location"], "/login?next=%2Fmonitor")
        r = c.get("/impresora/acceso")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("__VERSION__", r.text)
        self.assertIn("/static/js/login.js", r.text)
        imp = next(m for m in c.get("/api/modulos").json()["modulos"] if m["id"] == "impresora")
        self.assertEqual(imp["login"], "/impresora/acceso")


    def test_centro_activar_desactivar_eliminar_y_correo_de_prueba(self):
        """v1.4.88: lo que tenía Administración › Cuentas ahora se hace desde el Centro de administración."""
        c = self.entrar(ADMIN)
        mail = "centro.cuenta@tqt.mx"
        self.addCleanup(self.borrar, mail)
        with mock.patch.object(correo, "enviar", return_value="<id>"):
            c.post("/api/plataforma/invitaciones", json={"email": mail, "rol": "general", "modulos": ["impresora"]})
        with db.transaction() as cn:
            cn.execute("UPDATE usuarios SET inv_hash = NULL, activo = 1 WHERE email = ?", (mail,))
        d = c.patch(f"/api/plataforma/cuentas/{mail}", json={"activo": False}).json()
        cta = next(x for x in d["cuentas"] if x["email"] == mail)
        self.assertEqual(cta["activo"], 0)
        self.assertIn("ultimo_acceso", cta)
        self.assertIn("inv_exp", cta)
        d = c.patch(f"/api/plataforma/cuentas/{mail}", json={"activo": True}).json()
        self.assertEqual(next(x for x in d["cuentas"] if x["email"] == mail)["activo"], 1)
        # correo de prueba: sin SMTP => 503; con SMTP simulado => ok; sin sesión => 401
        with mock.patch.object(correo, "enviar", side_effect=correo.CorreoNoConfigurado("sin SMTP")):
            self.assertEqual(c.post("/api/plataforma/correo/prueba", json={"para": mail}).status_code, 503)
        with mock.patch.object(correo, "enviar", return_value="<id>"):
            self.assertTrue(c.post("/api/plataforma/correo/prueba", json={"para": mail}).json()["ok"])
        self.assertEqual(cliente_sin_sesion(app).post("/api/plataforma/correo/prueba", json={"para": mail}).status_code, 401)
        # eliminar
        d = c.delete(f"/api/plataforma/cuentas/{mail}").json()
        self.assertFalse(any(x["email"] == mail for x in d["cuentas"]))
        self.assertEqual(c.delete(f"/api/plataforma/cuentas/{mail}").status_code, 404)

    def test_centro_no_elimina_ni_desactiva_al_ultimo_administrador(self):
        c = self.entrar(ADMIN)
        with db.transaction() as cn:
            cn.execute("UPDATE usuarios SET activo = 0 WHERE rol = 'administrador' AND email != ?", (ADMIN,))
        try:
            self.assertEqual(c.patch(f"/api/plataforma/cuentas/{ADMIN}", json={"activo": False}).status_code, 422)
            self.assertEqual(c.delete(f"/api/plataforma/cuentas/{ADMIN}").status_code, 422)
        finally:
            with db.transaction() as cn:
                cn.execute("UPDATE usuarios SET activo = 1 WHERE inv_hash IS NULL")

    def test_admin_antiguo_redirige_al_centro_y_el_centro_trae_las_secciones(self):
        """v1.4.88: /admin redirige al Centro de administración (solo admite como destino el monitor) y el portal trae todas las secciones."""
        c = self.entrar(ADMIN)
        r = c.get("/admin", follow_redirects=False)
        self.assertEqual((r.status_code, r.headers["location"]), (302, "/inicio?centro=1"))
        r = c.get("/admin?next=/monitor", follow_redirects=False)
        self.assertEqual(r.headers["location"], "/inicio?centro=1&next=%2Fmonitor")
        self.assertEqual(c.get("/admin?next=https://evil.example", follow_redirects=False).headers["location"], "/inicio?centro=1")
        html = c.get("/inicio").text
        for sec in ("cuentas", "resumen", "modulos", "movimientos", "borrado", "clave"):
            self.assertIn(f'data-sec="{sec}"', html)
        self.assertNotIn('data-sec="tarjetas"', html); self.assertNotIn('data-sec="pcb"', html)   # son del módulo Escáner TQT
        for ident in ("admGate", "btnVaciar", "btnReset", "formClave", "mCsv", "admExcel", "admExcelMail"):
            self.assertIn(f'id="{ident}"', html)
        js = c.get("/static/js/centro_admin.js").text
        for ruta in ("/api/admin/login", "/api/admin/resumen", "/api/admin/movimientos", "/api/admin/reset",
                     "/api/admin/cambiar-clave", "/api/admin/respaldo/descargar", "/api/admin/export/excel", "/api/admin/dymo/cable-r3-auto", "/vaciar", "/api/plataforma/admin/modulos"):
            self.assertIn(ruta, js)
        self.assertNotRegex(js, r".innerHTMLs*[=+]")   # texto del servidor solo por textContent

    def test_tpms_tiene_su_propia_pantalla_de_acceso(self):
        """v1.4.27: TPMS ya está disponible, con su login propio y su ventana de escaneo."""
        c = cliente_sin_sesion(app)
        r = c.get("/tpms", follow_redirects=False)
        self.assertEqual(r.headers["location"], "/tpms/acceso?next=%2Ftpms")
        r = c.get("/tpms/acceso")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("__VERSION__", r.text)
        t = next(m for m in c.get("/api/modulos").json()["modulos"] if m["id"] == "tpms")
        self.assertEqual((t["estado"], t["url"], t["login"]), ("disponible", "/tpms", "/tpms/acceso"))
        self.assertEqual(modulos_cat.modulo_de_ruta("/static/js/tpms.js"), "tpms")


if __name__ == "__main__":
    unittest.main()
