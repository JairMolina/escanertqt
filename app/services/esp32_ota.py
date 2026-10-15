"""Per-unit BLE OTA authorization, encrypted transport and verified results.

No unit key is returned by this API. It lives in the private production SQLite
and in the device's personalized serial installation image, never in Git/catalog.
"""
import base64
import hashlib
import hmac
import json
import re
import secrets
import struct
import time
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from app.database import db, inventario as inv
from app.services import esp32_firmware as fw

INFO_LABEL=b'TQT-OTA-INFO-v1'
DATA_LABEL=b'TQT-OTA-DATA-v1'
LIFETIME=3600


def ensure(c):
    fw.ensure(c)
    c.execute('''CREATE TABLE IF NOT EXISTS esp32_ota_jobs (
        id TEXT PRIMARY KEY, pcb INTEGER NOT NULL, firmware TEXT NOT NULL,
        state TEXT NOT NULL, created REAL NOT NULL, operator TEXT NOT NULL,
        payload TEXT NOT NULL, result TEXT)''')


def fixed(value,size):
    if not isinstance(value,str): raise ValueError('Campo OTA inválido.')
    try: raw=value.encode('ascii')
    except UnicodeError as e: raise ValueError('Campo OTA debe ser ASCII.') from e
    if not 0<len(raw)<size or b'\0' in raw: raise ValueError('Longitud de campo OTA inválida.')
    return raw.ljust(size,b'\0')


def hex_bytes(value,size):
    if not isinstance(value,str) or not re.fullmatch('[a-f0-9]{'+str(size*2)+'}',value):
        raise ValueError('Nonce, hash o prueba OTA inválida.')
    return bytes.fromhex(value)


def version(value):
    if not isinstance(value,str) or len(value)>15 or not re.fullmatch(r'\d+(?:\.\d+)+',value):
        raise ValueError('Versión OTA inválida.')
    return tuple(int(v) for v in value.split('.'))


def mac(value):
    if not isinstance(value,str) or not re.fullmatch(r'(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}',value):
        raise ValueError('MAC OTA inválida.')
    return bytes.fromhex(value.replace(':',''))


def verify_info(info,key,pcb):
    if info.get('ota_protocol')!=1 or info.get('boot_valid') is not True or version(info.get('fw'))<(4,0):
        raise ValueError('La R2 debe confirmar su arranque y capacidad OTA; instala una base OTA por serial primero.')
    if info.get('nombre')!=pcb['nombre'].replace('-','_') or not isinstance(info.get('hw'),str) or info['hw'].replace('.','')!=pcb['version']:
        raise ValueError('El nombre/HW de la R2 Bluetooth no coincide con el inventario.')
    if not pcb.get('mac') or mac(info.get('mac'))!=mac(pcb['mac']):
        raise ValueError('La MAC Bluetooth no coincide con la R2 elegida.')
    if info.get('key_id')!=hashlib.sha256(key).hexdigest()[:16]:
        raise ValueError('Credencial OTA distinta; reinstala esta R2 por serial desde la web.')
    partition=info.get('partition')
    if type(partition) is not int or partition not in (0x10000,0x150000):
        raise ValueError('Partición OTA de origen incompatible.')
    payload=(INFO_LABEL+hex_bytes(info.get('nonce'),16)+hex_bytes(info.get('app_sha256'),32)+
             fixed(info['nombre'],24)+fixed(info['hw'],8)+fixed(info['fw'],16)+mac(info['mac'])+
             b'\x01'+struct.pack('<I',partition))
    proof=hmac.new(key,payload,hashlib.sha256).digest()
    if not hmac.compare_digest(proof,hex_bytes(info.get('proof'),32)):
        raise ValueError('La placa no presentó una prueba OTA auténtica.')


def capability(pcb_id):
    with db.transaction() as c:
        ensure(c)
        pcb=inv.get_pcb(pcb_id,conn=c)
        if not pcb or pcb['tipo']!='R2': raise ValueError('Elige una R2.')
        key=c.execute('SELECT 1 FROM esp32_unit_keys WHERE pcb=?',(pcb_id,)).fetchone()
    current=pcb.get('firmware') or ''
    # 4.0 original has no OTA. A recorded authenticated installation distinguishes the new base.
    from app.services import r2_programming as r2
    with db.transaction() as c:
        r2.ensure(c)
        proof=c.execute('SELECT firmware FROM r2_programming_state WHERE pcb=?',(pcb_id,)).fetchone()
    eligible=bool(key and pcb.get('mac') and re.fullmatch(r'\d+(?:\.\d+)+',current) and
                  (version(current)>=(4,1) or (current=='4.0' and proof and proof['firmware']=='4.0')))
    return dict(eligible=eligible,current_fw=current,requires_serial=not eligible)


