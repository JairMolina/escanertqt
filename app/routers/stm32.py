"""Session endpoints for operators; separate bearer authentication for Windows stations."""
import io
import base64
import json
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import Response
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from app.services import stm32_programming as svc, usuarios
from app.routers.ws import manager
from app.database import inventario as inv

router = APIRouter(prefix='/api/stm32', tags=['Programación R1 STM32'])


def run(fn, *args):
    try:
        return fn(*args)
    except ValueError as e:
        raise HTTPException(400, str(e))


def operator(req):
    return usuarios.validar_sesion(req.cookies.get(usuarios.COOKIE))['email']


class Station(BaseModel):
    name: str = Field(min_length=1, max_length=60)


class Job(BaseModel):
    pcb_id: int = Field(gt=0)
    station_id: str = Field(min_length=24, max_length=24)
    hex_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    physical_confirmed: bool = False


class Result(BaseModel):
    verified: bool = False
    hex_sha256: str = Field(default='', max_length=64)
    identity_sha256: str = Field(default='', max_length=64)
    uid: str = Field(default='', max_length=24)
    trace: str = Field(default='', max_length=16000)
    error: str = Field(default='', max_length=1000)


class HexSubido(BaseModel):
    contenido: str = Field(min_length=20, max_length=4_000_000)
    tipo: str = Field(default='R1', pattern='^R[13]$')


class Progress(BaseModel):
    stage: str = Field(pattern='^(preparing|writing|reading|restarting|reporting)$')


@router.post('/hex/analizar')
def analizar_hex(body: HexSubido):
    try:
        return run(svc.analizar_hex, body.contenido, body.tipo)
    except UnicodeError:
        raise HTTPException(400, 'El archivo no es un Intel HEX de texto.')


@router.get('/preview/{pcb_id}')
def preview(pcb_id: int):
    return run(svc.preview, pcb_id)[0]


@router.get('/hex/{pcb_id}')
def image(pcb_id: int):
    d, image = run(svc.preview, pcb_id)
    return Response(image, media_type='application/octet-stream', headers={
        'Content-Disposition': f'attachment; filename="{d["identity"]["nombre"]}_FW{d["identity"]["fw"]}.hex"',
        'Cache-Control': 'no-store'})


@router.get('/stations')
def stations():
    return svc.stations()


def station_archive(st, server):
    config = dict(server=server, station_id=st['id'], token=st['token'])
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('config.json', json.dumps(config, indent=2))
        for name in ('agent.py', 'iniciar.ps1', 'iniciar.cmd', 'LEEME.txt', 'instalar.ps1'):
            z.write(svc.ROOT/'station'/name, name)
        z.write(Path(svc.hx.__file__), 'tqt_hex.py')
        from app.ssl_cert import ca_paths
        ca = ca_paths()[0]
        if ca.is_file():
            z.write(ca, 'ca.crt')
    return stream.getvalue()


def station_installer(st, server):
    command = (svc.ROOT/'station/bootstrap_installer.ps1').read_text(encoding='utf-8')
    encoded = base64.b64encode(command.encode('utf-16le')).decode('ascii')
    payload = base64.b64encode(station_archive(st, server)).decode('ascii')
    return ('@echo off\r\nset "TQT_INSTALLER=%~f0"\r\n'
            f'powershell.exe -NoProfile -ExecutionPolicy Bypass -EncodedCommand {encoded}\r\n'
            'set "TQT_EXIT=%errorlevel%"\r\npause\r\nexit /b %TQT_EXIT%\r\n'
            '::TQT_PAYLOAD::\r\n'+payload+'\r\n').encode('ascii')


@router.post('/stations/bundle')
def bundle(body: Station, req: Request):
    st = svc.station_create(body.name.strip(), operator(req))
    return Response(station_archive(st, str(req.base_url).rstrip('/')), media_type='application/zip', headers={
        'Content-Disposition': f'attachment; filename="Agente_TQT_{st["id"]}.zip"',
        'Cache-Control': 'no-store'})


@router.post('/stations/installer')
def installer(body: Station, req: Request):
    st = svc.station_create(body.name.strip(), operator(req))
    return Response(station_installer(st, str(req.base_url).rstrip('/')), media_type='application/octet-stream', headers={
        'Content-Disposition': f'attachment; filename="Instalar_TQT_{st["id"]}.cmd"',
        'Cache-Control': 'no-store'})


@router.post('/jobs')
def create(body: Job, req: Request):
    return run(svc.create_job, body.pcb_id, body.station_id, body.hex_sha256, operator(req), body.physical_confirmed)


@router.get('/jobs/{jid}')
def status(jid: str):
    return run(svc.job, jid)


def station_token(authorization: str = Header(default='')):
    if not authorization.startswith('Bearer '):
        raise HTTPException(401, 'Falta credencial de estación.')
    try:
        return svc.station_auth(authorization[7:])
    except ValueError:
        raise HTTPException(401, 'Credencial de estación inválida.')


@router.post('/agent/claim')
def claim(st=Depends(station_token)):
    return svc.claim(st['id'])


@router.post('/agent/jobs/{jid}/result')
async def finish(jid: str, body: Result, st=Depends(station_token)):
    result = await run_in_threadpool(run, svc.finish, st['id'], jid, body.model_dump())
    if result['state'] == 'verified':
        j = await run_in_threadpool(svc.job, jid)
        pcb = await run_in_threadpool(inv.get_pcb, j['pcb'])
        await manager.broadcast('PCB_ACTUALIZADA', {'pcb': pcb})
    return result


@router.post('/agent/jobs/{jid}/progress')
def progress(jid: str, body: Progress, st=Depends(station_token)):
    return run(svc.progress, st['id'], jid, body.stage)
