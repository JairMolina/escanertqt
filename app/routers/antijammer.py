"""API del módulo Skudo AntiJammer (v1.4.31): misma forma que /api/tpms (rutas, parámetros y JSON), solo cambia el prefijo
y el nombre de la placa. El consultor solo lee (lo aplica el middleware de roles)."""
from typing import List, Literal, Optional

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from app.routers.auth import usuario_actual
from app.services import antijammer as svc
from app.services import antijammer_parejas as parejas_svc
from app.services import materiales
from app.services import antijammer_etiqueta as etq
from app.services import dymo_remoto
from app.services.dymo_service import FORMATO_POR_DEFECTO as FORMATO_ETQ

router = APIRouter(prefix="/api/antijammer", tags=["Skudo AntiJammer"])


class EscaneoAj(BaseModel):
    codigo: str = Field(..., max_length=200)
    lote: str = Field("", max_length=60)


class AltaManual(BaseModel):
    version: str = Field(..., min_length=1, max_length=10)
    serie: str = Field(..., min_length=1, max_length=10)
    lote: str = Field("", max_length=60)


class FirmwareAj(BaseModel):
    firmware: Optional[str] = Field(None, max_length=60)
    tipo: Optional[Literal["RX", "TX"]] = None          # v1.4.104: RX/TX y número de pareja dados al programar
    pareja: Optional[int] = Field(None, ge=1, le=9999)


class EdicionAj(BaseModel):
    version: Optional[str] = Field(None, max_length=10)
    serie: Optional[str] = Field(None, max_length=10)
    lote: Optional[str] = Field(None, max_length=60)
    estado: Optional[str] = Field(None, max_length=20)
    nota: Optional[str] = Field(None, max_length=500)


class RenombrarLote(BaseModel):
    de: str = Field(..., max_length=60)
    a: str = Field(..., max_length=60)


class MasaAj(BaseModel):
    ids: List[int] = Field(..., min_length=1, max_length=5000)
    accion: Literal["firmware", "version", "lote", "estado", "eliminar"]
    valor: Optional[str] = Field(None, max_length=60)


def _http(e: svc.AntijammerError) -> HTTPException:
    if isinstance(e, svc.NoEncontrada):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    if isinstance(e, svc.Duplicada):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return HTTPException(status_code=422, detail=str(e))


async def _ejecutar(fn, *args):
    try:
        return await run_in_threadpool(fn, *args)
    except svc.AntijammerError as e:
        raise _http(e)


def _email(request: Request) -> Optional[str]:
    return usuario_actual(request).get("email")


@router.post("/escanear", summary="Registrar una placa Skudo AntiJammer por su QR (idempotente)")
async def escanear(body: EscaneoAj, request: Request):
    return await run_in_threadpool(svc.escanear, body.codigo, body.lote, _email(request))


# Rutas fijas antes de /pcb/{pcb_id}
@router.post("/pcb/manual", status_code=status.HTTP_201_CREATED, summary="Alta manual por versión y serie")
async def alta_manual(body: AltaManual, request: Request):
    return {"pcb": await _ejecutar(svc.alta_manual, body.version, body.serie, body.lote, _email(request))}


@router.post("/pcb/masa", summary="Acción sobre varias placas (todo o nada)")
async def masa(body: MasaAj, request: Request):
    return await _ejecutar(svc.masa, body.ids, body.accion, body.valor, _email(request))


class EtiquetasAj(BaseModel):
    codigos: List[str] = Field(..., min_length=1, max_length=100)
    copias: int = Field(1, ge=1, le=5)


def _lista_codigos(texto: str) -> List[str]:
    return [c.strip() for c in (texto or "").split(",") if c.strip()][:100]


@router.get("/etiquetas/estado", summary="Estado de la DYMO compartida (en línea / lista) para imprimir etiquetas del gabinete")
async def etiquetas_estado():
    return await run_in_threadpool(dymo_remoto.estado)


