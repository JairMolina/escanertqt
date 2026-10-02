"""Servicio de Sincronización con Excel mensual para Escaner TQT.

REGLA DE ORO: NUNCA sobrescribir ni romper fórmulas, validaciones de datos ni formatos existentes.

Cómo funciona la plantilla (verificado celda por celda):
  * Producción      : el operador/sistema solo captura A (ID), D/G (firmware), E (respaldo), H (semana), I/J (fechas).
                      B, C y F son FÓRMULAS (nombre y MAC por INDEX/MATCH contra 'Catálogo PCB').
  * Catálogo PCB    : aquí VIVEN las MAC (B = R1, G = R2). Estado en C/H con la lista
                      'SIN PROBAR, FUNCIONAL, NO FUNCIONAL, REPARACIÓN'. D e I son fórmulas (SUELTA/DUPLICADA).
  * Pruebas         : B:F son fórmulas LOOKUP(2,1/…) que leen la BITÁCORA DE ACTUALIZACIÓN MASIVA (J:AA):
                      J Fecha · K Proceso · L Estatus · M:AA hasta 15 IDs por fila. Gana la última fila que
                      contiene el ID. Por eso el sistema escribe SOLO en la bitácora y jamás en B:G.
  * Etiquetas       : todo son fórmulas.

Fidelidad: openpyxl descarta bloques <extLst> (p. ej. la validación x14 Producción!E2:E101 que apunta a
otra hoja). Tras guardar, este módulo los re-inyecta desde el archivo original y verifica que el número de
validaciones, reglas de formato condicional y tablas de cada hoja no haya disminuido. La escritura es
atómica (archivo temporal + os.replace) y conserva un respaldo `.bak`.
"""
import logging
import os
import re
import shutil
import threading
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from copy import copy
import openpyxl
from openpyxl.worksheet.worksheet import Worksheet

from app.config import settings
from app.database import db, inventario as inv
from app.database.models import (
    ETAPA_KEYS,
    ETAPA_LABEL,
    MESES_ES,
    derivar_estado_general,
    estado_pcb_desde_prueba,
    extract_mac,
    normalizar_estado_prueba,
    parse_tarjeta_code,
)

logger = logging.getLogger(__name__)

EXCEL_ERROR_CODES = {"#REF!", "#NAME?", "#VALUE!", "#DIV/0!", "#NULL!", "#NUM!", "#N/A", "#SPILL!", "#CALC!"}

# Zonas de la plantilla
CAT_FILA_MIN, CAT_FILA_MAX = 3, 102          # Catálogo PCB
PROD_FILA_MIN, PROD_FILA_MAX = 2, 101        # Producción
LOG_FILA_MIN, LOG_FILA_MAX = 3, 200          # Bitácora masiva (las fórmulas leen hasta la fila 200)
LOG_COL_FECHA, LOG_COL_PROCESO, LOG_COL_ESTATUS, LOG_COL_ID1, LOG_COL_ID_ULT = 10, 11, 12, 13, 27  # J, K, L, M..AA
IDS_POR_FILA = LOG_COL_ID_ULT - LOG_COL_ID1 + 1  # 15

# Columnas de Producción según la versión de la plantilla. La nueva (v1.1.12) trae 'Botón R3' en H y corre todo una columna.
COLS_PROD_R3 = {"r3": 8, "semana": 9, "fecha_p": 10, "fecha_r": 11, "gabinete": 12, "fw1": 15, "fw2": 17}
# Columnas extra de Producción (se crean al exportar si faltan; se reconocen por su encabezado exacto en cualquier columna)
HDR_FECHA_LLEGADA, HDR_FECHA_FINAL = "Fecha Llegada", "Fecha Finalizado"
COL_EXTRA_FECHAS = (19, 20)               # S, T: libres en la plantilla (A:L datos, N:Q listas)
GABINETES_XLSX = ("Quintalock", "Translock")
COLS_PROD_V0 = {"r3": None, "semana": 8, "fecha_p": 9, "fecha_r": 10, "gabinete": 11, "fw1": 14, "fw2": 16}
HDR_PROD_R3 = "Botón R3"
CAT_R3_NOMBRE, CAT_R3_ESTADO = 11, 12  # Catálogo PCB!K/L (R3 sin MAC); M = fórmula 'Asignada a'; O = FILTER de disponibles

# Estado PCB de la BD -> lista desplegable del Catálogo PCB
CAT_ESTADO_EXCEL = {"PENDIENTE": "SIN PROBAR", "FUNCIONAL": "FUNCIONAL", "FALLA": "NO FUNCIONAL"}
CAT_ESTADO_DB = {"FUNCIONAL": "FUNCIONAL", "NO FUNCIONAL": "FALLA"}

# Producción!B (nombre R1) es una FÓRMULA derivada del ID. Solo se sustituye por un valor cuando la R1 real de la
# tarjeta no coincide con lo que produce (tarjetas impares u otra versión) y se restaura si vuelve a coincidir.
FORMULA_PROD_B = '=IF(A{r}="","","TQT-R1-V30-"&TEXT(VALUE(A{r}),"0000"))'

_EXPORT_LOCK = threading.Lock()  # una sola escritura Excel a la vez (dos clics en "Sincronizar")


class ExcelIntegrityError(RuntimeError):
    """El archivo resultante perdió validaciones/formatos/fórmulas; no se reemplazó el original."""


class ExcelBloqueadoError(PermissionError):
    """El archivo está abierto en Excel (o sin permiso de escritura)."""


# ============================================================================
# Utilidades
# ============================================================================
def _normalize_str(text: str) -> str:
    """Elimina acentos y convierte a minúsculas para comparaciones insensibles a diacríticos."""
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFD", str(text).lower().strip())
    return "".join(c for c in nfkd if unicodedata.category(c) != "Mn")


def get_sheet_by_name(wb: openpyxl.Workbook, target_name: str) -> Worksheet:
    """Busca una hoja en el libro por nombre de forma insensible a mayúsculas y acentos."""
    target_clean = _normalize_str(target_name)
    for name in wb.sheetnames:
        if _normalize_str(name) == target_clean:
            return wb[name]
    for name in wb.sheetnames:
        if target_clean in _normalize_str(name):
            return wb[name]
    raise KeyError(f"No se encontró la hoja '{target_name}' en el libro Excel. Hojas disponibles: {wb.sheetnames}")


def map_test_status_to_excel(status_db: Optional[str]) -> str:
    """Estado de prueba (cualquier vocabulario) -> valor canónico que espera la hoja Pruebas."""
    return normalizar_estado_prueba(status_db, default="PENDIENTE")


def map_test_status_from_excel(status_excel: Optional[str]) -> str:
    """Valor de la hoja Pruebas (OK, FALLA, RETRABAJO, NO APLICA, PENDIENTE) -> estado canónico de la BD."""
    s = str(status_excel or "").strip().upper()
    if s == "LIBERADO":
        s = "OK"
    elif s == "DETENIDO":
        s = "FALLA"
    return normalizar_estado_prueba(s, default="PENDIENTE")


