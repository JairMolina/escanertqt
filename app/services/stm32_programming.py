"""R1 STM32: immutable firmware, inventory-derived identities and durable station jobs."""
import hashlib
import json
import secrets
import re
import time
from pathlib import Path

from app.database import db, inventario as inv
from app.services import tqt_hex as hx
from app.services import stm32_firmware as catalogue

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'firmware/stm32_r1/fw43_base.hex'
# v1.3.55: la R3 (STM32F103RET6 «TIMER») lleva una imagen fija, sin identidad por unidad.
R3_BASE = ROOT / 'firmware/stm32_r3/r3_fw10.hex'
# v1.4.40: claims refresh last_seen at most every 5 s (online window is 20 s).
LAST_SEEN_S = 5


def firmware_r3():
    meta = json.loads(R3_BASE.with_suffix('.hex.json').read_text(encoding='utf-8'))
    texto = R3_BASE.read_text(encoding='ascii')
    if hashlib.sha256(texto.encode('ascii')).hexdigest() != meta['hex_sha256']:
        raise ValueError('El firmware R3 no coincide con su registro.')
    mem, _ = hx.leer_hex(R3_BASE)
    if any(not hx.FLASH_BEGIN <= a < hx.IDENTITY_BEGIN for a in mem):
        raise ValueError('El firmware R3 escribe fuera de la Flash de aplicación.')
    return texto, mem, meta


def huella(mem):
    """SHA-256 de los bytes de la imagen en orden de dirección; el agente la recalcula sobre la lectura de Flash."""
    return hashlib.sha256(bytes(mem[a] for a in sorted(mem))).hexdigest()


def init():
    # Close the schema read before acquiring a write transaction. A deferred read
    # upgraded to ALTER can fail with SQLITE_BUSY_SNAPSHOT while agents poll.
    with db.get_db() as c:
        cols = {r[1] for r in c.execute('PRAGMA table_info(stm32_stations)')}
    if cols and not {'revoked_at', 'revoked_by', 'tokens_previos'} <= cols:
        with db.transaction() as c:
            cols = {r[1] for r in c.execute('PRAGMA table_info(stm32_stations)')}
            for name, kind in (('revoked_at', 'REAL'), ('revoked_by', 'TEXT'), ('tokens_previos', 'TEXT')):
                if name not in cols:
                    c.execute(f'ALTER TABLE stm32_stations ADD COLUMN {name} {kind}')
    with db.get_db() as c:
        c.execute('CREATE TABLE IF NOT EXISTS stm32_stations (id TEXT PRIMARY KEY, name TEXT NOT NULL, token_hash TEXT NOT NULL, owner TEXT NOT NULL, last_seen REAL NOT NULL DEFAULT 0, revoked_at REAL, revoked_by TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS stm32_jobs (id TEXT PRIMARY KEY, station TEXT NOT NULL, pcb INTEGER NOT NULL, state TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL, operator TEXT NOT NULL, payload TEXT NOT NULL, image TEXT NOT NULL, result TEXT)')
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS stm32_pcb_busy ON stm32_jobs(pcb) WHERE state IN ('queued','running')")
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS stm32_station_busy ON stm32_jobs(station) WHERE state IN ('queued','running')")
        catalogue.ensure(c)


def firmware():
    mem, starts = hx.leer_hex(BASE)
    if any(a >= hx.IDENTITY_BEGIN for a in mem):
        raise ValueError('El firmware base contiene identidad de otra tarjeta.')
    return mem, starts, hx.leer_perfil(mem)


