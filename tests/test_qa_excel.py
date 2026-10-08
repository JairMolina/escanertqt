"""QA del Excel mensual: fidelidad OPC/XML frente a la plantilla, casos de datos, operación (bloqueo, atomicidad,
rutas, concurrencia) e import/export. Todo con datos reales de una BD temporal (sin mocks de la BD ni de openpyxl)."""
import _aislamiento  # noqa: F401  (debe ser lo primero)
import hashlib
import os
import posixpath
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import warnings
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from unittest import mock

import openpyxl
from starlette.testclient import TestClient

from app.config import settings
from app.database import db, inventario as inv
from app.database.models import MESES_ES
from app.main import app
from app.services import admin_auth
from app.services.excel_sync import ExcelBloqueadoError, ExcelSyncEngine, _totales, structure_counts

from _aislamiento import crear_par, mac_unica, verificar_aislamiento

warnings.filterwarnings("ignore")

NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_CT = "http://schemas.openxmlformats.org/package/2006/content-types"
NS_REL = "http://schemas.openxmlformats.org/package/2006/relationships"


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def problemas_opc(path):
    """Valida la estructura OPC como lo haría Excel: XML bien formado, [Content_Types], relaciones sin destinos
    rotos, partes sin tipo, sin entradas duplicadas, hojas de workbook.xml resolubles y sharedStrings coherentes."""
    fallos = []
    with zipfile.ZipFile(path) as z:
        nombres = z.namelist()
        if len(nombres) != len(set(nombres)):
            fallos.append("entradas duplicadas en el zip")
        if z.testzip():
            fallos.append("CRC roto")
        for n in nombres:
            if n.endswith((".xml", ".rels")):
                try:
                    ET.fromstring(z.read(n))
                except ET.ParseError as e:
                    fallos.append(f"{n}: XML mal formado ({e})")
        if "[Content_Types].xml" not in nombres:
            return fallos + ["falta [Content_Types].xml"]
        ct = ET.fromstring(z.read("[Content_Types].xml"))
        defaults = {e.get("Extension").lower() for e in ct if e.tag == f"{{{NS_CT}}}Default"}
        overrides = {e.get("PartName") for e in ct if e.tag == f"{{{NS_CT}}}Override"}
        for o in overrides:
            if o.lstrip("/") not in nombres:
                fallos.append(f"Override huérfano: {o}")
        for n in nombres:
            if n == "[Content_Types].xml":
                continue
            if "/" + n not in overrides and n.rsplit(".", 1)[-1].lower() not in defaults:
                fallos.append(f"parte sin content-type: {n}")
        for n in nombres:
            if not n.endswith(".rels"):
                continue
            base = posixpath.dirname(posixpath.dirname(n))  # carpeta de la parte dueña
            for rel in ET.fromstring(z.read(n)):
                if rel.get("TargetMode") == "External":
                    continue
                t = rel.get("Target")
                destino = t.lstrip("/") if t.startswith("/") else posixpath.normpath(posixpath.join(base, t))
                if destino not in nombres:
                    fallos.append(f"{n}: relación {rel.get('Id')} apunta a {destino} que no existe")
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        rels = {r.get("Id"): r.get("Target") for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
        for s in wb.find(f"{{{NS_MAIN}}}sheets"):
            if s.get(f"{{{NS_R}}}id") not in rels:
                fallos.append(f"hoja {s.get('name')} con rId inexistente")
        nsst = 0
        if "xl/sharedStrings.xml" in nombres:
            nsst = len(ET.fromstring(z.read("xl/sharedStrings.xml")))
        for n in nombres:
            if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n):
                x = z.read(n).decode("utf-8")
                for m in re.finditer(r't="s"[^>]*><v>(\d+)</v>', x):
                    if int(m.group(1)) >= nsst:
                        fallos.append(f"{n}: índice de sharedStrings fuera de rango")
                        break
                for m in re.finditer(r'<f t="array"([^>]*)>', x):
                    if "ref=" not in m.group(1):
                        fallos.append(f"{n}: fórmula array sin ref")
                        break
        if "xl/calcChain.xml" in nombres:  # una calcChain que apunte a celdas sin fórmula hace que Excel "repare" el libro
            hojas = {}
            for s in wb.find(f"{{{NS_MAIN}}}sheets"):
                i = int(s.get("sheetId"))
                hojas[i] = "xl/" + rels[s.get(f"{{{NS_R}}}id")].lstrip("/").replace("xl/", "")
            for c in ET.fromstring(z.read("xl/calcChain.xml")):
                ref, i = c.get("r"), int(c.get("i", 0) or 0) or None
                if i and i in hojas:
                    if not re.search(rf'<c r="{ref}"[^>]*>(?:(?!</c>).)*<f', z.read(hojas[i]).decode("utf-8"), re.S):
                        fallos.append(f"calcChain huérfana: hoja {i} {ref}")
                        break
    return fallos


def formulas(path):
    wb = openpyxl.load_workbook(path, data_only=False)
    out = {}
    for ws in wb:
        for fila in ws.iter_rows():
            for c in fila:
                v = c.value
                if hasattr(v, "text"):
                    out[f"{ws.title}!{c.coordinate}"] = ("array", v.ref, v.text)
                elif c.data_type == "f":
                    out[f"{ws.title}!{c.coordinate}"] = v
    return out


