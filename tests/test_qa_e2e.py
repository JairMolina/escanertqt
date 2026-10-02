"""QA E2E/UX del frontend: comprobaciones que corren SIN navegador (HTML/CSS/JS estáticos y páginas servidas).
Las pruebas con Chrome real (recorrido, axe, latencia, robustez) están en tests/e2e/ (ver su README)."""
import _aislamiento  # noqa: F401  (debe ser lo primero)
import json
import re
import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.database import db
from app.main import app

STATIC = Path(__file__).resolve().parent.parent / "app" / "static"
sys.path.insert(0, str(Path(__file__).resolve().parent / "e2e"))
import contraste  # noqa: E402

PAGINAS = {"/": "index.html", "/emparejar": "emparejar.html", "/programar": "programar.html", "/consultar": "consultar.html",
           "/monitor": "monitor.html", "/dymo": "dymo_preview.html", "/admin": "admin.html"}


def leer(nombre):
    return (STATIC / nombre).read_text(encoding="utf-8")


class TestContrasteTokens(unittest.TestCase):
    def test_tokens_cumplen_aa_en_ambos_temas(self):
        # accent sobre bg (2.5) es solo decorativo (marco del visor); el texto de acento usa accent-text.
        fallos = [f"{t} {fg}/{bg}={r} < {m}" for t, fg, bg, r, m in contraste.calcular() if r < m and fg != "accent"]
        self.assertEqual(fallos, [])

    def test_texto_atenuado_legible(self):
        # regresión: --faint (claro) era 3.1:1 sobre el fondo y se usa para texto real (hora del feed, ranuras vacías)
        for tema, fg, bg, r, m in contraste.calcular():
            if fg == "faint":
                self.assertGreaterEqual(r, 4.5, (tema, bg, r))


