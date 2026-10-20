"""Etiquetas para DYMO LabelWriter 550 (térmica directa, cabezal de 300 dpi).

Formato principal: **30334 Multi-Purpose** (2-1/4" x 1-1/4" = 57 x 32 mm, apaisada). El 30252 (89 x 28 mm) queda
como formato secundario. Todo es blanco y negro puro: sin grises, sin degradados, sin texto menor a 7 pt.

Trama (texto impreso Y contenido del QR), 4 líneas exactas, MAC en minúsculas y R3 fuera:
    TQT-R1-V30-0021
    70:4b:ca:5b:9f:6e
    TQT-R2-V30-0010
    70:4b:ca:5b:9c:a2
Los nombres llevan la versión real de cada PCB. Si falta una MAC esa línea queda vacía (no se inventa).

Estados: INCOMPLETA (falta R1 o R2) · IDENTIFICACION (R1+R2 asignadas; imprimible con aviso) ·
FINAL (R1 y R2 asignadas, ambas con MAC válida) = 'LISTA PARA IMPRIMIR'.

Formatos de archivo que produce (ver docs/DYMO.md):
  * `.dymo`  -> DYMO Connect (DCD): `<DesktopLabel><DYMOLabel Version="3">`, unidades en PULGADAS, objetos
                `QR` (BarcodeObject) y `TEXTO` (TextObject). Es lo que consume `dymo.label.framework.openLabelXml`
                con el servicio web local de DYMO Connect (https://127.0.0.1:41951).
  * `.label` -> DYMO Label v8 (`<DieCutLabel Version="8.0" Units="twips">`), mismos objetos `QR` y `TEXTO`.
La estructura del `.dymo` sigue los ejemplos oficiales dymosoftware/DCD-SDK-Sample (PreviewLabelFramework.dymo y
samplelabel.dymo); el objeto de texto usa la misma forma que su AddressObject (FormattedText/LineTextSpan).
"""
import base64
import html
import io
import logging
import zipfile
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import qrcode
from xml.sax.saxutils import escape as xml_escape

from app.database import db
from app.database.models import extract_mac

logger = logging.getLogger(__name__)

DYMO_WS_PORT = 41951
DYMO_WS_HTTPS_URL = f"https://127.0.0.1:{DYMO_WS_PORT}/DYMO/DLS/Printing"
DYMO_WS_HTTP_URL = f"http://127.0.0.1:{DYMO_WS_PORT}/DYMO/DLS/Printing"

# --- Constantes físicas ------------------------------------------------------------------------------------------
DPI = 300
DOTS_PER_MM = DPI / 25.4                 # 11.811 puntos por mm en el cabezal del LabelWriter 550
TWIPS_PER_MM = 1440 / 25.4
MARGEN_SEGURO_MM = 1.5                   # zona segura: nada se imprime en los 1.5 mm del borde
PUNTOS_POR_MODULO = 6                    # módulo del QR = 6 puntos = 0.508 mm (QR de 20.8 mm; mínimo aceptable: 4)
SILENCIO_MODULOS = 2                     # zona de silencio del QR (DYMO admite 2; el estándar pide 4)
SEPARACION_MM = 1.5                      # aire entre el QR y el texto
FUENTE = "Consolas"                      # monoespaciada de Windows: 17 caracteres a 8 pt = 26.4 mm (Courier New = 28.8)
FUENTE_PT = 9.5
# v1.4.2: en Linux (DYMO compartida en la Raspberry) no hay Consolas; Inconsolata es más angosta, así que el texto cabe.
FUENTE_SVG = f"{FUENTE}, Inconsolata, 'DejaVu Sans Mono', 'Courier New', monospace"
FUENTE_AVANCE_EM = 0.55                  # ancho de un carácter de Consolas en unidades de em
INTERLINEADO = 1.25                      # alto de línea / tamaño de fuente
MIN_FUENTE_PT = 7.0
NIVEL_CORRECCION = qrcode.constants.ERROR_CORRECT_M
PT_A_MM = 25.4 / 72


class LabelFormat(str, Enum):
    DYMO_30334 = "30334"  # 57 x 32 mm (Multi-Purpose 2-1/4" x 1-1/4") — PRINCIPAL
    DYMO_30252 = "30252"  # 89 x 28 mm (Address 1-1/8" x 3-1/2") — secundaria


@dataclass(frozen=True)
class FormatoEtiqueta:
    codigo: str
    ancho_mm: float
    alto_mm: float
    twips_ancho: int          # largo del rollo en twips (orientación apaisada)
    twips_alto: int
    paper_id: str             # DieCutLabel/Id del .label v8
    paper_name: str           # DieCutLabel/PaperName del .label v8
    nombre_dcd: str           # DYMOLabel/LabelName del .dymo (DYMO Connect)
    v8_orientacion: str = "Landscape"  # DieCutLabel/PaperOrientation (copiado de las etiquetas reales de DYMO Label v8)
    v8_ancho: int = 0         # RoundRectangle Width/Height del .label v8 (0 = usar twips_alto / twips_ancho)
    v8_alto: int = 0


FORMATOS: Dict[str, FormatoEtiqueta] = {
    "30334": FormatoEtiqueta("30334", 57.0, 32.0, 3231, 1814, "Small30334", "30334 2-1/4 in x 1-1/4 in", "SmallMultipurpose",
                                "Portrait", 3240, 1800),
    "30252": FormatoEtiqueta("30252", 89.0, 28.0, 5040, 1581, "Address", "30252 Address", "Address"),
}
FORMATO_POR_DEFECTO = "30334"
LEYENDA_APROBADA = "Aprobada"   # v1.4.0: solo en la etiqueta que imprime Validación al aprobar


def obtener_formato(label_format: Optional[str]) -> FormatoEtiqueta:
    """Formato pedido o el principal (30334). Un código desconocido es ValueError."""
    codigo = str(label_format or FORMATO_POR_DEFECTO).strip()
    if codigo not in FORMATOS:
        raise ValueError(f"Formato de etiqueta no soportado: '{label_format}'. Usa 30334 (principal) o 30252.")
    return FORMATOS[codigo]


# --- Geometría ---------------------------------------------------------------------------------------------------
def matriz_qr(texto: str) -> List[List[bool]]:
    """Matriz de módulos del QR (nivel M, sin borde). Para el payload de 4 líneas resulta versión 5 (37 x 37)."""
    qr = qrcode.QRCode(error_correction=NIVEL_CORRECCION, border=0, box_size=1)
    qr.add_data(texto)
    qr.make(fit=True)
    return qr.get_matrix()


def version_qr(texto: str) -> int:
    qr = qrcode.QRCode(error_correction=NIVEL_CORRECCION, border=0, box_size=1)
    qr.add_data(texto)
    qr.make(fit=True)
    return qr.version


@dataclass(frozen=True)
class Caja:
    x: float
    y: float
    w: float
    h: float

    @property
    def derecha(self) -> float:
        return self.x + self.w

    @property
    def abajo(self) -> float:
        return self.y + self.h


@dataclass(frozen=True)
class Diseno:
    formato: FormatoEtiqueta
    zona_segura: Caja           # mm, desde la esquina superior izquierda de la etiqueta (apaisada)
    qr: Caja                    # incluye la zona de silencio
    qr_modulos: int
    puntos_por_modulo: int
    texto: Caja
    fuente_pt: float
    lineas: int = 4


def calcular_diseno(formato: FormatoEtiqueta, qr_modulos: int, lineas: int = 4) -> Diseno:
    """QR a la izquierda (módulos enteros de >= 4 puntos) y texto monoespaciado a la derecha, todo dentro de la zona segura."""
    m = MARGEN_SEGURO_MM
    seguro = Caja(m, m, formato.ancho_mm - 2 * m, formato.alto_mm - 2 * m)
    ppm = PUNTOS_POR_MODULO
    while ppm > 4 and (qr_modulos + 2 * SILENCIO_MODULOS) * ppm / DOTS_PER_MM > seguro.h:
        ppm -= 1
    lado = (qr_modulos + 2 * SILENCIO_MODULOS) * ppm / DOTS_PER_MM
    if lado > seguro.h + 1e-9:
        raise ValueError(f"El QR ({lado:.1f} mm) no cabe en la zona segura de {formato.codigo}.")
    qr = Caja(seguro.x, seguro.y + (seguro.h - lado) / 2, lado, lado)
    x_texto = qr.derecha + SEPARACION_MM
    texto = Caja(x_texto, seguro.y, seguro.derecha - x_texto, seguro.h)
    return Diseno(formato, seguro, qr, qr_modulos, ppm, texto, FUENTE_PT, lineas)


def ancho_texto_mm(linea: str, fuente_pt: float = FUENTE_PT) -> float:
    """Ancho de una línea en la fuente monoespaciada de la etiqueta."""
    return len(linea) * FUENTE_AVANCE_EM * fuente_pt * PT_A_MM


def alto_texto_mm(lineas: int = 4, fuente_pt: float = FUENTE_PT) -> float:
    return lineas * fuente_pt * INTERLINEADO * PT_A_MM


