"""Persistent R2 verification jobs. Agents receive identity, never the unit secret."""
import hashlib
import json
import secrets
import time
from app.database import db, inventario as inv
from app.services import esp32_firmware as fw

ACTIVE = ('flashing','queued','running')
TTL = 600

def ensure(c):
    fw.ensure(c)
    c.execute('''CREATE TABLE IF NOT EXISTS r2_programming_attempts (
        id TEXT PRIMARY KEY, pcb INTEGER NOT NULL, firmware TEXT NOT NULL,
        station TEXT NOT NULL, operator TEXT NOT NULL, method TEXT NOT NULL,
        state TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL,
        expected TEXT NOT NULL, result TEXT, error TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS r2_programming_state (
        pcb INTEGER PRIMARY KEY, method TEXT NOT NULL, programmed_at REAL NOT NULL,
        verified_at REAL NOT NULL, firmware TEXT NOT NULL, hw TEXT NOT NULL,
        app_sha256 TEXT NOT NULL, validation TEXT NOT NULL)''')
    if not any(r[1]=='mac' for r in c.execute('PRAGMA table_info(r2_programming_state)')):
        c.execute('ALTER TABLE r2_programming_state ADD COLUMN mac TEXT')
    c.execute('''CREATE TABLE IF NOT EXISTS r2_agent_presence (
        station TEXT PRIMARY KEY, seen REAL NOT NULL, available INTEGER NOT NULL)''')
    c.execute("UPDATE r2_programming_attempts SET state='error',error='Verificación interrumpida o vencida.',updated=? WHERE state IN ('flashing','queued','running') AND created<?",(time.time(),time.time()-TTL))

def record(c,pcb,method,info,validation='ble'):
    ensure(c)
    now=time.time()
    # A read-only verification updates verified_at, not the installation date/method.
    prior=c.execute('SELECT * FROM r2_programming_state WHERE pcb=?',(pcb['id'],)).fetchone()
    installed=(prior['programmed_at'] if prior else 0) if method=='verify' else now
    method=prior['method'] if method=='verify' and prior else method
    c.execute('INSERT OR REPLACE INTO r2_programming_state(pcb,method,programmed_at,verified_at,firmware,hw,app_sha256,validation,mac) VALUES(?,?,?,?,?,?,?,?,?)',
              (pcb['id'],method,installed,now,info['fw'],info['hw'],info.get('app_sha256',''),validation,pcb['mac']))

def statuses():
    with db.transaction() as c:
        ensure(c)
        catalogue=fw.rows(c)
        latest={}
        for row in catalogue: latest.setdefault(row['hw'].replace('.',''),row['fw'])
        states={r['pcb']:dict(r) for r in c.execute('SELECT * FROM r2_programming_state')}
        explicit=set(states)
        if c.execute("SELECT 1 FROM sqlite_master WHERE name='esp32_ota_jobs'").fetchone():
            for r in c.execute("SELECT pcb,payload FROM esp32_ota_jobs WHERE state='verified' ORDER BY created"):
                if r['pcb'] not in explicit:
                    p=json.loads(r['payload'])
                    states[r['pcb']]=dict(firmware=p['fw'],hw=p['hw'],validation='ble_ota',method='ble_ota',
                                          programmed_at=None,verified_at=0,app_sha256=p['app_sha256'],mac=p['mac'])
        jobs={}
        for r in c.execute('SELECT pcb,state,error,updated FROM r2_programming_attempts ORDER BY created'): jobs[r['pcb']]=dict(r)
        result=[]
        for p in c.execute("SELECT id,version,firmware,mac FROM pcb_inventario WHERE tipo='R2'"):
            evidence=states.get(p['id']); job=jobs.get(p['id']) or {}
            current=p['firmware']; newest=latest.get(p['version'])
            verified=bool(evidence and evidence['firmware']==current and p['mac'] and
                          evidence.get('mac') and evidence['mac'].upper()==p['mac'].upper() and evidence['hw'].replace('.','')==p['version'])
            state='updated' if verified and current==newest else 'outdated' if verified else 'unprogrammed'
            if job.get('state')=='error' and job.get('updated',0)>(evidence or {}).get('verified_at',0): state='error'
            if job.get('state') in ACTIVE: state='busy'
            result.append(dict(pcb_id=p['id'],state=state,installed_fw=current,latest_fw=newest,
                               verified=verified,error=job.get('error'),evidence=evidence))
        return dict(items=result)

