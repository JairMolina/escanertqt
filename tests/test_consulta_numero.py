"""Consultar por número de tarjeta / de serie (sin escanear)."""
import _aislamiento  # noqa: F401  (debe ser lo primero)
import tempfile
import unittest
from pathlib import Path

from app.database import db, inventario as inv
from app.database.db import NoEncontradoError

from _aislamiento import verificar_aislamiento


class TestConsultaNumero(unittest.TestCase):
    def setUp(self):
        verificar_aislamiento()
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "c.db"
        db.init_db(self.path)
        ids = [inv.escanear_pcb(f"TQT-{t}-V30-{s}", db_path=self.path)["pcb"]["id"]
               for s, t in (("0011", "R1"), ("0011", "R2"), ("0011", "R3"), ("0021", "R1"), ("0030", "R2"), ("0030", "R3"))]
        inv.confirmar_recepcion(ids, db_path=self.path)
        self.lote = db.get_active_lote(db_path=self.path)["id"]
        inv.emparejar_auto(self.lote, ["0011"], r3_auto=True, db_path=self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_numero_de_tarjeta_con_o_sin_ceros(self):
        for txt in ("0011", "11", "#11", " 11 "):
            d = inv.consulta(txt, db_path=self.path)
            self.assertEqual((d["origen"], d["tarjeta"]["id_tarjeta_num"]), ("tarjeta", "0011"), txt)
            self.assertEqual(d["tarjeta"]["r3"]["nombre"], "TQT-R3-V30-0011")

    def test_numero_sin_tarjeta_muestra_las_placas_de_esa_serie(self):
        d = inv.consulta("30", db_path=self.path)
        self.assertEqual((d["origen"], d["tarjeta"], d["serie"]["numero"]), ("serie", None, "0030"))
        self.assertIsNone(d["serie"]["r1"])
        self.assertEqual((d["serie"]["r2"]["nombre"], d["serie"]["r3"]["nombre"]), ("TQT-R2-V30-0030", "TQT-R3-V30-0030"))
        self.assertTrue(any("Todavía no hay una tarjeta" in a for a in d["avisos"]))

    def test_numero_inexistente_o_invalido(self):
        with self.assertRaises(NoEncontradoError):
            inv.consulta("0999", db_path=self.path)
        with self.assertRaises(ValueError):
            inv.consulta("123456", db_path=self.path)

    def test_lo_que_ya_funcionaba_sigue_igual(self):
        self.assertEqual(inv.consulta("TQT-R1-V30-0021", db_path=self.path)["origen"], "pcb")


if __name__ == "__main__":
    unittest.main()
