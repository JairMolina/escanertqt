"""v1.4.89: pestaña «Módulos» del Centro de administración. Listado y borrado de los datos de cada módulo.

Seguridad: sesión de usuario con rol administrador (`_admin` de plataforma) Y token X-Admin-Token válido (`admin_requerido`);
el listado de módulos exige solo el rol. Todo borrado hace antes un respaldo de la BD (mismo mecanismo que /api/admin).
Una colección solo se puede borrar si su servicio ya tiene un borrado seguro; si no, es `solo_lectura`.
"""
from typing import Any, Callable, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from app import modulos as catalogo
from app.database import admin_ops, db, inventario as inv
from app.database.db import NoEncontradoError
from app.routers.admin import _cambio, _destructiva, admin_requerido
from app.routers.plataforma import _admin
from app.services import activos as svc_activos
from app.services import antijammer, caiquen, sigfox, speedlocker, tpms

router = APIRouter(prefix="/api/plataforma/admin", tags=["Plataforma · administración de módulos"])

LIMITE_MAX = 500


class BorrarIn(BaseModel):
    ids: List[int] = Field(..., min_length=1, max_length=LIMITE_MAX)


def _col(k: str, label: str, mono: bool = False) -> Dict[str, Any]:
    return {"k": k, "label": label, "mono": True} if mono else {"k": k, "label": label}


def _todos_los_lotes(fn: Callable[[], Any]) -> Any:
    """Ejecuta `fn` viendo TODOS los lotes (la cabecera X-TQT-Lote no aplica a esta vista de administración)."""
    token = db.LOTE_VISTA.set(0)
    try:
        return fn()
    finally:
        db.LOTE_VISTA.reset(token)


def _existentes(tabla: str, ids: List[int], vacio: str) -> List[int]:
    with db.get_db() as c:
        ok = {r[0] for r in c.execute(f"SELECT id FROM {tabla} WHERE id IN ({','.join('?' * len(ids))})", ids)}
    if not ok:
        raise NoEncontradoError(vacio)
    return [i for i in ids if i in ok]


# ---------------------------------------------------------------------------- Escáner TQT
def _nom(p: Optional[Dict[str, Any]]) -> str:
    return (p or {}).get("nombre") or ""


def _tarjetas(q: str, limit: int, offset: int) -> Tuple[List[Dict[str, Any]], int]:
    items, total = _todos_los_lotes(lambda: db.list_tarjetas(limit=limit, offset=offset, search=q or None))
    return [{"id": t["id"], "tarjeta": t["id_tarjeta_num"], "r1": _nom(t.get("r1")), "r2": _nom(t.get("r2")), "r3": _nom(t.get("r3")),
             "estado": t.get("estado_general") or ""} for t in items], total


def _pcb(q: str, limit: int, offset: int) -> Tuple[List[Dict[str, Any]], int]:
    d = _todos_los_lotes(lambda: inv.listar_pcb(q=q or None, limit=limit, offset=offset))
    return [{"id": p["id"], "tipo": p.get("tipo"), "nombre": p.get("nombre"), "mac": p.get("mac") or "",
             "estado": p.get("estado_ciclo") or "", "tarjeta": p.get("id_tarjeta_num") or ""} for p in d["items"]], d["total"]


def _borrar_tarjetas(ids: List[int], respaldo: str) -> Dict[str, Any]:
    # liberar_pcb=True: las PCB vuelven a DISPONIBLE (no se pierde inventario); mismo borrado que /api/admin/tarjetas
    return admin_ops.borrar_tarjetas(ids, True, respaldo)


def _borrar_pcb(ids: List[int], respaldo: str) -> Dict[str, Any]:
    return admin_ops.borrar_pcb(ids, respaldo)


# ---------------------------------------------------------------------------- placas de Caiquén, Skudo, TPMS y SpeedLocker
_CAMPOS_PLACA = ("nombre", "version", "serie", "lote", "estado", "firmware", "recibida_en")


