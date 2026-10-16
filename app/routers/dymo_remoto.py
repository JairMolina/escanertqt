"""v1.4.2: DYMO compartida (agente en Raspberry Pi). Operadores con sesión encolan; el agente usa su token Bearer."""

import asyncio, re
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.routers.excel_dymo import NOMBRE_R3, NUMERO_CABLE, _exigir_aprobada, _tarjeta_o_404
from app.routers.stm32 import operator, run
from app.services import dymo_remoto as svc
from app.services.dymo_service import DymoService, obtener_formato

router = APIRouter(prefix="/api/dymo/remoto", tags=["DYMO compartida"])
FORMATO = "30334"


class Pedido(BaseModel):
    tipo: Literal["tarjeta", "aprobada", "cable", "r3"]
    tarjeta_id: Optional[int] = Field(default=None, gt=0)
    numero: str = Field(default="", max_length=13)
    nombres: List[str] = Field(default_factory=list, max_length=2)
    copias: int = Field(default=1, ge=1, le=20)


class Latido(BaseModel):
    version: str = Field(default="", max_length=40)
    cola: str = Field(default="", max_length=60)
    impresora_ok: bool = False
    detalle: str = Field(default="", max_length=300)


class Resultado(BaseModel):
    estado: Literal["impresa", "error", "desconocido"]
    detalle: str = Field(default="", max_length=500)
    cups_id: str = Field(default="", max_length=64)


def _validar(p: Pedido):
    """Mismas reglas que /api/dymo/*: tarjeta existente, «Aprobada» solo con la última prueba TQT aprobada."""
    if p.tipo in ("tarjeta", "aprobada"):
        if not p.tarjeta_id:
            raise HTTPException(422, "Falta la tarjeta.")
        t = _tarjeta_o_404(p.tarjeta_id)
        if p.tipo == "aprobada":
            _exigir_aprobada(p.tarjeta_id)
        num = str(t.get("id_tarjeta_num") or t["id"])
        return {"tarjeta_id": p.tarjeta_id}, ("Aprobada · " if p.tipo == "aprobada" else "Tarjeta ") + num
    if p.tipo == "cable":
        if not re.fullmatch(NUMERO_CABLE, p.numero):
            raise HTTPException(422, f"Número inválido: {p.numero}")
        return {"numero": p.numero}, "Cable " + p.numero
    if not 1 <= len(p.nombres) <= 2 or not all(re.fullmatch(NOMBRE_R3, n) for n in p.nombres):
        raise HTTPException(422, "Indica una o dos placas con nombre TQT-Rx-Vxx-0000.")
    return {"nombres": p.nombres}, " + ".join(p.nombres)


def _svg(tipo, params):
    if tipo in ("tarjeta", "aprobada"):
        t = _tarjeta_o_404(params["tarjeta_id"])
        if tipo == "aprobada":
            _exigir_aprobada(params["tarjeta_id"])
        return DymoService.generate_svg_preview(t, FORMATO, guia=False, aprobada=tipo == "aprobada", borde=False)
    if tipo == "cable":
        return DymoService.generate_cable_svg(params["numero"], FORMATO)
    return DymoService.generate_r3_svg(params["nombres"], FORMATO)


# ------------------------------------------------------------------ operadores (sesión)
@router.get("/estado")
def estado():
    return svc.estado()


@router.post("/trabajos")
def encolar(body: Pedido, req: Request):
    params, desc = _validar(body)
    return run(svc.encolar, body.tipo, params, body.copias, desc, operator(req))


@router.get("/trabajos/{jid}")
def trabajo(jid: str):
    return run(svc.trabajo, jid)


@router.post("/trabajos/{jid}/cancelar")
def cancelar(jid: str):
    return run(svc.cancelar, jid)


# ------------------------------------------------------------------ agente (Bearer, sin sesión; solo conexiones salientes)
def agente(authorization: str = Header(default="")):
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Falta credencial de agente DYMO.")
    try:
        return svc.agente_auth(authorization[7:])
    except ValueError:
        raise HTTPException(401, "Credencial de agente DYMO inválida.")


@router.post("/agente/latido")
def latido(body: Latido, ag=Depends(agente)):
    return svc.latido(ag["id"], body.model_dump())


@router.get("/agente/siguiente")
async def siguiente(espera: int = Query(25, ge=0, le=30), ag=Depends(agente)):
    fin = asyncio.get_running_loop().time() + espera
    while True:
        j = await run_in_threadpool(svc.tomar, ag["id"])
        if j:
            f = obtener_formato(FORMATO)
            return {"id": j["id"], "svg_url": f"/api/dymo/remoto/agente/trabajos/{j['id']}/svg", "ancho_mm": f.ancho_mm,
                    "alto_mm": f.alto_mm, "copias": j["copias"], "descripcion": j["descripcion"], "tipo": j["tipo"]}
        if asyncio.get_running_loop().time() >= fin:
            return Response(status_code=204)
        await asyncio.sleep(1)


@router.get("/agente/trabajos/{jid}/svg")
def svg(jid: str, ag=Depends(agente)):
    j = run(svc.del_agente, ag["id"], jid)
    return Response(content=_svg(j["tipo"], j["params"]), media_type="image/svg+xml")


@router.post("/agente/trabajos/{jid}/resultado")
def resultado(jid: str, body: Resultado, ag=Depends(agente)):
    return run(svc.resultado, ag["id"], jid, body.estado, body.detalle, body.cups_id)
