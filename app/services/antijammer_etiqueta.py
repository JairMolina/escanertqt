"""Etiqueta DYMO 30334 (57 x 32 mm) del GABINETE de una tarjeta Skudo AntiJammer (v1.4.104).

v1.4.106: QR a la izquierda con el nombre de la placa (en Consultar abre su ficha con la pareja, la compañera y el historial) y,
a la derecha, «SKUDO 8» y «RX» grande (antes «PAREJA 8», sin QR). Se imprime por pareja:
al pedir una placa se imprime también su compañera (ver `expandir`). Reutiliza la zona segura y la fuente de `dymo_service`.
Salidas: SVG a escala 1 unidad = 1 mm (vista previa, navegador y DYMO compartida) y `.dymo` (DYMO Connect local).
"""
from typing import Any, Dict, List, Optional, Tuple
from xml.sax.saxutils import escape as xml_escape

from app.database import db
from app.services import antijammer as aj
from app.services import antijammer_parejas as parejas
from app.services import dymo_service as ds
from app.services.dymo_service import Caja, DymoService

MARCA = "SKUDO"
PT_MARCA_MAX, PT_TIPO_MAX, MARCA_MIN_PT = 22.0, 48.0, 12.0
MAX_PUNTOS_QR = 11


def datos_de(nombre: str) -> Dict[str, Any]:
    """Datos de la etiqueta; NoEncontrada si no es AntiJammer o no existe, Invalida si aún no tiene número de pareja."""
    n = aj._nombre_de_codigo(nombre)
    if not n:
        raise aj.NoEncontrada(f"'{(nombre or '')[:40]}' no corresponde a una placa Skudo AntiJammer.")
    aj._asegurar()
    with db.get_db() as c:
        r = c.execute("SELECT id, nombre FROM antijammer_pcb WHERE nombre = ?", (n,)).fetchone()
    if not r:
        raise aj.NoEncontrada(f"{n} no está registrada.")
    par = parejas.de_placa(r["id"])
    if not par:
        raise aj.Invalida(f"{n} no tiene número de pareja: dáselo en Programar o en Emparejar.")
    return {"nombre": r["nombre"], "numero": par["numero"], "tipo": par["tipo"], "socio": par["socio"]}


def expandir(codigos: List[str]) -> List[str]:
    """Cada código seguido de su compañera de pareja (sin repetir): la etiqueta se imprime por pareja, RX primero."""
    out: List[str] = []
    for cod in codigos:
        n = aj._nombre_de_codigo(cod) or cod
        try:
            d = datos_de(n)
            grupo = [n, d["socio"]] if d["tipo"] == "RX" else [d["socio"], n]
        except aj.AntijammerError:
            grupo = [n]
        for x in grupo:
            if x and x not in out:
                out.append(x)
    return out