def _placas(tabla: str, svc: Any) -> Dict[str, Any]:
    def listar(q: str, limit: int, offset: int):
        svc._asegurar()
        w, a = "", []
        if q:
            w = " WHERE (nombre LIKE ? OR serie LIKE ? OR lote LIKE ? OR IFNULL(firmware,'') LIKE ?)"
            a = [f"%{q}%"] * 4
        with db.get_db() as c:
            total = c.execute(f"SELECT COUNT(*) FROM {tabla}{w}", a).fetchone()[0]
            filas = c.execute(f"SELECT * FROM {tabla}{w} ORDER BY id DESC LIMIT ? OFFSET ?", a + [limit, offset]).fetchall()
        return [{"id": f["id"], **{k: (f[k] if k in f.keys() and f[k] is not None else "") for k in _CAMPOS_PLACA}} for f in filas], total

    def verificar(ids: List[int]) -> List[int]:
        svc._asegurar()
        return _existentes(tabla, ids, "Ninguna de las placas indicadas existe.")

    def borrar(ids: List[int], respaldo: str) -> Dict[str, Any]:
        n = 0
        for i in ids:   # el borrado seguro del servicio (una transacción y evento en su bitácora por placa)
            try:
                svc.eliminar(i, "admin")
                n += 1
            except Exception:   # ya no existe
                continue
        return {"eliminados": n}
    cols = [_col("nombre", "Placa", True), _col("version", "Versión"), _col("serie", "Serie", True), _col("lote", "Lote"),
            _col("estado", "Estado"), _col("firmware", "Firmware"), _col("recibida_en", "Recibida")]
    return _coleccion("placas", "Placas", cols, listar, borrar, verificar, "BORRAR_" + tabla.upper())


# ---------------------------------------------------------------------------- Impresora (activos)
def _activos(q: str, limit: int, offset: int):
    svc_activos._asegurar()
    w, a = "", []
    if q:
        w = " WHERE (nombre LIKE ? OR categoria LIKE ? OR serie LIKE ? OR responsable LIKE ? OR ubicacion LIKE ?)"
        a = [f"%{q}%"] * 5
    with db.get_db() as c:
        total = c.execute(f"SELECT COUNT(*) FROM activos{w}", a).fetchone()[0]
        filas = c.execute(f"SELECT * FROM activos{w} ORDER BY numero DESC LIMIT ? OFFSET ?", a + [limit, offset]).fetchall()
    return [{"id": f["id"], "codigo": svc_activos.codigo_de(f["numero"]), "nombre": f["nombre"], "categoria": f["categoria"],
             "ubicacion": f["ubicacion"], "responsable": f["responsable"], "estado": f["estado"]} for f in filas], total


def _verificar_activos(ids: List[int]) -> List[int]:
    svc_activos._asegurar()
    return _existentes("activos", ids, "Ninguno de los activos indicados existe.")


def _borrar_activos(ids: List[int], respaldo: str) -> Dict[str, Any]:
    with db.get_db() as c:
        nums = [r["numero"] for r in c.execute(f"SELECT numero FROM activos WHERE id IN ({','.join('?' * len(ids))})", ids)]
    return svc_activos.eliminar_lote([svc_activos.codigo_de(n) for n in nums], "admin")   # borrado seguro existente (con bitácora)


# ---------------------------------------------------------------------------- catálogo de colecciones
def _coleccion(id_: str, nombre: str, columnas: List[Dict[str, Any]], listar: Callable, borrar: Optional[Callable] = None,
               verificar: Optional[Callable] = None, evento: str = "") -> Dict[str, Any]:
    return {"id": id_, "nombre": nombre, "columnas": columnas, "listar": listar, "borrar": borrar, "verificar": verificar, "evento": evento}


