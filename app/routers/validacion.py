"""Pruebas y validación por Bluetooth LE: bitácora de lo que el navegador (Web Bluetooth) hace con las tarjetas TQT."""
import io
import secrets
import threading
import time
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.database import db, inventario as inv
from app.routers.ws import manager
from app.services import usuarios
from app.routers.stm32 import station_token

router = APIRouter(prefix="/api/validacion", tags=["Pruebas y validación BLE"])

TESTER_DIR = Path(__file__).resolve().parents[2] / "station" / "ble_tester"
_DDL = """CREATE TABLE IF NOT EXISTS validaciones_ble (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pcb_id INTEGER, tarjeta_id INTEGER,
    dispositivo TEXT NOT NULL, ble_id TEXT,
    comando TEXT NOT NULL, resultado TEXT NOT NULL,
    detalle TEXT, respuesta TEXT, operador TEXT,
    creado_en TEXT NOT NULL DEFAULT (datetime('now','localtime')))"""
_IDX = "CREATE INDEX IF NOT EXISTS ix_validaciones_ble ON validaciones_ble(id DESC)"


def init():
    with db.get_db() as c:
        c.execute(_DDL)
        c.execute(_IDX)


class Registro(BaseModel):
    codigo: Optional[str] = Field(default=None, max_length=200)
    dispositivo: str = Field(min_length=1, max_length=100)
    ble_id: Optional[str] = Field(default=None, max_length=200)
    comando: Literal["CONECTAR", "PPON", "POFF", "DESCONECTAR", "NOTIFICACION"]
    resultado: Literal["ok", "error"]
    detalle: Optional[str] = Field(default=None, max_length=1000)
    respuesta: Optional[str] = Field(default=None, max_length=1000)


def _resolver(texto: Optional[str]):
    if not texto or not texto.strip():
        return None, None
    try:
        r = inv.consulta(texto.strip())
    except (ValueError, db.NoEncontradoError):
        return None, None
    return r.get("pcb"), r.get("tarjeta")


def _fila(r) -> Dict[str, Any]:
    d = dict(r)
    d["pcb"] = {"id": d["pcb_id"], "nombre": d.pop("pcb_nombre", None), "tipo": d.pop("pcb_tipo", None)} if d["pcb_id"] else None
    d["tarjeta"] = {"id": d["tarjeta_id"], "id_tarjeta_num": d.pop("id_tarjeta_num", None)} if d["tarjeta_id"] else None
    d.pop("pcb_nombre", None); d.pop("pcb_tipo", None); d.pop("id_tarjeta_num", None)
    return d


_SEL = """SELECT v.*, p.nombre AS pcb_nombre, p.tipo AS pcb_tipo, t.id_tarjeta_num AS id_tarjeta_num
          FROM validaciones_ble v LEFT JOIN pcb_inventario p ON p.id = v.pcb_id
          LEFT JOIN tarjetas_produccion t ON t.id = v.tarjeta_id"""


def _crear(datos: Registro, operador: str) -> Dict[str, Any]:
    init()
    pcb, tarjeta = _resolver(datos.codigo)
    if not pcb and not tarjeta:
        pcb, tarjeta = _resolver(datos.dispositivo)
    pcb_id = pcb["id"] if pcb else None
    tarjeta_id = tarjeta["id"] if tarjeta else (pcb or {}).get("tarjeta_id")
    with db.transaction() as c:
        cur = c.execute(
            "INSERT INTO validaciones_ble (pcb_id, tarjeta_id, dispositivo, ble_id, comando, resultado, detalle, respuesta, operador, creado_en) "
            "VALUES (?,?,?,?,?,?,?,?,?, datetime('now','localtime'))",
            (pcb_id, tarjeta_id, datos.dispositivo.strip(), datos.ble_id, datos.comando, datos.resultado,
             datos.detalle, datos.respuesta, operador))
        fila = c.execute(_SEL + " WHERE v.id = ?", (cur.lastrowid,)).fetchone()
        reg = _fila(fila)
    db.log_evento("VALIDACION_BLE", valor=datos.dispositivo, operador=operador,
                  detalle=f"{datos.comando} {datos.resultado}" + (f": {datos.detalle}" if datos.detalle else ""))
    return reg