def analizar_hex(texto, tipo='R1'):
    """v1.3.54: lee un HEX subido por el operador y extrae su perfil (MCU/HW/FW) sin guardarlo."""
    import tempfile
    with tempfile.TemporaryDirectory(prefix='tqt_hex_') as tmp:
        path = Path(tmp)/'subido.hex'
        path.write_text(texto, encoding='ascii', errors='strict')
        mem, _ = hx.leer_hex(path)
    if tipo == 'R3':
        _, r3mem, meta = firmware_r3()
        igual = mem == r3mem
        with db.get_db() as c:
            catalogue.ensure(c)
            known = c.execute('SELECT * FROM stm32_firmwares WHERE kind=? AND sha256=?', ('R3',hashlib.sha256(texto.encode('ascii')).hexdigest())).fetchone()
            if known:
                meta = catalogue.public(known)
                igual = True
        return dict(mcu=meta['mcu'], hw=meta['hw'] if igual else '?', fw=meta['fw'] if igual else 'desconocida', bytes=len(mem),
                    sha256=hashlib.sha256(texto.encode('ascii')).hexdigest(), identidad=None,
                    base_fw=meta['fw'], base_hw=meta['hw'],
                    aviso=None if igual else 'El HEX R3 no contiene versión interna. Indica HW y FW para registrarlo en el catálogo.')
    identidad = hx.leer_identidad(mem)
    app = {a: b for a, b in mem.items() if a < hx.IDENTITY_BEGIN}
    profile = hx.leer_perfil(app)
    base = firmware()[2]
    return dict(mcu=profile['mcu'], hw=profile['hw'], fw=profile['fw'], bytes=len(app),
                sha256=hashlib.sha256(texto.encode('ascii')).hexdigest(),
                identidad=identidad.get('nombre') if identidad else None,
                base_fw=base['fw'], base_hw=base['hw'])


def preview(pcb_id, conn=None, firmware_id=None):
    def read_r3(c, p):
        hw = p['version']
        meta, texto = catalogue.selected(c, 'R3', hw, firmware_id)
        mem, _ = catalogue.parse(texto)
        if hw == meta['hw'].replace('.', ''):
            hw = meta['hw']
        identity = dict(nombre='TQT_R3_V'+hw.replace('.', '')+'_'+p['serie'], hw=hw, fw=meta['fw'])
        result = dict(kind='R3', pcb_id=p['id'], tarjeta_id=p['tarjeta_id'], nombre=p['nombre'], r1=p['nombre'],
                      firmware_id=meta['id'], firmware=meta,
                      identity=identity, profile=dict(mcu=meta['mcu'], hw=meta['hw'], fw=meta['fw']),
                      base_sha256=meta['sha256'], hex_sha256=meta['sha256'],
                      identity_sha256=huella(mem), bytes=len(mem))
        return result, texto

    def read(c):
        p = inv.get_pcb(pcb_id, conn=c)
        if p and p['tipo'] == 'R3':
            if p['estado_ciclo'] in ('FALLA', 'BAJA'):
                raise ValueError('La R3 está marcada como FALLA o BAJA.')
            return read_r3(c, p)
        if not p or p['tipo'] != 'R1':
            raise ValueError('Selecciona una PCB R1 o R3 registrada.')
        if p['estado_ciclo'] in ('FALLA', 'BAJA'):
            raise ValueError('La R1 está marcada como FALLA o BAJA.')
        t = db.get_tarjeta_by_id(p['tarjeta_id'], c) if p['tarjeta_id'] else None
        r2 = t.get('r2') if t else None
        if not r2 or not r2.get('mac') or r2['estado_ciclo'] in ('FALLA', 'BAJA'):
            raise ValueError('La R1 necesita una R2 vinculada, sin falla y con MAC registrada.')
        hw = p['version']
        meta, stored = catalogue.selected(c, 'R1', hw, firmware_id)
        mem, starts = catalogue.parse(stored)
        profile = hx.leer_perfil(mem)
        # Inventario almacena V30; el contrato STM32 usa HW 3.0.
        if hw == profile['hw'].replace('.', ''):
            hw = profile['hw']
        identity = dict(nombre='TQT_R1_V'+hw.replace('.', '')+'_'+p['serie'],
                        id_r=r2['serie'], mac_r=r2['mac'].upper(), hw=hw, fw=profile['fw'])
        raw = hx.identidad_bytes(**identity)
        hx.comprobar_perfil(identity, profile)
        mem.update({hx.IDENTITY_BEGIN+i: b for i, b in enumerate(raw)})
        image = hx.emitir_hex(mem, starts)
        result = dict(kind='R1', pcb_id=p['id'], tarjeta_id=t['id'], r1=p['nombre'], nombre=p['nombre'], r2=r2['nombre'],
                      firmware_id=meta['id'], firmware=meta,
                      r2_id=r2['id'], identity=identity, profile=profile,
                      base_sha256=meta['sha256'],
                      hex_sha256=hashlib.sha256(image.encode('ascii')).hexdigest(),
                      identity_sha256=hashlib.sha256(raw).hexdigest(),
                      crc32=f'{int.from_bytes(raw[-4:], "little"):08X}')
        return result, image
    if conn is not None:
        return read(conn)
    with db.get_db() as c:
        return read(c)


