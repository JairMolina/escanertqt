"""v1.4.96: las R3 entregadas antes de v1.4.94 con prueba TQT aprobada (o con advertencias) pasan a «Aprobada» una sola vez;
las fallidas y sin prueba no; y la etiqueta «Aprobada» de la tarjeta se emite también con advertencias."""
import _aislamiento  # noqa: F401  (debe ser lo primero)
import unittest

from app.database import db
from app.main import app
from app.services import usuarios

from _aislamiento import cliente_sin_sesion, verificar_aislamiento
from test_r3_aprobada_finalizada import TestR3AprobadaFinalizada as _Base

CLAVE = "r3_aprobadas_anteriores_v1_4_96"


class TestR3Anteriores(_Base):
    def _r3(self, r3):
        with db.get_db() as c:
            return c.execute("SELECT aprobada, aprobada_por FROM pcb_inventario WHERE id=?", (r3,)).fetchone()

    def _migrar(self):
        with db.get_db() as c:
            c.execute("DELETE FROM ajustes WHERE clave=?", (CLAVE,))
            db._aprobar_r3_anteriores(c)

    def test_backfill_solo_aprobadas_y_una_vez(self):
        casos = {}
        for res in ("aprobado", "aprobado_con_advertencias", "fallido", "no_verificado", None):
            tid, _, _, r3 = self._tarjeta()
            if res:
                self._prueba_tqt(tid, res)
            casos[res] = r3
        tid, _, _, r3_sinfw = self._tarjeta(fw_r3=None)
        self._prueba_tqt(tid, "aprobado")
        self._migrar()
        for res, r3 in casos.items():
            esperado = res in ("aprobado", "aprobado_con_advertencias")
            self.assertEqual(bool(self._r3(r3)["aprobada"]), esperado, res)
        self.assertEqual(self._r3(casos["aprobado"])["aprobada_por"], "migración v1.4.96")
        self.assertFalse(self._r3(r3_sinfw)["aprobada"], "sin firmware no se aprueba")
        # desaprobar a mano y volver a arrancar: no se re-aprueba
        with db.get_db() as c:
            c.execute("UPDATE pcb_inventario SET aprobada=0 WHERE id=?", (casos["aprobado"],))
            db._aprobar_r3_anteriores(c)
        self.assertFalse(self._r3(casos["aprobado"])["aprobada"])

    def test_etiqueta_tarjeta_con_advertencias(self):
        tid, _, _, _ = self._tarjeta()
        self._prueba_tqt(tid, "aprobado_con_advertencias")
        r = self.c.get(f"/api/dymo/label/{tid}/xml", params={"aprobada": "true", "tipo": "label"})
        self.assertEqual(r.status_code, 200, r.text)
        tid2, _, _, _ = self._tarjeta()
        self._prueba_tqt(tid2, "fallido")
        self.assertEqual(self.c.get(f"/api/dymo/label/{tid2}/xml", params={"aprobada": "true"}).status_code, 403)

    def test_r3_migrada_imprime_aprobada(self):
        tid, _, _, r3 = self._tarjeta()
        self._prueba_tqt(tid, "aprobado")
        self._migrar()
        nombre = db.get_tarjeta_by_id(tid)["r3"]["nombre"]
        r = self.c.get("/api/dymo/r3/xml", params={"nombre": nombre, "aprobada": "true", "tipo": "label"})
        self.assertEqual(r.status_code, 200, r.text)


# la clase base trae sus propias pruebas: no las repitas aquí
for _n in [n for n in dir(_Base) if n.startswith("test_")]:
    setattr(TestR3Anteriores, _n, None)

if __name__ == "__main__":
    unittest.main()
