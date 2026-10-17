import _aislamiento as iso
import base64
import hashlib
import hmac
import importlib
import json
import secrets
import struct
import threading
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, utils
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from fastapi.testclient import TestClient
from app.main import app
from app.database import db, inventario as inv
from app.services import android_offline as offline, android_ota as android, esp32_firmware as fw, esp32_ota as ota
from test_android_ota import info as legacy_info
from test_esp32_firmware import rewrite


def public(key):
    return key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)


def sign(key, body):
    r, s = utils.decode_dss_signature(key.sign(body, ec.ECDSA(hashes.SHA256())))
    return (r.to_bytes(32, 'big') + s.to_bytes(32, 'big')).hex()


def attestation(meta, key, device, mac, anchor, counter=0, receipt='0' * 32, partition=0x10000):
    value = legacy_info(meta, key, mac, partition)
    value.update(offline_protocol=1, offline_public_key=public(device).hex(), offline_counter=counter,
                 offline_anchor_id=anchor, offline_last_grant=receipt)
    identity = (b'TQT-OFFLINE-IDENTITY-v1' + bytes.fromhex(value['proof']) + public(device) +
                struct.pack('<I', counter) + bytes.fromhex(anchor))
    value['offline_identity_proof'] = hmac.new(key, identity, hashlib.sha256).hexdigest()
    body = (b'TQT-OFFLINE-INFO-v1' + bytes.fromhex(value['nonce']) + bytes.fromhex(value['app_sha256']) +
            struct.pack('<II', counter, partition) + b'\x01' + value['nombre'].encode().ljust(24, b'\0') +
            value['hw'].encode().ljust(8, b'\0') + value['fw'].encode().ljust(16, b'\0') + bytes.fromhex(mac.replace(':', '')) + bytes.fromhex(receipt))
    value['offline_signature'] = sign(device, body)
    return value


class AndroidOfflineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init_db()
        # A fresh fixture root, never a private production key or a replacement
        # of the immutable generic base. The synthetic image is never flashed.
        cls.root = ec.generate_private_key(ec.SECP256R1())
        cls.root_public = public(cls.root)
        cls.anchor = hashlib.sha256(cls.root_public).hexdigest()[:16]
        raw = (fw.ROOT / 'firmware/esp32_r2/TQT_R2_V4_2.merged.bin').read_bytes()
        _, profile, layout = fw.inspect(raw)
        raw = rewrite(raw, profile + 28, b'4.3'.ljust(16, b'\0'))
        at = layout['segments'][0][0] + 512
        assert not (at < profile + 128 and at + 100 > profile)
        raw = rewrite(raw, at, b'TQT_OFFLINE_V1_P256\0' + cls.root_public)
        cls.firmware = fw.save(raw, 'TEST_ONLY_OFFLINE43.bin', 'offline-fixture@tqt.invalid')['id']
        cls.raw = raw

    @classmethod
    def tearDownClass(cls):
        with db.transaction() as c:
            c.execute('DELETE FROM esp32_firmwares WHERE id=?', (cls.firmware,))

    def setUp(self):
        self.operator = f'offline-{uuid.uuid4().hex}@tqt.invalid'
        self.other = f'other-{uuid.uuid4().hex}@tqt.invalid'
        self.pcb = iso.crear_par(iso.nuevo_lote()['id'])['r2']
        self.pid = self.pcb['id']
        self.meta, image = fw.prepare(self.pid, self.firmware, True)
        self.meta['app_sha256'] = image[fw.inspect(image)[2]['end'] - 32:fw.inspect(image)[2]['end']].hex()
        with db.get_db() as c:
            self.key = bytes(c.execute('SELECT secret FROM esp32_unit_keys WHERE pcb=?', (self.pid,)).fetchone()[0])
        inv.set_firmware(self.pid, '4.3')
        self.pcb = inv.get_pcb(self.pid)
        self.device, self.phone = ec.generate_private_key(ec.SECP256R1()), ec.generate_private_key(ec.SECP256R1())
        self.identifier = str(uuid.uuid4())
        self.signer_path = iso.TMP / ('offline-fixture-' + uuid.uuid4().hex + '.pem')
        self.signer_path.write_bytes(self.root.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        self.patches = [patch.object(offline, '_anchor', return_value=(self.root_public, self.anchor)),
                        patch.dict('os.environ', {'TQT_R2_ENROLL_SIGNING_KEY': str(self.signer_path)})]
        for fixture in self.patches:
            fixture.start()
        self.before = self.info()
        offline.bind(self.pid, self.before, self.operator)

    def tearDown(self):
        with db.transaction() as c:
            c.execute('DELETE FROM android_offline_grants WHERE target_pcb=?', (self.pid,))
        for fixture in reversed(self.patches):
            fixture.stop()

    def info(self, **changes):
        return attestation(changes.pop('meta', self.meta), self.key, changes.pop('device', self.device),
                           self.pcb['mac'], self.anchor, **changes)

    def create(self, identifier=None, operator=None):
        return offline.create(identifier or self.identifier, self.pid, self.firmware, public(self.phone).hex(), operator or self.operator)

    def report_body(self, package):
        value = package['package']
        before = self.info()
        after = self.info(meta=dict(self.meta, app_sha256=value['target_app_digest'], fw=value['fw']),
                          counter=value['source_counter'] + 1, receipt=uuid.UUID(package['client_operation_id']).hex, partition=0x150000)
        session = (b'TQT-OFFLINE-SESSION-v1' + uuid.UUID(package['client_operation_id']).bytes +
                   bytes.fromhex(before['nonce']) + hashlib.sha256(base64.b64decode(value['grant'])).digest())
        return dict(outcome='verified', before=before, after=after, phone_signature=sign(self.phone, session), error='')

    def test_grant_offsets_signatures_and_encrypted_transport_match_normative_contract(self):
        value = self.create()
        package = value['package']
        grant = base64.b64decode(package['grant'])
        self.assertEqual(len(grant), 408)
        self.assertEqual(grant[:16], bytes.fromhex('5451542d4f46464c494e452d76310000'))
        self.assertEqual(grant[16:32], uuid.UUID(self.identifier).bytes)
        self.assertEqual(grant[32:97], public(self.device))
        self.assertEqual(grant[97:162], public(self.phone))
        self.assertEqual(struct.unpack_from('<I', grant, 178)[0], 0)
        self.assertEqual(grant[182:214].hex(), self.before['app_sha256'])
        self.assertEqual(grant[246:278].hex(), package['target_app_digest'])
        self.assertEqual(grant[282:306], self.pcb['nombre'].encode().ljust(24, b'\0'))
        self.assertEqual(grant[306:314], b'3.0'.ljust(8, b'\0'))
        self.assertEqual(grant[314:330], b'4.3'.ljust(16, b'\0'))
        self.assertEqual(grant[330:336], bytes.fromhex(self.pcb['mac'].replace(':', '')))
        self.assertEqual(grant[336:344].hex(), self.anchor)
        self.root.public_key().verify(utils.encode_dss_signature(int.from_bytes(grant[344:376], 'big'), int.from_bytes(grant[376:408], 'big')),
                                      grant[:344], ec.ECDSA(hashes.SHA256()))
        derived = hmac.new(self.key, b'TQT-OFFLINE-DATA-v1' + uuid.UUID(self.identifier).bytes, hashlib.sha256).digest()
        decryptor = Cipher(algorithms.AES(derived), modes.CTR(grant[162:178])).decryptor()
        clear = decryptor.update(base64.b64decode(package['encrypted_image'])) + decryptor.finalize()
        self.assertEqual(hashlib.sha256(clear).digest(), grant[214:246])
        self.assertEqual(clear[-32:].hex(), package['target_app_digest'])
        self.assertEqual(len(clear), struct.unpack_from('<I', grant, 278)[0])
        self.assertNotIn(self.key.hex(), json.dumps(value))
        self.assertEqual(value['expires_at'] - value['created'], 86400)
        self.assertEqual(value['receive_until'] - value['created'], 604800)

    def test_binding_checks_legacy_hmac_device_signature_identity_root_and_monotonic_counter(self):
        for field, invalid in [('proof', '0' * 64), ('offline_identity_proof', '0' * 64),
                               ('offline_signature', '0' * 128), ('offline_anchor_id', '0' * 16), ('offline_counter', True)]:
            with self.assertRaises(ValueError, msg=field):
                offline.bind(self.pid, dict(self.before, **{field: invalid}), self.operator)
        with self.assertRaises(offline.Error):
            offline.bind(self.pid, self.info(device=ec.generate_private_key(ec.SECP256R1())), self.operator)
        offline.bind(self.pid, self.info(counter=2), self.operator)
        with self.assertRaises(offline.Error) as stale:
            offline.bind(self.pid, self.before, self.operator)
        self.assertEqual(stale.exception.status, 409)

    def test_missing_or_wrong_existing_signer_never_generates_or_replaces_a_key(self):
        missing = iso.TMP / ('does-not-exist-' + uuid.uuid4().hex + '.pem')
        with patch.dict('os.environ', {'TQT_R2_ENROLL_SIGNING_KEY': str(missing)}), patch('app.services.r2_enrollment.signing_key', side_effect=AssertionError('must not generate')):
            with self.assertRaises(offline.Error) as unavailable:
                self.create()
        self.assertEqual(unavailable.exception.status, 503)
        self.assertFalse(missing.exists())
        wrong = ec.generate_private_key(ec.SECP256R1())
        self.signer_path.write_bytes(wrong.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        prior = self.signer_path.read_bytes()
        with self.assertRaises(offline.Error) as mismatch:
            self.create()
        self.assertEqual(mismatch.exception.status, 503)
        self.assertEqual(self.signer_path.read_bytes(), prior)

    def test_exact_prepare_uuid_is_durable_idempotent_and_private(self):
        first = self.create()
        self.assertEqual(self.create(), first)
        self.assertEqual(offline.get(self.identifier, self.operator), first)
        with self.assertRaises(offline.Error) as wrong_owner:
            offline.get(self.identifier, self.other)
        self.assertEqual(wrong_owner.exception.status, 404)
        self.assertEqual(offline.history(self.other)['items'], [])
        summary = offline.history(self.operator)['items'][0]
        self.assertNotIn('encrypted_image', summary['package'])
        with self.assertRaises(offline.Error):
            offline.create(self.identifier, self.pid, self.firmware, public(ec.generate_private_key(ec.SECP256R1())).hex(), self.operator)
        with db.get_db() as c:
            self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_simultaneous_requests_create_one_grant_and_other_phone_is_blocked(self):
        barrier = threading.Barrier(2)
        def create():
            barrier.wait()
            return self.create()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: create(), range(2)))
        self.assertEqual(results[0], results[1])
        with self.assertRaises(offline.Error) as busy:
            self.create(str(uuid.uuid4()), self.other)
        self.assertEqual(busy.exception.status, 409)

    def test_authenticated_receipt_applies_existing_inventory_evidence_once(self):
        package = self.create()
        body = self.report_body(package)
        result = offline.report(self.identifier, body, self.operator)
        self.assertEqual(result['state'], 'verified')
        self.assertTrue(result['result']['verified'])
        self.assertTrue(result['result']['inventory_updated'])
        self.assertEqual(result['info_after'], body['after'])
        self.assertEqual(offline.report(self.identifier, body, self.operator), result)
        with db.get_db() as c:
            self.assertEqual(c.execute('SELECT method FROM r2_programming_state WHERE pcb=?', (self.pid,)).fetchone()[0], 'ble_offline')
            self.assertEqual(c.execute("SELECT COUNT(*) FROM android_offline_events WHERE operation=? AND kind='verified'", (self.identifier,)).fetchone()[0], 1)
        with self.assertRaises(offline.Error) as conflict:
            offline.report(self.identifier, dict(body, error='different'), self.operator)
        self.assertEqual(conflict.exception.status, 409)

    def test_wrong_receipt_counter_partition_digest_identity_and_phone_proof_never_apply(self):
        package = self.create()
        body = self.report_body(package)
        variants = [dict(body['after'], offline_identity_proof='0' * 64), dict(body['after'], offline_signature='0' * 128),
                    self.info(counter=2, receipt=uuid.UUID(self.identifier).hex, partition=0x150000),
                    self.info(counter=1, receipt='0' * 32, partition=0x150000),
                    self.info(counter=1, receipt=uuid.UUID(self.identifier).hex, partition=0x10000),
                    self.info(meta=dict(self.meta, app_sha256='1' * 64), counter=1, receipt=uuid.UUID(self.identifier).hex, partition=0x150000)]
        for after in variants:
            with self.assertRaises(offline.Error):
                offline.report(self.identifier, dict(body, after=after), self.operator)
            self.assertIsNone(offline.get(self.identifier, self.operator)['result'])
        with self.assertRaises(offline.Error):
            offline.report(self.identifier, dict(body, phone_signature='0' * 128), self.operator)
        self.assertEqual(offline.report(self.identifier, body, self.operator)['state'], 'verified')

    def test_unknown_remains_recoverable_and_holds_authorization(self):
        package = self.create()
        pending = dict(outcome='unknown', error='No se confirmó el reinicio.')
        self.assertEqual(offline.report(self.identifier, pending, self.operator)['state'], 'pending_verification')
        with self.assertRaises(offline.Error):
            self.create(str(uuid.uuid4()))
        self.assertEqual(offline.report(self.identifier, self.report_body(package), self.operator)['state'], 'verified')

    def test_fresh_binding_of_this_receipt_before_sync_does_not_supersede_its_own_operation(self):
        package = self.create()
        body = self.report_body(package)
        offline.bind(self.pid, body['after'], self.operator)
        self.assertEqual(offline.get(self.identifier, self.operator)['state'], 'authorized')
        self.assertEqual(offline.report(self.identifier, body, self.operator)['state'], 'verified')

    def test_consumed_counter_with_unconfirmed_new_partition_can_authorize_a_fresh_grant(self):
        self.create()
        # COMMIT consumed its counter but the original partition is running.
        # Reusing that grant is impossible; a fresh authenticated probe permits recovery.
        offline.bind(self.pid, self.info(counter=1, receipt=uuid.UUID(self.identifier).hex), self.operator)
        self.assertEqual(offline.get(self.identifier, self.operator)['state'], 'superseded')
        self.assertEqual(self.create(str(uuid.uuid4()))['package']['source_counter'], 1)

    def test_erased_inventory_uses_authentic_offline_binding_and_restores_only_after_verified_boot(self):
        inv.set_firmware(self.pid, None)
        inv.set_mac(self.pid, None)
        offline.bind(self.pid, self.info(), self.operator)
        self.assertTrue(android.device(self.pid)['capability']['offline'])
        package = self.create()
        self.assertIsNone(inv.get_pcb(self.pid)['firmware'])
        self.assertIsNone(inv.get_pcb(self.pid)['mac'])
        result = offline.report(self.identifier, self.report_body(package), self.operator)
        self.assertEqual(result['state'], 'verified')
        self.assertEqual(result['result']['pcb']['firmware'], '4.3')
        self.assertEqual(result['result']['pcb']['mac'], self.pcb['mac'])

    def test_signed_grant_metadata_tampering_and_exhausted_counter_fail_closed(self):
        package = self.create()
        body = self.report_body(package)
        with db.transaction() as c:
            tampered = dict(package['package'], bytes=123)
            c.execute('UPDATE android_offline_grants SET package=? WHERE id=?', (json.dumps(tampered), self.identifier))
        with self.assertRaises(offline.Error):
            offline.report(self.identifier, body, self.operator)
        with db.transaction() as c:
            c.execute('UPDATE android_offline_grants SET package=? WHERE id=?', (json.dumps(package['package']), self.identifier))
        offline.report(self.identifier, dict(outcome='cancelled'), self.operator)
        offline.bind(self.pid, self.info(counter=0xFFFFFFFF), self.operator)
        with self.assertRaises(offline.Error) as exhausted:
            self.create(str(uuid.uuid4()))
        self.assertEqual(exhausted.exception.status, 409)

    def test_cancel_or_failure_does_not_claim_firmware_change_and_is_terminal(self):
        package = self.create()
        body = dict(outcome='cancelled', error='Antes de COMMIT')
        cancelled = offline.report(self.identifier, body, self.operator)
        self.assertEqual(cancelled['state'], 'cancelled')
        self.assertFalse(cancelled['result']['inventory_updated'])
        self.assertEqual(offline.report(self.identifier, body, self.operator), cancelled)
        with self.assertRaises(offline.Error):
            offline.report(self.identifier, self.report_body(package), self.operator)

    def test_newer_inventory_and_expired_grants_are_history_without_overwrite(self):
        package = self.create()
        inv.set_firmware(self.pid, '9.9', self.other)
        result = offline.report(self.identifier, self.report_body(package), self.operator)
        self.assertEqual(result['state'], 'conflict')
        self.assertTrue(result['result']['accepted_history'])
        self.assertFalse(result['result']['verified'])
        self.assertEqual(inv.get_pcb(self.pid)['firmware'], '9.9')

    def test_late_authentic_result_is_retained_without_extending_ttl(self):
        package = self.create()
        with db.transaction() as c:
            c.execute('UPDATE android_offline_grants SET expires_at=1,receive_until=2 WHERE id=?', (self.identifier,))
        body = self.report_body(package)
        late = offline.report(self.identifier, body, self.operator)
        self.assertEqual(late['state'], 'accepted_history')
        self.assertFalse(late['result']['inventory_updated'])
        self.assertEqual(late['expires_at'], 1)
        with db.get_db() as c:
            self.assertIsNone(c.execute('SELECT 1 FROM r2_programming_state WHERE pcb=?', (self.pid,)).fetchone())

    def test_superseded_grant_and_later_binding_counter_do_not_overwrite_current_state(self):
        old = self.create()
        with db.transaction() as c:
            c.execute('UPDATE android_offline_grants SET expires_at=1 WHERE id=?', (self.identifier,))
        newer = self.create(str(uuid.uuid4()))
        result = offline.report(self.identifier, self.report_body(old), self.operator)
        self.assertEqual(result['state'], 'conflict')
        self.assertEqual(result['result']['reason'], 'authorization_superseded')
        offline.bind(self.pid, self.info(counter=1, receipt=uuid.UUID(self.identifier).hex), self.operator)
        self.assertEqual(offline.get(newer['client_operation_id'], self.operator)['state'], 'superseded')
        self.assertEqual(self.create(str(uuid.uuid4()))['package']['source_counter'], 1)

    def test_online_and_station_guard_both_directions_without_changing_legacy_ttl(self):
        from app.services import r2_programming as r2
        package = self.create()
        with self.assertRaisesRegex(ValueError, 'offline'):
            ota.prepare(self.pid, self.firmware, self.before, self.operator)
        with self.assertRaisesRegex(ValueError, 'offline'):
            r2.start(self.pid, self.firmware, 'a' * 24, self.operator)
        offline.report(self.identifier, dict(outcome='cancelled', error='test'), self.operator)
        online = ota.prepare(self.pid, self.firmware, self.info(), self.operator)
        with self.assertRaises(offline.Error) as blocked:
            self.create(str(uuid.uuid4()))
        self.assertEqual(blocked.exception.status, 409)
        ota.cancel(online['job_id'], self.operator)
        with db.transaction() as c:
            r2.ensure(c)
            c.execute('''INSERT INTO r2_programming_attempts
                (id,pcb,firmware,station,operator,method,state,created,updated,expected) VALUES(?,?,?,?,?,?,?,?,?,?)''',
                      ('station-' + self.identifier, self.pid, self.firmware, 'a' * 24, self.operator, 'serial', 'flashing', offline.time.time(), offline.time.time(), '{}'))
        with self.assertRaises(offline.Error) as busy:
            self.create(str(uuid.uuid4()))
        self.assertEqual(busy.exception.status, 409)
        self.assertEqual(ota.LIFETIME, 3600)

    def test_template_without_offline_marker_or_wrong_root_is_rejected(self):
        with self.assertRaises(offline.Error):
            offline.create(self.identifier, self.pid, 'base-R2-v42', public(self.phone).hex(), self.operator)
        _, profile, _ = fw.inspect(self.raw)
        raw = rewrite(self.raw, profile + 28, b'4.3.1'.ljust(16, b'\0'))
        raw = rewrite(raw, raw.find(self.root_public), public(ec.generate_private_key(ec.SECP256R1())))
        identifier = fw.save(raw, 'WRONG_ROOT_TEST_ONLY.bin', self.operator)['id']
        try:
            with self.assertRaises(offline.Error):
                offline.create(self.identifier, self.pid, identifier, public(self.phone).hex(), self.operator)
        finally:
            with db.transaction() as c:
                c.execute('DELETE FROM esp32_firmwares WHERE id=?', (identifier,))

    def test_atomic_application_rolls_back_inventory_if_shared_history_fails(self):
        package = self.create()
        with patch('app.services.r2_programming.record', side_effect=ValueError('fixture persistence failure')):
            with self.assertRaises(offline.Error):
                offline.report(self.identifier, self.report_body(package), self.operator)
        self.assertEqual(offline.get(self.identifier, self.operator)['state'], 'pending_verification')
        with db.get_db() as c:
            self.assertIsNone(c.execute('SELECT 1 FROM r2_programming_state WHERE pcb=?', (self.pid,)).fetchone())

    def test_api_cookie_role_origin_ownership_and_evidence_contract(self):
        body = dict(client_operation_id=self.identifier, pcb_id=self.pid, firmware_id=self.firmware, phone_public_key=public(self.phone).hex())
        anonymous = iso.cliente_sin_sesion(app)
        self.assertEqual(anonymous.get('/api/android/offline/packages').status_code, 401)
        client = TestClient(app, base_url='https://testserver')
        with patch('app.services.usuarios.validar_sesion', return_value=dict(email=self.operator, rol='consultor')):
            self.assertEqual(client.post('/api/android/offline/packages', json=body).status_code, 403)
        with patch('app.services.usuarios.validar_sesion', return_value=dict(email=self.operator, rol='general')):
            self.assertEqual(client.post(f'/api/android/offline/bind/{self.pid}', json=dict(device=self.info())).status_code, 200)
            self.assertEqual(client.post('/api/android/offline/packages', json=body, headers={'Origin': 'https://foreign.invalid'}).status_code, 403)
            prepared = client.post('/api/android/offline/packages', json=body)
            self.assertEqual(prepared.status_code, 200)
            url = f'/api/android/offline/operations/{self.identifier}/result'
            self.assertEqual(client.post(url, json=dict(success=True)).status_code, 422)
            self.assertEqual(client.post(url, json=dict(outcome='verified')).status_code, 422)
            result = client.post(url, json=self.report_body(prepared.json()))
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json()['state'], 'verified')
        with patch('app.services.usuarios.validar_sesion', return_value=dict(email=self.other, rol='general')):
            self.assertEqual(client.get(f'/api/android/offline/packages/{self.identifier}').status_code, 404)


if __name__ == '__main__':
    unittest.main()
