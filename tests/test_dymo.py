"""DYMO LabelWriter 550, etiqueta 30334 (57 x 32 mm): trama, estados, XML DYMO Connect (.dymo) y v8 (.label),
geometría dentro de la zona segura de 3 mm, peor caso de texto y endpoints de descarga."""
import _aislamiento  # noqa: F401  (debe ser lo primero)
import io
import unittest
import xml.etree.ElementTree as ET
import zipfile

from fastapi.testclient import TestClient

from app.database import db, inventario as inv
from app.main import app
from app.services import dymo_service as dy
from app.services.dymo_service import DymoService

from _aislamiento import crear_par, nuevo_lote, verificar_aislamiento

# Ejemplo del usuario: tarjeta impar (R1 0021 con R2 0010)
EJEMPLO = {"id": 1, "id_tarjeta_num": "0021", "nombre_r1": "TQT-R1-V30-0021", "mac_r1": "70:4B:CA:5B:9F:6E",
           "nombre_r2": "TQT-R2-V30-0010", "mac_r2": "70:4B:CA:5B:9C:A2", "estado_pcb_r1": "FUNCIONAL", "estado_pcb_r2": "FUNCIONAL",
           "estado_general": "LIBERADO"}
PEOR_CASO = {**EJEMPLO, "nombre_r1": "TQT-R1-V31-9999", "mac_r1": "FF:FF:FF:FF:FF:FE", "nombre_r2": "TQT-R2-V31-9999", "mac_r2": "FF:FF:FF:FF:FF:FE"}
MM = 25.4
TW = 1440 / 25.4


def _dcd(xml: str):
    raiz = ET.fromstring(xml)
    objetos = {o.findtext("Name"): o for o in raiz.find("DYMOLabel/DynamicLayoutManager/LabelObjects")}
    return raiz, objetos


def _caja_dcd(obj):  # pulgadas -> mm
    lay = obj.find("ObjectLayout")
    x, y = float(lay.findtext("DYMOPoint/X")) * MM, float(lay.findtext("DYMOPoint/Y")) * MM
    return x, y, float(lay.findtext("Size/Width")) * MM, float(lay.findtext("Size/Height")) * MM


def _cajas_v8(xml: str):
    out = {}
    for info in ET.fromstring(xml).findall("ObjectInfo"):
        nombre = next(info.iter("Name")).text
        b = info.find("Bounds")
        out[nombre] = tuple(int(b.get(k)) / TW for k in ("X", "Y", "Width", "Height"))
    return out


class TestTrama(unittest.TestCase):
    def test_01_trama_exacta_del_usuario(self):
        self.assertEqual(DymoService.format_label_text(EJEMPLO),
                         "TQT-R1-V30-0021\n70:4b:ca:5b:9f:6e\nTQT-R2-V30-0010\n70:4b:ca:5b:9c:a2")
        self.assertEqual(DymoService.format_qr_payload(EJEMPLO), DymoService.format_label_text(EJEMPLO))  # QR = texto impreso

    def test_02_versiones_reales_por_pcb_y_r3_fuera(self):
        t = {**EJEMPLO, "nombre_r1": "TQT-R1-V31-0021", "nombre_r3": "TQT-R3-V30-0021", "mac_r3": "AA:AA:AA:AA:AA:AA"}
        self.assertEqual(DymoService.trama_lineas(t), ["TQT-R1-V31-0021", "70:4b:ca:5b:9f:6e", "TQT-R2-V30-0010", "70:4b:ca:5b:9c:a2"])
        self.assertNotIn("R3", DymoService.format_label_text(t))

    def test_03_mac_ausente_deja_la_linea_vacia(self):
        self.assertEqual(DymoService.trama_lineas({**EJEMPLO, "mac_r2": None})[3], "")
        self.assertEqual(DymoService.trama_lineas({**EJEMPLO, "mac_r1": ""})[1], "")

    def test_04_estados_de_etiqueta(self):
        self.assertEqual(DymoService.estado_etiqueta(EJEMPLO)[0], "FINAL")
        self.assertEqual(DymoService.estado_etiqueta({**EJEMPLO, "nombre_r2": None})[0], "INCOMPLETA")
        est, motivos, adv = DymoService.estado_etiqueta({**EJEMPLO, "mac_r1": None})
        self.assertEqual(est, "IDENTIFICACION")
        self.assertTrue(any("MAC" in m and "R1" in m for m in motivos) and adv)
        # ya no hay pruebas de calidad: solo importan R1 y R2 asignadas y con MAC
        self.assertEqual(DymoService.estado_etiqueta({**EJEMPLO, "estado_pcb_r2": "PENDIENTE"})[0], "FINAL")
        self.assertEqual(DymoService.estado_etiqueta({**EJEMPLO, "estado_general": "DETENIDO"})[0], "FINAL")
        listo, msg, _ = DymoService.validate_label_readiness({**EJEMPLO, "mac_r1": ""})
        self.assertEqual((listo, msg), (False, "REVISAR PCB/MAC"))
        self.assertEqual(DymoService.validate_label_readiness(EJEMPLO)[:2], (True, "LISTA PARA IMPRIMIR"))


