import _aislamiento as iso
import hashlib
import hmac
import importlib
import json
import secrets
import sqlite3
import struct
import subprocess
import sys
import tempfile
import threading
import unittest
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from app.main import app
from app.database import db, inventario as inv
from app.services import android_ota as android, esp32_firmware as fw, esp32_ota as ota


def info(meta, key, mac, partition=0x10000):
    """Independent framing of the authenticated INFO emitted by the real FW."""
    value = dict(nombre=meta['nombre'], hw=meta['hw'], fw=meta['fw'], mac=mac,
                 ota_protocol=1, key_id=hashlib.sha256(key).hexdigest()[:16], nonce=secrets.token_hex(16),
                 app_sha256=meta['app_sha256'], boot_valid=True, partition=partition, chunk=180, name_format=2)
    payload = (b'TQT-OTA-INFO-v1' + bytes.fromhex(value['nonce']) + bytes.fromhex(value['app_sha256']) +
               value['nombre'].encode().ljust(24, b'\0') + value['hw'].encode().ljust(8, b'\0') +
               value['fw'].encode().ljust(16, b'\0') + bytes.fromhex(mac.replace(':', '')) +
               b'\x01' + struct.pack('<I', partition))
    value['proof'] = hmac.new(key, payload, hashlib.sha256).hexdigest()
    return value


class AndroidOtaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init_db()

    def setUp(self):
        self.operator = f'android-{uuid.uuid4().hex}@tqt.invalid'
        self.other = f'other-{uuid.uuid4().hex}@tqt.invalid'
        self.pcb = iso.crear_par(iso.nuevo_lote()['id'])['r2']
        self.pid = self.pcb['id']
        self.meta, self.image = fw.prepare(self.pid, 'base-R2-v42', True)
        self.meta['app_sha256'] = self.image[fw.inspect(self.image)[2]['end'] - 32:fw.inspect(self.image)[2]['end']].hex()
        with db.get_db() as c:
            self.key = bytes(c.execute('SELECT secret FROM esp32_unit_keys WHERE pcb=?', (self.pid,)).fetchone()[0])
        inv.set_firmware(self.pid, '4.1')
        self.pcb = inv.get_pcb(self.pid)
        self.before = info(self.meta, self.key, self.pcb['mac'])
        self.identifier = str(uuid.uuid4())

    def prepare(self, identifier=None):
        return android.prepare(identifier or self.identifier, self.pid, 'base-R2-v42', self.before, self.operator)

    def boot(self, prepared):
        return info(dict(nombre=prepared['nombre'], hw=prepared['hw'], fw=prepared['fw'],
                         app_sha256=prepared['app_sha256']), self.key, self.pcb['mac'], 0x150000)

    def report(self, **changes):
        body = dict(outcome='verified', device=self.boot(self.prepared['prepared']), error='')
        body.update(changes)
        return body

    def test_device_catalogue_is_paginated_linked_r2_only_and_no_private_key(self):
        found = android.devices(q=self.pcb['nombre'], limit=1, offset=0)
        self.assertEqual(found['total'], 1)
        item = found['items'][0]
        self.assertEqual((item['pcb_id'], item['hw'], item['mac'], item['tarjeta_id']),
                         (self.pid, '30', self.pcb['mac'], self.pcb['tarjeta_id']))
        self.assertFalse(item['capability']['offline'])
        self.assertTrue(item['capability']['continue_prepared_session'])
        self.assertIn('/firmwares?hw=30', item['links']['firmwares'])
        self.assertNotIn(self.key.hex(), json.dumps(found))
        self.assertEqual(android.devices(q=self.pcb['nombre'], limit=1, offset=1)['items'], [])
        with self.assertRaises(android.AndroidError):
            android.device(self.pid - 1)  # The R1 in this isolated pair.

    def test_prepare_uuid_is_idempotent_durable_and_does_not_export_unit_keys(self):
        first = self.prepare()
        importlib.reload(android)  # State must come from SQLite, not process memory.
        second = self.prepare()
        self.assertEqual(first, second)
        self.assertEqual(android.operation(self.identifier, self.operator)['prepared'], first['prepared'])
        # A separate interpreter opens the same isolated database after all
        # original connections have closed; no in-memory cache can satisfy it.
        process = subprocess.run([sys.executable, '-c',
            "import hashlib,json,sys; from app.config import settings; "
            "assert 'tqt_tests_' in str(settings.DB_PATH); "
            "from app.services import android_ota; "
            "v=android_ota.operation(sys.argv[1],sys.argv[2]); "
            "print(json.dumps({'state':v['state'],'prepared_hash':android_ota._digest(v['prepared'])}))",
            self.identifier, self.operator], capture_output=True, text=True, timeout=20, check=True)
        self.assertEqual(json.loads(process.stdout), dict(state='prepared', prepared_hash=android._digest(first['prepared'])))
        self.assertNotIn(self.key.hex(), json.dumps(first))
        self.assertEqual(len(android.history(self.operator)['items']), 1)
        with db.get_db() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM esp32_ota_jobs WHERE pcb=?', (self.pid,)).fetchone()[0], 1)
            self.assertEqual(c.execute('SELECT version FROM android_schema').fetchone()[0], 1)
            self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_uuid_cannot_be_reassigned_to_a_request_or_another_user(self):
        self.prepare()
        with self.assertRaises(android.AndroidError) as changed:
            android.prepare(self.identifier, self.pid, 'base-R2-v41', self.before, self.operator)
        self.assertEqual(changed.exception.status, 409)
        with self.assertRaises(android.AndroidError) as other:
            android.prepare(self.identifier, self.pid, 'base-R2-v42', self.before, self.other)
        self.assertEqual(other.exception.status, 409)
        with self.assertRaises(android.AndroidError) as private:
            android.operation(self.identifier, self.other)
        self.assertEqual(private.exception.status, 404)
        self.assertEqual(android.history(self.other)['items'], [])

    def test_two_simultaneous_identical_prepare_requests_create_one_job(self):
        barrier = threading.Barrier(2)
        def perform():
            barrier.wait()
            return self.prepare()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: perform(), range(2)))
        self.assertEqual(results[0], results[1])
        with db.get_db() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM esp32_ota_jobs WHERE pcb=?', (self.pid,)).fetchone()[0], 1)

    def test_concurrent_other_operation_web_and_serial_are_blocked(self):
        self.prepare()
        fresh = info(self.meta, self.key, self.pcb['mac'])
        with self.assertRaises(android.AndroidError) as blocked:
            android.prepare(str(uuid.uuid4()), self.pid, 'base-R2-v42', fresh, self.other)
        self.assertEqual(blocked.exception.status, 409)
        with self.assertRaisesRegex(ValueError, 'pendiente'):
            ota.prepare(self.pid, 'base-R2-v42', fresh, self.other)
        from app.services import r2_programming as r2
        with self.assertRaisesRegex(ValueError, 'pendiente'):
            r2.start(self.pid, 'base-R2-v42', 'a' * 24, self.other)

    def test_station_job_blocks_android_prepare(self):
        from app.services import r2_programming as r2
        with db.transaction() as c:
            r2.ensure(c)
            c.execute('''INSERT INTO r2_programming_attempts
                (id,pcb,firmware,station,operator,method,state,created,updated,expected)
                VALUES(?,?,?,?,?,?,?,?,?,?)''',
                      (secrets.token_hex(12), self.pid, 'base-R2-v42', 'a' * 24, self.other, 'serial',
                       'flashing', ota.time.time(), ota.time.time(), '{}'))
        with self.assertRaises(android.AndroidError) as blocked:
            self.prepare()
        self.assertEqual(blocked.exception.status, 409)

    def test_pending_enrollment_blocks_ota_but_assigned_identity_can_continue(self):
        from app.services import r2_enrollment
        with db.transaction() as c:
            r2_enrollment.ensure(c)
            c.execute('INSERT INTO r2_enrollments VALUES(?,?,?,?,?,?)',
                      ('enroll-' + self.identifier, self.pid, self.operator, ota.time.time(), 'prepared',
                       json.dumps(dict(nonce=secrets.token_hex(16), mac=self.pcb['mac']))))
        with self.assertRaises(android.AndroidError) as blocked:
            self.prepare()
        self.assertEqual(blocked.exception.status, 409)
        with db.transaction() as c:
            c.execute("UPDATE r2_enrollments SET state='assigned' WHERE id=?", ('enroll-' + self.identifier,))
        self.assertEqual(self.prepare()['state'], 'prepared')

    def test_verified_boot_reuses_inventory_evidence_events_and_exact_result_replay(self):
        self.prepared = self.prepare()
        body = self.report()
        result = android.report(self.identifier, body, self.operator)
        self.assertEqual(result['state'], 'verified')
        self.assertTrue(result['result']['inventory_updated'])
        self.assertEqual(inv.get_pcb(self.pid)['firmware'], '4.2')
        self.assertEqual(result['info_before'], self.before)
        self.assertEqual(result['info_after'], body['device'])
        importlib.reload(android)
        self.assertEqual(android.report(self.identifier, body, self.operator), result)
        with db.get_db() as c:
            self.assertEqual(c.execute('SELECT firmware FROM r2_programming_state WHERE pcb=?', (self.pid,)).fetchone()[0], '4.2')
            self.assertEqual(c.execute("SELECT COUNT(*) FROM escaneos WHERE evento='ESP32_OTA_VERIFICADA' AND detalle LIKE ?",
                                       ('%job=' + self.prepared['prepared']['job_id'] + '%',)).fetchone()[0], 1)
        with self.assertRaises(android.AndroidError) as conflict:
            android.report(self.identifier, dict(body, error='different'), self.operator)
        self.assertEqual(conflict.exception.status, 409)

    def test_two_simultaneous_final_reports_have_one_inventory_effect(self):
        self.prepared = self.prepare()
        body = self.report()
        barrier = threading.Barrier(2)
        def perform():
            barrier.wait()
            return android.report(self.identifier, body, self.operator)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: perform(), range(2)))
        self.assertEqual(results[0], results[1])
        with db.get_db() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM android_ota_events WHERE operation=? AND kind=?',
                                       (self.identifier, 'verified')).fetchone()[0], 1)

    def test_unknown_persists_then_authentic_reboot_recovers_without_reflashing(self):
        self.prepared = self.prepare()
        pending = dict(outcome='unknown', error='No se pudo confirmar el reinicio.', device=None)
        value = android.report(self.identifier, pending, self.operator)
        self.assertEqual(value['state'], 'pending_verification')
        self.assertEqual(inv.get_pcb(self.pid)['firmware'], '4.1')
        self.assertEqual(android.report(self.identifier, pending, self.operator), value)
        importlib.reload(android)
        complete = android.report(self.identifier, self.report(), self.operator)
        self.assertEqual(complete['state'], 'verified')
        self.assertEqual(complete['prepared']['job_id'], self.prepared['prepared']['job_id'])

    def test_failed_and_cancelled_never_change_inventory_and_are_immutable(self):
        self.prepare()
        body = dict(outcome='failed', device=None, error='Bluetooth desconectado')
        value = android.report(self.identifier, body, self.operator)
        self.assertEqual(value['state'], 'failed')
        self.assertFalse(value['result']['inventory_updated'])
        self.assertEqual(inv.get_pcb(self.pid)['firmware'], '4.1')
        self.assertEqual(android.report(self.identifier, body, self.operator), value)
        with self.assertRaises(android.AndroidError):
            android.report(self.identifier, dict(body, outcome='cancelled'), self.operator)
        fresh = info(self.meta, self.key, self.pcb['mac'])
        other_id = str(uuid.uuid4())
        android.prepare(other_id, self.pid, 'base-R2-v42', fresh, self.operator)
        cancelled = android.report(other_id, dict(outcome='cancelled', error='', device=None), self.operator)
        self.assertEqual(cancelled['state'], 'cancelled')
        self.assertEqual(inv.get_pcb(self.pid)['firmware'], '4.1')

    def test_forged_wrong_image_and_same_boot_evidence_stay_pending(self):
        self.prepared = self.prepare()
        valid = self.report()
        invalid = [dict(valid['device'], proof='0' * 64), self.before,
                   info(dict(self.meta, app_sha256='1' * 64), self.key, self.pcb['mac'], 0x150000)]
        for device in invalid:
            with self.assertRaises(android.AndroidError):
                android.report(self.identifier, dict(valid, device=device), self.operator)
            value = android.operation(self.identifier, self.operator)
            self.assertEqual(value['state'], 'pending_verification')
            self.assertEqual(inv.get_pcb(self.pid)['firmware'], '4.1')
        complete = android.report(self.identifier, valid, self.operator)
        self.assertEqual(complete['state'], 'verified')
        self.assertEqual(sum(e['kind'] == 'invalid_evidence' for e in android.operation(self.identifier, self.operator)['events']), 3)

    def test_revision_prevents_overwriting_a_later_web_update_even_if_values_reverted(self):
        self.prepared = self.prepare()
        inv.set_firmware(self.pid, '9.9', self.other)
        inv.set_firmware(self.pid, '4.1', self.other)
        result = android.report(self.identifier, self.report(), self.operator)
        self.assertEqual(result['state'], 'conflict')
        self.assertTrue(result['result']['accepted_history'])
        self.assertFalse(result['result']['inventory_updated'])
        self.assertEqual(inv.get_pcb(self.pid)['firmware'], '4.1')

    def test_programming_snapshot_detects_later_web_serial_verification_without_pcb_change(self):
        self.prepared = self.prepare()
        from app.services import r2_programming as r2
        with db.transaction() as c:
            r2.record(c, self.pcb, 'verify', self.before)
        result = android.report(self.identifier, self.report(), self.operator)
        self.assertEqual(result['state'], 'conflict')
        self.assertFalse(result['result']['inventory_updated'])

    def test_late_authentic_evidence_is_history_without_extending_authorization(self):
        self.prepared = self.prepare()
        with db.transaction() as c:
            c.execute('UPDATE esp32_ota_jobs SET created=0 WHERE id=?', (self.prepared['prepared']['job_id'],))
            c.execute('UPDATE android_ota_operations SET expires_at=1 WHERE id=?', (self.identifier,))
        body = self.report()
        result = android.report(self.identifier, body, self.operator)
        self.assertEqual(result['state'], 'accepted_history')
        self.assertTrue(result['result']['accepted_history'])
        self.assertFalse(result['result']['verified'])
        self.assertEqual(inv.get_pcb(self.pid)['firmware'], '4.1')
        self.assertEqual(android.report(self.identifier, body, self.operator), result)

    def test_late_forgery_is_not_accepted_as_history(self):
        self.prepared = self.prepare()
        with db.transaction() as c:
            c.execute('UPDATE android_ota_operations SET expires_at=1 WHERE id=?', (self.identifier,))
        body = self.report()
        body['device']['proof'] = '0' * 64
        with self.assertRaises(android.AndroidError):
            android.report(self.identifier, body, self.operator)
        self.assertIsNone(android.operation(self.identifier, self.operator)['result'])

    def test_result_application_rolls_back_partial_existing_service_failure(self):
        self.prepared = self.prepare()
        with patch('app.services.r2_programming.record', side_effect=ValueError('simulated persistence failure')):
            with self.assertRaises(android.AndroidError):
                android.report(self.identifier, self.report(), self.operator)
        self.assertEqual(inv.get_pcb(self.pid)['firmware'], '4.1')
        with db.get_db() as c:
            self.assertEqual(c.execute('SELECT state FROM esp32_ota_jobs WHERE id=?',
                                       (self.prepared['prepared']['job_id'],)).fetchone()[0], 'prepared')

    def test_exact_name_two_step_migration_remains_available(self):
        oldmeta = dict(self.meta, nombre=self.pcb['nombre'].replace('-', '_'))
        oldinfo = info(oldmeta, self.key, self.pcb['mac'])
        oldinfo['name_format'] = 1
        bridge = android.prepare(self.identifier, self.pid, 'base-R2-v42', oldinfo, self.operator)
        self.assertTrue(bridge['prepared']['migration_required'])
        bridge_info = self.boot(bridge['prepared'])
        partial = android.report(self.identifier, dict(outcome='verified', device=bridge_info, error=''), self.operator)
        self.assertEqual(partial['state'], 'migration_required')
        self.assertEqual(inv.get_pcb(self.pid)['firmware'], '4.1')
        final_id = str(uuid.uuid4())
        final = android.prepare(final_id, self.pid, 'base-R2-v42', bridge_info, self.operator)
        final_info = info(dict(self.meta, nombre=final['prepared']['nombre'], app_sha256=final['prepared']['app_sha256']),
                          self.key, self.pcb['mac'], 0x10000)
        complete = android.report(final_id, dict(outcome='verified', device=final_info, error=''), self.operator)
        self.assertEqual(complete['state'], 'verified')
        self.assertEqual(complete['result']['pcb']['nombre'], self.pcb['nombre'])

    def test_prepare_rejects_non_uuid_and_invalid_device_proof(self):
        with self.assertRaises(android.AndroidError):
            self.prepare(identifier='not-a-uuid')
        with self.assertRaises(android.AndroidError):
            android.prepare(self.identifier, self.pid, 'base-R2-v42', dict(self.before, proof='0' * 64), self.operator)
        with db.get_db() as c:
            self.assertIsNone(c.execute('SELECT 1 FROM android_ota_operations WHERE id=?', (self.identifier,)).fetchone())

    def test_new_tables_enforce_foreign_keys(self):
        self.prepare()
        with self.assertRaises(sqlite3.IntegrityError):
            with db.transaction() as c:
                c.execute('INSERT INTO android_ota_events(operation,created,kind,evidence) VALUES(?,?,?,?)',
                          (str(uuid.uuid4()), 0, 'bad', '{}'))

    def test_api_reuses_login_role_origin_owner_and_rejects_success_boolean(self):
        body = dict(client_operation_id=self.identifier, pcb_id=self.pid, firmware_id='base-R2-v42', device=self.before)
        anonymous = iso.cliente_sin_sesion(app)
        for url in ('/api/android/devices', '/api/android/apk/manifest', '/api/android/apk/download'):
            self.assertEqual(anonymous.get(url).status_code, 401)
        client = TestClient(app, base_url='https://testserver')
        with patch('app.services.usuarios.validar_sesion', return_value={'email': self.operator, 'rol': 'consultor'}):
            self.assertEqual(client.get('/api/android/devices').status_code, 200)
            self.assertEqual(client.post('/api/android/operations/prepare', json=body).status_code, 403)
        with patch('app.services.usuarios.validar_sesion', return_value={'email': self.operator, 'rol': 'general'}):
            self.assertEqual(client.post('/api/android/operations/prepare', json=body,
                                         headers={'Origin': 'https://other.invalid'}).status_code, 403)
            prepared = client.post('/api/android/operations/prepare', json=body)
            self.assertEqual(prepared.status_code, 200)
            self.assertEqual(prepared.headers['Cache-Control'], 'no-store')
            url = f'/api/android/operations/{self.identifier}/result'
            self.assertEqual(client.post(url, json={'success': True}).status_code, 422)
            self.assertEqual(client.post(url, json={'outcome': 'verified'}).status_code, 422)
            result = client.post(url, json=dict(outcome='verified', device=self.boot(prepared.json()['prepared'])))
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json()['state'], 'verified')
        with patch('app.services.usuarios.validar_sesion', return_value={'email': self.other, 'rol': 'general'}):
            self.assertEqual(client.get(f'/api/android/operations/{self.identifier}').status_code, 404)


