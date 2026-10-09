"""R1 STM32: immutable firmware, inventory-derived identities and durable station jobs."""
import hashlib
import json
import secrets
import re
import time
from pathlib import Path

from app.database import db, inventario as inv
from app.services import tqt_hex as hx

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'firmware/stm32_r1/fw43_base.hex'


def init():
    with db.get_db() as c:
        c.execute('CREATE TABLE IF NOT EXISTS stm32_stations (id TEXT PRIMARY KEY, name TEXT NOT NULL, token_hash TEXT NOT NULL, owner TEXT NOT NULL, last_seen REAL NOT NULL DEFAULT 0)')
        c.execute('CREATE TABLE IF NOT EXISTS stm32_jobs (id TEXT PRIMARY KEY, station TEXT NOT NULL, pcb INTEGER NOT NULL, state TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL, operator TEXT NOT NULL, payload TEXT NOT NULL, image TEXT NOT NULL, result TEXT)')
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS stm32_pcb_busy ON stm32_jobs(pcb) WHERE state IN ('queued','running')")
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS stm32_station_busy ON stm32_jobs(station) WHERE state IN ('queued','running')")


def firmware():
    mem, starts = hx.leer_hex(BASE)
    if any(a >= hx.IDENTITY_BEGIN for a in mem):
        raise ValueError('El firmware base contiene identidad de otra tarjeta.')
    return mem, starts, hx.leer_perfil(mem)


def analizar_hex(texto):
    """v1.3.54: lee un HEX subido por el operador y extrae su perfil (MCU/HW/FW) sin guardarlo."""
    import tempfile
    with tempfile.TemporaryDirectory(prefix='tqt_hex_') as tmp:
        path = Path(tmp)/'subido.hex'
        path.write_text(texto, encoding='ascii', errors='strict')
        mem, _ = hx.leer_hex(path)
    identidad = hx.leer_identidad(mem)
    app = {a: b for a, b in mem.items() if a < hx.IDENTITY_BEGIN}
    profile = hx.leer_perfil(app)
    base = firmware()[2]
    return dict(mcu=profile['mcu'], hw=profile['hw'], fw=profile['fw'], bytes=len(app),
                sha256=hashlib.sha256(texto.encode('ascii')).hexdigest(),
                identidad=identidad.get('nombre') if identidad else None,
                base_fw=base['fw'], base_hw=base['hw'])


def preview(pcb_id, conn=None):
    def read(c):
        p = inv.get_pcb(pcb_id, conn=c)
        if not p or p['tipo'] != 'R1':
            raise ValueError('Selecciona una PCB R1 registrada.')
        if p['estado_ciclo'] in ('FALLA', 'BAJA'):
            raise ValueError('La R1 está marcada como FALLA o BAJA.')
        t = db.get_tarjeta_by_id(p['tarjeta_id'], c) if p['tarjeta_id'] else None
        r2 = t.get('r2') if t else None
        if not r2 or not r2.get('mac') or r2['estado_ciclo'] in ('FALLA', 'BAJA'):
            raise ValueError('La R1 necesita una R2 vinculada, sin falla y con MAC registrada.')
        mem, starts, profile = firmware()
        hw = p['version']
        # Inventario almacena V30; el contrato STM32 usa HW 3.0.
        if hw == profile['hw'].replace('.', ''):
            hw = profile['hw']
        identity = dict(nombre='TQT_R1_V'+hw.replace('.', '')+'_'+p['serie'],
                        id_r=r2['serie'], mac_r=r2['mac'].upper(), hw=hw, fw=profile['fw'])
        raw = hx.identidad_bytes(**identity)
        hx.comprobar_perfil(identity, profile)
        mem.update({hx.IDENTITY_BEGIN+i: b for i, b in enumerate(raw)})
        image = hx.emitir_hex(mem, starts)
        result = dict(pcb_id=p['id'], tarjeta_id=t['id'], r1=p['nombre'], r2=r2['nombre'],
                      r2_id=r2['id'], identity=identity, profile=profile,
                      base_sha256=hashlib.sha256(BASE.read_bytes()).hexdigest(),
                      hex_sha256=hashlib.sha256(image.encode('ascii')).hexdigest(),
                      identity_sha256=hashlib.sha256(raw).hexdigest(),
                      crc32=f'{int.from_bytes(raw[-4:], "little"):08X}')
        return result, image
    if conn is not None:
        return read(conn)
    with db.get_db() as c:
        return read(c)


