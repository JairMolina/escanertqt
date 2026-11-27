import _aislamiento  # noqa: F401  (debe ser lo primero)
"""Parejas Skudo AntiJammer (v1.4.104): RX + TX unidas por número; se forman solas al programar o a mano en Emparejar."""
import unittest

from app.database import db
from app.main import app
from app.services import antijammer_etiqueta as etq
from app.services import antijammer_parejas as ps
from app.services import usuarios

from _aislamiento import cliente_sin_sesion, verificar_aislamiento


class TestAntijammerParejas(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        verificar_aislamiento()
        db.init_db()
        usuarios.sembrar(iteraciones=1000)
        usuarios.limitador.reiniciar()
        cls.sin = cliente_sin_sesion(app)
        cls.c = cliente_sin_sesion(app)
        r = cls.c.post("/api/auth/login", json={"email": "developer@skyguardian.mx", "password": usuarios.CLAVE_INICIAL})
        assert r.status_code == 200, r.text
        cls.id = {}
        for s in ("7101", "7102", "7103", "7104", "7105", "7110", "7120", "7130", "7140", "7141", "7142", "7143"):
            r = cls.c.post("/api/antijammer/pcb/manual", json={"version": "1", "serie": s})
            assert r.status_code == 201
            cls.id[s] = r.json()["pcb"]["id"]

    def _sueltas(self):
        return {p["nombre"] for p in self.c.get("/api/antijammer/parejas").json()["sin_pareja"]}

    def _par(self, numero):
        return next((p for p in self.c.get("/api/antijammer/parejas").json()["parejas"] if p["numero"] == numero), None)

    def _prog(self, serie, **extra):
        return self.c.put(f"/api/antijammer/pcb/{self.id[serie]}/firmware", json={"firmware": "AJ-1.0", **extra})

    def test_01_sin_sesion(self):
        self.assertIn(self.sin.get("/api/antijammer/parejas").status_code, (401, 403))

    def test_02_manual_con_numero_y_reglas(self):
        r = self.c.post("/api/antijammer/parejas", json={"rx": "SJ-V1-7101", "tx": "7102", "numero": 40})
        self.assertEqual(r.status_code, 201, r.text)
        par = self._par(40)
        self.assertEqual((par["rx"]["nombre"], par["tx"]["nombre"], par["completa"]), ("SJ-V1-7101", "SJ-V1-7102", True))
        self.assertNotIn("SJ-V1-7101", self._sueltas())
        self.assertEqual((etq.datos_de("SJ-V1-7101")["tipo"], etq.datos_de("SJ-V1-7102")["tipo"]), ("RX", "TX"))
        # placa en otra pareja, misma placa, ajena, inexistente, número ocupado o fuera de rango
        self.assertEqual(self.c.post("/api/antijammer/parejas", json={"rx": "7101", "tx": "7103"}).status_code, 409)
        self.assertEqual(self.c.post("/api/antijammer/parejas", json={"rx": "7103", "tx": "7103"}).status_code, 422)
        self.assertEqual(self.c.post("/api/antijammer/parejas", json={"rx": "7103", "tx": "TPMS_V1_0004"}).status_code, 404)
        self.assertEqual(self.c.post("/api/antijammer/parejas", json={"rx": "7103", "tx": "SJ-V1-9988"}).status_code, 404)
        self.assertEqual(self.c.post("/api/antijammer/parejas", json={"rx": "7103", "tx": "7104", "numero": 40}).status_code, 409)
        self.assertEqual(self.c.post("/api/antijammer/parejas", json={"rx": "7103", "tx": "7104", "numero": 0}).status_code, 422)
        # sin número = el siguiente libre
        # (otros módulos de la suite pueden dejar parejas en la BD de prueba: el siguiente es el máximo + 1)
        d = self.c.get("/api/antijammer/parejas").json()
        sig = max(p["numero"] for p in d["parejas"]) + 1
        self.assertEqual(d["siguiente"], sig)
        r = self.c.post("/api/antijammer/parejas", json={"rx": "7103", "tx": "7104"})
        self.assertEqual(r.json()["numero"], sig)
        type(self).auto = sig
        # deshacer: vuelven a estar sueltas, sin número y con su RX/TX
        pid = self._par(40)["id"]
        self.assertEqual(self.c.delete(f"/api/antijammer/parejas/{pid}").status_code, 200)
        self.assertTrue({"SJ-V1-7101", "SJ-V1-7102"} <= self._sueltas())
        self.assertIsNone(ps.de_placa(self.id["7101"]))
        self.assertEqual(self.c.delete(f"/api/antijammer/parejas/{pid}").status_code, 404)
        ev = self.c.get("/api/antijammer/pcb/por-codigo", params={"codigo": "SJ-V1-7101"}).json()["eventos"]
        self.assertTrue({"emparejada", "desemparejada"} <= {e["accion"] for e in ev})

    def test_03_al_programar_se_empareja_solo(self):
        # RX 7110 con el número 8: pareja incompleta
        r = self._prog("7110", tipo="RX", pareja=8)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["pcb"]["firmware"], "AJ-1.0")
        self.assertEqual((r.json()["pareja"]["numero"], r.json()["pareja"]["completa"]), (8, False))
        self.assertNotIn("SJ-V1-7110", self._sueltas())
        self.assertEqual(self.c.get("/api/antijammer/pcb/por-codigo", params={"codigo": "7110"}).json()["pareja"],
                         {"numero": 8, "tipo": "RX", "socio": None})
        # otra RX con el 8 choca y no guarda el firmware
        r = self._prog("7130", tipo="RX", pareja=8)
        self.assertEqual(r.status_code, 409, r.text)
        self.assertIsNone(self.c.get("/api/antijammer/pcb/por-codigo", params={"codigo": "7130"}).json()["pcb"]["firmware"])
        self.assertEqual(self._prog("7130", pareja=8).status_code, 422)   # número sin RX/TX
        # TX 7120 con el 8: la pareja queda completa
        r = self._prog("7120", tipo="TX", pareja=8)
        self.assertTrue(r.json()["pareja"]["completa"])
        par = self._par(8)
        self.assertEqual((par["rx"]["nombre"], par["tx"]["nombre"]), ("SJ-V1-7110", "SJ-V1-7120"))
        self.assertEqual(etq.datos_de("SJ-V1-7120")["tipo"], "TX")
        # reprogramar la TX con otro número la cambia de pareja (lo programado manda)
        self._prog("7120", tipo="TX", pareja=9)
        self.assertIsNone(self._par(8)["tx"])
        self.assertEqual(self._par(9)["tx"]["nombre"], "SJ-V1-7120")
        # solo tipo: va a Materiales sin número
        self.assertEqual(self._prog("7130", tipo="TX").json()["pareja"], None)
        self.assertEqual(next(p for p in self.c.get("/api/antijammer/parejas").json()["sin_pareja"] if p["nombre"] == "SJ-V1-7130")["tipo"], "TX")
        # completar a mano la incompleta 8 con la 7130
        r = self.c.post("/api/antijammer/parejas", json={"rx": "7110", "tx": "7130", "numero": 8})
        self.assertEqual(r.status_code, 201, r.text)
        self.assertTrue(self._par(8)["completa"])

    def test_04_filtro_mes_placa_eliminada_y_migracion(self):
        d = self.c.get("/api/antijammer/parejas").json()
        self.assertTrue(d["meses"])
        vacio = self.c.get("/api/antijammer/parejas", params={"mes": "1999-01"}).json()
        self.assertEqual((vacio["parejas"], vacio["sin_pareja"]), ([], []))
        self.assertEqual(self.c.get("/api/antijammer/parejas", params={"mes": "mal"}).status_code, 422)
        par = self._par(self.auto)
        self.assertEqual(self.c.delete(f"/api/antijammer/pcb/{par['tx']['id']}").status_code, 200)
        self.assertIsNone(self._par(self.auto)["tx"])   # la pareja pierde su lado y queda incompleta
        # tabla de 1.4.103 (sin número): cada pareja toma su id como número
        with db.transaction() as c:
            c.execute("ALTER TABLE antijammer_parejas RENAME TO _bk")
            c.execute("CREATE TABLE antijammer_parejas(id INTEGER PRIMARY KEY AUTOINCREMENT, rx_id INTEGER NOT NULL UNIQUE, "
                      "tx_id INTEGER NOT NULL UNIQUE, operador TEXT, creada_en TEXT NOT NULL DEFAULT (datetime('now','localtime')))")
            c.execute("INSERT INTO antijammer_parejas(id, rx_id, tx_id) VALUES (500, ?, ?)", (self.id["7101"], self.id["7102"]))
        try:
            self.assertEqual((self._par(500)["rx"]["nombre"], self._par(500)["tx"]["nombre"]), ("SJ-V1-7101", "SJ-V1-7102"))
        finally:
            with db.transaction() as c:
                c.execute("DROP TABLE antijammer_parejas")
                c.execute("ALTER TABLE _bk RENAME TO antijammer_parejas")

    def test_05_cambiar_numero_a_mano(self):
        """v1.4.105: el número de una pareja se edita a mano; si choca 409, si complementa a una incompleta se unen."""
        r = self.c.post("/api/antijammer/parejas", json={"rx": "7140", "tx": "7141", "numero": 70})
        self.assertEqual(r.status_code, 201, r.text)
        pid = r.json()["id"]
        self.assertIn(self.sin.put(f"/api/antijammer/parejas/{pid}", json={"numero": 71}).status_code, (401, 403))
        r = self.c.put(f"/api/antijammer/parejas/{pid}", json={"numero": 71})
        self.assertEqual((r.status_code, r.json()["numero"]), (200, 71), r.text)
        self.assertIsNone(self._par(70))
        self.assertEqual((self._par(71)["rx"]["nombre"], self._par(71)["tx"]["nombre"]), ("SJ-V1-7140", "SJ-V1-7141"))
        self.assertEqual(ps.de_placa(self.id["7141"])["numero"], 71)   # la etiqueta toma el nuevo número
        # mismo número: sin cambio; fuera de rango; inexistente; ocupado por una pareja completa
        self.assertEqual(self.c.put(f"/api/antijammer/parejas/{pid}", json={"numero": 71}).status_code, 200)
        self.assertEqual(self.c.put(f"/api/antijammer/parejas/{pid}", json={"numero": 0}).status_code, 422)
        self.assertEqual(self.c.put("/api/antijammer/parejas/999999", json={"numero": 5}).status_code, 404)
        otra = self.c.post("/api/antijammer/parejas", json={"rx": "7142", "tx": "7143", "numero": 72})
        self.assertEqual(otra.status_code, 201, otra.text)
        self.assertEqual(self.c.put(f"/api/antijammer/parejas/{pid}", json={"numero": 72}).status_code, 409)
        self.assertEqual(self._par(71)["rx"]["nombre"], "SJ-V1-7140")   # nada cambió
        # una incompleta solo-RX y otra solo-TX: renumerar una al número de la otra las une
        self.c.delete(f"/api/antijammer/parejas/{otra.json()['id']}")
        rx = self._prog("7142", tipo="RX", pareja=80)
        tx = self._prog("7143", tipo="TX", pareja=81)
        self.assertEqual((rx.status_code, tx.status_code), (200, 200), rx.text + tx.text)
        r = self.c.put(f"/api/antijammer/parejas/{self._par(81)['id']}", json={"numero": 80})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIsNone(self._par(81))
        par = self._par(80)
        self.assertEqual((par["rx"]["nombre"], par["tx"]["nombre"], par["completa"]), ("SJ-V1-7142", "SJ-V1-7143", True))


if __name__ == "__main__":
    unittest.main()
