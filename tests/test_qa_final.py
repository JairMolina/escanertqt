"""Regresiones de la verificación final (coordinador)."""
import _aislamiento  # noqa: F401  (debe ser lo primero)
import tempfile
import unittest
from pathlib import Path

from app.database import db, inventario as inv
from app.services.excel_sync import ExcelSyncEngine

from _aislamiento import verificar_aislamiento


class TestVerificacionFinal(unittest.TestCase):
    def setUp(self):
        verificar_aislamiento()
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "f.db"
        db.init_db(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_confirmar_con_lista_vacia_no_confirma_nada(self):
        """ids=[] (error del cliente) NO debe confirmar el borrador; solo 'sin ids' confirma todo."""
        for n in ("0001", "0002"):
            inv.escanear_pcb(f"TQT-R1-V30-{n}", db_path=self.path)
        r = inv.confirmar_recepcion(ids=[], db_path=self.path)
        self.assertEqual(len(r.get("ids", [])), 0)
        self.assertEqual(inv.listar_recepcion(db_path=self.path)["conteos"]["total"], 2)  # siguen en borrador
        r = inv.confirmar_recepcion(ids=None, db_path=self.path)
        self.assertEqual(len(r["ids"]), 2)

    def test_plantilla_ausente_no_cae_al_excel_del_escritorio(self):
        eng = ExcelSyncEngine(db_path=self.path)
        eng.template_path = Path(self.tmp.name) / "no_existe.xlsx"
        with self.assertRaises(FileNotFoundError):
            eng.get_template_path()


if __name__ == "__main__":
    unittest.main()