def station_create(name, owner):
    init()
    sid, token = secrets.token_hex(12), secrets.token_urlsafe(32)
    with db.get_db() as c:
        c.execute('INSERT INTO stm32_stations(id,name,token_hash,owner) VALUES(?,?,?,?)',
                  (sid, name, hashlib.sha256(token.encode()).hexdigest(), owner))
    return dict(id=sid, token=token, name=name)


def station_auth(token):
    init()
    with db.get_db() as c:
        row = c.execute('SELECT * FROM stm32_stations WHERE token_hash=?',
                        (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
    if not row:
        raise ValueError('Credencial de estación inválida.')
    return dict(row)


def stations():
    init()
    with db.get_db() as c:
        return [dict(id=r['id'], name=r['name'], online=time.time()-r['last_seen']<20)
                for r in c.execute('SELECT * FROM stm32_stations ORDER BY name')]


def create_job(pcb, station, expected, operator, physical_confirmed=False):
    if physical_confirmed is not True:
        raise ValueError('Confirma desde la web que la R1 seleccionada está conectada al J-Link.')
    init()
    with db.transaction() as c:
        st = c.execute('SELECT * FROM stm32_stations WHERE id=?', (station,)).fetchone()
        if not st or time.time()-st['last_seen'] > 20:
            raise ValueError('La estación Windows está desconectada. Inicia el agente.')
        data, image = preview(pcb, c)
        if data['hex_sha256'] != expected:
            raise ValueError('Cambió el inventario o firmware. Vuelve a cargar los datos antes de programar.')
        if c.execute("SELECT 1 FROM stm32_jobs WHERE (pcb=? OR station=?) AND state IN ('queued','running')", (pcb, station)).fetchone():
            raise ValueError('La tarjeta o estación ya tiene un trabajo en curso.')
        jid, now = secrets.token_hex(16), time.time()
        data['confirmation'] = dict(source='web', operator=operator, pcb_id=pcb,
                                    nombre=data['identity']['nombre'], at=now)
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
        now = time.time()
        c.execute('UPDATE stm32_stations SET last_seen=? WHERE id=?', (now, sid))
        # Never automatically repeat an interrupted flash operation.
        c.execute("UPDATE stm32_jobs SET state='unknown',updated=?,result=? WHERE station=? AND state='running' AND updated<?",
                  (now, json.dumps({'error': 'Agente interrumpido; comprobar la tarjeta antes de repetir.'}), sid, now-600))
        r = c.execute("SELECT * FROM stm32_jobs WHERE station=? AND state='queued' ORDER BY created LIMIT 1", (sid,)).fetchone()
        if not r:
            return None
        d = json.loads(r['payload'])
        try:
            current, _ = preview(r['pcb'], c)
            if current['hex_sha256'] != d['hex_sha256'] or now-r['created']>120:
                raise ValueError('Trabajo caducado o datos del inventario modificados; vuelve a preparar la tarjeta.')
        except ValueError as e:
            c.execute("UPDATE stm32_jobs SET state='failed',result=?,updated=? WHERE id=?", (json.dumps({'error': str(e)}), now, r['id']))
            return None
        c.execute("UPDATE stm32_jobs SET state='running',updated=? WHERE id=?", (now, r['id']))
        return dict(id=r['id'], payload=d, hex=r['image'])


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
        if r and r['state'] in ('verified', 'failed') and json.loads(r['result']) == result:
            return dict(id=jid, state=r['state'])  # Lost HTTP acknowledgement: harmless retry.
        if not r or r['state'] not in ('running', 'unknown'):
            raise ValueError('El trabajo no pertenece a la estación o ya terminó.')
        p = json.loads(r['payload'])
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
        db.log_evento('STM32_PROGRAMACION', None, None, f"R1 PCB {r['pcb']} FW {p['identity']['fw']} {state}; job={jid}", r['operator'], conn=c)
    return job(jid)
