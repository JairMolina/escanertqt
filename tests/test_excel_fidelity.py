"""Fidelidad del .xlsx mensual: cero pérdida de validaciones, formatos condicionales, tablas y fórmulas.

Compara ORIGEN vs SALIDA contando en el XML crudo, hoja por hoja:
  validaciones de datos (estándar + x14), reglas de formato condicional (estándar + x14) y tablas.
También prueba: XML bien formado, atomicidad, no sobrescritura del mensual y round-trip export -> import.
"""
import _aislamiento  # noqa: F401  (debe ser lo primero)
import hashlib
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from unittest import mock

import openpyxl

from app.database import db, inventario as inv
from app.services import excel_sync
from app.services.excel_sync import (
    ExcelBloqueadoError, ExcelIntegrityError, ExcelSyncEngine, _totales, structure_counts,
)

from _aislamiento import crear_par, mac_unica, verificar_aislamiento


def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def _formulas(path):
    wb = openpyxl.load_workbook(path, data_only=False)
    out = {}
    for ws in wb:
        for fila in ws.iter_rows():
            for c in fila:
                v = c.value
                if hasattr(v, "text") or (isinstance(v, str) and v.startswith("=")):
                    out[f"{ws.title}!{c.coordinate}"] = v.text if hasattr(v, "text") else v
    return out


