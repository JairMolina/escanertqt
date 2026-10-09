"""Inventario de PCB, recepción por QR, emparejado y MAC (docs/SPEC_v2.md §3).

Los resultados de negocio del escaneo continuo (`/pcb/escanear`) viajan siempre en el cuerpo con HTTP 200, de modo que
la cámara nunca recibe errores HTTP en ráfaga. El resto de endpoints usan 400 (dato inválido), 404 y 409 (conflicto).
"""
import logging
import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.concurrency import run_in_threadpool

from app.database import db, inventario as inv
from app.database.db import ConflictoError, NoEncontradoError
from app.database.models import (
    AjustesUpdate,
    AsignarPCB,
    DisolverMasivo,
    ConfirmarRecepcion,
    EmparejarAuto,
    EscanearPCB,
    FallaPCB,
    FirmwareCatalogoIn,
    FirmwareCompilarRequest,
    FirmwareUpdate,
    MACUpdate,
    PCBEditar,
    PCBManual,
    ProgramacionLote,
    ProgramacionUpdate,
    TarjetaDatos,
    TarjetaNueva,
    VersionMasiva,
)
from app.routers.ws import manager
from app.services import firmware_build
from app.services.admin_dep import admin_si_habilitado

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Inventario y Emparejado"])


async def _run(fn, *args, **kwargs):
    """Ejecuta una función de BD en el threadpool traduciendo los errores de negocio a HTTP."""
    try:
        return await run_in_threadpool(fn, *args, **kwargs)
    except NoEncontradoError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ConflictoError as e:  # antes que ValueError: es una subclase
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


def _sesion(request: Request) -> Optional[str]:
    """Marca anónima del equipo (cabecera X-Cliente, la genera la app en cada celular/PC): separa los borradores de recepción."""
    v = re.sub(r"[^A-Za-z0-9_-]", "", request.headers.get("x-cliente", ""))[:40]
    return v or None


def _conteos() -> Dict[str, int]:
    with db.get_db() as c:
        return inv.conteos_recepcion(c)


async def _notificar_tarjeta(tarjeta: Optional[Dict[str, Any]], evento: str = "TARJETA_ACTUALIZADA", mensaje: Optional[str] = None) -> None:
    if not tarjeta:
        return
    stats = await run_in_threadpool(db.get_stats, tarjeta["lote_id"])
    datos = {"tarjeta": tarjeta, "stats": stats}
    if mensaje:
        datos["mensaje"] = mensaje
    await manager.broadcast(evento, datos)


# ============================================================================
# Ajustes
# ============================================================================
@router.get("/ajustes", summary="Ajustes globales (versión por defecto)")
def get_ajustes():
    return inv.get_ajustes()


@router.put("/ajustes", summary="Cambiar la versión por defecto de las altas manuales")
async def put_ajustes(payload: AjustesUpdate):
    await _run(inv.set_version_defecto, payload.version_defecto)
    ajustes = await run_in_threadpool(inv.get_ajustes)
    await manager.broadcast("AJUSTES_ACTUALIZADOS", ajustes)
    return ajustes


# ============================================================================
# Recepción
# ============================================================================
@router.post("/pcb/escanear", summary="Alta automática de una PCB desde el visor de cámara (idempotente)")
async def escanear_pcb(payload: EscanearPCB, request: Request):
    """AGREGADA / DUPLICADA / INVALIDA siempre con HTTP 200. Una PCB nueva queda RECIBIDA (borrador) hasta confirmar."""
    resultado = await run_in_threadpool(inv.escanear_pcb, payload.codigo, payload.operador, payload.tipo_forzado, payload.version,
                                        sesion=_sesion(request))
    if resultado["resultado"] == "AGREGADA":
        await manager.broadcast("PCB_RECIBIDA", {"pcb": resultado["pcb"], "conteos": resultado["conteos"], "operador": payload.operador})
    return resultado


@router.get("/recepcion", summary="Borrador de recepción: PCB recibidas sin confirmar")
def get_recepcion(request: Request):
    return inv.listar_recepcion(sesion=_sesion(request))


@router.post("/recepcion/confirmar", summary="Confirmar el lote de recepción (RECIBIDA -> DISPONIBLE)")
async def confirmar_recepcion(request: Request, payload: ConfirmarRecepcion = ConfirmarRecepcion()):
    resultado = await _run(inv.confirmar_recepcion, payload.ids, payload.nota, payload.operador, sesion=_sesion(request))
    await manager.broadcast("RECEPCION_CONFIRMADA", {**resultado, "operador": payload.operador})
    return resultado


