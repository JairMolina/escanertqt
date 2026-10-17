"""Durable Android coordination around the existing authenticated BLE OTA service.

The existing SQLite, catalogue, users and unit credentials remain authoritative.
Stored prepared bytes authorize one already observed nonce, never a new offline
session. A historical authenticated reboot is distinct from current inventory.
"""
import hashlib
import json
import os
import re
import subprocess
import time
import uuid
import zipfile
from io import BytesIO
from pathlib import Path

from app.database import db, inventario as inv
from app.services import esp32_firmware as fw, esp32_ota as ota

SCHEMA_VERSION = 1
TERMINAL = {'verified', 'migration_required', 'failed', 'cancelled', 'conflict', 'accepted_history'}


class AndroidError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False)


def _digest(value):
    return hashlib.sha256(_json(value).encode('ascii')).hexdigest()


def _uuid(value):
    try:
        parsed = uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError) as exc:
        raise AndroidError('UUID de operación inválido.', 422) from exc
    if parsed.int == 0:
        raise AndroidError('UUID de operación inválido.', 422)
    return str(parsed)


def ensure(c):
    """An additive, independently versioned schema in the production database."""
    ota.ensure(c)
    c.execute('CREATE TABLE IF NOT EXISTS android_schema (version INTEGER NOT NULL)')
    schema = c.execute('SELECT version FROM android_schema').fetchone()
    if schema and schema['version'] != SCHEMA_VERSION:
        raise AndroidError('Esquema Android incompatible; requiere revisión del servidor.', 503)
    c.execute('''CREATE TABLE IF NOT EXISTS android_device_revisions (
        pcb INTEGER PRIMARY KEY REFERENCES pcb_inventario(id) ON DELETE CASCADE,
        revision INTEGER NOT NULL DEFAULT 0 CHECK(revision >= 0))''')
    if not schema:
        c.execute('INSERT OR IGNORE INTO android_device_revisions(pcb) SELECT id FROM pcb_inventario')
    # All inventory writers participate, including web/serial writes in one second
    # and a change later reverted to exactly the same observable values.
    c.execute('''CREATE TRIGGER IF NOT EXISTS android_pcb_revision_insert AFTER INSERT ON pcb_inventario
        BEGIN INSERT OR IGNORE INTO android_device_revisions(pcb) VALUES(NEW.id); END''')
    c.execute('''CREATE TRIGGER IF NOT EXISTS android_pcb_revision_update AFTER UPDATE ON pcb_inventario
        BEGIN INSERT INTO android_device_revisions(pcb,revision) VALUES(NEW.id,1)
        ON CONFLICT(pcb) DO UPDATE SET revision=revision+1; END''')
    c.execute('''CREATE TABLE IF NOT EXISTS android_ota_operations (
        id TEXT PRIMARY KEY, pcb INTEGER REFERENCES pcb_inventario(id) ON DELETE SET NULL,
        target_pcb INTEGER NOT NULL, firmware TEXT NOT NULL REFERENCES esp32_firmwares(id),
        ota_job TEXT NOT NULL UNIQUE REFERENCES esp32_ota_jobs(id),
        operator TEXT NOT NULL, state TEXT NOT NULL,
        created REAL NOT NULL, updated REAL NOT NULL, expires_at REAL NOT NULL,
        revision INTEGER NOT NULL, snapshot TEXT NOT NULL, request_hash TEXT NOT NULL,
        info_before TEXT NOT NULL, prepared TEXT NOT NULL,
        info_after TEXT, report TEXT, report_hash TEXT, result TEXT, error TEXT)''')
    c.execute('CREATE INDEX IF NOT EXISTS android_ota_owner_history ON android_ota_operations(operator,created DESC)')
    c.execute('''CREATE TABLE IF NOT EXISTS android_ota_events (
        id INTEGER PRIMARY KEY, operation TEXT NOT NULL REFERENCES android_ota_operations(id) ON DELETE CASCADE,
        created REAL NOT NULL, kind TEXT NOT NULL, evidence TEXT NOT NULL)''')
    if not schema:
        c.execute('INSERT INTO android_schema(version) VALUES(?)', (SCHEMA_VERSION,))


