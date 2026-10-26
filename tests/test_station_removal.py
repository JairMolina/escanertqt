import _aislamiento as iso
import json
import secrets
import time
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.database import db
from app.main import app
from app.services import stm32_programming as stm, test_station as tests, native_ble as ble
from app.services import r2_programming as r2, usuarios


class RemovalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init_db()
        ble.init()
        with db.get_db() as c:
            r2.ensure(c)

    def setUp(self):
        self.op = 'station-owner@test.mx'
        self.st = stm.station_create('Banco de pruebas', self.op)
        self.sid = self.st['id']
        self.card = iso.crear_par(iso.nuevo_lote()['id'])
        stm.claim(self.sid)

    def tearDown(self):
        with db.get_db() as c:
            c.execute("UPDATE stm32_jobs SET state='failed' WHERE station=?", (self.sid,))
            c.execute("UPDATE tqt_test_runs SET state='interrupted' WHERE requested_card=?", (self.card['id'],))
            c.execute("UPDATE tqt_test_commands SET state='error' WHERE station=?", (self.sid,))
            c.execute("UPDATE r2_programming_attempts SET state='error' WHERE station=?", (self.sid,))

    def remove(self):
        return stm.revoke_stations([self.sid], self.op)

    def insert_run(self, sid=None, state='finished'):
        rid = secrets.token_hex(16)
        with db.get_db() as c:
            c.execute('INSERT INTO tqt_test_runs(id,station,requested_card,operator,state,created,updated,inventory) VALUES(?,?,?,?,?,?,?,?)',
                      (rid, sid or self.sid, self.card['id'], self.op, state, time.time(), time.time(), '{}'))
        return rid

    def test_preserves_history_audit_and_browser_station(self):
        rid = self.insert_run()
        with db.get_db() as c:
            logical = tests.web_station(c, self.op)
        result = self.remove()
        self.assertTrue(result['history_preserved'])
        self.assertNotIn(self.sid, [x['id'] for x in stm.stations()])
        with db.get_db() as c:
            row = c.execute('SELECT * FROM stm32_stations WHERE id=?', (self.sid,)).fetchone()
            self.assertEqual(row['revoked_by'], self.op)
            self.assertIsNotNone(row['revoked_at'])
            self.assertEqual(c.execute('SELECT station FROM tqt_test_runs WHERE id=?', (rid,)).fetchone()[0], self.sid)
            self.assertIsNone(c.execute('SELECT revoked_at FROM stm32_stations WHERE id=?', (logical,)).fetchone()[0])
            self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(), [])
        self.assertEqual(self.remove(), result)  # repeat removal is harmless
        with self.assertRaises(stm.StationRevokedError): stm.station_auth(self.st['token'])
        with self.assertRaises(stm.StationRevokedError): stm.claim(self.sid)
        with self.assertRaises(stm.StationRevokedError): tests.claim(self.sid, {})
        with self.assertRaises(stm.StationRevokedError): stm.create_job(self.card['r1']['id'], self.sid, '0'*64, self.op, True)
        with self.assertRaises(stm.StationRemovalError): stm.revoke_stations([logical], self.op, True)

    def test_permissions_and_atomic_bulk(self):
        other = stm.station_create('Otro', 'other@test.mx')['id']
        with self.assertRaises(stm.StationRemovalError) as e:
            stm.revoke_stations([self.sid, other], self.op)
        self.assertEqual(e.exception.status, 403)
        self.assertEqual(stm.station_auth(self.st['token'])['id'], self.sid)
        stm.revoke_stations([other], self.op, True)
        with self.assertRaises(stm.StationRemovalError) as e:
            stm.revoke_stations(['f'*24], self.op, True)
        self.assertEqual(e.exception.status, 404)

    def test_refuses_programming_test_command_and_r2(self):
        with db.get_db() as c:
            c.execute('INSERT INTO stm32_jobs VALUES(?,?,?,?,?,?,?,?,?,NULL)',
                      ('busy-'+self.sid, self.sid, self.card['r1']['id'], 'running', time.time(), time.time(), self.op, '{}', ''))
        with self.assertRaises(stm.StationRemovalError) as e: self.remove()
        self.assertEqual(e.exception.status, 409)
        with db.get_db() as c: c.execute("UPDATE stm32_jobs SET state='failed' WHERE station=?", (self.sid,))
        rid = self.insert_run(state='running')
        with self.assertRaises(stm.StationRemovalError): self.remove()
        with db.get_db() as c:
            c.execute("UPDATE tqt_test_runs SET state='finished' WHERE id=?", (rid,))
            c.execute('INSERT INTO tqt_test_commands VALUES(?,?,?,?,?,?,NULL)', ('command-'+self.sid, self.sid, 'ble', '{}', 'running', time.time()))
        with self.assertRaises(stm.StationRemovalError): self.remove()
        with db.get_db() as c:
            c.execute("UPDATE tqt_test_commands SET state='done' WHERE station=?", (self.sid,))
            c.execute('INSERT INTO r2_programming_attempts VALUES(?,?,?,?,?,?,?,?,?,?,NULL,NULL)',
                      ('r2-'+self.sid, self.card['r2']['id'], 'test', self.sid, self.op, 'serial', 'flashing', time.time(), time.time(), '{}'))
        with self.assertRaises(stm.StationRemovalError): self.remove()

    def test_browser_run_reserves_ble_even_between_commands(self):
        with db.get_db() as c: logical = tests.web_station(c, self.op)
        rid = self.insert_run(logical, 'running')
        with db.get_db() as c:
            c.execute('INSERT INTO tqt_ble_leases VALUES(?,?,?,?,?,?)', (self.sid, 'lease', self.op, self.card['id'], rid, time.time()))
        with self.assertRaises(stm.StationRemovalError): self.remove()

    def test_stale_command_and_presence_cannot_resurrect_agent(self):
        with db.get_db() as c:
            c.execute('INSERT INTO tqt_test_commands VALUES(?,?,?,?,?,?,NULL)', ('old-'+self.sid, self.sid, 'ble', '{}', 'queued', time.time()-181))
            c.execute('INSERT OR REPLACE INTO tqt_test_presence VALUES(?,?,?)', (self.sid, time.time(), json.dumps(dict(ble_bridge=1))))
            c.execute('INSERT OR REPLACE INTO r2_agent_presence VALUES(?,?,?)', (self.sid, time.time(), 1))
        self.remove()
        self.assertNotIn(self.sid, [r['id'] for r in ble.stations(self.op)])
        with self.assertRaises(stm.StationRevokedError):
            ble.prepare(self.op, dict(station_id=self.sid, operation='scan', role='R1', request_id='x'))
        with db.get_db() as c:
            self.assertEqual(c.execute('SELECT state FROM tqt_test_commands WHERE id=?', ('old-'+self.sid,)).fetchone()[0], 'error')
            self.assertIsNone(c.execute('SELECT * FROM r2_agent_presence WHERE station=?', (self.sid,)).fetchone())

    def test_http_delete_owner_admin_and_revoked_token(self):
        client = TestClient(app, base_url='https://testserver')
        url = '/api/stm32/stations/'+self.sid
        anon = iso.cliente_sin_sesion(app)
        self.assertEqual(anon.delete(url).status_code, 401)
        with patch.object(usuarios, 'validar_sesion', return_value=dict(email='other@test.mx', rol='operador', debe_cambiar=False, modulos=['escaner-tqt'])):
            self.assertEqual(client.delete(url).status_code, 403)
        with patch.object(usuarios, 'validar_sesion', return_value=dict(email=self.op, rol='operador', debe_cambiar=False, modulos=['escaner-tqt'])):
            listed = client.get('/api/stm32/stations').json()
            row = next(r for r in listed if r['id']==self.sid)
            self.assertEqual(row['owner'], self.op)
            self.assertTrue(row['can_delete'])
            self.assertEqual(client.delete(url).status_code, 200)
        r = anon.post('/api/stm32/agent/claim', json={}, headers={'Authorization':'Bearer '+self.st['token']})
        self.assertEqual(r.status_code, 410)
        self.assertEqual(anon.post('/api/stm32/agent/claim', json={}, headers={'Authorization':'Bearer wrong'}).status_code, 401)

    def test_account_label_and_actual_operator_are_separate(self):
        self.assertEqual(self.st['owner'], self.op)
        self.assertTrue(self.st['name'].startswith('station-owner · '))
        preview, _ = stm.preview(self.card['r1']['id'])
        job = stm.create_job(self.card['r1']['id'], self.sid, preview['hex_sha256'], 'different-user@test.mx', True)
        self.assertEqual(job['operator'], 'different-user@test.mx')
        self.assertEqual(job['payload']['agent']['registered_by'], self.op)
        self.assertEqual(job['payload']['agent']['id'], self.sid)
        rid = self.insert_run()
        with db.get_db() as c:
            c.execute('UPDATE tqt_test_runs SET operator=? WHERE id=?', ('different-user@test.mx', rid))
            c.execute("UPDATE stm32_jobs SET state='failed' WHERE id=?", (job['id'],))
        self.remove()
        historical = tests.read(rid)
        self.assertEqual(historical['operator'], 'different-user@test.mx')
        self.assertEqual(historical['station_owner'], self.op)

    def test_installer_identity_is_session_owned_and_revocation_stops_new_agent(self):
        from app.routers.stm32 import station_archive
        import io, zipfile, sys, urllib.error
        from pathlib import Path
        from app.services import tqt_hex
        sys.modules['tqt_hex'] = tqt_hex
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'station'))
        import agent
        with zipfile.ZipFile(io.BytesIO(station_archive(self.st, 'https://testserver'))) as z:
            cfg = json.loads(z.read('config.json'))
        self.assertEqual(cfg['registered_by'], self.op)
        self.assertEqual(cfg['name'], self.st['name'])
        with patch.object(agent.urllib.request, 'urlopen', side_effect=urllib.error.HTTPError('https://testserver', 410, 'Gone', {}, None)):
            with self.assertRaises(agent.StationRevokedError): agent.api_response(None)
        with patch.object(agent.urllib.request, 'urlopen', side_effect=urllib.error.HTTPError('https://testserver', 503, 'Unavailable', {}, None)):
            with self.assertRaises(urllib.error.HTTPError): agent.api_response(None)


