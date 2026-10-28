"""v1.4.51 · API de Pruebas automáticas: campañas de resistencia de firmware en UN banco, la Raspberry (Linux)."""

import time
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.database import db
from app.routers.test_station import (INSTALACION, _version_servidor, config_agente, guardar_instalador_sh,
                                      paquete_agente, texto_log, zip_agente)
from app.services import instalador_linux
from app.services import pruebas_auto as svc
from app.services import test_station as ts
from app.services import usuarios

router = APIRouter(prefix="/api/pruebas-auto", tags=["Pruebas automáticas"])


def _txt(texto, nombre):
    return Response(texto, media_type="text/plain; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{nombre}"', "Cache-Control": "no-store"})


class Agente(BaseModel):
    puerto_serie: str | None = Field(default=None, max_length=120, pattern=r"^/dev/[A-Za-z0-9_./:+-]+$")
    formato: Literal["zip", "sh", "comando"] = "zip"   # v1.4.64


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


def quien(req):
    """(email, es_admin) de la sesión. v1.4.52: cada cuenta tiene su sesión de pruebas."""
    u = usuarios.validar_sesion(req.cookies.get(usuarios.COOKIE))
    return u["email"], u.get("rol") == "administrador"


def run(fn, *args):
    """Como stm32.run, y además «Raspberry ocupada» → 409 con quién la usa (la web muestra la pantalla completa)."""
    try:
        return fn(*args)
    except svc.Ocupado as e:
        raise HTTPException(409, {"mensaje": str(e), "ocupacion": e.info})
    except ValueError as e:
        raise HTTPException(400, str(e))


def _tomar(email, admin):
    with db.transaction() as c:
        svc.tomar(c, email, admin)


@router.get("/banco")
def banco(req: Request):
    email, admin = quien(req)
    return dict(svc.banco(email), yo=email, admin=admin)


@router.post("/banco/tomar")
def tomar(req: Request):
    """Reserva la Raspberry para esta cuenta (al entrar a la página); 409 si la usa otra."""
    svc.init()
    email, admin = quien(req)
    run(_tomar, email, admin)
    return dict(svc.banco(email), yo=email, admin=admin)


@router.post("/banco/liberar")
def liberar(req: Request):
    """Suelta la Raspberry. El administrador puede forzarlo (detiene la campaña de otra cuenta)."""
    return run(svc.liberar, *quien(req))


@router.post("/agente")
def agente(body: Agente, req: Request):
    """Agente de la Raspberry (EL banco del submódulo). v1.4.64: reutiliza la estación del banco (mismo id, token nuevo).
    formato «zip» (como antes), «sh» (instalador autoextraíble) o «comando» (curl … | sh con código de un solo uso)."""
    st = run(svc.registrar_banco, *quien(req))
    INSTALACION.pop(st["id"], None)   # el avance de una instalación anterior no cuenta para esta
    if body.formato == "zip":
        res = zip_agente(req, st, False, body.puerto_serie, "TQT_Pruebas_Raspberry.zip")
        res.headers["X-TQT-Station"] = st["id"]
        return res
    nombre, datos = instalador_linux.construir(paquete_agente(config_agente(req, st, False, body.puerto_serie)), st["id"])
    if body.formato == "sh":
        return Response(datos, media_type="text/x-shellscript", headers={
            "Content-Disposition": f'attachment; filename="{nombre}"', "Cache-Control": "no-store", "X-TQT-Station": st["id"]})
    codigo, expira = guardar_instalador_sh(datos)
    url = f"{str(req.base_url).rstrip('/')}/api/stm32/agent/tests/instalar/{codigo}.sh"
    return {"comando": f"curl -fsSL '{url}' | sh", "expira": expira, "station": st["id"]}


@router.get("/agente/instalacion")
def instalacion(req: Request):
    """v1.4.64: avance del instalador de la Raspberry y si su agente ya está en línea con la versión del servidor."""
    return run(svc.instalacion, INSTALACION, _version_servidor(), *quien(req))


@router.post("/puerto")
def puerto(body: Puerto, req: Request):
    """Conecta o desconecta el puerto serie de la R1 en la Raspberry (comandos normales de Pruebas TQT)."""
    b = svc.banco()
    if not b["registrado"]:
        raise HTTPException(400, "Primero instala el agente de la Raspberry.")
    if body.accion == "conectar" and not body.puerto:
        raise HTTPException(400, "Elige un puerto.")
    run(_tomar, *quien(req))   # el puerto solo lo maneja quien tiene la Raspberry
    accion = "connect_serial" if body.accion == "conectar" else "disconnect_serial"
    return run(ts.command, b["station"], accion, {"port": body.puerto})


@router.post("/agente/log")
def pedir_log(req: Request):
    return run(svc.pedir_log, *quien(req))


@router.get("/agente/log")
def ver_log(req: Request):
    texto, t = run(svc.log_agente, *quien(req))
    return {"texto": texto, "ts": t}


@router.get("/agente/log.txt")
def bajar_log(req: Request):
    texto, t = run(svc.log_agente, *quien(req))
    marca = time.strftime("%Y%m%d-%H%M", time.localtime(t)) if t else "vacio"
    return _txt(texto, f"raspberry_agent_{marca}.txt")


@router.get("/campanas")
def campanas(req: Request):
    return svc.lista(quien(req)[0])


@router.post("/campanas")
def crear(body: Campana, req: Request):
    email, admin = quien(req)
    return run(svc.crear, body.nombre, body.firmware, body.tarjeta_id, body.ciclos, body.pausa_s,
               body.detener_en_falla, email, body.physical_confirmed, admin)


@router.get("/campanas/{cid}")
def detalle(cid: str, req: Request):
    return run(svc.leer, cid, *quien(req))


@router.get("/campanas/{cid}/log.txt")
def log_campana(cid: str, req: Request):
    d, texto = run(svc.log_campana, cid, texto_log, *quien(req))
    return _txt(texto, f"campana_{cid[:8]}_{len(d['ciclos_detalle'])}ciclos.txt")


@router.get("/ciclos/{jid}/log.txt")
def log_ciclo(jid: str, req: Request):
    run(svc.ciclo_permitido, jid, *quien(req))
    return _txt(run(texto_log, jid), f"ciclo_{jid[:8]}.txt")


@router.post("/campanas/{cid}/accion")
def accion(cid: str, body: Accion, req: Request):
    return run(svc.cambiar, cid, body.accion, *quien(req))


@router.get("/tarjetas")
def tarjetas(q: str = ""):
    """Tarjetas armadas (R1+R2 con MAC) que coinciden con el texto: número de tarjeta o nombre de la R1."""
    return svc.buscar_tarjetas(q)
