"""Área de administración protegida con contraseña (docs/SPEC_v2.md §Admin).

Autenticación: POST /api/admin/login -> token (cabecera `X-Admin-Token`, caduca a los 30 min). Toda acción destructiva
hace antes un respaldo automático de la BD, deja registro en la bitácora, emite `ADMIN_CAMBIO` por WebSocket y devuelve
el nombre del respaldo.
"""
import logging
import os
import shutil
import sqlite3
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Query, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from app.config import settings
from app.database import admin_ops, db
from app.database.db import NoEncontradoError
from app.database.models import MESES_ES
from app.routers.excel_dymo import excel_engine, ruta_permitida
from app.routers.ws import manager
from app.services import admin_auth, correo, usuarios
from app.services.admin_auth import (
    AdminDeshabilitadoError, BloqueadoError, TokenInvalidoError, MENSAJE_DESHABILITADO,
)
from app.services.excel_sync import ExcelBloqueadoError, ExcelIntegrityError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["Administración"])

MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


# ============================================================================
# Modelos
# ============================================================================
class LoginIn(BaseModel):
    password: str = Field(..., max_length=200)


class CambiarClaveIn(BaseModel):
    actual: str = Field(..., max_length=200)
    nueva: str = Field(..., max_length=200)


class BorrarTarjetasIn(BaseModel):
    ids: List[int] = Field(..., min_length=1, max_length=2000, description="ids internos de tarjeta")
    liberar_pcb: bool = Field(True, description="True: sus PCB vuelven a DISPONIBLE. False: las PCB también se eliminan.")


class BorrarPCBIn(BaseModel):
    ids: List[int] = Field(..., min_length=1, max_length=2000)


class VaciarLoteIn(BaseModel):
    confirmar: str = Field(..., max_length=20, description='Debe ser exactamente "VACIAR"')
    eliminar_pcb: bool = Field(False, description="True: las PCB de sus tarjetas también se eliminan (por defecto vuelven a DISPONIBLE)")


class CorreoPruebaIn(BaseModel):
    para: str = Field(..., max_length=200)
    reply_to: Optional[str] = Field(None, max_length=200)


class ResetIn(BaseModel):
    confirmar: str = Field(..., max_length=30, description='Debe ser exactamente "BORRAR TODO"')


# ============================================================================
# Dependencia de autenticación
# ============================================================================
COOKIE_SESION = "tqt_admin"


def admin_requerido(x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
                    tqt_admin: Optional[str] = Cookie(None, alias=COOKIE_SESION)) -> Dict[str, Any]:
    """Sesión de administrador: cabecera X-Admin-Token (API/admin.js) o cookie HttpOnly (páginas como /monitor)."""
    try:
        return admin_auth.validar_token(x_admin_token or tqt_admin)
    except AdminDeshabilitadoError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=MENSAJE_DESHABILITADO)
    except TokenInvalidoError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


def fijar_cookie(response: Response, token: str) -> None:
    """Cookie de sesión: solo HTTPS, no legible por JS, no se envía desde otros sitios."""
    response.set_cookie(COOKIE_SESION, token, max_age=settings.ADMIN_TOKEN_TTL, httponly=True, secure=True,
                        samesite="strict", path="/")


def _cliente(request: Request) -> str:
    """Clave del limitador: IP + marca anónima del equipo (cookie tqt_cid, la pone /admin). Sin marca válida: cubo compartido de la IP."""
    cid = request.cookies.get("tqt_cid", "")
    return f"{_ip(request)}|{cid if cid.isalnum() and 8 <= len(cid) <= 40 else ''}"


def _ip(request: Request) -> str:
    return request.client.host if request.client else "desconocida"


async def _cambio(accion: str, respaldo: str, **detalle: Any) -> None:
    await manager.broadcast("ADMIN_CAMBIO", {"accion": accion, "respaldo": respaldo, **detalle})


async def _destructiva(motivo: str, verificar, *args):
    """Verifica que el objetivo exista y hace el respaldo ANTES de tocar nada. Devuelve el nombre del respaldo."""
    try:
        if verificar:
            await run_in_threadpool(verificar, *args)
        return await run_in_threadpool(admin_ops.respaldar, motivo)
    except NoEncontradoError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except (OSError, sqlite3.Error) as e:  # sin permiso/espacio en TQT_BACKUP_DIR: NO se borra nada y el mensaje es claro
        logger.error("No se pudo crear el respaldo previo (%s): %s", motivo, e)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="No se pudo crear el respaldo previo, así que no se borró nada. Revisa la carpeta de respaldos (TQT_BACKUP_DIR) y el espacio en disco.")


