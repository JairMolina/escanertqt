"""Movimientos de /admin (docs/qa/ADMIN_MOVIMIENTOS.md): API de consulta, registro de eventos y comprobaciones estáticas de la pantalla.
Las pruebas de navegador viven en tests/e2e/admin_mov*.py."""
import _aislamiento  # noqa: F401  (debe ser lo primero)
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from app.config import settings
from app.database import db
from app.main import app
from app.services import admin_auth

from _aislamiento import crear_par, verificar_aislamiento

CLAVE = "ClaveQA-12345"
RAIZ = Path(__file__).resolve().parent.parent
JS = (RAIZ / "app" / "static" / "js" / "admin.js").read_text(encoding="utf-8")
HTML = (RAIZ / "app" / "static" / "admin.html").read_text(encoding="utf-8")


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        verificar_aislamiento()
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls._db_previa, cls._bk_previo = settings.DB_PATH, settings.BACKUP_DIR
        settings.DB_PATH = Path(cls.tmp.name) / "mov.db"
        settings.BACKUP_DIR = Path(cls.tmp.name) / "bk"
        cls._parches = [mock.patch.dict(os.environ, {"TQT_ADMIN_PASSWORD": CLAVE}),
                        mock.patch.object(settings, "ADMIN_RETARDO_MS", 0), mock.patch.object(settings, "ADMIN_PBKDF2_ITER", 1000)]
        for p in cls._parches:
            p.start()
        db.init_db()
        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)
        for p in reversed(cls._parches):
            p.stop()
        settings.DB_PATH, settings.BACKUP_DIR = cls._db_previa, cls._bk_previo
        cls.tmp.cleanup()

    def setUp(self):
        admin_auth.limitador.reiniciar()
        with db.transaction() as c:
            c.execute("DELETE FROM ajustes WHERE clave LIKE 'admin_%'")
            c.execute("DELETE FROM escaneos")
        self.client.cookies.clear()
        r = self.client.post("/api/admin/login", json={"password": CLAVE})
        self.assertEqual(r.status_code, 200, r.text)
        self.H = {"X-Admin-Token": r.json()["token"]}
        self.client.cookies.clear()

    def mov(self, **q):
        r = self.client.get("/api/admin/movimientos", params=q, headers=self.H)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def eventos(self):
        return [m["evento"] for m in self.mov(limite=200)["items"]]


