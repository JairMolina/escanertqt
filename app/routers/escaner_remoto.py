"""Escáner remoto (v1.3.43): el celular se vincula a la consola de escritorio con un QR y le envía lo que escanea.

Flujo: la consola pide una sesión (POST /api/escaner/sesion) y muestra el QR con `/escaner?s=<token>`. El celular
(con su propia sesión iniciada) abre esa página, se une (POST /api/escaner/<token>/unir) y cada lectura la manda con
POST /api/escaner/<token>/codigo. El servidor la reenvía por WebSocket como ESCANEO_REMOTO con el `id` PÚBLICO de la
sesión (nunca el token): solo quien tiene el token (el que vio el QR) puede enviar códigos a esa consola.
Las sesiones viven en memoria (un solo proceso) y caducan tras 12 h sin uso.
"""
import secrets
import time
from threading import Lock
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from app.routers.ws import manager
from app.services import usuarios

router = APIRouter(prefix="/api/escaner", tags=["Escáner remoto"])

TTL_SEG = 12 * 3600
MAX_SESIONES = 200
_sesiones: Dict[str, Dict[str, Any]] = {}
_lock = Lock()


class CodigoIn(BaseModel):
    codigo: str = Field(..., min_length=1, max_length=2000)


class SeccionIn(BaseModel):
    seccion: str = Field("", max_length=40)
    titulo: str = Field("", max_length=80)


class ResultadoIn(BaseModel):
    n: int = Field(0, ge=0)
    ok: bool = True
    texto: str = Field("", max_length=300)


MAX_GUARDADOS = 50


def _limpiar(ahora: float) -> None:
    for tok in [t for t, s in _sesiones.items() if ahora - s["uso"] > TTL_SEG]:
        _sesiones.pop(tok, None)


def _sesion(token: str) -> Dict[str, Any]:
    with _lock:
        ahora = time.time()
        _limpiar(ahora)
        s = _sesiones.get(token or "")
        if not s:
            raise HTTPException(404, "La vinculación ya no existe o caducó. Vuelve a escanear el QR de la consola.")
        s["uso"] = ahora
        return s


def _publica(s: Dict[str, Any]) -> Dict[str, Any]:
    return {"id": s["id"], "seccion": s["seccion"], "titulo": s["titulo"], "moviles": s["moviles"], "n": s["n"]}


async def _usuario(request: Request) -> str:
    try:
        u = await run_in_threadpool(usuarios.validar_sesion, request.cookies.get(usuarios.COOKIE))
        return str(u.get("email") or "")
    except Exception:  # noqa: BLE001 (el middleware ya exigió sesión; el nombre es solo informativo)
        return ""


@router.post("/sesion", summary="Crear una vinculación para la consola (devuelve el token del QR)")
async def crear_sesion(datos: Optional[SeccionIn] = None):
    with _lock:
        ahora = time.time()
        _limpiar(ahora)
        if len(_sesiones) >= MAX_SESIONES:   # se descarta la más vieja
            _sesiones.pop(min(_sesiones, key=lambda t: _sesiones[t]["uso"]), None)
        token = secrets.token_urlsafe(18)
        s = {"id": secrets.token_hex(6), "creada": ahora, "uso": ahora, "seccion": (datos.seccion if datos else ""),
             "titulo": (datos.titulo if datos else ""), "moviles": 0, "n": 0, "ultimo": None, "codigos": [], "res": {}}
        _sesiones[token] = s
    return {"token": token, "id": s["id"], "ruta": f"/escaner?s={token}", "caduca_seg": TTL_SEG}


@router.get("/{token}", summary="Estado de una vinculación")
async def estado(token: str):
    return _publica(_sesion(token))


@router.post("/{token}/seccion", summary="La consola avisa en qué sección está")
async def seccion(token: str, datos: SeccionIn):
    s = _sesion(token)
    s["seccion"], s["titulo"] = datos.seccion, datos.titulo
    await manager.broadcast("ESCANER_SECCION", {"id": s["id"], "seccion": s["seccion"], "titulo": s["titulo"]})
    return _publica(s)


@router.post("/{token}/unir", summary="El celular se une a la vinculación")
async def unir(token: str, request: Request):
    s = _sesion(token)
    s["moviles"] += 1
    await manager.broadcast("ESCANER_VINCULADO", {"id": s["id"], "usuario": await _usuario(request), "moviles": s["moviles"]})
    return _publica(s)


@router.post("/{token}/codigo", summary="El celular envía un código leído a la consola")
async def codigo(token: str, datos: CodigoIn):
    s = _sesion(token)
    s["n"] += 1
    s["ultimo"] = time.time()
    s.setdefault("codigos", []).append({"n": s["n"], "codigo": datos.codigo.strip()})   # respaldo si la consola perdió el WebSocket
    del s["codigos"][:-MAX_GUARDADOS]
    await manager.broadcast("ESCANEO_REMOTO", {"id": s["id"], "n": s["n"], "codigo": datos.codigo.strip()})
    return {"ok": True, "n": s["n"], "titulo": s["titulo"]}


@router.post("/{token}/resultado", summary="La consola responde al celular qué hizo con el código")
async def resultado(token: str, datos: ResultadoIn):
    s = _sesion(token)
    res = s.setdefault("res", {})
    res[datos.n] = {"ok": datos.ok, "texto": datos.texto}   # respaldo si el celular perdió el WebSocket
    for viejo in sorted(res)[:-MAX_GUARDADOS]:
        res.pop(viejo, None)
    await manager.broadcast("ESCANER_RESULTADO", {"id": s["id"], "n": datos.n, "ok": datos.ok, "texto": datos.texto})
    return {"ok": True}


@router.get("/{token}/codigos", summary="Códigos enviados después de `desde` (la consola los recupera si perdió el WebSocket)")
async def codigos(token: str, desde: int = 0):
    s = _sesion(token)
    return {**_publica(s), "items": [c for c in s.get("codigos", []) if c["n"] > desde]}


@router.get("/{token}/resultado/{n}", summary="Respuesta de la consola a un código (el celular la consulta si perdió el WebSocket)")
async def ver_resultado(token: str, n: int):
    s = _sesion(token)
    r = s.get("res", {}).get(n)
    return {**_publica(s), "listo": r is not None, **(r or {})}


@router.delete("/{token}", summary="Terminar la vinculación")
async def cerrar(token: str):
    with _lock:
        s = _sesiones.pop(token or "", None)
    if s:
        await manager.broadcast("ESCANER_CERRADO", {"id": s["id"]})
    return {"ok": True}
