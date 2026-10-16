/* v1.4.0: capa Web Serial compartida (window.TQTSerial).
 * - Un único propietario por puerto (monitor, flasheo y pruebas no se pisan).
 * - Lector incremental: los bytes se entregan en orden y un tramador arma líneas por LF.
 * - Cola de escritura serializada; los locks del lector/escritor se liberan siempre.
 * - Cancelación (AbortSignal) y limpieza al cerrar o al desconectar el cable.
 * No lista los COM del sistema: solo puertos que el usuario autorizó en el selector nativo.
 * Otra pestaña que tenga el puerto abierto hace fallar open(): se informa, no se fuerza. */
(function () {
    'use strict';
    const propietarios = new Map();   // SerialPort -> conexión activa

    function soportado() { return !!(navigator.serial && window.isSecureContext); }

    function describir(port) {
        try {
            const i = port.getInfo ? port.getInfo() : {};
            if (i.usbVendorId == null) return 'Puerto serial';
            const hex = n => n.toString(16).toUpperCase().padStart(4, '0');
            return 'USB ' + hex(i.usbVendorId) + ':' + hex(i.usbProductId || 0);
        } catch (_) { return 'Puerto serial'; }
    }

    async function autorizados() {
        if (!navigator.serial) return [];
        try { return await navigator.serial.getPorts(); } catch (_) { return []; }
    }

    async function elegir(filtros) {
        if (!soportado()) throw new Error('Este navegador no soporta Web Serial. Usa Chrome o Edge de escritorio en HTTPS.');
        return navigator.serial.requestPort(filtros ? { filters: filtros } : {});
    }

    /* Tramador: acumula bytes y emite cada línea terminada en LF (sin el CR final).
     * Conserva los bytes crudos para el registro HEX de tramas dañadas. */
    function crearTramador({ onLinea, maxBytes = 8192, onDesborde }) {
        let buf = [];
        const dec = new TextDecoder('utf-8', { fatal: false });
        return {
            empujar(bytes) {
                for (const b of bytes) {
                    if (b === 10) {
                        const raw = Uint8Array.from(buf);
                        buf = [];
                        let linea = dec.decode(raw);
                        if (linea.endsWith('\r')) linea = linea.slice(0, -1);
                        onLinea(linea, raw);
                    } else if (buf.length < maxBytes) buf.push(b);
                    else { buf = []; onDesborde && onDesborde(); }
                }
            },
            pendientes() { return buf.length; },
            cola() { return dec.decode(Uint8Array.from(buf)); },
            vaciar() { buf = []; },
        };
    }

    /* Abre un puerto con un propietario. onBytes recibe Uint8Array en orden de llegada.
     * Devuelve {port, propietario, escribir(datos), cerrar(), cerrado (Promise), activo()}. */
    async function abrir(port, { baudRate, propietario, onBytes, onCierre, signal, dataBits = 8, parity = 'none', stopBits = 1 }) {
        if (!port) throw new Error('Elige primero el puerto serial.');
        if (!baudRate) throw new Error('Falta la velocidad (baudios) del protocolo.');
        const actual = propietarios.get(port);
        if (actual) throw new Error('El puerto está en uso por ' + actual.propietario + '. Ciérralo antes de usarlo aquí.');
        const cx = { port, propietario: propietario || 'desconocido', abierto: false };
        propietarios.set(port, cx);
        try {
            await port.open({ baudRate, dataBits, parity, stopBits, bufferSize: 4096 });
        } catch (e) {
            propietarios.delete(port);
            const msg = String(e && e.message || e);
            throw new Error(/already open|InvalidState/i.test(msg)
                ? 'El puerto ya está abierto (otra pestaña o programa). Ciérralo y reintenta.'
                : /Failed to open|NetworkError|access/i.test(msg)
                    ? 'No se pudo abrir el puerto: puede estar ocupado por otro programa o se desconectó.'
                    : 'No se pudo abrir el puerto: ' + msg);
        }
        cx.abierto = true;
        let reader = null, cerrando = false, cola = Promise.resolve(), motivo = '';
        let resolverCierre;
        cx.cerrado = new Promise(r => { resolverCierre = r; });

        const leer = (async () => {
            while (cx.abierto && port.readable) {
                reader = port.readable.getReader();
                try {
                    for (;;) {
                        const { value, done } = await reader.read();
                        if (done) break;
                        if (value && value.length && onBytes) {
                            try { onBytes(value); } catch (e) { console.error(e); }
                        }
                    }
                } catch (e) {
                    // Errores de trama/paridad son recuperables; la pérdida del dispositivo no.
                    if (!cerrando) motivo = String(e && e.message || e);
                    if (!cerrando && e && /BreakError|FramingError|ParityError|BufferOverrunError/.test(e.name || '')) {
                        try { reader.releaseLock(); } catch (_) {}
                        reader = null;
                        continue;
                    }
                } finally {
                    try { reader && reader.releaseLock(); } catch (_) {}
                    reader = null;
                }
                break;
            }
        })();

        function escribir(datos) {
            const bytes = typeof datos === 'string' ? new TextEncoder().encode(datos) : datos;
            const tarea = cola.then(async () => {
                if (!cx.abierto || !port.writable) throw new Error('Puerto serial desconectado.');
                const w = port.writable.getWriter();
                try { await w.write(bytes); }
                finally { try { w.releaseLock(); } catch (_) {} }
                return bytes.length;
            });
            cola = tarea.catch(() => {});
            return tarea;
        }

        async function cerrar(razon) {
            if (cerrando) return cx.cerrado;
            cerrando = true;
            if (razon) motivo = razon;
            try { if (reader) await reader.cancel(); } catch (_) {}
            try { await leer; } catch (_) {}
            try { await cola; } catch (_) {}
            try { await port.close(); } catch (_) {}
            cx.abierto = false;
            propietarios.delete(port);
            navigator.serial && navigator.serial.removeEventListener('disconnect', alDesconectar);
            signal && signal.removeEventListener('abort', alAbortar);
            resolverCierre(motivo);
            try { onCierre && onCierre(motivo); } catch (_) {}
            return motivo;
        }
        function alDesconectar(ev) { if (ev.target === port || ev.port === port) cerrar('Cable/puerto desconectado'); }
        function alAbortar() { cerrar('Cancelado'); }
        navigator.serial && navigator.serial.addEventListener('disconnect', alDesconectar);
        signal && signal.addEventListener('abort', alAbortar, { once: true });
        // Si el lector termina solo (dispositivo perdido), liberar todo.
        leer.then(() => { if (!cerrando) cerrar(motivo || 'Lectura serial terminada'); });

        cx.escribir = escribir;
        cx.cerrar = cerrar;
        cx.activo = () => cx.abierto && !cerrando;
        cx.descripcion = describir(port);
        return cx;
    }

    function enUso(port) { const c = propietarios.get(port); return c ? c.propietario : null; }

    window.TQTSerial = { soportado, autorizados, elegir, abrir, enUso, describir, crearTramador };
})();
