import _aislamiento  # noqa: F401  (debe ser lo primero)
"""v1.4.27: placas TPMS. Las V1 traen la plantilla de la R3 Timer con guiones ('PCB_TQT-R3_V2_0_TIMER-0004'):
TPMS las registra como TPMS-V1-<serie> y Escáner TQT las rechaza; la R3 Timer real (guiones bajos) sigue siendo TQT."""
import unittest

from app.database import db
from app.database.models import parse_tarjeta_code, parse_tpms
from app.main import app
from app.services import usuarios

from _aislamiento import cliente_sin_sesion, verificar_aislamiento


class TestTpms(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        verificar_aislamiento()
        db.init_db()
        usuarios.sembrar(iteraciones=1000)
        usuarios.limitador.reiniciar()
        cls.c = cliente_sin_sesion(app)
        r = cls.c.post("/api/auth/login", json={"email": "developer@skyguardian.mx", "password": usuarios.CLAVE_INICIAL})
        assert r.status_code == 200, r.text

    def test_formatos(self):
        self.assertEqual(parse_tpms("PCB_TQT-R3_V2_0_TIMER-0004")["nombre"], "TPMS-V1-0004")
        self.assertEqual(parse_tpms("TPMS_V1_12")["nombre"], "TPMS-V1-0012")
        self.assertEqual(parse_tpms("pcb tpms 7")["nombre"], "TPMS-V1-0007")
        self.assertEqual(parse_tpms("TPMS-V1_1-0003")["nombre"], "TPMS-V1.1-0003")
        self.assertIsNone(parse_tpms("TPMS_V0_0001"))
        self.assertIsNone(parse_tpms("PCB_TQT_R3_V2_0_TIMER_0073"))             # R3 Timer real
        self.assertEqual(parse_tarjeta_code("PCB_TQT_R3_V2_0_TIMER_0073")["nombre"], "TQT-R3-V20-0073")
        self.assertIsNone(parse_tarjeta_code("PCB_TQT-R3_V2_0_TIMER-0004"))     # TPMS: no es TQT

    def test_alta_y_rechazo_en_tqt(self):
        r = self.c.post("/api/tpms/escanear", json={"codigo": "PCB_TQT-R3_V2_0_TIMER-0004", "lote": "Marzo 2026"}).json()
        self.assertEqual((r["resultado"], r["pcb"]["nombre"], r["pcb"]["lote"]), ("AGREGADA", "TPMS-V1-0004", "Marzo 2026"))
        self.assertEqual(r["pcb"]["operador"], "developer@skyguardian.mx")
        self.assertEqual(self.c.post("/api/tpms/escanear", json={"codigo": "TPMS_V1_0004"}).json()["resultado"], "REPETIDA")
        self.assertEqual(self.c.post("/api/tpms/escanear", json={"codigo": "TQT-R1-V30-0001"}).json()["resultado"], "INVALIDA")
        self.assertIn("TPMS-V1-0004", [p["nombre"] for p in self.c.get("/api/tpms/pcb?lote=Marzo 2026").json()["items"]])
        e = self.c.post("/api/pcb/escanear", json={"codigo": "PCB_TQT-R3_V2_0_TIMER-0004"}).json()
        self.assertEqual(e["resultado"], "INVALIDA")
        self.assertIn("TPMS", e["mensaje"])


if __name__ == "__main__":
    unittest.main()