class TestGeometria30334(unittest.TestCase):
    def test_05_formato_principal_es_30334(self):
        self.assertEqual(dy.FORMATO_POR_DEFECTO, "30334")
        f = dy.obtener_formato(None)
        self.assertEqual((f.ancho_mm, f.alto_mm, f.paper_name), (57.0, 32.0, "30334 2-1/4 in x 1-1/4 in"))
        self.assertEqual(dy.obtener_formato("30252").ancho_mm, 89.0)  # secundaria
        with self.assertRaises(ValueError):
            dy.obtener_formato("99999")

    def test_06_qr_version_5_nivel_m_con_modulos_enteros(self):
        for t in (EJEMPLO, PEOR_CASO):
            payload = DymoService.format_qr_payload(t)
            self.assertLessEqual(len(payload), 70)
            self.assertEqual(dy.version_qr(payload), 5)             # nivel M: versión 5 (37 módulos). Con L sería 4.
            self.assertEqual(len(dy.matriz_qr(payload)), 37)
            d = DymoService.diseno(t)
            self.assertGreaterEqual(d.puntos_por_modulo, 4)          # nunca menos de 4 puntos (0.34 mm)
            self.assertEqual(d.puntos_por_modulo, 6)                 # 6 puntos = 0.51 mm
            self.assertAlmostEqual(d.qr.w, (37 + 2 * dy.SILENCIO_MODULOS) * 6 / dy.DOTS_PER_MM, places=6)  # módulos enteros

    def test_07_nada_sale_de_la_zona_segura(self):
        for fmt in ("30334", "30252"):
            d = DymoService.diseno(PEOR_CASO, fmt)
            f = d.formato
            s = d.zona_segura
            self.assertEqual((s.x, s.y), (1.5, 1.5))
            self.assertAlmostEqual(s.derecha, f.ancho_mm - 1.5)
            self.assertAlmostEqual(s.abajo, f.alto_mm - 1.5)
            for nombre, caja in (("qr", d.qr), ("texto", d.texto)):
                self.assertGreaterEqual(caja.x, s.x - 1e-9, f"{fmt} {nombre}")
                self.assertGreaterEqual(caja.y, s.y - 1e-9, f"{fmt} {nombre}")
                self.assertLessEqual(caja.derecha, s.derecha + 1e-9, f"{fmt} {nombre}")
                self.assertLessEqual(caja.abajo, s.abajo + 1e-9, f"{fmt} {nombre}")
            self.assertLessEqual(d.qr.derecha + dy.SEPARACION_MM, d.texto.x + 1e-9)  # el texto no toca al QR

    def test_08_zona_segura_util_es_54_x_29_mm(self):
        s = DymoService.diseno(EJEMPLO).zona_segura
        self.assertEqual((s.w, s.h), (54.0, 29.0))
        self.assertEqual((round(s.w * dy.DOTS_PER_MM), round(s.h * dy.DOTS_PER_MM)), (638, 343))

    def test_09_las_4_lineas_no_desbordan_su_caja_en_el_peor_caso(self):
        d = DymoService.diseno(PEOR_CASO)
        lineas = DymoService.trama_lineas(PEOR_CASO)
        self.assertEqual(lineas, ["TQT-R1-V31-9999", "ff:ff:ff:ff:ff:fe", "TQT-R2-V31-9999", "ff:ff:ff:ff:ff:fe"])
        for l in lineas:
            self.assertLessEqual(dy.ancho_texto_mm(l, d.fuente_pt), d.texto.w, l)     # ancho: 17 caracteres = 26.4 mm < 28.2 mm
        self.assertLessEqual(dy.alto_texto_mm(4, d.fuente_pt), d.texto.h)              # alto: 4 líneas = 14 mm < 26 mm
        self.assertGreaterEqual(d.fuente_pt, dy.MIN_FUENTE_PT)                         # nada por debajo de 7 pt
        self.assertEqual(d.fuente_pt, 9.5)

    def test_10_qr_y_texto_dentro_de_la_etiqueta_para_ambos_xml(self):
        for t in (EJEMPLO, PEOR_CASO):
            d = DymoService.diseno(t)
            s = d.zona_segura
            _, objs = _dcd(DymoService.generate_dcd_xml(t))
            for nombre in ("QR", "TEXTO"):
                x, y, w, h = _caja_dcd(objs[nombre])
                self.assertGreaterEqual(x, s.x - 0.01)
                self.assertGreaterEqual(y, s.y - 0.01)
                self.assertLessEqual(x + w, s.derecha + 0.01)
                self.assertLessEqual(y + h, s.abajo + 0.01)
            cajas = _cajas_v8(DymoService.generate_dymo_xml(t))
            for nombre, (x, y, w, h) in cajas.items():
                self.assertGreaterEqual(x, s.x - 0.01, nombre)
                self.assertGreaterEqual(y, s.y - 0.01, nombre)
                self.assertLessEqual(x + w, s.derecha + 0.01, nombre)
                self.assertLessEqual(y + h, s.abajo + 0.01, nombre)


