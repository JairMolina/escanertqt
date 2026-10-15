"""R2 (and R1, unmodified) images with a fixed profile; modify identity data and ESP image checksums only.

Format: Espressif ESP32 image v1 (24-byte header, segment XOR, appended SHA256).
Source: docs.espressif.com/projects/esptool/en/latest/esp32/advanced-topics/firmware-image-format.html
"""
import hashlib
import json
import re
import secrets
import struct
import time
import zlib
from pathlib import Path
from app.database import db, inventario as inv

ROOT = Path(__file__).resolve().parents[2]
FLASH_SIZE = 4 * 1024 * 1024
MAX_UPLOAD = 12 * 1024 * 1024
MAGIC = b'TQT_R2_CFG_V1' + bytes(3)
PROFILE = struct.Struct('<16sI8s16s24s24s')
PROFILE_V2 = struct.Struct('<16sI8s16s24s24sI32s')
NAME_OFFSET = 44
KEY_OFFSET = 96


def hex_image(raw):
    """Intel HEX with ESP flash offsets; bounded allocation, checksums and no overlaps."""
    try:
        lines = raw.decode('ascii').splitlines()
    except UnicodeError as e:
        raise ValueError('El HEX debe ser texto ASCII.') from e
    image = bytearray(b'\xff') * FLASH_SIZE
    seen = bytearray(FLASH_SIZE)
    base = end = 0
    eof = False
    for line in lines:
        if not line.strip():
            continue
        if eof or not re.fullmatch(r':[0-9a-fA-F]+', line.strip()):
            raise ValueError('Registro HEX inválido o posterior a EOF.')
        try:
            record = bytes.fromhex(line.strip()[1:])
        except ValueError as e:
            raise ValueError('Registro HEX inválido.') from e
        if len(record) < 5 or record[0] != len(record)-5 or sum(record) % 256:
            raise ValueError('Longitud o checksum HEX incorrecto.')
        size, offset, kind = record[0], int.from_bytes(record[1:3], 'big'), record[3]
        data = record[4:-1]
        if kind == 0:
            start = base + offset
            stop = start + size
            if offset+size > 65536 or stop > FLASH_SIZE or any(seen[start:stop]):
                raise ValueError('HEX fuera de Flash ESP32 o con direcciones superpuestas.')
            image[start:stop] = data
            seen[start:stop] = b'\x01' * size
            end = max(end, stop)
        elif kind in (2, 4) and size == 2 and offset == 0:
            base = int.from_bytes(data, 'big') << (4 if kind == 2 else 16)
        elif kind == 1 and size == offset == 0:
            eof = True
        else:
            raise ValueError('Tipo de registro HEX no soportado para ESP32.')
    if not eof or not end:
        raise ValueError('HEX vacío o sin EOF.')
    return bytes(image[:end])