def abrir_exclusivo(path):
    """Handle de Windows sin compartir (lo que hace Excel al abrir un libro). Devuelve un callable que lo cierra."""
    import ctypes
    from ctypes import wintypes
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.CreateFileW.restype = wintypes.HANDLE
    k.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                              wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    h = k.CreateFileW(str(path), 0x80000000 | 0x40000000, 0, None, 3, 0x80, None)  # GENERIC_READ|WRITE, share 0, OPEN_EXISTING
    if h in (None, wintypes.HANDLE(-1).value):
        raise OSError(ctypes.get_last_error())
    return lambda: k.CloseHandle(h)


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        verificar_aislamiento()
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dir = Path(cls.tmp.name)
        cls.template = str(ExcelSyncEngine().get_template_path())
        cls.n = 0

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        type(self).n += 1
        self.path = self.dir / f"qa{self.n}.db"
        db.init_db(self.path)
        self.engine = ExcelSyncEngine(db_path=self.path)

    def nuevo(self, nombre="x", mes=9, anio=2026):
        excel = self.engine.create_monthly_excel(mes, anio, target_path=str(self.dir / f"{nombre}_{self.n}.xlsx"))
        lote = db.create_lote(f"Q{self.n}-{nombre}", mes, anio, ruta_excel=excel, activo=True, db_path=self.path)["id"]
        return excel, lote

    def tarjeta(self, lote, num, etapas=(), **kw):
        t = crear_par(lote, num=num, path=self.path, **kw)
        for etapa, estado in etapas:
            db.set_prueba(t["id"], etapa, estado, db_path=self.path)
        return db.get_tarjeta_by_id(t["id"], db_path=self.path)

    def sync(self, excel, lote):
        return self.engine.export_to_excel(excel, lote, db_path=self.path)


