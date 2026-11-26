"""Etiqueta DYMO 30334 (57 x 32 mm) del GABINETE de una tarjeta Skudo AntiJammer.

QR a la izquierda con el identificador exacto de la tarjeta (`SJ-V1-0052`: en AntiJammer cada QR es una tarjeta) y a la derecha
«SKUDO ANTIJAMMER», el identificador grande y, si existen, el lote y la fecha de recepción. Reutiliza la geometría y los
ayudantes de `dymo_service` (QR, zona segura, fuente) sin tocar el diseño de Escáner TQT ni el de Impresora.
Salidas: SVG a escala 1 unidad = 1 mm (vista previa, navegador y DYMO compartida) y `.dymo` (DYMO Connect local).
"""
from typing import Any, Dict, List, Optional, Tuple
from xml.sax.saxutils import escape as xml_escape

from app.database import db
from app.services import antijammer as aj
from app.services import dymo_service as ds
from app.services.dymo_service import Caja, DymoService

NOMBRE_MODULO = "SKUDO ANTIJAMMER"
PT_MARCA, PT_CODIGO_MAX, PT_DETALLE = 7.5, 18.0, 7.0
MAX_PUNTOS_QR = 9
CODIGO_MIN_PT = 12.0


def _fecha_corta(valor: Optional[str]) -> str:
    """'2026-11-04 10:15:00' -> '04/11/2026' (vacío si no hay fecha)."""
    s = (valor or "").strip()[:10]
    p = s.split("-")
    return f"{p[2]}/{p[1]}/{p[0]}" if len(p) == 3 and all(p) else ""


def datos_de(nombre: str) -> Dict[str, Any]:
    """Datos de la etiqueta de una placa registrada; NoEncontrada si el código no es AntiJammer o no existe."""
    n = aj._nombre_de_codigo(nombre)
    if not n:
        raise aj.NoEncontrada(f"'{(nombre or '')[:40]}' no corresponde a una placa Skudo AntiJammer.")
    aj._asegurar()
    with db.get_db() as c:
        r = c.execute("SELECT id, nombre, lote, recibida_en FROM antijammer_pcb WHERE nombre = ?", (n,)).fetchone()
        tipo = ""
        if r:
            try:   # RX/TX se asigna en Materiales (costeo_pcb_tarjeta); sin asignar o sin la tabla, no se muestra
                t = c.execute("SELECT tarjeta FROM costeo_pcb_tarjeta WHERE modulo='skudo-antijammer' AND pcb_id=?", (r["id"],)).fetchone()
                tipo = (t["tarjeta"] if t else "") or ""
            except Exception:
                tipo = ""
    if not r:
        raise aj.NoEncontrada(f"{n} no está registrada.")
    return {"nombre": r["nombre"], "tipo": tipo, "lote": r["lote"] or "", "fecha": _fecha_corta(r["recibida_en"])}


def _recorta(texto: str, pt: float, ancho: float) -> str:
    """Corta con «…» lo que no cabe en `ancho` mm a `pt` puntos (fuente monoespaciada)."""
    cabe = max(int(ancho / (ds.FUENTE_AVANCE_EM * pt * ds.PT_A_MM)), 1)
    return texto if len(texto) <= cabe else texto[:max(cabe - 1, 1)] + "…"


