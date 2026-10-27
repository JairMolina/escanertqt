"""v1.4.xx · API de Pruebas automáticas: campañas de resistencia de firmware en UN banco, la Raspberry (Linux)."""

import time
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.routers.stm32 import operator, run
from app.routers.test_station import texto_log, zip_agente
from app.services import pruebas_auto as svc
from app.services import test_station as ts

router = APIRouter(prefix="/api/pruebas-auto", tags=["Pruebas automáticas"])


def _txt(texto, nombre):
    return Response(texto, media_type="text/plain; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{nombre}"', "Cache-Control": "no-store"})


class Agente(BaseModel):
    puerto_serie: str | None = Field(default=None, max_length=120, pattern=r"^/dev/[A-Za-z0-9_./:+-]+$")


class Puerto(BaseModel):
    accion: Literal["conectar", "desconectar"]
    puerto: str = Field(default="", max_length=100, pattern=r"^$|^/dev/[A-Za-z0-9_./:+-]+$")


class Campana(BaseModel):
    nombre: str = Field(min_length=1, max_length=80)
    firmware: str = Field(min_length=1, max_length=80)
    tarjeta_id: int = Field(gt=0)
    ciclos: int = Field(ge=1, le=svc.MAX_CICLOS)
    pausa_s: int = Field(default=60, ge=0, le=svc.MAX_PAUSA_S)
    detener_en_falla: bool = True
    physical_confirmed: bool = False


class Accion(BaseModel):
    accion: Literal["pausar", "reanudar", "detener"]


@router.get("/banco")
def banco():
    return svc.banco()


@router.post("/agente")
def agente(body: Agente, req: Request):
    """ZIP del agente para la Raspberry; lo registra como EL banco del submódulo."""
    st = run(svc.registrar_banco, operator(req))
    return zip_agente(req, st, False, body.puerto_serie, "TQT_Pruebas_Raspberry.zip")


@router.post("/puerto")
def puerto(body: Puerto):
    """Conecta o desconecta el puerto serie de la R1 en la Raspberry (comandos normales de Pruebas TQT)."""
    b = svc.banco()
    if not b["registrado"]:
        raise HTTPException(400, "Primero instala el agente de la Raspberry.")
    if body.accion == "conectar" and not body.puerto:
        raise HTTPException(400, "Elige un puerto.")
    accion = "connect_serial" if body.accion == "conectar" else "disconnect_serial"
    return run(ts.command, b["station"], accion, {"port": body.puerto})


@router.post("/agente/log")
def pedir_log():
    return run(svc.pedir_log)


@router.get("/agente/log")
def ver_log():
    texto, t = svc.log_agente()
    return {"texto": texto, "ts": t}


@router.get("/agente/log.txt")
def bajar_log():
    texto, t = svc.log_agente()
    marca = time.strftime("%Y%m%d-%H%M", time.localtime(t)) if t else "vacio"
    return _txt(texto, f"raspberry_agent_{marca}.txt")


@router.get("/campanas")
def campanas():
    return svc.lista()


@router.post("/campanas")
def crear(body: Campana, req: Request):
    return run(svc.crear, body.nombre, body.firmware, body.tarjeta_id, body.ciclos, body.pausa_s,
               body.detener_en_falla, operator(req), body.physical_confirmed)


@router.get("/campanas/{cid}")
def detalle(cid: str):
    return run(svc.leer, cid)


@router.get("/campanas/{cid}/log.txt")
def log_campana(cid: str):
    d, texto = run(svc.log_campana, cid, texto_log)
    return _txt(texto, f"campana_{cid[:8]}_{len(d['ciclos_detalle'])}ciclos.txt")


@router.get("/ciclos/{jid}/log.txt")
def log_ciclo(jid: str):
    return _txt(run(texto_log, jid), f"ciclo_{jid[:8]}.txt")


@router.post("/campanas/{cid}/accion")
def accion(cid: str, body: Accion, req: Request):
    return run(svc.cambiar, cid, body.accion, operator(req))


@router.get("/tarjetas")
def tarjetas(q: str = ""):
    """Tarjetas armadas (R1+R2 con MAC) que coinciden con el texto: número de tarjeta o nombre de la R1."""
    return svc.buscar_tarjetas(q)