def diseno(datos: Dict[str, Any], label_format: Optional[str] = None) -> Tuple[Any, Caja, int, List[Tuple[str, Caja, float, bool]]]:
    """(formato, caja del QR, puntos por módulo, [(texto, caja, pt, negrita)]): QR a la izquierda con el nombre de la placa y,
    a la derecha, «SKUDO n» arriba y RX/TX grande abajo, centrados en su columna dentro de la zona segura."""
    f = ds.obtener_formato(label_format)
    m = ds.MARGEN_SEGURO_MM
    seguro = Caja(m, m, f.ancho_mm - 2 * m, f.alto_mm - 2 * m)
    unidad = ds.FUENTE_AVANCE_EM * ds.PT_A_MM   # mm por pt y por carácter
    modulos = len(ds.matriz_qr(datos["nombre"]))
    marca = f"{MARCA} {datos['numero']}"

    def lado(ppm: int) -> float:
        return (modulos + 2 * ds.SILENCIO_MODULOS) * ppm / ds.DOTS_PER_MM

    ppm = MAX_PUNTOS_QR
    while ppm > 4 and (lado(ppm) > seguro.h + 1e-9
                       or seguro.derecha - (seguro.x + lado(ppm) + ds.SEPARACION_MM) < len(marca) * MARCA_MIN_PT * unidad):
        ppm -= 1
    lq = lado(ppm)
    qr = Caja(seguro.x, seguro.y + (seguro.h - lq) / 2, lq, lq)
    x = qr.derecha + ds.SEPARACION_MM
    col = Caja(x, seguro.y, seguro.derecha - x, seguro.h)
    if lq > seguro.h + 1e-9 or col.w <= 0:
        raise ValueError(f"El QR no cabe en la zona segura de {f.codigo}.")
    alto = lambda pt: pt * ds.INTERLINEADO * ds.PT_A_MM   # noqa: E731
    filas = [(t, min(pt, col.w / (max(len(t), 1) * unidad))) for t, pt in ((marca, PT_MARCA_MAX), (datos["tipo"], PT_TIPO_MAX))]
    k = min(1.0, col.h / sum(alto(pt) for _, pt in filas))   # si no cabe en alto, se reduce todo
    filas = [(t, pt * k) for t, pt in filas]
    y = col.y + (col.h - sum(alto(pt) for _, pt in filas)) / 2
    lineas = []
    for t, pt in filas:
        lineas.append((t, Caja(col.x, y, col.w, alto(pt)), pt, True))
        y += alto(pt)
    return f, qr, ppm, lineas


def svg(datos: Dict[str, Any], label_format: Optional[str] = None, borde: bool = False) -> str:
    """SVG a escala real (1 unidad = 1 mm)."""
    f, qr, ppm, lineas = diseno(datos, label_format)
    mod = ppm / ds.DOTS_PER_MM
    x0, y0 = qr.x + ds.SILENCIO_MODULOS * mod, qr.y + ds.SILENCIO_MODULOS * mod
    celdas = "".join(f'<rect x="{x0 + c * mod:.4f}" y="{y0 + r * mod:.4f}" width="{mod:.4f}" height="{mod:.4f}"/>'
                     for r, fila in enumerate(ds.matriz_qr(datos["nombre"])) for c, v in enumerate(fila) if v)
    marco = (f'<rect width="{f.ancho_mm:g}" height="{f.alto_mm:g}" rx="2.5" fill="#fff" stroke="#000" stroke-width="0.2"/>' if borde
             else f'<rect width="{f.ancho_mm:g}" height="{f.alto_mm:g}" fill="#fff"/>')
    texto = "".join(f'<text x="{c.x + c.w / 2:.3f}" y="{c.y + c.h / 2:.3f}" text-anchor="middle" dominant-baseline="central" '
                    f'font-size="{pt * ds.PT_A_MM:.4f}" font-weight="700">{xml_escape(t)}</text>' for t, c, pt, _b in lineas)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{f.ancho_mm:g}mm" height="{f.alto_mm:g}mm" viewBox="0 0 {f.ancho_mm:g} {f.alto_mm:g}">'
            f'{marco}<g fill="#000" shape-rendering="crispEdges">{celdas}</g>'
            f'<g fill="#000" font-family="{ds.FUENTE_SVG}">{texto}</g></svg>')


def dymo_xml(datos: Dict[str, Any], label_format: Optional[str] = None) -> str:
    """`.dymo` (DYMO Connect) para `openLabelXml`: BarcodeObject QR (nombre de la placa) + un TextObject centrado por línea."""
    f, qr, _ppm, lineas = diseno(datos, label_format)
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
          <HorizontalAlignment>Center</HorizontalAlignment>
          <VerticalAlignment>Middle</VerticalAlignment>
          <FitMode>AlwaysFit</FitMode>
          <IsVertical>False</IsVertical>
          <FormattedText>
            <FitMode>AlwaysFit</FitMode>
            <HorizontalAlignment>Center</HorizontalAlignment>
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
    <Description>Skudo AntiJammer SKUDO {datos['numero']} {datos['tipo']} {datos['nombre']} {f.ancho_mm:g}x{f.alto_mm:g} mm</Description>
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