class AndroidApkTests(unittest.TestCase):
    def test_apk_disabled_without_approved_verified_package(self):
        with patch.dict('os.environ', {}, clear=True):
            with self.assertRaises(android.AndroidError) as disabled:
                android.apk_package()
        self.assertEqual(disabled.exception.status, 503)

    def test_apk_verification_checks_zip_hash_certificate_and_actual_manifest(self):
        with tempfile.TemporaryDirectory(prefix='tqt_android_apk_test_') as temporary:
            folder = Path(temporary)
            apk = folder / 'TQT.apk'
            with zipfile.ZipFile(apk, 'w') as archive:
                archive.writestr('AndroidManifest.xml', b'manifest fixture, SDK parses actual production manifest')
                archive.writestr('classes.dex', b'dex fixture')
            verifier = folder / 'apksigner'
            verifier.touch()
            aapt = folder / 'aapt'
            aapt.touch()
            meta = dict(approved=True, filename=apk.name, package_name='mx.tqt.android', version_code=1,
                        version_name='1.0', min_sdk=26, sha256=hashlib.sha256(apk.read_bytes()).hexdigest(),
                        certificate_sha256='a' * 64)
            manifest = folder / 'manifest.json'
            manifest.write_text(json.dumps(meta), encoding='utf-8')
            env = dict(TQT_ANDROID_APK_DIR=str(folder), TQT_ANDROID_APKSIGNER=str(verifier), TQT_ANDROID_AAPT=str(aapt))
            signed = subprocess.CompletedProcess([], 0, 'Signer #1 certificate SHA-256 digest: ' + 'a' * 64, '')
            parsed = subprocess.CompletedProcess([], 0, "package: name='mx.tqt.android' versionCode='1' versionName='1.0'\nsdkVersion:'26'\n", '')
            with patch.dict('os.environ', env), patch.object(android.subprocess, 'run', side_effect=[signed, parsed]):
                public, raw = android.apk_package()
                self.assertEqual(public['certificate_sha256'], meta['certificate_sha256'])
                self.assertEqual(raw, apk.read_bytes())
                self.assertNotIn(str(folder), json.dumps(public))
            wrong_certificate = subprocess.CompletedProcess([], 0, 'Signer #1 certificate SHA-256 digest: ' + 'b' * 64, '')
            with patch.dict('os.environ', env), patch.object(android.subprocess, 'run', side_effect=[wrong_certificate, parsed]):
                with self.assertRaises(android.AndroidError):
                    android.apk_package()
            wrong_package = subprocess.CompletedProcess([], 0, "package: name='other.app' versionCode='1' versionName='1.0'\nsdkVersion:'26'\n", '')
            with patch.dict('os.environ', env), patch.object(android.subprocess, 'run', side_effect=[signed, wrong_package]):
                with self.assertRaises(android.AndroidError):
                    android.apk_package()
            apk.write_bytes(b'not a ZIP')
            with patch.dict('os.environ', env):
                with self.assertRaises(android.AndroidError):
                    android.apk_package()
            meta['sha256'] = hashlib.sha256(apk.read_bytes()).hexdigest()
            manifest.write_text(json.dumps(meta), encoding='utf-8')
            with patch.dict('os.environ', env):
                with self.assertRaises(android.AndroidError):
                    android.apk_package()


if __name__ == '__main__':
    unittest.main()
