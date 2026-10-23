import _aislamiento  # noqa: F401  (debe ser lo primero)
"""v1.4.37: módulo Caiquén (clon de SpeedLocker). QR PROVISIONAL 'CQ-0001' → 'CQ-V1-0001';
Escáner TQT, TPMS, AntiJammer y SpeedLocker lo rechazan y Caiquén rechaza los suyos."""
import unittest

from app.database import db
from app.database.models import parse_antijammer, parse_caiquen, parse_sigfox, parse_speedlocker, parse_tarjeta_code, parse_tpms
from app.main import app
from app.modulos import MODULOS, CAIQUEN, modulo_de_ruta
from app.services import usuarios

from _aislamiento import cliente_sin_sesion, verificar_aislamiento


class TestCaiquen(unittest.TestCase):
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
        self.assertEqual(parse_caiquen("CQ-0001")["nombre"], "CQ-V1-0001")   # QR provisional
        self.assertEqual(parse_caiquen("CQ_0001")["nombre"], "CQ-V1-0001")
        self.assertEqual(parse_caiquen("cq 1")["nombre"], "CQ-V1-0001")
        self.assertEqual(parse_caiquen("PCB_CQ_V2_0001")["nombre"], "CQ-V2-0001")
        self.assertEqual(parse_caiquen("CAIQUÉN-0007")["nombre"], "CQ-V1-0007")
        self.assertEqual(parse_caiquen("caiquen_v1_0007")["nombre"], "CQ-V1-0007")
        self.assertEqual(parse_caiquen("CAIQUEN-0008")["nombre"], "CQ-V1-0008")
        self.assertEqual(parse_caiquen("CQ-V1_1-0003")["nombre"], "CQ-V1.1-0003")
        self.assertIsNone(parse_caiquen("CQ-V0-0001"))
        self.assertIsNone(parse_caiquen("CQ-V1-0000"))
        for ajeno in ("SF-0001", "SJ_0052", "SL-0024", "SPEEDLOCKER-0007", "TPMS_V1_0004", "TQT-R1-V30-0011"):
            self.assertIsNone(parse_caiquen(ajeno), ajeno)
        for cq in ("CQ_0001", "CAIQUÉN-0007", "CAIQUEN-0008", "CQ-V1-0001"):
            self.assertIsNone(parse_tpms(cq), cq)
            self.assertIsNone(parse_antijammer(cq), cq)
            self.assertIsNone(parse_speedlocker(cq), cq)
            self.assertIsNone(parse_sigfox(cq), cq)
            self.assertIsNone(parse_tarjeta_code(cq), cq)
            self.assertIsNone(parse_tarjeta_code(cq, tipo_esperado="R2"), cq)

    def test_modulo_y_paginas(self):
        m = next(x for x in MODULOS if x["id"] == CAIQUEN)
        self.assertEqual((m["estado"], m["url"], m["login"], m["acento"]), ("disponible", "/caiquen", "/caiquen/acceso", "#EF4444"))
        for ruta in ("/caiquen", "/caiquen/acceso", "/api/caiquen/pcb", "/static/caiquen.html", "/static/js/caiquen.js",
                     "/static/css/caiquen.css"):
            self.assertEqual(modulo_de_ruta(ruta), CAIQUEN, ruta)
        self.assertEqual(modulo_de_ruta("/api/speedlocker/pcb"), "speedlocker")

    def test_alta_repetida_y_rechazos(self):
        r = self.c.post("/api/caiquen/escanear", json={"codigo": "CQ_0001", "lote": "Oct 2026"}).json()
        self.assertEqual((r["resultado"], r["pcb"]["nombre"], r["pcb"]["lote"]), ("AGREGADA", "CQ-V1-0001", "Oct 2026"))
        self.assertEqual(r["pcb"]["operador"], "developer@skyguardian.mx")
        self.assertEqual(self.c.post("/api/caiquen/escanear", json={"codigo": "caiquen_v1_1"}).json()["resultado"], "REPETIDA")
        # Caiquén rechaza TPMS, AntiJammer, SpeedLocker y Escáner TQT
        for codigo, marca in (("TPMS_V1_0004", "TPMS"), ("SJ_0052", "AntiJammer"), ("SL-0024", "SpeedLocker"),
                              ("TQT-R1-V30-0001", "Escáner TQT")):
            t = self.c.post("/api/caiquen/escanear", json={"codigo": codigo}).json()
            self.assertEqual(t["resultado"], "INVALIDA", codigo)
            self.assertIn(marca, t["mensaje"])
        # Escáner TQT, TPMS, AntiJammer y SpeedLocker rechazan la placa Caiquén
        for url in ("/api/pcb/escanear", "/api/tpms/escanear", "/api/antijammer/escanear", "/api/speedlocker/escanear"):
            e = self.c.post(url, json={"codigo": "CQ_0001"}).json()
            self.assertEqual(e["resultado"], "INVALIDA", url)
            self.assertIn("Caiquén", e["mensaje"], url)
        # Tablas separadas
        for mod in ("antijammer", "tpms", "speedlocker"):
            self.assertEqual(self.c.get(f"/api/{mod}/pcb", params={"q": "CQ-"}).json()["total"], 0, mod)
        with db.get_db() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM caiquen_pcb WHERE nombre = 'CQ-V1-0001'").fetchone()[0], 1)

    def _manual(self, serie, version="1", lote="L-cq"):
        r = self.c.post("/api/caiquen/pcb/manual", json={"version": version, "serie": serie, "lote": lote})
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()["pcb"]

    def test_manual_por_codigo_firmware_y_masa(self):
        p = self._manual("101")
        self.assertEqual((p["nombre"], p["estado"]), ("CQ-V1-0101", "RECIBIDA"))
        self.assertEqual(self.c.post("/api/caiquen/pcb/manual", json={"version": "V1", "serie": "0101"}).status_code, 409)
        for codigo in ("101", "CQ-V1-0101", "CQ_0101", "CQ-0101", "caiquen_v1_0101", "CAIQUEN 101"):
            r = self.c.get("/api/caiquen/pcb/por-codigo", params={"codigo": codigo})
            self.assertEqual(r.status_code, 200, codigo)
            self.assertEqual(r.json()["pcb"]["id"], p["id"])
        self.assertEqual(self.c.get("/api/caiquen/pcb/por-codigo", params={"codigo": "SL_0101"}).status_code, 404)
        r = self.c.put(f"/api/caiquen/pcb/{p['id']}/firmware", json={"firmware": "cq-1.0"}).json()["pcb"]
        self.assertEqual((r["firmware"], r["estado"]), ("cq-1.0", "PROGRAMADA"))
        ids = [self._manual(s, lote="L-cq-masa")["id"] for s in ("401", "402")]
        self.assertEqual(self.c.post("/api/caiquen/pcb/masa", json={"ids": ids, "accion": "estado", "valor": "BAJA"}).json()["afectadas"], 2)
        self.assertEqual(self.c.post("/api/caiquen/pcb/masa", json={"ids": ids + [999999], "accion": "lote", "valor": "X"}).status_code, 404)
        self.assertEqual(self.c.patch(f"/api/caiquen/pcb/{ids[0]}", json={"nota": "ok"}).json()["pcb"]["nota"], "ok")
        self.assertEqual(self.c.delete(f"/api/caiquen/pcb/{ids[1]}").json(), {"ok": True})

    def test_resumen_eventos_lotes_y_exportar(self):
        self._manual("501", lote="L-cq-res")
        r = self.c.get("/api/caiquen/resumen").json()
        self.assertIn({"lote": "L-cq-res", "n": 1}, r["lotes"])
        self.assertEqual(len(r["actividad"]), 14)
        self.assertGreaterEqual(self.c.get("/api/caiquen/eventos", params={"q": "CQ-V1-0501"}).json()["total"], 1)
        self.assertIn("L-cq-res", [x["lote"] for x in self.c.get("/api/caiquen/lotes").json()["items"]])
        self.assertEqual(self.c.post("/api/caiquen/lotes/renombrar", json={"de": "L-cq-res", "a": "L-cq-res2"}).json()["afectadas"], 1)
        x = self.c.get("/api/caiquen/exportar")
        self.assertEqual(x.status_code, 200)
        self.assertIn("Caiquen_placas_", x.headers["content-disposition"])
        self.assertTrue(x.content.startswith(b"PK"))

    def test_paginas_se_sirven(self):
        self.assertEqual(self.c.get("/caiquen/acceso").status_code, 200)
        self.assertEqual(self.c.get("/caiquen").status_code, 200)


if __name__ == "__main__":
    unittest.main()