def observed_state(pcb_id):
    """Historical evidence only. Does not read hardware or depend on the selected firmware."""
    init()
    with db.get_db() as c:
        p=inv.get_pcb(pcb_id,conn=c)
        if not p or p['tipo'] not in ('R1','R3'):
            raise ValueError('Selecciona una PCB R1 o R3 registrada.')
        hw=str(p.get('version') or '')
        if re.fullmatch(r'[0-9]{2,}',hw): hw=hw[0]+'.'+hw[1:]
        fw=p.get('firmware') or None
        event=c.execute("SELECT creado_en FROM escaneos WHERE evento='FIRMWARE_GUARDADO' AND valor=? AND detalle=? ORDER BY id DESC LIMIT 1",
                        (p['nombre'],'FW '+fw)).fetchone() if fw else None
        data=dict(pcb_id=p['id'],kind=p['tipo'],source='inventory' if fw else 'none',
                  firmware=fw,hardware=hw,nombre=p['nombre'],id_r=None,mac_r=None,
                  recorded_at=event['creado_en'] if event else None,verified_at=None,
                  job_id=None,uid=None,current_unconfirmed=False,
                  note='Dato de inventario; el contenido actual del STM32 no se ha leído.' if fw else 'No hay una programación verificada ni un firmware registrado.')
        attempts=c.execute('SELECT id,state,created,updated,payload,result FROM stm32_jobs WHERE pcb=? ORDER BY created DESC,id DESC',(p['id'],)).fetchall()
        verified=[]
        for row in attempts:
            if row['state']!='verified': continue
            try:
                payload=json.loads(row['payload']); result=json.loads(row['result'] or '{}')
                identity=payload['identity']; uid=result.get('uid','')
                valid=(result.get('verified') is True and re.fullmatch(r'[a-f0-9]{64}',payload['hex_sha256']) is not None
                       and re.fullmatch(r'[a-f0-9]{64}',payload['identity_sha256']) is not None
                       and result.get('hex_sha256')==payload['hex_sha256']
                       and result.get('identity_sha256')==payload['identity_sha256']
                       and re.fullmatch(r'[A-Fa-f0-9]{24}',uid) is not None
                       and uid.upper() not in ('0'*24,'F'*24)
                       and payload.get('kind','R1')==p['tipo'] and identity.get('fw') and identity.get('hw'))
                if valid: verified.append((row,payload,result))
            except (KeyError,TypeError,ValueError,AttributeError): continue
        if verified:
            row,payload,result=max(verified,key=lambda item:(item[0]['updated'],item[0]['created']))
            identity=payload['identity']
            data.update(source='verified_programming',firmware=identity['fw'],hardware=identity['hw'],
                        nombre=identity.get('nombre'),id_r=identity.get('id_r'),mac_r=identity.get('mac_r'),
                        verified_at=row['updated'],job_id=row['id'],uid=result['uid'],
                        note='Última Flash verificada por lectura J-Link; no es una lectura en vivo ni de EEPROM.')
        if attempts:
            last=attempts[0]
            data['last_attempt']=dict(id=last['id'],state=last['state'])
            if last['id']!=data['job_id'] and last['state']!='queued':
                data['current_unconfirmed']=True
                data['note']='Hay un intento posterior sin verificar: el contenido actual puede no coincidir con el último registro.'
        return data


