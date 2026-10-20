"""v1.4.12: administración de cuentas por módulo desde el núcleo del portal /inicio.

Usa la sesión normal de usuario (no la clave aparte de /admin): solo cuentas con rol administrador.
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from app import modulos as modulos_cat
from app.database import db
from app.routers.auth import LoginIn, _cliente, _etq, _ip, fijar_sesion, usuario_actual
from app.services import admin_auth as aa
from app.services import correo, usuarios
from app.routers.admin import _enlace, _enviar_invitacion

router = APIRouter(prefix="/api/plataforma", tags=["Plataforma"])


def _admin(request: Request) -> Dict[str, Any]:
    u = usuario_actual(request)
    if u.get("rol") != "administrador":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solo los administradores pueden asignar módulos.",
                            headers={"X-Acceso": "rol"})
    return u


class CuentaModulosIn(BaseModel):
    rol: Optional[str] = Field(None, max_length=20)
    modulos: Optional[List[str]] = Field(None, max_length=30)


class InvitacionIn(BaseModel):
    email: str = Field(..., max_length=254)
    rol: str = Field("general", max_length=20)
    modulos: List[str] = Field(default_factory=list, max_length=30)


class TodosIn(BaseModel):
    activo: bool


def _respuesta() -> Dict[str, Any]:
    catalogo = [{"id": m["id"], "nombre": m["nombre"], "estado": m["estado"], "acento": m["acento"], "icono": m["icono"]}
                for m in modulos_cat.MODULOS]
    cuentas = [{k: u[k] for k in ("email", "rol", "modulos", "activo", "pendiente")} for u in usuarios.listar()]
    return {"modulos": catalogo, "roles": list(usuarios.ROLES), "cuentas": cuentas, "smtp": correo.configurado()}


def _nombres(ids: List[str]) -> List[str]:
    return [m["nombre"] for m in modulos_cat.MODULOS if m["id"] in ids]


@router.post("/invitaciones", summary="Invitar por correo a una cuenta nueva con su rol y sus módulos")
async def invitar(payload: InvitacionIn, request: Request):
    yo = _admin(request)
    try:
        mods = modulos_cat.normalizar_lista(payload.modulos)
        token = await run_in_threadpool(usuarios.crear_invitacion, payload.email, payload.rol, yo["email"], None, None, mods)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    email = usuarios.normalizar(payload.email)
    r = await run_in_threadpool(_enviar_invitacion, email, payload.rol.lower(), _enlace(request, token), yo["email"], _nombres(mods))
    await run_in_threadpool(db.log_evento, "USUARIO_ALTA", None, email,
                            f"Invitación ({payload.rol.lower()}; módulos {','.join(mods) or 'ninguno'}); correo {'enviado' if r['enviado'] else 'NO enviado'}", yo["email"])
    return {**r, **(await run_in_threadpool(_respuesta))}


@router.post("/invitaciones/{email}/reenviar", summary="Reenviar la invitación (el enlace anterior deja de valer)")
async def reenviar(email: str, request: Request):
    yo = _admin(request)
    try:
        token = await run_in_threadpool(usuarios.reenviar_invitacion, email)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    u = next(x for x in await run_in_threadpool(usuarios.listar) if x["email"] == usuarios.normalizar(email))
    r = await run_in_threadpool(_enviar_invitacion, u["email"], u["rol"], _enlace(request, token), yo["email"], _nombres(u["modulos"]))
    await run_in_threadpool(db.log_evento, "USUARIO_INVITACION", None, u["email"], "Invitación reenviada desde el portal", yo["email"])
    return {**r, **(await run_in_threadpool(_respuesta))}


@router.delete("/invitaciones/{email}", summary="Cancelar una invitación pendiente (borra la cuenta que nunca se activó)")
async def cancelar(email: str, request: Request):
    yo = _admin(request)
    u = next((x for x in await run_in_threadpool(usuarios.listar) if x["email"] == usuarios.normalizar(email)), None)
    if not u or not u["pendiente"]:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Esa cuenta no tiene una invitación pendiente.")
    await run_in_threadpool(usuarios.eliminar_cuenta, u["email"])
    await run_in_threadpool(db.log_evento, "USUARIO_INVITACION", None, u["email"], "Invitación cancelada desde el portal", yo["email"])
    return await run_in_threadpool(_respuesta)


@router.post("/entrar", summary="Ingreso de administrador desde el núcleo del portal (solo crea sesión si es administrador)")
async def entrar(payload: LoginIn, request: Request, response: Response):
    try:
        r = await run_in_threadpool(usuarios.iniciar_sesion, payload.email, payload.password, _cliente(request))
    except aa.BloqueadoError as e:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(e), headers={"Retry-After": str(e.restante)})
    except PermissionError as e:
        await run_in_threadpool(db.log_evento, "USUARIO_LOGIN_FALLIDO", None, _ip(request), _etq(payload.email) + " (núcleo I+D)", "sistema")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    u = await run_in_threadpool(usuarios.validar_sesion, r["token"])
    if u["rol"] != "administrador":   # credenciales correctas pero sin permiso: no se abre sesión
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Esta cuenta no es de administrador. Solo un administrador puede gestionar cuentas y módulos.")
    if r["debe_cambiar"]:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Esta cuenta debe cambiar su contraseña: entra primero por la pantalla de inicio de sesión.")
    fijar_sesion(response, r["token"])
    await run_in_threadpool(db.log_evento, "USUARIO_LOGIN", None, r["email"], f"Ingreso de administrador desde el portal ({_ip(request)})", r["email"])
    return {"email": r["email"], "rol": u["rol"]}


@router.get("/cuentas", summary="Cuentas con su rol y sus módulos (solo administradores)")
async def cuentas(request: Request):
    _admin(request)
    return await run_in_threadpool(_respuesta)


@router.patch("/cuentas/{email}", summary="Cambiar rol y/o módulos de una cuenta")
async def cuenta_cambio(email: str, payload: CuentaModulosIn, request: Request):
    yo = _admin(request)
    try:
        await run_in_threadpool(usuarios.actualizar_cuenta, email, payload.rol, None, None, payload.modulos)
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    detalle = "; ".join(x for x in (f"rol {payload.rol}" if payload.rol else "",
                                     "módulos " + (",".join(payload.modulos) or "ninguno") if payload.modulos is not None else "") if x)
    await run_in_threadpool(db.log_evento, "USUARIO_MODULOS", None, usuarios.normalizar(email), detalle, yo["email"])
    return await run_in_threadpool(_respuesta)


@router.post("/modulos/{modulo_id}/todos", summary="Dar o quitar un módulo a todas las cuentas que no son administrador")
async def modulo_todos(modulo_id: str, payload: TodosIn, request: Request):
    yo = _admin(request)
    if modulo_id not in modulos_cat.IDS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No existe ese módulo.")

    def aplicar() -> int:
        n = 0
        for u in usuarios.listar():
            if u["rol"] == "administrador" or (modulo_id in u["modulos"]) == payload.activo:
                continue
            nuevos = u["modulos"] + [modulo_id] if payload.activo else [m for m in u["modulos"] if m != modulo_id]
            usuarios.actualizar_cuenta(u["email"], modulos=nuevos)
            n += 1
        return n

    n = await run_in_threadpool(aplicar)
    await run_in_threadpool(db.log_evento, "MODULO_TODOS", None, modulo_id, f"{'dado a' if payload.activo else 'quitado de'} {n} cuentas", yo["email"])
    return await run_in_threadpool(_respuesta)
