import _aislamiento as iso
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app
from app.database import db,inventario as inv
from app.services import stm32_firmware as f,stm32_programming as s,tqt_hex as hx


class FirmwareCatalogueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init_db()

    def setUp(self):
        self.operator='catalogue-test@tqt.invalid'
        self.card=iso.crear_par(iso.nuevo_lote()['id'],version='30')
        inv.set_mac(self.card['r1']['id'],iso.mac_unica())
        inv.set_mac(self.card['r2']['id'],iso.mac_unica())
        self.r3=inv.registrar_manual('R3','30',iso.num_unico())['pcbs'][0]
        self.station=s.station_create('Simulador sin hardware',self.operator)
        s.claim(self.station['id'])
        self.base,self.mem,_=s.firmware_r3()

    def tearDown(self):
        with db.get_db() as c:
            c.execute('DELETE FROM stm32_firmwares WHERE operator=?',(self.operator,))

    def simulated(self,delta=1):
        mem=dict(self.mem)
        address=max(mem)
        mem[address]=(mem[address]+delta)%256
        return hx.emitir_hex(mem)

    def save(self,fw='1.1',delta=1,hw='3.0'):
        saved=f.save(self.simulated(delta),'R3','SIMULADO_NO_PROGRAMAR.hex',hw,fw,self.operator)
        f.approve(saved['id'],self.operator,'Pruebas simuladas de catalogo; no hardware.')
        return saved

    def test_seed_legacy_and_no_image_in_list(self):
        d=f.catalogue('R3')
        self.assertEqual(d['default_id'],'base-R3')
        self.assertEqual(d['items'][0]['fw'],'1.0')
        self.assertNotIn('image',d['items'][0])

    def test_numeric_version_default_compatible_hw_and_older_selection(self):
        a=self.save('1.9',1); b=self.save('1.10',2); self.save('2.0',3,'3.1')
        self.assertEqual(f.catalogue('R3','30')['default_id'],b['id'])
        current,_=s.preview(self.r3['id'])
        self.assertEqual(current['identity']['fw'],'1.10')
        old,_=s.preview(self.r3['id'],firmware_id=a['id'])
        self.assertEqual(old['identity']['fw'],'1.9')
        with self.assertRaises(ValueError): s.preview(self.card['r1']['id'],firmware_id=a['id'])

    def test_queued_job_keeps_selected_image_when_newer_uploaded(self):
        a=self.save(); data,image=s.preview(self.r3['id'],firmware_id=a['id'])
        job=s.create_job(self.r3['id'],self.station['id'],data['hex_sha256'],self.operator,True,a['id'])
        self.save('1.2',2)
        claimed=s.claim(self.station['id'])
        self.assertEqual(claimed['id'],job['id'])
        self.assertEqual(claimed['hex'],image)
        self.assertEqual(claimed['payload']['firmware_id'],a['id'])
        self.assertEqual(claimed['payload']['identity']['fw'],'1.1')

    def test_duplicate_immutable_and_conflicting_label_rejected(self):
        a=self.save(); b=self.save()
        self.assertEqual(a['id'],b['id']); self.assertTrue(b['existing'])
        with self.assertRaises(ValueError): self.save('1.2')
        self.assertEqual(s.analizar_hex(self.simulated(),'R3')['fw'],'1.1')

    def test_checksum_vectors_reserved_page_and_version_rejected(self):
        bad=self.simulated().replace(':02000004',':02000005',1)
        with self.assertRaises(ValueError): f.save(bad,'R3','bad.hex','3.0','1.1',self.operator)
        for mem in ({hx.FLASH_BEGIN:0},dict(self.mem,**{})):
            if len(mem)>1: mem[hx.IDENTITY_BEGIN]=1
            with self.assertRaises(ValueError): f.save(hx.emitir_hex(mem),'R3','bad.hex','3.0','1.1',self.operator)
        with self.assertRaises(ValueError): self.save('desconocida')
        with self.assertRaises(ValueError): f.save(self.base,'R3','bad.bin','3.0','1.0',self.operator)

    def test_r1_removes_old_identity_and_uses_inventory(self):
        data,image=s.preview(self.card['r1']['id'])
        saved=f.save(image,'R1','r1_personalizado.hex','','',self.operator)
        self.assertTrue(saved['identity_removed'])
        with db.get_db() as c:
            meta,stored=f.selected(c,'R1','30',saved['id'])
        mem,_=f.parse(stored)
        self.assertFalse(any(a>=hx.IDENTITY_BEGIN for a in mem))
        d,new=s.preview(self.card['r1']['id'],firmware_id=saved['id'])
        newmem,_=f.parse(new)
        self.assertEqual(hx.leer_identidad(newmem)['nombre'],d['identity']['nombre'])
        with self.assertRaises(ValueError): f.save(image,'R1','wrong.hex','3.0','9.9',self.operator)
        with self.assertRaises(ValueError): f.save(image,'R3','wrong.hex','3.0','9.9',self.operator)

    def test_hash_tamper_and_wrong_hardware_fail_closed(self):
        saved=self.save()
        with db.get_db() as c:
            c.execute('UPDATE stm32_firmwares SET image=? WHERE id=?',('invalid',saved['id']))
        with self.assertRaises(ValueError): s.preview(self.r3['id'],firmware_id=saved['id'])
        with self.assertRaises(ValueError): s.preview(self.r3['id'],firmware_id='missing')

    def test_upload_authenticated_and_download_exact_selected_hex(self):
        anon=iso.cliente_sin_sesion(app)
        body=dict(tipo='R3',filename='simulation.hex',contenido=self.simulated(),hw='3.0',fw='1.1')
        self.assertEqual(anon.post('/api/stm32/firmwares',json=body).status_code,401)
        with patch('app.routers.stm32.operator',return_value=self.operator):
            client=TestClient(app,base_url='https://testserver')
            self.assertEqual(client.post('/api/stm32/firmwares',json=body,headers={'Origin':'https://otro.invalid'}).status_code,403)
            response=client.post('/api/stm32/firmwares',json=body)
            self.assertEqual(response.status_code,200)
            identifier=response.json()['id']
            preview=client.get(f'/api/stm32/preview/{self.r3["id"]}?firmware_id={identifier}').json()
            self.assertEqual(preview['identity']['fw'],'1.1')
            downloaded=client.get(f'/api/stm32/hex/{self.r3["id"]}?firmware_id={identifier}')
            self.assertEqual(downloaded.text,body['contenido'])
            body.update(station_id=self.station['id'],pcb_id=self.r3['id'],firmware_id=identifier,hex_sha256=preview['hex_sha256'],physical_confirmed=True)
            self.assertEqual(client.post('/api/stm32/jobs',json=body).status_code,200)


