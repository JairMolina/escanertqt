"""QA profundo de /admin (docs/qa/ADMIN_PROFUNDO.md): regresiones de backend y comprobaciones estáticas de admin.js/admin.html.
Las pruebas de navegador viven en tests/e2e/admin_ui*.py (no forman parte de unittest)."""
import _aislamiento  # noqa: F401  (debe ser lo primero)
import os
import re
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from app.config import settings
from app.database import admin_ops, db
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
        settings.DB_PATH = Path(cls.tmp.name) / "adm2.db"
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
        self.client.cookies.clear()

    def login(self):
        r = self.client.post("/api/admin/login", json={"password": CLAVE})
        self.assertEqual(r.status_code, 200, r.text)
        self.client.cookies.clear()
        return {"X-Admin-Token": r.json()["token"]}

    def conteo(self, tabla):
        with db.get_db() as c:
            return c.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0]


class TestBackendAdmin(Base):
    def test_sin_respaldo_posible_no_se_borra_nada_y_el_mensaje_es_claro(self):
        """Bug hallado en Docker: TQT_BACKUP_DIR inutilizable daba un 500 mudo ('Error 500') en TODA acción destructiva."""
        t = crear_par(r3=True)
        h = self.login()
        antes = self.conteo("tarjetas_produccion")
        with mock.patch.object(admin_ops, "respaldar", side_effect=PermissionError("denegado")):
            for m, u, j in (("DELETE", "/api/admin/tarjetas", {"ids": [t["id"]], "liberar_pcb": True}),
                            ("DELETE", "/api/admin/pcb", {"ids": [t["pcb_r1_id"]]}),
                            ("POST", f"/api/admin/lote/{t['lote_id']}/vaciar", {"confirmar": "VACIAR"}),
                            ("POST", "/api/admin/reset", {"confirmar": "BORRAR TODO"})):
                with self.subTest(ruta=u):
                    r = self.client.request(m, u, json=j, headers=h)
                    self.assertEqual(r.status_code, 500)
                    self.assertIn("no se borró nada", r.json()["detail"])
        self.assertEqual(self.conteo("tarjetas_produccion"), antes)

    def test_borrar_tarjetas_con_y_sin_liberar_pcb(self):
        a, b = crear_par(r3=True), crear_par(r3=True)
        h = self.login()
        r = self.client.request("DELETE", "/api/admin/tarjetas", json={"ids": [a["id"]], "liberar_pcb": True}, headers=h)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["tarjetas_borradas"], 1)  # admin.js lee esta clave para el aviso
        for k in ("pcb_r1_id", "pcb_r2_id", "pcb_r3_id"):
            p = self.client.get("/api/pcb", params={"limit": 5000}).json()["items"]
            fila = next(x for x in p if x["id"] == a[k])
            self.assertEqual((fila["estado_ciclo"], fila["tarjeta_id"]), ("DISPONIBLE", None))
        r = self.client.request("DELETE", "/api/admin/tarjetas", json={"ids": [b["id"]], "liberar_pcb": False}, headers=h)
        self.assertEqual((r.json()["pcb_eliminadas"], r.json()["pcb_liberadas"]), (3, 0))
        ids = {x["id"] for x in self.client.get("/api/pcb", params={"limit": 5000}).json()["items"]}
        self.assertFalse(ids & {b["pcb_r1_id"], b["pcb_r2_id"], b["pcb_r3_id"]})

    def test_eliminar_pcb_asignada_deja_la_tarjeta_incompleta_y_no_liberada(self):
        t = crear_par(r3=True)
        h = self.login()
        for e in ("Soldadura", "Programación", "Prueba PCB", "Integración", "Prueba Final"):
            self.client.put(f"/api/tarjetas/{t['id']}/pruebas", json={"etapa": e, "estado": "OK"})
        r = self.client.request("DELETE", "/api/admin/pcb", json={"ids": [t["pcb_r1_id"]]}, headers=h)
        self.assertEqual((r.status_code, r.json()["pcb_eliminadas"], r.json()["tarjetas_afectadas"]), (200, 1, 1))
        nueva = db.get_tarjeta_by_id(t["id"])
        self.assertNotEqual(nueva["estado_general"], "LIBERADO")
        self.assertFalse(nueva["completa"])

    def test_resumen_tiene_la_forma_que_pinta_la_pantalla(self):
        """admin.js dibuja totales, lotes[{codigo_lote,activo,tarjetas,por_estado}], inventario{tipo:{ciclo:n}}, respaldos[{nombre,bytes}], bd_bytes."""
        crear_par(r3=True)
        d = self.client.get("/api/admin/resumen", headers=self.login()).json()
        self.assertTrue({"totales", "lotes", "inventario", "respaldos", "bd_bytes"} <= set(d))
        self.assertTrue({"tarjetas", "pcb", "bitacora"} <= set(d["totales"]))
        self.assertTrue({"id", "codigo_lote", "activo", "tarjetas", "por_estado"} <= set(d["lotes"][0]))
        self.assertEqual(d["totales"]["pcb"], sum(sum(v.values()) for v in d["inventario"].values()))
        self.assertIsInstance(d["bd_bytes"], int)

    def test_el_token_lleva_su_caducidad_en_segundos_para_la_pantalla(self):
        """admin.js (expDeToken) lee `exp` del cuerpo del token en vez de fiarse de sessionStorage."""
        import base64
        import json
        t = self.login()["X-Admin-Token"].split(".")[0]
        exp = json.loads(base64.urlsafe_b64decode(t + "=" * (-len(t) % 4)))["exp"]
        self.assertTrue(0 < exp - __import__("time").time() <= settings.ADMIN_TOKEN_TTL + 2)

    def test_clave_actual_incorrecta_responde_401_con_texto_distinguible(self):
        """admin.js distingue 'clave actual mal escrita' de 'sesión caducada' por este texto (no debe cambiar sin tocar admin.js)."""
        h = self.login()
        r = self.client.post("/api/admin/cambiar-clave", json={"actual": "incorrecta-1", "nueva": "NuevaClave-2026"}, headers=h)
        self.assertEqual(r.status_code, 401)
        self.assertRegex(r.json()["detail"], r"(?i)actual no es correcta")
        r = self.client.post("/api/admin/cambiar-clave", json={"actual": CLAVE, "nueva": "NuevaClave-2026"}, headers={"X-Admin-Token": "a.b"})
        self.assertEqual(r.status_code, 401)
        self.assertNotRegex(r.json()["detail"], r"(?i)actual no es correcta")

    def test_clave_cambiada_sobrevive_al_reinicio_y_la_variable_nueva_la_restablece(self):
        h = self.login()
        r = self.client.post("/api/admin/cambiar-clave", json={"actual": CLAVE, "nueva": "NuevaClave-2026"}, headers=h)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(admin_auth.verificar_password("NuevaClave-2026"))
        self.assertFalse(admin_auth.verificar_password(CLAVE))
        admin_auth.sincronizar()  # "reinicio" con la misma variable
        self.assertTrue(admin_auth.verificar_password("NuevaClave-2026"))
        with mock.patch.dict(os.environ, {"TQT_ADMIN_PASSWORD": "OtraEnv-2027"}):  # variable cambiada + reinicio
            self.assertTrue(admin_auth.verificar_password("OtraEnv-2027"))
            self.assertFalse(admin_auth.verificar_password("NuevaClave-2026"))

    def test_api_admin_no_se_guarda_en_cache(self):
        r = self.client.get("/api/admin/resumen", headers=self.login())
        self.assertIn("no-store", r.headers.get("cache-control", ""))
        self.assertIn("no-store", self.client.get("/api/admin/resumen").headers.get("cache-control", ""))