class TestConsulta(Base):
    def test_sin_token_401_y_token_basura_401(self):
        self.assertEqual(self.client.get("/api/admin/movimientos").status_code, 401)
        self.assertEqual(self.client.get("/api/admin/movimientos", headers={"X-Admin-Token": "x.y"}).status_code, 401)

    def test_categorias_conteo_y_filtro(self):
        for ev in ("PCB_ALTA", "PCB_ALTA", "MAC_GUARDADA", "PCB_ELIMINADA", "EXCEL_EXPORTADO", "EVENTO_RARO"):
            db.log_evento(ev, None, "v", "d", "op")
        d = self.mov(limite=200)
        self.assertEqual(set(d["categorias"]), {"alta", "edicion", "eliminacion", "sesion", "excel", "otro"})
        self.assertEqual((d["conteo"]["alta"], d["conteo"]["edicion"], d["conteo"]["eliminacion"], d["conteo"]["excel"], d["conteo"]["otro"]), (2, 1, 1, 1, 1))
        self.assertEqual(d["conteo"]["sesion"], 1)   # el login del setUp
        for cat, n in (("alta", 2), ("edicion", 1), ("eliminacion", 1), ("excel", 1), ("otro", 1), ("sesion", 1)):
            with self.subTest(cat=cat):
                f = self.mov(categoria=cat)
                self.assertEqual(f["total"], n)
                self.assertTrue(all(m["categoria"] == cat for m in f["items"]))
        # el conteo por categoría no depende de la categoría elegida (para pintar los contadores)
        self.assertEqual(self.mov(categoria="alta")["conteo"], d["conteo"])
        self.assertEqual(self.mov(categoria="otro")["items"][0]["titulo"], "Evento raro")

    def test_orden_mas_reciente_primero_y_campos(self):
        db.log_evento("PCB_ALTA", None, "TQT-R1-V30-0001", "QR", "Ana")
        db.log_evento("MAC_GUARDADA", None, "TQT-R1-V30-0001", "70:4B:CA:5B:00:01", "Beto")
        it = self.mov()["items"]
        self.assertEqual(it[0]["evento"], "MAC_GUARDADA")
        self.assertEqual(set(it[0]), {"id", "fecha", "evento", "categoria", "titulo", "valor", "detalle", "operador", "lote_id", "lote"})
        self.assertGreater(it[0]["id"], it[1]["id"])

    def test_paginacion(self):
        for i in range(130):
            db.log_evento("MAC_GUARDADA", None, f"P{i:03d}", "d", "op")
        total = self.mov(limite=1)["total"]
        self.assertEqual(total, 131)
        vistos = []
        for off in range(0, total, 50):
            p = self.mov(limite=50, desplazamiento=off)
            self.assertEqual(p["desplazamiento"], off)
            vistos += [m["id"] for m in p["items"]]
        self.assertEqual(len(vistos), total)
        self.assertEqual(len(set(vistos)), total)          # sin repetidos ni huecos
        self.assertEqual(vistos, sorted(vistos, reverse=True))
        self.assertEqual(self.mov(limite=50, desplazamiento=total)["items"], [])
        for malo in ({"limite": 0}, {"limite": 201}, {"desplazamiento": -1}):
            self.assertEqual(self.client.get("/api/admin/movimientos", params=malo, headers=self.H).status_code, 422)

    def test_busqueda_con_comodines_se_toma_literal(self):
        db.log_evento("MAC_GUARDADA", None, "100%", "descuento", "op")
        db.log_evento("MAC_GUARDADA", None, "a_b", "guion bajo", "op")
        db.log_evento("MAC_GUARDADA", None, "axb", "no debe salir con _", "op")
        db.log_evento("MAC_GUARDADA", None, "hola!", "exclamación", "op")
        db.log_evento("MAC_GUARDADA", None, "hola", "sin exclamación", "op")
        todo = self.mov(limite=200)["items"]
        campos = lambda m: [str(m[k] or "") for k in ("valor", "detalle", "operador", "evento")]
        for q in ("%", "_", "!", "a_b", "100%", "hola!"):
            with self.subTest(q=q):
                esperado = {m["id"] for m in todo if any(q.lower() in c.lower() for c in campos(m))}
                self.assertEqual({m["id"] for m in self.mov(q=q, limite=200)["items"]}, esperado)
        self.assertEqual([m["valor"] for m in self.mov(q="100%")["items"]], ["100%"])
        self.assertEqual([m["valor"] for m in self.mov(q="hola!")["items"]], ["hola!"])
        self.assertNotIn("axb", [m["valor"] for m in self.mov(q="a_b")["items"]])
        self.assertEqual(self.mov(q="'; DROP TABLE escaneos; --")["total"], 0)

    def test_fechas_categoria_y_lote(self):
        t = crear_par()
        db.log_evento("MAC_GUARDADA", t["lote_id"], "x", "d", "op")
        hoy = self.mov()["items"][0]["fecha"][:10]
        self.assertGreaterEqual(self.mov(desde=hoy, hasta=hoy)["total"], 1)
        self.assertEqual(self.mov(desde="2999-01-01")["total"], 0)
        self.assertEqual(self.mov(hasta="2000-01-01")["total"], 0)
        self.assertGreaterEqual(self.mov(lote_id=t["lote_id"])["total"], 1)
        self.assertTrue(all(m["lote_id"] == t["lote_id"] for m in self.mov(lote_id=t["lote_id"])["items"]))
        for malo in ({"desde": "2026-13-45"}, {"hasta": "ayer"}, {"desde": "2026/09/01"}, {"desde": "2026-9-1x"}):
            with self.subTest(malo=malo):
                self.assertEqual(self.client.get("/api/admin/movimientos", params=malo, headers=self.H).status_code, 400)
        for cat in ("inventada", "ALTA", "alta,edicion"):
            with self.subTest(cat=cat):
                self.assertEqual(self.client.get("/api/admin/movimientos", params={"categoria": cat}, headers=self.H).status_code, 400)