def _texto(celda, valor: Any) -> None:
    """Escribe `valor` como TEXTO: un firmware/nombre que empiece por '=' jamás debe convertirse en fórmula
    (openpyxl lo haría), porque se ejecutaría al abrir el Excel (inyección de fórmulas)."""
    celda.value = valor
    if isinstance(valor, str) and valor.startswith("="):
        celda.data_type = "s"


def _layout_prod(ws_prod: Worksheet) -> Dict[str, Optional[int]]:
    """Columnas de Producción: con el encabezado exacto 'Botón R3' en H1 es la plantilla nueva; si no, la anterior."""
    return COLS_PROD_R3 if str(ws_prod.cell(1, 8).value or "").strip() == HDR_PROD_R3 else COLS_PROD_V0


def _cols_fechas_extra(ws: Worksheet, crear: bool = False) -> Dict[str, Optional[int]]:
    """Columnas 'Fecha Llegada' y 'Fecha Finalizado' (por encabezado). Con crear=True las agrega en S/T copiando el estilo de
    'Gabinete' si el libro no las tiene (los Excel de versiones anteriores siguen abriéndose y exportándose)."""
    hallado: Dict[str, Optional[int]] = {"llegada": None, "final": None}
    for c in range(1, ws.max_column + 1):
        v = str(ws.cell(1, c).value or "").strip()
        if v == HDR_FECHA_LLEGADA:
            hallado["llegada"] = c
        elif v == HDR_FECHA_FINAL:
            hallado["final"] = c
    if crear:
        modelo = ws.cell(1, _layout_prod(ws)["gabinete"])
        for clave, hdr, col in (("llegada", HDR_FECHA_LLEGADA, COL_EXTRA_FECHAS[0]), ("final", HDR_FECHA_FINAL, COL_EXTRA_FECHAS[1])):
            if hallado[clave] is None:
                libre = col if ws.cell(1, col).value in (None, "") else ws.max_column + 2
                celda = ws.cell(1, libre)
                celda.value = hdr
                celda._style = copy(modelo._style)
                ws.column_dimensions[celda.column_letter].width = 18
                hallado[clave] = libre
    return hallado