@router.post("/registros", summary="Registrar una acción de validación BLE")
async def crear_registro(datos: Registro, request: Request):
    try:
        operador = usuarios.validar_sesion(request.cookies.get(usuarios.COOKIE))["email"]
    except usuarios.SesionInvalidaError:
        raise HTTPException(401, "Inicia sesión.")
    reg = await run_in_threadpool(_crear, datos, operador)
    await manager.broadcast("VALIDACION_BLE", reg)
    return reg


def _listar(tarjeta_id, pcb_id, q, limit) -> Dict[str, Any]:
    init()
    cond: List[str] = []
    args: List[Any] = []
    if tarjeta_id:
        cond.append("v.tarjeta_id = ?"); args.append(tarjeta_id)
    if pcb_id:
        cond.append("v.pcb_id = ?"); args.append(pcb_id)
    if q and q.strip():
        like = f"%{q.strip()}%"
        cond.append("(v.dispositivo LIKE ? OR p.nombre LIKE ? OR v.comando LIKE ?)"); args += [like, like, like]
    where = (" WHERE " + " AND ".join(cond)) if cond else ""
    with db.get_db() as c:
        total = c.execute("SELECT COUNT(*) FROM validaciones_ble v LEFT JOIN pcb_inventario p ON p.id = v.pcb_id" + where, args).fetchone()[0]
        filas = c.execute(_SEL + where + " ORDER BY v.id DESC LIMIT ?", args + [limit]).fetchall()
        return {"items": [_fila(f) for f in filas], "total": total}


@router.get("/registros", summary="Historial de validaciones BLE (más recientes primero)")
async def listar(tarjeta_id: Optional[int] = None, pcb_id: Optional[int] = None, q: Optional[str] = Query(None, max_length=100),
                 limit: int = Query(100, ge=1, le=500)):
    return await run_in_threadpool(_listar, tarjeta_id, pcb_id, q, limit)


def _resumen() -> Dict[str, Any]:
    init()
    with db.get_db() as c:
        r = c.execute("SELECT COUNT(*) n, COALESCE(SUM(resultado='ok'),0) ok, COALESCE(SUM(resultado='error'),0) er, "
                      "COUNT(DISTINCT dispositivo) d FROM validaciones_ble WHERE date(creado_en) = date('now','localtime')").fetchone()
        u = c.execute(_SEL + " ORDER BY v.id DESC LIMIT 1").fetchone()
        return {"hoy": r["n"], "ok_hoy": r["ok"], "error_hoy": r["er"], "dispositivos_hoy": r["d"], "ultima": _fila(u) if u else None}


@router.get("/resumen", summary="Resumen de validaciones de hoy")
async def resumen():
    return await run_in_threadpool(_resumen)


