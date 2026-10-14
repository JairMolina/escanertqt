/* BLE OTA v1. Device protocol is authenticated/encrypted by the server, not by browser-held keys. */
(function () {
    'use strict';
    const SERVICE = 'd45a0001-6a76-4e41-9f38-a7043f0ec069';
    const UUID = {
        info: 'd45a0002-6a76-4e41-9f38-a7043f0ec069',
        control: 'd45a0003-6a76-4e41-9f38-a7043f0ec069',
        data: 'd45a0004-6a76-4e41-9f38-a7043f0ec069',
        status: 'd45a0005-6a76-4e41-9f38-a7043f0ec069'
    };
    const STORAGE = 'tqt-r2-ota-pending';
    const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
    const decode = value => new Uint8Array(Uint8Array.from(atob(value), c => c.charCodeAt(0)));
    function pending() { try { return JSON.parse(sessionStorage.getItem(STORAGE) || 'null'); } catch (_) { return null; } }
    function save(value) { if (value) sessionStorage.setItem(STORAGE, JSON.stringify(value)); else sessionStorage.removeItem(STORAGE); }
    function check(signal) { if (signal?.aborted) throw new Error('Actualización cancelada.'); }
    async function bounded(promise, signal, ms = 15000) {
        check(signal);
        let timer, abort;
        try {
            return await Promise.race([promise,
                new Promise((_, reject) => { timer = setTimeout(() => reject(new Error('Bluetooth no respondió a tiempo.')), ms); }),
                new Promise((_, reject) => { abort = () => reject(new Error('Actualización cancelada.')); signal?.addEventListener('abort', abort, { once: true }); })]);
        } finally { clearTimeout(timer); signal?.removeEventListener('abort', abort); }
    }
    async function json(characteristic, signal) {
        const value = await bounded(characteristic.readValue(), signal);
        try { return JSON.parse(new TextDecoder().decode(value)); }
        catch (_) { throw new Error('La R2 respondió información OTA inválida.'); }
    }
    async function connect(device, signal) {
        const server = await bounded(device.gatt.connect(), signal);
        const service = await bounded(server.getPrimaryService(SERVICE), signal);
        const chars = {};
        // Serialized GATT requests avoid "operation already in progress" on Windows.
        for (const [key, id] of Object.entries(UUID)) chars[key] = await bounded(service.getCharacteristic(id), signal);
        return chars;
    }
    async function bootInfo(chars, signal) {
        const deadline = Date.now() + 20000;
        let info;
        do {
            info = await json(chars.info, signal);
            if (info.boot_valid) return info;
            await sleep(200);
        } while (Date.now() < deadline);
        throw new Error('La R2 todavía no confirmó su arranque.');
    }
    async function waitState(chars, accept, signal, ms = 15000) {
        const deadline = Date.now() + ms;
        do {
            const status = await json(chars.status, signal);
            if (status.state === 'error') throw new Error('La R2 detuvo OTA: ' + status.error);
            if (accept(status)) return status;
            await sleep(30);
        } while (Date.now() < deadline);
        throw new Error('La R2 no confirmó el bloque OTA; no se activó el firmware.');
    }
    async function stream(chars, bytes, chunk, signal, manifest, progress) {
        const started = performance.now();
        for (let offset = 0, batch = 0; offset < bytes.length;) {
            check(signal);
            const length = Math.min(chunk, bytes.length - offset);
            const packet = new Uint8Array(length + 4);
            new DataView(packet.buffer).setUint32(0, offset, true);
            packet.set(bytes.subarray(offset, offset + length), 4);
            await bounded(chars.data.writeValueWithResponse(packet), signal);
            offset += length;
            // Firmware v1 queues eight packets. Drain at that boundary before sending more.
            if (++batch === 8 || offset === bytes.length) {
                await waitState(chars, status => manifest ?
                    (status.state === 'manifest' && status.offset >= offset) || (offset === bytes.length && status.state === 'receiving') :
                    (status.state === 'receiving' && status.offset >= offset) || (offset === bytes.length && status.state === 'ready'), signal);
                batch = 0; if (!manifest) progress(offset, bytes.length, { elapsed: (performance.now() - started) / 1000 });
            }
        }
    }
    async function reconnect(device, signal) {
        const deadline = Date.now() + 45000;
        let last;
        do {
            check(signal);
            try { return await connect(device, signal); }
            catch (e) { last = e; device.gatt.disconnect(); await sleep(500); }
        } while (Date.now() < deadline);
        throw new Error('No se reconectó la R2. Usa «Verificar OTA pendiente» cuando esté encendida. ' + (last?.message || ''));
    }
    async function execute(options, recovery = false) {
        const { pcb, firmwareId, api, signal, stage, progress, committing } = options;
        if (!navigator.bluetooth || !window.isSecureContext) throw new Error('OTA requiere Bluetooth y Chrome/Edge en HTTPS o localhost.');
        check(signal);
        let device, chars, job = null, committed = false;
        const abortDevice = () => device?.gatt?.disconnect();
        try {
            // Keep requestDevice in the click gesture, before network operations.
            const selection = navigator.bluetooth.requestDevice({ filters: [{ name: pcb.nombre.replace(/-/g, '_') }], optionalServices: [SERVICE] });
            stage('Selecciona la R2 conectada por Bluetooth');
            device = await bounded(selection, signal, 120000);
            signal?.addEventListener('abort', abortDevice);
            stage('Conectando y verificando la identidad de la R2');
            chars = await connect(device, signal);
            let info = await bootInfo(chars, signal);
            if (info.nombre !== pcb.nombre.replace(/-/g, '_') || info.ota_protocol !== 1) throw new Error('La placa no corresponde a la R2 elegida o no tiene OTA V4.1.');
            if (recovery) {
                const saved = pending();
                if (!saved || saved.pcb_id !== pcb.id) throw new Error('No hay OTA pendiente para esta R2.');
                stage('Verificando el firmware instalado');
                const result = await api('/api/esp32/ota/result/' + saved.job_id, { method: 'POST', body: info });
                if (!result.ok) throw new Error(result.error);
                save(null); return result.data;
            }
            if (pending()) throw new Error('Primero verifica o descarta la OTA pendiente.');
            stage('Autorizando y preparando el firmware cifrado');
            const prepared = await api('/api/esp32/ota/prepare/' + pcb.id, { method: 'POST', body: { firmware_id: firmwareId, device: info } });
            if (!prepared.ok) throw new Error(prepared.error);
            job = prepared.data.job_id;
            const chunk = Math.min(180, Math.max(1, info.chunk || 16));
            await bounded(chars.control.writeValueWithResponse(new Uint8Array([1])), signal);
            await waitState(chars, s => s.state === 'manifest', signal);
            await stream(chars, decode(prepared.data.manifest), chunk, signal, true, progress);
            stage('Enviando firmware por Bluetooth');
            const encrypted = decode(prepared.data.encrypted_image);
            progress(0, encrypted.length, { elapsed: 0 });
            await stream(chars, encrypted, chunk, signal, false, progress);
            await waitState(chars, s => s.state === 'ready', signal);
            // Cancellation is safe up to this point. Afterwards the device may already boot the new slot.
            save({ pcb_id: pcb.id, nombre: pcb.nombre, job_id: job }); committing(true); committed = true;
            stage('Firmware verificado; activando y reiniciando la R2');
            await bounded(chars.control.writeValueWithResponse(new Uint8Array([2])), signal);
            const disconnectDeadline = Date.now() + 10000;
            while (device.gatt.connected && Date.now() < disconnectDeadline) await sleep(100);
            if (device.gatt.connected) throw new Error('La R2 no confirmó el reinicio; verifica la OTA pendiente.');
            stage('Reconectando y comprobando la nueva versión');
            chars = await reconnect(device, signal);
            info = await bootInfo(chars, signal);
            const result = await api('/api/esp32/ota/result/' + job, { method: 'POST', body: info });
            if (!result.ok) throw new Error(result.error);
            save(null); return result.data;
        } catch (error) {
            if (job && !committed) {
                if (device?.gatt?.connected && chars?.control) {
                    try { await bounded(chars.control.writeValueWithResponse(new Uint8Array([3])), null, 3000); } catch (_) { /* disconnect also aborts */ }
                }
                await api('/api/esp32/ota/cancel/' + job, { method: 'POST' });
            }
            if (committed) error.message += ' Quedó un resultado pendiente de verificación; no repitas la instalación por serial.';
            throw error;
        } finally {
            signal?.removeEventListener('abort', abortDevice);
            device?.gatt?.disconnect(); committing(false);
        }
    }
    window.TQTR2OTA = {
        execute, pending,
        async discard(api) {
            const value = pending(); if (!value) return;
            const result = await api('/api/esp32/ota/cancel/' + value.job_id, { method: 'POST' });
            if (!result.ok) throw new Error(result.error); save(null);
        }
    };
})();
