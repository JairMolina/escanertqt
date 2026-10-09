/* R1 STM32: selection from inventory/remote QR; Windows J-Link station jobs. */
window.TQTSTM32 = function (host, ctx) {
    'use strict';
    const { h, api, T } = ctx;
    let alive = true, current = null, selectedPcb = null, busy = false, timer = null, requestN = 0, listN = 0;
    const unsubs = [];
    const search = h('input', { class: 'input', type: 'search', id: 'stm-q', autocomplete: 'off', placeholder: 'Número, nombre o QR de la tarjeta' });
    const list = h('div', { class: 'prog-lista' });
    const empty = T.empty('flash', 'Elige una R1', 'Búscala por número, nombre o QR a la izquierda, o elige una de la lista.');
    const panel = h('div', { class: 'prog-detalle' }, empty);
    const status = h('div', { class: 'prog-resultado', role: 'status', 'aria-live': 'polite' });
    const station = h('select', { class: 'input', id: 'stm-est' });
    const stationName = h('input', { class: 'input', value: 'PC de programación', id: 'stm-est-nombre', maxlength: 60 });
    const btnProgram = h('button', { class: 'btn btn-primary', type: 'button', disabled: true, onclick: program }, 'Programar STM32 con J-Link');
    const btnHex = h('button', { class: 'btn', type: 'button', disabled: true, onclick: async () => {
        try { await download('/api/stm32/hex/' + current.pcb_id); } catch (e) { message(e.message, true); }
    } }, 'Descargar HEX de esta R1');
    // v1.3.54: orden de programación de la pareja: ESP32 de R2 (MAC) → STM32 de R1 → ESP32 de R1 (MAC de R1)
    const btnEsp = h('button', { class: 'btn', type: 'button', disabled: true, onclick: async () => {
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
        btnSubir.disabled = true; message('Leyendo ' + f.name + '…');
        try {
            const r = await api('/api/stm32/hex/analizar', { method: 'POST', body: { contenido: await f.text() } });
            if (!r.ok) { message(f.name + ': ' + r.error, true); return; }
            const d = r.data; const igual = d.fw === d.base_fw && d.hw === d.base_hw;
            status.replaceChildren(T.banner(igual ? 'ok' : 'info', igual ? 'check' : 'info', h('div', null,
                h('b', null, f.name + ' · FW ' + d.fw), h('br'),
                'MCU ' + d.mcu + ' · HW ' + d.hw + ' · ' + (d.bytes / 1024).toFixed(0) + ' KB de aplicación' + (d.identidad ? ' · trae identidad ' + d.identidad : ''), h('br'),
                igual ? 'Es la misma versión que el firmware base de la app (FW ' + d.base_fw + ').' : 'El firmware base de la app es FW ' + d.base_fw + ' / HW ' + d.base_hw + '.')));
        } catch (e) { message(e.message, true); }
        finally { btnSubir.disabled = busy; }
    });
    const lookup = h('button', { class: 'btn', type: 'button', onclick: () => scan(search.value) }, 'Buscar / cargar QR');
    const bundleBtn = h('button', { class: 'btn', type: 'button', onclick: async () => {
        try { await download('/api/stm32/stations/installer', { name: stationName.value.trim() }); await stations(); }
        catch (e) { message(e.message, true); }
    } }, 'Instalar agente en esta laptop');
    host.append(h('div', { class: 'prog-wrap' },
        h('div', { class: 'prog-panel' }, h('h2', null, 'Elige una R1'),
          h('div', { class: 'field' }, h('label', { for: 'stm-q' }, 'Buscar'), search),
          h('div', { class: 'row wrap' }, lookup), list),
        h('div', { class: 'prog-panel prog-panel-detalle' }, panel,
          h('div', { class: 'field' }, h('label', { for: 'stm-est' }, 'Estación Windows conectada al J-Link'), station,
            h('div', { class: 'row wrap' }, h('button', { class: 'btn btn-sm btn-ghost', type: 'button', onclick: stations }, 'Actualizar estaciones'))),
          h('details', { class: 'prog-config' }, h('summary', null, 'Configurar esta computadora por primera vez'),
            h('div', { class: 'field' }, h('label', { for: 'stm-est-nombre' }, 'Nombre de estación Windows'), stationName),
            h('div', { class: 'row wrap' }, bundleBtn),
            h('p', { class: 'hint' }, 'Abre el archivo Instalar_TQT descargado una sola vez: instala el agente y lo deja iniciando con Windows en segundo plano. Después, todas las grabaciones se controlan desde esta pantalla. Usa Python 3.10+ y J-Link de SEGGER o STM32CubeIDE ya instalados.')),
          h('div', { class: 'row wrap' }, btnProgram, btnEsp, btnHex, btnSubir, hexIn),
          h('p', { class: 'hint' }, 'Orden de la pareja: 1) ESP32 de la R2 (da su MAC) · 2) STM32 de la R1 con la MAC y número de la R2 · 3) ESP32 de la R1 (da la MAC de la R1).'), status)));
    function message(text, bad = false) { status.replaceChildren(T.banner(bad ? 'bad' : 'info', bad ? 'alert' : 'info', text)); }
    function progress(job) {
        const stages = [
            ['queued', 'Esperando a la laptop'],
            ['preparing', 'Preparando firmware y datos de la R1'],
            ['writing', 'Conectando al STM32 y grabando firmware'],
            ['reading', 'Leyendo y verificando la grabación'],
            ['restarting', 'Reiniciando la tarjeta'],
            ['reporting', 'Guardando el resultado en la web']
        ];
        const stage = job.state === 'queued' ? 'queued' : (job.payload?.progress?.stage || 'preparing');
        const index = stages.findIndex(s => s[0] === stage);
        const pct = Math.round((index + 1) / stages.length * 100);
        status.replaceChildren(h('div', { class: 'prog-avance', 'aria-busy': 'true' },
            h('strong', null, 'Programando R1 ' + current.identity.nombre.slice(-4)),
            h('p', { class: 'hint' }, stages[index][1] + '…'),
            h('ol', { class: 'prog-pasos' }, ...stages.map(([key, label], n) => h('li', {
                class: 'prog-paso', 'aria-current': key === stage ? 'step' : null,
                dataset: { e: n < index ? 'ok' : n === index ? 'activo' : 'pendiente' }
            }, h('span', { class: 'prog-paso-ico' }), h('span', { class: 'prog-paso-t' }, label)))),
            h('div', { class: 'prog-bar', role: 'progressbar', 'aria-label': 'Programación STM32 en curso', 'aria-valuemin': '0', 'aria-valuemax': '100', 'aria-valuenow': String(pct) },
                h('div', { class: 'prog-bar-fill', style: 'width:' + pct + '%' })),
            h('p', { class: 'hint' }, 'No desconectes la R1 hasta que termine la verificación.')));
    }
    function enable() {
        btnProgram.textContent = busy ? 'Programando…' : current ? 'Programar R1 ' + current.identity.nombre.slice(-4) + ' con J-Link' : 'Programar STM32 con J-Link';
        btnProgram.disabled = busy || !current || !station.value || station.selectedOptions[0]?.dataset.online !== 'true';
        btnHex.disabled = busy || !current;
        btnEsp.disabled = busy || !current; btnSubir.disabled = busy;
        search.disabled = busy; lookup.disabled = busy; station.disabled = busy; bundleBtn.disabled = busy;
        list.querySelectorAll('button').forEach(b => b.disabled = busy);
    }
    async function stations() {
        const r = await api('/api/stm32/stations'); if (!alive) return;
        if (!r.ok) {
            [...station.options].forEach(o => o.dataset.online = 'false');
            enable(); return;
        }
        const selected = station.value;
        station.replaceChildren(h('option', { value: '' }, 'Elige una estación'));
        r.data.forEach(s => station.append(h('option', { value: s.id, dataset: { online: String(s.online) } }, s.name + (s.online ? ' · conectada' : ' · desconectada'))));
        if (selected && [...station.options].some(o => o.value === selected)) station.value = selected;
        else if (r.data.filter(s => s.online).length === 1) station.value = r.data.find(s => s.online).id;
        enable();
    }
    station.addEventListener('change', enable);
    async function choose(pcb, quiet = false) {
        if (busy) return { ok: false, texto: 'Hay una programación en curso.' };
        selectedPcb = pcb;
        const n = ++requestN; current = null; enable(); panel.replaceChildren(h('p', { class: 'hint' }, 'Cargando R1 y su R2…')); markSel();
        const r = await api('/api/stm32/preview/' + pcb.id);
        if (!alive || n !== requestN) return { ok: false, texto: 'Selección cambiada.' };
        if (!r.ok) { panel.replaceChildren(T.banner('bad', 'alert', r.error)); return { ok: false, texto: r.error }; }
        current = r.data;
        const d = current.identity;
        panel.replaceChildren(h('div', { class: 'prog-cab' }, T.tipoChip('R1'), h('span', { class: 'prog-nm' }, current.r1),
            h('span', { class: 'dim' }, 'R2 ' + current.r2)), h('dl', { class: 'prog-dl' },
            ...[['Nombre R1', d.nombre], ['R2 vinculada', current.r2], ['ID R2', d.id_r], ['MAC R2', d.mac_r], ['HW', d.hw], ['Firmware', d.fw], ['CRC32', current.crc32]]
              .flatMap(([k, v]) => [h('dt', null, k), h('dd', null, v)])),
            h('p', { class: 'hint' }, 'Al pulsar Programar confirmas que esta R1 es la conectada al J-Link. La grabación empieza directamente y el resultado aparece aquí.'),
            h('p', { class: 'hint' }, 'Se conserva la configuración existente en EEPROM, incluido su nombre.'));
        if (!quiet) message('Datos cargados. Revisa la R1 física y la R2 asociada antes de programar.'); enable();
        return { ok: true, texto: 'R1 y datos de R2 cargados para STM32.' };
    }
    async function scan(code) {
        if (busy) return { ok: false, texto: 'Hay una programación en curso.' };
        if (!String(code || '').trim()) return { ok: false, texto: 'Indica una tarjeta o QR.' };
        const r = await api('/api/consulta?codigo=' + encodeURIComponent(code));
        if (!r.ok) { message(r.error, true); return { ok: false, texto: r.error }; }
        const p = r.data.tarjeta?.r1 || (r.data.pcb?.tipo === 'R1' ? r.data.pcb : null) || r.data.serie?.r1;
        if (!p) { message('El código no corresponde a una tarjeta con R1.', true); return { ok: false, texto: 'No se encontró R1.' }; }
        return choose(p);
    }
    async function loadList() {
        const n = ++listN;
        const r = await api('/api/pcb?tipo=R1&limit=500&q=' + encodeURIComponent(search.value));
        if (!alive || n !== listN) return;
        if (!r.ok) { list.replaceChildren(T.banner('bad', 'alert', r.error)); return; }
        list.replaceChildren(...r.data.items.map(p => h('button', { class: 'prog-item', type: 'button', onclick: () => choose(p), disabled: busy,
            'aria-pressed': String(!!selectedPcb && selectedPcb.id === p.id), dataset: { id: p.id } },
            T.tipoChip('R1'), h('span', { class: 'nm' }, p.nombre), h('span', { class: 'dim' }, p.id_tarjeta_num ? '#' + String(p.id_tarjeta_num).padStart(4, '0') : 'Suelta'))));
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
    }
    async function program() {
        if (!current || busy) return;
        busy = true; enable();
        progress({ state: 'queued' });
        const r = await api('/api/stm32/jobs', { method: 'POST', body: { pcb_id: current.pcb_id, station_id: station.value, hex_sha256: current.hex_sha256, physical_confirmed: true } });
        if (!r.ok) { busy = false; enable(); message(r.error, true); return; }
        progress(r.data);
        async function poll() {
            const r = await api('/api/stm32/jobs/' + rJob);
            if (!alive) return;
            if (!r.ok) { message('Recuperando conexión para consultar el avance. No desconectes la R1; la grabación no se repite.', true); timer = setTimeout(poll, 3000); return; }
            const j = r.data;
            if (['queued', 'running'].includes(j.state)) { progress(j); timer = setTimeout(poll, 1000); return; }
            busy = false; await stations();
            if (selectedPcb) await choose(selectedPcb, true);
            enable();
            message(j.state === 'verified' ? '✓ STM32 programado y verificado por lectura · FW ' + j.payload.identity.fw + ' · UID ' + j.result.uid + '. Ya puedes desconectar la R1.' : (j.result?.error || 'No se confirmó la programación. Revisa la estación y la tarjeta.'), j.state !== 'verified');
        }
        const rJob = r.data.id; timer = setTimeout(poll, 1000);
    }
    function refresh() {
        if (!alive || busy) return;
        loadList(); stations();
        if (selectedPcb) choose(selectedPcb, true);
    }
    const ws = ctx.ws || (T.ws && T.ws());
    if (ws?.on) ['PCB_ACTUALIZADA', 'PCB_ELIMINADA', 'TARJETA_ACTUALIZADA', 'TARJETA_EMPAREJADA'].forEach(ev => unsubs.push(ws.on(ev, refresh)));
    loadList(); stations();
    const stationTimer = setInterval(() => { if (alive && !busy) stations(); }, 5000);
    return { escaneo: scan, ocupada() { return busy; }, actualizar: refresh, desmontar() { alive = false; clearTimeout(timer); clearTimeout(debounce); clearInterval(stationTimer); unsubs.forEach(fn => fn()); } };
};