class TestPaginasEstaticas(unittest.TestCase):
    def test_metadatos_por_pagina(self):
        titulos = set()
        for ruta, f in PAGINAS.items():
            h = leer(f)
            self.assertIn('<html lang="es">', h, ruta)
            self.assertRegex(h, r'<meta name="viewport" content="width=device-width, initial-scale=1', ruta)
            self.assertRegex(h, r'<link rel="icon"', ruta)
            self.assertRegex(h, r'<link rel="manifest"', ruta)
            self.assertRegex(h, r'<link rel="apple-touch-icon"', ruta)
            t = re.search(r"<title>(.*?)</title>", h).group(1)
            self.assertTrue(t.strip() and "Escáner TQT" in t, (ruta, t))
            titulos.add(t)
            self.assertGreaterEqual(len(re.findall(r"<h1[ >]", h)), 1, f"{ruta}: falta <h1> (puede ser sr-only)")
        self.assertEqual(len(titulos), len(PAGINAS), "cada página debe tener su propio <title>")

    def test_sin_recursos_externos(self):
        """Todo local: ni CDN ni fuentes remotas en HTML, CSS y JS propios (jsQR/qrcode/DYMO vendorizados)."""
        ext = re.compile(r"""(?:src|href)=["']https?://|url\(\s*["']?https?://|@import\s+url\(\s*["']?https?://|fetch\(\s*["']https?://""")
        for f in list(STATIC.glob("*.html")) + [STATIC / "css" / "app.css"] + [p for p in (STATIC / "js").glob("*.js")]:
            self.assertIsNone(ext.search(f.read_text(encoding="utf-8", errors="ignore")), f"recurso externo en {f.name}")

    def test_referencias_locales_existen(self):
        for f in STATIC.glob("*.html"):
            for ref in re.findall(r'(?:src|href)="(/static/[^"?#]+)', f.read_text(encoding="utf-8")):
                self.assertTrue((STATIC.parent.parent / ref.lstrip("/").replace("static/", "app/static/", 1)).exists(), f"{f.name}: {ref}")
        css = (STATIC / "css" / "app.css").read_text(encoding="utf-8")
        for ref in re.findall(r'url\("(/static/[^"]+)"\)', css):
            self.assertTrue((STATIC.parent.parent / ref.lstrip("/").replace("static/", "app/static/", 1)).exists(), ref)

    def test_sin_dialogos_nativos(self):
        """Criterio de diseño: hojas propias en pantalla, nunca confirm()/alert()/prompt()."""
        pat = re.compile(r"(?<![\w.])(?:window\.)?(?:confirm|alert|prompt)\(")
        for p in (STATIC / "js").glob("*.js"):
            if p.name in ("jsQR.js", "qrcode-generator.js"):
                continue
            for i, linea in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                if linea.lstrip().startswith(("//", "*", "/*")):
                    continue
                self.assertIsNone(pat.search(linea), f"{p.name}:{i}: {linea.strip()[:80]}")

    def test_botones_sin_rol_listitem(self):
        """role=listitem sobre <button> anula la semántica de botón para lectores de pantalla."""
        for p in (STATIC / "js").glob("*.js"):
            for i, linea in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                if "h('button'" in linea and "role: 'listitem'" in linea:
                    self.fail(f"{p.name}:{i}: button con role listitem")

    def test_resultados_de_escaneo_con_aria_live(self):
        self.assertRegex(leer("index.html"), r'id="readout"[^>]*aria-live="polite"')
        self.assertRegex(leer("programar.html"), r'id="activo"[^>]*aria-live="polite"')
        self.assertRegex(leer("consultar.html"), r'id="ficha"[^>]*aria-live="polite"')

    def test_reduced_motion_y_focus(self):
        css = (STATIC / "css" / "app.css").read_text(encoding="utf-8")
        self.assertIn("prefers-reduced-motion: reduce", css)
        self.assertIn(":focus-visible", css)

    def test_objetivos_tactiles_minimos(self):
        css = (STATIC / "css" / "app.css").read_text(encoding="utf-8")
        for regla in (r"\.btn-sm \{ min-height: 4[4-9]px", r"\.iconbtn \{[^}]*width: 4[4-9]px; height: 4[4-9]px",
                      r"\.visor \.status \{[^}]*min-height: 4[4-9]px", r"\.desk-nav a, \.desk-nav button \{ min-height: 4[4-9]px"):
            self.assertRegex(css, regla)

    def test_manifest_y_iconos(self):
        m = json.loads((STATIC / "icons" / "manifest.webmanifest").read_text(encoding="utf-8"))
        self.assertEqual(m["lang"], "es")
        self.assertIn(m["display"], ("standalone", "fullscreen", "minimal-ui"))
        tallas = {i["sizes"] for i in m["icons"]}
        self.assertTrue({"192x192", "512x512"} <= tallas)
        for i in m["icons"]:
            self.assertTrue((STATIC.parent.parent / i["src"].lstrip("/").replace("static/", "app/static/", 1)).exists(), i["src"])


class TestPaginasServidas(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init_db()
        cls.client = TestClient(app)

    def test_paginas_y_favicon_200(self):
        for ruta in list(PAGINAS) + ["/favicon.ico", "/static/icons/favicon.svg", "/static/icons/manifest.webmanifest",
                                     "/static/icons/apple-touch-icon.png", "/static/emparejar.html", "/static/programar.html"]:
            r = self.client.get(ruta)
            self.assertEqual(r.status_code, 200, ruta)

    def test_pestanas_inferiores_apuntan_a_paginas_reales(self):
        js = (STATIC / "js" / "common.js").read_text(encoding="utf-8")
        for href in re.findall(r"href: '(/[^']*)', label", js):
            self.assertEqual(self.client.get(href).status_code, 200, href)

    def test_frontend_pide_limites_que_la_api_acepta(self):
        """Regresión: monitor/admin/recibir pedían /api/pcb?limit=5000 y la API respondía 422 (inventario vacío en pantalla)."""
        limites = set()
        for p in (STATIC / "js").glob("*.js"):
            limites |= set(re.findall(r"/api/pcb\?[^'`\"]*limit=(\d+)", p.read_text(encoding="utf-8")))
        self.assertTrue(limites)
        for lim in limites:
            self.assertEqual(self.client.get(f"/api/pcb?limit={lim}").status_code, 200, f"limit={lim}")

    def test_gzip_en_estaticos_grandes(self):
        r = self.client.get("/static/js/jsQR.js", headers={"Accept-Encoding": "gzip"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers.get("content-encoding"), "gzip")
        self.assertIn("no-cache", r.headers.get("cache-control", ""))


if __name__ == "__main__":
    unittest.main()
