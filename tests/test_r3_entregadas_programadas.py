"""v1.4.99: las R3 de tarjetas ya entregadas que quedaron «Sin programar» (anteriores al registro de firmware R3) pasan a programadas una sola vez."""
import _aislamiento  # noqa: F401  (debe ser lo primero)
import itertools
import unittest

from app.database import db

from test_r3_aprobada_finalizada import TestR3AprobadaFinalizada as _Base

CLAVE = "r3_programadas_entregadas_v1_4_99"


class TestR3Entregadas(_Base):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        g = _Base._tarjeta.__globals__
        cls._serie_previa = g['_serie']
        g['_serie'] = itertools.count(9984)   # rango propio (la MAC sale de serie % 256)

    @classmethod
    def tearDownClass(cls):
        _Base._tarjeta.__globals__['_serie'] = cls._serie_previa   # no afecta a las pruebas de la clase base
        super().tearDownClass()

    def _r3(self, tid):
        with db.get_db() as c:
            return c.execute("SELECT p.firmware, p.aprobada, p.aprobada_por FROM tarjetas_produccion t JOIN pcb_inventario p ON p.id=t.pcb_r3_id WHERE t.id=?", (tid,)).fetchone()

    def _entregar(self, tid):
        with db.get_db() as c:
            c.execute("UPDATE tarjetas_produccion SET fecha_real='2026-10-05' WHERE id=?", (tid,))

    def _migrar(self):
        with db.get_db() as c:
            c.execute("DELETE FROM ajustes WHERE clave=?", (CLAVE,))
            db._programar_r3_entregadas(c)

    def test_entregadas_sin_firmware_quedan_programadas_y_una_vez(self):
        t_ok, _, _, _ = self._tarjeta(fw_r3=None); self._entregar(t_ok); self._prueba_tqt(t_ok, "aprobado")
        t_adv, _, _, _ = self._tarjeta(fw_r3=None); self._entregar(t_adv); self._prueba_tqt(t_adv, "aprobado_con_advertencias")
        t_fail, _, _, _ = self._tarjeta(fw_r3=None); self._entregar(t_fail); self._prueba_tqt(t_fail, "fallido")
        t_sin, _, _, _ = self._tarjeta(fw_r3=None); self._prueba_tqt(t_sin, "aprobado")   # NO entregada
        t_fw, _, _, _ = self._tarjeta(fw_r3="1.1"); self._entregar(t_fw)                  # ya tenía firmware
        self._migrar()
        for t in (t_ok, t_adv, t_fail):
            self.assertEqual(self._r3(t)["firmware"], db.SIN_DATO_FW)
            self.assertTrue(db.get_tarjeta_by_id(t)["r3"]["programada"])
        self.assertTrue(self._r3(t_ok)["aprobada"] and self._r3(t_adv)["aprobada"])
        self.assertFalse(self._r3(t_fail)["aprobada"])
        self.assertFalse(self._r3(t_sin)["firmware"], "no entregada: no se toca")
        self.assertEqual(self._r3(t_fw)["firmware"], "1.1", "no pisa un firmware existente")
        # una vez: quitar la programación a mano y volver a arrancar no la repone
        with db.get_db() as c:
            c.execute("UPDATE pcb_inventario SET firmware=NULL, aprobada=0 WHERE id=(SELECT pcb_r3_id FROM tarjetas_produccion WHERE id=?)", (t_ok,))
            db._programar_r3_entregadas(c)
        self.assertFalse(self._r3(t_ok)["firmware"])

    def test_finaliza_con_r3_migrada(self):
        t, _, _, _ = self._tarjeta(fw_r3=None); self._entregar(t); self._skytec(t); self._prueba_tqt(t, "aprobado")
        self.assertFalse(db.get_tarjeta_by_id(t)["finalizada"])
        self._migrar()
        x = db.get_tarjeta_by_id(t)
        self.assertTrue(x["finalizada"])
        self.assertEqual(x["faltantes"], [])


for _n in [n for n in dir(_Base) if n.startswith("test_")]:
    setattr(TestR3Entregadas, _n, None)

if __name__ == "__main__":
    unittest.main()
