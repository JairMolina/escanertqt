"""v1.4.89: /api/plataforma/admin (pestaña Módulos del Centro): doble candado, forma de las respuestas y borrado con respaldo."""
import _aislamiento  # noqa: F401  (debe ser lo primero)
import os
import unittest
from unittest import mock

from app.config import settings
from app.database import db
from app.main import app
from app.services import admin_auth, caiquen, usuarios

from _aislamiento import cliente_sin_sesion, crear_par, nuevo_lote, verificar_aislamiento

CLAVE = "ClaveModulos-12345"
ADMIN = "developer@skyguardian.mx"
OTRA = "developer6@skyguardian.mx"
BASE = "/api/plataforma/admin"


class TestPlataformaAdmin(unittest.TestCase):
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

    def entrar(self, email):
        c = cliente_sin_sesion(app)
        self.assertEqual(c.post("/api/auth/login", json={"email": email, "password": usuarios.CLAVE_INICIAL}).status_code, 200)
        return c

    def token(self, c):
        r = c.post("/api/admin/login", json={"password": CLAVE})
        self.assertEqual(r.status_code, 200, r.text)
        return {"X-Admin-Token": r.json()["token"]}

    def test_sin_sesion_sin_rol_o_sin_token(self):
        anon = cliente_sin_sesion(app)
        self.assertEqual(anon.get(f"{BASE}/modulos").status_code, 401)
        c = self.entrar(ADMIN)
        # rol admin pero sin token: el listado de módulos va, el de datos y el borrado no
        self.assertEqual(c.get(f"{BASE}/modulos").status_code, 200)
        self.assertEqual(c.get(f"{BASE}/modulos/escaner-tqt/colecciones/pcb").status_code, 401)
        self.assertEqual(c.request("DELETE", f"{BASE}/modulos/escaner-tqt/colecciones/pcb", json={"ids": [1]}).status_code, 401)
        # token válido pero cuenta sin rol administrador
        h = self.token(c)
        g = self.entrar(OTRA)
        usuarios.actualizar_cuenta(OTRA, rol="general", modulos=["escaner-tqt"])
        self.assertEqual(g.get(f"{BASE}/modulos").status_code, 403)
        self.assertEqual(g.get(f"{BASE}/modulos/escaner-tqt/colecciones/pcb", headers=h).status_code, 403)
        self.assertEqual(g.request("DELETE", f"{BASE}/modulos/escaner-tqt/colecciones/pcb", json={"ids": [1]}, headers=h).status_code, 403)

    def test_404_y_validaciones(self):
        c = self.entrar(ADMIN)
        h = self.token(c)
        self.assertEqual(c.get(f"{BASE}/modulos/nada/colecciones/pcb", headers=h).status_code, 404)
        self.assertEqual(c.get(f"{BASE}/modulos/escaner-tqt/colecciones/nada", headers=h).status_code, 404)
        self.assertEqual(c.get(f"{BASE}/modulos/documentacion-hw/colecciones/pcb", headers=h).status_code, 404)
        self.assertEqual(c.get(f"{BASE}/modulos/escaner-tqt/colecciones/pcb", params={"limit": 501}, headers=h).status_code, 422)
        d = lambda ids: c.request("DELETE", f"{BASE}/modulos/escaner-tqt/colecciones/pcb", json={"ids": ids}, headers=h)
        self.assertEqual(d(list(range(1, 502))).status_code, 422)
        self.assertEqual(d([]).status_code, 422)
        self.assertEqual(d([99999999]).status_code, 404)

    def test_forma_de_modulos_y_colecciones(self):
        lote = nuevo_lote()
        t = crear_par(lote["id"], r3=True)
        c = self.entrar(ADMIN)
        h = self.token(c)
        mods = {m["id"]: m for m in c.get(f"{BASE}/modulos").json()}
        self.assertEqual(mods["documentacion-hw"]["colecciones"], [])
        self.assertEqual({x["id"] for x in mods["escaner-tqt"]["colecciones"]}, {"tarjetas", "pcb"})
        self.assertIs(mods["tpms"]["vaciar"], False)
        r = c.get(f"{BASE}/modulos/escaner-tqt/colecciones/tarjetas", params={"q": str(t["id_tarjeta_num"])}, headers=h).json()
        self.assertEqual([x["k"] for x in r["columnas"]], ["tarjeta", "r1", "r2", "r3", "estado"])
        self.assertTrue(any(i["id"] == t["id"] for i in r["items"]))
        self.assertGreaterEqual(r["total"], 1)
        p = c.get(f"{BASE}/modulos/escaner-tqt/colecciones/pcb", params={"limit": 5}, headers=h).json()
        self.assertEqual([x["k"] for x in p["columnas"]], ["tipo", "nombre", "mac", "estado", "tarjeta"])
        self.assertLessEqual(len(p["items"]), 5)
        self.assertGreaterEqual(p["total"], 3)
        for mid, col in (("impresora", "activos"), ("caiquen", "placas"), ("skudo-antijammer", "placas"), ("skudo-sigfox", "placas"),
                         ("tpms", "placas"), ("speedlocker", "placas")):
            j = c.get(f"{BASE}/modulos/{mid}/colecciones/{col}", headers=h)
            self.assertEqual(j.status_code, 200, (mid, j.text))
            self.assertTrue({"columnas", "items", "total"} <= set(j.json()))

    def test_borrado_con_respaldo(self):
        lote = nuevo_lote()
        a, b = crear_par(lote["id"]), crear_par(lote["id"])
        c = self.entrar(ADMIN)
        h = self.token(c)
        r = c.request("DELETE", f"{BASE}/modulos/escaner-tqt/colecciones/tarjetas", json={"ids": [a["id"]]}, headers=h)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["eliminados"], 1)
        self.assertTrue((settings.BACKUP_DIR / r.json()["respaldo"]).exists())
        ids = [x["id"] for x in c.get(f"{BASE}/modulos/escaner-tqt/colecciones/tarjetas", params={"limit": 500}, headers=h).json()["items"]]
        self.assertNotIn(a["id"], ids)
        self.assertIn(b["id"], ids)
        # placas de un módulo
        pl = caiquen.alta_manual("1", "7771", "L-ADM", "t")
        r = c.request("DELETE", f"{BASE}/modulos/caiquen/colecciones/placas", json={"ids": [pl["id"]]}, headers=h)
        self.assertEqual((r.status_code, r.json()["eliminados"]), (200, 1), r.text)
        self.assertTrue((settings.BACKUP_DIR / r.json()["respaldo"]).exists())


if __name__ == "__main__":
    unittest.main()
