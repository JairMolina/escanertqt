"""v1.4.14: API del módulo Impresora (/api/activos): registro de activos con etiqueta DYMO «ACT 0000» y QR.

La sesión y el permiso del módulo los valida el middleware (el rol consultor solo lee). Aquí se resuelve la lógica de
cada endpoint; los errores salen con código HTTP y `detail` legible: 404 no existe, 409 número repetido, 422 datos
inválidos, 503 sin DYMO compartida disponible.
"""
import logging
import os
from datetime import datetime
from email import policy
from email.parser import BytesParser
from typing import Any, Callable, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from app.routers.auth import _cliente
from app.services import activos as svc
from app.services import admin_auth as aa
from app.services import activos_import
from app.services import dymo_remoto, usuarios
from app.services.dymo_service import FORMATO_POR_DEFECTO

router = APIRouter(prefix="/api/activos", tags=["Impresora (activos)"])
log = logging.getLogger(__name__)

FECHA = r"^(\d{4}-\d{2}-\d{2})?$"
LOTE_MAX = 500   # etiquetas por lote de impresión y activos por eliminación


class Caracteristica(BaseModel):
    """Par etiqueta → valor libre (procesador, RAM, colaborador...)."""
    model_config = ConfigDict(str_strip_whitespace=True)
    etiqueta: str = Field(..., min_length=1, max_length=60)
    valor: str = Field("", max_length=500)


class ActivoIn(BaseModel):
    """Alta de un activo. Sin `numero` se asigna el siguiente libre."""
    model_config = ConfigDict(str_strip_whitespace=True)
    numero: Optional[int] = Field(None, ge=1, le=svc.NUMERO_MAX)
    nombre: str = Field(..., min_length=1, max_length=120)
    categoria: str = Field("", max_length=80)
    departamento: str = Field("", max_length=80)
    caracteristicas: List[Caracteristica] = Field(default_factory=list, max_length=svc.MAX_CARACTERISTICAS)
    marca: str = Field("", max_length=80)
    modelo: str = Field("", max_length=80)
    serie: str = Field("", max_length=80)
    ubicacion: str = Field("", max_length=120)
    responsable: str = Field("", max_length=120)
    estado: str = Field("activo", max_length=20)
    fecha_adquisicion: Optional[str] = Field(None, pattern=FECHA)
    valor: Optional[float] = Field(None, ge=0, le=1e12)
    notas: str = Field("", max_length=2000)


class ActivoPatch(BaseModel):
    """Edición parcial: solo se aplican los campos enviados."""
    model_config = ConfigDict(str_strip_whitespace=True)
    numero: Optional[int] = Field(None, ge=1, le=svc.NUMERO_MAX)
    nombre: Optional[str] = Field(None, min_length=1, max_length=120)
    categoria: Optional[str] = Field(None, max_length=80)
    departamento: Optional[str] = Field(None, max_length=80)
    caracteristicas: Optional[List[Caracteristica]] = Field(None, max_length=svc.MAX_CARACTERISTICAS)
    marca: Optional[str] = Field(None, max_length=80)
    modelo: Optional[str] = Field(None, max_length=80)
    serie: Optional[str] = Field(None, max_length=80)
    ubicacion: Optional[str] = Field(None, max_length=120)
    responsable: Optional[str] = Field(None, max_length=120)
    estado: Optional[str] = Field(None, max_length=20)
    fecha_adquisicion: Optional[str] = Field(None, pattern=FECHA)
    valor: Optional[float] = Field(None, ge=0, le=1e12)
    notas: Optional[str] = Field(None, max_length=2000)


def _base(request: Request) -> str:
    """URL pública del sitio: TQT_PUBLIC_URL si está definida; si no, la del request (respeta el proxy de Cloudflare)."""
    base = os.getenv("TQT_PUBLIC_URL", "").rstrip("/")
    if not base:
        esquema = request.headers.get("x-forwarded-proto", request.url.scheme).split(",")[0].strip()
        base = f"{esquema}://{request.headers.get('host') or request.url.netloc}"
    return base


def _por(request: Request) -> str:
    u = usuarios.validar_sesion(request.cookies.get(usuarios.COOKIE)) or {}
    return u.get("email", "")


def _numero(codigo: str) -> int:
    """Código flexible → número; un código irreconocible equivale a un activo inexistente (404)."""
    try:
        return svc.numero_de(codigo)
    except ValueError as e:
        raise HTTPException(404, str(e))