def _tw(mm: float) -> int:
    return round(mm * TWIPS_PER_MM)


def _pulg(mm: float) -> str:
    return f"{mm / 25.4:.4f}"


# --- Etiqueta R3 doble (v1.3.44) ------------------------------------------------------------------------------------
# La PCB R3 es muy pequeña: cada etiqueta lleva DOS R3, una en cada mitad HORIZONTAL (se corta a lo largo: dos tiras de
# 57 x 16 mm). Cada tira: QR (solo el nombre) a la izquierda y el nombre a la derecha. Con una sola R3 se usa la de arriba.
R3_FUENTE_PT = 10.0
R3_SEPARACION_MM = 1.5


@dataclass(frozen=True)
class MitadR3:
    nombre: str
    qr: Caja
    puntos_por_modulo: int
    texto: Caja


def calcular_diseno_r3(formato: FormatoEtiqueta, nombres: List[str]) -> List[MitadR3]:
    m = MARGEN_SEGURO_MM
    mitad = formato.alto_mm / 2
    mitades: List[MitadR3] = []
    for i, nombre in enumerate(nombres[:2]):
        y0, alto = i * mitad + m, mitad - 2 * m
        modulos = len(matriz_qr(nombre)) + 2 * SILENCIO_MODULOS
        ppm = PUNTOS_POR_MODULO
        while ppm > 3 and modulos * ppm / DOTS_PER_MM > alto:
            ppm -= 1
        lado = modulos * ppm / DOTS_PER_MM
        qr = Caja(m, y0 + (alto - lado) / 2, lado, lado)
        x_txt = qr.derecha + R3_SEPARACION_MM
        texto = Caja(x_txt, y0, formato.ancho_mm - m - x_txt, alto)
        mitades.append(MitadR3(nombre, qr, ppm, texto))
    return mitades


# --- Etiqueta de cable (v1.3.83) -----------------------------------------------------------------------------------
# La etiqueta rectangular se divide a la mitad en vertical: solo la mitad izquierda lleva el número (grande y centrado);
# la derecha va en blanco porque se enrolla sobre el cable y queda visible solo el número.
# v1.3.84: el número va en vertical (girado 90°), a lo largo de la mitad izquierda.
CABLE_FUENTE_PT = 36.0

# --- Etiqueta de activo (v1.4.14/16): «ACT 0001» grande y centrado a la derecha del QR, sin más líneas ---
ACTIVO_CODIGO_PT = 24.0        # tope del tamaño del código
ACTIVO_MIN_CODIGO_PT = 18.0    # el QR crece mientras el código no baje de esto
ACTIVO_MAX_PUNTOS = 8          # puntos por módulo del QR (0.68 mm a 300 dpi); la etiqueta de tarjeta usa 6


CABLE_TEXTO_ANCHO_MM = 13.0   # v1.3.93: franja pegada al borde izquierdo (al doblar, el texto no se recorre hacia la línea)


def caja_cable(formato: "FormatoEtiqueta") -> "Caja":
    m = MARGEN_SEGURO_MM
    return Caja(m, m, min(CABLE_TEXTO_ANCHO_MM, formato.ancho_mm / 2 - 2 * m), formato.alto_mm - 2 * m)


# v1.3.90: línea punteada vertical al centro (referencia para doblar/pegar la etiqueta sobre el cable).
CABLE_LINEA_ANCHO_MM = 1.5   # v1.3.91: caja más ancha y trazo de 0.5 mm para que DYMO no la descarte
CABLE_GUION_MM, CABLE_HUECO_MM = 1.6, 1.2


def lineas_cable(numero: str, r3: str = "") -> List[str]:
    """v1.4.5: «Cable R3» = «TQT: 0000» arriba y «R3: 0000» abajo; el cable normal sigue con «TQT» y el número."""
    return [f"TQT: {numero}", f"R3: {r3}"] if r3 else ["TQT", numero]


def caja_linea_cable(formato: "FormatoEtiqueta") -> "Caja":
    m = MARGEN_SEGURO_MM
    return Caja(formato.ancho_mm / 2 - CABLE_LINEA_ANCHO_MM / 2, m, CABLE_LINEA_ANCHO_MM, formato.alto_mm - 2 * m)


def png_linea_punteada(c: "Caja") -> str:
    """PNG (base64) a 300 dpi con una línea vertical punteada negra que llena la caja `c`."""
    from PIL import Image, ImageDraw
    ppm = 300 / 25.4
    w, h = max(3, round(c.w * ppm)), max(10, round(c.h * ppm))
    img = Image.new("L", (w, h), 255)
    d = ImageDraw.Draw(img)
    guion, paso = round(CABLE_GUION_MM * ppm), round((CABLE_GUION_MM + CABLE_HUECO_MM) * ppm)
    x0, x1 = w // 2 - 3, w // 2 + 3   # ~0.5 mm a 300 dpi
    for y in range(0, h, paso):
        d.rectangle([x0, y, x1, min(h - 1, y + guion - 1)], fill=0)
    buf = io.BytesIO()
    img.convert("1").save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _v8_imagen(nombre: str, png: str, c: "Caja") -> str:
    return f"""    <ObjectInfo>
        <ImageObject>
            <Name>{nombre}</Name>
            <ForeColor Alpha="255" Red="0" Green="0" Blue="0" />
            <BackColor Alpha="0" Red="255" Green="255" Blue="255" />
            <LinkedObjectName></LinkedObjectName>
            <Rotation>Rotation0</Rotation>
            <IsMirrored>False</IsMirrored>
            <IsVariable>False</IsVariable>
            <GroupID>-1</GroupID>
            <IsOutlined>False</IsOutlined>
            <Image>{png}</Image>
            <ScaleMode>Uniform</ScaleMode>
            <BorderWidth>0</BorderWidth>
            <BorderColor Alpha="255" Red="0" Green="0" Blue="0" />
            <HorizontalAlignment>Center</HorizontalAlignment>
            <VerticalAlignment>Center</VerticalAlignment>
        </ImageObject>
        <Bounds X="{_tw(c.x)}" Y="{_tw(c.y)}" Width="{_tw(c.w)}" Height="{_tw(c.h)}" />
    </ObjectInfo>
"""


def _v8_texto(nombre: str, texto: str, pt: float, c: "Caja", alineacion: str = "Left", rotacion: str = "Rotation0") -> str:
    return f"""    <ObjectInfo>
        <TextObject>
            <Name>{nombre}</Name>
            <ForeColor Alpha="255" Red="0" Green="0" Blue="0" />
            <BackColor Alpha="0" Red="255" Green="255" Blue="255" />
            <LinkedObjectName></LinkedObjectName>
            <Rotation>{rotacion}</Rotation>
            <IsMirrored>False</IsMirrored>
            <IsVariable>False</IsVariable>
            <GroupID>-1</GroupID>
            <IsOutlined>False</IsOutlined>
            <HorizontalAlignment>{alineacion}</HorizontalAlignment>
            <VerticalAlignment>Middle</VerticalAlignment>
            <TextFitMode>ShrinkToFit</TextFitMode>
            <UseFullFontHeight>True</UseFullFontHeight>
            <Verticalized>False</Verticalized>
            <StyledText>
                <Element>
                    <String>{xml_escape(texto)}</String>
                    <Attributes>
                        <Font Family="{FUENTE}" Size="{pt:g}" Bold="True" Italic="False" Underline="False" Strikeout="False" />
                        <ForeColor Alpha="255" Red="0" Green="0" Blue="0" />
                    </Attributes>
                </Element>
            </StyledText>
        </TextObject>
        <Bounds X="{_tw(c.x)}" Y="{_tw(c.y)}" Width="{_tw(c.w)}" Height="{_tw(c.h)}" />
    </ObjectInfo>
"""


