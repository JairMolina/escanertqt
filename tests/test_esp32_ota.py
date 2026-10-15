import _aislamiento as iso
import base64
import hashlib
import hmac
import json
import secrets
import struct
import unittest
from unittest.mock import patch
from cryptography.hazmat.primitives.ciphers import Cipher,algorithms,modes
from fastapi.testclient import TestClient
from app.main import app
from app.database import db,inventario as inv
from app.services import esp32_firmware as fw,esp32_ota as ota


def attestation(meta,key,mac,partition=0x10000,nonce=None):
    value=dict(nombre=meta['nombre'],hw=meta['hw'],fw=meta['fw'],mac=mac,ota_protocol=1,
               key_id=hashlib.sha256(key).hexdigest()[:16],nonce=(nonce or secrets.token_bytes(16)).hex(),
               app_sha256=meta['app_sha256'],boot_valid=True,partition=partition,chunk=180)
    # Independent protocol framing, matching the firmware's packed INFO message.
    message=(b'TQT-OTA-INFO-v1'+bytes.fromhex(value['nonce'])+bytes.fromhex(value['app_sha256'])+
             value['nombre'].encode().ljust(24,b'\0')+value['hw'].encode().ljust(8,b'\0')+
             value['fw'].encode().ljust(16,b'\0')+bytes.fromhex(mac.replace(':',''))+b'\x01'+struct.pack('<I',partition))
    value['proof']=hmac.new(key,message,hashlib.sha256).hexdigest()
    return value


