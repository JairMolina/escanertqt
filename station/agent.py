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
import time
import urllib.request
import tqt_hex as hx

USER_AGENT = 'TQT-Station/1.3.51'


def web_confirmation(work):
    data = work['payload']
    confirmed = data.get('confirmation') or {}
    if (confirmed.get('source') != 'web' or not confirmed.get('operator')
            or confirmed.get('pcb_id') != data.get('pcb_id')
            or confirmed.get('nombre') != data['identity']['nombre']):
        raise ValueError('Trabajo sin confirmación web válida de la R1 conectada; vuelve a prepararlo desde la web.')


def execute(work, exe, serial='', progress=lambda stage: None):
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


def validate(work, directory):
    image = directory/'firmware.hex'
    data = work['payload']
    image.write_bytes(work['hex'].encode('ascii'))
    if hashlib.sha256(image.read_bytes()).hexdigest() != data['hex_sha256']:
        raise ValueError('El hash del HEX recibido no coincide.')
    mem, _ = hx.leer_hex(image)
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
        raw = readback[hx.IDENTITY_BEGIN-hx.FLASH_BEGIN:hx.IDENTITY_BEGIN-hx.FLASH_BEGIN+hx.SIZE]
        hx.parsear_identidad(raw)
        uid = (directory/'uid.bin').read_bytes()
        if len(uid)!=12 or uid in (bytes(12), bytes([255])*12):
            raise ValueError(f'UID STM32 inválido o lectura incompleta: se recibieron {len(uid)} bytes; se esperaban 12.')
        progress('restarting')
        trace += commander(exe, directory, ['r', 'g', 'q'], serial)
        progress('reporting')
        return dict(verified=True, hex_sha256=work['payload']['hex_sha256'],
                    identity_sha256=hashlib.sha256(raw).hexdigest(), uid=uid.hex().upper(), trace=trace[-16000:])


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
    exe = cfg.get('jlink') or find_jlink()
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