class DymoService:
    """Validación, trama, QR y archivos de etiqueta para la DYMO LabelWriter 550."""

    # ------------------------------------------------------------------ reglas
    @staticmethod
    def estado_etiqueta(tarjeta: Dict[str, Any]) -> Tuple[str, List[str], List[str]]:
        """Devuelve (estado, motivos_para_FINAL, advertencias).
          INCOMPLETA     : falta la R1 o la R2 (no hay trama que imprimir).
          IDENTIFICACION : R1 y R2 asignadas, pero aún no cumple la regla FINAL.
          FINAL          : R1 y R2 asignadas y con MAC válida (ya no hay pruebas de calidad que condicionen la etiqueta).
        """
        motivos: List[str] = []
        nombre_r1, nombre_r2 = tarjeta.get("nombre_r1"), tarjeta.get("nombre_r2")
        if not nombre_r1:
            motivos.append("Falta asignar la PCB Principal (R1).")
        if not nombre_r2:
            motivos.append("Falta asignar la PCB de Respaldo (R2).")
        if not (nombre_r1 and nombre_r2):
            return "INCOMPLETA", motivos, []

        for etiqueta, clave in (("Principal (R1)", "mac_r1"), ("Respaldo (R2)", "mac_r2")):
            if not extract_mac(str(tarjeta.get(clave) or "")):
                motivos.append(f"MAC de Tarjeta {etiqueta} faltante o con formato inválido.")
        advertencias = [m for m in motivos if "MAC" in m]
        return ("FINAL" if not motivos else "IDENTIFICACION"), motivos, advertencias

    @classmethod
    def validate_label_readiness(cls, tarjeta: Dict[str, Any], pcb_r1: Optional[Dict[str, Any]] = None,
                                 pcb_r2: Optional[Dict[str, Any]] = None) -> Tuple[bool, str, List[str]]:
        """'LISTA PARA IMPRIMIR' = estado FINAL (ambas MAC válidas).
        `pcb_r1`/`pcb_r2` (opcionales) sobreescriben MAC/estado de esa PCB para consultas puntuales."""
        datos = dict(tarjeta)
        for k, pcb in (("r1", pcb_r1), ("r2", pcb_r2)):
            if pcb:
                datos[f"mac_{k}"] = datos.get(f"mac_{k}") or pcb.get("mac_address") or pcb.get("mac")
                if pcb.get("estado_pcb"):
                    datos[f"estado_pcb_{k}"] = pcb["estado_pcb"]
                datos[f"nombre_{k}"] = datos.get(f"nombre_{k}") or pcb.get("nombre")
        estado, motivos, _ = cls.estado_etiqueta(datos)
        listo = estado == "FINAL"
        return listo, ("LISTA PARA IMPRIMIR" if listo else "REVISAR PCB/MAC"), motivos

    # ------------------------------------------------------------------ trama
    @staticmethod
    def trama_lineas(tarjeta: Dict[str, Any]) -> List[str]:
        """Las 4 líneas de la trama: nombre R1, MAC R1 (minúsculas), nombre R2, MAC R2 (minúsculas)."""
        if tarjeta.get("_lineas"):   # etiqueta suelta (p. ej. R3: solo su nombre)
            return [str(x) for x in tarjeta["_lineas"]]
        def mac(clave: str) -> str:
            m = extract_mac(str(tarjeta.get(clave) or ""))
            return m.lower() if m else ""
        return [str(tarjeta.get("nombre_r1") or ""), mac("mac_r1"), str(tarjeta.get("nombre_r2") or ""), mac("mac_r2")]

    @classmethod
    def lineas_texto(cls, tarjeta: Dict[str, Any], aprobada: bool = False) -> List[str]:
        """v1.4.0: líneas del texto impreso. Con `aprobada` se agrega debajo la leyenda exacta «Aprobada»; el QR NO cambia."""
        lin = cls.trama_lineas(tarjeta)
        return lin + [LEYENDA_APROBADA] if aprobada else lin

    @classmethod
    def format_label_text(cls, tarjeta: Dict[str, Any]) -> str:
        """Texto impreso de la etiqueta: las 4 líneas de la trama unidas con salto de línea, sin salto final."""
        return "\n".join(cls.trama_lineas(tarjeta))

    @classmethod
    def format_qr_payload(cls, tarjeta: Dict[str, Any]) -> str:
        """Contenido del QR de la etiqueta: exactamente la misma trama que el texto impreso."""
        return cls.format_label_text(tarjeta)

    @staticmethod
    def generate_qr_base64(qr_text: str, box_size: int = 6, border: int = SILENCIO_MODULOS) -> str:
        """PNG del QR (nivel M, módulos de `box_size` px) en Base64, solo blanco y negro puros."""
        qr = qrcode.QRCode(error_correction=NIVEL_CORRECCION, box_size=box_size, border=border)
        qr.add_data(qr_text)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white").convert("1")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("ascii")

    @classmethod
    def diseno(cls, tarjeta: Dict[str, Any], label_format: Optional[str] = None) -> Diseno:
        formato = obtener_formato(label_format)
        return calcular_diseno(formato, len(matriz_qr(cls.format_qr_payload(tarjeta))))

    # ------------------------------------------------------------------ .label (DYMO Label v8, twips)
    @classmethod
    def generate_dymo_xml(cls, tarjeta: Dict[str, Any], label_format: Optional[str] = None, aprobada: bool = False) -> str:
        """`.label` de DYMO Label v8 con los objetos `QR` (BarcodeObject) y `TEXTO` (TextObject)."""
        d = cls.diseno(tarjeta, label_format)
        f = d.formato
        # El servicio DLS dibuja un BarcodeObject con tamaño fijo (Small/Medium/Large, máx. 16 mm) e ignora la caja;
        # por eso el QR va como imagen 1 bit a 300 dpi, con módulos de PUNTOS_POR_MODULO puntos exactos.
        qr_png = cls.generate_qr_base64(cls.format_qr_payload(tarjeta), box_size=d.puntos_por_modulo)
        texto = xml_escape("\n".join(cls.lineas_texto(tarjeta, aprobada)))
        qr, tx = d.qr, d.texto
        return f"""<?xml version="1.0" encoding="utf-8"?>
<DieCutLabel Version="8.0" Units="twips">
    <PaperOrientation>{f.v8_orientacion}</PaperOrientation>
    <Id>{f.paper_id}</Id>
    <PaperName>{f.paper_name}</PaperName>
    <DrawCommands>
        <RoundRectangle X="0" Y="0" Width="{f.v8_ancho or f.twips_alto}" Height="{f.v8_alto or f.twips_ancho}" Rx="270" Ry="270" />
    </DrawCommands>
    <ObjectInfo>
        <ImageObject>
            <Name>QR</Name>
            <ForeColor Alpha="255" Red="0" Green="0" Blue="0" />
            <BackColor Alpha="0" Red="255" Green="255" Blue="255" />
            <LinkedObjectName></LinkedObjectName>
            <Rotation>Rotation0</Rotation>
            <IsMirrored>False</IsMirrored>
            <IsVariable>False</IsVariable>
            <GroupID>-1</GroupID>
            <IsOutlined>False</IsOutlined>
            <Image>{qr_png}</Image>
            <ScaleMode>Uniform</ScaleMode>
            <BorderWidth>0</BorderWidth>
            <BorderColor Alpha="255" Red="0" Green="0" Blue="0" />
            <HorizontalAlignment>Center</HorizontalAlignment>
            <VerticalAlignment>Center</VerticalAlignment>
        </ImageObject>
        <Bounds X="{_tw(qr.x)}" Y="{_tw(qr.y)}" Width="{_tw(qr.w)}" Height="{_tw(qr.h)}" />
    </ObjectInfo>
    <ObjectInfo>
        <TextObject>
            <Name>TEXTO</Name>
            <ForeColor Alpha="255" Red="0" Green="0" Blue="0" />
            <BackColor Alpha="0" Red="255" Green="255" Blue="255" />
            <LinkedObjectName></LinkedObjectName>
            <Rotation>Rotation0</Rotation>
            <IsMirrored>False</IsMirrored>
            <IsVariable>False</IsVariable>
            <GroupID>-1</GroupID>
            <IsOutlined>False</IsOutlined>
            <HorizontalAlignment>Left</HorizontalAlignment>
            <VerticalAlignment>Middle</VerticalAlignment>
            <TextFitMode>ShrinkToFit</TextFitMode>
            <UseFullFontHeight>True</UseFullFontHeight>
            <Verticalized>False</Verticalized>
            <StyledText>
                <Element>
                    <String>{texto}</String>
                    <Attributes>
                        <Font Family="{FUENTE}" Size="{d.fuente_pt:g}" Bold="True" Italic="False" Underline="False" Strikeout="False" />
                        <ForeColor Alpha="255" Red="0" Green="0" Blue="0" />
                    </Attributes>
                </Element>
            </StyledText>
        </TextObject>
        <Bounds X="{_tw(tx.x)}" Y="{_tw(tx.y)}" Width="{_tw(tx.w)}" Height="{_tw(tx.h)}" />
    </ObjectInfo>
</DieCutLabel>"""

    # ------------------------------------------------------------------ .dymo (DYMO Connect / DCD, pulgadas)
    @staticmethod
    def _color(a: int, r: int, g: int, b: int) -> str:
        return f'<SolidColorBrush><Color A="{a}" R="{r}" G="{g}" B="{b}"></Color></SolidColorBrush>'

    @classmethod
    def _brushes(cls, fondo_alpha: int = 0) -> str:
        negro, blanco = cls._color(1, 0, 0, 0), cls._color(fondo_alpha, 1, 1, 1)
        return (f"<Brushes><BackgroundBrush>{blanco}</BackgroundBrush><BorderBrush>{negro}</BorderBrush>"
                f"<StrokeBrush>{negro}</StrokeBrush><FillBrush>{negro}</FillBrush></Brushes>")

    @classmethod
    def generate_dcd_xml(cls, tarjeta: Dict[str, Any], label_format: Optional[str] = None, texto_como: str = "text",
                     aprobada: bool = False) -> str:
        """Etiqueta para DYMO Connect (`.dymo`, lo que recibe `dymo.label.framework.openLabelXml`).
        Objetos con nombre: `QR` (BarcodeObject, payload = trama de 4 líneas) y `TEXTO` (las mismas 4 líneas).
        `texto_como='address'` emite el texto como AddressObject (el único objeto de texto que trae el ejemplo oficial)
        por si una versión de DYMO Connect no acepta TextObject."""
        d = cls.diseno(tarjeta, label_format)
        f = d.formato
        payload = xml_escape(cls.format_qr_payload(tarjeta))
        negro = cls._color(1, 0, 0, 0)
        fuente = (f"<FontInfo><FontName>{FUENTE}</FontName><FontSize>{d.fuente_pt:g}</FontSize><IsBold>True</IsBold>"
                  f"<IsItalic>False</IsItalic><IsUnderline>False</IsUnderline><FontBrush>{negro}</FontBrush></FontInfo>")
        lineas = "".join(f"<LineTextSpan><TextSpan><Text>{xml_escape(l)}</Text>{fuente}</TextSpan></LineTextSpan>"
                         for l in cls.lineas_texto(tarjeta, aprobada))
        margen = '<Margin><DYMOThickness Left="0" Top="0" Right="0" Bottom="0" /></Margin>'
        qr, tx, seg = d.qr, d.texto, d.zona_segura
        objeto = "AddressObject" if texto_como == "address" else "TextObject"
        extra = "<BarcodePosition>None</BarcodePosition>" if texto_como == "address" else ""

        def layout(c: Caja) -> str:
            return (f"<ObjectLayout><DYMOPoint><X>{_pulg(c.x)}</X><Y>{_pulg(c.y)}</Y></DYMOPoint>"
                    f"<Size><Width>{_pulg(c.w)}</Width><Height>{_pulg(c.h)}</Height></Size></ObjectLayout>")

        return f"""<?xml version="1.0" encoding="utf-8"?>
<DesktopLabel Version="1">
  <DYMOLabel Version="3">
    <Description>TQT {f.codigo} {f.ancho_mm:g}x{f.alto_mm:g} mm</Description>
    <Orientation>Landscape</Orientation>
    <LabelName>{f.nombre_dcd}</LabelName>
    <InitialLength>0</InitialLength>
    <BorderStyle>SolidLine</BorderStyle>
    <DYMORect>
      <DYMOPoint>
        <X>{_pulg(seg.x)}</X>
        <Y>{_pulg(seg.y)}</Y>
      </DYMOPoint>
      <Size>
        <Width>{_pulg(seg.w)}</Width>
        <Height>{_pulg(seg.h)}</Height>
      </Size>
    </DYMORect>
    <BorderColor>{negro}</BorderColor>
    <BorderThickness>1</BorderThickness>
    <Show_Border>False</Show_Border>
    <DynamicLayoutManager>
      <RotationBehavior>ClearObjects</RotationBehavior>
      <LabelObjects>
        <BarcodeObject>
          <Name>QR</Name>
          {cls._brushes()}
          <Rotation>Rotation0</Rotation>
          <OutlineThickness>1</OutlineThickness>
          <IsOutlined>False</IsOutlined>
          <BorderStyle>SolidLine</BorderStyle>
          {margen}
          <BarcodeFormat>QRCode</BarcodeFormat>
          <Data>
            <MultiDataString>
              <DataString>{payload}</DataString>
            </MultiDataString>
          </Data>
          <HorizontalAlignment>Center</HorizontalAlignment>
          <VerticalAlignment>Middle</VerticalAlignment>
          <Size>Medium</Size>
          <TextPosition>None</TextPosition>
          <FontInfo><FontName>{FUENTE}</FontName><FontSize>8</FontSize><IsBold>False</IsBold><IsItalic>False</IsItalic><IsUnderline>False</IsUnderline><FontBrush>{negro}</FontBrush></FontInfo>
          {layout(qr)}
        </BarcodeObject>
        <{objeto}>
          <Name>TEXTO</Name>
          {cls._brushes()}
          <Rotation>Rotation0</Rotation>
          <OutlineThickness>1</OutlineThickness>
          <IsOutlined>False</IsOutlined>
          <BorderStyle>SolidLine</BorderStyle>
          {margen}
          <HorizontalAlignment>Left</HorizontalAlignment>
          <VerticalAlignment>Middle</VerticalAlignment>
          <FitMode>AlwaysFit</FitMode>
          <IsVertical>False</IsVertical>
          <FormattedText>
            <FitMode>AlwaysFit</FitMode>
            <HorizontalAlignment>Left</HorizontalAlignment>
            <VerticalAlignment>Middle</VerticalAlignment>
            <IsVertical>False</IsVertical>
            {lineas}
          </FormattedText>
          {extra}
          {layout(tx)}
        </{objeto}>
      </LabelObjects>
    </DynamicLayoutManager>
  </DYMOLabel>
  <LabelApplication>Blank</LabelApplication>
  <DataTable>
    <Columns></Columns>
    <Rows></Rows>
  </DataTable>
</DesktopLabel>"""

    @classmethod
    def archivo_dymo(cls, tarjeta: Dict[str, Any], label_format: Optional[str] = None, tipo: str = "dymo",
                     aprobada: bool = False) -> Tuple[bytes, str]:
        """(bytes, nombre) del archivo para abrir en DYMO. `.dymo` = DYMO Connect (con BOM UTF-8 como los oficiales);
        `.label` = DYMO Label v8."""
        num = tarjeta.get("id_tarjeta_num") or "0000"
        if tipo == "label":
            return cls.generate_dymo_xml(tarjeta, label_format, aprobada).encode("utf-8"), f"TQT_{num}.label"
        return b"\xef\xbb\xbf" + cls.generate_dcd_xml(tarjeta, label_format, aprobada=aprobada).encode("utf-8"), f"TQT_{num}.dymo"

    @classmethod
    def zip_lote(cls, tarjetas: List[Dict[str, Any]], label_format: Optional[str] = None, tipo: str = "dymo") -> bytes:
        """ZIP con un archivo por tarjeta (un `.dymo` con varias etiquetas no es un formato documentado)."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            usados = set()
            for t in tarjetas:
                datos, nombre = cls.archivo_dymo(t, label_format, tipo)
                if nombre in usados:  # mismo número en lotes distintos (o ids repetidos): el ZIP no puede tener nombres repetidos
                    base, ext = nombre.rsplit(".", 1)
                    nombre = f"{base}_id{t.get('id')}.{ext}"
                usados.add(nombre)
                z.writestr(nombre, datos)
        return buf.getvalue()

    # ------------------------------------------------------------------ R3 doble (v1.3.44): dos R3 por etiqueta, una por mitad
    @classmethod
    def generate_r3_label_xml(cls, nombres: List[str], label_format: Optional[str] = None) -> str:
        """`.label` (DYMO Label v8) con 1 o 2 R3: objetos QR1/TEXTO1 (mitad de arriba) y QR2/TEXTO2 (de abajo)."""
        f = obtener_formato(label_format)
        objetos = ""
        for i, md in enumerate(calcular_diseno_r3(f, nombres), 1):
            objetos += _v8_imagen(f"QR{i}", cls.generate_qr_base64(md.nombre, box_size=md.puntos_por_modulo), md.qr)
            objetos += _v8_texto(f"TEXTO{i}", md.nombre, R3_FUENTE_PT, md.texto)
        return f"""<?xml version="1.0" encoding="utf-8"?>