def station_create(name, owner):
    init()
    # Owner is supplied by the authenticated server session, never the installer body.
    label = str(owner).split('@', 1)[0][:28]
    name = label + ' · ' + (str(name).strip() or 'Equipo de programación')[:29]
    sid, token = secrets.token_hex(12), secrets.token_urlsafe(32)
    with db.get_db() as c:
        c.execute('INSERT INTO stm32_stations(id,name,token_hash,owner) VALUES(?,?,?,?)',
                  (sid, name, hashlib.sha256(token.encode()).hexdigest(), owner))
    return dict(id=sid, token=token, name=name, owner=owner)


def station_rotate(sid, owner):
    """v1.4.64: reinstalar el mismo puente/agente: conserva id, nombre y dueño y solo emite token nuevo.
    Devuelve None si la estación no existe, está revocada o es de otra cuenta (entonces se crea una nueva)."""
    init()
    token = secrets.token_urlsafe(32)
    with db.get_db() as c:
        row = c.execute('SELECT * FROM stm32_stations WHERE id=? AND revoked_at IS NULL AND lower(owner)=lower(?)',
                        (str(sid or ''), str(owner))).fetchone()
        if not row:
            return None
        # el token anterior sigue valiendo (hasta 4): un instalador descargado antes que se abra después no queda en 401
        previos = ([row['token_hash']] + json.loads(row['tokens_previos'] or '[]'))[:4]
        c.execute('UPDATE stm32_stations SET token_hash=?, tokens_previos=? WHERE id=?',
                  (hashlib.sha256(token.encode()).hexdigest(), json.dumps(previos), row['id']))
    return dict(id=row['id'], token=token, name=row['name'], owner=row['owner'])


def station_auth(token):
    init()
    with db.get_db() as c:
        th = hashlib.sha256(token.encode()).hexdigest()
        row = c.execute('SELECT * FROM stm32_stations WHERE token_hash=?', (th,)).fetchone()
        if not row:   # v1.4.64: token de un instalador anterior de la misma estación (ver station_rotate)
            row = c.execute("SELECT s.* FROM stm32_stations s, json_each(COALESCE(s.tokens_previos,'[]')) j WHERE j.value=?", (th,)).fetchone()
    if not row:
        raise ValueError('Credencial de estación inválida.')
    if row['revoked_at'] is not None:
        raise StationRevokedError('Agente eliminado. Su credencial ya no permite recibir trabajos.')
    return dict(row)


# v1.3.75: IP pública desde la que reporta cada agente (en memoria); sirve para mostrar solo la estación local
STATION_IP = {}


class StationRevokedError(ValueError):
    pass


class StationRemovalError(ValueError):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def require_station(c, sid):
    row = c.execute('SELECT * FROM stm32_stations WHERE id=? AND revoked_at IS NULL', (sid,)).fetchone()
    if not row:
        raise StationRevokedError('Agente eliminado o inexistente. Registra y selecciona un agente vigente.')
    return row


