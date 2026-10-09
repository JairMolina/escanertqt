"""Outbound Windows agent. No listening ports; writes require physical confirmation in the web UI."""
import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path
import ssl
import subprocess
import tempfile
import threading
import time
import urllib.request
import tqt_hex as hx

USER_AGENT = 'TQT-Station/1.3.63'


# ---------------------------------------------------------------------------
# Bluetooth LE opcional (bleak). Hilo propio con su event loop: nunca bloquea STM32/J-Link.
# ---------------------------------------------------------------------------
BLE_SERVICE = '4fafc201-1fb5-459e-8fcc-c5c9c331914b'
BLE_CHAR = 'beb5483e-36e1-4688-b7f5-ea07361b26a8'
BLE_FALTA = 'Instala bleak: python -m pip install --user "bleak>=0.22,<3"'
try:
    import bleak
except Exception:  # bleak ausente o sin backend Bluetooth
    bleak = None


class BleWorker:
    """Ejecuta los trabajos BLE de la web. `api(path, body)` ya autentica con el bearer de estación."""

    def __init__(self, api, lib=None):
        self.api = api
        self.lib = lib if lib is not None else bleak
        self.client = None
        self.nombre = None
        self.address = None
        self.loop = None

    @property
    def disponible(self):
        return self.lib is not None

    @property
    def conectado(self):
        return bool(self.client is not None and self.client.is_connected)

    def _evento(self, tipo, texto, nombre=None, address=None):
        try:
            self.api('ble/evento', {'tipo': tipo, 'texto': (texto or '')[:1000], 'nombre': nombre, 'address': address})
        except Exception as e:
            print('Evento BLE no reportado:', str(e)[:200])

    def _evento_async(self, *args):
        # Fuera del event loop para no bloquearlo con la red.
        threading.Thread(target=self._evento, args=args, daemon=True).start()

    async def escanear(self):
        found = await self.lib.BleakScanner.discover(timeout=6.0, return_adv=True)
        out = []
        for address, pair in found.items():
            device, adv = pair
            name = device.name or getattr(adv, 'local_name', None) or ''
            if 'TQT' in name.upper():
                out.append({'nombre': name, 'address': address, 'rssi': getattr(adv, 'rssi', None)})
        out.sort(key=lambda d: d['rssi'] if d['rssi'] is not None else -999, reverse=True)
        return {'dispositivos': out}

    async def desconectar(self):
        client, self.client = self.client, None
        self.nombre = self.address = None
        if client is not None:
            try:
                client.disconnected_callback = None
            except Exception:
                pass
            try:
                await client.disconnect()
            except Exception:
                pass
        return {'conectado': False}

    async def conectar(self, address):
        if not address:
            raise ValueError('Falta la dirección del dispositivo.')
        await self.desconectar()
        nombre = address
        try:
            dev = await self.lib.BleakScanner.find_device_by_address(address, timeout=6.0)
            if dev is not None and dev.name:
                nombre = dev.name
        except Exception:
            pass

        def lost(_client):
            if self.client is not None and self.address == address:
                self.client = None
                self.nombre = self.address = None
                self._evento_async('desconexion', 'El dispositivo se desconectó.', nombre, address)

        client = self.lib.BleakClient(address, disconnected_callback=lost)
        await client.connect()
        try:
            char = None
            for svc in client.services:
                if svc.uuid.lower() == BLE_SERVICE:
                    for ch in svc.characteristics:
                        if ch.uuid.lower() == BLE_CHAR:
                            char = ch
            if char is None:
                raise ValueError('El dispositivo no tiene el servicio/característica TQT esperados.')
            props = set(p.lower() for p in char.properties)
            if props & {'notify', 'indicate'}:
                def on_notify(_sender, data):
                    self._evento_async('notificacion', bytes(data).decode('utf-8', errors='replace'), nombre, address)
                await client.start_notify(char, on_notify)
        except Exception:
            try:
                client.disconnected_callback = None
                await client.disconnect()
            except Exception:
                pass
            raise
        self.client, self.nombre, self.address = client, nombre, address
        return {'conectado': True, 'nombre': nombre, 'address': address}

    async def enviar(self, comando):
        if comando not in ('PPON', 'POFF'):
            raise ValueError('Comando no permitido.')
        if not self.conectado:
            raise ValueError('No hay dispositivo conectado.')
        char = self.client.services.get_characteristic(BLE_CHAR)
        if char is None:
            raise ValueError('Característica TQT no disponible.')
        props = set(p.lower() for p in char.properties)
        if not props & {'write', 'write-without-response'}:
            raise ValueError('La característica no admite escritura.')
        await self.client.write_gatt_char(char, comando.encode('ascii'), response='write' in props)
        return {'comando': comando}

    async def ejecutar(self, work):
        if not self.disponible:
            raise ValueError(BLE_FALTA)
        accion = work.get('accion')
        if accion == 'escanear':
            return await self.escanear()
        if accion == 'conectar':
            return await self.conectar(work.get('address'))
        if accion == 'enviar':
            return await self.enviar(work.get('comando'))
        if accion == 'desconectar':
            return await self.desconectar()
        raise ValueError('Acción BLE desconocida.')

    async def paso(self):
        """Un ciclo: informa estado, toma un trabajo y reporta su resultado. Los errores de red no salen de aquí."""
        import asyncio
        try:
            work = await asyncio.to_thread(self.api, 'ble/claim', {
                'ble_disponible': self.disponible, 'conectado': self.conectado,
                'nombre': self.nombre, 'address': self.address})
        except Exception as e:
            print('BLE sin conexión al servidor:', str(e)[:200])
            return None
        if not work:
            return None
        try:
            body = {'ok': True, 'resultado': await self.ejecutar(work)}
        except Exception as e:
            body = {'ok': False, 'error': (str(e) or e.__class__.__name__)[:1000]}
        for _ in range(3):
            try:
                await asyncio.to_thread(self.api, 'ble/'+work['id']+'/resultado', body)
                break
            except Exception as e:
                print('Resultado BLE no reportado:', str(e)[:200])
                await asyncio.sleep(1)
        return body

    async def bucle(self):
        import asyncio
        while True:
            try:
                await self.paso()
            except Exception as e:
                print('Error BLE:', str(e)[:200])
            await asyncio.sleep(0.7)

    def hilo(self):
        import asyncio
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self.bucle())


