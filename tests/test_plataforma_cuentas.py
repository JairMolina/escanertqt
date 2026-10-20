"""v1.4.12: cuentas por módulo desde el núcleo del portal (/api/plataforma/*, solo administradores con sesión normal)."""
import _aislamiento  # noqa: F401  (debe ser lo primero)
import unittest

from app.database import db
from app.main import app
from app.services import usuarios

from _aislamiento import cliente_sin_sesion, verificar_aislamiento

ADMIN = "developer@skyguardian.mx"
OTRA = "developer6@skyguardian.mx"


class TestPlataformaCuentas(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        verificar_aislamiento()
        db.init_db()
        usuarios.sembrar(iteraciones=1000)

    def setUp(self):
        usuarios.limitador.reiniciar()
        usuarios.actualizar_cuenta(ADMIN, rol="administrador")
        usuarios.actualizar_cuenta(OTRA, rol="general", modulos=["escaner-tqt"])
        self.addCleanup(usuarios.actualizar_cuenta, OTRA, "administrador", None, None, ["escaner-tqt"])

    def entrar(self, email):
        c = cliente_sin_sesion(app)
        self.assertEqual(c.post("/api/auth/login", json={"email": email, "password": usuarios.CLAVE_INICIAL}).status_code, 200)
        return c

    def test_sin_sesion_y_no_admin_no_entran(self):
        self.assertEqual(cliente_sin_sesion(app).get("/api/plataforma/cuentas").status_code, 401)
        self.assertEqual(self.entrar(OTRA).get("/api/plataforma/cuentas").status_code, 403)

    def test_admin_lista_y_asigna_modulos_y_rol(self):
        c = self.entrar(ADMIN)
        d = c.get("/api/plataforma/cuentas").json()
        self.assertEqual(len(d["modulos"]), 7)
        self.assertIn(OTRA, {x["email"] for x in d["cuentas"]})
        d = c.patch(f"/api/plataforma/cuentas/{OTRA}", json={"rol": "consultor", "modulos": ["tpms", "caiquen"]}).json()
        fila = next(x for x in d["cuentas"] if x["email"] == OTRA)
        self.assertEqual((fila["rol"], fila["modulos"]), ("consultor", ["tpms", "caiquen"]))
        self.assertEqual(c.patch(f"/api/plataforma/cuentas/{OTRA}", json={"modulos": ["nada"]}).status_code, 422)

    def test_dar_y_quitar_un_modulo_a_todos(self):
        c = self.entrar(ADMIN)
        d = c.post("/api/plataforma/modulos/tpms/todos", json={"activo": True}).json()
        self.assertTrue(all("tpms" in x["modulos"] for x in d["cuentas"] if x["rol"] != "administrador"))
        d = c.post("/api/plataforma/modulos/tpms/todos", json={"activo": False}).json()
        self.assertFalse(any("tpms" in x["modulos"] for x in d["cuentas"] if x["rol"] != "administrador"))
        self.assertEqual(c.post("/api/plataforma/modulos/nada/todos", json={"activo": True}).status_code, 404)

    def _sin_cambio_pendiente(self, email, valor=0):
        with db.transaction() as cx:
            cx.execute("UPDATE usuarios SET debe_cambiar = ? WHERE email = ?", (valor, email))

    def test_ingreso_desde_el_nucleo_solo_para_administradores(self):
        """v1.4.13: el núcleo pide credenciales; solo un administrador obtiene sesión."""
        self._sin_cambio_pendiente(ADMIN); self.addCleanup(self._sin_cambio_pendiente, ADMIN, 1)
        self._sin_cambio_pendiente(OTRA); self.addCleanup(self._sin_cambio_pendiente, OTRA, 1)
        c = cliente_sin_sesion(app)
        self.assertEqual(c.post("/api/plataforma/entrar", json={"email": ADMIN, "password": "mala-clave-123"}).status_code, 401)
        r = c.post("/api/plataforma/entrar", json={"email": OTRA, "password": usuarios.CLAVE_INICIAL})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(c.get("/api/auth/yo").status_code, 401)            # la cuenta general no quedó con sesión
        r = c.post("/api/plataforma/entrar", json={"email": ADMIN, "password": usuarios.CLAVE_INICIAL})
        self.assertEqual((r.status_code, r.json()["rol"]), (200, "administrador"))
        self.assertEqual(c.get("/api/plataforma/cuentas").status_code, 200)

    def test_ingreso_con_cambio_de_clave_pendiente_va_al_login(self):
        self._sin_cambio_pendiente(ADMIN, 1)
        r = cliente_sin_sesion(app).post("/api/plataforma/entrar", json={"email": ADMIN, "password": usuarios.CLAVE_INICIAL})
        self.assertEqual(r.status_code, 409)

    def test_portal_marca_el_equipo_para_el_limite_de_intentos(self):
        self.assertIn("tqt_cid", cliente_sin_sesion(app).get("/inicio").headers.get("set-cookie", ""))


if __name__ == "__main__":
    unittest.main()
