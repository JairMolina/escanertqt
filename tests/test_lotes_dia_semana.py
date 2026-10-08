"""v1.3.44: lotes de MES, SEMANA o DÍA (varios lotes en el mismo mes, cada uno con su código, nombre y Excel propio)."""
import _aislamiento  # noqa: F401  (debe ser lo primero)
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app.database import admin_ops, db
from app.main import app
from app.routers import api
from app.routers.excel_dymo import excel_engine
from app.services import usuarios

from _aislamiento import cliente_sin_sesion, verificar_aislamiento

ADMIN = "developer@skyguardian.mx"
STATIC = Path(__file__).resolve().parent.parent / "app" / "static"


class TestNormalizar(unittest.TestCase):
    def test_01_codigos_y_mes_de_la_fecha(self):
        m = db.normalizar_lote("mes", None, 2091, 9)
        self.assertEqual((m["codigo_lote"], m["fecha_inicio"], m["anio"], m["mes"]), ("2091-09", "2091-09-01", 2091, 9))
        s = db.normalizar_lote("semana", "2026-10-01")   # jueves -> lunes 28 sep, semana ISO 40
        self.assertEqual((s["codigo_lote"], s["fecha_inicio"], s["mes"]), ("2026-S40", "2026-09-28", 9))
        d = db.normalizar_lote("dia", "2026-09-15")
        self.assertEqual((d["codigo_lote"], d["fecha_inicio"], d["anio"], d["mes"]), ("2026-09-15", "2026-09-15", 2026, 9))
        for malo in (("hora", "2026-09-15"), ("dia", "2026-13-40"), ("dia", None), ("dia", "2019-01-01")):
            with self.assertRaises(ValueError):
                db.normalizar_lote(*malo)

    def test_02_nombres_y_archivos(self):
        self.assertEqual(db.nombre_lote_de({"mes": 9, "anio": 2026, "codigo_lote": "2026-09"}), "Septiembre 2026")
        sem = {**db.normalizar_lote("semana", "2026-09-28")}
        self.assertEqual(db.nombre_lote_de(sem), "Semana 40 · 28 sep–4 oct 2026")
        self.assertEqual(db.nombre_lote_de(db.normalizar_lote("semana", "2025-12-31")), "Semana 1 · 29 dic 2025–4 ene 2026")
        dia = db.normalizar_lote("dia", "2026-09-15")
        self.assertEqual(db.nombre_lote_de(dia), "15 sep 2026")
        mes = db.normalizar_lote("mes", None, 2026, 9)
        nombres = {db.archivo_excel_lote(x) for x in (mes, sem, dia)}
        self.assertEqual(len(nombres), 3, nombres)
        self.assertIn("Control_Produccion_TQT_Septiembre_2026.xlsx", nombres)   # el mensual conserva el nombre histórico
        self.assertEqual(excel_engine.lote_path(mes), excel_engine.monthly_path(9, 2026))


class TestMigracion(unittest.TestCase):
    def test_03_bd_vieja_queda_como_mes(self):
        tmp = Path(tempfile.mkdtemp(prefix="tqt_lotes_"))
        ruta = tmp / "vieja.db"
        db.init_db(ruta)
        with sqlite3.connect(ruta) as c:   # simula una base anterior: sin columnas nuevas
            c.execute("ALTER TABLE lotes_mensuales DROP COLUMN tipo_lote")
            c.execute("ALTER TABLE lotes_mensuales DROP COLUMN fecha_inicio")
            c.execute("INSERT INTO lotes_mensuales (codigo_lote, mes, anio, activo) VALUES ('2090-03', 3, 2090, 0)")
        db.init_db(ruta)
        lotes = db.list_lotes(db_path=ruta)
        viejo = next(l for l in lotes if l["codigo_lote"] == "2090-03")
        self.assertEqual((viejo["tipo_lote"], viejo["fecha_inicio"], viejo["nombre"]), ("mes", "2090-03-01", "Marzo 2090"))
        self.assertTrue(all(l["tipo_lote"] == "mes" and l["fecha_inicio"] for l in lotes))


