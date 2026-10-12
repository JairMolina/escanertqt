"""Pruebas y validación por Bluetooth LE: bitácora de lo que el navegador (Web Bluetooth) hace con las tarjetas TQT."""
import io
import json
import re
import secrets
import threading
import time
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from app.database import db, inventario as inv
from app.routers.ws import manager
from app.services import usuarios
from app.routers.stm32 import station_token
from app.services import stm32_programming as svc

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
_ips: Dict[str, str] = {}   # estación -> última IP del agente
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
    firmware: Optional[str] = Field(default=None, max_length=40)   # opcional: el agente puede reportarlo


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
                "address": e["address"], "visto": round(time.time() - e["visto"], 1), "eventos": list(e["eventos"][-20:]),
                # v1.3.67: varios usuarios prueban a la vez; quién usa la conexión de esta laptop
                "en_uso_por": (_ultimo.get(station_id) or {}).get("operador") if e["conectado"] else None}


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
async def ble_claim(body: ReclamoBLE, request: Request, st=Depends(station_token)):
    sid = st["id"]
    _recordar_ip(sid, request)
    await run_in_threadpool(_tocar, sid)
    ahora = time.time()
    with _lock:
        _purgar(ahora)
        e = _estado_de(sid)
        antes = (e["conectado"], e["nombre"], e["address"])
        e.update(ble_disponible=body.ble_disponible, conectado=body.conectado,
                 nombre=body.nombre if body.conectado else None, address=body.address if body.conectado else None,
                 firmware=body.firmware if body.conectado else None, visto=ahora)
        job = None
        for j in sorted(_jobs.values(), key=lambda x: x["creado"]):
            if j["station"] == sid and j["estado"] == "pendiente":
                j["estado"] = "en_curso"
                job = {"id": j["id"], "accion": j["accion"], "address": j["address"], "comando": j["comando"]}
                break
    await _aviso_estado(sid, antes, e)
    return job


@agent_router.post("/evento")
async def ble_evento(body: EventoBLE, request: Request, st=Depends(station_token)):
    sid = st["id"]
    _recordar_ip(sid, request)
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
async def ble_resultado(jid: str, body: ResultadoBLE, request: Request, st=Depends(station_token)):
    sid = st["id"]
    _recordar_ip(sid, request)
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


# ───────── v1.3.64: estaciones, comparación y validación ─────────
def _ip_cliente(request: Request) -> str:
    h = request.headers
    ip = (h.get("cf-connecting-ip") or "").strip()
    if not ip:
        ip = (h.get("x-forwarded-for") or "").split(",")[0].strip()
    return ip or (request.client.host if request.client else "")


def _recordar_ip(sid: str, request: Request) -> None:
    ip = _ip_cliente(request)
    if ip:
        _ips[sid] = ip


@router.get("/estaciones", summary="Estaciones en línea; marca la que está en la IP de quien consulta")
async def estaciones(request: Request):
    en_linea = [e for e in await run_in_threadpool(svc.stations) if e["online"]]
    ip = _ip_cliente(request)
    mias = [e for e in en_linea if _misma_red(ip, _ips.get(e["id"]))]
    if mias:
        return {"estaciones": [dict(id=e["id"], name=e["name"], online=True, esta_laptop=True, ip=_ips.get(e["id"])) for e in mias], "coincide": True, "ip": ip}
    return {"estaciones": [dict(id=e["id"], name=e["name"], online=True, esta_laptop=False, ip=_ips.get(e["id"])) for e in en_linea], "coincide": False, "ip": ip}


def _misma_red(a: Optional[str], b: Optional[str]) -> bool:
    """v1.3.66: misma IP; en IPv6 basta el mismo prefijo /64 (las direcciones temporales cambian el resto)."""
    if not a or not b:
        return False
    if a == b:
        return True
    if ":" in a and ":" in b:
        import ipaddress
        try:
            return ipaddress.ip_network(a + "/64", strict=False) == ipaddress.ip_network(b + "/64", strict=False)
        except ValueError:
            return False
    return False


def _mac_norm(m) -> str:
    return re.sub(r"[^0-9A-F]", "", (m or "").upper())


def _nombre_norm(n) -> str:
    return re.sub(r"[^0-9A-Z]", "", (n or "").upper())


def _version_de_nombre(n) -> Optional[str]:
    m = re.search(r"_V(\d)(\d)(?:_|$)", (n or "").upper())
    return f"{m.group(1)}.{m.group(2)}" if m else None


def _mayor_menor(fw) -> Optional[str]:
    m = re.match(r"\s*v?(\d+)(?:\.(\d+))?", str(fw or ""), re.I)
    return f"{int(m.group(1))}.{int(m.group(2) or 0)}" if m else None


