"""Serial frames arriving in fragments, corrupt short frames, and reset startup."""
import tempfile
import time
import threading
import unittest
from collections import deque
from pathlib import Path
from tqtstation.serial_port import SerialLink
from tqtstation.protocol import parse_status
from test_engine_fake import Fixture, FakeSerial, FakeBLE
from tqtstation.engine import TestStation

CARD = 'TQT_R1_V3_0_0036'
READY = f'AT$POST=1,0,"{CARD} - Lista para usarse "'
STATUS = ('AT$POST=1,0,"S29|BLK;0|OUT1;0|OUT2;0|OUT3;1|INT1;0|INT2;0|INT3;0|'
          'EST1;1|EST2;1|EST3;0|MOTOR;0|SEN_MOT;0|TIEMPO;0|DBG;0|VIVA;1|TQT;0|'
          'ON;0|OFF;1|PB;0|err;0|RESET;1|VER;4.2|HW;3.0|MOV;0|Mensaje;1.0|'
          'IDR;0077|MACR;8C:8C:29:C3:F4:86|ID;0036|MAC;8c:8c:29:c3:d7:fe"')

class ReplaySerial:
    def __init__(self, link, fragments):
        self.link = link
        self.is_open = True
        self.fragments = deque(fragments)
        self.writes = []
    @property
    def in_waiting(self): return len(self.fragments[0]) if self.fragments else 0
    def read(self, n):
        if not self.fragments:
            self.link._running.clear()
            return b''
        data = self.fragments.popleft()
        if not self.fragments:
            self.link._running.clear()
        return data
    def write(self, data):
        self.writes.append(data)
        return len(data)
    def flush(self): pass

class FragmentTests(unittest.TestCase):
    def test_complete_status_delivered_across_many_usb_fragments(self):
        received, logs = [], []
        link = SerialLink(received.append, logs.append)
        chunks = [STATUS.encode('ascii')[i:i + 11] for i in range(0, len(STATUS), 11)]
        fake = ReplaySerial(link, chunks + [b'\r', b'\n'])
        link._serial = fake
        link._running.set()
        link.ack_delay_s = 0.001
        link._read()
        self.assertEqual(received, [STATUS])
        self.assertEqual(fake.writes, [b'$OK\r\n'])
        self.assertEqual(parse_status(received[0]).fields['ID'], '0036')
        self.assertEqual(link.health['partial_warnings'], 0)

    def test_corrupt_header_is_excluded_but_hex_preserved(self):
        received, logs = [], []
        link = SerialLink(received.append, logs.append)
        link.ack_delay_s = .001
        # Trama dañada similar al prefijo observado en las sesiones del usuario.
        fake = ReplaySerial(link,[b'P\x15\x12\xffMQ\x811,0," SPAS = |  SPAV = ;"\r\n'])
        link._serial=fake;link._running.set();link._read()
        self.assertEqual(received, [])
        self.assertEqual(link.health['corrupt_frames'], 1)
        self.assertTrue(any('RX HEX CORRUPTA' in msg for msg in logs))
        self.assertTrue(any('50 15 12 FF' in msg for msg in logs))
        self.assertEqual(fake.writes, [], 'No se confirma una trama sin cabecera válida')

    def test_truncated_status_with_early_newline_is_diagnosed(self):
        received, logs = [], []
        link = SerialLink(received.append, logs.append)
        link.ack_delay_s = 0.001
        fake = ReplaySerial(link, [b'AT$POST=1,0,"S29|BLK;0\r\n'])
        link._serial, link._running = fake, threading.Event()
        link._running.set()
        link._read()
        self.assertEqual(received, [], 'Una trama S29 incompleta no debe llegar al motor de pruebas')
        self.assertEqual(link.health['partial_warnings'], 1)
        self.assertTrue(any('S29 incompleto' in msg for msg in logs))

class ResetStartupTests(unittest.TestCase):
    def test_waits_for_spontaneous_s29_without_immediate_status_query(self):
        fx=Fixture()
        sent=[]
        class ResetSerial(FakeSerial):
            def send(self,raw):
                sent.append(raw.decode('ascii').strip())
                if raw == b'$SMSG=Reset_44\r\n':
                    fx.station.on_line('AT$POST=1,0,"TQT_R1_V3_0_0011 - Lista para usarse "')
                    threading.Timer(.12, fx.emit).start()
                else:
                    super().send(raw)
        station=TestStation(ResetSerial(fx), FakeBLE(fx), lambda *a: None)
        fx.station=station;station.repeat_verify_s=.08
        with tempfile.TemporaryDirectory() as tmp:
            station.output_dir=Path(tmp)
            station.start('COM_SIM')
            station._run_thread.join(15)
            self.assertFalse(station.running,station.report)
            self.assertEqual(station.report['result'], 'aprobado', station.report)
        self.assertEqual(sent[0], '$SMSG=Reset_44')
        self.assertEqual(sent[1], '$SMSG=OFF', sent[:4])

if __name__=='__main__': unittest.main()
