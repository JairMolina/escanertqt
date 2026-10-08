"""Consultar (ficha por etiqueta/QR/MAC), R3 sin MAC pero con firmware, y que Pruebas ya no exista como URL."""
import _aislamiento  # noqa: F401  (debe ser lo primero)
import sqlite3
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.database import db
from app.main import app

from _aislamiento import mac_unica, num_unico, verificar_aislamiento

ETIQUETA = "TQT-R1-V30-{a}\n{m1}\nTQT-R2-V30-{b}\n{m2}"
RAIZ = Path(__file__).resolve().parent.parent


class TestConsulta(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        verificar_aislamiento()
        db.init_db()
        cls.c = TestClient(app, base_url="https://testserver")
        cls.a, cls.b = num_unico(), num_unico()          # tarjeta "impar": R1 de una serie, R2 de otra
        # MAC únicas: la BD de pruebas es compartida entre módulos
        cls.mac1, cls.mac2 = mac_unica().upper(), mac_unica().upper()
        for t, n in (("R1", cls.a), ("R2", cls.b), ("R3", cls.a)):
            assert cls.c.post("/api/pcb/escanear", json={"codigo": f"TQT-{t}-V30-{n}"}).json()["resultado"] == "AGREGADA"
        cls.c.post("/api/recepcion/confirmar", json={"ids": None})
        ids = {p["nombre"]: p["id"] for p in cls.c.get("/api/pcb", params={"limit": 1000}).json()["items"]}
        cls.ids = ids
        t = cls.c.post("/api/tarjetas", json={"r1_id": ids[f"TQT-R1-V30-{cls.a}"], "r2_id": ids[f"TQT-R2-V30-{cls.b}"],
                                              "r3_id": ids[f"TQT-R3-V30-{cls.a}"]})
        assert t.status_code == 201, t.text
        cls.t = t.json()

    def mac(self, nombre, mac):
        return self.c.put(f"/api/pcb/{self.ids[nombre]}/mac", json={"mac": mac})

    def programar_todo(self):
        self.mac(f"TQT-R1-V30-{self.a}", self.mac1)
        self.mac(f"TQT-R2-V30-{self.b}", self.mac2)

    def test_01_r1_y_r2_llevan_mac_unica_y_la_r3_no(self):
        self.assertEqual(self.mac(f"TQT-R1-V30-{self.a}", self.mac1.replace(":", "").lower()).json()["mac"], self.mac1)
        self.assertEqual(self.mac(f"TQT-R2-V30-{self.b}", self.mac2.replace(":", "-").lower()).json()["mac"], self.mac2)
        self.assertEqual(self.mac(f"TQT-R3-V30-{self.a}", mac_unica()).status_code, 400)      # la R3 no lleva MAC
        self.assertEqual(self.mac(f"TQT-R2-V30-{self.b}", self.mac1).status_code, 409)         # MAC de la R1

    def test_02_firmware_solo_r1_y_r2_y_viaja_con_la_placa(self):
        r = self.c.patch(f"/api/tarjetas/{self.t['id']}", json={"firmware_r1": "4.1", "firmware_r2": "2.1"})
        self.assertEqual(r.status_code, 200, r.text)
        t = self.c.get(f"/api/tarjetas/{self.t['id']}").json()
        self.assertEqual([t["r1"]["firmware"], t["r2"]["firmware"], t["r3"].get("firmware")], ["4.1", "2.1", None])
        # el firmware es de la PCB: se guarda también con la programación (MAC + firmware); la R3 también lleva firmware (v1.3.44)
        p1 = self.c.put(f"/api/pcb/{self.ids[f'TQT-R1-V30-{self.a}']}/programacion", json={"mac": self.mac1, "firmware": "4.2"})
        self.assertEqual((p1.status_code, p1.json()["firmware"]), (200, "4.2"))
        self.assertEqual(self.c.get(f"/api/tarjetas/{self.t['id']}").json()["firmware_r1"], "4.2")
        r3 = self.c.put(f"/api/pcb/{self.ids[f'TQT-R3-V30-{self.a}']}/firmware", json={"firmware": "1.0"})
        self.assertEqual((r3.status_code, r3.json()["firmware"]), (200, "1.0"))
        self.assertEqual(self.c.put(f"/api/pcb/{self.ids[f'TQT-R1-V30-{self.a}']}/firmware", json={"firmware": "<b>x</b>"}).status_code, 400)
        self.assertEqual(self.c.patch(f"/api/tarjetas/{self.t['id']}", json={"firmware_r1": "x" * 41}).status_code, 422)

    def test_02b_catalogo_de_firmware_como_el_excel(self):
        cat = self.c.get("/api/firmware").json()
        for v in ("2", "3.2", "3.3", "4.0", "4.1", "4.2"):
            self.assertIn(v, cat["R1"])
        for v in ("2", "2.1"):
            self.assertIn(v, cat["R2"])
        self.c.put(f"/api/pcb/{self.ids[f'TQT-R2-V30-{self.b}']}/firmware", json={"firmware": "2.9-beta"})
        self.assertIn("2.9-beta", self.c.get("/api/firmware").json()["R2"])         # una versión nueva entra al catálogo sola
        self.assertEqual(self.c.post("/api/firmware", json={"rol": "R4", "version": "1"}).status_code, 400)
        self.assertIn("1", self.c.post("/api/firmware", json={"rol": "R3", "version": "1"}).json()["R3"])

    def test_03_etiqueta_de_4_lineas_devuelve_la_ficha_completa(self):
        self.programar_todo()
        etiqueta = ETIQUETA.format(a=self.a, b=self.b, m1=self.mac1.lower(), m2=self.mac2.lower())
        j = self.c.get("/api/consulta", params={"codigo": etiqueta}).json()
        self.assertEqual((j["origen"], j["avisos"]), ("etiqueta", []))
        t = j["tarjeta"]
        self.assertEqual(t["id_tarjeta_num"], self.a)
        self.assertEqual([(t[s]["nombre"], t[s]["version"], t[s]["mac"]) for s in ("r1", "r2", "r3")],
                         [(f"TQT-R1-V30-{self.a}", "30", self.mac1), (f"TQT-R2-V30-{self.b}", "30", self.mac2), (f"TQT-R3-V30-{self.a}", "30", None)])
        self.assertEqual(t["sin_mac"], [])

    def test_04_qr_de_una_pcb_o_una_mac_tambien_abre_la_tarjeta(self):
        self.programar_todo()
        for codigo, origen in ((f"TQT-R3-V30-{self.a}", "pcb"), (f"tqt r2 v30 {self.b}", "pcb"), (self.mac2.replace(":", "-"), "mac")):
            j = self.c.get("/api/consulta", params={"codigo": codigo}).json()
            self.assertEqual((j["origen"], j["tarjeta"]["id_tarjeta_num"]), (origen, self.a), codigo)

    def test_05_errores(self):
        self.assertEqual(self.c.get("/api/consulta", params={"codigo": "hola"}).status_code, 400)
        self.assertEqual(self.c.get("/api/consulta", params={"codigo": "TQT-R1-V30-9999"}).status_code, 404)
        self.assertEqual(self.c.get("/api/consulta", params={"codigo": "TQT-R1-V30-0000"}).status_code, 400)
        self.assertEqual(self.c.get("/api/consulta", params={"codigo": "x" * 3000}).status_code, 422)
        self.assertEqual(self.c.get("/api/consulta").status_code, 422)

    def test_06_avisa_si_la_etiqueta_ya_no_coincide(self):
        self.programar_todo()
        otra = num_unico()
        self.c.post("/api/pcb/escanear", json={"codigo": f"TQT-R2-V30-{otra}"})
        self.c.post("/api/recepcion/confirmar", json={"ids": None})
        etiqueta = f"TQT-R1-V30-{self.a}\n{self.mac1.lower()}\nTQT-R2-V30-{otra}\n{mac_unica().lower()}"
        j = self.c.get("/api/consulta", params={"codigo": etiqueta}).json()
        self.assertTrue(any("ya no está en la tarjeta" in a or "todavía no está" in a or "quedó suelta" in a for a in j["avisos"]), j["avisos"])
        # MAC distinta a la registrada
        mala = f"TQT-R1-V30-{self.a}\n{mac_unica().lower()}\nTQT-R2-V30-{self.b}\n{self.mac2.lower()}"
        j = self.c.get("/api/consulta", params={"codigo": mala}).json()
        self.assertTrue(any("no coincide con la registrada" in a for a in j["avisos"]), j["avisos"])

    def test_07_pcb_suelta_muestra_aviso_y_sin_tarjeta(self):
        n = num_unico()
        self.c.post("/api/pcb/escanear", json={"codigo": f"TQT-R1-V31-{n}"})
        j = self.c.get("/api/consulta", params={"codigo": f"TQT-R1-V31-{n}"}).json()
        self.assertEqual((j["tarjeta"], j["pcb"]["version"]), (None, "31"))
        self.assertTrue(any("no está en ninguna tarjeta" in a for a in j["avisos"]))


class TestPruebasEliminado(unittest.TestCase):
    """La sección Pruebas se quitó: ni página, ni API, ni enlaces."""
    @classmethod
    def setUpClass(cls):
        verificar_aislamiento()
        db.init_db()
        cls.c = TestClient(app, base_url="https://testserver")

    def test_ninguna_url_de_pruebas(self):
        for m, u in (("get", "/pruebas"), ("get", "/static/pruebas.html"), ("get", "/static/js/pruebas.js"),
                     ("get", "/api/tarjetas/1/pruebas"), ("put", "/api/tarjetas/1/pruebas"), ("post", "/api/pruebas/lote")):
            r = getattr(self.c, m)(u) if m == "get" else getattr(self.c, m)(u, json={})
            self.assertIn(r.status_code, (404, 405), u)

    def test_no_queda_ningun_enlace_en_las_paginas(self):
        estatico = RAIZ / "app" / "static"
        for f in list(estatico.glob("*.html")) + list((estatico / "js").glob("*.js")) + list(estatico.glob("icons/*.webmanifest")):
            if f.name == "jsQR.js":
                continue
            txt = f.read_text(encoding="utf-8", errors="ignore")
            for malo in ("/pruebas", "pruebas.html", "pruebas.js", "PRUEBA_ACTUALIZADA", "PRUEBAS_LOTE_ACTUALIZADAS"):
                self.assertNotIn(malo, txt, f"{f.name} sigue mencionando {malo}")

    def test_la_navegacion_ofrece_consultar_en_lugar_de_pruebas(self):
        js = (RAIZ / "app" / "static" / "js" / "common.js").read_text(encoding="utf-8")
        self.assertIn("href: '/consultar'", js)
        self.assertEqual(self.c.get("/consultar").status_code, 200)

    def test_frontend_hardware_firmware_y_selector_de_lote(self):
        """Rótulos Hardware/Firmware, sin firmware de R3, firmware con la MAC en una llamada y sub-título del encabezado = botón de lotes."""
        st = RAIZ / "app" / "static" / "js"
        prog = (st / "programar.js").read_text(encoding="utf-8")
        self.assertNotIn("firmware_r3", prog)
        self.assertIn("/programacion", prog)
        self.assertIn("/api/firmware", prog)
        cons = (st / "consultar.js").read_text(encoding="utf-8")
        self.assertNotIn("firmware_r3", cons)
        self.assertIn("La R3 no lleva MAC", cons)
        self.assertNotIn("ni firmware", cons)
        self.assertIn("'Hardware'", cons)
        com = (st / "common.js").read_text(encoding="utf-8")
        self.assertIn("button", com[com.index("const sub = h("):com.index("const sub = h(") + 80])
        self.assertIn("/api/lotes/${l.id}/activar", com)
        self.assertIn("/api/admin/login", com)
        self.assertIn("?lote=", (st / "escritorio.js").read_text(encoding="utf-8") + com)

    def test_logo_de_la_consola_lleva_al_resumen_no_a_la_raiz(self):
        """La consola de escritorio es lo que sirve `/` en una PC: el logo va a #/resumen (ir a `/` volvía a la consola)."""
        js = (RAIZ / "app" / "static" / "js" / "escritorio.js").read_text(encoding="utf-8")
        self.assertIn("href: '#/resumen', class: 'esc-logo'", js)
        html = (RAIZ / "app" / "static" / "monitor.html").read_text(encoding="utf-8")
        self.assertIn("Consola · Escáner TQT", html)
        for prohibido in ("jsQR", "scanner.js", "visor.js"):
            self.assertNotIn(prohibido, html)   # la consola de escritorio no usa cámara


class TestMigracionFirmwarePorPcb(unittest.TestCase):
    def test_base_anterior_sin_columna_se_actualiza_sin_perder_datos(self):
        verificar_aislamiento()
        with tempfile.TemporaryDirectory() as d:
            ruta = Path(d) / "vieja.db"
            db.init_db(ruta)
            con = sqlite3.connect(ruta)
            con.execute("ALTER TABLE pcb_inventario DROP COLUMN firmware")
            con.execute("DELETE FROM firmware_catalogo")
            con.commit()
            con.close()
            db.init_db(ruta)                                   # vuelve a agregar la columna y siembra el catálogo del Excel
            con = sqlite3.connect(ruta)
            cols = {r[1] for r in con.execute("PRAGMA table_info(pcb_inventario)")}
            n = con.execute("SELECT COUNT(*) FROM firmware_catalogo").fetchone()[0]
            con.close()
            self.assertIn("firmware", cols)
            self.assertEqual(n, 8)                             # R1: 6 versiones, R2: 2
            db.init_db(ruta)                                   # idempotente
            con = sqlite3.connect(ruta)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM firmware_catalogo").fetchone()[0], 8)
            con.close()


if __name__ == "__main__":
    unittest.main()