<DieCutLabel Version="8.0" Units="twips">
    <PaperOrientation>{f.v8_orientacion}</PaperOrientation>
    <Id>{f.paper_id}</Id>
    <PaperName>{f.paper_name}</PaperName>
    <DrawCommands>
        <RoundRectangle X="0" Y="0" Width="{f.v8_ancho or f.twips_alto}" Height="{f.v8_alto or f.twips_ancho}" Rx="270" Ry="270" />
    </DrawCommands>
{objetos}</DieCutLabel>"""

    @classmethod
    def generate_r3_dcd_xml(cls, nombres: List[str], label_format: Optional[str] = None) -> str:
        """`.dymo` (DYMO Connect) con 1 o 2 R3, una por mitad de la etiqueta."""
        f = obtener_formato(label_format)
        m = MARGEN_SEGURO_MM
        negro = cls._color(1, 0, 0, 0)
        margen = '<Margin><DYMOThickness Left="0" Top="0" Right="0" Bottom="0" /></Margin>'

        def layout(c: Caja) -> str:
            return (f"<ObjectLayout><DYMOPoint><X>{_pulg(c.x)}</X><Y>{_pulg(c.y)}</Y></DYMOPoint>"
                    f"<Size><Width>{_pulg(c.w)}</Width><Height>{_pulg(c.h)}</Height></Size></ObjectLayout>")
        fuente = (f"<FontInfo><FontName>{FUENTE}</FontName><FontSize>{R3_FUENTE_PT:g}</FontSize><IsBold>True</IsBold>"
                  f"<IsItalic>False</IsItalic><IsUnderline>False</IsUnderline><FontBrush>{negro}</FontBrush></FontInfo>")
        objetos = ""
        for i, md in enumerate(calcular_diseno_r3(f, nombres), 1):
            objetos += f"""
        <BarcodeObject>
          <Name>QR{i}</Name>
          {cls._brushes()}
          <Rotation>Rotation0</Rotation>
          <OutlineThickness>1</OutlineThickness>
          <IsOutlined>False</IsOutlined>
          <BorderStyle>SolidLine</BorderStyle>
          {margen}
          <BarcodeFormat>QRCode</BarcodeFormat>
          <Data><MultiDataString><DataString>{xml_escape(md.nombre)}</DataString></MultiDataString></Data>
          <HorizontalAlignment>Center</HorizontalAlignment>
          <VerticalAlignment>Middle</VerticalAlignment>
          <Size>Medium</Size>
          <TextPosition>None</TextPosition>
          {fuente}
          {layout(md.qr)}
        </BarcodeObject>
        <TextObject>
          <Name>TEXTO{i}</Name>
          {cls._brushes()}
          <Rotation>Rotation0</Rotation>
          <OutlineThickness>1</OutlineThickness>
          <IsOutlined>False</IsOutlined>
          <BorderStyle>SolidLine</BorderStyle>
          {margen}
          <HorizontalAlignment>Left</HorizontalAlignment>
          <VerticalAlignment>Middle</VerticalAlignment>
          <FitMode>AlwaysFit</FitMode>
          <IsVertical>False</IsVertical>
          <FormattedText>
            <FitMode>AlwaysFit</FitMode>
            <HorizontalAlignment>Left</HorizontalAlignment>
            <VerticalAlignment>Middle</VerticalAlignment>
            <IsVertical>False</IsVertical>
            <LineTextSpan><TextSpan><Text>{xml_escape(md.nombre)}</Text>{fuente}</TextSpan></LineTextSpan>
          </FormattedText>
          {layout(md.texto)}
        </TextObject>"""
        return f"""<?xml version="1.0" encoding="utf-8"?>
