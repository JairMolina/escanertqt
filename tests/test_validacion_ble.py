import _aislamiento as iso
import io
import unittest
import zipfile
from fastapi.testclient import TestClient
from app.database import db
from app.main import app


class ValidacionBLETests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init_db()

    def setUp(self):
        self.t = iso.crear_par(iso.nuevo_lote()['id'], version='30')
        self.c = TestClient(app, base_url='https://testserver')

    def body(self, **kw):
        d = dict(dispositivo='TQT-X', comando='PPON', resultado='ok')
        d.update(kw)
        return d

    def test_alta_con_codigo(self):
        r = self.c.post('/api/validacion/registros', json=self.body(codigo=self.t['r2']['nombre'], dispositivo='TQT-ZZZ', detalle='x', respuesta='OK'))
        self.assertEqual(r.status_code, 200, r.text)
        j = r.json()
        self.assertEqual(j['pcb']['id'], self.t['r2']['id'])
        self.assertEqual(j['pcb']['tipo'], 'R2')
        self.assertEqual(j['tarjeta']['id'], self.t['id'])
        self.assertTrue(j['operador'])
        self.assertTrue(j['creado_en'])

    def test_tarjeta_validada(self):
        """v1.3.59: la tarjeta queda «validada» con PPON y POFF ok (un error no cuenta)."""
        nombre = self.t['r2']['nombre']
        estado = lambda: db.get_tarjeta_by_id(self.t['id'])
        self.assertFalse(estado()['validada'])
        self.c.post('/api/validacion/registros', json=self.body(codigo=nombre, comando='PPON'))
        self.c.post('/api/validacion/registros', json=self.body(codigo=nombre, comando='POFF', resultado='error'))
        self.assertEqual((estado()['validada'], estado()['validacion']), (False, ['PPON']))
        self.c.post('/api/validacion/registros', json=self.body(codigo=nombre, comando='POFF'))
        self.assertTrue(estado()['validada'])

    def test_alta_por_nombre_de_dispositivo(self):
        nombre = self.t['r1']['nombre'].replace('-', '_')
        j = self.c.post('/api/validacion/registros', json=self.body(dispositivo=nombre, comando='CONECTAR')).json()
        self.assertEqual(j['pcb']['id'], self.t['r1']['id'])
        self.assertEqual(j['tarjeta']['id_tarjeta_num'], self.t['id_tarjeta_num'])

    def test_sin_resolver(self):
        j = self.c.post('/api/validacion/registros', json=self.body(dispositivo='TQT-DESCONOCIDO')).json()
        self.assertIsNone(j['pcb'])
        self.assertIsNone(j['tarjeta'])

    def test_comando_invalido(self):
        self.assertEqual(self.c.post('/api/validacion/registros', json=self.body(comando='BORRAR')).status_code, 422)
        self.assertEqual(self.c.post('/api/validacion/registros', json=self.body(resultado='quizas')).status_code, 422)

    def test_listado_filtro_y_resumen(self):
        n = self.t['r2']['nombre']
        self.c.post('/api/validacion/registros', json=self.body(dispositivo=n, comando='PPON'))
        self.c.post('/api/validacion/registros', json=self.body(dispositivo=n, comando='POFF', resultado='error'))
        r = self.c.get('/api/validacion/registros', params={'tarjeta_id': self.t['id']}).json()
        self.assertEqual(r['total'], 2)
        self.assertEqual([x['comando'] for x in r['items']], ['POFF', 'PPON'])
        self.assertEqual(self.c.get('/api/validacion/registros', params={'pcb_id': self.t['r2']['id'], 'q': 'poff'}).json()['total'], 1)
        self.assertEqual(self.c.get('/api/validacion/registros', params={'limit': 501}).status_code, 422)
        s = self.c.get('/api/validacion/resumen').json()
        self.assertGreaterEqual(s['hoy'], 2)
        self.assertGreaterEqual(s['ok_hoy'], 1)
        self.assertGreaterEqual(s['error_hoy'], 1)
        self.assertGreaterEqual(s['dispositivos_hoy'], 1)
        self.assertEqual(s['ultima']['comando'], 'POFF')

    def test_zip(self):
        r = self.c.get('/api/validacion/tester.zip')
        self.assertEqual(r.status_code, 200)
        self.assertIn('TQT_BLE_Tester_Windows_v1.1.zip', r.headers['content-disposition'])
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            self.assertIn('TQT_BLE_Tester.py', z.namelist())

    def test_sin_sesion(self):
        c = iso.cliente_sin_sesion(app)
        self.assertEqual(c.get('/api/validacion/resumen').status_code, 401)


if __name__ == '__main__':
    unittest.main()
