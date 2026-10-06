"""Inicio de sesión de la app: correo + contraseña, cookie firmada `tqt_sesion` (HttpOnly, Secure, SameSite=Lax)."""
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from app.config import settings
from app.database import db
from app.services import admin_auth as aa
from app.routers.ws import manager
from app.services import correo, usuarios

router = APIRouter(prefix="/api/auth", tags=["Sesión"])


class LoginIn(BaseModel):
    email: str = Field(..., max_length=200)
    password: str = Field(..., max_length=200)


class CambioClaveIn(BaseModel):
    actual: str = Field(..., max_length=200)
    nueva: str = Field(..., max_length=200)


class OlvideIn(BaseModel):
    email: str = Field(..., max_length=200)


class TicketIn(BaseModel):
    ticket: str = Field(..., max_length=100)


class RestablecerIn(BaseModel):
    ticket: str = Field(..., max_length=100)
    codigo: str = Field(..., max_length=12)
    nueva: str = Field(..., max_length=200)


def _etq(email: str) -> str:
    """Correo normalizado para la bitácora; si lo tecleado no parece un correo (p. ej. una contraseña pegada por error) no se guarda."""
    e = usuarios.normalizar(email)
    return e[:80] if usuarios._EMAIL.match(e) else "(formato no válido)"


def _ip(request: Request) -> str:
    return request.client.host if request.client else "?"


def _cliente(request: Request) -> str:
    """IP + marca anónima del equipo (cookie tqt_cid que pone /login): una persona que se equivoca no bloquea a las demás."""
    cid = request.cookies.get("tqt_cid", "")
    return f"{_ip(request)}|{cid[:32]}" if len(cid) >= 16 else _ip(request)


def fijar_sesion(response: Response, token: str) -> None:
    response.set_cookie(usuarios.COOKIE, token, max_age=settings.SESION_HORAS * 3600, httponly=True, secure=True, samesite="lax", path="/")


def borrar_sesion(response: Response) -> None:
    response.delete_cookie(usuarios.COOKIE, path="/", secure=True, httponly=True, samesite="lax")


def usuario_actual(request: Request) -> Dict[str, Any]:
    """Usuario de la sesión vigente o 401."""
    try:
        return usuarios.validar_sesion(request.cookies.get(usuarios.COOKIE))
    except usuarios.SesionInvalidaError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


@router.post("/login", summary="Iniciar sesión con correo y contraseña")
async def login(payload: LoginIn, request: Request, response: Response):
    try:
        r = await run_in_threadpool(usuarios.iniciar_sesion, payload.email, payload.password, _cliente(request))
    except aa.BloqueadoError as e:
        await run_in_threadpool(db.log_evento, "USUARIO_BLOQUEO", None, _ip(request), f"{_etq(payload.email)}: bloqueado {e.restante} s", "sistema")
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(e), headers={"Retry-After": str(e.restante)})
    except PermissionError as e:
        await run_in_threadpool(db.log_evento, "USUARIO_LOGIN_FALLIDO", None, _ip(request), _etq(payload.email), "sistema")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    fijar_sesion(response, r["token"])
    await run_in_threadpool(db.log_evento, "USUARIO_LOGIN", None, r["email"], f"Inicio de sesión desde {_ip(request)}", r["email"])
    return {"email": r["email"], "debe_cambiar": r["debe_cambiar"]}


@router.post("/logout", summary="Cerrar sesión")
async def logout(response: Response):
    borrar_sesion(response)
    return {"ok": True}


@router.get("/yo", summary="Quién tiene la sesión abierta")
async def yo(request: Request):
    return usuario_actual(request)


@router.post("/cambiar-clave", summary="Cambiar la contraseña de la cuenta con sesión abierta")
async def cambiar_clave(payload: CambioClaveIn, request: Request, response: Response):
    u = usuario_actual(request)
    try:
        token = await run_in_threadpool(usuarios.cambiar_clave, u["email"], payload.actual, payload.nueva)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    fijar_sesion(response, token)   # las demás sesiones de la cuenta quedan invalidadas
    await run_in_threadpool(db.log_evento, "USUARIO_CLAVE", None, u["email"], "Contraseña cambiada", u["email"])
    return {"ok": True}


