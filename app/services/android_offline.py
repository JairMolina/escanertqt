"""Signed one-use FW4.3 grants, without exporting unit keys or the enrollment signer.

Wire format is protocols/offline-v1.json. Device counters provide causal scope;
the ESP32 has no trusted UTC clock. Expiry and revocation are server/app policy,
not a promise that an already disconnected device rejects an expired grant.
"""
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import struct
import time
import uuid
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, utils
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from app.config import settings
from app.database import db, inventario as inv
from app.services import android_ota as android, esp32_firmware as fw, esp32_ota as ota

Error = android.AndroidError
SCHEMA_VERSION = 1
PACKAGE_TTL = 24 * 3600
RECEIVE_TTL = 7 * 24 * 3600
MARKER = b'TQT_OFFLINE_V1_P256'
MAGIC = b'TQT-OFFLINE-v1\0\0'
IDENTITY_LABEL = b'TQT-OFFLINE-IDENTITY-v1'
INFO_LABEL = b'TQT-OFFLINE-INFO-v1'
SESSION_LABEL = b'TQT-OFFLINE-SESSION-v1'
DATA_LABEL = b'TQT-OFFLINE-DATA-v1'
TERMINAL = {'verified', 'failed', 'cancelled', 'conflict', 'accepted_history'}


def ensure(c):
    android.ensure(c)
    c.execute('CREATE TABLE IF NOT EXISTS android_offline_schema(version INTEGER NOT NULL)')
    prior = c.execute('SELECT version FROM android_offline_schema').fetchone()
    if prior and prior['version'] != SCHEMA_VERSION:
        raise Error('Esquema offline incompatible; requiere revisión.', 503)
    c.execute('''CREATE TABLE IF NOT EXISTS android_offline_bindings (
        pcb INTEGER PRIMARY KEY REFERENCES pcb_inventario(id) ON DELETE CASCADE,
        public_key TEXT NOT NULL UNIQUE, counter INTEGER NOT NULL CHECK(counter BETWEEN 0 AND 4294967295),
        app_digest TEXT NOT NULL, last_grant TEXT NOT NULL, anchor TEXT NOT NULL,
        info TEXT NOT NULL, revision INTEGER NOT NULL, snapshot TEXT NOT NULL,
        state TEXT NOT NULL, updated REAL NOT NULL, operator TEXT NOT NULL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS android_offline_grants (
        id TEXT PRIMARY KEY, pcb INTEGER REFERENCES pcb_inventario(id) ON DELETE SET NULL,
        target_pcb INTEGER NOT NULL, firmware TEXT NOT NULL REFERENCES esp32_firmwares(id),
        operator TEXT NOT NULL, state TEXT NOT NULL, source_counter INTEGER NOT NULL,
        created REAL NOT NULL, updated REAL NOT NULL, expires_at REAL NOT NULL, receive_until REAL NOT NULL,
        revision INTEGER NOT NULL, snapshot TEXT NOT NULL, binding_info TEXT NOT NULL,
        request_hash TEXT NOT NULL, package TEXT NOT NULL, info_before TEXT, info_after TEXT,
        report_hash TEXT, result TEXT, error TEXT)''')
    c.execute("CREATE UNIQUE INDEX IF NOT EXISTS android_offline_active_counter ON android_offline_grants(target_pcb,source_counter) WHERE state IN ('authorized','pending_verification')")
    c.execute('CREATE INDEX IF NOT EXISTS android_offline_owner ON android_offline_grants(operator,created DESC)')
    c.execute('''CREATE TABLE IF NOT EXISTS android_offline_events (
        id INTEGER PRIMARY KEY, operation TEXT NOT NULL REFERENCES android_offline_grants(id) ON DELETE CASCADE,
        created REAL NOT NULL, kind TEXT NOT NULL, evidence TEXT NOT NULL)''')
    if not prior:
        c.execute('INSERT INTO android_offline_schema VALUES(?)', (SCHEMA_VERSION,))


