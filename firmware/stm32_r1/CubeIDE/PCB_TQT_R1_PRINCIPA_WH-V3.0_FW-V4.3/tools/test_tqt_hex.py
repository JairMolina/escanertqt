"""Offline tests against real CubeIDE outputs. Never opens a probe or USB port."""
import hashlib
import json
import re
import shutil
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
import tqt_hex as t

PROJECT = Path(__file__).resolve().parents[1]
NAME = 'PCB_TQT_R1_PRINCIPA_WH-V3.0_FW-V4.3'

class IdentityTests(unittest.TestCase):
    def setUp(self):
        self.test_root = PROJECT/'tools/.test-tmp'
        self.test_root.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=self.test_root)
        self.dir = Path(self.temp.name)
        self.source = PROJECT/'Debug'/(NAME+'.hex')
        self.mem,self.starts=t.leer_hex(self.source)
        self.profile=t.leer_perfil(self.mem)
    def tearDown(self):
        assert self.dir.resolve().is_relative_to(self.test_root.resolve())
        self.temp.cleanup()
    def cli(self,*args,ok=True):
        p=subprocess.run([sys.executable,str(PROJECT/'tools/tqt_hex.py'),*map(str,args)],capture_output=True,text=True)
        self.assertEqual(p.returncode==0,ok,p.stdout+p.stderr)
        return p
    def test_crc_known_vector(self):
        self.assertEqual(zlib.crc32(b'123456789'),0xCBF43926)
    def test_real_debug_and_release(self):
        for config in ('Debug','Release'):
            mem,_=t.leer_hex(PROJECT/config/(NAME+'.hex'))
            i=t.leer_identidad(mem)
            t.comprobar_perfil(i,t.leer_perfil(mem))
            settings=(PROJECT/'Core/Inc/Datos_editar.h').read_text(encoding='utf-8')
            for macro,key in [('TQT_FW_VERSION','fw'),('TQT_LOCAL_ID','id_r'),('TQT_LOCAL_NAME','nombre')]:
                expected=re.search(r'^#define\s+'+macro+r'\s+"([^"]+)"',settings,re.M).group(1)
                self.assertEqual(i[key],expected)
            generated=t.identidad_bytes(i['nombre'],i['id_r'],i['mac_r'],i['hw'],i['fw'])
            self.assertEqual(generated,bytes(mem[t.IDENTITY_BEGIN+k] for k in range(t.SIZE)))
    def test_two_units_only_change_identity(self):
        original_hash=hashlib.sha256(self.source.read_bytes()).hexdigest()
        base=self.dir/'base.hex'
        self.cli('preparar-web','--hex',self.source,'--salida',base)
        outputs=[]
        for serial in ('0023','0024'):
            out=self.dir/(serial+'.hex')
            self.cli('personalizar','--hex',base,'--nombre','TQT_R1_V30_'+serial,
                     '--id',serial,'--mac-r','8C:8C:29:C3:F4:47','--hw','3.0','--salida',out)
            mem,_=t.leer_hex(out); outputs.append(mem)
            self.assertEqual({a:b for a,b in mem.items() if a<t.IDENTITY_BEGIN},
                             {a:b for a,b in self.mem.items() if a<t.IDENTITY_BEGIN})
            manifest=json.loads(out.with_suffix('.hex.json').read_text())
            self.assertEqual(manifest['identity']['fw'],'4.3')
            self.assertEqual(manifest['hex_sha256'],hashlib.sha256(out.read_bytes()).hexdigest())
        changed={a for a in outputs[0] if outputs[0][a]!=outputs[1][a]}
        self.assertTrue(changed)
        self.assertTrue(all(t.IDENTITY_BEGIN<=a<t.IDENTITY_BEGIN+t.SIZE for a in changed))
        self.assertEqual(original_hash,hashlib.sha256(self.source.read_bytes()).hexdigest())
    def test_r1_and_r2_independent(self):
        payload=t.identidad_bytes('TQT_R1_V30_0045','0032','8C:8C:29:C3:F4:47','3.0',self.profile['fw'])
        identity=t.parsear_identidad(payload)
        t.comprobar_perfil(identity,self.profile)
        self.assertEqual(identity['nombre'],'TQT_R1_V30_0045')
        self.assertEqual(identity['id_r'],'0032')

    def test_local_generator_independent_pair(self):
        inc=self.dir/'Core/Inc'; inc.mkdir(parents=True)
        settings=(PROJECT/'Core/Inc/Datos_editar.h').read_text(encoding='utf-8')
        settings=re.sub(r'(#define TQT_LOCAL_NAME )"[^"]+"',r'\1"TQT_R1_V30_0045"',settings)
        settings=re.sub(r'(#define TQT_LOCAL_ID )"[^"]+"',r'\1"0032"',settings)
        (inc/'Datos_editar.h').write_text(settings,encoding='utf-8')
        shutil.copy2(PROJECT/'Core/Inc/tqt_identity.h',inc/'tqt_identity.h')
        run=subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',
                            str(PROJECT/'tools/generate_identity.ps1'),'-ProjectRoot',str(self.dir)],
                           capture_output=True,text=True)
        self.assertEqual(run.returncode,0,run.stdout+run.stderr)
        generated=(inc/'tqt_identity_generated.h').read_text()
        payload=bytes(int(x,16) for x in re.findall(r'0x([A-F0-9]{2})',generated))
        identity=t.parsear_identidad(payload)
        self.assertEqual(identity['nombre'],'TQT_R1_V30_0045')
        self.assertEqual(identity['id_r'],'0032')
        self.assertEqual(payload,t.identidad_bytes(identity['nombre'],identity['id_r'],
                         identity['mac_r'],identity['hw'],identity['fw']))

    def test_wrong_fw_rejected_even_with_valid_crc(self):
        payload=t.identidad_bytes('TQT_R1_V30_0022','0022','8C:8C:29:C3:F4:46','3.0','4.2')
        with self.assertRaises(ValueError):
            t.comprobar_perfil(t.parsear_identidad(payload),self.profile)
    def test_wrong_hw_rejected(self):
        payload=t.identidad_bytes('TQT_R1_V31_0022','0022','8C:8C:29:C3:F4:46','3.1','4.3')
        with self.assertRaises(ValueError):
            t.comprobar_perfil(t.parsear_identidad(payload),self.profile)
    def test_corrupted_crc(self):
        raw=bytearray(self.mem[t.IDENTITY_BEGIN+k] for k in range(t.SIZE))
        raw[10]^=1
        with self.assertRaises(ValueError): t.parsear_identidad(bytes(raw))
    def test_corrupt_fields_with_recomputed_crc(self):
        for offset,value in [(35,ord('X')),(30,ord('X')),(70,1),(36,ord('g'))]:
            raw=bytearray(self.mem[t.IDENTITY_BEGIN+k] for k in range(t.SIZE))
            raw[offset]=value; raw[72:]=struct.pack('<I',zlib.crc32(raw[:72]))
            with self.assertRaises(ValueError): t.parsear_identidad(bytes(raw))
    def test_invalid_inputs(self):
        for name,serial,mac in [('TQT_R1_V30_0022','22','8C:8C:29:C3:F4:46'),
                                ('TQT_R1_V30_002','0022','8C:8C:29:C3:F4:46'),
                                ('TQT_R1_V30_0022','0022','00:00:00:00:00:00'),
                                ('TQT_R1_V30_0022','0022','8C:8C:29:C3:F4')]:
            with self.assertRaises(ValueError): t.identidad_bytes(name,serial,mac,'3.0','4.3')
    def test_no_overwrite(self):
        out=self.dir/'base.hex'; out.write_text('keep')
        self.cli('preparar-web','--hex',self.source,'--salida',out,ok=False)
        self.assertEqual(out.read_text(),'keep')
    def test_missing_profile_and_bad_vector(self):
        with self.assertRaises(ValueError): t.leer_perfil({t.FLASH_BEGIN:0})
        mem=dict(self.mem); mem[t.FLASH_BEGIN+4]&=0xFE
        with self.assertRaises(ValueError): t.leer_perfil(mem)
    def test_overlap_and_bad_checksum(self):
        for data in [t._registro(4,0,b'\x08\x00')+'\n'+t._registro(0,0,b'\x01')+'\n'+t._registro(0,0,b'\x01')+'\n'+t._registro(1,0,b'')+'\n',
                     ':010000000100\n:00000001FF\n']:
            path=self.dir/'bad.hex'; path.write_text(data)
            with self.assertRaises(ValueError): t.leer_hex(path)
    def test_out_of_range_and_partial_identity(self):
        path=self.dir/'bad.hex'; path.write_text(t.emitir_hex({0x08080000:0}))
        with self.assertRaises(ValueError): t.leer_hex(path)
        mem=dict(self.mem); del mem[t.IDENTITY_BEGIN+3]
        with self.assertRaises(ValueError): t.leer_identidad(mem)

if __name__=='__main__': unittest.main(verbosity=2)
