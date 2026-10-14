"""Persistent R2 firmware catalogue and images customized from inventory."""
import base64
import binascii
from fastapi import APIRouter, HTTPException, Request, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from app.services import esp32_firmware as svc, usuarios

router=APIRouter(prefix='/api/esp32',tags=['Programación R2 ESP32'])


class Upload(BaseModel):
    filename: str = Field(min_length=5,max_length=180)
    contenido: str = Field(min_length=20,max_length=16_777_216)


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
    meta,data=run(svc.prepare,pcb_id,firmware_id)
    return Response(data,media_type='application/octet-stream',headers={
        'Content-Disposition':f'attachment; filename="{meta["nombre"]}_FW{meta["fw"]}.bin"',
        'X-TQT-Nombre-Ble':meta['nombre'],'X-TQT-Firmware':meta['fw'],
        'X-TQT-Hardware':meta['hw'],'X-TQT-Sha256':meta['sha256'],
        'X-TQT-Firmware-Id':meta['firmware_id'],'Cache-Control':'no-store'})