<DesktopLabel Version="1">
  <DYMOLabel Version="3">
    <Description>TQT R3 doble {f.codigo} {f.ancho_mm:g}x{f.alto_mm:g} mm</Description>
    <Orientation>Landscape</Orientation>
    <LabelName>{f.nombre_dcd}</LabelName>
    <InitialLength>0</InitialLength>
    <BorderStyle>SolidLine</BorderStyle>
    <DYMORect>
      <DYMOPoint><X>{_pulg(m)}</X><Y>{_pulg(m)}</Y></DYMOPoint>
      <Size><Width>{_pulg(f.ancho_mm - 2 * m)}</Width><Height>{_pulg(f.alto_mm - 2 * m)}</Height></Size>
    </DYMORect>
    <BorderColor>{negro}</BorderColor>
    <BorderThickness>1</BorderThickness>
    <Show_Border>False</Show_Border>
    <DynamicLayoutManager>
      <RotationBehavior>ClearObjects</RotationBehavior>
      <LabelObjects>{objetos}
      </LabelObjects>
    </DynamicLayoutManager>
  </DYMOLabel>
  <LabelApplication>Blank</LabelApplication>
  <DataTable>
    <Columns></Columns>
    <Rows></Rows>
  </DataTable>
</DesktopLabel>"""

    @classmethod
    def archivo_r3(cls, nombres: List[str], label_format: Optional[str] = None, tipo: str = "dymo") -> Tuple[bytes, str]:
        base = "_".join(n.rsplit("-", 1)[-1] for n in nombres[:2])
        if tipo == "label":
            return cls.generate_r3_label_xml(nombres, label_format).encode("utf-8"), f"TQT_R3_{base}.label"
        return b"\xef\xbb\xbf" + cls.generate_r3_dcd_xml(nombres, label_format).encode("utf-8"), f"TQT_R3_{base}.dymo"

    # ------------------------------------------------------------------ cable (v1.3.83): número en la mitad izquierda
    @classmethod
    def generate_cable_label_xml(cls, numero: str, label_format: Optional[str] = None, r3: str = "") -> str:
        """`.label` (DYMO Label v8) con el número solo en la mitad izquierda."""
        f = obtener_formato(label_format)
        objeto = _v8_texto("NUMERO", "\n".join(lineas_cable(numero, r3)), CABLE_FUENTE_PT, caja_cable(f), "Center", "Rotation90")   # v1.3.84 vertical; v1.3.92 «TQT» arriba
        linea = caja_linea_cable(f)
        objeto += _v8_imagen("LINEA", png_linea_punteada(linea), linea)   # v1.3.90: línea punteada al centro
        return f"""<?xml version="1.0" encoding="utf-8"?>
<DieCutLabel Version="8.0" Units="twips">
    <PaperOrientation>{f.v8_orientacion}</PaperOrientation>
    <Id>{f.paper_id}</Id>
    <PaperName>{f.paper_name}</PaperName>
    <DrawCommands>
        <RoundRectangle X="0" Y="0" Width="{f.v8_ancho or f.twips_alto}" Height="{f.v8_alto or f.twips_ancho}" Rx="270" Ry="270" />
    </DrawCommands>
{objeto}</DieCutLabel>"""

    @classmethod
    def generate_r3_svg(cls, nombres: List[str], label_format: Optional[str] = None) -> str:
        """v1.4.2: SVG a escala real (1 unidad = 1 mm) de la etiqueta R3 doble, mismo diseño que el .label (QR + nombre por mitad)."""
        f = obtener_formato(label_format)
        pt = R3_FUENTE_PT * PT_A_MM
        partes = []
        for md in calcular_diseno_r3(f, nombres):
            mod = md.puntos_por_modulo / DOTS_PER_MM
            x0, y0 = md.qr.x + SILENCIO_MODULOS * mod, md.qr.y + SILENCIO_MODULOS * mod
            partes.append("".join(f'<rect x="{x0 + c * mod:.4f}" y="{y0 + r * mod:.4f}" width="{mod:.4f}" height="{mod:.4f}"/>'
                                  for r, fila in enumerate(matriz_qr(md.nombre)) for c, v in enumerate(fila) if v))
            partes.append(f'<text x="{md.texto.x:.3f}" y="{md.texto.y + md.texto.h / 2:.3f}" dominant-baseline="central" '
                          f'font-family="{FUENTE_SVG}" font-weight="700" font-size="{pt:.4f}">{xml_escape(md.nombre)}</text>')
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{f.ancho_mm:g}mm" height="{f.alto_mm:g}mm" viewBox="0 0 {f.ancho_mm:g} {f.alto_mm:g}">'
                f'<rect width="{f.ancho_mm:g}" height="{f.alto_mm:g}" fill="#fff"/><g fill="#000" shape-rendering="crispEdges">{"".join(partes)}</g></svg>')

    @classmethod
    def generate_cable_svg(cls, numero: str, label_format: Optional[str] = None, r3: str = "") -> str:
        """v1.4.0: SVG a escala real (1 unidad = 1 mm) de la etiqueta de cable, para el respaldo de impresión del navegador."""
        f = obtener_formato(label_format)
        c, ln = caja_cable(f), caja_linea_cable(f)
        # v1.4.2: dos líneas («TQT» y el número) deben caber en la franja de c.w mm; a 36 pt se salían del borde izquierdo.
        arriba, abajo = lineas_cable(numero, r3)
        pt = min(CABLE_FUENTE_PT * PT_A_MM, c.w / 2.1, c.h / (max(len(arriba), len(abajo), 3) * 0.6))
        cx, cy = c.x + c.w / 2, c.y + c.h / 2
        textos = "".join(f'<text transform="translate({cx + dx:.3f} {cy:.3f}) rotate(-90)" text-anchor="middle" dominant-baseline="central">{xml_escape(t)}</text>'
                         for dx, t in ((-pt * 0.52, arriba), (pt * 0.52, abajo)))
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{f.ancho_mm:g}mm" height="{f.alto_mm:g}mm" viewBox="0 0 {f.ancho_mm:g} {f.alto_mm:g}">'
                f'<rect width="{f.ancho_mm:g}" height="{f.alto_mm:g}" fill="#fff"/>'
                f'<g fill="#000" font-family="{FUENTE_SVG}" font-weight="700" font-size="{pt:.4f}">{textos}</g>'
                f'<line x1="{ln.x + ln.w / 2:.3f}" y1="{ln.y:.3f}" x2="{ln.x + ln.w / 2:.3f}" y2="{ln.abajo:.3f}" stroke="#000" stroke-width="0.5" '
                f'stroke-dasharray="{CABLE_GUION_MM} {CABLE_HUECO_MM}"/></svg>')

    @classmethod
    def generate_cable_dcd_xml(cls, numero: str, label_format: Optional[str] = None, r3: str = "") -> str:
        """`.dymo` (DYMO Connect) con el número solo en la mitad izquierda."""
        f = obtener_formato(label_format)
        m = MARGEN_SEGURO_MM
        c = caja_cable(f)
        ln = caja_linea_cable(f)
        negro = cls._color(1, 0, 0, 0)
        fuente = (f"<FontInfo><FontName>{FUENTE}</FontName><FontSize>{CABLE_FUENTE_PT:g}</FontSize><IsBold>True</IsBold>"
                  f"<IsItalic>False</IsItalic><IsUnderline>False</IsUnderline><FontBrush>{negro}</FontBrush></FontInfo>")
        return f"""<?xml version="1.0" encoding="utf-8"?>
