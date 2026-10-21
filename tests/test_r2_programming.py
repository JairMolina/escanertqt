import _aislamiento as iso
import asyncio
import json
import time
import unittest
from app.database import db,inventario as inv
from app.services import r2_programming as r2, esp32_firmware as fw, esp32_ota as ota, stm32_programming as stations
from test_esp32_ota import attestation

class VerificationTests(unittest.TestCase):
    def setUp(self):
        db.init_db()
        self.p=iso.crear_par(iso.nuevo_lote()['id'])['r2']
        self.meta,self.image=fw.prepare(self.p['id'],'base-R2-v411',True)
        layout=fw.inspect(self.image)[2];self.meta['app_sha256']=self.image[layout['end']-32:layout['end']].hex()
        with db.get_db() as c:self.key=bytes(c.execute('SELECT secret FROM esp32_unit_keys WHERE pcb=?',(self.p['id'],)).fetchone()[0])
        self.station=stations.station_create('R2 test','test@invalid')['id']
        r2.claim(self.station,True)
        self.operator='r2@invalid'
        self.mac=self.p['mac']

    def job(self):
        j=r2.start(self.p['id'],'base-R2-v411',self.station,self.operator)
        r2.ready(j['id'],self.operator,self.mac)
        self.assertEqual(r2.claim(self.station,True)['id'],j['id'])
        return j['id']

    def result(self,identifier,info=None,address=None):
        return r2.finish(self.station,identifier,dict(ok=True,info=info or attestation(self.meta,self.key,self.mac),address=address or self.mac))

    def test_verified_record_and_idempotent_result(self):
        identifier=self.job();res=self.result(identifier)
        self.assertTrue(res['verified'])
        self.assertEqual(self.result(identifier),res)
        state=next(x for x in r2.statuses()['items'] if x['pcb_id']==self.p['id'])
        self.assertEqual((state['state'],state['evidence']['method']),('outdated','serial'))
        self.assertEqual(state['evidence']['hw'],'3.0')
        self.assertGreater(state['evidence']['programmed_at'],0)

    def test_wrong_hash_and_mac_do_not_mark_programmed(self):
        identifier=self.job()
        meta=dict(self.meta,app_sha256='00'*32)
        res=self.result(identifier,attestation(meta,self.key,self.mac))
        self.assertFalse(res['verified'])
        self.assertNotEqual(inv.get_pcb(self.p['id'])['firmware'],'4.1.1')
        state=next(x for x in r2.statuses()['items'] if x['pcb_id']==self.p['id'])
        self.assertEqual(state['state'],'error')

    def test_observed_address_and_forged_info_rejected(self):
        identifier=self.job()
        self.assertFalse(self.result(identifier,address='AA:BB:CC:DD:EE:00')['verified'])
        identifier=self.job();info=attestation(self.meta,self.key,self.mac);info['proof']='00'*32
        self.assertFalse(self.result(identifier,info)['verified'])

    def test_no_agent_and_conflicting_jobs(self):
        with self.assertRaises(ValueError):r2.start(self.p['id'],'base-R2-v411','0'*24,self.operator)
        self.job()
        with self.assertRaises(ValueError):r2.start(self.p['id'],'base-R2-v411',self.station,self.operator)

    def test_foreign_station_operator_and_expired(self):
        identifier=self.job()
        with self.assertRaises(ValueError):r2.get(identifier,'other@invalid')
        with self.assertRaises(ValueError):r2.finish('0'*24,identifier,{'ok':True})
        with db.get_db() as c:c.execute('UPDATE r2_programming_attempts SET created=? WHERE id=?',(time.time()-700,identifier))
        self.assertEqual(r2.get(identifier,self.operator)['state'],'error')
        with self.assertRaises(ValueError):self.result(identifier)

    def test_manual_firmware_counts_without_evidence(self):
        # v1.4.20: programada fuera de la app (FW capturado a mano) = programada, aunque sin evidencia BLE
        inv.set_firmware(self.p['id'],'4.1.1')
        state=next(x for x in r2.statuses()['items'] if x['pcb_id']==self.p['id'])
        self.assertIn(state['state'],('outdated','updated'))
        self.assertFalse(state['verified'])

    def test_manual_mac_change_invalidates_old_evidence(self):
        self.result(self.job())
        inv.set_mac(self.p['id'],iso.mac_unica())
        state=next(x for x in r2.statuses()['items'] if x['pcb_id']==self.p['id'])
        self.assertFalse(state['verified'])

    def test_api_requires_session_and_agent_bearer(self):
        from fastapi.testclient import TestClient
        from app.main import app
        anonymous=iso.cliente_sin_sesion(app)
        self.assertEqual(anonymous.get('/api/esp32/r2/status').status_code,401)
        self.assertEqual(anonymous.post('/api/stm32/agent/r2/claim',json={'available':True}).status_code,401)
        client=TestClient(app,base_url='https://testserver')
        response=client.post('/api/esp32/r2/'+str(self.p['id'])+'/attempts',json={'firmware_id':'base-R2-v411','station_id':self.station,'method':'serial'})
        self.assertEqual(response.status_code,200)
        self.assertEqual(client.get('/api/esp32/r2/attempts/'+response.json()['id']).status_code,200)

    def test_replayed_info_and_cancelled_job_cannot_commit(self):
        info=attestation(self.meta,self.key,self.mac)
        self.result(self.job(),info)
        identifier=self.job()
        self.assertFalse(self.result(identifier,info)['verified'])
        identifier=self.job();r2.fail(identifier,self.operator,'Cancelado por operador')
        with self.assertRaises(ValueError):self.result(identifier)

    def test_base_40_has_fast_ota_and_old_40_is_retained(self):
        meta,image=fw.prepare(self.p['id'],'base-R2-v40-ota',True)
        self.assertEqual((meta['fw'],meta['schema'],meta['ota_protocol']),('4.0',2,1))
        self.assertEqual(fw.inspect(bytes((fw.ROOT/'firmware/esp32_r2/TQT_R2_V4_0.merged.bin').read_bytes()))[0]['ota_protocol'],0)
        layout=fw.inspect(image)[2];meta['app_sha256']=image[layout['end']-32:layout['end']].hex()
        inv.set_firmware(self.p['id'],'4.0')
        self.assertTrue(ota.capability(self.p['id'])['eligible'])
        j=r2.start(self.p['id'],'base-R2-v40-ota',self.station,self.operator)
        r2.ready(j['id'],self.operator,self.mac);r2.claim(self.station,True)
        self.assertTrue(self.result(j['id'],attestation(meta,self.key,self.mac))['verified'])
        self.assertTrue(ota.capability(self.p['id'])['eligible'])
        self.assertTrue(ota.prepare(self.p['id'],'base-R2-v411',attestation(meta,self.key,self.mac),self.operator)['encrypted_image'])

    def test_read_only_verification_preserves_installation_date(self):
        self.result(self.job())
        before=next(x for x in r2.statuses()['items'] if x['pcb_id']==self.p['id'])['evidence']
        j=r2.start(self.p['id'],'base-R2-v411',self.station,self.operator,'verify');r2.claim(self.station,True);self.result(j['id'])
        after=next(x for x in r2.statuses()['items'] if x['pcb_id']==self.p['id'])['evidence']
        self.assertEqual(before['programmed_at'],after['programmed_at'])
        self.assertEqual(after['method'],'serial')
