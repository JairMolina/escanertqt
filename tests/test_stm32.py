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
        return s.create_job(self.t['r1']['id'], self.st['id'], d['hex_sha256'], 'operador@test.mx')

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
        with self.assertRaises(ValueError):s.create_job(self.t['r1']['id'],self.st['id'],d['hex_sha256'],'test')

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

    def test_agent_checks_readback_without_hardware(self):
        d,image=self.prepared();work=dict(payload=d,hex=image)
        def fake(exe,directory,commands,serial):
            if any('loadfile' in x for x in commands):
                mem,_=hx.leer_hex(directory/'firmware.hex'); raw=bytearray([255])*0x80000
                for a,b in mem.items():raw[a-hx.FLASH_BEGIN]=b
                (directory/'readback.bin').write_bytes(raw)
                (directory/'uid.bin').write_bytes(bytes(range(1,13)))
            return 'mock J-Link'
        with patch.object(agent,'commander',side_effect=fake):self.assertTrue(agent.flash(work,'mock')['verified'])
        def corrupt(*args):
            text=fake(*args)
            p=args[1]/'readback.bin'
            if p.exists():
                b=bytearray(p.read_bytes());b[8]^=1;p.write_bytes(b)
            return text
        with patch.object(agent,'commander',side_effect=corrupt):
            with self.assertRaises(ValueError):agent.flash(work,'mock')

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
        response=c.post('/api/stm32/jobs',json={'pcb_id':pid,'station_id':self.st['id'],'hex_sha256':d['hex_sha256']})
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


if __name__=='__main__':unittest.main()
