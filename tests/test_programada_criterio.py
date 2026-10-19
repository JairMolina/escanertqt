"""v1.4.8: un solo criterio de «programada» (R1 y R2 con MAC y firmware) en reporte por fecha y consumo de materiales."""
import _aislamiento as iso  # noqa: F401  (debe ser lo primero)
import unittest
from datetime import date

from app.database import db, inventario as inv
from app.services import reporte_dia

from _aislamiento import verificar_aislamiento


def programada_sql(tid):
    with db.get_db() as c:
        return bool(c.execute(f"SELECT {db._R1R2_PROGRAMADAS} FROM tarjetas_produccion WHERE id = ?", (tid,)).fetchone()[0])


class TestProgramadaCriterio(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        verificar_aislamiento()
        db.init_db()
        cls.lote = iso.nuevo_lote()["id"]

    def reporte(self, tid):
        hoy = date.today().isoformat()
        return next((f for f in reporte_dia.tarjetas_del_rango(hoy, hoy)["items"] if f["id"] == tid), None)

    def test_mac_sin_firmware_no_es_programada(self):
        t = iso.crear_par(self.lote, r3=True)
        self.assertFalse(programada_sql(t["id"]))
        inv.set_firmware(t["pcb_r3_id"], "1.0")   # firmware de la R3 no programa la tarjeta
        f = self.reporte(t["id"])
        self.assertFalse(f and f["programada"])
        inv.set_firmware(t["pcb_r1_id"], "3.0")
        self.assertFalse(programada_sql(t["id"]))   # falta la R2
        inv.set_firmware(t["pcb_r2_id"], "3.1.2")
        self.assertTrue(programada_sql(t["id"]))
        self.assertTrue(self.reporte(t["id"])["programada"])

    def test_firmware_heredado_de_la_tarjeta(self):
        t = iso.crear_par(self.lote)
        with db.get_db() as c:
            c.execute("UPDATE tarjetas_produccion SET firmware_r1='3.0', firmware_r2='3.0' WHERE id=?", (t["id"],))
        self.assertTrue(programada_sql(t["id"]))   # igual que la API (COALESCE con firmware_rN de la tarjeta)

    def test_espacios_no_cuentan(self):
        t = iso.crear_par(self.lote)
        with db.get_db() as c:
            c.execute("UPDATE pcb_inventario SET firmware='  ' WHERE id IN (?,?)", (t["pcb_r1_id"], t["pcb_r2_id"]))
        self.assertFalse(programada_sql(t["id"]))


if __name__ == "__main__":
    unittest.main()