def prepare(pcb_id,firmware_id,info,operator):
    with db.transaction() as c:
        ensure(c)
        pcb=inv.get_pcb(pcb_id,conn=c)
        keyrow=c.execute('SELECT secret FROM esp32_unit_keys WHERE pcb=?',(pcb_id,)).fetchone()
        if c.execute("SELECT 1 FROM sqlite_master WHERE name='r2_programming_attempts'").fetchone():
            if c.execute("SELECT 1 FROM r2_programming_attempts WHERE pcb=? AND state IN ('flashing','queued','running') AND created>?",(pcb_id,time.time()-600)).fetchone():
                raise ValueError('La R2 está programándose o verificándose en la estación.')
        if not pcb or pcb['tipo']!='R2' or not keyrow:
            raise ValueError('Primero instala R2 V4.1 por serial desde esta web.')
        key=bytes(keyrow['secret']);verify_info(info,key,pcb)
        row=next((r for r in fw.rows(c,pcb['version']) if r['id']==firmware_id),None)
        if not row: raise ValueError('Firmware elegido incompatible o inexistente.')
        raw=bytes(row['image'])
        if hashlib.sha256(raw).hexdigest()!=row['sha256']: raise ValueError('El firmware guardado no coincide con su hash.')
        meta,_,layout=fw.inspect(raw)
        if meta['ota_protocol']!=1: raise ValueError('Ese firmware no admite OTA; usa serial para instalarlo.')
        image,meta=fw.personalize(raw,pcb['nombre'].replace('-','_'),key)
        application=image[layout['start']:layout['end']]
        nonce=hex_bytes(info['nonce'],16)
        manifest=(nonce+hashlib.sha256(application).digest()+struct.pack('<I',len(application))+
                  fixed(meta['nombre'],24)+fixed(meta['hw'],8)+fixed(meta['fw'],16)+mac(pcb['mac']))
        assert len(manifest)==106
        manifest+=hmac.new(key,manifest,hashlib.sha256).digest()
        session_key=hmac.new(key,DATA_LABEL+nonce,hashlib.sha256).digest()
        cipher=Cipher(algorithms.AES(session_key),modes.CTR(nonce)).encryptor()
        encrypted=cipher.update(application)+cipher.finalize()
        now=time.time()
        # A nonce is used once. Cancellation causes the device to generate a new one.
        previous=c.execute('SELECT payload FROM esp32_ota_jobs WHERE pcb=? AND created>?',(pcb_id,now-LIFETIME)).fetchall()
        if any(json.loads(r['payload'])['nonce']==info['nonce'] for r in previous):
            raise ValueError('Esta sesión OTA ya fue usada; desconecta y vuelve a conectar Bluetooth.')
        identifier=secrets.token_hex(12)
        payload=dict(pcb_id=pcb_id,firmware_id=firmware_id,nombre=meta['nombre'],hw=meta['hw'],fw=meta['fw'],
                     mac=pcb['mac'],nonce=info['nonce'],source_partition=info['partition'],
                     chunk_bytes=info.get('chunk',16),
                     app_sha256=application[-32:].hex(),transfer_sha256=hashlib.sha256(application).hexdigest(),bytes=len(application))
        c.execute('INSERT INTO esp32_ota_jobs VALUES(?,?,?,?,?,?,?,NULL)',
                  (identifier,pcb_id,firmware_id,'prepared',now,operator,json.dumps(payload)))
        db.log_evento('ESP32_OTA_PREPARADA',None,None,f'{meta["nombre"]}; FW {meta["fw"]}; job={identifier}',operator,conn=c)
        return dict(payload,job_id=identifier,manifest=base64.b64encode(manifest).decode('ascii'),
                    encrypted_image=base64.b64encode(encrypted).decode('ascii'))


def finish(identifier,info,operator):
    with db.transaction() as c:
        ensure(c)
        row=c.execute('SELECT * FROM esp32_ota_jobs WHERE id=?',(identifier,)).fetchone()
        if not row or row['operator']!=operator: raise ValueError('Trabajo OTA no encontrado para este operador.')
        if row['state']=='verified': return json.loads(row['result'])
        if row['state']!='prepared' or time.time()-row['created']>LIFETIME: raise ValueError('Trabajo OTA cancelado o vencido.')
        payload=json.loads(row['payload'])
        pcb=inv.get_pcb(row['pcb'],conn=c)
        key=c.execute('SELECT secret FROM esp32_unit_keys WHERE pcb=?',(row['pcb'],)).fetchone()
        if not pcb or not key: raise ValueError('Identidad OTA ya no disponible.')
        verify_info(info,bytes(key['secret']),pcb)
        if (info['nombre'],info['hw'],info['fw'],info['app_sha256'])!=(payload['nombre'],payload['hw'],payload['fw'],payload['app_sha256']):
            raise ValueError('La placa no arrancó con la imagen y versión elegidas; no se guarda el resultado.')
        if info['partition']==payload['source_partition'] or info['nonce']==payload['nonce']:
            raise ValueError('La R2 no confirmó el arranque en la partición nueva.')
        updated=inv.guardar_programacion(pcb['id'],pcb['mac'],payload['fw'],operator,conn=c)
        from app.services import r2_programming as r2
        r2.record(c,updated,'ble_ota',info)
        result=dict(verified=True,pcb=updated,fw=payload['fw'],app_sha256=payload['app_sha256'])
        c.execute("UPDATE esp32_ota_jobs SET state='verified',result=? WHERE id=?",(json.dumps(result),identifier))
        db.log_evento('ESP32_OTA_VERIFICADA',None,None,f'{payload["nombre"]}; FW {payload["fw"]}; job={identifier}; sha={payload["app_sha256"]}',operator,conn=c)
        return result


def cancel(identifier,operator,error=''):
    with db.transaction() as c:
        ensure(c)
        row=c.execute('SELECT * FROM esp32_ota_jobs WHERE id=? AND operator=?',(identifier,operator)).fetchone()
        if not row: raise ValueError('Trabajo OTA no encontrado.')
        if row['state']=='prepared':
            c.execute("UPDATE esp32_ota_jobs SET state='cancelled',result=? WHERE id=?",(json.dumps(dict(verified=False,error=error[:1000])),identifier))
            if error:
                from app.services import r2_programming as r2
                r2.ensure(c)
                now=time.time()
                c.execute('INSERT INTO r2_programming_attempts VALUES(?,?,?,?,?,?,?,?,?,?,NULL,?)',
                          ('ota-'+identifier,row['pcb'],row['firmware'],'',operator,'ble_ota','error',now,now,row['payload'],error[:1000]))
    return dict(cancelled=row['state']!='verified')