class TestXML(unittest.TestCase):
    def test_11_dcd_dimensiones_y_objetos_nombrados(self):
        raiz, objs = _dcd(DymoService.generate_dcd_xml(EJEMPLO))
        self.assertEqual(raiz.tag, "DesktopLabel")
        self.assertEqual(raiz.find("DYMOLabel").get("Version"), "3")
        self.assertEqual(raiz.findtext("DYMOLabel/Orientation"), "Landscape")
        self.assertEqual(raiz.findtext("DYMOLabel/LabelName"), "SmallMultipurpose")
        # la zona imprimible que declara es la zona segura: 51 x 26 mm desde (3, 3) mm, en pulgadas
        rect = raiz.find("DYMOLabel/DYMORect")
        self.assertAlmostEqual(float(rect.findtext("DYMOPoint/X")) * MM, 1.5, places=2)
        self.assertAlmostEqual(float(rect.findtext("Size/Width")) * MM, 54.0, places=2)
        self.assertAlmostEqual(float(rect.findtext("Size/Height")) * MM, 29.0, places=2)
        self.assertEqual(set(objs), {"QR", "TEXTO"})
        self.assertEqual(objs["QR"].tag, "BarcodeObject")
        self.assertEqual(objs["QR"].findtext("BarcodeFormat"), "QRCode")
        self.assertEqual(objs["QR"].findtext("Data/MultiDataString/DataString"), DymoService.format_qr_payload(EJEMPLO))
        self.assertEqual(objs["TEXTO"].tag, "TextObject")
        lineas = ["".join(t.text or "" for t in ls.iter("Text")) for ls in objs["TEXTO"].iter("LineTextSpan")]
        self.assertEqual(lineas, DymoService.trama_lineas(EJEMPLO))
        self.assertEqual(objs["TEXTO"].findtext(".//FontInfo/FontName"), "Consolas")
        self.assertEqual(float(objs["TEXTO"].findtext(".//FontInfo/FontSize")), 9.5)

    def test_12_dcd_solo_blanco_y_negro(self):
        xml = DymoService.generate_dcd_xml(EJEMPLO)
        for c in ET.fromstring(xml).iter("Color"):
            self.assertEqual((c.get("R"), c.get("G"), c.get("B")) in {("0", "0", "0"), ("1", "1", "1")}, True)  # sin grises
        self.assertNotIn("Gradient", xml)

    def test_13_dcd_texto_como_address_es_la_alternativa_verificada(self):
        _, objs = _dcd(DymoService.generate_dcd_xml(EJEMPLO, texto_como="address"))
        self.assertEqual(objs["TEXTO"].tag, "AddressObject")  # el objeto de texto que trae el ejemplo oficial del SDK

    def test_14_v8_30334_dimensiones_reales(self):
        xml = DymoService.generate_dymo_xml(EJEMPLO)
        raiz = ET.fromstring(xml)
        self.assertEqual(raiz.tag, "DieCutLabel")
        self.assertEqual((raiz.get("Version"), raiz.get("Units")), ("8.0", "twips"))
        self.assertEqual(raiz.findtext("PaperName"), "30334 2-1/4 in x 1-1/4 in")
        self.assertEqual(raiz.findtext("Id"), "Small30334")   # Id real de DYMO Label v8
        self.assertEqual(raiz.findtext("PaperOrientation"), "Portrait")
        rr = raiz.find("DrawCommands/RoundRectangle")
        self.assertEqual((int(rr.get("Width")), int(rr.get("Height"))), (3240, 1800))   # igual que el .label oficial 30334
        self.assertAlmostEqual(int(rr.get("Width")) / TW, 57.0, delta=0.3)
        self.assertAlmostEqual(int(rr.get("Height")) / TW, 32.0, delta=0.3)
        # DLS dibuja BarcodeObject con tamaño fijo (<=16 mm) e ignora la caja: el QR va como imagen de tamaño exacto
        self.assertIsNone(raiz.find("ObjectInfo/BarcodeObject"))
        self.assertEqual(set(_cajas_v8(xml)), {"QR", "TEXTO"})
        import base64, io
        from PIL import Image
        png = Image.open(io.BytesIO(base64.b64decode(raiz.findtext("ObjectInfo/ImageObject/Image"))))
        lado = (37 + 2 * dy.SILENCIO_MODULOS) * dy.PUNTOS_POR_MODULO
        self.assertEqual(png.size, (lado, lado))                    # módulos enteros de 6 puntos a 300 dpi
        d = DymoService.diseno(EJEMPLO)
        self.assertAlmostEqual(_cajas_v8(xml)["QR"][2], lado / dy.DOTS_PER_MM, delta=0.05)   # caja = 20.8 mm
        self.assertEqual(raiz.findtext("ObjectInfo/ImageObject/ScaleMode"), "Uniform")

    def test_15_v8_30252_sigue_disponible(self):
        raiz = ET.fromstring(DymoService.generate_dymo_xml(EJEMPLO, "30252"))
        self.assertEqual(raiz.findtext("PaperName"), "30252 Address")
        self.assertEqual(int(raiz.find("DrawCommands/RoundRectangle").get("Height")), 5040)

    def test_16_svg_a_escala_real_con_guia_punteada(self):
        svg = DymoService.generate_svg_preview(EJEMPLO)
        raiz = ET.fromstring(svg)
        self.assertEqual((raiz.get("width"), raiz.get("height"), raiz.get("viewBox")), ("57mm", "32mm", "0 0 57 32"))
        self.assertIn('stroke-dasharray="1 1"', svg)                       # zona segura punteada
        self.assertNotIn('class="guia"', DymoService.generate_svg_preview(EJEMPLO, guia=False))
        rects = [r for r in raiz.iter("{http://www.w3.org/2000/svg}rect") if r.get("width") and float(r.get("width")) < 1]
        self.assertGreater(len(rects), 300)                               # módulos del QR como vectores (no PNG, no grises)
        textos = [t.text for t in raiz.iter("{http://www.w3.org/2000/svg}text")]
        self.assertEqual(textos, DymoService.trama_lineas(EJEMPLO))

    def test_17_html_preview_a_escala_57x32(self):
        html = DymoService.generate_html_preview({**EJEMPLO, "mac_r2": None})
        self.assertIn("57mm", html)
        self.assertIn("32mm", html)
        self.assertIn("SOLO IDENTIFICACIÓN", html)
        self.assertIn("class=\"guia\"", html)
        self.assertIn("size: 57mm 32mm", html)


