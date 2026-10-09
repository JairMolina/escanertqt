import _aislamiento as iso
import asyncio
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from app.database import db
from app.services import stm32_programming as s
from app.services import tqt_hex as hx
from app.main import app
from app.routers import validacion as v

sys.modules['tqt_hex'] = hx
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'station'))
import agent


class BleAgenteServidorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init_db()

    def setUp(self):
        self.c = TestClient(app, base_url='https://testserver')
        self.st = s.station_create('ble-test', 'qa')
        self.h = {'Authorization': 'Bearer ' + self.st['token']}
        self.sid = self.st['id']
        self.t = iso.crear_par(iso.nuevo_lote()['id'], version='30')

    def claim(self, **kw):
        body = dict(ble_disponible=True, conectado=False)
        body.update(kw)
        r = self.c.post('/api/stm32/agent/ble/claim', json=body, headers=self.h)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def trabajo(self, **kw):
        d = dict(station_id=self.sid, accion='escanear')
        d.update(kw)
        return self.c.post('/api/validacion/ble/trabajos', json=d)

    def resultado(self, jid, ok=True, **kw):
        return self.c.post(f'/api/stm32/agent/ble/{jid}/resultado', json=dict(ok=ok, **kw), headers=self.h)

    def test_estacion_desconectada_400(self):
        r = self.trabajo()
        self.assertEqual(r.status_code, 400, r.text)
        self.assertEqual(self.trabajo(station_id='0' * 24).status_code, 400)

    def test_enviar_sin_comando(self):
        self.claim()
        self.assertIn(self.trabajo(accion='enviar').status_code, (400, 422))

    def test_agente_requiere_bearer(self):
        r = self.c.post('/api/stm32/agent/ble/claim', json={'ble_disponible': True, 'conectado': False})
        self.assertEqual(r.status_code, 401)

    def test_flujo_completo(self):
        self.assertIsNone(self.claim())
        est = self.c.get('/api/validacion/ble/estado', params={'station_id': self.sid}).json()
        self.assertTrue(est['ble_disponible']); self.assertFalse(est['conectado']); self.assertLess(est['visto'], 5)
        self.assertTrue(s.stations()[-1]['online'] or any(x['id'] == self.sid and x['online'] for x in s.stations()))

        # Escanear
        j = self.trabajo(accion='escanear').json()
        self.assertEqual(j['estado'], 'pendiente')
        w = self.claim()
        self.assertEqual((w['id'], w['accion']), (j['id'], 'escanear'))
        self.assertEqual(self.c.get(f"/api/validacion/ble/trabajos/{j['id']}").json()['estado'], 'en_curso')
        self.assertIsNone(self.claim())
        self.resultado(j['id'], resultado={'dispositivos': [{'nombre': 'TQT-1', 'address': 'AA', 'rssi': -50}]})
        g = self.c.get(f"/api/validacion/ble/trabajos/{j['id']}").json()
        self.assertEqual(g['estado'], 'ok'); self.assertEqual(g['resultado']['dispositivos'][0]['address'], 'AA')

        # Conectar -> registro CONECTAR y estado conectado
        nombre = self.t['r2']['nombre']
        j = self.trabajo(accion='conectar', address='AA:BB', codigo=nombre).json()
        w = self.claim(); self.assertEqual(w['address'], 'AA:BB')
        self.resultado(j['id'], resultado={'conectado': True, 'nombre': 'TQT-9', 'address': 'AA:BB'})
        est = self.c.get('/api/validacion/ble/estado', params={'station_id': self.sid}).json()
        self.assertTrue(est['conectado']); self.assertEqual(est['nombre'], 'TQT-9')
        regs = self.c.get('/api/validacion/registros', params={'q': 'TQT-9'}).json()['items']
        self.assertEqual(regs[0]['comando'], 'CONECTAR'); self.assertEqual(regs[0]['resultado'], 'ok')
        self.assertEqual(regs[0]['ble_id'], 'AA:BB'); self.assertEqual(regs[0]['pcb']['id'], self.t['r2']['id'])

        # Enviar PPON -> registro PPON con respuesta
        j = self.trabajo(accion='enviar', comando='PPON', codigo=nombre).json()
        w = self.claim(conectado=True, nombre='TQT-9', address='AA:BB'); self.assertEqual(w['comando'], 'PPON')
        self.resultado(j['id'], resultado={'comando': 'PPON', 'respuesta': 'OK'})
        regs = self.c.get('/api/validacion/registros', params={'q': 'PPON'}).json()['items']
        self.assertEqual((regs[0]['comando'], regs[0]['respuesta'], regs[0]['dispositivo']), ('PPON', 'OK', 'TQT-9'))

        # Notificación -> NOTIFICACION y evento visible
        r = self.c.post('/api/stm32/agent/ble/evento', json={'tipo': 'notificacion', 'texto': 'hola'}, headers=self.h)
        self.assertEqual(r.status_code, 200, r.text)
        regs = self.c.get('/api/validacion/registros', params={'q': 'NOTIFICACION'}).json()['items']
        self.assertEqual(regs[0]['respuesta'], 'hola')
        est = self.c.get('/api/validacion/ble/estado', params={'station_id': self.sid}).json()
        self.assertEqual(est['eventos'][-1]['tipo'], 'notificacion')

        # Desconexión inesperada
        self.c.post('/api/stm32/agent/ble/evento', json={'tipo': 'desconexion', 'texto': 'perdida'}, headers=self.h)
        est = self.c.get('/api/validacion/ble/estado', params={'station_id': self.sid}).json()
        self.assertFalse(est['conectado'])
        regs = self.c.get('/api/validacion/registros', params={'q': 'DESCONECTAR'}).json()['items']
        self.assertEqual(regs[0]['detalle'], 'perdida')

    def test_error_de_comando_registra_error(self):
        self.claim()
        j = self.trabajo(accion='enviar', comando='POFF').json()
        self.claim(); self.resultado(j['id'], ok=False, error='sin conexión')
        g = self.c.get(f"/api/validacion/ble/trabajos/{j['id']}").json()
        self.assertEqual((g['estado'], g['error']), ('error', 'sin conexión'))
        regs = self.c.get('/api/validacion/registros', params={'q': 'POFF'}).json()['items']
        self.assertEqual((regs[0]['comando'], regs[0]['resultado']), ('POFF', 'error'))

    def test_trabajo_caduca(self):
        self.claim()
        j = self.trabajo().json()
        v._jobs[j['id']]['creado'] -= 61
        self.assertEqual(self.c.get(f"/api/validacion/ble/trabajos/{j['id']}").json()['estado'], 'error')
        self.assertIsNone(self.claim())