def diseno(datos: Dict[str, Any], label_format: Optional[str] = None) -> Tuple[Any, Caja, int, int, List[Tuple[str, Caja, float, bool]]]:
    """(formato, caja del QR, módulos, puntos por módulo, [(texto, caja, pt, negrita)]) de la etiqueta."""
    f = ds.obtener_formato(label_format)
    codigo = datos["nombre"]
    modulos = len(ds.matriz_qr(codigo))
    m = ds.MARGEN_SEGURO_MM
    seguro = Caja(m, m, f.ancho_mm - 2 * m, f.alto_mm - 2 * m)
    unidad = ds.FUENTE_AVANCE_EM * ds.PT_A_MM   # mm por pt y por carácter

    def lado(ppm: int) -> float:
        return (modulos + 2 * ds.SILENCIO_MODULOS) * ppm / ds.DOTS_PER_MM

    ppm = MAX_PUNTOS_QR
    while ppm > 4 and (lado(ppm) > seguro.h + 1e-9 or seguro.derecha - (seguro.x + lado(ppm) + ds.SEPARACION_MM) < len(codigo) * CODIGO_MIN_PT * unidad):
        ppm -= 1
    lq = lado(ppm)
    qr = Caja(seguro.x, seguro.y + (seguro.h - lq) / 2, lq, lq)
    x = qr.derecha + ds.SEPARACION_MM
    ancho = seguro.derecha - x
    if lq > seguro.h + 1e-9 or ancho <= 0:
        raise ValueError(f"El QR no cabe en la zona segura de {f.codigo}.")
    pt_cod = max(ds.MIN_FUENTE_PT, min(PT_CODIGO_MAX, ancho / (max(len(codigo), 1) * unidad)))
    marca = f"{NOMBRE_MODULO} {datos['tipo']}" if datos.get("tipo") else NOMBRE_MODULO
    filas = [(marca, PT_MARCA, True), (codigo, pt_cod, True)]
    for t in (f"Lote {datos['lote']}" if datos.get("lote") else "", datos.get("fecha") or ""):
        if t:
            filas.append((t, PT_DETALLE, False))
    filas = [(_recorta(t, pt, ancho), pt, b) for t, pt, b in filas]
    total = sum(pt * ds.INTERLINEADO * ds.PT_A_MM for _, pt, _ in filas)
    y = seguro.y + (seguro.h - total) / 2
    lineas = []
    for t, pt, b in filas:
        alto = pt * ds.INTERLINEADO * ds.PT_A_MM
        lineas.append((t, Caja(x, y, ancho, alto), pt, b))
        y += alto
    return f, qr, modulos, ppm, lineas


def svg(datos: Dict[str, Any], label_format: Optional[str] = None, borde: bool = False) -> str:
    """SVG a escala real (1 unidad = 1 mm)."""
    f, qr, _mod, ppm, lineas = diseno(datos, label_format)
    mod = ppm / ds.DOTS_PER_MM
    x0, y0 = qr.x + ds.SILENCIO_MODULOS * mod, qr.y + ds.SILENCIO_MODULOS * mod
    celdas = "".join(f'<rect x="{x0 + c * mod:.4f}" y="{y0 + r * mod:.4f}" width="{mod:.4f}" height="{mod:.4f}"/>'
                     for r, fila in enumerate(ds.matriz_qr(datos["nombre"])) for c, v in enumerate(fila) if v)
    marco = (f'<rect width="{f.ancho_mm:g}" height="{f.alto_mm:g}" rx="2.5" fill="#fff" stroke="#000" stroke-width="0.2"/>' if borde
             else f'<rect width="{f.ancho_mm:g}" height="{f.alto_mm:g}" fill="#fff"/>')
    peso = {True: ' font-weight="700"', False: ""}
    texto = "".join(f'<text x="{c.x:.3f}" y="{c.y + c.h / 2:.3f}" dominant-baseline="central" font-size="{pt * ds.PT_A_MM:.4f}"'
                    f'{peso[b]}>{xml_escape(t)}</text>' for t, c, pt, b in lineas)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{f.ancho_mm:g}mm" height="{f.alto_mm:g}mm" viewBox="0 0 {f.ancho_mm:g} {f.alto_mm:g}">'
            f'{marco}<g fill="#000" shape-rendering="crispEdges">{celdas}</g>'
            f'<g fill="#000" font-family="{ds.FUENTE_SVG}">{texto}</g></svg>')


