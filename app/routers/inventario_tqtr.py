"""Inventario TQTR (réplica del Excel INVENTARIO_TQTR_26_v.xlsx): dashboard, registro de movimientos, componentes (BOM) y configuración.

La sesión y los roles los aplica el middleware (los consultores solo pueden hacer GET).
"""
from datetime import date
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Response, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from app.database.db import ConflictoError, NoEncontradoError
from app.services import inventario_tqtr as svc

router = APIRouter(prefix="/api/inventario-tqtr", tags=["Inventario TQTR"])
MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


async def _run(fn, *args, **kwargs):
    try:
        return await run_in_threadpool(fn, *args, **kwargs)
    except NoEncontradoError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ConflictoError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


class MovimientoIn(BaseModel):
    codigo: Optional[str] = None
    fecha_entrada: Optional[str] = None
    categoria: Optional[str] = None
    modelo: Optional[str] = None
    condicion: Optional[str] = None
    movimiento: Optional[str] = None
    cantidad: Optional[float] = None
    unidad: Optional[str] = None
    fecha_salida: Optional[str] = None
    destino: Optional[str] = None
    notas: Optional[str] = None


class ComponenteIn(BaseModel):
    grupo: Optional[str] = None
    categoria: Optional[str] = None
    descripcion: Optional[str] = None
    cantidad_lote: Optional[float] = None
    unidad_lote: Optional[str] = None
    cantidad_ensamble: Optional[float] = None
    unidad: Optional[str] = None
    proveedor: Optional[str] = None
    unidad_inventario: Optional[str] = None
    notas: Optional[str] = None
    stock_minimo: Optional[float] = None
    en_dashboard: Optional[bool] = None
    orden: Optional[int] = None
    bom: Optional[Dict[str, float]] = None


class CatalogoIn(BaseModel):
    tipo: Optional[str] = None
    valor: Optional[str] = None
    efecto: Optional[float] = None
    descripcion: Optional[str] = None


class ProductoIn(BaseModel):
    nombre: str


def _datos(m: BaseModel) -> Dict[str, Any]:
    return m.model_dump(exclude_unset=True) if hasattr(m, "model_dump") else m.dict(exclude_unset=True)


# ---------------------------------------------------------------- lectura
@router.get("/dashboard")
async def get_dashboard():
    return await _run(svc.dashboard)


@router.get("/registros")
async def get_registros(q: str = "", movimiento: str = "", categoria: str = "", modelo: str = "", condicion: str = "",
                        desde: str = "", hasta: str = "", orden: str = "fecha", desc: bool = True,
                        limit: int = Query(200, ge=1, le=5000), offset: int = Query(0, ge=0)):
    return await _run(svc.listar_registros, q=q, movimiento=movimiento, categoria=categoria, modelo=modelo, condicion=condicion,
                      desde=desde, hasta=hasta, orden=orden, desc=desc, limit=limit, offset=offset)


@router.get("/registros/{mov_id}")
async def get_registro(mov_id: int):
    return await _run(svc.obtener_registro, mov_id)


@router.get("/componentes")
async def get_componentes():
    return await _run(svc.listar_componentes)


@router.get("/configuracion")
async def get_configuracion():
    return await _run(svc.configuracion)


