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
    def start_once(self, fx, recuperacion_s=None, motor_reintento_s=None):
        ui=[]
        station=TestStation(FakeSerial(fx), FakeBLE(fx),lambda *a:ui.append(a))
        station.repeat_verify_s=.08
        if recuperacion_s: station.recuperacion_s=recuperacion_s
        if motor_reintento_s: station.motor_reintento_s=motor_reintento_s
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
        """v1.4.84: ON=0 OFF=0 (perno a medio camino) que NO se destraba con PPON/POFF sigue fallando en la etapa 2."""
        class Atorado(Fixture):
            def move(self,cmd,origin): self.emit()   # ignora PPON/POFF: el perno no se mueve
        fx=Atorado()
        fx.values.update({'ON':'0','OFF':'0'})
        station,_=self.start_once(fx,recuperacion_s=.3)
        self.assertEqual(station.report['result'],'fallido')
        self.assertIn('Sensores de motor inconsistentes',station.report['issue'])
        self.assertEqual(station.steps[1].state,'fallido')
        self.assertEqual(station.steps[2].state,'pendiente')

    def test_perno_a_medio_camino_se_recupera_solo_y_queda_en_el_log(self):
        """v1.4.84: ON=0 OFF=0 al iniciar: PPON lo asienta y el ciclo sigue; el log y la etapa 2 lo dicen."""
        fx=Fixture()
        fx.values.update({'ON':'0','OFF':'0'})
        station,ui=self.start_once(fx)
        self.assertEqual(station.steps[1].state,'aprobado',station.report)
        self.assertIn('recuperado automáticamente con PPON',station.steps[1].detail)
        self.assertTrue(any(a[0]=='log' and 'RECUPERACIÓN AUTOMÁTICA: enviando PPON' in a[1] for a in ui))

    def test_perno_no_asienta_se_repite_el_comando_y_cuenta_con_advertencia(self):
        """v1.4.85: PPON deja ON=0 OFF=0; a los N s se repite el MISMO comando una vez y, si asienta, el ciclo sigue con aviso."""
        class Perezoso(Fixture):
            primera=True
            def move(self,cmd,origin):
                if Perezoso.primera and origin==1:
                    Perezoso.primera=False
                    self.values['PB']=str(origin); self.values['ON']='0'; self.values['OFF']='0'
                    self.values['MOV']=str(int(self.values['MOV'])+1); self.emit(); return
                super().move(cmd,origin)
        fx=Perezoso(); fx.values.update({'ON':'1','OFF':'0'})
        station,ui=self.start_once(fx,motor_reintento_s=.6)
        self.assertEqual(station.steps[2].state,'aprobado',station.report)
        self.assertIn('reintento automático',station.steps[2].detail)
        self.assertEqual(station.report['motor_reintentos'],1)
        self.assertEqual(station.report['result'],'no_verificado')   # estricto en Pruebas TQT; la campaña lo cuenta como advertencia
        self.assertTrue(any('no asentó el perno' in w for w in station.report['warnings']))
        self.assertTrue(any(a[0]=='log' and 'REINTENTO AUTOMÁTICO' in a[1] for a in ui))

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