def _snapshot(c, pcb_id):
    pcb = inv.get_pcb(pcb_id, conn=c)
    programmed = None
    if c.execute("SELECT 1 FROM sqlite_master WHERE name='r2_programming_state'").fetchone():
        row = c.execute('SELECT * FROM r2_programming_state WHERE pcb=?', (pcb_id,)).fetchone()
        programmed = dict(row) if row else None
    return {'pcb': pcb, 'programming': programmed}


def _revision(c, pcb_id):
    row = c.execute('SELECT revision FROM android_device_revisions WHERE pcb=?', (pcb_id,)).fetchone()
    return row['revision'] if row else None


def _capability(c, pcb):
    current = pcb.get('firmware') or ''
    known_old = bool(current and re.fullmatch(r'\d+(?:\.\d+)+', current) and ota.version(current) < (4, 0))
    key = c.execute('SELECT 1 FROM esp32_unit_keys WHERE pcb=?', (pcb['id'],)).fetchone()
    binding = None
    if c.execute("SELECT 1 FROM sqlite_master WHERE name='android_offline_bindings'").fetchone():
        binding = c.execute("SELECT 1 FROM android_offline_bindings WHERE pcb=? AND state='bound' AND revision=?", (pcb['id'], _revision(c, pcb['id']))).fetchone()
    firmware43 = bool(current and re.fullmatch(r'\d+(?:\.\d+)+', current) and ota.version(current) >= (4, 3))
    return dict(eligible=not known_old, current_fw=current, requires_serial=known_old,
                requires_probe=not known_old, reason='legacy' if known_old else 'enrollment' if not key else 'probe',
                needs_enrollment=not bool(key), offline=bool(binding),
                offline_protocol=1 if binding else 0,
                offline_binding_required=firmware43 and not bool(binding), continue_prepared_session=True)


def _device(c, pcb):
    return dict(pcb_id=pcb['id'], nombre=pcb['nombre'], hw=pcb['version'], mac=pcb.get('mac'),
                firmware=pcb.get('firmware'), tarjeta_id=pcb.get('tarjeta_id'),
                id_tarjeta_num=pcb.get('id_tarjeta_num'), estado_ciclo=pcb['estado_ciclo'],
                revision=_revision(c, pcb['id']), capability=_capability(c, pcb),
                links=dict(detail=f'/api/android/devices/{pcb["id"]}',
                           capability=f'/api/android/devices/{pcb["id"]}/capability',
                           firmwares=f'/api/android/firmwares?hw={pcb["version"]}'))


def devices(q='', limit=50, offset=0):
    with db.transaction() as c:
        ensure(c)
        found = inv.listar_pcb(tipo='R2', q=q, limit=limit, offset=offset, conn=c)
        return dict(items=[_device(c, p) for p in found['items']], total=found['total'], limit=limit, offset=offset)


def device(pcb_id):
    with db.transaction() as c:
        ensure(c)
        pcb = inv.get_pcb(pcb_id, conn=c)
        if not pcb or pcb['tipo'] != 'R2':
            raise AndroidError('R2 no encontrada.', 404)
        return _device(c, pcb)


def _owned(c, identifier, operator):
    row = c.execute('SELECT * FROM android_ota_operations WHERE id=? AND operator=?',
                    (_uuid(identifier), operator)).fetchone()
    if not row:
        raise AndroidError('Operación no encontrada para este usuario.', 404)
    return row


