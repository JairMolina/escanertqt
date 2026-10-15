"""Persistent R2 firmware catalogue and images customized from inventory."""
import base64
import binascii
from fastapi import APIRouter, HTTPException, Request, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from fastapi.concurrency import run_in_threadpool
from app.database import db
from app.routers.inventario import _conteos, _notificar_tarjeta
from app.routers.ws import manager
from fastapi import Depends
from app.routers.stm32 import station_token
from app.services import r2_programming as r2
from app.services import r2_enrollment as enrollment
from app.services import esp32_firmware as svc, esp32_ota as ota, usuarios

router=APIRouter(prefix='/api/esp32',tags=['Programación R2 ESP32'])
agent_router=APIRouter(prefix='/api/stm32/agent/r2',tags=['Verificación automática R2'])

class R2Attempt(BaseModel):
    firmware_id: str = Field(min_length=1,max_length=32)
    station_id: str = Field(min_length=24,max_length=24)
    method: str = Field(default='serial',pattern='^(serial|verify)$')

class R2Ready(BaseModel):
    mac: str = Field(pattern=r'^(?:[a-fA-F0-9]{2}:){5}[a-fA-F0-9]{2}$')

class R2Failure(BaseModel):
    error: str = Field(min_length=1,max_length=1000)

class OtaStop(BaseModel):
    error: str = Field(default='',max_length=1000)

class R2Claim(BaseModel):
    available: bool = False

@router.get('/r2/status')
def r2_status():
    return run(r2.statuses)

@router.post('/r2/{pcb_id}/attempts')
def r2_start(pcb_id: int,body: R2Attempt,req: Request):
    return run(r2.start,pcb_id,body.firmware_id,body.station_id,operator(req),body.method)

@router.get('/r2/attempts/{identifier}')
def r2_job(identifier: str,req: Request):
    return run(r2.get,identifier,operator(req))

@router.post('/r2/attempts/{identifier}/ready')
def r2_ready(identifier: str,body: R2Ready,req: Request):
    return run(r2.ready,identifier,operator(req),body.mac)

@router.post('/r2/attempts/{identifier}/failure')
def r2_failure(identifier: str,body: R2Failure,req: Request):
    return run(r2.fail,identifier,operator(req),body.error)

@agent_router.post('/claim')
def r2_claim(body: R2Claim,st=Depends(station_token)):
    return run(r2.claim,st['id'],body.available)

@agent_router.post('/{identifier}/result')
async def r2_result(identifier: str,body: dict,st=Depends(station_token)):
    res=await run_in_threadpool(run,r2.finish,st['id'],identifier,body)
    if res.get('verified'):
        await manager.broadcast('PCB_ACTUALIZADA',{'pcb':res['pcb'],'conteos':await run_in_threadpool(_conteos)})
        if res['pcb'].get('tarjeta_id'):
            await _notificar_tarjeta(await run_in_threadpool(db.get_tarjeta_by_id,res['pcb']['tarjeta_id']))
    return res


class Upload(BaseModel):
    filename: str = Field(min_length=5,max_length=180)
    contenido: str = Field(min_length=20,max_length=16_777_216)
    tipo: str = Field(default='R2',pattern=r'^R2$')   # la R1 usa firmware fijo del repo: no se suben archivos
    version: str | None = Field(default=None,max_length=15)


class DeviceInfo(BaseModel):
    nombre: str = Field(min_length=1,max_length=23)
    hw: str = Field(pattern=r'^\d+(?:\.\d+)+$',max_length=7)
    fw: str = Field(pattern=r'^\d+(?:\.\d+)+$',max_length=15)
    mac: str = Field(pattern=r'^(?:[a-fA-F0-9]{2}:){5}[a-fA-F0-9]{2}$')
    ota_protocol: int = Field(ge=1,le=1,strict=True)
    key_id: str = Field(pattern=r'^[a-f0-9]{16}$')
    nonce: str = Field(pattern=r'^[a-f0-9]{32}$')
    app_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    proof: str = Field(pattern=r'^[a-f0-9]{64}$')
    boot_valid: bool = Field(strict=True)
    partition: int = Field(ge=0,le=4_194_304,strict=True)
    chunk: int = Field(default=16,ge=1,le=500)
    name_format: int = Field(default=1,ge=1,le=2,strict=True)


class OtaPrepare(BaseModel):
    firmware_id: str = Field(min_length=1,max_length=32)
    device: DeviceInfo

