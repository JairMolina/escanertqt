"""Etiquetas DYMO: zona «Cable» restaurada y botón «Imprimir como aprobada» en Tarjetas."""
import pathlib
import unittest

RAIZ = pathlib.Path(__file__).resolve().parents[1] / "app" / "static"


class DymoCableAprobadaUi(unittest.TestCase):
    def setUp(self):
        self.html = (RAIZ / "dymo_preview.html").read_text(encoding="utf-8")
        self.js = (RAIZ / "js" / "dymo.js").read_text(encoding="utf-8")

    def test_zona_cable_restaurada(self):
        for ident in ('data-zona="cable"', 'id="cableBox"', 'id="btnCablePrint"', 'id="cableDesde"'):
            self.assertIn(ident, self.html)
        self.assertIn("cableNumeros", self.js)

    def test_boton_aprobada(self):
        self.assertIn('id="btnPrintAprob"', self.html)
        self.assertIn("Imprimir como aprobada", self.html)
        self.assertIn("tipo: aprobada ? 'aprobada' : 'tarjeta'", self.js)
        self.assertIn("&aprobada=true", self.js)


if __name__ == "__main__":
    unittest.main()
