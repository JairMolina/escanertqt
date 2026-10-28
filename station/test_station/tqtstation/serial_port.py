"""Serial TQT: RX continuo, ACK prioritario y comandos sin colisiones con reportes."""
from __future__ import annotations
import re
import threading
import time


class SerialLink:
    def __init__(self, on_line, on_info):
        self.on_line, self.on_info = on_line, on_info
        self._serial = None
        self._running = threading.Event()
        self._writer = threading.Lock()
        self._thread = None
        self.port_name = ''
        self._ack_attempts = {}
        self._ack_warnings = 0
        self._ack_idle = threading.Event()
        self._ack_idle.set()
        self.ack_delay_s = 0.18
        # Dejar terminar el siguiente reporte espontaneo de R1 antes de mandar otra orden.
        self.command_quiet_s = 0.30
        # Sin retraso EXTRA para Status: firmware 4.3 ya emite RX limpio.
        # Los comandos conservan una guarda mínima compartida de 300 ms
        # y una barrera de S29 para no solapar Status con ON/OFF.
        self._last_command_tx = 0.0
        # Barrera: una consulta Status pendiente debe producir un S29 completo
        # antes de iniciar una orden posterior. Evita Status y OFF consecutivos.
        self._pending_status = threading.Event()
        self._last_rx = 0.0
        self._last_ack = 0.0
        self._frames = 0
        self._partial_warnings = 0
        self._corrupt_frames = 0
        self._ack_errors = 0

    @staticmethod
    def ports():
        from serial.tools.list_ports import comports
        return [p.device for p in comports()]

    @property
    def connected(self):
        return bool(self._serial and self._serial.is_open)

    def connect(self, port: str, baudrate: int = 57600):
        if self.connected:
            raise RuntimeError('Puerto ya conectado')
        import serial
        self._serial = serial.Serial(port, baudrate=baudrate, bytesize=8, parity='N', stopbits=1,
                                     timeout=0.08, write_timeout=1)
        self.port_name = port
        self.reset_diagnostics()
        self._ack_idle.set()
        self._pending_status.clear()
        self._last_rx = self._last_ack = self._last_command_tx = 0.0
        self._running.set()
        self._thread = threading.Thread(target=self._read, daemon=True, name='TQT serial RX')
        self._thread.start()

    @property
    def health(self):
        return {'frames': self._frames, 'retries': self._ack_warnings,
                'partial_warnings': self._partial_warnings,
                'corrupt_frames': self._corrupt_frames, 'ack_errors': self._ack_errors}

    def reset_diagnostics(self):
        self._ack_attempts.clear()
        self._ack_warnings = 0
        self._partial_warnings = 0
        self._corrupt_frames = 0
        self._ack_errors = 0
        self._frames = 0

    def _wait_command_window(self, timeout=8.0):
        """Pausar solo para ACK/RX y guarda general: sin pausa exclusiva de Status."""
        quiet_s = self.command_quiet_s
        end = time.monotonic() + timeout
        while self.connected and self._running.is_set() and time.monotonic() < end:
            if self._ack_idle.is_set() and not self._pending_status.is_set():
                now = time.monotonic()
                if now - max(self._last_rx, self._last_ack, self._last_command_tx) >= quiet_s:
                    return
            time.sleep(.015)
        if not self.connected:
            raise RuntimeError('Puerto COM desconectado mientras esperaba ventana de TX')
        if self._pending_status.is_set():
            raise TimeoutError('Sigue pendiente S29 posterior a $SMSG=Status; no se enviará otra orden para evitar solapamiento.')
        raise TimeoutError('COM ocupado con reportes/ACK; no se envió otro comando. Revisa la consola RX.')

    def send(self, data: bytes):
        if not self.connected:
            raise RuntimeError('Conecta primero el puerto COM')
        # ACK manual para diagnóstico: prioritario, sin esperar la ventana normal
        # de comandos (la R1 puede estar aguardando precisamente esta respuesta).
        if data == b'$OK\r\n':
            self._write(data)
            self._last_ack = time.monotonic()
            return
        # Los comandos normales deben aguardar el fin de las tramas pendientes.
        # Status y demás comandos comparten SOLO la guarda básica del canal.
        # _pending_status sigue evitando una orden posterior sin un S29 nuevo.
        self._wait_command_window()
        self._write(data)

    def _write(self, data: bytes, log: bool = True):
        with self._writer:
            is_status = data == b'$SMSG=Status\r\n'
            if is_status:
                self._pending_status.set()
            try:
                count = self._serial.write(data)
                self._serial.flush()
            except Exception:
                if is_status: self._pending_status.clear()
                raise
        if data != b'$OK\r\n':
            self._last_command_tx = time.monotonic()
        if count != len(data):
            if data == b'$SMSG=Status\r\n': self._pending_status.clear()
            raise IOError(f'Escritura serial incompleta: {count}/{len(data)} bytes')
        if log:
            label = data.decode('utf-8', 'replace').replace('\r', '[CR]').replace('\n', '[LF]')
            self.on_info('TX SERIAL: ' + label)

    def _read(self):
        buf = bytearray()
        last_fragment = 0.0
        reported_fragment = False
        while self._running.is_set():
            try:
                serial = self._serial
                if serial is None:
                    break
                data = serial.read(min(serial.in_waiting or 1, 512))
                if data:
                    now = time.monotonic()
                    self._last_rx = now
                    last_fragment = now
                    for b in data:
                        if b == 10:
                            raw_line = bytes(buf)
                            line = raw_line.decode('utf-8', 'replace').rstrip('\r')
                            buf.clear()
                            reported_fragment = False
                            if line:
                                self._frames += 1
                                has_header = line.startswith('AT$POST=1,0,"')
                                # v1.4.73: el $OK sale ANTES de registrar la línea. Registrar (archivo + cola de eventos
                                # en SQLite sobre la SD de la Raspberry) podía tardar 1–2 s; la R1 reintentaba, se le
                                # acumulaba la cola de mensajes y las tramas llegaban decenas de segundos tarde.
                                ack_ok = None
                                if has_header:
                                    self._ack_idle.clear()
                                    try:
                                        time.sleep(self.ack_delay_s)
                                        self._write(b'$OK\r\n', log=False)
                                        self._last_ack = time.monotonic()
                                        ack_ok = True
                                    except Exception as exc:
                                        self._ack_errors += 1
                                        ack_ok = exc
                                    finally:
                                        self._ack_idle.set()
                                self.on_info('RX SERIAL: ' + line)
                                if ack_ok is True:
                                    self.on_info('TX SERIAL: $OK[CR][LF]')
                                elif ack_ok is not None:
                                    self.on_info('ERROR ACK: ' + str(ack_ok))
                                damaged = ('\ufffd' in line or
                                           ('AT$POST' in line and not has_header))
                                if damaged:
                                    self._corrupt_frames += 1
                                    self.on_info('AVISO RX: caracteres ilegibles o cabecera dañada; no se utilizará como evidencia')
                                    self.on_info('RX HEX CORRUPTA: ' + raw_line.hex(' ').upper())
                                partial = False
                                if has_header:
                                    self._observe_retry(line)
                                    if '"S29' in line and (not line.endswith('"') or line.count('|') < 29):
                                        partial = True
                                        self._partial_warnings += 1
                                        self.on_info('ERROR RX: S29 incompleto, longitud=' + str(len(line)) +
                                                     '; campos=' + str(line.count('|')) + '/29; no sirve para validación')
                                    # (el ACK ya se envió arriba, también para tramas dañadas: aceptar ACK no aprueba evidencia)
                                if has_header and not damaged and not partial and line.endswith('"'):
                                    # S29 completo: liberar la consulta pendiente.
                                    # Puede ser una trama espontánea; el origen exacto no
                                    # se distingue sin correlación en el protocolo.
                                    if line.startswith('AT$POST=1,0,"S29|'):
                                        self._pending_status.clear()
                                    self.on_line(line)
                        elif len(buf) < 8192:
                            buf.append(b)
                        else:
                            self._partial_warnings += 1
                            self.on_info('ERROR RX: longitud de trama >8192 bytes, descartada')
                            buf.clear()
                elif buf and time.monotonic() - last_fragment > 3.0:
                    if not reported_fragment:
                        reported_fragment = True
                        self._partial_warnings += 1
                        tail = buf.decode('utf-8', 'replace')[-140:]
                        self.on_info(f'AVISO RX: trama incompleta ({len(buf)} bytes, sin LF desde hace 3 s): {tail!r}')
                    # Evitar contaminación de la siguiente trama después de un silencio largo.
                    if time.monotonic() - last_fragment > 6.0:
                        self.on_info('ERROR RX: descartando fragmento sin fin de línea; se conserva en log diagnóstico')
                        buf.clear()
                        reported_fragment = False
            except Exception as exc:
                if self._running.is_set():
                    self.on_info('ERROR SERIAL: ' + str(exc))
                break
        self._running.clear()
        self._ack_idle.set()
        self._pending_status.clear()
        self.on_info('Puerto serial detenido')

    def _observe_retry(self, line: str):
        hit = re.search(r'Mensaje[:;](\d+)\.(\d+)', line)
        if not hit:
            return
        seq, attempt = map(int, hit.groups())
        if seq <= 0:
            return
        last = self._ack_attempts.get(seq)
        if attempt > 0 and (last is None or attempt > last):
            self._ack_warnings += 1
            self.on_info(f'AVISO ACK: reintento {attempt} del mensaje {seq}; se debe comprobar recepción real en R1')
        self._ack_attempts[seq] = max(last or 0, attempt)
        if len(self._ack_attempts) > 100:
            for key in list(self._ack_attempts)[:50]:
                self._ack_attempts.pop(key, None)

    def disconnect(self):
        self._running.clear()
        self._pending_status.clear()
        port = self._serial
        self._serial = None
        if port is not None:
            try:
                port.close()
            except Exception:
                pass
        self._ack_idle.set()