# ============================================================================
# Sesión
# ============================================================================
@router.get("/estado", summary="¿Está habilitada el área de administración?")
def estado():
    """Público: permite a la interfaz avisar 'admin deshabilitado' sin intentar un login."""
    ok = admin_auth.habilitado()
    return {"habilitado": ok, "mensaje": None if ok else MENSAJE_DESHABILITADO,
            "token_ttl_segundos": settings.ADMIN_TOKEN_TTL}


@router.post("/login", summary="Iniciar sesión de administrador (devuelve un token de 30 minutos)")
async def login(payload: LoginIn, request: Request, response: Response):
    try:
        resultado = await run_in_threadpool(admin_auth.iniciar_sesion, payload.password, _cliente(request))
        fijar_cookie(response, resultado["token"])
        await run_in_threadpool(db.log_evento, "ADMIN_LOGIN", None, _ip(request), "Inicio de sesión", "admin")
        return resultado
    except AdminDeshabilitadoError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=MENSAJE_DESHABILITADO)
    except BloqueadoError as e:
        await run_in_threadpool(db.log_evento, "ADMIN_BLOQUEO", None, _ip(request), f"Bloqueado {e.restante} s por intentos fallidos", "admin")
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(e), headers={"Retry-After": str(e.restante)})
    except PermissionError as e:
        await run_in_threadpool(db.log_evento, "ADMIN_LOGIN_FALLIDO", None, _ip(request), "Contraseña incorrecta", "admin")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


@router.post("/logout", summary="Cerrar sesión: borra la cookie del navegador")
async def logout(request: Request, response: Response):
    response.delete_cookie(COOKIE_SESION, path="/", secure=True, httponly=True, samesite="strict")
    if request.cookies.get(COOKIE_SESION) or request.headers.get("x-admin-token"):
        await run_in_threadpool(db.log_evento, "ADMIN_LOGOUT", None, _ip(request), "Cierre de sesión", "admin")
    return {"ok": True}


@router.post("/cambiar-clave", summary="Cambiar la contraseña de administrador (mínimo 8 caracteres)")
async def cambiar_clave(payload: CambiarClaveIn, request: Request, response: Response, _: Dict = Depends(admin_requerido)):
    """Exige token válido Y la contraseña actual. Invalida los tokens anteriores y devuelve uno nuevo. Los intentos con una
    contraseña actual incorrecta cuentan para el bloqueo por IP."""
    ip = _cliente(request)
    espera = admin_auth.limitador.restante(ip)
    if espera:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(BloqueadoError(espera)),
                            headers={"Retry-After": str(espera)})
    try:
        await run_in_threadpool(admin_auth.cambiar_clave, payload.actual, payload.nueva)
    except PermissionError as e:
        bloqueo = admin_auth.limitador.fallo(ip)
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS if bloqueo else status.HTTP_401_UNAUTHORIZED,
                            detail=str(BloqueadoError(bloqueo)) if bloqueo else str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    await run_in_threadpool(db.log_evento, "ADMIN_CLAVE_CAMBIADA", None, None, "Contraseña de administrador cambiada", "admin")
    nuevo = await run_in_threadpool(admin_auth.emitir_token)
    fijar_cookie(response, nuevo["token"])          # la cookie anterior quedó invalidada con la clave vieja
    return {"mensaje": "Contraseña actualizada.", **nuevo}


# ============================================================================
# Consulta
# ============================================================================
@router.get("/movimientos", summary="Movimientos: qué se hizo (altas, ediciones, eliminaciones, sesiones, Excel), cuándo y quién")
async def movimientos(limite: int = Query(50, ge=1, le=200), desplazamiento: int = Query(0, ge=0, le=1_000_000),
                      categoria: Optional[str] = Query(None, max_length=20), q: Optional[str] = Query(None, max_length=100),
                      desde: Optional[str] = Query(None, max_length=10), hasta: Optional[str] = Query(None, max_length=10),
                      lote_id: Optional[int] = Query(None, ge=1, le=2**31), _: Dict = Depends(admin_requerido)):
    try:
        return await run_in_threadpool(admin_ops.movimientos, limite, desplazamiento, categoria, q, desde, hasta, lote_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/correo/prueba", summary="Enviar un correo de prueba desde el backend (SMTP configurado por variables de entorno)")
async def correo_prueba(payload: CorreoPruebaIn, _: Dict = Depends(admin_requerido)):
    try:
        html = correo.plantilla("Prueba de envío", ["Este es un correo de prueba enviado desde la aplicación Escáner TQT.",
                                                     "Si lo recibiste, el envío de correo del servidor está funcionando."],
                                aviso=("ok", "Configuración de correo verificada."))
        mid = await run_in_threadpool(correo.enviar, payload.para.strip(), "Prueba de envío · Escáner TQT",
                                      "Correo de prueba enviado desde la aplicación Escáner TQT.", html, payload.reply_to)
    except correo.CorreoNoConfigurado as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))
    except Exception as e:  # noqa: BLE001 - SMTP/red: se informa sin exponer credenciales
        logger.warning("Fallo el correo de prueba: %s", e)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"No se pudo enviar: {type(e).__name__}")
    return {"ok": True, "message_id": mid}


