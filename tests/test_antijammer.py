import _aislamiento  # noqa: F401  (debe ser lo primero)
"""v1.4.31: módulo Skudo AntiJammer (clon de TPMS). QR provisional 'SJ-V1-0001'; Escáner TQT y TPMS lo rechazan."""
import unittest

from app.database import db
from app.database.models import parse_antijammer, parse_tarjeta_code, parse_tpms
from app.main import app
from app.modulos import ANTIJAMMER, MODULOS, modulo_de_ruta
from app.services import usuarios

from _aislamiento import cliente_sin_sesion, verificar_aislamiento


class TestAntijammer(unittest.TestCase):
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
        self.assertEqual(parse_antijammer("SJ_0052")["nombre"], "SJ-V1-0052")   # QR real de la placa
        self.assertEqual(parse_antijammer("sj 52")["nombre"], "SJ-V1-0052")
        self.assertIsNone(parse_tpms("SJ_0052"))
        self.assertIsNone(parse_tarjeta_code("SJ_0052"))
        self.assertEqual(parse_antijammer("SJ-V1-0001")["nombre"], "SJ-V1-0001")
        self.assertEqual(parse_antijammer("skudo_aj_v1_0001")["nombre"], "SJ-V1-0001")
        self.assertEqual(parse_antijammer("skudo aj 7")["nombre"], "SJ-V1-0007")
        self.assertEqual(parse_antijammer("SJ-V1_1-0003")["nombre"], "SJ-V1.1-0003")
        self.assertIsNone(parse_antijammer("SJ-V0-0001"))
        self.assertIsNone(parse_antijammer("SJ-V1-0000"))
        self.assertIsNone(parse_antijammer("TPMS_V1_0004"))
        self.assertIsNone(parse_antijammer("TQT-R1-V30-0011"))
        self.assertIsNone(parse_tpms("SJ-V1-0001"))
        self.assertIsNone(parse_tarjeta_code("SJ-V1-0001"))
        self.assertIsNone(parse_tarjeta_code("SJ-V1-0001", tipo_esperado="R2"))

    def test_modulo_y_paginas(self):
        m = next(x for x in MODULOS if x["id"] == ANTIJAMMER)
        self.assertEqual((m["estado"], m["url"], m["login"], m["acento"]), ("disponible", "/antijammer", "/antijammer/acceso", "#39FF14"))
        for ruta in ("/antijammer", "/api/antijammer/pcb", "/static/antijammer.html", "/static/js/antijammer.js"):
            self.assertEqual(modulo_de_ruta(ruta), ANTIJAMMER, ruta)
        self.assertEqual(modulo_de_ruta("/api/tpms/pcb"), "tpms")

    def test_alta_repetida_y_rechazos(self):
        r = self.c.post("/api/antijammer/escanear", json={"codigo": "SJ-V1-0001", "lote": "Oct 2026"}).json()
        self.assertEqual((r["resultado"], r["pcb"]["nombre"], r["pcb"]["lote"]), ("AGREGADA", "SJ-V1-0001", "Oct 2026"))
        self.assertEqual(r["pcb"]["operador"], "developer@skyguardian.mx")
        self.assertEqual(self.c.post("/api/antijammer/escanear", json={"codigo": "skudo_aj_v1_1"}).json()["resultado"], "REPETIDA")
        t = self.c.post("/api/antijammer/escanear", json={"codigo": "TPMS_V1_0004"}).json()
        self.assertEqual(t["resultado"], "INVALIDA")
        self.assertIn("TPMS", t["mensaje"])
        self.assertEqual(self.c.post("/api/antijammer/escanear", json={"codigo": "TQT-R1-V30-0001"}).json()["resultado"], "INVALIDA")
        # Escáner TQT y TPMS rechazan la placa AntiJammer
        e = self.c.post("/api/pcb/escanear", json={"codigo": "SJ-V1-0001"}).json()
        self.assertEqual(e["resultado"], "INVALIDA")
        self.assertIn("AntiJammer", e["mensaje"])
        e = self.c.post("/api/tpms/escanear", json={"codigo": "SJ-V1-0001"}).json()
        self.assertEqual(e["resultado"], "INVALIDA")
        self.assertIn("AntiJammer", e["mensaje"])
        # Tablas separadas
        self.assertEqual(self.c.get("/api/tpms/pcb", params={"q": "SJ-"}).json()["total"], 0)
        with db.get_db() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM antijammer_pcb WHERE nombre = 'SJ-V1-0001'").fetchone()[0], 1)

    def _manual(self, serie, version="1", lote="L-aj"):
        r = self.c.post("/api/antijammer/pcb/manual", json={"version": version, "serie": serie, "lote": lote})
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()["pcb"]

    def test_manual_por_codigo_firmware_y_masa(self):
        p = self._manual("101")
        self.assertEqual((p["nombre"], p["estado"]), ("SJ-V1-0101", "RECIBIDA"))
        self.assertEqual(self.c.post("/api/antijammer/pcb/manual", json={"version": "V1", "serie": "0101"}).status_code, 409)
        for codigo in ("101", "SJ-V1-0101", "skudo_aj_v1_0101"):
            r = self.c.get("/api/antijammer/pcb/por-codigo", params={"codigo": codigo})
            self.assertEqual(r.status_code, 200, codigo)
            self.assertEqual(r.json()["pcb"]["id"], p["id"])
        self.assertEqual(self.c.get("/api/antijammer/pcb/por-codigo", params={"codigo": "TPMS_V1_0101"}).status_code, 404)
        r = self.c.put(f"/api/antijammer/pcb/{p['id']}/firmware", json={"firmware": "aj-1.0"}).json()["pcb"]
        self.assertEqual((r["firmware"], r["estado"]), ("aj-1.0", "PROGRAMADA"))
        ids = [self._manual(s, lote="L-aj-masa")["id"] for s in ("401", "402")]
        self.assertEqual(self.c.post("/api/antijammer/pcb/masa", json={"ids": ids, "accion": "estado", "valor": "BAJA"}).json()["afectadas"], 2)
        self.assertEqual(self.c.post("/api/antijammer/pcb/masa", json={"ids": ids + [999999], "accion": "lote", "valor": "X"}).status_code, 404)
        self.assertEqual(self.c.patch(f"/api/antijammer/pcb/{ids[0]}", json={"nota": "ok"}).json()["pcb"]["nota"], "ok")
        self.assertEqual(self.c.delete(f"/api/antijammer/pcb/{ids[1]}").json(), {"ok": True})

    def test_resumen_eventos_lotes_y_exportar(self):
        self._manual("501", lote="L-aj-res")
        r = self.c.get("/api/antijammer/resumen").json()
        self.assertIn({"lote": "L-aj-res", "n": 1}, r["lotes"])
        self.assertEqual(len(r["actividad"]), 14)
        self.assertGreaterEqual(self.c.get("/api/antijammer/eventos", params={"q": "SJ-V1-0501"}).json()["total"], 1)
        self.assertIn("L-aj-res", [x["lote"] for x in self.c.get("/api/antijammer/lotes").json()["items"]])
        self.assertEqual(self.c.post("/api/antijammer/lotes/renombrar", json={"de": "L-aj-res", "a": "L-aj-res2"}).json()["afectadas"], 1)
        x = self.c.get("/api/antijammer/exportar")
        self.assertEqual(x.status_code, 200)
        self.assertIn("SkudoAntiJammer_placas_", x.headers["content-disposition"])
        self.assertTrue(x.content.startswith(b"PK"))


if __name__ == "__main__":
    unittest.main()