def _nombre_ble_esperado(p: Dict[str, Any]) -> Optional[str]:
    if p.get("tipo") == "R2":
        m = re.search(r"(\d{4})\s*$", p.get("nombre") or "")
        if m and m.group(1) != "0000":
            from app.services.firmware_build import nombre_ble_r2
            try:
                return nombre_ble_r2(m.group(1))
            except Exception:
                return None
    return None


def _comparar(codigo: str, station_id: str) -> Dict[str, Any]:
    init()
    try:
        r = inv.consulta((codigo or "").strip())
    except ValueError:
        raise HTTPException(404, "No reconozco el código.")
    except db.NoEncontradoError:
        raise HTTPException(404, "El código no existe.")
    pcb, tj = r.get("pcb"), r.get("tarjeta")
    tid = (tj or {}).get("id") or (pcb or {}).get("tarjeta_id")
    tarjeta = db.get_tarjeta_by_id(tid) if tid else None
    if not tarjeta and not pcb:
        raise HTTPException(404, "El código no existe.")
    placas = []
    fuente = [tarjeta.get(k) for k in ("r1", "r2", "r3")] if tarjeta else [pcb]
    for p in fuente:
        if not p:
            continue
        with db.get_db() as c:
            row = c.execute("SELECT tipo, nombre, mac, firmware FROM pcb_inventario WHERE id=?", (p.get("id"),)).fetchone()
        d = dict(row) if row else dict(tipo=p.get("tipo"), nombre=p.get("nombre"), mac=p.get("mac"), firmware=p.get("firmware"))
        d["id"] = p.get("id")
        d["nombre_ble"] = _nombre_ble_esperado(d)
        placas.append(d)
    with _lock:
        e = dict(_estados.get(station_id) or {})
    con = bool(e.get("conectado"))
    ble = dict(conectado=con, nombre=e.get("nombre") if con else None,
               address=e.get("address") if con else None, firmware=e.get("firmware") if con else None)
    probada = None
    if con:
        for p in placas:
            if (p["mac"] and _mac_norm(p["mac"]) == _mac_norm(ble["address"])) or \
               (p["nombre_ble"] and _nombre_norm(p["nombre_ble"]) == _nombre_norm(ble["nombre"])):
                probada = p
                break
    checks: List[Dict[str, Any]] = []

    def chk(campo, etiqueta, esperado, actual, ok, detalle=""):
        checks.append(dict(campo=campo, etiqueta=etiqueta, esperado=esperado, actual=actual, ok=ok, detalle=detalle))

    esperadas = ", ".join(p["nombre"] or "?" for p in placas)
    if not con:
        chk("tarjeta", "Tarjeta", esperadas, None, False, "No hay un dispositivo BLE conectado en la estación.")
    elif not probada:
        chk("tarjeta", "Tarjeta", esperadas, ble["nombre"] or ble["address"], False,
            "El dispositivo conectado no corresponde a ninguna placa de esta tarjeta.")
    else:
        chk("tarjeta", "Tarjeta", probada["nombre"], ble["nombre"] or ble["address"], True, f"Placa {probada['tipo']} reconocida.")
        esp = probada["nombre_ble"]
        if esp:
            ok = _nombre_norm(esp) == _nombre_norm(ble["nombre"])
            chk("nombre", "Nombre BLE", esp, ble["nombre"], ok, "" if ok else "El nombre BLE no coincide con el esperado.")
        else:
            chk("nombre", "Nombre BLE", None, ble["nombre"], None, "Sin nombre BLE esperado para esta placa.")
        if probada["mac"]:
            ok = _mac_norm(probada["mac"]) == _mac_norm(ble["address"])
            chk("mac", "MAC", probada["mac"], ble["address"], ok, "" if ok else "La MAC registrada no coincide con la del dispositivo.")
        else:
            chk("mac", "MAC", None, ble["address"], None, "La placa no tiene MAC registrada.")
        act_fw = _mayor_menor(ble["firmware"]) or _version_de_nombre(ble["nombre"])
        if not probada["firmware"]:
            chk("firmware", "Firmware", None, act_fw, None, "La placa no tiene firmware registrado.")
        elif not act_fw:
            chk("firmware", "Firmware", probada["firmware"], None, None, "No reportado por el dispositivo.")
        else:
            ok = _mayor_menor(probada["firmware"]) == act_fw
            chk("firmware", "Firmware", probada["firmware"], act_fw, ok,
                "" if ok else "La versión del dispositivo no coincide con el firmware registrado.")
        with db.get_db() as c:
            cmds = {x["comando"] for x in c.execute(
                "SELECT DISTINCT comando FROM validaciones_ble WHERE resultado='ok' AND comando IN ('PPON','POFF') "
                "AND (pcb_id=? OR (ble_id IS NOT NULL AND UPPER(ble_id)=UPPER(?)))", (probada["id"], ble["address"] or ""))}
        falta = [x for x in ("PPON", "POFF") if x not in cmds]
        chk("pruebas", "Pruebas PPON/POFF", "PPON y POFF ok", ", ".join(sorted(cmds)) or "ninguna", not falta,
            "" if not falta else "Falta: " + ", ".join(falta))
    ids = [p["id"] for p in placas if p["id"]]
    with db.get_db() as c:
        v = c.execute("SELECT comando, creado_en, operador FROM validaciones_ble WHERE resultado='ok' AND comando IN "
                      "('VALIDACION_AUTO','VALIDACION_MANUAL') AND (tarjeta_id IS ? OR pcb_id IN (%s)) ORDER BY id DESC LIMIT 1"
                      % ",".join("?" * len(ids)), [tarjeta["id"] if tarjeta else None] + ids).fetchone()
    validada = dict(modo="auto" if v["comando"].endswith("AUTO") else "manual", creado_en=v["creado_en"], operador=v["operador"]) if v else None
    return {"codigo": codigo, "tarjeta": tarjeta,
            "placas": [{k: p[k] for k in ("tipo", "nombre", "mac", "firmware", "nombre_ble")} for p in placas],
            "ble": ble, "placa_probada": probada["tipo"] if probada else None, "checks": checks,
            "ok": not any(c["ok"] is False for c in checks), "validada": validada,
            "_probada_id": probada["id"] if probada else None}