def revoke_stations(ids, operator, administrator=False):
    """Atomic logical removal. Historical FK references and results are retained."""
    init()
    ids = list(dict.fromkeys(ids))
    if not ids or any(not re.fullmatch('[a-f0-9]{24}', sid) for sid in ids):
        raise StationRemovalError(400, 'Selecciona agentes físicos válidos; los bancos del navegador se conservan.')
    with db.transaction() as c:
        tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        now = time.time()
        for sid in ids:
            row = c.execute('SELECT * FROM stm32_stations WHERE id=?', (sid,)).fetchone()
            if not row:
                raise StationRemovalError(404, 'Agente no encontrado.')
            if row['owner'] != operator and not administrator:
                raise StationRemovalError(403, 'Solo el usuario que registró el agente o un administrador puede borrarlo.')
            checks = [('stm32_jobs', "station=? AND state IN ('queued','running')", (sid,)),
                      ('tqt_test_runs', "station=? AND state IN ('queued','running')", (sid,)),
                      ('tqt_test_commands', "station=? AND state IN ('queued','running') AND created>?", (sid, now-180)),
                      ('r2_programming_attempts', "station=? AND state IN ('queued','running','flashing') AND created>?", (sid, now-600))]
            for table, where, params in checks:
                if table in tables and c.execute('SELECT 1 FROM '+table+' WHERE '+where, params).fetchone():
                    raise StationRemovalError(409, 'El agente tiene un trabajo o una prueba en curso. Espera a que termine o detenlo antes de borrarlo.')
            if {'tqt_ble_leases', 'tqt_test_runs'} <= tables and c.execute(
                "SELECT 1 FROM tqt_ble_leases l JOIN tqt_test_runs r ON r.id=l.run WHERE l.station=? AND r.state IN ('queued','running')", (sid,)).fetchone():
                raise StationRemovalError(409, 'El agente está reservado para Bluetooth en una prueba en curso.')
        for sid in ids:
            c.execute('UPDATE stm32_stations SET revoked_at=?,revoked_by=? WHERE id=? AND revoked_at IS NULL', (now, operator, sid))
            if 'tqt_test_commands' in tables:
                c.execute("UPDATE tqt_test_commands SET state='error',result=? WHERE station=? AND state IN ('queued','running')",
                          (json.dumps({'error': 'Agente eliminado; comando caducado, no ejecutado de nuevo.'}), sid))
            for table in ('tqt_test_presence', 'r2_agent_presence', 'tqt_ble_leases'):
                if table in tables:
                    c.execute('DELETE FROM '+table+' WHERE station=?', (sid,))
    for sid in ids:
        STATION_IP.pop(sid, None)
    return dict(removed=ids, history_preserved=True)


def stations(client_ip=None, operator=None, administrator=False):
    init()
    with db.get_db() as c:
        return [dict(id=r['id'], name=r['name'], owner=r['owner'], can_delete=administrator or r['owner']==operator, online=time.time()-r['last_seen']<20,
                     local=bool(client_ip) and STATION_IP.get(r['id']) == client_ip)
                for r in c.execute("SELECT * FROM stm32_stations WHERE id NOT LIKE 'web-%' AND revoked_at IS NULL ORDER BY name")]


def create_job(pcb, station, expected, operator, physical_confirmed=False, firmware_id=None):
    if physical_confirmed is not True:
        raise ValueError('Confirma desde la web que la placa seleccionada está conectada al J-Link.')
    init()
    active_jobs(station)
    with db.transaction() as c:
        st = require_station(c, station)
        if not st or time.time()-st['last_seen'] > 20:
            raise ValueError('La estación Windows está desconectada. Inicia el agente.')
        data, image = preview(pcb, c, firmware_id)
        if data['hex_sha256'] != expected:
            raise ValueError('Cambió el inventario o firmware. Vuelve a cargar los datos antes de programar.')
        if c.execute("SELECT 1 FROM stm32_jobs WHERE (pcb=? OR station=?) AND state IN ('queued','running')", (pcb, station)).fetchone():
            raise ValueError('La tarjeta o estación ya tiene un trabajo en curso.')
        if c.execute("SELECT 1 FROM sqlite_master WHERE name='r2_programming_attempts'").fetchone():
            if c.execute("SELECT 1 FROM r2_programming_attempts WHERE station=? AND state IN ('flashing','queued','running') AND created>?",(station,time.time()-600)).fetchone():
                raise ValueError('La estación está programando o verificando una R2.')
        if c.execute("SELECT 1 FROM sqlite_master WHERE name='tqt_test_runs'").fetchone():
            if c.execute("SELECT 1 FROM tqt_test_runs WHERE (station=? OR requested_card=?) AND state IN ('queued','running')",(station,data.get('tarjeta_id'))).fetchone():
                raise ValueError('La tarjeta o estación está ejecutando una prueba física; espera a que termine.')
        jid, now = secrets.token_hex(16), time.time()
        data['confirmation'] = dict(source='web', operator=operator, pcb_id=pcb,
                                    nombre=data['identity']['nombre'], at=now)
        data['agent'] = dict(id=st['id'], name=st['name'], registered_by=st['owner'])
        c.execute('INSERT INTO stm32_jobs VALUES(?,?,?,?,?,?,?,?,?,NULL)',
                  (jid, station, pcb, 'queued', now, now, operator, json.dumps(data), image))
    return job(jid)