class FakeClient:
    def __init__(self, address, disconnected_callback=None):
        self.address, self.cb, self.is_connected, self.writes = address, disconnected_callback, False, []
        char = MagicMock(uuid=agent.BLE_CHAR, properties=['read', 'write', 'notify'])
        svc = MagicMock(uuid=agent.BLE_SERVICE, characteristics=[char])
        self.services = MagicMock()
        self.services.__iter__.return_value = iter([svc])
        self.services.get_characteristic.return_value = char

    async def connect(self):
        self.is_connected = True

    async def start_notify(self, char, cb):
        self.notify = cb

    async def write_gatt_char(self, char, data, response=None):
        self.writes.append((data, response))

    async def disconnect(self):
        self.is_connected = False


class BleAgenteTests(unittest.TestCase):
    def lib(self):
        lib = MagicMock()
        lib.BleakClient = FakeClient
        dev = MagicMock(); dev.name = 'TQT-7'
        adv = MagicMock(rssi=-40)
        otro = MagicMock(); otro.name = 'Otro'
        lib.BleakScanner.discover = lambda **k: _coro({'A': (dev, adv), 'B': (otro, MagicMock(rssi=-10))})
        lib.BleakScanner.find_device_by_address = lambda *a, **k: _coro(dev)
        return lib

    def test_importa_sin_bleak(self):
        w = agent.BleWorker(lambda *a: None, lib=None)
        w.lib = None
        self.assertFalse(w.disponible)
        with self.assertRaises(ValueError) as cm:
            asyncio.run(w.ejecutar({'accion': 'escanear'}))
        self.assertIn('pip install', str(cm.exception))

    def test_trabajos_con_bleak_simulado(self):
        w = agent.BleWorker(lambda *a: None, lib=self.lib())
        r = asyncio.run(w.ejecutar({'accion': 'escanear'}))
        self.assertEqual([d['nombre'] for d in r['dispositivos']], ['TQT-7'])

        async def flujo():
            c = await w.ejecutar({'accion': 'conectar', 'address': 'A'})
            e = await w.ejecutar({'accion': 'enviar', 'comando': 'PPON'})
            with self.assertRaises(ValueError):
                await w.ejecutar({'accion': 'enviar', 'comando': 'XXXX'})
            cli = w.client
            d = await w.ejecutar({'accion': 'desconectar'})
            return c, e, d, cli
        c, e, d, cli = asyncio.run(flujo())
        self.assertEqual(c, {'conectado': True, 'nombre': 'TQT-7', 'address': 'A'})
        self.assertEqual(e['comando'], 'PPON')
        self.assertEqual(cli.writes, [(b'PPON', True)])
        self.assertEqual(d, {'conectado': False})


async def _coro(v):
    return v


if __name__ == '__main__':
    unittest.main()