def _anchor():
    path = fw.ROOT / 'firmware/esp32_r2/TQT_R2_BASE_V4_0_GENERIC/enrollment_trust.h'
    try:
        text = path.read_text(encoding='utf-8')
        match = re.search(r'ENROLL_PUBLIC_KEY\s*\[65\]\s*=\s*\{([^}]+)\}', text)
        key_id = re.search(r'ENROLL_KEY_ID\[\]\s*=\s*"([a-f0-9]{16})"', text)
        public = bytes(int(v, 16) for v in re.findall(r'0x([a-fA-F0-9]{2})', match[1]))
        if len(public) != 65 or not key_id or hashlib.sha256(public).hexdigest()[:16] != key_id[1]:
            raise ValueError()
        _public_key(public.hex())
        return public, key_id[1]
    except (OSError, ValueError, TypeError, IndexError) as exc:
        raise Error('No se pudo verificar el ancla pública de la base fija.', 503) from exc


def _signer():
    """Read the existing signer directly: never call a generate-on-missing path."""
    path = Path(os.environ.get('TQT_R2_ENROLL_SIGNING_KEY', str(Path(settings.DB_PATH).parent / 'r2_enrollment_signing.pem')))
    try:
        with path.open('rb') as handle:
            raw = handle.read(16385)
        if len(raw) > 16384:
            raise ValueError()
        key = serialization.load_pem_private_key(raw, password=None)
        if not isinstance(key, ec.EllipticCurvePrivateKey) or not isinstance(key.curve, ec.SECP256R1):
            raise ValueError()
        public = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
        expected, anchor = _anchor()
        if not hmac.compare_digest(public, expected):
            raise ValueError()
        return key, expected, anchor
    except (OSError, ValueError, TypeError) as exc:
        raise Error('Offline deshabilitado: falta el firmante existente de la base fija o no coincide con su ancla.', 503) from exc


def _public_key(value):
    raw = ota.hex_bytes(value, 65)
    if raw[0] != 4:
        raise Error('Clave pública P256 inválida.', 422)
    try:
        return ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), raw)
    except ValueError as exc:
        raise Error('Clave pública P256 inválida.', 422) from exc


def _sign(key, body):
    r, s = utils.decode_dss_signature(key.sign(body, ec.ECDSA(hashes.SHA256())))
    return r.to_bytes(32, 'big') + s.to_bytes(32, 'big')


def _verify(public, signature, body):
    raw = ota.hex_bytes(signature, 64)
    try:
        public.verify(utils.encode_dss_signature(int.from_bytes(raw[:32], 'big'), int.from_bytes(raw[32:], 'big')),
                      body, ec.ECDSA(hashes.SHA256()))
    except (ValueError, InvalidSignature) as exc:
        raise Error('Firma offline inválida.') from exc


def verify_info(info, key, pcb, anchor):
    if not isinstance(info, dict):
        raise Error('Se requiere INFO4.3 completo y auténtico.', 422)
    ota.verify_info(info, key, pcb, allow_missing_mac=True)
    if (info.get('offline_protocol') != 1 or type(info.get('offline_protocol')) is not int or
            ota.version(info['fw']) < (4, 3) or info['hw'] != '3.0' or
            info['nombre'] != pcb['nombre'] or info.get('name_format') != 2):
        raise Error('Completa la instalación online4.3 con nombre exacto antes de habilitar offline.')
    counter = info.get('offline_counter')
    if type(counter) is not int or not 0 <= counter <= 0xFFFFFFFF:
        raise Error('Contador offline inválido.', 422)
    public_raw = ota.hex_bytes(info.get('offline_public_key'), 65)
    public = _public_key(info['offline_public_key'])
    if info.get('offline_anchor_id') != anchor:
        raise Error('El ancla offline del dispositivo no coincide con la base fija.')
    expected = hmac.new(key, IDENTITY_LABEL + ota.hex_bytes(info['proof'], 32) + public_raw +
                        struct.pack('<I', counter) + bytes.fromhex(anchor), hashlib.sha256).digest()
    if not hmac.compare_digest(expected, ota.hex_bytes(info.get('offline_identity_proof'), 32)):
        raise Error('El dispositivo no presentó una identidad offline auténtica.')
    last_grant = ota.hex_bytes(info.get('offline_last_grant'), 16)
    body = (INFO_LABEL + ota.hex_bytes(info['nonce'], 16) + ota.hex_bytes(info['app_sha256'], 32) +
            struct.pack('<II', counter, info['partition']) + b'\x01' + ota.fixed(info['nombre'], 24) +
            ota.fixed(info['hw'], 8) + ota.fixed(info['fw'], 16) + ota.mac(info['mac']) + last_grant)
    _verify(public, info.get('offline_signature'), body)
    return counter