class TestApiLotes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        verificar_aislamiento()
        db.init_db()
        usuarios.sembrar(iteraciones=1000)

    def setUp(self):
        self.c = cliente_sin_sesion(app)
        self.c.cookies.set(usuarios.COOKIE, usuarios.emitir_sesion(ADMIN))
        self.activo = db.get_active_lote()

        async def falso(ev, data=None):
            return None
        p = mock.patch.object(api.manager, "broadcast", side_effect=falso)
        p.start(); self.addCleanup(p.stop)
        if self.activo:
            self.addCleanup(db.set_active_lote, self.activo["id"])

    def _crear(self, **cuerpo):
        cuerpo.setdefault("crear_excel", False)
        cuerpo.setdefault("activo", False)
        return self.c.post("/api/lotes", json=cuerpo)

    def test_04_varios_lotes_del_mismo_mes(self):
        r_mes = self._crear(tipo_lote="mes", mes=5, anio=2093)
        r_sem = self._crear(tipo_lote="semana", fecha_inicio="2093-05-13")   # miércoles
        r_dia = self._crear(tipo_lote="dia", fecha_inicio="2093-05-20")
        r_dia2 = self._crear(tipo_lote="dia", fecha_inicio="2093-05-21", activo=True)
        for r in (r_mes, r_sem, r_dia, r_dia2):
            self.assertEqual(r.status_code, 201, r.text)
        self.assertEqual(r_mes.json()["codigo_lote"], "2093-05")
        sem = r_sem.json()
        self.assertEqual((sem["tipo_lote"], sem["fecha_inicio"], sem["anio"], sem["mes"]), ("semana", "2093-05-11", 2093, 5))
        self.assertTrue(sem["codigo_lote"].startswith("2093-S"))
        self.assertEqual(r_dia.json()["nombre"], "20 may 2093")
        self.assertEqual(db.get_active_lote()["id"], r_dia2.json()["id"])
        # repetido -> 409 con el nombre del lote
        r = self._crear(tipo_lote="dia", fecha_inicio="2093-05-20")
        self.assertEqual(r.status_code, 409)
        self.assertIn("20 may 2093", r.json()["detail"])
        self.assertEqual(self._crear(tipo_lote="semana", fecha_inicio="2093-05-16").status_code, 409)   # misma semana
        # orden por fecha de inicio desc
        ids = [l["id"] for l in self.c.get("/api/lotes").json() if l["anio"] == 2093]
        self.assertEqual(ids, [r_dia2.json()["id"], r_dia.json()["id"], r_sem.json()["id"], r_mes.json()["id"]])
        res = admin_ops.resumen()
        fila = next(l for l in res["lotes"] if l["id"] == r_sem.json()["id"])
        self.assertTrue(fila["nombre"].startswith("Semana "))

    def test_05_compatibilidad_cuerpo_viejo_y_errores(self):
        r = self._crear(codigo_lote="2094-02", mes=2, anio=2094)   # cliente anterior (sin tipo)
        self.assertEqual(r.status_code, 201, r.text)
        self.assertEqual((r.json()["tipo_lote"], r.json()["fecha_inicio"]), ("mes", "2094-02-01"))
        self.assertEqual(self._crear(tipo_lote="dia").status_code, 400)
        self.assertEqual(self._crear(tipo_lote="hora", fecha_inicio="2094-02-01").status_code, 422)
        self.assertEqual(self._crear(tipo_lote="dia", fecha_inicio="2094-02-30").status_code, 400)

    def test_06_excel_propio_por_lote(self):
        if not excel_engine.template_path.exists():
            self.skipTest("Sin plantilla de Excel")
        r = self._crear(tipo_lote="dia", fecha_inicio="2095-07-04", crear_excel=True)
        self.assertEqual(r.status_code, 201, r.text)
        ruta = r.json()["ruta_excel"]
        self.assertTrue(ruta and Path(ruta).name == "Control_Produccion_TQT_Julio_2095_Dia04.xlsx", ruta)
        self.assertTrue(Path(ruta).exists())

    def test_07_frontend(self):
        js = (STATIC / "js" / "common.js").read_text(encoding="utf-8")
        for txt in ("tipo_lote", "ordenarLotes", "id: 'nlTipo'", "Semana ${"):
            self.assertIn(txt, js)
        css = (STATIC / "css" / "escritorio.css").read_text(encoding="utf-8")
        self.assertIn("text-overflow: ellipsis", css.split(".esc-lote .nm", 1)[1].split("\n", 1)[0])


if __name__ == "__main__":
    unittest.main()
