"""Small native BLE-only adapter. It neither imports nor opens a serial port."""
import time
from .protocol import normalize_mac


def execute(ble, authorize):
    payload = authorize()  # online, one-use authorization immediately before native I/O
    op, address = payload['operation'], payload['address']
    if time.time() > payload['deadline']:
        raise ValueError('Comando vencido; no se ejecuta.')
    if op == 'disconnect':
        ble.disconnect()
        return {'disconnected': True}
    if op in ('scan', 'connect'):
        found = ble.scan(target=address)
        matches = [d for d in found if normalize_mac(d.address) == normalize_mac(address)]
        if len(matches) != 1:
            raise ValueError('No se localizó una única tarjeta con MAC ' + address)
        device = matches[0]
        if op == 'connect':
            ble.connect(device.address)
        return {'address': device.address, 'name': device.name, 'connected': op == 'connect'}
    if op != 'send' or payload['command'] not in ('PPON', 'POFF'):
        raise ValueError('Operación BLE no permitida.')
    if normalize_mac(ble.address) != normalize_mac(address):
        raise ValueError('Bluetooth conectado a otra MAC; no se mueve.')
    ble.send(payload['command'])
    return {'address': ble.address, 'sent': payload['command']}
