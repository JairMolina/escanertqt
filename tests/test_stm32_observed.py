import _aislamiento as iso
import json
import unittest
from fastapi.testclient import TestClient
from app.main import app
from app.database import db,inventario as inv
from app.services import stm32_programming as s,stm32_firmware as f,tqt_hex as hx

class ObservedStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): db.init_db()
    def setUp(self):
        self.op='observed-'+self._testMethodName+'@tqt.invalid'
        self.card=iso.crear_par(iso.nuevo_lote()['id'],version='30')
        self.pid=self.card['r1']['id']
        self.station=s.station_create('Sin hardware',self.op)
        s.claim(self.station['id'])
    def tearDown(self):
        with db.get_db() as c:c.execute('DELETE FROM stm32_firmwares WHERE operator=?',(self.op,))
    def beta(self):
        mem,starts,_=s.firmware();addresses=sorted(mem);blob=bytes(mem[a] for a in addresses)
        at=addresses[blob.index(hx.PROFILE_MAGIC)]+24
        for i,b in enumerate(b'9.6\0\0\0\0\0'):mem[at+i]=b
        return f.save(hx.emitir_hex(mem,starts),'R1','SIMULADO_NO_PROGRAMAR.hex','','',self.op)
    def queue(self,firmware_id=None):
        d,_=s.preview(self.pid,firmware_id=firmware_id)
        return s.create_job(self.pid,self.station['id'],d['hex_sha256'],self.op,True,firmware_id)
    def verify(self,job):
        work=s.claim(self.station['id'])
        result=dict(verified=True,uid='1234567890ABCDEF12345678',hex_sha256=work['payload']['hex_sha256'],identity_sha256=work['payload']['identity_sha256'])
        return s.finish(self.station['id'],job['id'],result)
    def test_none_and_inventory_are_not_live_reads(self):
        a=s.observed_state(self.pid)
        self.assertEqual(a['source'],'none');self.assertIsNone(a['firmware'])
        inv.set_firmware(self.pid,'4.3',self.op)
        b=s.observed_state(self.pid)
        self.assertEqual(b['source'],'inventory');self.assertEqual(b['firmware'],'4.3')
        self.assertEqual(b['hardware'],'3.0');self.assertIsNotNone(b['recorded_at'])
        self.assertIsNone(b['verified_at']);self.assertIsNone(b['mac_r'])
    def test_preview_different_firmware_does_not_change_observed_or_create_jobs(self):
        inv.set_firmware(self.pid,'4.3',self.op)
        beta=self.beta();before=s.observed_state(self.pid)
        data,_=s.preview(self.pid,firmware_id=beta['id'])
        self.assertEqual(data['identity']['fw'],'9.6')
        self.assertEqual(s.observed_state(self.pid),before)
        with db.get_db() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM stm32_jobs WHERE pcb=?',(self.pid,)).fetchone()[0],0)
    def test_actual_changes_only_after_verified_result(self):
        first=self.queue();self.verify(first)
        before=s.observed_state(self.pid)
        self.assertEqual(before['source'],'verified_programming');self.assertEqual(before['firmware'],'4.3')
        self.assertTrue(before['verified_at']);self.assertTrue(before['uid'])
        beta=self.beta();next_job=self.queue(beta['id'])
        self.assertEqual(s.observed_state(self.pid)['firmware'],'4.3')
        s.claim(self.station['id'])
        self.assertTrue(s.observed_state(self.pid)['current_unconfirmed'])
        s.finish(self.station['id'],next_job['id'],dict(verified=False,error='Fallo simulado'))
        failed=s.observed_state(self.pid)
        self.assertEqual(failed['firmware'],'4.3');self.assertTrue(failed['current_unconfirmed'])
        self.verify(self.queue(beta['id']))
        good=s.observed_state(self.pid)
        self.assertEqual(good['firmware'],'9.6');self.assertFalse(good['current_unconfirmed'])
    def test_archived_identity_is_not_replaced_by_current_inventory(self):
        job=self.queue();self.verify(job)
        before=s.observed_state(self.pid)
        inv.set_firmware(self.pid,'8.0',self.op)
        r2=inv.registrar_manual('R2','30',iso.num_unico())['pcbs'][0]
        inv.confirmar_recepcion([r2['id']]);inv.set_mac(r2['id'],iso.mac_unica())
        inv.asignar_pcb(self.card['id'],'R2',r2['id'])
        after=s.observed_state(self.pid)
        self.assertEqual(after['firmware'],before['firmware'])
        self.assertEqual(after['id_r'],before['id_r']);self.assertEqual(after['mac_r'],before['mac_r'])
    def test_false_or_broken_verified_record_is_not_physical_evidence(self):
        job=self.queue()
        with db.get_db() as c:
            c.execute("UPDATE stm32_jobs SET state='verified',result=? WHERE id=?",(json.dumps({'verified':True,'uid':'1234567890ABCDEF12345678'}),job['id']))
        a=s.observed_state(self.pid)
        self.assertNotEqual(a['source'],'verified_programming');self.assertTrue(a['current_unconfirmed'])
        with db.get_db() as c:c.execute('UPDATE stm32_jobs SET payload=? WHERE id=?',('null',job['id']))
        self.assertNotEqual(s.observed_state(self.pid)['source'],'verified_programming')
    def test_r3_and_authenticated_endpoint(self):
        r3=inv.registrar_manual('R3','30',iso.num_unico())['pcbs'][0]
        inv.set_firmware(r3['id'],'1.0',self.op)
        self.assertEqual(s.observed_state(r3['id'])['firmware'],'1.0')
        prepared,_=s.preview(r3['id'])
        job=s.create_job(r3['id'],self.station['id'],prepared['hex_sha256'],self.op,True)
        self.verify(job)
        r3_state=s.observed_state(r3['id'])
        self.assertEqual(r3_state['source'],'verified_programming');self.assertIsNone(r3_state['mac_r'])
        anon=iso.cliente_sin_sesion(app)
        self.assertEqual(anon.get('/api/stm32/estado/'+str(self.pid)).status_code,401)
        client=TestClient(app,base_url='https://testserver')
        self.assertEqual(client.get('/api/stm32/estado/'+str(self.pid)).status_code,200)
        self.assertEqual(client.get('/api/stm32/estado/'+str(self.card['r2']['id'])).status_code,400)
        self.assertEqual(client.get('/api/stm32/estado/999999999').status_code,400)