def _binding_public(row):
    return dict(pcb_id=row['pcb'], offline_protocol=1, device_public_key=row['public_key'],
                offline_counter=row['counter'], source_app_digest=row['app_digest'], revision=row['revision'],
                anchor_key_id=row['anchor'], updated=row['updated'], state=row['state'])


def bind(pcb_id, info, operator):
    _, anchor = _anchor()
    with db.transaction() as c:
        ensure(c)
        pcb = inv.get_pcb(pcb_id, conn=c)
        key = c.execute('SELECT secret FROM esp32_unit_keys WHERE pcb=?', (pcb_id,)).fetchone()
        if not pcb or pcb['tipo'] != 'R2' or pcb['version'] != '30' or not key:
            raise Error('Instala online4.3 y vincula una R2 HW3.0 existente.', 400)
        if pcb['estado_ciclo'] in ('BAJA', 'FALLA'):
            raise Error('La R2 no está habilitada para programarse.', 409)
        counter = verify_info(info, bytes(key['secret']), pcb, anchor)
        prior = c.execute('SELECT * FROM android_offline_bindings WHERE pcb=?', (pcb_id,)).fetchone()
        if prior and (prior['public_key'] != info['offline_public_key'] or counter < prior['counter'] or
                      (counter == prior['counter'] and (prior['app_digest'] != info['app_sha256'] or prior['last_grant'] != info['offline_last_grant']))):
            raise Error('La identidad offline o el contador cambiaron de forma incompatible; requiere revisión.', 409)
        if c.execute('SELECT 1 FROM android_offline_bindings WHERE public_key=? AND pcb!=?', (info['offline_public_key'], pcb_id)).fetchone():
            raise Error('La identidad offline ya pertenece a otra R2.', 409)
        c.execute('''INSERT INTO android_offline_bindings VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(pcb) DO UPDATE SET counter=excluded.counter,app_digest=excluded.app_digest,
            last_grant=excluded.last_grant,info=excluded.info,revision=excluded.revision,snapshot=excluded.snapshot,
            state=excluded.state,updated=excluded.updated,operator=excluded.operator''',
                  (pcb_id, info['offline_public_key'], counter, info['app_sha256'], info['offline_last_grant'], anchor,
                   android._json(info), android._revision(c, pcb_id), android._json(android._snapshot(c, pcb_id)),
                   'bound', time.time(), operator))
        receipt_id = str(uuid.UUID(hex=info['offline_last_grant']))
        receipt = c.execute('SELECT * FROM android_offline_grants WHERE id=? AND target_pcb=?', (receipt_id, pcb_id)).fetchone()
        keep = ''
        if receipt:
            expected = json.loads(receipt['package'])
            origin = json.loads(receipt['binding_info'])
            if (counter == receipt['source_counter'] + 1 and info['app_sha256'] == expected['target_app_digest'] and
                    tuple(info[k] for k in ('nombre', 'hw', 'fw')) == tuple(expected[k] for k in ('nombre', 'hw', 'fw')) and
                    info['partition'] != origin['partition']):
                keep = receipt_id  # The matching successful boot may still be waiting for synchronization.
        c.execute("UPDATE android_offline_grants SET state='superseded',updated=? WHERE target_pcb=? AND source_counter<? AND id!=? AND state IN ('authorized','pending_verification')",
                  (time.time(), pcb_id, counter, keep))
        return _binding_public(c.execute('SELECT * FROM android_offline_bindings WHERE pcb=?', (pcb_id,)).fetchone())


