"""Real RX frames supplied by the operator (card 0036)."""
import unittest
import time
from tqtstation.protocol import FIELDS, parse_status, serial_action
from tqtstation.serial_port import SerialLink

BASE='AT$POST=1,0,"S29|BLK;0|OUT1;0|OUT2;0|OUT3;1|INT1;0|INT2;0|INT3;0|EST1;1|EST2;1|EST3;0|MOTOR;0|SEN_MOT;0|TIEMPO;0|DBG;0|VIVA;1|TQT;3|ON;0|OFF;1|PB;1|err;0|RESET;1|VER;4.2|HW;3.0|MOV;0|Mensaje;4.0|IDR;0077|MACR;8C:8C:29:C3:F4:86|ID;0036|MAC;8c:8c:29:c3:d7:fe"'
class LiveLogTests(unittest.TestCase):
    def test_during_motor(self):
        s=parse_status(BASE)
        self.assertEqual(len(s.fields),29)
        self.assertEqual(s.fields['ID'],'0036')
        self.assertEqual(s.position,'abierto')
        self.assertEqual(s.number('TQT'),3)
    def test_after_motor(self):
        text=BASE.replace('TQT;3','TQT;0').replace('ON;0|OFF;1','ON;1|OFF;0').replace('MOV;0','MOV;1')
        s=parse_status(text)
        self.assertEqual(s.position,'cerrado')
        self.assertEqual(s.number('MOV'),1)
    def test_ack_retry_diagnostic(self):
        msgs=[];link=SerialLink(lambda s: None,msgs.append)
        link._observe_retry(BASE)
        self.assertEqual(msgs,[])
        link._observe_retry(BASE.replace('Mensaje;4.0','Mensaje;4.1'))
        self.assertEqual(len(msgs),1)
        self.assertIn('reintento 1',msgs[0])
        self.assertEqual(serial_action('POFF'),b'$SMSG=OFF\r\n')

if __name__=='__main__': unittest.main()

class SerialAckBytesTests(unittest.TestCase):
    def test_ack_is_dollar_ok_crlf_and_reaches_serial_write(self):
        logs = []
        received = []
        link = SerialLink(received.append, logs.append)
        class FakePort:
            is_open = True
            in_waiting = 512
            writes = []
            def read(self, n):
                link._running.clear()
                return (BASE + '\r\n').encode('ascii')
            def write(self, data):
                self.writes.append(data)
                return len(data)
            def flush(self): pass
        fake = FakePort()
        link._serial = fake
        link._running.set()
        t0 = time.monotonic()
        link._read()
        self.assertGreaterEqual(time.monotonic() - t0, 0.17)
        self.assertEqual(fake.writes,[b'$OK\r\n'])
        self.assertEqual(received,[BASE])
        self.assertIn('TX SERIAL: $OK[CR][LF]',logs)