class TestFidelidadExcel(unittest.TestCase):
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
        # El inventario de PCB es global (una PCB física solo puede estar en una tarjeta): cada test usa su propia BD.
        type(self).n += 1
        self.path = self.dir / f"fid{self.n}.db"
        db.init_db(self.path)
        self.engine = ExcelSyncEngine(db_path=self.path)

    def _lote(self, nombre, excel):
        return db.create_lote(nombre, 9, 2026, ruta_excel=excel, activo=True, db_path=self.path)["id"]

    def _tarjeta(self, lote_id, num, etapas=(), path=None, **kw):
        t = crear_par(lote_id, num=num, path=path or self.path, **kw)
        for etapa, estado in etapas:
            db.set_prueba(t["id"], etapa, estado, db_path=path or self.path)
        return db.get_tarjeta_by_id(t["id"], db_path=path or self.path)

    # ----------------------------------------------------------------- estructura
    def test_01_la_plantilla_tiene_la_estructura_que_esperamos(self):
        conteo = structure_counts(self.template)
        self.assertEqual(conteo["Producción"]["validaciones_x14"], 2)   # E2:E101 -> 'Catálogo PCB'!F3:F102 y H (Botón R3)
        self.assertGreaterEqual(conteo["Producción"]["validaciones"], 5)
        self.assertEqual(conteo["Producción"]["tablas"], 1)

    def test_02_estructura_identica_tras_sincronizar(self):
        excel = self.engine.create_monthly_excel(9, 2026, target_path=str(self.dir / "estructura.xlsx"))
        lote = self._lote("F-ESTRUCTURA", excel)
        for i, n in enumerate(range(11, 41)):
            self._tarjeta(lote, f"{n:04d}", [("soldadura", "OK"), ("prueba_pcb", "OK" if i % 2 else "FALLA")])

        res = self.engine.export_to_excel(excel, lote, db_path=self.path)
        self.assertGreaterEqual(res["extensiones_reinyectadas"], 1)

        antes, despues = structure_counts(self.template), structure_counts(excel)
        self.assertEqual(_totales(antes), _totales(despues))
        # la validación x14 (desplegable de respaldo) sigue existiendo, ahora inyectada
        self.assertEqual(despues["Producción"]["validaciones_x14"], 2)
        with zipfile.ZipFile(excel) as z:
            xml = z.read("xl/worksheets/sheet1.xml").decode()
        self.assertIn("'Catálogo PCB'!$F$3:$F$102", xml)
        self.assertIn("<xm:sqref>E2:E101</xm:sqref>", xml)

    def test_03_todo_el_xml_esta_bien_formado_y_abre_con_openpyxl(self):
        excel = self.engine.create_monthly_excel(9, 2026, target_path=str(self.dir / "xml.xlsx"))
        self.engine.export_to_excel(excel, self._lote("F-XML", excel), db_path=self.path)
        with zipfile.ZipFile(excel) as z:
            self.assertIsNone(z.testzip())
            for nombre in z.namelist():
                if nombre.endswith((".xml", ".rels")):
                    ET.fromstring(z.read(nombre))
        openpyxl.load_workbook(excel).close()

    def test_04_formulas_identicas_y_son_2211(self):
        excel = self.engine.create_monthly_excel(9, 2026, target_path=str(self.dir / "formulas.xlsx"))
        lote = self._lote("F-FORMULAS", excel)
        for n in range(11, 31):
            self._tarjeta(lote, f"{n:04d}", [("soldadura", "OK")])
        self.engine.export_to_excel(excel, lote, db_path=self.path)

        antes, despues = _formulas(self.template), _formulas(excel)
        self.assertEqual(len(antes), 2211)
        self.assertEqual(len(despues), 2211)
        self.assertEqual([k for k in antes if antes[k] != despues.get(k)], [])
        rep = self.engine.verify_excel_integrity(excel)
        self.assertTrue(rep["is_valid"], rep["summary"])
        self.assertTrue(rep["estructura_ok"])

    def test_05_sincronizaciones_repetidas_no_degradan_el_archivo(self):
        excel = self.engine.create_monthly_excel(9, 2026, target_path=str(self.dir / "repetido.xlsx"))
        lote = self._lote("F-REPETIDO", excel)
        self._tarjeta(lote, "0011", [("soldadura", "OK")])
        for _ in range(5):
            self.engine.export_to_excel(excel, lote, db_path=self.path)
        self.assertEqual(_totales(structure_counts(excel)), _totales(structure_counts(self.template)))
        self.assertEqual(len(_formulas(excel)), 2211)
        self.assertEqual(structure_counts(excel)["Producción"]["validaciones_x14"], 2)  # no se duplicó el extLst

    # ----------------------------------------------------------------- atomicidad y seguridad
    def test_06_si_se_pierde_estructura_no_se_reemplaza_el_original(self):
        excel = self.engine.create_monthly_excel(9, 2026, target_path=str(self.dir / "atomico.xlsx"))
        lote = self._lote("F-ATOMICO", excel)
        self._tarjeta(lote, "0011")
        antes = _sha(excel)

        def sin_reinyectar(origen, generado, destino):  # simula una regresión: se pierde el extLst
            Path(destino).write_bytes(Path(generado).read_bytes())
            return 0

        with mock.patch.object(excel_sync, "_reinyectar_extensiones", sin_reinyectar):
            with self.assertRaises(ExcelIntegrityError):
                self.engine.export_to_excel(excel, lote, db_path=self.path)
        self.assertEqual(_sha(excel), antes)                               # original intacto
        self.assertEqual([p.name for p in self.dir.glob(".atomico*")], [])  # sin temporales huérfanos

    def test_07_archivo_abierto_en_excel_devuelve_error_claro_sin_tocarlo(self):
        excel = self.engine.create_monthly_excel(9, 2026, target_path=str(self.dir / "bloqueado.xlsx"))
        lote = self._lote("F-BLOQUEO", excel)
        self._tarjeta(lote, "0011")
        antes = _sha(excel)
        with mock.patch.object(excel_sync.os, "replace", side_effect=PermissionError("en uso")):
            with self.assertRaises(ExcelBloqueadoError):
                self.engine.export_to_excel(excel, lote, db_path=self.path)
        self.assertEqual(_sha(excel), antes)
        self.assertEqual([p.name for p in self.dir.glob(".bloqueado*")], [])

    def test_08_deja_respaldo_bak_del_contenido_anterior(self):
        excel = self.engine.create_monthly_excel(9, 2026, target_path=str(self.dir / "respaldo.xlsx"))
        lote = self._lote("F-BAK", excel)
        self._tarjeta(lote, "0011")
        antes = _sha(excel)
        res = self.engine.export_to_excel(excel, lote, db_path=self.path)
        self.assertEqual(_sha(res["respaldo"]), antes)

    def test_09_crear_mensual_nunca_sobrescribe_datos_existentes(self):
        destino = str(self.dir / "mensual.xlsx")
        self.engine.create_monthly_excel(10, 2026, target_path=destino)
        lote = self._lote("F-MENSUAL", destino)
        self._tarjeta(lote, "0011", [("soldadura", "OK")])
        self.engine.export_to_excel(destino, lote, db_path=self.path)
        con_datos = _sha(destino)
        self.assertEqual(self.engine.create_monthly_excel(10, 2026, target_path=destino), str(Path(destino).resolve()))
        self.assertEqual(_sha(destino), con_datos)  # reutilizado, no reemplazado por la plantilla vacía

    def test_10_nombre_estandar_del_mensual(self):
        p = self.engine.monthly_path(10, 2026)
        self.assertEqual(p.name, "Control_Produccion_TQT_Octubre_2026.xlsx")
        self.assertEqual(p.parent, Path(_aislamiento.TMP) / "excel_mensual")

    # ----------------------------------------------------------------- datos
    def test_11_tarjeta_fuera_de_la_lista_reutiliza_un_renglon_libre_y_avisa(self):
        excel = self.engine.create_monthly_excel(9, 2026, target_path=str(self.dir / "capacidad.xlsx"))
        lote = self._lote("F-CAPACIDAD", excel)
        self._tarjeta(lote, "0011")
        self._tarjeta(lote, "0500")  # la plantilla solo trae renglones para los IDs prefijados (0011..0130)
        res = self.engine.export_to_excel(excel, lote, db_path=self.path)
        self.assertEqual((res["exported_tarjetas"], res["omitidas"]), (2, []))
        self.assertTrue(any("0500" in a and "fila" in a for a in res["avisos"]), res["avisos"])
        prod = openpyxl.load_workbook(excel)["Producción"]
        self.assertIn("0500", [prod.cell(r, 1).value for r in range(2, 102)])
        self.assertEqual(len(_formulas(excel)), 2211)     # reutilizar un renglón no toca ninguna fórmula

    def test_11b_sin_renglones_libres_se_reporta_en_omitidas(self):
        excel = self.engine.create_monthly_excel(9, 2026, target_path=str(self.dir / "lleno.xlsx"))
        lote = self._lote("F-LLENO", excel)
        prod = openpyxl.load_workbook(excel)["Producción"]
        for n in [prod.cell(r, 1).value for r in range(2, 102)]:   # las 100 tarjetas de la plantilla ocupan todos los renglones
            self._tarjeta(lote, n)
        self._tarjeta(lote, "0999")                                # la 101.ª ya no cabe
        res = self.engine.export_to_excel(excel, lote, db_path=self.path)
        self.assertEqual(res["exported_tarjetas"], 100)
        self.assertEqual(res["omitidas"], ["0999"])

    def test_11c_tarjeta_impar_y_otra_version_escriben_el_nombre_real_de_la_r1(self):
        """Producción!B es una fórmula TQT-R1-V30-<ID>: si la R1 real es otra (versión V31 o número distinto), se escribe
        el nombre como valor SOLO en esa fila y se avisa; las demás filas conservan su fórmula."""
        excel = self.engine.create_monthly_excel(9, 2026, target_path=str(self.dir / "impares.xlsx"))
        lote = self._lote("F-IMPARES", excel)
        ids = {t: inv.registrar_manual(t, v, s, db_path=self.path)["pcbs"][0]["id"] for t, v, s in (("R1", "31", "0012"), ("R2", "30", "0012"))}
        inv.confirmar_recepcion(list(ids.values()), db_path=self.path)
        inv.crear_tarjeta(lote, "0012", ids["R1"], ids["R2"], db_path=self.path)      # 0012 con R1 en versión 31
        self._tarjeta(lote, "0013")                                                    # normal
        r1 = inv.registrar_manual("R1", "30", "0014", db_path=self.path)["pcbs"][0]["id"]
        r2 = inv.registrar_manual("R2", "30", "0010", db_path=self.path)["pcbs"][0]["id"]
        inv.confirmar_recepcion([r1, r2], db_path=self.path)
        inv.crear_tarjeta(lote, "0014", r1, r2, db_path=self.path)                     # impar: R1 0014 con R2 0010
        inv.set_mac(r1, mac_unica(), db_path=self.path)
        inv.set_mac(r2, mac_unica(), db_path=self.path)

        res = self.engine.export_to_excel(excel, lote, db_path=self.path)
        self.assertEqual(len([a for a in res["avisos"] if "Producción!B" in a]), 1, res["avisos"])
        self.assertIn("TQT-R1-V31-0012", " ".join(res["avisos"]))
        prod = openpyxl.load_workbook(excel)["Producción"]
        fila = {prod.cell(r, 1).value: r for r in range(2, 102)}
        self.assertEqual(prod.cell(fila["0012"], 2).value, "TQT-R1-V31-0012")           # valor literal
        self.assertTrue(str(prod.cell(fila["0013"], 2).value).startswith("="))            # fórmula intacta
        self.assertTrue(str(prod.cell(fila["0014"], 2).value).startswith("="))
        self.assertEqual(prod.cell(fila["0014"], 5).value, "TQT-R2-V30-0010")            # el R2 impar va en E (es entrada)
        self.assertEqual(len(_formulas(excel)), 2210)                                     # solo B de la 0012 dejó de ser fórmula
        inv.editar_pcb(ids["R1"], version="30", db_path=self.path)                        # si vuelve a coincidir, se restaura
        res2 = self.engine.export_to_excel(excel, lote, db_path=self.path)
        self.assertEqual([a for a in res2["avisos"] if "Producción!B" in a], [])
        self.assertTrue(str(openpyxl.load_workbook(excel)["Producción"].cell(fila["0012"], 2).value).startswith("="))
        self.assertEqual(len(_formulas(excel)), 2211)

    def test_11d_r3_se_guarda_en_la_bd_y_se_exporta_a_produccion_h_y_catalogo(self):
        excel = self.engine.create_monthly_excel(9, 2026, target_path=str(self.dir / "r3.xlsx"))
        lote = self._lote("F-R3", excel)
        self._tarjeta(lote, "0011", r3=True)
        res = self.engine.export_to_excel(excel, lote, db_path=self.path)
        self.assertFalse(any("R3" in a for a in res["avisos"]), res["avisos"])    # la plantilla nueva sí trae Botón R3
        wb = openpyxl.load_workbook(excel)
        prod, cat = wb["Producción"], wb["Catálogo PCB"]
        fila = next(r for r in range(2, 102) if str(prod.cell(r, 1).value).strip() == "0011")
        self.assertEqual(prod.cell(fila, 8).value, "TQT-R3-V30-0011")             # Producción!H = Botón R3
        filas_k = [r for r in range(3, 103) if cat.cell(r, 11).value == "TQT-R3-V30-0011"]
        self.assertEqual(len(filas_k), 1)                                          # Catálogo!K contiene la R3
        self.assertTrue(cat.cell(filas_k[0], 12).value)                            # y su Estado PCB (L)
        self.assertEqual(len(_formulas(excel)), 2211)

    def test_12_round_trip_export_import_conserva_macs_y_estados(self):
        db1 = self.dir / "rt1.db"
        db2 = self.dir / "rt2.db"
        db.init_db(db1)
        db.init_db(db2)
        motor1, motor2 = ExcelSyncEngine(db_path=db1), ExcelSyncEngine(db_path=db2)
        excel = motor1.create_monthly_excel(9, 2026, target_path=str(self.dir / "roundtrip.xlsx"))
        lote1 = db.create_lote("RT", 9, 2026, ruta_excel=excel, db_path=db1)["id"]

        esperado = {}
        plan = {"0011": [("soldadura", "OK"), ("programacion", "OK"), ("prueba_pcb", "OK"), ("integracion", "OK"), ("prueba_final", "OK")],
                "0012": [("soldadura", "FALLA")],
                "0013": [("soldadura", "OK"), ("programacion", "RETRABAJO")],
                "0014": [("prueba_final", "NO APLICA")],
                "0015": []}
        for num, etapas in plan.items():
            t = self._tarjeta(lote1, num, etapas, path=db1)
            esperado[num] = (t["mac_r1"], t["mac_r2"])
        motor1.export_to_excel(excel, lote1, db_path=db1)

        lote2 = db.create_lote("RT2", 9, 2026, db_path=db2)["id"]
        res = motor2.import_from_excel(excel, lote2, db_path=db2)
        self.assertEqual(res["status"], "success", res["errores"])
        self.assertEqual(res["imported_tarjetas"], 5)

        origen = {t["id_tarjeta_num"]: t for t in db.list_tarjetas(lote_id=lote1, limit=50, db_path=db1)[0]}
        copia = {t["id_tarjeta_num"]: t for t in db.list_tarjetas(lote_id=lote2, limit=50, db_path=db2)[0]}
        self.assertEqual(set(copia), set(plan))
        self.assertTrue(all(t["completa"] and t["r1"]["estado_ciclo"] == "ASIGNADA" for t in copia.values()))
        for num in plan:
            for campo in ("mac_r1", "mac_r2", "soldadura", "programacion", "prueba_pcb", "integracion", "prueba_final", "estado_general",
                          "estado_pcb_r1", "estado_pcb_r2"):
                self.assertEqual(copia[num][campo], origen[num][campo], f"{num}.{campo}")

    def test_13_importar_plantilla_vacia_no_crea_pcb_ni_tarjetas_fantasma(self):
        dbv = self.dir / "vacia.db"
        db.init_db(dbv)
        lote = db.create_lote("VACIA", 9, 2026, db_path=dbv)["id"]
        res = ExcelSyncEngine(db_path=dbv).import_from_excel(self.template, lote, db_path=dbv)
        self.assertEqual((res["imported_tarjetas"], res["imported_pcbs"]), (0, 0))    # nombres sin MAC = renglones de plantilla
        self.assertEqual(db.list_tarjetas(lote_id=lote, db_path=dbv)[1], 0)
        self.assertEqual(inv.listar_pcb(db_path=dbv)["total"], 0)                    # no inunda el inventario con PCB inexistentes
        ExcelSyncEngine(db_path=dbv).import_from_excel(self.template, lote, db_path=dbv)  # idempotente

    def test_14_estado_pcb_y_general_reflejados_en_el_excel(self):
        excel = self.engine.create_monthly_excel(9, 2026, target_path=str(self.dir / "estados.xlsx"))
        lote = self._lote("F-ESTADOS", excel)
        self._tarjeta(lote, "0011", [("prueba_pcb", "OK")])
        self._tarjeta(lote, "0012", [("prueba_pcb", "FALLA")])
        self._tarjeta(lote, "0013")
        self.engine.export_to_excel(excel, lote, db_path=self.path)
        cat = openpyxl.load_workbook(excel)["Catálogo PCB"]
        self.assertEqual([cat[f"C{r}"].value for r in (3, 4)], ["FUNCIONAL", "NO FUNCIONAL"])
        self.assertEqual(cat["H4"].value, "NO FUNCIONAL")
        self.assertIn(cat["C5"].value, ("SIN PROBAR", None))


if __name__ == "__main__":
    unittest.main()