def image_layout(raw, start, limit):
    if start+24 > limit or raw[start] != 0xE9:
        raise ValueError('Falta imagen de arranque ESP32; usa el archivo merged.bin completo.')
    count = raw[start+1]
    if not 1 <= count <= 16 or raw[start+12:start+14] != b'\0\0' or raw[start+23] != 1:
        raise ValueError('Imagen incompatible: se requiere ESP32 clásico con SHA256, sin firma Secure Boot.')
    if raw[start+2] not in (0,1,2,3) or raw[start+3]>>4 != 2 or raw[start+3]&15 not in (0,1,2,15):
        raise ValueError('Configuración Flash incompatible con ESP32-WROOM-32E-N4 de 4 MB.')
    pos = start+24
    segments = []
    loaded = []
    checksum = 0xEF
    for _ in range(count):
        if pos+8 > limit:
            raise ValueError('Segmento ESP32 incompleto.')
        address, length = struct.unpack_from('<II', raw, pos)
        pos += 8
        if length > FLASH_SIZE or pos+length > limit:
            raise ValueError('Longitud de segmento ESP32 inválida.')
        segments.append((pos, pos+length))
        loaded.append((address,address+length))
        for value in raw[pos:pos+length]:
            checksum ^= value
        pos += length
    entry = struct.unpack_from('<I',raw,start+4)[0]
    if not any(first<=entry<last for first,last in loaded):
        raise ValueError('Punto de entrada ESP32 fuera de los segmentos de aplicación.')
    checksum_pos = start + ((pos-start)//16)*16 + 15
    end = checksum_pos+33
    if end > limit or raw[checksum_pos] != checksum:
        raise ValueError('Checksum de imagen ESP32 incorrecto.')
    if hashlib.sha256(raw[start:checksum_pos+1]).digest() != raw[checksum_pos+1:end]:
        raise ValueError('SHA256 interno de imagen ESP32 incorrecto.')
    return dict(start=start, segments=segments, checksum=checksum_pos, end=end)


def field(raw):
    value, sep, padding = raw.partition(b'\0')
    if not sep or not value or any(padding):
        raise ValueError('Perfil TQT incompleto o no canónico.')
    try:
        return value.decode('ascii')
    except UnicodeError as e:
        raise ValueError('Perfil TQT debe ser ASCII.') from e


def inspect(raw, kind='R2'):
    if not isinstance(raw, bytes) or not 65536 < len(raw) <= FLASH_SIZE:
        raise ValueError('Se requiere firmware ESP32 completo, de hasta 4 MB.')
    boot = image_layout(raw, 0x1000, 0x8000)
    partitions = []
    digest_seen = False
    for pos in range(0x8000, 0x9000, 32):
        record = raw[pos:pos+32]
        magic = record[:2]
        if magic == b'\xff\xff':
            break
        if magic == b'\xeb\xeb':
            if digest_seen or record[2:16] != b'\xff'*14 or hashlib.md5(raw[0x8000:pos]).digest() != record[16:32]:
                raise ValueError('Checksum de tabla de particiones incorrecto.')
            digest_seen = True
            continue
        if magic != b'\xaa\x50' or digest_seen:
            raise ValueError('Tabla de particiones ESP32 inválida.')
        _, typ, subtype, offset, size, label, flags = struct.unpack('<HBBII16sI', record)
        if not size or offset < 0x9000 or offset % 4096 or offset+size > FLASH_SIZE or flags:
            raise ValueError('Particiones fuera de Flash o cifradas; formato no soportado.')
        if any(offset < p['offset']+p['size'] and offset+size > p['offset'] for p in partitions):
            raise ValueError('Particiones superpuestas.')
        partitions.append(dict(type=typ, subtype=subtype, offset=offset, size=size))
    apps = [p for p in partitions if p['type'] == 0]
    if not digest_seen or not apps:
        raise ValueError('Falta tabla de particiones verificada y aplicación.')
    # Arduino default layout: otadata must select the first app; other OTA slots remain erased.
    app = apps[0]
    if app['offset'] != 0x10000 or app['subtype'] not in (0, 0x10):
        raise ValueError('Se requiere aplicación inicial en 0x10000 (configuración Arduino por defecto).')
    layout = image_layout(raw, app['offset'], min(len(raw), app['offset']+app['size']))
    allowed = [(0x1000, boot['end']), (0x8000, 0x9000), (app['offset'], layout['end'])]
    for p in partitions:
        if p['type'] == 1 and p['subtype'] == 0:  # boot_app0/OTA select data
            if (p['offset'],p['size'])!=(0xE000,0x2000):
                raise ValueError('Datos OTA fuera de la configuración Arduino por defecto.')
            ota=raw[0xE000:0x10000]
            if len(ota)!=0x2000 or ota[:4]!=b'\x01\0\0\0' or ota[4:28]!=b'\xff'*24:
                raise ValueError('La imagen OTA no selecciona la aplicación inicial de forma segura.')
            if struct.unpack_from('<I',ota,28)[0]!=zlib.crc32(ota[:4],0xFFFFFFFF):
                raise ValueError('CRC de selección OTA incorrecto.')
            if any(b!=255 for b in ota[32:4096]) or ota[4096:4100] not in (b'\0'*4,b'\xff'*4) or any(b!=255 for b in ota[4100:]):
                raise ValueError('La imagen incluye un estado OTA previo o selecciona otra aplicación.')
            allowed.append((p['offset'], p['offset']+p['size']))
    if app['subtype']==0x10 and not any(p['type']==1 and p['subtype']==0 for p in partitions):
        raise ValueError('Falta la selección OTA de la aplicación inicial.')
    # Never propagate EEPROM/NVS data, encrypted payloads or a second preloaded application.
    cursor = 0
    for first, last in sorted(allowed):
        if any(b != 255 for b in raw[cursor:first]):
            raise ValueError('El archivo incluye datos de unidad u otra aplicación fuera de las regiones permitidas.')
        cursor = min(last, len(raw))
    if any(b != 255 for b in raw[cursor:]):
        raise ValueError('Hay datos adicionales o firma Secure Boot; no se personalizan.')
    if kind=='R1':   # sketch sin perfil ni identidad por unidad: solo se valida la estructura de la imagen
        return dict(kind='R1',hw='',fw='',nombre='',module='ESP32',schema=0,bytes=len(raw),
                    sha256=hashlib.sha256(raw).hexdigest(),ota_protocol=0,key_id=''), None, layout
    positions = []
    for first, last in layout['segments']:
        pos = raw.find(MAGIC, first, last)
        while pos >= 0:
            if pos+PROFILE.size <= last:
                positions.append(pos)
            pos = raw.find(MAGIC, pos+1, last)
    if len(positions) != 1:
        raise ValueError('Falta perfil único R2 V4.0; el firmware anterior no admite personalizar un binario.')
    pos = positions[0]
    _, schema, hw, fw, name, module = PROFILE.unpack_from(raw, pos)
    hw, fw, name, module = map(field, (hw, fw, name, module))
    if schema not in (1,2,3) or module != 'ESP32-WROOM-32E-N4':
        raise ValueError('Esquema o módulo ESP32 no soportado.')
    if not re.fullmatch(r'\d+(?:\.\d+)+', hw) or len(hw) > 7 or not re.fullmatch(r'\d+(?:\.\d+)+', fw) or len(fw) > 15:
        raise ValueError('Versiones HW/FW inválidas en el perfil.')
    suffix=r'XXXX' if schema==3 else r'\d{4}'
    prefixes=[re.escape('TQT_R2_V'+hw.replace('.', '')+'_'),re.escape('TQT-R2-V'+hw.replace('.', '')+'-')]
    if not re.fullmatch('(?:'+'|'.join(prefixes)+')'+suffix, name) or len(name) > 23:
        raise ValueError('Nombre BLE incompatible con el HW del firmware.')
    meta = dict(kind='R2', hw=hw, fw=fw, nombre=name, module=module, schema=schema,
                bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    meta.update(ota_protocol=0,key_id='',exact_name=b'"name_format":2' in raw)
    if schema in (2,3):
        if not any(a<=pos and pos+PROFILE_V2.size<=b for a,b in layout['segments']):
            raise ValueError('Perfil OTA incompleto.')
        flags,key=struct.unpack_from('<I32s',raw,pos+92)
        if flags!=(3 if schema==3 else 1) or tuple(int(v) for v in fw.split('.'))<(4,0):
            raise ValueError('Capacidad/version OTA no soportada.')
        if [(p['offset'],p['size'],p['subtype']) for p in apps]!=[(0x10000,0x140000,0x10),(0x150000,0x140000,0x11)]:
            raise ValueError('OTA requiere las dos particiones Arduino de 1280 KiB.')
        meta.update(ota_protocol=1,key_id=hashlib.sha256(key).hexdigest()[:16] if any(key) else '')
        if schema==3:
            if fw!='4.0' or any(key):raise ValueError('La base genérica debe ser4.0 y no contener clave de unidad.')
            meta['bootstrap']=True
    return meta, pos, layout


def personalize(raw, name, ota_key=None):
    meta, pos, layout = inspect(raw)
    if meta.get('bootstrap'):raise ValueError('La base genérica se instala idéntica; la identidad se asigna por BLE.')
    prefixes=[re.escape('TQT_R2_V'+meta['hw'].replace('.', '')+'_'),re.escape('TQT-R2-V'+meta['hw'].replace('.', '')+'-')]
    if not re.fullmatch('(?:'+'|'.join(prefixes)+')'+r'\d{4}', name) or len(name)>23:
        raise ValueError('La identidad del inventario no coincide con el HW del firmware.')
    image = bytearray(raw)
    image[pos+NAME_OFFSET:pos+NAME_OFFSET+24] = name.encode('ascii').ljust(24,b'\0')
    if meta['schema']==2 and ota_key is not None:
        if not isinstance(ota_key,bytes) or len(ota_key)!=32:
            raise ValueError('Credencial de unidad OTA inválida.')
        image[pos+KEY_OFFSET:pos+KEY_OFFSET+32]=ota_key
    checksum = 0xEF
    for first,last in layout['segments']:
        for value in image[first:last]:
            checksum ^= value
    image[layout['checksum']] = checksum
    image[layout['checksum']+1:layout['end']] = hashlib.sha256(image[layout['start']:layout['checksum']+1]).digest()
    final = bytes(image)
    verified, _, _ = inspect(final)
    return final, dict(verified, source_sha256=meta['sha256'])


def normalize(raw, filename, tipo='R2', version=None):
    if tipo not in ('R1','R2'):
        raise ValueError('Tipo de placa inválido.')
    if not isinstance(raw,bytes) or len(raw)>MAX_UPLOAD:
        raise ValueError('Firmware vacío o mayor de 12 MB.')
    filename=filename.replace('\\','/').split('/')[-1].strip()
    if not 1<=len(filename)<=180 or any(ord(ch)<32 for ch in filename):
        raise ValueError('Nombre de archivo inválido.')
    if filename.lower().endswith('.hex'):
        raw = hex_image(raw)
    elif not filename.lower().endswith('.bin'):
        raise ValueError('Sube un merged.bin o un Intel HEX de ESP32 completo.')
    if tipo=='R1':
        version=(version or '').strip()
        if not re.fullmatch(r'\d+(?:\.\d+)*',version) or len(version)>15:
            raise ValueError('Indica la versión del firmware R1 (por ejemplo 1.0).')
        meta, _, layout=inspect(raw,'R1')
        raw=raw[:layout['end']]
        meta, _, _=inspect(raw,'R1')
        return dict(meta,fw=version),raw,filename
    meta, _, layout=inspect(raw)
    raw=raw[:layout['end']]  # canonical image: ignore erased padding, never flash unused NVS/OTA slots
    if meta.get('bootstrap'):return inspect(raw)[0],raw,filename
    template='TQT-R2-V'+meta['hw'].replace('.','')+'-0000' if meta.get('exact_name') else 'TQT_R2_V'+meta['hw'].replace('.','')+'_0000'
    stored, _=personalize(raw,template,bytes(32))
    meta, _, _=inspect(stored)
    return meta,stored,filename


def ensure(c):
    c.execute('''CREATE TABLE IF NOT EXISTS esp32_firmwares (
      id TEXT PRIMARY KEY, hw TEXT NOT NULL, fw TEXT NOT NULL, filename TEXT NOT NULL,
      sha256 TEXT NOT NULL UNIQUE, metadata TEXT NOT NULL, image BLOB NOT NULL,
      created REAL NOT NULL, operator TEXT NOT NULL, tipo TEXT NOT NULL DEFAULT 'R2')''')
    if not any(r[1]=='tipo' for r in c.execute('PRAGMA table_info(esp32_firmwares)')):   # migración: catálogo previo = R2
        c.execute("ALTER TABLE esp32_firmwares ADD COLUMN tipo TEXT NOT NULL DEFAULT 'R2'")
    c.execute('''CREATE TABLE IF NOT EXISTS esp32_unit_keys (
        pcb INTEGER PRIMARY KEY REFERENCES pcb_inventario(id) ON DELETE CASCADE, secret BLOB NOT NULL CHECK(length(secret)=32),
        created REAL NOT NULL)''')
    if not c.execute('SELECT 1 FROM esp32_firmwares LIMIT 1').fetchone():
        path=ROOT/'firmware/esp32_r2/TQT_R2_V4_0.merged.bin'
        meta,image,filename=normalize(path.read_bytes(),path.name)
        c.execute('INSERT OR IGNORE INTO esp32_firmwares(id,hw,fw,filename,sha256,metadata,image,created,operator) VALUES(?,?,?,?,?,?,?,?,?)',
                  ('base-R2-v4',meta['hw'],meta['fw'],filename,meta['sha256'],json.dumps(meta),image,0,'sistema'))
    path=ROOT/'firmware/esp32_r2/TQT_R2_V4_1.merged.bin'
    if path.is_file() and not c.execute("SELECT 1 FROM esp32_firmwares WHERE id='base-R2-v41'").fetchone():
        meta,image,filename=normalize(path.read_bytes(),path.name)
        c.execute('INSERT INTO esp32_firmwares(id,hw,fw,filename,sha256,metadata,image,created,operator) VALUES(?,?,?,?,?,?,?,?,?)',
                  ('base-R2-v41',meta['hw'],meta['fw'],filename,meta['sha256'],json.dumps(meta),image,1,'sistema'))
    path=ROOT/'firmware/esp32_r2/TQT_R2_V4_1_1.merged.bin'
    if path.is_file() and not c.execute("SELECT 1 FROM esp32_firmwares WHERE id='base-R2-v411'").fetchone():
        meta,image,filename=normalize(path.read_bytes(),path.name)
        c.execute('INSERT INTO esp32_firmwares(id,hw,fw,filename,sha256,metadata,image,created,operator) VALUES(?,?,?,?,?,?,?,?,?)',
                  ('base-R2-v411',meta['hw'],meta['fw'],filename,meta['sha256'],json.dumps(meta),image,2,'sistema'))
    seed_r1(c)
    for identifier,filename,created in [('base-R2-v42','TQT_R2_V4_2.merged.bin',4),('base-R2-v40-generic','TQT_R2_BASE_V4_0_GENERIC.merged.bin',5)]:
        path=ROOT/'firmware/esp32_r2'/filename
        if path.is_file() and not c.execute('SELECT 1 FROM esp32_firmwares WHERE id=?',(identifier,)).fetchone():
            meta,image,filename=normalize(path.read_bytes(),filename)
            c.execute('INSERT INTO esp32_firmwares(id,hw,fw,filename,sha256,metadata,image,created,operator) VALUES(?,?,?,?,?,?,?,?,?)',
                      (identifier,meta['hw'],meta['fw'],filename,meta['sha256'],json.dumps(meta),image,created,'sistema'))
    path=ROOT/'firmware/esp32_r2/TQT_R2_BASE_V4_0_OTA.merged.bin'
    if path.is_file() and not c.execute("SELECT 1 FROM esp32_firmwares WHERE id='base-R2-v40-ota'").fetchone():
        meta,image,filename=normalize(path.read_bytes(),path.name)
        c.execute('INSERT INTO esp32_firmwares(id,hw,fw,filename,sha256,metadata,image,created,operator) VALUES(?,?,?,?,?,?,?,?,?)',
                  ('base-R2-v40-ota',meta['hw'],meta['fw'],filename,meta['sha256'],json.dumps(meta),image,3,'sistema'))


def seed_r1(c):
    """R1: ESP32_BLE_SERIAL.json + .merged.bin -> entrada 'base-R1-ble' (idempotente; se omite si falta algo o el hash no coincide)."""
    if c.execute("SELECT 1 FROM esp32_firmwares WHERE id='base-R1-ble'").fetchone(): return
    path=ROOT/'firmware/esp32_r1/ESP32_BLE_SERIAL.merged.bin'
    try:
        info=json.loads((ROOT/'firmware/esp32_r1/ESP32_BLE_SERIAL.json').read_text(encoding='utf-8'))
        raw=path.read_bytes()
        if info.get('sha256') and info['sha256']!=hashlib.sha256(raw).hexdigest(): return
        meta,image,filename=normalize(raw,path.name,'R1',str(info.get('version','')))
        meta.update(hw=str(info.get('hw') or ''),hardware=info.get('hardware',''),fqbn=info.get('fqbn',''),fecha=info.get('fecha',''))
        if c.execute('SELECT 1 FROM esp32_firmwares WHERE sha256=?',(meta['sha256'],)).fetchone(): return
        c.execute("INSERT INTO esp32_firmwares(id,hw,fw,filename,sha256,metadata,image,created,operator,tipo) VALUES(?,?,?,?,?,?,?,?,?,'R1')",
                  ('base-R1-ble',meta['hw'],meta['fw'],filename,meta['sha256'],json.dumps(meta),image,0,'sistema'))
    except (OSError,ValueError,TypeError,AttributeError): return


def public(row):
    return dict(json.loads(row['metadata']),id=row['id'],filename=row['filename'],created=row['created'])


def rows(c,hw='',tipo='R2'):
    ensure(c)
    found=list(c.execute('SELECT * FROM esp32_firmwares WHERE tipo=?',(tipo,)))
    if hw and tipo=='R2':
        found=[r for r in found if r['hw'].replace('.','')==hw.replace('.','')]
    def order(row):
        parts=[int(x) for x in row['fw'].split('.')]
        while len(parts)>1 and parts[-1]==0:
            parts.pop()
        return tuple(parts),row['created'],row['id']
    return sorted(found,key=order,reverse=True)


def catalogue(hw='',tipo='R2'):
    with db.transaction() as c:
        found=rows(c,hw,tipo)
    return dict(items=[public(r) for r in found],default_id=found[0]['id'] if found else None)


def save(raw,filename,operator,tipo='R2',version=None):
    meta,image,filename=normalize(raw,filename,tipo,version)
    with db.transaction() as c:
        ensure(c)
        previous=c.execute('SELECT * FROM esp32_firmwares WHERE sha256=?',(meta['sha256'],)).fetchone()
        if previous:
            return dict(public(previous),existing=True)
        identifier=secrets.token_hex(12)
        c.execute('INSERT INTO esp32_firmwares(id,hw,fw,filename,sha256,metadata,image,created,operator,tipo) VALUES(?,?,?,?,?,?,?,?,?,?)',
                  (identifier,meta['hw'],meta['fw'],filename,meta['sha256'],json.dumps(meta),image,time.time(),operator,tipo))
        db.log_evento('ESP32_FIRMWARE_GUARDADO',None,None,f'{tipo} HW {meta["hw"]} FW {meta["fw"]}; sha256={meta["sha256"]}',operator,conn=c)
        return dict(meta,id=identifier,filename=filename,existing=False)


def r1_gate(c,pcb):
    """Orden de producción: R2 con MAC -> STM32 de la R1 verificado con J-Link -> recién entonces el ESP32 de la R1."""
    falta=[]
    tarjeta=db.get_tarjeta_by_id(pcb['tarjeta_id'],c) if pcb.get('tarjeta_id') else None
    if not tarjeta: falta.append('la R1 no está vinculada a una tarjeta')
    elif not (tarjeta.get('r2') or {}).get('mac'): falta.append('la R2 de la tarjeta no tiene MAC guardada')
    job=None
    if c.execute("SELECT 1 FROM sqlite_master WHERE name='stm32_jobs'").fetchone():
        job=c.execute('SELECT state FROM stm32_jobs WHERE pcb=? ORDER BY created DESC,updated DESC LIMIT 1',(pcb['id'],)).fetchone()
    if not job: falta.append('el STM32 de esta R1 no se ha programado con J-Link')
    elif job['state']!='verified': falta.append(f'el último trabajo J-Link del STM32 está en estado «{job["state"]}», no verificado')
    if falta: raise ValueError('Primero programa la R2 (MAC) y el STM32 de esta R1 con J-Link; falta: '+'; '.join(falta)+'.')


def gate(pcb_id):
    with db.transaction() as c:
        pcb=inv.get_pcb(pcb_id,conn=c)
        if not pcb or pcb['tipo']!='R1': return dict(ok=True,motivo='')
        try: r1_gate(c,pcb)
        except ValueError as e: return dict(ok=False,motivo=str(e))
        return dict(ok=True,motivo='')


def prepare(pcb_id,firmware_id=None,provision=False):
    with db.transaction() as c:
        pcb=inv.get_pcb(pcb_id,conn=c)
        if not pcb or pcb['tipo'] not in ('R1','R2'):
            raise ValueError('Elige una R1 o R2 del inventario.')
        r1=pcb['tipo']=='R1'
        if r1: r1_gate(c,pcb)
        found=rows(c,pcb['version'],pcb['tipo'])
        row=next((r for r in found if r['id']==firmware_id),None) if firmware_id else (found[0] if found else None)
        if row is None:
            raise ValueError('No hay firmware ESP32 compatible con la placa seleccionada.' if r1 else 'No hay firmware compatible con el HW de la R2 seleccionada.')
        raw=bytes(row['image'])
        if hashlib.sha256(raw).hexdigest()!=row['sha256']:
            raise ValueError('El firmware guardado no coincide con su hash.')
        if r1:   # sin identidad por unidad: la imagen se entrega tal cual está en el catálogo
            inspect(raw,'R1')
            return dict(json.loads(row['metadata']),firmware_id=row['id'],pcb_id=pcb_id),raw
        meta,_,_=inspect(raw)
        name=pcb['nombre'] if meta.get('exact_name') else pcb['nombre'].replace('-','_')
        if not name.replace('_','-').endswith('-'+pcb['serie']) or pcb['serie']=='0000':
            raise ValueError('Nombre y serie de R2 inconsistentes en el inventario.')
        meta,_,_=inspect(raw)
        if meta.get('bootstrap'):return dict(meta,firmware_id=row['id'],pcb_id=pcb_id),raw
        secret=None
        if meta['ota_protocol']:
            key=c.execute('SELECT secret FROM esp32_unit_keys WHERE pcb=?',(pcb_id,)).fetchone()
            if not key and provision:
                secret=secrets.token_bytes(32)
                c.execute('INSERT INTO esp32_unit_keys VALUES(?,?,?)',(pcb_id,secret,time.time()))
            elif key:
                secret=bytes(key['secret'])
        image,meta=personalize(raw,name,secret)
        return dict(meta,firmware_id=row['id'],pcb_id=pcb_id),image


def result(pcb_id,mac,firmware_id,name,hw,fw,operator,key_id='',ota_protocol=0):
    with db.transaction() as c:
        ensure(c)
        pcb=inv.get_pcb(pcb_id,conn=c)
        row=c.execute('SELECT * FROM esp32_firmwares WHERE id=?',(firmware_id,)).fetchone()
        if not pcb or pcb['tipo'] not in ('R1','R2') or not row or row['tipo']!=pcb['tipo']:
            raise ValueError('Placa R2 o firmware no encontrado.')
        if pcb['tipo']=='R1':
            r1_gate(c,pcb)
            # solo MAC: pcb.firmware de una R1 es el del STM32 y no se toca
            if hashlib.sha256(bytes(row['image'])).hexdigest()!=row['sha256']:
                raise ValueError('El archivo guardado no coincide con su hash.')
            updated=inv.guardar_programacion(pcb_id,mac,None,operator,conn=c)
            db.log_evento('ESP32_PROGRAMADA',None,None,f'{pcb["nombre"]}; firmware_id={firmware_id}; ESP32 R1 FW {row["fw"]}; base_sha256={row["sha256"]}',operator,conn=c)
            return updated
        expected_name=pcb['nombre'] if json.loads(row['metadata']).get('exact_name') else pcb['nombre'].replace('-','_')
        if (name,hw,fw)!=(expected_name,row['hw'],row['fw']) or pcb['version']!=hw.replace('.',''):
            raise ValueError('Nombre o versiones verificadas no coinciden con la R2 y su firmware.')
        if hashlib.sha256(bytes(row['image'])).hexdigest()!=row['sha256']:
            raise ValueError('El archivo guardado no coincide con su hash.')
        image_meta,_,_=inspect(bytes(row['image']))
        if image_meta['ota_protocol']:
            key=c.execute('SELECT secret FROM esp32_unit_keys WHERE pcb=?',(pcb_id,)).fetchone()
            expected=hashlib.sha256(bytes(key['secret'])).hexdigest()[:16] if key else ''
            if not expected or ota_protocol!=1 or key_id!=expected:
                raise ValueError('La R2 no confirmó la credencial y capacidad OTA de esta unidad.')
        updated=inv.guardar_programacion(pcb_id,mac,fw,operator,conn=c)
        db.log_evento('ESP32_PROGRAMADA',None,None,f'{name}; firmware_id={firmware_id}; HW {hw} FW {fw}; base_sha256={row["sha256"]}',operator,conn=c)
        return updated
