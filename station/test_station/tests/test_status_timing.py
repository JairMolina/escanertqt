"""v0.6.3: sin retardo especial de Status, ACK prioritario y barrera S29 intacta."""
import threading
import time
import unittest
from tqtstation.serial_port import SerialLink
from tqtstation.reporting import report_html


class Port:
    def __init__(self):
        self.is_open = True
        self.writes = []
    def write(self, payload):
        self.writes.append((time.monotonic(), payload))
        return len(payload)
    def flush(self): pass


class StatusTimingTests(unittest.TestCase):
    def link(self, quiet=.025):
        logs=[]
        link=SerialLink(lambda x:None, logs.append)
        link._serial=Port()
        link._running.set()
        link.command_quiet_s=quiet
        return link,logs

    def test_no_extra_status_delay_attribute(self):
        link,_=self.link()
        self.assertFalse(hasattr(link,'status_quiet_s'))

    def test_status_uses_same_guard_as_other_commands(self):
        link,_=self.link(.060)
        link.send(b'$SMSG=ON\r\n')
        t1=link._serial.writes[-1][0]
        link.send(b'$SMSG=Status\r\n')
        t2=link._serial.writes[-1][0]
        self.assertGreaterEqual(t2-t1,.055)
        self.assertLess(t2-t1,.25)

    def test_status_uses_rx_guard_not_one_second(self):
        link,_=self.link(.05)
        link._last_rx=time.monotonic()
        started=time.monotonic()
        link.send(b'$SMSG=Status\r\n')
        elapsed=time.monotonic()-started
        self.assertGreaterEqual(elapsed,.045)
        self.assertLess(elapsed,.30)

    def test_ack_has_priority_when_status_pending(self):
        link,_=self.link(.9)
        link._pending_status.set()
        started=time.monotonic()
        link.send(b'$OK\r\n')
        self.assertLess(time.monotonic()-started,.2)
        self.assertEqual(link._serial.writes[-1][1],b'$OK\r\n')
        self.assertTrue(link._pending_status.is_set())

    def test_pending_status_blocks_next_motor_command_until_s29(self):
        link,_=self.link(.02)
        link.send(b'$SMSG=Status\r\n')
        done=threading.Event()
        def worker():
            link.send(b'$SMSG=OFF\r\n')
            done.set()
        thread=threading.Thread(target=worker)
        thread.start()
        time.sleep(.07)
        self.assertFalse(done.is_set())
        self.assertEqual([v for t,v in link._serial.writes],[b'$SMSG=Status\r\n'])
        link._pending_status.clear() # llegada del S29 válido
        thread.join(2)
        self.assertTrue(done.is_set())
        self.assertEqual(link._serial.writes[-1][1],b'$SMSG=OFF\r\n')

    def test_report_displays_zero_extra_status_and_guard(self):
        report={'report_schema':'tqt-station/0.6.3','date':'2026-10-13T13:00:00-06:00',
                'card':'TQT_R1_V30_0036','result':'aprobado',
                'serial_timing':{'ack_delay_ms':180,'status_quiet_ms':0,'command_quiet_ms':300},
                'steps':[],'communication_quality':{},'serial_health':{},'inventory_check':{},'warnings':[]}
        html=report_html(report)
        self.assertIn('Espera adicional Status</th><td>0 ms',html)
        self.assertIn('Guardia de canal</th><td>300 ms',html)
        self.assertIn('Espera ACK configurada</th><td>180 ms',html)
        self.assertIn('TEST STATION v0.6.3',html)

if __name__=='__main__': unittest.main()
