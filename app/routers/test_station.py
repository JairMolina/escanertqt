"""Authenticated operator API and outbound-only Windows station API."""

import io, json, secrets, threading, time, zipfile
from functools import lru_cache
from pathlib import Path
from typing import Literal
from fastapi import APIRouter, Depends, Request, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from app.routers.stm32 import station_token, operator, run
from app.services import test_station as svc, stm32_programming as stm
from app.services import native_ble, pruebas_auto, skytec, usuarios, instalador_windows
from app.database import db

router = APIRouter(prefix="/api/validacion/tqt", tags=["Pruebas TQT"])
agent_router = APIRouter(prefix="/api/stm32/agent/tests", tags=["Agente Pruebas TQT"])


class Start(BaseModel):
    station_id: str = Field(pattern="^[a-f0-9]{24}$")
    tarjeta_id: int = Field(gt=0)
    physical_confirmed: bool = False


class Command(BaseModel):
    station_id: str = Field(pattern="^[a-f0-9]{24}$")
    action: Literal[
        "ports",
        "connect_serial",
        "disconnect_serial",
        "scan_ble",
        "connect_ble",
        "disconnect_ble",
        "serial",
        "ble",
    ]
    port: str = Field(default="", max_length=100)
    address: str = Field(default="", max_length=64)
    command: str = Field(default="", max_length=40)
    tarjeta_id: int | None = Field(default=None, gt=0)


class Event(BaseModel):
    seq: int = Field(ge=1)
    data: dict


class Events(BaseModel):
    items: list[Event] = Field(max_length=100)


# v1.4.0: ejecuciones desde el navegador (Web Serial/Web Bluetooth) con banco seguro fijo.
class WebStart(BaseModel):
    tarjeta_id: int = Field(gt=0)


class WebEvents(BaseModel):
    items: list[Event] = Field(default_factory=list, max_length=100)


class WebIdentity(BaseModel):
    detectada: dict
    confirmar: bool = False


class Installer(BaseModel):
    name: str = Field(default="Banco de pruebas local", max_length=60, min_length=1)
    ble_only: bool = False
    puerto_serie: str | None = Field(default=None, max_length=120, pattern=r"^/dev/[A-Za-z0-9_./:+-]+$|^COM[0-9]{1,3}$")   # v1.4.51: banco fijo
    formato: Literal["zip", "cmd"] = "zip"   # v1.4.64: «cmd» = instalador autoextraíble de doble clic
    station_id: str | None = Field(default=None, pattern="^[a-f0-9]{24}$")   # v1.4.64: reinstalar la misma estación


class NativeBleCommand(BaseModel):
    station_id: str = Field(pattern='^[a-f0-9]{24}$')
    request_id: str = Field(pattern='^[a-f0-9]{32}$')
    operation: Literal['scan', 'connect', 'send', 'disconnect']
    role: Literal['R1', 'R2'] | None = None   # v1.4.64: opcional solo para «scan» (lista lo que ve el puente)
    tarjeta_id: int | None = Field(default=None, gt=0)
    run_id: str | None = Field(default=None, pattern='^[a-f0-9]{32}$')
    mac: str | None = Field(default=None, max_length=32)
    command: Literal['PPON', 'POFF'] | None = None
    status_raw: str = Field(default='', max_length=4096)


@router.get('/web/ble/stations')
def native_stations(req: Request):
    return run(native_ble.stations, operator(req))


@router.post('/web/ble/commands')
def native_prepare(body: NativeBleCommand, req: Request):
    return run(native_ble.prepare, operator(req), body.model_dump())


@router.get('/web/ble/commands/{identifier}')
def native_result(identifier: str, req: Request):
    return run(native_ble.result, operator(req), identifier)


@agent_router.post('/ble/{identifier}/authorize')
def native_authorize(identifier: str, st=Depends(station_token)):
    return run(native_ble.authorize, st['id'], identifier)


@router.get("/stations")
def stations(req: Request):
    svc.init()
    yo = operator(req)
    with db.get_db() as c:
        return [
            dict(
                id=r["station"],
                name=r["name"],
                online=time.time() - r["seen"] < 15,
                **json.loads(r["state"]),
            )
            for r in c.execute(
                "SELECT p.*,s.name FROM tqt_test_presence p JOIN stm32_stations s ON s.id=p.station WHERE s.revoked_at IS NULL AND s.name NOT LIKE ? AND lower(s.owner)=lower(?)", (svc.RASPBERRY_LIKE, yo)
            )
            # v1.4.55: un puente «solo BLE» no ejecuta pruebas ni abre el COM; no se ofrece como agente
            if not json.loads(r["state"]).get("ble_only")
        ]


@router.get("/agentes/desactualizados")
def agentes_desactualizados(req: Request):
    return svc.desactualizados(operator(req))


