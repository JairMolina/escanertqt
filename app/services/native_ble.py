"""BLE-only Windows transport for the browser test engine; never owns the UART."""
import json
import re
import secrets
import time
from app.database import db
from app.services import test_station as tests


def init():
    tests.init()
    with db.get_db() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS tqt_ble_leases(
            station TEXT PRIMARY KEY, id TEXT NOT NULL, operator TEXT NOT NULL,
            tarjeta INTEGER NOT NULL, run TEXT, updated REAL NOT NULL)''')


def mac(value):
    value = re.sub('[^0-9A-F]', '', str(value or '').upper())
    if not re.fullmatch('[0-9A-F]{12}', value):
        raise ValueError('MAC Bluetooth inválida.')
    return ':'.join(value[i:i+2] for i in range(0, 12, 2))


def stations(operator):
    init()
    with db.get_db() as c:
        return [dict(id=r['station'], name=r['name'], online=time.time()-r['seen'] < 15,
                     **json.loads(r['state'])) for r in c.execute(
            'SELECT p.*,s.name FROM tqt_test_presence p JOIN stm32_stations s ON s.id=p.station WHERE s.owner=? AND s.revoked_at IS NULL', (operator,))
            if json.loads(r['state']).get('ble_bridge') == 1]


def _inventory(c, operator, body, disconnect=False):
    jid = body.get('run_id')
    if jid:
        row = tests._web_row(c, jid, operator, states=())
        if not disconnect and (row['state'] != 'running' or row['cancel']):
            raise ValueError('Prueba cancelada o terminada; Bluetooth bloqueado.')
        return json.loads(row['inventory'])
    tid = body.get('tarjeta_id')
    if c.execute("SELECT 1 FROM tqt_test_runs WHERE requested_card=? AND state IN ('queued','running')", (tid,)).fetchone() and not disconnect:
        raise ValueError('Los controles manuales están bloqueados durante la prueba.')
    return tests.snapshot(tid, c)


def prepare(operator, body):
    init()
    sid, op, role = body['station_id'], body['operation'], body.get('role')
    identifier = body['request_id']
    if op not in ('scan', 'connect', 'send', 'disconnect') or role not in ('R1', 'R2'):
        raise ValueError('Operación Bluetooth inválida.')
    if op == 'send' and body.get('command') not in ('PPON', 'POFF'):
        raise ValueError('Comando Bluetooth no permitido.')
    with db.transaction() as c:
        station = tests.stm.require_station(c, sid)
        if not station or station['owner'] != operator:
            raise ValueError('El puente pertenece a otro operador.')
        p = c.execute('SELECT seen,state FROM tqt_test_presence WHERE station=?', (sid,)).fetchone()
        state = json.loads(p['state']) if p else {}
        if not p or time.time()-p['seen'] >= 15 or state.get('ble_bridge') != 1:
            raise ValueError('El puente Bluetooth Windows no está conectado o necesita actualizarse.')
        if state.get('serial_connected') or state.get('running'):
            raise ValueError('Ese agente está usando serial o una prueba propia; no se usa como puente BLE.')
        if c.execute("SELECT 1 FROM stm32_jobs WHERE station=? AND state IN ('queued','running')", (sid,)).fetchone():
            raise ValueError('La estación está programando firmware.')
        d = _inventory(c, operator, body, op == 'disconnect')
        address = mac(d['mac_r1' if role == 'R1' else 'mac_r2'])
        if body.get('mac') and mac(body['mac']) != address:
            raise ValueError('La MAC leída por serial no coincide con el inventario.')
        if op == 'send':
            status = tests.parse_s29(body.get('status_raw', ''))
            if not status or mac(status.get('MAC')) != mac(d['mac_r1']) or mac(status.get('MACR')) != mac(d['mac_r2']):
                raise ValueError('Se necesita evidencia S29 de la pareja correcta para mover por BLE.')
        old = c.execute('SELECT * FROM tqt_test_commands WHERE id=?', (identifier,)).fetchone()
        if old:
            previous = json.loads(old['body'])
            if old['station'] != sid or previous.get('operator') != operator or previous.get('request') != body:
                raise ValueError('Identificador de comando ya utilizado.')
            return {'id': identifier}
        lease = c.execute('SELECT * FROM tqt_ble_leases WHERE station=?', (sid,)).fetchone()
        if lease and time.time()-lease['updated'] < 180 and (lease['operator'] != operator or (lease['run'] and lease['run'] != body.get('run_id'))):
            active = c.execute("SELECT 1 FROM tqt_test_runs WHERE id=? AND state='running' AND cancel=0", (lease['run'],)).fetchone()
            if lease['operator'] != operator or active:
                raise ValueError('Bluetooth reservado por otra sesión.')
        if c.execute("SELECT 1 FROM tqt_test_commands WHERE station=? AND state IN ('queued','running') AND created>?", (sid, time.time()-90)).fetchone():
            raise ValueError('Hay un comando Bluetooth pendiente; no se repite.')
        lid = lease['id'] if lease and lease['operator'] == operator and lease['run'] == body.get('run_id') else secrets.token_hex(16)
        now = time.time()
        c.execute('INSERT OR REPLACE INTO tqt_ble_leases VALUES(?,?,?,?,?,?)',
                  (sid, lid, operator, d['id'], body.get('run_id'), now))
        payload = dict(request=body, operator=operator, lease=lid, address=address,
                       operation=op, role=role, command=body.get('command'),
                       deadline=now+(8 if op == 'send' else 45))
        c.execute('INSERT INTO tqt_test_commands VALUES(?,?,?,?,?,?,NULL)',
                  (identifier, sid, 'ble_bridge', json.dumps(payload), 'queued', now))
    return {'id': identifier}


def authorize(sid, identifier):
    """Called by the authenticated bridge immediately BEFORE native I/O, not by JS."""
    init()
    with db.transaction() as c:
        row = c.execute('SELECT * FROM tqt_test_commands WHERE id=? AND station=? AND action=?', (identifier, sid, 'ble_bridge')).fetchone()
        if not row or row['state'] != 'running':
            raise ValueError('Comando Bluetooth no activo.')
        payload = json.loads(row['body'])
        lease = c.execute('SELECT * FROM tqt_ble_leases WHERE station=?', (sid,)).fetchone()
        if not lease or lease['id'] != payload['lease'] or time.time() > payload['deadline'] or payload.get('authorized'):
            raise ValueError('Comando Bluetooth vencido; no se ejecuta.')
        d = _inventory(c, payload['operator'], payload['request'], payload['operation'] == 'disconnect')
        if mac(d['mac_r1' if payload['role'] == 'R1' else 'mac_r2']) != payload['address']:
            raise ValueError('El inventario cambió antes de ejecutar Bluetooth.')
        c.execute('UPDATE tqt_ble_leases SET updated=? WHERE station=?', (time.time(), sid))
        payload['authorized'] = time.time()
        c.execute('UPDATE tqt_test_commands SET body=? WHERE id=?', (json.dumps(payload), identifier))
        return {k: payload[k] for k in ('operation', 'address', 'command', 'role', 'deadline')}


def result(operator, identifier):
    init()
    with db.transaction() as c:
        r = c.execute('SELECT * FROM tqt_test_commands WHERE id=? AND action=?', (identifier, 'ble_bridge')).fetchone()
        if not r or json.loads(r['body'])['operator'] != operator:
            raise ValueError('Comando Bluetooth ajeno o inexistente.')
        if r['state'] == 'queued' and time.time() > json.loads(r['body'])['deadline']:
            message = dict(ok=False, error='El puente no atendió a tiempo; comando vencido sin ejecutar.')
            c.execute("UPDATE tqt_test_commands SET state='error',result=? WHERE id=?", (json.dumps(message), identifier))
            return dict(state='error', result=message)
        return dict(state=r['state'], result=json.loads(r['result']) if r['result'] else None)


def connections(c, jid):
    """Only native agent-authenticated results count as observed addresses; ignore JS claims."""
    found = {}
    for r in c.execute("SELECT body,result FROM tqt_test_commands WHERE action='ble_bridge' AND state='done' ORDER BY created"):
        p, res = json.loads(r['body']), json.loads(r['result'] or '{}')
        try:
            if p['request'].get('run_id') == jid and p['operation'] == 'connect' and p.get('authorized') and res.get('ok') and mac(res.get('data', {}).get('address')) == p['address']:
                found[p['role']] = p['address']
        except (ValueError, TypeError, AttributeError):
            continue
    return found