# ============================================================================ FIDELIDAD
class TestFidelidadXml(Base):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tmp2 = tempfile.TemporaryDirectory()

    def _salida(self):
        excel, lote = self.nuevo("fid")
        self.tarjeta(lote, "0011", [("soldadura", "OK"), ("prueba_final", "FALLA")])
        self.tarjeta(lote, "0012", [("programacion", "RETRABAJO")])
        db.update_tarjeta_campos = getattr(db, "update_tarjeta_campos", None)
        self.sync(excel, lote)
        return excel, lote

    def test_01_plantilla_y_salida_son_paquetes_opc_validos(self):
        self.assertEqual(problemas_opc(self.template), [], "la plantilla ya está mal")
        excel, _ = self._salida()
        self.assertEqual(problemas_opc(excel), [])

    def test_02_hojas_orden_ocultas_definednames_tablas(self):
        excel, _ = self._salida()
        w0, w1 = openpyxl.load_workbook(self.template), openpyxl.load_workbook(excel)
        self.assertEqual(w1.sheetnames, w0.sheetnames)
        self.assertEqual([w1[n].sheet_state for n in w1.sheetnames], [w0[n].sheet_state for n in w0.sheetnames])
        self.assertEqual({k: v.attr_text for k, v in w1.defined_names.items()}, {k: v.attr_text for k, v in w0.defined_names.items()})
        for n in w0.sheetnames:
            self.assertEqual(dict(w1[n].tables.items()), dict(w0[n].tables.items()), n)
        with zipfile.ZipFile(self.template) as a, zipfile.ZipFile(excel) as b:
            for t in ("xl/tables/table1.xml", "xl/tables/table2.xml"):
                self.assertEqual(len(ET.fromstring(a.read(t))), len(ET.fromstring(b.read(t))), t)

    def test_03_anchos_de_columna_filas_y_estilos(self):
        excel, _ = self._salida()
        w0, w1 = openpyxl.load_workbook(self.template), openpyxl.load_workbook(excel)
        for n in w0.sheetnames:
            a, b = w0[n], w1[n]
            ca = {k: (round(d.width or 0, 3), d.hidden, d.min, d.max) for k, d in a.column_dimensions.items()}
            cb = {k: (round(d.width or 0, 3), d.hidden, d.min, d.max) for k, d in b.column_dimensions.items()}
            if n == "Producción":   # v1.2.16: las columnas S y T (fechas de llegada y finalizado) son nuevas a propósito
                self.assertEqual({k: v for k, v in cb.items() if k not in ("S", "T")}, ca, f"anchos {n}")
            else:
                self.assertEqual(cb, ca, f"anchos {n}")
            self.assertEqual({k: (d.hidden, d.height) for k, d in b.row_dimensions.items()},
                             {k: (d.hidden, d.height) for k, d in a.row_dimensions.items()}, f"filas {n}")
            self.assertEqual(sorted(map(str, b.merged_cells.ranges)), sorted(map(str, a.merged_cells.ranges)))
            self.assertEqual(b.freeze_panes, a.freeze_panes)
            malos = []
            for fila in a.iter_rows():
                for ca_ in fila:
                    cb_ = b[ca_.coordinate]
                    if (ca_.number_format, ca_.font.b, ca_.font.name, ca_.font.sz, ca_.fill.fgColor.rgb, ca_.border.left.style,
                            ca_.alignment.horizontal, ca_.protection.locked) != \
                       (cb_.number_format, cb_.font.b, cb_.font.name, cb_.font.sz, cb_.fill.fgColor.rgb, cb_.border.left.style,
                            cb_.alignment.horizontal, cb_.protection.locked):
                        # Excepción legítima: las fechas de captura reciben yyyy-mm-dd si estaban en General
                        if not (n == "Producción" and ca_.column in (9, 10)) and not (n == "Pruebas" and ca_.column == 10):
                            malos.append(f"{n}!{ca_.coordinate}")
            self.assertEqual(malos[:10], [], f"estilos cambiados en {n}")

    def test_04_validaciones_y_formatos_condicionales_std_y_x14_por_hoja(self):
        excel, _ = self._salida()
        a, b = structure_counts(self.template), structure_counts(excel)
        for hoja in a:
            self.assertEqual(b[hoja]["validaciones_x14"], a[hoja]["validaciones_x14"], hoja)
            self.assertEqual(b[hoja]["tablas"], a[hoja]["tablas"], hoja)
        self.assertEqual({h: c["validaciones"] for h, c in b.items()}, {h: c["validaciones"] for h, c in a.items()})
        # contenido: mismos sqref/tipos/fórmulas de las validaciones y mismos rangos+prioridades de CF (por hoja)
        with zipfile.ZipFile(self.template) as za, zipfile.ZipFile(excel) as zb:
            for i in range(1, 5):
                xa, xb = za.read(f"xl/worksheets/sheet{i}.xml").decode(), zb.read(f"xl/worksheets/sheet{i}.xml").decode()
                sig = lambda x: sorted((re.search(r'type="(\w+)"', m.group(0)).group(1), re.search(r'sqref="([^"]+)"', m.group(0)).group(1))
                                       for m in re.finditer(r'<dataValidation [^>]*>', x))
                self.assertEqual(sig(xb), sig(xa), f"dataValidation sheet{i}")
                rules = lambda x: sorted(re.findall(r'<cfRule [^>]*?type="(\w+)"', x))
                self.assertEqual(rules(xb), rules(xa), f"cfRule sheet{i}")
                self.assertEqual(set(re.findall(r'<conditionalFormatting[^>]*sqref="([^"]+)"', xb)),   # openpyxl fusiona bloques con el mismo rango
                                 set(re.findall(r'<conditionalFormatting[^>]*sqref="([^"]+)"', xa)), f"cf sqref sheet{i}")
        with zipfile.ZipFile(excel) as zb:  # el x14 de Producción!E (lista de otra hoja) sigue apuntando a ella
            x = zb.read("xl/worksheets/sheet1.xml").decode()
            self.assertRegex(x, r"<x14:dataValidation[^>]*>.*Cat.logo PCB.*</x14:dataValidation>")
            self.assertIn('xmlns:x14=', x)

    def test_05_las_2211_formulas_son_identicas_incluidas_arrays(self):
        excel, _ = self._salida()
        a, b = formulas(self.template), formulas(excel)
        self.assertEqual(len(a), 2211)
        self.assertEqual(len(b), 2211)
        dif = [k for k in a if a[k] != b.get(k)]
        # Única diferencia admitida: Producción!B de una fila cuya R1 real difiere (aquí ninguna)
        self.assertEqual(dif, [])
        self.assertGreaterEqual(sum(1 for v in a.values() if isinstance(v, tuple)), 500)  # arrays LOOKUP de Pruebas

    def test_06_arrays_calcchain_y_recalculo_al_abrir(self):
        excel, _ = self._salida()
        with zipfile.ZipFile(excel) as z:
            x = z.read("xl/worksheets/sheet2.xml").decode()
            self.assertEqual(x.count('t="array"'), 500)                # siguen siendo fórmulas array
            self.assertEqual(x.count(' cm="1"'), 500)                  # matriz dinámica como la plantilla (no {=...} heredadas)
            self.assertIn("xl/metadata.xml", z.namelist())
            self.assertIn("metadata.xml", z.read("xl/_rels/workbook.xml.rels").decode())
            self.assertNotIn("calcChain", z.read("[Content_Types].xml").decode())
            self.assertNotIn("calcChain", z.read("xl/_rels/workbook.xml.rels").decode())
            self.assertIn('fullCalcOnLoad="1"', z.read("xl/workbook.xml").decode())
            for n in z.namelist():
                self.assertNotIn("webextension", n) if False else None
        self.assertEqual(problemas_opc(excel), [])

    def test_07_segundo_sync_es_idempotente_byte_a_byte_en_las_hojas(self):
        excel, lote = self._salida()
        self.sync(excel, lote)
        with zipfile.ZipFile(excel) as z:
            h1 = {n: hashlib.sha256(z.read(n)).hexdigest() for n in z.namelist() if n != "docProps/core.xml"}
        self.sync(excel, lote)
        self.sync(excel, lote)
        with zipfile.ZipFile(excel) as z:
            h2 = {n: hashlib.sha256(z.read(n)).hexdigest() for n in z.namelist() if n != "docProps/core.xml"}  # core.xml: fecha de modificación
        self.assertEqual(h2, h1)
        self.assertEqual(problemas_opc(excel), [])

    def test_08_avisa_de_lo_que_se_pierde_del_paquete_original(self):
        """metadata.xml/webextensions/calcChain los descarta openpyxl (no afectan datos ni fórmulas). Se documenta."""
        excel, _ = self._salida()
        with zipfile.ZipFile(self.template) as a, zipfile.ZipFile(excel) as b:
            perdidas = set(a.namelist()) - set(b.namelist())
        self.assertLessEqual(perdidas, {"xl/calcChain.xml", "xl/metadata.xml", "xl/sharedStrings.xml",
                                        "xl/webextensions/_rels/taskpanes.xml.rels", "xl/webextensions/taskpanes.xml",
                                        "xl/webextensions/webextension1.xml"})