<DesktopLabel Version="1">
  <DYMOLabel Version="3">
    <Description>TQT cable {f.codigo} {f.ancho_mm:g}x{f.alto_mm:g} mm</Description>
    <Orientation>Landscape</Orientation>
    <LabelName>{f.nombre_dcd}</LabelName>
    <InitialLength>0</InitialLength>
    <BorderStyle>SolidLine</BorderStyle>
    <DYMORect>
      <DYMOPoint><X>{_pulg(m)}</X><Y>{_pulg(m)}</Y></DYMOPoint>
      <Size><Width>{_pulg(f.ancho_mm - 2 * m)}</Width><Height>{_pulg(f.alto_mm - 2 * m)}</Height></Size>
    </DYMORect>
    <BorderColor>{negro}</BorderColor>
    <BorderThickness>1</BorderThickness>
    <Show_Border>False</Show_Border>
    <DynamicLayoutManager>
      <RotationBehavior>ClearObjects</RotationBehavior>
      <LabelObjects>
        <TextObject>
          <Name>NUMERO</Name>
          {cls._brushes()}
          <Rotation>Rotation90</Rotation>
          <OutlineThickness>1</OutlineThickness>
          <IsOutlined>False</IsOutlined>
          <BorderStyle>SolidLine</BorderStyle>
          <Margin><DYMOThickness Left="0" Top="0" Right="0" Bottom="0" /></Margin>
          <HorizontalAlignment>Center</HorizontalAlignment>
          <VerticalAlignment>Middle</VerticalAlignment>
          <FitMode>AlwaysFit</FitMode>
          <IsVertical>False</IsVertical>
          <FormattedText>
            <FitMode>AlwaysFit</FitMode>
            <HorizontalAlignment>Center</HorizontalAlignment>
            <VerticalAlignment>Middle</VerticalAlignment>
            <IsVertical>False</IsVertical>
            {"".join(f"<LineTextSpan><TextSpan><Text>{xml_escape(t)}</Text>{fuente}</TextSpan></LineTextSpan>" for t in lineas_cable(numero, r3))}
          </FormattedText>
          <ObjectLayout><DYMOPoint><X>{_pulg(c.x)}</X><Y>{_pulg(c.y)}</Y></DYMOPoint><Size><Width>{_pulg(c.w)}</Width><Height>{_pulg(c.h)}</Height></Size></ObjectLayout>
        </TextObject>
        <ImageObject>
          <Name>LINEA</Name>
          {cls._brushes()}
          <Rotation>Rotation0</Rotation>
          <OutlineThickness>1</OutlineThickness>
          <IsOutlined>False</IsOutlined>
          <BorderStyle>SolidLine</BorderStyle>
          <Margin><DYMOThickness Left="0" Top="0" Right="0" Bottom="0" /></Margin>
          <Data>{png_linea_punteada(ln)}</Data>
          <ScaleMode>Fill</ScaleMode>
          <HorizontalAlignment>Center</HorizontalAlignment>
          <VerticalAlignment>Middle</VerticalAlignment>
          <ObjectLayout><DYMOPoint><X>{_pulg(ln.x)}</X><Y>{_pulg(ln.y)}</Y></DYMOPoint><Size><Width>{_pulg(ln.w)}</Width><Height>{_pulg(ln.h)}</Height></Size></ObjectLayout>
        </ImageObject>
      </LabelObjects>
    </DynamicLayoutManager>
  </DYMOLabel>
  <LabelApplication>Blank</LabelApplication>
  <DataTable>
    <Columns></Columns>
    <Rows></Rows>
  </DataTable>
</DesktopLabel>"""

    @classmethod
    def archivo_cable(cls, numero: str, label_format: Optional[str] = None, tipo: str = "dymo", r3: str = "") -> Tuple[bytes, str]:
        base = f"TQT_cable_{numero.replace('/', '-')}" + (f"_R3_{r3}" if r3 else "")
        if tipo == "label":
            return cls.generate_cable_label_xml(numero, label_format, r3).encode("utf-8"), f"{base}.label"
        return b"\xef\xbb\xbf" + cls.generate_cable_dcd_xml(numero, label_format, r3).encode("utf-8"), f"{base}.dymo"

    # ------------------------------------------------------------------ activo (v1.4.14, simplificada en v1.4.16)
    # Solo «ACT 0001» y el QR con la URL del activo. Mismo formato y reglas que la etiqueta de tarjeta (QR a la izquierda con
    # módulos exactos a 300 dpi, todo dentro de la zona segura); sin nombre ni otras líneas, así que el QR y el código crecen
    # hasta donde caben: el módulo más grande (hasta ACTIVO_MAX_PUNTOS) que aún deja al código en >= ACTIVO_MIN_CODIGO_PT.
    @classmethod
    def diseno_activo(cls, url: str, etiqueta: str, label_format: Optional[str] = None):
        """(Diseno, caja del código centrada en vertical, pt del código) de la etiqueta de un activo."""
        f = obtener_formato(label_format)
        modulos = len(matriz_qr(url))
        m = MARGEN_SEGURO_MM
        seguro = Caja(m, m, f.ancho_mm - 2 * m, f.alto_mm - 2 * m)
        avance = max(len(etiqueta), 1) * FUENTE_AVANCE_EM * PT_A_MM   # mm de ancho por cada pt de fuente

        def medidas(ppm: int):
            lado = (modulos + 2 * SILENCIO_MODULOS) * ppm / DOTS_PER_MM
            ancho = seguro.derecha - (seguro.x + lado + SEPARACION_MM)
            return lado, ancho, min(ACTIVO_CODIGO_PT, ancho / avance)

        ppm = ACTIVO_MAX_PUNTOS
        while ppm > 4 and (medidas(ppm)[0] > seguro.h + 1e-9 or medidas(ppm)[2] < ACTIVO_MIN_CODIGO_PT):
            ppm -= 1
        lado, ancho, pt = medidas(ppm)
        if lado > seguro.h + 1e-9 or ancho <= 0:
            raise ValueError(f"El QR ({lado:.1f} mm) no cabe en la zona segura de {f.codigo}.")
        pt = max(MIN_FUENTE_PT, pt)
        qr = Caja(seguro.x, seguro.y + (seguro.h - lado) / 2, lado, lado)
        alto = pt * INTERLINEADO * PT_A_MM
        texto = Caja(qr.derecha + SEPARACION_MM, seguro.y + (seguro.h - alto) / 2, ancho, alto)
        return Diseno(f, seguro, qr, modulos, ppm, texto, pt, 1), texto, pt

    @classmethod
    def generate_activo_xml(cls, url: str, etiqueta: str, label_format: Optional[str] = None) -> str:
        """`.label` (DYMO Label v8) del activo: objetos `QR` (imagen 1 bit) y `TEXTO` («ACT 0001»)."""
        d, c_cod, pt = cls.diseno_activo(url, etiqueta, label_format)
        f = d.formato
        objetos = (_v8_imagen("QR", cls.generate_qr_base64(url, box_size=d.puntos_por_modulo), d.qr)
                   + _v8_texto("TEXTO", etiqueta, round(pt, 1), c_cod))
        return f"""<?xml version="1.0" encoding="utf-8"?>
<DieCutLabel Version="8.0" Units="twips">
    <PaperOrientation>{f.v8_orientacion}</PaperOrientation>
    <Id>{f.paper_id}</Id>
    <PaperName>{f.paper_name}</PaperName>
    <DrawCommands>
        <RoundRectangle X="0" Y="0" Width="{f.v8_ancho or f.twips_alto}" Height="{f.v8_alto or f.twips_ancho}" Rx="270" Ry="270" />
    </DrawCommands>
{objetos}</DieCutLabel>"""

    @classmethod
    def generate_activo_dcd_xml(cls, url: str, etiqueta: str, label_format: Optional[str] = None) -> str:
        """`.dymo` (DYMO Connect) del activo, para `dymo.label.framework.openLabelXml`: `QR` (BarcodeObject con la URL)
        y `TEXTO` («ACT 0001», grande y centrado en vertical)."""
        d, c_cod, pt = cls.diseno_activo(url, etiqueta, label_format)
        f, seg = d.formato, d.zona_segura
        negro = cls._color(1, 0, 0, 0)
        margen = '<Margin><DYMOThickness Left="0" Top="0" Right="0" Bottom="0" /></Margin>'

        def layout(c: Caja) -> str:
            return (f"<ObjectLayout><DYMOPoint><X>{_pulg(c.x)}</X><Y>{_pulg(c.y)}</Y></DYMOPoint>"
                    f"<Size><Width>{_pulg(c.w)}</Width><Height>{_pulg(c.h)}</Height></Size></ObjectLayout>")

        fuente = (f"<FontInfo><FontName>{FUENTE}</FontName><FontSize>{round(pt, 1):g}</FontSize><IsBold>True</IsBold>"
                  f"<IsItalic>False</IsItalic><IsUnderline>False</IsUnderline><FontBrush>{negro}</FontBrush></FontInfo>")
        return f"""<?xml version="1.0" encoding="utf-8"?>
