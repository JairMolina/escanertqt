"""Deterministic fake devices exercise the complete sequence without touching hardware."""
import tempfile
import time
import unittest
from pathlib import Path
from tqtstation.engine import TestStation
from tqtstation.protocol import FIELDS
from tqtstation.ble import FoundDevice

class Fixture:
    def __init__(self):
        self.values={k:'0' for k in FIELDS}
        self.values.update({'VER':'4.3','HW':'3.0','MAC':'AA:BB:CC:DD:EE:FF',
                            'MACR':'11:22:33:44:55:66','ID':'0011','IDR':'R2',
                            'Mensaje':'1.0','ON':'0','OFF':'1','TQT':'0','PB':'0','MOV':'0','SEN_MOT':'0','MOTOR':'0'})
        self.station=None
        self.active_ble=''
        self.devices={}
        self.connected=True
    def emit(self):
        text='AT$POST=1,0,"S29|'+ '|'.join(k+';'+self.values[k] for k in FIELDS) + '"'
        self.station.on_line(text)
    def move(self,cmd,origin):
        target= 'cerrado' if cmd=='POFF' else 'abierto'
        old = 'cerrado' if self.values['ON']=='1' else 'abierto'
        self.values['PB']=str(origin)
        self.values['ON']='1' if target=='cerrado' else '0'
        self.values['OFF']='1' if target=='abierto' else '0'
        if target!=old:
            if origin in (1,2): self.values['MOV']=str(int(self.values['MOV'])+1)
            else: self.values['err']='14' if target=='cerrado' else '13'
        self.emit()
    def send(self,raw):
        cmd=raw.decode().strip()
        if cmd=='$SMSG=Reset_44':
            self.station.on_line('AT$POST=1,0,"TQT_R1_V3_0_0011 - Lista para usarse "')
            self.emit()
        elif cmd=='$SMSG=Status': self.emit()
        elif cmd=='$SMSG=Status_Motor':
            suffix='Bloqueado' if self.values['ON']=='1' else 'Desbloqueado'
            self.station.on_line('AT$POST=1,0,"TQT_R1 - El perno esta '+suffix+'"')
        elif cmd=='$SMSG=ON': self.move('PPON',1)
        elif cmd=='$SMSG=OFF': self.move('POFF',1)
    def scan(self):
        names=[FoundDevice('TQT_R1_V3_0_0011','AA:BB:CC:DD:EE:FF'),FoundDevice('TQT_R2_V3_0_0011','11:22:33:44:55:66')]
        self.devices={d.address:d for d in names}
        return names
    def connect(self,addr):self.active_ble=addr
    def disconnect(self):self.active_ble=''
    def send_ble(self,cmd):self.move(cmd,2 if self.active_ble=='AA:BB:CC:DD:EE:FF' else 3)

class FakeSerial:
    def __init__(self,fx):self.fx=fx;self.connected=True
    def send(self,raw):self.fx.send(raw)
class FakeBLE:
    def __init__(self,fx):self.fx=fx;self.devices={}
    def scan(self):
        arr=self.fx.scan();self.devices=self.fx.devices;return arr
    def connect(self,addr):self.fx.connect(addr)
    def disconnect(self):self.fx.disconnect()
    def send(self,cmd):self.fx.send_ble(cmd)

class TestWorkflow(unittest.TestCase):
    def test_full_flow_with_fake_hardware(self):
        fx=Fixture();ui=[]
        station=TestStation(FakeSerial(fx),FakeBLE(fx),lambda *a:ui.append(a))
        fx.station=station;station.repeat_verify_s=.08
        with tempfile.TemporaryDirectory() as tmp:
            station.output_dir=Path(tmp)
            station.start('COM_SIMULADO','11:22:33:44:55:66')
            station._run_thread.join(20)
            self.assertFalse(station._run_thread.is_alive())
            self.assertEqual(station.report['result'],'aprobado',station.report)
            self.assertEqual(station.report['ending_position'],'abierto')
            self.assertEqual(len(list(Path(tmp).glob('*.json'))),1)
            self.assertEqual(len(list(Path(tmp).glob('*.log'))),1)
            self.assertEqual(len(station.steps),14)

    def test_start_closed_autoselects_pon_first_and_r2_by_macr(self):
        fx=Fixture();fx.values['ON']='1';fx.values['OFF']='0'
        ui=[];station=TestStation(FakeSerial(fx),FakeBLE(fx),lambda *a:ui.append(a))
        fx.station=station;station.repeat_verify_s=.08
        with tempfile.TemporaryDirectory() as tmp:
            station.output_dir=Path(tmp)
            station.start('COM_FAKE')
            station._run_thread.join(20)
            self.assertFalse(station._run_thread.is_alive())
            self.assertEqual(station.report['result'],'aprobado',station.report)
            self.assertEqual(station.report['ending_position'],'cerrado')
            self.assertIn('PPON',station.steps[2].name)
            self.assertEqual(station.report['r2_ble_address'],'11:22:33:44:55:66')

    def test_start_inconsistent_sensor_fails_without_motion(self):
        fx=Fixture();fx.values['ON']='1';fx.values['OFF']='1'
        commands=[]
        class AuditSerial(FakeSerial):
            def send(self,raw):
                commands.append(raw.decode('ascii'))
                super().send(raw)
        st=TestStation(AuditSerial(fx),FakeBLE(fx),lambda *a:None)
        fx.station=st;st.repeat_verify_s=.08
        with tempfile.TemporaryDirectory() as tmp:
            st.output_dir=Path(tmp);st.start('COM_FAKE')
            st._run_thread.join(20)
            self.assertEqual(st.report['result'],'fallido')
            self.assertFalse(any(v.startswith('$SMSG=ON') or v.startswith('$SMSG=OFF') for v in commands))

if __name__=='__main__':unittest.main()
