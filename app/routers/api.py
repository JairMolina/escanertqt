"""Rutas de la API REST para Escaner TQT: estado, lotes, tarjetas, estadísticas y Excel.

El inventario de PCB, la recepción, el emparejado y la MAC viven en `app/routers/inventario.py`.
El wizard v1 (/api/scan/validate y /api/scan/pair) se eliminó: las MAC ya no se escanean, se teclean tras programar.
"""
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, Response

from app.services.admin_dep import admin_si_habilitado, admin_token

from app.config import settings
from app.database import db
from app.database.models import LoteCreate, StatsResponse
from app.routers.excel_dymo import ejecutar_sync_excel, excel_engine, ruta_permitida
from app.routers.ws import manager
from app.services import reporte_dia as reporte_dia_svc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["API Producción"])


# ============================================================================
# Estado del Sistema
# ============================================================================
@router.get("/status", summary="Obtener estado del servidor y configuración de red")
def get_system_status():
    """Retorna el estado general, IP detectada, lote activo y conexiones WebSocket."""
    return {
        "status": "online",
        "app_name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "local_ip": settings.LOCAL_IP,
        "https_url": settings.https_url,
        "monitor_url": settings.monitor_url,
        "ws_url": settings.ws_url,
        "active_lote": db.get_active_lote(),
        "ws_clients_connected": manager.count(),
        "server_time": datetime.now().isoformat(),
        "migration_warnings": db.MIGRATION_WARNINGS,
    }


# ============================================================================
# Lotes Mensuales
# ============================================================================
@router.get("/lotes", response_model=List[Dict[str, Any]], summary="Listar todos los lotes")
def list_lotes():
    """Lista todos los lotes mensuales registrados en el sistema."""
    return db.list_lotes()