@router.post("/pcb/manual", summary="Alta de PCB sin QR (serie automática o indicada)")
async def pcb_manual(payload: PCBManual, request: Request):
    resultado = await _run(inv.registrar_manual, payload.tipo, payload.version, payload.serie, payload.cantidad, payload.operador,
                           sesion=_sesion(request))
    await manager.broadcast("PCB_RECIBIDA", {"pcb": resultado["pcbs"][-1], "pcbs": resultado["pcbs"],
                                              "conteos": resultado["conteos"], "operador": payload.operador})
    return resultado


# ============================================================================
# Consulta y edición del inventario
# ============================================================================
@router.get("/pcb", summary="Listar PCB del inventario con filtros")
def listar_pcb(
    tipo: Optional[str] = Query(None, max_length=2),
    estado_ciclo: Optional[str] = Query(None, max_length=12),
    q: Optional[str] = Query(None, max_length=60, description="Nombre, serie o MAC"),
    sin_mac: bool = Query(False, description="R1/R2 sin MAC (pendientes de programar)"),
    sin_tarjeta: bool = Query(False, description="PCB que no están en ninguna tarjeta"),
    limit: int = Query(100, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    sin_firmware: bool = Query(False, description="PCB activas sin firmware (con tipo=R3: R3 por programar)"),
):
    try:
        return inv.listar_pcb(tipo, estado_ciclo, q, sin_mac, sin_tarjeta, limit, offset, sin_firmware=sin_firmware)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/pcb/por-codigo", summary="Buscar una PCB (y su tarjeta) por QR o MAC")
async def pcb_por_codigo(codigo: str = Query(..., min_length=1, max_length=300)):
    return await _run(inv.pcb_por_codigo, codigo)


@router.get("/consulta", summary="Ficha completa de una tarjeta/PCB a partir de la etiqueta, el QR o la MAC escaneados")
async def consulta(codigo: str = Query(..., min_length=1, max_length=2000)):
    return await _run(inv.consulta, codigo)


@router.post("/pcb/version", summary="Cambiar la versión de varias PCB a la vez")
async def pcb_version_masiva(payload: VersionMasiva):
    resultado = await _run(inv.cambiar_version_masiva, payload.ids, payload.version, payload.operador)
    if resultado["pcbs"]:
        await manager.broadcast("PCB_ACTUALIZADA", {"pcbs": resultado["pcbs"], "pcb": resultado["pcbs"][-1], "conteos": await run_in_threadpool(_conteos)})
    return resultado


@router.get("/pcb/{pcb_id}", summary="Detalle de una PCB")
async def get_pcb(pcb_id: int):
    p = await run_in_threadpool(inv.get_pcb, pcb_id)
    if not p:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"PCB con ID {pcb_id} no encontrada.")
    return p


@router.patch("/pcb/{pcb_id}", summary="Editar tipo, versión o serie de una PCB")
async def patch_pcb(pcb_id: int, payload: PCBEditar):
    pcb = await _run(inv.editar_pcb, pcb_id, payload.tipo, payload.version, payload.serie, payload.operador,
                      liberar=payload.liberar)
    await manager.broadcast("PCB_ACTUALIZADA", {"pcb": pcb, "conteos": await run_in_threadpool(_conteos)})
    if pcb.get("tarjeta_id"):
        await _notificar_tarjeta(await run_in_threadpool(db.get_tarjeta_by_id, pcb["tarjeta_id"]))
    return pcb


@router.delete("/pcb/{pcb_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Eliminar una PCB (borra RECIBIDA/DISPONIBLE; el resto pasa a BAJA)")
async def delete_pcb(pcb_id: int):
    resultado = await _run(inv.eliminar_pcb, pcb_id)
    await manager.broadcast("PCB_ELIMINADA", resultado)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/pcb/{pcb_id}/mac", summary="Guardar (o borrar) la MAC de una R1/R2 después de programarla (la R3 no lleva MAC)")