def _public(row, include_prepared=True):
    value = dict(client_operation_id=row['id'], pcb_id=row['target_pcb'], firmware_id=row['firmware'],
                 state=row['state'], created=row['created'], updated=row['updated'], expires_at=row['expires_at'],
                 revision=row['revision'], info_before=json.loads(row['info_before']),
                 info_after=json.loads(row['info_after']) if row['info_after'] else None,
                 result=json.loads(row['result']) if row['result'] else None, error=row['error'],
                 offline=False, continue_prepared_session=True)
    if include_prepared:
        value['prepared'] = json.loads(row['prepared'])
    return value


def prepare(identifier, pcb_id, firmware_id, info, operator):
    identifier = _uuid(identifier)
    request_hash = _digest(dict(pcb_id=pcb_id, firmware_id=firmware_id, device=info))
    with db.transaction() as c:
        ensure(c)
        old = c.execute('SELECT * FROM android_ota_operations WHERE id=?', (identifier,)).fetchone()
        if old:
            if old['operator'] != operator:
                raise AndroidError('UUID de operación no disponible.', 409)
            if old['request_hash'] != request_hash:
                raise AndroidError('El UUID ya pertenece a otra solicitud.', 409)
            return _public(old)
        if c.execute("SELECT 1 FROM sqlite_master WHERE name='android_offline_grants'").fetchone():
            if c.execute('SELECT 1 FROM android_offline_grants WHERE id=?', (identifier,)).fetchone():
                raise AndroidError('El UUID ya pertenece a una operación offline.', 409)
        snapshot = _snapshot(c, pcb_id)
        if not snapshot['pcb'] or snapshot['pcb']['tipo'] != 'R2':
            raise AndroidError('R2 no encontrada.', 404)
        if snapshot['pcb']['estado_ciclo'] in ('BAJA', 'FALLA'):
            raise AndroidError('La R2 está dada de baja o marcada con falla.', 409)
        revision = _revision(c, pcb_id)
        try:
            prepared = ota.prepare(pcb_id, firmware_id, info, operator, conn=c)
        except ValueError as exc:
            raise AndroidError(str(exc), 409 if 'pendiente' in str(exc) or 'estación' in str(exc) else 400) from exc
        now = time.time()
        c.execute('''INSERT INTO android_ota_operations
            (id,pcb,target_pcb,firmware,ota_job,operator,state,created,updated,expires_at,revision,snapshot,
             request_hash,info_before,prepared) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                  (identifier, pcb_id, pcb_id, firmware_id, prepared['job_id'], operator, 'prepared', now, now,
                   now + ota.LIFETIME, revision, _json(snapshot), request_hash, _json(info), _json(prepared)))
        c.execute('INSERT INTO android_ota_events(operation,created,kind,evidence) VALUES(?,?,?,?)',
                  (identifier, now, 'prepared', _json(info)))
        return _public(_owned(c, identifier, operator))


def operation(identifier, operator):
    with db.transaction() as c:
        ensure(c)
        row = _owned(c, identifier, operator)
        value = _public(row)
        value['events'] = [dict(created=r['created'], kind=r['kind'], evidence=json.loads(r['evidence']))
                           for r in c.execute('SELECT created,kind,evidence FROM android_ota_events WHERE operation=? ORDER BY id', (row['id'],))]
        return value


def history(operator, limit=50, offset=0):
    with db.transaction() as c:
        ensure(c)
        total = c.execute('SELECT COUNT(*) FROM android_ota_operations WHERE operator=?', (operator,)).fetchone()[0]
        rows = c.execute('SELECT * FROM android_ota_operations WHERE operator=? ORDER BY created DESC,id LIMIT ? OFFSET ?',
                         (operator, limit, offset)).fetchall()
        return dict(items=[_public(r, False) for r in rows], total=total, limit=limit, offset=offset)


def report(identifier, body, operator):
    """Persist evidence and compare-and-set inventory within the SAME write lock."""
    if body.get('outcome') not in ('verified', 'failed', 'cancelled', 'unknown'):
        raise AndroidError('Resultado inválido.', 422)
    outcome = body['outcome']
    info = body.get('device')
    if outcome == 'verified' and not isinstance(info, dict):
        raise AndroidError('La verificación requiere INFO autenticado posterior al reinicio.', 422)
    report_hash = _digest(body)
    error_to_raise = None
    with db.transaction() as c:
        ensure(c)
        row = _owned(c, identifier, operator)
        if row['state'] in TERMINAL:
            if row['report_hash'] != report_hash:
                raise AndroidError('La operación ya recibió un resultado diferente.', 409)
            return _public(row)
        if row['report_hash'] == report_hash:
            return _public(row)
        # An unknown transport result remains recoverable. A terminal report is
        # immutable; a later, authentic reboot may resolve pending verification.
        now = time.time()
        result, state, error = None, 'pending_verification', (body.get('error') or '')[:1000] or None
        if outcome == 'verified':
            c.execute('SAVEPOINT android_apply_result')
            job = c.execute('SELECT * FROM esp32_ota_jobs WHERE id=?', (row['ota_job'],)).fetchone()
            changed = (_revision(c, row['target_pcb']) != row['revision'] or
                       _json(_snapshot(c, row['target_pcb'])) != row['snapshot'])
            try:
                if not job or job['operator'] != operator:
                    raise ValueError('Autorización OTA no disponible.')
                # Preserve authentic history without overwriting a later web or
                # serial result, or pretending an expired authorization is live.
                if changed or now > row['expires_at'] or now - job['created'] > ota.LIFETIME or job['state'] != 'prepared':
                    ota.validate_result(c, job, info, json.loads(row['snapshot'])['pcb'])
                    state = 'conflict' if changed or job['state'] != 'prepared' else 'accepted_history'
                    result = dict(verified=False, accepted_history=True, inventory_updated=False,
                                  reason='inventory_changed' if changed else 'authorization_closed' if job['state'] != 'prepared' else 'authorization_expired')
                    error = 'Evidencia auténtica conservada; el estado actual requiere revisión.'
                    if job['state'] == 'prepared':
                        ota.cancel(row['ota_job'], operator, '', conn=c)
                else:
                    result = ota.finish(row['ota_job'], info, operator, conn=c)
                    state = 'verified' if result.get('verified') is True else 'migration_required'
                    result = dict(result, inventory_updated=result.get('verified') is True)
                c.execute('RELEASE android_apply_result')
            except (ValueError, KeyError, TypeError) as exc:
                c.execute('ROLLBACK TO android_apply_result')
                c.execute('RELEASE android_apply_result')
                error = str(exc)[:1000]
                error_to_raise = AndroidError(error, 400)
                # Invalid evidence never becomes an immutable success/failure.
                report_hash = None
        elif outcome in ('failed', 'cancelled'):
            ota.cancel(row['ota_job'], operator, error or outcome, conn=c)
            state = outcome
            result = dict(verified=False, inventory_updated=False)
        c.execute('''UPDATE android_ota_operations SET state=?,updated=?,info_after=?,report=?,report_hash=?,result=?,error=?
                     WHERE id=?''',
                  (state, now, _json(info) if info else None, _json(body), report_hash,
                   _json(result) if result else None, error, row['id']))
        c.execute('INSERT INTO android_ota_events(operation,created,kind,evidence) VALUES(?,?,?,?)',
                  (row['id'], now, 'invalid_evidence' if error_to_raise else state, _json(body)))
        value = _public(_owned(c, row['id'], operator))
    if error_to_raise:
        raise error_to_raise
    return value


def apk_package():
    """Serve only an explicitly approved APK, verified with configured SDK tools.

    Signing keys are never consumed or created here. The directory and Android
    SDK verification tools are operator configuration, not request input.
    """
    disabled = AndroidError('Descarga Android deshabilitada: no hay APK aprobado y verificado.', 503)
    try:
        directory = Path(os.environ['TQT_ANDROID_APK_DIR']).resolve(strict=True)
        root = fw.ROOT.resolve()
        if (not directory.is_dir() or directory == root or root in directory.parents or
                any((p / '.git').exists() for p in (directory, *directory.parents))):
            raise disabled
        manifest_path = directory / 'manifest.json'
        if manifest_path.resolve(strict=True).parent != directory or manifest_path.stat().st_size > 16384:
            raise disabled
        meta = json.loads(manifest_path.read_text(encoding='utf-8'))
        required = ('filename', 'package_name', 'version_code', 'version_name', 'min_sdk', 'sha256', 'certificate_sha256')
        if meta.get('approved') is not True or any(k not in meta for k in required):
            raise disabled
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,120}\.apk', meta['filename']):
            raise disabled
        if not re.fullmatch(r'[a-zA-Z]\w*(?:\.[a-zA-Z]\w*)+', meta['package_name']):
            raise disabled
        if type(meta['version_code']) is not int or meta['version_code'] < 1 or type(meta['min_sdk']) is not int or meta['min_sdk'] < 23:
            raise disabled
        if not isinstance(meta['version_name'], str) or not 1 <= len(meta['version_name']) <= 80:
            raise disabled
        for key in ('sha256', 'certificate_sha256'):
            if not isinstance(meta[key], str) or not re.fullmatch('[a-f0-9]{64}', meta[key]):
                raise disabled
        apk = directory / meta['filename']
        if apk.resolve(strict=True).parent != directory or not 0 < apk.stat().st_size <= 134217728:
            raise disabled
        raw = apk.read_bytes()
        if hashlib.sha256(raw).hexdigest() != meta['sha256']:
            raise disabled
        with zipfile.ZipFile(BytesIO(raw)) as archive:
            entries = archive.infolist()
            if len(entries) > 30000 or sum(r.file_size for r in entries) > 536870912:
                raise disabled
            names = {r.filename for r in entries}
            if (len(names) != len(entries) or any(r.flag_bits & 1 or r.filename.startswith(('/', '\\')) or
                    '..' in r.filename.replace('\\', '/').split('/') for r in entries) or
                    not {'AndroidManifest.xml', 'classes.dex'}.issubset(names) or archive.testzip() is not None):
                raise disabled
        outputs = []
        for env, arguments in (('TQT_ANDROID_APKSIGNER', ['verify', '--verbose', '--print-certs']),
                               ('TQT_ANDROID_AAPT', ['dump', 'badging'])):
            tool = Path(os.environ[env])
            if not tool.is_absolute() or not tool.is_file():
                raise disabled
            completed = subprocess.run([str(tool), *arguments, str(apk)], capture_output=True, text=True,
                                       timeout=30, check=False, shell=False)
            if completed.returncode != 0:
                raise disabled
            outputs.append(completed.stdout)
        certs = re.findall(r'Signer #\d+ certificate SHA-256 digest: ([0-9a-fA-F]{64})', outputs[0])
        if not certs or {v.lower() for v in certs} != {meta['certificate_sha256']}:
            raise disabled
        package = re.search(r"^package: name='([^']+)' versionCode='([^']+)' versionName='([^']+)'", outputs[1], re.MULTILINE)
        sdk = re.search(r"^sdkVersion:'(\d+)'", outputs[1], re.MULTILINE)
        if not package or not sdk or package.groups() != (meta['package_name'], str(meta['version_code']), meta['version_name']) or int(sdk[1]) != meta['min_sdk']:
            raise disabled
        # Re-read after SDK verification to close a local replacement race. The
        # returned bytes, rather than a later file open, are sent to the client.
        if apk.read_bytes() != raw:
            raise disabled
        public = {k: meta[k] for k in required}
        public.update(available=True, bytes=len(raw), download_url='/api/android/apk/download')
        return public, raw
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RuntimeError, NotImplementedError,
            zipfile.BadZipFile, subprocess.SubprocessError) as exc:
        raise disabled from exc
