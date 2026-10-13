"""TQT R1 wire protocol extracted from main.c; no hardware dependencies."""
from __future__ import annotations
from dataclasses import dataclass
import re

FIELDS = (
    "BLK", "OUT1", "OUT2", "OUT3", "INT1", "INT2", "INT3", "EST1", "EST2", "EST3",
    "MOTOR", "SEN_MOT", "TIEMPO", "DBG", "VIVA", "TQT", "ON", "OFF", "PB", "err",
    "RESET", "VER", "HW", "MOV", "Mensaje", "IDR", "MACR", "ID", "MAC",
)
HELP = {
 "BLK":"Salida asociada al bloqueo externo del rastreador. 0 significa deshabilitada.",
 "OUT1":"Configuración de la salida auxiliar 1; no es una prueba física de este proyecto.",
 "OUT2":"Configuración de la salida auxiliar 2; no se prueba en la rutina actual.",
 "OUT3":"Estado/indicador de bloqueo actualizado por la lógica del motor.",
 "INT1":"Configuración de la entrada auxiliar 1 (sin prueba física en este flujo).",
 "INT2":"Configuración de la entrada auxiliar 2 (sin prueba física en este flujo).",
 "INT3":"Configuración de la entrada auxiliar 3 (sin prueba física en este flujo).",
 "EST1":"Nivel lógico observado de entrada auxiliar 1, invertido desde la lectura GPIO.",
 "EST2":"Nivel lógico observado de entrada auxiliar 2, invertido desde la lectura GPIO.",
 "EST3":"Nivel lógico observado de entrada auxiliar 3, invertido desde la lectura GPIO.",
 "MOTOR":"Configuración del límite de corriente del motor: 0 es el valor de fábrica y no selecciona explícitamente un umbral. En este main.c, ADC_DELTA se inicializa con ADC_5A_DELTA y no se actualiza según MOTOR; confirmar protección real en el banco.",
 "SEN_MOT":"Modo de control: 0 utiliza sensores de fin de carrera; 1 funciona por tiempo sin validación del sensor.",
 "TIEMPO":"Segundos adicionales autorizados para completar el movimiento del motor (0–10).",
 "DBG":"Modo de mensajes de diagnóstico TQT. 0 transmite estados S29; 1 transmite mensajes de diagnóstico.",
 "VIVA":"Indicador alternante de vida que el firmware conmuta periódicamente; no es prueba del motor.",
 "TQT":"Estado temporal del motor: 0 espera, 1 abriendo, 2 abierto, 3 cerrando, 4 cerrado, 5 error. Generalmente vuelve a 0.",
 "ON":"Sensor de CIERRE. 1 significa sensor de perno afuera / bloqueado activo. No es el comando ON.",
 "OFF":"Sensor de APERTURA. 1 significa sensor de perno adentro / desbloqueado activo. No es el comando OFF.",
 "PB":"Origen del último comando de movimiento: 1 serial/plataforma; 2 Bluetooth; 0 sistema.",
 "err":"Último código de error/evento informado por R1; puede persistir hasta que se limpia (hasta dos minutos). Los códigos 13/14 son cambios de sensores en espera.",
 "RESET":"Contador de arranques de R1; Reset_44 reinicia configuración y contadores en EEPROM.",
 "VER":"Versión firmware declarada por identidad fija de R1.",
 "HW":"Versión de hardware declarada por identidad fija de R1.",
 "MOV":"Contador de movimientos exitosos. Debe aumentar una vez por movimiento real y no por órdenes repetidas cuando ya está en posición.",
 "Mensaje":"Número de mensaje/reintento de la cola GPS, por ejemplo 3.0. Sirve para detectar retransmisiones.",
 "IDR":"Identificador fijo del conjunto o R relacionado, obtenido de identidad compilada.",
 "MACR":"MAC del dispositivo R relacionado según la identidad compilada; NO es la MAC que transmite R1 al pedir MAC al ESP32.",
 "ID":"Sufijo del nombre de tarjeta obtenido de su identidad fija.",
 "MAC":"MAC que R1 consulta al ESP32 por UART. Debe contrastarse con la MAC BLE observada, teniendo en cuenta privacidad BLE de Windows.",
}
ERRORS = {0:"Sin error activo",1:"Comando no reconocido",2:"Comando Bluetooth no reconocido",3:"Fallo de apertura",4:"Fallo de cierre",5:"Reinicio BLE por comunicación",6:"Bloqueo fuera de rango",7:"Reinicio Bluetooth solicitado",8:"No se guardó nombre BLE",9:"Nombre BLE guardado (evento)",10:"Error al guardar nombre",11:"Salida fuera de rango",12:"Entrada fuera de rango",13:"Cambio del sensor de apertura en reposo",14:"Cambio del sensor de cierre en reposo",15:"Evento de protección",16:"Mensaje BLE incompleto",17:"Mensaje GPS incompleto",18:"Mensaje debug incompleto",19:"Modo de sensores incorrecto",20:"Separador de sensores inválido",21:"Separador de valor inválido",22:"Modo debug incorrecto",23:"Tiempo fuera de rango"}
READY_RE = re.compile(r'(?P<name>[A-Za-z0-9_\-]+)\s*-\s*Lista para usarse\b', re.IGNORECASE)
POST_RE = re.compile(r'AT\$POST=1,0,"(?P<body>[^"]*)"')
MAC_RE = re.compile(r'^[0-9A-F]{12}$')