@router.post("/commands")
def commands(body: Command, req: Request):
    with db.get_db() as c:
        run(svc.propia, c, body.station_id, operator(req))
    return run(svc.command, body.station_id, body.action, body.model_dump())


@router.get("/commands/{jid}")
def command_result(jid: str):
    svc.init()
    with db.get_db() as c:
        r = c.execute(
            "SELECT state,result FROM tqt_test_commands WHERE id=?", (jid,)
        ).fetchone()
    if not r:
        raise HTTPException(404, "Comando no encontrado.")
    return {
        "state": r["state"],
        "result": json.loads(r["result"]) if r["result"] else None,
    }


@router.post("/runs")
def start(body: Start, req: Request):
    return run(
        svc.create,
        body.station_id,
        body.tarjeta_id,
        operator(req),
        body.physical_confirmed,
    )


@router.get("/runs")
def history(tarjeta_id: int | None = None):
    svc.init()
    with db.get_db() as c:
        w, a = db.clausula_lote(c, "t.lote_id")
        where = " WHERE 1=1" + w
        if tarjeta_id:
            where += " AND r.requested_card=?"
            a.append(tarjeta_id)
        return [
            dict(r)
            for r in c.execute(
                "SELECT r.id,r.requested_card,r.tarjeta_id,r.operator,r.state,r.created,r.updated,r.result,r.origin,r.station,s.name station_name,s.owner station_owner FROM tqt_test_runs r JOIN stm32_stations s ON s.id=r.station LEFT JOIN tarjetas_produccion t ON t.id=COALESCE(r.tarjeta_id,r.requested_card)"
                + where
                + " ORDER BY r.created DESC LIMIT 500",
                a,
            )
        ]


@router.post("/web/runs")
def web_start(body: WebStart, req: Request):
    return run(svc.web_create, body.tarjeta_id, operator(req))


@router.post("/web/runs/{jid}/events")
def web_events(jid: str, body: WebEvents, req: Request):
    return run(svc.web_events, operator(req), jid, [x.model_dump() for x in body.items])


@router.post("/web/runs/{jid}/identity")
def web_identity(jid: str, body: WebIdentity, req: Request):
    return run(svc.web_identity, operator(req), jid, body.detectada, body.confirmar)


@router.post("/web/runs/{jid}/result")
def web_result(jid: str, body: dict, req: Request):
    return run(svc.web_finish, operator(req), jid, body)


@router.get("/runs/{jid}")
def get_run(jid: str):
    return run(svc.read, jid)


@router.post("/runs/{jid}/cancel")
def cancel(jid: str, req: Request):
    svc.read(jid)
    with db.get_db() as c:
        # v1.4.56: solo quien la inició, el dueño del agente o un administrador
        u = usuarios.validar_sesion(req.cookies.get(usuarios.COOKIE))
        r = c.execute("SELECT r.operator,s.owner FROM tqt_test_runs r JOIN stm32_stations s ON s.id=r.station WHERE r.id=?", (jid,)).fetchone()
        if r and u.get("rol") != "administrador" and u["email"].lower() not in (str(r["operator"]).lower(), str(r["owner"]).lower()):
            raise HTTPException(403, "Esa prueba es de otra cuenta; no puedes cancelarla.")
        c.execute(
            "UPDATE tqt_test_runs SET cancel=1 WHERE id=? AND state IN ('queued','running')",
            (jid,),
        )
    return {
        "ok": True,
        "detail": "Cancelación solicitada; el firmware puede finalizar el movimiento actual.",
    }


@router.post("/tarjetas/{tarjeta_id}/skytec")
def alta_skytec(tarjeta_id: int, req: Request):
    """v1.4.58: al imprimir etiquetas de un armado aprobado, registra R1 y R2 como candados en Skytec."""
    operator(req)
    from app.routers.excel_dymo import _exigir_aprobada  # import diferido: evita ciclos
    _exigir_aprobada(tarjeta_id)
    return alta_skytec_tarjeta(tarjeta_id, operator(req))


def alta_skytec_tarjeta(tarjeta_id: int, operador: str):
    try:
        return skytec.alta_tarjeta(tarjeta_id, operador)
    except skytec.TarjetaNoEncontrada as e:
        raise HTTPException(404, str(e))
    except (skytec.SkytecNoConfigurado, skytec.SkytecError) as e:
        raise HTTPException(503, str(e))


@router.get("/runs/{jid}/events")
def get_events(jid: str, after: int = Query(0, ge=0)):
    svc.read(jid)
    with db.get_db() as c:
        rows = c.execute(
            "SELECT seq,data FROM tqt_test_events WHERE run=? AND seq>? ORDER BY seq LIMIT 500",
            (jid, after),
        ).fetchall()
    return [{"seq": r["seq"], "data": json.loads(r["data"])} for r in rows]