def _busy(c, pcb_id, now):
    if c.execute("SELECT 1 FROM esp32_ota_jobs WHERE pcb=? AND state='prepared' AND created>?", (pcb_id, now - ota.LIFETIME)).fetchone():
        raise Error('La R2 tiene una OTA online pendiente.', 409)
    if c.execute("SELECT 1 FROM sqlite_master WHERE name='r2_programming_attempts'").fetchone() and c.execute(
            "SELECT 1 FROM r2_programming_attempts WHERE pcb=? AND state IN ('flashing','queued','running') AND created>?",
            (pcb_id, now - 600)).fetchone():
        raise Error('La R2 está programándose o verificándose en la estación.', 409)
    if c.execute("SELECT 1 FROM sqlite_master WHERE name='r2_enrollments'").fetchone() and c.execute(
            "SELECT 1 FROM r2_enrollments WHERE pcb=? AND state='prepared' AND created>?", (pcb_id, now - 600)).fetchone():
        raise Error('La R2 tiene un alta online pendiente.', 409)


def _owned(c, identifier, operator):
    row = c.execute('SELECT * FROM android_offline_grants WHERE id=? AND operator=?',
                    (android._uuid(identifier), operator)).fetchone()
    if not row:
        raise Error('Paquete offline no encontrado para este usuario.', 404)
    return row


def _public(row, include_image=True):
    value = dict(client_operation_id=row['id'], pcb_id=row['target_pcb'], firmware_id=row['firmware'],
                 state=row['state'], created=row['created'], updated=row['updated'], expires_at=row['expires_at'],
                 receive_until=row['receive_until'], revision=row['revision'], offline=True,
                 info_before=json.loads(row['info_before']) if row['info_before'] else None,
                 info_after=json.loads(row['info_after']) if row['info_after'] else None,
                 result=json.loads(row['result']) if row['result'] else None, error=row['error'])
    package = json.loads(row['package'])
    if not include_image:
        package.pop('encrypted_image', None)
        package.pop('grant', None)
    value['package'] = package
    return value


