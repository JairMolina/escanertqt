/* R1 STM32: selection from inventory/remote QR; Windows J-Link station jobs. */
window.TQTSTM32 = function (host, ctx) {
    'use strict';
    const { h, api, T } = ctx;
    let alive = true, current = null, busy = false, timer = null, requestN = 0;
    const search = h('input', { class: 'input', placeholder: 'Número, nombre o QR de la tarjeta', 'aria-label': 'Buscar R1 STM32' });
    const list = h('div', { class: 'prog-lista' });
    const panel = h('div', { class: 'prog-panel' });
    const status = h('div', { role: 'status', 'aria-live': 'polite' });
    const station = h('select', { class: 'input', 'aria-label': 'Estación Windows J-Link' });
    const stationName = h('input', { class: 'input', value: 'PC de programación', maxlength: 60, 'aria-label': 'Nombre de estación Windows' });
    const btnProgram = h('button', { class: 'btn btn-primary', type: 'button', disabled: true, onclick: program }, 'Programar STM32 con J-Link');
    const btnHex = h('button', { class: 'btn', type: 'button', disabled: true, onclick: async () => {
        try { await download('/api/stm32/hex/' + current.pcb_id); } catch (e) { message(e.message, true); }
    } }, 'Descargar HEX de esta R1');
    const lookup = h('button', { class: 'btn', type: 'button', onclick: () => scan(search.value) }, 'Buscar / cargar QR');
    const bundleBtn = h('button', { class: 'btn', type: 'button', onclick: async () => {
        try { await download('/api/stm32/stations/bundle', { name: stationName.value.trim() }); await stations(); }
        catch (e) { message(e.message, true); }
    } }, 'Descargar agente Windows');
    host.append(h('h2', null, 'R1 · STM32 / J-Link'),
        h('p', null, 'Selecciona la R1 o escanea su QR con el celular vinculado. Los datos de R2 se toman del emparejamiento registrado.'),
        h('div', { class: 'prog-wrap' }, h('div', { class: 'prog-panel' }, search, lookup, list),
          h('div', { class: 'prog-panel' }, panel,
            h('div', { class: 'field' }, h('label', null, 'Estación Windows conectada al J-Link'), station,
              h('button', { class: 'btn btn-sm', type: 'button', onclick: stations }, 'Actualizar estaciones')),
            h('details', null, h('summary', null, 'Configurar esta computadora por primera vez'), stationName, bundleBtn,
              h('p', null, 'Extrae el ZIP, abre iniciar.cmd y mantén su ventana abierta. Selecciona la estación y confirma la R1 conectada cuando el agente lo solicite.')),
            h('div', { class: 'row wrap' }, btnHex, btnProgram), status)));
    function message(text, bad = false) { status.replaceChildren(T.banner(bad ? 'bad' : 'info', bad ? 'alert' : 'info', text)); }
    function enable() {
        btnProgram.disabled = busy || !current || !station.value || station.selectedOptions[0]?.dataset.online !== 'true';
        btnHex.disabled = busy || !current;
        search.disabled = busy; lookup.disabled = busy; station.disabled = busy; bundleBtn.disabled = busy;
        list.querySelectorAll('button').forEach(b => b.disabled = busy);
    }
    async function stations() {
        const r = await api('/api/stm32/stations'); if (!alive || !r.ok) return;
        const selected = station.value;
        station.replaceChildren(h('option', { value: '' }, 'Elige una estación'));
        r.data.forEach(s => station.append(h('option', { value: s.id, dataset: { online: String(s.online) } }, s.name + (s.online ? ' · conectada' : ' · desconectada'))));
        if ([...station.options].some(o => o.value === selected)) station.value = selected;
        else if (r.data.filter(s => s.online).length === 1) station.value = r.data.find(s => s.online).id;
        enable();
    }
    station.addEventListener('change', enable);
    async function choose(pcb) {
        if (busy) return { ok: false, texto: 'Hay una programación en curso.' };
        const n = ++requestN; current = null; enable(); panel.replaceChildren(h('p', null, 'Cargando R1 y su R2…'));
        const r = await api('/api/stm32/preview/' + pcb.id);
        if (!alive || n !== requestN) return { ok: false, texto: 'Selección cambiada.' };
        if (!r.ok) { panel.replaceChildren(T.banner('bad', 'alert', r.error)); return { ok: false, texto: r.error }; }
        current = r.data;
        const d = current.identity;
        panel.replaceChildren(h('h3', null, current.r1), h('dl', { class: 'mono' },
            ...[['Nombre R1', d.nombre], ['R2 vinculada', current.r2], ['ID R2', d.id_r], ['MAC R2', d.mac_r], ['HW', d.hw], ['Firmware', d.fw], ['CRC32', current.crc32]]
              .flatMap(([k, v]) => [h('dt', null, k), h('dd', null, v)])),
            h('p', { class: 'hint' }, 'Se conserva la configuración existente en EEPROM, incluido su nombre.'));
        message('Datos cargados. Revisa la R1 física y la R2 asociada antes de programar.'); enable();
        return { ok: true, texto: 'R1 y datos de R2 cargados para STM32.' };
    }
    async function scan(code) {
        if (!String(code || '').trim()) return { ok: false, texto: 'Indica una tarjeta o QR.' };
        const r = await api('/api/consulta?codigo=' + encodeURIComponent(code));
        if (!r.ok) { message(r.error, true); return { ok: false, texto: r.error }; }
        const p = r.data.tarjeta?.r1 || (r.data.pcb?.tipo === 'R1' ? r.data.pcb : null);
        if (!p) { message('El código no corresponde a una tarjeta con R1.', true); return { ok: false, texto: 'No se encontró R1.' }; }
        return choose(p);
    }
    async function loadList() {
        const r = await api('/api/pcb?tipo=R1&limit=500&q=' + encodeURIComponent(search.value));
        if (!alive || !r.ok) return;
        list.replaceChildren(...r.data.items.map(p => h('button', { class: 'prog-item', type: 'button', onclick: () => choose(p), disabled: busy }, p.nombre)));
        if (!r.data.items.length) list.append(h('p', null, 'Sin coincidencias. También puedes cargar un QR o número con Buscar.'));
    }
    let debounce;
    search.addEventListener('input', () => { clearTimeout(debounce); debounce = setTimeout(loadList, 250); });
    search.addEventListener('keydown', e => { if (e.key === 'Enter') scan(search.value); });
    async function download(url, body) {
        const resp = await fetch(url, body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : {});
        if (!resp.ok) { const d = await resp.json(); throw new Error(d.detail || 'Error al descargar'); }
        const filename = /filename="([^"]+)"/.exec(resp.headers.get('Content-Disposition') || '')?.[1] || 'TQT.hex';
        const u = URL.createObjectURL(await resp.blob()), a = h('a', { href: u, download: filename });
        document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(u), 10000);
    }
    async function program() {
        if (!current || busy) return;
        busy = true; enable();
        const r = await api('/api/stm32/jobs', { method: 'POST', body: { pcb_id: current.pcb_id, station_id: station.value, hex_sha256: current.hex_sha256 } });
        if (!r.ok) { busy = false; enable(); message(r.error, true); return; }
        message('Trabajo enviado. Confirma la R1 conectada en la ventana del agente Windows.');
        async function poll() {
            const r = await api('/api/stm32/jobs/' + rJob);
            if (!alive) return;
            if (!r.ok) { message('No se pudo consultar el resultado. La grabación no se repite; recuperando conexión…', true); timer = setTimeout(poll, 3000); return; }
            const j = r.data;
            if (['queued', 'running'].includes(j.state)) { timer = setTimeout(poll, 2000); return; }
            busy = false; await stations(); enable();
            message(j.state === 'verified' ? 'STM32 programado y verificado por lectura · FW ' + j.payload.identity.fw + ' · UID ' + j.result.uid : (j.result?.error || 'No se confirmó la programación. Revisa la estación y la tarjeta.'), j.state !== 'verified');
        }
        const rJob = r.data.id; timer = setTimeout(poll, 1000);
    }
    loadList(); stations();
    return { escaneo: scan, actualizar() { if (!busy) { loadList(); stations(); } }, desmontar() { alive = false; clearTimeout(timer); clearTimeout(debounce); } };
};
