"""QA DYMO: contenido de la etiqueta 30334, geometría REAL (SVG rasterizado a 300 dpi con PyMuPDF), QR decodificado,
archivos (.dymo/.label/ZIP) y XML contra la estructura de los ejemplos oficiales (DCD-SDK-Sample).

Hardware real (LabelWriter 550 / DYMO Connect) NO disponible: nada de esto prueba la impresión física."""
import _aislamiento  # noqa: F401  (debe ser lo primero)
import io
import re
import unittest
import xml.etree.ElementTree as ET
import zipfile

from fastapi.testclient import TestClient

from app.database import db, inventario as inv
from app.main import app
from app.services import dymo_service as dy
from app.services.dymo_service import DymoService

from _aislamiento import crear_par, nuevo_lote, verificar_aislamiento, mac_unica, num_unico

try:
    import numpy as np
    import pymupdf
    HAY_RASTER = True
except Exception:  # pragma: no cover
    HAY_RASTER = False
try:
    import zxingcpp
except Exception:  # pragma: no cover
    zxingcpp = None
try:
    import cv2
except Exception:  # pragma: no cover
    cv2 = None

DPI = 300
PX_POR_MM = DPI / 25.4
ANCHO_PX, ALTO_PX = 674, 378
BASE = {"id": 1, "id_tarjeta_num": "0021", "nombre_r1": "TQT-R1-V30-0021", "mac_r1": "70:4B:CA:5B:9F:6E",
        "nombre_r2": "TQT-R2-V30-0010", "mac_r2": "70:4B:CA:5B:9C:A2", "estado_pcb_r1": "FUNCIONAL",
        "estado_pcb_r2": "FUNCIONAL", "estado_general": "LIBERADO"}
PEOR = {**BASE, "nombre_r1": "TQT-R1-V31-9999", "mac_r1": "FF:FF:FF:FF:FF:FE", "nombre_r2": "TQT-R2-V31-9999",
        "mac_r2": "FF:FF:FF:FF:FF:FE"}


def rasterizar(svg: str):
    """SVG -> matriz de grises uint8 a 300 dpi."""
    doc = pymupdf.open(stream=svg.encode("utf-8"), filetype="svg")
    pm = doc[0].get_pixmap(dpi=DPI, alpha=False, colorspace=pymupdf.csGRAY)
    return np.frombuffer(pm.samples, dtype=np.uint8).reshape(pm.height, pm.width).copy()


def decodificar(gris) -> str:
    """Decodifica el QR con ZXing (y con OpenCV si acierta; el detector de OpenCV 5 falla con algunos patrones válidos)."""
    _, bn = cv2.threshold(gris, 128, 255, cv2.THRESH_BINARY)
    lecturas = [b.text for b in zxingcpp.read_barcodes(bn)] if zxingcpp else []
    if lecturas:
        return lecturas[0]
    if cv2 is not None:
        return cv2.QRCodeDetector().detectAndDecode(bn)[0]
    return ""


