/**
 * recibir.js - Recepción continua de PCB (estilo caja registradora).
 * La cámara lee el QR `TQT-R#-V##-####`; cada placa se agrega sola al borrador.
 * El operador confirma el lote completo o corrige/elimina partidas antes.
 * API: POST /api/pcb/escanear · GET /api/recepcion · POST /api/recepcion/confirmar
 *      PATCH/DELETE /api/pcb/{id} · POST /api/pcb/manual · POST /api/pcb/version · GET/PUT /api/ajustes
 */
document.addEventListener('DOMContentLoaded', () => {
    'use strict';
    const T = window.TQT;
    const { h, api, icon, toast, sheet } = T;
    const $ = (id) => document.getElementById(id);

    T.hydrateIcons();
    T.mountShell({ active: 'recibir', sub: 'Recepción' });

    const state = {
        items: [],              // borrador confirmado por el servidor (RECIBIDA)
        pending: [],            // lecturas optimistas aún sin respuesta: {tmp, parsed, codigo, err}
        known: new Map(),       // nombre -> pcb (todo el inventario) para detectar repetidas al instante
        huecos: {}, avisos: [],
        version: T.VERSION_DEFAULT,
        seq: 0,
    };

    // ------------------------------------------------------------------ lectura serigráfica
    const ro = { box: $('readout'), serie: $('roSerie'), tipo: $('roTipo'), name: $('roName'), msg: $('roMsg') };
    function showRead(o) {
        ro.box.dataset.idle = o.idle ? '1' : '';
        ro.box.dataset.k = o.kind || '';
        ro.serie.textContent = o.serie || '0000';
        ro.tipo.replaceChildren(o.tipo ? T.tipoChip(o.tipo, { lg: true }) : '');
        ro.name.textContent = o.nombre || o.name || '';
        ro.msg.textContent = o.msg || '';
    }

    // ------------------------------------------------------------------ contadores y avisos
    function counts() {
        const c = { R1: 0, R2: 0, R3: 0 };
        state.items.forEach((p) => { if (c[p.tipo] !== undefined) c[p.tipo]++; });
        state.pending.forEach((p) => { if (!p.err && c[p.parsed.tipo] !== undefined) c[p.parsed.tipo]++; });
        c.total = c.R1 + c.R2 + c.R3;
        return c;
    }
    let lastCounts = { R1: 0, R2: 0, R3: 0, total: 0 };
    function renderCounters() {
        const c = counts();
        [['R1', 'cR1'], ['R2', 'cR2'], ['R3', 'cR3'], ['total', 'cT']].forEach(([k, id]) => {
            const el = $(id);
            if (el.textContent !== String(c[k])) {
                el.textContent = String(c[k]);
                if (c[k] > lastCounts[k]) { el.classList.remove('bump'); void el.offsetWidth; el.classList.add('bump'); }
            }
        });
        lastCounts = c;
        $('ctaCount').textContent = String(c.total);
        $('btnConfirm').disabled = c.total === 0 || state.pending.length > 0;   // con lecturas aún sin enviar (o sin red) no se confirma el lote
    }

    // El servidor también describe los huecos dentro de `avisos`; aquí ya se listan con sus números.
    const avisosSinHuecos = () => (state.avisos || []).filter((a) => !/^R[123]: faltan \d+/.test(a));
    function renderAvisos() {
        const box = $('avisos');
        box.replaceChildren();
        const c = counts();
        if (!c.total) return;
        const msgs = [];
        const hs = Object.entries(state.huecos || {}).filter(([, v]) => v && v.length);
        hs.forEach(([t, v]) => msgs.push(`Faltan en ${t}: ${v.slice(0, 8).join(', ')}${v.length > 8 ? ` y ${v.length - 8} más` : ''}`));
        avisosSinHuecos().forEach((a) => msgs.push(a));
        if (msgs.length) box.appendChild(T.banner('warn', 'alert', h('b', null, 'Revisa antes de confirmar'), ...msgs.map((m) => h('div', null, m))));
    }

    // ------------------------------------------------------------------ lista
    function row(p, opts = {}) {
        const btn = h('button', {
            class: 'item' + (opts.enter ? ' enter' : ''), type: 'button',
            dataset: { pending: opts.pending ? '1' : '', err: opts.err ? '1' : '', id: p.id || '' },
            'aria-label': `${p.nombre}. Tocar para editar`,
            onclick: () => { if (opts.pending || opts.err) { if (opts.err) retryPending(opts.tmp); return; } openEdit(p); },
        },
            T.tipoChip(p.tipo),
            h('div', null, h('div', { class: 't1' }, p.nombre),
                h('div', { class: 't2' }, opts.err ? 'Sin enviar: toca para reintentar' : opts.pending ? 'Registrando…' : `${T.hora(p.recibida_en)} · ${p.origen === 'MANUAL' ? 'sin QR' : 'QR'}`)),
            h('span', { class: 'tail' }, opts.err ? icon('refresh') : opts.pending ? '' : icon('edit')));
        return btn;
    }

    let lastIds = new Set();
    function renderList() {
        const box = $('lista');
        box.replaceChildren();
        const rows = [];
        state.pending.forEach((p) => rows.push(row({ tipo: p.parsed.tipo, nombre: p.parsed.nombre }, { pending: !p.err, err: p.err, tmp: p.tmp, enter: true })));
        state.items.forEach((p) => rows.push(row(p, { enter: !lastIds.has(p.id) && lastIds.size > 0 })));
        lastIds = new Set(state.items.map((p) => p.id));
        if (!rows.length) {
            box.replaceWith(h('div', { id: 'lista', class: 'empty' }, icon('recibir'), h('b', null, 'Todavía no hay placas'),
                h('span', null, 'Acerca una placa a la cámara. El QR está grabado en su cara trasera, junto al número.')));
        } else {
            if (box.classList.contains('empty')) box.className = 'list';
            box.append(...rows);
        }
        renderCounters();
        renderAvisos();
    }
    function ensureListBox() {
        const cur = $('lista');
        if (cur && cur.classList.contains('empty')) {
            const list = h('div', { id: 'lista', class: 'list' });
            cur.replaceWith(list);
        }
    }

    // ------------------------------------------------------------------ carga
    async function loadInventory() {
        const r = await api('/api/pcb?limit=5000');
        if (r.ok && r.data) { state.known.clear(); (r.data.items || []).forEach((p) => state.known.set(p.nombre, p)); }
    }
    async function loadDraft() {
        const r = await api('/api/recepcion');
        if (!r.ok) { toast(r.error || 'No se pudo cargar el lote', { kind: 'bad' }); return; }
        state.items = (r.data && r.data.items) || [];
        state.huecos = (r.data && r.data.huecos) || {};
        state.avisos = (r.data && r.data.avisos) || [];
        state.items.forEach((p) => state.known.set(p.nombre, p));
        ensureListBox();
        renderList();
    }
    const reloadSoon = T.debounce(() => { loadDraft(); loadInventory(); }, 250);

    async function loadVersion() {
        const r = await api('/api/ajustes');
        if (r.ok && r.data && r.data.version_defecto) state.version = String(r.data.version_defecto);
        $('verChip').textContent = 'V' + state.version;
    }

    // ------------------------------------------------------------------ lectura de códigos
    const sessionSeen = new Set();

    function onCode(text) {
        const parsed = T.parseNombre(text);
        if (!parsed) {
            window.SoundFX.playError(); window.Haptics.error();
            showRead({ kind: 'bad', msg: 'Código no reconocido', name: text.length > 40 ? text.slice(0, 40) + '…' : text });
            return;
        }
        const known = state.known.get(parsed.nombre);
        if (known || sessionSeen.has(parsed.nombre)) return duplicated(parsed, known);

        // Lectura válida y nueva: confirmar de inmediato con sonido/vibración y registrar en segundo plano.
        window.SoundFX.playScan(parsed.tipo); window.Haptics.scan();
        showRead({ kind: 'ok', tipo: parsed.tipo, serie: parsed.serie, nombre: parsed.nombre, msg: 'Leída · registrando…' });
        sessionSeen.add(parsed.nombre);
        const item = { tmp: ++state.seq, parsed, codigo: text, err: false };
        state.pending.unshift(item);
        ensureListBox(); renderList();
        send(item);
    }

    function duplicated(parsed, pcb) {
        window.SoundFX.playDup(); window.Haptics.dup();
        const ciclo = pcb ? (T.CICLO_LABEL[pcb.estado_ciclo] || pcb.estado_ciclo || '').toLowerCase() : 'ya leída';
        showRead({ kind: 'warn', tipo: parsed.tipo, serie: parsed.serie, nombre: parsed.nombre, msg: `Ya registrada${ciclo ? ` · ${ciclo}` : ''}` });
        const inDraft = pcb && state.items.find((p) => p.id === pcb.id);
        if (inDraft) {   // resalta la fila sin mover la página: el visor debe seguir a la vista mientras se escanea
            const el = document.querySelector(`.item[data-id="${pcb.id}"]`);
            if (el) { el.classList.remove('enter'); void el.offsetWidth; el.classList.add('enter'); }
        }
    }

    async function send(item) {
        const r = await api('/api/pcb/escanear', { method: 'POST', body: { codigo: item.codigo }, timeout: 6000 });
        const i = state.pending.findIndex((p) => p.tmp === item.tmp);
        if (r.network || (!r.ok && r.status >= 500)) {
            if (i >= 0) state.pending[i].err = true;
            showRead({ kind: 'bad', tipo: item.parsed.tipo, serie: item.parsed.serie, nombre: item.parsed.nombre, msg: r.network ? 'Sin conexión: se enviará al volver la red' : 'El servidor falló: se reintentará solo' });
            renderList();
            return;
        }
        if (i >= 0) state.pending.splice(i, 1);
        const d = r.data || {};
        if (r.ok && d.resultado === 'AGREGADA' && d.pcb) {
            state.known.set(d.pcb.nombre, d.pcb);
            if (!state.items.some((p) => p.id === d.pcb.id)) state.items.unshift(d.pcb);
            showRead({ kind: 'ok', tipo: d.pcb.tipo, serie: d.pcb.serie, nombre: d.pcb.nombre, msg: `Registrada · V${d.pcb.version}` });
        } else if (d.resultado === 'DUPLICADA') {
            if (d.pcb) state.known.set(d.pcb.nombre, d.pcb);
            duplicated(item.parsed, d.pcb || null);
        } else {
            sessionSeen.delete(item.parsed.nombre);
            window.SoundFX.playError(); window.Haptics.error();
            showRead({ kind: 'bad', tipo: item.parsed.tipo, serie: item.parsed.serie, nombre: item.parsed.nombre, msg: d.mensaje || r.error || 'No se pudo registrar' });
        }
        renderList();
    }

    function retryPending(tmp) {
        const it = state.pending.find((p) => p.tmp === tmp);
        if (!it) return;
        it.err = false; renderList(); send(it);
    }
    setInterval(() => { state.pending.filter((p) => p.err).forEach((p) => retryPending(p.tmp)); }, 12000);

    // ------------------------------------------------------------------ edición de una partida
    function openEdit(p) {
        let tipo = p.tipo;
        const inVer = h('input', { class: 'input mono', id: 'edVer', inputmode: 'numeric', maxlength: 3, value: p.version, 'aria-label': 'Versión de hardware' });
        const inSer = h('input', { class: 'input mono', id: 'edSer', inputmode: 'numeric', maxlength: 4, value: p.serie, 'aria-label': 'Serie' });
        const prev = h('div', { class: 'mono', style: 'font-size:17px;font-weight:600', 'aria-live': 'polite' });
        const err = h('div', { class: 'hint err', role: 'alert' });
        const segBtns = ['R1', 'R2', 'R3'].map((t) => h('button', { type: 'button', 'aria-pressed': String(t === tipo), onclick: () => { tipo = t; segBtns.forEach((b, i) => b.setAttribute('aria-pressed', String(['R1', 'R2', 'R3'][i] === t))); upd(); } }, t));
        const upd = () => { prev.textContent = T.nombreDe(tipo, inVer.value || '?', inSer.value || '?'); };
        [inVer, inSer].forEach((i) => i.addEventListener('input', () => { i.value = i.value.replace(/\D/g, ''); upd(); }));
        upd();
        sheet({
            title: 'Editar placa',
            body: [
                h('div', { class: 'field' }, h('label', null, 'Tipo'), h('div', { class: 'seg' }, segBtns)),
                h('div', { class: 'row' },
                    h('div', { class: 'field grow' }, h('label', { for: 'edVer' }, 'Hardware (V)'), inVer),
                    h('div', { class: 'field grow' }, h('label', { for: 'edSer' }, 'Serie'), inSer)),
                h('div', { class: 'field' }, h('label', null, 'Quedará como'), prev),
                err,
            ],
            actions: [
                { label: 'Eliminar', kind: 'danger', icon: 'trash', onClick: async () => { const ok = await removePcb(p); return ok; } },
                { label: 'Guardar', kind: 'primary', keepOpen: true, onClick: async () => {
                    err.textContent = '';
                    const body = {};
                    if (tipo !== p.tipo) body.tipo = tipo;
                    if (inVer.value && inVer.value !== p.version) body.version = inVer.value;
                    if (inSer.value && inSer.value !== p.serie) body.serie = inSer.value.padStart(4, '0');
                    if (!Object.keys(body).length) return true;
                    const r = await api(`/api/pcb/${p.id}`, { method: 'PATCH', body });
                    if (!r.ok) { err.textContent = r.error; window.SoundFX.playError(); return false; }
                    toast('Cambios guardados', { kind: 'ok' });
                    await Promise.all([loadDraft(), loadInventory()]);
                    return true;
                } },
            ],
        });
    }

    async function removePcb(p) {
        const r = await api(`/api/pcb/${p.id}`, { method: 'DELETE' });
        if (!r.ok && r.status !== 204) { toast(r.error || 'No se pudo eliminar', { kind: 'bad' }); return false; }
        state.known.delete(p.nombre); sessionSeen.delete(p.nombre);
        state.items = state.items.filter((x) => x.id !== p.id);
        renderList();
        toast(`${p.nombre} eliminada`, {
            action: { label: 'Deshacer', onClick: async () => {
                const u = p.origen === 'QR'   // conserva el origen: una placa leída por QR vuelve como QR
                    ? await api('/api/pcb/escanear', { method: 'POST', body: { codigo: p.nombre } }).then((x) => (x.ok && x.data && x.data.resultado === 'AGREGADA' ? x : { ok: false, error: x.error || (x.data && x.data.mensaje) }))
                    : await api('/api/pcb/manual', { method: 'POST', body: { tipo: p.tipo, version: p.version, serie: p.serie, cantidad: 1 } });
                if (u.ok) { toast('Restaurada', { kind: 'ok' }); reloadSoon(); } else toast(u.error || 'No se pudo restaurar', { kind: 'bad' });
            } },
        });
        return true;
    }

    // ------------------------------------------------------------------ versión por defecto y en masa
    $('btnVersion').addEventListener('click', () => {
        const inp = h('input', { class: 'input mono', id: 'verIn', inputmode: 'numeric', maxlength: 3, value: state.version, 'aria-label': 'Versión de hardware' });
        inp.addEventListener('input', () => { inp.value = inp.value.replace(/\D/g, ''); });
        const err = h('div', { class: 'hint err', role: 'alert' });
        sheet({
            title: 'Versión de hardware',
            body: [
                h('p', { class: 'muted' }, 'Es la versión de HARDWARE: el número que va después de la V en el nombre (TQT-R1-V30-0021). No es el firmware. Un QR leído trae su propia versión; esta se usa en las altas sin QR.'),
                h('div', { class: 'field' }, h('label', { for: 'verIn' }, 'Hardware por defecto (V)'), inp), err,
                state.items.length ? h('p', { class: 'hint' }, `Puedes cambiarla también en las ${state.items.length} placas sin confirmar de este lote.`) : null,
            ],
            actions: [
                ...(state.items.length ? [{ label: `Aplicar a las ${state.items.length}`, keepOpen: true, onClick: async () => {
                    if (!inp.value) { err.textContent = 'Escribe una versión'; return false; }
                    const r = await api('/api/pcb/version', { method: 'POST', body: { ids: state.items.map((p) => p.id), version: inp.value } });
                    if (!r.ok) { err.textContent = r.error; return false; }
                    toast(`Hardware V${inp.value} aplicado`, { kind: 'ok' }); await Promise.all([loadDraft(), loadInventory()]); return true;
                } }] : []),
                { label: 'Guardar', kind: 'primary', onClick: async () => {
                    if (!inp.value) { err.textContent = 'Escribe una versión'; return false; }
                    const r = await api('/api/ajustes', { method: 'PUT', body: { version_defecto: inp.value } });
                    if (!r.ok) { err.textContent = r.error; return false; }
                    state.version = String((r.data && r.data.version_defecto) || inp.value); $('verChip').textContent = 'V' + state.version; return true;
                } },
            ],
        });
    });

    // ------------------------------------------------------------------ agregar sin QR
    function openManual() {
        let tipo = 'R1';
        const inVer = h('input', { class: 'input mono', id: 'mnVer', inputmode: 'numeric', maxlength: 3, value: state.version });
        const inSer = h('input', { class: 'input mono', id: 'mnSer', inputmode: 'numeric', maxlength: 4, placeholder: 'Automática' });
        const qty = h('input', { id: 'mnQty', inputmode: 'numeric', value: '1', 'aria-label': 'Cantidad' });
        const err = h('div', { class: 'hint err', role: 'alert' });
        const prev = h('div', { class: 'mono', style: 'font-size:17px;font-weight:600' });
        const segBtns = ['R1', 'R2', 'R3'].map((t) => h('button', { type: 'button', 'aria-pressed': String(t === tipo), onclick: () => { tipo = t; segBtns.forEach((b, i) => b.setAttribute('aria-pressed', String(['R1', 'R2', 'R3'][i] === t))); upd(); } }, t));
        const clamp = () => { const n = Math.max(1, Math.min(200, parseInt(qty.value || '1', 10) || 1)); qty.value = String(n); return n; };
        const upd = () => { prev.textContent = inSer.value ? T.nombreDe(tipo, inVer.value || '?', inSer.value) : `TQT-${tipo}-V${inVer.value || '?'}-(siguiente libre)`; };
        [inVer, inSer, qty].forEach((i) => i.addEventListener('input', () => { i.value = i.value.replace(/\D/g, ''); upd(); }));
        upd();
        sheet({
            title: 'Agregar sin QR',
            body: [
                h('p', { class: 'muted' }, 'Para placas sin número grabado. Si dejas la serie vacía se usa el siguiente número libre; escríbelo en la placa.'),
                h('div', { class: 'field' }, h('label', null, 'Tipo'), h('div', { class: 'seg' }, segBtns)),
                h('div', { class: 'row' },
                    h('div', { class: 'field grow' }, h('label', { for: 'mnVer' }, 'Hardware (V)'), inVer),
                    h('div', { class: 'field grow' }, h('label', { for: 'mnSer' }, 'Serie'), inSer)),
                h('div', { class: 'field' }, h('label', { for: 'mnQty' }, 'Cantidad'), h('div', { class: 'stepper' },
                    h('button', { type: 'button', 'aria-label': 'Menos', onclick: () => { qty.value = String(Math.max(1, clamp() - 1)); } }, '−'), qty,
                    h('button', { type: 'button', 'aria-label': 'Más', onclick: () => { qty.value = String(Math.min(200, clamp() + 1)); } }, '+'))),
                h('div', { class: 'field' }, h('label', null, 'Quedará como'), prev), err,
            ],
            actions: [{ label: 'Agregar', kind: 'primary', keepOpen: true, onClick: async () => {
                err.textContent = '';
                const body = { tipo, version: inVer.value || state.version, cantidad: clamp() };
                if (inSer.value) body.serie = inSer.value.padStart(4, '0');
                const r = await api('/api/pcb/manual', { method: 'POST', body });
                if (!r.ok) { err.textContent = r.error; window.SoundFX.playError(); return false; }
                const n = ((r.data && r.data.pcbs) || []).length;
                window.SoundFX.playScan(tipo);
                toast(`${n} placa${n === 1 ? '' : 's'} agregada${n === 1 ? '' : 's'}`, { kind: 'ok' });
                await Promise.all([loadDraft(), loadInventory()]);
                return true;
            } }],
        });
    }
    $('btnManual').addEventListener('click', openManual);

    // ------------------------------------------------------------------ confirmar el lote
    $('btnConfirm').addEventListener('click', () => {
        const c = counts();
        const cell = (t) => h('div', { class: 'row' }, T.tipoChip(t), h('span', { class: 'mono', style: 'font-size:22px;font-weight:600' }, String(c[t])));
        const notes = [];
        Object.entries(state.huecos || {}).forEach(([t, v]) => { if (v && v.length) notes.push(T.banner('warn', 'alert', h('b', null, `Faltan en ${t}: `), v.slice(0, 12).join(', '))); });
        avisosSinHuecos().forEach((a) => notes.push(T.banner('warn', 'alert', a)));
        const err = h('div', { class: 'hint err', role: 'alert' });
        sheet({
            title: `Confirmar ${c.total} placa${c.total === 1 ? '' : 's'}`,
            body: [
                h('div', { class: 'row wrap', style: 'gap:18px' }, cell('R1'), cell('R2'), cell('R3')),
                ...notes,
                h('p', { class: 'muted' }, 'Al confirmar quedan disponibles para emparejar. Después aún puedes editarlas desde el monitor.'),
                err,
            ],
            actions: [
                { label: 'Seguir escaneando', kind: 'ghost', onClick: () => true },
                { label: 'Confirmar lote', kind: 'primary', keepOpen: true, onClick: async () => {
                    const r = await api('/api/recepcion/confirmar', { method: 'POST', body: {} });
                    if (!r.ok) { err.textContent = r.error; return false; }
                    window.SoundFX.playComplete(); window.Haptics.success();
                    const n = (r.data && r.data.confirmadas) || c.total;
                    toast(`${n} placas confirmadas`, { kind: 'ok', action: { label: 'Emparejar', onClick: () => { location.href = '/static/emparejar.html'; } } });
                    sessionSeen.clear();
                    showRead({ idle: true, name: 'Lote confirmado. Puedes seguir recibiendo.' });
                    await Promise.all([loadDraft(), loadInventory()]);
                    return true;
                } },
            ],
        });
    });

    // ------------------------------------------------------------------ tiempo real (otros celulares)
    const ws = T.ws();
    if (ws) {
        ['PCB_RECIBIDA', 'PCB_ACTUALIZADA', 'PCB_ELIMINADA', 'RECEPCION_CONFIRMADA'].forEach((e) => ws.on(e, () => reloadSoon()));
        ws.onStatus((s) => { if (s === 'connected') { reloadSoon(); state.pending.filter((p) => p.err).forEach((p) => retryPending(p.tmp)); } });
    }
    T.resync((motivo) => { if (motivo !== 'reconexion') reloadSoon(); });   // la reconexión ya recarga arriba

    // ------------------------------------------------------------------ arranque
    T.mountVisor($('visorHost'), { onCode, onManual: openManual });
    showRead({ idle: true });
    loadVersion();
    Promise.all([loadInventory(), loadDraft()]);
});
