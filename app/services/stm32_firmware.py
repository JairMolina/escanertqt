"""Immutable HEX catalogue in the same persistent SQLite database as inventory."""
import hashlib
import json
import re
import secrets
import struct
import tempfile
import time
from pathlib import Path
from app.database import db
from app.services import tqt_hex as hx

ROOT = Path(__file__).resolve().parents[2]


def parse(text):
    if not isinstance(text, str) or not 20 <= len(text) <= 4_000_000:
        raise ValueError('HEX vacío o mayor de 4 MB.')
    try:
        raw = text.encode('ascii')
    except UnicodeError:
        raise ValueError('El HEX debe contener únicamente texto ASCII.')
    with tempfile.TemporaryDirectory(prefix='tqt_catalog_') as tmp:
        p = Path(tmp) / 'firmware.hex'
        p.write_bytes(raw)
        mem, starts = hx.leer_hex(p)
    return mem, starts


def version(value):
    if not isinstance(value, str) or len(value) > 7 or not re.fullmatch(r'[0-9]+(?:\.[0-9]+)*', value):
        raise ValueError('Indica una versión numérica, por ejemplo 1.1 (máximo 7 caracteres).')
    return value


def inspect(text, kind, hw='', fw=''):
    if kind not in ('R1', 'R3'):
        raise ValueError('Tipo de firmware no soportado.')
    mem, starts = parse(text)
    identity = None
    if kind == 'R1':
        identity = hx.leer_identidad(mem)
        app = {a:b for a,b in mem.items() if a < hx.IDENTITY_BEGIN}
        profile = hx.leer_perfil(app)
        if identity:
            hx.comprobar_perfil(identity, profile)
        if (hw and hw != profile['hw']) or (fw and fw != profile['fw']):
            raise ValueError('La versión indicada contradice el perfil interno del HEX R1.')
        hw, fw = profile['hw'], profile['fw']
        stored = hx.emitir_hex(app, starts)
        mem = app
        origin = 'perfil interno'
    else:
        if any(not hx.FLASH_BEGIN <= a < hx.IDENTITY_BEGIN for a in mem):
            raise ValueError('R3 escribe fuera de la Flash de aplicación o contiene identidad de otra placa.')
        blob = bytes(mem[a] for a in sorted(mem))
        if hx.PROFILE_MAGIC in blob:
            raise ValueError('El archivo contiene un perfil R1; no se guarda como R3.')
        hw, fw = version(hw), version(fw)
        stored = text
        origin = 'confirmada por operador'
    try:
        stack, reset = struct.unpack('<II', bytes(mem[hx.FLASH_BEGIN+i] for i in range(8)))
    except KeyError:
        raise ValueError('El HEX no contiene los vectores de arranque del STM32.')
    if not 0x20000000 < stack <= 0x20010000 or stack % 8 or not reset & 1 or (reset & ~1) not in mem:
        raise ValueError('Vectores de arranque incompatibles con STM32F103RET6.')
    if not hx.FLASH_BEGIN <= (reset & ~1) < hx.IDENTITY_BEGIN:
        raise ValueError('Dirección de inicio fuera de la aplicación.')
    for typ, data in starts:
        if typ != 5 or int.from_bytes(data, 'big') not in (reset, reset & ~1):
            raise ValueError('El registro de inicio no coincide con el vector de reset.')
    meta = dict(kind=kind, hw=hw, fw=fw, mcu='STM32F103RET6', bytes=len(mem),
                sha256=hashlib.sha256(stored.encode('ascii')).hexdigest(),
                source_sha256=hashlib.sha256(text.encode('ascii')).hexdigest(),
                origin=origin, identity_removed=bool(identity))
    return meta, stored


