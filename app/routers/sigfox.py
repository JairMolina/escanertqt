"""API del módulo Skudo Sigfox (v1.4.33): misma forma que /api/speedlocker (rutas, parámetros y JSON), solo cambia el prefijo
y el nombre de la placa. El consultor solo lee (lo aplica el middleware de roles)."""
from typing import List, Literal, Optional

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from app.routers.auth import usuario_actual
from app.services import sigfox as svc

router = APIRouter(prefix="/api/sigfox", tags=["Skudo Sigfox"])


class EscaneoSl(BaseModel):
    codigo: str = Field(..., max_length=200)
    lote: str = Field("", max_length=60)


class AltaManual(BaseModel):
    version: str = Field(..., min_length=1, max_length=10)
    serie: str = Field(..., min_length=1, max_length=10)
    lote: str = Field("", max_length=60)


class FirmwareSl(BaseModel):
    firmware: Optional[str] = Field(None, max_length=60)


class EdicionSl(BaseModel):
    version: Optional[str] = Field(None, max_length=10)
    serie: Optional[str] = Field(None, max_length=10)
    lote: Optional[str] = Field(None, max_length=60)
    estado: Optional[str] = Field(None, max_length=20)
    nota: Optional[str] = Field(None, max_length=500)


class RenombrarLote(BaseModel):
    de: str = Field(..., max_length=60)
    a: str = Field(..., max_length=60)


class MasaSl(BaseModel):
    ids: List[int] = Field(..., min_length=1, max_length=5000)
    accion: Literal["firmware", "version", "lote", "estado", "eliminar"]
    valor: Optional[str] = Field(None, max_length=60)


def _http(e: svc.SigfoxError) -> HTTPException:
    if isinstance(e, svc.NoEncontrada):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    if isinstance(e, svc.Duplicada):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return HTTPException(status_code=422, detail=str(e))


async def _ejecutar(fn, *args):
    try:
        return await run_in_threadpool(fn, *args)
    except svc.SigfoxError as e:
        raise _http(e)


def _email(request: Request) -> Optional[str]:
    return usuario_actual(request).get("email")


@router.post("/escanear", summary="Registrar una placa Skudo Sigfox por su QR (idempotente)")
async def escanear(body: EscaneoSl, request: Request):
    return await run_in_threadpool(svc.escanear, body.codigo, body.lote, _email(request))


# Rutas fijas antes de /pcb/{pcb_id}
@router.post("/pcb/manual", status_code=status.HTTP_201_CREATED, summary="Alta manual por versión y serie")
async def alta_manual(body: AltaManual, request: Request):
    return {"pcb": await _ejecutar(svc.alta_manual, body.version, body.serie, body.lote, _email(request))}


@router.post("/pcb/masa", summary="Acción sobre varias placas (todo o nada)")
async def masa(body: MasaSl, request: Request):
    return await _ejecutar(svc.masa, body.ids, body.accion, body.valor, _email(request))


@router.get("/pcb/por-codigo", summary="Placa por QR, nombre o serie, con su historial")
async def por_codigo(codigo: str = Query(..., min_length=1, max_length=200)):
    return await _ejecutar(svc.por_codigo, codigo)


@router.get("/pcb", summary="Placas Skudo Sigfox registradas (más recientes primero)")
async def listar(q: Optional[str] = Query(None, max_length=100), estado: Optional[str] = Query(None, max_length=20),
                 version: Optional[str] = Query(None, max_length=10), firmware: Optional[str] = Query(None, max_length=60),
                 lote: Optional[str] = Query(None, max_length=60), limit: int = Query(500, ge=1, le=5000)):
    return await _ejecutar(svc.listar, lote, limit, q, estado, version, firmware)


@router.get("/eventos", summary="Movimientos Skudo Sigfox (filtrados y paginados)")
async def eventos(accion: Optional[str] = Query(None, max_length=20), q: Optional[str] = Query(None, max_length=100),
                  desde: Optional[str] = Query(None, max_length=10), hasta: Optional[str] = Query(None, max_length=10),
                  limit: int = Query(200, ge=1, le=2000), offset: int = Query(0, ge=0)):
    return await _ejecutar(svc.eventos, accion, q, desde, hasta, limit, offset)


@router.get("/lotes", summary="Lotes con conteos por estado")
async def lotes():
    return await _ejecutar(svc.lotes)


@router.post("/lotes/renombrar", summary="Renombrar un lote (todas sus placas)")
async def renombrar_lote(body: RenombrarLote, request: Request):
    return await _ejecutar(svc.renombrar_lote, body.de, body.a, _email(request))


@router.get("/exportar", summary="Exportar placas y movimientos a Excel (.xlsx)")
async def exportar(q: Optional[str] = Query(None, max_length=100), estado: Optional[str] = Query(None, max_length=20),
                   version: Optional[str] = Query(None, max_length=10), firmware: Optional[str] = Query(None, max_length=60),
                   lote: Optional[str] = Query(None, max_length=60)):
    datos = await _ejecutar(svc.exportar_xlsx, q, estado, version, firmware, lote)
    nombre = f"SkudoSigfox_placas_{datetime.now():%Y%m%d}.xlsx"
    return Response(content=datos, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{nombre}"', "Cache-Control": "no-store"})


@router.put("/pcb/{pcb_id}/firmware", summary="Asignar o quitar firmware")
async def firmware(pcb_id: int, body: FirmwareSl, request: Request):
    return {"pcb": await _ejecutar(svc.poner_firmware, pcb_id, body.firmware, _email(request))}


@router.patch("/pcb/{pcb_id}", summary="Editar versión, serie, lote, estado o nota")
async def editar(pcb_id: int, body: EdicionSl, request: Request):
    return {"pcb": await _ejecutar(svc.editar, pcb_id, body.model_dump(exclude_none=True), _email(request))}


@router.delete("/pcb/{pcb_id}", summary="Eliminar una placa")
async def eliminar(pcb_id: int, request: Request):
    return await _ejecutar(svc.eliminar, pcb_id, _email(request))


@router.get("/resumen", summary="Conteos por estado, versión, firmware y lote")
async def resumen():
    return await _ejecutar(svc.resumen)
