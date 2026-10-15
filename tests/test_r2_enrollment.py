import _aislamiento as iso
import base64,hashlib,json,secrets,struct,unittest
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import ec,utils
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from app.database import db,inventario as inv
from app.services import r2_enrollment as enroll,esp32_firmware as fw,esp32_ota as ota
from test_esp32_ota import attestation

class EnrollmentTests(unittest.TestCase):
    def test_multiple_registered_base_builds_remain_usable(self):
        from test_esp32_firmware import rewrite
        pos=self.raw.index(b'Auto-fix deshabilitado')
        variant=rewrite(self.raw,pos,b'Auto-fix deshabilitadO')
        fw.save(variant,'BASE_RECOMPILADA_SIMULADA.bin',self.operator)
        first=self.prepare()
        self.assertTrue(first['ticket'])
        self.info['nonce']=secrets.token_hex(16)
        _,_,layout=fw.inspect(variant)
        self.info['app_sha256']=variant[layout['end']-32:layout['end']].hex()
        self.assertTrue(self.prepare()['ticket'])

    def test_generic_info_fits_one_gatt_value_without_unit_hmac(self):
        from app.routers.esp32 import EnrollmentDevice
        info=dict(nombre='TQT_R2_V30_XXXX',hw='3.0',fw='4.0',mac='FF:FF:FF:FF:FF:FF',ota_protocol=1,
                  nonce='f'*32,app_sha256='f'*64,boot_valid=False,chunk=500,enrollment=1,
                  enroll_key_id='f'*16,device_pub='04'+'f'*128)
        wire=json.dumps(info,separators=(',',':')).encode()
        self.assertLessEqual(len(wire),512)
        self.assertEqual(EnrollmentDevice(**dict(info,boot_valid=True)).nombre,'TQT_R2_V30_XXXX')

    def setUp(self):
        db.init_db();self.p=iso.crear_par(iso.nuevo_lote()['id'])['r2'];self.operator='enroll@test.invalid'
        with db.get_db() as c:c.execute('UPDATE pcb_inventario SET mac=NULL,firmware=NULL WHERE id=?',(self.p['id'],))
        self.raw=(fw.ROOT/'firmware/esp32_r2/TQT_R2_BASE_V4_0_GENERIC.merged.bin').read_bytes()
        meta,_,layout=fw.inspect(self.raw)
        self.peer=ec.generate_private_key(ec.SECP256R1())
        pub=self.peer.public_key().public_bytes(serialization.Encoding.X962,serialization.PublicFormat.UncompressedPoint)
        self.info=dict(nombre='TQT_R2_V30_XXXX',hw='3.0',fw='4.0',mac=self.p['mac'],boot_valid=True,enrollment=1,
                       nonce=secrets.token_hex(16),device_pub=pub.hex(),enroll_key_id=enroll.key_id(),app_sha256=self.raw[layout['end']-32:layout['end']].hex())

    def prepare(self,info=None):return enroll.prepare(self.p['id'],'base-R2-v42',info or self.info,self.operator)

    def decrypt(self,result):
        ticket=base64.b64decode(result['ticket']);self.assertEqual(len(ticket),286)
        pub=bytes.fromhex(self.info['device_pub']);nonce=bytes.fromhex(self.info['nonce']);mac=ota.mac(self.info['mac'])
        # Independent device-side implementation, verifying the server signature before decrypting.
        signer=enroll.signing_key().public_key()
        signature=utils.encode_dss_signature(int.from_bytes(ticket[222:254],'big'),int.from_bytes(ticket[254:286],'big'))
        signer.verify(signature,enroll.LABEL+pub+nonce+mac+ticket[:222],ec.ECDSA(hashes.SHA256()))
        ephemeral=ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(),ticket[1:66])
        shared=self.peer.exchange(ec.ECDH(),ephemeral)
        key=hashlib.sha256(enroll.LABEL+shared+nonce+mac).digest()
        clear=AESGCM(key).decrypt(ticket[66:78],ticket[78:222],enroll.LABEL+nonce+mac)
        return fw.PROFILE_V2.unpack(clear)

    def test_identical_generic_for_all_cards_without_creating_unit_key(self):
        meta,a=fw.prepare(self.p['id'],'base-R2-v40-generic',True)
        other=iso.crear_par(iso.nuevo_lote()['id'])['r2'];_,b=fw.prepare(other['id'],'base-R2-v40-generic',True)
        self.assertEqual(a,b);self.assertEqual(a,self.raw)
        self.assertEqual((meta['nombre'],meta['fw'],meta['schema'],meta['key_id']),('TQT_R2_V30_XXXX','4.0',3,''))
        with db.get_db() as c:self.assertIsNone(c.execute('SELECT 1 FROM esp32_unit_keys WHERE pcb=?',(self.p['id'],)).fetchone())

    def test_enrollment_then_42_boot_is_only_inventory_commit(self):
        result=self.prepare();profile=self.decrypt(result)
        name=profile[4].rstrip(b'\0').decode();secret=profile[7]
        self.assertEqual(name,self.p['nombre']);self.assertEqual(profile[1],2)
        self.assertNotIn(secret,base64.b64decode(result['ticket']))
        self.assertIsNone(inv.get_pcb(self.p['id'])['firmware']);self.assertIsNone(inv.get_pcb(self.p['id'])['mac'])
        base=dict(nombre=name,hw='3.0',fw='4.0',app_sha256=self.info['app_sha256'])
        assigned=attestation(base,secret,self.p['mac'])
        self.assertTrue(enroll.finish(result['id'],assigned,self.operator)['assigned'])
        self.assertIsNone(inv.get_pcb(self.p['id'])['mac'])
        job=ota.prepare(self.p['id'],'base-R2-v42',assigned,self.operator)
        target=dict(nombre=name,hw='3.0',fw='4.2',app_sha256=job['app_sha256'])
        boot=attestation(target,secret,self.p['mac'],partition=0x150000)
        finished=ota.finish(job['job_id'],boot,self.operator)
        self.assertEqual(finished['pcb']['firmware'],'4.2');self.assertEqual(finished['pcb']['mac'],self.p['mac'])

    def test_invalid_base_key_hash_identity_nonce_and_other_mac_are_rejected(self):
        for field,value in [('enroll_key_id','0'*16),('hw','3.1'),('app_sha256','0'*64),('enrollment',0),('nombre','TQT_R2_V30_9999'),('device_pub','04'+'00'*64)]:
            with self.assertRaises(ValueError,msg=field):self.prepare(dict(self.info,**{field:value}))
        self.prepare()
        with self.assertRaises(ValueError):self.prepare()
        other=iso.crear_par(iso.nuevo_lote()['id'])['r2']
        with self.assertRaises(ValueError):self.prepare(dict(self.info,mac=other['mac'],nonce=secrets.token_hex(16)))

    def test_new_connection_recovers_interrupted_assignment_with_same_unit_key(self):
        first=self.prepare();secret1=self.decrypt(first)[7]
        self.info['nonce']=secrets.token_hex(16)
        second=self.prepare();self.assertEqual(self.decrypt(second)[7],secret1)
        self.assertIsNone(inv.get_pcb(self.p['id'])['firmware'])
