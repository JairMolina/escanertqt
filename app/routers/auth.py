"""Inicio de sesión de la app: correo + contraseña, cookie firmada `tqt_sesion` (HttpOnly, Secure, SameSite=Lax)."""
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from app.config import settings
from app.database import db
from app.services import admin_auth as aa
from app.services import usuarios

router = APIRouter(prefix="/api/auth", tags=["Sesión"])


class LoginIn(BaseModel):
    email: str = Field(..., max_length=200)
    password: str = Field(..., max_length=200)


class CambioClaveIn(BaseModel):
    actual: str = Field(..., max_length=200)
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
