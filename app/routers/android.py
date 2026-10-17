"""Private Android API: existing cookie/role middleware remains authoritative."""
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.database import db
from app.routers.auth import usuario_actual
from app.routers.esp32 import DeviceInfo
from app.routers.inventario import _conteos, _notificar_tarjeta
from app.routers.ws import manager
from app.services import android_ota as svc, android_offline as offline, esp32_firmware as fw

router = APIRouter(prefix='/api/android', tags=['TQT Android'])


class Prepare(BaseModel):
    model_config = ConfigDict(extra='forbid')
    client_operation_id: UUID
    pcb_id: int = Field(gt=0, le=9_223_372_036_854_775_807)
    firmware_id: str = Field(min_length=1, max_length=32)
    device: DeviceInfo


class Result(BaseModel):
    model_config = ConfigDict(extra='forbid')
    outcome: Literal['verified', 'failed', 'cancelled', 'unknown']
    device: DeviceInfo | None = None
    error: str = Field(default='', max_length=1000)

    @model_validator(mode='after')
    def require_evidence(self):
        if self.outcome == 'verified' and self.device is None:
            raise ValueError('Se requiere INFO autenticado después del reinicio.')
        return self


class OfflineInfo(DeviceInfo):
    model_config = ConfigDict(extra='forbid')
    offline_protocol: int = Field(ge=1, le=1, strict=True)
    offline_public_key: str = Field(pattern=r'^04[a-f0-9]{128}$')
    offline_counter: int = Field(ge=0, le=4_294_967_295, strict=True)
    offline_anchor_id: str = Field(pattern=r'^[a-f0-9]{16}$')
    offline_identity_proof: str = Field(pattern=r'^[a-f0-9]{64}$')
    offline_signature: str = Field(pattern=r'^[a-f0-9]{128}$')
    offline_last_grant: str = Field(pattern=r'^[a-f0-9]{32}$')


class OfflineBind(BaseModel):
    model_config = ConfigDict(extra='forbid')
    device: OfflineInfo


class OfflinePackage(BaseModel):
    model_config = ConfigDict(extra='forbid')
    client_operation_id: UUID
    pcb_id: int = Field(gt=0, le=9_223_372_036_854_775_807)
    firmware_id: str = Field(min_length=1, max_length=32)
    phone_public_key: str = Field(pattern=r'^04[a-f0-9]{128}$')


class OfflineResult(BaseModel):
    model_config = ConfigDict(extra='forbid')
    outcome: Literal['verified', 'failed', 'cancelled', 'unknown'] = 'verified'
    before: OfflineInfo | None = None
    after: OfflineInfo | None = None
    phone_signature: str | None = Field(default=None, pattern=r'^[a-f0-9]{128}$')
    error: str = Field(default='', max_length=1000)

    @model_validator(mode='after')
    def require_evidence(self):
        if self.outcome == 'verified' and (self.before is None or self.after is None):
            raise ValueError('Se requiere INFO4.3 auténtico antes y después del arranque.')
        return self


def run(fn, *args):
    try:
        return fn(*args)
    except svc.AndroidError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


def operator(request, write=False):
    user = usuario_actual(request)
    if write and user.get('rol') not in ('administrador', 'general'):
        raise HTTPException(403, 'Tu cuenta solo permite consultar.')
    return user['email']


@router.get('/devices')
def devices(q: str = Query(default='', max_length=120), limit: int = Query(default=50, ge=1, le=200),
            offset: int = Query(default=0, ge=0, le=9_223_372_036_854_775_807)):
    return run(svc.devices, q, limit, offset)


@router.get('/devices/{pcb_id}')
def device(pcb_id: int):
    return run(svc.device, pcb_id)


@router.get('/devices/{pcb_id}/capability')
def capability(pcb_id: int):
    return run(svc.device, pcb_id)['capability']


@router.get('/firmwares')
def firmwares(hw: str = Query(default='', max_length=7)):
    return run(fw.catalogue, hw, 'R2')


@router.post('/operations/prepare')
def prepare(body: Prepare, request: Request):
    return run(svc.prepare, str(body.client_operation_id), body.pcb_id, body.firmware_id,
               body.device.model_dump(), operator(request, True))


@router.get('/operations')
def history(request: Request, limit: int = Query(default=50, ge=1, le=200),
            offset: int = Query(default=0, ge=0, le=9_223_372_036_854_775_807)):
    return run(svc.history, operator(request), limit, offset)


@router.get('/operations/{identifier}')
def operation(identifier: UUID, request: Request):
    return run(svc.operation, str(identifier), operator(request))


@router.post('/operations/{identifier}/result')
async def result(identifier: UUID, body: Result, request: Request):
    value = await run_in_threadpool(run, svc.report, str(identifier), body.model_dump(), operator(request, True))
    pcb = (value.get('result') or {}).get('pcb')
    if value['state'] == 'verified' and pcb:
        await manager.broadcast('PCB_ACTUALIZADA', {'pcb': pcb, 'conteos': await run_in_threadpool(_conteos)})
        if pcb.get('tarjeta_id'):
            await _notificar_tarjeta(await run_in_threadpool(db.get_tarjeta_by_id, pcb['tarjeta_id']))
    return value


@router.get('/apk/manifest')
def apk_manifest():
    return run(svc.apk_package)[0]


@router.get('/apk/download')
def apk_download():
    meta, raw = run(svc.apk_package)
    return Response(raw, media_type='application/vnd.android.package-archive', headers={
        'Content-Disposition': f'attachment; filename="{meta["filename"]}"',
        'X-TQT-Sha256': meta['sha256'], 'X-TQT-Certificate-Sha256': meta['certificate_sha256']})


@router.post('/offline/bind/{pcb_id}')
def offline_bind(pcb_id: int, body: OfflineBind, request: Request):
    return run(offline.bind, pcb_id, body.device.model_dump(), operator(request, True))


@router.post('/offline/packages')
def offline_create(body: OfflinePackage, request: Request):
    return run(offline.create, str(body.client_operation_id), body.pcb_id, body.firmware_id,
               body.phone_public_key, operator(request, True))


@router.get('/offline/packages')
def offline_history(request: Request, limit: int = Query(default=50, ge=1, le=200),
                    offset: int = Query(default=0, ge=0, le=9_223_372_036_854_775_807)):
    return run(offline.history, operator(request), limit, offset)


@router.get('/offline/packages/{identifier}')
def offline_package(identifier: UUID, request: Request):
    return run(offline.get, str(identifier), operator(request))


@router.post('/offline/operations/{identifier}/result')
async def offline_result(identifier: UUID, body: OfflineResult, request: Request):
    value = await run_in_threadpool(run, offline.report, str(identifier), body.model_dump(), operator(request, True))
    pcb = (value.get('result') or {}).get('pcb')
    if value['state'] == 'verified' and pcb:
        await manager.broadcast('PCB_ACTUALIZADA', {'pcb': pcb, 'conteos': await run_in_threadpool(_conteos)})
        if pcb.get('tarjeta_id'):
            await _notificar_tarjeta(await run_in_threadpool(db.get_tarjeta_by_id, pcb['tarjeta_id']))
    return value
