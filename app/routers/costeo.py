"""API de costeo por módulo (v1.4.34): /api/<modulo>/costos para cada módulo de `costeo.MODULOS_COSTEO`, y desde v1.4.35
/api/<modulo>/materiales (inventario de materiales que descuenta cada tarjeta programada).
Va bajo el prefijo del módulo, así que el permiso por módulo (modulos.modulo_de_ruta) y el solo-lectura del consultor
se aplican igual que al resto de su API. El Excel se sube como cuerpo binario (sin multipart)."""
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from app.routers.auth import usuario_actual
from app.services import costeo as svc
from app.services import materiales as mat

XLSX_MAX = 5 * 1024 * 1024


class ComponenteIn(BaseModel):
    tarjeta: Optional[str] = Field(None, max_length=40)
    categoria: Optional[str] = Field(None, max_length=120)
    descripcion: Optional[str] = Field(None, max_length=300)
    proveedor: Optional[str] = Field(None, max_length=120)
    cantidad_lote: Optional[float] = None
    unidad: Optional[str] = Field(None, max_length=20)
    cantidad: Optional[float] = None
    moneda: Optional[str] = Field(None, max_length=3)
    costo_unitario: Optional[float] = None
    tipo: Optional[str] = Field(None, max_length=20)
    notas: Optional[str] = Field(None, max_length=300)
    orden: Optional[int] = None


class ParametrosIn(BaseModel):
    tipo_cambio: float


class ActivarIn(BaseModel):
    desde: Optional[str] = Field(None, max_length=10)


class MovimientoIn(BaseModel):
    descripcion: str = Field(..., max_length=300)
    tipo: str = Field(..., max_length=10)
    cantidad: float
    nota: str = Field("", max_length=300)


class MinimoIn(BaseModel):
    descripcion: str = Field(..., max_length=300)
    minimo: float


class AsignarIn(BaseModel):
    pcb_ids: List[int] = Field(..., min_length=1, max_length=5000)
    tarjeta: str = Field(..., max_length=40)


async def _ejecutar(fn, *args):
    try:
        return await run_in_threadpool(fn, *args)
    except svc.NoEncontrado as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e))
    except svc.CosteoError as e:
        raise HTTPException(422, str(e))


def _router(slug: str) -> APIRouter:
    r = APIRouter(prefix=f"/api/{slug}/costos", tags=[f"Costos {svc.MODULOS_COSTEO[slug]['nombre']}"])

    @r.get("", summary="Cotizador: componentes, costo por tarjeta y recurrentes")
    async def ver():
        return await _ejecutar(svc.resumen, slug)

    @r.post("", status_code=status.HTTP_201_CREATED, summary="Agregar un material")
    async def crear(body: ComponenteIn):
        return await _ejecutar(svc.crear, slug, body.model_dump(exclude_none=True))

    @r.patch("/parametros", summary="Cambiar el tipo de cambio del módulo")
    async def parametros(body: ParametrosIn):
        return await _ejecutar(svc.fijar_tipo_cambio, slug, body.tipo_cambio)

    @r.post("/importar", summary="Importar el cotizador (.xlsx, cuerpo binario)")
    async def importar(request: Request, reemplazar: bool = Query(True)):
        if int(request.headers.get("content-length") or 0) > XLSX_MAX:
            raise HTTPException(413, "El archivo supera el máximo de 5 MB.")
        cuerpo = await request.body()
        if not cuerpo or len(cuerpo) > XLSX_MAX:
            raise HTTPException(413 if cuerpo else 422, "El archivo supera el máximo de 5 MB." if cuerpo else "Falta el archivo.")
        return await _ejecutar(svc.importar_xlsx, slug, cuerpo, reemplazar)

    @r.get("/exportar", summary="Descargar el cotizador con fórmulas (.xlsx)")
    async def exportar():
        datos = await _ejecutar(svc.exportar_xlsx, slug)
        nombre = f"Cotizador_{svc.MODULOS_COSTEO[slug]['nombre'].replace(' ', '')}_{datetime.now():%Y%m%d}.xlsx"
        return Response(datos, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f'attachment; filename="{nombre}"'})

    @r.patch("/{cid}", summary="Editar un material")
    async def editar(cid: int, body: ComponenteIn):
        return await _ejecutar(svc.editar, slug, cid, body.model_dump(exclude_none=True))

    @r.delete("/{cid}", status_code=status.HTTP_204_NO_CONTENT, summary="Eliminar un material")
    async def eliminar(cid: int):
        await _ejecutar(svc.eliminar, slug, cid)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return r


def _router_materiales(slug: str) -> APIRouter:
    r = APIRouter(prefix=f"/api/{slug}/materiales", tags=[f"Materiales {svc.MODULOS_COSTEO[slug]['nombre']}"])

    @r.get("", summary="Existencias, consumo por tarjeta realizada, tarjetas posibles y placas por asignar")
    async def ver():
        return await _ejecutar(mat.estado, slug)

    @r.post("/activar", summary="Empezar a descontar las tarjetas programadas desde una fecha (por omisión hoy)")
    async def activar(body: ActivarIn):
        return await _ejecutar(mat.activar, slug, body.desde)

    @r.post("/movimientos", status_code=status.HTTP_201_CREATED, summary="Entrada, salida o ajuste de un material")
    async def movimiento(body: MovimientoIn, request: Request):
        return await _ejecutar(mat.registrar_movimiento, slug, body.model_dump(), usuario_actual(request).get("email") or "")

    @r.delete("/movimientos/{mid}", summary="Eliminar un movimiento capturado por error")
    async def borrar_movimiento(mid: int):
        return await _ejecutar(mat.eliminar_movimiento, slug, mid)

    @r.patch("/minimo", summary="Stock mínimo de un material")
    async def minimo(body: MinimoIn):
        return await _ejecutar(mat.fijar_minimo, slug, body.descripcion, body.minimo)

    @r.post("/asignar", summary="Indicar qué tarjeta es cada placa (p. ej. RX o TX)")
    async def asignar(body: AsignarIn):
        return await _ejecutar(mat.asignar_tarjeta, slug, body.pcb_ids, body.tarjeta)

    return r


routers: List[APIRouter] = [f(s) for s in svc.MODULOS_COSTEO for f in (_router, _router_materiales)]