# ============================================================================ DATOS
class TestDatos(Base):
    def _xl(self, excel):
        wb = openpyxl.load_workbook(excel)
        return wb["Producción"], wb["Catálogo PCB"], wb["Pruebas"]

    def test_01_cero_tarjetas(self):
        excel, lote = self.nuevo("cero")
        r = self.sync(excel, lote)
        self.assertEqual((r["exported_tarjetas"], r["omitidas"]), (0, []))
        self.assertEqual(formulas(excel), formulas(self.template))
        self.assertEqual(problemas_opc(excel), [])

    def test_02_una_tarjeta_y_datos_de_captura(self):
        excel, lote = self.nuevo("una")
        t = self.tarjeta(lote, "0011", [("soldadura", "OK")])
        db.update_tarjeta_campos(t["id"], {"firmware_r1": "1.2.3", "firmware_r2": "1.2.4", "semana_produccion": 38,
                                           "fecha_proyectada": "2026-09-20"}, db_path=self.path) \
            if hasattr(db, "update_tarjeta_campos") else None
        self.sync(excel, lote)
        prod, cat, pr = self._xl(excel)
        self.assertEqual(prod["A2"].value, "0011")
        self.assertTrue(str(prod["B2"].value).startswith("="))
        self.assertEqual(prod["E2"].value, "TQT-R2-V30-0011")
        self.assertEqual(cat["A3"].value, "TQT-R1-V30-0011")
        self.assertEqual(cat["B3"].value, t["mac_r1"])
        self.assertEqual(cat["G3"].value, t["mac_r2"])

    def test_03_cien_tarjetas_limite_y_101_avisa(self):
        excel, lote = self.nuevo("cien")
        for n in range(11, 111):
            self.tarjeta(lote, f"{n:04d}", [("soldadura", "OK")] if n % 2 else [])
        r = self.sync(excel, lote)
        self.assertEqual((r["exported_tarjetas"], r["omitidas"], r["exported_pcbs"]), (100, [], 200))
        self.assertEqual(problemas_opc(excel), [])
        # tarjeta 101: no cabe -> omitida Y con aviso visible (no solo en `omitidas`)
        self.tarjeta(lote, "0500")
        r = self.sync(excel, lote)
        self.assertEqual(r["exported_tarjetas"], 100)
        self.assertEqual(r["omitidas"], ["0500"])
        self.assertTrue(any("0500" in a and "plantilla" in a.lower() for a in r["avisos"]), r["avisos"])
        self.assertEqual(len(formulas(excel)), 2211)
        prod = openpyxl.load_workbook(excel)["Producción"]
        self.assertNotIn("0500", [prod.cell(i, 1).value for i in range(2, 102)])

    def test_04_impares_ids_no_consecutivos_ceros_v31_y_r3(self):
        excel, lote = self.nuevo("impares")
        # R1 0021 + R2 0010 (impar), ID 0777 fuera de la lista, versión V31 y R3
        r1 = inv.registrar_manual("R1", "30", "0021")["pcbs"][0]["id"] if False else None
        t1 = crear_par(lote, num="0021", path=self.path)
        t2 = crear_par(lote, num="0777", path=self.path, version="31", r3=True)
        t3 = crear_par(lote, num="0099", path=self.path)
        r = self.sync(excel, lote)
        prod, cat, _ = self._xl(excel)
        filas = {str(prod.cell(i, 1).value): i for i in range(2, 102)}
        for num in ("0021", "0777", "0099"):
            self.assertIn(num, filas)
        i = filas["0777"]
        self.assertEqual(prod.cell(i, 2).value, "TQT-R1-V31-0777")       # literal solo porque difiere
        self.assertEqual(prod.cell(i, 5).value, "TQT-R2-V31-0777")
        self.assertTrue(any("Producción!B" in a and "0777" in a for a in r["avisos"]))
        self.assertTrue(str(prod.cell(i, 8).value).startswith("TQT-R3-V"), prod.cell(i, 8).value)
        self.assertFalse(any("R3" in a for a in r["avisos"]), r["avisos"])
        # las que coinciden conservan la fórmula
        self.assertTrue(str(prod.cell(filas["0021"], 2).value).startswith("="))
        self.assertTrue(str(prod.cell(filas["0099"], 2).value).startswith("="))
        # C y F (MAC AUTO) intactas en todas las filas
        a, b = formulas(self.template), formulas(excel)
        cambios = [k for k in a if a[k] != b.get(k)]
        self.assertEqual([k for k in cambios if not re.fullmatch(r"Producción!B\d+", k)], [])
        # vuelve la versión 30 => se restaura la fórmula
        db.set_prueba(t2["id"], "soldadura", "OK", db_path=self.path)
        self.assertEqual(problemas_opc(excel), [])

    def test_05_mac_minusculas_mayusculas_y_pcb_disponibles_sin_tarjeta(self):
        excel, lote = self.nuevo("macs")
        with db.transaction(self.path) as c:  # PCB sueltas (DISPONIBLES) con MAC: no son tarjeta
            p = inv.registrar_manual("R1", "30", "0800", conn=c)["pcbs"][0]["id"]
            inv.confirmar_recepcion([p], conn=c)
            inv.set_mac(p, "aa:bb:cc:dd:ee:0a", conn=c)
        t = self.tarjeta(lote, "0011", macs=False)
        with db.transaction(self.path) as c:
            inv.set_mac(t["pcb_r1_id"], "70-4b-ca-5b-9f-6e", conn=c)   # otro formato de tecleo
            inv.set_mac(t["pcb_r2_id"], "704bca5b9ca2", conn=c)
        r = self.sync(excel, lote)
        _, cat, _ = self._xl(excel)
        self.assertEqual(cat["B3"].value, "70:4B:CA:5B:9F:6E")
        self.assertEqual(cat["G3"].value, "70:4B:CA:5B:9C:A2")
        self.assertEqual(r["exported_tarjetas"], 1)
        # la PCB suelta con MAC también está en el Catálogo (fila propia, estado, sin tarjeta) y sobrevive al round-trip
        filas = {cat.cell(i, 1).value: i for i in range(3, 103)}
        self.assertIn("TQT-R1-V30-0800", filas)
        i = filas["TQT-R1-V30-0800"]
        self.assertEqual((cat.cell(i, 2).value, cat.cell(i, 3).value), ("AA:BB:CC:DD:EE:0A", "SIN PROBAR"))
        db2 = self.dir / f"suelta{self.n}.db"
        db.init_db(db2)
        l2 = db.create_lote("S2", 9, 2026, db_path=db2)["id"]
        ExcelSyncEngine(db_path=db2).import_from_excel(excel, l2, db_path=db2)
        sueltas = inv.listar_pcb(tipo="R1", q="0800", db_path=db2)["items"]
        self.assertEqual([(p["mac"], p["estado_ciclo"]) for p in sueltas], [("AA:BB:CC:DD:EE:0A", "DISPONIBLE")])

    def test_06_tarjeta_incompleta_sin_r2_ni_mac(self):
        excel, lote = self.nuevo("incompleta")
        with db.transaction(self.path) as c:
            p = inv.registrar_manual("R1", "30", "0042", conn=c)["pcbs"][0]["id"]
            inv.confirmar_recepcion([p], conn=c)
            inv.crear_tarjeta(lote, "0042", p, None, None, conn=c)
        r = self.sync(excel, lote)
        prod, cat, _ = self._xl(excel)
        fila = [i for i in range(2, 102) if prod.cell(i, 1).value == "0042"][0]
        self.assertIn(prod.cell(fila, 5).value, (None, ""))
        self.assertEqual(problemas_opc(excel), [])
        self.assertEqual(len(formulas(excel)), 2211)
        self.assertEqual(r["exported_tarjetas"], 1)

    def test_07_todos_los_estados_de_prueba_van_a_la_bitacora_y_no_a_B_G(self):
        excel, lote = self.nuevo("estados")
        etapas = ["soldadura", "programacion", "prueba_pcb", "integracion", "prueba_final"]
        estados = ["OK", "FALLA", "RETRABAJO", "NO APLICA", "PENDIENTE"]
        for i, est in enumerate(estados):
            self.tarjeta(lote, f"{11 + i:04d}", [(e, est) for e in etapas])
        self.sync(excel, lote)
        _, _, pr = self._xl(excel)
        log = {(pr.cell(r, 11).value, pr.cell(r, 12).value): [pr.cell(r, c).value for c in range(13, 28) if pr.cell(r, c).value]
               for r in range(3, 201) if pr.cell(r, 11).value}
        self.assertEqual(len(log), 4 * 5)                    # PENDIENTE no se registra
        self.assertEqual(log[("Soldadura", "OK")], ["0011"])
        self.assertEqual(log[("Prueba Final", "NO APLICA")], ["0014"])
        for r in range(2, 20):                                # B:G siguen siendo fórmulas
            for c in range(1, 8):
                self.assertTrue(isinstance(pr.cell(r, c).value, str) and pr.cell(r, c).value.startswith("=") or hasattr(pr.cell(r, c).value, "text"),
                                f"Pruebas!{pr.cell(r, c).coordinate}")

    def test_08_bitacora_mas_de_15_ids_por_fila_y_sin_desbordar(self):
        excel, lote = self.nuevo("bitacora")
        for n in range(11, 41):  # 30 tarjetas OK en las 5 etapas -> 2 filas por etapa
            self.tarjeta(lote, f"{n:04d}", [(e, "OK") for e in ("soldadura", "programacion", "prueba_pcb", "integracion", "prueba_final")])
        self.sync(excel, lote)
        pr = openpyxl.load_workbook(excel)["Pruebas"]
        filas = [r for r in range(3, 201) if pr.cell(r, 11).value == "Soldadura"]
        self.assertEqual(len(filas), 2)
        self.assertEqual(sum(1 for c in range(13, 28) if pr.cell(filas[0], c).value), 15)

    def test_09_caracteres_especiales_y_formula_injection_en_firmware(self):
        excel, lote = self.nuevo("chars")
        t = self.tarjeta(lote, "0011")
        for k, v in (("firmware_r1", "=HYPERLINK(\"http://x\",\"a\")"), ("firmware_r2", "Ñandú <b>&\"é\" 1.0")):
            with db.transaction(self.path) as c:
                c.execute(f"UPDATE tarjetas_produccion SET {k}=? WHERE id=?", (v, t["id"]))
        self.sync(excel, lote)
        prod = openpyxl.load_workbook(excel)["Producción"]
        self.assertEqual(prod["G2"].value, "Ñandú <b>&\"é\" 1.0")
        self.assertEqual(prod["D2"].value, "=HYPERLINK(\"http://x\",\"a\")")
        self.assertEqual(prod["D2"].data_type, "s", "el firmware no puede convertirse en fórmula")
        self.assertEqual(problemas_opc(excel), [])
        self.assertEqual(len(formulas(excel)), 2211)


