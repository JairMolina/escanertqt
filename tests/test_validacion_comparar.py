import _aislamiento as iso
import time
import unittest
from fastapi.testclient import TestClient
from app.database import db
from app.main import app
from app.routers import validacion as val
from app.services import stm32_programming as svc


class CompararTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init_db()
        val.init()

    def setUp(self):
        self.t = iso.crear_par(iso.nuevo_lote()['id'], version='30')
        self.c = TestClient(app, base_url='https://testserver')
        st = svc.station_create('LAPTOP-' + str(self.t['id']), 'test')
        self.sid = st['id'] if isinstance(st, dict) and 'id' in st else st['station']['id']
        with db.get_db() as c:
            c.execute('UPDATE stm32_stations SET last_seen=? WHERE id=?', (time.time(), self.sid))
        self.r2 = self.t['r2']
        num = self.r2['nombre'][-4:]
        self.nombre_ble = 'TQT_R2_V30_' + num

    def conectar(self, nombre=None, address=None, fw=None):
        val._estados[self.sid] = dict(ble_disponible=True, conectado=True, nombre=nombre or self.nombre_ble,
                                      address=address or self.r2['mac'], firmware=fw, visto=time.time(), eventos=[])

    def cmp(self):
        return self.c.get('/api/validacion/comparar', params=dict(codigo=self.r2['nombre'], station_id=self.sid))

    def probar(self, *cmds):
        for cmd in cmds:
            self.c.post('/api/validacion/registros', json=dict(codigo=self.r2['nombre'], dispositivo=self.nombre_ble,
                                                                ble_id=self.r2['mac'], comando=cmd, resultado='ok'))

    def checks(self, j):
        return {k['campo']: k for k in j['checks']}

    def test_codigo_inexistente_404(self):
        r = self.c.get('/api/validacion/comparar', params=dict(codigo='TQT-R2-V30-9999-X', station_id=self.sid))
        self.assertEqual(r.status_code, 404)

    def test_sin_ble_conectado(self):
        val._estados.pop(self.sid, None)
        j = self.cmp().json()
        self.assertFalse(j['ok'])
        self.assertIsNone(j['placa_probada'])
        self.assertIs(self.checks(j)['tarjeta']['ok'], False)

    def test_dispositivo_ajeno(self):
        self.conectar(nombre='OTRO', address='AA:BB:CC:DD:EE:01')
        j = self.cmp().json()
        self.assertIsNone(j['placa_probada'])
        self.assertFalse(j['ok'])

    def test_ok_completo_y_validar_auto(self):
        self.conectar()
        self.probar('PPON', 'POFF')
        j = self.cmp().json()
        self.assertEqual(j['placa_probada'], 'R2', j)
        self.assertTrue(j['ok'], j['checks'])
        self.assertIsNone(j['validada'])
        r = self.c.post('/api/validacion/validar', json=dict(codigo=self.r2['nombre'], station_id=self.sid, modo='auto'))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()['validada']['modo'], 'auto')
        self.assertFalse(db.get_tarjeta_by_id(self.t['id'])['validada'])   # v1.3.65: falta confirmar la tarjeta
        items = self.c.get('/api/validacion/placas-validadas').json()['items']
        self.assertEqual((items[0]['tarjeta_id'], items[0]['modo'], items[0]['tarjeta_validada']), (self.t['id'], 'auto', False))
        self.assertTrue(items[0]['probo'])
        r = self.c.post('/api/validacion/tarjetas/validar', json=dict(tarjeta_ids=[self.t['id']]))
        self.assertEqual(r.json()['validadas'], [self.t['id']])
        self.assertEqual(self.c.post('/api/validacion/tarjetas/validar', json=dict(tarjeta_ids=[self.t['id']])).json()['validadas'], [])
        t = db.get_tarjeta_by_id(self.t['id'])
        self.assertEqual((t['validada'], t['validada_modo']), (True, 'auto'))
        self.assertTrue(self.c.get('/api/validacion/placas-validadas').json()['items'][0]['tarjeta_validada'])

    def test_auto_rechaza_sin_pruebas(self):
        self.conectar()
        r = self.c.post('/api/validacion/validar', json=dict(codigo=self.r2['nombre'], station_id=self.sid, modo='auto'))
        self.assertEqual(r.status_code, 409)
        self.assertIs([k for k in r.json()['checks'] if k['campo'] == 'pruebas'][0]['ok'], False)
        self.assertFalse(db.get_tarjeta_by_id(self.t['id'])['validada'])

    def test_mac_distinta_y_manual(self):
        self.conectar(address='AA:BB:CC:00:00:99')  # el nombre BLE coincide, la MAC no
        j = self.cmp().json()
        self.assertEqual(j['placa_probada'], 'R2')
        self.assertIs(self.checks(j)['mac']['ok'], False)
        r = self.c.post('/api/validacion/validar', json=dict(codigo=self.r2['nombre'], station_id=self.sid, modo='manual', motivo='MAC cambiada'))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()['validada']['modo'], 'manual')
        self.c.post('/api/validacion/tarjetas/validar', json=dict(tarjeta_ids=[self.t['id']]))
        t = db.get_tarjeta_by_id(self.t['id'])
        self.assertEqual((t['validada'], t['validada_modo']), (True, 'manual'))
        with db.get_db() as c:
            d = c.execute("SELECT detalle FROM validaciones_ble WHERE comando='VALIDACION_MANUAL' AND tarjeta_id=?", (self.t['id'],)).fetchone()[0]
        self.assertIn('MAC cambiada', d)

    def test_firmware_derivado_del_nombre(self):
        self.conectar()
        with db.get_db() as c:
            c.execute('UPDATE pcb_inventario SET firmware=? WHERE id=?', ('2.1', self.r2['id']))
        self.assertIs(self.checks(self.cmp().json())['firmware']['ok'], False)
        with db.get_db() as c:
            c.execute('UPDATE pcb_inventario SET firmware=? WHERE id=?', ('3.0.2', self.r2['id']))
        self.assertIs(self.checks(self.cmp().json())['firmware']['ok'], True)
        self.conectar(nombre=self.nombre_ble, fw='3.0')
        self.assertIs(self.checks(self.cmp().json())['firmware']['ok'], True)

    def test_estaciones_por_ip(self):
        j = self.c.get('/api/validacion/estaciones').json()
        self.assertIn(self.sid, [e['id'] for e in j['estaciones']])
        self.assertFalse(j['coincide'])
        val._ips[self.sid] = '10.9.8.7'
        j = self.c.get('/api/validacion/estaciones', headers={'X-Forwarded-For': '10.9.8.7, 1.1.1.1'}).json()
        self.assertTrue(j['coincide'])
        self.assertEqual([e['id'] for e in j['estaciones']], [self.sid])
        self.assertTrue(j['estaciones'][0]['esta_laptop'])
        j = self.c.get('/api/validacion/estaciones', headers={'CF-Connecting-IP': '9.9.9.9', 'X-Forwarded-For': '10.9.8.7'}).json()
        self.assertFalse(j['coincide'])

    def test_pruebas_ppon_poff_ya_no_validan_solas(self):
        self.probar('PPON', 'POFF')
        t = db.get_tarjeta_by_id(self.t['id'])
        self.assertEqual((t['validada'], t['validacion']), (False, ['POFF', 'PPON']))
        with db.get_db() as c:   # registros anteriores al corte siguen contando
            c.execute("UPDATE validaciones_ble SET creado_en='2026-10-09 17:00:00'")
        t = db.get_tarjeta_by_id(self.t['id'])
        self.assertEqual((t['validada'], t['validada_modo']), (True, 'pruebas'))


    def test_misma_red_ipv6(self):
        self.assertTrue(val._misma_red('2806:2f0:1:2:aaaa::1', '2806:2f0:1:2:bbbb::9'))
        self.assertFalse(val._misma_red('2806:2f0:1:3::1', '2806:2f0:1:2::1'))
        self.assertFalse(val._misma_red('1.2.3.4', None))


if __name__ == '__main__':
    unittest.main()