# ============================================================================
# Cuentas de usuario (alta por invitación de correo, roles)
# ============================================================================
class CuentaIn(BaseModel):
    email: str = Field(..., max_length=200)
    rol: str = Field(..., max_length=20)


class CuentaCambioIn(BaseModel):
    rol: Optional[str] = Field(None, max_length=20)
    activo: Optional[bool] = None


def _quien(request: Request) -> str:
    try:
        return usuarios.validar_sesion(request.cookies.get(usuarios.COOKIE))["email"]
    except usuarios.SesionInvalidaError:
        return "admin"


def _enlace(request: Request, token: str) -> str:
    """URL pública del enlace: TQT_PUBLIC_URL si está definida; si no, la que usó el administrador (respeta el proxy de Cloudflare)."""
    base = os.getenv("TQT_PUBLIC_URL", "").rstrip("/")
    if not base:
        esquema = request.headers.get("x-forwarded-proto", request.url.scheme).split(",")[0].strip()
        base = f"{esquema}://{request.headers.get('host') or request.url.netloc}"
    return f"{base}/invitacion#{token}"


def _enviar_invitacion(email: str, rol: str, enlace: str, por: str) -> Dict[str, Any]:
    """Envía el correo; si falla, el administrador recibe el enlace para dárselo por otro medio."""
    texto = (f"Hola:\n\n{por} te dio de alta en Escáner TQT con el rol «{rol}».\n\n"
             f"Para activar tu cuenta y elegir tu contraseña abre este enlace (vale 48 horas y se usa una sola vez):\n{enlace}\n\n"
             "Si no esperabas este correo, ignóralo.\n\nInventario TQT")
    html = correo.plantilla("Activa tu cuenta", saludo="Hola:", preencabezado=f"{por} te dio de alta en Escáner TQT",
                            parrafos=[f"{por} te dio de alta en Escáner TQT. Para activar tu cuenta y elegir tu contraseña, usa el botón:"],
                            filas=[("Cuenta", email), ("Rol", rol.capitalize())], boton=("Activar mi cuenta", enlace),
                            aviso=("gris", "El enlace vale 48 horas y se usa una sola vez. Si no esperabas este correo, ignóralo."))
    try:
        correo.enviar(email, "Activa tu cuenta de Escáner TQT", texto, html)
        return {"enviado": True}
    except correo.CorreoNoConfigurado as e:
        return {"enviado": False, "error": str(e), "enlace": enlace}
    except Exception as e:  # noqa: BLE001 - SMTP/red: se informa sin exponer credenciales
        logger.warning("No se pudo enviar la invitación a %s: %s", email, e)
        return {"enviado": False, "error": f"No se pudo enviar el correo ({type(e).__name__}).", "enlace": enlace}


@router.get("/usuarios", summary="Cuentas de usuario con su rol y estado")
async def cuentas(_: Dict = Depends(admin_requerido)):
    return {"items": await run_in_threadpool(usuarios.listar), "roles": list(usuarios.ROLES), "smtp": correo.configurado()}


@router.post("/usuarios", summary="Dar de alta una cuenta y enviarle la invitación por correo")
async def cuenta_alta(payload: CuentaIn, request: Request, _: Dict = Depends(admin_requerido)):
    por = _quien(request)
    try:
        token = await run_in_threadpool(usuarios.crear_invitacion, payload.email, payload.rol, por)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    email = usuarios.normalizar(payload.email)
    r = await run_in_threadpool(_enviar_invitacion, email, payload.rol.lower(), _enlace(request, token), por)
    await run_in_threadpool(db.log_evento, "USUARIO_ALTA", None, email, f"Invitación ({payload.rol.lower()}); correo {'enviado' if r['enviado'] else 'NO enviado'}", por)
    return r