class EnrollmentDevice(BaseModel):
    nombre: str = Field(min_length=1,max_length=23)
    hw: str = Field(pattern=r'^\d+(?:\.\d+)+$',max_length=7)
    fw: str = Field(pattern=r'^4\.0$')
    mac: str = Field(pattern=r'^(?:[a-fA-F0-9]{2}:){5}[a-fA-F0-9]{2}$')
    nonce: str = Field(pattern=r'^[a-f0-9]{32}$')
    app_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    boot_valid: bool = Field(strict=True)
    enrollment: int = Field(ge=1,le=1,strict=True)
    enroll_key_id: str = Field(pattern=r'^[a-f0-9]{16}$')
    device_pub: str = Field(pattern=r'^04[a-f0-9]{128}$')

class EnrollmentPrepare(BaseModel):
    firmware_id: str = Field(min_length=1,max_length=32)
    device: EnrollmentDevice

@router.post('/enroll/prepare/{pcb_id}')
def enrollment_prepare(pcb_id: int,body: EnrollmentPrepare,req: Request):
    return run(enrollment.prepare,pcb_id,body.firmware_id,body.device.model_dump(),operator(req))

@router.post('/enroll/result/{identifier}')
def enrollment_result(identifier: str,body: DeviceInfo,req: Request):
    return run(enrollment.finish,identifier,body.model_dump(),operator(req))


def operator(req):
    return usuarios.validar_sesion(req.cookies.get(usuarios.COOKIE))['email']


@router.get('/ota/capability/{pcb_id}')
def ota_capability(pcb_id: int):
    return run(ota.capability,pcb_id)


@router.post('/ota/prepare/{pcb_id}')
def ota_prepare(pcb_id: int,body: OtaPrepare,req: Request):
    return run(ota.prepare,pcb_id,body.firmware_id,body.device.model_dump(),operator(req))


@router.post('/ota/result/{identifier}')
async def ota_result(identifier: str,body: DeviceInfo,req: Request):
    try:
        res=await run_in_threadpool(ota.finish,identifier,body.model_dump(),operator(req))
    except ValueError as e:
        raise HTTPException(400,str(e)) from e
    pcb=res.get('pcb') if isinstance(res,dict) else None
    if pcb:   # igual que PUT /api/pcb/{id}/programacion: las vistas se refrescan con MAC y firmware nuevos
        await manager.broadcast('PCB_ACTUALIZADA',{'pcb':pcb,'conteos':await run_in_threadpool(_conteos)})
        if pcb.get('tarjeta_id'):
            await _notificar_tarjeta(await run_in_threadpool(db.get_tarjeta_by_id,pcb['tarjeta_id']))
    return res


@router.post('/ota/cancel/{identifier}')
def ota_cancel(identifier: str,req: Request,body: OtaStop | None = None):
    return run(ota.cancel,identifier,operator(req),body.error if body else '')


def run(fn,*args):
    try:
        return fn(*args)
    except ValueError as e:
        raise HTTPException(400,str(e)) from e


def decode(body):
    try:
        return base64.b64decode(body.contenido,validate=True)
    except (ValueError,binascii.Error) as e:
        raise HTTPException(400,'Contenido base64 inválido.') from e


@router.get('/firmwares')
def catalogue(hw: str = Query(default='',max_length=7),tipo: str = Query(default='R2',pattern=r'^R[12]$')):
    return run(svc.catalogue,hw,tipo)


@router.post('/firmwares/analizar')
def analyze(body: Upload):
    return run(svc.normalize,decode(body),body.filename,body.tipo,body.version)[0]


@router.post('/firmwares')
def upload(body: Upload,req: Request):
    operator=usuarios.validar_sesion(req.cookies.get(usuarios.COOKIE))['email']
    return run(svc.save,decode(body),body.filename,operator,body.tipo,body.version)


@router.get('/r1-gate/{pcb_id}')
def r1_gate(pcb_id: int):
    return run(svc.gate,pcb_id)


@router.get('/preview/{pcb_id}')
def preview(pcb_id: int,firmware_id: str | None = Query(default=None,max_length=32)):
    return run(svc.prepare,pcb_id,firmware_id)[0]


@router.post('/bin/{pcb_id}')
def image(pcb_id: int,firmware_id: str | None = Query(default=None,max_length=32)):
    meta,data=run(svc.prepare,pcb_id,firmware_id,True)
    return Response(data,media_type='application/octet-stream',headers={
        'Content-Disposition':f'attachment; filename="{meta["nombre"] or meta["kind"]}_FW{meta["fw"]}.bin"',
        'X-TQT-Nombre-Ble':meta['nombre'],'X-TQT-Firmware':meta['fw'],
        'X-TQT-Hardware':meta['hw'],'X-TQT-Sha256':meta['sha256'],
        'X-TQT-Firmware-Id':meta['firmware_id'],'X-TQT-OTA-Protocol':str(meta['ota_protocol']),
        'X-TQT-Bootstrap':'1' if meta.get('bootstrap') else '0',
        'X-TQT-Key-Id':meta['key_id'],'Cache-Control':'no-store'})