def _ejecutar(fn: Callable[..., Any], *args: Any, **kw: Any) -> Any:
    """Traduce los errores del servicio a HTTP; lo inesperado se registra y sale como 500 estructurado (no se silencia)."""
    try:
        return fn(*args, **kw)
    except svc.ActivoNoEncontrado as e:
        raise HTTPException(404, str(e))
    except svc.ActivoDuplicado as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(422, str(e))


def _sin_cache(contenido: Any, tipo: str, extra: Optional[Dict[str, str]] = None) -> Response:
    return Response(content=contenido, media_type=tipo, headers={"Cache-Control": "no-store", **(extra or {})})


# ------------------------------------------------------------------ rutas fijas (antes de /{codigo})
@router.get("", summary="Lista de activos (filtros q, estado, categoría)")
def listar(request: Request, q: str = Query("", max_length=120), estado: str = Query("", max_length=20),
           categoria: str = Query("", max_length=80), departamento: str = Query("", max_length=80),
           desde: str = Query("", max_length=10, description="Fecha de alta AAAA-MM-DD (solo desde = ese día)"),
           hasta: str = Query("", max_length=10, description="Fecha de alta AAAA-MM-DD, inclusive"),
           impresa: Optional[int] = Query(None, ge=0, le=1, description="0 = nunca impresa, 1 = ya impresa"),
           codigos: str = Query("", max_length=20000, description="Lista separada por comas"),
           limite: int = Query(svc.LIMITE_DEFECTO, ge=1, le=svc.LIMITE_MAXIMO)):
    lista = [c.strip() for c in codigos.split(",") if c.strip()] if codigos.strip() else None
    return _ejecutar(svc.listar, _base(request), q, estado, categoria, limite, departamento, desde, hasta, impresa, lista)


@router.get("/exportar.xlsx", summary="Exporta a Excel los activos que cumplen los mismos filtros que el listado")
def exportar(q: str = Query("", max_length=120), estado: str = Query("", max_length=20), categoria: str = Query("", max_length=80),
             departamento: str = Query("", max_length=80), desde: str = Query("", max_length=10), hasta: str = Query("", max_length=10),
             impresa: Optional[int] = Query(None, ge=0, le=1), codigos: str = Query("", max_length=20000)):
    """Solo lectura: el consultor también puede exportar. Archivo `activos_AAAAMMDD-HHMM.xlsx`."""
    lista = [c.strip() for c in codigos.split(",") if c.strip()] if codigos.strip() else None
    datos = _ejecutar(svc.exportar_xlsx, q, estado, categoria, departamento, desde, hasta, impresa, lista)
    nombre = f"activos_{datetime.now():%Y%m%d-%H%M}.xlsx"
    return _sin_cache(datos, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                      {"Content-Disposition": f'attachment; filename="{nombre}"'})


class EliminarIn(BaseModel):
    codigos: List[str] = Field(..., min_length=1, max_length=LOTE_MAX)
    password: str = Field("", max_length=200)


@router.post("/eliminar-lote", summary="Elimina activos (y su bitácora) tras confirmar la contraseña de la sesión")
def eliminar_lote(body: EliminarIn, request: Request):
    por = _por(request)
    try:
        svc.confirmar_clave(por, body.password, _cliente(request))
    except aa.BloqueadoError as e:
        raise HTTPException(429, str(e), headers={"Retry-After": str(e.restante)})
    except PermissionError as e:
        raise HTTPException(401, str(e))
    return _ejecutar(svc.eliminar_lote, body.codigos, por)


@router.get("/impresora/estado", summary="Estado de la DYMO compartida (en línea / lista) para el módulo Impresora")
def estado_impresora():
    """Mismo dato que `/api/dymo/remoto/estado` (que pertenece al módulo Escáner TQT y un usuario solo-Impresora no puede leer):
    {disponible, agentes:[{nombre, en_linea, impresora_ok, detalle}], en_cola}."""
    return dymo_remoto.estado()


ESTADO_TRABAJO = {"pendiente": "pendiente", "enviada": "imprimiendo", "impresa": "impresa"}


