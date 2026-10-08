"""v1.3.43: escáner remoto (el celular se vincula a la consola con un QR) y estatus de la tarjeta en Consultar."""
import _aislamiento  # noqa: F401  (debe ser lo primero)
import unittest
from pathlib import Path
from unittest import mock

from app import main
from app.database import db
from app.main import app
from app.routers import escaner_remoto
from app.services import usuarios

from _aislamiento import cliente_sin_sesion, verificar_aislamiento

ADMIN = "developer@skyguardian.mx"
STATIC = Path(__file__).resolve().parent.parent / "app" / "static"


class TestEscanerRemoto(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        verificar_aislamiento()
        db.init_db()
        usuarios.sembrar(iteraciones=1000)

    def setUp(self):
        self.c = cliente_sin_sesion(app)
        self.c.cookies.set(usuarios.COOKIE, usuarios.emitir_sesion(ADMIN))
        self.eventos = []

        async def falso(ev, data=None):
            self.eventos.append((ev, data))
        p = mock.patch.object(escaner_remoto.manager, "broadcast", side_effect=falso)
        p.start(); self.addCleanup(p.stop)

    def test_01_flujo_completo(self):
        r = self.c.post("/api/escaner/sesion", json={"seccion": "macs", "titulo": "MAC y firmware"})
        self.assertEqual(r.status_code, 200, r.text)
        tok, sid = r.json()["token"], r.json()["id"]
        self.assertEqual(r.json()["ruta"], f"/escaner?s={tok}")
        u = self.c.post(f"/api/escaner/{tok}/unir").json()
        self.assertEqual((u["id"], u["titulo"], u["moviles"]), (sid, "MAC y firmware", 1))
        e = self.c.post(f"/api/escaner/{tok}/codigo", json={"codigo": " TQT-R1-V30-0021 "}).json()
        self.assertEqual(e["n"], 1)
        ev, data = self.eventos[-1]
        self.assertEqual((ev, data["id"], data["codigo"], data["n"]), ("ESCANEO_REMOTO", sid, "TQT-R1-V30-0021", 1))
        self.assertNotIn(tok, repr(self.eventos))   # el token (lo que permite enviar) nunca sale por WebSocket
        self.c.post(f"/api/escaner/{tok}/resultado", json={"n": 1, "ok": True, "texto": "ubicada"})
        self.assertEqual(self.eventos[-1][0], "ESCANER_RESULTADO")
        self.c.post(f"/api/escaner/{tok}/seccion", json={"seccion": "tarjetas", "titulo": "Tarjetas"})
        self.assertEqual(self.c.get(f"/api/escaner/{tok}").json()["titulo"], "Tarjetas")
        self.assertEqual(self.c.delete(f"/api/escaner/{tok}").status_code, 200)
        self.assertEqual(self.eventos[-1], ("ESCANER_CERRADO", {"id": sid}))
        self.assertEqual(self.c.post(f"/api/escaner/{tok}/codigo", json={"codigo": "x"}).status_code, 404)

    def test_02_token_falso_y_sin_sesion(self):
        self.assertEqual(self.c.post("/api/escaner/no-existe-123456/codigo", json={"codigo": "x"}).status_code, 404)
        anon = cliente_sin_sesion(app)
        self.assertEqual(anon.post("/api/escaner/sesion").status_code, 401)
        self.assertEqual(anon.get("/escaner", follow_redirects=False).status_code, 302)

    def test_03_caduca(self):
        tok = self.c.post("/api/escaner/sesion").json()["token"]
        escaner_remoto._sesiones[tok]["uso"] -= escaner_remoto.TTL_SEG + 1
        self.assertEqual(self.c.get(f"/api/escaner/{tok}").status_code, 404)

    def test_04_consultor_puede_usar_el_escaner(self):
        self.assertIsNone(main._permiso_rol("consultor", "/escaner", "GET"))
        self.assertIsNone(main._permiso_rol("consultor", "/api/escaner/abc/codigo", "POST"))
        self.assertIsNotNone(main._permiso_rol("consultor", "/api/tarjetas/1", "PATCH"))

    def test_05_frontend(self):
        esc = (STATIC / "js" / "escritorio.js").read_text(encoding="utf-8")
        for x in ("Botón de escaneo", "ESCANEO_REMOTO", "inst.escaneo", "/api/escaner/sesion", "fichaRapida"):
            self.assertIn(x, esc)
        self.assertIn("qrcode-generator.js", (STATIC / "monitor.html").read_text(encoding="utf-8"))
        self.assertIn("escaneo,", (STATIC / "js" / "sec_macs.js").read_text(encoding="utf-8"))
        com = (STATIC / "js" / "common.js").read_text(encoding="utf-8")
        self.assertIn("function estatusTarjeta", com)
        self.assertIn("'/escaner'", com)
        for f in ("consultar.js", "sec_consultar.js"):
            self.assertIn("T.estatusTarjeta(t", (STATIC / "js" / f).read_text(encoding="utf-8"))
        self.assertIn("Math.min(screen.width, screen.height) >= 700", (STATIC / "index.html").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()


class TestRespaldoHttpV1346(TestEscanerRemoto):
    """v1.3.46: códigos y resultados se pueden recuperar por HTTP; el nombre tolera 'PCB_TQT_R3_V2_0_TIMER_0073'."""

    def test_respaldo_http(self):
        tok = self.c.post("/api/escaner/sesion", json={"seccion": "macs", "titulo": "MAC y firmware"}).json()["token"]
        self.c.post(f"/api/escaner/{tok}/codigo", json={"codigo": "A"})
        self.c.post(f"/api/escaner/{tok}/seccion", json={"seccion": "dymo", "titulo": "Etiquetas DYMO"})
        e = self.c.post(f"/api/escaner/{tok}/codigo", json={"codigo": "B"}).json()
        self.assertEqual(e["titulo"], "Etiquetas DYMO")
        cs = self.c.get(f"/api/escaner/{tok}/codigos?desde=1").json()
        self.assertEqual([x["codigo"] for x in cs["items"]], ["B"])
        self.assertFalse(self.c.get(f"/api/escaner/{tok}/resultado/2").json()["listo"])
        self.c.post(f"/api/escaner/{tok}/resultado", json={"n": 2, "ok": True, "texto": "hecho"})
        r = self.c.get(f"/api/escaner/{tok}/resultado/2").json()
        self.assertEqual((r["listo"], r["ok"], r["texto"], r["titulo"]), (True, True, "hecho", "Etiquetas DYMO"))

    def test_nombre_tolerante(self):
        from app.database.models import parse_tarjeta_code as p
        self.assertEqual(p("PCB_TQT_R3_V2_0_TIMER_0073")["nombre"], "TQT-R3-V20-0073")
        self.assertEqual(p("TQT_R1_V30_0021")["nombre"], "TQT-R1-V30-0021")
        self.assertEqual(p("TQT-R1-V30-0021\n70:4b:ca:5b:9f:6e")["nombre"], "TQT-R1-V30-0021")