class OtaTests(unittest.TestCase):
    def test_fast_template_and_transport_limit(self):
        from app.routers.esp32 import DeviceInfo
        from pydantic import ValidationError
        self.assertEqual(DeviceInfo(**dict(self.info,chunk=500)).chunk,500)
        with self.assertRaises(ValidationError):
            DeviceInfo(**dict(self.info,chunk=501))
        catalogue=fw.catalogue('30')
        self.assertEqual(catalogue['default_id'],'base-R2-v411')
        meta,image=fw.prepare(self.pid,'base-R2-v411',True)
        self.assertEqual((meta['fw'],meta['nombre'],meta['key_id']),
                         ('4.1.1',self.meta['nombre'],self.meta['key_id']))
        self.assertEqual(fw.inspect(image)[0]['fw'],'4.1.1')

    @classmethod
    def setUpClass(cls):
        db.init_db()
        cls.raw=(fw.ROOT/'firmware/esp32_r2/TQT_R2_V4_1.merged.bin').read_bytes()

    def setUp(self):
        self.operator='ota-test@tqt.invalid'
        self.card=iso.crear_par(iso.nuevo_lote()['id'])
        self.pcb=self.card['r2'];self.pid=self.pcb['id']
        self.meta,self.image=fw.prepare(self.pid,'base-R2-v41',True)
        self.layout=fw.inspect(self.image)[2]
        self.app=self.image[self.layout['start']:self.layout['end']]
        self.meta['app_sha256']=self.app[-32:].hex()
        with db.get_db() as c:
            self.key=bytes(c.execute('SELECT secret FROM esp32_unit_keys WHERE pcb=?',(self.pid,)).fetchone()[0])
        inv.set_firmware(self.pid,'4.1')
        self.pcb=inv.get_pcb(self.pid)
        self.info=attestation(self.meta,self.key,self.pcb['mac'])

    def prepare(self,info=None,firmware='base-R2-v41'):
        return ota.prepare(self.pid,firmware,info or self.info,self.operator)

    def test_profile_capability_and_stable_per_unit_provisioning(self):
        meta,_,_=fw.inspect(self.raw)
        self.assertEqual((meta['schema'],meta['fw'],meta['ota_protocol'],meta['key_id']),(2,'4.1',1,''))
        again,image=fw.prepare(self.pid,'base-R2-v41',True)
        self.assertEqual(image,self.image)
        self.assertEqual(again['key_id'],self.info['key_id'])
        other=iso.crear_par(iso.nuevo_lote()['id'])['r2']
        new,_=fw.prepare(other['id'],'base-R2-v41',True)
        self.assertNotEqual(new['key_id'],again['key_id'])

    def test_read_only_preview_never_provisions_a_key(self):
        other=iso.crear_par(iso.nuevo_lote()['id'])['r2']
        meta,_=fw.prepare(other['id'],'base-R2-v41')
        self.assertEqual(meta['key_id'],'')
        with db.get_db() as c:
            self.assertIsNone(c.execute('SELECT 1 FROM esp32_unit_keys WHERE pcb=?',(other['id'],)).fetchone())

    def test_uploaded_unit_image_strips_private_key_and_name(self):
        meta,image,_=fw.normalize(self.image,'personalized.bin')
        self.assertEqual(image,self.raw)
        self.assertEqual(meta['key_id'],'')
        self.assertEqual(meta['nombre'],'TQT_R2_V30_0000')
        self.assertNotIn(self.key,self.raw)

    def test_credential_only_adds_reserved_bytes_and_integrity_fields(self):
        _,pos,layout=fw.inspect(self.raw)
        allowed=set(range(pos+44,pos+68))|set(range(pos+96,pos+128))|set(range(layout['checksum'],layout['end']))
        self.assertTrue(all(i in allowed for i,(a,b) in enumerate(zip(self.raw,self.image)) if a!=b))
        self.assertEqual(self.raw[:65536],self.image[:65536])

    def test_serial_result_requires_unit_key_fingerprint(self):
        for tag in ('','a'*16):
            with self.assertRaises(ValueError): fw.result(self.pid,self.pcb['mac'],'base-R2-v41',self.meta['nombre'],'3.0','4.1',self.operator,tag,1)
        saved=fw.result(self.pid,self.pcb['mac'],'base-R2-v41',self.meta['nombre'],'3.0','4.1',self.operator,self.meta['key_id'],1)
        self.assertEqual(saved['firmware'],'4.1')

    def test_encrypted_image_and_manifest_match_firmware_protocol(self):
        job=self.prepare()
        manifest=base64.b64decode(job['manifest'])
        encrypted=base64.b64decode(job['encrypted_image'])
        self.assertEqual(len(manifest),138)
        self.assertEqual(manifest[:16],bytes.fromhex(self.info['nonce']))
        self.assertEqual(manifest[16:48],hashlib.sha256(self.app).digest())
        self.assertEqual(struct.unpack_from('<I',manifest,48)[0],len(self.app))
        self.assertEqual(manifest[52:76],self.info['nombre'].encode().ljust(24,b'\0'))
        self.assertEqual(manifest[76:84],b'3.0'.ljust(8,b'\0'))
        self.assertEqual(manifest[84:100],b'4.1'.ljust(16,b'\0'))
        self.assertEqual(manifest[100:106],bytes.fromhex(self.pcb['mac'].replace(':','')))
        self.assertTrue(hmac.compare_digest(hmac.new(self.key,manifest[:106],hashlib.sha256).digest(),manifest[106:]))
        derived=hmac.new(self.key,b'TQT-OTA-DATA-v1'+manifest[:16],hashlib.sha256).digest()
        decrypt=Cipher(algorithms.AES(derived),modes.CTR(manifest[:16])).decryptor()
        # Unequal fragments exercise CTR state across packet boundaries, including 16-byte BLE payloads.
        clear=b''
        for offset in range(0,len(encrypted),179): clear+=decrypt.update(encrypted[offset:offset+179])
        clear+=decrypt.finalize()
        self.assertEqual(clear,self.app)
        self.assertNotEqual(encrypted,self.app)
        self.assertNotIn(self.key,encrypted)

    def test_changed_identity_mac_hash_and_proof_are_rejected(self):
        for field,value in [('nombre','TQT_R2_V30_9999'),('mac',iso.mac_unica()),('hw','3.1'),
                            ('app_sha256','0'*64),('proof','0'*64),('key_id','0'*16),('boot_valid',False),('ota_protocol',0),('fw','4.0')]:
            with self.assertRaises(ValueError,msg=field): self.prepare(dict(self.info,**{field:value}))
        with self.assertRaises(ValueError): self.prepare(attestation(self.meta,secrets.token_bytes(32),self.pcb['mac']))

    def test_legacy_target_and_nonce_reuse_are_rejected(self):
        with self.assertRaises(ValueError): self.prepare(firmware='base-R2-v4')
        self.prepare()
        with self.assertRaises(ValueError): self.prepare()

    def test_capability_requires_installed_version_mac_and_key(self):
        self.assertTrue(ota.capability(self.pid)['eligible'])
        inv.set_firmware(self.pid,'4.0')
        self.assertFalse(ota.capability(self.pid)['eligible'])
        other=iso.crear_par(iso.nuevo_lote()['id'])['r2']
        inv.set_firmware(other['id'],'4.1')
        self.assertFalse(ota.capability(other['id'])['eligible'])

    def test_confirmed_same_version_requires_new_boot_partition(self):
        job=self.prepare()
        with self.assertRaises(ValueError): ota.finish(job['job_id'],self.info,self.operator)
        boot=attestation(self.meta,self.key,self.pcb['mac'],partition=0x150000)
        result=ota.finish(job['job_id'],boot,self.operator)
        self.assertTrue(result['verified'])
        self.assertEqual(result['fw'],'4.1')
        self.assertEqual(ota.finish(job['job_id'],boot,self.operator),result)

    def test_wrong_image_and_rollback_do_not_save_results(self):
        job=self.prepare()
        for meta in [dict(self.meta,app_sha256='1'*64),dict(self.meta,fw='4.2')]:
            with self.assertRaises(ValueError): ota.finish(job['job_id'],attestation(meta,self.key,self.pcb['mac'],0x150000),self.operator)
        with self.assertRaises(ValueError): ota.finish(job['job_id'],attestation(self.meta,self.key,self.pcb['mac'],0x10000),self.operator)
        with db.get_db() as c:
            self.assertEqual(c.execute('SELECT state FROM esp32_ota_jobs WHERE id=?',(job['job_id'],)).fetchone()[0],'prepared')

    def test_cancelled_expired_and_other_operator_jobs_fail_closed(self):
        job=self.prepare();boot=attestation(self.meta,self.key,self.pcb['mac'],0x150000)
        with self.assertRaises(ValueError): ota.finish(job['job_id'],boot,'other@tqt.invalid')
        self.assertTrue(ota.cancel(job['job_id'],self.operator)['cancelled'])
        with self.assertRaises(ValueError): ota.finish(job['job_id'],boot,self.operator)
        info=attestation(self.meta,self.key,self.pcb['mac'])
        next_job=self.prepare(info)
        with db.get_db() as c: c.execute('UPDATE esp32_ota_jobs SET created=0 WHERE id=?',(next_job['job_id'],))
        with self.assertRaises(ValueError): ota.finish(next_job['job_id'],boot,self.operator)

    def test_result_stays_bound_to_selected_firmware(self):
        job=self.prepare()
        from test_esp32_firmware import rewrite
        _,pos,_=fw.inspect(self.raw)
        other=rewrite(self.raw,pos+28,b'4.2'.ljust(16,b'\0'))
        saved=fw.save(other,'SIMULATED_FW42.bin',self.operator)
        try:
            result=ota.finish(job['job_id'],attestation(self.meta,self.key,self.pcb['mac'],0x150000),self.operator)
            self.assertEqual(result['fw'],'4.1')
        finally:
            with db.get_db() as c: c.execute('DELETE FROM esp32_firmwares WHERE id=?',(saved['id'],))

    def test_api_requires_session_role_same_origin_and_actual_device_proof(self):
        body=dict(firmware_id='base-R2-v41',device=self.info)
        anon=iso.cliente_sin_sesion(app)
        self.assertEqual(anon.post(f'/api/esp32/ota/prepare/{self.pid}',json=body).status_code,401)
        with patch('app.services.usuarios.validar_sesion',return_value={'email':self.operator,'rol':'consultor'}):
            client=TestClient(app,base_url='https://testserver')
            self.assertEqual(client.post(f'/api/esp32/ota/prepare/{self.pid}',json=body).status_code,403)
        with patch('app.services.usuarios.validar_sesion',return_value={'email':self.operator,'rol':'general'}):
            self.assertEqual(client.post(f'/api/esp32/ota/prepare/{self.pid}',json=body,headers={'Origin':'https://other.invalid'}).status_code,403)
            response=client.post(f'/api/esp32/ota/prepare/{self.pid}',json=body)
            self.assertEqual(response.status_code,200)
            self.assertNotIn(self.key.hex(),json.dumps(response.json()))
            boot=attestation(self.meta,self.key,self.pcb['mac'],0x150000)
            result=client.post('/api/esp32/ota/result/'+response.json()['job_id'],json=boot)
            self.assertEqual(result.status_code,200)
            invalid=dict(self.info,ota_protocol=True)
            self.assertEqual(client.post(f'/api/esp32/ota/prepare/{self.pid}',json=dict(body,device=invalid)).status_code,422)


if __name__=='__main__': unittest.main()