def normalize_mac(value: str) -> str:
    return re.sub(r'[^0-9A-F]', '', (value or '').upper())


def read_ready(line: str) -> str | None:
    match = READY_RE.search(line)
    return match.group('name') if match else None


@dataclass(frozen=True)
class Status:
    fields: dict[str, str]
    raw: str
    def number(self, name: str) -> int | None:
        try: return int(self.fields[name])
        except (ValueError, TypeError, KeyError): return None
    @property
    def position(self) -> str:
        closed, opened = self.number('ON'), self.number('OFF')
        if (closed, opened) == (1, 0): return 'cerrado'
        if (closed, opened) == (0, 1): return 'abierto'
        if (closed, opened) == (1, 1): return 'conflicto'
        return 'indeterminado'


def parse_status(line: str) -> Status | None:
    found = POST_RE.search(line)
    if not found: return None
    body = found.group('body')
    m = re.match(r'S29(?P<sep>[^\w\s])', body)
    if not m: return None
    sep = m.group('sep')
    entries = body[4:].split(sep)
    if len(entries) != 29: return None
    # SPAV is configurable (: or ; among usual choices). Only split at first occurrence.
    values: dict[str, str] = {}
    for expected, entry in zip(FIELDS, entries):
        if not entry.startswith(expected) or len(entry) <= len(expected): return None
        v = entry[len(expected):]
        if v[0] not in ':;=,': return None
        values[expected] = v[1:]
    return Status(values, line)


def serial_action(command: str) -> bytes:
    actions = {'POFF':'$SMSG=OFF\r\n', 'PPON':'$SMSG=ON\r\n',
               'RESET_FACTORY':'$SMSG=Reset_44\r\n','RESET':'$SMSG=Reset\r\n',
               'RESET_BLE':'$SMSG=Reset_BLE\r\n',
               'STATUS':'$SMSG=Status\r\n', 'MOTOR_STATUS':'$SMSG=Status_Motor\r\n',
               'MAP_QUERY':'$SMSG=MAP?\r\n','MAP_M1_0':'$SMSG=MAP_M1:0\r\n',
               'MAP_M1_1':'$SMSG=MAP_M1:1\r\n','MAP_M2_0':'$SMSG=MAP_M2:0\r\n',
               'MAP_M2_1':'$SMSG=MAP_M2:1\r\n'}
    if command not in actions: raise ValueError('Comando serial no autorizado')
    return actions[command].encode('ascii')