# ---------------------------------------------------------------- olvidé mi contraseña (aprobada por otra cuenta)
@router.post("/olvide", summary="Pedir que otra cuenta apruebe el restablecimiento de mi contraseña")
async def olvide(payload: OlvideIn, request: Request):
    try:
        r = await run_in_threadpool(usuarios.solicitar_restablecimiento, payload.email, _cliente(request))
    except aa.BloqueadoError as e:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(e), headers={"Retry-After": str(e.restante)})
    if r["registrada"]:
        await run_in_threadpool(db.log_evento, "USUARIO_RESET_SOLICITUD", None, r["email"], f"Pidió restablecer su contraseña desde {_ip(request)}", "sistema")
        await manager.broadcast("CLAVE_SOLICITADA", {"email": r["email"]})
    return {"ticket": r["ticket"], "vigencia_seg": r["vigencia_seg"]}   # mismo formato exista o no la cuenta


@router.post("/olvide/estado", summary="Estado de mi solicitud de restablecimiento")
async def olvide_estado(payload: TicketIn):
    return {"estado": await run_in_threadpool(usuarios.estado_solicitud, payload.ticket)}


@router.post("/restablecer", summary="Poner la contraseña nueva con el código que dio la otra cuenta")
async def restablecer(payload: RestablecerIn, request: Request):
    try:
        email = await run_in_threadpool(usuarios.restablecer_clave, payload.ticket, payload.codigo, payload.nueva, _cliente(request))
    except aa.BloqueadoError as e:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(e), headers={"Retry-After": str(e.restante)})
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    await run_in_threadpool(db.log_evento, "USUARIO_CLAVE_RESTABLECIDA", None, email, "Contraseña restablecida con aprobación de otra cuenta", email)
    await run_in_threadpool(correo.avisar_clave_restablecida, email)
    return {"ok": True}


@router.get("/solicitudes", summary="Solicitudes de restablecimiento pendientes de otras cuentas")
async def solicitudes(request: Request):
    u = usuario_actual(request)
    return {"items": await run_in_threadpool(usuarios.solicitudes_pendientes, u["email"])}


async def _resolver(sid: int, request: Request, aprobar: bool):
    u = usuario_actual(request)
    try:
        if aprobar:
            return u, await run_in_threadpool(usuarios.aprobar_solicitud, sid, u["email"])
        return u, {"email": await run_in_threadpool(usuarios.rechazar_solicitud, sid, u["email"])}
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.post("/solicitudes/{sid}/aprobar", summary="Aprobar la solicitud y obtener el código de 6 dígitos")
async def aprobar(sid: int, request: Request):
    u, r = await _resolver(sid, request, True)
    await run_in_threadpool(db.log_evento, "USUARIO_RESET_APROBADO", None, r["email"], f"Aprobó {u['email']}", u["email"])
    return r


@router.post("/solicitudes/{sid}/rechazar", summary="Rechazar la solicitud")
async def rechazar(sid: int, request: Request):
    u, r = await _resolver(sid, request, False)
    await run_in_threadpool(db.log_evento, "USUARIO_RESET_RECHAZADO", None, r["email"], f"Rechazó {u['email']}", u["email"])
    return {"ok": True}


# ---------------------------------------------------------------- invitaciones (públicas: quien es invitado aún no tiene sesión)
class AceptarInvitacionIn(BaseModel):
    token: str = Field(..., max_length=100)
    nueva: str = Field(..., max_length=200)


class VerInvitacionIn(BaseModel):
    token: str = Field(..., max_length=100)


@router.post("/invitacion", summary="Datos de una invitación vigente (correo y rol)")
async def ver_invitacion(payload: VerInvitacionIn):
    try:
        return await run_in_threadpool(usuarios.ver_invitacion, payload.token)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post("/invitacion/aceptar", summary="Elegir contraseña, activar la cuenta y abrir sesión")
async def aceptar_invitacion(payload: AceptarInvitacionIn, request: Request, response: Response):
    try:
        r = await run_in_threadpool(usuarios.aceptar_invitacion, payload.token, payload.nueva)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    fijar_sesion(response, r["token"])
    await run_in_threadpool(db.log_evento, "USUARIO_INVITACION_ACEPTADA", None, r["email"], f"Cuenta activada ({r['rol']}) desde {_ip(request)}", r["email"])
    return {"email": r["email"], "rol": r["rol"]}