@router.get("/lote/estado", summary="Avance de los trabajos de un lote en la cola de la DYMO compartida")
def estado_lote(trabajos: str = Query(..., max_length=20000, description="ids separados por comas (máx. 500)")):
    ids = [t.strip() for t in trabajos.split(",") if t.strip()]
    if not ids or len(ids) > LOTE_MAX:
        raise HTTPException(422, f"Indica de 1 a {LOTE_MAX} trabajos.")
    cola = dymo_remoto.trabajos(ids)
    out, resumen = [], {"pendiente": 0, "imprimiendo": 0, "impresa": 0, "error": 0}
    for jid in dict.fromkeys(ids):
        t = cola.get(jid)
        est = ESTADO_TRABAJO.get(t["estado"], "error") if t else "error"
        detalle = (t["detalle"] if t else "El trabajo no existe en la cola.") or (f"Estado en la cola: {t['estado']}." if est == "error" else "")
        resumen[est] += 1
        out.append({"trabajo_id": jid, "estado": est, "detalle": detalle, "delante": t["delante"] if t else 0})
    resumen["total"] = len(out)
    return {"trabajos": out, "resumen": resumen, "terminado": resumen["pendiente"] + resumen["imprimiendo"] == 0}


@router.get("/siguiente", summary="Siguiente número de activo libre")
def siguiente():
    return svc.siguiente()


@router.get("/catalogos", summary="Categorías, ubicaciones, responsables ya usados y estados")
def catalogos():
    return svc.catalogos()


@router.get("/buscar", summary="Activo por código flexible o por la URL que lee el celular")
def buscar(request: Request, codigo: str = Query(..., max_length=500)):
    return _ejecutar(svc.obtener, _numero(codigo), _base(request))


ZIP_MAX = 1000


class LoteIn(BaseModel):
    codigos: List[str] = Field(..., min_length=1, max_length=ZIP_MAX)


class LoteImpresionIn(BaseModel):
    """Lote por `codigos` o resuelto en el servidor con filtros (al menos uno)."""
    model_config = ConfigDict(str_strip_whitespace=True)
    codigos: Optional[List[str]] = Field(None, min_length=1, max_length=LOTE_MAX)
    desde: str = Field("", max_length=10)
    hasta: str = Field("", max_length=10)
    impresa: Optional[int] = Field(None, ge=0, le=1)
    departamento: str = Field("", max_length=80)
    q: str = Field("", max_length=120)
    estado: str = Field("", max_length=20)
    categoria: str = Field("", max_length=80)
XLSX_MAX = 10 * 1024 * 1024
MUESTRA = 20
OMITIDOS_MAX = 50


async def _leer_formulario(request: Request) -> Dict[str, Any]:
    """Lee un multipart/form-data sin python-multipart: {campo: texto | (nombre_archivo, bytes)}. 413 si pasa de 10 MB."""
    tipo = request.headers.get("content-type", "")
    if not tipo.lower().startswith("multipart/form-data"):
        raise HTTPException(422, "Envía el archivo como multipart/form-data (campo «archivo»).")
    if int(request.headers.get("content-length") or 0) > XLSX_MAX + 4096:
        raise HTTPException(413, "El archivo supera el máximo de 10 MB.")
    cuerpo = await request.body()
    if len(cuerpo) > XLSX_MAX + 4096:
        raise HTTPException(413, "El archivo supera el máximo de 10 MB.")
    crlf = bytes((13, 10))
    cabecera = b"Content-Type: " + tipo.encode("latin-1", "replace") + crlf + b"MIME-Version: 1.0" + crlf + crlf
    msg = BytesParser(policy=policy.HTTP).parsebytes(cabecera + cuerpo)
    campos: Dict[str, Any] = {}
    for parte in msg.iter_parts():
        nombre = parte.get_param("name", header="content-disposition")
        if not nombre:
            continue
        datos = parte.get_payload(decode=True) or b""
        archivo = parte.get_filename()
        campos[nombre] = (archivo, datos) if archivo is not None else datos.decode("utf-8", "replace").strip()
    return campos


def _resumen_importacion(a: Dict[str, Any]) -> Dict[str, Any]:
    hojas = [{**{k: h[k] for k in ("hoja", "formato", "filas_verdes", "nuevos", "actualizar")},
              "omitidos": h["omitidos"][:OMITIDOS_MAX], "n_omitidos": len(h["omitidos"])} for h in a["hojas"]]
    return {"hojas": hojas, "totales": a["totales"], "avisos": a["avisos"][:OMITIDOS_MAX], "muestra": a["items"][:MUESTRA]}


