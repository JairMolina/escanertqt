"""v1.4.98: `faltantes` por placa en la tarjeta (qué falta para FINALIZADA) y `r3.programada`; la R3 solo es «programada» y «aprobada»."""
import _aislamiento  # noqa: F401  (debe ser lo primero)
import itertools
import unittest

from app.database import db

from test_r3_aprobada_finalizada import TestR3AprobadaFinalizada as _Base


def _pares(t):
    return {(f["placa"], f["motivo"]) for f in t["faltantes"]}


class TestFaltantes(_Base):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        _Base._tarjeta.__globals__['_serie'] = itertools.count(9600)   # rango propio: evita choques con la prueba base cargada dos veces

    def test_r3_sin_programar_y_sin_prueba(self):
        tid, _, _, _ = self._tarjeta(fw_r3=None)
        t = db.get_tarjeta_by_id(tid)
        self.assertIn(("R3", "sin_programar"), _pares(t))
        self.assertIn(("R1 y R2", "sin_skytec"), _pares(t))
        self.assertIn(("TARJETA", "sin_prueba_tqt"), _pares(t))
        self.assertNotIn(("R1", "sin_mac"), _pares(t))
        self.assertFalse(t["r3"]["programada"])

    def test_sin_mac_se_atribuye_a_r1_y_r2(self):
        tid, _, _, _ = self._tarjeta(mac_ok=False)
        p = _pares(db.get_tarjeta_by_id(tid))
        self.assertIn(("R1", "sin_mac"), p)
        self.assertIn(("R2", "sin_mac"), p)
        self.assertNotIn(("R3", "sin_mac"), p)   # la R3 no lleva MAC

    def test_r3_aprobada_no_es_requisito_y_finalizada_no_tiene_faltantes(self):
        tid, _, _, r3 = self._tarjeta()
        self._skytec(tid)
        self._prueba_tqt(tid, "aprobado")
        t = db.get_tarjeta_by_id(tid)
        self.assertTrue(t["finalizada"])
        self.assertEqual(t["faltantes"], [])
        self.assertTrue(t["r3"]["programada"])
        self.assertFalse(t["r3"]["aprobada"])


for _n in [n for n in dir(_Base) if n.startswith("test_")]:
    setattr(TestFaltantes, _n, None)

if __name__ == "__main__":
    unittest.main()