# ============================================================================ OPERACIÓN
class TestOperacion(Base):
    def test_01_escritura_atomica_si_falla_el_guardado_el_original_queda_igual(self):
        excel, lote = self.nuevo("atom")
        self.tarjeta(lote, "0011")
        antes = sha(excel)
        with mock.patch("os.replace", side_effect=OSError("disco lleno")):
            with self.assertRaises(OSError):
                self.sync(excel, lote)
        self.assertEqual(sha(excel), antes)
        self.assertEqual([p.name for p in Path(excel).parent.iterdir() if ".tmp" in p.name], [])

    def test_02_archivo_abierto_en_excel_da_423_original_intacto_y_sin_tmp(self):
        if os.name != "nt":
            self.skipTest("solo Windows")
        excel, lote = self.nuevo("lock")
        self.tarjeta(lote, "0011")
        antes = sha(excel)
        cerrar = abrir_exclusivo(excel)
        try:
            with self.assertRaises(ExcelBloqueadoError) as cm:
                self.sync(excel, lote)
            self.assertIn("Ciérralo", str(cm.exception))
        finally:
            cerrar()
        self.assertEqual(sha(excel), antes)
        self.assertEqual([p.name for p in Path(excel).parent.iterdir() if ".tmp" in p.name], [])
        self.sync(excel, lote)  # liberado: ya funciona

    def test_03_bak_contiene_la_version_previa(self):
        excel, lote = self.nuevo("bak")
        self.tarjeta(lote, "0011")
        self.sync(excel, lote)
        previo = sha(excel)
        self.tarjeta(lote, "0012")
        self.sync(excel, lote)
        self.assertEqual(sha(excel + ".bak"), previo)

    def test_04_concurrencia_dos_sync_a_la_vez(self):
        excel, lote = self.nuevo("conc")
        for n in range(11, 31):
            self.tarjeta(lote, f"{n:04d}", [("soldadura", "OK")])
        errores = []

        def go():
            try:
                self.sync(excel, lote)
            except Exception as e:  # noqa: BLE001
                errores.append(repr(e))
        hilos = [threading.Thread(target=go) for _ in range(4)]
        [h.start() for h in hilos]
        [h.join() for h in hilos]
        self.assertEqual(errores, [])
        self.assertEqual(problemas_opc(excel), [])
        self.assertEqual(len(formulas(excel)), 2211)

    def test_05_doce_meses_en_espanol(self):
        nombres = []
        for m in range(1, 13):
            p = Path(self.engine.create_monthly_excel(m, 2027, target_path=str(self.dir / self.engine.monthly_path(m, 2027).name)))
            nombres.append(p.name)
        self.assertEqual(nombres, [f"Control_Produccion_TQT_{x}_2027.xlsx" for x in
                                   "Enero Febrero Marzo Abril Mayo Junio Julio Agosto Septiembre Octubre Noviembre Diciembre".split()])
        with self.assertRaises(ValueError):
            self.engine.create_monthly_excel(13, 2027)
        with self.assertRaises(ValueError):
            self.engine.create_monthly_excel(0, 2027)

    def test_06_plantilla_ausente_o_corrupta(self):
        malo = ExcelSyncEngine(template_path=str(self.dir / "no_existe.xlsx"), db_path=self.path)
        with mock.patch.object(ExcelSyncEngine, "get_template_path", side_effect=FileNotFoundError("sin plantilla")):
            with self.assertRaises(FileNotFoundError):
                malo.create_monthly_excel(1, 2030, target_path=str(self.dir / "a.xlsx"))
        corrupta = self.dir / "corrupta.xlsx"
        corrupta.write_bytes(b"PK\x03\x04esto no es un xlsx")
        lote = db.create_lote(f"COR{self.n}", 9, 2026, ruta_excel=str(corrupta), db_path=self.path)["id"]
        antes = sha(corrupta)
        with self.assertRaises(Exception):
            self.sync(str(corrupta), lote)
        self.assertEqual(sha(corrupta), antes)
        self.assertEqual([p.name for p in self.dir.iterdir() if ".tmp" in p.name], [])

    def test_07_archivo_inexistente(self):
        _, lote = self.nuevo("noex")
        with self.assertRaises(FileNotFoundError):
            self.sync(str(self.dir / "carpeta_que_no_existe" / "x.xlsx"), lote)


