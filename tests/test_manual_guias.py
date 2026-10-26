"""v1.4.39: el manual de usuario sigue a los módulos.

- Cada módulo de la plataforma tiene su guía en el índice (salvo la propia Documentación).
- Cada guía es válida: sus capturas existen y sus marcas caen dentro de la imagen.
- docs/manual/*.md están al día con las guías (si falla: python scripts/generar_manual_md.py).
"""
import json
import sys
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "scripts"))

import _aislamiento  # noqa: E402,F401  (BD de pruebas aislada antes de importar la app)
import generar_manual_md as gen  # noqa: E402
from app import modulos  # noqa: E402

SIN_GUIA = {"documentacion-hw"}   # el manual vive dentro de este módulo


def _id(m):
    return m["id"] if isinstance(m, dict) else m.id


class TestManualGuias(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.idx = json.loads((gen.GUIAS / "indice.json").read_text(encoding="utf-8"))
        cls.ids = [g["id"] for g in cls.idx["guias"]]

    def test_01_cada_modulo_tiene_guia(self):
        faltan = [_id(m) for m in modulos.MODULOS if _id(m) not in SIN_GUIA and _id(m) not in self.ids]
        self.assertEqual(faltan, [], "Módulos sin guía en guias/indice.json")

    def test_02_guias_validas(self):
        self.assertEqual(len(self.ids), len(set(self.ids)), "ids repetidos en el índice")
        for gid in self.ids:
            with self.subTest(guia=gid):
                g = json.loads((gen.GUIAS / f"{gid}.json").read_text(encoding="utf-8"))
                self.assertEqual(g["id"], gid)
                caps = []
                for s in g["secciones"]:
                    caps += [s["captura"]] if s.get("captura") else []
                    caps += [p["captura"] for p in s.get("pasos") or [] if p.get("captura")]
                for c in caps:
                    self.assertTrue((gen.DOC / c["src"]).is_file(), c["src"])
                    for m in c.get("marcas") or []:
                        self.assertLessEqual(m["x"] + m["w"], 100.01, (c["src"], m))
                        self.assertLessEqual(m["y"] + m["h"], 100.01, (c["src"], m))
                for r in g.get("relacionadas") or []:
                    self.assertIn(r, self.ids, f"relacionada inexistente: {r}")

    def test_03_md_al_dia(self):
        dif = gen.diferencias(gen.generar())
        self.assertEqual(dif, [], "docs/manual desactualizado: corre python scripts/generar_manual_md.py")


class TestDocumentacionPublica(unittest.TestCase):
    """v1.4.39: Documentación TEAM HW se ve sin sesión; nada más se abre."""
    @classmethod
    def setUpClass(cls):
        from _aislamiento import cliente_sin_sesion
        from app.main import app
        cls.c = cliente_sin_sesion(app)

    def test_publico_sin_sesion(self):
        for ruta in ("/documentacion", "/documentacion/manual", "/static/documentacion/guias/indice.json",
                     "/static/documentacion/documentacion.js", "/static/documentacion/img/pcb-hero.jpg"):
            with self.subTest(ruta=ruta):
                self.assertEqual(self.c.get(ruta, follow_redirects=False).status_code, 200)

    def test_lo_demas_sigue_cerrado(self):
        for ruta in ("/api/config", "/api/status", "/api/tpms/placas", "/static/js/common.js", "/static/documentacion/../index.html"):
            with self.subTest(ruta=ruta):
                self.assertIn(self.c.get(ruta, follow_redirects=False).status_code, (302, 303, 307, 401, 403, 404))
        for ruta in ("/tpms", "/monitor", "/impresora", "/caiquen"):
            with self.subTest(ruta=ruta):
                self.assertIn(self.c.get(ruta, follow_redirects=False).status_code, (302, 303, 307))

    def test_no_se_sale_de_la_carpeta_publica(self):
        """'..' (crudo o %2e%2e / %2f) no debe llegar a /static fuera de los prefijos públicos."""
        for ruta in ("/static/documentacion/../js/common.js", "/static/documentacion/%2e%2e/js/common.js",
                     "/static/documentacion/..%2fjs/common.js", "/static/css/../index.html", "/static/css/..%5cindex.html"):
            with self.subTest(ruta=ruta):
                r = self.c.get(ruta, follow_redirects=False)
                self.assertNotEqual(r.status_code, 200)
                self.assertNotIn("function", r.text[:2000])

    def test_portal_lo_marca_publico(self):
        m = next(x for x in self.c.get("/api/modulos").json()["modulos"] if x["id"] == "documentacion-hw")
        self.assertTrue(m["publico"])
        self.assertTrue(m["permitido"])


if __name__ == "__main__":
    unittest.main()
