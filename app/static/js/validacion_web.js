/* v1.4.0: motor web de Validación TQT (window.TQTValWeb), port fiel de
 * station/test_station/tqtstation/{protocol,serial_port,ble,engine,reporting}.py (v0.6.3).
 * Mismas 14 etapas, 57600 8N1, ACK $OK\r\n a 180 ms de cada trama AT$POST, guardia de canal
 * 300 ms, barrera S29 tras $SMSG=Status, ventana de repetición 5 s y comandos BLE PPON/POFF
 * (ASCII sin terminador) por el servicio/característica del BLE Tester.
 * Límite de confianza: el servidor valida estructura, evidencia S29 cruda e inventario, pero
 * no observa el hardware; el informe lo arma este JS y no es una atestación criptográfica.
 * Web Bluetooth no expone la MAC: nunca se usa device.id como MAC. */
(function () {
    'use strict';
    const BAUD = 57600;
    const SERVICE_UUID = '4fafc201-1fb5-459e-8fcc-c5c9c331914b';
    const CHAR_UUID = 'beb5483e-36e1-4688-b7f5-ea07361b26a8';
    // Servicio OTA de R2 v4.x: su característica info declara la MAC del propio ESP32 (opcional).
    const OTA_SERVICE = 'd45a0001-6a76-4e41-9f38-a7043f0ec069';
    const OTA_INFO = 'd45a0002-6a76-4e41-9f38-a7043f0ec069';
    const API = '/api/validacion/tqt';
    const CONTEXTO = 'banco de pruebas · modo seguro';
    const FIELDS = ['BLK', 'OUT1', 'OUT2', 'OUT3', 'INT1', 'INT2', 'INT3', 'EST1', 'EST2', 'EST3',
        'MOTOR', 'SEN_MOT', 'TIEMPO', 'DBG', 'VIVA', 'TQT', 'ON', 'OFF', 'PB', 'err',
        'RESET', 'VER', 'HW', 'MOV', 'Mensaje', 'IDR', 'MACR', 'ID', 'MAC'];
    const STEP_NAMES = [
        'Restablecer e identificar R1', 'Verificar estado inicial del motor',
        'R1 serial · Primer movimiento', 'R1 serial · Repetición sin movimiento',
        'R1 serial · Movimiento inverso', 'R1 serial · Repetición inversa',
        'Localizar y conectar R1 BLE', 'R1 BLE · Primer movimiento',
        'R1 BLE · Repetición sin movimiento', 'R1 BLE · Movimiento inverso',
        'R1 BLE · Repetición inversa', 'Desconectar R1 y conectar R2 BLE automáticamente',
        'R2 BLE · Primer movimiento', 'R2 BLE · Movimiento inverso',
    ];
    const ACTIONS = {
        POFF: '$SMSG=OFF\r\n', PPON: '$SMSG=ON\r\n', RESET_FACTORY: '$SMSG=Reset_44\r\n',
        RESET: '$SMSG=Reset\r\n', RESET_BLE: '$SMSG=Reset_BLE\r\n', STATUS: '$SMSG=Status\r\n',
        MOTOR_STATUS: '$SMSG=Status_Motor\r\n', MAP_QUERY: '$SMSG=MAP?\r\n',
        MAP_M1_0: '$SMSG=MAP_M1:0\r\n', MAP_M1_1: '$SMSG=MAP_M1:1\r\n',
        MAP_M2_0: '$SMSG=MAP_M2:0\r\n', MAP_M2_1: '$SMSG=MAP_M2:1\r\n',
    };
    const OK = '$OK\r\n';
    const STATUS_TX = ACTIONS.STATUS;

    // ------------------------------------------------------------ protocolo (protocol.py)
    const READY_RE = /([A-Za-z0-9_\-]+)\s*-\s*Lista para usarse\b/i;
    const POST_RE = /AT\$POST=1,0,"([^"]*)"/;
    const normalizeMac = v => String(v || '').toUpperCase().replace(/[^0-9A-F]/g, '');
    const norm = v => String(v || '').toUpperCase().replace(/[^A-Z0-9]/g, '');
    function readReady(line) { const m = READY_RE.exec(line); return m ? m[1] : null; }
    function parseStatus(line) {
        const found = POST_RE.exec(line);
        if (!found) return null;
        const body = found[1];
        const m = /^S29([^\w\s])/.exec(body);
        if (!m) return null;
        const entries = body.slice(4).split(m[1]);
        if (entries.length !== 29) return null;
        const fields = {};
        for (let i = 0; i < 29; i++) {
            const expected = FIELDS[i], entry = entries[i];
            if (!entry.startsWith(expected) || entry.length <= expected.length) return null;
            const v = entry.slice(expected.length);
            if (!':;=,'.includes(v[0])) return null;
            fields[expected] = v.slice(1);
        }
        return { fields, raw: line };
    }
    function num(st, name) {
        const v = st && st.fields[name];
        if (v === undefined || v === null || !/^\s*[-+]?\d+\s*$/.test(v)) return null;
        return parseInt(v, 10);
    }
    function position(st) {
        const c = num(st, 'ON'), o = num(st, 'OFF');
        if (c === 1 && o === 0) return 'cerrado';
        if (c === 0 && o === 1) return 'abierto';
        if (c === 1 && o === 1) return 'conflicto';
        return 'indeterminado';
    }
    function serialAction(cmd) {
        if (!ACTIONS[cmd]) throw new Error('Comando serial no autorizado');
        return ACTIONS[cmd];
    }

    class TestFailure extends Error {}
    class NoVerification extends Error {}
    class Interrupted extends Error {}

    const ahora = () => (typeof performance !== 'undefined' ? performance.now() : Date.now());
    const dormir = ms => new Promise(r => setTimeout(r, ms));
    const isoMs = () => {
        const d = new Date(), off = -d.getTimezoneOffset(), s = off >= 0 ? '+' : '-';
        const p = (n, l = 2) => String(Math.abs(n)).padStart(l, '0');
        return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate()) + 'T' + p(d.getHours()) + ':' +
            p(d.getMinutes()) + ':' + p(d.getSeconds()) + '.' + p(d.getMilliseconds(), 3) + s + p(Math.floor(Math.abs(off) / 60)) + ':' + p(Math.abs(off) % 60);
    };
    const hex = raw => Array.from(raw, b => b.toString(16).toUpperCase().padStart(2, '0')).join(' ');

    // ------------------------------------------------------------ enlace serial (serial_port.py)
    class SerialLink {
        constructor({ onLine, onInfo, cfg }) {
            this.onLine = onLine; this.onInfo = onInfo;
            this.ack_delay_ms = cfg.ackMs; this.command_quiet_ms = cfg.quietMs;
            this.cx = null; this.portName = '';
            this._ackAttempts = new Map();
            this._ackIdle = true; this._pendingStatus = false;
            this._lastRx = this._lastAck = this._lastCommandTx = 0;
            this._lastFragment = 0; this._reportedFragment = false;
            this._cola = Promise.resolve();
            this.resetDiagnostics();
            this.tramador = (window.TQTSerial ? window.TQTSerial.crearTramador : crearTramadorLocal)({
                onLinea: (line, raw) => { this._cola = this._cola.then(() => this._procesar(line, raw)).catch(e => this.onInfo('ERROR RX: ' + e.message)); },
                onDesborde: () => { this._partial++; this.onInfo('ERROR RX: longitud de trama >8192 bytes, descartada'); },
            });
        }
        get connected() { return !!(this.cx && this.cx.activo()); }
        attach(cx, name) {
            this.cx = cx; this.portName = name || cx.descripcion || 'Web Serial';
            this.resetDiagnostics();
            this._ackIdle = true; this._pendingStatus = false;
            this._lastRx = this._lastAck = this._lastCommandTx = 0;
            clearInterval(this._vigia);
            this._vigia = setInterval(() => this._vigilarFragmento(), 500);
        }
        detach() {
            clearInterval(this._vigia);
            this.cx = null; this._ackIdle = true; this._pendingStatus = false;
            this.tramador.vaciar();
        }
        feed(bytes) {
            const now = ahora();
            this._lastRx = now; this._lastFragment = now;
            this.tramador.empujar(bytes);
        }
        get health() {
            return { frames: this._frames, retries: this._ackWarnings, partial_warnings: this._partial,
                corrupt_frames: this._corrupt, ack_errors: this._ackErrors };
        }
        resetDiagnostics() {
            this._ackAttempts = new Map();
            this._ackWarnings = 0; this._partial = 0; this._corrupt = 0; this._ackErrors = 0; this._frames = 0;
        }
        clearPendingStatus() { this._pendingStatus = false; }
        async _waitCommandWindow(timeout = 8000) {
            const end = ahora() + timeout;
            while (this.connected && ahora() < end) {
                if (this._ackIdle && !this._pendingStatus) {
                    if (ahora() - Math.max(this._lastRx, this._lastAck, this._lastCommandTx) >= this.command_quiet_ms) return;
                }
                await dormir(15);
            }
            if (!this.connected) throw new Error('Puerto COM desconectado mientras esperaba ventana de TX');
            if (this._pendingStatus) throw new Error('Sigue pendiente S29 posterior a $SMSG=Status; no se enviará otra orden para evitar solapamiento.');
            throw new Error('COM ocupado con reportes/ACK; no se envió otro comando. Revisa la consola RX.');
        }
        async send(data) {
            if (!this.connected) throw new Error('Conecta primero el puerto COM');
            if (data === OK) { await this._write(data); this._lastAck = ahora(); return; }
            await this._waitCommandWindow();
            await this._write(data);
        }
        async _write(data) {
            const isStatus = data === STATUS_TX;
            if (isStatus) this._pendingStatus = true;
            let count;
            try { count = await this.cx.escribir(new TextEncoder().encode(data)); }
            catch (e) { if (isStatus) this._pendingStatus = false; throw e; }
            if (data !== OK) this._lastCommandTx = ahora();
            if (count !== data.length) {
                if (isStatus) this._pendingStatus = false;
                throw new Error('Escritura serial incompleta: ' + count + '/' + data.length + ' bytes');
            }
            this.onInfo('TX SERIAL: ' + data.replace(/\r/g, '[CR]').replace(/\n/g, '[LF]'));
        }
        async _procesar(line, raw) {
            if (!line) return;
            this._frames++;
            this.onInfo('RX SERIAL: ' + line);
            const hasHeader = line.startsWith('AT$POST=1,0,"');
            const damaged = line.includes('�') || (line.includes('AT$POST') && !hasHeader);
            if (damaged) {
                this._corrupt++;
                this.onInfo('AVISO RX: caracteres ilegibles o cabecera dañada; no se utilizará como evidencia');
                this.onInfo('RX HEX CORRUPTA: ' + hex(raw || []));
            }
            let partial = false;
            if (hasHeader) {
                this._observeRetry(line);
                if (line.includes('"S29') && (!line.endsWith('"') || line.split('|').length - 1 < 29)) {
                    partial = true; this._partial++;
                    this.onInfo('ERROR RX: S29 incompleto, longitud=' + line.length + '; campos=' + (line.split('|').length - 1) + '/29; no sirve para validación');
                }
                // ACK de recepción aun con trama dañada; aceptar ACK no aprueba evidencia.
                this._ackIdle = false;
                try {
                    await dormir(this.ack_delay_ms);
                    await this._write(OK);
                    this._lastAck = ahora();
                } catch (e) {
                    this._ackErrors++;
                    this.onInfo('ERROR ACK: ' + (e && e.message || e));
                } finally { this._ackIdle = true; }
            }
            if (hasHeader && !damaged && !partial && line.endsWith('"')) {
                if (line.startsWith('AT$POST=1,0,"S29|')) this._pendingStatus = false;
                this.onLine(line);
            }
        }
        _vigilarFragmento() {
            if (!this.tramador.pendientes()) { this._reportedFragment = false; return; }
            const quiet = ahora() - this._lastFragment;
            if (quiet > 3000 && !this._reportedFragment) {
                this._reportedFragment = true; this._partial++;
                this.onInfo('AVISO RX: trama incompleta (' + this.tramador.pendientes() + ' bytes, sin LF desde hace 3 s): ' + JSON.stringify(this.tramador.cola().slice(-140)));
            }
            if (quiet > 6000) {
                this.onInfo('ERROR RX: descartando fragmento sin fin de línea; se conserva en log diagnóstico');
                this.tramador.vaciar(); this._reportedFragment = false;
            }
        }
        _observeRetry(line) {
            const hit = /Mensaje[:;](\d+)\.(\d+)/.exec(line);
            if (!hit) return;
            const seq = +hit[1], attempt = +hit[2];
            if (seq <= 0) return;
            const last = this._ackAttempts.get(seq);
            if (attempt > 0 && (last === undefined || attempt > last)) {
                this._ackWarnings++;
                this.onInfo('AVISO ACK: reintento ' + attempt + ' del mensaje ' + seq + '; se debe comprobar recepción real en R1');
            }
            this._ackAttempts.set(seq, Math.max(last || 0, attempt));
            if (this._ackAttempts.size > 100) [...this._ackAttempts.keys()].slice(0, 50).forEach(k => this._ackAttempts.delete(k));
        }
    }
    function crearTramadorLocal({ onLinea, onDesborde }) {
        let buf = [];
        const dec = new TextDecoder('utf-8');
        return {
            empujar(bytes) {
                for (const b of bytes) {
                    if (b === 10) { const raw = Uint8Array.from(buf); buf = []; let l = dec.decode(raw); if (l.endsWith('\r')) l = l.slice(0, -1); onLinea(l, raw); }
                    else if (buf.length < 8192) buf.push(b); else { buf = []; onDesborde && onDesborde(); }
                }
            },
            pendientes: () => buf.length, cola: () => dec.decode(Uint8Array.from(buf)), vaciar() { buf = []; },
        };
    }

    // ------------------------------------------------------------ BLE (ble.py sobre Web Bluetooth)
    async function acotado(promesa, ms, texto) {
        let t;
        try { return await Promise.race([promesa, new Promise((_, rej) => { t = setTimeout(() => rej(new Error(texto || 'Tiempo agotado en Bluetooth')), ms); })]); }
        finally { clearTimeout(t); }
    }
    class BleLink {
        constructor(log, onCambio) {
            this.log = log; this.onCambio = onCambio || (() => {});
            this.device = null; this.char = null; this.dispositivo = null; this.nombre = '';
            this._intencional = false;
            this._alPerder = () => {
                if (this._intencional) return;
                this.device = null; this.char = null;
                this.log('AVISO BLE: enlace perdido sin solicitud de desconexión');
                this.onCambio('error', 'Enlace BLE perdido');
            };
        }
        get address() { return this.device ? this.nombre : ''; }
        get connected() { return !!(this.device && this.device.gatt && this.device.gatt.connected && this.char); }
        /* Busca un dispositivo ya autorizado con nombre exacto; si no existe, pide gesto del usuario. */
        async localizar({ nombre, dispositivo, gesto }) {
            if (!navigator.bluetooth) throw new Error('Este navegador no soporta Web Bluetooth.');
            let previos = [];
            try { previos = navigator.bluetooth.getDevices ? await navigator.bluetooth.getDevices() : []; } catch (_) {}
            const iguales = previos.filter(d => (d.name || '').toUpperCase() === String(nombre).toUpperCase());
            if (iguales.length > 1) throw new NoVerification(dispositivo + ' BLE ambigua: hay ' + iguales.length + ' dispositivos autorizados con el nombre ' + nombre);
            if (iguales.length === 1) { this.log('BLE: reutilizando ' + dispositivo + ' autorizado previamente (' + nombre + ')'); return iguales[0]; }
            this.log('BLE: ' + dispositivo + ' ' + nombre + ' sin permiso previo; se requiere gesto del operador para el selector nativo');
            const autorizar = () => navigator.bluetooth.requestDevice({ filters: [{ name: nombre }], optionalServices: [SERVICE_UUID, OTA_SERVICE] });
            const device = await gesto({ dispositivo, nombre, autorizar });
            if (!device) throw new Interrupted('No se autorizó el dispositivo Bluetooth ' + dispositivo);
            if ((device.name || '').toUpperCase() !== String(nombre).toUpperCase())
                throw new NoVerification('Se eligió «' + (device.name || '?') + '», se esperaba ' + nombre + '. No se enviaron comandos.');
            return device;
        }
        async connect(device, dispositivo) {
            if (this.device) await this.disconnect(true);
            this.char = null; this.onCambio('conectando', 'Conectando ' + dispositivo, dispositivo);
            let server;
            try {
                try { server = await acotado(device.gatt.connect(), 15000); }
                catch (e) {
                    // Dispositivo recordado sin anuncio reciente: escuchar anuncios y reintentar una vez.
                    if (!device.watchAdvertisements) throw e;
                    const visto = new Promise(r => device.addEventListener('advertisementreceived', r, { once: true }));
                    await device.watchAdvertisements().catch(() => {});
                    await acotado(visto, 7000, 'BLE ' + (device.name || '') + ' no anuncia; acércala o reiníciala').catch(err => { throw err; });
                    server = await acotado(device.gatt.connect(), 15000);
                }
                const service = await acotado(server.getPrimaryService(SERVICE_UUID), 10000).catch(() => null);
                if (!service) throw new Error('Servicio TQT del BLE Tester no encontrado');
                const ch = await acotado(service.getCharacteristic(CHAR_UUID), 10000).catch(() => null);
                if (!ch) throw new Error('Característica TQT no encontrada');
                const p = ch.properties || {};
                if (!(p.write || p.writeWithoutResponse)) throw new Error('Característica BLE no escribible');
                if (p.notify || p.indicate) {
                    try {
                        ch.addEventListener('characteristicvaluechanged', ev => this.log('RX BLE: ' + new TextDecoder().decode(ev.target.value).trim()));
                        await acotado(ch.startNotifications(), 10000);
                    } catch (e) { this.log('BLE sin notificaciones: ' + e.message); }
                }
                device.addEventListener('gattserverdisconnected', this._alPerder);
                this.device = device; this.char = ch; this.dispositivo = dispositivo; this.nombre = device.name || '';
                this.log('BLE conectado: ' + this.nombre + ' (' + dispositivo + ')');
                this.onCambio('ok', this.nombre, dispositivo);
            } catch (e) {
                this._intencional = true;
                try { device.gatt.connected && device.gatt.disconnect(); } catch (_) {}
                this._intencional = false;
                this.onCambio('error', e.message, null);
                throw e;
            }
        }
        async send(command) {
            if (command !== 'POFF' && command !== 'PPON') throw new Error('Comando BLE no autorizado');
            if (!this.connected) throw new Error('No existe una conexión BLE activa');
            const ack = !!this.char.properties.write;
            const data = new TextEncoder().encode(command);
            await acotado(ack ? this.char.writeValueWithResponse(data) : this.char.writeValueWithoutResponse(data), 15000);
            this.log('TX BLE: ' + command + ' (GATT ' + (ack ? 'con respuesta' : 'sin respuesta') + '; no certifica movimiento)');
        }
        /* MAC declarada por la propia R2 en su info OTA (si el firmware la expone). No es la MAC observada. */
        async macDeclarada() {
            try {
                const svc = await acotado(this.device.gatt.getPrimaryService(OTA_SERVICE), 8000);
                const ch = await acotado(svc.getCharacteristic(OTA_INFO), 8000);
                const info = JSON.parse(new TextDecoder().decode(await acotado(ch.readValue(), 8000)));
                return info && info.mac ? String(info.mac) : null;
            } catch (_) { return null; }
        }
        async disconnect(silencioso) {
            const d = this.device;
            this.device = null; this.char = null; this.dispositivo = null; this.nombre = '';
            if (d) {
                d.removeEventListener('gattserverdisconnected', this._alPerder);
                this._intencional = true;
                try { d.gatt.connected && d.gatt.disconnect(); } catch (_) {}
                this._intencional = false;
            }
            if (!silencioso) this.log('BLE desconectado');
            this.onCambio('off', '', null);
        }
    }

    // ------------------------------------------------------------ reporting.py (calidad)
    function communicate(h) {
        const total = +h.frames || 0, bad = +h.corrupt_frames || 0, partial = +h.partial_warnings || 0,
            retries = +h.retries || 0, ack = +h.ack_errors || 0;
        const state = (partial || retries || ack) ? 'no_verificable' : bad ? 'advertencias' : 'limpia';
        return { state, received_lines: total, corrupt_lines: bad, partial_warnings: partial, retries, ack_errors: ack,
            corrupt_percent: total ? Math.round(1000 * bad / total) / 10 : 0.0,
            note: 'Las líneas dañadas no se usan como evidencia funcional. No se ha demostrado su causa física.' };
    }
    function buildWarnings(h, prior) {
        const notes = [...new Set(prior)];
        const bad = +h.corrupt_frames || 0, total = +h.frames || 0;
        if (bad) notes.push('Comunicación: ' + bad + ' líneas RX con cabecera/bytes ilegibles de ' + total + ' (' + (total ? Math.round(1000 * bad / total) / 10 : 0) + '%). Excluidas como evidencia; revisar canal UART y trazas HEX.');
        if (h.retries) notes.push('Comunicación: ' + h.retries + ' reintentos de ACK observados.');
        if (h.partial_warnings) notes.push('Comunicación: ' + h.partial_warnings + ' tramas/fragments incompletos.');
        if (h.ack_errors) notes.push('Comunicación: ' + h.ack_errors + ' errores de escritura de ACK.');
        return notes;
    }

    // ------------------------------------------------------------ motor (engine.py)
    class Motor {
        constructor({ serial, ble, ui, cfg, hooks }) {
            this.serial = serial; this.ble = ble; this.ui = ui; this.cfg = cfg; this.hooks = hooks;
            this.observations = []; this.latest = null; this._latestAt = 0; this.ready_name = '';
            this.steps = STEP_NAMES.map(name => ({ name, state: 'pendiente', detail: '', started_at: '', finished_at: '', duration_s: null }));
            this.cancelled = false; this.running = false; this.report = {};
            this.mac_comparison = 'pendiente'; this.warnings = []; this._overcurrent = false;
            this.identity_status = null; this.expected = null; this.identity_change = null;
            this.repeat_verify_ms = cfg.repeatVerifyMs;
            this.logText = ''; this._waiters = new Set(); this.cancelReason = '';
            this.ble_identity = { r1: null, r2: null };
        }
        log(message) { const row = isoMs() + ' | ' + message; this.logText += row + '\n'; this.ui('log', row); }
        _notify() { const w = this._waiters; this._waiters = new Set(); w.forEach(r => r()); }
        _esperar(ms) { return new Promise(r => { const t = setTimeout(() => { this._waiters.delete(f); r(); }, ms); const f = () => { clearTimeout(t); r(); }; this._waiters.add(f); }); }
        on_line(line) {
            const status = parseStatus(line), name = readReady(line);
            let motor = null;
            if (line.includes('El perno esta Bloqueado')) motor = 'cerrado';
            else if (line.includes('El perno esta Desbloqueado')) motor = 'abierto';
            else if (line.includes('Ambos sensores activados')) motor = 'conflicto';
            else if (line.includes('El perno esta en MOVIMIENTO')) motor = 'indeterminado';
            if (name) { this.ready_name = name; this.observations.push(['ready', name]); }
            if (motor) this.observations.push(['motor_status', motor]);
            const valid = status && (!this.running || this.ready_name);
            if (valid) { this.latest = status; this._latestAt = ahora(); this.observations.push(['status', status]); }
            // v1.4.0 (punto 12): S29 previo a Reset_44 solo sirve para identificar sin efectos.
            else if (status && this.running) this.observations.push(['pre_status', status]);
            this._notify();
            if (valid) {
                this.ui('status', { fields: status.fields, raw: status.raw });
                if (this.running && num(status, 'err') === 15 && !this._overcurrent) {
                    this._overcurrent = true;
                    const w = 'Protección / consumo: R1 notificó err=15. Revisar el motor y su corriente.';
                    this.warnings.push(w); this.log('ADVERTENCIA: ' + w); this.ui('warning', w);
                }
            }
            if (name) this.ui('card', name);
        }
        _checkpoint() { return this.observations.length; }
        _checkCancel(msg) { if (this.cancelled) throw new Interrupted(this.cancelReason || msg || 'Prueba detenida por el usuario'); }
        async _wait(start, pred, seconds, what = 'respuesta') {
            const until = ahora() + seconds * 1000;
            let nextNotice = ahora() + 5000;
            for (;;) {
                this._checkCancel('Prueba detenida por el usuario');
                for (const [tag, val] of this.observations.slice(start)) if (pred(tag, val)) return val;
                const rest = until - ahora();
                if (rest <= 0) throw new NoVerification('No llegó ' + what + ' completo en ' + seconds + ' s (diagnóstico serial: ' + JSON.stringify(this.serial.health) + ')');
                await this._esperar(Math.min(rest, 200));
                if (ahora() >= nextNotice) { this.log('ESPERANDO: ' + what + '. No se enviará otro comando hasta recibir la trama requerida.'); nextNotice = ahora() + 5000; }
            }
        }
        async _initial_s29(start, timeout = 22) {
            this.log('Esperando S29 espontáneo posterior a Lista para usarse (sin enviar Status)…');
            return this._wait(start, tag => tag === 'status', timeout, 'S29 inicial después del reinicio');
        }
        async _fresh_status(timeout = 12, maxAge = 3000) {
            const cached = this.latest;
            if (cached && num(cached, 'TQT') === 0 && ahora() - this._latestAt <= maxAge) return cached;
            const start = this._checkpoint();
            await this._send(serialAction('STATUS'));
            return this._wait(start, (tag, v) => tag === 'status' && num(v, 'TQT') === 0, timeout);
        }
        // Guardia del agente (agent.py safe_send): no mover sin identidad/MAC de la tarjeta esperada.
        _guard() {
            const d = this.expected, v = this.latest ? this.latest.fields : {};
            if (!d || norm(v.MAC) !== norm(d.mac_r1) || norm(v.MACR) !== norm(d.mac_r2) || norm(this.ready_name) !== norm(d.nombre))
                throw new NoVerification('Identidad/MAC no coincide con la tarjeta seleccionada; movimiento bloqueado.');
        }
        async _send(data) {
            if (this.running && (data === ACTIONS.PPON || data === ACTIONS.POFF)) this._guard();
            await this.serial.send(data);
        }
        async _bleSend(cmd) { if (this.running) this._guard(); await this.ble.send(cmd); }
        async _step(idx, fn, title) {
            this._checkCancel('Cancelada');
            const step = this.steps[idx];
            if (title) step.name = title;
            step.state = 'ejecutando'; step.detail = '';
            const t0 = ahora(); step.started_at = isoMs();
            this.ui('step', idx, step.state, step.detail);
            this.log('PRUEBA: ' + step.name);
            try {
                const detail = (await fn()) || 'Validación completa';
                step.state = 'aprobado'; step.detail = detail;
            } catch (e) {
                const nv = e instanceof NoVerification || e instanceof Interrupted;
                step.state = nv ? 'no_verificado' : 'fallido'; step.detail = String(e && e.message || e);
                this.ui('step', idx, step.state, step.detail);
                this.log((nv ? 'NO VERIFICADO: ' : 'FALLO: ') + step.detail);
                throw e;
            } finally {
                step.finished_at = isoMs(); step.duration_s = Math.round(ahora() - t0) / 1000;
            }
            this.ui('step', idx, step.state, step.detail);
            this.log('APROBADO: ' + step.detail);
        }
        _require(v, msg) { if (!v) throw new TestFailure(msg); }
        _position(st) {
            const p = position(st);
            if (p !== 'cerrado' && p !== 'abierto') throw new TestFailure('Sensores de motor inconsistentes: ON=' + st.fields.ON + ' OFF=' + st.fields.OFF + '; detener movimientos');
            return p;
        }
        _nextCommand(p) {
            if (p === 'cerrado') return ['PPON', 'abierto'];
            if (p === 'abierto') return ['POFF', 'cerrado'];
            throw new TestFailure('No se puede mover motor con sensores inconsistentes');
        }
        async _await_motor(cursor, expected, prev, movement, origin, timeout = 31) {
            const needed = prev + (movement ? 1 : 0), until = ahora() + timeout * 1000;
            let lastPoll = ahora();
            while (ahora() < until) {
                this._checkCancel('Prueba detenida');
                for (const [kind, v] of this.observations.slice(cursor)) {
                    if (kind !== 'status') continue;
                    const err = num(v, 'err');
                    if (err === 3 || err === 4) throw new TestFailure('R1 informó error motor ' + v.fields.err);
                    if (position(v) === expected && num(v, 'MOV') === needed && num(v, 'PB') === origin && num(v, 'TQT') === 0) return v;
                    if (num(v, 'MOV') !== null && num(v, 'MOV') > needed) throw new TestFailure('MOV subió más de lo esperado: ' + num(v, 'MOV') + ' > ' + needed);
                }
                await this._esperar(200);
                if (ahora() - lastPoll >= 5000 && ahora() + 2000 < until) {
                    lastPoll = ahora();
                    try { await this._send(serialAction('STATUS')); } catch (e) { this.log('No se pudo consultar Status: ' + e.message); }
                }
            }
            throw new TestFailure('No llegó S29 final: ' + expected + ', MOV=' + needed + ', PB=' + origin + ', TQT=0');
        }
        async _await_repetition(cursor, expected, prev, origin, commandTime, timeout = 18) {
            const until = ahora() + timeout * 1000, eligibleAt = commandTime + this.repeat_verify_ms;
            let polled = false, pollCursor = null, lastIndex = cursor;
            while (ahora() < until) {
                this._checkCancel('Prueba detenida');
                const current = this.observations.slice(lastIndex);
                lastIndex = this.observations.length;
                for (let off = 0; off < current.length; off++) {
                    const [kind, v] = current[off];
                    if (kind !== 'status') continue;
                    const err = num(v, 'err');
                    if (err === 3 || err === 4) throw new TestFailure('R1 informó error motor ' + err + ' durante repetición');
                    const mov = num(v, 'MOV');
                    if (mov !== null && mov !== prev) throw new TestFailure('MOV cambió durante repetición ' + prev + '→' + mov);
                    const tqt = num(v, 'TQT');
                    if (position(v) !== expected || tqt === 1 || tqt === 3 || tqt === 5)
                        throw new TestFailure('Se detectó estado/movimiento inesperado durante repetición: ON=' + v.fields.ON + ', OFF=' + v.fields.OFF + ', TQT=' + v.fields.TQT);
                    const index = lastIndex - current.length + off;
                    if (polled && pollCursor !== null && index >= pollCursor && ahora() >= eligibleAt && tqt === 0 && num(v, 'PB') === origin && mov === prev) return v;
                }
                if (!polled && ahora() >= eligibleAt) {
                    pollCursor = this._checkpoint();
                    await this._send(serialAction('STATUS'));
                    polled = true;
                    continue;
                }
                await this._esperar(80);
            }
            throw new NoVerification('No se verificó la repetición ' + expected + ' sin movimiento adicional (MOV=' + prev + ', ventana=' + (this.repeat_verify_ms / 1000).toFixed(1) + 's)');
        }
        async _motor(iface, command, expected, movement, origin) {
            const before = await this._fresh_status(18);
            this._position(before);
            const prev = num(before, 'MOV');
            this._require(prev !== null, 'MOV no válido');
            if (movement) this._require(position(before) !== expected, 'Motor ya está ' + expected + '; no se prueba movimiento');
            else this._require(position(before) === expected, 'Repetición incorrecta: estado ' + position(before));
            const cursor = this._checkpoint();
            if (iface === 'serial') await this._send(serialAction(command)); else await this._bleSend(command);
            const sentAt = ahora();
            const after = movement ? await this._await_motor(cursor, expected, prev, true, origin)
                : await this._await_repetition(cursor, expected, prev, origin, sentAt);
            return command + ' → ' + expected + '; MOV ' + prev + '→' + num(after, 'MOV') + '; PB=' + origin;
        }
        async _r2(cmd, expected, code) {
            const before = await this._fresh_status(18);
            this._position(before);
            this._require(position(before) !== expected, 'R2 no producirá transición: ya ' + expected);
            if (num(before, 'err') === code) throw new NoVerification('err=' + code + ' ya estaba activo antes de R2, no es evidencia nueva');
            const cursor = this._checkpoint();
            await this._bleSend(cmd);
            const until = ahora() + 32000;
            let lastPoll = 0, moved = false, event = false;
            while (ahora() < until) {
                this._checkCancel('Cancelada');
                for (const [kind, v] of this.observations.slice(cursor)) {
                    if (kind !== 'status') continue;
                    if (position(v) === expected) moved = true;
                    if (num(v, 'err') === code) event = true;
                }
                if (moved && event) break;
                await this._esperar(200);
                if (ahora() - lastPoll > 3000 && ahora() + 2000 < until) {
                    lastPoll = ahora();
                    try { await this._send(serialAction('STATUS')); } catch (_) {}
                }
            }
            this._require(moved, 'R1 no observó ' + expected + ' tras ' + cmd + ' por R2');
            this._require(event, 'R1 no notificó error nuevo ' + code + ' tras ' + cmd + ' por R2');
            const after = await this._fresh_status(18);
            this._require(position(after) === expected, 'Posición de R2 no se mantuvo estable');
            this._require(num(after, 'MOV') === num(before, 'MOV'), 'MOV de R1 cambió durante R2');
            return cmd + ' → ' + expected + ', err=' + code + ' nuevo en R1; MOV de R1 sin incremento';
        }
        stop(reason) {
            this.cancelled = true;
            if (reason) this.cancelReason = reason;
            this._notify();
            this.log('Solicitud de detener: no se enviarán más comandos. El firmware puede terminar un movimiento ya iniciado.');
        }
        // v1.4.0 (punto 12): cotejo de identidad; ante otra tarjeta pide confirmación y continúa sin reiniciar.
        _coincide(fields, name) {
            const d = this.expected;
            return norm(fields.MAC) === norm(d.mac_r1) && norm(fields.MACR) === norm(d.mac_r2) && (!name || norm(name) === norm(d.nombre));
        }
        async _resolverIdentidad(fields, name, momento) {
            if (this._coincide(fields, name)) return;
            const detectada = { nombre: name || '', id: fields.ID || '', mac: fields.MAC || '', macr: fields.MACR || '', idr: fields.IDR || '' };
            if (this.identity_change) throw new TestFailure('La identidad física no coincide con la tarjeta confirmada; no se moverá el motor.');
            this.log('IDENTIDAD: la tarjeta conectada no es la seleccionada (' + momento + '). Detectada ID ' + detectada.id + ' MAC ' + detectada.mac + ' MACR ' + detectada.macr);
            let propuesta;
            try { propuesta = await this.hooks.identidad(detectada, false); }
            catch (e) { throw new NoVerification('Tarjeta detectada no resoluble en inventario: ' + e.message); }
            this.ui('identity_prompt', { seleccionada: propuesta.seleccionada, detectada: propuesta.detectada });
            let ok = false;
            try { ok = await this.hooks.confirmar({ seleccionada: propuesta.seleccionada, detectada: propuesta.detectada }); }
            catch (_) { ok = false; }
            this._checkCancel('Cancelada');
            if (!ok) {
                this.cancelReason = 'Cancelada: el operador no confirmó continuar con la tarjeta detectada';
                this.cancelled = true;
                throw new Interrupted(this.cancelReason);
            }
            const r = await this.hooks.identidad(detectada, true);
            this.expected = r.inventory;
            this.identity_change = r.identity_change;
            this.log('IDENTIDAD CONFIRMADA por el operador: seleccionada ' + (propuesta.seleccionada.nombre || '') + ' → detectada ' + (propuesta.detectada.nombre || '') + '. Las evidencias siguientes corresponden a la detectada.');
            this.ui('identity_change', r.identity_change);
        }
        async _preIdentidad() {
            const start = this._checkpoint();
            try {
                await this.serial.send(serialAction('STATUS'));
                const st = await this._wait(start, (tag, v) => (tag === 'pre_status' || tag === 'status') && v.fields.MAC, 8, 'S29 de identificación previa');
                return st;
            } catch (e) {
                if (e instanceof Interrupted) throw e;
                this.serial.clearPendingStatus();
                this.log('IDENTIDAD PREVIA no disponible (' + e.message + '); se identificará tras Reset_44 y antes de cualquier movimiento.');
                return null;
            }
        }
        async run({ expected, portName }) {
            if (this.running) throw new Error('Ya hay una ejecución activa');
            if (!this.serial.connected) throw new Error('Conecta el COM primero');
            this.running = true; this.expected = expected;
            this.serial.resetDiagnostics();
            this.ui('reset_steps');
            let issue = '', label = 'no_verificado', r1Name = '', r2Name = '';
            try {
                this.log('SESIÓN INICIADA | puerto=' + portName + ' | ' + CONTEXTO + ' | origen navegador (Web Serial/Web Bluetooth)');
                this.log('CONFIG TX: ACK=' + this.serial.ack_delay_ms + ' ms | Guardia COM=' + this.serial.command_quiet_ms + ' ms | Status sin espera adicional; barrera S29 activa');
                await this._step(0, async () => {
                    const pre = await this._preIdentidad();
                    if (pre) await this._resolverIdentidad(pre.fields, '', 'antes de Reset_44, sin efectos');
                    const start = this._checkpoint();
                    await this.serial.send(serialAction('RESET_FACTORY'));
                    const name = await this._wait(start, tag => tag === 'ready', 65, 'Lista para usarse');
                    const status = await this._initial_s29(start, 22);
                    this._require(status.fields.ID, 'S29 sin ID');
                    this._require(status.fields.MAC, 'S29 sin MAC');
                    // Identidad tras reinicio y antes de cualquier movimiento.
                    await this._resolverIdentidad(status.fields, name, 'tras Reset_44, antes de mover');
                    this.identity_status = status;
                    return name + ' | ID ' + status.fields.ID + ' | FW ' + status.fields.VER + ' | MAC ' + status.fields.MAC;
                });
                await this._step(1, async () => {
                    const v = await this._fresh_status(22);
                    this._position(v);
                    this._require(num(v, 'SEN_MOT') === 0, 'SEN_MOT debe ser 0 para verificar sensores físicos');
                    this._require(num(v, 'TQT') === 0, 'Motor sigue ejecutando una acción');
                    this._require(![3, 4].includes(num(v, 'err')), 'Error motor activo err=' + num(v, 'err'));
                    this.log('Banco de pruebas: MOTOR=' + num(v, 'MOTOR') + '; no se exige autorización adicional');
                    return 'Inicio: ' + position(v) + ' (ON=' + v.fields.ON + ' OFF=' + v.fields.OFF + '); MOTOR=' + num(v, 'MOTOR');
                });
                const series = async (first, iface, origin) => {
                    const before = await this._fresh_status(20);
                    const p = this._position(before);
                    const [a1, t1] = this._nextCommand(p), [a2, t2] = this._nextCommand(t1);
                    for (const [off, cmd, target, movement] of [[0, a1, t1, true], [1, a1, t1, false], [2, a2, t2, true], [3, a2, t2, false]]) {
                        await this._step(first + off, () => this._motor(iface, cmd, target, movement, origin), 'R1 ' + iface + ' · ' + cmd + ' ' + (movement ? 'movimiento' : 'repetición'));
                    }
                };
                await series(2, 'serial', 1);
                await this._step(6, async () => {
                    const reported = normalizeMac(this.latest ? this.latest.fields.MAC : '');
                    const device = await this.ble.localizar({ nombre: this.ready_name, dispositivo: 'R1', gesto: this.hooks.gesto });
                    this._checkCancel('Cancelada');
                    await this.ble.connect(device, 'R1');
                    r1Name = device.name || '';
                    // La MAC BLE no es observable desde el navegador: el vínculo se demuestra con PB=2 en los movimientos.
                    this.mac_comparison = 'no_expuesta_navegador';
                    this.ble_identity.r1 = { nombre: r1Name, metodo: 'nombre exacto autorizado + vínculo funcional PB=2', mac_reportada_r1: reported, id_opaco_navegador: device.id || null };
                    this.ui('ble_ident', 'R1', r1Name, '', this.mac_comparison);
                    return r1Name + ' | criterio nombre exacto; MAC BLE no expuesta por el navegador (se verifica por movimiento PB=2)';
                });
                await series(7, 'ble', 2);
                if ([7, 8, 9, 10].every(i => this.steps[i].state === 'aprobado')) this.mac_comparison = 'vinculo_funcional';
                await this._step(11, async () => {
                    await this.ble.disconnect();
                    const related = normalizeMac(this.latest ? this.latest.fields.MACR : '');
                    const nombre = this.expected.r2_nombre || '';
                    if (!nombre) throw new NoVerification('El inventario no tiene nombre BLE de R2; no se enviaron comandos a otro BLE.');
                    const device = await this.ble.localizar({ nombre, dispositivo: 'R2', gesto: this.hooks.gesto });
                    this._require(String(device.name || '').toUpperCase().includes('R2'), 'El nombre BLE no identifica a R2: ' + device.name);
                    this._checkCancel('Cancelada');
                    await this.ble.connect(device, 'R2');
                    r2Name = device.name || '';
                    const declarada = await this.ble.macDeclarada();
                    if (declarada && related && normalizeMac(declarada) !== related)
                        throw new TestFailure('La R2 conectada declara MAC ' + declarada + ' distinta de MACR=' + related + '; no se enviaron comandos.');
                    const method = declarada ? 'MAC declarada por R2 (info OTA) = MACR reportada por R1' : 'nombre BLE de inventario; MAC no expuesta (se verifica por err=13/14 en R1)';
                    this.ble_identity.r2 = { nombre: r2Name, metodo: method, mac_declarada_r2: declarada, macr_reportada_r1: related, id_opaco_navegador: device.id || null };
                    this.ui('ble_ident', 'R2', r2Name, '', method);
                    this.log('R2 conectada automáticamente por ' + method + ': ' + r2Name);
                    return 'R2 ' + r2Name + ', criterio: ' + method;
                });
                const initial = await this._fresh_status(20);
                const [first, target] = this._nextCommand(this._position(initial));
                const [other, finalTarget] = this._nextCommand(target);
                for (const [i, cmd, dest] of [[12, first, target], [13, other, finalTarget]]) {
                    const code = cmd === 'POFF' ? 14 : 13;
                    await this._step(i, () => this._r2(cmd, dest, code), 'R2 BLE · ' + cmd + ', nuevo err=' + code);
                }
                label = this.steps.every(s => s.state === 'aprobado') && this.mac_comparison === 'vinculo_funcional' ? 'aprobado' : 'no_verificado';
                if (communicate(this.serial.health).state === 'no_verificable') {
                    label = 'no_verificado';
                    issue = (issue ? issue + '; ' : '') + 'Comunicación serial no verificable: faltaron bytes, hubo reintentos o falló un ACK; diagnóstico ' + JSON.stringify(this.serial.health);
                }
            } catch (e) {
                if (e instanceof Interrupted || e instanceof NoVerification) { issue = e.message; label = 'no_verificado'; }
                else { issue = String(e && e.message || e); label = 'fallido'; this.log('SESIÓN INTERRUMPIDA: ' + (e && e.constructor && e.constructor.name) + ': ' + issue); }
            } finally {
                try { await this.ble.disconnect(); } catch (e) { this.log('AVISO BLE: ' + e.message); }
                const base = this.identity_status || this.latest, f = base ? base.fields : {};
                const health = Object.assign({}, this.serial.health), quality = communicate(health);
                const warnings = buildWarnings(health, this.warnings);
                const d = this.expected || {};
                const r1 = !d.mac_r1 ? 'no_verificado' : (normalizeMac(d.mac_r1) === normalizeMac(f.MAC) && this.mac_comparison === 'vinculo_funcional') ? 'coincide' : (f.MAC && normalizeMac(d.mac_r1) !== normalizeMac(f.MAC)) ? 'no_coincide' : 'no_verificado';
                const r2ok = [12, 13].every(i => this.steps[i].state === 'aprobado');
                const r2 = !d.mac_r2 ? 'no_verificado' : (normalizeMac(d.mac_r2) === normalizeMac(f.MACR) && r2ok) ? 'coincide' : (f.MACR && normalizeMac(d.mac_r2) !== normalizeMac(f.MACR)) ? 'no_coincide' : 'no_verificado';
                const state = (r1 === 'no_coincide' || r2 === 'no_coincide') ? 'no_coincide' : (r1 === 'coincide' && r2 === 'coincide') ? 'coincide' : 'incompleto';
                const check = { state, r1, r2, detail: 'Inventario: R1 ' + r1 + ', R2 ' + r2 + ' (MAC de firmware + vínculo funcional BLE)', matched_by: 'inventario_web' };
                if (label === 'aprobado' && state === 'no_coincide') { label = 'no_verificado'; issue = 'La MAC no coincide con inventario. ' + check.detail; }
                if (label === 'aprobado' && quality.state === 'no_verificable') { label = 'no_verificado'; issue = 'Tramas parciales/reintentos/errores ACK impiden certificación serial'; }
                const cancelada = this.cancelled;
                this.report = {
                    report_schema: 'tqt-station/0.6.3-web', origin: 'web', context: CONTEXTO,
                    date: isoMs(), card: this.ready_name, serial_port: portName,
                    firmware: f.VER || null, hardware: f.HW || null, card_id: f.ID || null,
                    // MAC observada por BLE: no disponible en el navegador (nunca device.id).
                    r1_ble_address: null, r2_ble_address: null, r1_ble_name: r1Name || null, r2_ble_name: r2Name || null,
                    ble_identity: this.ble_identity,
                    reported_mac: f.MAC || null, reported_mac_r2: f.MACR || null,
                    inventory_source: 'Inventario TQT SQLite; snapshot del servidor', inventory_mac: d.mac_r1 || null,
                    inventory_check: check, mac_comparison: this.mac_comparison, result: label, issue,
                    cancelled: cancelada, identity_change: this.identity_change,
                    ending_position: this.latest ? position(this.latest) : null,
                    steps: this.steps.map(s => Object.assign({}, s)), serial_health: health,
                    communication_quality: quality,
                    serial_timing: { ack_delay_ms: this.serial.ack_delay_ms, status_quiet_ms: 0, command_quiet_ms: this.serial.command_quiet_ms },
                    warnings, status_final: this.latest ? Object.assign({}, this.latest.fields) : {},
                };
                this.log('RESULTADO ' + label.toUpperCase() + (warnings.length ? ' (CON AVISOS)' : '') + (cancelada ? ' | CANCELADA' : ''));
                if (warnings.length) this.log('ADVERTENCIAS: ' + warnings.length + ' · ' + warnings.join(' | '));
                this.running = false;
                this.ui('done', label, issue, { cancelada });
            }
            return this.report;
        }
    }

    // ------------------------------------------------------------ servidor
    async function http(path, body, timeout = 15000) {
        if (window.TQT && window.TQT.api) {
            const r = await window.TQT.api(API + path, body !== undefined ? { method: 'POST', body, timeout } : { timeout });
            if (!r.ok) { const e = new Error(r.error || 'Error del servidor'); e.network = r.network; throw e; }
            return r.data;
        }
        const res = await fetch(API + path, body !== undefined ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : {});
        const data = await res.json().catch(() => null);
        if (!res.ok) throw new Error((data && data.detail) || 'Error ' + res.status);
        return data;
    }

    /* Publicador por lotes: orden estricto, idempotente por seq, latido cada 20 s. */
    class Publicador {
        constructor(jid, onCancel, enviar) {
            this.jid = jid; this.onCancel = onCancel; this.enviar = enviar || http;
            this.cola = []; this.seq = 0; this.enVuelo = null; this.ultimo = 0; this.fallos = 0;
            this.timer = setInterval(() => this.flush().catch(() => {}), 1000);
        }
        push(data) { this.seq += 1; const e = { seq: this.seq, data }; this.cola.push(e); return e; }
        async flush(forzar) {
            if (this.enVuelo) { await this.enVuelo.catch(() => {}); if (!forzar) return; }
            const latido = Date.now() - this.ultimo > 20000;
            if (!this.cola.length && !latido) return;
            const items = this.cola.slice(0, 100);
            this.enVuelo = (async () => {
                const r = await this.enviar('/web/runs/' + this.jid + '/events', { items });
                this.cola.splice(0, items.length); this.ultimo = Date.now(); this.fallos = 0;
                if (r && r.cancel) this.onCancel();
            })();
            try { await this.enVuelo; } catch (e) { this.fallos++; throw e; } finally { this.enVuelo = null; }
        }
        async drenar() {
            for (let i = 0; i < 40 && this.cola.length; i++) {
                try { await this.flush(true); } catch (_) { await dormir(Math.min(500 * (i + 1), 3000)); }
            }
            if (this.cola.length) throw new Error('No se pudieron enviar ' + this.cola.length + ' eventos al servidor.');
        }
        cerrar() { clearInterval(this.timer); }
    }

    // ------------------------------------------------------------ estado público y API K1
    const CFG = { ackMs: 180, quietMs: 300, repeatVerifyMs: 5000 };
    const st = { serial: { estado: 'off', puerto: '', texto: 'Sin puerto' }, ble: { estado: 'off', dispositivo: null, texto: 'Sin Bluetooth' } };
    const subs = new Set(), monitores = new Set();
    let port = null, cx = null, link = null, motor = null, enCurso = false;
    function emitir() { const s = estado(); subs.forEach(fn => { try { fn(s); } catch (e) { console.error(e); } }); }
    function estado() { return { serial: Object.assign({}, st.serial), ble: Object.assign({}, st.ble) }; }
    function setSerial(estadoS, texto) { st.serial = { estado: estadoS, puerto: port ? (window.TQTSerial ? TQTSerial.describir(port) : 'Puerto serial') : '', texto: texto || '' }; emitir(); }
    function setBle(estadoB, texto, dispositivo) { st.ble = { estado: estadoB, dispositivo: estadoB === 'off' || estadoB === 'error' ? null : (dispositivo || st.ble.dispositivo), texto: texto || '' }; emitir(); }
    const bleLink = new BleLink(msg => { if (motor && motor.running) motor.log(msg); else monitores.forEach(fn => fn({ kind: 'log', text: msg })); },
        (e, texto, disp) => setBle(e, texto, disp));

    function soportado() { return !!(window.isSecureContext && navigator.serial && navigator.bluetooth && window.TQTSerial); }
    function onEstado(fn) { subs.add(fn); return () => subs.delete(fn); }
    function onMonitor(fn) { monitores.add(fn); return () => monitores.delete(fn); }

    function nuevoLink() {
        return new SerialLink({
            cfg: CFG,
            onLine: line => {
                if (motor) motor.on_line(line);
                else { const s = parseStatus(line); monitores.forEach(fn => fn({ kind: 'line', text: line, status: s })); }
            },
            onInfo: text => { if (motor) motor.log(text); else monitores.forEach(fn => fn({ kind: 'log', text })); },
        });
    }
    async function conectar(p) {
        if (cx) await desconectar();
        port = p;
        setSerial('conectando', 'Abriendo a ' + BAUD + ' baudios');
        link = nuevoLink();
        try {
            cx = await TQTSerial.abrir(p, {
                baudRate: BAUD, propietario: 'Validación TQT',
                onBytes: b => link && link.feed(b),
                onCierre: motivo => {
                    link && link.detach(); cx = null;
                    setSerial(motivo === 'Cerrado por el operador' ? 'off' : 'error', motivo || 'Puerto cerrado');
                },
            });
        } catch (e) { cx = null; setSerial('error', e.message); throw e; }
        link.attach(cx, cx.descripcion);
        setSerial('ok', cx.descripcion + ' · ' + BAUD + ' 8N1');
        return estado();
    }
    async function elegirPuerto() {
        if (enCurso) throw new Error('Hay una prueba en curso; no se cambia el puerto.');
        if (!window.TQTSerial || !TQTSerial.soportado()) throw new Error('Este navegador no soporta Web Serial. Usa Chrome o Edge de escritorio en HTTPS.');
        let p;
        try { p = await TQTSerial.elegir(); }
        catch (e) {
            // Cancelar el selector: reutilizar el único puerto autorizado si existe.
            const previos = await TQTSerial.autorizados();
            if (previos.length !== 1) throw new Error('No se eligió puerto.');
            p = previos[0];
        }
        return conectar(p);
    }
    async function reutilizarPuerto() {
        if (cx) return true;
        const previos = window.TQTSerial ? await TQTSerial.autorizados() : [];
        if (previos.length === 1) { await conectar(previos[0]); return true; }
        return false;
    }
    async function desconectar() {
        if (enCurso) throw new Error('Hay una prueba en curso.');
        if (cx) await cx.cerrar('Cerrado por el operador');
        cx = null; link = null;
        setSerial('off', 'Desconectado');
    }

    /* Gesto de usuario para Web Bluetooth: requestDevice exige activación transitoria.
     * Si la UI no aporta solicitarGesto, se muestra un diálogo propio con un botón. */
    function gestoPorDefecto(signal) {
        return ({ dispositivo, nombre, autorizar }) => new Promise((resolve, reject) => {
            const dlg = document.createElement('dialog');
            dlg.setAttribute('aria-labelledby', 'tqtvw-t');
            dlg.className = 'tqt-dialog';
            const t = document.createElement('p'); t.id = 'tqtvw-t';
            t.textContent = 'La prueba necesita permiso de Bluetooth para ' + dispositivo + '. Pulsa «Autorizar» y elige «' + nombre + '» en el selector del navegador.';
            const ok = document.createElement('button'); ok.type = 'button'; ok.className = 'btn primary'; ok.textContent = 'Autorizar ' + dispositivo + ' BLE';
            const no = document.createElement('button'); no.type = 'button'; no.className = 'btn'; no.textContent = 'Cancelar prueba';
            const fin = () => { signal && signal.removeEventListener('abort', ab); try { dlg.close(); } catch (_) {} dlg.remove(); };
            const ab = () => { fin(); reject(new Interrupted('Prueba detenida por el usuario')); };
            ok.onclick = () => { autorizar().then(d => { fin(); resolve(d); }, e => { t.textContent = 'No se autorizó (' + (e && e.message || e) + '). Reintenta o cancela.'; }); };
            no.onclick = () => { fin(); reject(new Interrupted('Cancelada: no se autorizó Bluetooth ' + dispositivo)); };
            signal && signal.addEventListener('abort', ab, { once: true });
            dlg.append(t, ok, document.createTextNode(' '), no);
            document.body.appendChild(dlg);
            dlg.showModal ? dlg.showModal() : dlg.setAttribute('open', '');
            ok.focus();
        });
    }

    async function conLock(fn) {
        if (navigator.locks && navigator.locks.request) {
            return navigator.locks.request('tqt-validacion-web', { ifAvailable: true }, async lock => {
                if (!lock) throw new Error('Otra pestaña de este navegador está ejecutando una validación.');
                return fn();
            });
        }
        return fn();
    }

    async function iniciar({ tarjetaId, onEvento, confirmarIdentidad, signal, solicitarGesto } = {}) {
        if (!soportado()) throw new Error('Validación directa requiere Chrome/Edge de escritorio en HTTPS con Web Serial y Web Bluetooth.');
        if (enCurso) throw new Error('Ya hay una prueba en curso en esta pestaña.');
        if (!tarjetaId) throw new Error('Selecciona la tarjeta.');
        if (signal && signal.aborted) throw new Error('Cancelada antes de iniciar.');
        if (!cx && !(await reutilizarPuerto())) throw new Error('Elige el puerto serial de la R1.');
        await reintentarPendiente();
        return conLock(async () => {
            enCurso = true;
            let pub = null;
            try {
                const run = await http('/web/runs', { tarjeta_id: tarjetaId });
                const jid = run.id;
                let m;
                pub = new Publicador(jid, () => m && !m.cancelled && m.stop('Cancelación solicitada desde el servidor'));
                const emitirEv = (kind, ...args) => {
                    const e = pub.push({ kind, args });
                    try { onEvento && onEvento(e); } catch (err) { console.error(err); }
                };
                m = new Motor({
                    serial: link, ble: bleLink, cfg: CFG, ui: emitirEv,
                    hooks: {
                        gesto: solicitarGesto || gestoPorDefecto(signal),
                        confirmar: confirmarIdentidad || (async () => false),
                        identidad: (detectada, confirmar) => http('/web/runs/' + jid + '/identity', { detectada, confirmar }),
                    },
                });
                motor = m;
                const alAbortar = () => { m.stop('Prueba detenida por el usuario'); http('/runs/' + jid + '/cancel', {}).catch(() => {}); };
                signal && signal.addEventListener('abort', alAbortar, { once: true });
                let report;
                try { report = await m.run({ expected: run.inventory, portName: link.portName }); }
                finally { signal && signal.removeEventListener('abort', alAbortar); motor = null; }
                pub.push({ kind: 'full_log', text: m.logText });
                await pub.drenar().catch(e => m.log('AVISO: ' + e.message));
                pub.cerrar();
                const resultado = await enviarResultado(jid, report);
                return { jid, resultado };
            } finally {
                pub && pub.cerrar();
                enCurso = false;
            }
        });
    }
    const PENDIENTE = 'tqt-validacion-web-resultado';
    async function enviarResultado(jid, report) {
        for (let i = 0; i < 5; i++) {
            try { const r = await http('/web/runs/' + jid + '/result', report, 30000); try { sessionStorage.removeItem(PENDIENTE); } catch (_) {} return r; }
            catch (e) { if (!e.network && i > 0) throw e; await dormir(1500 * (i + 1)); }
        }
        try { sessionStorage.setItem(PENDIENTE, JSON.stringify({ jid, report })); } catch (_) {}
        throw new Error('No se pudo guardar el resultado en el servidor; se reintentará al iniciar la siguiente prueba. No repitas la prueba.');
    }
    async function reintentarPendiente() {
        let p = null;
        try { p = JSON.parse(sessionStorage.getItem(PENDIENTE) || 'null'); } catch (_) {}
        if (!p) return;
        try { await http('/web/runs/' + p.jid + '/result', p.report, 30000); }
        catch (e) { if (e.network) return; }  // rechazo definitivo del servidor: no reintentar para siempre
        try { sessionStorage.removeItem(PENDIENTE); } catch (_) {}
    }

    /* ON/OFF manual por BLE (PPON/POFF exactos). Bloqueado durante la prueba automática.
     * Si el dispositivo no está conectado, debe invocarse desde un clic (puede abrir el selector). */
    async function bleManual({ dispositivo, accion, nombre } = {}) {
        const comando = accion === 'ON' ? 'PPON' : accion === 'OFF' ? 'POFF' : null;
        if (!comando || !['R1', 'R2'].includes(dispositivo)) return { ok: false, enviado: null, respuesta: null, error: 'Acción o dispositivo inválido.' };
        if (enCurso) return { ok: false, enviado: null, respuesta: null, error: 'La prueba automática usa el Bluetooth; espera a que termine.' };
        if (!navigator.bluetooth) return { ok: false, enviado: null, respuesta: null, error: 'Este navegador no soporta Web Bluetooth.' };
        const respuestas = [];
        const quitar = onMonitor(e => { if (e.kind === 'log' && e.text.startsWith('RX BLE: ')) respuestas.push(e.text.slice(8)); });
        try {
            if (!(bleLink.connected && bleLink.dispositivo === dispositivo && (!nombre || bleLink.nombre.toUpperCase() === nombre.toUpperCase()))) {
                const prefijo = 'TQT';
                let device = null;
                if (nombre) {
                    const previos = navigator.bluetooth.getDevices ? await navigator.bluetooth.getDevices().catch(() => []) : [];
                    device = previos.find(d => (d.name || '').toUpperCase() === nombre.toUpperCase()) || null;
                }
                if (!device) device = await navigator.bluetooth.requestDevice({ filters: nombre ? [{ name: nombre }] : [{ namePrefix: prefijo }], optionalServices: [SERVICE_UUID, OTA_SERVICE] });
                if (dispositivo === 'R2' && !String(device.name || '').toUpperCase().includes('R2')) throw new Error('El dispositivo elegido no es una R2: ' + device.name);
                if (dispositivo === 'R1' && String(device.name || '').toUpperCase().includes('R2')) throw new Error('El dispositivo elegido es una R2, no R1: ' + device.name);
                await bleLink.connect(device, dispositivo);
            }
            await bleLink.send(comando);
            await dormir(600);
            return { ok: true, enviado: comando + ' → ' + bleLink.nombre + ' (' + dispositivo + ')', respuesta: respuestas.join(' | ') || null, error: null };
        } catch (e) {
            return { ok: false, enviado: null, respuesta: respuestas.join(' | ') || null, error: String(e && e.message || e) };
        } finally { quitar(); }
    }

    if (navigator.serial) {
        navigator.serial.addEventListener('connect', () => { if (!cx && !enCurso) reutilizarPuerto().catch(() => {}); });
    }

    window.TQTValWeb = {
        soportado, estado, onEstado, elegirPuerto, iniciar, bleManual,
        // v1.4.0: extras (no forman parte de K1 pero son útiles para la UI)
        desconectar, onMonitor, reutilizarPuerto, contexto: CONTEXTO,
        _interno: { parseStatus, readReady, position, serialAction, normalizeMac, communicate, buildWarnings,
            SerialLink, BleLink, Motor, Publicador, TestFailure, NoVerification, Interrupted, CFG, STEP_NAMES, FIELDS },
    };
})();
