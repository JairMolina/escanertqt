"""QA de seguridad: /admin y autenticación, superficie de la API (CSRF/WebSocket entre sitios, cabeceras, rutas, inyección,
enteros gigantes) y estáticos. Regresiones de los hallazgos de docs/qa/SEGURIDAD_ADMIN_DOCKER.md."""
import _aislamiento  # noqa: F401  (debe ser lo primero)
import itertools
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from urllib.parse import quote
from unittest import mock

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.config import settings
from app.database import db
from app.main import app, origen_distinto
from app.services import admin_auth
from app.services.admin_auth import LimitadorIntentos

from _aislamiento import crear_par, verificar_aislamiento

_n = itertools.count(1)


def nuevo_lote():
    """Lote nuevo en la BD propia de este módulo (nuevo_lote de _aislamiento exige la BD compartida de los tests)."""
    return db.create_lote(f"SEG-{os.getpid()}-{next(_n)}", 9, 2026, activo=True)

CLAVE = "ClaveQA-12345"
XSS = '<img src=x onerror="window.__x=1;alert(1)">'


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        verificar_aislamiento()
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls._db_previa = settings.DB_PATH
        cls._bk_previo = settings.BACKUP_DIR
        settings.DB_PATH = Path(cls.tmp.name) / "seg.db"
        settings.BACKUP_DIR = Path(cls.tmp.name) / "bk"
        cls._parches = [
            mock.patch.dict(os.environ, {"TQT_ADMIN_PASSWORD": CLAVE}),
            mock.patch.object(settings, "ADMIN_RETARDO_MS", 0),
            mock.patch.object(settings, "ADMIN_PBKDF2_ITER", 1000),
        ]
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
        settings.DB_PATH = cls._db_previa
        settings.BACKUP_DIR = cls._bk_previo
        cls.tmp.cleanup()

    def setUp(self):
        admin_auth.limitador.reiniciar()
        with db.transaction() as c:
            c.execute("DELETE FROM ajustes WHERE clave LIKE 'admin_%'")

    def login(self, clave=CLAVE):
        r = self.client.post("/api/admin/login", json={"password": clave})
        self.assertEqual(r.status_code, 200, r.text)
        return {"X-Admin-Token": r.json()["token"]}

    def conteos(self, ruta=None):
        c = sqlite3.connect(ruta or settings.DB_PATH)
        try:
            return {t: c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                    for t in ("tarjetas_produccion", "pcb_inventario", "pruebas_historial", "escaneos", "lotes_mensuales")}
        finally:
            c.close()


