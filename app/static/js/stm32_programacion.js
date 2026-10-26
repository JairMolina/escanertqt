/* R1/R3 STM32 (ctx.tipo, v1.3.55): selection from inventory/remote QR; Windows J-Link station jobs. */
window.TQTSTM32 = function (host, ctx) {
    'use strict';
    const { h, api, T } = ctx;
    const K = ctx.tipo === 'R3' ? 'R3' : 'R1', ID = 'stm-' + K.toLowerCase();
    let alive = true, current = null, selectedPcb = null, busy = false, timer = null, requestN = 0, listN = 0;
    let activeJob = null, activeFirmware = null, activeStation = null, cancelling = false;
    let selectedFirmware = null, firmwareRequest = 0, uploadOpen = false;
    const firmwareSelect = h('select', { class: 'input', id: ID + '-fw', disabled: true });
    const firmwareHint = h('p', { class: 'hint', 'aria-live': 'polite' }, 'Cargando firmware…');
    let firmwareItems = [];
    const approveBtn = h('button', { class: 'btn', type: 'button', hidden: true, onclick: () => {
        const f = firmwareItems.find(x => x.id === selectedFirmware);
        if (!f || f.release_status !== 'beta' || busy) return;
        const evidence = h('textarea', { class: 'input', id: ID + '-evidence', minlength: 10, maxlength: 2000, required: true });
        const error = h('div', { role: 'alert' });
        T.sheet({ title: 'Aprobar FW ' + f.fw + ' · ' + f.sha256.slice(0, 8),
            body: h('div', { class: 'stack' },
                h('p', null, 'Aprueba solo después de probar esta imagen en una tarjeta. La lectura J-Link correcta por sí sola no valida su funcionamiento.'),
                h('label', { for: evidence.id }, 'Tarjeta, pruebas realizadas y resultado'), evidence,
                h('p', { class: 'hint' }, 'La aprobación es una declaración del administrador y queda registrada. Si es la versión aprobada más alta, será la predeterminada.'), error),
            actions: [{ label: 'Aprobar firmware', kind: 'primary', onClick: async () => {
                if (!evidence.reportValidity()) return false;
                const r = await api('/api/stm32/firmwares/' + f.id + '/aprobar', { method: 'POST', body: { evidence: evidence.value.trim() } });
                if (!r.ok) { error.replaceChildren(T.banner('bad', 'alert', r.error)); return false; }
                await loadFirmwares(true); await loadList();
                if (selectedPcb) await choose(selectedPcb, true);
                message('Firmware aprobado. La selección automática considera solo versiones aprobadas.');
                return true;
            } }, { label: 'Cancelar', kind: 'ghost', onClick: () => true }] });
    } }, 'Aprobar firmware beta');
    const unsubs = [];
    const search = h('input', { class: 'input', type: 'search', id: ID + '-q', autocomplete: 'off', placeholder: 'Número, nombre o QR de la tarjeta' });
    const list = h('div', { class: 'prog-lista' });
    const empty = T.empty('flash', 'Elige una ' + K, 'Búscala por número, nombre o QR a la izquierda, o elige una de la lista.');
    const panel = h('div', { class: 'prog-detalle' }, empty);
    const status = h('div', { class: 'prog-resultado', role: 'status', 'aria-live': 'polite' });
    // v1.3.73: semáforo de estado de programación junto al detalle de la tarjeta
    // v1.4.0: estado con la plantilla compartida TQTProgEstado (igual que R2); conexión = Agente J-Link, sin puerto serial
    const estadoBox = window.TQTProgEstado.crear();
    let luzState = 'bad', luzExtra = {};
    function setLuz(k, extra) {
        luzState = k; luzExtra = extra || {};
        const id = current?.identity;
        const opt = station.selectedOptions[0];
        window.TQTProgEstado.pintar(estadoBox, Object.assign({
            estado: k, conexion: 'Agente J-Link' + (opt && opt.value ? ' · ' + (opt.dataset.name || opt.textContent) + (opt.dataset.online === 'true' ? ' (conectado)' : ' (desconectado)') : ' · sin estación elegida'),
            fw: id?.fw || '', hw: id?.hw || ''
        }, extra || {}));
    }
    const station = h('select', { class: 'input', id: ID + '-est' });
    const SKEY = 'tqt.station.stm32', STATION_EVENT = 'tqt:stm32-station-selected';
    const getSaved = () => { try { return localStorage.getItem(SKEY) || ''; } catch (e) { return ''; } };
    const getSavedName = () => { try { return localStorage.getItem(SKEY + '.name') || ''; } catch (e) { return ''; } };
    const setSaved = (id, name) => {
        try {
            if (id) { localStorage.setItem(SKEY, id); localStorage.setItem(SKEY + '.name', name || ''); }
            else { localStorage.removeItem(SKEY); localStorage.removeItem(SKEY + '.name'); }
            return true;
        } catch (e) { return false; }
    };
    let stationChoice = getSaved(), stationChoiceName = getSavedName(), stationRequest = 0, stationSignature = '', bindingStored = true;
    const sessionTxt = h('span', { class: 'prog-sesion-txt', role: 'status', 'aria-live': 'polite' });
    const sessionBox = h('div', { class: 'row wrap prog-sesion' }, sessionTxt,
        h('button', { class: 'btn btn-sm btn-ghost', type: 'button', onclick: () => stations() }, 'Actualizar'));
    function renderStation() {
        const opt = station.selectedOptions[0];
        sessionTxt.textContent = opt && opt.value
            ? 'Agente fijado: ' + (opt.dataset.name || stationChoiceName || opt.textContent) + ' · ' + (opt.dataset.online === 'true' ? 'conectado' : 'desconectado / no disponible') + (bindingStored ? '' : ' · solo esta sesión: no se pudo guardar la elección')
            : 'Elige el agente de esta laptop. No se selecciona otro automáticamente.';
        if (current) setLuz(luzState, luzExtra);
    }
    function bindStation(id, name, notify = true) {
        if (busy || cancelling) { station.value = activeStation || stationChoice; return; }
        stationChoice = id; stationChoiceName = name || ''; ++stationRequest; stationSignature = '';
        bindingStored = setSaved(id, name);
        if (id && ![...station.options].some(o => o.value === id)) station.append(h('option', { value: id, dataset: { online: 'false', name: name || 'Agente guardado' } }, (name || 'Agente guardado') + ' · esperando conexión'));
        station.value = id;
        renderStation(); enable();
        if (notify) window.dispatchEvent(new CustomEvent(STATION_EVENT, { detail: { id, name, source: ID } }));
        stations();
    }
    station.addEventListener('change', () => bindStation(station.value, station.selectedOptions[0]?.dataset.name || ''));
    const stationChanged = e => {
        if (e.detail?.source === ID || busy || cancelling) return;
        if (e.detail && (e.detail.id === '' || /^[a-f0-9]{24}$/.test(e.detail.id))) bindStation(e.detail.id, e.detail.name, false);
    };
    window.addEventListener(STATION_EVENT, stationChanged);
    const stationName = h('input', { class: 'input', value: 'PC de programación', id: ID + '-est-nombre', maxlength: 60 });
    const btnProgram = h('button', { class: 'btn btn-primary', type: 'button', disabled: true, onclick: program }, 'Programar STM32 con J-Link');
    const btnCancel = h('button', { class: 'btn', type: 'button', disabled: true, onclick: cancelStation }, 'Detener y cancelar programación');
    // v1.3.54: orden de programación de la pareja: ESP32 de R2 (MAC) → STM32 de R1 → ESP32 de R1 (MAC de R1)
    const btnEsp = K !== 'R1' ? null : h('button', { class: 'btn', type: 'button', disabled: true, onclick: async () => {
        if (busy || !selectedPcb) return;
        const r = await api('/api/pcb/' + selectedPcb.id);
        const p = r.ok && r.data ? r.data : selectedPcb;
        const ir = () => { if (ctx.programarEsp32) ctx.programarEsp32(p); return true; };
        if (p.firmware) { ir(); return; }
        T.sheet({ title: 'STM32 aún sin programar', body: h('p', null, 'La R1 ' + p.nombre + ' no tiene el STM32 programado y verificado. El orden correcto es STM32 primero y después ESP32.'),
            actions: [{ label: 'Programar ESP32 de todos modos', kind: 'primary', onClick: ir }, { label: 'Cancelar', kind: 'ghost', onClick: () => true }] });
    } }, 'Programar ESP32 R1');
    const hexIn = h('input', { type: 'file', accept: '.hex,text/plain', hidden: true, 'aria-hidden': 'true', tabindex: '-1' });
    const btnSubir = h('button', { class: 'btn', type: 'button', onclick: () => { hexIn.value = ''; hexIn.click(); } }, 'Subir HEX');
    hexIn.addEventListener('change', async () => {
        const f = hexIn.files && hexIn.files[0]; if (!f) return;
        if (f.size > 4_000_000) { message('El archivo es demasiado grande para un HEX de STM32.', true); return; }
        uploadOpen = true; enable(); message('Validando ' + f.name + '…');
        let opened = false;
        try {
            const contenido = await f.text();
            const r = await api('/api/stm32/hex/analizar', { method: 'POST', body: { contenido, tipo: K } });
            if (!r.ok) { message(f.name + ': ' + r.error, true); return; }
            if (!alive) return;
            const d = r.data;
            const suggested = /FW[-_]?V?([0-9]+(?:\.[0-9]+)*)/i.exec(f.name)?.[1] || '';
            const hw = h('input', { class: 'input', id: ID + '-upload-hw', value: K === 'R1' ? d.hw : d.hw !== '?' ? d.hw : '3.0', maxlength: 7, required: true, readonly: K === 'R1' });
            const fw = h('input', { class: 'input', id: ID + '-upload-fw', value: K === 'R1' ? d.fw : d.fw !== 'desconocida' ? d.fw : suggested, maxlength: 7, required: true, readonly: K === 'R1' });
            const error = h('div', { role: 'alert' });
            T.sheet({ title: 'Guardar firmware beta ' + K,
                body: h('div', { class: 'stack' }, h('p', null, f.name),
                    h('p', { class: 'hint' }, d.mcu + ' · ' + (d.bytes / 1024).toFixed(1) + ' KB'),
                    h('div', { class: 'field' }, h('label', { for: hw.id }, 'Versión de hardware (HW)'), hw),
                    h('div', { class: 'field' }, h('label', { for: fw.id }, 'Versión de firmware (FW)'), fw),
                    h('p', { class: 'hint' }, K === 'R3' ? 'Este HEX no contiene su versión. Comprueba HW y FW antes de guardarlo; el nombre del archivo solo propone una versión.' : 'La versión se obtiene del perfil interno. La identidad individual se retira para preparar cada tarjeta con sus datos del inventario.'), error),
                onClose: () => { uploadOpen = false; enable(); },
                actions: [{ label: 'Guardar como beta', kind: 'primary', onClick: async () => {
                    if (!hw.reportValidity() || !fw.reportValidity()) return false;
                    const saved = await api('/api/stm32/firmwares', { method: 'POST', body: { tipo: K, contenido, filename: f.name, hw: hw.value.trim(), fw: fw.value.trim() } });
                    if (!saved.ok) { error.replaceChildren(T.banner('bad', 'alert', saved.error)); return false; }
                    await loadFirmwares(true);
                    if (selectedPcb) await choose(selectedPcb, true);
                    message(saved.data.existing ? 'Este firmware ya estaba guardado. Puedes seleccionarlo para programar.' : 'Firmware beta guardado. Elígelo en la lista para probarlo; la versión aprobada sigue como predeterminada.');
                    return true;
                } }, { label: 'Cancelar', kind: 'ghost', onClick: () => true }] });
            opened = true;
        } catch (e) { message(e.message, true); }
        finally { if (!opened) { uploadOpen = false; enable(); } }
    });
    const lookup = h('button', { class: 'btn', type: 'button', onclick: () => scan(search.value) }, 'Buscar / cargar QR');
    const bundleBtn = h('button', { class: 'btn', type: 'button', onclick: async () => {
        try {
            const fn = await download('/api/stm32/stations/installer', { name: stationName.value.trim() });
            const m = /^(?:Instalar|Agente)_TQT_(.+)\.(?:cmd|zip)$/i.exec(fn || '');
            if (m) bindStation(m[1], stationName.value.trim());
            await stations();
        }
        catch (e) { message(e.message, true); }
    } }, 'Instalar agente en esta laptop');
    host.append(h('div', { class: 'prog-wrap' },
        h('div', { class: 'prog-panel' }, h('h2', null, 'Elige una ' + K),
          h('div', { class: 'field' }, h('label', { for: ID + '-q' }, 'Buscar'), search),
          h('div', { class: 'row wrap' }, lookup), list),
        h('div', { class: 'prog-panel prog-panel-detalle' }, panel,
          h('div', { class: 'row wrap prog-acciones' }, btnProgram, ...(btnEsp ? [btnEsp] : []), btnSubir, btnCancel, hexIn), status,
          h('div', { class: 'field' }, h('label', { for: ID + '-fw' }, 'Firmware a programar'), firmwareSelect, firmwareHint, approveBtn),
          h('div', { class: 'field' }, h('label', { for: station.id }, 'Agente Windows conectado al J-Link'), station, sessionBox, h('p', { class: 'hint' }, 'Elige una vez el agente que tiene tu J-Link; se guarda en este navegador. La IP compartida no identifica una laptop con certeza. Si se desconecta, la elección se conserva.')),
          h('details', { class: 'prog-config' }, h('summary', null, 'Configurar esta computadora por primera vez'),
            h('div', { class: 'field' }, h('label', { for: ID + '-est-nombre' }, 'Nombre para instalar un agente nuevo'), stationName, h('p', { class: 'hint' }, 'Este nombre se usa solo al instalar. El agente en uso se elige en el selector de arriba.')),
            h('div', { class: 'row wrap' }, bundleBtn),
            h('p', { class: 'hint' }, 'Abre el archivo Instalar_TQT descargado una sola vez: instala el agente y lo deja iniciando con Windows en segundo plano. Después, todas las grabaciones se controlan desde esta pantalla. Usa Python 3.10+ y J-Link de SEGGER o STM32CubeIDE ya instalados.')),
          h('p', { class: 'hint' }, K === 'R1' ? 'Orden de la pareja: 1) ESP32 de la R2 (da su MAC) · 2) STM32 de la R1 con la MAC y número de la R2 · 3) ESP32 de la R1 (da la MAC de la R1).' : 'La R3 lleva un firmware fijo (sin MAC ni identidad por unidad). Al verificarse queda registrada como programada.'))));
    function message(text, bad = false) { status.replaceChildren(T.banner(bad ? 'bad' : 'info', bad ? 'alert' : 'info', text)); }
    function progress(job) {
        const stages = [
            ['queued', 'Esperando a la laptop'],
            ['preparing', 'Preparando firmware y datos de la ' + K],
            ['writing', 'Conectando al STM32 y grabando firmware'],
            ['reading', 'Leyendo y verificando la grabación'],
            ['restarting', 'Reiniciando la tarjeta'],
            ['reporting', 'Guardando el resultado en la web']
        ];
        setLuz('warn', { fase: job.payload?.cancel_requested ? 'Deteniendo la programación…' : stages[Math.max(0, stages.findIndex(s => s[0] === (job.state === 'queued' ? 'queued' : (job.payload?.progress?.stage || 'preparing'))))][1], cancelada: !!job.payload?.cancel_requested });
        const stage = job.state === 'queued' ? 'queued' : (job.payload?.progress?.stage || 'preparing');
        const index = stages.findIndex(s => s[0] === stage);
        const pct = Math.round((index + 1) / stages.length * 100);
        status.replaceChildren(h('div', { class: 'prog-avance', 'aria-busy': 'true' },
            h('strong', null, job.payload?.cancel_requested ? 'Deteniendo la programación…' : 'Programando ' + (job.payload?.identity?.nombre || current?.identity.nombre || K)),
            h('p', { class: 'hint' }, job.payload?.cancel_requested ? 'Esperando que el agente cierre J-Link y confirme la cancelación.' : stages[index][1] + '…'),
            h('ol', { class: 'prog-pasos' }, ...stages.map(([key, label], n) => h('li', {
                class: 'prog-paso', 'aria-current': key === stage ? 'step' : null,
                dataset: { e: n < index ? 'ok' : n === index ? 'activo' : 'pendiente' }
            }, h('span', { class: 'prog-paso-ico' }), h('span', { class: 'prog-paso-t' }, label)))),
            h('div', { class: 'prog-bar', role: 'progressbar', 'aria-label': 'Programación STM32 en curso', 'aria-valuemin': '0', 'aria-valuemax': '100', 'aria-valuenow': String(pct) },
                h('div', { class: 'prog-bar-fill', style: 'width:' + pct + '%' })),
            h('p', { class: 'hint' }, 'No desconectes la ' + K + ' hasta que termine la verificación.')));
    }
    function enable() {
        const chosenFw = firmwareItems.find(x => x.id === selectedFirmware);
        approveBtn.hidden = !chosenFw || chosenFw.release_status !== 'beta';
        approveBtn.disabled = busy || uploadOpen;
        btnCancel.disabled = !station.value || cancelling;
        btnProgram.textContent = busy ? 'Programando…' : current ? 'Programar ' + K + ' ' + current.identity.nombre.slice(-4) + ' con J-Link' : 'Programar STM32 con J-Link';
        btnProgram.disabled = busy || uploadOpen || !current || !firmwareSelect.value || !station.value || station.selectedOptions[0]?.dataset.online !== 'true';
        if (btnEsp) btnEsp.disabled = busy || !current;
        btnSubir.disabled = busy || uploadOpen;
        firmwareSelect.disabled = busy || uploadOpen || !firmwareSelect.options.length;
        search.disabled = busy; lookup.disabled = busy; station.disabled = busy || cancelling; bundleBtn.disabled = busy;
        list.querySelectorAll('button').forEach(b => b.disabled = busy);
    }

    async function loadFirmwares(reset = false) {
        const n = ++firmwareRequest;
        const hw = selectedPcb?.version || '';
        const r = await api('/api/stm32/firmwares?tipo=' + K + '&hw=' + encodeURIComponent(hw));
        if (!alive || n !== firmwareRequest) return;
        if (!r.ok) { firmwareHint.textContent = r.error; firmwareSelect.replaceChildren(); enable(); return; }
        const d = r.data;
        firmwareItems = d.items;
        if (busy && activeFirmware) selectedFirmware = activeFirmware;
        else if (reset || !d.items.some(f => f.id === selectedFirmware)) selectedFirmware = d.default_id;
        firmwareSelect.replaceChildren(...d.items.map(f => h('option', { value: f.id }, 'FW ' + f.fw + ' · HW ' + f.hw + ' · ' + f.sha256.slice(0, 8) + (f.release_status === 'beta' ? ' · BETA · solo pruebas' : ' · Aprobado') + (f.id === d.default_id ? ' · más reciente aprobado' : ''))));
        firmwareSelect.value = selectedFirmware || '';
        firmwareHint.textContent = d.items.length ? 'Por defecto se usa la versión aprobada más alta compatible. Las BETA se eligen manualmente y no cuentan como actualización pendiente.' : 'No hay firmware compatible con esta placa. Sube un HEX para su hardware.';
        enable();
    }
    firmwareSelect.addEventListener('change', () => {
        selectedFirmware = firmwareSelect.value;
        enable();
        if (selectedPcb) choose(selectedPcb, true);
    });
    async function stations() {
        if (!alive || busy || cancelling) return;
        const n = ++stationRequest, choice = stationChoice;
        const r = await api('/api/stm32/stations');
        if (!alive || n !== stationRequest || choice !== stationChoice || busy || cancelling) return;
        if (!r.ok) {
            [...station.options].forEach(o => o.dataset.online = 'false');
            stationSignature = ''; renderStation(); enable(); return;
        }
        // Una IP pública puede representar varias laptops. Nunca sustituir una elección por otra.
        const all = [...r.data].sort((a, b) => a.name.localeCompare(b.name) || a.id.localeCompare(b.id));
        const chosen = all.find(x => x.id === choice);
        if (chosen) stationChoiceName = chosen.name;
        const options = [{ id: '', name: 'Elige el agente de esta laptop', online: false, placeholder: true }, ...all];
        if (choice && !chosen) options.push({ id: choice, name: stationChoiceName || 'Agente guardado', online: false, missing: true });
        const signature = JSON.stringify(options.map(x => [x.id, x.name, !!x.online, !!x.local, !!x.missing]));
        if (signature !== stationSignature) {
            station.replaceChildren(...options.map(x => h('option', { value: x.id, dataset: { online: String(!!x.online), name: x.placeholder ? '' : x.name } },
                x.placeholder ? x.name : x.name + ' · ' + x.id.slice(-6) + (x.online ? ' · conectado' : ' · desconectado') + (x.missing ? ' / no disponible' : x.local ? ' · misma red' : ''))));
            stationSignature = signature;
        }
        station.value = choice;
        renderStation(); enable();
        await recover();
    }

    async function recover() {
        const sid = station.value;
        if (!sid || busy) return;
        const r = await api('/api/stm32/stations/' + sid + '/jobs');
        if (!alive || station.value !== sid || busy) return;
        const own = r.ok && r.data.find(j => (j.payload?.kind || 'R1') === K && (!j.station || j.station === sid));
        if (own) watchJob(own);
    }

    async function cancelStation() {
        const sid = activeStation || station.value;
        if (!sid || cancelling) return;
        cancelling = true; enable();
        try {
            const r = await api('/api/stm32/stations/' + sid + '/cancel', { method: 'POST', body: {} });
            if (!r.ok) { message(r.error, true); return; }
            if (r.data.jobs.some(j => j.waiting)) {
                message('Cancelación solicitada. Espera que el agente cierre J-Link; aún no desconectes la placa.');
                if (!busy) await recover();
            } else {
                clearTimeout(timer); activeJob = null; activeFirmware = null; activeStation = null; busy = false;
                message('Trabajos pendientes cancelados. Puedes preparar otra programación.');
            }
        } finally { cancelling = false; enable(); }
    }

    function watchJob(j) {
        activeStation = j.station || station.value;
        activeFirmware = j.payload?.firmware_id || null;
        if (activeFirmware) { selectedFirmware = activeFirmware; firmwareSelect.value = activeFirmware; }
        activeJob = j.id; busy = true; enable(); progress(j);
        clearTimeout(timer);
        async function poll() {
            const id = activeJob;
            const r = await api('/api/stm32/jobs/' + id);
            if (!alive || activeJob !== id) return;
            if (!r.ok) { message('Recuperando conexión. Puedes solicitar detener la programación; no desconectes la placa.', true); timer = setTimeout(poll, 3000); return; }
            const job = r.data;
            if (['queued', 'running'].includes(job.state)) { progress(job); timer = setTimeout(poll, 1000); return; }
            activeJob = null; activeFirmware = null; activeStation = null; busy = false; await stations(); loadList();
            if (selectedPcb) await choose(selectedPcb, true);
            enable();
            const okJob = job.state === 'verified', canc = !!job.payload?.cancel_requested || /cancel/i.test(job.state);
            setLuz(okJob ? 'ok' : 'err', okJob ? { fase: 'Terminado', resultado: 'Programado y verificado por lectura · UID ' + (job.result?.uid || '—') + '. Ya puedes desconectar la placa.' }
                : { fase: canc ? 'Cancelada' : 'Terminado con error', cancelada: canc, error: job.result?.error || 'No se confirmó la programación. Revisa la estación y la tarjeta.' });
            message(job.state === 'verified' ? '✓ STM32 programado y verificado por lectura · FW ' + job.payload.identity.fw + ' · UID ' + job.result.uid + '. Ya puedes desconectar la placa.' : (job.result?.error || 'No se confirmó la programación. Revisa la estación y la tarjeta.'), job.state !== 'verified');
        }
        timer = setTimeout(poll, 1000);
    }
    async function choose(pcb, quiet = false) {
        if (busy) return { ok: false, texto: 'Hay una programación en curso.' };
        selectedPcb = pcb;
        const n = ++requestN; current = null; enable(); panel.replaceChildren(h('p', { class: 'hint' }, K === 'R1' ? 'Cargando R1 y su R2…' : 'Cargando R3…')); markSel();
        await loadFirmwares();
        if (!alive || n !== requestN) return { ok: false, texto: 'Selección cambiada.' };
        const [r, fresca] = await Promise.all([api('/api/stm32/preview/' + pcb.id + (selectedFirmware ? '?firmware_id=' + encodeURIComponent(selectedFirmware) : '')), api('/api/pcb/' + pcb.id)]);
        if (!alive || n !== requestN) return { ok: false, texto: 'Selección cambiada.' };
        if (!r.ok) { panel.replaceChildren(T.banner('bad', 'alert', r.error)); return { ok: false, texto: r.error }; }
        current = r.data;
        const d = current.identity;
        const filas = K === 'R1'
            ? [['Nombre R1', d.nombre], ['R2 vinculada', current.r2], ['ID R2', d.id_r], ['MAC R2', d.mac_r], ['HW', d.hw], ['Firmware', d.fw], ['CRC32', current.crc32]]
            : [['Nombre R3', d.nombre], ['HW', d.hw], ['Firmware', d.fw], ['Imagen', (current.bytes / 1024).toFixed(1) + ' KB']];
        setLuz((fresca.ok && fresca.data ? fresca.data : pcb).firmware ? 'ok' : 'bad', { fase: 'Lista para programar' });
        panel.replaceChildren(h('div', { class: 'prog-split' }, h('div', { class: 'prog-datos' }, h('div', { class: 'prog-cab' }, T.tipoChip(K), h('span', { class: 'prog-nm' }, current.nombre || current.r1),
            h('span', { class: 'dim' }, K === 'R1' ? 'R2 ' + current.r2 : (pcb.id_tarjeta_num ? 'Tarjeta #' + String(pcb.id_tarjeta_num).padStart(4, '0') : 'Suelta'))),
            h('dl', { class: 'prog-dl' }, ...filas.flatMap(([k, v]) => [h('dt', null, k), h('dd', null, v)])),
            h('p', { class: 'hint' }, 'Al pulsar Programar confirmas que esta ' + K + ' es la conectada al J-Link. La grabación empieza directamente y el resultado aparece aquí.'),
            ...(K === 'R1' ? [h('p', { class: 'hint' }, 'Se conserva la configuración existente en EEPROM, incluido su nombre.')] : [])), estadoBox));
        if (!quiet) message(K === 'R1' ? 'Datos cargados. Revisa la R1 física y la R2 asociada antes de programar.' : 'Datos cargados. Revisa la R3 física antes de programar.'); enable();
        return { ok: true, texto: K === 'R1' ? 'R1 y datos de R2 cargados para STM32.' : 'R3 cargada para STM32.' };
    }
    async function scan(code) {
        if (busy) return { ok: false, texto: 'Hay una programación en curso.' };
        if (!String(code || '').trim()) return { ok: false, texto: 'Indica una tarjeta o QR.' };
        const r = await api('/api/consulta?codigo=' + encodeURIComponent(code));
        if (!r.ok) { message(r.error, true); return { ok: false, texto: r.error }; }
        const k = K.toLowerCase();
        const p = r.data.tarjeta?.[k] || (r.data.pcb?.tipo === K ? r.data.pcb : null) || r.data.serie?.[k];
        if (!p) { message('El código no corresponde a una tarjeta con ' + K + '.', true); return { ok: false, texto: 'No se encontró ' + K + '.' }; }
        return choose(p);
    }
    async function loadList() {
        const n = ++listN;
        const [r, cat] = await Promise.all([api('/api/pcb?tipo=' + K + '&limit=500&q=' + encodeURIComponent(search.value)), api('/api/stm32/firmwares?tipo=' + K)]);
        if (!alive || n !== listN) return;
        if (!r.ok) { list.replaceChildren(T.banner('bad', 'alert', r.error)); return; }
        // v1.4.19: estatus por tarjeta como en R2 (FW guardado vs. el más alto compatible con su HW)
        const vnum = v => String(v || '').split('.').map(x => parseInt(x, 10) || 0);
        const mayor = (a, b) => { const x = vnum(a), y = vnum(b); for (let i = 0; i < Math.max(x.length, y.length); i++) { if ((x[i] || 0) !== (y[i] || 0)) return (x[i] || 0) > (y[i] || 0); } return false; };
        const ultimo = {};
        (cat.ok ? cat.data.items : []).forEach(f => { if (f.release_status === 'beta') return; const hw = String(f.hw).replace(/\./g, ''); if (!ultimo[hw] || mayor(f.fw, ultimo[hw])) ultimo[hw] = f.fw; });
        const badge = p => {
            const vig = ultimo[String(p.version).replace(/\./g, '')], s = !p.firmware ? 'unprogrammed' : vig && mayor(vig, p.firmware) ? 'outdated' : 'updated';
            return h('span', { class: 'prog-r2-state', dataset: { s }, title: 'Instalado: ' + (p.firmware || 'sin firmware') + ' · vigente: ' + (vig || '—') }, { unprogrammed: 'Sin programar', outdated: 'Desactualizada', updated: 'Actualizada' }[s]);
        };
        list.replaceChildren(...r.data.items.map(p => h('button', { class: 'prog-item', type: 'button', onclick: () => choose(p), disabled: busy,
            'aria-pressed': String(!!selectedPcb && selectedPcb.id === p.id), dataset: { id: p.id } },
            T.tipoChip(K), h('span', { class: 'nm' }, p.nombre), badge(p), h('span', { class: 'dim' }, p.id_tarjeta_num ? '#' + String(p.id_tarjeta_num).padStart(4, '0') : 'Suelta'))));
        if (!r.data.items.length) list.append(T.empty('search', 'Sin coincidencias', 'También puedes cargar un QR o número con Buscar.'));
    }
    function markSel() { list.querySelectorAll('.prog-item').forEach(b => b.setAttribute('aria-pressed', String(!!selectedPcb && String(selectedPcb.id) === b.dataset.id))); }
    let debounce;
    search.addEventListener('input', () => { clearTimeout(debounce); debounce = setTimeout(loadList, 250); });
    search.addEventListener('keydown', e => { if (e.key === 'Enter') scan(search.value); });
    async function download(url, body) {
        const resp = await fetch(url, body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : {});
        if (!resp.ok) { const d = await resp.json(); throw new Error(d.detail || 'Error al descargar'); }
        const filename = /filename="([^"]+)"/.exec(resp.headers.get('Content-Disposition') || '')?.[1] || 'TQT.hex';
        const u = URL.createObjectURL(await resp.blob()), a = h('a', { href: u, download: filename });
        document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(u), 10000);
        return filename;
    }
    async function program() {
        if (!current || busy) return;
        const sid = station.value;
        if (!sid || sid !== stationChoice || station.selectedOptions[0]?.dataset.online !== 'true') { message('El agente fijado no está conectado. Revisa esa laptop o elige otro agente expresamente.', true); return; }
        activeStation = sid;
        busy = true; enable();
        progress({ state: 'queued' });
        const r = await api('/api/stm32/jobs', { method: 'POST', body: { pcb_id: current.pcb_id, station_id: sid, hex_sha256: current.hex_sha256, firmware_id: current.firmware_id, physical_confirmed: true } });
        if (!r.ok) { activeStation = null; busy = false; enable(); setLuz('err', { fase: 'No se pudo iniciar', error: r.error }); message(r.error, true); return; }
        watchJob(r.data);
    }
    function refresh() {
        if (!alive || busy) return;
        loadList(); stations();
        if (selectedPcb) choose(selectedPcb, true);
    }
    const ws = ctx.ws || (T.ws && T.ws());
    if (ws?.on) ['PCB_ACTUALIZADA', 'PCB_ELIMINADA', 'TARJETA_ACTUALIZADA', 'TARJETA_EMPAREJADA'].forEach(ev => unsubs.push(ws.on(ev, refresh)));
    loadFirmwares(true); loadList(); stations();
    const stationTimer = setInterval(() => { if (alive && !busy) stations(); }, 5000);
    return { escaneo: scan, ocupada() { return busy; }, actualizar: refresh, desmontar() { alive = false; clearTimeout(timer); clearTimeout(debounce); clearInterval(stationTimer); ++stationRequest; window.removeEventListener(STATION_EVENT, stationChanged); unsubs.forEach(fn => fn()); } };
};
