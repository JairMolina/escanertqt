"""Endpoints REST para Sincronización Excel e Impresión DYMO LabelWriter 550."""
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse

from app.services.admin_dep import admin_si_habilitado, admin_token
from pydantic import BaseModel, Field

from app.config import settings
from app.database import db
from app.routers.ws import manager
from app.services.dymo_service import DymoService, LabelFormat, obtener_formato
from app.services.excel_sync import ExcelBloqueadoError, ExcelIntegrityError, ExcelSyncEngine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Excel & DYMO"])
excel_engine = ExcelSyncEngine()


# ============================================================================
# Esquemas Pydantic
# ============================================================================
class SyncExcelRequest(BaseModel):
    lote_id: Optional[int] = Field(None, description="ID del lote a exportar. Si es nulo, usa el lote activo.")
    excel_path: Optional[str] = Field(None, max_length=500, description="Ruta de destino del Excel. Si es nulo, usa la ruta configurada en el lote.")


SyncRequest = SyncExcelRequest


class CreateMonthlyRequest(BaseModel):
    mes: int = Field(..., ge=1, le=12, description="Mes del lote (1 a 12)")
    anio: int = Field(..., ge=2020, le=2100, description="Año del lote, ej. 2026")
    target_path: Optional[str] = Field(None, max_length=500, description="Ruta personalizada para guardar el archivo")
    activar: bool = Field(True, description="Indica si debe marcarse como activo de inmediato")


CreateMonthlyExcelRequest = CreateMonthlyRequest


class ImportExcelRequest(BaseModel):
    excel_path: Optional[str] = Field(None, max_length=500, description="Ruta del archivo Excel a importar")
    lote_id: Optional[int] = Field(None, description="ID del lote destino en SQLite")


ImportRequest = ImportExcelRequest


# ============================================================================
# Utilidades
# ============================================================================
_NOMBRES_RESERVADOS = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def ruta_permitida(ruta: str, solo_lectura: bool = False) -> Path:
    """Las rutas que llegan del cliente solo pueden ser .xlsx dentro de la carpeta de Excel mensuales,
    del proyecto o del Escritorio del usuario (evita leer/escribir archivos arbitrarios del servidor)."""
    if "\x00" in ruta:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ruta no válida.")
    p = Path(ruta).expanduser().resolve()
    if p.suffix.lower() != ".xlsx":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Solo se permiten archivos .xlsx.")
    # Nombres reservados de Windows (CON, NUL, COM1...): crearían dispositivos/carpetas imposibles de borrar
    if any(parte.split(".")[0].rstrip(" ").upper() in _NOMBRES_RESERVADOS for parte in p.parts[1:]):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nombre de archivo o carpeta no permitido.")
    # La plantilla original nunca se sobrescribe
    if not solo_lectura and settings.TEMPLATES_DIR.resolve() in p.parents:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No se puede escribir sobre la carpeta de plantillas.")
    raices = [settings.EXCEL_DIR.resolve(), settings.BASE_DIR.resolve(), (Path.home() / "Desktop").resolve()]
    if not any(p == r or r in p.parents for r in raices):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ruta fuera de las carpetas permitidas ({settings.EXCEL_DIR}).",
        )
    return p


