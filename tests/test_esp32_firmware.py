import _aislamiento as iso
import base64
import hashlib
import struct
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app
from app.database import db, inventario as inv
from app.services import esp32_firmware as f


def rewrite(raw, offset, value):
    _,_,layout=f.inspect(raw)
    image=bytearray(raw)
    image[offset:offset+len(value)]=value
    checksum=0xEF
    for first,last in layout['segments']:
        for b in image[first:last]: checksum ^= b
    image[layout['checksum']]=checksum
    image[layout['checksum']+1:layout['end']]=hashlib.sha256(image[layout['start']:layout['checksum']+1]).digest()
    return bytes(image)


def as_hex(raw):
    lines=[]
    for start in range(0,len(raw),32):
        if start % 65536 == 0:
            data=bytes([2,0,0,4])+struct.pack('>H',start>>16)
            lines.append(':'+(data+bytes([-sum(data)&255])).hex().upper())
        payload=raw[start:start+32]
        data=bytes([len(payload)])+struct.pack('>H',start&65535)+b'\0'+payload
        lines.append(':'+(data+bytes([-sum(data)&255])).hex().upper())
    return ('\n'.join(lines)+'\n:00000001FF\n').encode('ascii')


class Esp32FirmwareTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init_db()
        cls.raw=(f.ROOT/'firmware/esp32_r2/TQT_R2_V4_0.merged.bin').read_bytes()

    def setUp(self):
        self.operator='esp32-test@tqt.invalid'
        self.card=iso.crear_par(iso.nuevo_lote()['id'],macs=False)
        with db.get_db() as c:
            f.ensure(c)

    def tearDown(self):
        with db.get_db() as c:
            c.execute('DELETE FROM esp32_firmwares WHERE operator=?',(self.operator,))

    def simulated(self,fw='4.1',hw='3.0'):
        _,pos,_=f.inspect(self.raw)
        if hw!='3.0': return self.changed_hw(fw,hw,pos)
        image=rewrite(self.raw,pos+20,hw.encode().ljust(8,b'\0'))
        image=rewrite(image,pos+28,fw.encode().ljust(16,b'\0'))
        # HW update requires a coherent placeholder name as well.
        return rewrite(image,pos+44,('TQT_R2_V'+hw.replace('.','')+'_0000').encode().ljust(24,b'\0'))

    def changed_hw(self,fw,hw,pos):
        fields=f.PROFILE.pack(f.MAGIC,1,hw.encode().ljust(8,b'\0'),fw.encode().ljust(16,b'\0'),
            ('TQT_R2_V'+hw.replace('.','')+'_0000').encode().ljust(24,b'\0'),b'ESP32-WROOM-32E-N4'.ljust(24,b'\0'))
        return rewrite(self.raw,pos,fields)

    def test_real_native_image_profile(self):
        meta,pos,layout=f.inspect(self.raw)
        self.assertEqual((meta['fw'],meta['hw'],meta['nombre']),('4.0','3.0','TQT_R2_V30_0000'))
        self.assertEqual(meta['module'],'ESP32-WROOM-32E-N4')
        self.assertTrue(any(a<=pos<pos+92<=b for a,b in layout['segments']))

    def test_only_identity_and_image_integrity_bytes_change(self):
        before,pos,layout=f.inspect(self.raw)
        first,meta=f.personalize(self.raw,'TQT_R2_V30_0036')
        other,_=f.personalize(self.raw,'TQT_R2_V30_9999')
        allowed=set(range(pos+44,pos+68))|set(range(layout['checksum'],layout['end']))
        self.assertTrue(all(i in allowed for i,(a,b) in enumerate(zip(self.raw,first)) if a!=b))
        self.assertEqual(len(first),len(self.raw))
        self.assertEqual(meta['nombre'],'TQT_R2_V30_0036')
        self.assertEqual(first[:65536],self.raw[:65536])
        self.assertNotEqual(first,other)
        self.assertEqual(f.inspect(other)[0]['fw'],'4.0')

    def test_invalid_names_rejected(self):
        for name in ['TQT_R2_V31_0001','TQT_R1_V30_0001','TQT-R2-V30-0001','TQT_R2_V30_1','bad\"']:
            with self.assertRaises(ValueError,msg=name): f.personalize(self.raw,name)

    def test_corrupt_app_bootloader_partition_and_sha_rejected(self):
        _,pos,layout=f.inspect(self.raw)
        for address in [0x1000,0x8000,pos,layout['checksum'],layout['checksum']+1]:
            raw=bytearray(self.raw); raw[address]^=1
            with self.assertRaises(ValueError,msg=hex(address)): f.inspect(bytes(raw))

    def test_wrong_chip_signed_extra_data_and_truncation_rejected(self):
        for offset in [0x1000+12,0x10000+12,0x9000]:
            raw=bytearray(self.raw); raw[offset]=1
            with self.assertRaises(ValueError): f.inspect(bytes(raw))
        for raw in [self.raw[:40000],self.raw+b'signature',self.raw[65536:]]:
            with self.assertRaises(ValueError): f.inspect(raw)

    def test_missing_or_duplicate_profile_and_schema_rejected(self):
        _,pos,layout=f.inspect(self.raw)
        for value in [b'NO_PROFILE_HERE!!', f.MAGIC+struct.pack('<I',2)]:
            with self.assertRaises(ValueError): f.inspect(rewrite(self.raw,pos,value))
        # A second complete marker in an application segment is never accepted.
        first,last=next((a,b) for a,b in layout['segments'] if b-a>256)
        duplicate=rewrite(self.raw,first+128,self.raw[pos:pos+92])
        with self.assertRaises(ValueError): f.inspect(duplicate)

    def test_hex_roundtrip_and_stm32_hex_rejected(self):
        meta,image,_=f.normalize(as_hex(self.raw),'R2.hex')
        self.assertEqual(image,self.raw)
        self.assertEqual(meta['fw'],'4.0')
        for raw in [b':020000040800F2\n:0400000001020304F2\n:00000001FF\n',
                    as_hex(self.raw).replace(b':020000040000FA',b':020000040000FB',1),
                    b':00000001FF\n',as_hex(self.raw)+b':00000001FF\n']:
            with self.assertRaises(ValueError): f.normalize(raw,'R2.hex')

    def test_saved_personalized_binary_is_canonical_and_duplicate(self):
        image,_=f.personalize(self.raw,'TQT_R2_V30_0042')
        saved=f.save(image,'unit.bin',self.operator)
        self.assertTrue(saved['existing'])
        self.assertEqual(saved['id'],'base-R2-v4')
        self.assertEqual(saved['nombre'],'TQT_R2_V30_0000')
        padded=self.raw+b'\xff'*(f.FLASH_SIZE-len(self.raw))
        self.assertEqual(f.normalize(padded,'full.merged.bin')[1],self.raw)

    def test_ota_selection_data_corruption_is_rejected(self):
        for offset in (0xE000,0xE01C,0xF000,0xE100):
            raw=bytearray(self.raw); raw[offset]^=1
            with self.assertRaises(ValueError): f.inspect(bytes(raw))

    def test_numeric_latest_and_hw_compatibility(self):
        a=f.save(self.simulated('4.9'),'a.bin',self.operator)
        b=f.save(self.simulated('4.10'),'b.bin',self.operator)
        f.save(self.changed_hw('5.0','3.1',f.inspect(self.raw)[1]),'c.bin',self.operator)
        self.assertEqual(f.catalogue('30')['default_id'],b['id'])
        meta,_=f.prepare(self.card['r2']['id'],a['id'])
        self.assertEqual(meta['fw'],'4.9')
        self.assertEqual(meta['nombre'],self.card['r2']['nombre'].replace('-','_'))
        self.assertNotIn('image',f.catalogue()['items'][0])

    def test_missing_selection_wrong_pcb_and_tampered_saved_blob(self):
        with self.assertRaises(ValueError): f.prepare(self.card['r1']['id'])
        with self.assertRaises(ValueError): f.prepare(self.card['r2']['id'],'missing')
        saved=f.save(self.simulated(),'new.bin',self.operator)
        with db.get_db() as c:
            c.execute('UPDATE esp32_firmwares SET image=? WHERE id=?',(b'corrupt',saved['id']))
        with self.assertRaises(ValueError): f.prepare(self.card['r2']['id'],saved['id'])

    def test_result_requires_actual_matching_name_hw_fw(self):
        meta,_=f.prepare(self.card['r2']['id'],'base-R2-v4')
        for name,hw,fw in [(meta['nombre'],'3.0','9.0'),('TQT_R2_V30_0000','3.0','4.0'),(meta['nombre'],'3.1','4.0')]:
            with self.assertRaises(ValueError): f.result(self.card['r2']['id'],iso.mac_unica(),meta['firmware_id'],name,hw,fw,self.operator)
        self.assertIsNone(inv.get_pcb(self.card['r2']['id'])['mac'])
        mac=iso.mac_unica()
        saved=f.result(self.card['r2']['id'],mac,meta['firmware_id'],meta['nombre'],meta['hw'],meta['fw'],self.operator)
        self.assertEqual((saved['mac'],saved['firmware']),(mac,'4.0'))

    def test_legacy_r1_result_is_preserved(self):
        client=TestClient(app,base_url='https://testserver')
        mac=iso.mac_unica()
        response=client.put(f'/api/pcb/{self.card["r1"]["id"]}/programacion',json={'mac':mac})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['mac'],mac)
        self.assertIsNone(response.json()['firmware'])

    def test_api_upload_session_origin_and_exact_selected_download(self):
        body=dict(filename='R2.bin',contenido=base64.b64encode(self.raw).decode())
        self.assertEqual(iso.cliente_sin_sesion(app).post('/api/esp32/firmwares',json=body).status_code,401)
        with patch('app.services.usuarios.validar_sesion',return_value={'email':self.operator,'rol':'general'}):
            client=TestClient(app,base_url='https://testserver')
            self.assertEqual(client.post('/api/esp32/firmwares',json=body,headers={'Origin':'https://other.invalid'}).status_code,403)
            response=client.post('/api/esp32/firmwares',json=body)
            self.assertEqual(response.status_code,200)
            identifier=response.json()['id']
            preview=client.get(f'/api/esp32/preview/{self.card["r2"]["id"]}?firmware_id={identifier}')
            self.assertEqual(preview.status_code,200)
            download=client.post(f'/api/esp32/bin/{self.card["r2"]["id"]}?firmware_id={identifier}')
            self.assertEqual(f.inspect(download.content)[0]['nombre'],preview.json()['nombre'])
            self.assertEqual(download.headers['X-TQT-Firmware'],'4.0')
            self.assertEqual(client.post('/api/esp32/firmwares/analizar',json=dict(filename='bad.bin',contenido='!'*30)).status_code,400)
            body=dict(mac=iso.mac_unica(),firmware='4.0',firmware_id=identifier,
                      nombre_verificado=preview.json()['nombre'],hardware_verificado='3.0',operador='spoofed')
            result=client.put(f'/api/pcb/{self.card["r2"]["id"]}/programacion',json=body)
            self.assertEqual(result.status_code,200)
            with db.get_db() as c:
                audit=c.execute("SELECT operador FROM escaneos WHERE evento='ESP32_PROGRAMADA' ORDER BY id DESC LIMIT 1").fetchone()
                self.assertEqual(audit['operador'],self.operator)
        with patch('app.services.usuarios.validar_sesion',return_value={'email':self.operator,'rol':'consultor'}):
            self.assertEqual(client.post(f'/api/esp32/bin/{self.card["r2"]["id"]}').status_code,403)


if __name__=='__main__': unittest.main()