def _colecciones() -> Dict[str, Dict[str, Dict[str, Any]]]:
    return {
        catalogo.ESCANER_TQT: {
            "tarjetas": _coleccion("tarjetas", "Tarjetas", [_col("tarjeta", "Tarjeta", True), _col("r1", "R1", True), _col("r2", "R2", True),
                                                          _col("r3", "R3", True), _col("estado", "Estado")],
                                   _tarjetas, _borrar_tarjetas, admin_ops.verificar_tarjetas, "BORRAR_TARJETAS"),
            "pcb": _coleccion("pcb", "PCB", [_col("tipo", "Tipo"), _col("nombre", "Nombre", True), _col("mac", "MAC", True),
                                              _col("estado", "Estado"), _col("tarjeta", "Tarjeta", True)],
                              _pcb, _borrar_pcb, admin_ops.verificar_pcb, "BORRAR_PCB"),
        },
        catalogo.IMPRESORA: {"activos": _coleccion("activos", "Activos", [
            _col("codigo", "Código", True), _col("nombre", "Nombre"), _col("categoria", "Categoría"), _col("ubicacion", "Ubicación"),
            _col("responsable", "Responsable"), _col("estado", "Estado")], _activos, _borrar_activos, _verificar_activos, "BORRAR_ACTIVOS")},
        catalogo.CAIQUEN: {"placas": _placas("caiquen_pcb", caiquen)},
        catalogo.ANTIJAMMER: {"placas": _placas("antijammer_pcb", antijammer)},
        catalogo.SIGFOX: {"placas": _placas("sigfox_pcb", sigfox)},
        catalogo.TPMS: {"placas": _placas("tpms_pcb", tpms)},
        catalogo.SPEEDLOCKER: {"placas": _placas("speedlocker_pcb", speedlocker)},
    }


def _resolver(modulo: str, col: str) -> Dict[str, Any]:
    if modulo not in catalogo.IDS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Módulo no encontrado.")
    c = _colecciones().get(modulo, {}).get(col)
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Colección no encontrada.")
    return c


@router.get("/modulos", summary="Módulos con sus colecciones administrables (solo rol administrador)")
def listar_modulos(_: Dict = Depends(_admin)):
    cols = _colecciones()
    return [{"id": m["id"], "nombre": m["nombre"],
             "colecciones": [{"id": c["id"], "nombre": c["nombre"], "solo_lectura": not c["borrar"]}
                             for c in cols.get(m["id"], {}).values()],
             "vaciar": False} for m in catalogo.MODULOS]


@router.get("/modulos/{modulo}/colecciones/{col}", summary="Registros de una colección")
async def listar_coleccion(modulo: str, col: str, q: str = Query("", max_length=60), limit: int = Query(50, ge=1, le=LIMITE_MAX),
                           offset: int = Query(0, ge=0), _u: Dict = Depends(_admin), _t: Dict = Depends(admin_requerido)):
    c = _resolver(modulo, col)
    try:
        items, total = await run_in_threadpool(c["listar"], q.strip(), limit, offset)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    return {"columnas": c["columnas"], "items": items, "total": total, "solo_lectura": not c["borrar"]}


@router.delete("/modulos/{modulo}/colecciones/{col}", summary="Borrar registros (con respaldo previo)")
async def borrar_coleccion(modulo: str, col: str, body: BorrarIn, _u: Dict = Depends(_admin), _t: Dict = Depends(admin_requerido)):
    c = _resolver(modulo, col)
    if not c["borrar"]:
        raise HTTPException(status.HTTP_405_METHOD_NOT_ALLOWED, "Esta colección es de solo lectura.")
    ids = list(dict.fromkeys(body.ids))
    # verifica que existan y hace el respaldo ANTES de tocar nada (404 si no existe ninguno; 500 sin borrar si falla el respaldo)
    respaldo = await _destructiva(f"borrar_{modulo}_{col}", c["verificar"], ids)
    res = await run_in_threadpool(c["borrar"], ids, respaldo)
    n = int(next((res[k] for k in ("eliminados", "tarjetas_borradas", "pcb_eliminadas") if k in res), 0))
    await _cambio(c["evento"], respaldo, modulo=modulo, coleccion=col, eliminados=n)
    return {"eliminados": n, "respaldo": respaldo}