@router.post("/importar", summary="Importa activos desde el Excel de inventario (vista previa o aplicar)")
async def importar(request: Request):
    """multipart: `archivo` (.xlsx, máx. 10 MB), `solo_verdes` (1 por defecto) y `aplicar` (0 = vista previa, 1 = escribir)."""
    campos = await _leer_formulario(request)
    arch = campos.get("archivo")
    if not isinstance(arch, tuple) or not arch[1]:
        raise HTTPException(422, "Falta el archivo .xlsx (campo «archivo»).")
    nombre, datos = arch
    if not (nombre or "").lower().endswith(".xlsx") or not datos.startswith(b"PK"):
        raise HTTPException(422, "Solo se aceptan libros de Excel .xlsx.")
    solo_verdes = str(campos.get("solo_verdes", "1")).lower() not in ("0", "false", "no")
    aplicar = str(campos.get("aplicar", "0")).lower() in ("1", "true", "si", "sí")
    por = _por(request)
    a = await run_in_threadpool(_ejecutar, activos_import.analizar, datos, solo_verdes)
    out = _resumen_importacion(a)
    out["aplicado"] = False
    if aplicar:
        r = await run_in_threadpool(_ejecutar, activos_import.aplicar, a["items"], por)
        out.update(aplicado=True, codigos=r["codigos"], resultado={k: r[k] for k in ("creados", "actualizados", "sin_cambios", "errores")})
        log.info("Importación de activos por %s: %s nuevos, %s actualizados", por, r["creados"], r["actualizados"])
    return out


@router.post("/imprimir-lote", summary="Encola un lote de etiquetas en la DYMO compartida (por códigos o por filtros, máx. 500)")
def imprimir_lote(body: LoteImpresionIn, request: Request):
    """Usa la misma cola y el mismo estado de la Raspberry que las etiquetas de tarjeta (`dymo_remoto.encolar`)."""
    por, base = _por(request), _base(request)
    filtros = body.model_dump(exclude={"codigos"})
    items = _ejecutar(svc.resolver_lote, LOTE_MAX, body.codigos, **filtros)
    if not dymo_remoto.estado()["disponible"]:
        raise HTTPException(503, "La DYMO compartida no está en línea o la impresora no está lista; no se envió ninguna etiqueta.")
    encolados, errores = [], []
    for a in items:
        try:
            t = dymo_remoto.encolar("activo", {"numero": a["numero"], "base": base}, 1, f"Activo {a['etiqueta']} · {a['nombre']}", por)
            svc.registrar_impresion(a["numero"], por, f"DYMO compartida (lote) · trabajo {t['id']}")
            encolados.append({"codigo": a["codigo"], "trabajo_id": t["id"]})
        except (svc.ActivoNoEncontrado, ValueError) as e:   # p. ej. la DYMO se desconectó a mitad del lote
            log.warning("Lote de etiquetas: %s: %s", a["codigo"], e)
            errores.append({"codigo": a["codigo"], "detail": str(e)})
    if body.codigos:   # códigos pedidos que no existen
        hallados = {a["numero"] for a in items}
        for cod in body.codigos:
            try:
                if svc.numero_de(cod) in hallados:
                    continue
            except ValueError:
                pass
            errores.append({"codigo": cod, "detail": "No existe ese activo."})
    return {"ok": not errores, "encolados": len(encolados), "trabajos": encolados, "errores": errores, "via": "compartida"}


@router.get("/etiquetas.zip", summary="ZIP con un .dymo por activo (codigos=ACT-0001,ACT-0002 o importacion=ultima)")
def etiquetas_zip(request: Request, codigos: str = Query("", max_length=8000), importacion: str = Query("", pattern="^(ultima)?$"),
                  formato: str = Query("dymo", pattern="^(dymo|label)$")):
    lista = ([c.strip() for c in codigos.split(",") if c.strip()] if codigos else [])
    if importacion == "ultima":
        lista += activos_import.codigos_ultima_importacion()
    return _zip_etiquetas(lista, request, formato)


@router.post("/etiquetas.zip", summary="Igual que el GET, con los códigos en el cuerpo JSON (para listas largas)")
def etiquetas_zip_post(body: LoteIn, request: Request, formato: str = Query("dymo", pattern="^(dymo|label)$")):
    return _zip_etiquetas(body.codigos, request, formato)


