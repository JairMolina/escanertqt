"""One-time generic R2 assignment: server-signed P256 ECDH/AES-GCM envelope.

The signing private key is persistent server data, never a firmware/repository asset.
No shared enrollment password or plaintext unit key is sent to the browser.
"""
import base64
import hashlib
import json
import os
import secrets
import time
from pathlib import Path
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, utils
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from app.config import settings
from app.database import db,inventario as inv
from app.services import esp32_firmware as fw,esp32_ota as ota

LABEL=b'TQT-ENROLL-v1'
TTL=600

def signing_key():
    path=Path(os.environ.get('TQT_R2_ENROLL_SIGNING_KEY',str(Path(settings.DB_PATH).parent/'r2_enrollment_signing.pem')))
    if not path.exists():
        path.parent.mkdir(parents=True,exist_ok=True)
        key=ec.generate_private_key(ec.SECP256R1())
        raw=key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption())
        try:
            fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        except FileExistsError: pass
        else:
            with os.fdopen(fd,'wb') as out:out.write(raw)
    key=serialization.load_pem_private_key(path.read_bytes(),password=None)
    if not isinstance(key,ec.EllipticCurvePrivateKey) or not isinstance(key.curve,ec.SECP256R1):
        raise ValueError('Clave de alta R2 incompatible.')
    return key

def public_key():
    return signing_key().public_key().public_bytes(serialization.Encoding.X962,serialization.PublicFormat.UncompressedPoint)

def key_id():return hashlib.sha256(public_key()).hexdigest()[:16]

def ensure(c):
    fw.ensure(c)
    c.execute('''CREATE TABLE IF NOT EXISTS r2_enrollments (
        id TEXT PRIMARY KEY, pcb INTEGER NOT NULL, operator TEXT NOT NULL,
        created REAL NOT NULL, state TEXT NOT NULL, payload TEXT NOT NULL)''')