@router.post("/lotes", summary="Crear un nuevo lote mensual", status_code=status.HTTP_201_CREATED)
async def create_lote(payload: LoteCreate, _: Optional[Dict] = Depends(admin_si_habilitado)):
    """Crea un lote de mes, semana o día y, salvo `crear_excel=false`, su Excel a partir de la plantilla (un archivo por lote)."""
    try:
        norm = db.normalizar_lote(payload.tipo_lote, payload.fecha_inicio, payload.anio, payload.mes)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    codigo = payload.codigo_lote or norm["codigo_lote"]
    if await run_in_threadpool(db.get_lote_by_codigo, codigo):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Ya existe el lote {db.nombre_lote_de(norm)} (código '{codigo}').")

    ruta_excel = payload.ruta_excel
    if ruta_excel:
        ruta_excel = str(ruta_permitida(ruta_excel))  # 400 si es un archivo/carpeta fuera de las zonas permitidas
    excel_error = None
    if payload.crear_excel and not ruta_excel:
        try:
            ruta_excel = await run_in_threadpool(excel_engine.create_monthly_excel, norm["mes"], norm["anio"],
                                                 str(excel_engine.lote_path({**norm, "codigo_lote": codigo})))
        except Exception as e:  # el lote se crea igual; el Excel se generará en la primera sincronización
            excel_error = str(e)
            logger.warning("No se pudo crear el Excel mensual: %s", e)

    try:
        nuevo = await run_in_threadpool(
            db.create_lote, codigo, norm["mes"], norm["anio"], ruta_excel, payload.activo, None, None, norm["tipo_lote"], norm["fecha_inicio"]
        )
    except sqlite3.IntegrityError:  # dos peticiones simultáneas con el mismo código
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Ya existe un lote con el código '{codigo}'.")
    except Exception as e:
        logger.error("Error al crear lote: %s", e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

    nuevo["nombre"] = db.nombre_lote_de(nuevo)
    await run_in_threadpool(db.log_evento, "LOTE_CREADO", nuevo["id"], nuevo["codigo_lote"], f"Lote {nuevo['nombre']} creado{' y activado' if payload.activo else ''}", "supervisor")
    if excel_error:
        nuevo["excel_error"] = excel_error
    if payload.activo:
        await manager.broadcast("LOTE_CAMBIADO", {"lote_activo": nuevo})
    return nuevo


@router.post("/lotes/{lote_id}/activar", summary="Activar un lote mensual")
async def activate_lote(lote_id: int, _: Optional[Dict] = Depends(admin_si_habilitado)):
    """Marca un lote específico como activo para las operaciones actuales."""
    lote = await run_in_threadpool(db.set_active_lote, lote_id)
    if not lote:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Lote con ID {lote_id} no encontrado.")

    await run_in_threadpool(db.log_evento, "LOTE_ACTIVADO", lote_id, lote["codigo_lote"], "Lote activado", "supervisor")
    stats = await run_in_threadpool(db.get_stats, lote_id)
    await manager.broadcast("LOTE_CAMBIADO", {"lote_activo": lote, "stats": stats})
    return {"mensaje": f"Lote '{lote['codigo_lote']}' activado con éxito.", "lote": lote}


# ============================================================================
# Tarjetas de Producción
# ============================================================================
@router.get("/tarjetas", summary="Listar tarjetas del lote activo o filtrado")
def list_tarjetas(
    lote_id: Optional[int] = Query(None, description="ID del lote. Por defecto toma el activo."),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    search: Optional[str] = Query(None, max_length=60, description="Búsqueda por número, nombre de PCB o MAC"),
    estado: Optional[str] = Query(None, max_length=20, description="(heredado) alias de estado_general"),
    estado_general: Optional[str] = Query(None, max_length=20, description="PENDIENTE | EN PROCESO | RETRABAJO | DETENIDO | LIBERADO"),
):
    """Retorna las tarjetas con ranuras R1/R2/R3, sus 5 etapas de prueba y estado_general (paginado)."""
    items, total = db.list_tarjetas(
        lote_id=lote_id, limit=limit, offset=offset, search=search, estado=estado, estado_general=estado_general,
    )
    return {"total": total, "limit": limit, "offset": offset, "items": items}


@router.get("/tarjetas/by-mac/{mac}", summary="Buscar tarjeta por MAC Address")
def get_tarjeta_by_mac(mac: str):
    """Busca la tarjeta (de cualquier lote) cuya R1 o R2 tiene esa MAC."""
    item = db.find_tarjeta_by_mac(mac)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Ninguna tarjeta encontrada con MAC '{mac}'.")
    return item


@router.get("/tarjetas/{tarjeta_id}", summary="Obtener detalle de una tarjeta por ID")
def get_tarjeta(tarjeta_id: int):
    """Consulta la información completa de una tarjeta emparejada."""
    item = db.get_tarjeta_by_id(tarjeta_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Tarjeta con ID {tarjeta_id} no encontrada.")
    return item


# ============================================================================
# Estadísticas
# ============================================================================
@router.get("/stats", response_model=StatsResponse, summary="Obtener estadísticas para pantalla de monitoreo")
def get_statistics(lote_id: Optional[int] = Query(None, description="ID del lote. Por defecto el activo.")):
    """Totales por estado general (LIBERADO/DETENIDO/RETRABAJO/EN PROCESO/PENDIENTE), tarjetas incompletas e inventario."""
    return db.get_stats(lote_id)


# ============================================================================
# Sincronización y Exportación Excel (motor con plantilla)
# ============================================================================
@router.post("/sync/excel", summary="Sincronizar el lote hacia su Excel mensual (alias de /api/excel/sync)")
async def sync_excel(lote_id: Optional[int] = Query(None, description="ID del lote a sincronizar"), _: Optional[Dict] = Depends(admin_si_habilitado)):
    """Alias compatible con el botón del monitor: delega en el motor con plantilla, que preserva
    fórmulas, validaciones y formatos del Excel mensual."""
    resultado = await ejecutar_sync_excel(lote_id, None)
    lote_id_real = resultado["lote_id"]
    nombre = Path(resultado["excel_path"]).name
    return {
        "success": True,
        "mensaje": f"Excel sincronizado con {resultado['exported_tarjetas']} tarjetas.",
        "filename": nombre,
        "total_tarjetas": resultado["exported_tarjetas"],
        "download_url": f"/api/export/excel?lote_id={lote_id_real}",
        **resultado,
    }


@router.get("/export/excel", summary="Descargar el Excel mensual del lote")
def export_excel(lote_id: Optional[int] = Query(None, description="ID del lote a descargar")):
    """Descarga el archivo Excel mensual del lote especificado o activo. v1.3.44: solo pide sesión de usuario (sin clave de admin)."""
    lote = db.get_active_lote() if lote_id is None else db.get_lote_by_id(lote_id)
    if not lote:
        raise HTTPException(status_code=404, detail="Lote no encontrado.")

    ruta = lote.get("ruta_excel")
    if not ruta or not Path(ruta).exists():
        raise HTTPException(status_code=404, detail="El Excel de este lote aún no ha sido generado. Pulsa 'Sincronizar con Excel' primero.")

    return FileResponse(
        path=ruta,
        filename=Path(ruta).name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# ============================================================================
# Reporte de un día: tarjetas completadas y entregadas en una fecha (v1.3.35)
# ============================================================================
def _rango(fecha: Optional[str], desde: Optional[str], hasta: Optional[str]):
    """`fecha` (un día, como en v1.3.35) o `desde`/`hasta` (rango, v1.3.41)."""
    inicio = desde or fecha
    if not inicio:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Indica la fecha o el rango (desde/hasta).")
    return inicio, hasta or inicio


@router.get("/reporte-dia", summary="Tarjetas completadas (fecha de finalizado) y entregadas (fecha real) en una fecha o un rango, de todos los lotes")
async def reporte_dia(fecha: Optional[str] = Query(None, max_length=10, description="AAAA-MM-DD (un día)"),
                      desde: Optional[str] = Query(None, max_length=10, description="AAAA-MM-DD"),
                      hasta: Optional[str] = Query(None, max_length=10, description="AAAA-MM-DD")):
    a, b = _rango(fecha, desde, hasta)
    try:
        return await run_in_threadpool(reporte_dia_svc.tarjetas_del_rango, a, b)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/reporte-dia/excel", summary="Descargar el reporte del día o del rango en Excel")
async def reporte_dia_excel(fecha: Optional[str] = Query(None, max_length=10, description="AAAA-MM-DD (un día)"),
                            desde: Optional[str] = Query(None, max_length=10, description="AAAA-MM-DD"),
                            hasta: Optional[str] = Query(None, max_length=10, description="AAAA-MM-DD")):
    a, b = _rango(fecha, desde, hasta)
    try:
        datos = await run_in_threadpool(reporte_dia_svc.excel_del_rango, a, b)
        nombre = reporte_dia_svc.nombre_archivo(a, b)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return Response(content=datos, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{nombre}"'})