def dymo_xml(datos: Dict[str, Any], label_format: Optional[str] = None) -> str:
    """`.dymo` (DYMO Connect) para `openLabelXml`: BarcodeObject QR + un TextObject por línea."""
    f, qr, _mod, _ppm, lineas = diseno(datos, label_format)
    seg = Caja(ds.MARGEN_SEGURO_MM, ds.MARGEN_SEGURO_MM, f.ancho_mm - 2 * ds.MARGEN_SEGURO_MM, f.alto_mm - 2 * ds.MARGEN_SEGURO_MM)
    negro = DymoService._color(1, 0, 0, 0)
    margen = '<Margin><DYMOThickness Left="0" Top="0" Right="0" Bottom="0" /></Margin>'
    pul = ds._pulg

    def layout(c: Caja) -> str:
        return (f"<ObjectLayout><DYMOPoint><X>{pul(c.x)}</X><Y>{pul(c.y)}</Y></DYMOPoint>"
                f"<Size><Width>{pul(c.w)}</Width><Height>{pul(c.h)}</Height></Size></ObjectLayout>")

    def texto(i: int, valor: str, pt: float, c: Caja, negrita: bool) -> str:
        fuente = (f"<FontInfo><FontName>{ds.FUENTE}</FontName><FontSize>{round(pt, 1):g}</FontSize><IsBold>{negrita}</IsBold>"
                  f"<IsItalic>False</IsItalic><IsUnderline>False</IsUnderline><FontBrush>{negro}</FontBrush></FontInfo>")
        return f"""        <TextObject>
          <Name>TEXTO{i}</Name>
          {DymoService._brushes()}
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
            <LineTextSpan><TextSpan><Text>{xml_escape(valor)}</Text>{fuente}</TextSpan></LineTextSpan>
          </FormattedText>
          {layout(c)}
        </TextObject>
"""

    textos = "".join(texto(i + 1, t, pt, c, b) for i, (t, c, pt, b) in enumerate(lineas))
    return f"""<?xml version="1.0" encoding="utf-8"?>
<DesktopLabel Version="1">
  <DYMOLabel Version="3">
    <Description>Skudo AntiJammer {datos['nombre']} {f.ancho_mm:g}x{f.alto_mm:g} mm</Description>
    <Orientation>Landscape</Orientation>
    <LabelName>{f.nombre_dcd}</LabelName>
    <InitialLength>0</InitialLength>
    <BorderStyle>SolidLine</BorderStyle>
    <DYMORect>
      <DYMOPoint><X>{pul(seg.x)}</X><Y>{pul(seg.y)}</Y></DYMOPoint>
      <Size><Width>{pul(seg.w)}</Width><Height>{pul(seg.h)}</Height></Size>
    </DYMORect>
    <BorderColor>{negro}</BorderColor>
    <BorderThickness>1</BorderThickness>
    <Show_Border>False</Show_Border>
    <DynamicLayoutManager>
      <RotationBehavior>ClearObjects</RotationBehavior>
      <LabelObjects>
        <BarcodeObject>
          <Name>QR</Name>
          {DymoService._brushes()}
          <Rotation>Rotation0</Rotation>
          <OutlineThickness>1</OutlineThickness>
          <IsOutlined>False</IsOutlined>
          <BorderStyle>SolidLine</BorderStyle>
          {margen}
          <BarcodeFormat>QRCode</BarcodeFormat>
          <Data>
            <MultiDataString>
              <DataString>{xml_escape(datos['nombre'])}</DataString>
            </MultiDataString>
          </Data>
          <HorizontalAlignment>Center</HorizontalAlignment>
          <VerticalAlignment>Middle</VerticalAlignment>
          <Size>Medium</Size>
          <TextPosition>None</TextPosition>
          <FontInfo><FontName>{ds.FUENTE}</FontName><FontSize>8</FontSize><IsBold>False</IsBold><IsItalic>False</IsItalic><IsUnderline>False</IsUnderline><FontBrush>{negro}</FontBrush></FontInfo>
          {layout(qr)}
        </BarcodeObject>
{textos}      </LabelObjects>
    </DynamicLayoutManager>
  </DYMOLabel>
  <LabelApplication>Blank</LabelApplication>
  <DataTable>
    <Columns></Columns>
    <Rows></Rows>
  </DataTable>
</DesktopLabel>"""