@router.post("/usuarios/{email}/reenviar", summary="Reenviar la invitación (el enlace anterior deja de valer)")
async def cuenta_reenviar(email: str, request: Request, _: Dict = Depends(admin_requerido)):
    por = _quien(request)
    try:
        token = await run_in_threadpool(usuarios.reenviar_invitacion, email)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    rol = next((u["rol"] for u in await run_in_threadpool(usuarios.listar) if u["email"] == usuarios.normalizar(email)), "")
    r = await run_in_threadpool(_enviar_invitacion, usuarios.normalizar(email), rol, _enlace(request, token), por)
    await run_in_threadpool(db.log_evento, "USUARIO_INVITACION", None, usuarios.normalizar(email), "Invitación reenviada", por)
    return r


@router.patch("/usuarios/{email}", summary="Cambiar rol o activar/desactivar una cuenta")
async def cuenta_cambio(email: str, payload: CuentaCambioIn, request: Request, _: Dict = Depends(admin_requerido)):
    try:
        await run_in_threadpool(usuarios.actualizar_cuenta, email, payload.rol, payload.activo)
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    cambios = ", ".join(x for x in (payload.rol and f"rol {payload.rol}", payload.activo is not None and ("activada" if payload.activo else "desactivada")) if x)
    await run_in_threadpool(db.log_evento, "USUARIO_CAMBIO", None, usuarios.normalizar(email), cambios or "sin cambios", _quien(request))
    return {"ok": True}


@router.delete("/usuarios/{email}", summary="Eliminar una cuenta")
async def cuenta_baja(email: str, request: Request, _: Dict = Depends(admin_requerido)):
    try:
        await run_in_threadpool(usuarios.eliminar_cuenta, email)
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    await run_in_threadpool(db.log_evento, "USUARIO_BAJA", None, usuarios.normalizar(email), "Cuenta eliminada", _quien(request))
    return {"ok": True}


@router.get("/resumen", summary="Conteos por lote, tipo y estado, y tamaño de la BD")
def resumen(_: Dict = Depends(admin_requerido)):
    return admin_ops.resumen()


# ============================================================================
# Acciones destructivas (todas con respaldo previo)
# ============================================================================
@router.delete("/tarjetas", summary="Borrar tarjetas elegidas (y sus pruebas)")
async def borrar_tarjetas(payload: BorrarTarjetasIn, _: Dict = Depends(admin_requerido)):
    respaldo = await _destructiva("borrar_tarjetas", admin_ops.verificar_tarjetas, payload.ids)
    res = await run_in_threadpool(admin_ops.borrar_tarjetas, payload.ids, payload.liberar_pcb, respaldo)
    await _cambio("BORRAR_TARJETAS", respaldo, **res)
    return {"respaldo": respaldo, **res}


@router.delete("/pcb", summary="Eliminar PCB del inventario")
async def borrar_pcb(payload: BorrarPCBIn, _: Dict = Depends(admin_requerido)):
    respaldo = await _destructiva("borrar_pcb", admin_ops.verificar_pcb, payload.ids)
    res = await run_in_threadpool(admin_ops.borrar_pcb, payload.ids, respaldo)
    await _cambio("BORRAR_PCB", respaldo, **res)
    return {"respaldo": respaldo, **res}


@router.post("/lote/{lote_id}/vaciar", summary='Vaciar un lote (confirmar: "VACIAR")')
async def vaciar_lote(lote_id: int, payload: VaciarLoteIn, _: Dict = Depends(admin_requerido)):
    if payload.confirmar != "VACIAR":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Confirmación incorrecta: escribe exactamente "VACIAR".')
    lote = await run_in_threadpool(db.get_lote_by_id, lote_id)
    if not lote:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Lote con ID {lote_id} no encontrado.")
    respaldo = await _destructiva("vaciar_lote", None)
    res = await run_in_threadpool(admin_ops.vaciar_lote, lote_id, payload.eliminar_pcb, respaldo)
    await _cambio("VACIAR_LOTE", respaldo, **res)
    return {"respaldo": respaldo, **res}


@router.post("/reset", summary='Borrar tarjetas, pruebas, inventario y bitácora (confirmar: "BORRAR TODO")')
async def reset(payload: ResetIn, _: Dict = Depends(admin_requerido)):
    if payload.confirmar != "BORRAR TODO":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Confirmación incorrecta: escribe exactamente "BORRAR TODO".')
    respaldo = await _destructiva("reset_total", None)
    res = await run_in_threadpool(admin_ops.reset_total, respaldo)
    await _cambio("RESET", respaldo, **res)
    return {"respaldo": respaldo, **res}