class BetaCatalogueTests(FirmwareCatalogueTests):
    def beta(self,fw='9.8',delta=18):
        return f.save(self.simulated(delta),'R3','BETA_NO_PROGRAMAR.hex','3.0',fw,self.operator)

    def test_beta_never_default_or_latest_even_after_inventory_recorded(self):
        before=f.catalogue('R3','30')['default_id']
        beta=self.beta()
        cat=f.catalogue('R3','30')
        self.assertEqual(cat['default_id'],before)
        self.assertEqual(next(x for x in cat['items'] if x['id']==beta['id'])['release_status'],'beta')
        self.assertEqual(s.preview(self.r3['id'],firmware_id=beta['id'])[0]['identity']['fw'],'9.8')
        inv.set_firmware(self.r3['id'],'9.8',self.operator)
        self.assertNotIn('9.8',inv.listar_firmware()['R3'])
        approved=f.approve(beta['id'],self.operator,'Tarjeta simulada: prueba de promocion, sin hardware.')
        self.assertEqual(approved['release_status'],'aprobado')
        self.assertEqual(f.catalogue('R3','30')['default_id'],beta['id'])
        self.assertIn('9.8',inv.listar_firmware()['R3'])
        self.assertEqual(f.approve(beta['id'],self.operator,'Segunda aprobacion idempotente')['approved_at'],approved['approved_at'])

    def test_duplicate_beta_does_not_approve_and_approval_preserves_image(self):
        a=self.beta(); b=self.beta()
        self.assertEqual(a['id'],b['id']); self.assertEqual(b['release_status'],'beta')
        with db.get_db() as c:
            before=c.execute('SELECT image,sha256 FROM stm32_firmwares WHERE id=?',(a['id'],)).fetchone()
        with self.assertRaises(ValueError):f.approve(a['id'],self.operator,'')
        f.approve(a['id'],self.operator,'Pruebas simuladas de promocion correctas.')
        with db.get_db() as c:
            after=c.execute('SELECT image,sha256 FROM stm32_firmwares WHERE id=?',(a['id'],)).fetchone()
        self.assertEqual(tuple(before),tuple(after))

    def test_approval_rejects_tampered_image_and_non_admin(self):
        from app.routers.stm32 import approve_firmware,FirmwareApproval
        from fastapi import HTTPException
        from types import SimpleNamespace
        a=self.beta();req=SimpleNamespace(cookies={})
        body=FirmwareApproval(evidence='Pruebas realizadas y aprobadas por operador.')
        with patch('app.routers.stm32.usuarios.validar_sesion',return_value={'email':self.operator,'rol':'general'}):
            with self.assertRaises(HTTPException) as ex:approve_firmware(a['id'],body,req)
            self.assertEqual(ex.exception.status_code,403)
        with db.get_db() as c:c.execute('UPDATE stm32_firmwares SET image=? WHERE id=?',('corrupto',a['id']))
        with self.assertRaises(ValueError):f.approve(a['id'],self.operator,body.evidence)