@router.get("/tester.zip", summary="Descarga del tester BLE para Windows")
async def tester_zip():
    if not TESTER_DIR.is_dir():
        raise HTTPException(404, "El tester BLE no está disponible en este servidor.")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(TESTER_DIR.rglob("*")):
            if f.is_file() and "__pycache__" not in f.parts:
                z.write(f, f.relative_to(TESTER_DIR).as_posix())
    return Response(buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="TQT_BLE_Tester_Windows_v1.1.zip"'})


# ---------------------------------------------------------------------------
# BLE mediante el agente Windows de la estación (cola en memoria)
# ---------------------------------------------------------------------------
agent_router = APIRouter(prefix="/api/stm32/agent/ble", tags=["Agente BLE"])

JOB_TTL = 60          # s: un trabajo que nadie toma caduca
RESULT_TTL = 300      # s: el resultado se conserva
ONLINE = 20           # s: ventana de estación conectada
_lock = threading.Lock()
_jobs: Dict[str, Dict[str, Any]] = {}
_estados: Dict[str, Dict[str, Any]] = {}
_ultimo: Dict[str, Dict[str, Any]] = {}   # estación -> {operador, codigo}


class TrabajoBLE(BaseModel):
    station_id: str = Field(min_length=24, max_length=24)
    accion: Literal["escanear", "conectar", "enviar", "desconectar"]
    address: Optional[str] = Field(default=None, max_length=64)
    comando: Optional[Literal["PPON", "POFF"]] = None
    codigo: Optional[str] = Field(default=None, max_length=200)


class ReclamoBLE(BaseModel):
    ble_disponible: bool = False
    conectado: bool = False
    nombre: Optional[str] = Field(default=None, max_length=200)
    address: Optional[str] = Field(default=None, max_length=64)


class ResultadoBLE(BaseModel):
    ok: bool
    resultado: Optional[Dict[str, Any]] = None
    error: Optional[str] = Field(default=None, max_length=1000)


class EventoBLE(BaseModel):
    tipo: Literal["notificacion", "desconexion"]
    texto: Optional[str] = Field(default=None, max_length=1000)
    nombre: Optional[str] = Field(default=None, max_length=200)
    address: Optional[str] = Field(default=None, max_length=64)


def _purgar(ahora: float) -> None:
    for jid, j in list(_jobs.items()):
        if j["estado"] == "pendiente" and ahora - j["creado"] > JOB_TTL:
            j.update(estado="error", error="La estación no tomó el trabajo a tiempo.", fin=ahora)
        if j.get("fin") and ahora - j["fin"] > RESULT_TTL:
            del _jobs[jid]


def _estacion_en_linea(sid: str) -> bool:
    with db.get_db() as c:
        r = c.execute("SELECT last_seen FROM stm32_stations WHERE id=?", (sid,)).fetchone()
    return bool(r) and time.time() - r["last_seen"] <= ONLINE


def _operador(request: Request) -> str:
    try:
        return usuarios.validar_sesion(request.cookies.get(usuarios.COOKIE))["email"]
    except usuarios.SesionInvalidaError:
        raise HTTPException(401, "Inicia sesión.")


def _crear_trabajo(datos: TrabajoBLE, operador: str) -> Dict[str, Any]:
    if datos.accion == "enviar" and not datos.comando:
        raise HTTPException(422, "Indica el comando (PPON o POFF).")
    if not _estacion_en_linea(datos.station_id):
        raise HTTPException(400, "La estación Windows no existe o está desconectada. Inicia el agente.")
    ahora = time.time()
    jid = secrets.token_hex(8)
    with _lock:
        _purgar(ahora)
        _jobs[jid] = dict(id=jid, station=datos.station_id, accion=datos.accion, address=datos.address,
                          comando=datos.comando, codigo=datos.codigo, operador=operador, estado="pendiente",
                          resultado=None, error=None, creado=ahora, fin=None)
        _ultimo[datos.station_id] = dict(operador=operador, codigo=datos.codigo)
    return {"id": jid, "accion": datos.accion, "estado": "pendiente"}


@router.post("/ble/trabajos", summary="Pedir al agente de la estación una acción BLE")
async def ble_crear_trabajo(datos: TrabajoBLE, request: Request):
    operador = _operador(request)
    return await run_in_threadpool(_crear_trabajo, datos, operador)


@router.get("/ble/trabajos/{jid}", summary="Estado de un trabajo BLE")
async def ble_trabajo(jid: str):
    with _lock:
        _purgar(time.time())
        j = _jobs.get(jid)
        if not j:
            raise HTTPException(404, "Trabajo no encontrado o caducado.")
        return {k: j[k] for k in ("id", "accion", "estado", "resultado", "error")}


@router.get("/ble/estado", summary="Estado BLE de la estación")
async def ble_estado(station_id: str = Query(min_length=1, max_length=24)):
    with _lock:
        e = _estados.get(station_id)
        if not e:
            return {"ble_disponible": False, "conectado": False, "nombre": None, "address": None, "visto": None, "eventos": []}
        return {"ble_disponible": e["ble_disponible"], "conectado": e["conectado"], "nombre": e["nombre"],
                "address": e["address"], "visto": round(time.time() - e["visto"], 1), "eventos": list(e["eventos"][-20:])}


def _estado_de(sid: str) -> Dict[str, Any]:
    return _estados.setdefault(sid, dict(ble_disponible=False, conectado=False, nombre=None, address=None, visto=0.0, eventos=[]))


async def _aviso_estado(sid: str, antes, e) -> None:
    if antes != (e["conectado"], e["nombre"], e["address"]):
        await manager.broadcast("BLE_ESTADO", {"station_id": sid, "conectado": e["conectado"], "nombre": e["nombre"], "address": e["address"]})


async def _registrar(comando: str, ok: bool, nombre, address, detalle=None, respuesta=None, operador=None, codigo=None) -> None:
    datos = Registro(codigo=codigo, dispositivo=(nombre or address or "BLE")[:100], ble_id=address,
                     comando=comando, resultado="ok" if ok else "error",
                     detalle=(detalle or None) and detalle[:1000], respuesta=(respuesta or None) and respuesta[:1000])
    reg = await run_in_threadpool(_crear, datos, operador or "estación")
    await manager.broadcast("VALIDACION_BLE", reg)


def _tocar(sid: str) -> None:
    with db.get_db() as c:
        c.execute("UPDATE stm32_stations SET last_seen=? WHERE id=?", (time.time(), sid))


@agent_router.post("/claim")
async def ble_claim(body: ReclamoBLE, st=Depends(station_token)):
    sid = st["id"]
    await run_in_threadpool(_tocar, sid)
    ahora = time.time()
    with _lock:
        _purgar(ahora)
        e = _estado_de(sid)
        antes = (e["conectado"], e["nombre"], e["address"])
        e.update(ble_disponible=body.ble_disponible, conectado=body.conectado,
                 nombre=body.nombre if body.conectado else None, address=body.address if body.conectado else None, visto=ahora)
        job = None
        for j in sorted(_jobs.values(), key=lambda x: x["creado"]):
            if j["station"] == sid and j["estado"] == "pendiente":
                j["estado"] = "en_curso"
                job = {"id": j["id"], "accion": j["accion"], "address": j["address"], "comando": j["comando"]}
                break
    await _aviso_estado(sid, antes, e)
    return job


@agent_router.post("/evento")
async def ble_evento(body: EventoBLE, st=Depends(station_token)):
    sid = st["id"]
    with _lock:
        e = _estado_de(sid)
        antes = (e["conectado"], e["nombre"], e["address"])
        nombre = body.nombre or e["nombre"]
        address = body.address or e["address"]
        e["eventos"].append({"t": time.time(), "tipo": body.tipo, "texto": body.texto or ""})
        del e["eventos"][:-20]
        if body.tipo == "desconexion":
            e.update(conectado=False, nombre=None, address=None)
        ult = dict(_ultimo.get(sid) or {})
    if body.tipo == "notificacion":
        await _registrar("NOTIFICACION", True, nombre, address, respuesta=body.texto, operador=ult.get("operador"), codigo=ult.get("codigo"))
    else:
        await _registrar("DESCONECTAR", True, nombre, address, detalle=body.texto or "Desconexión del dispositivo",
                         operador=ult.get("operador"), codigo=ult.get("codigo"))
    await _aviso_estado(sid, antes, e)
    return {"ok": True}


@agent_router.post("/{jid}/resultado")
async def ble_resultado(jid: str, body: ResultadoBLE, st=Depends(station_token)):
    sid = st["id"]
    with _lock:
        j = _jobs.get(jid)
        if not j or j["station"] != sid:
            raise HTTPException(404, "Trabajo no encontrado.")
        r = body.resultado or {}
        j.update(estado="ok" if body.ok else "error", resultado=r, error=None if body.ok else (body.error or "Error BLE"), fin=time.time())
        e = _estado_de(sid)
        antes = (e["conectado"], e["nombre"], e["address"])
        nombre = r.get("nombre") or e["nombre"]
        address = r.get("address") or e["address"] or j["address"]
        if body.ok and j["accion"] == "conectar":
            e.update(conectado=True, nombre=r.get("nombre"), address=r.get("address") or j["address"])
        elif body.ok and j["accion"] == "desconectar":
            e.update(conectado=False, nombre=None, address=None)
        accion, comando, operador, codigo = j["accion"], j["comando"], j["operador"], j["codigo"]
    err = None if body.ok else (body.error or "Error BLE")
    if accion == "conectar":
        await _registrar("CONECTAR", body.ok, nombre, address, err, operador=operador, codigo=codigo)
    elif accion == "enviar":
        await _registrar(comando, body.ok, nombre, address, err, r.get("respuesta"), operador, codigo)
    elif accion == "desconectar":
        await _registrar("DESCONECTAR", body.ok, nombre, address, err, operador=operador, codigo=codigo)
    await _aviso_estado(sid, antes, e)
    return {"ok": True}