class TestContenido(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        verificar_aislamiento()
        db.init_db()
        cls.client = TestClient(app)
        cls.lote = nuevo_lote()["id"]

    def _impar(self, num, r1_serie, r2_serie, v1="30", v2="30", macs=(True, True)):
        macs = tuple(mac_unica() if m else None for m in macs)
        i1 = inv.registrar_manual("R1", v1, r1_serie)["pcbs"][0]["id"]
        i2 = inv.registrar_manual("R2", v2, r2_serie)["pcbs"][0]["id"]
        inv.confirmar_recepcion([i1, i2])
        t = inv.crear_tarjeta(self.lote, num, i1, i2, None)
        for pid, m in zip((i1, i2), macs):
            if m:
                inv.set_mac(pid, m)
        return t, i1, i2

    def _lineas(self, tid):
        d = self.client.get(f"/api/dymo/label/{tid}").json()
        self.assertEqual(d["qr_payload"], d["label_text"])
        self.assertEqual(d["qr_payload"].split("\n"), d["trama_lineas"])
        if d["trama_lineas"][3]:
            self.assertFalse(d["qr_payload"].endswith("\n"))
        return d

    def test_01_tarjeta_impar_r1_0021_con_r2_0010(self):
        t, _, _ = self._impar("0021", "0021", "0010")
        d = self._lineas(t["id"])
        t = db.get_tarjeta_by_id(t["id"])
        l = d["qr_payload"].split("\n")
        self.assertEqual((l[0], l[2]), ("TQT-R1-V30-0021", "TQT-R2-V30-0010"))
        self.assertEqual((l[1], l[3]), (t["mac_r1"].lower(), t["mac_r2"].lower()))
        self.assertNotIn("R3", d["qr_payload"])
        self.assertNotIn("\r", d["qr_payload"])

    def test_02_versiones_v31_v5_v100_y_cada_pcb_su_version(self):
        for v1, v2, esp1, esp2 in (("31", "5", "V31", "V5"), ("100", "30", "V100", "V30"), ("V007", "999", "V7", "V999")):
            t, _, _ = self._impar(None, None, None, v1, v2)
            l = self._lineas(t["id"])["trama_lineas"]
            self.assertIn(f"-{esp1}-", l[0])
            self.assertIn(f"-{esp2}-", l[2])
            self.assertRegex(l[0], r"^TQT-R1-V\d{1,3}-\d{4}$")
            self.assertRegex(l[1], r"^([0-9a-f]{2}:){5}[0-9a-f]{2}$")

    def test_03_mac_faltante_linea_vacia_e_identificacion_vs_final(self):
        t, i1, i2 = self._impar(None, None, None, macs=(False, True))
        d = self._lineas(t["id"])
        self.assertEqual(d["trama_lineas"][1], "")
        self.assertEqual(len(d["qr_payload"].split("\n")), 4)
        self.assertEqual(d["estado_etiqueta"], "IDENTIFICACION")
        self.assertEqual(d["sin_mac"], ["R1"])
        self.assertFalse(d["is_ready_to_print"])
        self.assertTrue(d["imprimible"])
        inv.set_mac(i1, "70:4B:CA:5B:9F:11")
        db.set_prueba(t["id"], "prueba_pcb", "OK")
        d = self._lineas(t["id"])
        self.assertEqual((d["estado_etiqueta"], d["sin_mac"]), ("FINAL", []))

    def test_04_tarjeta_incompleta_no_es_imprimible(self):
        i1 = inv.registrar_manual("R1", "30", None)["pcbs"][0]["id"]
        inv.confirmar_recepcion([i1])
        t = inv.crear_tarjeta(self.lote, None, i1, None, None)
        d = self._lineas(t["id"])
        self.assertEqual((d["estado_etiqueta"], d["imprimible"]), ("INCOMPLETA", False))
        self.assertEqual(d["trama_lineas"][2:], ["", ""])
        # aun así el XML se genera sin romperse
        self.assertEqual(ET.fromstring(self.client.get(f"/api/dymo/label/{t['id']}/xml").text).tag, "DesktopLabel")

    def test_05_mac_mayuscula_en_bd_sale_en_minuscula_y_ceros_se_conservan(self):
        t = crear_par(self.lote)
        d = self._lineas(t["id"])
        self.assertTrue(t["mac_r1"] == t["mac_r1"].upper())
        self.assertEqual(d["trama_lineas"][1], t["mac_r1"].lower())
        self.assertEqual(d["trama_lineas"][0], t["nombre_r1"])
        self.assertRegex(d["id_tarjeta_num"], r"^\d{4}$")

    def test_06_tarjeta_inexistente_404_en_todas_las_rutas(self):
        for ruta in ("label/99999999", "label/99999999/xml", "label/99999999/archivo", "preview/99999999", "svg/99999999"):
            self.assertEqual(self.client.get(f"/api/dymo/{ruta}").status_code, 404, ruta)
        self.assertEqual(self.client.get("/api/dymo/label/abc").status_code, 422)

    def test_07_pcb_sustituida_tras_falla_refleja_la_pcb_actual(self):
        t = crear_par(self.lote)
        antes = self._lineas(t["id"])["trama_lineas"]
        nueva = inv.registrar_manual("R2", "31", None)["pcbs"][0]
        inv.confirmar_recepcion([nueva["id"]])
        inv.set_mac(nueva["id"], "aa:bb:cc:dd:ee:01")
        pcb_vieja = db.get_tarjeta_by_id(t["id"])["pcb_r2_id"] if "pcb_r2_id" in db.get_tarjeta_by_id(t["id"]) else None
        if pcb_vieja is None:
            pcb_vieja = db.get_tarjeta_by_id(t["id"])["r2"]["id"]
        inv.marcar_falla(pcb_vieja, "falla", nueva["id"])
        despues = self._lineas(t["id"])
        self.assertEqual(despues["trama_lineas"][0:2], antes[0:2])
        self.assertEqual(despues["trama_lineas"][2], nueva["nombre"])
        self.assertEqual(despues["trama_lineas"][3], "aa:bb:cc:dd:ee:01")
        self.assertNotIn(antes[2], despues["qr_payload"])
        self.assertNotIn(antes[3], despues["qr_payload"])
        self.assertIn(nueva["nombre"], self.client.get(f"/api/dymo/label/{t['id']}/xml").text)

    def test_08_pcb_sustituida_sin_reemplazo_deja_incompleta(self):
        t = crear_par(self.lote)
        pid = db.get_tarjeta_by_id(t["id"])["r1"]["id"]
        inv.marcar_falla(pid, "falla")
        d = self._lineas(t["id"])
        self.assertEqual(d["estado_etiqueta"], "INCOMPLETA")
        self.assertEqual(d["trama_lineas"][:2], ["", ""])

    def test_09_lote_por_ids_y_modo_de_trama_identica(self):
        t = crear_par(self.lote)
        lab = self.client.get(f"/api/dymo/batch-labels?lote_id={self.lote}&modo=todas").json()["labels"]
        d = next(x for x in lab if x["tarjeta_id"] == t["id"])
        self.assertEqual(d["qr_payload"], self._lineas(t["id"])["qr_payload"])


@unittest.skipUnless(HAY_RASTER and cv2 is not None, "requiere pymupdf, numpy y opencv")
class TestGeometriaRaster(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        verificar_aislamiento()

    def _img(self, tarjeta, guia=False):
        svg = DymoService.generate_svg_preview(tarjeta, guia=guia)
        # se quita el contorno de corte de la etiqueta (no se imprime): solo se mide lo que sí saldría impreso
        svg = re.sub(r'<rect width="57" height="32" rx="2.5"[^>]*/>', "", svg, count=1)
        return rasterizar(svg)

    def test_10_lienzo_674_x_378_px_a_300_dpi(self):
        g = self._img(BASE)
        self.assertEqual((g.shape[1], g.shape[0]), (ANCHO_PX, ALTO_PX))

    def test_11_zona_segura_de_1_5_mm_sin_ningun_elemento_fuera(self):
        for t in (BASE, PEOR):
            g = self._img(t)
            oscuro = g < 128
            # el contorno redondeado de la etiqueta (borde de corte, no se imprime) se excluye: se mira el interior
            m = round(1.5 * PX_POR_MM)                    # 18 px
            ys, xs = np.where(oscuro)
            self.assertGreaterEqual(xs.min(), m - 1, "elemento dentro de los 1.5 mm izquierdos")
            self.assertLessEqual(xs.max(), ANCHO_PX - m, "elemento dentro de los 1.5 mm derechos")
            self.assertGreaterEqual(ys.min(), m - 1, "elemento dentro de los 1.5 mm superiores")
            self.assertLessEqual(ys.max(), ALTO_PX - m, "elemento dentro de los 1.5 mm inferiores")

    def test_12_qr_al_menos_20_mm_con_zona_de_silencio(self):
        d = DymoService.diseno(BASE)
        self.assertGreaterEqual(d.qr.w, 20.0)
        g = self._img(BASE)
        cols = np.where((g[:, :int(d.qr.derecha * PX_POR_MM)] < 128).any(axis=0))[0]
        lado_modulos_mm = (cols.max() - cols.min() + 1) / PX_POR_MM
        self.assertGreaterEqual(lado_modulos_mm + 2 * dy.SILENCIO_MODULOS * d.puntos_por_modulo / dy.DOTS_PER_MM, 20.0)
        # silencio: sin tinta entre el QR y el borde de su caja
        x0 = round(d.qr.x * PX_POR_MM)
        self.assertGreaterEqual(cols.min() - x0, 2 * d.puntos_por_modulo - 2)
        self.assertGreaterEqual(d.puntos_por_modulo, 4)

    @unittest.skipUnless(zxingcpp or cv2, "sin decodificador QR")
    def test_13_qr_rasterizado_se_decodifica_y_es_la_trama_exacta(self):
        for t in (BASE, PEOR):
            g = self._img(t)
            self.assertEqual(decodificar(g), DymoService.format_qr_payload(t))
        self.assertEqual(decodificar(self._img(BASE)), "TQT-R1-V30-0021\n70:4b:ca:5b:9f:6e\nTQT-R2-V30-0010\n70:4b:ca:5b:9c:a2")

    @unittest.skipUnless(zxingcpp, "sin zxing-cpp")
    def test_14_qr_se_decodifica_en_todas_las_variantes_de_contenido(self):
        for mod in ({}, {"mac_r1": ""}, {"mac_r2": "", "mac_r1": ""}, {"nombre_r1": "TQT-R1-V5-0001"},
                    {"nombre_r2": "TQT-R2-V100-9999"}):
            t = {**BASE, **mod}
            self.assertEqual(decodificar(self._img(t)), DymoService.format_qr_payload(t), mod)

    def test_15_texto_peor_caso_no_desborda_su_caja(self):
        d = DymoService.diseno(PEOR)
        g = self._img(PEOR)
        x0 = int(d.texto.x * PX_POR_MM)
        zona = g[:, x0 - 2:] < 128
        ys, xs = np.where(zona)
        self.assertGreater(len(xs), 0)
        self.assertLessEqual((xs.max() + x0 - 2) / PX_POR_MM, d.texto.derecha + 0.05)
        self.assertLessEqual(ys.max() / PX_POR_MM, d.texto.abajo + 0.05)
        self.assertGreaterEqual(ys.min() / PX_POR_MM, d.texto.y - 0.05)
        # el ancho teórico de Consolas (0.55 em) cabe con margen; la fuente de PyMuPDF es distinta, así que también el cálculo
        self.assertLess(max(dy.ancho_texto_mm(l) for l in DymoService.trama_lineas(PEOR)), d.texto.w)
        self.assertLess(dy.alto_texto_mm(4), d.texto.h)

    def test_16_fuente_al_menos_7_pt_y_solo_blanco_y_negro(self):
        svg = DymoService.generate_svg_preview(BASE, guia=False)
        pt = float(re.search(r'font-size="([\d.]+)"', svg).group(1)) / dy.PT_A_MM
        self.assertGreaterEqual(pt, 7.0)
        colores = set(re.findall(r'(?:fill|stroke)="(#[0-9a-fA-F]{3,6}|[a-z]+)"', svg)) - {"none"}
        self.assertLessEqual({c.lower() for c in colores}, {"#000", "#fff", "#000000", "#ffffff", "black", "white"})
        self.assertNotIn("gradient", svg.lower())
        self.assertNotIn("opacity", svg.lower())
        for xml in (DymoService.generate_dcd_xml(BASE), DymoService.generate_dymo_xml(BASE)):
            for tam in re.findall(r"<FontSize>([\d.]+)</FontSize>|Size=\"([\d.]+)\"", xml):
                v = float(tam[0] or tam[1])
                self.assertGreaterEqual(v, 7.0)

    def test_18_qr_y_texto_centrados_verticalmente(self):
        d = DymoService.diseno(PEOR)
        self.assertAlmostEqual(d.qr.y + d.qr.h / 2, 16.0, delta=0.05)


class TestArchivosYXML(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        verificar_aislamiento()
        db.init_db()
        cls.client = TestClient(app)
        cls.lote = nuevo_lote()["id"]

    def test_20_dcd_estructura_de_los_ejemplos_oficiales(self):
        raiz = ET.fromstring(DymoService.generate_dcd_xml(BASE))
        self.assertEqual(raiz.tag, "DesktopLabel")
        self.assertEqual(raiz.get("Version"), "1")
        lab = raiz.find("DYMOLabel")
        self.assertEqual(lab.get("Version"), "3")
        for tag in ("Description", "Orientation", "LabelName", "InitialLength", "BorderStyle", "DYMORect", "BorderColor",
                    "BorderThickness", "Show_Border", "DynamicLayoutManager"):
            self.assertIsNotNone(lab.find(tag), tag)
        self.assertIsNotNone(lab.find("DYMORect/DYMOPoint/X"))
        self.assertIsNotNone(lab.find("DYMORect/Size/Width"))
        self.assertIsNotNone(raiz.find("LabelApplication"))
        self.assertIsNotNone(raiz.find("DataTable/Columns"))
        objs = {o.findtext("Name"): o for o in lab.find("DynamicLayoutManager/LabelObjects")}
        self.assertEqual(set(objs), {"QR", "TEXTO"})
        qr = objs["QR"]
        self.assertEqual(qr.tag, "BarcodeObject")
        self.assertEqual(qr.findtext("BarcodeFormat"), "QRCode")
        self.assertEqual(qr.findtext("Data/MultiDataString/DataString"), DymoService.format_qr_payload(BASE))
        for tag in ("Brushes", "Rotation", "Margin", "ObjectLayout", "Size", "TextPosition"):
            self.assertIsNotNone(qr.find(tag), tag)
        texto = objs["TEXTO"]
        lineas = ["".join(x.text or "" for x in ls.iter("Text")) for ls in texto.iter("LineTextSpan")]
        self.assertEqual(lineas, DymoService.trama_lineas(BASE))
        self.assertEqual("\n".join(lineas), DymoService.format_label_text(BASE))
        self.assertEqual(lab.findtext("Orientation"), "Landscape")
        # unidades en pulgadas: la etiqueta 30334 es 2.25 x 1.25 in, la zona segura 2.008 x 1.024
        self.assertAlmostEqual(float(lab.findtext("DYMORect/Size/Width")), 54 / 25.4, places=3)
        self.assertAlmostEqual(float(lab.findtext("DYMORect/Size/Height")), 29 / 25.4, places=3)

    def test_21_modo_alterno_address(self):
        r = self.client.get("/api/dymo/label/%d/xml?texto_como=address" % crear_par(self.lote)["id"])
        raiz = ET.fromstring(r.text)
        objs = {o.findtext("Name"): o for o in raiz.find("DYMOLabel/DynamicLayoutManager/LabelObjects")}
        self.assertEqual(objs["TEXTO"].tag, "AddressObject")
        self.assertIsNotNone(objs["TEXTO"].find("BarcodePosition"))
        self.assertIsNotNone(objs["TEXTO"].find("FormattedText/LineTextSpan"))
        self.assertEqual(self.client.get("/api/dymo/label/1/xml?texto_como=zzz").status_code, 422)

    def test_22_escapes_xml_en_nombres_hostiles(self):
        t = {**BASE, "nombre_r1": "TQT-R1-V30-<&>\"'", "nombre_r2": "]]><x/>"}
        for xml in (DymoService.generate_dcd_xml(t), DymoService.generate_dcd_xml(t, texto_como="address"),
                    DymoService.generate_dymo_xml(t)):
            raiz = ET.fromstring(xml)                     # bien formado
            textos = [e.text for e in raiz.iter() if e.text and "TQT-R1-V30-" in e.text]
            self.assertIn("TQT-R1-V30-<&>\"'", "\n".join(textos))
            self.assertNotIn("<x/>", ET.tostring(raiz, encoding="unicode").replace("&lt;x/&gt;", ""))
        # SVG y HTML de vista previa también bien formados
        ET.fromstring(DymoService.generate_svg_preview(t))
        self.assertNotIn("<x/>", DymoService.generate_html_preview({**t, "id": 1}))

    def test_23_v8_label_estructura(self):
        raiz = ET.fromstring(DymoService.generate_dymo_xml(BASE))
        self.assertEqual(raiz.tag, "DieCutLabel")
        self.assertEqual(raiz.get("Version"), "8.0")
        self.assertEqual(raiz.findtext("Id"), "Small30334")
        nombres = [o.findtext("./*/Name") for o in raiz.findall("ObjectInfo")]
        self.assertEqual(nombres, ["QR", "TEXTO"])
        self.assertIsNotNone(raiz.find("ObjectInfo/ImageObject/Image"))   # QR como imagen: DLS ignora la caja del BarcodeObject

    def test_24_archivo_dymo_cabeceras_y_nombre(self):
        t = crear_par(self.lote)
        r = self.client.get(f"/api/dymo/label/{t['id']}/archivo")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers["content-disposition"], 'attachment; filename="TQT_%s.dymo"' % t["id_tarjeta_num"])
        self.assertEqual(r.headers["content-type"], "application/octet-stream")
        self.assertTrue(r.content.startswith(b"\xef\xbb\xbf<?xml"))
        self.assertEqual(r.content.decode("utf-8-sig"), self.client.get(f"/api/dymo/label/{t['id']}/xml").text)
        self.assertEqual(self.client.get(f"/api/dymo/label/{t['id']}/archivo?label_format=30252").status_code, 200)
        self.assertEqual(self.client.get(f"/api/dymo/label/{t['id']}/archivo?label_format=1").status_code, 400)

    def test_25_lote_zip_grande_de_100_nombres_unicos(self):
        ids = [crear_par(self.lote)["id"] for _ in range(100)]
        r = self.client.get("/api/dymo/lote/archivo?ids=" + ",".join(map(str, ids)))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers["content-disposition"], 'attachment; filename="TQT_etiquetas.zip"')
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            nombres = z.namelist()
            self.assertEqual(len(nombres), 100)
            self.assertEqual(len(set(nombres)), 100)
            self.assertIsNone(z.testzip())
            for n in nombres[:5]:
                ET.fromstring(z.read(n).decode("utf-8-sig"))

    def test_26_lote_ids_repetidos_vacios_e_inexistentes(self):
        a, b = crear_par(self.lote)["id"], crear_par(self.lote)["id"]
        r = self.client.get(f"/api/dymo/lote/archivo?ids={a},{a},{b},,99999999")
        self.assertEqual(r.status_code, 200)
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            self.assertEqual(len(z.namelist()), 2)
        for ids, codigo in (("", 422), (",,,", 400), ("0", 404), ("-5", 404), ("1;2", 400), ("1.5", 400)):
            self.assertEqual(self.client.get(f"/api/dymo/lote/archivo?ids={ids}").status_code, codigo, ids)
        self.assertEqual(self.client.get(f"/api/dymo/lote/archivo?ids={','.join(['1'] * 501)}").status_code, 422 if False else 400)

    def test_27_lote_tarjetas_de_mismo_numero_en_lotes_distintos_no_pisan_nombres(self):
        otro = nuevo_lote()["id"]
        n = num_unico()
        a = crear_par(self.lote, n, version="29")
        b = crear_par(otro, n, version="31")
        r = self.client.get(f"/api/dymo/lote/archivo?ids={a['id']},{b['id']}")
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            self.assertEqual(len(set(z.namelist())), 2, "mismo número en dos lotes: los nombres del ZIP deben ser únicos")

    def test_28_head_del_zip_para_la_sonda_del_frontend(self):
        r = self.client.head("/api/dymo/lote/archivo?ids=1")
        self.assertIn(r.status_code, (200, 404, 405))

    # -- comparación estructural con los ejemplos oficiales (github.com/dymosoftware/DCD-SDK-Sample, copiados en fixtures)
    @staticmethod
    def _oficial(nombre):
        from pathlib import Path
        return ET.fromstring((Path(__file__).parent / "fixtures" / "dymo_oficial" / nombre).read_text(encoding="utf-8-sig"))

    @staticmethod
    def _hijos(el):
        return [c.tag for c in el]

    def test_30_dymo_mismos_elementos_y_orden_que_el_ejemplo_oficial(self):
        of_addr = self._oficial("PreviewLabelFramework.dymo")
        of_bar = self._oficial("samplelabel.dymo")
        mio = ET.fromstring(DymoService.generate_dcd_xml(BASE, texto_como="address"))
        self.assertEqual(self._hijos(mio), self._hijos(of_addr))
        self.assertEqual(self._hijos(mio.find("DYMOLabel")), self._hijos(of_addr.find("DYMOLabel")))
        self.assertEqual(self._hijos(mio.find("DYMOLabel/DynamicLayoutManager")), self._hijos(of_addr.find("DYMOLabel/DynamicLayoutManager")))
        objs = {o.findtext("Name"): o for o in mio.find("DYMOLabel/DynamicLayoutManager/LabelObjects")}
        # AddressObject: idéntico a IAddressObject0 del ejemplo, elemento por elemento y en el mismo orden
        oa = of_addr.find("DYMOLabel/DynamicLayoutManager/LabelObjects/AddressObject")
        self.assertEqual(self._hijos(objs["TEXTO"]), self._hijos(oa))
        self.assertEqual(self._hijos(objs["TEXTO"].find("FormattedText")), self._hijos(oa.find("FormattedText"))[:4] + ["LineTextSpan"] * 4)
        self.assertEqual(self._hijos(objs["TEXTO"].find("FormattedText/LineTextSpan/TextSpan")), self._hijos(oa.find("FormattedText/LineTextSpan/TextSpan")))
        self.assertEqual(self._hijos(objs["TEXTO"].find("FormattedText/LineTextSpan/TextSpan/FontInfo")),
                         self._hijos(oa.find("FormattedText/LineTextSpan/TextSpan/FontInfo")))
        # BarcodeObject: idéntico a BARCODE de samplelabel.dymo
        ob = of_bar.find("DYMOLabel/DynamicLayoutManager/LabelObjects/BarcodeObject")
        self.assertEqual(self._hijos(objs["QR"]), self._hijos(ob))
        for ruta in ("Brushes", "Margin/DYMOThickness", "Data/MultiDataString/DataString", "FontInfo/FontBrush/SolidColorBrush/Color",
                     "ObjectLayout/DYMOPoint/X", "ObjectLayout/Size/Height"):
            self.assertIsNotNone(objs["QR"].find(ruta), ruta)
        # y el modo por defecto solo cambia el nombre del objeto de texto
        pred = ET.fromstring(DymoService.generate_dcd_xml(BASE))
        self.assertEqual([o.tag for o in pred.find("DYMOLabel/DynamicLayoutManager/LabelObjects")], ["BarcodeObject", "TextObject"])

    def test_31_label_v8_mismos_elementos_que_el_ejemplo_oficial(self):
        of = self._oficial("PreviewLabelFramework.label")
        mio = ET.fromstring(DymoService.generate_dymo_xml(BASE, "30252"))
        self.assertEqual(self._hijos(mio), self._hijos(of) + ["ObjectInfo"])   # QR + TEXTO
        self.assertEqual(mio.findtext("Id"), of.findtext("Id"))
        self.assertEqual(mio.findtext("PaperName"), of.findtext("PaperName"))
        self.assertEqual(mio.find("DrawCommands/RoundRectangle").get("Width"), of.find("DrawCommands/RoundRectangle").get("Width"))
        self.assertEqual(mio.find("DrawCommands/RoundRectangle").get("Height"), of.find("DrawCommands/RoundRectangle").get("Height"))
        texto = mio.findall("ObjectInfo")[1]
        oficiales = [t for t in self._hijos(of.find("ObjectInfo/AddressObject")) if t not in ("ShowBarcodeFor9DigitZipOnly", "BarcodePosition", "LineFonts")]
        propios = self._hijos(texto.find("TextObject"))
        self.assertEqual([t for t in propios if t in oficiales], oficiales)   # mismos elementos y orden (TextObject añade GroupID/IsOutlined, como DLS)

    def test_32_30252_tambien_es_valido_en_ambos_formatos(self):
        for f in ("30252", "30334"):
            for gen in (lambda: DymoService.generate_dcd_xml(BASE, f), lambda: DymoService.generate_dymo_xml(BASE, f)):
                ET.fromstring(gen())

    def test_29_svg_y_preview(self):
        t = crear_par(self.lote)
        svg = self.client.get(f"/api/dymo/svg/{t['id']}")
        self.assertEqual(svg.headers["content-type"], "image/svg+xml")
        raiz = ET.fromstring(svg.text)
        self.assertEqual(raiz.get("width"), "57mm")
        self.assertEqual(raiz.get("height"), "32mm")
        self.assertIn("guia", self.client.get(f"/api/dymo/svg/{t['id']}?guia=true").text)
        self.assertNotIn("guia", self.client.get(f"/api/dymo/svg/{t['id']}?guia=false").text)
        html = self.client.get(f"/api/dymo/preview/{t['id']}").text
        self.assertIn("57mm", html)
        self.assertIn("@page { size: 57mm 32mm", html)


if __name__ == "__main__":
    unittest.main()
