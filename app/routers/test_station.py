"""Authenticated operator API and outbound-only Windows station API."""

import io, json, time, zipfile
from pathlib import Path
from typing import Literal
from fastapi import APIRouter, Depends, Request, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from app.routers.stm32 import station_token, operator, run
from app.services import test_station as svc, stm32_programming as stm
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


@router.get("/stations")
def stations():
    svc.init()
    with db.get_db() as c:
        return [
            dict(
                id=r["station"],
                name=r["name"],
                online=time.time() - r["seen"] < 15,
                **json.loads(r["state"]),
            )
            for r in c.execute(
                "SELECT p.*,s.name FROM tqt_test_presence p JOIN stm32_stations s ON s.id=p.station"
            )
        ]


@router.post("/commands")
def commands(body: Command):
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
        where = " WHERE requested_card=?" if tarjeta_id else ""
        return [
            dict(r)
            for r in c.execute(
                "SELECT id,requested_card,tarjeta_id,operator,state,created,updated,result,origin FROM tqt_test_runs"
                + where
                + " ORDER BY created DESC LIMIT 500",
                (tarjeta_id,) if tarjeta_id else (),
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
def cancel(jid: str):
    svc.read(jid)
    with db.get_db() as c:
        c.execute(
            "UPDATE tqt_test_runs SET cancel=1 WHERE id=? AND state IN ('queued','running')",
            (jid,),
        )
    return {
        "ok": True,
        "detail": "Cancelación solicitada; el firmware puede finalizar el movimiento actual.",
    }


@router.get("/runs/{jid}/events")
def get_events(jid: str, after: int = Query(0, ge=0)):
    svc.read(jid)
    with db.get_db() as c:
        rows = c.execute(
            "SELECT seq,data FROM tqt_test_events WHERE run=? AND seq>? ORDER BY seq LIMIT 500",
            (jid, after),
        ).fetchall()
    return [{"seq": r["seq"], "data": json.loads(r["data"])} for r in rows]


@router.get("/runs/{jid}/log")
def log(jid: str):
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
    st = stm.station_create(body.name, operator(req))
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as z:
        root = Path(__file__).resolve().parents[2] / "station/test_station"
        for f in root.rglob("*"):
            if f.is_file() and "__pycache__" not in f.parts and "tests" not in f.parts:
                z.write(f, f.relative_to(root))
        z.writestr(
            "config.json",
            json.dumps(dict(server=str(req.base_url).rstrip("/"), **st), indent=2),
        )
    return Response(
        stream.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="TQT_Pruebas_{st["id"]}.zip"',
            "Cache-Control": "no-store",
        },
    )


@agent_router.post("/claim")
def claim(body: dict, st=Depends(station_token)):
    return run(svc.claim, st["id"], body)


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
