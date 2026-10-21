"""API del módulo TPMS. v1.4.27: alta por QR y lista. v1.4.28: alta manual, búsqueda por código, firmware,
edición, borrado, operaciones en masa (todo o nada) y resumen. El consultor solo lee (lo aplica el middleware de roles)."""
from typing import List, Literal, Optional

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from app.routers.auth import usuario_actual
from app.services import tpms as svc

router = APIRouter(prefix="/api/tpms", tags=["TPMS"])


class EscaneoTpms(BaseModel):
    codigo: str = Field(..., max_length=200)
    lote: str = Field("", max_length=60)


class AltaManual(BaseModel):
    version: str = Field(..., min_length=1, max_length=10)
    serie: str = Field(..., min_length=1, max_length=10)
    lote: str = Field("", max_length=60)


class FirmwareTpms(BaseModel):
    firmware: Optional[str] = Field(None, max_length=60)


class EdicionTpms(BaseModel):
    version: Optional[str] = Field(None, max_length=10)
    serie: Optional[str] = Field(None, max_length=10)
    lote: Optional[str] = Field(None, max_length=60)
    estado: Optional[str] = Field(None, max_length=20)
    nota: Optional[str] = Field(None, max_length=500)


class MasaTpms(BaseModel):
    ids: List[int] = Field(..., min_length=1, max_length=5000)
    accion: Literal["firmware", "version", "lote", "estado", "eliminar"]
    valor: Optional[str] = Field(None, max_length=60)


def _http(e: svc.TpmsError) -> HTTPException:
    if isinstance(e, svc.NoEncontrada):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    if isinstance(e, svc.Duplicada):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return HTTPException(status_code=422, detail=str(e))


async def _ejecutar(fn, *args):
    try:
        return await run_in_threadpool(fn, *args)
    except svc.TpmsError as e:
        raise _http(e)


def _email(request: Request) -> Optional[str]:
    return usuario_actual(request).get("email")


@router.post("/escanear", summary="Registrar una placa TPMS por su QR (idempotente)")
async def escanear(body: EscaneoTpms, request: Request):
    return await run_in_threadpool(svc.escanear, body.codigo, body.lote, _email(request))


# Rutas fijas antes de /pcb/{pcb_id}
@router.post("/pcb/manual", status_code=status.HTTP_201_CREATED, summary="Alta manual por versión y serie")
async def alta_manual(body: AltaManual, request: Request):
    return {"pcb": await _ejecutar(svc.alta_manual, body.version, body.serie, body.lote, _email(request))}


@router.post("/pcb/masa", summary="Acción sobre varias placas (todo o nada)")
async def masa(body: MasaTpms, request: Request):
    return await _ejecutar(svc.masa, body.ids, body.accion, body.valor, _email(request))


@router.get("/pcb/por-codigo", summary="Placa por QR, nombre o serie, con su historial")
async def por_codigo(codigo: str = Query(..., min_length=1, max_length=200)):
    return await _ejecutar(svc.por_codigo, codigo)


@router.get("/pcb", summary="Placas TPMS registradas (más recientes primero)")
async def listar(q: Optional[str] = Query(None, max_length=100), estado: Optional[str] = Query(None, max_length=20),
                 version: Optional[str] = Query(None, max_length=10), firmware: Optional[str] = Query(None, max_length=60),
                 lote: Optional[str] = Query(None, max_length=60), limit: int = Query(500, ge=1, le=5000)):
    return await _ejecutar(svc.listar, lote, limit, q, estado, version, firmware)


@router.put("/pcb/{pcb_id}/firmware", summary="Asignar o quitar firmware")
async def firmware(pcb_id: int, body: FirmwareTpms, request: Request):
    return {"pcb": await _ejecutar(svc.poner_firmware, pcb_id, body.firmware, _email(request))}


@router.patch("/pcb/{pcb_id}", summary="Editar versión, serie, lote, estado o nota")
async def editar(pcb_id: int, body: EdicionTpms, request: Request):
    return {"pcb": await _ejecutar(svc.editar, pcb_id, body.model_dump(exclude_none=True), _email(request))}


@router.delete("/pcb/{pcb_id}", summary="Eliminar una placa")
async def eliminar(pcb_id: int, request: Request):
    return await _ejecutar(svc.eliminar, pcb_id, _email(request))


@router.get("/resumen", summary="Conteos por estado, versión, firmware y lote")
async def resumen():
    return await _ejecutar(svc.resumen)
