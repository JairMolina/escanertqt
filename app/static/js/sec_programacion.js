/**
 * sec_programacion.js - Sección "Programación" (consola de escritorio): buscar/elegir una R1/R2
 * pendiente y flashearla por USB (Web Serial). R2 usa un catálogo persistente BIN/HEX
 * con perfil HW/FW y nombre personalizado desde inventario, con monitor serial
 * en vivo, pasos visuales y manejo de puertos COM (recordar, refrescar y olvidar los autorizados).
 * Sin cámara, sin CDN (esptool-js vendorizado en /static/js/vendor/esptool-js/).
 */
(function () {
    'use strict';

    const ESPTOOL_URL = '/static/js/vendor/esptool-js/bundle.js';
    const MAC_RE = /(^|[^0-9A-Fa-f])((?:[0-9A-Fa-f]{2}[:\-.]?){5}[0-9A-Fa-f]{2})(?![0-9A-Fa-f])/;
    const VID_NOMBRE = { '10c4': 'Silicon Labs CP210x', '1a86': 'CH340/CH341', '0403': 'FTDI' };
    const PASOS = [
        { id: 'compilar', t: 'Preparar firmware' },
        { id: 'puerto', t: 'Puerto elegido' },
        { id: 'boot', t: 'BOOT + RESET (manual)' },
        { id: 'sync', t: 'Modo programador' },
        { id: 'flash', t: 'Flashear' },
        { id: 'arranque', t: 'Soltar BOOT + RESET' },
        { id: 'mac', t: 'Leer nombre y MAC' },
    ];

    function hexDe(s) { return String(s || '').replace(/[^0-9A-Fa-f]/g, ''); }
    function extraerMac(txt) {
        const m = MAC_RE.exec(txt);
        if (!m) return null;
        const hex = hexDe(m[2]).toUpperCase();
        if (/^0{12}$/.test(hex) || /^F{12}$/.test(hex)) return null;   // relleno: no es una MAC real
        return hex.match(/.{2}/g).join(':');
    }

    function montar(host, ctx) {
        const { T, api, h, icon, toast, util } = ctx;

        const S = { vivo: true, pendientes: [], filtro: '', tarjeta: null, busy: false, puertos: [], puertoSel: null, completed: null, capability: null, otaCommitting: false };
        const timers = new Set();
        const unsubs = [];

        let r1Gate = { ok: true, motivo: '' };
        let firmwareRequest = 0, uploadBusy = false, firmwareLoading = false;
        const firmwareSelect = h('select', { class: 'input', id: 'esp-r2-fw' });
        const firmwareHint = h('p', { class: 'hint', 'aria-live': 'polite' }, 'Cargando firmware…');
        const uploadInput = h('input', { type: 'file', accept: '.bin,.hex', hidden: true });
        const uploadBtn = h('button', { class: 'btn', type: 'button', onclick: () => uploadInput.click() }, 'Subir BIN / HEX');
        const firmwareLabel = h('label', { for: 'esp-r2-fw' }, 'Firmware R2 a programar');
        const firmwarePanel = h('div', { class: 'field' }, firmwareLabel, firmwareSelect, firmwareHint, h('div', { class: 'row wrap' }, uploadBtn, uploadInput));
        let esptoolProm = null;
        function cargarEsptool() { return esptoolProm || (esptoolProm = import(ESPTOOL_URL)); }

        // ------------------------------------------------------------ lista de pendientes (buscar/elegir)
        const buscar = h('input', { class: 'input', type: 'search', id: 'prog-q', autocomplete: 'off', placeholder: 'Número o nombre (p. ej. 0021 o TQT-R2-V30-0021)…' });
        const lista = h('div', { class: 'prog-lista' });
        buscar.addEventListener('input', (e) => { S.filtro = e.target.value; pintarLista(); });

        async function cargarPendientes() {
            const r = await api('/api/pcb?tipo=R2&limit=500');
            if (!S.vivo) return;
            if (!r.ok) { lista.replaceChildren(T.banner('bad', 'alert', r.network ? 'Sin conexión con el servidor.' : `No se pudo cargar: ${r.error}`)); return; }
            S.pendientes = ((r.data && r.data.items) || []).filter((p) => p.tipo === 'R2');   // v1.3.55: este modo es el de R2; la R1 llega con «Programar ESP32 R1»
            if (S.tarjeta && S.completed !== S.tarjeta.id && !S.pendientes.some((p) => p.id === S.tarjeta.id)) { S.tarjeta = null; pintarDetalle(); }
            pintarLista();
        }
        function filtradas() {
            const q = S.filtro.trim().toLowerCase().replace(/^#/, '');
            const l = !q ? S.pendientes : S.pendientes.filter((p) => `${p.nombre} ${p.serie}`.toLowerCase().includes(q));
            return l.slice().sort((a, b) => Number(a.serie) - Number(b.serie) || a.tipo.localeCompare(b.tipo));
        }
        function pintarLista() {
            const items = filtradas();
            lista.replaceChildren();
            lista.classList.toggle('is-busy', S.busy);
            if (!items.length) { lista.appendChild(T.empty('search', S.pendientes.length ? 'Ninguna coincide con la búsqueda' : 'No hay R2 registradas', '')); return; }
            items.forEach((p) => {
                const b = h('button', {
                    class: 'prog-item', type: 'button', disabled: S.busy, 'aria-pressed': String(S.tarjeta && S.tarjeta.id === p.id),
                    onclick: () => seleccionar(p),
                }, T.tipoChip(p.tipo), h('span', { class: 'nm' }, p.nombre), h('span', { class: 'dim' }, p.id_tarjeta_num ? '#' + String(p.id_tarjeta_num).padStart(4, '0') : 'Suelta'));
                lista.appendChild(b);
            });
        }

        // ------------------------------------------------------------ pasos visuales
        const pasoEls = {};
        const pasosEl = h('ol', { class: 'prog-pasos' }, ...PASOS.map((p) => {
            const li = h('li', { class: 'prog-paso', dataset: { e: 'pendiente' } }, h('span', { class: 'prog-paso-ico' }), h('span', { class: 'prog-paso-t' }, p.t));
            pasoEls[p.id] = li;
            return li;
        }));
        function marcarPaso(id, estado) { if (pasoEls[id]) pasoEls[id].dataset.e = estado; }
        function resetPasos() { PASOS.forEach((p) => marcarPaso(p.id, 'pendiente')); }
        function marcarActivoComoError() { const act = PASOS.find((p) => pasoEls[p.id].dataset.e === 'activo'); if (act) marcarPaso(act.id, 'error'); }

        // ------------------------------------------------------------ puertos COM: recuerda, refresca y olvida los autorizados
        const puertosWrap = h('div', { class: 'prog-puertos' });
        function etiquetaPuerto(port) {
            const info = port.getInfo ? port.getInfo() : {};
            if (info.usbVendorId != null) {
                const vid = info.usbVendorId.toString(16).padStart(4, '0'), pid = (info.usbProductId || 0).toString(16).padStart(4, '0');
                return `${VID_NOMBRE[vid] || 'Adaptador USB-Serial'} (${vid}:${pid})`;
            }
            return 'Puerto serial';
        }
        function pintarPuertos() {
            puertosWrap.replaceChildren();
            if (!navigator.serial) { puertosWrap.appendChild(h('div', { class: 'hint err' }, 'Este navegador no soporta Web Serial. Usa Chrome o Edge de escritorio.')); return; }
            S.puertos.forEach((port) => {
                const sel = S.puertoSel === port;
                const fila = h('div', { class: 'prog-puerto', dataset: { sel: String(sel) } },
                    h('button', { type: 'button', class: 'prog-puerto-btn', disabled: S.busy, 'aria-pressed': String(sel), onclick: () => { S.puertoSel = port; pintarPuertos(); } },
                        icon(sel ? 'check' : 'circle'), etiquetaPuerto(port)));
                if (typeof port.forget === 'function') {
                    fila.appendChild(h('button', { type: 'button', class: 'prog-puerto-x', disabled: S.busy, title: 'Olvidar este puerto (el navegador volverá a pedir permiso)', 'aria-label': 'Olvidar este puerto', onclick: async () => { await port.forget(); S.puertos = S.puertos.filter((p) => p !== port); if (S.puertoSel === port) S.puertoSel = null; pintarPuertos(); } }, icon('trash')));
                }
                puertosWrap.appendChild(fila);
            });
            const acc = h('div', { class: 'row wrap' },
                h('button', { class: 'btn btn-sm', type: 'button', disabled: S.busy, onclick: agregarPuerto }, icon('flash'), S.puertos.length ? 'Agregar otro puerto…' : 'Elegir puerto…'),
                h('button', { class: 'btn btn-sm btn-ghost', type: 'button', disabled: S.busy, onclick: refrescarPuertosAutorizados, title: 'Vuelve a leer los puertos ya autorizados por el navegador' }, icon('refresh'), 'Actualizar'));
            puertosWrap.appendChild(acc);
        }
        async function agregarPuerto() {
            try {
                const port = await navigator.serial.requestPort();   // aquí el navegador muestra la lista real de COM de Windows
                if (!S.puertos.includes(port)) S.puertos.push(port);
                S.puertoSel = port;
                pintarPuertos();
            } catch (e) { /* el operador cerró el diálogo del navegador */ }
        }
        async function refrescarPuertosAutorizados() {
            if (!navigator.serial) { pintarPuertos(); return; }
            S.puertos = await navigator.serial.getPorts();
            if (S.puertoSel && !S.puertos.includes(S.puertoSel)) S.puertoSel = null;
            if (!S.puertoSel && S.puertos.length === 1) S.puertoSel = S.puertos[0];
            pintarPuertos();
        }

        // ------------------------------------------------------------ monitor serial + resultado
        const log = h('pre', { class: 'prog-log', 'aria-live': 'polite' }, 'Elige una tarjeta y un puerto, y pulsa «Compilar y flashear».\n');
        const escribir = (linea) => { log.textContent += linea + '\n'; log.scrollTop = log.scrollHeight; };
        const relleno = h('div', { class: 'prog-bar-fill' });
        const barra = h('div', { class: 'prog-bar' }, relleno);
        const otaProgress = h('p', { class: 'hint', hidden: true, role: 'status', 'aria-live': 'polite' });
        const resultado = h('div', { class: 'prog-resultado', hidden: true, role: 'status' });
        const btnFlash = h('button', { class: 'btn btn-primary', type: 'button' }, icon('flash'), 'Compilar y flashear');
        let otaController = null;
        const btnOta = h('button', { class: 'btn btn-primary', type: 'button', onclick: () => ejecutarOta(false) }, 'Actualizar por Bluetooth');
        const btnOtaVerify = h('button', { class: 'btn', type: 'button', onclick: () => ejecutarOta(true) }, 'Verificar OTA pendiente');
        const btnOtaDiscard = h('button', { class: 'btn btn-ghost', type: 'button', onclick: async () => {
            try { await window.TQTR2OTA.discard(api); enableFirmware(); } catch (e) { escribir('✗ ' + e.message); }
        } }, 'Descartar pendiente');
        const btnOtaCancel = h('button', { class: 'btn', type: 'button', onclick: () => otaController?.abort() }, 'Detener actualización Bluetooth');
        const otaHint = h('p', { class: 'hint', 'aria-live': 'polite' });
        const otaPanel = h('div', { class: 'field' }, h('h3', null, 'Actualización por Bluetooth'), otaHint,
            h('div', { class: 'row wrap' }, btnOta, btnOtaVerify, btnOtaDiscard, btnOtaCancel));

        // ---- monitor serial (estilo Arduino IDE): comparte el puerto con el flasheo, nunca a la vez
        const MON_MAX = 2000, BAUDS_MON = [115200, 9600, 57600, 74880, 230400, 460800, 921600], BAUDS_FLASH = [921600, 460800, 230400, 115200];
        const mon = { port: null, reader: null, tarea: null, txt: '', n: 0, raf: 0, abierto: false, ocupado: false };
        const monLog = h('pre', { class: 'prog-mon-log', 'aria-live': 'off', tabindex: '0', role: 'log', 'aria-label': 'Salida del monitor serial' });
        const monBaud = h('select', { id: 'prog-mon-baud', class: 'input' }, ...BAUDS_MON.map((b) => h('option', { value: String(b) }, String(b))));
        const monFin = h('select', { id: 'prog-mon-fin', class: 'input' }, h('option', { value: '\n' }, 'LF (\\n)'), h('option', { value: '\r\n' }, 'CRLF (\\r\\n)'), h('option', { value: '' }, 'Sin fin de línea'));
        const monIn = h('input', { id: 'prog-mon-in', class: 'input', type: 'text', autocomplete: 'off', spellcheck: 'false' });
        const monToggle = h('button', { class: 'btn btn-sm', type: 'button', onclick: () => (mon.abierto ? monDetener() : monAbrir()) }, 'Abrir monitor');
        const monEnviar = h('button', { class: 'btn btn-sm', type: 'button', onclick: () => monEnvia() }, 'Enviar');
        const monReiniciar = h('button', { class: 'btn btn-sm', type: 'button', title: 'Pulsa EN (RTS) con IO0 alto para ver el arranque', onclick: () => monReset() }, 'Reiniciar placa');
        const monLimpiar = h('button', { class: 'btn btn-sm btn-ghost', type: 'button', onclick: () => { mon.txt = ''; mon.n = 0; monPintar(); } }, 'Limpiar');
        const monEstado = h('span', { class: 'hint', role: 'status' }, 'Cerrado');
        const chkAbrir = h('input', { type: 'checkbox', id: 'prog-mon-auto', checked: true });
        let selFlashBaud = null;
        const monPanel = h('details', { class: 'prog-config prog-mon' }, h('summary', null, 'Monitor serial'),
            h('div', { class: 'row wrap' },
                h('div', { class: 'field' }, h('label', { for: 'prog-mon-baud' }, 'Velocidad'), monBaud), monToggle, monReiniciar, monLimpiar, monEstado),
            monLog,
            h('form', { class: 'row wrap prog-mon-envio', onsubmit: (ev) => { ev.preventDefault(); monEnvia(); } },
                h('div', { class: 'field prog-mon-campo' }, h('label', { for: 'prog-mon-in' }, 'Texto a enviar'), monIn),
                h('div', { class: 'field' }, h('label', { for: 'prog-mon-fin' }, 'Fin de línea'), monFin),
                monEnviar),
            h('label', { class: 'prog-mon-chk', for: 'prog-mon-auto' }, chkAbrir, ' Abrir monitor al terminar de grabar'));
        function monPintar() {
            if (mon.raf) return;
            mon.raf = requestAnimationFrame(() => {
                mon.raf = 0; if (!S.vivo) return;
                const abajo = monLog.scrollHeight - monLog.scrollTop - monLog.clientHeight < 24;
                monLog.textContent = mon.txt;
                if (abajo) monLog.scrollTop = monLog.scrollHeight;
            });
        }
        function monAppend(t) {
            if (!t) return;
            mon.txt += t;
            for (let i = t.indexOf('\n'); i >= 0; i = t.indexOf('\n', i + 1)) mon.n++;
            if (mon.n > MON_MAX) {
                let corte = 0, sobran = mon.n - MON_MAX;
                while (sobran-- > 0) corte = mon.txt.indexOf('\n', corte) + 1;
                mon.txt = mon.txt.slice(corte); mon.n = MON_MAX;
            }
            monPintar();
        }
        function monUI() {
            const bloq = S.busy || mon.ocupado;
            monToggle.textContent = mon.abierto ? 'Cerrar monitor' : 'Abrir monitor';
            monToggle.disabled = bloq || (!mon.abierto && !S.puertoSel);
            monBaud.disabled = bloq || mon.abierto;
            monReiniciar.disabled = bloq || !mon.abierto; monEnviar.disabled = bloq || !mon.abierto; monIn.disabled = bloq || !mon.abierto;
            monFin.disabled = bloq; monLimpiar.disabled = false;
            monEstado.textContent = mon.abierto ? `Abierto a ${monBaud.value} baud` : 'Cerrado';
        }
        async function monAbrir() {
            if (mon.abierto || mon.ocupado || S.busy || !S.puertoSel) return;
            mon.ocupado = true; monUI();
            const port = S.puertoSel;
            try {
                try { if (port.readable || port.writable) await port.close(); } catch (e) { /* ya cerrado */ }
                await port.open({ baudRate: +monBaud.value || 115200 });
                mon.port = port; mon.abierto = true;
                const dec = new TextDecoder('utf-8'); const reader = port.readable.getReader(); mon.reader = reader;
                mon.tarea = (async () => {
                    try { for (;;) { const { value, done } = await reader.read(); if (done) break; if (value) monAppend(dec.decode(value, { stream: true })); } }
                    catch (e) { /* cable quitado o cancelado */ }
                    finally { try { reader.releaseLock(); } catch (e) { /* nada */ } }
                    if (mon.reader === reader) await monCerrarPuerto();   // fin inesperado (desconexión)
                })();
            } catch (e) {
                monAppend('✗ No se pudo abrir el puerto: ' + (e && e.message ? e.message : e) + '\n');
                try { await port.close(); } catch (e2) { /* nada */ }
                mon.abierto = false; mon.port = null;
            } finally { mon.ocupado = false; if (S.vivo) monUI(); }
        }
        async function monCerrarPuerto() {
            const port = mon.port; mon.reader = null; mon.port = null; mon.abierto = false;
            try { if (port && (port.readable || port.writable)) await port.close(); } catch (e) { /* nada */ }
            if (S.vivo) monUI();
        }
        /** Libera por completo el puerto (cancela lector, suelta locks, cierra). Seguro de llamar siempre. */
        async function monDetener() {
            const reader = mon.reader, tarea = mon.tarea;
            if (!mon.abierto && !reader) return;
            mon.ocupado = true; mon.reader = null; monUI();
            try { if (reader) await reader.cancel(); } catch (e) { /* nada */ }
            try { if (tarea) await tarea; } catch (e) { /* nada */ }
            mon.tarea = null;
            await monCerrarPuerto();
            mon.ocupado = false; if (S.vivo) monUI();
        }
        async function monEnvia() {
            if (!mon.abierto || !mon.port || !mon.port.writable) return;
            const txt = monIn.value + monFin.value;
            if (!txt) return;
            try {
                const w = mon.port.writable.getWriter();
                try { await w.write(new TextEncoder().encode(txt)); } finally { w.releaseLock(); }
                monIn.value = '';
            } catch (e) { monAppend('✗ No se pudo enviar: ' + (e && e.message ? e.message : e) + '\n'); }
        }
        async function monReset() {
            if (!mon.abierto || !mon.port || !mon.port.setSignals) return;
            const pausa = (ms) => new Promise((r) => setTimeout(r, ms));
            try {   // DTR bajo = IO0 alto (arranque normal); RTS alto = EN bajo (reset)
                await mon.port.setSignals({ dataTerminalReady: false, requestToSend: true }); await pausa(120);
                await mon.port.setSignals({ dataTerminalReady: false, requestToSend: false });
            } catch (e) { monAppend('✗ No se pudo reiniciar por RTS/DTR: ' + (e && e.message ? e.message : e) + '\n'); }
        }
        try { const g = +localStorage.getItem('prog_flash_baud'); selFlashBaud = BAUDS_FLASH.includes(g) ? g : null; } catch (e) { /* sin storage */ }
        const selBaudFlash = h('select', { id: 'prog-flash-baud', class: 'input', onchange: () => { try { localStorage.setItem('prog_flash_baud', selBaudFlash.value); } catch (e) { /* nada */ } } },
            ...BAUDS_FLASH.map((b) => h('option', { value: String(b) }, String(b))));
        selBaudFlash.value = String(selFlashBaud || 921600);
        unsubs.push(() => { cancelAnimationFrame(mon.raf); monDetener(); });

        function enableFirmware() {
            const blocked = S.busy || uploadBusy || firmwareLoading;
            firmwareSelect.disabled = blocked || !firmwareSelect.options.length;
            uploadBtn.disabled = blocked;
            btnFlash.disabled = blocked || !S.tarjeta || S.completed === S.tarjeta.id || !firmwareSelect.value || (S.tarjeta?.tipo === 'R1' && !r1Gate.ok);
            btnFlash.textContent = 'Instalar por serial';
            const esR1 = S.tarjeta?.tipo === 'R1';   // R1: firmware fijo (ESP32_BLE_SERIAL), sin catálogo ni subida
            firmwareLabel.textContent = esR1 ? 'Firmware ESP32 de la R1 (fijo)' : 'Firmware R2 a programar';
            uploadBtn.hidden = esR1; firmwareSelect.hidden = esR1;
            selBaudFlash.disabled = blocked; monUI();
            const saved = window.TQTR2OTA?.pending();
            const ownPending = saved?.pcb_id === S.tarjeta?.id;
            const selectedOta = firmwareSelect.selectedOptions[0]?.dataset.ota === '1';
            btnOta.disabled = blocked || !S.capability?.eligible || !selectedOta || Boolean(saved) || !navigator.bluetooth;
            btnOtaVerify.hidden = !ownPending; btnOtaDiscard.hidden = !saved;
            btnOtaVerify.disabled = btnOtaDiscard.disabled = blocked;
            btnOtaCancel.hidden = !otaController; btnOtaCancel.disabled = S.otaCommitting;
            otaPanel.hidden = S.tarjeta?.tipo !== 'R2';
            otaHint.textContent = ownPending ? 'Hay una actualización pendiente de comprobar. Conecta la R2 encendida para verificarla.' :
                saved ? 'Verifica o descarta la OTA pendiente de ' + (saved.nombre || 'otra R2') + ' antes de iniciar otra.' :
                S.capability?.eligible ? 'FW ' + S.capability.current_fw + ': admite OTA. Mantén alimentación estable y libera la conexión Bluetooth de la R1 durante la actualización.' :
                'Primera instalación: instala FW 4.1 o superior por serial desde esta web. Después podrás actualizar por Bluetooth.';
        }
        async function loadFirmwares(reset = false) {
            const n = ++firmwareRequest;
            firmwareLoading = true; enableFirmware();
            const selected = firmwareSelect.value;
            const tipo = S.tarjeta?.tipo === 'R1' ? 'R1' : 'R2';
            const hw = tipo === 'R2' ? S.tarjeta?.version || '' : '';
            const [r, capability] = await Promise.all([
                api('/api/esp32/firmwares?tipo=' + tipo + '&hw=' + encodeURIComponent(hw)),
                S.tarjeta?.tipo === 'R2' ? api('/api/esp32/ota/capability/' + S.tarjeta.id) : Promise.resolve(null)
            ]);
            if (!S.vivo || n !== firmwareRequest) return;
            firmwareLoading = false;
            S.capability = capability?.ok ? capability.data : null;
            r1Gate = { ok: true, motivo: '' };
            if (tipo === 'R1') { const g = await api('/api/esp32/r1-gate/' + S.tarjeta.id); if (n !== firmwareRequest) return; r1Gate = g.ok ? g.data : { ok: false, motivo: g.error }; }
            if (!r.ok) {
                firmwareSelect.replaceChildren(); firmwareHint.textContent = r.error;
                enableFirmware(); return;
            }
            firmwareSelect.replaceChildren(...r.data.items.map(f => h('option', { value: f.id, dataset: { ota: String(f.ota_protocol || 0) } },
                `FW ${f.fw}` + (f.hw ? ` · HW ${f.hw}` : '') + (f.ota_protocol ? ' · OTA' : '') + (f.id === r.data.default_id ? ' · más reciente' : ''))));
            firmwareSelect.value = !reset && r.data.items.some(f => f.id === selected) ? selected : (r.data.default_id || '');
            firmwareHint.textContent = tipo === 'R1' ? (r.data.items.length ? `ESP32_BLE_SERIAL FW ${r.data.items[0].fw}: es el mismo para todas las R1 (el nombre BLE lo graba el STM32). Se verifica solo la MAC.` : 'Falta el firmware fijo de la R1 en el servidor (firmware/esp32_r1).')
                : r.data.items.length ? 'El nombre se toma de la R2 elegida; HW y FW se leen del archivo. Puedes elegir una versión anterior.' : 'No hay firmware compatible con el hardware de esta R2.';
            if (!r1Gate.ok) firmwareHint.textContent = r1Gate.motivo;
            enableFirmware();
        }
        uploadInput.addEventListener('change', async () => {
            const file = uploadInput.files?.[0]; uploadInput.value = '';
            if (!file || S.busy || uploadBusy) return;
            uploadBusy = true; enableFirmware();
            try {
                if (file.size > 12 * 1024 * 1024) throw new Error('El archivo excede 12 MB.');
                const bytes = new Uint8Array(await file.arrayBuffer());
                let binary = '';
                for (let i = 0; i < bytes.length; i += 8192) binary += String.fromCharCode(...bytes.subarray(i, i+8192));
                const tipo = S.tarjeta?.tipo === 'R1' ? 'R1' : 'R2';
                const body = { filename: file.name, contenido: btoa(binary), tipo };
                const r = await api('/api/esp32/firmwares/analizar', { method: 'POST', body });
                if (!r.ok) throw new Error(r.error);
                if (!S.vivo) return;
                const d = r.data;
                let saved = false;
                let saving = false;
                const error = h('div', { role: 'alert' });
                await new Promise(resolve => {
                    const modal = T.sheet({ title: 'Guardar firmware ' + tipo,
                    body: h('div', null, h('p', null, `${file.name} · FW ${d.fw}` + (d.hw ? ` · HW ${d.hw}` : '')),
                        h('p', { class: 'hint' }, tipo === 'R1' ? 'El archivo se guardará tal cual, sin modificarlo. La R1 se verifica solo por su MAC.' : 'El archivo se guardará sin identidad ni credenciales de unidad. Al instalar se colocarán los datos de la R2 del inventario.'),
                        h('p', { class: 'hint' }, 'Módulo: ' + d.module), error),
                    onClose: resolve,
                    actions: [{ label: 'Guardar firmware', kind: 'primary', onClick: async () => {
                        saving = true;
                        const cancel = modal.el.querySelector('.btn-ghost'); cancel.disabled = true;
                        try {
                            const res = await api('/api/esp32/firmwares', { method: 'POST', body });
                            if (!res.ok) { error.replaceChildren(T.banner('bad', 'alert', res.error)); return false; }
                            saved = true; resolve(); return true;
                        } finally { saving = false; cancel.disabled = false; }
                    } }, { label: 'Cancelar', kind: 'ghost', onClick: () => { if (saving) return false; resolve(); return true; } }] });
                    modal.el.addEventListener('keydown', e => {
                        if (e.key === 'Escape' && saving) { e.preventDefault(); e.stopPropagation(); }
                        if (e.key !== 'Tab') return;
                        const buttons = [...modal.el.querySelectorAll('button:not(:disabled)')];
                        const first = buttons[0], last = buttons[buttons.length-1];
                        if (!first) return;
                        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
                        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
                    });
                    modal.el.previousElementSibling.addEventListener('click', e => {
                        if (saving) { e.preventDefault(); e.stopImmediatePropagation(); }
                    }, true);
                });
                if (saved && S.vivo) { await loadFirmwares(true); toast('Firmware guardado; se eligió el más reciente compatible.', { kind: 'ok' }); }
            } catch (e) { toast(e.message, { kind: 'bad' }); }
            finally { uploadBusy = false; if (S.vivo) enableFirmware(); }
        });
        firmwareSelect.addEventListener('change', enableFirmware);
        async function compilarFirmware(pcb) {
            const resp = await fetch(`/api/esp32/bin/${pcb.id}?firmware_id=${encodeURIComponent(firmwareSelect.value)}`, { method: 'POST' });
            if (!resp.ok) {
                let msg = `Error ${resp.status}`;
                try { const j = await resp.json(); msg = j.detail || msg; } catch (e) { /* sin JSON */ }
                throw new Error('No se pudo preparar el firmware: ' + msg);
            }
            const hd = k => resp.headers.get('X-TQT-' + k) || '';
            return { bin: new Uint8Array(await resp.arrayBuffer()), nombreBle: hd('Nombre-Ble'), firmware: hd('Firmware'), hardware: hd('Hardware'), firmwareId: hd('Firmware-Id'), sha: hd('Sha256') || hd('Fuente-Sha256'), otaProtocol: Number(hd('OTA-Protocol') || 0), keyId: hd('Key-Id') };
        }
        async function leerMacPorSerial(port, requireProfile = false) {
            await monDetener();
            try { if (port.readable || port.writable) await port.close(); } catch (e) { /* ya estaba cerrado */ }
            await port.open({ baudRate: 115200 });
            let mac = null, nombre = null, hardware = null, firmware = null, retry = null, otaProtocol = 0, keyId = '';
            try {
                await new Promise((res) => setTimeout(res, 300));
                const ask = async () => {
                    const writer = port.writable.getWriter();
                    try { await writer.write(new TextEncoder().encode(requireProfile ? 'INFO\n' : 'MAC\n')); }
                    finally { writer.releaseLock(); }
                };
                await ask();
                if (requireProfile) retry = setInterval(() => ask().catch(() => {}), 1000);
                const decoder = new TextDecoderStream();
                const listo = port.readable.pipeTo(decoder.writable).catch(() => {});
                const reader = decoder.readable.getReader();
                let buffer = '';
                const limite = Date.now() + 8000;
                try {
                    while (Date.now() < limite && !mac) {
                        const espera = new Promise((res) => setTimeout(() => res({ timeout: true }), Math.max(50, limite - Date.now())));
                        const paso = await Promise.race([reader.read(), espera]);
                        if (paso.timeout || paso.done) break;
                        buffer += paso.value || '';
                        const lineas = buffer.split('\n');
                        buffer = lineas.pop();
                        for (const linea of lineas) {
                            monAppend(linea + '\n');
                            // v1.3.62: la R2 responde «<nombre> MAC: AA:BB:…»; se guarda la línea completa para validar el nombre
                            if (requireProfile) {
                                if (!linea.startsWith('TQT_INFO ')) continue;
                                try { const info = JSON.parse(linea.slice(9));
                                    mac = extraerMac(info.mac || ''); nombre = info.nombre; hardware = info.hw; firmware = info.fw; otaProtocol = info.ota_protocol || 0; keyId = info.key_id || '';
                                } catch (e) { continue; }
                                if (mac) break;
                                continue;
                            }
                            const m = extraerMac(linea); if (m) { mac = m; nombre = (/^\s*(\S+)\s+MAC:/i.exec(linea) || [])[1] || null; break; }
                        }
                    }
                } finally {
                    try { await reader.cancel(); } catch (e) { /* nada */ }
                    try { await listo; } catch (e) { /* nada */ }
                }
            } finally {
                clearInterval(retry);
                try { await port.close(); } catch (e) { /* nada */ }
            }
            return { mac, nombre, hardware, firmware, otaProtocol, keyId };
        }
        /** Hoja de confirmación dentro del flujo (sin confirm()): resuelve true al continuar, false al cancelar. */
        function confirmar(titulo, texto, ok) {
            return new Promise((res) => {
                let hecho = false; const fin = (v) => { if (!hecho) { hecho = true; res(v); } return true; };
                T.sheet({ title: titulo, body: h('p', null, texto), onClose: () => fin(false),
                    actions: [{ label: 'Cancelar', kind: 'ghost', onClick: () => fin(false) }, { label: ok || 'Listo, continuar', kind: 'primary', onClick: () => fin(true) }] });
            });
        }

        function mostrarResultado(pcb, mac, fw) {
            S.completed = pcb.id;
            resultado.hidden = false;
            const macTxt = h('span', { class: 'prog-mac' }, mac);
            resultado.replaceChildren(
                T.banner('ok', 'check', `${pcb.nombre}: programada correctamente.`),
                fw.hardware ? h('p', { class: 'hint' }, `FW ${fw.firmware} · HW ${fw.hardware} · ${fw.nombreBle}`) : null,
                h('div', { class: 'prog-mac-row' }, h('span', { class: 'hint' }, 'MAC:'), macTxt,
                    h('button', { class: 'btn btn-sm', type: 'button', onclick: () => util.copiar(mac, 'MAC copiada') }, icon('paste'), 'Copiar')),
                h('button', { class: 'btn', type: 'button', onclick: () => { S.tarjeta = null; pintarDetalle(); buscar.focus(); } }, 'Elegir otra tarjeta'));
        }

        async function ejecutar() {
            if (!S.tarjeta || S.completed === S.tarjeta.id || S.busy || uploadBusy || firmwareLoading) return;
            if (!navigator.serial) { escribir('✗ Este navegador no soporta Web Serial. Usa Chrome o Edge de escritorio.'); return; }
            const port = S.puertoSel;
            if (!port) { escribir('✗ Elige primero el puerto de la tarjeta.'); return; }
            S.busy = true; btnFlash.disabled = true; resultado.hidden = true; relleno.style.width = '0';
            otaProgress.hidden = true;
            pintarLista(); pintarPuertos(); resetPasos(); enableFirmware();
            const pcb = S.tarjeta;
            let transport = null;
            try {
                await monDetener();   // el monitor libera el puerto antes de flashear
                marcarPaso('compilar', 'activo');
                escribir(pcb.tipo === 'R2' ? 'Preparando firmware y nombre desde inventario…' : 'Preparando firmware fijo de R1…');
                const fw = await compilarFirmware(pcb); const binario = fw.bin; const esR2 = pcb.tipo === 'R2';
                marcarPaso('compilar', 'ok');
                escribir(`Firmware listo (${(binario.length / 1024).toFixed(0)} KB)${fw.firmware ? ' · FW ' + fw.firmware + (fw.hardware ? ' · HW ' + fw.hardware : '') : ''}${fw.nombreBle ? ' · nombre BLE ' + fw.nombreBle : ''}.`);

                marcarPaso('puerto', 'ok');
                {
                    marcarPaso('boot', 'activo');
                    if (!await confirmar('Modo descarga de la ' + pcb.tipo, 'Conecta el USB–TTL, mantén GPIO0 (BOOT) en bajo y haz RESET. Confirma cuando esté listo.', 'Ya está en BOOT')) throw new Error('Cancelado antes de programar: no se grabó nada.');
                }
                marcarPaso('boot', 'ok');
                const esptool = await cargarEsptool();
                // sincroniza siempre a 115200 (romBaudrate) y sube a la velocidad elegida para los datos
                let usar = +selBaudFlash.value || 115200, intento = 0, loader = null, escritoAlgo = false;
                const terminal = { clean() { /* nada */ }, writeLine: (s) => { escribir(s); monAppend(s + '\n'); }, write: (s) => { const t = String(s).replace(/\n$/, ''); escribir(t); monAppend(t + '\n'); } };
                for (;;) {
                    transport = new esptool.Transport(port, true);
                    loader = new esptool.ESPLoader({ transport, baudrate: usar, romBaudrate: 115200, terminal });
                    try {
                        marcarPaso('sync', 'activo');
                        escribir('Sincronizando… si no avanza, pon la tarjeta en modo programador.');
                        const chip = await loader.main();
                        marcarPaso('sync', 'ok');
                        escribir('Tarjeta detectada: ' + chip + (usar > 115200 ? ` · datos a ${usar} baud` : ''));

                        marcarPaso('flash', 'activo');
                        escribir('Flasheando (no desconectes el USB)…');
                        let pct = -1;
                        await loader.writeFlash({
                            fileArray: esR2 ? [{ data: binario, address: 0x0 }] : [{ data: binario.slice(0, 0x9000), address: 0x0 }, { data: binario.slice(0xE000), address: 0xE000 }],   // R1: como Arduino IDE, no borra NVS (0x9000–0xE000) donde vive el nombre BLE que pone el STM32
                            flashMode: 'keep', flashFreq: 'keep', flashSize: 'keep',
                            eraseAll: false, compress: true,
                            reportProgress: (_i, escrito, total) => {
                                if (escrito > 0) escritoAlgo = true;
                                const p = Math.round((escrito / total) * 100); if (p !== pct) { pct = p; relleno.style.width = p + '%'; }
                            },
                        });
                        break;
                    } catch (err) {
                        try { await transport.disconnect(); } catch (e) { /* ya cerrado */ }
                        transport = null;
                        if (usar <= 115200 || intento > 0) throw err;
                        escribir(`⚠ Falló a ${usar} baud (${err && err.message ? err.message : err}). Reintentando a 115200…`);
                        if (!await confirmar('Reintentar a 115200', (escritoAlgo ? 'La grabación se interrumpió a alta velocidad. ' : 'No se pudo sincronizar a alta velocidad. ') + 'Vuelve a poner la R2 en modo descarga (GPIO0/BOOT en bajo + RESET) y confirma para reintentar a 115200.', 'Ya está en BOOT')) throw err;
                        usar = 115200; intento++; escritoAlgo = false; relleno.style.width = '0';
                    }
                }
                escribir('Flasheo terminado. Reiniciando la tarjeta…');
                await loader.after('hard_reset');
                try { await transport.disconnect(); } catch (e) { /* ya se cerró al reiniciar */ }
                marcarPaso('flash', 'ok');

                {
                    marcarPaso('arranque', 'activo');
                    if (!await confirmar('Arranque normal', 'Suelta BOOT (GPIO0) y haz RESET para que arranque el firmware. Confirma cuando esté listo.', 'Ya reinicié')) throw new Error('Grabado, pero sin verificar: falta arrancar en modo normal y leer la MAC.');
                }
                marcarPaso('arranque', 'ok');
                marcarPaso('mac', 'activo');
                escribir('Leyendo nombre y MAC por USB…');
                const leido = await leerMacPorSerial(port, esR2); const mac = leido.mac;
                if (!mac) throw new Error('No se detectó la MAC por USB (sin comunicación). Revisa que soltaste BOOT y reiniciaste; puedes teclearla en «MAC y firmware».');
                if (esR2 && fw.nombreBle && leido.nombre !== fw.nombreBle) throw new Error(`Identidad incorrecta: la placa respondió «${leido.nombre || 'sin nombre'}» y se esperaba «${fw.nombreBle}». No se guardó la MAC.`);
                if (esR2 && (leido.hardware !== fw.hardware || leido.firmware !== fw.firmware)) throw new Error('La versión HW/FW que responde la R2 no coincide con el archivo. No se guardó el resultado.');
                if (esR2 && fw.otaProtocol && (leido.otaProtocol !== fw.otaProtocol || leido.keyId !== fw.keyId)) throw new Error('La R2 no confirmó su credencial OTA. No se guardó el resultado.');
                if (pcb.mac && pcb.mac.toUpperCase() !== mac && !await confirmar('MAC diferente', `${pcb.nombre} ya tiene la MAC ${pcb.mac} y la placa respondió ${mac}. ¿Reemplazarla? Hazlo solo si confirmaste que es la misma placa física.`, 'Reemplazar MAC')) throw new Error('MAC en conflicto: no se cambió el registro.');
                marcarPaso('mac', 'ok');
                escribir('MAC leída: ' + mac + (leido.nombre ? ' · nombre ' + leido.nombre : ''));

                const cuerpo = { mac }; if (!esR2 && fw.firmwareId) cuerpo.firmware_id = fw.firmwareId;   // R1: solo MAC; pcb.firmware es el del STM32
                if (esR2 && fw.firmware) Object.assign(cuerpo, { firmware: fw.firmware, firmware_id: fw.firmwareId, nombre_verificado: leido.nombre, hardware_verificado: leido.hardware, ota_protocol_verificado: leido.otaProtocol, key_id_verificado: leido.keyId });   
                const res = await api(`/api/pcb/${pcb.id}/programacion`, { method: 'PUT', body: cuerpo });
                if (!res.ok) throw new Error(res.network ? 'Sin conexión con el servidor: no se guardó.' : res.error);
                escribir('Guardado ✓');
                toast(`${pcb.nombre}: MAC ${mac} guardada`, { kind: 'ok' });
                S.tarjeta = Object.assign({}, pcb, res.data);
                mostrarResultado(S.tarjeta, mac, fw);
                await loadFirmwares();
            } catch (e) {
                marcarActivoComoError();
                escribir('✗ ' + (e && e.message ? e.message : String(e)));
            } finally {
                if (transport) { try { await transport.disconnect(); } catch (e) { /* ya cerrado */ } }
                try { if (port.readable || port.writable) await port.close(); } catch (e) { /* sin puerto abierto */ }
                S.busy = false; enableFirmware();
                pintarLista(); pintarPuertos();
                if (S.vivo && chkAbrir.checked && S.puertoSel === port) monAbrir();   // ver el arranque tras grabar
            }
        }
        btnFlash.addEventListener('click', ejecutar);
        async function ejecutarOta(recovery) {
            if (!S.tarjeta || S.busy || uploadBusy || firmwareLoading || !window.TQTR2OTA) return;
            const pcb = S.tarjeta, firmwareId = firmwareSelect.value;
            otaController = new AbortController(); S.busy = true; S.completed = null;
            resultado.hidden = true; log.textContent = ''; relleno.style.width = '0';
            otaProgress.hidden = false; otaProgress.textContent = 'Preparando actualización Bluetooth…';
            let lastProgressUpdate = 0;
            enableFirmware(); pintarLista(); pintarPuertos(); resetPasos();
            try {
                const result = await window.TQTR2OTA.execute({ pcb, firmwareId, api,
                    signal: otaController.signal, stage: text => { escribir(text + '…'); otaProgress.textContent = text + '…'; },
                    progress: (done, total, timing = { elapsed: 0 }) => {
                        const percent = Math.floor(done / total * 100);
                        relleno.style.width = percent + '%';
                        const now = performance.now();
                        if (lastProgressUpdate && done > 0 && done < total && now - lastProgressUpdate < 1000) return;
                        lastProgressUpdate = now;
                        const rate = timing.elapsed > 0 ? done / timing.elapsed : 0;
                        const remaining = rate > 0 ? Math.ceil((total - done) / rate) : 0;
                        const eta = remaining >= 60 ? Math.ceil(remaining / 60) + ' min' : remaining + ' s';
                        otaProgress.textContent = `Enviado ${percent}% · ${Math.round(done / 1024)} / ${Math.round(total / 1024)} KB` +
                            (rate > 0 ? ` · ${(rate / 1024).toFixed(1)} KB/s` : '') +
                            (timing.elapsed >= 3 && done < total ? ` · Restan aproximadamente ${eta}` : '');
                    },
                    committing: value => { S.otaCommitting = value; enableFirmware(); } }, recovery);
                S.tarjeta = result.pcb;
                escribir('OTA verificada ✓ · FW ' + result.fw);
                otaProgress.textContent = 'Actualización y nuevo arranque verificados · FW ' + result.fw;
                mostrarResultado(S.tarjeta, S.tarjeta.mac, { firmware: result.fw, hardware: S.tarjeta.version, nombreBle: S.tarjeta.nombre.replace(/-/g, '_') });
                toast('R2 actualizada y verificada por Bluetooth', { kind: 'ok' });
            } catch (e) { escribir('✗ ' + e.message); otaProgress.textContent = e.message; }
            finally { S.busy = false; otaController = null; S.otaCommitting = false; await loadFirmwares(); enableFirmware(); pintarLista(); pintarPuertos(); }
        }

        // ------------------------------------------------------------ panel de detalle
        const cabecera = h('div', { class: 'prog-cab' });
        const detalle = h('div', { class: 'prog-detalle', hidden: true },
            cabecera, pasosEl,
            h('div', { class: 'field' }, h('label', null, 'Puerto de la tarjeta'), puertosWrap,
                h('div', { class: 'hint' }, 'Solo se listan aquí los puertos que ya autorizaste antes. «Elegir puerto» abre la lista real de puertos COM de Windows (el navegador la pide una vez por puerto; luego queda recordado).')),
            h('div', { class: 'hint' }, 'Antes de sincronizar, pon la tarjeta en modo programador; el registro avisa si no avanza.'),
            h('div', { class: 'field' }, h('label', { for: 'prog-flash-baud' }, 'Velocidad de grabación'), selBaudFlash,
                h('div', { class: 'hint' }, 'Se sincroniza a 115200 y los datos van a esta velocidad; si falla, reintenta a 115200.')),
            log, barra, otaProgress, h('div', { class: 'row' }, btnFlash), monPanel, otaPanel, resultado);
        const vacio = T.empty('flash', 'Elige una tarjeta', 'Búscala por número o nombre a la izquierda, o elige una de la lista.');

        function seleccionar(p) {
            if (S.busy || uploadBusy) return;
            S.tarjeta = p; S.capability = null;
            otaProgress.hidden = true;
            S.completed = null;
            loadFirmwares(true);
            pintarDetalle();
            pintarLista();
        }
        function pintarDetalle() {
                        enableFirmware();
            if (!S.tarjeta) { detalle.hidden = true; vacio.hidden = false; return; }
            vacio.hidden = true; detalle.hidden = false;
            const p = S.tarjeta;
            cabecera.replaceChildren(T.tipoChip(p.tipo), h('span', { class: 'prog-nm' }, p.nombre),
                h('span', { class: 'dim' }, `Hardware V${p.version}${p.id_tarjeta_num ? ' · Tarjeta #' + String(p.id_tarjeta_num).padStart(4, '0') : ' · suelta'}`));
            resetPasos(); log.textContent = ''; relleno.style.width = '0'; resultado.hidden = true;
        }

        // ------------------------------------------------------------ montaje
        host.classList.add('prog');
        host.append(h('div', { class: 'prog-wrap' },
            h('div', { class: 'prog-panel' }, h('h2', null, 'Elige una tarjeta'), h('div', { class: 'field' }, h('label', { for: 'prog-q' }, 'Buscar'), buscar), lista),
            h('div', { class: 'prog-panel prog-panel-detalle' }, firmwarePanel, vacio, detalle)));

        const espHost = host.lastElementChild;
        const stmHost = h('div');
        // v1.3.54: «Programar ESP32 R1» del panel STM32 abre el flujo ESP32 con la misma R1 elegida
        const stm = window.TQTSTM32(stmHost, Object.assign({}, ctx, { tipo: 'R1', programarEsp32(p) { if (S.busy) return; modo('esp'); seleccionar(p); } }));
        // v1.3.55: R3 (STM32 «TIMER») con el mismo agente J-Link y firmware fijo
        const r3Host = h('div');
        const stm3 = window.TQTSTM32(r3Host, Object.assign({}, ctx, { tipo: 'R3' }));
        const MODOS = {
            stm: { host: stmHost, btn: h('button', { class: 'btn', type: 'button', onclick: () => modo('stm') }, 'R1 · STM32 / J-Link') },
            esp: { host: espHost, btn: h('button', { class: 'btn', type: 'button', onclick: () => modo('esp') }, 'R2 · ESP32 · USB serial') },
            r3: { host: r3Host, btn: h('button', { class: 'btn', type: 'button', onclick: () => modo('r3') }, 'R3 · STM32 / J-Link') },
        };
        let actual = 'stm';
        function modo(id) {
            if (S.busy || uploadBusy || stm.ocupada() || stm3.ocupada()) return;
            actual = id;
            Object.entries(MODOS).forEach(([k, m]) => {
                m.host.hidden = k !== id; m.btn.classList.toggle('btn-primary', k === id); m.btn.setAttribute('aria-pressed', String(k === id));
            });
        }
        host.prepend(h('div', { class: 'row wrap' }, MODOS.esp.btn, MODOS.stm.btn, MODOS.r3.btn));
        host.append(stmHost, r3Host); modo('stm');

        cargarPendientes(); loadFirmwares();
        refrescarPuertosAutorizados();

        let tRec = null;
        function recargarSuave() { clearTimeout(tRec); tRec = setTimeout(() => { timers.delete(tRec); if (S.vivo && !S.busy) cargarPendientes(); }, 250); timers.add(tRec); }
        const wsc = ctx.ws || (T.ws && T.ws());
        if (wsc && wsc.on) ['PCB_ACTUALIZADA', 'PCB_RECIBIDA', 'PCB_ELIMINADA'].forEach((ev) => unsubs.push(wsc.on(ev, recargarSuave)));
        if (navigator.serial) { const onConn = () => refrescarPuertosAutorizados(); navigator.serial.addEventListener('connect', onConn); navigator.serial.addEventListener('disconnect', onConn); unsubs.push(() => { navigator.serial.removeEventListener('connect', onConn); navigator.serial.removeEventListener('disconnect', onConn); }); }

        return {
            actualizar() { stm.actualizar(); stm3.actualizar(); if (!S.busy && !uploadBusy) { cargarPendientes(); loadFirmwares(); } },
            escaneo(codigo) { if (actual === 'r3') return stm3.escaneo(codigo); modo('stm'); return stm.escaneo(codigo); },
            desmontar() {
                S.vivo = false;
                if (!S.otaCommitting) otaController?.abort();
                stm.desmontar(); stm3.desmontar();
                timers.forEach((t) => clearTimeout(t)); timers.clear();
                unsubs.forEach((u) => { try { u(); } catch (e) { /* nada */ } });
                host.replaceChildren();
            },
        };
    }

    const def = { id: 'programacion', titulo: 'Programación', icono: 'flash', grupo: 'operacion', orden: 30, montar };
    if (window.TQTEscritorio && window.TQTEscritorio.registrar) window.TQTEscritorio.registrar(def);
    else { (window.__TQTSecciones = window.__TQTSecciones || []).push(def); }
})();
