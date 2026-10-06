"""Reporte de un día (v1.3.35): tarjetas COMPLETADAS (`fecha_finalizado`) y ENTREGADAS (`fecha_real`) en una fecha,
de todos los lotes, y su exportación a un Excel de fácil lectura (resumen + detalle con filtros)."""
import io
import re
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

from app.database import db
from app.database.models import MESES_ES

_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DIAS_ES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def _validar(fecha: str) -> date:
    if not _FECHA.match(fecha or ""):
        raise ValueError("Fecha no válida (AAAA-MM-DD).")
    return date.fromisoformat(fecha)


def tarjetas_del_dia(fecha: str, db_path: Optional[Path] = None) -> Dict[str, Any]:
    _validar(fecha)
    sql = """SELECT t.id, t.id_tarjeta_num, p1.nombre AS nombre_r1, p1.mac AS mac_r1, p2.nombre AS nombre_r2, p2.mac AS mac_r2,
                    p3.nombre AS nombre_r3, t.fecha_finalizado, t.fecha_real, t.gabinete, l.mes, l.anio
             FROM tarjetas_produccion t JOIN lotes_mensuales l ON l.id = t.lote_id
             LEFT JOIN pcb_inventario p1 ON p1.id = t.pcb_r1_id
             LEFT JOIN pcb_inventario p2 ON p2.id = t.pcb_r2_id
             LEFT JOIN pcb_inventario p3 ON p3.id = t.pcb_r3_id
             WHERE t.fecha_finalizado = ? OR t.fecha_real = ?
             ORDER BY l.anio, l.mes, t.id_tarjeta_num"""
    with db.get_db(db_path) as c:
        filas = [dict(r) for r in c.execute(sql, (fecha, fecha))]
    for f in filas:
        f["lote"] = f"{MESES_ES[f.pop('mes') - 1]} {f.pop('anio')}"
        f["completada"] = f["fecha_finalizado"] == fecha
        f["entregada"] = f["fecha_real"] == fecha
    return {"fecha": fecha, "completadas": sum(f["completada"] for f in filas), "entregadas": sum(f["entregada"] for f in filas), "items": filas}


# ---------------------------------------------------------------- Excel
AZUL, AZUL_CLARO, VERDE, VERDE_CLARO, GRIS, BORDE = "1F3A5F", "E8EEF6", "1E7B4F", "E6F4EC", "667085", "D0D7E2"
F = "Arial"


def _fecha_larga(d: date) -> str:
    return f"{DIAS_ES[d.weekday()].capitalize()} {d.day} de {MESES_ES[d.month - 1].lower()} de {d.year}"


