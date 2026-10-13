"""V0.6: reporte, cotejo opcional y calidad de comunicación."""
import csv
import json
import tempfile
import unittest
from pathlib import Path
from tqtstation.reporting import (load_inventory, compare_inventory, communicate,
                                  build_warnings, report_html, append_history)
from tqtstation.engine import TestStation
from test_engine_fake import Fixture, FakeBLE, FakeSerial


class ReportTests(unittest.TestCase):
    def test_real_health_nonblocking_warning(self):
        health={'frames':104,'corrupt_frames':30,'retries':0,'partial_warnings':0}
        q=communicate(health)
        self.assertEqual(q['state'],'advertencias')
        self.assertEqual(q['corrupt_percent'],28.8)
        self.assertIn('30 líneas',build_warnings(health,[])[0])

    def test_communication_transport_breakdown_changes_quality(self):
        self.assertEqual(communicate({'frames':10, 'retries':1})['state'],'no_verificable')
        self.assertEqual(communicate({'frames':10, 'ack_errors':1})['state'],'no_verificable')
        self.assertEqual(communicate({'frames':10})['state'],'limpia')

    def test_inventory_missing_is_not_match(self):
        result=compare_inventory(None,'0036','AA:BB:CC:DD:EE:FF','AA:BB:CC:DD:EE:FF','','')
        self.assertEqual(result['state'],'no_configurado')
        self.assertEqual(result['r1'],'no_verificado')

    def test_inventory_loaded_matched_both(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'stock.csv'
            path.write_text('ID,MAC_R1,MAC_R2,Nombre\n0036,AA:BB:CC:DD:EE:FF,11:22:33:44:55:66,R1-0036\n',encoding='utf-8')
            data=load_inventory(path)
            result=compare_inventory(data,'36','AA:BB:CC:DD:EE:FF','AA:BB:CC:DD:EE:FF',
                                     '11:22:33:44:55:66','11:22:33:44:55:66')
            self.assertEqual(result['state'],'coincide')
            self.assertEqual(result['record']['nombre'],'R1-0036')

    def test_inventory_wrong_r2_not_pass(self):
        data={'36':{'mac_r1':'AA:BB:CC:DD:EE:FF','mac_r2':'22:22:22:22:22:22','nombre':''}}
        res=compare_inventory(data,'0036','AA:BB:CC:DD:EE:FF','AA:BB:CC:DD:EE:FF',
                              '11:22:33:44:55:66','11:22:33:44:55:66')
        self.assertEqual(res['state'],'no_coincide')
        self.assertEqual(res['r1'],'coincide')
        self.assertEqual(res['r2'],'no_coincide')

    def test_semicolon_csv_and_duplicate_check(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'stock.csv'
            path.write_text('Número de tarjeta;MAC R1;MAC R2\n36;AA:BB:CC:DD:EE:FF;11:22:33:44:55:66\n',encoding='utf-8')
            self.assertEqual(load_inventory(path)['36']['mac_r1'],'AA:BB:CC:DD:EE:FF')
            path.write_text(path.read_text()+'0036;AA:BB:CC:DD:EE:FF;11:22:33:44:55:66\n',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'duplicado'): load_inventory(path)

    def test_report_html_escape_and_archive(self):
        report={'card':'<script>alert(1)</script>','date':'2026-10-13','result':'aprobado',
                'serial_port':'COM9', 'steps':[{'name':'Prueba', 'state':'aprobado','detail':'MOV 0→1','duration_s':5}],
                'warnings':['Cabecera dañada <xml>'], 'communication_quality':{'state':'advertencias'},
                'inventory_check':{'state':'no_configurado'},'serial_health':{'frames':104,'corrupt_frames':30}}
        generated=report_html(report)
        self.assertNotIn('<script>',generated)
        self.assertIn('&lt;script&gt;',generated)
        self.assertIn('MOV 0→1',generated)
        with tempfile.TemporaryDirectory() as d:
            append_history(Path(d),report,'x.json','x.html')
            append_history(Path(d),report,'y.json','y.html')
            with (Path(d)/'historial_pruebas.csv').open(encoding='utf-8-sig') as f:
                rows=list(csv.DictReader(f))
            self.assertEqual(len(rows),2)
            self.assertEqual(rows[0]['rx_corruptas'],'30')

    def test_functional_pass_warnings_keeps_approved(self):
        fx=Fixture();ui=[]
        class CorruptSerial(FakeSerial):
            @property
            def health(self):
                return {'frames':104,'corrupt_frames':30, 'retries':0,'partial_warnings':0}
        station=TestStation(CorruptSerial(fx),FakeBLE(fx),lambda *args:ui.append(args))
        fx.station=station;station.repeat_verify_s=.02
        with tempfile.TemporaryDirectory() as d:
            station.output_dir=Path(d);station.start('COM_FAKE')
            station._run_thread.join(15)
            self.assertEqual(station.report['result'],'aprobado',station.report)
            self.assertEqual(station.report['communication_quality']['state'],'advertencias')
            self.assertEqual(station.report['inventory_check']['state'],'no_configurado')
            self.assertTrue(station.report['warnings'])
            self.assertEqual(len(list(Path(d).glob('*.html'))),1)
            self.assertEqual(len(list(Path(d).glob('*.json'))),1)
            self.assertEqual(len(list(Path(d).glob('*.log'))),1)
            self.assertEqual(len(list(Path(d).glob('*.csv'))),1)
            self.assertTrue(all(s['duration_s'] is not None for s in station.report['steps']))
            self.assertTrue(any(x[0]=='report' for x in ui))

    def test_inventory_mismatch_prevents_green_release(self):
        fx=Fixture();station=TestStation(FakeSerial(fx),FakeBLE(fx),lambda *args: None)
        station.inventory_records={'11':{'mac_r1':'AA:BB:CC:DD:EE:FF','mac_r2':'00:00:00:00:00:01',
                                         'nombre':'','observaciones':'','id':'0011'}}
        fx.station=station;station.repeat_verify_s=.02
        with tempfile.TemporaryDirectory() as d:
            station.output_dir=Path(d);station.start('COM_FAKE')
            station._run_thread.join(15)
            self.assertEqual(station.report['result'],'no_verificado',station.report)
            self.assertEqual(station.report['inventory_check']['state'],'no_coincide')
            self.assertIn('Discrepancia',station.report['issue'])

if __name__=='__main__':unittest.main()
