"""Firmware por placa (solo R1/R2) y su paso al Excel: columnas D/G de Producción y listas N/P del catálogo."""
import _aislamiento  # noqa: F401  (debe ser lo primero)
import io
import os
import unittest
import warnings
from unittest import mock

import openpyxl
from fastapi.testclient import TestClient

from app.database import db
from app.main import app
from app.services import admin_auth

from _aislamiento import mac_unica, num_unico, verificar_aislamiento

CLAVE = "Firmware-Excel-123"


class TestFirmwareEnExcel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        verificar_aislamiento()
        db.init_db()
        cls._env = mock.patch.dict(os.environ, {"TQT_ADMIN_PASSWORD": CLAVE})
        cls._env.start()
        admin_auth.limitador.reiniciar()
        cls.c = TestClient(app, base_url="https://testserver")
        cls.c.headers["X-Admin-Token"] = cls.c.post("/api/admin/login", json={"password": CLAVE}).json()["token"]

    @classmethod
    def tearDownClass(cls):
        admin_auth.limitador.reiniciar()
        cls._env.stop()

    def _tarjeta(self, fw1, fw2):
        n = num_unico()
        for t in ("R1", "R2"):
            self.c.post("/api/pcb/escanear", json={"codigo": f"TQT-{t}-V30-{n}"})
        self.c.post("/api/recepcion/confirmar", json={"ids": None})
        ids = {p["nombre"]: p["id"] for p in self.c.get("/api/pcb", params={"limit": 1000}).json()["items"]}
        t = self.c.post("/api/tarjetas", json={"r1_id": ids[f"TQT-R1-V30-{n}"], "r2_id": ids[f"TQT-R2-V30-{n}"]}).json()
        self.c.put(f"/api/pcb/{ids[f'TQT-R1-V30-{n}']}/programacion", json={"mac": mac_unica(), "firmware": fw1})
        self.c.put(f"/api/pcb/{ids[f'TQT-R2-V30-{n}']}/programacion", json={"mac": mac_unica(), "firmware": fw2})
        return t, n

    def _excel(self, lote_id):
        r = self.c.get("/api/admin/export/excel", params={"lote_id": lote_id})
        self.assertEqual(r.status_code, 200, r.text[:200])
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return openpyxl.load_workbook(io.BytesIO(r.content))

    def test_el_firmware_de_cada_placa_llega_a_las_columnas_d_y_g_y_al_catalogo(self):
        t, n = self._tarjeta("4.3", "2.5")
        wb = self._excel(t["lote_id"])
        ws = wb["Producción"]
        fila = next(r for r in range(2, 102) if str(ws.cell(r, 1).value).strip() == n)
        self.assertEqual((str(ws.cell(fila, 4).value), str(ws.cell(fila, 7).value)), ("4.3", "2.5"))      # D = Principal (R1), G = Respaldo (R2)
        principal = [str(ws.cell(r, 15).value) for r in range(2, 53) if ws.cell(r, 15).value not in (None, "")]
        respaldo = [str(ws.cell(r, 17).value) for r in range(2, 53) if ws.cell(r, 17).value not in (None, "")]
        for v in ("2", "3.2", "3.3", "4.0", "4.1", "4.2", "4.3"):       # las de la plantilla siguen y la nueva se agregó
            self.assertIn(v, principal)
        for v in ("2", "2.1", "2.5"):
            self.assertIn(v, respaldo)

    def test_las_listas_desplegables_del_excel_se_conservan(self):
        t, _ = self._tarjeta("4.0", "2")
        ws = self._excel(t["lote_id"])["Producción"]
        listas = {str(dv.sqref): dv.formula1 for dv in ws.data_validations.dataValidation if dv.type == "list"}
        self.assertEqual(listas.get("D2:D101"), "$O$2:$O$52")
        self.assertEqual(listas.get("G2:G101"), "$Q$2:$Q$52")

    def test_reemplazar_una_placa_cambia_el_firmware_que_se_exporta(self):
        t, n = self._tarjeta("4.1", "2")
        # llega otra R1 con otro firmware y reemplaza a la anterior: el firmware viaja con la placa, no con la tarjeta
        m = num_unico()
        self.c.post("/api/pcb/escanear", json={"codigo": f"TQT-R1-V30-{m}"})
        self.c.post("/api/recepcion/confirmar", json={"ids": None})
        nueva = next(p for p in self.c.get("/api/pcb", params={"limit": 1000}).json()["items"] if p["nombre"] == f"TQT-R1-V30-{m}")
        r = self.c.put(f"/api/tarjetas/{t['id']}/asignar", json={"ranura": "R1", "pcb_id": nueva["id"]})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertIsNone(self.c.get(f"/api/tarjetas/{t['id']}").json()["firmware_r1"])                   # la nueva aún no se programa
        self.c.put(f"/api/pcb/{nueva['id']}/programacion", json={"mac": mac_unica(), "firmware": "4.2"})
        self.assertEqual(self.c.get(f"/api/tarjetas/{t['id']}").json()["firmware_r1"], "4.2")


if __name__ == "__main__":
    unittest.main()