def start(pcb_id,firmware_id,station,operator,method='serial'):
    from app.services import esp32_ota as ota
    with db.transaction() as c:
        ensure(c)
        p=inv.get_pcb(pcb_id,conn=c)
        if not p or p['tipo']!='R2': raise ValueError('Elige una R2.')
        if c.execute("SELECT 1 FROM sqlite_master WHERE name='android_offline_grants'").fetchone():
            if c.execute("SELECT 1 FROM android_offline_grants WHERE target_pcb=? AND state IN ('authorized','pending_verification') AND expires_at>?",(pcb_id,time.time())).fetchone():
                raise ValueError('La R2 tiene un paquete offline pendiente; ciérralo o verifica su resultado primero.')
        if method=='verify' and not p.get('mac'): raise ValueError('Primero instala por serial y lee la MAC.')
        if c.execute("SELECT 1 FROM sqlite_master WHERE name='esp32_ota_jobs'").fetchone():
            if c.execute("SELECT 1 FROM esp32_ota_jobs WHERE pcb=? AND state='prepared' AND created>?",(pcb_id,time.time()-3600)).fetchone():
                raise ValueError('La R2 tiene una OTA pendiente; verifícala o cancélala primero.')
        for table in ('stm32_jobs','tqt_test_runs'):
            if c.execute("SELECT 1 FROM sqlite_master WHERE name=?",(table,)).fetchone():
                if c.execute('SELECT 1 FROM '+table+" WHERE station=? AND state IN ('queued','running')",(station,)).fetchone():
                    raise ValueError('La estación tiene una programación o prueba física activa.')
        if c.execute("SELECT 1 FROM sqlite_master WHERE name='tqt_test_commands'").fetchone():
            if c.execute("SELECT 1 FROM tqt_test_commands WHERE station=? AND state IN ('queued','running')",(station,)).fetchone():
                raise ValueError('La estación ejecuta un comando de prueba; espera a que termine.')
        presence=c.execute('SELECT * FROM r2_agent_presence WHERE station=?',(station,)).fetchone()
        if not presence or time.time()-presence['seen']>20 or not presence['available']:
            raise ValueError('Inicia o actualiza el agente Windows de esta laptop para verificar R2 automáticamente.')
        if c.execute("SELECT 1 FROM r2_programming_attempts WHERE (pcb=? OR station=?) AND state IN ('flashing','queued','running')",(pcb_id,station)).fetchone():
            raise ValueError('La tarjeta o estación ya está verificando una R2.')
        row=next((r for r in fw.rows(c,p['version']) if r['id']==firmware_id),None)
        key=c.execute('SELECT secret FROM esp32_unit_keys WHERE pcb=?',(pcb_id,)).fetchone()
        if not row or not key: raise ValueError('Prepara primero el firmware personalizado desde esta web.')
        raw=bytes(row['image'])
        if hashlib.sha256(raw).hexdigest()!=row['sha256']: raise ValueError('Firmware guardado alterado.')
        template,_,_=fw.inspect(raw)
        image,meta=fw.personalize(raw,p['nombre'] if template.get('exact_name') else p['nombre'].replace('-','_'),bytes(key['secret']))
        if not meta['ota_protocol']: raise ValueError('Este firmware antiguo no admite verificación BLE autenticada. Elige la base OTA o 4.1+.')
        _,_,layout=fw.inspect(image)
        expected=dict(nombre=meta['nombre'],fw=meta['fw'],hw=meta['hw'],app_sha256=image[layout['end']-32:layout['end']].hex(),mac=p.get('mac'))
        identifier=secrets.token_hex(12); now=time.time()
        c.execute('INSERT INTO r2_programming_attempts VALUES(?,?,?,?,?,?,?,?,?,?,NULL,NULL)',
                  (identifier,pcb_id,firmware_id,station,operator,method,'flashing' if method=='serial' else 'queued',now,now,json.dumps(expected)))
        return dict(id=identifier,state='flashing' if method=='serial' else 'queued')

def get(identifier,operator):
    with db.transaction() as c:
        ensure(c)
        r=c.execute('SELECT * FROM r2_programming_attempts WHERE id=? AND operator=?',(identifier,operator)).fetchone()
        if not r: raise ValueError('Verificación no encontrada.')
        return dict(id=r['id'],state=r['state'],error=r['error'],result=json.loads(r['result']) if r['result'] else None)