def prepare(pcb_id,firmware_id,info,operator):
    if info.get('enrollment')!=1 or info.get('nombre')!='TQT_R2_V'+str(info.get('hw','')).replace('.','')+'_XXXX':
        raise ValueError('La tarjeta no está en modo de alta genérica.')
    if info.get('fw')!='4.0' or info.get('boot_valid') is not True or info.get('enroll_key_id')!=key_id():
        raise ValueError('Base genérica incompatible, sin arranque confirmado o de otro servidor.')
    nonce=ota.hex_bytes(info.get('nonce'),16);mac=ota.mac(info.get('mac'))
    peer=bytes.fromhex(info.get('device_pub',''))
    if len(peer)!=65:raise ValueError('Clave pública del dispositivo inválida.')
    try:peer_key=ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(),peer)
    except ValueError as exc:raise ValueError('Clave pública del dispositivo inválida.') from exc
    with db.transaction() as c:
        ensure(c)
        pcb=inv.get_pcb(pcb_id,conn=c)
        if not pcb or pcb['tipo']!='R2' or pcb['version']!=info['hw'].replace('.',''):
            raise ValueError('HW de la base genérica distinto del inventario.')
        for table,condition,lifetime in [('r2_programming_attempts',"state IN ('flashing','queued','running')",600),('esp32_ota_jobs',"state='prepared'",3600)]:
            if c.execute("SELECT 1 FROM sqlite_master WHERE name=?",(table,)).fetchone():
                if c.execute('SELECT 1 FROM '+table+' WHERE pcb=? AND '+condition+' AND created>?',(pcb_id,time.time()-lifetime)).fetchone():
                    raise ValueError('La R2 tiene una programación o verificación en curso.')
        if pcb.get('mac') and ota.mac(pcb['mac'])!=mac:raise ValueError('La MAC no coincide con la R2 elegida.')
        if c.execute('SELECT 1 FROM pcb_inventario WHERE UPPER(mac)=? AND id!=?',(info['mac'].upper(),pcb_id)).fetchone():
            raise ValueError('La MAC ya corresponde a otra PCB.')
        target=next((r for r in fw.rows(c,pcb['version']) if r['id']==firmware_id),None)
        if not target or ota.version(target['fw'])<(4,2):raise ValueError('El alta genérica requiere FW4.2 o superior.')
        base=next((r for r in fw.rows(c,pcb['version']) if json.loads(r['metadata']).get('bootstrap')),None)
        if not base:raise ValueError('No está registrada la base genérica.')
        base_image=bytes(base['image']);_,_,layout=fw.inspect(base_image)
        if info.get('app_sha256')!=base_image[layout['end']-32:layout['end']].hex():
            raise ValueError('La base instalada no coincide con el firmware genérico registrado.')
        for active in c.execute("SELECT id,payload FROM r2_enrollments WHERE pcb=? AND state='prepared' AND created>?",(pcb_id,time.time()-TTL)):
            previous=json.loads(active['payload'])
            if previous['mac']!=info['mac'].upper() or previous['nonce']==info['nonce']:
                raise ValueError('Hay un alta pendiente para esa unidad; vuelve a conectar la misma tarjeta.')
            c.execute("UPDATE r2_enrollments SET state='interrupted' WHERE id=?",(active['id'],))
        for r in c.execute('SELECT payload FROM r2_enrollments WHERE created>?',(time.time()-3600,)):
            previous=json.loads(r['payload'])
            if previous['nonce']==info['nonce'] and previous['mac']==info['mac'].upper():
                raise ValueError('La sesión de alta ya fue usada; vuelve a conectar la tarjeta.')
        existing=c.execute('SELECT secret FROM esp32_unit_keys WHERE pcb=?',(pcb_id,)).fetchone()
        secret=bytes(existing['secret']) if existing else secrets.token_bytes(32)
        if not existing:c.execute('INSERT INTO esp32_unit_keys VALUES(?,?,?)',(pcb_id,secret,time.time()))
        # Assigned runtime base profile. The eventual4.2 image embeds the same name/key.
        profile=fw.PROFILE_V2.pack(fw.MAGIC,2,ota.fixed(info['hw'],8),ota.fixed('4.0',16),
                                  ota.fixed(pcb['nombre'],24),ota.fixed('ESP32-WROOM-32E-N4',24),1,secret)
        ephemeral=ec.generate_private_key(ec.SECP256R1())
        pub=ephemeral.public_key().public_bytes(serialization.Encoding.X962,serialization.PublicFormat.UncompressedPoint)
        shared=ephemeral.exchange(ec.ECDH(),peer_key)
        cipher_key=hashlib.sha256(LABEL+shared+nonce+mac).digest()
        iv=secrets.token_bytes(12); encrypted=AESGCM(cipher_key).encrypt(iv,profile,LABEL+nonce+mac)
        body=b'\x01'+pub+iv+encrypted
        signature=signing_key().sign(LABEL+peer+nonce+mac+body,ec.ECDSA(hashes.SHA256()))
        r,s=utils.decode_dss_signature(signature)
        ticket=body+r.to_bytes(32,'big')+s.to_bytes(32,'big')
        assert len(ticket)==286
        identifier=secrets.token_hex(12)
        payload=dict(mac=info['mac'].upper(),nonce=info['nonce'],nombre=pcb['nombre'],hw=info['hw'],
                     app_sha256=info['app_sha256'],firmware_id=firmware_id,key_id=hashlib.sha256(secret).hexdigest()[:16])
        c.execute('INSERT INTO r2_enrollments VALUES(?,?,?,?,?,?)',(identifier,pcb_id,operator,time.time(),'prepared',json.dumps(payload)))
        return dict(id=identifier,ticket=base64.b64encode(ticket).decode(),nombre=payload['nombre'],mac=payload['mac'])

def finish(identifier,info,operator):
    with db.transaction() as c:
        ensure(c)
        row=c.execute('SELECT * FROM r2_enrollments WHERE id=? AND operator=?',(identifier,operator)).fetchone()
        if not row or time.time()-row['created']>TTL:raise ValueError('Alta no encontrada o vencida.')
        payload=json.loads(row['payload']);pcb=inv.get_pcb(row['pcb'],conn=c)
        secret=bytes(c.execute('SELECT secret FROM esp32_unit_keys WHERE pcb=?',(row['pcb'],)).fetchone()['secret'])
        ota.verify_info(info,secret,dict(pcb,mac=payload['mac']))
        if info['fw']!='4.0' or info['app_sha256']!=payload['app_sha256'] or info['nonce']==payload['nonce']:
            raise ValueError('La base no confirmó la identidad nueva y la sesión de alta.')
        c.execute("UPDATE r2_enrollments SET state='assigned' WHERE id=?",(identifier,))
        # Still no MAC/FW/programmed flag in inventory: only the confirmed4.2 boot will write them.
        return dict(assigned=True,nombre=payload['nombre'],mac=payload['mac'])