def create(identifier, pcb_id, firmware_id, phone_public_key, operator):
    identifier = android._uuid(identifier)
    _public_key(phone_public_key)
    key, root_public, anchor = _signer()
    request_hash = android._digest(dict(pcb_id=pcb_id, firmware_id=firmware_id, phone_public_key=phone_public_key))
    with db.transaction() as c:
        ensure(c)
        old = c.execute('SELECT * FROM android_offline_grants WHERE id=?', (identifier,)).fetchone()
        if old:
            if old['operator'] != operator or old['request_hash'] != request_hash:
                raise Error('El UUID ya pertenece a otra solicitud o usuario.', 409)
            return _public(old)
        if c.execute('SELECT 1 FROM android_ota_operations WHERE id=?', (identifier,)).fetchone():
            raise Error('El UUID ya pertenece a una operación online.', 409)
        now = time.time()
        c.execute("UPDATE android_offline_grants SET state='expired',updated=? WHERE state IN ('authorized','pending_verification') AND expires_at<=?", (now, now))
        binding = c.execute('SELECT * FROM android_offline_bindings WHERE pcb=?', (pcb_id,)).fetchone()
        pcb = inv.get_pcb(pcb_id, conn=c)
        secret = c.execute('SELECT secret FROM esp32_unit_keys WHERE pcb=?', (pcb_id,)).fetchone()
        if not binding or binding['state'] != 'bound' or not pcb or not secret:
            raise Error('Primero vincula la identidad offline mediante INFO4.3 auténtico.', 409)
        if pcb['tipo'] != 'R2' or pcb['version'] != '30' or pcb['estado_ciclo'] in ('BAJA', 'FALLA'):
            raise Error('La R2 no está habilitada para offline.', 409)
        snapshot = android._json(android._snapshot(c, pcb_id))
        revision = android._revision(c, pcb_id)
        if binding['revision'] != revision or binding['snapshot'] != snapshot:
            raise Error('El inventario cambió; vuelve a leer y vincular la R2.', 409)
        if binding['counter'] >= 0xFFFFFFFF:
            raise Error('Contador offline agotado; requiere revisión.', 409)
        _busy(c, pcb_id, now)
        if c.execute("SELECT 1 FROM android_offline_grants WHERE target_pcb=? AND state IN ('authorized','pending_verification')", (pcb_id,)).fetchone():
            raise Error('La R2 ya tiene un paquete offline autorizado.', 409)
        row = next((r for r in fw.rows(c, '30', 'R2') if r['id'] == firmware_id), None)
        if not row:
            raise Error('Firmware compatible no encontrado.')
        raw = bytes(row['image'])
        if hashlib.sha256(raw).hexdigest() != row['sha256']:
            raise Error('La imagen guardada no coincide con su hash.')
        meta, _, layout = fw.inspect(raw)
        app = raw[layout['start']:layout['end']]
        if (ota.version(meta['fw']) < (4, 3) or meta['hw'] != '3.0' or meta['module'] != 'ESP32-WROOM-32E-N4' or
                meta['schema'] != 2 or meta['ota_protocol'] != 1 or not meta.get('exact_name') or MARKER not in app or root_public not in app):
            raise Error('Offline requiere una plantilla4.3 autorizada con protocolo y ancla compatibles.')
        image, meta = fw.personalize(raw, pcb['nombre'], bytes(secret['secret']))
        application = image[layout['start']:layout['end']]
        grant_id = uuid.UUID(identifier).bytes
        iv = secrets.token_bytes(16)
        transfer = hashlib.sha256(application).digest()
        target = application[-32:]
        body = (MAGIC + grant_id + bytes.fromhex(binding['public_key']) + bytes.fromhex(phone_public_key) + iv +
                struct.pack('<I', binding['counter']) + bytes.fromhex(binding['app_digest']) + transfer + target +
                struct.pack('<I', len(application)) + ota.fixed(meta['nombre'], 24) + ota.fixed(meta['hw'], 8) +
                ota.fixed(meta['fw'], 16) + ota.mac(json.loads(binding['info'])['mac']) + bytes.fromhex(anchor))
        assert len(body) == 344
        grant = body + _sign(key, body)
        image_key = hmac.new(bytes(secret['secret']), DATA_LABEL + grant_id, hashlib.sha256).digest()
        cipher = Cipher(algorithms.AES(image_key), modes.CTR(iv)).encryptor()
        encrypted = cipher.update(application) + cipher.finalize()
        package = dict(offline_protocol=1, grant=base64.b64encode(grant).decode('ascii'),
                       encrypted_image=base64.b64encode(encrypted).decode('ascii'), bytes=len(application),
                       nombre=meta['nombre'], hw=meta['hw'], fw=meta['fw'], mac=json.loads(binding['info'])['mac'].upper(),
                       source_counter=binding['counter'], source_app_digest=binding['app_digest'],
                       target_app_digest=target.hex(), transfer_sha256=transfer.hex(), encrypted_sha256=hashlib.sha256(encrypted).hexdigest(), device_public_key=binding['public_key'],
                       phone_public_key=phone_public_key, anchor_key_id=anchor)
        c.execute('''INSERT INTO android_offline_grants
            (id,pcb,target_pcb,firmware,operator,state,source_counter,created,updated,expires_at,receive_until,
             revision,snapshot,binding_info,request_hash,package) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                  (identifier, pcb_id, pcb_id, firmware_id, operator, 'authorized', binding['counter'], now, now,
                   now + PACKAGE_TTL, now + RECEIVE_TTL, revision, snapshot, binding['info'], request_hash, android._json(package)))
        c.execute('INSERT INTO android_offline_events(operation,created,kind,evidence) VALUES(?,?,?,?)',
                  (identifier, now, 'authorized', android._json(dict(phone_public_key=phone_public_key, source_counter=binding['counter']))))
        return _public(_owned(c, identifier, operator))


def get(identifier, operator):
    with db.transaction() as c:
        ensure(c)
        return _public(_owned(c, identifier, operator))


def history(operator, limit=50, offset=0):
    with db.transaction() as c:
        ensure(c)
        count = c.execute('SELECT COUNT(*) FROM android_offline_grants WHERE operator=?', (operator,)).fetchone()[0]
        rows = c.execute('SELECT * FROM android_offline_grants WHERE operator=? ORDER BY created DESC,id LIMIT ? OFFSET ?',
                         (operator, limit, offset)).fetchall()
        return dict(items=[_public(r, False) for r in rows], total=count, limit=limit, offset=offset)


def _verify_result(c, row, before, after, phone_signature):
    package = json.loads(row['package'])
    snapshot = json.loads(row['snapshot'])['pcb']
    secret = c.execute('SELECT secret FROM esp32_unit_keys WHERE pcb=?', (row['target_pcb'],)).fetchone()
    if not secret or not snapshot:
        raise Error('La identidad de unidad ya no está disponible.')
    root_public, anchor = _anchor()
    # Verify the stored grant itself, not merely its deserialized metadata.
    grant = base64.b64decode(package['grant'], validate=True)
    if len(grant) != 408:
        raise Error('Autorización offline guardada inválida.')
    _verify(_public_key(root_public.hex()), grant[344:].hex(), grant[:344])
    expected_id = uuid.UUID(row['id']).bytes
    if (grant[:16] != MAGIC or grant[16:32] != expected_id or grant[32:97].hex() != package['device_public_key'] or
            grant[97:162].hex() != package['phone_public_key'] or struct.unpack_from('<I', grant, 178)[0] != package['source_counter'] or
            grant[182:214].hex() != package['source_app_digest'] or grant[214:246].hex() != package['transfer_sha256'] or
            grant[246:278].hex() != package['target_app_digest'] or struct.unpack_from('<I', grant, 278)[0] != package['bytes'] or
            grant[282:306] != ota.fixed(package['nombre'], 24) or grant[306:314] != ota.fixed(package['hw'], 8) or
            grant[314:330] != ota.fixed(package['fw'], 16) or grant[330:336] != ota.mac(package['mac']) or
            grant[336:344].hex() != anchor or package['anchor_key_id'] != anchor or package['source_counter'] != row['source_counter']):
        raise Error('Los metadatos no coinciden con la autorización offline firmada.')
    source = verify_info(before, bytes(secret['secret']), snapshot, anchor)
    counter = verify_info(after, bytes(secret['secret']), snapshot, anchor)
    if (before['offline_public_key'] != package['device_public_key'] or after['offline_public_key'] != package['device_public_key'] or
            source != package['source_counter'] or counter != source + 1 or
            before['app_sha256'] != package['source_app_digest'] or after['app_sha256'] != package['target_app_digest'] or
            after['offline_last_grant'] != expected_id.hex() or after['nonce'] == before['nonce'] or
            after['partition'] == before['partition'] or
            tuple(after[k] for k in ('nombre', 'hw', 'fw')) != tuple(package[k] for k in ('nombre', 'hw', 'fw')) or
            ota.mac(before['mac']) != ota.mac(package['mac']) or ota.mac(after['mac']) != ota.mac(package['mac'])):
        raise Error('La R2 no confirmó el nuevo arranque, imagen, contador y recibo de este paquete.')
    if phone_signature:
        _verify(_public_key(package['phone_public_key']), phone_signature,
                SESSION_LABEL + expected_id + bytes.fromhex(before['nonce']) + hashlib.sha256(grant).digest())
    return package


def report(identifier, body, operator):
    outcome = body.get('outcome', 'verified')
    if outcome not in ('verified', 'failed', 'cancelled', 'unknown'):
        raise Error('Resultado offline inválido.', 422)
    if outcome == 'verified' and (not isinstance(body.get('before'), dict) or not isinstance(body.get('after'), dict)):
        raise Error('Se requieren INFO4.3 auténticos anteriores y posteriores.', 422)
    report_hash = android._digest(body)
    error_to_raise = None
    with db.transaction() as c:
        ensure(c)
        row = _owned(c, identifier, operator)
        if row['state'] in TERMINAL:
            if row['report_hash'] != report_hash:
                raise Error('La operación offline ya recibió un resultado diferente.', 409)
            return _public(row, False)
        if row['report_hash'] == report_hash:
            return _public(row, False)
        now = time.time()
        error = (body.get('error') or '')[:1000] or None
        result, state = None, 'pending_verification'
        if outcome == 'verified':
            c.execute('SAVEPOINT android_offline_apply')
            try:
                package = _verify_result(c, row, body['before'], body['after'], body.get('phone_signature'))
                binding = c.execute('SELECT * FROM android_offline_bindings WHERE pcb=?', (row['target_pcb'],)).fetchone()
                changed = (android._revision(c, row['target_pcb']) != row['revision'] or
                           android._json(android._snapshot(c, row['target_pcb'])) != row['snapshot'] or
                           not binding or binding['counter'] > package['source_counter'] + 1 or
                           (binding['counter'] == package['source_counter'] + 1 and binding['last_grant'] != uuid.UUID(row['id']).hex))
                superseded = c.execute('SELECT 1 FROM android_offline_grants WHERE target_pcb=? AND source_counter=? AND created>? AND id!=?',
                                       (row['target_pcb'], row['source_counter'], row['created'], row['id'])).fetchone()
                historical = changed or bool(superseded) or now > row['expires_at'] or row['state'] in ('expired', 'superseded')
                if historical:
                    state = 'conflict' if changed or superseded else 'accepted_history'
                    result = dict(verified=False, inventory_updated=False, accepted_history=True,
                                  reason='inventory_or_counter_changed' if changed else 'authorization_superseded' if superseded else 'authorization_expired')
                    error = 'Evidencia auténtica conservada; no reemplaza el estado actual.'
                else:
                    payload = dict(nombre=package['nombre'], hw=package['hw'], fw=package['fw'], mac=package['mac'],
                                   app_sha256=package['target_app_digest'])
                    result = dict(ota.record_verified(c, inv.get_pcb(row['target_pcb'], conn=c), payload, body['after'], operator,
                                                      row['id'], 'ble_offline', 'ANDROID_OFFLINE_VERIFICADA'), inventory_updated=True)
                    state = 'verified'
                if binding and (body['after']['offline_counter'] > binding['counter'] or
                                (body['after']['offline_counter'] == binding['counter'] and
                                 body['after']['offline_last_grant'] == binding['last_grant'] and
                                 body['after']['app_sha256'] == binding['app_digest'])):
                    c.execute('''UPDATE android_offline_bindings SET counter=?,app_digest=?,last_grant=?,info=?,revision=?,snapshot=?,state=?,updated=? WHERE pcb=?''',
                              (body['after']['offline_counter'], body['after']['app_sha256'], body['after']['offline_last_grant'],
                               android._json(body['after']), android._revision(c, row['target_pcb']), android._json(android._snapshot(c, row['target_pcb'])),
                               'review' if historical else 'bound', now, row['target_pcb']))
                c.execute('RELEASE android_offline_apply')
            except (ValueError, KeyError, TypeError) as exc:
                c.execute('ROLLBACK TO android_offline_apply')
                c.execute('RELEASE android_offline_apply')
                error = str(exc)[:1000]
                error_to_raise = Error(error, 400)
                report_hash = None
        elif outcome in ('failed', 'cancelled'):
            state, result = outcome, dict(verified=False, inventory_updated=False)
        c.execute('''UPDATE android_offline_grants SET state=?,updated=?,info_before=?,info_after=?,report_hash=?,result=?,error=? WHERE id=?''',
                  (state, now, android._json(body.get('before')) if body.get('before') else None,
                   android._json(body.get('after')) if body.get('after') else None, report_hash,
                   android._json(result) if result else None, error, row['id']))
        c.execute('INSERT INTO android_offline_events(operation,created,kind,evidence) VALUES(?,?,?,?)',
                  (row['id'], now, 'invalid_evidence' if error_to_raise else state, android._json(body)))
        value = _public(_owned(c, row['id'], operator), False)
    if error_to_raise:
        raise error_to_raise
    return value