<DesktopLabel Version="1">
  <DYMOLabel Version="3">
    <Description>TQT activo {f.codigo} {f.ancho_mm:g}x{f.alto_mm:g} mm</Description>
    <Orientation>Landscape</Orientation>
    <LabelName>{f.nombre_dcd}</LabelName>
    <InitialLength>0</InitialLength>
    <BorderStyle>SolidLine</BorderStyle>
    <DYMORect>
      <DYMOPoint><X>{_pulg(seg.x)}</X><Y>{_pulg(seg.y)}</Y></DYMOPoint>
      <Size><Width>{_pulg(seg.w)}</Width><Height>{_pulg(seg.h)}</Height></Size>
    </DYMORect>
    <BorderColor>{negro}</BorderColor>
    <BorderThickness>1</BorderThickness>
    <Show_Border>False</Show_Border>
    <DynamicLayoutManager>
      <RotationBehavior>ClearObjects</RotationBehavior>
      <LabelObjects>
        <BarcodeObject>
          <Name>QR</Name>
          {cls._brushes()}
          <Rotation>Rotation0</Rotation>
          <OutlineThickness>1</OutlineThickness>
          <IsOutlined>False</IsOutlined>
          <BorderStyle>SolidLine</BorderStyle>
          {margen}
          <BarcodeFormat>QRCode</BarcodeFormat>
          <Data>
            <MultiDataString>
              <DataString>{xml_escape(url)}</DataString>
            </MultiDataString>
          </Data>
          <HorizontalAlignment>Center</HorizontalAlignment>
          <VerticalAlignment>Middle</VerticalAlignment>
          <Size>Medium</Size>
          <TextPosition>None</TextPosition>
          <FontInfo><FontName>{FUENTE}</FontName><FontSize>8</FontSize><IsBold>False</IsBold><IsItalic>False</IsItalic><IsUnderline>False</IsUnderline><FontBrush>{negro}</FontBrush></FontInfo>
          {layout(d.qr)}
        </BarcodeObject>
        <TextObject>
          <Name>TEXTO</Name>
          {cls._brushes()}
          <Rotation>Rotation0</Rotation>
          <OutlineThickness>1</OutlineThickness>
          <IsOutlined>False</IsOutlined>
          <BorderStyle>SolidLine</BorderStyle>
          {margen}
          <HorizontalAlignment>Left</HorizontalAlignment>
          <VerticalAlignment>Middle</VerticalAlignment>
          <FitMode>AlwaysFit</FitMode>
          <IsVertical>False</IsVertical>
          <FormattedText>
            <FitMode>AlwaysFit</FitMode>
            <HorizontalAlignment>Left</HorizontalAlignment>
            <VerticalAlignment>Middle</VerticalAlignment>
            <IsVertical>False</IsVertical>
            <LineTextSpan><TextSpan><Text>{xml_escape(etiqueta)}</Text>{fuente}</TextSpan></LineTextSpan>
          </FormattedText>
          {layout(c_cod)}
        </TextObject>
      </LabelObjects>
    </DynamicLayoutManager>
  </DYMOLabel>
  <LabelApplication>Blank</LabelApplication>
  <DataTable>
    <Columns></Columns>
    <Rows></Rows>
  </DataTable>