class TestEndpointsDymo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        verificar_aislamiento()
        db.init_db()
        cls.client = TestClient(app)
        cls.lote = nuevo_lote()["id"]
        cls.t = crear_par(cls.lote, r3=True)
        db.set_prueba(cls.t["id"], "prueba_pcb", "OK")
        cls.tid = cls.t["id"]

    def test_18_label_por_defecto_es_30334(self):
        d = self.client.get(f"/api/dymo/label/{self.tid}").json()
        self.assertEqual(d["label_format"], "30334")
        self.assertEqual(d["geometria_mm"]["etiqueta"], [57.0, 32.0])
        self.assertEqual(d["estado_etiqueta"], "FINAL")
        self.assertTrue(d["is_ready_to_print"])
        self.assertEqual(d["qr_version"], 5)
        self.assertEqual(len(d["trama_lineas"]), 4)
        self.assertIn("DesktopLabel", d["dcd_xml"])
        self.assertIn("DieCutLabel", d["dymo_xml"])
        self.assertEqual(self.client.get(f"/api/dymo/label/{self.tid}?label_format=99").status_code, 400)
        self.assertEqual(self.client.get("/api/dymo/label/99999999").status_code, 404)

    def test_19_xml_para_openLabelXml(self):
        r = self.client.get(f"/api/dymo/label/{self.tid}/xml")
        self.assertEqual(r.status_code, 200)
        self.assertIn("application/xml", r.headers["content-type"])
        self.assertEqual(ET.fromstring(r.text).tag, "DesktopLabel")
        self.assertFalse(r.content.startswith(b"\xef\xbb\xbf"))           # sin BOM: va directo a openLabelXml
        v8 = self.client.get(f"/api/dymo/label/{self.tid}/xml?tipo=label")
        self.assertEqual(ET.fromstring(v8.text).tag, "DieCutLabel")
        addr = self.client.get(f"/api/dymo/label/{self.tid}/xml?texto_como=address").text
        self.assertIn("<AddressObject>", addr)
        self.assertEqual(self.client.get(f"/api/dymo/label/{self.tid}/xml?tipo=exe").status_code, 422)

    def test_20_archivo_dymo_es_descarga_para_abrir_con_dymo_connect(self):
        r = self.client.get(f"/api/dymo/label/{self.tid}/archivo")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers["content-type"], "application/octet-stream")
        self.assertIn("attachment", r.headers["content-disposition"])
        self.assertIn(f'TQT_{self.t["id_tarjeta_num"]}.dymo', r.headers["content-disposition"])
        self.assertTrue(r.content.startswith(b"\xef\xbb\xbf<?xml"))       # BOM UTF-8 como los archivos oficiales de DYMO
        self.assertEqual(ET.fromstring(r.content.decode("utf-8-sig")).tag, "DesktopLabel")
        lab = self.client.get(f"/api/dymo/label/{self.tid}/archivo?tipo=label")
        self.assertIn(".label", lab.headers["content-disposition"])
        self.assertEqual(self.client.get("/api/dymo/label/99999999/archivo").status_code, 404)

    def test_21_lote_en_zip(self):
        otra = crear_par(self.lote)
        r = self.client.get(f"/api/dymo/lote/archivo?ids={self.tid},{otra['id']},99999999")
        self.assertEqual(r.status_code, 200)
        self.assertIn("attachment", r.headers["content-disposition"])
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            self.assertEqual(sorted(z.namelist()), sorted([f"TQT_{self.t['id_tarjeta_num']}.dymo", f"TQT_{otra['id_tarjeta_num']}.dymo"]))
            for n in z.namelist():
                ET.fromstring(z.read(n).decode("utf-8-sig"))
        self.assertEqual(self.client.get("/api/dymo/lote/archivo?ids=abc").status_code, 400)
        self.assertEqual(self.client.get("/api/dymo/lote/archivo?ids=99999998").status_code, 404)

    def test_22_cola_por_modo(self):
        lote = nuevo_lote()["id"]
        completa = crear_par(lote)
        db.set_prueba(completa["id"], "prueba_pcb", "OK")
        sin_probar = crear_par(lote)
        sin_mac = crear_par(lote, macs=False)
        ids = inv.registrar_manual("R1", None, None, 1)["pcbs"][0]["id"]
        inv.confirmar_recepcion([ids])
        incompleta = inv.crear_tarjeta(lote, None, ids, None, None)
        total = lambda modo: self.client.get(f"/api/dymo/batch-labels?lote_id={lote}&modo={modo}").json()["total"]  # noqa: E731
        self.assertEqual((total("final"), total("identificacion"), total("todas")), (2, 3, 4))
        self.assertEqual(self.client.get(f"/api/dymo/batch-labels?lote_id={lote}").json()["total"], 2)  # only_ready=true por defecto
        self.assertEqual(self.client.get(f"/api/dymo/batch-labels?lote_id={lote}&modo=otro").status_code, 400)
        etiqueta = {d["id_tarjeta_num"]: d for d in self.client.get(f"/api/dymo/batch-labels?lote_id={lote}&modo=todas").json()["labels"]}
        self.assertEqual(etiqueta[incompleta["id_tarjeta_num"]]["estado_etiqueta"], "INCOMPLETA")
        self.assertEqual(etiqueta[sin_mac["id_tarjeta_num"]]["sin_mac"], ["R1", "R2"])
        self.assertEqual(etiqueta[sin_probar["id_tarjeta_num"]]["estado_etiqueta"], "FINAL")  # con MAC basta

    def test_23_preview_y_svg(self):
        h = self.client.get(f"/api/dymo/preview/{self.tid}")
        self.assertEqual(h.status_code, 200)
        self.assertIn("text/html", h.headers["content-type"])
        self.assertIn("57mm", h.text)
        s = self.client.get(f"/api/dymo/svg/{self.tid}")
        self.assertEqual(s.headers["content-type"], "image/svg+xml")
        self.assertIn("dasharray", s.text)
        self.assertNotIn("dasharray", self.client.get(f"/api/dymo/svg/{self.tid}?guia=false").text)


if __name__ == "__main__":
    unittest.main()