def start_ble(api, lib=None):
    worker = BleWorker(api, lib)
    if not worker.disponible:
        print('BLE no disponible.', BLE_FALTA)
    threading.Thread(target=worker.hilo, name='tqt-ble', daemon=True).start()
    return worker


def web_confirmation(work):
    data = work['payload']
    confirmed = data.get('confirmation') or {}
    if (confirmed.get('source') != 'web' or not confirmed.get('operator')
            or confirmed.get('pcb_id') != data.get('pcb_id')
            or confirmed.get('nombre') != data['identity']['nombre']):
        raise ValueError('Trabajo sin confirmación web válida de la R1 conectada; vuelve a prepararlo desde la web.')


def execute(work, exe, serial='', progress=lambda stage: None):
    if not exe:
        raise ValueError('Esta laptop no tiene J-Link (SEGGER o STM32CubeIDE): solo puede hacer pruebas Bluetooth.')
    web_confirmation(work)
    return flash(work, exe, serial, progress)


def find_jlink():
    found = shutil.which('JLink.exe')
    if found:
        return found
    for root in (Path(os.environ.get('ProgramFiles', 'C:/Program Files')),
                 Path(os.environ.get('ProgramFiles(x86)', 'C:/Program Files (x86)'))):
        files = sorted((root/'SEGGER').glob('JLink*/JLink.exe'), reverse=True)
        if files:
            return str(files[0])
    # CubeIDE includes Commander and its matching DLLs; keep it in its installation.
    for root in (Path('C:/ST'), Path(os.environ.get('ProgramFiles', 'C:/Program Files'))/'ST'):
        files = sorted(root.glob('STM32CubeIDE*/STM32CubeIDE/plugins/com.st.stm32cube.ide.mcu.externaltools.jlink*/tools/bin/JLink.exe'), reverse=True)
        if files:
            return str(files[0])
    raise ValueError('No se encontró JLink.exe en SEGGER ni STM32CubeIDE. Instala J-Link o indica su ruta en config.json.')


def image_hash(mem):
    return hashlib.sha256(bytes(mem[a] for a in sorted(mem))).hexdigest()


