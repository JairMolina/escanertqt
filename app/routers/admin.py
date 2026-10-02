"""Área de administración protegida con contraseña (docs/SPEC_v2.md §Admin).

Autenticación: POST /api/admin/login -> token (cabecera `X-Admin-Token`, caduca a los 30 min). Toda acción destructiva
hace antes un respaldo automático de la BD, deja registro en la bitácora, emite `ADMIN_CAMBIO` por WebSocket y devuelve
el nombre del respaldo.
"""
import logging
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
from app.services import admin_auth
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
    _: Dict = Depends(admin_requerido),
):
    """Genera una copia nueva desde la plantilla (Producción / Catálogo PCB / Pruebas / Etiquetas con fórmulas intactas) con los
    datos del lote. NO toca el archivo mensual en uso. Sin `ruta` responde el archivo como descarga; con `ruta` lo guarda ahí
    (solo carpetas permitidas) y responde su ubicación."""
    lote = await run_in_threadpool(db.get_lote_by_id, lote_id) if lote_id else await run_in_threadpool(db.get_active_lote)
    if not lote:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lote no encontrado o sin lote activo.")
    nombre = f"Control_Produccion_TQT_{MESES_ES[lote['mes'] - 1]}_{lote['anio']}.xlsx"

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