@router.get("/etiquetas/vista", summary="Vista previa SVG (1 unidad = 1 mm) de las etiquetas de varias placas; las no registradas van en `faltan`")
async def etiquetas_vista(codigos: str = Query(..., min_length=1, max_length=4000, description="nombres separados por comas (máx. 100)")):
    def _go():
        items, faltan, errores = [], [], []
        for c in etq.expandir(_lista_codigos(codigos)):
            try:
                d = etq.datos_de(c)
                items.append({**d, "svg": etq.svg(d, FORMATO_ETQ)})
            except svc.AntijammerError as e:
                faltan.append(c)
                errores.append({"codigo": c, "detail": str(e)})
        return {"items": items, "faltan": faltan, "errores": errores}
    return await run_in_threadpool(_go)


@router.get("/etiquetas/{nombre}/xml", summary="XML .dymo de la etiqueta para DYMO Connect local (dymo.label.framework.openLabelXml)")
async def etiqueta_xml(nombre: str):
    d = await _ejecutar(etq.datos_de, nombre)
    return Response(content=etq.dymo_xml(d, FORMATO_ETQ), media_type="application/xml", headers={"Cache-Control": "no-store"})


@router.post("/etiquetas/imprimir", summary="Encola etiquetas en la DYMO compartida (agente en la Raspberry); 503 si no hay DYMO disponible")
async def etiquetas_imprimir(body: EtiquetasAj, request: Request):
    def _go():
        if not dymo_remoto.estado()["disponible"]:
            raise HTTPException(503, "La DYMO compartida no está en línea o la impresora no está lista; no se envió ninguna etiqueta.")
        por, enc, errores = _email(request) or "", [], []
        for c in etq.expandir(body.codigos):
            try:
                d = etq.datos_de(c)
                t = dymo_remoto.encolar("antijammer", {"nombre": d["nombre"]}, body.copias, f"AntiJammer pareja {d['numero']} {d['tipo']} {d['nombre']}", por)
                enc.append({"nombre": d["nombre"], "trabajo": t["id"]})
            except svc.AntijammerError as e:
                errores.append({"codigo": c, "detail": str(e)})
            except ValueError as e:   # p. ej. la DYMO se desconectó a mitad del lote
                errores.append({"codigo": c, "detail": str(e)})
        return {"encolados": len(enc), "trabajos": enc, "errores": errores}
    return await run_in_threadpool(_go)


@router.get("/pcb/por-codigo", summary="Placa por QR, nombre o serie, con su historial")
async def por_codigo(codigo: str = Query(..., min_length=1, max_length=200)):
    d = await _ejecutar(svc.por_codigo, codigo)
    if isinstance(d, dict) and d.get("pcb"):   # v1.4.104: número de pareja y RX/TX de la placa
        d["pareja"] = await run_in_threadpool(parejas_svc.de_placa, d["pcb"]["id"])
    return d


@router.get("/pcb", summary="Placas Skudo AntiJammer registradas (más recientes primero)")
async def listar(q: Optional[str] = Query(None, max_length=100), estado: Optional[str] = Query(None, max_length=20),
                 version: Optional[str] = Query(None, max_length=10), firmware: Optional[str] = Query(None, max_length=60),
                 lote: Optional[str] = Query(None, max_length=60), limit: int = Query(500, ge=1, le=5000)):
    return await _ejecutar(svc.listar, lote, limit, q, estado, version, firmware)


@router.get("/eventos", summary="Movimientos Skudo AntiJammer (filtrados y paginados)")
async def eventos(accion: Optional[str] = Query(None, max_length=20), q: Optional[str] = Query(None, max_length=100),
                  desde: Optional[str] = Query(None, max_length=10), hasta: Optional[str] = Query(None, max_length=10),
                  limit: int = Query(200, ge=1, le=2000), offset: int = Query(0, ge=0)):
    return await _ejecutar(svc.eventos, accion, q, desde, hasta, limit, offset)


@router.get("/lotes", summary="Lotes con conteos por estado")
async def lotes():
    return await _ejecutar(svc.lotes)