@router.get("/comparar", summary="Compara la tarjeta escaneada con el dispositivo BLE conectado")
async def comparar(codigo: str = Query(min_length=1, max_length=2000), station_id: str = Query(min_length=1, max_length=24)):
    res = await run_in_threadpool(_comparar, codigo, station_id)
    res.pop("_probada_id", None)
    return res


class ValidarIn(BaseModel):
    codigo: str = Field(min_length=1, max_length=2000)
    station_id: str = Field(min_length=1, max_length=24)
    modo: Literal["auto", "manual"] = "auto"
    motivo: Optional[str] = Field(default=None, max_length=300)


def _validar(datos: ValidarIn, operador: str):
    res = _comparar(datos.codigo, datos.station_id)
    if datos.modo == "auto" and not res["ok"]:
        fallos = [c["etiqueta"] for c in res["checks"] if c["ok"] is False]
        return JSONResponse(status_code=409, content={"detail": "No se puede validar: " + ", ".join(fallos), "checks": res["checks"]}), None
    tj = res["tarjeta"]
    tid = tj["id"] if tj else None
    pid = res.pop("_probada_id", None)
    if not pid and tj:
        pid = tj.get("pcb_r2_id") or tj.get("pcb_r1_id")
    if not pid and not tid:
        return JSONResponse(status_code=409, content={"detail": "No hay tarjeta ni placa que validar.", "checks": res["checks"]}), None
    manual = datos.modo == "manual"
    detalle = json.dumps({"motivo": datos.motivo, "fallidos": [c for c in res["checks"] if c["ok"] is False]},
                         ensure_ascii=False) if manual else None
    disp = (res["ble"]["nombre"] or res["ble"]["address"] or "BLE")[:100]
    cmd = "VALIDACION_MANUAL" if manual else "VALIDACION_AUTO"
    with db.transaction() as c:
        cur = c.execute(
            "INSERT INTO validaciones_ble (pcb_id, tarjeta_id, dispositivo, ble_id, comando, resultado, detalle, operador, creado_en) "
            "VALUES (?,?,?,?,?,'ok',?,?, datetime('now','localtime'))",
            (pid, tid, disp, res["ble"]["address"], cmd, detalle, operador))
        reg = _fila(c.execute(_SEL + " WHERE v.id = ?", (cur.lastrowid,)).fetchone())
    db.log_evento("VALIDACION_BLE", valor=disp, operador=operador, detalle=cmd)
    nuevo = _comparar(datos.codigo, datos.station_id)
    nuevo.pop("_probada_id", None)
    return reg, nuevo


@router.post("/validar", summary="Marcar una tarjeta como Validada (automática o manual)")
async def validar(datos: ValidarIn, request: Request):
    operador = _operador(request)
    reg, res = await run_in_threadpool(_validar, datos, operador)
    if res is None:
        return reg
    await manager.broadcast("VALIDACION_BLE", reg)
    return res


# --- v1.3.65: placas validadas (auto/manual) y confirmación de la tarjeta como «Validada» ---
def _usuario_ids(c) -> Dict[str, int]:
    """email -> id de usuario (rowid de la tabla usuarios)."""
    try:
        return {r["email"]: r["rowid"] for r in c.execute("SELECT rowid, email FROM usuarios")}
    except Exception:
        return {}


