#!/usr/bin/env python3
"""Herramientas offline para R1 STM32F103RET6. NO programa dispositivos.

Ejemplos:
  python tqt_hex.py inspeccionar --hex Debug/mi_firmware.hex
  python tqt_hex.py preparar-web --hex Debug/mi_firmware.hex --salida firmware_base.hex
  python tqt_hex.py identidad --nombre TQT_R1_V30_0023 --id 0023 --mac-r 8C:8C:29:C3:F4:47 --hw 3.0 --fw 4.3 --salida id_0023.hex
  python tqt_hex.py personalizar --hex firmware_base.hex --nombre TQT_R1_V30_0023 --id 0023 --mac-r 8C:8C:29:C3:F4:47 --hw 3.0 --salida r1_0023.hex

El personalizador trabaja solo con la direccion de Flash reservada y no
modifica opcodes ni archivos fuente. Rechaza rangos fuera de la Flash prevista.
"""
from __future__ import annotations

import argparse
import re
import struct
import zlib
import hashlib
import json
from pathlib import Path

FLASH_BEGIN = 0x08000000
IDENTITY_BEGIN = 0x0807F800
FLASH_END_EXCLUSIVE = 0x08080000
PAGE_BYTES = 2048
MAGIC = 0x31545154  # TQT1 en little-endian
VERSION = 2
FORMAT = '<IHH23s5s18s8s8sHI'
SIZE = struct.calcsize(FORMAT)
assert SIZE == 76
PROFILE_FORMAT = '<8s16s8s8sHHI'
PROFILE_MAGIC = b'TQTFWM2\0'


def _field(value: str, maximum: int, description: str) -> bytes:
    try:
        raw = value.encode('ascii')
    except UnicodeEncodeError as ex:
        raise ValueError(f'{description} solo acepta ASCII') from ex
    if not (1 <= len(raw) <= maximum) or b'\0' in raw:
        raise ValueError(f'{description}: longitud permitida 1..{maximum} y sin NUL')
    return raw + bytes(maximum + 1 - len(raw))


def validar(nombre: str, id_r: str, mac_r: str, hw: str, fw: str) -> None:
    if re.fullmatch(r'[A-Za-z0-9_-]{1,22}', nombre) is None:
        raise ValueError('Nombre: use hasta 22 letras ASCII, numeros, _ o -')
    if re.fullmatch(r'[0-9]{4}', id_r) is None:
        raise ValueError('ID_R de R2: deben ser 4 digitos')
    if re.fullmatch(r'(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}', mac_r) is None:
        raise ValueError('MAC_R: formato requerido XX:XX:XX:XX:XX:XX')
    if mac_r.upper() in ('00:00:00:00:00:00', 'FF:FF:FF:FF:FF:FF'):
        raise ValueError('MAC_R vacia o broadcast')
    for key, value in [('HW', hw), ('FW', fw)]:
        if len(value) > 7 or re.fullmatch(r'[0-9]+(?:\.[0-9]+)*', value) is None:
            raise ValueError(f'{key}: version numerica hasta 7 caracteres')
    prefix = 'TQT_R1_V' + hw.replace('.', '') + '_'
    if re.fullmatch(re.escape(prefix) + r'[0-9]{4}', nombre) is None:
        raise ValueError('Nombre de R1 no coincide con HW o no tiene cuatro digitos')


def identidad_bytes(nombre: str, id_r: str, mac_r: str, hw: str, fw: str) -> bytes:
    validar(nombre, id_r, mac_r, hw, fw)
    raw = struct.pack(FORMAT, MAGIC, VERSION, SIZE,
                       _field(nombre, 22, 'Nombre'),
                       _field(id_r, 4, 'ID_R'),
                       _field(mac_r.upper(), 17, 'MAC_R'),
                       _field(hw, 7, 'HW'), _field(fw, 7, 'FW'), 0, 0)
    return raw[:72] + struct.pack('<I', zlib.crc32(raw[:72]))


