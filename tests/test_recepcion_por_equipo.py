"""v1.1.5: cada equipo (marca anónima X-Cliente) ve, cuenta y confirma solo SU lote de recepción."""
import _aislamiento  # noqa: F401  (debe ser lo primero)
import tempfile
import unittest
from pathlib import Path

from app.database import db, inventario as inv

from _aislamiento import verificar_aislamiento


class TestRecepcionPorEquipo(unittest.TestCase):
    def setUp(self):
        verificar_aislamiento()
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "eq.db"
        db.init_db(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_lotes_separados_y_confirmar_solo_el_propio(self):
        for n in (1, 2, 3):
            inv.escanear_pcb(f"TQT-R1-V30-000{n}", db_path=self.path, sesion="A")
        for n in (4, 5):
            inv.escanear_pcb(f"TQT-R2-V30-000{n}", db_path=self.path, sesion="B")
        a = inv.listar_recepcion(db_path=self.path, sesion="A")
        b = inv.listar_recepcion(db_path=self.path, sesion="B")
        self.assertEqual((a["conteos"]["total"], b["conteos"]["total"]), (3, 2))
        self.assertEqual({p["tipo"] for p in b["items"]}, {"R2"})
        # Sin marca (API directa) sigue viendo todo el borrador.
        self.assertEqual(inv.listar_recepcion(db_path=self.path)["conteos"]["total"], 5)

        r = inv.confirmar_recepcion(db_path=self.path, sesion="A")
        self.assertEqual(r["confirmadas"], 3)
        self.assertEqual(inv.listar_recepcion(db_path=self.path, sesion="B")["conteos"]["total"], 2)
        self.assertEqual(inv.listar_recepcion(db_path=self.path, sesion="A")["conteos"]["total"], 0)

    def test_manual_y_duplicado_respetan_la_marca(self):
        inv.registrar_manual("R1", cantidad=2, db_path=self.path, sesion="A")
        self.assertEqual(inv.listar_recepcion(db_path=self.path, sesion="B")["conteos"]["total"], 0)
        dup = inv.escanear_pcb("TQT-R1-V30-0001", db_path=self.path, sesion="B")
        self.assertEqual(dup["resultado"], "DUPLICADA")
        self.assertEqual(dup["conteos"]["total"], 0)


if __name__ == "__main__":
    unittest.main()
