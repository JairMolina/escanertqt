"""Desemparejar en masa y cambiar el tipo de una placa ya montada en una tarjeta."""
import _aislamiento  # noqa: F401  (debe ser lo primero)
import tempfile
import unittest
from pathlib import Path

from app.database import db, inventario as inv
from app.database.db import ConflictoError

from _aislamiento import verificar_aislamiento


class TestDesemparejar(unittest.TestCase):
    def setUp(self):
        verificar_aislamiento()
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "d.db"
        db.init_db(self.path)
        ids = []
        for s in ("0011", "0012", "0013"):
            for t in ("R1", "R2", "R3"):
                ids.append(inv.escanear_pcb(f"TQT-{t}-V30-{s}", db_path=self.path)["pcb"]["id"])
        inv.confirmar_recepcion(ids, db_path=self.path)
        self.lote = db.get_active_lote(db_path=self.path)["id"]
        self.creadas = inv.emparejar_auto(self.lote, r3_auto=True, db_path=self.path)["creadas"]

    def tearDown(self):
        self.tmp.cleanup()

    def pcbs(self, estado):
        return [p for p in inv.listar_pcb(db_path=self.path, limit=100)["items"] if p["estado_ciclo"] == estado]

    def test_desemparejar_todas(self):
        self.assertEqual(len(self.creadas), 3)
        r = inv.disolver_masivo(todas=True, lote_id=self.lote, db_path=self.path)
        self.assertEqual(len(r["disueltas"]), 3)
        self.assertEqual(r["liberadas"], 9)
        self.assertEqual(len(self.pcbs("DISPONIBLE")), 9)
        self.assertEqual(len(self.pcbs("ASIGNADA")), 0)

    def test_desemparejar_elegidas(self):
        r = inv.disolver_masivo(ids=[self.creadas[0]["id"]], db_path=self.path)
        self.assertEqual(len(r["disueltas"]), 1)
        self.assertEqual(len(self.pcbs("DISPONIBLE")), 3)

    def test_sin_objetivo_es_error(self):
        with self.assertRaises(ValueError):
            inv.disolver_masivo(db_path=self.path)

    def test_omite_con_pruebas_salvo_forzar(self):
        tid = self.creadas[0]["id"]
        with db.transaction(self.path) as c:
            c.execute("INSERT OR IGNORE INTO pruebas_historial (tarjeta_id) VALUES (?)", (tid,))
            c.execute("UPDATE pruebas_historial SET soldadura='OK' WHERE tarjeta_id=?", (tid,))
        r = inv.disolver_masivo(todas=True, lote_id=self.lote, db_path=self.path)
        self.assertEqual((len(r["disueltas"]), len(r["omitidas"])), (2, 1))
        r = inv.disolver_masivo(ids=[tid], forzar=True, db_path=self.path)
        self.assertEqual(len(r["disueltas"]), 1)

    def test_cambiar_tipo_montada_requiere_liberar(self):
        r1 = self.creadas[0]["r1"]
        with self.assertRaises(ConflictoError):
            inv.editar_pcb(r1["id"], tipo="R2", db_path=self.path)

    def test_cambiar_tipo_montada_con_liberar(self):
        r1 = self.creadas[0]["r1"]
        # 0011 R2 ya existe: choca y no se libera nada (todo o nada)
        with self.assertRaises(ConflictoError):
            inv.editar_pcb(r1["id"], tipo="R2", liberar=True, db_path=self.path)
        self.assertEqual(inv.get_pcb(r1["id"], db_path=self.path)["estado_ciclo"], "ASIGNADA")
        # con la serie corregida sí: sale de la tarjeta y queda DISPONIBLE con el tipo nuevo
        p = inv.editar_pcb(r1["id"], tipo="R2", serie="0099", liberar=True, db_path=self.path)
        self.assertEqual((p["tipo"], p["estado_ciclo"], p["tarjeta_id"]), ("R2", "DISPONIBLE", None))
        t = db.get_tarjeta_by_id(self.creadas[0]["id"], db_path=self.path)
        self.assertIsNone(t["r1"])


if __name__ == "__main__":
    unittest.main()
