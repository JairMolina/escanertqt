"""Hardware-in-the-loop test runner. All pass verdicts require fresh R1 S29 evidence."""
from __future__ import annotations
import json
import re
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable
from .protocol import Status, parse_status, read_ready, normalize_mac, serial_action
from .reporting import compare_inventory, communicate, build_warnings, report_html, append_history


@dataclass
class Step:
    name: str
    state: str = 'pendiente'  # pendiente, ejecutando, aprobado, fallido, no_verificado
    detail: str = ''
    started_at: str = ''
    finished_at: str = ''
    duration_s: float | None = None


STEP_NAMES = [
 'Restablecer e identificar R1', 'Verificar estado inicial del motor',
 'R1 serial · Primer movimiento', 'R1 serial · Repetición sin movimiento',
 'R1 serial · Movimiento inverso', 'R1 serial · Repetición inversa',
 'Localizar y conectar R1 BLE', 'R1 BLE · Primer movimiento',
 'R1 BLE · Repetición sin movimiento', 'R1 BLE · Movimiento inverso',
 'R1 BLE · Repetición inversa', 'Desconectar R1 y conectar R2 BLE automáticamente',
 'R2 BLE · Primer movimiento', 'R2 BLE · Movimiento inverso',
]


class TestFailure(Exception): pass
class NoVerification(Exception): pass
class Interrupted(Exception): pass