class TestFrontendAdminEstatico(unittest.TestCase):
    def test_arranque_valida_el_token_con_el_servidor_antes_de_mostrar_el_panel(self):
        m = re.search(r"async function arrancar\(\) \{(.*?)\n    \}\n", JS, re.S)
        self.assertIsNotNone(m)
        cuerpo = m.group(1)
        self.assertIn("/api/admin/estado", cuerpo)
        self.assertLess(cuerpo.index("/api/admin/resumen"), cuerpo.index("verAdmin()"))
        self.assertNotIn("if (restaurar()) verAdmin()", JS)  # el patrón antiguo confiaba solo en sessionStorage

    def test_la_caducidad_sale_del_token_y_no_de_sessionstorage(self):
        self.assertIn("function expDeToken", JS)
        self.assertIn("expDeToken(v.t)", JS)

    def test_next_solo_admite_monitor(self):
        m = re.search(r"function destinoNext\(\) \{(.*?)\n    \}", JS, re.S)
        self.assertIsNotNone(m)
        self.assertIn("n === '/monitor'", m.group(1))
        self.assertIn("location.replace(n)", JS)

    def test_cerrar_sesion_llama_al_servidor_para_borrar_la_cookie(self):
        self.assertTrue(re.search(r"async \(\) => \{\s*\$\('btnLogout'\)\.disabled = true;\s*await adm\('/api/admin/logout'", JS))

    def test_salir_limpia_datos_y_hojas_abiertas(self):
        m = re.search(r"function verLogin\(msg(?:, opts)?\) \{(.*?)\n    \}", JS, re.S)
        self.assertIn("replaceChildren()", m.group(1))
        self.assertIn(".scrim, .sheet", m.group(1))

    def test_clave_actual_incorrecta_no_expulsa_al_login(self):
        self.assertRegex(JS, r"cambiar-clave'.*noAuthRedirect: true")
        self.assertIn("actual no es correcta", JS)

    def test_atras_desde_cache_recarga(self):
        self.assertIn("ev.persisted", JS)

    def test_sin_innerhtml_ni_dialogos_nativos(self):
        self.assertNotRegex(JS, r"\.(innerHTML|outerHTML)|insertAdjacentHTML|\balert\(|\bconfirm\(|\bprompt\(")

    def test_el_texto_de_borrar_todo_no_promete_borrar_los_lotes(self):
        """reset_total conserva lotes y clave (ADMIN.md): ni la pantalla ni el html deben decir lo contrario."""
        self.assertNotRegex(JS, r"Se vac[ií]a toda la base de datos: lotes")
        self.assertNotIn("Deja la base de datos vacía: lotes", HTML)
        self.assertIn("Se conservan los lotes", HTML)

    def test_tablas_con_scroll_son_enfocables_y_con_nombre_unico(self):
        etiquetas = re.findall(r"class: 'tablewrap', tabindex: '0', role: 'region', 'aria-label': '([^']+)'", JS)
        self.assertGreaterEqual(len(etiquetas), 3)
        self.assertEqual(len(etiquetas), len(set(etiquetas)))

    def test_la_navegacion_no_desborda_en_movil(self):
        self.assertRegex(HTML, r"@media \(max-width: 700px\)[^}]*\.desk-nav[^}]*flex-wrap: wrap")   # v1.3.42: filas, no scroll lateral

    def test_el_toast_de_borrado_usa_las_claves_reales_del_servidor(self):
        self.assertIn("d.tarjetas_borradas", JS)
        self.assertIn("d.pcb_eliminadas", JS)
        self.assertNotIn("d.eliminadas", JS)


if __name__ == "__main__":
    unittest.main()
