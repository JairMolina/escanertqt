"""v1.3.44: el consultor entra a la consola de escritorio (solo Dashboard, Tarjetas, Inventario, Consultar y Excel; solo lectura)
y las descargas de Excel ya no piden la contraseña de administración (para ningún rol)."""
import _aislamiento  # noqa: F401  (debe ser lo primero)
import unittest
from pathlib import Path

from app import main
from app.database import db
from app.main import app
from app.services import usuarios

from _aislamiento import cliente_sin_sesion, verificar_aislamiento

CLAVE = "ClaveDeConsulta-2026"
STATIC = Path(__file__).resolve().parent.parent / "app" / "static"


def _cuenta(email, rol):
    if not any(u["email"] == email for u in usuarios.listar()):
        usuarios.aceptar_invitacion(usuarios.crear_invitacion(email, rol, "developer@skyguardian.mx"), CLAVE)
    c = cliente_sin_sesion(app)
    c.cookies.set(usuarios.COOKIE, usuarios.emitir_sesion(email))
    return c


class TestConsultorEscritorio(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        verificar_aislamiento()
        db.init_db()
        usuarios.sembrar(iteraciones=1000)

    def test_01_permisos_del_middleware(self):
        p = main._permiso_rol
        self.assertIsNone(p("consultor", "/monitor", "GET"))
        self.assertIsNone(p("consultor", "/static/monitor.html", "GET"))
        self.assertIsNone(p("consultor", "/consultar", "GET"))
        self.assertIsNone(p("consultor", "/api/admin/export/excel", "GET"))   # descarga del Excel del lote
        self.assertIsNone(p("general", "/api/admin/export/excel", "GET"))
        self.assertIsNone(p("consultor", "/api/export/excel", "GET"))
        # sigue siendo de solo lectura
        for ruta, metodo in (("/api/tarjetas/1", "PATCH"), ("/api/pcb/1", "DELETE"), ("/api/emparejar/auto", "POST"),
                             ("/api/correo/excel", "POST"), ("/api/sync/excel", "POST"), ("/api/admin/export/excel", "POST")):
            self.assertIsNotNone(p("consultor", ruta, metodo), (ruta, metodo))
        # el resto de Administración sigue cerrado para no administradores
        self.assertIsNotNone(p("general", "/api/admin/usuarios", "GET"))
        self.assertIsNotNone(p("consultor", "/api/admin/movimientos", "GET"))
        # otras páginas siguen cerradas
        for ruta in ("/programar", "/emparejar", "/dymo", "/admin"):
            self.assertEqual(p("consultor", ruta, "GET").headers["location"].split("?")[0], "/consultar", ruta)

    def test_02_inicio_sin_bucles(self):
        c = _cuenta("consulta.escritorio@ejemplo.com", "consultor")
        self.assertEqual(c.get("/monitor", follow_redirects=False).status_code, 200)
        r = c.get("/", follow_redirects=False)
        self.assertEqual((r.status_code, r.headers["location"]), (302, "/consultar?inicio=1"))
        self.assertEqual(c.get("/consultar?inicio=1", follow_redirects=False).status_code, 200)
        self.assertEqual(c.post("/api/lotes", json={"mes": 1, "anio": 2030}).status_code, 403)
        html = (STATIC / "consultar.html").read_text(encoding="utf-8")
        self.assertIn("inicio=1", html)
        self.assertIn("location.replace('/monitor')", html)

    def test_03_descarga_excel_sin_clave_admin(self):
        for email, rol in (("consulta.excel@ejemplo.com", "consultor"), ("general.excel@ejemplo.com", "general")):
            c = _cuenta(email, rol)
            # sin lote: 404 (no 401 de "falta la clave" ni 403 por rol)
            self.assertEqual(c.get("/api/admin/export/excel?lote_id=999999").status_code, 404, rol)
            self.assertEqual(c.get("/api/export/excel?lote_id=999999").status_code, 404, rol)
        # guardar en una carpeta del servidor escribe en disco: sigue pidiendo la clave de administración
        g = _cuenta("general.excel@ejemplo.com", "general")
        self.assertIn(g.get("/api/admin/export/excel?lote_id=999999&ruta=x").status_code, (401, 503))
        # sin sesión de usuario, nada
        self.assertEqual(cliente_sin_sesion(app).get("/api/export/excel").status_code, 401)

    def test_04_frontend(self):
        esc = (STATIC / "js" / "escritorio.js").read_text(encoding="utf-8")
        self.assertIn("SEC_CONSULTOR = new Set(['resumen', 'tarjetas', 'inventario', 'consultar', 'excel'])", esc)
        self.assertIn("T.avisoAcceso('sec:'", esc)
        com = (STATIC / "js" / "common.js").read_text(encoding="utf-8")
        self.assertIn("zona === 'monitor'", com)
        self.assertIn("'data-escribe': true", com)   # "Enviar por correo" se oculta al consultor
        self.assertIn("descargar Excel", com)         # PUEDE_TXT del consultor
        self.assertIn('[data-rol="consultor"] [data-escribe]', (STATIC / "css" / "escritorio.css").read_text(encoding="utf-8"))
        self.assertNotIn("/admin?next=", (STATIC / "js" / "sec_excel.js").read_text(encoding="utf-8"))
        for f in ("sec_tarjetas.js", "sec_inventario.js", "sec_excel.js"):
            self.assertIn("data-escribe", (STATIC / "js" / f).read_text(encoding="utf-8"), f)


if __name__ == "__main__":
    unittest.main()