class MigrationTests(unittest.TestCase):
    def test_legacy_migration_waits_for_writer_and_is_repeatable(self):
        import sqlite3, tempfile, threading
        from pathlib import Path
        original = db.get_db
        transaction = db.transaction
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'legacy.db'
            with sqlite3.connect(path) as c:
                c.execute('PRAGMA journal_mode=WAL')
                c.execute('CREATE TABLE stm32_stations(id TEXT PRIMARY KEY,name TEXT NOT NULL,token_hash TEXT NOT NULL,owner TEXT NOT NULL,last_seen REAL NOT NULL DEFAULT 0)')
                c.execute('INSERT INTO stm32_stations VALUES(?,?,?,?,?)', ('a'*24, 'Legacy', 'hash', 'owner@test.mx', 0))
            writer = sqlite3.connect(path, check_same_thread=False)
            writer.execute('BEGIN IMMEDIATE')
            writer.execute('UPDATE stm32_stations SET last_seen=1')
            release = threading.Timer(0.2, writer.commit)
            release.start()
            try:
                with patch.object(db, 'get_db', side_effect=lambda: original(path)), patch.object(db, 'transaction', side_effect=lambda: transaction(path)), patch.object(stm.catalogue, 'ensure'):
                    stm.init()
                    stm.init()
                with sqlite3.connect(path) as c:
                    cols = {r[1] for r in c.execute('PRAGMA table_info(stm32_stations)')}
                    self.assertTrue({'revoked_at', 'revoked_by'} <= cols)
                    self.assertEqual(c.execute('SELECT last_seen,revoked_at FROM stm32_stations').fetchone(), (1, None))
            finally:
                release.join()
                writer.close()
