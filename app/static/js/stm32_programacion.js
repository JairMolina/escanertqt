/* R1/R3 STM32 (ctx.tipo, v1.3.55): selection from inventory/remote QR; Windows J-Link station jobs. */
window.TQTSTM32 = function (host, ctx) {
    'use strict';
    const { h, api, T } = ctx;
    const K = ctx.tipo === 'R3' ? 'R3' : 'R1', ID = 'stm-' + K.toLowerCase();
    let alive = true, current = null, selectedPcb = null, busy = false, timer = null, requestN = 0, listN = 0;
    let activeJob = null, activeFirmware = null, cancelling = false;
    let selectedFirmware = null, firmwareRequest = 0, uploadOpen = false;
    const firmwareSelect = h('select', { class: 'input', id: ID + '-fw', disabled: true });
    const firmwareHint = h('p', { class: 'hint', 'aria-live': 'polite' }, 'Cargando firmware…');
    const unsubs = [];
    const search = h('input', { class: 'input', type: 'search', id: ID + '-q', autocomplete: 'off', placeholder: 'Número, nombre o QR de la tarjeta' });
    const list = h('div', { class: 'prog-lista' });
    const empty = T.empty('flash', 'Elige una ' + K, 'Búscala por número, nombre o QR a la izquierda, o elige una de la lista.');
    const panel = h('div', { class: 'prog-detalle' }, empty);
    const status = h('div', { class: 'prog-resultado', role: 'status', 'aria-live': 'polite' });
    // v1.3.73: semáforo de estado de programación junto al detalle de la tarjeta
    // v1.4.0: estado con la plantilla compartida TQTProgEstado (igual que R2); conexión = Agente J-Link, sin puerto serial
    const estadoBox = window.TQTProgEstado.crear();
    function setLuz(k, extra) {
        const id = current?.identity;
        const opt = station.selectedOptions[0];
        window.TQTProgEstado.pintar(estadoBox, Object.assign({
            estado: k, conexion: 'Agente J-Link' + (opt && opt.value ? ' · ' + (opt.dataset.name || opt.textContent) + (opt.dataset.online === 'true' ? ' (conectado)' : ' (desconectado)') : ' · sin estación elegida'),
            fw: id?.fw || '', hw: id?.hw || ''
        }, extra || {}));
    }
    const station = h('select', { class: 'input', id: ID + '-est' });
    const SKEY = 'tqt.station.stm32';
    const getSaved = () => { try { return localStorage.getItem(SKEY) || ''; } catch (e) { return ''; } };
    const setSaved = id => { try { if (id) localStorage.setItem(SKEY, id); else localStorage.removeItem(SKEY); } catch (e) { /* sin storage */ } };
    let changing = false;
    const sessionTxt = h('span', { class: 'prog-sesion-txt' });
    const sessionBox = h('div', { class: 'row wrap prog-sesion', hidden: true },
        sessionTxt, h('button', { class: 'btn btn-sm btn-ghost', type: 'button', onclick: () => { changing = true; renderStation(); } }, 'Cambiar dispositivo'));
    const btnChange = sessionBox.lastElementChild;
    function renderStation() {
        const opt = station.selectedOptions[0];
        const has = !!station.value && !changing;
        sessionBox.hidden = !has;
        stationPick.hidden = has;
        if (has) sessionTxt.textContent = 'Dispositivo de esta PC: ' + (opt?.dataset.name || opt?.textContent || '') + ' · ' + (opt?.dataset.online === 'true' ? 'conectado' : 'desconectado');
    }
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
            T.sheet({ title: 'Guardar firmware ' + K,
                body: h('div', { class: 'stack' }, h('p', null, f.name),
                    h('p', { class: 'hint' }, d.mcu + ' · ' + (d.bytes / 1024).toFixed(1) + ' KB'),
                    h('div', { class: 'field' }, h('label', { for: hw.id }, 'Versión de hardware (HW)'), hw),
                    h('div', { class: 'field' }, h('label', { for: fw.id }, 'Versión de firmware (FW)'), fw),
                    h('p', { class: 'hint' }, K === 'R3' ? 'Este HEX no contiene su versión. Comprueba HW y FW antes de guardarlo; el nombre del archivo solo propone una versión.' : 'La versión se obtiene del perfil interno. La identidad individual se retira para preparar cada tarjeta con sus datos del inventario.'), error),
                onClose: () => { uploadOpen = false; enable(); },
                actions: [{ label: 'Guardar firmware', kind: 'primary', onClick: async () => {
                    if (!hw.reportValidity() || !fw.reportValidity()) return false;
                    const saved = await api('/api/stm32/firmwares', { method: 'POST', body: { tipo: K, contenido, filename: f.name, hw: hw.value.trim(), fw: fw.value.trim() } });
                    if (!saved.ok) { error.replaceChildren(T.banner('bad', 'alert', saved.error)); return false; }
                    await loadFirmwares(true);
                    if (selectedPcb) await choose(selectedPcb, true);
                    message(saved.data.existing ? 'Este firmware ya estaba guardado. Puedes seleccionarlo para programar.' : 'Firmware guardado. Se seleccionó la versión más reciente compatible.');
                    return true;
                } }, { label: 'Cancelar', kind: 'ghost', onClick: () => true }] });
            opened = true;
        } catch (e) { message(e.message, true); }
        finally { if (!opened) { uploadOpen = false; enable(); } }
    });
    const stationPick = h('div', null, station,
        h('div', { class: 'row wrap' }, h('button', { class: 'btn btn-sm btn-ghost', type: 'button', onclick: stations }, 'Actualizar estaciones')));
    const lookup = h('button', { class: 'btn', type: 'button', onclick: () => scan(search.value) }, 'Buscar / cargar QR');
    const bundleBtn = h('button', { class: 'btn', type: 'button', onclick: async () => {
        try {
            const fn = await download('/api/stm32/stations/installer', { name: stationName.value.trim() });
            const m = /^(?:Instalar|Agente)_TQT_(.+)\.(?:cmd|zip)$/i.exec(fn || '');
            if (m) { setSaved(m[1]); changing = false; }
            await stations();
        }
        catch (e) { message(e.message, true); }
    } }, 'Instalar agente en esta laptop');
    host.append(h('div', { class: 'prog-wrap' },
        h('div', { class: 'prog-panel' }, h('h2', null, 'Elige una ' + K),
          h('div', { class: 'field' }, h('label', { for: ID + '-q' }, 'Buscar'), search),
          h('div', { class: 'row wrap' }, lookup), list),
        h('div', { class: 'prog-panel prog-panel-detalle' }, panel,
          h('div', { class: 'field' }, h('label', { for: ID + '-fw' }, 'Firmware a programar'), firmwareSelect, firmwareHint),
          h('div', { class: 'field' }, h('label', { for: ID + '-est' }, 'Estación Windows conectada al J-Link'), sessionBox, stationPick),
          h('details', { class: 'prog-config' }, h('summary', null, 'Configurar esta computadora por primera vez'),
            h('div', { class: 'field' }, h('label', { for: ID + '-est-nombre' }, 'Nombre de estación Windows'), stationName),
            h('div', { class: 'row wrap' }, bundleBtn),
            h('p', { class: 'hint' }, 'Abre el archivo Instalar_TQT descargado una sola vez: instala el agente y lo deja iniciando con Windows en segundo plano. Después, todas las grabaciones se controlan desde esta pantalla. Usa Python 3.10+ y J-Link de SEGGER o STM32CubeIDE ya instalados.')),
          h('div', { class: 'row wrap' }, btnProgram, ...(btnEsp ? [btnEsp] : []), btnSubir, btnCancel, hexIn),
          h('p', { class: 'hint' }, K === 'R1' ? 'Orden de la pareja: 1) ESP32 de la R2 (da su MAC) · 2) STM32 de la R1 con la MAC y número de la R2 · 3) ESP32 de la R1 (da la MAC de la R1).' : 'La R3 lleva un firmware fijo (sin MAC ni identidad por unidad). Al verificarse queda registrada como programada.'), status)));
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
        btnCancel.disabled = !station.value || cancelling;
        btnProgram.textContent = busy ? 'Programando…' : current ? 'Programar ' + K + ' ' + current.identity.nombre.slice(-4) + ' con J-Link' : 'Programar STM32 con J-Link';
        btnProgram.disabled = busy || uploadOpen || !current || !firmwareSelect.value || !station.value || station.selectedOptions[0]?.dataset.online !== 'true';
        if (btnEsp) btnEsp.disabled = busy || !current;
        btnSubir.disabled = busy || uploadOpen;
        firmwareSelect.disabled = busy || uploadOpen || !firmwareSelect.options.length;
        search.disabled = busy; lookup.disabled = busy; station.disabled = busy; bundleBtn.disabled = busy;
        list.querySelectorAll('button').forEach(b => b.disabled = busy);
    }

    async function loadFirmwares(reset = false) {
        const n = ++firmwareRequest;
        const hw = selectedPcb?.version || '';
        const r = await api('/api/stm32/firmwares?tipo=' + K + '&hw=' + encodeURIComponent(hw));
        if (!alive || n !== firmwareRequest) return;
        if (!r.ok) { firmwareHint.textContent = r.error; firmwareSelect.replaceChildren(); enable(); return; }
        const d = r.data;
        if (busy && activeFirmware) selectedFirmware = activeFirmware;
        else if (reset || !d.items.some(f => f.id === selectedFirmware)) selectedFirmware = d.default_id;
        firmwareSelect.replaceChildren(...d.items.map(f => h('option', { value: f.id }, 'FW ' + f.fw + ' · HW ' + f.hw + ' · ' + f.sha256.slice(0, 8) + (f.id === d.default_id ? ' · más reciente' : ''))));
        firmwareSelect.value = selectedFirmware || '';
        firmwareHint.textContent = d.items.length ? 'Por defecto se usa la versión más alta compatible; puedes elegir una anterior.' : 'No hay firmware compatible con esta placa. Sube un HEX para su hardware.';
        enable();
    }
    firmwareSelect.addEventListener('change', () => {
        selectedFirmware = firmwareSelect.value;
        if (selectedPcb) choose(selectedPcb, true);
    });
    async function stations() {
        const r = await api('/api/stm32/stations'); if (!alive) return;
        if (!r.ok) {
            [...station.options].forEach(o => o.dataset.online = 'false');
            renderStation(); enable(); return;
        }
        const selected = station.value;
        // v1.3.75: solo las estaciones que reportan desde la misma red que este navegador (la PC local)
        const locales = r.data.filter(s => s.local);
        btnChange.hidden = locales.length < 2;
        station.replaceChildren(h('option', { value: '' }, locales.length ? 'Elige una estación' : 'Ninguna estación J-Link en esta PC'));
        locales.forEach(s => station.append(h('option', { value: s.id, dataset: { online: String(s.online), name: s.name } }, s.name + (s.online ? ' · conectada' : ' · desconectada'))));
        const has = id => !!id && [...station.options].some(o => o.value === id);
        const saved = getSaved();
        if (saved && !r.data.some(s => s.id === saved)) { setSaved(''); changing = false; }
        if (has(saved)) station.value = saved;
        else if (has(selected)) station.value = selected;
        else if (locales.some(s => s.online)) { station.value = locales.find(s => s.online).id; setSaved(station.value); }
        renderStation();
        enable();
        if (!busy) await recover();
    }
    station.addEventListener('change', () => { if (station.value) { setSaved(station.value); changing = false; } renderStation(); enable(); recover(); });

    async function recover() {
        const sid = station.value;
        if (!sid || busy) return;
        const r = await api('/api/stm32/stations/' + sid + '/jobs');
        if (!alive || station.value !== sid || busy) return;
        if (r.ok && r.data.length) watchJob(r.data[0]);
    }

    async function cancelStation() {
        if (!station.value || cancelling) return;
        cancelling = true; enable();
        try {
            const r = await api('/api/stm32/stations/' + station.value + '/cancel', { method: 'POST', body: {} });
            if (!r.ok) { message(r.error, true); return; }
            if (r.data.jobs.some(j => j.waiting)) {
                message('Cancelación solicitada. Espera que el agente cierre J-Link; aún no desconectes la placa.');
                if (!busy) await recover();
            } else {
                clearTimeout(timer); activeJob = null; activeFirmware = null; busy = false;
                message('Trabajos pendientes cancelados. Puedes preparar otra programación.');
            }
        } finally { cancelling = false; enable(); }
    }

    function watchJob(j) {
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
            activeJob = null; activeFirmware = null; busy = false; await stations();
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
        const r = await api('/api/pcb?tipo=' + K + '&limit=500&q=' + encodeURIComponent(search.value));
        if (!alive || n !== listN) return;
        if (!r.ok) { list.replaceChildren(T.banner('bad', 'alert', r.error)); return; }
        list.replaceChildren(...r.data.items.map(p => h('button', { class: 'prog-item', type: 'button', onclick: () => choose(p), disabled: busy,
            'aria-pressed': String(!!selectedPcb && selectedPcb.id === p.id), dataset: { id: p.id } },
            T.tipoChip(K), h('span', { class: 'nm' }, p.nombre), h('span', { class: 'dim' }, p.id_tarjeta_num ? '#' + String(p.id_tarjeta_num).padStart(4, '0') : 'Suelta'))));
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
        busy = true; enable();
        progress({ state: 'queued' });
        const r = await api('/api/stm32/jobs', { method: 'POST', body: { pcb_id: current.pcb_id, station_id: station.value, hex_sha256: current.hex_sha256, firmware_id: current.firmware_id, physical_confirmed: true } });
        if (!r.ok) { busy = false; enable(); setLuz('err', { fase: 'No se pudo iniciar', error: r.error }); message(r.error, true); return; }
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
    return { escaneo: scan, ocupada() { return busy; }, actualizar: refresh, desmontar() { alive = false; clearTimeout(timer); clearTimeout(debounce); clearInterval(stationTimer); unsubs.forEach(fn => fn()); } };
};
