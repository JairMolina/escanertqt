"""v1.3.33: "Olvidé mi contraseña" aprobado por otra cuenta (código de 6 dígitos). Sin compartir contraseñas."""
import _aislamiento  # noqa: F401  (debe ser lo primero)
import unittest
from unittest import mock

from app.config import settings
from app.database import db
from app.main import app
from app.services import admin_auth, usuarios

from _aislamiento import cliente_sin_sesion, verificar_aislamiento

OLVIDADA = "developer5@skyguardian.mx"
AYUDA = "developer6@skyguardian.mx"
NUEVA = "ClaveNuevaSegura-2026"


class TestReset(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        verificar_aislamiento()
        db.init_db()
        usuarios.sembrar(iteraciones=1000)

    def setUp(self):
        usuarios.limitador.reiniciar()
        admin_auth.limitador.reiniciar()
        usuarios._sol_por_cliente.clear()
        p = mock.patch.object(settings, "ADMIN_RETARDO_MS", 0); p.start(); self.addCleanup(p.stop)
        # restablece la clave de la cuenta de prueba a la inicial por si otra prueba la cambió
        with db.transaction() as c:
            c.execute("UPDATE usuarios SET hash = ?, debe_cambiar = 1 WHERE email IN (?, ?)", (usuarios.aa.hash_clave(usuarios.CLAVE_INICIAL, 1000), OLVIDADA, AYUDA))
        self.anon = cliente_sin_sesion(app)
        self.ayuda = cliente_sin_sesion(app)
        r = self.ayuda.post("/api/auth/login", json={"email": AYUDA, "password": usuarios.CLAVE_INICIAL})
        self.assertEqual(r.status_code, 200)

    def pedir(self, email=OLVIDADA):
        r = self.anon.post("/api/auth/olvide", json={"email": email})
        self.assertEqual(r.status_code, 200)
        return r.json()["ticket"]

    def test_01_flujo_completo(self):
        t = self.pedir()
        self.assertEqual(self.anon.post("/api/auth/olvide/estado", json={"ticket": t}).json()["estado"], "pendiente")
        pend = self.ayuda.get("/api/auth/solicitudes").json()["items"]
        self.assertEqual([p["email"] for p in pend], [OLVIDADA])
        a = self.ayuda.post(f"/api/auth/solicitudes/{pend[0]['id']}/aprobar")
        self.assertEqual(a.status_code, 200)
        codigo = a.json()["codigo"]
        self.assertRegex(codigo, r"^\d{6}$")
        self.assertEqual(self.anon.post("/api/auth/olvide/estado", json={"ticket": t}).json()["estado"], "aprobada")
        r = self.anon.post("/api/auth/restablecer", json={"ticket": t, "codigo": codigo, "nueva": NUEVA})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.anon.post("/api/auth/login", json={"email": OLVIDADA, "password": NUEVA}).json()["debe_cambiar"], False)
        self.assertEqual(cliente_sin_sesion(app).post("/api/auth/login", json={"email": OLVIDADA, "password": usuarios.CLAVE_INICIAL}).status_code, 401)
        # el código es de un solo uso
        r2 = self.anon.post("/api/auth/restablecer", json={"ticket": t, "codigo": codigo, "nueva": NUEVA + "x"})
        self.assertEqual(r2.status_code, 403)

    def test_02_no_se_aprueba_la_propia_solicitud(self):
        self.pedir(AYUDA)
        self.assertEqual(self.ayuda.get("/api/auth/solicitudes").json()["items"], [])   # ni la ve
        with db.get_db() as c:
            sid = c.execute("SELECT id FROM usuarios_reset WHERE email = ? AND estado = 'pendiente'", (AYUDA,)).fetchone()["id"]
        self.assertEqual(self.ayuda.post(f"/api/auth/solicitudes/{sid}/aprobar").status_code, 403)

    def test_03_codigo_incorrecto_se_cancela_tras_5_intentos(self):
        t = self.pedir()
        sid = self.ayuda.get("/api/auth/solicitudes").json()["items"][0]["id"]
        codigo = self.ayuda.post(f"/api/auth/solicitudes/{sid}/aprobar").json()["codigo"]
        mal = "000000" if codigo != "000000" else "111111"
        with mock.patch.object(usuarios, "RESET_MAX_INTENTOS", 3):
            for _ in range(3):
                usuarios.limitador.reiniciar()
                self.assertEqual(self.anon.post("/api/auth/restablecer", json={"ticket": t, "codigo": mal, "nueva": NUEVA}).status_code, 403)
        usuarios.limitador.reiniciar()
        # aun con el código bueno, la solicitud quedó cancelada
        self.assertEqual(self.anon.post("/api/auth/restablecer", json={"ticket": t, "codigo": codigo, "nueva": NUEVA}).status_code, 403)
        self.assertEqual(self.anon.post("/api/auth/olvide/estado", json={"ticket": t}).json()["estado"], "cancelada")

    def test_04_codigo_vencido_y_clave_corta(self):
        t = self.pedir()
        sid = self.ayuda.get("/api/auth/solicitudes").json()["items"][0]["id"]
        codigo = self.ayuda.post(f"/api/auth/solicitudes/{sid}/aprobar").json()["codigo"]
        self.assertEqual(self.anon.post("/api/auth/restablecer", json={"ticket": t, "codigo": codigo, "nueva": "corta"}).status_code, 422)
        with mock.patch.object(usuarios.time, "time", return_value=__import__("time").time() + usuarios.RESET_VIGENCIA_CODIGO + 5):
            self.assertEqual(self.anon.post("/api/auth/restablecer", json={"ticket": t, "codigo": codigo, "nueva": NUEVA}).status_code, 403)

    def test_05_correo_inexistente_responde_igual_y_no_crea_solicitud(self):
        r = self.anon.post("/api/auth/olvide", json={"email": "nadie@skyguardian.mx"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(set(r.json()), {"ticket", "vigencia_seg"})
        self.assertEqual(self.ayuda.get("/api/auth/solicitudes").json()["items"], [])

    def test_06_limite_de_solicitudes_por_equipo_y_sesion_obligatoria(self):
        for _ in range(usuarios.RESET_MAX_SOLICITUDES):
            self.pedir()
        self.assertEqual(self.anon.post("/api/auth/olvide", json={"email": OLVIDADA}).status_code, 429)
        self.assertEqual(cliente_sin_sesion(app).get("/api/auth/solicitudes").status_code, 401)
        self.assertEqual(cliente_sin_sesion(app).post("/api/auth/solicitudes/1/aprobar").status_code, 401)

    def test_07_rechazar_cancela_la_solicitud(self):
        t = self.pedir()
        sid = self.ayuda.get("/api/auth/solicitudes").json()["items"][0]["id"]
        self.assertEqual(self.ayuda.post(f"/api/auth/solicitudes/{sid}/rechazar").status_code, 200)
        self.assertEqual(self.anon.post("/api/auth/olvide/estado", json={"ticket": t}).json()["estado"], "cancelada")

    def test_08_cambiar_la_clave_cierra_las_sesiones_de_la_cuenta(self):
        viejo = cliente_sin_sesion(app)
        self.assertEqual(viejo.post("/api/auth/login", json={"email": OLVIDADA, "password": usuarios.CLAVE_INICIAL}).status_code, 200)
        t = self.pedir()
        sid = self.ayuda.get("/api/auth/solicitudes").json()["items"][0]["id"]
        codigo = self.ayuda.post(f"/api/auth/solicitudes/{sid}/aprobar").json()["codigo"]
        self.assertEqual(self.anon.post("/api/auth/restablecer", json={"ticket": t, "codigo": codigo, "nueva": NUEVA}).status_code, 200)
        self.assertEqual(viejo.get("/api/auth/yo").status_code, 401)


if __name__ == "__main__":
    unittest.main()
