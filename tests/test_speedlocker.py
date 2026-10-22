import _aislamiento  # noqa: F401  (debe ser lo primero)
"""v1.4.32: módulo SpeedLocker (clon de Skudo AntiJammer). QR real 'SL-0024' → 'SL-V1-0024';
Escáner TQT, TPMS y AntiJammer lo rechazan y SpeedLocker rechaza los suyos."""
import unittest

from app.database import db
from app.database.models import parse_antijammer, parse_speedlocker, parse_tarjeta_code, parse_tpms
from app.main import app
from app.modulos import MODULOS, SPEEDLOCKER, modulo_de_ruta
from app.services import usuarios

from _aislamiento import cliente_sin_sesion, verificar_aislamiento


class TestSpeedlocker(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        verificar_aislamiento()
        db.init_db()
        usuarios.sembrar(iteraciones=1000)
        usuarios.limitador.reiniciar()
        cls.c = cliente_sin_sesion(app)
        r = cls.c.post("/api/auth/login", json={"email": "developer@skyguardian.mx", "password": usuarios.CLAVE_INICIAL})
        assert r.status_code == 200, r.text

    def test_formatos_y_rechazos_cruzados(self):
        self.assertEqual(parse_speedlocker("SL-0024")["nombre"], "SL-V2-0024")   # QR real de la placa
        self.assertEqual(parse_speedlocker("SL_0001")["nombre"], "SL-V2-0001")
        self.assertEqual(parse_speedlocker("sl 1")["nombre"], "SL-V2-0001")
        self.assertEqual(parse_speedlocker("PCB_SL_V1_0001")["nombre"], "SL-V1-0001")
        self.assertEqual(parse_speedlocker("SPEEDLOCKER-0007")["nombre"], "SL-V2-0007")
        self.assertEqual(parse_speedlocker("speed_locker_v1_0007")["nombre"], "SL-V1-0007")
        self.assertEqual(parse_speedlocker("SL-V1_1-0003")["nombre"], "SL-V1.1-0003")
        self.assertIsNone(parse_speedlocker("SL-V0-0001"))
        self.assertIsNone(parse_speedlocker("SL-V1-0000"))
        for ajeno in ("SJ_0052", "TPMS_V1_0004", "TQT-R1-V30-0011"):
            self.assertIsNone(parse_speedlocker(ajeno), ajeno)
        for sl in ("SL_0001", "SPEEDLOCKER-0007", "SL-V1-0001"):
            self.assertIsNone(parse_tpms(sl), sl)
            self.assertIsNone(parse_antijammer(sl), sl)
            self.assertIsNone(parse_tarjeta_code(sl), sl)
            self.assertIsNone(parse_tarjeta_code(sl, tipo_esperado="R2"), sl)

    def test_modulo_y_paginas(self):
        m = next(x for x in MODULOS if x["id"] == SPEEDLOCKER)
        self.assertEqual((m["estado"], m["url"], m["login"], m["acento"]), ("disponible", "/speedlocker", "/speedlocker/acceso", "#38BDF8"))
        for ruta in ("/speedlocker", "/speedlocker/acceso", "/api/speedlocker/pcb", "/static/speedlocker.html", "/static/js/speedlocker.js",
                     "/static/css/speedlocker.css"):
            self.assertEqual(modulo_de_ruta(ruta), SPEEDLOCKER, ruta)
        self.assertEqual(modulo_de_ruta("/api/antijammer/pcb"), "skudo-antijammer")

    def test_alta_repetida_y_rechazos(self):
        r = self.c.post("/api/speedlocker/escanear", json={"codigo": "SL_0001", "lote": "Oct 2026"}).json()
        self.assertEqual((r["resultado"], r["pcb"]["nombre"], r["pcb"]["lote"]), ("AGREGADA", "SL-V2-0001", "Oct 2026"))
        self.assertEqual(r["pcb"]["operador"], "developer@skyguardian.mx")
        self.assertEqual(self.c.post("/api/speedlocker/escanear", json={"codigo": "speedlocker_v2_1"}).json()["resultado"], "REPETIDA")
        # SpeedLocker rechaza TPMS, AntiJammer y Escáner TQT
        for codigo, marca in (("TPMS_V1_0004", "TPMS"), ("SJ_0052", "AntiJammer"), ("TQT-R1-V30-0001", "Escáner TQT")):
            t = self.c.post("/api/speedlocker/escanear", json={"codigo": codigo}).json()
            self.assertEqual(t["resultado"], "INVALIDA", codigo)
            self.assertIn(marca, t["mensaje"])
        # Escáner TQT, TPMS y AntiJammer rechazan la placa SpeedLocker
        for url in ("/api/pcb/escanear", "/api/tpms/escanear", "/api/antijammer/escanear"):
            e = self.c.post(url, json={"codigo": "SL_0001"}).json()
            self.assertEqual(e["resultado"], "INVALIDA", url)
            self.assertIn("SpeedLocker", e["mensaje"], url)
        # Tablas separadas
        self.assertEqual(self.c.get("/api/antijammer/pcb", params={"q": "SL-"}).json()["total"], 0)
        self.assertEqual(self.c.get("/api/tpms/pcb", params={"q": "SL-"}).json()["total"], 0)
        with db.get_db() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM speedlocker_pcb WHERE nombre = 'SL-V2-0001'").fetchone()[0], 1)

    def _manual(self, serie, version="2", lote="L-sl"):
        r = self.c.post("/api/speedlocker/pcb/manual", json={"version": version, "serie": serie, "lote": lote})
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()["pcb"]

    def test_manual_por_codigo_firmware_y_masa(self):
        p = self._manual("101")
        self.assertEqual((p["nombre"], p["estado"]), ("SL-V2-0101", "RECIBIDA"))
        self.assertEqual(self.c.post("/api/speedlocker/pcb/manual", json={"version": "V2", "serie": "0101"}).status_code, 409)
        for codigo in ("101", "SL-V2-0101", "SL_0101", "SL-0101", "speedlocker_v2_0101"):
            r = self.c.get("/api/speedlocker/pcb/por-codigo", params={"codigo": codigo})
            self.assertEqual(r.status_code, 200, codigo)
            self.assertEqual(r.json()["pcb"]["id"], p["id"])
        self.assertEqual(self.c.get("/api/speedlocker/pcb/por-codigo", params={"codigo": "SJ_0101"}).status_code, 404)
        r = self.c.put(f"/api/speedlocker/pcb/{p['id']}/firmware", json={"firmware": "sl-1.0"}).json()["pcb"]
        self.assertEqual((r["firmware"], r["estado"]), ("sl-1.0", "PROGRAMADA"))
        ids = [self._manual(s, lote="L-sl-masa")["id"] for s in ("401", "402")]
        self.assertEqual(self.c.post("/api/speedlocker/pcb/masa", json={"ids": ids, "accion": "estado", "valor": "BAJA"}).json()["afectadas"], 2)
        self.assertEqual(self.c.post("/api/speedlocker/pcb/masa", json={"ids": ids + [999999], "accion": "lote", "valor": "X"}).status_code, 404)
        self.assertEqual(self.c.patch(f"/api/speedlocker/pcb/{ids[0]}", json={"nota": "ok"}).json()["pcb"]["nota"], "ok")
        self.assertEqual(self.c.delete(f"/api/speedlocker/pcb/{ids[1]}").json(), {"ok": True})

    def test_resumen_eventos_lotes_y_exportar(self):
        self._manual("501", lote="L-sl-res")
        r = self.c.get("/api/speedlocker/resumen").json()
        self.assertIn({"lote": "L-sl-res", "n": 1}, r["lotes"])
        self.assertEqual(len(r["actividad"]), 14)
        self.assertGreaterEqual(self.c.get("/api/speedlocker/eventos", params={"q": "SL-V2-0501"}).json()["total"], 1)
        self.assertIn("L-sl-res", [x["lote"] for x in self.c.get("/api/speedlocker/lotes").json()["items"]])
        self.assertEqual(self.c.post("/api/speedlocker/lotes/renombrar", json={"de": "L-sl-res", "a": "L-sl-res2"}).json()["afectadas"], 1)
        x = self.c.get("/api/speedlocker/exportar")
        self.assertEqual(x.status_code, 200)
        self.assertIn("SpeedLocker_placas_", x.headers["content-disposition"])
        self.assertTrue(x.content.startswith(b"PK"))


if __name__ == "__main__":
    unittest.main()