def _zip_etiquetas(lista: List[str], request: Request, formato: str) -> Response:
    if not lista:
        raise HTTPException(404, "No hay activos para las etiquetas pedidas.")
    if len(lista) > ZIP_MAX:
        raise HTTPException(422, f"Máximo {ZIP_MAX} etiquetas por archivo.")
    datos = _ejecutar(svc.zip_etiquetas, lista, _base(request), formato)
    return _sin_cache(datos, "application/zip", {"Content-Disposition": 'attachment; filename="etiquetas_activos.zip"'})


@router.post("", status_code=201, summary="Alta de un activo")
def crear(body: ActivoIn, request: Request):
    return _ejecutar(svc.crear, body.model_dump(exclude_none=True), _por(request), _base(request))


# ------------------------------------------------------------------ un activo
@router.get("/{codigo}", summary="Activo con su bitácora")
def obtener(codigo: str, request: Request):
    return _ejecutar(svc.obtener, _numero(codigo), _base(request))


@router.patch("/{codigo}", summary="Edición parcial de un activo")
def editar(codigo: str, body: ActivoPatch, request: Request):
    cambios = body.model_dump(exclude_unset=True)
    if "nombre" in cambios and cambios["nombre"] is None:
        raise HTTPException(422, "El nombre del activo es obligatorio.")
    return _ejecutar(svc.actualizar, _numero(codigo), cambios, _por(request), _base(request))


# ------------------------------------------------------------------ etiqueta
@router.get("/{codigo}/etiqueta.svg", summary="Etiqueta como SVG a escala real (1 unidad = 1 mm)")
def etiqueta_svg(codigo: str, request: Request, label_format: str = Query(FORMATO_POR_DEFECTO),
                 borde: bool = Query(False, description="Contorno redondeado (solo para vista previa)")):
    return _sin_cache(_ejecutar(svc.svg_etiqueta, _numero(codigo), _base(request), label_format, borde), "image/svg+xml")


@router.get("/{codigo}/etiqueta/xml", summary="XML de etiqueta para dymo.label.framework.openLabelXml (DYMO Connect)")
def etiqueta_xml(codigo: str, request: Request, label_format: str = Query(FORMATO_POR_DEFECTO),
                 tipo: str = Query("dymo", pattern="^(dymo|label)$", description="dymo = DYMO Connect (DCD) · label = DYMO Label v8")):
    return _sin_cache(_ejecutar(svc.xml_etiqueta, _numero(codigo), _base(request), tipo, label_format), "application/xml; charset=utf-8")


@router.get("/{codigo}/etiqueta/archivo", summary="Descarga la etiqueta como archivo .dymo o .label")
def etiqueta_archivo(codigo: str, request: Request, formato: str = Query("dymo", pattern="^(dymo|label)$"),
                     label_format: str = Query(FORMATO_POR_DEFECTO)):
    datos, nombre = _ejecutar(svc.archivo_etiqueta, _numero(codigo), _base(request), formato, label_format)
    return _sin_cache(datos, "application/octet-stream", {"Content-Disposition": f'attachment; filename="{nombre}"'})


# ------------------------------------------------------------------ impresión
@router.post("/{codigo}/imprimir", summary="Envía la etiqueta a la DYMO compartida (agente en la Raspberry)")
def imprimir(codigo: str, request: Request):
    n, por, base = _numero(codigo), _por(request), _base(request)
    a = _ejecutar(svc.obtener, n, base)
    try:
        trabajo = dymo_remoto.encolar("activo", {"numero": n, "base": base}, 1, f"Activo {a['etiqueta']} · {a['nombre']}", por)
    except ValueError as e:   # sin agente en línea o impresora no lista: nada se encoló
        log.warning("Activo %s: DYMO compartida no disponible (%s)", a["codigo"], e)
        raise HTTPException(503, str(e))
    _ejecutar(svc.registrar_impresion, n, por, f"DYMO compartida · trabajo {trabajo['id']}")
    return {"ok": True, "trabajo_id": trabajo["id"], "via": "compartida"}


@router.post("/{codigo}/impreso", summary="El frontend avisa que imprimió con DYMO Connect local")
def impreso(codigo: str, request: Request):
    _ejecutar(svc.registrar_impresion, _numero(codigo), _por(request), "DYMO Connect local")
    return {"ok": True}