async def ejecutar_sync_excel(lote_id: Optional[int], excel_path: Optional[str]) -> Dict[str, Any]:
    """Sincroniza el lote hacia su Excel mensual (lo crea desde la plantilla si aún no existe),
    verifica la integridad y notifica por WebSocket. Compartido por /api/excel/sync y /api/sync/excel."""
    if not lote_id:
        active = await run_in_threadpool(db.get_active_lote)
        if not active:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No hay ningún lote activo configurado.")
        lote_id = active["id"]

    lote = await run_in_threadpool(db.get_lote_by_id, lote_id)
    if not lote:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Lote con ID {lote_id} no encontrado.")

    ruta = str(ruta_permitida(excel_path)) if excel_path else lote.get("ruta_excel")
    if ruta and not excel_path:
        ruta_permitida(ruta)  # la ruta guardada en el lote también debe estar en una carpeta permitida (nunca escribir donde sea)
    if not ruta or not Path(ruta).exists():
        try:
            ruta = await run_in_threadpool(excel_engine.create_monthly_excel, lote["mes"], lote["anio"], ruta if excel_path else None)
            await run_in_threadpool(db.set_ruta_excel, lote_id, ruta)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error al generar archivo mensual para el lote: {e}",
            )
    elif ruta != lote.get("ruta_excel"):
        await run_in_threadpool(db.set_ruta_excel, lote_id, ruta)

    try:
        resultado = await run_in_threadpool(excel_engine.export_to_excel, ruta, lote_id)
        integridad = await run_in_threadpool(excel_engine.verify_excel_integrity, ruta)
    except ExcelBloqueadoError as e:
        raise HTTPException(status_code=status.HTTP_423_LOCKED, detail=str(e))
    except ExcelIntegrityError as e:
        logger.error("Sincronización abortada por integridad: %s", e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"{e} El archivo original NO fue modificado.")
    except Exception as e:
        logger.error("Error durante sync_excel: %s", e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Fallo en la sincronización a Excel: {e}")

    resultado["integridad"] = integridad
    await run_in_threadpool(db.log_evento, "EXCEL_SINCRONIZADO", lote_id, lote["codigo_lote"], f"{resultado.get('total_tarjetas', '')} tarjetas", "supervisor")
    await manager.broadcast("SYNC_EXCEL_COMPLETO", {
        "lote_id": lote_id,
        "codigo_lote": lote["codigo_lote"],
        "excel_path": ruta,
        "filename": Path(ruta).name,
        "total_tarjetas": resultado.get("exported_tarjetas"),
        "is_valid": integridad.get("is_valid"),
        "download_url": f"/api/export/excel?lote_id={lote_id}",
    })
    return resultado


# ============================================================================
# Endpoints de Excel
# ============================================================================
@router.post("/excel/sync", summary="Sincronizar lote de SQLite hacia archivo Excel preservando fórmulas")
async def sync_excel(payload: SyncExcelRequest = SyncExcelRequest(), _: Optional[Dict] = Depends(admin_si_habilitado)):
    """
    Vuelca tarjetas, catálogo de PCB y pruebas del lote (o el activo) a su Excel mensual, dejando intactas
    fórmulas, validaciones de datos y formatos. Si el archivo está abierto en Excel responde 423.
    """
    return await ejecutar_sync_excel(payload.lote_id, payload.excel_path)


@router.post("/excel/create-monthly", summary="Crear nuevo archivo mensual de producción basado en plantilla")
async def create_monthly(payload: CreateMonthlyRequest, _: Dict = Depends(admin_token)):
    """
    Copia la plantilla maestra para el mes/año (Control_Produccion_TQT_[Mes]_[Año].xlsx). Si el archivo ya
    existe se reutiliza (NUNCA se sobrescribe). Crea o asocia el registro en 'lotes_mensuales'.
    """
    try:
        destino = str(ruta_permitida(payload.target_path)) if payload.target_path else None
        previo = Path(destino) if destino else excel_engine.monthly_path(payload.mes, payload.anio)
        reutilizado = previo.exists()
        excel_path = await run_in_threadpool(excel_engine.create_monthly_excel, payload.mes, payload.anio, destino)

        codigo_lote = f"{payload.anio}-{payload.mes:02d}"
        lote_existente = await run_in_threadpool(db.get_lote_by_codigo, codigo_lote)

        if lote_existente:
            lote_id = lote_existente["id"]
            await run_in_threadpool(db.set_ruta_excel, lote_id, excel_path)
            if payload.activar:
                await run_in_threadpool(db.set_active_lote, lote_id)
            lote_actualizado = await run_in_threadpool(db.get_lote_by_id, lote_id)
        else:
            lote_actualizado = await run_in_threadpool(
                db.create_lote, codigo_lote, payload.mes, payload.anio, excel_path, payload.activar
            )

        if payload.activar:
            await manager.broadcast("LOTE_CAMBIADO", {"lote_activo": lote_actualizado})

        return {
            "success": True,
            "codigo_lote": codigo_lote,
            "excel_path": excel_path,
            "reutilizado": reutilizado,
            "lote": lote_actualizado,
            "mensaje": (f"Se reutilizó el archivo existente {excel_path}" if reutilizado
                        else f"Archivo mensual creado exitosamente en {excel_path}"),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error en create_monthly: %s", e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error al crear el archivo mensual: {e}")


@router.get("/excel/verify", summary="Reporte de integridad y validación de fórmulas de Excel")
def verify_excel(
    excel_path: Optional[str] = Query(None, max_length=500, description="Ruta al archivo Excel a comprobar"),
    lote_id: Optional[int] = Query(None, description="ID del lote a consultar (usa su ruta_excel)"),
):
    """Verifica fórmulas (#REF!, #NAME?...), fórmulas clave y que no falten validaciones/formatos/tablas."""
    path_to_check = str(ruta_permitida(excel_path, solo_lectura=True)) if excel_path else None
    if not path_to_check and lote_id:
        lote = db.get_lote_by_id(lote_id)
        if lote:
            path_to_check = lote.get("ruta_excel")

    if not path_to_check:
        active = db.get_active_lote()
        if active and active.get("ruta_excel"):
            path_to_check = active["ruta_excel"]
        else:
            path_to_check = str(excel_engine.get_template_path())

    if not path_to_check or not Path(path_to_check).exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Archivo Excel a verificar no encontrado: {path_to_check}")

    try:
        return excel_engine.verify_excel_integrity(path_to_check)
    except Exception as e:
        logger.error("Error en verify_excel: %s", e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error durante la verificación de integridad: {e}")


@router.post("/excel/import", summary="Importar catálogo y tarjetas desde archivo Excel a SQLite")
async def import_excel(payload: ImportExcelRequest, _: Dict = Depends(admin_token)):
    """Carga catálogo PCB, tarjetas (con MAC) y pruebas (bitácora masiva) del Excel hacia SQLite."""
    lote_id = payload.lote_id
    if not lote_id:
        active = db.get_active_lote()
        if not active:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No hay lote activo configurado.")
        lote_id = active["id"]

    excel_path = str(ruta_permitida(payload.excel_path, solo_lectura=True)) if payload.excel_path else None
    if not excel_path:
        lote = db.get_lote_by_id(lote_id)
        excel_path = lote.get("ruta_excel") if lote else None

    if not excel_path or not Path(excel_path).exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Archivo Excel no encontrado: {excel_path}")

    try:
        resultado = await run_in_threadpool(excel_engine.import_from_excel, excel_path, lote_id)
        await manager.broadcast("EXCEL_IMPORTADO", {"lote_id": lote_id})   # las demás pantallas recargan sus datos
        return resultado
    except Exception as e:
        logger.error("Error en import_excel: %s", e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error durante la importación: {e}")


# ============================================================================
# Endpoints de Impresión DYMO LabelWriter 550 (etiqueta principal: 30334 de 57 x 32 mm)
# ============================================================================
FORMATO_DOC = "30334 (principal, 57x32 mm) o 30252 (secundaria, 89x28 mm)"


def _tarjeta_o_404(tarjeta_id: int) -> Dict[str, Any]:
    tarjeta = db.get_tarjeta_by_id(tarjeta_id)
    if not tarjeta:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Tarjeta con ID {tarjeta_id} no encontrada.")
    return tarjeta


def _formato_o_400(label_format: str) -> str:
    try:
        return obtener_formato(label_format).codigo
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/dymo/label/{tarjeta_id}", summary="Datos de la etiqueta DYMO de una tarjeta (trama, QR, XML DYMO Connect y v8)")
def get_dymo_label(tarjeta_id: int, label_format: str = Query("30334", description=FORMATO_DOC)):
    """Trama de 4 líneas, estado de etiqueta (INCOMPLETA/IDENTIFICACION/FINAL), QR, geometría en mm, el `.dymo`
    (`dcd_xml`, para openLabelXml de DYMO Connect) y el `.label` v8 (`dymo_xml`)."""
    fmt = _formato_o_400(label_format)
    return DymoService.get_label_details(_tarjeta_o_404(tarjeta_id), label_format=fmt)


@router.get("/dymo/label/{tarjeta_id}/xml", summary="XML de etiqueta para dymo.label.framework.openLabelXml (DYMO Connect)")
def get_dymo_xml(
    tarjeta_id: int,
    label_format: str = Query("30334", description=FORMATO_DOC),
    tipo: str = Query("dymo", pattern="^(dymo|label)$", description="dymo = DYMO Connect (DCD) · label = DYMO Label v8"),
    texto_como: str = Query("text", pattern="^(text|address)$", description="Objeto para el texto: text (TextObject) o address (AddressObject, el del ejemplo oficial)"),
):
    fmt = _formato_o_400(label_format)
    tarjeta = _tarjeta_o_404(tarjeta_id)
    xml = (DymoService.generate_dcd_xml(tarjeta, fmt, texto_como) if tipo == "dymo"
           else DymoService.generate_dymo_xml(tarjeta, fmt))
    return Response(content=xml, media_type="application/xml; charset=utf-8", headers={"Cache-Control": "no-store"})


def _adjunto(datos: bytes, nombre: str) -> Response:
    return Response(content=datos, media_type="application/octet-stream", headers={
        "Content-Disposition": f'attachment; filename="{nombre}"', "Cache-Control": "no-store"})


@router.get("/dymo/label/{tarjeta_id}/archivo", summary="Descarga la etiqueta como archivo .dymo (abre DYMO Connect) o .label")
def get_dymo_archivo(
    tarjeta_id: int,
    label_format: str = Query("30334", description=FORMATO_DOC),
    tipo: str = Query("dymo", pattern="^(dymo|label)$"),
):
    """`.dymo` (DYMO Connect, LabelWriter 550) con Content-Disposition attachment: Windows lo abre con DYMO Connect."""
    fmt = _formato_o_400(label_format)
    datos, nombre = DymoService.archivo_dymo(_tarjeta_o_404(tarjeta_id), fmt, tipo)
    return _adjunto(datos, nombre)


@router.get("/dymo/lote/archivo", summary="ZIP con un .dymo por tarjeta (ids de tarjeta separados por coma)")
def get_dymo_lote_archivo(
    ids: str = Query(..., min_length=1, max_length=4000, description="ids de tarjeta separados por coma, p. ej. 1,2,3"),
    label_format: str = Query("30334", description=FORMATO_DOC),
    tipo: str = Query("dymo", pattern="^(dymo|label)$"),
):
    fmt = _formato_o_400(label_format)
    try:
        lista = [int(x) for x in ids.split(",") if x.strip()]
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ids debe ser una lista de números separados por coma.")
    if not lista or len(lista) > 500:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Indica entre 1 y 500 ids de tarjeta.")
    tarjetas = [t for t in (db.get_tarjeta_by_id(i) for i in dict.fromkeys(lista)) if t]
    if not tarjetas:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ninguna de las tarjetas indicadas existe.")
    return _adjunto(DymoService.zip_lote(tarjetas, fmt, tipo), "TQT_etiquetas.zip")


@router.get("/dymo/batch-labels", summary="Obtener etiquetas en lote para tarjetas listas")
def get_batch_labels(
    lote_id: Optional[int] = Query(None, description="ID del lote. Por defecto toma el activo."),
    only_ready: bool = Query(True, description="True = solo estado FINAL ('LISTA PARA IMPRIMIR'); False = todas las tarjetas"),
    label_format: str = Query("30334", description=FORMATO_DOC),
    modo: Optional[str] = Query(None, description="final | identificacion | todas (tiene prioridad sobre only_ready)"),
):
    """Cola de etiquetas del lote. `final`: ambas MAC válidas. `identificacion`: además las tarjetas
    con R1 y R2 asignadas aunque falten MAC o pruebas (se imprimen con aviso)."""
    fmt = _formato_o_400(label_format)
    try:
        labels = DymoService.get_batch_labels(lote_id=lote_id, only_ready=only_ready, label_format=fmt, modo=modo)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return {
        "lote_id": lote_id,
        "total": len(labels),
        "only_ready": only_ready,
        "modo": (modo or ("final" if only_ready else "todas")).lower(),
        "label_format": fmt,
        "labels": labels,
    }


@router.get("/dymo/preview/{tarjeta_id}", response_class=HTMLResponse, summary="Vista previa HTML a escala real e impresión directa")
def preview_dymo_label(tarjeta_id: int, label_format: str = Query("30334", description=FORMATO_DOC)):
    """Etiqueta a escala real (57 x 32 mm para el 30334) con la zona segura de 3 mm punteada."""
    fmt = _formato_o_400(label_format)
    return HTMLResponse(content=DymoService.generate_html_preview(_tarjeta_o_404(tarjeta_id), label_format=fmt))


@router.get("/dymo/svg/{tarjeta_id}", summary="Etiqueta como gráfico vectorial SVG a escala real (1 unidad = 1 mm)")
def get_dymo_svg(
    tarjeta_id: int,
    label_format: str = Query("30334", description=FORMATO_DOC),
    guia: bool = Query(True, description="Dibuja la zona segura de 3 mm en línea punteada"),
):
    fmt = _formato_o_400(label_format)
    return Response(content=DymoService.generate_svg_preview(_tarjeta_o_404(tarjeta_id), label_format=fmt, guia=guia),
                    media_type="image/svg+xml")
