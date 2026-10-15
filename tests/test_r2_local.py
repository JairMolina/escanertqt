import _aislamiento
import importlib.util,json,tempfile,unittest
from pathlib import Path

PROJECT=Path(__file__).resolve().parents[1]/'firmware/esp32_r2/TQT_R2_V4_2'
spec=importlib.util.spec_from_file_location('r2_local',PROJECT/'preparar_local.py')
local=importlib.util.module_from_spec(spec);spec.loader.exec_module(local)

class LocalFirmwareTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Path(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def test_private_project_exact_name_and_stable_per_unit_key(self):
        original=(PROJECT/'tqt_profile.cpp').read_bytes()
        a=local.prepare(PROJECT,self.store,'TQT-R2-V30-0067')
        first=Path(a['project'],'tqt_profile.cpp').read_bytes()
        b=local.prepare(PROJECT,self.store,'TQT-R2-V30-0067',fw='4.3')
        self.assertEqual(a['key_id'],b['key_id']);self.assertFalse(b['new_identity'])
        self.assertIn(b'"TQT-R2-V30-0067"',first)
        self.assertIn(b'"4.3"',Path(b['project'],'tqt_profile.cpp').read_bytes())
        self.assertEqual(original,(PROJECT/'tqt_profile.cpp').read_bytes())
        self.assertNotIn(json.loads(Path(a['identity_file']).read_text())['ota_key'].encode(),original)
        other=local.prepare(PROJECT,self.store,'TQT-R2-V30-0068')
        self.assertNotEqual(a['key_id'],other['key_id'])
    def test_existing_web_identity_is_preserved(self):
        path=self.store/'web.json';path.write_text(json.dumps(dict(nombre='TQT-R2-V30-0067',hw='3.0',ota_key='ab'*32,web_registered=True)))
        before=path.read_bytes();r=local.prepare(PROJECT,self.store,'TQT-R2-V30-0067',identity_file=path)
        self.assertTrue(r['web_registered']);self.assertEqual(before,path.read_bytes())
        self.assertIn('0xab',Path(r['project'],'tqt_profile.cpp').read_text())
    def test_invalid_name_hw_version_and_wrong_credential_rejected(self):
        for name,hw,fw in [('TQT_R2_V30_0067','3.0','4.2'),('TQT-R2-V30-0000','3.0','4.2'),('TQT-R2-V31-0067','3.0','4.2'),('TQT-R2-V30-0067','3.0','3.1')]:
            with self.assertRaises(ValueError):local.prepare(PROJECT,self.store,name,hw,fw)
        with self.assertRaises(ValueError):local.prepare(PROJECT,self.store,'TQT-R2-V30-0067',identity_file=self.store/'missing.json')
        a=local.prepare(PROJECT,self.store,'TQT-R2-V30-0067')
        with self.assertRaises(ValueError):local.prepare(PROJECT,self.store,'TQT-R2-V30-0068',identity_file=a['identity_file'])