@router.get("/export")
async def get_export():
    datos = await _run(svc.exportar_xlsx)
    nombre = f"INVENTARIO_TQTR_{date.today().isoformat()}.xlsx"
    return Response(content=datos, media_type=MIME_XLSX, headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


# ---------------------------------------------------------------- movimientos
@router.post("/registros", status_code=status.HTTP_201_CREATED)
async def post_registro(body: MovimientoIn):
    return await _run(svc.crear_registro, _datos(body))


@router.patch("/registros/{mov_id}")
async def patch_registro(mov_id: int, body: MovimientoIn):
    return await _run(svc.editar_registro, mov_id, _datos(body))


@router.delete("/registros/{mov_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_registro(mov_id: int):
    await _run(svc.eliminar_registro, mov_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------- componentes
@router.post("/componentes", status_code=status.HTTP_201_CREATED)
async def post_componente(body: ComponenteIn):
    return await _run(svc.crear_componente, _datos(body))


@router.patch("/componentes/{comp_id}")
async def patch_componente(comp_id: int, body: ComponenteIn):
    return await _run(svc.editar_componente, comp_id, _datos(body))


@router.delete("/componentes/{comp_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_componente(comp_id: int):
    await _run(svc.eliminar_componente, comp_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------- configuración
@router.post("/configuracion", status_code=status.HTTP_201_CREATED)
async def post_catalogo(body: CatalogoIn):
    return await _run(svc.crear_catalogo, body.tipo or "", body.valor or "", body.efecto, body.descripcion or "")


@router.patch("/configuracion/{cat_id}")
async def patch_catalogo(cat_id: int, body: CatalogoIn):
    return await _run(svc.editar_catalogo, cat_id, _datos(body))


@router.delete("/configuracion/{cat_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_catalogo(cat_id: int):
    await _run(svc.eliminar_catalogo, cat_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------- costos
class CostoIn(BaseModel):
    componente_id: Optional[int] = None
    descripcion: Optional[str] = None
    categoria: Optional[str] = None
    grupo: Optional[str] = None
    costo_unitario: Optional[float] = None
    unidad: Optional[str] = None
    moneda: Optional[str] = None
    cantidad_armado: Optional[float] = None
    proveedor: Optional[str] = None
    variante: Optional[str] = None
    incluido: Optional[bool] = None
    notas: Optional[str] = None
    orden: Optional[int] = None


class ParametrosCostoIn(BaseModel):
    tipo_cambio: Optional[float] = None
    producto: Optional[str] = None


@router.get("/costos")
async def get_costos():
    return await _run(svc.costos)


@router.patch("/costos/parametros")
async def patch_parametros_costos(body: ParametrosCostoIn):
    return await _run(svc.editar_parametros_costos, _datos(body))


@router.post("/costos", status_code=status.HTTP_201_CREATED)
async def post_costo(body: CostoIn):
    return await _run(svc.crear_costo, _datos(body))


@router.patch("/costos/{cid}")
async def patch_costo(cid: int, body: CostoIn):
    return await _run(svc.editar_costo, cid, _datos(body))


@router.delete("/costos/{cid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_costo(cid: int):
    await _run(svc.eliminar_costo, cid)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------- consumo por tarjeta (ficha de materiales)
class MaterialIn(BaseModel):
    id: Optional[int] = None
    componente_id: Optional[int] = None
    cantidad_real: Optional[float] = None
    nota: Optional[str] = None


class MaterialesIn(BaseModel):
    items: List[MaterialIn]


class ConsumoDesdeIn(BaseModel):
    consumo_desde: str


@router.get("/consumos")
async def get_consumos():
    return await _run(svc.consumos)


@router.patch("/consumos/parametros")
async def patch_consumo_desde(body: ConsumoDesdeIn):
    return await _run(svc.editar_consumo_desde, body.consumo_desde)


@router.get("/tarjetas/{tarjeta_id}/materiales")
async def get_materiales(tarjeta_id: int):
    return await _run(svc.materiales_tarjeta, tarjeta_id)


@router.patch("/tarjetas/{tarjeta_id}/materiales")
async def patch_materiales(tarjeta_id: int, body: MaterialesIn):
    return await _run(svc.editar_materiales_tarjeta, tarjeta_id, [_datos(i) for i in body.items])


# ---------------------------------------------------------------- stock mínimo y conversiones (v1.3.39)
class StockMinimoIn(BaseModel):
    stock_minimo: Optional[float] = None
    punto_reorden: Optional[float] = None
    armados_objetivo: Optional[int] = None
    entrega_dias: Optional[int] = None
    entrega_nota: Optional[str] = None
    proveedor: Optional[str] = None


class ArmadosObjetivoIn(BaseModel):
    armados_objetivo: int


class ConversionesIn(BaseModel):
    conv_silicon_g_por_envase: Optional[float] = None
    conv_catalizador_ml_por_envase: Optional[float] = None
    precio_silicon_envase: Optional[float] = None


@router.get("/stock-minimo")
async def get_stock_minimo():
    return await _run(svc.stock_minimo)


@router.patch("/stock-minimo")
async def patch_armados_objetivo(body: ArmadosObjetivoIn):
    return await _run(svc.editar_armados_objetivo, body.armados_objetivo)


@router.patch("/stock-minimo/{comp_id}")
async def patch_stock_minimo(comp_id: int, body: StockMinimoIn):
    return await _run(svc.editar_stock_minimo, comp_id, _datos(body))


@router.get("/conversiones")
async def get_conversiones():
    return await _run(svc.conversiones)


@router.patch("/conversiones")
async def patch_conversiones(body: ConversionesIn):
    return await _run(svc.editar_conversiones, _datos(body))


class ReclasificarIn(BaseModel):
    accion: str
    cantidad: float
    nota: Optional[str] = None


@router.post("/componentes/{comp_id}/reclasificar")
async def post_reclasificar(comp_id: int, body: ReclasificarIn):
    return await _run(svc.reclasificar_devueltas, comp_id, body.accion, body.cantidad, body.nota or "")


@router.post("/productos", status_code=status.HTTP_201_CREATED)
async def post_producto(body: ProductoIn):
    return await _run(svc.crear_producto, body.nombre)


@router.delete("/productos/{prod_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_producto(prod_id: int):
    await _run(svc.eliminar_producto, prod_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
