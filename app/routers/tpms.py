"""v1.4.27: API del módulo TPMS (alta de placas por QR y lista)."""
from typing import Optional

from fastapi import APIRouter, Query, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from app.routers.auth import usuario_actual
from app.services import tpms as svc

router = APIRouter(prefix="/api/tpms", tags=["TPMS"])


class EscaneoTpms(BaseModel):
    codigo: str = Field(..., max_length=200)
    lote: str = Field("", max_length=60)


@router.post("/escanear", summary="Registrar una placa TPMS por su QR (idempotente)")
async def escanear(body: EscaneoTpms, request: Request):
    u = usuario_actual(request)
    return await run_in_threadpool(svc.escanear, body.codigo, body.lote, u.get("email"))


@router.get("/pcb", summary="Placas TPMS registradas (más recientes primero)")
def listar(lote: Optional[str] = Query(None, max_length=60), limit: int = Query(500, ge=1, le=5000)):
    return svc.listar(lote, limit)
