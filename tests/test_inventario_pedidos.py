"""v1.3.68: pedidos de material en Stock mínimo (Comprar → Comprado → ¿llegó?)."""
import _aislamiento  # noqa: F401  (debe ser lo primero)
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from app.database.db import ConflictoError
from app.services import inventario_tqtr as svc
from _aislamiento import verificar_aislamiento


class TestPedidos(unittest.TestCase):
    def setUp(self):
        verificar_aislamiento()
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "inv.db"
        st = svc.stock_minimo(db_path=self.path)
        self.x = st["items"][0]
        svc.editar_stock_minimo(self.x["id"], {"entrega_dias": 10}, db_path=self.path)

    def tearDown(self):
        svc._reiniciar_cache()
        self.tmp.cleanup()

    def item(self):
        return next(i for i in svc.stock_minimo(db_path=self.path)["items"] if i["id"] == self.x["id"])

    def test_pedido_cuenta_regresiva_y_llegada(self):
        p = svc.crear_pedido(self.x["id"], {"cantidad": 5}, "a@b.c", db_path=self.path)
        self.assertEqual((p["llegada"], p["dias_restantes"]), ((date.today() + timedelta(days=10)).isoformat(), 10))
        with self.assertRaises(ConflictoError):
            svc.crear_pedido(self.x["id"], {"cantidad": 1}, db_path=self.path)
        svc.editar_pedido(p["id"], {"llegada": date.today().isoformat()}, db_path=self.path)
        self.assertEqual(self.item()["pedido"]["dias_restantes"], 0)
        self.assertIn(self.x["id"], [i["id"] for i in svc.stock_minimo(db_path=self.path)["llegadas"]])
        svc.recibir_pedido(p["id"], False, {}, db_path=self.path)   # no llegó → +7 días
        self.assertEqual(self.item()["pedido"]["dias_restantes"], 7)
        antes = self.item()["disponible"]
        svc.recibir_pedido(p["id"], True, {}, db_path=self.path)    # llegó → entrada al stock
        it = self.item()
        self.assertIsNone(it["pedido"])
        self.assertAlmostEqual(it["disponible"], antes + 5)


if __name__ == "__main__":
    unittest.main()
