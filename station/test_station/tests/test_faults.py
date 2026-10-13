"""Escenarios aportados por el banco real 0036: sensor ON, OFF y motor sin energía."""
import tempfile
import time
import unittest
from pathlib import Path
from tqtstation.engine import TestStation, NoVerification
from test_engine_fake import Fixture, FakeSerial, FakeBLE

class NoClose(Fixture):
    """El comando POFF se recibe, pero el sensor de cierre nunca se activa."""
    def move(self, cmd, origin):
        if cmd == 'POFF' and origin == 1:
            self.values.update({'TQT':'3', 'PB':'1'})
            self.emit()
            self.values.update({'TQT':'5','ON':'0','OFF':'0','err':'4'})
            self.emit()
        else:
            super().move(cmd,origin)

class WarningCurrent(Fixture):
    def move(self, cmd, origin):
        if cmd == 'POFF' and origin == 1:
            self.values.update({'err':'15','PB':'1'})
            self.emit()
            self.values['err']='0'
        super().move(cmd,origin)

class FaultTests(unittest.TestCase):
    def start_once(self, fx):
        ui=[]
        station=TestStation(FakeSerial(fx), FakeBLE(fx),lambda *a:ui.append(a))
        station.repeat_verify_s=.08
        fx.station=station
        with tempfile.TemporaryDirectory() as path:
            station.output_dir=Path(path)
            station.start('COM_FAKE')
            station._run_thread.join(9)
            self.assertFalse(station.running)
            self.assertEqual(len(list(Path(path).glob('*.json'))),1)
        return station,ui

    def test_sensor_on_disconnected_during_poff(self):
        station,_=self.start_once(NoClose())
        self.assertEqual(station.report['result'],'fallido')
        self.assertIn('error motor 4',station.report['issue'])
        self.assertEqual(station.steps[2].state,'fallido')
        self.assertEqual(station.latest.number('MOV'),0)
        self.assertEqual(station.steps[6].state,'pendiente')

    def test_sensor_off_missing_at_initial_check(self):
        fx=Fixture()
        fx.values.update({'ON':'0','OFF':'0'})
        station,_=self.start_once(fx)
        self.assertEqual(station.report['result'],'fallido')
        self.assertIn('Sensores de motor inconsistentes',station.report['issue'])
        self.assertEqual(station.steps[1].state,'fallido')
        self.assertEqual(station.steps[2].state,'pendiente')

    def test_motor_power_removed_reports_motor_fault_not_power_cause(self):
        station,_=self.start_once(NoClose())
        # Sin instrumentación de alimentación, no atribuir el error a un componente.
        self.assertEqual(station.steps[2].state,'fallido')
        self.assertNotIn('alimentación',station.report['issue'])

    def test_overcurrent_notifies_without_solely_failing(self):
        station,ui=self.start_once(WarningCurrent())
        self.assertEqual(station.report['result'],'aprobado',station.report)
        self.assertEqual(len(station.report['warnings']),1)
        self.assertTrue(any(v[0]=='warning' for v in ui))

    def test_repeated_command_does_not_pass_without_new_status(self):
        fx=Fixture()
        station=TestStation(FakeSerial(fx),FakeBLE(fx),lambda *a:None)
        fx.station=station
        station.repeat_verify_s=.05
        station.on_line('AT$POST=1,0,"S29|..."') # No se convierte en S29 válido
        # Una línea vieja previa al comando no debe aprobar una repetición.
        with station.cond: station.observations.append(('status', None))
        # Sustituir STATUS por un canal mudo; no habrá estado nuevo.
        class Silent(FakeSerial):
            def send(self,raw): pass
        station.serial=Silent(fx)
        with self.assertRaises(NoVerification):
            station._await_repetition(station._checkpoint(), 'abierto', 0, 1,time.monotonic(),timeout=.18)

if __name__=='__main__':unittest.main()
