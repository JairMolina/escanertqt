"""Enviar por correo los Excel que la app exporta (v1.3.37).

El archivo SIEMPRE lo genera el servidor (mismo código que la descarga): el navegador solo dice qué reporte y a quién,
así nadie puede usar el correo de la app para mandar archivos arbitrarios. Mismos permisos que la descarga
(el Excel del lote exige la sesión de administración). Máximo 10 destinatarios por envío; todo queda en la bitácora."""
import logging
import shutil
import tempfile
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Cookie, Header, HTTPException, Request, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from app.database import db
from app.database.models import MESES_ES
from app.services import correo, reporte_dia, usuarios

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/correo", tags=["Correo"])

MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MAX_DESTINOS = 10
TIPOS = ("lote", "reporte_dia", "inventario_tqtr")


class EnvioExcelIn(BaseModel):
    tipo: str = Field(..., max_length=30, description="lote · reporte_dia · inventario_tqtr")
    para: List[str] = Field(..., min_length=1, max_length=MAX_DESTINOS)
    lote_id: Optional[int] = Field(None, ge=1, le=2**31)
    fecha: Optional[str] = Field(None, max_length=10)
    desde: Optional[str] = Field(None, max_length=10)
    hasta: Optional[str] = Field(None, max_length=10)
    mensaje: Optional[str] = Field(None, max_length=1000)


@router.get("/destinatarios", summary="Correos de las cuentas activas (para elegir a quién enviar)")
async def destinatarios():
    cuentas = await run_in_threadpool(usuarios.listar)
    return {"items": [{"email": u["email"], "rol": u["rol"]} for u in cuentas if u["activo"]], "smtp": correo.configurado(), "max": MAX_DESTINOS}


Kpis = List[Tuple[str, object, str]]


def _excel_lote(lote_id: Optional[int]) -> Tuple[str, bytes, str, Kpis]:
    from app.routers.admin import _exportar   # import diferido (admin importa routers que importan éste)
    lote = db.get_lote_by_id(lote_id) if lote_id else db.get_active_lote()
    if not lote:
        raise LookupError("Lote no encontrado o sin lote activo.")
    nombre = db.archivo_excel_lote(lote)
    carpeta = Path(tempfile.mkdtemp(prefix="tqt_correo_"))
    try:
        _exportar(lote, carpeta / nombre)
        return nombre, (carpeta / nombre).read_bytes(), f"Control de producción TQT · {db.nombre_lote_de(lote)}", []
    finally:
        shutil.rmtree(carpeta, ignore_errors=True)


def _generar(p: EnvioExcelIn) -> Tuple[str, bytes, str, Kpis]:
    """(archivo, bytes, título, indicadores para el cuerpo del correo)."""
    if p.tipo == "lote":
        return _excel_lote(p.lote_id)
    if p.tipo == "reporte_dia":
        a = p.desde or p.fecha or ""
        b = p.hasta or a
        res = reporte_dia.tarjetas_del_rango(a, b)
        kpis = [("Completadas", res["completadas"], "ok"), ("Entregadas", res["entregadas"], "info"), ("En el reporte", len(res["items"]), "gris")]
        return reporte_dia.nombre_archivo(a, b), reporte_dia.excel_del_rango(a, b), f"Reporte de tarjetas {'del ' if a == b else ''}{reporte_dia.texto_rango(a, b)}", kpis
    from app.services import inventario_tqtr
    hoy = date.today()
    return f"INVENTARIO_TQTR_{hoy}.xlsx", inventario_tqtr.exportar_xlsx(), f"Inventario TQTR al {hoy.day} de {MESES_ES[hoy.month - 1].lower()} de {hoy.year}", []


@router.post("/excel", summary="Generar un Excel de la app y enviarlo por correo a cuentas o direcciones externas")
async def enviar_excel(p: EnvioExcelIn, request: Request,
                       x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"), tqt_admin: Optional[str] = Cookie(None)) -> Dict[str, Any]:
    if p.tipo not in TIPOS:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Tipo de reporte no válido.")
    # v1.3.44: el Excel del lote ya no pide la clave de administración (mismo permiso que su descarga: sesión de usuario).
    # El consultor no llega aquí: es un POST y el middleware de roles lo rechaza con 403.
    para = sorted({usuarios.normalizar(x) for x in p.para if x and x.strip()})
    malos = [x for x in para if not usuarios._EMAIL.match(x)]
    if malos or not para:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Correo no válido: {', '.join(malos) or '(vacío)'}")
    if len(para) > MAX_DESTINOS:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Máximo {MAX_DESTINOS} destinatarios por envío.")
    if not correo.configurado():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="El envío de correo no está configurado en el servidor.")
    try:
        nombre, datos, titulo, kpis = await run_in_threadpool(_generar, p)
    except (LookupError, ValueError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    try:
        quien = usuarios.validar_sesion(request.cookies.get(usuarios.COOKIE))["email"]
    except usuarios.SesionInvalidaError:
        quien = "desconocido"
    mensaje = (p.mensaje or "").strip()
    texto = f"Hola:\n\n{quien} te comparte «{titulo}» desde Escáner TQT. El archivo {nombre} va adjunto a este correo.\n"
    if kpis:
        texto += "\n" + "\n".join(f"- {etq}: {val}" for etq, val, _ in kpis) + "\n"
    if mensaje:
        texto += f"\nMensaje de {quien}:\n{mensaje}\n"
    texto += "\nSaludos,\nEscáner TQT · Control de producción"
    html = correo.plantilla(titulo, [f"{quien} te comparte este reporte desde Escáner TQT. El archivo va adjunto a este correo."],
                            saludo="Hola:", preencabezado=f"{quien} te comparte {titulo}", kpis=kpis or None,
                            nota=(f"Mensaje de {quien}:\n{mensaje}" if mensaje else None), adjunto=nombre)
    enviados, fallos = [], []
    for d in para:   # uno por destinatario: nadie ve los correos de los demás
        try:
            await run_in_threadpool(correo.enviar, d, f"{titulo} · Escáner TQT", texto, html, quien if "@" in quien else None, [(nombre, datos, MIME_XLSX)])
            enviados.append(d)
        except Exception as e:  # noqa: BLE001 - SMTP/red: se informa sin exponer credenciales
            logger.warning("No se pudo enviar %s a %s: %s", nombre, d, e)
            fallos.append({"email": d, "error": type(e).__name__})
    await run_in_threadpool(db.log_evento, "EXCEL_CORREO", p.lote_id, nombre, f"Enviado a {', '.join(enviados) or 'nadie'}" + (f"; falló {len(fallos)}" if fallos else ""), quien)
    if not enviados:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="No se pudo enviar el correo a ningún destinatario.")
    return {"archivo": nombre, "enviados": enviados, "fallos": fallos}
