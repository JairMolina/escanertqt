"""Versión visible (v1.1.1) y contador "MAC guardadas hoy" que suma a todos los operarios."""
import _aislamiento  # noqa: F401  (debe ser lo primero)
import sqlite3
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import settings
from app.database import db
from app.main import app

from _aislamiento import mac_unica, num_unico, verificar_aislamiento

RAIZ = Path(__file__).resolve().parent.parent
ESTATICO = RAIZ / "app" / "static"


class TestVersion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        verificar_aislamiento()
        db.init_db()
        cls.c = TestClient(app, base_url="https://testserver")

    def test_la_version_es_1_1_4_y_sale_del_servidor(self):
        self.assertEqual(settings.APP_VERSION, "1.3.27")
        self.assertEqual(self.c.get("/api/config").json()["version"], "1.3.27")
        self.assertEqual(self.c.get("/api/status").json()["version"], "1.3.27")

    def test_la_version_tiene_un_lugar_visible_en_cada_vista(self):
        common = (ESTATICO / "js" / "common.js").read_text(encoding="utf-8")
        self.assertIn("/api/config", common)                                  # única fuente: el servidor
        self.assertIn("'verpie'", common)                                     # pie de página en las pantallas móviles
        self.assertIn("data-version", (ESTATICO / "js" / "escritorio.js").read_text(encoding="utf-8"))   # barra lateral de la consola
        self.assertIn("data-version", (ESTATICO / "admin.html").read_text(encoding="utf-8"))
        self.assertIn("data-version", (ESTATICO / "dymo_preview.html").read_text(encoding="utf-8"))
        # nada de versión escrita a mano en el código de las páginas (evita que quede desactualizada)
        for f in list(ESTATICO.glob("*.html")) + list((ESTATICO / "js").glob("*.js")):
            if f.name in ("jsQR.js",) or "vendor" in f.parts:
                continue
            self.assertNotRegex(f.read_text(encoding="utf-8", errors="ignore"), r"Escáner TQT v1\.\d", f.name)

    def test_el_changelog_menciona_la_version(self):
        self.assertIn("1.1.1", (RAIZ / "CHANGELOG.md").read_text(encoding="utf-8"))


class TestMacsHoy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        verificar_aislamiento()
        db.init_db()
        cls.c = TestClient(app, base_url="https://testserver")

    def _placas(self, n):
        ids = []
        for _ in range(n):
            s = num_unico()
            self.c.post("/api/pcb/escanear", json={"codigo": f"TQT-R1-V30-{s}"})
            ids.append(f"TQT-R1-V30-{s}")
        self.c.post("/api/recepcion/confirmar", json={"ids": None})
        por_nombre = {p["nombre"]: p["id"] for p in self.c.get("/api/pcb", params={"limit": 1000}).json()["items"]}
        return [por_nombre[i] for i in ids]

    def hoy(self):
        return self.c.get("/api/programacion/hoy").json()["guardadas"]

    def test_cuenta_lo_de_todos_los_operarios_y_no_las_borradas(self):
        antes = self.hoy()
        a, b, c3 = self._placas(3)
        self.c.put(f"/api/pcb/{a}/programacion", json={"mac": mac_unica(), "operador": "Ana"})            # operador 1
        self.c.put(f"/api/pcb/{b}/mac", json={"mac": mac_unica(), "operador": "Luis"})                    # operador 2, otro equipo
        self.assertEqual(self.hoy(), antes + 2)
        self.c.post("/api/programacion/lote", json={"items": [{"pcb_id": c3, "mac": mac_unica()}], "operador": "Marta"})   # en lote
        self.assertEqual(self.hoy(), antes + 3)
        self.c.put(f"/api/pcb/{a}/mac", json={"mac": None})                                               # borrar una MAC no suma
        self.assertEqual(self.hoy(), antes + 3)
        self.c.post("/api/programacion/lote", json={"items": [{"pcb_id": b, "mac": mac_unica()}], "simular": True})       # simular no suma
        self.assertEqual(self.hoy(), antes + 3)

    def test_solo_cuenta_el_dia_de_hoy_en_hora_local(self):
        placa = self._placas(1)[0]
        self.c.put(f"/api/pcb/{placa}/mac", json={"mac": mac_unica()})
        antes = self.hoy()
        con = sqlite3.connect(settings.DB_PATH)
        try:   # el mismo evento, pero de ayer (hora local)
            con.execute("INSERT INTO escaneos (evento, valor, detalle, creado_en) VALUES ('MAC_GUARDADA', 'x', '02:00:00:00:00:99', datetime('now','-1 day'))")
            con.commit()
        finally:
            con.close()
        self.assertEqual(self.hoy(), antes)


if __name__ == "__main__":
    unittest.main()