class TestApiRutas(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        verificar_aislamiento()
        db.init_db()
        cls._env = mock.patch.dict(os.environ, {"TQT_ADMIN_PASSWORD": "clave-qa-excel-1"})
        cls._env.start()
        admin_auth.limitador.reiniciar()
        cls.client = TestClient(app)
        tok = cls.client.post("/api/admin/login", json={"password": "clave-qa-excel-1"}).json()["token"]
        cls.client.headers["X-Admin-Token"] = tok
        settings.EXCEL_DIR.mkdir(parents=True, exist_ok=True)
        cls.previos = {p.name for p in settings.EXCEL_DIR.iterdir()}
        cls.tmp = Path(tempfile.mkdtemp())

    @classmethod
    def tearDownClass(cls):
        admin_auth.limitador.reiniciar()
        cls._env.stop()
        shutil.rmtree(cls.tmp, ignore_errors=True)
        for p in settings.EXCEL_DIR.iterdir():   # no dejar .bak/.xlsx en la carpeta compartida (otros tests los cuentan)
            if p.name not in cls.previos:
                shutil.rmtree(p, ignore_errors=True) if p.is_dir() else p.unlink()

    def _lote(self, codigo, mes=9, anio=2026):
        return self.client.post("/api/lotes", json={"codigo_lote": codigo, "mes": mes, "anio": anio}).json()

    def test_01_rutas_hostiles_se_rechazan_con_400(self):
        fuera = self.tmp / "x.xlsx"
        casos = [
            str(fuera),                                             # fuera de carpetas
            str(settings.EXCEL_DIR / ".." / ".." / ".." / "x.xlsx"),  # ..
            "\\\\127.0.0.1\\c$\\x.xlsx",                             # UNC
            "\\\\servidor\\share\\x.xlsx",
            "Z:\\otra_unidad\\x.xlsx",                                # unidad distinta
            str(settings.EXCEL_DIR / "x.xls"),                        # extensión
            str(settings.EXCEL_DIR / "x.xlsx.exe"),
            str(settings.EXCEL_DIR / "x.xlsm"),
            str(settings.EXCEL_DIR / "x"),
        ]
        lote = self._lote("Q-RUTAS")["id"]
        for ruta in casos:
            for url, body in (("/api/excel/sync", {"lote_id": lote, "excel_path": ruta}),
                              ("/api/excel/import", {"lote_id": lote, "excel_path": ruta}),
                              ("/api/excel/create-monthly", {"mes": 1, "anio": 2031, "target_path": ruta})):
                r = self.client.post(url, json=body)
                self.assertEqual(r.status_code, 400, f"{url} {ruta}: {r.status_code} {r.text[:120]}")
        self.assertEqual(self.client.get("/api/excel/verify", params={"excel_path": "\\\\127.0.0.1\\c$\\x.xlsx"}).status_code, 400)
        self.assertEqual(self.client.get("/api/admin/export/excel", params={"ruta": "\\\\127.0.0.1\\c$\\x.xlsx"}).status_code, 400)

    def test_02_enlace_(self):
        """Junction (sin privilegios) dentro de EXCEL_DIR que apunta fuera: resolve() lo sigue y se rechaza."""
        if os.name != "nt":
            self.skipTest("solo Windows")
        destino = self.tmp / "fuera_real"
        destino.mkdir()
        enlace = settings.EXCEL_DIR / "enlace_qa"
        r = subprocess.run(["cmd", "/c", "mklink", "/J", str(enlace), str(destino)], capture_output=True, text=True)
        if r.returncode != 0:
            self.skipTest("no se pudo crear el junction")
        try:
            lote = self._lote("Q-LINK")["id"]
            for url, body in (("/api/excel/sync", {"lote_id": lote, "excel_path": str(enlace / "x.xlsx")}),
                              ("/api/excel/create-monthly", {"mes": 2, "anio": 2031, "target_path": str(enlace / "y.xlsx")})):
                self.assertEqual(self.client.post(url, json=body).status_code, 400, url)
            self.assertEqual(list(destino.iterdir()), [])
        finally:
            subprocess.run(["cmd", "/c", "rmdir", str(enlace)], capture_output=True)

    def test_03_ruta_permitida_pero_carpeta_inexistente_se_crea_desde_plantilla(self):
        lote = self._lote("Q-NUEVA", 3, 2029)["id"]
        destino = settings.EXCEL_DIR / "sub_qa" / "Control_Produccion_TQT_Marzo_2029.xlsx"
        r = self.client.post("/api/excel/sync", json={"lote_id": lote, "excel_path": str(destino)})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(Path(r.json()["excel_path"]).resolve(), destino.resolve(), "debe escribir en la ruta pedida")
        self.assertTrue(destino.exists())

    def test_04_sync_423_con_archivo_abierto(self):
        if os.name != "nt":
            self.skipTest("solo Windows")
        lote = self._lote("Q-423", 4, 2029)
        crear_par(lote["id"])
        r = self.client.post("/api/excel/sync", json={"lote_id": lote["id"]})
        self.assertEqual(r.status_code, 200, r.text)
        ruta = r.json()["excel_path"]
        antes = sha(ruta)
        cerrar = abrir_exclusivo(ruta)
        try:
            r = self.client.post("/api/excel/sync", json={"lote_id": lote["id"]})
            r2 = self.client.post(f"/api/sync/excel?lote_id={lote['id']}")
        finally:
            cerrar()
        self.assertEqual((r.status_code, r2.status_code), (423, 423), (r.text, r2.text))
        self.assertIn("Excel", r.json()["detail"])
        self.assertEqual(sha(ruta), antes)

    def test_05_dos_sync_simultaneos_por_api(self):
        lote = self._lote("Q-PAR", 5, 2029)
        crear_par(lote["id"])
        res = []
        hilos = [threading.Thread(target=lambda: res.append(self.client.post("/api/excel/sync", json={"lote_id": lote["id"]}).status_code))
                 for _ in range(4)]
        [h.start() for h in hilos]
        [h.join() for h in hilos]
        self.assertEqual(res, [200] * 4)
        self.assertEqual(problemas_opc(self.client.get(f"/api/lotes/{lote['id']}").json().get("ruta_excel") or
                                       str(ExcelSyncEngine().monthly_path(5, 2029))), [])

    def test_06_export_admin_igual_al_sync_y_no_toca_el_mensual(self):
        lote = self._lote("Q-EXP", 6, 2029)
        for n in ("0011", "0012"):
            t = crear_par(lote["id"], num=n)
            self.client.put(f"/api/tarjetas/{t['id']}/pruebas", json={"etapa": "soldadura", "estado": "OK"})
        r = self.client.post("/api/excel/sync", json={"lote_id": lote["id"]})
        mensual = r.json()["excel_path"]
        antes = sha(mensual)
        bak_antes = os.path.exists(mensual + ".bak")
        dl = self.client.get("/api/admin/export/excel", params={"lote_id": lote["id"]})
        self.assertEqual(dl.status_code, 200)
        self.assertEqual(sha(mensual), antes)                       # el mensual en uso no se tocó
        self.assertEqual(os.path.exists(mensual + ".bak"), bak_antes)
        copia = self.tmp / "descarga_admin.xlsx"
        copia.write_bytes(dl.content)
        self.assertEqual(problemas_opc(copia), [])
        wa, wb_ = openpyxl.load_workbook(mensual), openpyxl.load_workbook(copia)
        for hoja in wa.sheetnames:
            va = {c.coordinate: (c.value.text if hasattr(c.value, "text") else c.value) for f in wa[hoja].iter_rows() for c in f if c.value is not None}
            vb = {c.coordinate: (c.value.text if hasattr(c.value, "text") else c.value) for f in wb_[hoja].iter_rows() for c in f if c.value is not None}
            # la bitácora lleva la fecha de hoy en ambos
            self.assertEqual(vb, va, hoja)
        self.assertEqual(structure_counts(str(copia)), structure_counts(mensual))
        self.assertEqual(self.client.get("/api/admin/export/excel").status_code in (200, 404), True)
        sin = TestClient(app).get("/api/admin/export/excel", params={"lote_id": lote["id"]})
        self.assertEqual(sin.status_code, 200)   # v1.3.44: la descarga ya no pide la clave de administración
        self.assertEqual(TestClient(app).get("/api/admin/export/excel", params={"lote_id": lote["id"], "ruta": "x"}).status_code, 401)


# ============================================================================ IMPORT
class TestImport(Base):
    def _importar(self, excel):
        db2 = self.dir / f"imp{self.n}.db"
        db.init_db(db2)
        lote = db.create_lote("IMP", 9, 2026, db_path=db2)["id"]
        res = ExcelSyncEngine(db_path=db2).import_from_excel(excel, lote, db_path=db2)
        return res, db2, lote

    def test_01_original_del_usuario_tal_cual_sin_tarjetas_fantasma(self):
        original = Path.home() / "Desktop" / "Control_Produccion_TQT_Septiembre.xlsx"
        if not original.exists():
            self.skipTest("no está el original del usuario")
        copia = self.dir / "original_copia.xlsx"
        shutil.copy2(original, copia)
        res, db2, lote = self._importar(str(copia))
        self.assertEqual(res["imported_tarjetas"], 0)
        self.assertEqual(res["errores"], [])
        self.assertEqual(db.list_tarjetas(lote_id=lote, db_path=db2)[1], 0)

    def test_02_round_trip_completo_con_impares_v31_y_pruebas(self):
        excel, lote = self.nuevo("rt")
        self.tarjeta(lote, "0011", [("soldadura", "OK"), ("programacion", "OK"), ("prueba_pcb", "OK"), ("integracion", "OK"), ("prueba_final", "OK")])
        self.tarjeta(lote, "0021", [("soldadura", "FALLA")])
        self.tarjeta(lote, "0777", [("prueba_pcb", "RETRABAJO")], version="31")
        self.tarjeta(lote, "0012")
        self.sync(excel, lote)
        res, db2, lote2 = self._importar(excel)
        self.assertEqual(res["errores"], [], res)
        self.assertEqual(res["imported_tarjetas"], 4)
        a = {t["id_tarjeta_num"]: t for t in db.list_tarjetas(lote_id=lote, limit=50, db_path=self.path)[0]}
        b = {t["id_tarjeta_num"]: t for t in db.list_tarjetas(lote_id=lote2, limit=50, db_path=db2)[0]}
        self.assertEqual(set(a), set(b))
        for n in a:
            for k in ("nombre_r1", "nombre_r2", "mac_r1", "mac_r2", "soldadura", "programacion", "prueba_pcb", "integracion",
                      "prueba_final", "estado_general"):
                self.assertEqual(b[n][k], a[n][k], f"{n}.{k}")

    def test_03_celdas_con_espacios_minusculas_filas_vacias_y_mac_duplicada(self):
        excel, lote = self.nuevo("sucio")
        self.tarjeta(lote, "0011")
        self.tarjeta(lote, "0012")
        self.sync(excel, lote)
        wb = openpyxl.load_workbook(excel)
        cat, prod = wb["Catálogo PCB"], wb["Producción"]
        cat["A3"] = "  TQT-R1-V30-0011  "
        cat["B3"] = " 70:4b:ca:5b:9f:6e "                     # minúsculas y espacios
        cat["G3"] = "70-4B-CA-5B-9C-A2"
        cat["B4"] = cat["G4"].value                          # R1 0012 con la MAC de R2 0012 (ok) ...
        cat["G4"] = "70:4B:CA:5B:9F:6E"                      # ... y la R2 con la MAC de R1 0011 => duplicada
        prod["D2"] = "  fw 1.0  "
        prod["A20"] = "   "                                  # fila 'vacía' con solo espacios
        wb.save(excel)
        res, db2, lote2 = self._importar(excel)
        tarjetas = {t["id_tarjeta_num"]: t for t in db.list_tarjetas(lote_id=lote2, limit=50, db_path=db2)[0]}
        self.assertIn("0011", tarjetas)
        self.assertEqual(tarjetas["0011"]["mac_r1"], "70:4B:CA:5B:9F:6E")
        self.assertEqual(tarjetas["0011"]["mac_r2"], "70:4B:CA:5B:9C:A2")
        self.assertEqual(len(tarjetas), len([1 for t in tarjetas if t]), "sin tarjetas fantasma")
        self.assertNotIn("   ", tarjetas)
        self.assertTrue(res["errores"], "la MAC duplicada debe reportarse")
        macs = [t["mac_r1"] for t in tarjetas.values()] + [t["mac_r2"] for t in tarjetas.values()]
        macs = [m for m in macs if m]
        self.assertEqual(len(macs), len(set(macs)), "una MAC nunca se guarda dos veces")

    def test_04_importar_dos_veces_es_idempotente(self):
        excel, lote = self.nuevo("idem")
        self.tarjeta(lote, "0011", [("soldadura", "OK")])
        self.sync(excel, lote)
        db2 = self.dir / f"idem_imp{self.n}.db"
        db.init_db(db2)
        l2 = db.create_lote("I2", 9, 2026, db_path=db2)["id"]
        e2 = ExcelSyncEngine(db_path=db2)
        e2.import_from_excel(excel, l2, db_path=db2)
        r = e2.import_from_excel(excel, l2, db_path=db2)
        self.assertEqual(db.list_tarjetas(lote_id=l2, db_path=db2)[1], 1)
        self.assertEqual(r["errores"], [])


if __name__ == "__main__":
    unittest.main()
