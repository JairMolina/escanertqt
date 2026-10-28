import _aislamiento as iso
import json
import secrets
import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from app.database import db
from app.services import test_station as runs, stm32_programming as stm, native_ble as svc

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'station/test_station'))
from tqtstation.native_ble import execute


def s29(d):
    values = {k: '0' for k in runs.S29_FIELDS}
    values.update(MAC=d['mac_r1'], MACR=d['mac_r2'], ID=d['r1_serie'], HW='3.0', VER='4.3')
    return 'AT$POST=1,0,"S29|' + '|'.join(k+':'+values[k] for k in runs.S29_FIELDS) + '"'


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.op = 'ble-operator@test.mx'
        self.card = iso.crear_par(iso.nuevo_lote()['id'])
        self.station = stm.station_create('Solo BLE prueba', self.op)['id']
        svc.init()
        runs.claim(self.station, dict(ble_bridge=1, ble_only=True, serial_connected=False, running=False))
        with db.get_db() as c:
            self.d = runs.snapshot(self.card['id'], c)

    def body(self, **over):
        return dict(station_id=self.station, tarjeta_id=self.card['id'], run_id=None,
                    request_id=secrets.token_hex(16), operation='connect', role='R1', mac=self.d['mac_r1'], **over)

    def claim(self, b):
        job = svc.prepare(self.op, b)
        runs.claim(self.station, dict(ble_bridge=1, serial_connected=False))
        return job['id']

    def tearDown(self):
        with db.get_db() as c:
            c.execute("UPDATE tqt_test_runs SET state='interrupted' WHERE state='running'")

    def test_owner_mac_and_unsupported_station_rejected(self):
        b = self.body()
        with self.assertRaisesRegex(ValueError, 'operador'): svc.prepare('other@test.mx', b)
        b['mac'] = '00:00:00:00:00:99'
        with self.assertRaisesRegex(ValueError, 'MAC'): svc.prepare(self.op, b)
        runs.claim(self.station, dict(ble_bridge=1, serial_connected=True))
        with self.assertRaisesRegex(ValueError, 'serial'): svc.prepare(self.op, self.body())

    def test_once_only_and_idempotent_submission(self):
        b = self.body(); jid = self.claim(b)
        self.assertEqual(svc.prepare(self.op, b)['id'], jid)
        self.assertEqual(svc.authorize(self.station, jid)['address'], svc.mac(self.d['mac_r1']))
        with self.assertRaisesRegex(ValueError, 'vencido'): svc.authorize(self.station, jid)
        with self.assertRaises(ValueError): svc.result('other@test.mx', jid)

    def test_cancel_and_expiration_block_execution(self):
        r = runs.web_create(self.card['id'], self.op)
        b = self.body(); b['run_id'] = r['id']; jid = self.claim(b)
        with db.get_db() as c: c.execute('UPDATE tqt_test_runs SET cancel=1 WHERE id=?', (r['id'],))
        with self.assertRaisesRegex(ValueError, 'cancelada'): svc.authorize(self.station, jid)
        with db.get_db() as c:
            row = c.execute('SELECT body FROM tqt_test_commands WHERE id=?', (jid,)).fetchone()
            p = json.loads(row['body']); p['deadline'] = time.time()-1
            c.execute('UPDATE tqt_test_commands SET body=? WHERE id=?', (json.dumps(p), jid))
        with self.assertRaisesRegex(ValueError, 'vencido'): svc.authorize(self.station, jid)

    def test_send_requires_pair_evidence(self):
        b = self.body(); b.update(operation='send', command='PPON', status_raw='')
        with self.assertRaisesRegex(ValueError, 'S29'): svc.prepare(self.op, b)
        b['status_raw'] = s29(self.d)
        jid = self.claim(b)
        self.assertEqual(svc.authorize(self.station, jid)['command'], 'PPON')

    def test_native_connections_come_from_authenticated_agent_results(self):
        r = runs.web_create(self.card['id'], self.op)
        b = self.body(); b['run_id'] = r['id']; jid = self.claim(b)
        with db.get_db() as c: self.assertEqual(svc.connections(c, r['id']), {})
        svc.authorize(self.station, jid)
        with db.get_db() as c:
            c.execute("UPDATE tqt_test_commands SET state='done',result=? WHERE id=?", (json.dumps(dict(ok=True,data=dict(address=self.d['mac_r1'],name='Nombre_antiguo'))), jid))
            self.assertEqual(svc.connections(c, r['id']), {'R1': svc.mac(self.d['mac_r1'])})

    def test_agent_adapter_uses_mac_not_name_and_never_serial(self):
        events = []
        class Ble:
            address = ''
            def scan(self, target): return [SimpleNamespace(name='Firmware viejo', address=target)]
            def connect(self, address): self.address = address; events.append(('connect', address))
            def send(self, command): events.append(('send', command))
            def disconnect(self): self.address = ''; events.append(('disconnect',))
        ble = Ble()
        payload = dict(operation='connect',address=self.d['mac_r1'],command=None,deadline=time.time()+20)
        self.assertEqual(execute(ble, lambda: payload)['name'], 'Firmware viejo')
        payload.update(operation='send', command='PPON')
        execute(ble, lambda: payload)
        payload['address'] = '00:00:00:00:00:99'
        with self.assertRaisesRegex(ValueError, 'otra MAC'): execute(ble, lambda: payload)
        self.assertEqual(events[-1], ('send', 'PPON'))

    # v1.4.64: «Elegir dispositivo» — escaneo sin MAC ni tarjeta, solo con el puente propio.
    def test_scan_without_mac_role_or_card_and_owner_enforced(self):
        b = dict(station_id=self.station, request_id=secrets.token_hex(16), operation='scan')
        with self.assertRaisesRegex(ValueError, 'operador'): svc.prepare('other@test.mx', dict(b))
        jid = self.claim(b)
        auth = svc.authorize(self.station, jid)
        self.assertEqual((auth['operation'], auth['address']), ('scan', None))
        with self.assertRaises(ValueError): svc.result('other@test.mx', jid)
        nb = dict(b, request_id=secrets.token_hex(16), operation='connect')
        with self.assertRaisesRegex(ValueError, 'inválida|tarjeta'): svc.prepare(self.op, nb)

    def test_connect_still_requires_inventory_mac(self):
        b = self.body(); b['mac'] = 'AA:BB:CC:DD:EE:FF'
        with self.assertRaisesRegex(ValueError, 'inventario'): svc.prepare(self.op, b)

    def test_agent_scan_lists_named_devices_tqt_first(self):
        from tqtstation.ble import ordenar_escaneo
        lista = ordenar_escaneo([dict(name='Auriculares', address='A', rssi=-40),
                                 dict(name='TQT-R2', address='B', rssi=-80),
                                 dict(name='TQT-R1', address='C', rssi=-60)])
        self.assertEqual([d['address'] for d in lista], ['C', 'B', 'A'])
        class Ble:
            address = ''
            def scan_all(self): return lista
        payload = dict(operation='scan', address=None, command=None, deadline=time.time()+20)
        self.assertEqual(execute(Ble(), lambda: payload), lista)


