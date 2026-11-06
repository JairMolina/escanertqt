"""v1.4.94: al terminar una prueba TQT se emite PRUEBA_TQT_TERMINADA y la vista recupera el resultado al volver."""
import _aislamiento  # noqa: F401  (debe ser lo primero)
import pathlib
import unittest
from unittest import mock

from app.routers import test_station as rt

RAIZ = pathlib.Path(__file__).resolve().parents[1] / "app" / "static" / "js"


class TestAvisoPruebaTQT(unittest.TestCase):
    def test_avisar_fin_emite_evento_con_operador_y_resultado(self):
        enviados = []
        class FalsoCm:
            @staticmethod
            def run(fn, *a): enviados.append(a)
        fila = {"run_id": "r1", "tarjeta_id": 5, "operator": "ana@x.com", "result": "aprobado", "origin": "agente", "id_tarjeta_num": "0005"}
        cur = mock.MagicMock(); cur.fetchone.return_value = fila
        con = mock.MagicMock(); con.__enter__.return_value.execute.return_value = cur
        with mock.patch.object(rt.db, "get_db", return_value=con), mock.patch.object(rt, "from_thread", FalsoCm):
            rt.avisar_fin_prueba("r1")
        self.assertEqual(len(enviados), 1)
        self.assertEqual(enviados[0][0], "PRUEBA_TQT_TERMINADA")
        self.assertEqual(enviados[0][1]["operator"], "ana@x.com")
        self.assertEqual(enviados[0][1]["result"], "aprobado")

    def test_aviso_no_rompe_si_falla_el_envio(self):
        with mock.patch.object(rt.db, "get_db", side_effect=RuntimeError("bd")):
            rt.avisar_fin_prueba("r1")   # no lanza

    def test_ui_cableada(self):
        com = (RAIZ / "common.js").read_text(encoding="utf-8")
        val = (RAIZ / "sec_validacion.js").read_text(encoding="utf-8")
        self.assertIn("PRUEBA_TQT_TERMINADA", com)
        self.assertIn("Ver e imprimir etiqueta", com)
        self.assertIn("recuperadas", val)
        self.assertIn("await finishRun(full)", val)


if __name__ == "__main__":
    unittest.main()