def job(jid):
    init()
    with db.get_db() as c:
        now = time.time()
        c.execute("UPDATE stm32_jobs SET state='failed',result=?,updated=? WHERE id=? AND state='queued' AND created<?",
                  (json.dumps({'error': 'El agente no tomó el trabajo a tiempo; vuelve a prepararlo.'}), now, jid, now-120))
        c.execute("UPDATE stm32_jobs SET state='unknown',result=?,updated=? WHERE id=? AND state='running' AND updated<?",
                  (json.dumps({'error': 'Sin resultado del agente. Comprueba físicamente la tarjeta antes de repetir.'}), now, jid, now-600))
        r = c.execute('SELECT * FROM stm32_jobs WHERE id=?', (jid,)).fetchone()
    if not r:
        raise ValueError('Trabajo no encontrado.')
    d = dict(r)
    d.pop('image')
    d['payload'] = json.loads(d['payload'])
    d['result'] = json.loads(d['result']) if d['result'] else None
    return d


def claim(sid):
    with db.transaction() as c:
        require_station(c, sid)
        now = time.time()
        # Agents poll every ~1 s; refresh at most every LAST_SEEN_S so idle polls do not write to the SD card.
        c.execute('UPDATE stm32_stations SET last_seen=? WHERE id=? AND last_seen<?', (now, sid, now-LAST_SEEN_S))
        # Never automatically repeat an interrupted flash operation.
        c.execute("UPDATE stm32_jobs SET state='unknown',updated=?,result=? WHERE station=? AND state='running' AND updated<?",
                  (now, json.dumps({'error': 'Agente interrumpido; comprobar la tarjeta antes de repetir.'}), sid, now-600))
        r = c.execute("SELECT * FROM stm32_jobs WHERE station=? AND state='queued' ORDER BY created LIMIT 1", (sid,)).fetchone()
        if not r:
            return None
        d = json.loads(r['payload'])
        try:
            current, _ = preview(r['pcb'], c, d.get('firmware_id'))
            if current['hex_sha256'] != d['hex_sha256'] or now-r['created']>120:
                raise ValueError('Trabajo caducado o datos del inventario modificados; vuelve a preparar la tarjeta.')
        except ValueError as e:
            c.execute("UPDATE stm32_jobs SET state='failed',result=?,updated=? WHERE id=?", (json.dumps({'error': str(e)}), now, r['id']))
            return None
        c.execute("UPDATE stm32_jobs SET state='running',updated=? WHERE id=?", (now, r['id']))
        return dict(id=r['id'], payload=d, hex=r['image'])


def active_jobs(sid):
    init()
    with db.get_db() as c:
        ids = [r['id'] for r in c.execute("SELECT id FROM stm32_jobs WHERE station=? AND state IN ('queued','running')", (sid,))]
    return [j for jid in ids if (j := job(jid))['state'] in ('queued', 'running')]


def cancel_station(sid, operator):
    init()
    with db.transaction() as c:
        if not c.execute('SELECT 1 FROM stm32_stations WHERE id=?', (sid,)).fetchone():
            raise ValueError('Estación no encontrada.')
        now = time.time()
        rows = c.execute("SELECT * FROM stm32_jobs WHERE station=? AND state IN ('queued','running')", (sid,)).fetchall()
        for r in rows:
            p = json.loads(r['payload'])
            p['cancel_requested'] = dict(operator=operator, at=now)
            state = 'cancelled' if r['state'] == 'queued' else 'running'
            result = json.dumps(dict(cancelled=True, verified=False, error='Cancelado desde la web antes de grabar.')) if state == 'cancelled' else r['result']
            c.execute('UPDATE stm32_jobs SET state=?,payload=?,result=?,updated=? WHERE id=?', (state,json.dumps(p),result,now,r['id']))
            db.log_evento('STM32_CANCELACION', None, None, 'Cancelación solicitada; job='+r['id'], operator, conn=c)
    return dict(ok=True, jobs=[dict(id=r['id'], waiting=r['state']=='running') for r in rows])