def validate(work, directory):
    image = directory/'firmware.hex'
    data = work['payload']
    image.write_bytes(work['hex'].encode('ascii'))
    if hashlib.sha256(image.read_bytes()).hexdigest() != data['hex_sha256']:
        raise ValueError('El hash del HEX recibido no coincide.')
    mem, _ = hx.leer_hex(image)
    if data.get('kind') == 'R3':
        # R3: fixed image without per-unit identity; never write the reserved identity page.
        if any(not hx.FLASH_BEGIN <= a < hx.IDENTITY_BEGIN for a in mem):
            raise ValueError('El firmware R3 escribe fuera de la Flash de aplicación.')
        if image_hash(mem) != data['identity_sha256']:
            raise ValueError('Hash de imagen R3 incorrecto.')
        return image, mem
    identity = hx.leer_identidad(mem)
    hx.comprobar_perfil(identity, hx.leer_perfil(mem))
    if identity != data['identity']:
        raise ValueError('La identidad recibida no coincide con el trabajo.')
    raw = bytes(mem[hx.IDENTITY_BEGIN+i] for i in range(hx.SIZE))
    if hashlib.sha256(raw).hexdigest() != data['identity_sha256']:
        raise ValueError('Hash de identidad incorrecto.')
    return image, mem


def commander(exe, directory, commands, serial=''):
    script = directory/'commands.jlink'
    script.write_text('\n'.join(commands)+'\n', encoding='ascii')
    args = [exe, '-Device', 'STM32F103RE', '-If', 'SWD', '-Speed', '1000',
            '-AutoConnect', '1', '-ExitOnError', '1', '-NoGui', '1', '-CommandFile', str(script)]
    if serial:
        args += ['-USB', serial]
    # -NoGui suppresses SEGGER dialogs; CREATE_NO_WINDOW suppresses the Windows console.
    options = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
    proc = subprocess.run(args, cwd=directory, capture_output=True, text=True, errors='replace', timeout=180, **options)
    trace = proc.stdout+'\n'+proc.stderr
    if proc.returncode:
        raise ValueError('J-Link falló: '+trace[-4000:])
    return trace


