import _aislamiento  # noqa: F401  (debe ser lo primero)
"""v1.4.24: cada usuario trabaja en su lote y las placas recibidas guardan el lote en el que entraron."""
import unittest

from app.database import db
from app.main import app
from app.services import usuarios

from _aislamiento import cliente_sin_sesion, verificar_aislamiento


def entrar(email):
    c = cliente_sin_sesion(app)
    r = c.post("/api/auth/login", json={"email": email, "password": usuarios.CLAVE_INICIAL})
    assert r.status_code == 200, r.text
    return c


class TestLotePorUsuario(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        verificar_aislamiento()
        db.init_db()
        usuarios.sembrar(iteraciones=1000)

    def setUp(self):
        usuarios.limitador.reiniciar()
        self.a, self.b = entrar("developer@skyguardian.mx"), entrar("developer4@skyguardian.mx")

    def lote_de(self, c):
        return c.get("/api/status").json()["active_lote"]["id"]

    def test_cambiar_de_lote_no_afecta_a_otro_usuario(self):
        global_antes = db.get_active_lote()["id"]
        b_antes = self.lote_de(self.b)
        r = self.a.post("/api/lotes", json={"tipo_lote": "dia", "fecha_inicio": "2026-10-21", "activo": True})
        self.assertEqual(r.status_code, 201, r.text)
        nuevo = r.json()["id"]
        self.assertEqual(self.lote_de(self.a), nuevo)
        self.assertEqual(self.lote_de(self.b), b_antes)            # B sigue en su lote
        self.assertEqual(db.get_active_lote()["id"], global_antes)  # el global no se movió
        activos = [l["id"] for l in self.a.get("/api/lotes").json() if l["activo"]]
        self.assertEqual(activos, [nuevo])                          # «Activo» en la lista = lote de A
        self.assertEqual(self.b.post(f"/api/lotes/{nuevo}/activar").status_code, 200)
        self.assertEqual(self.lote_de(self.b), nuevo)
        self.assertEqual(self.a.post(f"/api/lotes/{global_antes}/activar").status_code, 200)
        self.assertEqual((self.lote_de(self.a), self.lote_de(self.b)), (global_antes, nuevo))

    def test_recibida_guarda_el_lote_del_usuario(self):
        r = self.a.post("/api/lotes", json={"tipo_lote": "dia", "fecha_inicio": "2026-10-22", "activo": True})
        self.assertEqual(r.status_code, 201, r.text)
        lote = r.json()["id"]
        e = self.a.post("/api/pcb/escanear", json={"codigo": "TQT_R2_0951"}).json()
        self.assertEqual(e["resultado"], "AGREGADA", e)
        self.assertEqual(e["pcb"]["recibida_lote_id"], lote)
        m = self.a.post("/api/pcb/manual", json={"tipo": "R1", "version": "10", "serie": "0951"}).json()
        self.assertEqual(m["pcbs"][0]["recibida_lote_id"], lote)
        nombres = {p["nombre"] for p in self.a.get(f"/api/pcb?lote_id={lote}").json()["items"]}
        self.assertEqual(nombres, {"TQT-R2-V10-0951", "TQT-R1-V10-0951"})


if __name__ == "__main__":
    unittest.main()