def parsear_identidad(payload: bytes) -> dict:
    if len(payload) != SIZE:
        raise ValueError(f'Identidad incompleta: se esperaban {SIZE} bytes')
    magic, version, size, n, i, m, h, f, reserved, crc = struct.unpack(FORMAT, payload)
    if (magic, version, size) != (MAGIC, VERSION, SIZE):
        raise ValueError('Firma, version o longitud de identidad incorrecta')
    if reserved != 0 or crc != zlib.crc32(payload[:72]):
        raise ValueError('CRC32 o bytes reservados de identidad incorrectos')
    def s(raw: bytes) -> str:
        if b'\0' not in raw:
            raise ValueError('Campo de identidad sin NUL')
        dato, padding = raw.split(b'\0', 1)
        if any(padding):
            raise ValueError('Bytes de relleno no nulos: formato invalido')
        return dato.decode('ascii')
    nombre, id_r, mac_r, hw, fw = s(n), s(i), s(m), s(h), s(f)
    validar(nombre, id_r, mac_r, hw, fw)
    if mac_r != mac_r.upper():
        raise ValueError('MAC_R debe estar normalizada en mayusculas')
    return {'nombre': nombre, 'id_r': id_r, 'mac_r': mac_r, 'hw': hw, 'fw': fw}


def leer_perfil(mem: dict[int, int]) -> dict:
    addresses = [a for a in mem if a < IDENTITY_BEGIN]
    if not addresses:
        raise ValueError('Falta firmware: imagen de identidad sola no es una aplicacion')
    start, end = min(addresses), max(addresses) + 1
    blob = bytes(mem.get(a, 255) for a in range(start, end))
    positions = [i for i in range(len(blob)) if blob.startswith(PROFILE_MAGIC, i)]
    if len(positions) != 1:
        raise ValueError('Firmware sin perfil compatible unico; integrar primero esquema 2 en CubeIDE')
    pos = positions[0]
    size = struct.calcsize(PROFILE_FORMAT)
    if pos + size > len(blob) or any(start+pos+i not in mem for i in range(size)):
        raise ValueError('Perfil de firmware incompleto')
    _, mcu, fw, hw, schema, length, address = struct.unpack(PROFILE_FORMAT, blob[pos:pos+size])
    def field(raw):
        value, padding = raw.split(b'\0', 1)
        if not value or any(padding):
            raise ValueError('Perfil no canonico')
        return value.decode('ascii')
    result = dict(mcu=field(mcu), fw=field(fw), hw=field(hw), schema=schema,
                  identity_size=length, identity_address=address)
    if (result['mcu'], schema, length, address) != ('STM32F103RET6', VERSION, SIZE, IDENTITY_BEGIN):
        raise ValueError('Perfil MCU/esquema/direccion no soportado')
    validar('TQT_R1_V'+result['hw'].replace('.', '')+'_0000',
            '0000', '02:00:00:00:00:01', result['hw'], result['fw'])
    try:
        vector = bytes(mem[FLASH_BEGIN+i] for i in range(8))
    except KeyError as e:
        raise ValueError('Vectores de arranque ausentes') from e
    stack, reset = struct.unpack('<II', vector)
    if not 0x20000000 < stack <= 0x20010000 or stack % 8 or not reset & 1:
        raise ValueError('Vectores de arranque invalidos')
    if not FLASH_BEGIN <= (reset & ~1) < IDENTITY_BEGIN or (reset & ~1) not in mem:
        raise ValueError('Reset fuera del firmware')
    return result


def comprobar_perfil(identity: dict, profile: dict) -> None:
    if identity['hw'] != profile['hw'] or identity['fw'] != profile['fw']:
        raise ValueError('Identidad HW/FW incompatible con firmware compilado')


def _registro(tipo: int, offset: int, data: bytes) -> str:
    if not (0 <= len(data) <= 255 and 0 <= offset <= 65535):
        raise ValueError('Registro Intel HEX fuera de rango')
    blob = bytes([len(data), (offset >> 8) & 255, offset & 255, tipo]) + data
    return ':' + (blob + bytes([(-sum(blob)) & 255])).hex().upper()