def flash(work, exe, serial='', progress=lambda stage: None):
    with tempfile.TemporaryDirectory(prefix='tqt_stm32_') as tmp:
        directory = Path(tmp)
        progress('preparing')
        image, mem = validate(work, directory)
        # Fixed filenames avoid user strings inside Commander commands.
        progress('writing')
        trace = commander(exe, directory, ['r', 'h', 'loadfile firmware.hex', 'h', 'q'], serial)
        progress('reading')
        trace += commander(exe, directory, ['h', 'savebin readback.bin, 0x08000000, 0x80000',
                          'savebin uid.bin, 0x1FFFF7E8, 0xC', 'q'], serial)
        readback = (directory/'readback.bin').read_bytes()
        if len(readback) != 0x80000:
            raise ValueError('Lectura Flash incompleta. No se confirma programación.')
        for address, expected in mem.items():
            if readback[address-hx.FLASH_BEGIN] != expected:
                raise ValueError(f'La verificación difiere en 0x{address:08X}.')
        r3 = work['payload'].get('kind') == 'R3'
        if r3:
            raw = None
            proof = hashlib.sha256(bytes(readback[a-hx.FLASH_BEGIN] for a in sorted(mem))).hexdigest()
        else:
            raw = readback[hx.IDENTITY_BEGIN-hx.FLASH_BEGIN:hx.IDENTITY_BEGIN-hx.FLASH_BEGIN+hx.SIZE]
            hx.parsear_identidad(raw)
            proof = hashlib.sha256(raw).hexdigest()
        uid = (directory/'uid.bin').read_bytes()
        if len(uid)!=12 or uid in (bytes(12), bytes([255])*12):
            raise ValueError(f'UID STM32 inválido o lectura incompleta: se recibieron {len(uid)} bytes; se esperaban 12.')
        progress('restarting')
        trace += commander(exe, directory, ['r', 'g', 'q'], serial)
        progress('reporting')
        return dict(verified=True, hex_sha256=work['payload']['hex_sha256'],
                    identity_sha256=proof, uid=uid.hex().upper(), trace=trace[-16000:])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default='config.json')
    parser.add_argument('--check', action='store_true', help='Comprobar J-Link y conexión al servidor, sin programar')
    parser.add_argument('--background', action='store_true', help='Operar desde la web y guardar diagnóstico en agente.log')
    parser.add_argument('--validate-only', type=Path, help='Validar un trabajo JSON sin abrir J-Link')
    args = parser.parse_args()
    if args.validate_only:
        with tempfile.TemporaryDirectory() as tmp:
            validate(json.loads(args.validate_only.read_text(encoding='utf-8')), Path(tmp))
        print('HEX e identidad válidos. No se abrió J-Link.')
        return
    config_path = Path(args.config).resolve()
    cfg = json.loads(config_path.read_text(encoding='utf-8'))
    if args.background:
        import sys
        log = config_path.parent/'agente.log'
        if log.exists() and log.stat().st_size > 2_000_000:
            log.replace(config_path.parent/'agente.anterior.log')
        sys.stdout = sys.stderr = log.open('a', encoding='utf-8', buffering=1)
    server = cfg['server'].rstrip('/')
    ctx = ssl.create_default_context()
    if (config_path.parent/'ca.crt').exists():
        ctx.load_verify_locations(cafile=str(config_path.parent/'ca.crt'))
    def api(path, body):
        req = urllib.request.Request(server+'/api/stm32/agent/'+path,
              data=json.dumps(body).encode(), headers={'Authorization': 'Bearer '+cfg['token'], 'Content-Type': 'application/json', 'Accept': 'application/json', 'User-Agent': USER_AGENT})
        with urllib.request.urlopen(req, timeout=20, context=ctx) as response:
            return json.load(response)
    # v1.3.63: J-Link es opcional; una laptop solo para pruebas Bluetooth también queda conectada.
    try:
        exe = cfg.get('jlink') or find_jlink()
    except ValueError as e:
        exe = None
        print('Sin J-Link:', e)
    serial = cfg.get('jlink_serial', '')
    print('Estación:', cfg['station_id'], '\nServidor:', server, '\nJ-Link:', exe)
    if args.check:
        # Health is public. Do not claim a pending hardware job during diagnostics.
        request = urllib.request.Request(server+'/api/health', headers={'User-Agent': USER_AGENT, 'Accept': 'application/json'})
        with urllib.request.urlopen(request, timeout=20, context=ctx) as response:
            if json.load(response).get('ok') is not True:
                raise ValueError('El servidor no confirmó su estado.')
        print('Servidor accesible con TLS válido. J-Link localizado. No se abrió la sonda ni se programó.')
        return
    # One process per station, including hidden startup and manual launches.
    if os.name == 'nt':
        import ctypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateMutexW.restype = ctypes.c_void_p
        kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
        mutex = kernel.CreateMutexW(None, False, 'Local\\TQTSTM32_'+cfg['station_id'])
        if not mutex:
            raise OSError('No se pudo reservar la estación local.')
        if ctypes.get_last_error() == 183:
            print('La estación ya está en ejecución. Usa el botón de la web.')
            return
    start_ble(api)
    print('Estación lista. Selecciona y programa la R1 desde la web; no se requiere escribir en esta consola.')
    pending_result = None
    while True:
        try:
            if pending_result:
                api('jobs/'+pending_result[0]+'/result', pending_result[1])
                pending_result = None
            work = api('claim', {})
            if work:
                d = work['payload']['identity']
                print('\nR1:', d['nombre'], '| R2:', d['id_r'], d['mac_r'], '| FW:', d['fw'])
                try:
                    with tempfile.TemporaryDirectory() as tmp:
                        validate(work, Path(tmp))
                    def progress(stage):
                        try:
                            api('jobs/'+work['id']+'/progress', {'stage': stage})
                        except Exception as e:
                            # Reporting progress must never repeat or interrupt a hardware write.
                            print('Avance no reportado:', str(e)[:200])
                    result = execute(work, exe, serial, progress)
                    print('Grabación y lectura verificadas. UID:', result['uid'])
                except Exception as e:
                    result = dict(verified=False, error=str(e)[:1000])
                    print('ERROR:', e)
                pending_result = (work['id'], result)
                # Retrying the report never repeats a hardware write.
                saved = config_path.parent/'resultados'
                saved.mkdir(exist_ok=True)
                (saved/(work['id']+'.json')).write_text(json.dumps(result, indent=2), encoding='utf-8')
        except KeyboardInterrupt:
            break
        except Exception as e:
            print('Conexión/reporte pendiente:', str(e)[:300])
        time.sleep(3)


if __name__ == '__main__':
    main()