async def put_mac(pcb_id: int, payload: MACUpdate):
    pcb = await _run(inv.set_mac, pcb_id, payload.mac, payload.operador)
    await manager.broadcast("PCB_ACTUALIZADA", {"pcb": pcb, "conteos": await run_in_threadpool(_conteos)})
    if pcb.get("tarjeta_id"):
        await _notificar_tarjeta(await run_in_threadpool(db.get_tarjeta_by_id, pcb["tarjeta_id"]))
    return pcb


@router.put("/pcb/{pcb_id}/programacion", summary="Guardar la MAC y el firmware de una R1/R2 recién programada (una sola operación)")
async def put_programacion(pcb_id: int, payload: ProgramacionUpdate):
    pcb = await _run(inv.guardar_programacion, pcb_id, payload.mac, payload.firmware, payload.operador)
    await manager.broadcast("PCB_ACTUALIZADA", {"pcb": pcb, "conteos": await run_in_threadpool(_conteos)})
    if pcb.get("tarjeta_id"):
        await _notificar_tarjeta(await run_in_threadpool(db.get_tarjeta_by_id, pcb["tarjeta_id"]))
    return pcb


@router.get("/programacion/hoy", summary="MAC guardadas hoy por todos los operarios (para el contador de la consola)")
async def get_programacion_hoy():
    return {"guardadas": await _run(inv.contar_macs_hoy)}


@router.post("/firmware/compilar", summary="Compilar el firmware ESP32 de una R1/R2 (con su número) para flashearla por USB desde el navegador")
async def compilar_firmware(payload: FirmwareCompilarRequest):
    try:
        datos, info = await run_in_threadpool(firmware_build.compilar_firmware_meta, payload.tipo, payload.numero)
    except firmware_build.FirmwareBuildError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    nombre = f"{payload.tipo.strip().upper()}_{(payload.numero or 'firmware').strip()}.bin"
    # v1.3.62: trazabilidad para validar después del arranque (nombre BLE esperado, versión y hashes de la fuente)
    extra = {"X-TQT-" + k: str(v) for k, v in {"Nombre-Ble": info.get("nombre_ble", ""), "Firmware": info.get("firmware", ""),
             "Fuente-Sha256": info.get("sha256_fuente", ""), "Copia-Sha256": info.get("sha256_copia", "")}.items() if v}
    return Response(content=datos, media_type="application/octet-stream", headers={"Content-Disposition": f'attachment; filename="{nombre}"', **extra})


@router.post("/programacion/lote", summary="MAC (+ firmware) de muchas R1/R2 de una vez, con resultado por fila (simular = solo validar)")
async def post_programacion_lote(payload: ProgramacionLote):
    res = await _run(inv.programar_lote, [i.model_dump() for i in payload.items], payload.simular, payload.operador)
    if res["guardadas"] and not payload.simular:
        await manager.broadcast("PCB_ACTUALIZADA", {"pcbs": [f["pcb"] for f in res["resultados"] if f["ok"]], "conteos": await run_in_threadpool(_conteos)})
    for f in res["resultados"]:
        f.pop("pcb", None)     # la respuesta lleva solo lo necesario por fila
    return res


@router.put("/pcb/{pcb_id}/firmware", summary="Guardar (o borrar) el firmware de una R1, R2 o R3 (la R3 lleva firmware pero no MAC)")
async def put_firmware(pcb_id: int, payload: FirmwareUpdate):
    pcb = await _run(inv.set_firmware, pcb_id, payload.firmware, payload.operador)
    await manager.broadcast("PCB_ACTUALIZADA", {"pcb": pcb, "conteos": await run_in_threadpool(_conteos)})
    if pcb.get("tarjeta_id"):
        await _notificar_tarjeta(await run_in_threadpool(db.get_tarjeta_by_id, pcb["tarjeta_id"]))
    return pcb


@router.get("/firmware", summary="Catálogo de versiones de firmware (R1 = Principal, R2 = Respaldo, R3)")
async def get_firmware():
    return await _run(inv.listar_firmware)


@router.post("/firmware", summary="Agregar una versión de firmware al catálogo")
async def post_firmware(payload: FirmwareCatalogoIn):
    return await _run(inv.agregar_firmware, payload.rol, payload.version)


@router.delete("/firmware/{rol}/{version}", summary="Quitar una versión del catálogo (requiere sesión de supervisor si hay clave)")
async def delete_firmware(rol: str, version: str, _: Optional[Dict] = Depends(admin_si_habilitado)):
    return await _run(inv.quitar_firmware, rol, version)