def control(sid, jid):
    with db.transaction() as c:
        r = c.execute('SELECT * FROM stm32_jobs WHERE id=? AND station=?', (jid,sid)).fetchone()
        if not r:
            raise ValueError('Trabajo ajeno o inexistente.')
        if r['state'] == 'running':
            now = time.time()
            c.execute('UPDATE stm32_jobs SET updated=? WHERE id=?',(now,jid))
            c.execute('UPDATE stm32_stations SET last_seen=? WHERE id=?',(now,sid))
    return dict(cancel=bool(json.loads(r['payload']).get('cancel_requested')) or r['state'] not in ('queued','running'), state=r['state'])


def progress(sid, jid, stage):
    stages = ('preparing', 'writing', 'reading', 'restarting', 'reporting')
    if stage not in stages:
        raise ValueError('Etapa de programación inválida.')
    with db.transaction() as c:
        r = c.execute("SELECT * FROM stm32_jobs WHERE id=? AND station=? AND state='running'", (jid, sid)).fetchone()
        if not r:
            raise ValueError('El trabajo no está activo en esta estación.')
        payload = json.loads(r['payload'])
        previous = payload.get('progress', {}).get('stage')
        if previous in stages and stages.index(stage) < stages.index(previous):
            raise ValueError('El avance no puede retroceder.')
        now = time.time()
        payload['progress'] = dict(stage=stage, at=now)
        c.execute('UPDATE stm32_jobs SET payload=?,updated=? WHERE id=?', (json.dumps(payload), now, jid))
        c.execute('UPDATE stm32_stations SET last_seen=? WHERE id=?', (now, sid))
    return dict(ok=True)


def finish(sid, jid, result):
    with db.transaction() as c:
        r = c.execute('SELECT * FROM stm32_jobs WHERE id=? AND station=?', (jid, sid)).fetchone()
        if r and r['state'] == 'cancelled':
            return dict(id=jid, state='cancelled')
        if r and r['state'] in ('verified', 'failed') and json.loads(r['result']) == result:
            return dict(id=jid, state=r['state'])  # Lost HTTP acknowledgement: harmless retry.
        if not r or r['state'] not in ('running', 'unknown'):
            raise ValueError('El trabajo no pertenece a la estación o ya terminó.')
        p = json.loads(r['payload'])
        if p.get('cancel_requested') or result.get('cancelled'):
            result = dict(result, verified=False, cancelled=True, error='Programación detenida y cancelada. Comprueba la tarjeta antes de repetir.')
            c.execute("UPDATE stm32_jobs SET state='cancelled',updated=?,result=? WHERE id=?", (time.time(),json.dumps(result),jid))
            return dict(id=jid, state='cancelled')
        uid = result.get('uid', '')
        verified = (result.get('verified') is True and result.get('hex_sha256')==p['hex_sha256']
                    and result.get('identity_sha256')==p['identity_sha256']
                    and re.fullmatch(r'[A-Fa-f0-9]{24}', uid) is not None
                    and uid.upper() not in ('0'*24, 'F'*24))
        state = 'verified' if verified else 'failed'
        if verified:
            # Firmware is recorded only after an authenticated station confirms readback.
            inv.set_firmware(r['pcb'], p['identity']['fw'], r['operator'], conn=c)
        c.execute('UPDATE stm32_jobs SET state=?,updated=?,result=? WHERE id=?',
                  (state, time.time(), json.dumps(result), jid))
        db.log_evento('STM32_PROGRAMACION', None, None, f"{p.get('kind', 'R1')} PCB {r['pcb']} FW {p['identity']['fw']} {state}; job={jid}", r['operator'], conn=c)
    return job(jid)