class InstallerTests(unittest.TestCase):
    """v1.4.64: reinstalar conserva la estación (id/nombre/dueño) con token nuevo; .cmd autoextraíble; paquete OTA."""

    @classmethod
    def setUpClass(cls):
        from fastapi.testclient import TestClient
        from app.main import app
        from app.services import usuarios
        cls.client = TestClient(app, base_url='https://testserver')
        cls.op = usuarios.validar_sesion(iso._token_pruebas())['email']

    def post(self, **body):
        return self.client.post('/api/validacion/tqt/installer', json=dict(name='Laptop', ble_only=True, **body))

    def test_reuse_own_station_rotates_token_and_keeps_id(self):
        import io, zipfile
        st = stm.station_create('Mi laptop', self.op.upper())
        r = self.post(station_id=st['id'])
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers['X-TQT-Station'], st['id'])
        cfg = json.loads(zipfile.ZipFile(io.BytesIO(r.content)).read('config.json'))
        self.assertEqual((cfg['id'], cfg['name'], cfg['owner']), (st['id'], st['name'], st['owner']))
        self.assertNotEqual(cfg['token'], st['token'])
        # el instalador anterior sigue valiendo (descargado antes, abierto después) y el nuevo también
        self.assertEqual(stm.station_auth(st['token'])['id'], st['id'])
        self.assertEqual(stm.station_auth(cfg['token'])['id'], st['id'])
        stm.revoke_stations([st['id']], self.op, administrator=True)
        for tk in (st['token'], cfg['token']):
            with self.assertRaises(Exception): stm.station_auth(tk)   # revocar invalida todos

    def test_install_progress_y_estado(self):
        st = stm.station_create('Progreso', self.op)
        h = {'Authorization': 'Bearer ' + st['token']}
        self.assertEqual(self.client.post('/api/stm32/agent/tests/install-progress', json={'etapa': 'dependencias'}, headers=h).status_code, 200)
        self.assertEqual(self.client.post('/api/stm32/agent/tests/install-progress', json={'etapa': 'otra'}, headers=h).status_code, 422)
        e = self.client.get('/api/validacion/tqt/installer/' + st['id'] + '/estado').json()
        self.assertEqual((e['etapa'], e['online'], e['listo']), ('dependencias', False, False))
        ajena = stm.station_create('Ajena', 'otra-cuenta@test.mx')
        self.assertNotEqual(self.client.get('/api/validacion/tqt/installer/' + ajena['id'] + '/estado').status_code, 200)

    def test_foreign_or_revoked_station_creates_new(self):
        ajena = stm.station_create('Ajena', 'otra-cuenta@test.mx')
        r = self.post(station_id=ajena['id'])
        self.assertNotEqual(r.headers['X-TQT-Station'], ajena['id'])
        self.assertEqual(stm.station_auth(ajena['token'])['id'], ajena['id'])   # su token no se tocó
        propia = stm.station_create('Revocada', self.op)
        stm.revoke_stations([propia['id']], self.op)
        self.assertNotEqual(self.post(station_id=propia['id']).headers['X-TQT-Station'], propia['id'])
        self.assertEqual(len(self.post().headers['X-TQT-Station']), 24)

    def test_cmd_format_embeds_zip_with_config(self):
        import io, zipfile
        from app.services import instalador_windows as iw
        r = self.post(formato='cmd')
        self.assertEqual(r.status_code, 200)
        self.assertIn('TQT_Puente_Bluetooth.cmd', r.headers['content-disposition'])
        self.assertTrue(r.headers['content-type'].startswith('application/octet-stream'))
        self.assertTrue(r.content.startswith(b'@echo off\r\n'))
        self.assertNotIn(b'\n', r.content.replace(b'\r\n', b''))
        self.assertIn(b'::TQT_ZIP_BASE64\r\n', r.content)
        z = zipfile.ZipFile(io.BytesIO(iw.extraer_zip(r.content)))
        cfg = json.loads(z.read('config.json'))
        self.assertEqual(cfg['id'], r.headers['X-TQT-Station'])
        self.assertTrue(cfg['ble_only'])
        self.assertIn('agent.py', z.namelist())
        ps = iw.script_ps(r.content)
        self.assertIn(r'TQT\PuenteBluetooth', ps)
        self.assertNotIn(cfg['token'], ps)   # el token solo viaja dentro de config.json
        self.assertIn('TQT_Agente_Pruebas.cmd', self.client.post('/api/validacion/tqt/installer', json=dict(
            formato='cmd')).headers['content-disposition'])

    def test_claim_announces_version_and_package_has_no_config(self):
        import io, zipfile
        st = stm.station_create('OTA', self.op)
        h = {'Authorization': 'Bearer ' + st['token']}
        r = self.client.post('/api/stm32/agent/tests/claim', json=dict(ble_bridge=1, ble_only=True), headers=h)
        self.assertEqual(r.json()['agent_version'], runs.agente_actual())
        self.assertEqual(runs.agente_actual(), '1.4.64')
        p = self.client.get('/api/stm32/agent/tests/package', headers=h)
        self.assertEqual(p.status_code, 200)
        names = zipfile.ZipFile(io.BytesIO(p.content)).namelist()
        self.assertIn('agent.py', names)
        self.assertNotIn('config.json', names)
        self.assertFalse(any(n.startswith('tests/') for n in names))
        self.assertEqual(self.client.get('/api/stm32/agent/tests/package').status_code, 401)

    def test_http_scan_accepts_missing_mac_and_rejects_other_account(self):
        mine = stm.station_create('Puente', self.op)['id']
        runs.claim(mine, dict(ble_bridge=1, ble_only=True, serial_connected=False, running=False))
        body = dict(station_id=mine, request_id=secrets.token_hex(16), operation='scan')
        self.assertEqual(self.client.post('/api/validacion/tqt/web/ble/commands', json=body).status_code, 200)
        other = stm.station_create('Ajeno', 'otra-cuenta@test.mx')['id']
        runs.claim(other, dict(ble_bridge=1, ble_only=True, serial_connected=False, running=False))
        r = self.client.post('/api/validacion/tqt/web/ble/commands', json=dict(body, station_id=other, request_id=secrets.token_hex(16)))
        self.assertEqual(r.status_code, 400)


if __name__ == '__main__': unittest.main()