# ============================================================================ A. /admin y autenticación
class TestAdminAuth(Base):
    RUTAS_ADMIN = [("GET", "/api/admin/resumen", None), ("DELETE", "/api/admin/tarjetas", {"ids": [1]}),
                   ("DELETE", "/api/admin/pcb", {"ids": [1]}), ("POST", "/api/admin/lote/1/vaciar", {"confirmar": "VACIAR"}),
                   ("POST", "/api/admin/reset", {"confirmar": "BORRAR TODO"}), ("GET", "/api/admin/export/excel?ruta=x", None),
                   ("POST", "/api/admin/cambiar-clave", {"actual": CLAVE, "nueva": "OtraClave-99"}),
                   ("POST", "/api/excel/import", {"excel_path": "x.xlsx"}),
                   ("POST", "/api/excel/create-monthly", {"mes": 1, "anio": 2027})]

    def test_toda_ruta_sensible_exige_token(self):
        for m, u, j in self.RUTAS_ADMIN:
            with self.subTest(ruta=f"{m} {u}"):
                self.assertEqual(self.client.request(m, u, json=j).status_code, 401)
                self.assertEqual(self.client.request(m, u, json=j, headers={"X-Admin-Token": ""}).status_code, 401)
                self.assertEqual(self.client.request(m, u, json=j, headers={"X-Admin-Token": "a.b"}).status_code, 401)

    def test_token_en_query_o_bearer_no_valen(self):
        t = self.login()["X-Admin-Token"]
        self.assertEqual(self.client.get("/api/admin/resumen", params={"token": t}).status_code, 401)
        self.assertEqual(self.client.get("/api/admin/resumen", headers={"Authorization": f"Bearer {t}"}).status_code, 401)

    def test_token_manipulado(self):
        t = self.login()["X-Admin-Token"]
        cuerpo, firma = t.split(".")
        for malo in (cuerpo + "." + firma[:-2] + ("AA" if firma[-2:] != "AA" else "BB"), cuerpo + "x." + firma, "." + firma, cuerpo + ".",
                     cuerpo + "." + firma + "." + firma, "\x00.\x00"):
            with self.subTest(token=malo[:20]):
                self.assertEqual(self.client.get("/api/admin/resumen", headers={"X-Admin-Token": malo}).status_code, 401)

    def test_token_caducado(self):
        t = admin_auth.emitir_token(ahora=1_000_000)["token"]
        with self.assertRaises(admin_auth.TokenInvalidoError):
            admin_auth.validar_token(t, ahora=1_000_000 + settings.ADMIN_TOKEN_TTL + 1)
        admin_auth.validar_token(t, ahora=1_000_000 + settings.ADMIN_TOKEN_TTL - 1)

    def test_cambiar_clave_invalida_tokens_viejos_y_devuelve_uno_nuevo(self):
        h = self.login()
        r = self.client.post("/api/admin/cambiar-clave", headers=h, json={"actual": CLAVE, "nueva": "OtraClave-99"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.client.get("/api/admin/resumen", headers=h).status_code, 401)
        self.assertEqual(self.client.get("/api/admin/resumen", headers={"X-Admin-Token": r.json()["token"]}).status_code, 200)
        self.assertEqual(self.client.post("/api/admin/login", json={"password": CLAVE}).status_code, 401)
        self.assertEqual(self.client.post("/api/admin/login", json={"password": "OtraClave-99"}).status_code, 200)

    def test_cambiar_clave_validaciones(self):
        h = self.login()
        for actual, nueva, esperado in [(CLAVE, "corta", 400), (CLAVE, CLAVE, 400), ("mala-mala-1", "OtraClave-99", 401),
                                        (CLAVE, "x" * 201, 422), (CLAVE, "", 400)]:
            with self.subTest(nueva=nueva[:8]):
                r = self.client.post("/api/admin/cambiar-clave", headers=h, json={"actual": actual, "nueva": nueva})
                self.assertEqual(r.status_code, esperado, r.text)
        self.assertEqual(self.client.post("/api/admin/login", json={"password": CLAVE}).status_code, 200)

    def test_login_entradas_hostiles(self):
        for cuerpo, esperado in [({"password": ""}, 401), ({"password": "x"}, 401), ({"password": 123}, 422), ({}, 422),
                                 ({"password": "A" * 100000}, 422), ({"password": "' OR '1'='1"}, 401), ({"password": None}, 422)]:
            with self.subTest(cuerpo=str(cuerpo)[:30]):
                self.assertEqual(self.client.post("/api/admin/login", json=cuerpo).status_code, esperado)
        self.assertEqual(self.client.post("/api/admin/login", content="[" * 50000, headers={"content-type": "application/json"}).status_code, 400)

    def test_bloqueo_tras_5_fallos_y_desbloqueo(self):
        t = [1000.0]
        with mock.patch.object(admin_auth, "limitador", LimitadorIntentos(reloj=lambda: t[0])):
            for i in range(4):
                self.assertEqual(self.client.post("/api/admin/login", json={"password": "mala"}).status_code, 401, i)
            r = self.client.post("/api/admin/login", json={"password": "mala"})
            self.assertEqual(r.status_code, 429)
            self.assertGreater(int(r.headers["Retry-After"]), 0)
            # bloqueado: ni siquiera la clave correcta entra
            self.assertEqual(self.client.post("/api/admin/login", json={"password": CLAVE}).status_code, 429)
            t[0] += settings.ADMIN_BLOQUEO_SEG + 1
            self.assertEqual(self.client.post("/api/admin/login", json={"password": CLAVE}).status_code, 200)
            # un login correcto reinicia el contador
            for _ in range(4):
                self.client.post("/api/admin/login", json={"password": "mala"})
            self.assertEqual(self.client.post("/api/admin/login", json={"password": CLAVE}).status_code, 200)
            self.assertEqual(self.client.post("/api/admin/login", json={"password": "mala"}).status_code, 401)

    def test_admin_deshabilitado_sin_variable(self):
        with mock.patch.dict(os.environ, {"TQT_ADMIN_PASSWORD": ""}):
            r = self.client.post("/api/admin/login", json={"password": "cualquiera"})
            self.assertEqual(r.status_code, 503)
            self.assertIn("TQT_ADMIN_PASSWORD", r.json()["detail"])
            self.assertEqual(self.client.get("/api/admin/resumen", headers={"X-Admin-Token": "a.b"}).status_code, 503)
            self.assertFalse(self.client.get("/api/admin/estado").json()["habilitado"])
        with mock.patch.dict(os.environ, {"TQT_ADMIN_PASSWORD": "corta"}):
            self.assertEqual(self.client.post("/api/admin/login", json={"password": "corta"}).status_code, 503)


class TestAdminDestructivas(Base):
    def n_respaldos(self):
        return len(list(settings.BACKUP_DIR.glob("tqt_*.db"))) if settings.BACKUP_DIR.exists() else 0

    def test_confirmaciones_incorrectas_no_borran_ni_respaldan(self):
        lote = nuevo_lote()["id"]
        crear_par(lote)
        h = self.login()
        antes, bk = self.conteos(), self.n_respaldos()
        for conf in ("", "vaciar", "Vaciar", " VACIAR", "VACIAR ", "VACIAR\n", "BORRAR TODO"):
            with self.subTest(vaciar=conf):
                self.assertEqual(self.client.post(f"/api/admin/lote/{lote}/vaciar", headers=h, json={"confirmar": conf}).status_code, 400)
        for conf in ("", "borrar todo", "BORRAR  TODO", "BORRAR TODO ", "VACIAR", "BORRAR TODO\n"):
            with self.subTest(reset=conf):
                self.assertEqual(self.client.post("/api/admin/reset", headers=h, json={"confirmar": conf}).status_code, 400)
        self.assertEqual(self.client.post("/api/admin/reset", headers=h, json={}).status_code, 422)
        self.assertEqual(self.conteos(), antes)
        self.assertEqual(self.n_respaldos(), bk)

    def test_objetivos_inexistentes_e_invalidos_sin_respaldo(self):
        h = self.login()
        bk = self.n_respaldos()
        casos = [("DELETE", "/api/admin/tarjetas", {"ids": [999999]}, 404), ("DELETE", "/api/admin/tarjetas", {"ids": [-1, 0]}, 404),
                 ("DELETE", "/api/admin/tarjetas", {"ids": []}, 422), ("DELETE", "/api/admin/tarjetas", {"ids": ["1 OR 1=1"]}, 422),
                 ("DELETE", "/api/admin/tarjetas", {"ids": list(range(2001))}, 422), ("DELETE", "/api/admin/tarjetas", {"ids": [10 ** 30]}, 422),
                 ("DELETE", "/api/admin/pcb", {"ids": [999999]}, 404), ("DELETE", "/api/admin/pcb", {"ids": [10 ** 30]}, 422),
                 ("DELETE", "/api/admin/pcb", {"ids": None}, 422), ("POST", "/api/admin/lote/999999/vaciar", {"confirmar": "VACIAR"}, 404),
                 ("POST", f"/api/admin/lote/{10 ** 30}/vaciar", {"confirmar": "VACIAR"}, 422)]
        for m, u, j, esperado in casos:
            with self.subTest(caso=f"{m} {u[:30]} {str(j)[:30]}"):
                self.assertEqual(self.client.request(m, u, headers=h, json=j).status_code, esperado)
        self.assertEqual(self.n_respaldos(), bk)

    def test_respaldo_previo_es_restaurable_y_hay_bitacora(self):
        lote = nuevo_lote()["id"]
        crear_par(lote)
        crear_par(lote, r3=True)
        h = self.login()
        antes = self.conteos()
        self.assertGreaterEqual(antes["tarjetas_produccion"], 2)
        r = self.client.post("/api/admin/reset", headers=h, json={"confirmar": "BORRAR TODO"})
        self.assertEqual(r.status_code, 200, r.text)
        ruta = settings.BACKUP_DIR / r.json()["respaldo"]
        self.assertTrue(ruta.exists())
        c = sqlite3.connect(ruta)
        try:
            self.assertEqual(c.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        finally:
            c.close()
        self.assertEqual(self.conteos(ruta), antes)  # el respaldo tiene los datos ANTERIORES al borrado
        despues = self.conteos()
        self.assertEqual((despues["tarjetas_produccion"], despues["pcb_inventario"]), (0, 0))
        self.assertGreaterEqual(despues["lotes_mensuales"], 1)  # conserva los lotes
        with sqlite3.connect(settings.DB_PATH) as c2:
            evs = [x[0] for x in c2.execute("SELECT evento FROM escaneos")]
        self.assertIn("ADMIN_RESET", evs)
        self.assertEqual(self.client.post("/api/admin/login", json={"password": CLAVE}).status_code, 200)  # la clave sobrevive

    def test_borrar_tarjetas_y_pcb_y_vaciar_lote_dejan_bitacora(self):
        lote = nuevo_lote()["id"]
        t1, t2, t3 = crear_par(lote), crear_par(lote), crear_par(lote)
        h = self.login()
        r = self.client.request("DELETE", "/api/admin/tarjetas", headers=h, json={"ids": [t1["id"], 999999]})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["tarjetas_borradas"], 1)
        self.assertEqual(r.json()["no_encontradas"], [999999])
        r = self.client.request("DELETE", "/api/admin/pcb", headers=h, json={"ids": [t2["pcb_r1_id"]]})
        self.assertEqual(r.status_code, 200)
        r = self.client.post(f"/api/admin/lote/{lote}/vaciar", headers=h, json={"confirmar": "VACIAR"})
        self.assertEqual(r.status_code, 200)
        with sqlite3.connect(settings.DB_PATH) as c:
            evs = {x[0] for x in c.execute("SELECT evento FROM escaneos")}
        self.assertTrue({"ADMIN_TARJETAS_BORRADAS", "ADMIN_PCB_BORRADAS", "ADMIN_LOTE_VACIADO"} <= evs)

    def test_export_ruta_no_escribe_fuera_ni_nombres_reservados(self):
        h = self.login()
        nuevo_lote()
        base = settings.BASE_DIR
        antes = set(os.listdir(base))
        for ruta in ("C:/Windows/win.ini", "C:/Windows/System32", "..\\..\\..\\Windows\\x.xlsx", "\\\\host\\share\\x.xlsx",
                     "C:/Windows/x.xlsx", "CON", "aux", "NUL.xlsx", "COM1.xlsx", str(base / "CON" / "x.xlsx"), str(base / "LPT1.xlsx"),
                     str(settings.TEMPLATES_DIR / "Control_Produccion_TQT_Template.xlsx"), str(settings.TEMPLATES_DIR / "x.xlsx"),
                     "x\x00.xlsx", "x" * 501):
            with self.subTest(ruta=ruta[:40]):
                r = self.client.get("/api/admin/export/excel", headers=h, params={"ruta": ruta})
                self.assertIn(r.status_code, (400, 422), r.text[:200])
        self.assertEqual(set(os.listdir(base)), antes, "la exportación no debe crear nada en la carpeta del proyecto")

    def test_export_con_token_y_descarga(self):
        h = self.login()
        nuevo_lote()
        r = self.client.get("/api/admin/export/excel", headers=h)
        self.assertEqual(r.status_code, 200, r.text[:200])
        self.assertTrue(r.content.startswith(b"PK"))
        self.assertIn("attachment", r.headers["content-disposition"])
        self.assertEqual(self.client.get("/api/admin/export/excel", params={"lote_id": 999999}, headers=h).status_code, 404)


# ============================================================================ B. superficie de la API
class TestSuperficieApi(Base):
    def setUp(self):
        super().setUp()
        # crear/activar lote y sincronizar Excel exigen sesión de supervisor cuando hay clave de admin
        self.client.headers.update(self.login())

    def test_cabeceras_de_seguridad(self):
        for u in ("/api/status", "/", "/admin", "/static/js/admin.js", "/api/admin/estado", "/no-existe"):
            r = self.client.get(u)
            with self.subTest(url=u):
                self.assertEqual(r.headers.get("x-content-type-options"), "nosniff")
                self.assertEqual(r.headers.get("x-frame-options"), "DENY")
                self.assertEqual(r.headers.get("referrer-policy"), "no-referrer")
                self.assertIn("frame-ancestors 'none'", r.headers.get("content-security-policy", ""))

    def test_api_no_se_guarda_en_cache(self):
        for u in ("/api/status", "/api/lotes", "/api/tarjetas", "/api/admin/estado"):
            self.assertEqual(self.client.get(u).headers.get("cache-control"), "no-store", u)
        self.assertEqual(self.client.get("/api/admin/resumen", headers=self.login()).headers.get("cache-control"), "no-store")

    def test_sin_cors_abierto(self):
        r = self.client.options("/api/lotes", headers={"Origin": "https://evil.com", "Access-Control-Request-Method": "POST"})
        self.assertNotIn("access-control-allow-origin", r.headers)
        r = self.client.get("/api/lotes", headers={"Origin": "https://evil.com"})
        self.assertNotIn("access-control-allow-origin", r.headers)

    def test_csrf_peticion_que_cambia_datos_desde_otro_origen_se_rechaza(self):
        for origen in ("https://evil.com", "null", "http://otro:8443", "http://testserver.evil.com"):
            with self.subTest(origen=origen):
                for m, u in (("POST", "/api/recepcion/confirmar"), ("POST", "/api/emparejar/auto"), ("DELETE", "/api/tarjetas/1"),
                             ("POST", "/api/admin/login"), ("PUT", "/api/ajustes")):
                    r = self.client.request(m, u, headers={"Origin": origen})
                    self.assertEqual(r.status_code, 403, f"{m} {u}")
        # el mismo origen (la propia app) y los clientes sin Origin (curl, tests) siguen funcionando
        self.assertEqual(self.client.post("/api/recepcion/confirmar", headers={"Origin": "http://testserver"}).status_code, 200)
        self.assertEqual(self.client.post("/api/recepcion/confirmar").status_code, 200)
        self.assertEqual(self.client.get("/api/lotes", headers={"Origin": "https://evil.com"}).status_code, 200)  # sin CORS el navegador no lo lee

    def test_origen_distinto(self):
        self.assertFalse(origen_distinto({"host": "192.168.1.5:8443"}))
        self.assertFalse(origen_distinto({"origin": "https://192.168.1.5:8443", "host": "192.168.1.5:8443"}))
        self.assertTrue(origen_distinto({"origin": "https://192.168.1.6:8443", "host": "192.168.1.5:8443"}))
        self.assertTrue(origen_distinto({"origin": "null", "host": "x"}))

    def test_websocket_entre_sitios_rechazado(self):
        with self.client.websocket_connect("/ws") as ws:
            self.assertEqual(ws.receive_json()["evento"], "CONEXION_ESTABLECIDA")
        with self.client.websocket_connect("/ws", headers={"Origin": "http://testserver"}) as ws:
            self.assertEqual(ws.receive_json()["evento"], "CONEXION_ESTABLECIDA")
        with self.assertRaises(WebSocketDisconnect):
            with self.client.websocket_connect("/ws", headers={"Origin": "https://evil.com"}) as ws:
                ws.receive_json()

    def test_explorador_de_api_apagado(self):
        for u in ("/docs", "/redoc", "/openapi.json"):
            self.assertEqual(self.client.get(u).status_code, 404, u)

    def test_estaticos_no_exponen_codigo_ni_datos(self):
        for u in ("/static/../run_server.py", "/static/%2e%2e/run_server.py", "/static/..%2f..%2frun_server.py", "/static/..%5c..%5crun_server.py",
                  "/static/../../tqt_produccion.db", "/static/%2e%2e%2f%2e%2e%2f.env", "/static/../../certs/key.pem", "/certs/key.pem",
                  "/tqt_produccion.db", "/.env", "/docs/ADMIN.md", "/app/main.py", "/main.py", "/Dockerfile", "/static/", "/static/js/",
                  "/static/CON", "/static/NUL", "/static/%00", "/templates/Control_Produccion_TQT_Template.xlsx"):
            with self.subTest(url=u):
                r = self.client.get(u)
                self.assertEqual(r.status_code, 404)
                self.assertNotIn(b"PRIVATE KEY", r.content)
                self.assertNotIn(b"uvicorn.run", r.content)

    def test_cert_solo_entrega_el_certificado_publico(self):
        r = self.client.get("/cert")
        if r.status_code == 200:
            self.assertIn(b"BEGIN CERTIFICATE", r.content)
            self.assertNotIn(b"PRIVATE", r.content)
        else:
            self.assertEqual(r.status_code, 404)

    def test_enteros_gigantes_dan_422_no_500(self):
        big = 10 ** 30
        for m, u, j in [("GET", f"/api/tarjetas/{big}", None), ("GET", f"/api/pcb/{big}", None), ("DELETE", f"/api/tarjetas/{big}", None),
                        ("PATCH", f"/api/pcb/{big}", {"serie": "1"}), ("GET", f"/api/tarjetas?lote_id={big}", None),
                        ("GET", f"/api/tarjetas?offset={big}", None), ("POST", f"/api/lotes/{big}/activar", None),
                        ("GET", f"/api/dymo/label/{big}", None), ("GET", f"/api/stats?lote_id={big}", None),
                        ("POST", "/api/tarjetas", {"r1_id": big}), ("POST", "/api/recepcion/confirmar", {"ids": [big]})]:
            with self.subTest(caso=f"{m} {u[:40]}"):
                self.assertEqual(self.client.request(m, u, json=j).status_code, 422)

    def test_inyeccion_sql_en_parametros(self):
        lote = nuevo_lote()["id"]
        crear_par(lote)
        base = self.client.get("/api/tarjetas", params={"lote_id": lote}).json()["total"]
        for p in ("' OR '1'='1", "'; DROP TABLE tarjetas_produccion;--", "%' UNION SELECT 1,2,3--", '" OR 1=1 --', "1) OR (1=1", "\\", "\x00"):
            with self.subTest(payload=p):
                for r in (self.client.get("/api/tarjetas", params={"search": p, "lote_id": lote}),
                          self.client.get("/api/tarjetas", params={"estado_general": p}),
                          self.client.get("/api/pcb", params={"q": p}),
                          self.client.get("/api/pcb/por-codigo", params={"codigo": p}),
                          self.client.get("/api/tarjetas/by-mac/" + quote(p, safe=""))):
                    self.assertLess(r.status_code, 500, r.text[:200])
        self.assertEqual(self.client.get("/api/tarjetas", params={"lote_id": lote}).json()["total"], base)  # la tabla sigue viva

    def test_errores_no_filtran_trazas_ni_rutas(self):
        for r in (self.client.get("/api/tarjetas/abc"), self.client.post("/api/lotes", content=b"{bad", headers={"content-type": "application/json"}),
                  self.client.get("/api/dymo/label/999999"), self.client.get("/api/pcb/999999"), self.client.get("/api/excel/verify?excel_path=%5C%5Chost%5Cx.xlsx")):
            self.assertNotIn("Traceback", r.text)
            self.assertNotIn('File "', r.text)

    def test_ruta_excel_del_lote_no_puede_apuntar_fuera(self):
        """Antes POST /api/lotes aceptaba cualquier ruta_excel y la sincronización escribía allí."""
        for ruta in ("C:/Windows/win.ini", "C:/Windows/System32/x.xlsx", "\\\\host\\share\\x.xlsx", "..\\..\\x.xlsx"):
            with self.subTest(ruta=ruta):
                r = self.client.post("/api/lotes", json={"codigo_lote": f"RX-{abs(hash(ruta)) % 100000}", "mes": 9, "anio": 2026,
                                                        "ruta_excel": ruta, "crear_excel": False, "activo": False})
                self.assertEqual(r.status_code, 400, r.text)

    def test_sincronizar_ignora_rutas_peligrosas_guardadas_en_lotes_antiguos(self):
        lote = db.create_lote("LEGADO-WIN", 9, 2026, ruta_excel="C:/Windows/win.ini", activo=False)
        r = self.client.post("/api/excel/sync", json={"lote_id": lote["id"]})
        self.assertEqual(r.status_code, 400, r.text)
        ini = Path("C:/Windows/win.ini")
        if ini.exists():
            self.assertFalse(ini.read_bytes().startswith(b"PK"))

    def test_xss_almacenado_se_sirve_como_json_y_el_html_lo_escapa(self):
        lote = nuevo_lote()["id"]
        t = crear_par(lote)
        r = self.client.patch(f"/api/tarjetas/{t['id']}", json={"firmware_r1": XSS[:40], "firmware_r2": '"><script>alert(2)</script>'[:40]})
        self.assertEqual(r.status_code, 400)          # el firmware solo admite letras, números, punto, guion y +: el XSS ni entra
        r = self.client.get(f"/api/tarjetas/{t['id']}")
        self.assertTrue(r.headers["content-type"].startswith("application/json"))
        self.assertEqual(r.headers["x-content-type-options"], "nosniff")
        for u in (f"/api/dymo/preview/{t['id']}", f"/api/dymo/svg/{t['id']}", f"/api/dymo/label/{t['id']}/xml"):
            cuerpo = self.client.get(u).text
            self.assertNotIn("<script>alert(2)", cuerpo, u)
            self.assertNotIn('onerror="window.__x', cuerpo, u)

    def test_texto_hostil_en_operador_y_nombres_es_dato_inerte(self):
        r = self.client.post("/api/pcb/manual", json={"tipo": "R1", "version": "30", "serie": "", "operador": XSS[:60]})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.client.put("/api/pcb/999999/mac", json={"mac": XSS[:60]}).status_code, 404)
        self.assertEqual(self.client.post("/api/pcb/escanear", json={"codigo": XSS}).json()["resultado"], "INVALIDA")

    def test_cuerpos_enormes_y_tipos_erroneos(self):
        self.assertEqual(self.client.post("/api/lotes", json={"codigo_lote": "x" * 5000, "mes": 9, "anio": 2026}).status_code, 422)
        self.assertEqual(self.client.post("/api/pcb/escanear", json={"codigo": "A" * 100000}).status_code, 422)
        self.assertEqual(self.client.post("/api/lotes", json=[1, 2, 3]).status_code, 422)
        self.assertEqual(self.client.post("/api/lotes", json={"codigo_lote": {"a": {"b": [1] * 10}}, "mes": "9", "anio": []}).status_code, 422)
        anidado = "[" * 100000
        self.assertLess(self.client.post("/api/pcb/escanear", content=anidado, headers={"content-type": "application/json"}).status_code, 500)

    def test_metodos_inesperados(self):
        for m in ("TRACE", "PUT", "DELETE", "PATCH"):
            self.assertEqual(self.client.request(m, "/api/lotes").status_code, 405)


if __name__ == "__main__":
    unittest.main()
