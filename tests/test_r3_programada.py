"""v1.3.44: la R3 se programa (lleva firmware) pero no lleva MAC. Programada (R3) = con firmware."""
import _aislamiento  # noqa: F401  (debe ser lo primero)
import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.database import db
from app.database import inventario as inv
from app.main import app
from app.services import usuarios

from _aislamiento import cliente_sin_sesion, mac_unica, num_unico, verificar_aislamiento

ADMIN = "developer@skyguardian.mx"
JS = Path(__file__).resolve().parent.parent / "app" / "static" / "js"


class TestR3Programada(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        verificar_aislamiento()
        db.init_db()
        usuarios.sembrar(iteraciones=1000)

    def setUp(self):
        self.c = cliente_sin_sesion(app)
        self.c.cookies.set(usuarios.COOKIE, usuarios.emitir_sesion(ADMIN))
        self.n = num_unico()
        for t in ("R1", "R3"):
            r = self.c.post("/api/pcb/escanear", json={"codigo": f"TQT-{t}-V30-{self.n}"})
            self.assertEqual(r.json()["resultado"], "AGREGADA", r.text)
        items = self.c.get("/api/pcb", params={"q": self.n, "limit": 100}).json()["items"]
        self.ids = {p["nombre"]: p["id"] for p in items}
        self.r3 = self.ids[f"TQT-R3-V30-{self.n}"]
        self.r1 = self.ids[f"TQT-R1-V30-{self.n}"]

    def test_01_r3_acepta_firmware_y_rechaza_mac(self):
        r = self.c.put(f"/api/pcb/{self.r3}/firmware", json={"firmware": "1.3"})
        self.assertEqual((r.status_code, r.json()["firmware"], r.json()["mac"]), (200, "1.3", None))
        self.assertIn("1.3", self.c.get("/api/firmware").json()["R3"])        # la versión nueva entra al catálogo de R3
        self.assertEqual(self.c.put(f"/api/pcb/{self.r3}/mac", json={"mac": mac_unica()}).status_code, 400)
        self.assertEqual(self.c.put(f"/api/pcb/{self.r3}/programacion", json={"mac": mac_unica(), "firmware": "1.3"}).status_code, 400)
        self.assertEqual(self.c.put(f"/api/pcb/{self.r3}/firmware", json={"firmware": "<x>"}).status_code, 400)
        self.assertIsNone(self.c.put(f"/api/pcb/{self.r3}/firmware", json={"firmware": None}).json()["firmware"])

    def test_02_lote_rechaza_r3_y_catalogo_r3(self):
        res = inv.programar_lote([{"nombre": f"TQT-R3-V30-{self.n}", "mac": mac_unica(), "firmware": "1"}], simular=True)
        self.assertEqual(res["fallidas"], 1)
        cat = self.c.post("/api/firmware", json={"rol": "R3", "version": "9.9"}).json()
        self.assertIn("9.9", cat["R3"])
        self.assertEqual(self.c.post("/api/firmware", json={"rol": "R4", "version": "1"}).status_code, 400)
        self.assertNotIn("9.9", self.c.delete("/api/firmware/R3/9.9").json()["R3"])

    def test_03_filtro_sin_firmware_y_tarjeta_con_firmware_r3(self):
        q = {"tipo": "R3", "sin_firmware": 1, "limit": 5000}
        pend = {p["id"] for p in self.c.get("/api/pcb", params=q).json()["items"]}
        self.assertIn(self.r3, pend)
        self.c.put(f"/api/pcb/{self.r3}/firmware", json={"firmware": "1.0"})
        pend = {p["id"] for p in self.c.get("/api/pcb", params=q).json()["items"]}
        self.assertNotIn(self.r3, pend)
        self.c.post("/api/recepcion/confirmar", json={"ids": [self.r1, self.r3]})
        t = self.c.post("/api/tarjetas", json={"r1_id": self.r1, "r3_id": self.r3})
        self.assertEqual(t.status_code, 201, t.text)
        t = self.c.get(f"/api/tarjetas/{t.json()['id']}").json()
        self.assertEqual((t["r3"]["firmware"], t["r3"]["mac"]), ("1.0", None))
        j = self.c.get("/api/consulta", params={"codigo": f"TQT-R3-V30-{self.n}"}).json()
        self.assertEqual(j["tarjeta"]["r3"]["firmware"], "1.0")

    def test_04_migracion_catalogo_antiguo_acepta_r3(self):
        with tempfile.TemporaryDirectory() as d:
            ruta = Path(d) / "vieja.db"
            db.init_db(ruta)
            con = sqlite3.connect(ruta)
            con.executescript("DROP TABLE firmware_catalogo; CREATE TABLE firmware_catalogo (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                              "rol TEXT NOT NULL CHECK (rol IN ('R1','R2')), version TEXT NOT NULL, orden INTEGER NOT NULL DEFAULT 0, "
                              "UNIQUE (rol, version)); INSERT INTO firmware_catalogo (rol, version, orden) VALUES ('R1','4.1',1);")
            con.close()
            db.init_db(ruta)
            self.assertEqual(inv.listar_firmware(db_path=ruta), {"R1": ["4.1"], "R2": [], "R3": []})
            self.assertIn("1.0", inv.agregar_firmware("R3", "1.0", db_path=ruta)["R3"])

    def test_05_frontend(self):
        com = (JS / "common.js").read_text(encoding="utf-8")
        self.assertIn("(p.tipo === 'R3' || !!p.mac)", com)                     # R3 programada = con firmware
        for f in ("consultar.js", "escritorio.js", "programar.js", "sec_macs.js", "sec_inventario.js", "sec_resumen.js"):
            self.assertNotIn("no lleva MAC ni firmware", (JS / f).read_text(encoding="utf-8"), f)
        macs = (JS / "sec_macs.js").read_text(encoding="utf-8")
        self.assertIn("crearFilaR3", macs)
        self.assertIn("'R3 firmware '", macs)
        prog = (JS / "programar.js").read_text(encoding="utf-8")
        self.assertIn("sin_firmware=1", prog)
        self.assertIn("/firmware`", prog)


if __name__ == "__main__":
    unittest.main()