def ready(identifier,operator,mac):
    from app.services.esp32_ota import mac as parse_mac
    parse_mac(mac)
    with db.transaction() as c:
        ensure(c)
        r=c.execute('SELECT * FROM r2_programming_attempts WHERE id=? AND operator=?',(identifier,operator)).fetchone()
        if not r or r['state']!='flashing': raise ValueError('La instalación no está esperando verificación.')
        expected=json.loads(r['expected'])
        if expected['mac'] and expected['mac'].upper()!=mac.upper(): raise ValueError('La MAC difiere del inventario; no se reemplazó ninguna unidad.')
        expected['mac']=mac.upper()
        c.execute("UPDATE r2_programming_attempts SET state='queued',expected=?,updated=? WHERE id=?",(json.dumps(expected),time.time(),identifier))
    return dict(id=identifier,state='queued')

def fail(identifier,operator,error):
    with db.transaction() as c:
        ensure(c)
        c.execute("UPDATE r2_programming_attempts SET state='error',error=?,updated=? WHERE id=? AND operator=? AND state IN ('flashing','queued','running')",(error[:1000],time.time(),identifier,operator))
    return get(identifier,operator)

def claim(station,available):
    with db.transaction() as c:
        ensure(c)
        c.execute('INSERT OR REPLACE INTO r2_agent_presence VALUES(?,?,?)',(station,time.time(),int(available)))
        if not available: return None
        r=c.execute("SELECT * FROM r2_programming_attempts WHERE station=? AND state='queued' ORDER BY created LIMIT 1",(station,)).fetchone()
        if not r: return None
        c.execute("UPDATE r2_programming_attempts SET state='running',updated=? WHERE id=?",(time.time(),r['id']))
        return dict(id=r['id'],accion='verificar_r2',**json.loads(r['expected']))

def finish(station,identifier,body):
    from app.services import esp32_ota as ota
    with db.transaction() as c:
        ensure(c)
        r=c.execute('SELECT * FROM r2_programming_attempts WHERE id=? AND station=?',(identifier,station)).fetchone()
        if not r: raise ValueError('Verificación ajena o inexistente.')
        if r['state']=='verified': return json.loads(r['result'])
        if r['state']!='running': raise ValueError('La verificación ya terminó o venció.')
        error=body.get('error') or ''; result=None
        try:
            if not body.get('ok'): raise ValueError(error or 'No se pudo comunicar con R2 por Bluetooth.')
            info=body.get('info') or {}; expected=json.loads(r['expected'])
            p=inv.get_pcb(r['pcb'],conn=c)
            # Expected serial MAC is provisional and is not written until all checks pass.
            target=dict(p,mac=expected['mac'])
            key=c.execute('SELECT secret FROM esp32_unit_keys WHERE pcb=?',(r['pcb'],)).fetchone()
            if not key: raise ValueError('No existe credencial de esta unidad.')
            ota.verify_info(info,bytes(key['secret']),target)
            for old in c.execute("SELECT result FROM r2_programming_attempts WHERE pcb=? AND state='verified' AND id!=?",(p['id'],identifier)):
                if json.loads(old['result']).get('nonce')==info['nonce']:
                    raise ValueError('INFO ya usado; vuelve a conectar la R2 para una lectura nueva.')
            if any(info.get(k)!=expected[k] for k in ('nombre','fw','hw','app_sha256')):
                raise ValueError('El firmware instalado no coincide con el que se grabó.')
            if (body.get('address') or '').upper()!=expected['mac'].upper(): raise ValueError('La MAC observada por Bluetooth no coincide.')
            updated=inv.guardar_programacion(p['id'],info['mac'],info['fw'],r['operator'],conn=c)
            record(c,updated,r['method'],info)
            result=dict(verified=True,pcb=updated,fw=info['fw'],hw=info['hw'],method=r['method'],nonce=info['nonce'])
        except (ValueError,TypeError,KeyError) as exc:
            error=str(exc)[:1000]
        c.execute('UPDATE r2_programming_attempts SET state=?,result=?,error=?,updated=? WHERE id=?',
                  ('verified' if result else 'error',json.dumps(result) if result else None,None if result else error,time.time(),identifier))
        db.log_evento('R2_VERIFICADA' if result else 'R2_VERIFICACION_ERROR',None,None,f'pcb={r["pcb"]}; metodo={r["method"]}; intento={identifier}; '+('OK' if result else error),r['operator'],conn=c)
        return result or dict(verified=False,error=error)