def texto_log(jid):
    """LOG original completo de una ejecución (o, si no llegó, las líneas de log de sus eventos)."""
    svc.read(jid)
    with db.get_db() as c:
        rows = c.execute(
            "SELECT data FROM tqt_test_events WHERE run=? ORDER BY seq", (jid,)
        ).fetchall()
    full = [
        json.loads(r["data"])["text"]
        for r in rows
        if json.loads(r["data"]).get("kind") == "full_log"
    ]
    text = (
        full[-1]
        if full
        else "".join(
            json.loads(r["data"])["args"][0] + "\n"
            for r in rows
            if json.loads(r["data"]).get("kind") == "log"
        )
    )
    return text


@router.get("/runs/{jid}/log")
def log(jid: str):
    text = texto_log(jid)
    return Response(
        text,
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{jid}.log"',
            "Cache-Control": "no-store",
        },
    )


@router.get("/runs/{jid}/json")
def report_json(jid: str):
    d = run(svc.read, jid)
    with db.get_db() as c:
        d["events"] = [
            {"seq": r["seq"], "data": json.loads(r["data"])}
            for r in c.execute(
                "SELECT seq,data FROM tqt_test_events WHERE run=? ORDER BY seq", (jid,)
            )
        ]
    return Response(
        json.dumps(d, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{jid}.json"',
            "Cache-Control": "no-store",
        },
    )


@router.get("/inventory/{tid}")
def inventory(tid: int):
    with db.get_db() as c:
        return run(svc.snapshot, tid, c)


@router.post("/installer")
def installer(body: Installer, req: Request):
    svc.init()
    yo = operator(req)
    st = None
    if body.station_id:   # v1.4.64: misma estación (id, nombre y dueño) con token nuevo; nunca la de otra cuenta ni la Raspberry
        with db.get_db() as c:
            reutilizable = not svc.es_raspberry(c, body.station_id)
        st = stm.station_rotate(body.station_id, yo) if reutilizable else None
    if st is None:
        st = stm.station_create(body.name, yo)
    if body.formato == "cmd":
        zip_bytes = paquete_agente(dict(server=str(req.base_url).rstrip("/"), ble_only=body.ble_only,
                                        **({"serial_port": body.puerto_serie} if body.puerto_serie else {}), **st))
        nombre, datos = instalador_windows.construir(zip_bytes, st["id"], body.ble_only)
        return Response(datos, media_type="application/octet-stream", headers={
            "Content-Disposition": f'attachment; filename="{nombre}"', "Cache-Control": "no-store",
            "X-TQT-Station": st["id"]})
    res = zip_agente(req, st, body.ble_only, body.puerto_serie, f'TQT_Pruebas_{st["id"]}.zip')
    res.headers["X-TQT-Station"] = st["id"]
    return res


def paquete_agente(config=None):
    """ZIP de station/test_station (sin tests ni cachés). Con config, añade config.json (lleva el token)."""
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as z:
        root = Path(__file__).resolve().parents[2] / "station/test_station"
        for f in sorted(root.rglob("*")):
            rel = f.relative_to(root)
            if (f.is_file() and "__pycache__" not in rel.parts and "tests" not in rel.parts and ".venv" not in rel.parts
                    and "evidence" not in rel.parts and rel.suffix != ".db"
                    and rel.name not in ("config.json", "agent.log", "puerto_serie.txt", ".agent.lock")):
                z.write(f, rel)
        if config is not None:
            z.writestr("config.json", json.dumps(config, indent=2))
    return stream.getvalue()


def config_agente(req, st, ble_only, puerto_serie):
    return dict(server=str(req.base_url).rstrip("/"), ble_only=ble_only,
                **({"serial_port": puerto_serie} if puerto_serie else {}), **st)


def zip_agente(req, st, ble_only, puerto_serie, nombre):
    datos = paquete_agente(config_agente(req, st, ble_only, puerto_serie))
    return Response(
        datos,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{nombre}"',
            "Cache-Control": "no-store",
        },
    )


@agent_router.get("/package")
def agent_package(st=Depends(station_token)):
    """v1.4.64: autoactualización del agente Windows: el mismo paquete SIN config.json (el token no viaja)."""
    return Response(paquete_agente(), media_type="application/zip", headers={
        "Content-Disposition": 'attachment; filename="TQT_Agente_paquete.zip"', "Cache-Control": "no-store"})


# v1.4.64: avance del instalador .cmd (corre oculto): lo reporta con el token de su config.json y la web lo consulta.
# En memoria: es solo un aviso de progreso; si el servidor se reinicia, la web sigue con la presencia del agente.
INSTALACION = {}
ETAPAS = ("extrayendo", "python", "dependencias", "arrancando", "listo", "error")


