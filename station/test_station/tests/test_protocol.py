import unittest
from tqtstation.protocol import FIELDS, parse_status, read_ready, normalize_mac, serial_action


def example(sep='|', val=';', **replacements):
    fields = {k:'0' for k in FIELDS}
    fields.update({'VER':'4.3','HW':'3.0','MAC':'AA:BB:CC:DD:EE:FF',
                   'MACR':'11:22:33:44:55:66', 'ID':'0011','IDR':'R2','Mensaje':'23.0','ON':'1',
                   'OFF':'0','TQT':'0', 'MOV':'7'})
    fields.update(replacements)
    return 'AT$POST=1,0,"S29'+sep+sep.join(k+val+fields[k] for k in FIELDS)+'"'

class ProtocolTests(unittest.TestCase):
    def test_29_fields(self):
        report=parse_status(example())
        self.assertIsNotNone(report)
        self.assertEqual(len(report.fields),29)
        self.assertEqual(report.position,'cerrado')
        self.assertEqual(report.fields['MAC'],'AA:BB:CC:DD:EE:FF')
    def test_changed_separators(self):
        report=parse_status(example(sep='-', val=':'))
        self.assertEqual(report.fields['ID'],'0011')
        self.assertEqual(report.fields['MAC'],'AA:BB:CC:DD:EE:FF')
    def test_ignore_unrelated(self):
        self.assertIsNone(parse_status('AT$POST=1,0,"texto"'))
        self.assertIsNone(parse_status('AT$POST=1,0,"S29|bad"'))
    def test_ready(self):
        self.assertEqual(read_ready('AT$POST=1,0,"TQT_R1_V3_0_0011 - Lista para usarse "'),'TQT_R1_V3_0_0011')
    def test_commands(self):
        self.assertEqual(serial_action('POFF'),b'$SMSG=OFF\r\n')
        self.assertEqual(serial_action('RESET_FACTORY'),b'$SMSG=Reset_44\r\n')
        with self.assertRaises(ValueError):serial_action('AT$OUTC=5')
    def test_mac(self):
        self.assertEqual(normalize_mac('AA-BB:cc:dd:ee:ff'),'AABBCCDDEEFF')

if __name__=='__main__':unittest.main()