def _fmt_fecha(v: Any) -> Optional[str]:
    """Celda -> 'YYYY-MM-DD'. Acepta fechas de Excel, texto ISO y dd/mm/aaaa; cualquier otra cosa (seriales, basura) se ignora."""
    if isinstance(v, (datetime, date)):
        return v.strftime("%Y-%m-%d")
    s = str(v).strip() if v else ""
    for fmt, n in (("%Y-%m-%d", 10), ("%d/%m/%Y", 10)):
        try:
            return datetime.strptime(s[:n], fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _catalogo_tiene_r3(ws_cat: Worksheet) -> bool:
    return str(ws_cat.cell(1, CAT_R3_NOMBRE).value or "").strip().upper() == "PCB R3"


def _es_valor(v: Any) -> bool:
    """True si la celda tiene un valor literal (no vacío, no fórmula)."""
    return v is not None and str(v).strip() != "" and not str(v).startswith("=") and not hasattr(v, "text")


# ============================================================================
# Fidelidad del .xlsx: conteo de estructura y re-inyección de <extLst>
# ============================================================================
def _mapa_hojas(z: zipfile.ZipFile) -> Dict[str, str]:
    """nombre de hoja -> ruta del XML dentro del zip (vía workbook.xml + rels)."""
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
          "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    destinos = {r.get("Id"): r.get("Target") for r in rels}
    resultado = {}
    for s in wb.find("m:sheets", ns):
        rid = s.get("{%s}id" % ns["r"])
        destino = destinos[rid].lstrip("/")
        resultado[s.get("name")] = destino if destino.startswith("xl/") else f"xl/{destino}"
    return resultado


def structure_counts(path: str) -> Dict[str, Dict[str, int]]:
    """Cuenta por hoja: validaciones de datos (estándar + x14), reglas de formato condicional
    (estándar + x14) y tablas. Lee el XML crudo, no depende de openpyxl."""
    with zipfile.ZipFile(path) as z:
        conteo = {}
        for nombre, ruta in _mapa_hojas(z).items():
            xml = z.read(ruta).decode("utf-8")
            conteo[nombre] = {
                "validaciones": len(re.findall(r"<dataValidation[ >]", xml)),
                "validaciones_x14": len(re.findall(r"<x14:dataValidation[ >]", xml)),
                "reglas_formato": len(re.findall(r"<cfRule[ >]", xml)) + len(re.findall(r"<x14:cfRule[ >]", xml)),
                "tablas": len(re.findall(r"<tablePart[ >]", xml)),
            }
        return conteo


def _totales(conteo: Dict[str, Dict[str, int]]) -> Dict[str, Dict[str, int]]:
    """Resumen comparable: validaciones = estándar + x14."""
    return {h: {"validaciones": c["validaciones"] + c["validaciones_x14"], "reglas_formato": c["reglas_formato"],
                "tablas": c["tablas"]} for h, c in conteo.items()}


def _extlst_hoja(xml: str) -> Optional[str]:
    """Devuelve el <extLst> de nivel hoja (último hijo de <worksheet>) o None."""
    fin = xml.rfind("</worksheet>")
    if fin == -1:
        return None
    previo = xml[:fin].rstrip()
    if not previo.endswith("</extLst>"):
        return None
    # Retroceder hasta el <extLst> que abre este cierre, contando anidamiento
    profundidad = 0
    for m in reversed(list(re.finditer(r"</extLst>|<extLst[ >]", previo))):
        profundidad += 1 if m.group(0) == "</extLst>" else -1
        if profundidad == 0:
            return previo[m.start():]
    return None


def _reinyectar_extensiones(origen: str, generado: str, destino: str) -> int:
    """Copia `generado` a `destino` re-insertando en cada hoja el <extLst> que tenía `origen`
    y que openpyxl descartó. Devuelve cuántos bloques se re-inyectaron."""
    inyectados = 0
    usa_metadata = False
    with zipfile.ZipFile(origen) as zo, zipfile.ZipFile(generado) as zg:
        mapa_o, mapa_g = _mapa_hojas(zo), _mapa_hojas(zg)
        cambios: Dict[str, str] = {}
        for nombre, ruta_o in mapa_o.items():
            ruta_g = mapa_g.get(nombre)
            if not ruta_g:
                continue
            xml_o = zo.read(ruta_o).decode("utf-8")
            # Fórmulas de matriz dinámica (cm="1"): openpyxl pierde el atributo y Excel las mostraría como {=...} heredadas.
            dinamicas = set(re.findall(r'<c r="([A-Z]+[0-9]+)"[^>]*\scm="1"', xml_o))
            if dinamicas:
                xml_g0 = cambios.get(ruta_g) or zg.read(ruta_g).decode("utf-8")
                nuevo = re.sub(r'<c r="([A-Z]+[0-9]+)"((?:(?!cm=)[^>])*)>(<f t="array")',
                               lambda m: f'<c r="{m.group(1)}"{m.group(2)} cm="1">{m.group(3)}' if m.group(1) in dinamicas else m.group(0), xml_g0)
                if nuevo != xml_g0:
                    cambios[ruta_g] = nuevo
                    usa_metadata = True
            bloque = _extlst_hoja(xml_o)
            if not bloque:
                continue
            xml_g = cambios.get(ruta_g) or zg.read(ruta_g).decode("utf-8")
            if _extlst_hoja(xml_g):  # ya tiene uno: no duplicar
                continue
            bloque = re.sub(r'\sxr:uid="[^"]*"', "", bloque)  # el prefijo xr no está declarado en la salida
            fin = xml_g.rfind("</worksheet>")
            cambios[ruta_g] = xml_g[:fin] + bloque + xml_g[fin:]
            inyectados += 1

        meta = zo.read("xl/metadata.xml") if usa_metadata and "xl/metadata.xml" in zo.namelist() else None
        with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as zd:
            for item in zg.infolist():
                data = zg.read(item.filename)
                if item.filename in cambios:
                    ET.fromstring(cambios[item.filename])  # XML bien formado o excepción
                    data = cambios[item.filename].encode("utf-8")
                elif meta and item.filename == "[Content_Types].xml":
                    data = data.decode("utf-8").replace("</Types>", '<Override PartName="/xl/metadata.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheetMetadata+xml"/></Types>').encode("utf-8")
                elif meta and item.filename == "xl/_rels/workbook.xml.rels":
                    data = data.decode("utf-8").replace("</Relationships>", '<Relationship Id="rIdMeta1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sheetMetadata" Target="metadata.xml"/></Relationships>').encode("utf-8")
                zd.writestr(item, data)
            if meta:
                zd.writestr("xl/metadata.xml", meta)
    return inyectados


def _verificar_estructura(origen: str, resultado: str) -> Dict[str, Any]:
    """Compara estructura origen vs resultado; lanza ExcelIntegrityError si algo disminuyó."""
    antes, despues = _totales(structure_counts(origen)), _totales(structure_counts(resultado))
    problemas = []
    for hoja, c in antes.items():
        d = despues.get(hoja)
        if d is None:
            problemas.append(f"Falta la hoja '{hoja}'.")
            continue
        for clave, valor in c.items():
            if d[clave] < valor:
                problemas.append(f"Hoja '{hoja}': {clave} pasó de {valor} a {d[clave]}.")
    if problemas:
        raise ExcelIntegrityError("El Excel resultante perdió estructura: " + " ".join(problemas))
    return {"antes": antes, "despues": despues}


# ============================================================================
# Motor
# ============================================================================
class ExcelSyncEngine:
    """Motor de lectura, sincronización y validación de integridad para plantillas Excel TQT."""

    def __init__(self, template_path: Optional[str] = None, db_path: Optional[Path] = None):
        self.db_path = Path(db_path) if db_path else None
        if template_path:
            self.template_path = Path(template_path)
        else:
            default_template = settings.TEMPLATES_DIR / "Control_Produccion_TQT_Template.xlsx"
            self.template_path = default_template

    def get_template_path(self) -> Path:
        """Devuelve la ruta a la plantilla maestra existente."""
        if self.template_path.exists():
            return self.template_path
        # Sin respaldo en el Escritorio: si ese archivo llegara a tener datos, se copiarian a los meses nuevos.
        raise FileNotFoundError(f"Plantilla maestra de Excel no encontrada en {self.template_path}. Restaura templates/Control_Produccion_TQT_Template.xlsx.")

    # ------------------------------------------------------------------ creación
    def monthly_path(self, mes: int, anio: int) -> Path:
        """Ruta estándar del Excel mensual: <EXCEL_DIR>/Control_Produccion_TQT_[Mes]_[Año].xlsx"""
        return settings.EXCEL_DIR / f"Control_Produccion_TQT_{MESES_ES[mes - 1]}_{anio}.xlsx"

    def create_monthly_excel(
        self,
        mes: int,
        anio: int,
        target_path: Optional[str] = None,
        overwrite: bool = False,
    ) -> str:
        """Crea el Excel mensual copiando la plantilla intacta. Si el archivo ya existe NO se
        sobrescribe (contiene datos de producción): se devuelve el existente."""
        src = self.get_template_path()
        if mes < 1 or mes > 12:
            raise ValueError(f"Mes inválido: {mes}. Debe estar entre 1 y 12.")
        if anio < 2020 or anio > 2100:
            raise ValueError(f"Año inválido: {anio}. Debe estar entre 2020 y 2100.")

        dest = Path(target_path) if target_path else self.monthly_path(mes, anio)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists() and not overwrite:
            logger.info("El Excel mensual ya existe, se reutiliza sin sobrescribir: %s", dest)
            return str(dest.resolve())

        tmp = dest.with_name(f".{dest.name}.tmp")
        shutil.copy2(src, tmp)
        os.replace(tmp, dest)
        logger.info("Nuevo archivo mensual creado: %s a partir de %s", dest, src)
        return str(dest.resolve())

    # ------------------------------------------------------------------ importación
    def import_from_excel(self, excel_path: str, lote_id: int, db_path: Optional[Path] = None) -> Dict[str, Any]:
        """
        Lee catálogo PCB, tarjetas y pruebas del Excel y los carga en SQLite para el lote.
          * Las tarjetas solo se importan si su R1 y R2 tienen MAC en el catálogo (una fila con ID
            pero sin MAC es un renglón de la plantilla, no una tarjeta producida).
          * Las pruebas se reconstruyen leyendo la bitácora masiva J:AA (las fórmulas B:F no se evalúan).
        """
        path = Path(excel_path)
        if not path.exists():
            raise FileNotFoundError(f"Archivo Excel no encontrado: {excel_path}")

        target_db = db_path or self.db_path
        if not db.get_lote_by_id(lote_id, db_path=target_db):
            raise ValueError(f"Lote con ID {lote_id} no existe en la base de datos.")

        wb = openpyxl.load_workbook(str(path), data_only=False)
        ws_cat = get_sheet_by_name(wb, "Catálogo PCB")
        ws_prod = get_sheet_by_name(wb, "Producción")
        ws_pruebas = get_sheet_by_name(wb, "Pruebas")
        self._validar_encabezados(ws_prod, ws_cat)
        L = _layout_prod(ws_prod)
        con_r3 = _catalogo_tiene_r3(ws_cat)

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        n_pcbs = n_tarjetas = n_pruebas = 0
        omitidas: List[str] = []
        errores: List[str] = []

        with db.transaction(target_db) as c:
            # 1. Catálogo PCB (R1: A/B/C · R2: F/G/H) -> inventario. Solo las PCB con MAC son placas reales
            #    (el resto son renglones de la plantilla). Entran DISPONIBLES; las tarjetas las asignan.
            en_libro = set()  # (tipo, nombre) con MAC en el catálogo de ESTE libro: solo esas PCB pueden formar tarjetas
            for tipo, col_n, col_m, col_e in (("R1", 1, 2, 3), ("R2", 6, 7, 8)):
                for r in range(CAT_FILA_MIN, CAT_FILA_MAX + 1):
                    nombre = ws_cat.cell(r, col_n).value
                    if not _es_valor(nombre):
                        continue
                    mac = extract_mac(str(ws_cat.cell(r, col_m).value or ""))
                    if not mac:
                        continue
                    t = parse_tarjeta_code(str(nombre), tipo)
                    if not t or t["tipo"] != tipo:
                        errores.append(f"Catálogo {tipo} fila {r}: nombre de PCB no válido '{nombre}'")
                        continue
                    estado = CAT_ESTADO_DB.get(str(ws_cat.cell(r, col_e).value or "").strip().upper(), "PENDIENTE")
                    try:
                        c.execute("SAVEPOINT pcb")
                        inv.asegurar_pcb(c, tipo, t["version"], t["numero"], mac, estado)
                        c.execute("RELEASE pcb")
                        en_libro.add((tipo, t["nombre"]))
                        n_pcbs += 1
                    except Exception as e:  # noqa: BLE001
                        c.execute("ROLLBACK TO pcb")
                        c.execute("RELEASE pcb")
                        errores.append(f"Catálogo {tipo} fila {r}: {e}")

            # 1b. Catálogo R3 (K/L, sin MAC): todas las que existen en el libro; solo entran al inventario las usadas en
            #     Producción!H o con un estado ya decidido (el resto son renglones de la plantilla, como R1/R2 sin MAC).
            r3_catalogo: Dict[str, str] = {}
            if con_r3:
                for r in range(CAT_FILA_MIN, CAT_FILA_MAX + 1):
                    v = ws_cat.cell(r, CAT_R3_NOMBRE).value
                    if _es_valor(v):
                        r3_catalogo[str(v).strip()] = str(ws_cat.cell(r, CAT_R3_ESTADO).value or "").strip().upper()
            usadas_r3: Dict[str, str] = {}   # nombre R3 -> ID de la tarjeta (detecta repetidas)
            pedidas_r3 = set()
            if L["r3"]:
                for r in range(PROD_FILA_MIN, PROD_FILA_MAX + 1):
                    nom = ws_prod.cell(r, L["r3"]).value
                    if _es_valor(nom):
                        pedidas_r3.add(str(nom).strip())
            for nombre, est in r3_catalogo.items():
                if nombre not in pedidas_r3 and est in ("", "SIN PROBAR"):
                    continue
                t = parse_tarjeta_code(nombre, "R3")
                if not t or t["tipo"] != "R3":
                    errores.append(f"Catálogo R3: nombre de PCB no válido '{nombre}'")
                    continue
                try:
                    c.execute("SAVEPOINT pcb")
                    inv.asegurar_pcb(c, "R3", t["version"], t["numero"], None, CAT_ESTADO_DB.get(est, "PENDIENTE"))
                    c.execute("RELEASE pcb")
                    n_pcbs += 1
                except Exception as e:  # noqa: BLE001
                    c.execute("ROLLBACK TO pcb")
                    c.execute("RELEASE pcb")
                    errores.append(f"Catálogo R3 {nombre}: {e}")

            log = self._leer_bitacora_pruebas(ws_pruebas)

            # 2. Tarjetas de Producción (+ 3. pruebas)
            for r in range(PROD_FILA_MIN, PROD_FILA_MAX + 1):
                id_val = ws_prod.cell(r, 1).value
                if not _es_valor(id_val):
                    continue
                id_txt = str(id_val).strip()
                id_num = id_txt.zfill(4) if id_txt.isdigit() else id_txt
                b_val = ws_prod.cell(r, 2).value
                nombre_r1 = str(b_val).strip() if _es_valor(b_val) else f"TQT-R1-V30-{id_num}"
                nombre_r2 = str(ws_prod.cell(r, 5).value or "").strip() or f"TQT-R2-V30-{id_num}"
                p1 = c.execute("SELECT id FROM pcb_inventario WHERE tipo='R1' AND nombre=? AND mac IS NOT NULL", (nombre_r1,)).fetchone()
                p2 = c.execute("SELECT id FROM pcb_inventario WHERE tipo='R2' AND nombre=? AND mac IS NOT NULL", (nombre_r2,)).fetchone()
                if not p1 or not p2 or ("R1", nombre_r1) not in en_libro or ("R2", nombre_r2) not in en_libro:
                    omitidas.append(id_num)
                    continue

                nombre_r3, p3 = None, None
                if L["r3"] and _es_valor(ws_prod.cell(r, L["r3"]).value):
                    nombre_r3 = str(ws_prod.cell(r, L["r3"]).value).strip()
                    if nombre_r3 not in r3_catalogo:
                        errores.append(f"Producción fila {r} (tarjeta {id_num}): la R3 '{nombre_r3}' no existe en el Catálogo PCB; se ignoró.")
                    elif usadas_r3.get(nombre_r3):
                        errores.append(f"Producción fila {r} (tarjeta {id_num}): la R3 '{nombre_r3}' ya está en la tarjeta {usadas_r3[nombre_r3]}; se ignoró.")
                    else:
                        p3 = c.execute("SELECT id, mac FROM pcb_inventario WHERE tipo='R3' AND nombre=?", (nombre_r3,)).fetchone()
                        if not p3:
                            errores.append(f"Producción fila {r} (tarjeta {id_num}): la R3 '{nombre_r3}' no se pudo cargar; se ignoró.")
                        elif p3["mac"]:
                            errores.append(f"Producción fila {r} (tarjeta {id_num}): la R3 '{nombre_r3}' tiene MAC ({p3['mac']}); las R3 no llevan MAC.")
                            p3 = None
                        else:
                            usadas_r3[nombre_r3] = id_num

                semana = None
                m = re.search(r"W(\d+)|^(\d+)$", str(ws_prod.cell(r, L["semana"]).value or ""))
                if m:
                    semana = int(m.group(1) or m.group(2))
                fw1, fw2 = ws_prod.cell(r, 4).value, ws_prod.cell(r, 7).value
                fecha_p, fecha_r = ws_prod.cell(r, L["fecha_p"]).value, ws_prod.cell(r, L["fecha_r"]).value
                fmt = _fmt_fecha
                extra = _cols_fechas_extra(ws_prod)
                fecha_l = ws_prod.cell(r, extra["llegada"]).value if extra["llegada"] else None
                fecha_f = ws_prod.cell(r, extra["final"]).value if extra["final"] else None
                gab = str(ws_prod.cell(r, L["gabinete"]).value or "").strip().capitalize()
                gab = gab if gab in GABINETES_XLSX else None

                try:
                    c.execute("SAVEPOINT tarjeta")
                    existente = db.get_tarjeta_por_numero(lote_id, id_num, c)
                    if existente:
                        if (existente["pcb_r1_id"], existente["pcb_r2_id"]) != (p1["id"], p2["id"]):
                            raise ValueError("la tarjeta ya existe en el lote con otras PCB")
                        tarjeta_id = existente["id"]
                        if p3 and not existente["pcb_r3_id"]:
                            c.execute("UPDATE tarjetas_produccion SET pcb_r3_id = ? WHERE id = ?", (p3["id"], tarjeta_id))
                            c.execute("UPDATE pcb_inventario SET estado_ciclo='ASIGNADA', updated_at=? WHERE id=?", (now_str, p3["id"]))
                        elif p3 and existente["pcb_r3_id"] != p3["id"]:
                            errores.append(f"Producción fila {r} (tarjeta {id_num}): ya tiene otra R3 en la base; no se cambió a '{nombre_r3}'.")
                    else:
                        tarjeta_id = inv.crear_tarjeta(lote_id, id_num, p1["id"], p2["id"], p3["id"] if p3 else None, "excel", conn=c)["id"]
                    c.execute(
                        "UPDATE tarjetas_produccion SET firmware_r1 = COALESCE(?, firmware_r1), firmware_r2 = COALESCE(?, firmware_r2), "
                        "semana_produccion = COALESCE(?, semana_produccion), fecha_proyectada = COALESCE(?, fecha_proyectada), "
                        "fecha_real = COALESCE(?, fecha_real), fecha_llegada = COALESCE(?, fecha_llegada), "
                        "fecha_finalizado = COALESCE(?, fecha_finalizado), gabinete = COALESCE(?, gabinete), updated_at = ? WHERE id = ?",
                        (str(fw1) if fw1 else None, str(fw2) if fw2 else None, semana, fmt(fecha_p), fmt(fecha_r),
                         fmt(fecha_l), fmt(fecha_f), gab, now_str, tarjeta_id))
                    if id_num in log:
                        for etapa, estado in log[id_num].items():
                            c.execute(f"UPDATE pruebas_historial SET {etapa} = ?, updated_at = ? WHERE tarjeta_id = ?", (estado, now_str, tarjeta_id))
                    db.recalcular_general(c, tarjeta_id)
                    db.sincronizar_estado_pcb(c, tarjeta_id)
                    c.execute("RELEASE tarjeta")
                    n_tarjetas += 1
                    n_pruebas += 1
                except Exception as e:  # noqa: BLE001
                    c.execute("ROLLBACK TO tarjeta")
                    c.execute("RELEASE tarjeta")
                    errores.append(f"Producción fila {r} (tarjeta {id_num}): {e}")

            c.execute("UPDATE lotes_mensuales SET ruta_excel = ? WHERE id = ?", (str(path.resolve()), lote_id))

        logger.info("Importación Excel lote %d: %d PCBs, %d tarjetas, %d pruebas, %d omitidas, %d errores",
                    lote_id, n_pcbs, n_tarjetas, n_pruebas, len(omitidas), len(errores))
        return {
            "status": "success" if not errores else "partial",
            "lote_id": lote_id,
            "excel_path": str(path.resolve()),
            "imported_pcbs": n_pcbs,
            "imported_tarjetas": n_tarjetas,
            "imported_pruebas": n_pruebas,
            "omitidas_sin_mac": omitidas,
            "errores": errores,
        }

    @staticmethod
    def _validar_encabezados(ws_prod: Worksheet, ws_cat: Worksheet) -> None:
        """Encabezados exactos de las columnas de captura; si no coinciden, error claro (no se importa nada)."""
        L = _layout_prod(ws_prod)
        letra = openpyxl.utils.get_column_letter
        esperados = [(1, "ID Tarjeta"), (4, "Firmware PCB Principal"), (5, "Nombre Tarjeta Respaldo"), (7, "Firmware PCB Respaldo"),
                     (L["semana"], "Semana Producción"), (L["fecha_p"], "Fecha Proyectada Entrega"), (L["fecha_r"], "Fecha Real Entrega")]
        malos = [f"Producción!{letra(c)}1 debe decir '{t}' y dice '{ws_prod.cell(1, c).value}'"
                 for c, t in esperados if str(ws_prod.cell(1, c).value or "").strip() != t]
        malos += [f"Catálogo PCB!{letra(c)}2 debe decir '{t}' y dice '{ws_cat.cell(2, c).value}'"
                  for c, t in ((1, "Nombre PCB"), (2, "MAC Address"), (3, "Estado PCB"), (6, "Nombre PCB"), (7, "MAC Address"), (8, "Estado PCB"))
                  if str(ws_cat.cell(2, c).value or "").strip() != t]
        if malos:
            raise ValueError("El Excel no tiene la estructura esperada: " + "; ".join(malos) + ".")

    @staticmethod
    def _leer_bitacora_pruebas(ws: Worksheet) -> Dict[str, Dict[str, str]]:
        """Reconstruye {id_tarjeta: {etapa: estado}} leyendo la bitácora masiva (última fila gana)."""
        etiquetas = {_normalize_str(v): k for k, v in ETAPA_LABEL.items()}
        resultado: Dict[str, Dict[str, str]] = {}
        for r in range(LOG_FILA_MIN, LOG_FILA_MAX + 1):
            etapa = etiquetas.get(_normalize_str(str(ws.cell(r, LOG_COL_PROCESO).value or "")))
            estado_raw = ws.cell(r, LOG_COL_ESTATUS).value
            if not etapa or not _es_valor(estado_raw):
                continue
            estado = map_test_status_from_excel(estado_raw)
            for col in range(LOG_COL_ID1, LOG_COL_ID_ULT + 1):
                v = ws.cell(r, col).value
                if _es_valor(v):
                    s = str(v).strip()
                    resultado.setdefault(s.zfill(4) if s.isdigit() else s, {})[etapa] = estado
        return resultado

    # ------------------------------------------------------------------ exportación
    def export_to_excel(
        self,
        excel_path: str,
        lote_id: int,
        db_path: Optional[Path] = None,
        preserve_pruebas_formulas: bool = True,  # obsoleto: las fórmulas de Pruebas B:G NUNCA se tocan
    ) -> Dict[str, Any]:
        """
        Vuelca el lote de SQLite al Excel mensual SIN alterar fórmulas, validaciones ni formatos.
          * Catálogo PCB : nombre (A/F), MAC (B/G) y estado (C/H) de cada PCB. D/I intactas.
          * Producción   : ID (A), firmware (D/G), respaldo (E), semana (H), fechas (I/J). B, C, F intactas.
          * Pruebas      : SOLO la bitácora masiva J:AA (una fila por proceso+estatus, 15 IDs por fila).
                           Las fórmulas B:F la leen y G calcula el estado general.
        La escritura es atómica: archivo temporal -> verificación de estructura -> os.replace,
        y se deja un respaldo `<archivo>.bak` del contenido anterior.
        """
        path = Path(excel_path)
        if not path.exists():
            raise FileNotFoundError(f"Archivo Excel no encontrado para exportar: {excel_path}")
        target_db = db_path or self.db_path

        with _EXPORT_LOCK:
            try:
                with open(path, "r+b"):  # falla si Excel lo tiene abierto
                    pass
            except PermissionError as e:
                raise ExcelBloqueadoError(
                    f"El archivo '{path.name}' está abierto en Excel o sin permiso de escritura. Ciérralo y reintenta."
                ) from e

            lote = db.get_lote_by_id(lote_id, db_path=target_db)
            anio = lote["anio"] if lote else datetime.now().year
            tarjetas, _ = db.list_tarjetas(lote_id=lote_id, limit=100000, db_path=target_db)
            tarjetas.sort(key=lambda t: t["id"])

            wb = openpyxl.load_workbook(str(path), data_only=False)
            ws_prod = get_sheet_by_name(wb, "Producción")
            ws_cat = get_sheet_by_name(wb, "Catálogo PCB")
            ws_pruebas = get_sheet_by_name(wb, "Pruebas")

            omitidas: List[str] = []
            avisos: List[str] = []
            sueltas = self._pcb_sueltas(target_db)
            omitidas_cat: List[str] = []
            n_pcbs = self._escribir_catalogo(ws_cat, tarjetas + sueltas, omitidas_cat)
            omitidas.extend(o for o in omitidas_cat if not str(o).startswith("PCB "))
            if any(str(o).startswith("PCB ") for o in omitidas_cat):
                faltan = sorted({str(o)[4:] for o in omitidas_cat if str(o).startswith("PCB ")})
                avisos.append(f"{len(faltan)} PCB sueltas no caben en el Catálogo PCB de la plantilla (máx. {CAT_FILA_MAX - CAT_FILA_MIN + 1} por tipo) y no se escribieron: {', '.join(faltan)}. Siguen en la base de datos.")
            filas_prod = self._escribir_produccion(ws_prod, tarjetas, anio, omitidas, avisos)
            self._agregar_catalogo_firmware(ws_prod, inv.listar_firmware(db_path=target_db))
            con_r3 = [t["id_tarjeta_num"] for t in tarjetas if t.get("r3")]
            if con_r3 and not _layout_prod(ws_prod)["r3"]:
                avisos.append(f"{len(con_r3)} tarjeta(s) tienen R3 (se guarda en la BD): este Excel es de la versión anterior y no tiene "
                              "columna R3, por eso no aparece. Crea un Excel mensual nuevo para incluirla.")
            self._escribir_bitacora_pruebas(ws_pruebas, tarjetas, filas_prod, omitidas)
            if omitidas:
                avisos.append(f"{len(set(omitidas))} tarjeta(s) NO caben en la plantilla (máx. {PROD_FILA_MAX - PROD_FILA_MIN + 1} "
                              f"tarjetas y {CAT_FILA_MAX - CAT_FILA_MIN + 1} PCB por tipo, bitácora de pruebas hasta la fila {LOG_FILA_MAX}) "
                              f"y no se escribieron en el Excel: {', '.join(sorted(set(omitidas)))}. Siguen en la base de datos.")
            wb.calculation.fullCalcOnLoad = True  # Excel recalcula todo al abrir (openpyxl no guarda valores en caché)

            tmp1 = path.with_name(f".{path.stem}.1.tmp.xlsx")
            tmp2 = path.with_name(f".{path.stem}.2.tmp.xlsx")
            try:
                wb.save(str(tmp1))
                reinyectados = _reinyectar_extensiones(str(path), str(tmp1), str(tmp2))
                estructura = _verificar_estructura(str(path), str(tmp2))
                openpyxl.load_workbook(str(tmp2), data_only=False).close()  # el resultado debe abrir

                respaldo = path.with_name(path.name + ".bak")
                shutil.copy2(path, respaldo)
                try:
                    os.replace(tmp2, path)
                except PermissionError as e:
                    raise ExcelBloqueadoError(
                        f"No se pudo reemplazar '{path.name}': está abierto en Excel. Ciérralo y reintenta."
                    ) from e
            finally:
                for t in (tmp1, tmp2):
                    if t.exists():
                        try:
                            t.unlink()
                        except OSError:
                            pass

        logger.info("Excel sincronizado: %s (%d tarjetas, %d PCB, %d extensiones re-inyectadas, %d omitidas)",
                    path, len(filas_prod), n_pcbs, reinyectados, len(omitidas))
        return {
            "status": "success",
            "lote_id": lote_id,
            "excel_path": str(path.resolve()),
            "exported_pcbs": n_pcbs,
            "exported_tarjetas": len(filas_prod),
            "exported_pruebas": len(filas_prod),
            "extensiones_reinyectadas": reinyectados,
            "omitidas": sorted(set(omitidas)),
            "avisos": avisos,
            "respaldo": str(respaldo),
            "estructura": estructura,
        }

    # -- helpers de escritura ------------------------------------------------
    @staticmethod
    def _pcb_sueltas(db_path: Optional[Path]) -> List[Dict[str, Any]]:
        """TODAS las R1/R2 del inventario que no están en una tarjeta (sin confirmar, sueltas o con falla), con o sin MAC:
        el Catálogo PCB de la plantilla las lista igual (la fórmula de su columna D/I las marca SUELTA). Se devuelven con la forma
        de una 'tarjeta' de una sola ranura para reutilizar el escritor del catálogo. Las dadas de baja no salen."""
        salida: List[Dict[str, Any]] = []
        for estado in ("RECIBIDA", "DISPONIBLE", "FALLA"):
            for tipo in ("R1", "R2", "R3"):
                for p in inv.listar_pcb(tipo=tipo, estado_ciclo=estado, limit=5000, db_path=db_path)["items"]:
                    k = tipo.lower()
                    salida.append({"id_tarjeta_num": f"PCB {p['nombre']}", f"nombre_{k}": p["nombre"], f"mac_{k}": p.get("mac"),
                                   f"estado_pcb_{k}": "FALLA" if estado == "FALLA" else p.get("estado_pcb")})
        return salida

    @staticmethod
    def _escribir_catalogo(ws: Worksheet, tarjetas: List[Dict[str, Any]], omitidas: List[str]) -> int:
        """Catálogo PCB: nombre, MAC y estado. Nunca toca D ni I (fórmulas SUELTA/DUPLICADA)."""
        escritas = 0
        bloques = [("R1", 1, 2, 3, "nombre_r1", "mac_r1", "estado_pcb_r1"),
                   ("R2", 6, 7, 8, "nombre_r2", "mac_r2", "estado_pcb_r2")]
        if _catalogo_tiene_r3(ws):  # R3: sin MAC (col_m None)
            bloques.append(("R3", CAT_R3_NOMBRE, None, CAT_R3_ESTADO, "nombre_r3", "mac_r3", "estado_pcb_r3"))
        for tipo, col_n, col_m, col_e, k_nombre, k_mac, k_estado in bloques:
            filas = {}
            libres = []
            reservadas = []  # nombres de la plantilla que ninguna tarjeta usa y sin MAC/estado: se pueden reutilizar
            necesarios = {(t.get(k_nombre) or "").strip() for t in tarjetas}
            for r in range(CAT_FILA_MIN, CAT_FILA_MAX + 1):
                v = ws.cell(r, col_n).value
                if _es_valor(v):
                    filas[str(v).strip()] = r
                    if str(v).strip() not in necesarios and all(ws.cell(r, c).value in (None, "") for c in (col_m, col_e) if c):
                        reservadas.append(r)
                elif v is None:
                    libres.append(r)
            for t in tarjetas:
                nombre = (t.get(k_nombre) or "").strip()
                if not nombre:
                    continue
                fila = filas.get(nombre)
                if fila is None:
                    if libres:
                        fila = libres.pop(0)
                    elif reservadas:
                        fila = reservadas.pop(0)
                        filas.pop(str(ws.cell(fila, col_n).value).strip(), None)
                    else:
                        omitidas.append(t["id_tarjeta_num"])
                        continue
                    filas[nombre] = fila
                ws.cell(fila, col_n).value = nombre
                if col_m and t.get(k_mac):
                    ws.cell(fila, col_m).value = t[k_mac]
                estado = t.get(k_estado) or "PENDIENTE"
                celda = ws.cell(fila, col_e)
                # Un estado ya decidido en la BD manda; "PENDIENTE" no pisa lo que el usuario puso a mano.
                if estado != "PENDIENTE" or celda.value in (None, ""):
                    celda.value = CAT_ESTADO_EXCEL.get(estado, "SIN PROBAR")
                escritas += 1
        return escritas

    @staticmethod
    def _agregar_catalogo_firmware(ws: Worksheet, catalogo: Dict[str, List[str]]) -> None:
        """Agrega (sin borrar ni reordenar nada) las versiones de firmware del sistema que falten en las listas del Excel:
        Producción!O2:O52 (Firmware Principal, R1; N en la plantilla anterior) y Producción!Q2:Q52 (Firmware Respaldo, R2). Así el desplegable de
        las columnas D y G acepta las versiones nuevas."""
        L = _layout_prod(ws)
        for col, rol in ((L["fw1"], "R1"), (L["fw2"], "R2")):
            usados = {str(ws.cell(r, col).value).strip() for r in range(2, 53) if ws.cell(r, col).value not in (None, "")}
            libres = [r for r in range(2, 53) if ws.cell(r, col).value in (None, "")]
            for version in catalogo.get(rol, []):
                if version in usados or not libres:
                    continue
                _texto(ws.cell(libres.pop(0), col), version)
                usados.add(version)

    @staticmethod
    def _escribir_produccion(ws: Worksheet, tarjetas: List[Dict[str, Any]], anio: int, omitidas: List[str],
                             avisos: Optional[List[str]] = None) -> Dict[str, int]:
        """Producción: columnas de captura. Devuelve {id_tarjeta_num: fila}. La col. B (nombre R1) es fórmula y solo
        se reemplaza por un valor si la R1 real no coincide con `TQT-R1-V30-<ID>` (se avisa); se restaura si coincide."""
        avisos = avisos if avisos is not None else []
        filas: Dict[str, int] = {}
        libres = []
        L = _layout_prod(ws)
        reservadas = []  # IDs de la plantilla que ninguna tarjeta usa y sin datos de captura: se pueden reutilizar
        necesarios = {str(t["id_tarjeta_num"]).strip() for t in tarjetas}
        for r in range(PROD_FILA_MIN, PROD_FILA_MAX + 1):
            v = ws.cell(r, 1).value
            if _es_valor(v):
                s = str(v).strip()
                clave = s.zfill(4) if s.isdigit() else s
                filas[clave] = r
                if clave not in necesarios and all(ws.cell(r, c).value in (None, "") for c in (4, 7, 8, 9, 10, 11, 12)):
                    reservadas.append(r)
            elif v is None:
                libres.append(r)

        resultado: Dict[str, int] = {}
        for t in tarjetas:
            id_num = str(t["id_tarjeta_num"]).strip()
            fila = filas.get(id_num)
            if fila is None:
                if libres:
                    fila = libres.pop(0)
                elif reservadas:
                    fila = reservadas.pop(0)
                    viejo = str(ws.cell(fila, 1).value).strip()
                    filas.pop(viejo.zfill(4) if viejo.isdigit() else viejo, None)
                    avisos.append(f"Tarjeta {id_num}: no está en la lista de la plantilla; usó la fila {fila} (antes ID {viejo}).")
                else:
                    omitidas.append(id_num)
                    continue
                filas[id_num] = fila
            resultado[id_num] = fila

            ws.cell(fila, 1).value = id_num                       # A: ID (texto '0011', igual que la plantilla)
            # C y F son fórmulas: NUNCA se escriben. B solo se toca si la R1 real difiere de la fórmula.
            celda_b = ws.cell(fila, 2)
            b_es_formula = isinstance(celda_b.value, str) and celda_b.value.startswith("=")
            real, esperado = t.get("nombre_r1"), f"TQT-R1-V30-{id_num}"
            if real and real != esperado:
                celda_b.value = real
                avisos.append(f"Producción!B{fila} (tarjeta {id_num}): la R1 real es {real}; la fórmula daría {esperado}. "
                              "Se escribió el nombre como valor.")
            elif not real:
                if not b_es_formula:
                    celda_b.value = FORMULA_PROD_B.format(r=fila)      # la estructura de la plantilla no se altera: B siempre conserva su fórmula
                avisos.append(f"Tarjeta {id_num}: sin PCB R1 asignada; Producción!B{fila} conserva su fórmula y muestra el nombre derivado del ID.")
            elif not b_es_formula:
                celda_b.value = FORMULA_PROD_B.format(r=fila)      # vuelve a coincidir: se restaura la fórmula
            _texto(ws.cell(fila, 5), t.get("nombre_r2") or None)   # E: Nombre Tarjeta Respaldo (entrada)
            if t.get("firmware_r1"):
                _texto(ws.cell(fila, 4), t["firmware_r1"])         # D
            if t.get("firmware_r2"):
                _texto(ws.cell(fila, 7), t["firmware_r2"])         # G
            if L["r3"]:  # H: Botón R3 (texto, sin MAC). La BD manda: si la tarjeta ya no la tiene, se libera.
                _texto(ws.cell(fila, L["r3"]), t.get("nombre_r3") or None)
            if t.get("semana_produccion"):
                ws.cell(fila, L["semana"]).value = f"{anio}-W{int(t['semana_produccion']):02d}"  # lista '2026-W01'
            extra = _cols_fechas_extra(ws, crear=True)
            for col, clave in ((L["fecha_p"], "fecha_proyectada"), (L["fecha_r"], "fecha_real"),
                               (extra["llegada"], "fecha_llegada"), (extra["final"], "fecha_finalizado")):
                if t.get(clave):
                    try:
                        celda = ws.cell(fila, col)
                        celda.value = date.fromisoformat(str(t[clave])[:10])
                        if celda.number_format == "General":
                            celda.number_format = "yyyy-mm-dd"
                    except ValueError:
                        pass
            if t.get("gabinete") in GABINETES_XLSX:              # L: Gabinete (lista Translock/Quintalock)
                _texto(ws.cell(fila, L["gabinete"]), t["gabinete"])
        return resultado

    @staticmethod
    def _escribir_bitacora_pruebas(ws: Worksheet, tarjetas: List[Dict[str, Any]], filas_prod: Dict[str, int],
                                   omitidas: List[str]) -> int:
        """Reescribe la bitácora masiva J:AA con el estado actual de la BD (la BD es la fuente de verdad).
        Solo se registran estados distintos de PENDIENTE (las fórmulas devuelven PENDIENTE por defecto)."""
        for r in range(LOG_FILA_MIN, LOG_FILA_MAX + 1):
            for col in range(LOG_COL_FECHA, LOG_COL_ID_ULT + 1):
                ws.cell(r, col).value = None

        hoy = date.today()
        fila = LOG_FILA_MIN
        escritas = 0
        for clave in ETAPA_KEYS:
            for estado in ("OK", "FALLA", "RETRABAJO", "NO APLICA"):
                ids = sorted(t["id_tarjeta_num"] for t in tarjetas
                             if t["id_tarjeta_num"] in filas_prod and t.get(clave) == estado)
                for i in range(0, len(ids), IDS_POR_FILA):
                    if fila > LOG_FILA_MAX:
                        omitidas.extend(ids[i:])
                        break
                    ws.cell(fila, LOG_COL_FECHA).value = hoy
                    ws.cell(fila, LOG_COL_FECHA).number_format = "yyyy-mm-dd"
                    ws.cell(fila, LOG_COL_PROCESO).value = ETAPA_LABEL[clave]
                    ws.cell(fila, LOG_COL_ESTATUS).value = estado
                    for j, id_num in enumerate(ids[i:i + IDS_POR_FILA]):
                        ws.cell(fila, LOG_COL_ID1 + j).value = id_num  # texto, igual que Producción!A
                    fila += 1
                    escritas += 1
        return escritas

    # ------------------------------------------------------------------ verificación
    def verify_excel_integrity(self, excel_path: str) -> Dict[str, Any]:
        """
        Valida que ninguna fórmula se haya roto o corrompido y que no se hayan perdido validaciones de
        datos, reglas de formato condicional ni tablas respecto a la plantilla maestra.
        """
        path = Path(excel_path)
        if not path.exists():
            raise FileNotFoundError(f"Archivo Excel no encontrado para verificar: {excel_path}")

        wb = openpyxl.load_workbook(str(path), data_only=False)

        total_formulas = 0
        formulas_by_sheet: Dict[str, int] = {}
        corrupted_cells: List[Dict[str, Any]] = []
        errors_found: List[str] = []

        for req in ["Producción", "Catálogo PCB", "Pruebas", "Etiquetas"]:
            try:
                get_sheet_by_name(wb, req)
            except KeyError:
                errors_found.append(f"Falta la hoja obligatoria '{req}'.")

        for sname in wb.sheetnames:
            ws = wb[sname]
            f_count = 0
            for row in ws.iter_rows():
                for cell in row:
                    val = cell.value
                    if val is None:
                        continue
                    val_str = val.text if hasattr(val, "text") else str(val)
                    if val_str.startswith("=") or hasattr(val, "text"):
                        f_count += 1
                        total_formulas += 1
                        for err_code in EXCEL_ERROR_CODES:
                            if err_code in val_str:
                                corrupted_cells.append({"sheet": sname, "cell": cell.coordinate, "formula": val_str, "error": err_code})
                    elif val_str in EXCEL_ERROR_CODES:
                        corrupted_cells.append({"sheet": sname, "cell": cell.coordinate, "value": val_str, "error": val_str})
            formulas_by_sheet[sname] = f_count

        missing_key_formulas: List[str] = []
        try:
            ws_prod = get_sheet_by_name(wb, "Producción")
            ws_cat = get_sheet_by_name(wb, "Catálogo PCB")
            ws_pruebas = get_sheet_by_name(wb, "Pruebas")
            ws_etiquetas = get_sheet_by_name(wb, "Etiquetas")
            claves = [(ws_prod, "Producción", ["C2", "F2"]), (ws_cat, "Catálogo PCB", ["D3", "I3"] + (["M3", "O3"] if _catalogo_tiene_r3(ws_cat) else [])),
                      (ws_pruebas, "Pruebas", ["A2", "B2", "C2", "D2", "E2", "F2", "G2"]), (ws_etiquetas, "Etiquetas", ["E3"])]
            for ws, nombre, celdas in claves:
                for ref in celdas:
                    v = ws[ref].value
                    texto = v.text if hasattr(v, "text") else str(v or "")
                    if not texto.startswith("="):
                        missing_key_formulas.append(f"{nombre}!{ref} perdió su fórmula.")
        except KeyError:
            pass

        # Estructura vs plantilla maestra
        estructura_ok, estructura_detalle = True, []
        try:
            plantilla = _totales(structure_counts(str(self.get_template_path())))
            actual = _totales(structure_counts(str(path)))
            for hoja, c in plantilla.items():
                for clave, valor in c.items():
                    if actual.get(hoja, {}).get(clave, 0) < valor:
                        estructura_ok = False
                        estructura_detalle.append(f"Hoja '{hoja}': {clave} {actual.get(hoja, {}).get(clave, 0)} < plantilla {valor}.")
        except FileNotFoundError:
            pass

        is_valid = not corrupted_cells and not missing_key_formulas and not errors_found and estructura_ok
        if is_valid:
            summary = f"Verificación exitosa: {total_formulas} fórmulas intactas, validaciones y formatos completos. 0 corrupciones."
        else:
            summary = (f"Fallas de integridad: {len(corrupted_cells)} celdas corruptas, {len(missing_key_formulas)} fórmulas clave "
                       f"faltantes, {len(estructura_detalle)} diferencias de estructura.")

        return {
            "is_valid": is_valid,
            "excel_path": str(path.resolve()),
            "total_formulas": total_formulas,
            "formulas_by_sheet": formulas_by_sheet,
            "corrupted_cells": corrupted_cells,
            "missing_key_formulas": missing_key_formulas,
            "estructura_ok": estructura_ok,
            "estructura_detalle": estructura_detalle,
            "errors": errors_found,
            "summary": summary,
        }