# ============================================================================
# Exportación a Excel con la estructura de la plantilla mensual
# ============================================================================
def _raiz_permitida(p: Path) -> bool:
    raices = [settings.EXCEL_DIR.resolve(), settings.BASE_DIR.resolve(), (Path.home() / "Desktop").resolve()]
    return any(p == r or r in p.parents for r in raices)


def _exportar(lote: Dict[str, Any], destino: Path) -> Dict[str, Any]:
    """Copia la plantilla a `destino`, vuelca el lote con el motor con plantilla y verifica la integridad."""
    excel_engine.create_monthly_excel(lote["mes"], lote["anio"], target_path=str(destino), overwrite=True)
    resultado = excel_engine.export_to_excel(str(destino), lote["id"])
    resultado["integridad"] = excel_engine.verify_excel_integrity(str(destino))
    bak = destino.with_name(destino.name + ".bak")
    if bak.exists():
        bak.unlink()
    return resultado


@router.get("/export/excel", summary="Exportar el lote a un Excel con la estructura de la plantilla mensual (descarga)")
async def export_excel(
    lote_id: Optional[int] = Query(None, description="Por defecto el lote activo"),
    ruta: Optional[str] = Query(None, max_length=500, description="Carpeta o archivo .xlsx permitido donde guardarlo (en vez de descargar)"),
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
    tqt_admin: Optional[str] = Cookie(None, alias=COOKIE_SESION),
):
    """Genera una copia nueva desde la plantilla (Producción / Catálogo PCB / Pruebas / Etiquetas con fórmulas intactas) con los
    datos del lote. NO toca el archivo mensual en uso. Sin `ruta` responde el archivo como descarga; con `ruta` lo guarda ahí
    (solo carpetas permitidas) y responde su ubicación.
    v1.3.44: la DESCARGA solo pide sesión de usuario (cualquier rol; el middleware deja pasar este GET). Guardar en una
    carpeta del servidor (`ruta`) escribe en disco: sigue pidiendo la clave de administración."""
    if ruta:
        admin_requerido(x_admin_token, tqt_admin)
    lote =await run_in_threadpool(db.get_lote_by_id, lote_id) if lote_id else await run_in_threadpool(db.get_active_lote)
    if not lote:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lote no encontrado o sin lote activo.")
    nombre = db.archivo_excel_lote(lote)   # v1.3.44: semana/día llevan su código en el nombre

    try:
        if ruta:
            p = Path(ruta).expanduser().resolve()
            if p.suffix.lower() != ".xlsx":  # carpeta: se guarda con el nombre estándar
                if p.exists() and not p.is_dir():
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Indica una carpeta o un archivo .xlsx.")
                p = p / nombre
            if not _raiz_permitida(p.resolve()):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                    detail=f"Ruta fuera de las carpetas permitidas ({settings.EXCEL_DIR}).")
            ruta_permitida(str(p))
            p.parent.mkdir(parents=True, exist_ok=True)
            temporal = Path(tempfile.mkdtemp(prefix="tqt_export_")) / nombre
            try:
                res = await run_in_threadpool(_exportar, lote, temporal)
                shutil.move(str(temporal), str(p))  # el destino no existía o se reemplaza completo, nunca a medias
            finally:
                shutil.rmtree(temporal.parent, ignore_errors=True)
            await run_in_threadpool(db.log_evento, "EXCEL_EXPORTADO", lote["id"], lote["codigo_lote"], f"{res['exported_tarjetas']} tarjetas (guardado en carpeta)", "admin")
            return {"success": True, "ruta": str(p), "filename": p.name, "total_tarjetas": res["exported_tarjetas"],
                    "avisos": res.get("avisos", []), "integridad_valida": res["integridad"]["is_valid"]}

        carpeta = Path(tempfile.mkdtemp(prefix="tqt_export_"))
        destino = carpeta / nombre
        try:
            res = await run_in_threadpool(_exportar, lote, destino)
        except BaseException:
            shutil.rmtree(carpeta, ignore_errors=True)
            raise
        await run_in_threadpool(db.log_evento, "EXCEL_EXPORTADO", lote["id"], lote["codigo_lote"], f"{res['exported_tarjetas']} tarjetas (descarga)", "admin")
        return FileResponse(destino, media_type=MIME_XLSX, filename=nombre, background=BackgroundTask(shutil.rmtree, carpeta, True),
                            headers={"X-Total-Tarjetas": str(res["exported_tarjetas"]),
                                     "X-Integridad-Valida": str(bool(res["integridad"]["is_valid"])).lower()})
    except ExcelBloqueadoError as e:
        raise HTTPException(status_code=status.HTTP_423_LOCKED, detail=str(e))
    except ExcelIntegrityError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
