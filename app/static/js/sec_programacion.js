/**
 * sec_programacion.js - Sección "Programación" (consola de escritorio): buscar/elegir una R1/R2
 * pendiente y flashearla por USB (Web Serial) con el firmware fuente de `firmware/` (siempre el más
 * reciente; aquí no se elige versión de firmware, eso es cosa de "MAC y firmware"), con monitor serial
 * en vivo, pasos visuales y manejo de puertos COM (recordar, refrescar y olvidar los autorizados).
 * Sin cámara, sin CDN (esptool-js vendorizado en /static/js/vendor/esptool-js/).
 */
(function () {
    'use strict';

    const ESPTOOL_URL = '/static/js/vendor/esptool-js/bundle.js';
    const MAC_RE = /(^|[^0-9A-Fa-f])((?:[0-9A-Fa-f]{2}[:\-.]?){5}[0-9A-Fa-f]{2})(?![0-9A-Fa-f])/;
    const VID_NOMBRE = { '10c4': 'Silicon Labs CP210x', '1a86': 'CH340/CH341', '0403': 'FTDI' };
    const PASOS = [
        { id: 'compilar', t: 'Compilar firmware' },
        { id: 'puerto', t: 'Puerto elegido' },
        { id: 'sync', t: 'Modo programador' },
        { id: 'flash', t: 'Flashear' },
        { id: 'mac', t: 'Leer MAC' },
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

        const S = { vivo: true, pendientes: [], filtro: '', tarjeta: null, busy: false, puertos: [], puertoSel: null };
        const timers = new Set();
        const unsubs = [];

        let esptoolProm = null;
        function cargarEsptool() { return esptoolProm || (esptoolProm = import(ESPTOOL_URL)); }

        // ------------------------------------------------------------ lista de pendientes (buscar/elegir)
        const buscar = h('input', { class: 'input', type: 'search', id: 'prog-q', autocomplete: 'off', placeholder: 'Número o nombre (p. ej. 0021 o TQT-R2-V30-0021)…' });
        const lista = h('div', { class: 'prog-lista' });
        buscar.addEventListener('input', (e) => { S.filtro = e.target.value; pintarLista(); });

        async function cargarPendientes() {
            const r = await api('/api/pcb?sin_mac=1&limit=500');
            if (!S.vivo) return;
            if (!r.ok) { lista.replaceChildren(T.banner('bad', 'alert', r.network ? 'Sin conexión con el servidor.' : `No se pudo cargar: ${r.error}`)); return; }
            S.pendientes = ((r.data && r.data.items) || []).filter((p) => p.tipo === 'R1' || p.tipo === 'R2');
            if (S.tarjeta && !S.pendientes.some((p) => p.id === S.tarjeta.id)) { S.tarjeta = null; pintarDetalle(); }
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
            if (!items.length) { lista.appendChild(T.empty('search', S.pendientes.length ? 'Ninguna coincide con la búsqueda' : 'No hay R1 ni R2 pendientes de MAC', '')); return; }
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
        const resultado = h('div', { class: 'prog-resultado', hidden: true, role: 'status' });
        const btnFlash = h('button', { class: 'btn btn-primary', type: 'button' }, icon('flash'), 'Compilar y flashear');

        async function compilarFirmware(pcb) {
            const resp = await fetch('/api/firmware/compilar', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ tipo: pcb.tipo, numero: pcb.serie }),
            });
            if (!resp.ok) {
                let msg = `Error ${resp.status}`;
                try { const j = await resp.json(); msg = (j && j.detail) || msg; } catch (e) { /* sin cuerpo JSON */ }
                throw new Error('No se pudo compilar el firmware: ' + msg);
            }
            return new Uint8Array(await resp.arrayBuffer());
        }
        async function leerMacPorSerial(port) {
            try { if (port.readable || port.writable) await port.close(); } catch (e) { /* ya estaba cerrado */ }
            await port.open({ baudRate: 115200 });
            let mac = null;
            try {
                await new Promise((res) => setTimeout(res, 300));
                const writer = port.writable.getWriter();
                try { await writer.write(new TextEncoder().encode('MAC\n')); } finally { writer.releaseLock(); }
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
                        for (const linea of lineas) { const m = extraerMac(linea); if (m) { mac = m; break; } }
                    }
                } finally {
                    try { await reader.cancel(); } catch (e) { /* nada */ }
                    try { await listo; } catch (e) { /* nada */ }
                }
            } finally {
                try { await port.close(); } catch (e) { /* nada */ }
            }
            return mac;
        }

        function mostrarResultado(pcb, mac) {
            resultado.hidden = false;
            const macTxt = h('span', { class: 'prog-mac' }, mac);
            resultado.replaceChildren(
                T.banner('ok', 'check', `${pcb.nombre}: programada correctamente.`),
                h('div', { class: 'prog-mac-row' }, h('span', { class: 'hint' }, 'MAC:'), macTxt,
                    h('button', { class: 'btn btn-sm', type: 'button', onclick: () => util.copiar(mac, 'MAC copiada') }, icon('paste'), 'Copiar')),
                h('button', { class: 'btn', type: 'button', onclick: () => { S.tarjeta = null; pintarDetalle(); buscar.focus(); } }, 'Elegir otra tarjeta'));
        }

        async function ejecutar() {
            if (!S.tarjeta || S.busy) return;
            if (!navigator.serial) { escribir('✗ Este navegador no soporta Web Serial. Usa Chrome o Edge de escritorio.'); return; }
            const port = S.puertoSel;
            if (!port) { escribir('✗ Elige primero el puerto de la tarjeta.'); return; }
            S.busy = true; btnFlash.disabled = true; resultado.hidden = true; relleno.style.width = '0';
            pintarLista(); pintarPuertos(); resetPasos();
            const pcb = S.tarjeta;
            try {
                marcarPaso('compilar', 'activo');
                escribir(`Compilando firmware de ${pcb.tipo}…`);
                const binario = await compilarFirmware(pcb);
                marcarPaso('compilar', 'ok');
                escribir(`Firmware listo (${(binario.length / 1024).toFixed(0)} KB).`);

                marcarPaso('puerto', 'ok');
                const esptool = await cargarEsptool();
                const transport = new esptool.Transport(port, true);
                const loader = new esptool.ESPLoader({
                    transport, baudrate: 115200,
                    terminal: { clean() { /* nada */ }, writeLine: escribir, write: (s) => escribir(String(s).replace(/\n$/, '')) },
                });
                marcarPaso('sync', 'activo');
                escribir('Sincronizando… si no avanza, pon la tarjeta en modo programador.');
                const chip = await loader.main();
                marcarPaso('sync', 'ok');
                escribir('Tarjeta detectada: ' + chip);

                marcarPaso('flash', 'activo');
                escribir('Flasheando (no desconectes el USB)…');
                await loader.writeFlash({
                    fileArray: [{ data: binario, address: 0x0 }],
                    flashMode: 'keep', flashFreq: 'keep', flashSize: 'keep',
                    eraseAll: false, compress: true,
                    reportProgress: (_i, escrito, total) => { relleno.style.width = Math.round((escrito / total) * 100) + '%'; },
                });
                escribir('Flasheo terminado. Reiniciando la tarjeta…');
                await loader.after('hard_reset');
                try { await transport.disconnect(); } catch (e) { /* ya se cerró al reiniciar */ }
                marcarPaso('flash', 'ok');

                marcarPaso('mac', 'activo');
                escribir('Leyendo la MAC por USB…');
                const mac = await leerMacPorSerial(port);
                if (!mac) throw new Error('No se detectó la MAC por USB. Puedes teclearla a mano en «MAC y firmware».');
                marcarPaso('mac', 'ok');
                escribir('MAC leída: ' + mac);

                const res = await api(`/api/pcb/${pcb.id}/programacion`, { method: 'PUT', body: { mac } });   // sin firmware: aquí no se elige versión
                if (!res.ok) throw new Error(res.network ? 'Sin conexión con el servidor: no se guardó.' : res.error);
                escribir('Guardado ✓');
                toast(`${pcb.nombre}: MAC ${mac} guardada`, { kind: 'ok' });
                mostrarResultado(pcb, mac);
                S.pendientes = S.pendientes.filter((p) => p.id !== pcb.id);
            } catch (e) {
                marcarActivoComoError();
                escribir('✗ ' + (e && e.message ? e.message : String(e)));
            } finally {
                S.busy = false; btnFlash.disabled = false;
                pintarLista(); pintarPuertos();
            }
        }
        btnFlash.addEventListener('click', ejecutar);

        // ------------------------------------------------------------ panel de detalle
        const cabecera = h('div', { class: 'prog-cab' });
        const detalle = h('div', { class: 'prog-detalle', hidden: true },
            cabecera, pasosEl,
            h('div', { class: 'field' }, h('label', null, 'Puerto de la tarjeta'), puertosWrap,
                h('div', { class: 'hint' }, 'Solo se listan aquí los puertos que ya autorizaste antes. «Elegir puerto» abre la lista real de puertos COM de Windows (el navegador la pide una vez por puerto; luego queda recordado).')),
            h('div', { class: 'hint' }, 'Antes de sincronizar, pon la tarjeta en modo programador; el registro avisa si no avanza.'),
            log, barra, h('div', { class: 'row' }, btnFlash), resultado);
        const vacio = T.empty('flash', 'Elige una tarjeta', 'Búscala por número o nombre a la izquierda, o elige una de la lista.');

        function seleccionar(p) {
            if (S.busy) return;
            S.tarjeta = p;
            pintarDetalle();
            pintarLista();
        }
        function pintarDetalle() {
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
            h('div', { class: 'prog-panel prog-panel-detalle' }, vacio, detalle)));

        cargarPendientes();
        refrescarPuertosAutorizados();

        let tRec = null;
        function recargarSuave() { clearTimeout(tRec); tRec = setTimeout(() => { timers.delete(tRec); if (S.vivo && !S.busy) cargarPendientes(); }, 250); timers.add(tRec); }
        const wsc = ctx.ws || (T.ws && T.ws());
        if (wsc && wsc.on) ['PCB_ACTUALIZADA', 'PCB_RECIBIDA', 'PCB_ELIMINADA'].forEach((ev) => unsubs.push(wsc.on(ev, recargarSuave)));
        if (navigator.serial) { const onConn = () => refrescarPuertosAutorizados(); navigator.serial.addEventListener('connect', onConn); navigator.serial.addEventListener('disconnect', onConn); unsubs.push(() => { navigator.serial.removeEventListener('connect', onConn); navigator.serial.removeEventListener('disconnect', onConn); }); }

        return {
            actualizar() { if (!S.busy) cargarPendientes(); },
            desmontar() {
                S.vivo = false;
                timers.forEach((t) => clearTimeout(t)); timers.clear();
                unsubs.forEach((u) => { try { u(); } catch (e) { /* nada */ } });
                host.replaceChildren();
            },
        };
    }

    const def = { id: 'programacion', titulo: 'Programación', icono: 'flash', grupo: 'operacion', orden: 35, montar };
    if (window.TQTEscritorio && window.TQTEscritorio.registrar) window.TQTEscritorio.registrar(def);
    else { (window.__TQTSecciones = window.__TQTSecciones || []).push(def); }
})();
