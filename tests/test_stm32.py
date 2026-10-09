import _aislamiento as iso
import json
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.database import db, inventario as inv
from app.services import stm32_programming as s
from app.services import tqt_hex as hx
from app.main import app
import sys
sys.modules['tqt_hex'] = hx
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'station'))
import agent


class STM32Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init_db()

    def setUp(self):
        self.t = iso.crear_par(iso.nuevo_lote()['id'], version='30')
        # Deliberately pair a different R2 serial.
        r2 = inv.registrar_manual('R2', '30', iso.num_unico())['pcbs'][0]
        inv.confirmar_recepcion([r2['id']])
        inv.set_mac(r2['id'], iso.mac_unica())
        inv.asignar_pcb(self.t['id'], 'R2', r2['id'])
        self.t = db.get_tarjeta_by_id(self.t['id'])
        self.st = s.station_create('Prueba', 'operador@test.mx')
        s.claim(self.st['id'])

    def prepared(self):
        return s.preview(self.t['r1']['id'])

    def queued(self):
        d, _ = self.prepared()
        return s.create_job(self.t['r1']['id'], self.st['id'], d['hex_sha256'], 'operador@test.mx', True)

    def test_r1_r2_independientes_y_hex_real(self):
        d, image = self.prepared()
        self.assertNotEqual(self.t['r1']['serie'], d['identity']['id_r'])
        self.assertEqual(d['identity']['id_r'], self.t['r2']['serie'])
        self.assertEqual(d['identity']['mac_r'], self.t['r2']['mac'].upper())
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'image.hex';p.write_bytes(image.encode())
            mem,_=hx.leer_hex(p)
            self.assertEqual(hx.leer_identidad(mem),d['identity'])
            base,_,_=s.firmware()
            self.assertEqual({a:b for a,b in mem.items() if a<hx.IDENTITY_BEGIN}, base)
            agent.validate(dict(payload=d,hex=image),Path(temp))

    def test_missing_r2_mac_rejected(self):
        with db.get_db() as c:
            c.execute('UPDATE pcb_inventario SET mac=NULL WHERE id=?',(self.t['r2']['id'],))
        with self.assertRaises(ValueError):self.prepared()

    def test_incompatible_hw_rejected(self):
        with db.get_db() as c:
            c.execute("UPDATE pcb_inventario SET version='31' WHERE id=?",(self.t['r1']['id'],))
        with self.assertRaises(ValueError):self.prepared()

    def test_stale_preview_rejected(self):
        d,_=self.prepared()
        inv.set_mac(self.t['r2']['id'],iso.mac_unica())
        with self.assertRaises(ValueError):s.create_job(self.t['r1']['id'],self.st['id'],d['hex_sha256'],'test',True)

    def test_confirmation_from_web_replaces_console_input(self):
        d, _ = self.prepared()
        with self.assertRaises(ValueError):
            s.create_job(self.t['r1']['id'], self.st['id'], d['hex_sha256'], 'test')
        j = self.queued()
        work = s.claim(self.st['id'])
        self.assertEqual(work['payload']['confirmation']['pcb_id'], self.t['r1']['id'])
        with patch('builtins.input', side_effect=AssertionError('No console input allowed')), patch.object(agent, 'flash', return_value={'verified': True}) as flash:
            self.assertTrue(agent.execute(work, 'mock')['verified'])
            flash.assert_called_once()
        work['payload']['confirmation']['nombre'] = 'TQT_R1_V30_9999'
        with patch.object(agent, 'flash') as flash:
            with self.assertRaises(ValueError): agent.execute(work, 'mock')
            flash.assert_not_called()

    def test_legacy_job_without_web_confirmation_never_flashes(self):
        d, image = self.prepared()
        with patch.object(agent, 'flash') as flash:
            with self.assertRaises(ValueError): agent.execute(dict(payload=d, hex=image), 'mock')
            flash.assert_not_called()

    def test_claim_once_concurrency_and_changed_inventory(self):
        j=self.queued()
        with self.assertRaises(ValueError):self.queued()
        inv.set_mac(self.t['r2']['id'],iso.mac_unica())
        self.assertIsNone(s.claim(self.st['id']))
        self.assertEqual(s.job(j['id'])['state'],'failed')

    def test_verified_and_replay_rejected(self):
        j=self.queued();work=s.claim(self.st['id'])
        self.assertIsNone(s.claim(self.st['id']))
        result=dict(verified=True,hex_sha256=work['payload']['hex_sha256'],identity_sha256=work['payload']['identity_sha256'],uid='123456789012123456789012')
        self.assertEqual(s.finish(self.st['id'],j['id'],result)['state'],'verified')
        self.assertEqual(inv.get_pcb(self.t['r1']['id'])['firmware'],'4.3')
        self.assertEqual(s.finish(self.st['id'],j['id'],result)['state'],'verified')
        with self.assertRaises(ValueError):s.finish(self.st['id'],j['id'],dict(verified=False))

    def test_wrong_verification_not_success(self):
        j=self.queued();s.claim(self.st['id'])
        self.assertEqual(s.finish(self.st['id'],j['id'],dict(verified=True,hex_sha256='wrong'))['state'],'failed')

    def test_station_token_and_job_isolation(self):
        with self.assertRaises(ValueError):s.station_auth('invalid')
        self.assertEqual(s.station_auth(self.st['token'])['id'],self.st['id'])
        j=self.queued();s.claim(self.st['id'])
        with self.assertRaises(ValueError):s.finish('different',j['id'],{})

    def test_progress_is_owned_monotonic_and_does_not_confirm_firmware(self):
        j = self.queued()
        c = iso.cliente_sin_sesion(app)
        url = '/api/stm32/agent/jobs/'+j['id']+'/progress'
        self.assertEqual(c.post(url, json={'stage':'reading'}).status_code, 401)
        headers = {'Authorization':'Bearer '+self.st['token']}
        self.assertEqual(c.post(url, headers=headers, json={'stage':'reading'}).status_code, 400)
        s.claim(self.st['id'])
        with self.assertRaises(ValueError): s.progress('another', j['id'], 'writing')
        self.assertEqual(c.post(url, headers=headers, json={'stage':'reading'}).status_code, 200)
        self.assertEqual(s.job(j['id'])['payload']['progress']['stage'], 'reading')
        self.assertEqual(s.job(j['id'])['state'], 'running')
        self.assertNotEqual(inv.get_pcb(self.t['r1']['id'])['firmware'], '4.3')
        self.assertEqual(c.post(url, headers=headers, json={'stage':'writing'}).status_code, 400)
        self.assertEqual(c.post(url, headers=headers, json={'stage':'invalid'}).status_code, 422)
        s.finish(self.st['id'], j['id'], {'verified':False})
        self.assertEqual(c.post(url, headers=headers, json={'stage':'reporting'}).status_code, 400)

    def test_commander_hides_windows_console(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as temp, patch.object(agent.subprocess, 'run', return_value=SimpleNamespace(returncode=0,stdout='ok',stderr='')) as run:
            agent.commander('JLink.exe', Path(temp), ['q'])
            if agent.os.name == 'nt':
                self.assertEqual(run.call_args.kwargs['creationflags'], agent.subprocess.CREATE_NO_WINDOW)
            self.assertIn('-NoGui', run.call_args.args[0])

    def test_agent_checks_readback_without_hardware(self):
        d,image=self.prepared();work=dict(payload=d,hex=image)
        def fake(exe,directory,commands,serial):
            if any('savebin readback.bin' in x for x in commands):
                mem,_=hx.leer_hex(directory/'firmware.hex'); raw=bytearray([255])*0x80000
                for a,b in mem.items():raw[a-hx.FLASH_BEGIN]=b
                (directory/'readback.bin').write_bytes(raw)
                # Commander parses sizes as hexadecimal, including an unprefixed 12.
                uid_command = next(x for x in commands if x.startswith('savebin uid.bin'))
                size = int(uid_command.rsplit(',', 1)[1].strip(), 16)
                (directory/'uid.bin').write_bytes(bytes(range(1, size+1)))
            return 'mock J-Link'
        stages = []
        with patch.object(agent,'commander',side_effect=fake):self.assertTrue(agent.flash(work,'mock',progress=stages.append)['verified'])
        self.assertEqual(stages, ['preparing','writing','reading','restarting','reporting'])
        def corrupt(*args):
            text=fake(*args)
            p=args[1]/'readback.bin'
            if p.exists():
                b=bytearray(p.read_bytes());b[8]^=1;p.write_bytes(b)
            return text
        with patch.object(agent,'commander',side_effect=corrupt):
            with self.assertRaises(ValueError):agent.flash(work,'mock')

    def test_agent_detects_cubeide_jlink_without_standalone_install(self):
        cube = Path('C:/ST/STM32CubeIDE_1.19.0/STM32CubeIDE/plugins/com.st.stm32cube.ide.mcu.externaltools.jlink.win32/tools/bin/JLink.exe')
        def installed(path, pattern):
            return [cube] if 'STM32CubeIDE' in pattern and path.as_posix() == 'C:/ST' else []
        with patch.object(agent.shutil, 'which', return_value=None), patch.object(Path, 'glob', autospec=True, side_effect=installed):
            self.assertEqual(agent.find_jlink(), str(cube))

    def test_agent_diagnostics_identify_client_without_claiming_or_flashing(self):
        with tempfile.TemporaryDirectory() as temp:
            cfg = Path(temp)/'config.json'
            cfg.write_text(json.dumps(dict(server='https://inventariotqt.site', station_id='test', token='private')))
            with patch.object(sys, 'argv', ['agent.py', '--config', str(cfg), '--check']), patch.object(agent, 'find_jlink', return_value='JLink.exe'), patch.object(agent.urllib.request, 'urlopen') as request, patch.object(agent, 'flash') as flash:
                request.return_value.__enter__.return_value.read.return_value = b'{"ok": true}'
                agent.main()
                sent = request.call_args.args[0]
                self.assertEqual(sent.full_url, 'https://inventariotqt.site/api/health')
                self.assertEqual(sent.get_header('User-agent'), agent.USER_AGENT)
                self.assertIsNone(sent.get_header('Authorization'))
                flash.assert_not_called()

    def test_numeric_lookup_of_r1_in_different_numbered_card(self):
        # Serial search can return `serie.r1` when the assembly has another number.
        with db.get_db() as c:
            c.execute('UPDATE tarjetas_produccion SET id_tarjeta_num=? WHERE id=?', ('9999', self.t['id']))
        result = inv.consulta(self.t['r1']['serie'])
        self.assertEqual(result['serie']['r1']['id'], self.t['r1']['id'])
        preview, _ = s.preview(result['serie']['r1']['id'])
        self.assertEqual(preview['identity']['id_r'], self.t['r2']['serie'])

    def test_agent_api_auth_without_cookie(self):
        c=iso.cliente_sin_sesion(app)
        self.assertEqual(c.post('/api/stm32/agent/claim').status_code,401)
        self.assertEqual(c.post('/api/stm32/agent/claim',headers={'Authorization':'Bearer '+self.st['token']}).status_code,200)
        self.assertEqual(c.get('/api/stm32/preview/'+str(self.t['r1']['id'])).status_code,401)

    def test_operator_preview_hex_bundle_and_job_routes(self):
        c=TestClient(app,base_url='https://testserver')
        pid=self.t['r1']['id']
        self.assertEqual(c.get('/api/stm32/preview/'+str(pid)).status_code,200)
        resp=c.get('/api/stm32/hex/'+str(pid))
        self.assertEqual(resp.status_code,200)
        import io,zipfile
        bundle=c.post('/api/stm32/stations/bundle',json={'name':'PC Test'})
        self.assertEqual(bundle.status_code,200)
        with zipfile.ZipFile(io.BytesIO(bundle.content)) as z:
            cfg=json.loads(z.read('config.json'))
            self.assertIn('agent.py',z.namelist())
            self.assertEqual(s.station_auth(cfg['token'])['id'],cfg['station_id'])
        d,_=self.prepared()
        self.assertEqual(c.post('/api/stm32/jobs',json={'pcb_id':pid,'station_id':self.st['id'],'hex_sha256':d['hex_sha256']}).status_code,400)
        response=c.post('/api/stm32/jobs',json={'pcb_id':pid,'station_id':self.st['id'],'hex_sha256':d['hex_sha256'],'physical_confirmed':True})
        self.assertEqual(response.status_code,200)
        jid=response.json()['id']
        self.assertEqual(c.get('/api/stm32/jobs/'+jid).status_code,200)
        station=iso.cliente_sin_sesion(app)
        headers={'Authorization':'Bearer '+self.st['token']}
        self.assertEqual(station.post('/api/stm32/agent/claim',headers=headers).status_code,200)
        result=dict(verified=True,hex_sha256=d['hex_sha256'],identity_sha256=d['identity_sha256'],uid='010203040506070809101112')
        for _ in range(2):
            ack=station.post('/api/stm32/agent/jobs/'+jid+'/result',headers=headers,json=result)
            self.assertEqual(ack.status_code,200)
            self.assertEqual(ack.json()['state'],'verified')

    def test_self_contained_installer_contains_station_and_startup_scripts(self):
        import base64, io, zipfile
        c=TestClient(app,base_url='https://testserver')
        response=c.post('/api/stm32/stations/installer',json={'name':'Laptop installer'})
        self.assertEqual(response.status_code,200)
        text=response.content.decode('ascii')
        self.assertTrue(text.startswith('@echo off\r\n'))
        self.assertLess(max(len(line) for line in text.split('::TQT_PAYLOAD::')[0].splitlines()), 8191)
        encoded=text.split('::TQT_PAYLOAD::\r\n',1)[1].strip()
        with zipfile.ZipFile(io.BytesIO(base64.b64decode(encoded))) as z:
            cfg=json.loads(z.read('config.json'))
            self.assertEqual(cfg['server'],'https://testserver')
            self.assertEqual(s.station_auth(cfg['token'])['id'],cfg['station_id'])
            self.assertIn('instalar.ps1',z.namelist())
            self.assertIn(b'--background',z.read('instalar.ps1'))


if __name__=='__main__':unittest.main()


class AnalizarHexTest(unittest.TestCase):
    """v1.3.54: «Subir HEX» lee la versión del firmware sin guardarlo."""
    def test_base_y_errores(self):
        from app.services import stm32_programming as svc
        d = svc.analizar_hex(svc.BASE.read_text(encoding='ascii'))
        self.assertEqual((d['mcu'], d['fw'], d['hw']), ('STM32F103RET6', d['base_fw'], d['base_hw']))
        self.assertIsNone(d['identidad'])
        with self.assertRaises(ValueError):
            svc.analizar_hex(':00000001FF\n')
        with self.assertRaises(ValueError):
            svc.analizar_hex('esto no es un hex')
