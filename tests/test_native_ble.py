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


if __name__ == '__main__': unittest.main()
