"""Adapter derived from the uploaded TQT BLE Tester v1.1: same UUIDs and GATT semantics."""
from __future__ import annotations
import asyncio
import threading
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass
from typing import Any

SERVICE_UUID = '4fafc201-1fb5-459e-8fcc-c5c9c331914b'
CHAR_UUID = 'beb5483e-36e1-4688-b7f5-ea07361b26a8'

@dataclass(frozen=True)
class FoundDevice:
    name: str
    address: str


def ordenar_escaneo(found, limite=60):
    """TQT primero; luego por señal (RSSI mayor) y nombre."""
    return sorted(found, key=lambda d: ('TQT' not in d['name'].upper(),
                                       -(d['rssi'] if d['rssi'] is not None else -999),
                                       d['name'].upper(), d['address']))[:limite]


class BLELink:
    def __init__(self, log):
        self.log = log
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._start, name='TQT BLE loop', daemon=True)
        self.thread.start()
        self.devices: dict[str, Any] = {}
        self.client = None
        self.char = None
        self.address = ''
        self._requested_disconnect = False
        self._intentional_disconnect_ids = set()

    def _start(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def _call(self, coroutine, timeout=25):
        future = asyncio.run_coroutine_threadsafe(coroutine, self.loop)
        try: return future.result(timeout=timeout)
        except FutureTimeout:
            future.cancel()
            raise TimeoutError('Tiempo agotado en Bluetooth')

    async def _scan(self, target=None):
        from bleak import BleakScanner
        result = await BleakScanner.discover(timeout=7.0, return_adv=True)
        found = []
        self.devices = {}
        for d, adv in result.values():
            name = (adv.local_name or d.name or '').strip()
            if 'TQT' in name.upper() or (target and d.address.upper() == target.upper()):
                addr = d.address.upper()
                self.devices[addr] = d
                found.append(FoundDevice(name, addr))
        return sorted(found, key=lambda d:(d.name.upper(), d.address))

    async def _scan_all(self):
        from bleak import BleakScanner
        result = await BleakScanner.discover(timeout=7.0, return_adv=True)
        found = []
        self.devices = {}
        for d, adv in result.values():
            name = (adv.local_name or d.name or '').strip()
            if not name:
                continue
            addr = d.address.upper()
            self.devices[addr] = d
            rssi = getattr(adv, 'rssi', None)
            found.append({'name': name, 'address': addr, 'rssi': rssi if isinstance(rssi, int) else None})
        return ordenar_escaneo(found)

    def scan_all(self):
        """v1.4.64: «Elegir dispositivo» del navegador: todo lo que tiene nombre, TQT primero."""
        self.log('Buscando todos los BLE durante 7 segundos…')
        result = self._call(self._scan_all(), timeout=15)
        self.log(f'BLE: {len(result)} dispositivo(s) con nombre encontrados')
        return result

    def scan(self, target=None):
        self.log('Buscando BLE durante 7 segundos…')
        result = self._call(self._scan(target), timeout=15)
        self.log(f'BLE: {len(result)} dispositivo(s) TQT encontrados')
        return result

    def _disconnected(self, client):
        intentional = self._requested_disconnect or id(client) in self._intentional_disconnect_ids
        self._intentional_disconnect_ids.discard(id(client))
        if not intentional:
            if client is self.client:
                self.client, self.char, self.address = None, None, ''
            self.log('AVISO BLE: enlace perdido sin solicitud de desconexión')

    async def _connect(self, address):
        from bleak import BleakClient
        device = self.devices.get(address)
        if not device: raise RuntimeError('BLE no encontrado en el último escaneo')
        if self.client and self.client.is_connected:
            self._requested_disconnect = True
            self._intentional_disconnect_ids.add(id(self.client))
            try: await self.client.disconnect()
            finally: self._requested_disconnect = False
        self.char = None
        self.address = ''
        client = BleakClient(device, disconnected_callback=self._disconnected, timeout=15)
        try:
            await client.connect()
            service = client.services.get_service(SERVICE_UUID)
            if service is None: raise RuntimeError('Servicio TQT del BLE Tester no encontrado')
            characteristic = next((c for c in service.characteristics if c.uuid.lower() == CHAR_UUID), None)
            if characteristic is None: raise RuntimeError('Característica TQT no encontrada')
            props = {p.lower() for p in characteristic.properties}
            if not ({'write','write-without-response'} & props): raise RuntimeError('Característica BLE no escribible')
            if 'notify' in props or 'indicate' in props:
                try: await client.start_notify(characteristic, lambda _, data: self.log('RX BLE: '+bytes(data).decode('utf-8', 'replace').strip()))
                except Exception as exc: self.log('BLE sin notificaciones: ' + str(exc))
            self.client, self.char, self.address = client, characteristic, address
            self.log(f'BLE conectado: {address}')
        except Exception:
            if client.is_connected:
                self._intentional_disconnect_ids.add(id(client))
                await client.disconnect()
            raise

    def connect(self, address): self._call(self._connect(address.upper()), timeout=24)

    async def _send(self, command):
        if command not in ('POFF','PPON'): raise ValueError('Comando BLE no autorizado')
        if not self.client or not self.client.is_connected or not self.char:
            raise RuntimeError('No existe una conexión BLE activa')
        props = {p.lower() for p in self.char.properties}
        ack = 'write' in props
        await self.client.write_gatt_char(self.char, command.encode('ascii'), response=ack)
        self.log(f'TX BLE: {command} (GATT {"con respuesta" if ack else "sin respuesta"}; no certifica movimiento)')

    def send(self, command): self._call(self._send(command), timeout=15)

    async def _disconnect(self):
        client = self.client
        self.client, self.char, self.address = None, None, ''
        if client and client.is_connected:
            self._requested_disconnect = True
            self._intentional_disconnect_ids.add(id(client))
            try: await client.disconnect()
            finally: self._requested_disconnect = False
        self.log('BLE desconectado')

    def disconnect(self): self._call(self._disconnect(), timeout=15)