def leer_hex(path: Path) -> tuple[dict[int,int], list[tuple[int,bytes]]]:
    """Intel HEX standard (types 00/01/02/03/04/05) con checksum estricto."""
    memoria: dict[int,int] = {}
    arranques: list[tuple[int,bytes]] = []
    base = 0
    eof = False
    for lineno, raw in enumerate(path.read_text(encoding='ascii').splitlines(), 1):
        linea = raw.strip()
        if not linea:
            continue
        if eof or not linea.startswith(':') or len(linea) % 2 != 1:
            raise ValueError(f'{path}:{lineno}: registro invalido o despues de EOF')
        try:
            rec = bytes.fromhex(linea[1:])
        except ValueError as e:
            raise ValueError(f'{path}:{lineno}: bytes hex incorrectos') from e
        if len(rec) < 5 or rec[0] != len(rec)-5 or sum(rec) % 256:
            raise ValueError(f'{path}:{lineno}: longitud/checksum incorrecto')
        length, offset, typ = rec[0], (rec[1]<<8)|rec[2], rec[3]
        data = rec[4:-1]
        if typ == 0:
            if offset + length > 65536:
                raise ValueError(f'{path}:{lineno}: registro cruza segmento de 64 KiB')
            for k, val in enumerate(data):
                addr = base + offset + k
                if not FLASH_BEGIN <= addr < FLASH_END_EXCLUSIVE:
                    raise ValueError(f'{path}:{lineno}: dato fuera de Flash 0x{addr:08X}')
                if addr in memoria:
                    raise ValueError(f'{path}:{lineno}: direcciones superpuestas')
                memoria[addr] = val
        elif typ == 1:
            if length or offset:
                raise ValueError(f'{path}:{lineno}: EOF no valido')
            eof = True
        elif typ == 2:
            if length != 2 or offset:
                raise ValueError(f'{path}:{lineno}: segmento no valido')
            base = int.from_bytes(data,'big') << 4
        elif typ == 4:
            if length != 2 or offset:
                raise ValueError(f'{path}:{lineno}: extension lineal no valida')
            base = int.from_bytes(data,'big') << 16
        elif typ in (3, 5):
            if length != 4 or offset:
                raise ValueError(f'{path}:{lineno}: direccion de arranque no valida')
            if arranques:
                raise ValueError(f'{path}:{lineno}: varias direcciones de arranque')
            arranques.append((typ,data))
        else:
            raise ValueError(f'{path}:{lineno}: tipo de registro no admitido {typ:02X}')
    if not eof:
        raise ValueError(f'{path}: falta registro EOF')
    if not memoria:
        raise ValueError(f'{path}: imagen vacia')
    return memoria, arranques


def emitir_hex(memoria: dict[int,int], arranques: list[tuple[int,bytes]] | None=None) -> str:
    lines: list[str] = []
    upper = None
    addrs = sorted(memoria)
    j=0
    while j < len(addrs):
        first = addrs[j]
        segment = first >> 16
        if segment != upper:
            lines.append(_registro(4,0,segment.to_bytes(2,'big')))
            upper = segment
        data = bytearray([memoria[first]])
        j+=1
        while (j < len(addrs) and len(data) < 16 and
               addrs[j] == first + len(data) and (addrs[j]>>16) == upper):
            data.append(memoria[addrs[j]])
            j+=1
        lines.append(_registro(0,first&0xFFFF,bytes(data)))
    for typ, data in (arranques or []):
        lines.append(_registro(typ,0,data))
    lines.append(_registro(1,0,b''))
    return '\n'.join(lines)+'\n'