def excel_del_dia(fecha: str, db_path: Optional[Path] = None) -> bytes:
    d = _validar(fecha)
    datos = tarjetas_del_dia(fecha, db_path)
    filas: List[Dict[str, Any]] = datos["items"]
    wb = Workbook()
    ws = wb.active
    ws.title = "Reporte del día"
    ws.sheet_view.showGridLines = False
    fino = Side(style="thin", color=BORDE)

    # Encabezado
    ws.merge_cells("A1:J1")
    ws["A1"] = "Escáner TQT · Reporte de tarjetas del día"
    ws["A1"].font = Font(name=F, size=16, bold=True, color="FFFFFF")
    ws["A1"].fill = PatternFill("solid", fgColor=AZUL)
    ws["A1"].alignment = Alignment(vertical="center", indent=1)
    ws.row_dimensions[1].height = 34
    ws.merge_cells("A2:J2")
    ws["A2"] = _fecha_larga(d)
    ws["A2"].font = Font(name=F, size=11, italic=True, color=GRIS)
    ws["A2"].alignment = Alignment(indent=1)

    # Tarjetas KPI (fórmulas: se recalculan si alguien edita el detalle)
    n = len(filas)
    ini, fin = 9, 9 + max(n, 1)   # rango de datos de la tabla (fila 8 = encabezados)
    kpis = [("B", "D", "Completadas", f'=COUNTIF(H{ini}:H{fin - 1},"Sí")', VERDE, VERDE_CLARO),
            ("E", "G", "Entregadas", f'=COUNTIF(I{ini}:I{fin - 1},"Sí")', AZUL, AZUL_CLARO),
            ("H", "J", "Tarjetas en el reporte", f"=COUNTA(A{ini}:A{fin - 1})", GRIS, "F2F4F7")]
    for c1, c2, titulo, formula, color, fondo in kpis:
        ws.merge_cells(f"{c1}4:{c2}4")
        ws.merge_cells(f"{c1}5:{c2}5")
        ws[f"{c1}4"] = titulo
        ws[f"{c1}4"].font = Font(name=F, size=10, bold=True, color=color)
        ws[f"{c1}5"] = formula if n else 0
        ws[f"{c1}5"].font = Font(name=F, size=24, bold=True, color=color)
        for fila in (4, 5):
            for col in range(ws[f"{c1}4"].column, ws[f"{c2}4"].column + 1):
                cel = ws.cell(row=fila, column=col)
                cel.fill = PatternFill("solid", fgColor=fondo)
                cel.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[5].height = 36

    ws["A7"] = "Detalle"
    ws["A7"].font = Font(name=F, size=12, bold=True, color=AZUL)
    cab = ["Tarjeta", "Lote", "R1", "MAC R1", "R2", "MAC R2", "R3", "Completada", "Entregada", "Gabinete"]
    for i, t in enumerate(cab, 1):
        c = ws.cell(row=8, column=i, value=t)
        c.font = Font(name=F, bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor=AZUL)
        c.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[8].height = 22
    for r, f in enumerate(filas, ini):
        valores = ["#" + str(f["id_tarjeta_num"]), f["lote"], f["nombre_r1"] or "—", f["mac_r1"] or "—", f["nombre_r2"] or "—", f["mac_r2"] or "—",
                   f["nombre_r3"] or "—", "Sí" if f["completada"] else "No", "Sí" if f["entregada"] else "No", f["gabinete"] or "—"]
        for i, v in enumerate(valores, 1):
            c = ws.cell(row=r, column=i, value=v)
            c.font = Font(name=F, size=10, color=(VERDE if v == "Sí" else GRIS if v in ("No", "—") else "1B2333"), bold=(v == "Sí"))
            c.border = Border(bottom=fino)
            c.alignment = Alignment(horizontal="center" if i in (1, 8, 9, 10) else "left", vertical="center")
    if n:
        tabla = Table(displayName="TarjetasDelDia", ref=f"A8:J{fin - 1}")
        tabla.tableStyleInfo = TableStyleInfo(name="TableStyleLight9", showRowStripes=True)
        ws.add_table(tabla)
    else:
        ws.merge_cells("A9:J9")
        ws["A9"] = "No hubo tarjetas completadas ni entregadas en esta fecha."
        ws["A9"].font = Font(name=F, italic=True, color=GRIS)
        ws["A9"].alignment = Alignment(horizontal="center")

    nota = fin + 1
    ws.merge_cells(f"A{nota}:J{nota}")
    ws[f"A{nota}"] = ("Completada = el día en que la tarjeta quedó con R1, R2, R3 y MAC de R1 y R2 (fecha de finalizado). "
                      "Entregada = fecha real de entrega. Fuente: base de datos de Escáner TQT.")
    ws[f"A{nota}"].font = Font(name=F, size=9, italic=True, color=GRIS)
    ws[f"A{nota}"].alignment = Alignment(wrap_text=True)
    ws.row_dimensions[nota].height = 28

    anchos = [11, 17, 22, 20, 22, 20, 22, 13, 12, 14]
    for i, a in enumerate(anchos, 1):
        ws.column_dimensions[get_column_letter(i)].width = a
    ws.freeze_panes = "A9"
    ws.print_title_rows = "8:8"
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
