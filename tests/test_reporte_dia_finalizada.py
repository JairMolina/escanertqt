"""v1.4.94: el reporte por día/rango incluye `finalizada` y `r3_aprobada` (JSON y Excel)."""
import _aislamiento  # noqa: F401  (debe ser lo primero)
import io
import unittest
from datetime import date
from unittest import mock

from openpyxl import load_workbook

from app.database import db, inventario as inv
from app.services import reporte_dia

from _aislamiento import verificar_aislamiento


class TestReporteDiaFinalizada(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        verificar_aislamiento()
        db.init_db()
        cls.hoy = date.today().isoformat()
        with db.get_db() as c:
            r1 = inv.asegurar_pcb(c, "R1", "30", "9101", mac="70:4B:CA:91:00:01")
            r2 = inv.asegurar_pcb(c, "R2", "30", "9101", mac="70:4B:CA:91:00:02")
            r3 = inv.asegurar_pcb(c, "R3", "30", "9101")
            cls.tid = inv.crear_tarjeta(id_tarjeta_num="9101", r1_id=r1, r2_id=r2, r3_id=r3, conn=c)["id"]
            c.execute("UPDATE tarjetas_produccion SET fecha_finalizado = ? WHERE id = ?", (cls.hoy, cls.tid))

    def _fila(self):
        return next(f for f in reporte_dia.tarjetas_del_rango(self.hoy, self.hoy)["items"] if f["id"] == self.tid)

    def test_no_finalizada_por_defecto(self):
        f = self._fila()
        self.assertFalse(f["finalizada"])
        self.assertFalse(f["r3_aprobada"])
        d = reporte_dia.tarjetas_del_rango(self.hoy, self.hoy)
        self.assertEqual(d["finalizadas"], sum(1 for i in d["items"] if i["finalizada"]))   # otras tarjetas de la base de prueba pueden estar finalizadas

    def test_finalizada_se_cuenta_y_sale_en_excel(self):
        real = db.get_tarjeta_by_id
        def falso(i, conn=None, db_path=None):
            t = real(i, conn=conn, db_path=db_path)
            if t and i == self.tid:
                t["finalizada"] = True
                t["r3"]["aprobada"] = True
            return t
        antes = reporte_dia.tarjetas_del_rango(self.hoy, self.hoy)["finalizadas"]
        with mock.patch.object(db, "get_tarjeta_by_id", side_effect=falso):
            d = reporte_dia.tarjetas_del_rango(self.hoy, self.hoy)
            self.assertEqual(d["finalizadas"], antes + 1)
            ws = load_workbook(io.BytesIO(reporte_dia.excel_del_rango(self.hoy, self.hoy))).active
        cab = [ws.cell(8, i).value for i in range(1, 15)]
        self.assertEqual(cab[12:], ["Estado", "R3 aprobada"])
        fila = next(r for r in range(9, 30) if ws.cell(r, 1).value == "#9101")
        self.assertEqual((ws.cell(fila, 13).value, ws.cell(fila, 14).value), ("FINALIZADA", "Sí"))


if __name__ == "__main__":
    unittest.main()
