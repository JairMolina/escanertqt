"""Operaciones destructivas del área de administración.

Regla: NINGUNA se ejecuta sin antes haber hecho un respaldo completo de la BD (`respaldar`) y todas dejan registro en
la bitácora. El router valida la confirmación y el respaldo se hace ANTES de abrir la transacción de borrado, de modo
que aunque el borrado falle la copia ya existe.
"""
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import settings
from app.database import db
from app.database.db import NoEncontradoError


def respaldar(motivo: str, db_path: Optional[Path] = None) -> str:
    """Copia consistente de la BD (API de backup de SQLite, válida con WAL) en `BACKUP_DIR`. Devuelve el nombre del archivo."""
    settings.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    limpio = re.sub(r"[^a-z0-9_]+", "_", motivo.lower()).strip("_") or "admin"
    ruta = settings.BACKUP_DIR / f"tqt_{datetime.now():%Y%m%d_%H%M%S_%f}_{limpio}.db"
    origen = db.connect(db_path)
    destino = sqlite3.connect(ruta)
    try:
        origen.backup(destino)
    finally:
        destino.close()
        origen.close()
    return ruta.name


def listar_respaldos(limite: int = 10) -> List[Dict[str, Any]]:
    if not settings.BACKUP_DIR.exists():
        return []
    archivos = sorted(settings.BACKUP_DIR.glob("tqt_*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    return [{"nombre": p.name, "bytes": p.stat().st_size} for p in archivos[:limite]]


def resumen(db_path: Optional[Path] = None) -> Dict[str, Any]:
    with db.get_db(db_path) as c:
        lotes = []
        for lote in c.execute("SELECT id, codigo_lote, activo FROM lotes_mensuales ORDER BY anio DESC, mes DESC"):
            estados = {r["estado_general"]: r["n"] for r in c.execute(
                "SELECT COALESCE(p.estado_general,'PENDIENTE') AS estado_general, COUNT(*) n FROM tarjetas_produccion t "
                "LEFT JOIN pruebas_historial p ON p.tarjeta_id = t.id WHERE t.lote_id = ? GROUP BY 1", (lote["id"],))}
            lotes.append({"id": lote["id"], "codigo_lote": lote["codigo_lote"], "activo": bool(lote["activo"]),
                          "tarjetas": sum(estados.values()), "por_estado": estados})
        inventario: Dict[str, Dict[str, int]] = {}
        for r in c.execute("SELECT tipo, estado_ciclo, COUNT(*) n FROM pcb_inventario GROUP BY tipo, estado_ciclo"):
            inventario.setdefault(r["tipo"], {})[r["estado_ciclo"]] = r["n"]
        totales = {
            "tarjetas": c.execute("SELECT COUNT(*) FROM tarjetas_produccion").fetchone()[0],
            "pcb": c.execute("SELECT COUNT(*) FROM pcb_inventario").fetchone()[0],
            "bitacora": c.execute("SELECT COUNT(*) FROM escaneos").fetchone()[0],
        }
    path = Path(db_path or settings.DB_PATH)
    return {"lotes": lotes, "inventario": inventario, "totales": totales,
            "bd_bytes": path.stat().st_size if path.exists() else 0, "respaldos": listar_respaldos()}


def _existentes(c: sqlite3.Connection, tabla: str, ids: List[int]) -> List[int]:
    if not ids:
        return []
    ph = ",".join("?" * len(ids))
    return [r[0] for r in c.execute(f"SELECT id FROM {tabla} WHERE id IN ({ph})", ids)]


def verificar_tarjetas(ids: List[int], db_path: Optional[Path] = None) -> List[int]:
    """Ids de tarjeta que existen. NoEncontradoError si no existe ninguna (así no se hace respaldo para nada)."""
    with db.get_db(db_path) as c:
        ok = _existentes(c, "tarjetas_produccion", list(dict.fromkeys(ids)))
    if not ok:
        raise NoEncontradoError("Ninguna de las tarjetas indicadas existe.")
    return ok


def verificar_pcb(ids: List[int], db_path: Optional[Path] = None) -> List[int]:
    with db.get_db(db_path) as c:
        ok = _existentes(c, "pcb_inventario", list(dict.fromkeys(ids)))
    if not ok:
        raise NoEncontradoError("Ninguna de las PCB indicadas existe.")
    return ok


def _borrar_tarjetas_tx(c: sqlite3.Connection, ids: List[int], liberar_pcb: bool) -> Dict[str, Any]:
    pcbs: List[int] = []
    for tid in ids:
        fila = c.execute("SELECT pcb_r1_id, pcb_r2_id, pcb_r3_id FROM tarjetas_produccion WHERE id = ?", (tid,)).fetchone()
        if fila:
            pcbs += [x for x in fila if x]
    for tid in ids:
        c.execute("DELETE FROM tarjetas_produccion WHERE id = ?", (tid,))  # sus pruebas caen por ON DELETE CASCADE
    if pcbs:
        ph = ",".join("?" * len(pcbs))
        if liberar_pcb:
            c.execute(f"UPDATE pcb_inventario SET estado_ciclo='DISPONIBLE', estado_pcb='PENDIENTE', "
                      f"updated_at=datetime('now','localtime') WHERE id IN ({ph})", pcbs)
        else:
            c.execute(f"DELETE FROM pcb_inventario WHERE id IN ({ph})", pcbs)
    return {"tarjetas_borradas": len(ids), "pcb_liberadas": len(pcbs) if liberar_pcb else 0,
            "pcb_eliminadas": 0 if liberar_pcb else len(pcbs)}


def borrar_tarjetas(ids: List[int], liberar_pcb: bool, respaldo: str, db_path: Optional[Path] = None) -> Dict[str, Any]:
    with db.transaction(db_path) as c:
        existentes = _existentes(c, "tarjetas_produccion", list(dict.fromkeys(ids)))
        res = _borrar_tarjetas_tx(c, existentes, liberar_pcb)
        res["no_encontradas"] = [i for i in dict.fromkeys(ids) if i not in existentes]
        db.log_evento("ADMIN_TARJETAS_BORRADAS", None, str(len(existentes)),
                      f"liberar_pcb={liberar_pcb} respaldo={respaldo}", "admin", conn=c)
    return res


def borrar_pcb(ids: List[int], respaldo: str, db_path: Optional[Path] = None) -> Dict[str, Any]:
    with db.transaction(db_path) as c:
        existentes = _existentes(c, "pcb_inventario", list(dict.fromkeys(ids)))
        ph = ",".join("?" * len(existentes))
        montadas = [r["id"] for r in c.execute(
            f"SELECT id FROM tarjetas_produccion WHERE pcb_r1_id IN ({ph}) OR pcb_r2_id IN ({ph}) OR pcb_r3_id IN ({ph})",
            existentes * 3)] if existentes else []
        c.execute(f"DELETE FROM pcb_inventario WHERE id IN ({ph})", existentes) if existentes else None
        for tid in montadas:  # las tarjetas quedan incompletas: su estado general se recalcula (nunca LIBERADA sin R1/R2)
            db.recalcular_general(c, tid)
        db.log_evento("ADMIN_PCB_BORRADAS", None, str(len(existentes)),
                      f"tarjetas_afectadas={len(montadas)} respaldo={respaldo}", "admin", conn=c)
    return {"pcb_eliminadas": len(existentes), "tarjetas_afectadas": len(montadas),
            "no_encontradas": [i for i in dict.fromkeys(ids) if i not in existentes]}


def vaciar_lote(lote_id: int, eliminar_pcb: bool, respaldo: str, db_path: Optional[Path] = None) -> Dict[str, Any]:
    with db.transaction(db_path) as c:
        lote = c.execute("SELECT codigo_lote FROM lotes_mensuales WHERE id = ?", (lote_id,)).fetchone()
        if not lote:
            raise NoEncontradoError(f"Lote con ID {lote_id} no encontrado.")
        ids = [r[0] for r in c.execute("SELECT id FROM tarjetas_produccion WHERE lote_id = ?", (lote_id,))]
        res = _borrar_tarjetas_tx(c, ids, liberar_pcb=not eliminar_pcb)
        db.log_evento("ADMIN_LOTE_VACIADO", lote_id, lote["codigo_lote"],
                      f"tarjetas={len(ids)} eliminar_pcb={eliminar_pcb} respaldo={respaldo}", "admin", conn=c)
    return {"lote_id": lote_id, "codigo_lote": lote["codigo_lote"], **res}


def reset_total(respaldo: str, db_path: Optional[Path] = None) -> Dict[str, Any]:
    """Borra tarjetas, pruebas e inventario. Conserva los lotes, los ajustes (incluida la clave del admin) y los
    MOVIMIENTOS (bitácora): el historial de lo que se hizo, incluido este borrado, nunca se elimina desde aquí."""
    with db.transaction(db_path) as c:
        cuenta = {t: c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                  for t in ("tarjetas_produccion", "pcb_inventario", "pruebas_historial")}
        for t in ("pruebas_historial", "tarjetas_produccion", "pcb_inventario"):
            c.execute(f"DELETE FROM {t}")
        db.log_evento("ADMIN_RESET", None, "BORRAR TODO", f"borrado={cuenta} respaldo={respaldo}", "admin", conn=c)
    return {"borrado": cuenta, "lotes_conservados": True, "ajustes_conservados": True, "movimientos_conservados": True}


# ============================================================================
# Movimientos: consulta de la bitácora (qué se hizo, cuándo y quién)
# ============================================================================
# evento -> (categoría, texto para el usuario)
EVENTOS: Dict[str, tuple] = {
    "PCB_ALTA": ("alta", "Placa registrada"),
    "RECEPCION_CONFIRMADA": ("alta", "Lote de recepción confirmado"),
    "TARJETA_CREADA": ("alta", "Tarjeta creada"),
    "LOTE_CREADO": ("alta", "Lote creado"),
    "PCB_EDITADA": ("edicion", "Placa editada"),
    "VERSION_MASIVA": ("edicion", "Versión de hardware cambiada"),
    "MAC_GUARDADA": ("edicion", "MAC guardada"),
    "FIRMWARE_GUARDADO": ("edicion", "Firmware guardado"),
    "FIRMWARE_CATALOGO": ("edicion", "Catálogo de firmware"),
    "TARJETA_DATOS": ("edicion", "Datos de la tarjeta"),
    "PCB_FALLA": ("edicion", "Placa marcada con falla"),
    "PCB_REEMPLAZO": ("edicion", "Placa reemplazada"),
    "PCB_ASIGNADA": ("edicion", "Placa asignada a una tarjeta"),
    "PCB_LIBERADA": ("edicion", "Placa sacada de una tarjeta"),
    "AJUSTE": ("edicion", "Ajuste"),
    "LOTE_ACTIVADO": ("edicion", "Lote activado"),
    "PRUEBA": ("edicion", "Prueba (historial anterior)"),
    "PCB_ELIMINADA": ("eliminacion", "Placa eliminada"),
    "TARJETA_DISUELTA": ("eliminacion", "Tarjeta disuelta"),
    "ADMIN_TARJETAS_BORRADAS": ("eliminacion", "Tarjetas borradas (admin)"),
    "ADMIN_PCB_BORRADAS": ("eliminacion", "Placas borradas (admin)"),
    "ADMIN_LOTE_VACIADO": ("eliminacion", "Lote vaciado (admin)"),
    "ADMIN_RESET": ("eliminacion", "Borrado total (admin)"),
    "ADMIN_LOGIN": ("sesion", "Inicio de sesión de administrador"),
    "ADMIN_LOGIN_FALLIDO": ("sesion", "Intento de acceso fallido"),
    "ADMIN_BLOQUEO": ("sesion", "Acceso bloqueado por intentos"),
    "ADMIN_LOGOUT": ("sesion", "Cierre de sesión de administrador"),
    "ADMIN_CLAVE_CAMBIADA": ("sesion", "Contraseña cambiada"),
    "EXCEL_SINCRONIZADO": ("excel", "Excel sincronizado"),
    "EXCEL_EXPORTADO": ("excel", "Excel exportado"),
}
CATEGORIAS = {"alta": "Altas", "edicion": "Ediciones", "eliminacion": "Eliminaciones", "sesion": "Sesiones", "excel": "Excel", "otro": "Otros"}


def _categoria(evento: str) -> str:
    return EVENTOS.get(evento, ("otro", ""))[0]


def _titulo(evento: str) -> str:
    return EVENTOS.get(evento, ("otro", (evento or "").replace("_", " ").capitalize()))[1]


def movimientos(limite: int = 50, desplazamiento: int = 0, categoria: Optional[str] = None, q: Optional[str] = None,
                desde: Optional[str] = None, hasta: Optional[str] = None, lote_id: Optional[int] = None,
                db_path: Optional[Path] = None) -> Dict[str, Any]:
    """Bitácora de movimientos, del más reciente al más antiguo. Filtros: categoría (alta, edicion, eliminacion, sesion,
    excel, otro), texto libre (valor, detalle, operador), fechas YYYY-MM-DD y lote. Devuelve también el conteo por categoría."""
    for nombre, f in (("desde", desde), ("hasta", hasta)):
        if f:
            try:
                datetime.strptime(f, "%Y-%m-%d")
            except ValueError:
                raise ValueError(f"'{nombre}' debe tener el formato AAAA-MM-DD.")
    if categoria and categoria not in CATEGORIAS:
        raise ValueError("Categoría inválida: " + ", ".join(CATEGORIAS) + ".")
    conocidos = list(EVENTOS)
    base, params = [], []
    if q and q.strip():
        like = "%" + q.strip().replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"
        base.append("(e.valor LIKE ? ESCAPE '!' OR e.detalle LIKE ? ESCAPE '!' OR e.operador LIKE ? ESCAPE '!' OR e.evento LIKE ? ESCAPE '!')")
        params += [like, like, like, like]
    if desde:
        base.append("date(e.creado_en) >= ?")
        params.append(desde)
    if hasta:
        base.append("date(e.creado_en) <= ?")
        params.append(hasta)
    if lote_id:
        base.append("e.lote_id = ?")
        params.append(lote_id)
    filtros = list(base)
    fparams = list(params)
    if categoria:
        if categoria == "otro":
            filtros.append("e.evento NOT IN (" + ",".join("?" * len(conocidos)) + ")")
            fparams += conocidos
        else:
            ev = [k for k, v in EVENTOS.items() if v[0] == categoria]
            filtros.append("e.evento IN (" + ",".join("?" * len(ev)) + ")")
            fparams += ev
    w = ("WHERE " + " AND ".join(filtros)) if filtros else ""
    wb = ("WHERE " + " AND ".join(base)) if base else ""
    lim = max(1, min(int(limite), 200))
    with db.get_db(db_path) as c:
        total = c.execute(f"SELECT COUNT(*) FROM escaneos e {w}", fparams).fetchone()[0]
        filas = c.execute(
            f"SELECT e.id, e.creado_en, e.evento, e.valor, e.detalle, e.operador, e.lote_id, l.codigo_lote "
            f"FROM escaneos e LEFT JOIN lotes_mensuales l ON l.id = e.lote_id {w} ORDER BY e.id DESC LIMIT ? OFFSET ?",
            fparams + [lim, max(0, int(desplazamiento))]).fetchall()
        por_evento = c.execute(f"SELECT e.evento, COUNT(*) AS n FROM escaneos e {wb} GROUP BY e.evento", params).fetchall()
    conteo = {k: 0 for k in CATEGORIAS}
    for r in por_evento:
        conteo[_categoria(r["evento"])] += r["n"]
    items = [{"id": r["id"], "fecha": r["creado_en"], "evento": r["evento"], "categoria": _categoria(r["evento"]),
              "titulo": _titulo(r["evento"]), "valor": r["valor"], "detalle": r["detalle"], "operador": r["operador"],
              "lote_id": r["lote_id"], "lote": r["codigo_lote"]} for r in filas]
    return {"total": total, "items": items, "categorias": CATEGORIAS, "conteo": conteo,
            "limite": lim, "desplazamiento": max(0, int(desplazamiento))}
