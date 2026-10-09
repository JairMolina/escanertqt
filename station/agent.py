"""Outbound Windows agent. No listening ports; hardware writes only after local confirmation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import ssl
import subprocess
import tempfile
import time
import urllib.request
import tqt_hex as hx


def find_jlink():
    for root in (Path(os.environ.get('ProgramFiles', 'C:/Program Files')),
                 Path(os.environ.get('ProgramFiles(x86)', 'C:/Program Files (x86)'))):
        files = sorted((root/'SEGGER').glob('JLink*/JLink.exe'), reverse=True)
        if files:
            return str(files[0])
    raise ValueError('No se encontró SEGGER JLink.exe. Instala J-Link Software and Documentation Pack.')


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
    proc = subprocess.run(args, cwd=directory, capture_output=True, text=True, errors='replace', timeout=180)
    trace = proc.stdout+'\n'+proc.stderr
    if proc.returncode:
        raise ValueError('J-Link falló: '+trace[-4000:])
    return trace


def flash(work, exe, serial=''):
    with tempfile.TemporaryDirectory(prefix='tqt_stm32_') as tmp:
        directory = Path(tmp)
        image, mem = validate(work, directory)
        # Fixed filenames avoid user strings inside Commander commands.
        trace = commander(exe, directory, ['r', 'h', 'loadfile firmware.hex', 'h',
                          'savebin readback.bin, 0x08000000, 0x80000',
                          'savebin uid.bin, 0x1FFFF7E8, 12', 'q'], serial)
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
            raise ValueError('UID STM32 inválido o lectura incompleta.')
        trace += commander(exe, directory, ['r', 'g', 'q'], serial)
        return dict(verified=True, hex_sha256=work['payload']['hex_sha256'],
                    identity_sha256=hashlib.sha256(raw).hexdigest(), uid=uid.hex().upper(), trace=trace[-16000:])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default='config.json')
    parser.add_argument('--validate-only', type=Path, help='Validar un trabajo JSON sin abrir J-Link')
    args = parser.parse_args()
    if args.validate_only:
        with tempfile.TemporaryDirectory() as tmp:
            validate(json.loads(args.validate_only.read_text(encoding='utf-8')), Path(tmp))
        print('HEX e identidad válidos. No se abrió J-Link.')
        return
    config_path = Path(args.config).resolve()
    cfg = json.loads(config_path.read_text(encoding='utf-8'))
    server = cfg['server'].rstrip('/')
    ctx = ssl.create_default_context()
    if (config_path.parent/'ca.crt').exists():
        ctx.load_verify_locations(cafile=str(config_path.parent/'ca.crt'))
    def api(path, body):
        req = urllib.request.Request(server+'/api/stm32/agent/'+path,
              data=json.dumps(body).encode(), headers={'Authorization': 'Bearer '+cfg['token'], 'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=20, context=ctx) as response:
            return json.load(response)
    exe = cfg.get('jlink') or find_jlink()
    serial = cfg.get('jlink_serial', '')
    print('Estación:', cfg['station_id'], '\nServidor:', server, '\nJ-Link:', exe)
    print('Mantén esta ventana abierta. Cada trabajo pide confirmar la R1 conectada. Ctrl+C para salir.')
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
                    confirm = input('Confirma que ESA R1 está conectada al J-Link. Escribe PROGRAMAR: ')
                    if confirm != 'PROGRAMAR':
                        raise ValueError('Trabajo cancelado en la estación; no se grabó.')
                    result = flash(work, exe, serial)
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