class InstallProgress(BaseModel):
    etapa: Literal["extrayendo", "python", "dependencias", "arrancando", "listo", "error"]
    mensaje: str = Field("", max_length=500)


@agent_router.post("/install-progress")
def install_progress(body: InstallProgress, st=Depends(station_token)):
    INSTALACION[st["id"]] = dict(etapa=body.etapa, mensaje=body.mensaje, ts=time.time())
    return {"ok": True}


# v1.4.64: instalador .sh de la Raspberry por «curl … | sh»: código de UN solo uso que caduca a los 15 min (en memoria).
# Sin sesión ni Bearer: el middleware ya deja pasar /api/stm32/agent/ y aquí el código aleatorio es la credencial.
INSTALADORES_SH = {}
INSTALADOR_SH_S = 15 * 60
_instaladores_lock = threading.Lock()


def guardar_instalador_sh(datos, ahora=None):
    """Guarda el .sh y devuelve (codigo, expira). Purga los caducados."""
    ahora = ahora or time.time()
    codigo = secrets.token_urlsafe(24)
    with _instaladores_lock:
        for k in [k for k, v in INSTALADORES_SH.items() if v[0] <= ahora]:
            INSTALADORES_SH.pop(k, None)
        INSTALADORES_SH[codigo] = (ahora + INSTALADOR_SH_S, datos)
    return codigo, ahora + INSTALADOR_SH_S


@agent_router.get("/instalar/{codigo}.sh")
def instalar_sh(codigo: str):
    with _instaladores_lock:
        v = INSTALADORES_SH.pop(codigo, None)   # un solo uso: se borra al servirlo
    if not v or v[0] <= time.time():
        raise HTTPException(404, "Comando de instalación caducado o ya usado; genera otro en la página.")
    return Response(v[1], media_type="text/x-shellscript; charset=utf-8", headers={"Cache-Control": "no-store"})


@router.get("/installer/{sid}/estado")
def installer_estado(sid: str, req: Request):
    """Estado para la página: etapa del instalador + presencia/versión del agente de ESA estación (solo la propia)."""
    yo = operator(req)
    with db.get_db() as c:
        run(svc.propia, c, sid, yo)
        r = c.execute("SELECT p.seen,p.state FROM tqt_test_presence p JOIN stm32_stations s ON s.id=p.station "
                      "WHERE p.station=? AND s.revoked_at IS NULL", (sid,)).fetchone()
    st = json.loads(r["state"]) if r else {}
    online = bool(r) and time.time() - r["seen"] < 15
    servidor = _version_servidor()
    return dict(**INSTALACION.get(sid, {"etapa": "", "mensaje": "", "ts": 0}), online=online,
                agent_version=st.get("agent_version") or "", servidor_version=servidor,
                listo=online and (not servidor or st.get("agent_version") == servidor))


@lru_cache(maxsize=1)
def _version_servidor():
    return svc.agente_actual()


@agent_router.post("/claim")
def claim(body: dict, st=Depends(station_token)):
    res = run(svc.claim, st["id"], body)
    if isinstance(res, dict):   # v1.4.64: el agente Windows se autoactualiza si su AGENT_VERSION difiere
        res = dict(res, agent_version=_version_servidor())
    if pruebas_auto.pide_log(st["id"]):   # v1.4.51: la web de Pruebas automáticas pidió el agent.log
        res = dict(res, subir_log=True)
    return res


class AgentLog(BaseModel):
    texto: str = Field(max_length=400_000)


@agent_router.post("/agent-log")
def agent_log(body: AgentLog, st=Depends(station_token)):
    return run(pruebas_auto.guardar_log, st["id"], body.texto)


@agent_router.post("/commands/{jid}/result")
def command_done(jid: str, body: dict, st=Depends(station_token)):
    with db.get_db() as c:
        r = c.execute(
            "SELECT * FROM tqt_test_commands WHERE id=? AND station=? AND state IN ('running','done')",
            (jid, st["id"]),
        ).fetchone()
        if not r:
            raise HTTPException(400, "Comando ajeno o expirado.")
        encoded = json.dumps(body)
        if r["state"] == "done" and r["result"] != encoded:
            raise HTTPException(400, "No se reemplaza un resultado.")
        c.execute(
            "UPDATE tqt_test_commands SET state='done',result=? WHERE id=?",
            (encoded, jid),
        )
    return {"ok": True}


@agent_router.post("/runs/{jid}/events")
def events(jid: str, body: Events, st=Depends(station_token)):
    return run(svc.events, st["id"], jid, [x.model_dump() for x in body.items])


@agent_router.post("/runs/{jid}/result")
def finish(jid: str, body: dict, st=Depends(station_token)):
    return run(svc.finish, st["id"], jid, body)