</DesktopLabel>"""

    @classmethod
    def generate_activo_svg(cls, url: str, etiqueta: str, label_format: Optional[str] = None, borde: bool = False) -> str:
        """SVG a escala real (1 unidad = 1 mm) de la etiqueta del activo: vista previa e impresión del navegador / DYMO compartida."""
        d, c_cod, pt = cls.diseno_activo(url, etiqueta, label_format)
        f = d.formato
        mod = d.puntos_por_modulo / DOTS_PER_MM
        x0, y0 = d.qr.x + SILENCIO_MODULOS * mod, d.qr.y + SILENCIO_MODULOS * mod
        celdas = "".join(f'<rect x="{x0 + c * mod:.4f}" y="{y0 + r * mod:.4f}" width="{mod:.4f}" height="{mod:.4f}"/>'
                         for r, fila in enumerate(matriz_qr(url)) for c, v in enumerate(fila) if v)
        marco = (f'<rect width="{f.ancho_mm:g}" height="{f.alto_mm:g}" rx="2.5" fill="#fff" stroke="#000" stroke-width="0.2"/>' if borde
                 else f'<rect width="{f.ancho_mm:g}" height="{f.alto_mm:g}" fill="#fff"/>')
        texto = (f'<text x="{c_cod.x:.3f}" y="{c_cod.y + c_cod.h / 2:.3f}" dominant-baseline="central" '
                 f'font-size="{pt * PT_A_MM:.4f}">{xml_escape(etiqueta)}</text>')
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{f.ancho_mm:g}mm" height="{f.alto_mm:g}mm" viewBox="0 0 {f.ancho_mm:g} {f.alto_mm:g}">'
                f'{marco}<g fill="#000" shape-rendering="crispEdges">{celdas}</g>'
                f'<g fill="#000" font-family="{FUENTE_SVG}" font-weight="700">{texto}</g></svg>')

    @classmethod
    def archivo_activo(cls, url: str, etiqueta: str, label_format: Optional[str] = None, tipo: str = "dymo") -> Tuple[bytes, str]:
        """(bytes, nombre) del archivo `.dymo`/`.label` del activo; el nombre es el código sin espacios («ACT-0001.dymo»)."""
        base = etiqueta.replace(" ", "-")
        if tipo == "label":
            return cls.generate_activo_xml(url, etiqueta, label_format).encode("utf-8"), f"{base}.label"
        return b"\xef\xbb\xbf" + cls.generate_activo_dcd_xml(url, etiqueta, label_format).encode("utf-8"), f"{base}.dymo"

    # ------------------------------------------------------------------ paquete de datos
    @classmethod
    def get_label_details(cls, tarjeta: Dict[str, Any], label_format: Optional[str] = None) -> Dict[str, Any]:
        """Datos de etiqueta, validación, QR y XML (DCD y v8) listos para consumo."""
        formato = obtener_formato(label_format)
        estado, motivos, advertencias = cls.estado_etiqueta(tarjeta)
        is_ready = estado == "FINAL"
        qr_text = cls.format_qr_payload(tarjeta)
        lineas = cls.trama_lineas(tarjeta)
        d = cls.diseno(tarjeta, formato.codigo)
        return {
            "tarjeta_id": tarjeta.get("id"),
            "id_tarjeta_num": tarjeta.get("id_tarjeta_num"),
            "label_format": formato.codigo,
            "is_ready_to_print": is_ready,            # FINAL (regla del Excel)
            "estado_etiqueta": estado,                # INCOMPLETA | IDENTIFICACION | FINAL
            "imprimible": estado in ("IDENTIFICACION", "FINAL"),
            "sin_mac": [r for r, l in (("R1", lineas[1]), ("R2", lineas[3])) if tarjeta.get(f"nombre_{r.lower()}") and not l],
            "advertencias": advertencias,
            "status_message": "LISTA PARA IMPRIMIR" if is_ready else "REVISAR PCB/MAC",
            "validation_reasons": motivos,
            "trama_lineas": lineas,
            "nombre_r1": tarjeta.get("nombre_r1"),
            "mac_r1": tarjeta.get("mac_r1"),
            "nombre_r2": tarjeta.get("nombre_r2"),
            "mac_r2": tarjeta.get("mac_r2"),
            "semana_produccion": tarjeta.get("semana_produccion"),
            "qr_payload": qr_text,
            "qr_version": version_qr(qr_text),
            "qr_image_base64": f"data:image/png;base64,{cls.generate_qr_base64(qr_text)}",
            "label_text": cls.format_label_text(tarjeta),
            "dymo_xml": cls.generate_dymo_xml(tarjeta, formato.codigo),   # .label v8 (DYMO Label)
            "dcd_xml": cls.generate_dcd_xml(tarjeta, formato.codigo),     # .dymo (DYMO Connect; para openLabelXml)
            "geometria_mm": {
                "etiqueta": [formato.ancho_mm, formato.alto_mm],
                "zona_segura": [d.zona_segura.x, d.zona_segura.y, d.zona_segura.w, d.zona_segura.h],
                "qr": [round(d.qr.x, 3), round(d.qr.y, 3), round(d.qr.w, 3), round(d.qr.h, 3)],
                "texto": [round(d.texto.x, 3), round(d.texto.y, 3), round(d.texto.w, 3), round(d.texto.h, 3)],
                "puntos_por_modulo": d.puntos_por_modulo,
            },
            "dymo_connect": {
                "service_url_https": DYMO_WS_HTTPS_URL,
                "service_url_http": DYMO_WS_HTTP_URL,
                "print_endpoint": f"{DYMO_WS_HTTPS_URL}/PrintLabel",
                "printer_name": "DYMO LabelWriter 550",
                "print_params_xml": "<LabelWriterPrintParams><Copies>1</Copies><JobTitle>TQT Label</JobTitle><FlowDirection>LeftToRight</FlowDirection><PrintQuality>BarcodeAndGraphics</PrintQuality></LabelWriterPrintParams>",
            },
        }

    # ------------------------------------------------------------------ vistas previas a escala real
    @classmethod
    def generate_svg_preview(cls, tarjeta: Dict[str, Any], label_format: Optional[str] = None, guia: bool = True,
                             aprobada: bool = False, borde: bool = True) -> str:
        """SVG a escala real (1 unidad = 1 mm): módulos del QR como rectángulos (bordes nítidos, sin PNG), 4 líneas de
        texto y, con `guia`, la zona segura de 3 mm en línea punteada. v1.4.2: `borde=False` para imprimir (sin contorno)."""
        d = cls.diseno(tarjeta, label_format)
        f = d.formato
        matriz = matriz_qr(cls.format_qr_payload(tarjeta))
        mod = d.puntos_por_modulo / DOTS_PER_MM
        x0 = d.qr.x + SILENCIO_MODULOS * mod
        y0 = d.qr.y + SILENCIO_MODULOS * mod
        celdas = "".join(f'<rect x="{x0 + c * mod:.4f}" y="{y0 + r * mod:.4f}" width="{mod:.4f}" height="{mod:.4f}"/>'
                         for r, fila in enumerate(matriz) for c, v in enumerate(fila) if v)
        pt_mm = d.fuente_pt * PT_A_MM
        paso = pt_mm * INTERLINEADO
        lin_txt = cls.lineas_texto(tarjeta, aprobada)
        alto = paso * len(lin_txt)
        y_inicio = d.texto.y + (d.texto.h - alto) / 2 + paso * 0.8
        texto = "".join(
            f'<text x="{d.texto.x:.3f}" y="{y_inicio + i * paso:.3f}">{xml_escape(l) or "&#160;"}</text>'
            for i, l in enumerate(lin_txt))
        s = d.zona_segura
        guia_svg = (f'<rect x="{s.x}" y="{s.y}" width="{s.w}" height="{s.h}" fill="none" stroke="#000" stroke-width="0.15" '
                    f'stroke-dasharray="1 1" class="guia"/>') if guia else ""
        marco = (f'<rect width="{f.ancho_mm:g}" height="{f.alto_mm:g}" rx="2.5" fill="#fff" stroke="#000" stroke-width="0.2"/>' if borde
                 else f'<rect width="{f.ancho_mm:g}" height="{f.alto_mm:g}" fill="#fff"/>')
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{f.ancho_mm:g}mm" height="{f.alto_mm:g}mm" '
                f'viewBox="0 0 {f.ancho_mm:g} {f.alto_mm:g}">'
                f'{marco}'
                f'<g fill="#000" shape-rendering="crispEdges">{celdas}</g>'
                f'<g fill="#000" font-family="{FUENTE_SVG}" font-weight="700" font-size="{pt_mm:.4f}">{texto}</g>'
                f'{guia_svg}</svg>')

    @classmethod
    def generate_html_preview(cls, tarjeta: Dict[str, Any], label_format: Optional[str] = None) -> str:
        """Página de vista previa e impresión a escala real (57:32 para el 30334) con la zona segura punteada."""
        details = cls.get_label_details(tarjeta, label_format)
        f = obtener_formato(label_format)
        svg = cls.generate_svg_preview(tarjeta, label_format, guia=False)
        s = cls.diseno(tarjeta, label_format).zona_segura
        badge = {"FINAL": "LISTA PARA IMPRIMIR", "IDENTIFICACION": "SOLO IDENTIFICACIÓN · REVISAR PCB/MAC",
                 "INCOMPLETA": "TARJETA INCOMPLETA"}.get(details["estado_etiqueta"], details["status_message"])
        badge_class = "ready" if details["is_ready_to_print"] else "warning"
        motivos = ""
        if details["validation_reasons"]:
            motivos = "<ul class='alerts'>" + "".join(f"<li>{html.escape(r)}</li>" for r in details["validation_reasons"]) + "</ul>"
        num = html.escape(str(details["id_tarjeta_num"]))
        return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Etiqueta DYMO {f.codigo} · Tarjeta {num}</title>
<style>
  :root {{ color-scheme: light; }}
  body {{ font-family: "Segoe UI", Arial, sans-serif; background: #eef0f3; margin: 0; padding: 24px; display: flex; flex-direction: column; align-items: center; gap: 16px; }}
  h1 {{ font-size: 16px; margin: 0; }}
  .badge {{ padding: 6px 14px; border-radius: 4px; font-weight: 700; font-size: 13px; }}
  .badge.ready {{ background: #d7f3e3; color: #0b6b3a; border: 1px solid #7fd3a5; }}
  .badge.warning {{ background: #fde2e2; color: #9a1b1b; border: 1px solid #f3a3a3; }}
  .alerts {{ margin: 0; padding: 8px 8px 8px 28px; background: #fff4f4; border-left: 4px solid #d9534f; font-size: 13px; color: #7a1c1c; max-width: 420px; }}
  .escala {{ position: relative; width: {f.ancho_mm:g}mm; height: {f.alto_mm:g}mm; background: #fff; box-shadow: 0 2px 10px rgba(0,0,0,.15); }}
  .escala svg {{ display: block; }}
  .guia {{ position: absolute; left: {s.x:g}mm; top: {s.y:g}mm; width: {s.w:g}mm; height: {s.h:g}mm; border: 1px dashed #000; box-sizing: border-box; pointer-events: none; }}
  .acciones {{ display: flex; gap: 10px; flex-wrap: wrap; justify-content: center; }}
  button {{ padding: 10px 16px; font-size: 14px; font-weight: 600; border: 0; border-radius: 4px; cursor: pointer; background: #1d3b6b; color: #fff; }}
  button.sec {{ background: #d9dde3; color: #1b2433; }}
  @media print {{
    @page {{ size: {f.ancho_mm:g}mm {f.alto_mm:g}mm; margin: 0; }}
    body {{ background: none; padding: 0; display: block; }}
    h1, .badge, .alerts, .acciones, .guia {{ display: none !important; }}
    .escala {{ box-shadow: none; }}
  }}
</style>
</head>
<body>
  <h1>DYMO LabelWriter 550 · {f.codigo} ({f.ancho_mm:g} x {f.alto_mm:g} mm) · Tarjeta {num}</h1>
  <span class="badge {badge_class}">{html.escape(badge)}</span>
  {motivos}
  <div class="escala" id="dymoLabel">{svg}<div class="guia" title="Zona segura de {MARGEN_SEGURO_MM:g} mm"></div></div>
  <div class="acciones">
    <button onclick="window.print()">Imprimir desde el navegador</button>
    <a href="/api/dymo/label/{details['tarjeta_id']}/archivo?label_format={f.codigo}"><button class="sec" type="button">Descargar .dymo (DYMO Connect)</button></a>
  </div>
</body>
</html>"""

    # ------------------------------------------------------------------ lote
    @classmethod
    def get_batch_labels(
        cls,
        lote_id: Optional[int] = None,
        only_ready: bool = True,
        label_format: Optional[str] = None,
        modo: Optional[str] = None,
        ids: Optional[List[int]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Etiquetas de las tarjetas del lote (o del activo). `modo`:
          final          -> solo estado FINAL ('LISTA PARA IMPRIMIR'); es el comportamiento de only_ready=True.
          identificacion -> FINAL + IDENTIFICACION (R1 y R2 asignadas, aunque falten MAC o pruebas).
          todas          -> también las INCOMPLETAS (only_ready=False).
        Con `ids` (ids de tarjeta) solo esas, sin filtrar por estado.
        """
        modo = (modo or ("final" if only_ready else "todas")).lower()
        if modo not in ("final", "identificacion", "todas"):
            raise ValueError("modo debe ser final, identificacion o todas")
        obtener_formato(label_format)
        if ids:
            cards = [t for t in (db.get_tarjeta_by_id(i) for i in ids) if t]
            modo = "todas"
        else:
            cards, _ = db.list_tarjetas(lote_id=lote_id, limit=500)
        results: List[Dict[str, Any]] = []
        for card in cards:
            details = cls.get_label_details(card, label_format=label_format)
            if modo == "final" and details["estado_etiqueta"] != "FINAL":
                continue
            if modo == "identificacion" and not details["imprimible"]:
                continue
            results.append(details)
        return results