@router.post("/pcb/{pcb_id}/falla", summary="Marcar una PCB como FALLA y, si se indica, montar su reemplazo")
async def pcb_falla(pcb_id: int, payload: FallaPCB = FallaPCB()):
    resultado = await _run(inv.marcar_falla, pcb_id, payload.motivo, payload.reemplazo_id, payload.conservar_pruebas, payload.operador)
    conteos = await run_in_threadpool(_conteos)
    await manager.broadcast("PCB_ACTUALIZADA", {"pcb": resultado["pcb"], "reemplazo": resultado["reemplazo"], "conteos": conteos})
    await _notificar_tarjeta(resultado["tarjeta"])
    return resultado


# ============================================================================
# Emparejar
# ============================================================================
@router.get("/emparejar/sugerencias", summary="Series que se pueden emparejar hoy")
async def emparejar_sugerencias(lote_id: Optional[int] = Query(None), r3: str = Query("manual", pattern="^(manual|auto)$")):
    return await _run(inv.sugerencias, lote_id, r3 == "auto")


@router.post("/emparejar/auto", summary="Crear tarjetas con las series completas (R1+R2 del mismo número)")
async def emparejar_auto(payload: EmparejarAuto = EmparejarAuto()):
    resultado = await _run(inv.emparejar_auto, payload.lote_id, payload.series, payload.operador,
                         r3_auto=payload.r3 == "auto")
    for t in resultado["creadas"]:
        await _notificar_tarjeta(t, "TARJETA_EMPAREJADA", f"Tarjeta #{t['id_tarjeta_num']} emparejada.")
    return resultado


@router.post("/tarjetas", status_code=status.HTTP_201_CREATED, summary="Armar una tarjeta a mano (permite tarjetas impares)")
async def crear_tarjeta(payload: TarjetaNueva):
    tarjeta = await _run(inv.crear_tarjeta, payload.lote_id, payload.id_tarjeta_num, payload.r1_id, payload.r2_id,
                         payload.r3_id, payload.operador)
    await _notificar_tarjeta(tarjeta, "TARJETA_EMPAREJADA", f"Tarjeta #{tarjeta['id_tarjeta_num']} emparejada.")
    return tarjeta


@router.patch("/tarjetas/{tarjeta_id}", summary="Firmware, semana y fechas de una tarjeta")
async def patch_tarjeta(tarjeta_id: int, payload: TarjetaDatos):
    datos = payload.model_dump(exclude={"operador"}, exclude_none=True)
    tarjeta = await _run(inv.actualizar_datos_tarjeta, tarjeta_id, datos, payload.operador)
    await _notificar_tarjeta(tarjeta)
    return tarjeta


@router.put("/tarjetas/{tarjeta_id}/asignar", summary="Asignar, reemplazar o liberar la PCB de una ranura")
async def asignar_pcb(tarjeta_id: int, payload: AsignarPCB):
    tarjeta = await _run(inv.asignar_pcb, tarjeta_id, payload.ranura, payload.pcb_id, payload.marcar_falla,
                         payload.conservar_pruebas, payload.operador)
    await _notificar_tarjeta(tarjeta)
    return tarjeta


@router.post("/tarjetas/disolver", summary="Desemparejar varias tarjetas (elegidas o todas las del lote)")
async def disolver_tarjetas(payload: DisolverMasivo):
    r = await _run(inv.disolver_masivo, payload.ids, payload.todas, payload.lote_id, payload.forzar, payload.operador)
    lotes = {d["lote_id"] for d in r["disueltas"]}
    for lid in lotes:
        stats = await run_in_threadpool(db.get_stats, lid)
        await manager.broadcast("TARJETA_ACTUALIZADA", {"eliminada": True, "masiva": True, "lote_id": lid, "stats": stats})
    return r


@router.delete("/tarjetas/{tarjeta_id}", summary="Disolver una tarjeta y liberar sus PCB")
async def disolver_tarjeta(tarjeta_id: int, forzar: bool = Query(False)):
    resultado = await _run(inv.disolver_tarjeta, tarjeta_id, forzar)
    stats = await run_in_threadpool(db.get_stats, resultado["lote_id"])
    await manager.broadcast("TARJETA_ACTUALIZADA", {"eliminada": True, **resultado, "stats": stats})
    return resultado