def _placas_validadas(todas: bool) -> Dict[str, Any]:
    with db.get_db() as c:
        ids = _usuario_ids(c)
        filas = c.execute(
            "SELECT v.id, v.pcb_id, v.comando, v.creado_en, v.operador, p.nombre AS pcb_nombre, p.tipo AS pcb_tipo, "
            "t.id AS tarjeta_id, t.id_tarjeta_num, "
            "(SELECT pr.operador FROM validaciones_ble pr WHERE pr.resultado='ok' AND pr.comando IN ('PPON','POFF') AND pr.pcb_id=v.pcb_id ORDER BY pr.id DESC LIMIT 1) AS probo, "
            "(SELECT tv.creado_en FROM validaciones_ble tv WHERE tv.comando='TARJETA_VALIDADA' AND tv.resultado='ok' AND tv.tarjeta_id=t.id ORDER BY tv.id DESC LIMIT 1) AS tarjeta_validada_en "
            "FROM validaciones_ble v JOIN pcb_inventario p ON p.id = v.pcb_id "
            "LEFT JOIN tarjetas_produccion t ON t.id = COALESCE(v.tarjeta_id, (SELECT x.id FROM tarjetas_produccion x WHERE v.pcb_id IN (x.pcb_r1_id, x.pcb_r2_id) LIMIT 1)) "
            "WHERE v.resultado='ok' AND v.comando IN ('VALIDACION_AUTO','VALIDACION_MANUAL') "
            "AND v.id = (SELECT MAX(z.id) FROM validaciones_ble z WHERE z.pcb_id=v.pcb_id AND z.resultado='ok' AND z.comando IN ('VALIDACION_AUTO','VALIDACION_MANUAL')) "
            "ORDER BY v.id DESC LIMIT 300").fetchall()
    items = []
    for r in filas:
        d = dict(r)
        if not todas and d["tarjeta_validada_en"] and d["tarjeta_validada_en"][:10] < time.strftime("%Y-%m-%d"):
            continue   # ya confirmadas en días anteriores: no saturar la lista
        d["modo"] = "manual" if d.pop("comando").endswith("MANUAL") else "auto"
        d["probo"] = d["probo"] or d["operador"]
        d["probo_id"], d["operador_id"] = ids.get(d["probo"]), ids.get(d["operador"])
        d["tarjeta_validada"] = bool(d["tarjeta_validada_en"])
        items.append(d)
    return {"items": items}


@router.get("/placas-validadas", summary="Placas validadas (auto/manual) y si su tarjeta ya quedó «Validada»")
async def placas_validadas(request: Request, todas: bool = False):
    yo = _operador(request)
    res = await run_in_threadpool(_placas_validadas, todas)
    with db.get_db() as c:
        res["yo"] = {"email": yo, "id": _usuario_ids(c).get(yo)}
    return res


class TarjetasValidarIn(BaseModel):
    tarjeta_ids: List[int] = Field(min_length=1, max_length=200)


def _validar_tarjetas(ids: List[int], operador: str) -> Dict[str, Any]:
    hechas = []
    with db.transaction() as c:
        for tid in dict.fromkeys(ids):
            t = c.execute("SELECT id, id_tarjeta_num FROM tarjetas_produccion WHERE id=?", (tid,)).fetchone()
            if not t:
                continue
            ya = c.execute("SELECT 1 FROM validaciones_ble WHERE comando='TARJETA_VALIDADA' AND resultado='ok' AND tarjeta_id=?", (tid,)).fetchone()
            if ya:
                continue
            c.execute("INSERT INTO validaciones_ble (tarjeta_id, dispositivo, comando, resultado, operador, creado_en) "
                      "VALUES (?, ?, 'TARJETA_VALIDADA', 'ok', ?, datetime('now','localtime'))",
                      (tid, ("Tarjeta " + str(t["id_tarjeta_num"]))[:100], operador))
            hechas.append(tid)
    for tid in hechas:
        db.log_evento("VALIDACION_BLE", valor=str(tid), operador=operador, detalle="TARJETA_VALIDADA")
    return {"validadas": hechas}


@router.post("/tarjetas/validar", summary="Cambiar a «Validada» un conjunto de tarjetas")
async def validar_tarjetas(datos: TarjetasValidarIn, request: Request):
    operador = _operador(request)
    res = await run_in_threadpool(_validar_tarjetas, datos.tarjeta_ids, operador)
    await manager.broadcast("VALIDACION_BLE", {"comando": "TARJETA_VALIDADA", "tarjetas": res["validadas"], "operador": operador})
    return res
