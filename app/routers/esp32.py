"""Persistent R2 firmware catalogue and images customized from inventory."""
import base64
import binascii
from fastapi import APIRouter, HTTPException, Request, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from app.services import esp32_firmware as svc, esp32_ota as ota, usuarios

router=APIRouter(prefix='/api/esp32',tags=['Programación R2 ESP32'])


class Upload(BaseModel):
    filename: str = Field(min_length=5,max_length=180)
    contenido: str = Field(min_length=20,max_length=16_777_216)


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
    chunk: int = Field(default=16,ge=1,le=180)


class OtaPrepare(BaseModel):
    firmware_id: str = Field(min_length=1,max_length=32)
    device: DeviceInfo


def operator(req):
    return usuarios.validar_sesion(req.cookies.get(usuarios.COOKIE))['email']


@router.get('/ota/capability/{pcb_id}')
def ota_capability(pcb_id: int):
    return run(ota.capability,pcb_id)


@router.post('/ota/prepare/{pcb_id}')
def ota_prepare(pcb_id: int,body: OtaPrepare,req: Request):
    return run(ota.prepare,pcb_id,body.firmware_id,body.device.model_dump(),operator(req))


@router.post('/ota/result/{identifier}')
def ota_result(identifier: str,body: DeviceInfo,req: Request):
    return run(ota.finish,identifier,body.model_dump(),operator(req))


@router.post('/ota/cancel/{identifier}')
def ota_cancel(identifier: str,req: Request):
    return run(ota.cancel,identifier,operator(req))


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
def catalogue(hw: str = Query(default='',max_length=7)):
    return run(svc.catalogue,hw)


@router.post('/firmwares/analizar')
def analyze(body: Upload):
    return run(svc.normalize,decode(body),body.filename)[0]


@router.post('/firmwares')
def upload(body: Upload,req: Request):
    operator=usuarios.validar_sesion(req.cookies.get(usuarios.COOKIE))['email']
    return run(svc.save,decode(body),body.filename,operator)


@router.get('/preview/{pcb_id}')
def preview(pcb_id: int,firmware_id: str | None = Query(default=None,max_length=32)):
    return run(svc.prepare,pcb_id,firmware_id)[0]


@router.post('/bin/{pcb_id}')
def image(pcb_id: int,firmware_id: str | None = Query(default=None,max_length=32)):
    meta,data=run(svc.prepare,pcb_id,firmware_id,True)
    return Response(data,media_type='application/octet-stream',headers={
        'Content-Disposition':f'attachment; filename="{meta["nombre"]}_FW{meta["fw"]}.bin"',
        'X-TQT-Nombre-Ble':meta['nombre'],'X-TQT-Firmware':meta['fw'],
        'X-TQT-Hardware':meta['hw'],'X-TQT-Sha256':meta['sha256'],
        'X-TQT-Firmware-Id':meta['firmware_id'],'X-TQT-OTA-Protocol':str(meta['ota_protocol']),
        'X-TQT-Key-Id':meta['key_id'],'Cache-Control':'no-store'})