class TestRegistro(Base):
    def test_login_fallido_ok_y_logout_quedan_registrados(self):
        self.client.post("/api/admin/login", json={"password": "incorrecta-1"})
        self.assertIn("ADMIN_LOGIN_FALLIDO", self.eventos())
        self.assertIn("ADMIN_LOGIN", self.eventos())           # el del setUp
        self.client.post("/api/admin/logout", headers=self.H)
        ev = self.eventos()
        self.assertEqual(ev[0], "ADMIN_LOGOUT")
        cats = {m["evento"]: m["categoria"] for m in self.mov(limite=200)["items"]}
        self.assertTrue(all(cats[e] == "sesion" for e in ("ADMIN_LOGIN", "ADMIN_LOGIN_FALLIDO", "ADMIN_LOGOUT")))
        # la contraseña escrita nunca se guarda en el registro
        self.assertNotIn("incorrecta-1", str(self.mov(limite=200)))
        self.assertNotIn(CLAVE, str(self.mov(limite=200)))

    def test_logout_sin_sesion_no_registra(self):
        n = self.mov()["total"]
        self.assertEqual(self.client.post("/api/admin/logout").status_code, 200)
        self.assertEqual(self.mov()["total"], n)

    def test_exportacion_queda_registrada(self):
        t = crear_par(r3=True)
        r = self.client.get(f"/api/admin/export/excel?lote_id={t['lote_id']}", headers=self.H)
        self.assertEqual(r.status_code, 200, r.text[:200])
        m = self.mov(categoria="excel")["items"]
        self.assertEqual(len(m), 1)
        self.assertEqual(m[0]["evento"], "EXCEL_EXPORTADO")
        self.assertEqual(m[0]["lote_id"], t["lote_id"])

    def test_borrados_admin_quedan_registrados_en_eliminaciones(self):
        t = crear_par(r3=True)
        self.assertEqual(self.client.request("DELETE", "/api/admin/tarjetas", json={"ids": [t["id"]], "liberar_pcb": True}, headers=self.H).status_code, 200)
        self.assertIn("ADMIN_TARJETAS_BORRADAS", [m["evento"] for m in self.mov(categoria="eliminacion")["items"]])

    def test_reset_conserva_los_movimientos_y_registra_admin_reset(self):
        crear_par(r3=True)
        antes = self.mov(limite=200)
        self.assertGreater(antes["total"], 1)
        r = self.client.post("/api/admin/reset", json={"confirmar": "BORRAR TODO"}, headers=self.H)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json().get("movimientos_conservados"))
        despues = self.mov(limite=200)
        self.assertEqual(despues["total"], antes["total"] + 1)
        self.assertEqual(despues["items"][0]["evento"], "ADMIN_RESET")
        ids_antes = {m["id"] for m in antes["items"]}
        self.assertTrue(ids_antes <= {m["id"] for m in despues["items"]})   # ninguno desapareció
        resumen = self.client.get("/api/admin/resumen", headers=self.H).json()
        self.assertEqual(resumen["totales"]["bitacora"], despues["total"])


class TestPantalla(unittest.TestCase):
    """Comprobaciones estáticas de admin.html/admin.js (la conducta real está en tests/e2e/admin_mov_*.py)."""

    def test_pestana_y_textos(self):
        self.assertIn('data-v="movimientos"', HTML)
        self.assertIn("Historial de lo que se hizo en el sistema: altas, ediciones, eliminaciones, sesiones y Excel. No se borra con «Borrar TODO».", HTML)
        self.assertIn("Se conservan los lotes, la contraseña y los movimientos", HTML)
        self.assertIn("Todavía no hay movimientos con esos filtros", JS)
        self.assertNotIn("bitácora", HTML.lower().replace("<!--", ""))

    def test_movimientos_no_usan_innerhtml_con_datos_del_servidor(self):
        bloque = JS[JS.index("movimientos (tabla escaneos"):JS.index("exportar Excel (fetch")]
        self.assertNotRegex(bloque, r"innerHTML|insertAdjacentHTML|outerHTML|document\.write")

    def test_csv_neutraliza_formulas(self):
        self.assertIn("[=+\\-@\\t\\r]", JS)

    def test_logo_y_salidas_del_login_no_van_al_monitor(self):
        self.assertRegex(HTML, r'<a class="brand" href="/" ')
        self.assertNotIn('href="/monitor"', HTML)            # antes: logo y «Cancelar» -> /monitor -> otra vez el login
        self.assertIn('id="cerradaEscaner" href="/"', HTML)
        self.assertIn("Sesión cerrada", HTML)
        self.assertIn("Volver a entrar", HTML)
        self.assertIn("Para abrir el monitor necesitas la contraseña de supervisor.", HTML)

    def test_cerrar_sesion_limpia_y_avisa_a_otras_pestanas(self):
        self.assertRegex(JS, r"/api/admin/logout")
        self.assertIn("verLogin(null, { cerrada: true })", JS)
        self.assertIn("BroadcastChannel('tqt-admin')", JS)
        self.assertIn("history.replaceState", JS)             # se quita ?next= tras cerrar sesión

    def test_next_sigue_limitado_al_monitor(self):
        self.assertRegex(JS, r"n === '/monitor'")


if __name__ == "__main__":
    unittest.main()