def leer_identidad(mem: dict[int,int]) -> dict | None:
    found = [a for a in mem if IDENTITY_BEGIN <= a < FLASH_END_EXCLUSIVE]
    if not found:
        return None
    try:
        datos = bytes(mem[IDENTITY_BEGIN + k] for k in range(SIZE))
    except KeyError as e:
        raise ValueError('Identidad parcial en zona reservada') from e
    # El linker puede incluir 0-3 bytes adicionales por alineacion de seccion.
    limite = IDENTITY_BEGIN + ((SIZE+3)//4)*4
    if any(a >= limite for a in found):
        raise ValueError('Hay otros datos ajenos a identidad dentro de la pagina reservada')
    return parsear_identidad(datos)


def guardar(path: Path, contenido: str) -> None:
    if path.exists():
        raise ValueError(f'No se sobrescribe el archivo existente: {path}')
    # Exact bytes: Windows newline conversion must not invalidate SHA256.
    with path.open('xb') as target:
        target.write(contenido.encode('ascii'))


def guardar_imagen(path: Path, mem: dict, starts: list, source: Path, profile: dict) -> None:
    manifest_path = path.with_suffix(path.suffix + '.json')
    if path.exists() or manifest_path.exists() or path.resolve() == source.resolve():
        raise ValueError('Salida o manifiesto ya existe; no se sobreescribe')
    content = emitir_hex(mem, starts)
    identity = leer_identidad(mem)
    manifest = dict(profile=profile, identity=identity,
                    source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                    hex_sha256=hashlib.sha256(content.encode('ascii')).hexdigest(),
                    identity_sha256=hashlib.sha256(bytes(mem[IDENTITY_BEGIN+i] for i in range(SIZE))).hexdigest() if identity else None)
    guardar(path, content)
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')


def argumentos_identidad(p: argparse.ArgumentParser) -> None:
    p.add_argument('--nombre', required=True)
    p.add_argument('--id', dest='id_r', required=True, help='Numero de la R2 asociada; puede diferir del serial R1')
    p.add_argument('--mac-r', required=True)
    p.add_argument('--hw', required=True)
    p.add_argument('--fw', help='Debe coincidir con el perfil del HEX; por defecto se toma de ese perfil')


def main() -> None:
    parser = argparse.ArgumentParser(description='TQT R1: preparar HEX, offline. Nunca programa USB/J-Link.')
    sub = parser.add_subparsers(dest='accion', required=True)
    inspect = sub.add_parser('inspeccionar', help='revisar las direcciones y la identidad del HEX')
    inspect.add_argument('--hex',required=True,type=Path)
    verify = sub.add_parser('validar', help='validar imagen, perfil, vectores y CRC')
    verify.add_argument('--hex', required=True, type=Path)
    web = sub.add_parser('preparar-web', help='extraer firmware generico, sin identidad particular')
    web.add_argument('--hex',required=True,type=Path)
    web.add_argument('--salida',required=True,type=Path)
    ident = sub.add_parser('identidad', help='generar un HEX solo con los 76 bytes de identidad (no programa)')
    argumentos_identidad(ident)
    ident.add_argument('--salida',required=True,type=Path)
    personalize = sub.add_parser('personalizar', help='crear firmware HEX completo para una tarjeta')
    personalize.add_argument('--hex',required=True,type=Path,help='firmware generico (sin identidad)')
    argumentos_identidad(personalize)
    personalize.add_argument('--salida',required=True,type=Path)
    a=parser.parse_args()
    try:
        if a.accion == 'identidad':
            if not a.fw:
                raise ValueError('identidad requiere --fw; preferir personalizar una imagen completa')
            payload = identidad_bytes(a.nombre,a.id_r,a.mac_r,a.hw,a.fw)
            mem = {IDENTITY_BEGIN+k:b for k,b in enumerate(payload)}
            guardar(a.salida,emitir_hex(mem))
            print(f'Identidad generada: {a.salida} ({SIZE} bytes en 0x{IDENTITY_BEGIN:08X})')
            return
        mem, starts = leer_hex(a.hex)
        identity = leer_identidad(mem)
        profile = leer_perfil(mem)
        if identity:
            comprobar_perfil(identity, profile)
        if a.accion in ('inspeccionar', 'validar'):
            print(f'{a.hex}: {len(mem)} bytes de Flash registrados')
            print('Perfil:', profile)
            print('Identidad:', identity if identity else 'NO INCLUIDA')
            print('SHA256:', hashlib.sha256(a.hex.read_bytes()).hexdigest())
        elif a.accion == 'preparar-web':
            if not identity:
                raise ValueError('El HEX debe incluir una identidad local valida antes de prepararse')
            mem = {k:v for k,v in mem.items() if k < IDENTITY_BEGIN}
            guardar_imagen(a.salida,mem,starts,a.hex,profile)
            print(f'Generado firmware generico sin identidad: {a.salida}')
            print('Se extrajo identidad local:',identity)
        elif a.accion == 'personalizar':
            if identity or any(k >= IDENTITY_BEGIN for k in mem):
                raise ValueError('El archivo base contiene identidad: ejecutar preparar-web antes')
            fw = a.fw or profile['fw']
            payload=identidad_bytes(a.nombre,a.id_r,a.mac_r,a.hw,fw)
            comprobar_perfil(parsear_identidad(payload),profile)
            mem.update({IDENTITY_BEGIN+k:v for k,v in enumerate(payload)})
            guardar_imagen(a.salida,mem,starts,a.hex,profile)
            print(f'Firmware personalizado: {a.salida}')
    except (ValueError, OSError) as e:
        parser.exit(2,'ERROR: '+str(e)+'\n')


if __name__ == '__main__':
    main()