@router.post("/lotes/renombrar", summary="Renombrar un lote (todas sus placas)")
async def renombrar_lote(body: RenombrarLote, request: Request):
    return await _ejecutar(svc.renombrar_lote, body.de, body.a, _email(request))


@router.get("/exportar", summary="Exportar placas y movimientos a Excel (.xlsx)")
async def exportar(q: Optional[str] = Query(None, max_length=100), estado: Optional[str] = Query(None, max_length=20),
                   version: Optional[str] = Query(None, max_length=10), firmware: Optional[str] = Query(None, max_length=60),
                   lote: Optional[str] = Query(None, max_length=60)):
    datos = await _ejecutar(svc.exportar_xlsx, q, estado, version, firmware, lote)
    nombre = f"SkudoAntiJammer_placas_{datetime.now():%Y%m%d}.xlsx"
    return Response(content=datos, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{nombre}"', "Cache-Control": "no-store"})


@router.put("/pcb/{pcb_id}/firmware", summary="Asignar o quitar firmware")
async def firmware(pcb_id: int, body: FirmwareAj, request: Request):
    """Con `pareja` (y `tipo`) la placa entra a esa pareja antes de guardar el firmware: si el número choca, no se guarda nada."""
    if body.pareja is not None and not body.tipo:
        raise HTTPException(status_code=422, detail="Indica si la placa es RX o TX para darle el número de pareja.")
    par = None
    try:
        if body.pareja is not None:
            par = await _ejecutar(parejas_svc.asignar, pcb_id, body.tipo, body.pareja, _email(request))
        pcb = await _ejecutar(svc.poner_firmware, pcb_id, body.firmware, _email(request))
        if body.tipo and body.pareja is None:
            await run_in_threadpool(materiales.asignar_tarjeta, "antijammer", [pcb_id], body.tipo)
    except materiales.CosteoError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"pcb": pcb, "pareja": par}


@router.patch("/pcb/{pcb_id}", summary="Editar versión, serie, lote, estado o nota")
async def editar(pcb_id: int, body: EdicionAj, request: Request):
    return {"pcb": await _ejecutar(svc.editar, pcb_id, body.model_dump(exclude_none=True), _email(request))}


@router.delete("/pcb/{pcb_id}", summary="Eliminar una placa")
async def eliminar(pcb_id: int, request: Request):
    return await _ejecutar(svc.eliminar, pcb_id, _email(request))


@router.get("/resumen", summary="Conteos por estado, versión, firmware y lote")
async def resumen():
    return await _ejecutar(svc.resumen)


# ---------------------------------------------------------------- Parejas RX/TX (v1.4.103)
class ParejaAj(BaseModel):
    rx: str = Field(..., min_length=1, max_length=200)   # id numérico o QR/nombre/serie
    tx: str = Field(..., min_length=1, max_length=200)
    numero: Optional[int] = Field(None, ge=1, le=9999)   # vacío = el siguiente libre


def _ref(v: str):
    v = v.strip()
    return int(v[1:]) if v.startswith("#") and v[1:].isdigit() else v


@router.get("/parejas", summary="Parejas RX/TX y placas sin pareja (mes = AAAA-MM de recepción)")
async def parejas(mes: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}$")):
    return await _ejecutar(parejas_svc.listar, mes)


@router.post("/parejas", status_code=status.HTTP_201_CREATED, summary="Emparejar una RX con una TX (guarda RX/TX en Materiales)")
async def emparejar(body: ParejaAj, request: Request):
    try:
        return await _ejecutar(parejas_svc.emparejar, _ref(body.rx), _ref(body.tx), _email(request), body.numero)
    except materiales.CosteoError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.delete("/parejas/{pareja_id}", summary="Deshacer una pareja (cada placa conserva su RX/TX)")
async def deshacer_pareja(pareja_id: int, request: Request):
    return await _ejecutar(parejas_svc.deshacer, pareja_id, _email(request))