class TestStation:
    """Callback bridge is thread-safe; UI callbacks must enqueue and never touch Tk directly."""
    def __init__(self, serial, ble, ui: Callable):
        self.serial, self.ble, self.ui = serial, ble, ui
        self.cond = threading.Condition()
        self.observations: list[tuple[str, object]] = []
        self.latest: Status | None = None
        self._latest_at = 0.0
        self.ready_name = ''
        self.steps = [Step(n) for n in STEP_NAMES]
        self.cancel = threading.Event()
        self.running = False
        self.report: dict = {}
        self._log_file = None
        self._log_lock = threading.Lock()
        self._log_path: Path | None = None
        self._started_at = ''
        self._run_thread = None
        self.mac_comparison = 'pendiente'
        self.output_dir = Path('logs')
        self.warnings: list[str] = []
        self._overcurrent_seen = False
        self.inventory_records: dict | None = None
        self.inventory_source = ''
        self.identity_status: Status | None = None
        self.report_files: dict = {}
        # Ventana minima tras un comando repetido, para no aprobarlo con un S29
        # generado por una orden anterior. Es configurable para pruebas.
        self.repeat_verify_s = 5.0  # 4 s de accion base + margen de observacion

    def log(self, message: str):
        ts = datetime.now().astimezone().isoformat(timespec='milliseconds')
        row = f'{ts} | {message}\n'
        with self._log_lock:
            if self._log_file:
                self._log_file.write(row)
                self._log_file.flush()
        self.ui('log', row.rstrip())

    def on_line(self, line: str):
        status = parse_status(line)
        name = read_ready(line)
        motor_status = None
        if 'El perno esta Bloqueado' in line: motor_status = 'cerrado'
        elif 'El perno esta Desbloqueado' in line: motor_status = 'abierto'
        elif 'Ambos sensores activados' in line: motor_status = 'conflicto'
        elif 'El perno esta en MOVIMIENTO' in line: motor_status = 'indeterminado'
        with self.cond:
            if name:
                self.ready_name = name
                self.observations.append(('ready', name))
            if motor_status:
                self.observations.append(('motor_status', motor_status))
            if status and (not self.running or self.ready_name):
                self.latest = status
                self._latest_at = time.monotonic()
                self.observations.append(('status', status))
            self.cond.notify_all()
        if status and (not self.running or self.ready_name):
            self.ui('status', status)
            if self.running and status.number('err') == 15 and not self._overcurrent_seen:
                self._overcurrent_seen = True
                warning = 'Protección / consumo: R1 notificó err=15. Revisar el motor y su corriente.'
                self.warnings.append(warning)
                self.log('ADVERTENCIA: ' + warning)
                self.ui('warning', warning)
        if name: self.ui('card', name)

    def _checkpoint(self) -> int:
        with self.cond: return len(self.observations)

    def _wait(self, start: int, predicate, seconds: float, what='respuesta'):
        until = time.monotonic() + seconds
        next_notice = time.monotonic() + 5
        while True:
            if self.cancel.is_set(): raise Interrupted('Prueba detenida por el usuario')
            with self.cond:
                for tag, val in self.observations[start:]:
                    if predicate(tag, val): return val
                rest = until - time.monotonic()
                if rest <= 0:
                    health = getattr(self.serial, 'health', {})
                    details = f' (diagnóstico serial: {health})' if health else ''
                    raise NoVerification(f'No llegó {what} completo en {seconds:g} s{details}')
                self.cond.wait(min(rest, .2))
            if time.monotonic() >= next_notice:
                self.log(f'ESPERANDO: {what}. No se enviará otro comando hasta recibir la trama requerida.')
                next_notice = time.monotonic() + 5

    def _initial_s29(self, start: int, timeout=22.0) -> Status:
        """R1 emite S29 tras Lista para usarse. No solicitar Status en ese instante."""
        self.log('Esperando S29 espontáneo posterior a Lista para usarse (sin enviar Status)…')
        return self._wait(start, lambda tag, value: tag == 'status', timeout,
                          'S29 inicial después del reinicio')

    def _fresh_status(self, timeout=12, max_age=3.0) -> Status:
        # No inundar el firmware con $SMSG=Status mientras reporta por si mismo.
        with self.cond:
            cached = self.latest
            when = self._latest_at
        if (cached is not None and cached.number('TQT') == 0
                and time.monotonic() - when <= max_age):
            return cached
        start = self._checkpoint()
        self.serial.send(serial_action('STATUS'))
        return self._wait(start, lambda tag, val: tag == 'status' and val.number('TQT') == 0, timeout)

    def _step(self, idx: int, fn, title: str | None = None):
        if self.cancel.is_set(): raise Interrupted('Cancelada')
        step = self.steps[idx]
        if title: step.name = title
        step.state, step.detail = 'ejecutando', ''
        start_monotonic = time.monotonic()
        step.started_at = datetime.now().astimezone().isoformat(timespec='milliseconds')
        self.ui('step', idx, step.state, step.detail)
        self.log('PRUEBA: ' + step.name)
        try:
            detail = fn() or 'Validación completa'
            step.state, step.detail = 'aprobado', detail
        except (NoVerification, Interrupted) as exc:
            step.state, step.detail = 'no_verificado', str(exc)
            self.ui('step', idx, step.state, step.detail)
            self.log('NO VERIFICADO: ' + str(exc))
            raise
        except (TestFailure, RuntimeError, TimeoutError, ValueError) as exc:
            step.state, step.detail = 'fallido', str(exc)
            self.ui('step', idx, step.state, step.detail)
            self.log('FALLO: ' + str(exc))
            raise
        finally:
            step.finished_at = datetime.now().astimezone().isoformat(timespec='milliseconds')
            step.duration_s = round(time.monotonic() - start_monotonic, 3)
        self.ui('step', idx, step.state, step.detail)
        self.log('APROBADO: ' + step.detail)

    def _require(self, value, message):
        if not value: raise TestFailure(message)

    @staticmethod
    def _position(status: Status) -> str:
        position = status.position
        if position not in ('cerrado', 'abierto'):
            raise TestFailure(f'Sensores de motor inconsistentes: ON={status.fields.get("ON")} '
                              f'OFF={status.fields.get("OFF")}; detener movimientos')
        return position

    @staticmethod
    def _next_command(position: str) -> tuple[str, str]:
        if position == 'cerrado': return 'PPON', 'abierto'
        if position == 'abierto': return 'POFF', 'cerrado'
        raise TestFailure('No se puede mover motor con sensores inconsistentes')

    def _await_motor(self, cursor: int, expected: str, prev: int, movement: bool,
                     origin: int, timeout: float = 31) -> Status:
        needed = prev + int(movement)
        until = time.monotonic() + timeout
        last_poll = time.monotonic()
        while time.monotonic() < until:
            if self.cancel.is_set(): raise Interrupted('Prueba detenida')
            with self.cond:
                for kind, v in self.observations[cursor:]:
                    if kind != 'status': continue
                    if v.number('err') in (3, 4):
                        raise TestFailure(f'R1 informó error motor {v.fields["err"]}')
                    # err=15 informa una protección; solo emite aviso. El motor
                    # aun debe cumplir sensores/MOV o fallará por timeout.
                    if (v.position == expected and v.number('MOV') == needed and
                            v.number('PB') == origin and v.number('TQT') == 0):
                        return v
                    if v.number('MOV') is not None and v.number('MOV') > needed:
                        raise TestFailure(f'MOV subió más de lo esperado: {v.number("MOV")} > {needed}')
                self.cond.wait(.2)
            # Consultar solo cuando haya tiempo para procesar un movimiento.
            if time.monotonic() - last_poll >= 5 and time.monotonic() + 2 < until:
                last_poll = time.monotonic()
                try: self.serial.send(serial_action('STATUS'))
                except Exception as exc: self.log('No se pudo consultar Status: '+str(exc))
        raise TestFailure(f'No llegó S29 final: {expected}, MOV={needed}, PB={origin}, TQT=0')

    def _await_repetition(self, cursor: int, expected: str, prev: int, origin: int,
                          command_time: float, timeout: float = 18) -> Status:
        """Exige nueva medición después de una ventana de observación real.

        Nunca acepta un S29 antiguo emitido durante el envío ni justo después.
        MOV no debe cambiar en toda la ventana y debe conservarse la posición.
        """
        until = time.monotonic() + timeout
        eligible_at = command_time + self.repeat_verify_s
        polled = False
        poll_cursor = None
        last_index = cursor
        while time.monotonic() < until:
            if self.cancel.is_set(): raise Interrupted('Prueba detenida')
            with self.cond:
                current = self.observations[last_index:]
                last_index = len(self.observations)
            for offset, (kind, v) in enumerate(current):
                if kind != 'status': continue
                if v.number('err') in (3,4):
                    raise TestFailure(f'R1 informó error motor {v.number("err")} durante repetición')
                mov = v.number('MOV')
                if mov is not None and mov != prev:
                    raise TestFailure(f'MOV cambió durante repetición {prev}→{mov}')
                if v.position != expected or v.number('TQT') in (1,3,5):
                    raise TestFailure(f'Se detectó estado/movimiento inesperado durante repetición: '
                                      f'ON={v.fields.get("ON")}, OFF={v.fields.get("OFF")}, '
                                      f'TQT={v.fields.get("TQT")}')
                # Se exige un S29 recibido despues de solicitar una lectura nueva,
                # nunca se acredita uno antiguo que siga en la cola de la R1.
                index = last_index - len(current) + offset
                if (polled and poll_cursor is not None and index >= poll_cursor and
                        time.monotonic() >= eligible_at and v.number('TQT') == 0 and
                        v.number('PB') == origin and mov == prev):
                    return v
            # Esperar al menos una ventana completa y después solicitar una
            # lectura NUEVA: un estado anterior no demuestra que se ignoró la orden.
            if not polled and time.monotonic() >= eligible_at:
                poll_cursor = self._checkpoint()
                self.serial.send(serial_action('STATUS'))
                polled = True
                continue
            with self.cond: self.cond.wait(.08)
        raise NoVerification(f'No se verificó la repetición {expected} sin movimiento adicional '
                             f'(MOV={prev}, ventana={self.repeat_verify_s:.1f}s)')

    def _motor(self, interface: str, command: str, expected: str, movement: bool, origin: int):
        before = self._fresh_status(timeout=18)
        self._position(before)
        prev = before.number('MOV')
        self._require(prev is not None, 'MOV no válido')
        if movement:
            self._require(before.position != expected, f'Motor ya está {expected}; no se prueba movimiento')
        else:
            self._require(before.position == expected, f'Repetición incorrecta: estado {before.position}')
        cursor = self._checkpoint()
        if interface == 'serial': self.serial.send(serial_action(command))
        else: self.ble.send(command)
        sent_at = time.monotonic()
        if movement:
            after = self._await_motor(cursor, expected, prev, True, origin)
        else:
            after = self._await_repetition(cursor, expected, prev, origin, sent_at)
        return f'{command} → {expected}; MOV {prev}→{after.number("MOV")}; PB={origin}'

    def _r2(self, cmd: str, expected: str, code: int):
        before = self._fresh_status(timeout=18)
        self._position(before)
        self._require(before.position != expected, f'R2 no producirá transición: ya {expected}')
        if before.number('err') == code:
            raise NoVerification(f'err={code} ya estaba activo antes de R2, no es evidencia nueva')
        cursor = self._checkpoint()
        self.ble.send(cmd)
        until = time.monotonic() + 32
        last_poll = 0.0
        moved = event = False
        while time.monotonic() < until:
            if self.cancel.is_set(): raise Interrupted('Cancelada')
            with self.cond:
                for kind, val in self.observations[cursor:]:
                    if kind != 'status': continue
                    if val.position == expected: moved = True
                    if val.number('err') == code: event = True
                if moved and event: break
                self.cond.wait(.2)
            if time.monotonic() - last_poll > 3 and time.monotonic() + 2 < until:
                last_poll = time.monotonic()
                try: self.serial.send(serial_action('STATUS'))
                except Exception: pass
        self._require(moved, f'R1 no observó {expected} tras {cmd} por R2')
        self._require(event, f'R1 no notificó error nuevo {code} tras {cmd} por R2')
        after = self._posicion_estable(cursor, expected)
        self._require(after.position == expected, 'Posición de R2 no se mantuvo estable')
        self._require(after.number('MOV') == before.number('MOV'), 'MOV de R1 cambió durante R2')
        return f'{cmd} → {expected}, err={code} nuevo en R1; MOV de R1 sin incremento'

    def _posicion_estable(self, cursor, expected, ventana=1.5, timeout=10.0):
        """v1.4.65: con R2 el motor lo mueve R2 (R1 queda en TQT=0) y el sensor de fin de carrera puede rebotar
        (ON/OFF 1→0→1) al llegar. Antes se tomaba la última trama en caché, que podía ser justo el rebote.
        Ahora la posición debe sostenerse `ventana` s seguidas (con un Status fresco al final); si a los
        `timeout` s sigue cambiando, falla y se informa cuántos rebotes hubo."""
        hasta = time.monotonic() + timeout
        rebotes, desde, ultimo = 0, None, None
        visto, sondeo = cursor, 0.0
        while time.monotonic() < hasta:
            if self.cancel.is_set(): raise Interrupted('Cancelada')
            if time.monotonic() - sondeo >= 1.0:   # sin tramas espontáneas: se pide Status (1 por segundo como máximo)
                sondeo = time.monotonic()
                try: self.serial.send(serial_action('STATUS'))
                except Exception: pass
            with self.cond:
                for kind, val in self.observations[visto:]:
                    if kind != 'status': continue
                    if val.position == expected:
                        if desde is None: desde = time.monotonic()
                    else:
                        if desde is not None: rebotes += 1
                        desde = None
                    ultimo = val
                visto = len(self.observations)
                if desde is not None and time.monotonic() - desde >= ventana:
                    break
                self.cond.wait(.2)
        if rebotes:
            self.log(f'AVISO SENSOR: la posición {expected} rebotó {rebotes} vez/veces al llegar (R2); '
                     'revisa la alineación del imán y del sensor de fin de carrera')
        if desde is None or time.monotonic() - desde < ventana:
            return ultimo or self._fresh_status(timeout=8)
        final = self._fresh_status(timeout=8, max_age=0)   # confirmación con un Status pedido ahora
        return final

    def _rename_log(self, card: str):
        safe = re.sub(r'[^A-Za-z0-9_-]', '_', card)[:64]
        with self._log_lock:
            old = self._log_path
            if not old: return
            new = self.output_dir / f'{safe}_{self._started_at}.log'
            # Windows cannot reliably rename a file while this process holds it open.
            if self._log_file:
                self._log_file.flush()
                self._log_file.close()
                self._log_file = None
            old.rename(new)
            self._log_path = new
            self._log_file = new.open('a', encoding='utf-8', buffering=1)
        self.ui('logfile', str(new.absolute()))

    def start(self, port: str, r2_address: str = ''):
        if self.running: raise RuntimeError('Ya hay una ejecución activa')
        if not self.serial.connected: raise RuntimeError('Conecta el COM primero')
        self.running = True
        self.cancel.clear()
        self.steps = [Step(n) for n in STEP_NAMES]
        self.latest, self.ready_name = None, ''
        self._latest_at = 0.0
        self.mac_comparison = 'pendiente'
        self.warnings.clear()
        self._overcurrent_seen = False
        self.identity_status = None
        self.report_files = {}
        with self.cond: self.observations.clear()
        if callable(getattr(self.serial, 'reset_diagnostics', None)):
            self.serial.reset_diagnostics()
        self._started_at = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._log_path = self.output_dir / f'PENDIENTE_{self._started_at}.log'
        self._log_file = self._log_path.open('w', encoding='utf-8', buffering=1)
        self.ui('reset_steps')
        self.ui('logfile', str(self._log_path.absolute()))
        self._run_thread = threading.Thread(target=self._execute, args=(port,r2_address), daemon=True, name='TQT tests')
        self._run_thread.start()

    def stop(self):
        self.cancel.set()
        with self.cond: self.cond.notify_all()
        self.log('Solicitud de detener: no se enviarán más comandos. El firmware puede terminar un movimiento ya iniciado.')

    def _execute(self, port: str, r2_address: str):
        issue = ''
        label = 'no_verificado'
        selected_r1 = ''
        selected_r2 = ''
        try:
            self.log('SESIÓN INICIADA | puerto=' + port + ' | banco de pruebas')
            ack_ms=round(getattr(self.serial,'ack_delay_s',0.18)*1000)
            guard_ms=round(getattr(self.serial,'command_quiet_s',0.30)*1000)
            self.log(f'CONFIG TX: ACK={ack_ms} ms | Guardia COM={guard_ms} ms | '
                     'Status sin espera adicional; barrera S29 activa')
            def identify():
                start = self._checkpoint()
                self.serial.send(serial_action('RESET_FACTORY'))
                name = self._wait(start, lambda tag, val: tag == 'ready', 65, 'Lista para usarse')
                self._rename_log(name)
                status = self._initial_s29(start, timeout=22)
                self._require(status.fields.get('ID'), 'S29 sin ID')
                self._require(status.fields.get('MAC'), 'S29 sin MAC')
                self.identity_status = status
                return f'{name} | ID {status.fields["ID"]} | FW {status.fields["VER"]} | MAC {status.fields["MAC"]}'
            self._step(0, identify)
            def check():
                v = self._fresh_status(timeout=22)
                self._position(v)
                self._require(v.number('SEN_MOT') == 0, 'SEN_MOT debe ser 0 para verificar sensores físicos')
                self._require(v.number('TQT') == 0, 'Motor sigue ejecutando una acción')
                self._require(v.number('err') not in (3, 4), f'Error motor activo err={v.number("err")}')
                self.log('Banco de pruebas: MOTOR='+str(v.number('MOTOR'))+'; no se exige autorización adicional')
                return f'Inicio: {v.position} (ON={v.fields["ON"]} OFF={v.fields["OFF"]}); MOTOR={v.number("MOTOR")}'
            self._step(1, check)
            def motor_series(first_index, interface, origin):
                before = self._fresh_status(timeout=20)
                position = self._position(before)
                action1, target1 = self._next_command(position)
                action2, target2 = self._next_command(target1)
                for offset, cmd, target, movement in [(0,action1,target1,True),(1,action1,target1,False),
                                                      (2,action2,target2,True),(3,action2,target2,False)]:
                    label = f'R1 {interface} · {cmd} '+('movimiento' if movement else 'repetición')
                    self._step(first_index+offset, lambda c=cmd,t=target,m=movement:self._motor(interface,c,t,m,origin), label)
            motor_series(2, 'serial', 1)
            found = []
            def connect_r1():
                nonlocal selected_r1, found
                found = self.ble.scan()
                reported = normalize_mac(self.latest.fields.get('MAC','') if self.latest else '')
                names = [d for d in found if d.name.upper() == self.ready_name.upper()]
                mac_matches = [d for d in found if normalize_mac(d.address) == reported and reported]
                options = mac_matches or names
                if len(options) != 1:
                    raise NoVerification(f'R1 BLE ambigua/no localizada. MAC reportada {reported}; encontrados: '+
                                         ', '.join(f'{d.name} {d.address}' for d in found))
                selected_r1 = options[0].address
                self.ble.connect(selected_r1)
                self.mac_comparison = 'coincide' if normalize_mac(selected_r1) == reported else 'no_coincide'
                self.ui('ble_ident','R1',options[0].name,selected_r1,self.mac_comparison)
                if self.mac_comparison == 'no_coincide':
                    self.log('AVISO: MAC vista por Windows distinta de MAC informada por R1; requiere revisión por privacidad/identidad BLE')
                return f'{options[0].name} ({selected_r1}) | criterio '+('MAC' if mac_matches else 'nombre único')
            self._step(6, connect_r1)
            motor_series(7, 'ble', 2)
            def connect_r2():
                nonlocal selected_r2
                self.ble.disconnect()
                scanned = self.ble.scan()  # Fresh scan after disconnecting R1
                related = normalize_mac(self.latest.fields.get('MACR', '') if self.latest else '')
                exact = [d for d in scanned if related and normalize_mac(d.address) == related and
                         d.address != selected_r1]
                if len(exact) == 1:
                    chosen = exact[0]
                    method = 'MACR reportada por R1'
                elif r2_address and r2_address.upper() != selected_r1.upper() and r2_address.upper() in self.ble.devices:
                    selected = [d for d in scanned if d.address == r2_address.upper()]
                    self._require(len(selected) == 1 and 'R2' in selected[0].name.upper(),
                                  'Selección manual no es R2 inequívoca')
                    chosen = selected[0]
                    method = 'selección manual alternativa (MACR no coincidió)'
                else:
                    raise NoVerification('No se identificó R2 automáticamente por MACR='+related+
                        '. Por seguridad, no se enviaron comandos a otro BLE. '+
                        'Opciones: selección manual de R2 y reintentar. Detectados: '+
                        ', '.join(f'{d.name}({d.address})' for d in scanned))
                self._require('R2' in chosen.name.upper(),
                              'La MACR coincide pero el nombre BLE no identifica a R2: '+chosen.name)
                selected_r2 = chosen.address
                self.ble.connect(selected_r2)
                self.ui('ble_ident','R2',chosen.name,selected_r2,method)
                self.log(f'R2 conectada automáticamente por {method}: {chosen.name} / {selected_r2}')
                return f'R2 {chosen.name} ({selected_r2}), criterio: {method}'
            self._step(11,connect_r2)
            # R2 also adapts to the physical starting position, with one pulse per direction.
            initial_r2 = self._fresh_status(timeout=20)
            first, target = self._next_command(self._position(initial_r2))
            other, final_target = self._next_command(target)
            for i, cmd, dest in [(12,first,target),(13,other,final_target)]:
                code = 14 if cmd=='POFF' else 13
                self._step(i,lambda c=cmd,t=dest,e=code:self._r2(c,t,e),f'R2 BLE · {cmd}, nuevo err={code}')
            label = ('aprobado' if all(s.state == 'aprobado' for s in self.steps) and
                     self.mac_comparison == 'coincide' else 'no_verificado')
            health = getattr(self.serial, 'health', {})
            if communicate(health)['state'] == 'no_verificable':
                label = 'no_verificado'
                issue = (issue + '; ' if issue else '') + (
                    'Comunicación serial no verificable: faltaron bytes, hubo reintentos o falló un ACK; '
                    f'diagnóstico {health}')
            if self.mac_comparison == 'no_coincide':
                label = 'no_verificado'
                issue = 'Pruebas funcionales terminadas; discrepancia de MAC R1 vs Windows BLE por revisar'
            base = self.identity_status or self.latest
            check = compare_inventory(self.inventory_records,
                        base.fields.get('ID','') if base else '',
                        base.fields.get('MAC','') if base else '', selected_r1,
                        base.fields.get('MACR','') if base else '', selected_r2)
            if check.get('matched_by') == 'nombre':
                self.log('INVENTARIO: '+str(base.fields.get('ID'))+' localizado por Nombre; '+
                         'el ID de la columna CSV ('+str(check.get('csv_id'))+') es un consecutivo de fila')
            if check['state'] in ('no_coincide', 'ambiguo'):
                label = 'no_verificado'
                issue = (issue+'; ' if issue else '') + 'Discrepancia MAC con inventario: '+check['detail']
            elif check['state'] in ('sin_registro','incompleto'):
                self.warnings.append(check['detail'] + '. Cotejo incompleto, revisar antes de liberar a almacén.')
        except Interrupted as exc:
            issue, label = str(exc), 'no_verificado'
        except NoVerification as exc:
            issue, label = str(exc), 'no_verificado'
        except Exception as exc:
            issue, label = str(exc), 'fallido'
            self.log('SESIÓN INTERRUMPIDA: '+type(exc).__name__+': '+str(exc))
        finally:
            try: self.ble.disconnect()
            except Exception as exc: self.log('AVISO BLE: '+str(exc))
            initial = self.identity_status or self.latest
            health = dict(getattr(self.serial, 'health', {}) or {})
            quality = communicate(health)
            warnings = build_warnings(health, self.warnings)
            check = compare_inventory(self.inventory_records,
                initial.fields.get('ID','') if initial else '',
                initial.fields.get('MAC','') if initial else '', selected_r1,
                initial.fields.get('MACR','') if initial else '', selected_r2)
            # Aunque una falla interrumpa antes de llegar al cotejo, no presentarla como correcta.
            if label == 'aprobado' and check['state'] in ('no_coincide','ambiguo'):
                label = 'no_verificado'
                issue = 'La MAC no coincide con inventario. '+check['detail']
            if label == 'aprobado' and quality['state'] == 'no_verificable':
                label = 'no_verificado'
                issue = 'Tramas parciales/reintentos/errores ACK impiden certificación serial'
            self.report = {
                'report_schema':'tqt-station/0.6.3',
                'date':datetime.now().astimezone().isoformat(timespec='milliseconds'),
                'card':self.ready_name, 'serial_port':port,
                'firmware':initial.fields.get('VER') if initial else None,
                'hardware':initial.fields.get('HW') if initial else None,
                'card_id':initial.fields.get('ID') if initial else None,
                'r1_ble_address':selected_r1, 'r2_ble_address':selected_r2,
                'reported_mac':initial.fields.get('MAC') if initial else None,
                'reported_mac_r2':initial.fields.get('MACR') if initial else None,
                'inventory_source':self.inventory_source or None,
                'inventory_mac':(check.get('record') or {}).get('mac_r1'),
                'inventory_check':check,
                'mac_comparison':self.mac_comparison, 'result':label, 'issue':issue,
                'ending_position':self.latest.position if self.latest else None,
                'steps':[asdict(s) for s in self.steps], 'serial_health':health,
                'communication_quality':quality,
                'serial_timing':{'ack_delay_ms':round(getattr(self.serial,'ack_delay_s',0.18)*1000),
                                 'status_quiet_ms':0, # compatibilidad de esquema: 0 ms EXTRA
                                 'command_quiet_ms':round(getattr(self.serial,'command_quiet_s',0.3)*1000)},
                'warnings':warnings,
            }
            path = self._log_path
            if path:
                json_path, html_path = path.with_suffix('.json'), path.with_suffix('.html')
                try:
                    # Formato portable para consumo futuro por API de inventario web.
                    json_path.write_text(json.dumps(self.report, indent=2, ensure_ascii=False),encoding='utf-8')
                    html_path.write_text(report_html(self.report), encoding='utf-8')
                    self.report_files = {'json':str(json_path.absolute()),
                                         'html':str(html_path.absolute()), 'log':str(path.absolute())}
                    try: append_history(self.output_dir, self.report, json_path.name, html_path.name)
                    except Exception as exc: self.log('ADVERTENCIA: historial CSV no guardado: '+str(exc))
                    self.log('RESULTADO '+label.upper()+(' (CON AVISOS)' if warnings else '')+' | '+str(json_path.absolute()))
                    self.log('INFORME HTML | '+str(html_path.absolute()))
                    if warnings:
                        self.log('ADVERTENCIAS: '+str(len(warnings))+' · '+ ' | '.join(warnings))
                    self.ui('report',str(html_path.absolute()), str(json_path.absolute()), len(warnings),
                            quality['state'], check['state'])
                except Exception as exc:
                    self.log('ERROR al generar informe (conservar LOG): '+str(exc))
                    label = 'no_verificado'
                    issue = (issue+'; ' if issue else '') + 'No se generó el informe: '+str(exc)
                    self.report['result'], self.report['issue'] = label, issue
            with self._log_lock:
                if self._log_file: self._log_file.close()
                self._log_file = None
            self.running = False
            self.ui('done',label,issue)