def ensure(c):
    c.execute('''CREATE TABLE IF NOT EXISTS stm32_firmwares (
      id TEXT PRIMARY KEY, kind TEXT NOT NULL, hw TEXT NOT NULL, fw TEXT NOT NULL,
      filename TEXT NOT NULL, sha256 TEXT NOT NULL, source_sha256 TEXT NOT NULL,
      metadata TEXT NOT NULL, image TEXT NOT NULL, created REAL NOT NULL, operator TEXT NOT NULL,
      UNIQUE(kind,hw,sha256))''')
    for kind, rel in [('R1','firmware/stm32_r1/fw43_base.hex'),('R3','firmware/stm32_r3/r3_fw10.hex')]:
        if c.execute('SELECT 1 FROM stm32_firmwares WHERE kind=? LIMIT 1',(kind,)).fetchone():
            continue
        path=ROOT/rel
        text=path.read_bytes().decode('ascii')
        extra=json.loads(path.with_suffix('.hex.json').read_text(encoding='utf-8')) if kind=='R3' else {}
        meta, image=inspect(text,kind,extra.get('hw',''),extra.get('fw',''))
        c.execute('INSERT OR IGNORE INTO stm32_firmwares VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                  ('base-'+kind,kind,meta['hw'],meta['fw'],path.name,meta['sha256'],meta['source_sha256'],json.dumps(meta),image,0,'sistema'))


def public(r):
    d=json.loads(r['metadata'])
    return dict(d, release_status=d.get('release_status','aprobado'), id=r['id'],filename=r['filename'],created=r['created'],operator=r['operator'])


def order(r):
    parts=[int(x) for x in r['fw'].split('.')]
    while len(parts)>1 and parts[-1]==0:
        parts.pop()
    return tuple(parts),r['created'],r['id']


def rows(c,kind,hw=''):
    found=list(c.execute('SELECT * FROM stm32_firmwares WHERE kind=?',(kind,)))
    if hw:
        found=[r for r in found if r['hw'].replace('.','')==hw.replace('.','')]
    return sorted(found,key=order,reverse=True)


def catalogue(kind,hw=''):
    with db.get_db() as c:
        ensure(c)
        found=rows(c,kind,hw)
        approved=[r for r in found if public(r)['release_status']=='aprobado']
        found=approved+[r for r in found if public(r)['release_status']!='aprobado']
    return dict(items=[public(r) for r in found],default_id=approved[0]['id'] if approved else None)


def selected(c,kind,hw,identifier=None):
    ensure(c)
    found=rows(c,kind,hw)
    approved=[r for r in found if public(r)['release_status']=='aprobado']
    r=next((r for r in found if r['id']==identifier),None) if identifier else (approved[0] if approved else None)
    if r is None:
        raise ValueError('No hay firmware compatible con el tipo/HW de la placa seleccionada.')
    meta=public(r)
    if hashlib.sha256(r['image'].encode('ascii')).hexdigest()!=r['sha256']:
        raise ValueError('La copia guardada del firmware no coincide con su hash.')
    return meta,r['image']


def save(text,kind,filename,hw,fw,operator):
    meta,image=inspect(text,kind,hw,fw)
    meta['release_status']='beta'
    filename=filename.replace('\\','/').split('/')[-1].strip()
    if not filename.lower().endswith('.hex') or not 1<=len(filename)<=180 or any(ord(ch)<32 for ch in filename):
        raise ValueError('El nombre debe ser un archivo .hex válido (máximo 180 caracteres).')
    with db.transaction() as c:
        ensure(c)
        existing=c.execute('SELECT * FROM stm32_firmwares WHERE kind=? AND hw=? AND sha256=?',(kind,meta['hw'],meta['sha256'])).fetchone()
        if existing:
            if existing['fw']!=meta['fw']:
                raise ValueError('Ese HEX ya está registrado con otra versión; no se cambia su identidad.')
            return dict(public(existing),existing=True,identity_removed=meta['identity_removed'])
        identifier=secrets.token_hex(12)
        c.execute('INSERT INTO stm32_firmwares VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                  (identifier,kind,meta['hw'],meta['fw'],filename,meta['sha256'],meta['source_sha256'],json.dumps(meta),image,time.time(),operator))
        db.log_evento('STM32_FIRMWARE_GUARDADO',None,None,f'{kind} HW {meta["hw"]} FW {meta["fw"]}; sha256={meta["sha256"]}',operator,conn=c)
        return dict(meta,id=identifier,filename=filename,existing=False)


def approve(identifier,operator,evidence):
    evidence=str(evidence or '').strip()
    if not 10 <= len(evidence) <= 2000:
        raise ValueError('Describe las pruebas realizadas y su resultado (10 a 2000 caracteres).')
    with db.transaction() as c:
        ensure(c)
        r=c.execute('SELECT * FROM stm32_firmwares WHERE id=?',(identifier,)).fetchone()
        if not r: raise ValueError('Firmware no encontrado.')
        if hashlib.sha256(r['image'].encode('ascii')).hexdigest()!=r['sha256']:
            raise ValueError('La imagen guardada no coincide con su hash; no se aprueba.')
        meta=public(r)
        if meta['release_status']=='aprobado': return meta
        stored=json.loads(r['metadata'])
        stored.update(release_status='aprobado',approved_by=operator,approved_at=time.time(),approval_evidence=evidence)
        c.execute('UPDATE stm32_firmwares SET metadata=? WHERE id=?',(json.dumps(stored),identifier))
        from app.database import inventario
        inventario.agregar_firmware(r['kind'],r['fw'],conn=c)
        db.log_evento('STM32_FIRMWARE_APROBADO',None,None,
            f'{identifier}; {r["kind"]} FW {r["fw"]}; sha256={r["sha256"]}; pruebas: {evidence}',operator,conn=c)
        return dict(meta,**{k:stored[k] for k in ('approved_by','approved_at','approval_evidence')},release_status='aprobado')
