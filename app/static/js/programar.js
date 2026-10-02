/**
 * programar.js - Captura de la MAC y del firmware (versión con la que se programó) de las placas R1 y R2.
 * La R3 no lleva MAC ni firmware. Se escanea el QR de la placa (o se elige de "Pendientes"), se teclea la MAC con el
 * teclado hexadecimal propio, se elige el firmware del catálogo (R1 = Principal, R2 = Respaldo) o se escribe otro,
 * y se guarda todo junto; luego salta a la siguiente pendiente.
 * API: GET /api/pcb/por-codigo · GET /api/pcb?sin_mac=1 · GET /api/firmware · PUT /api/pcb/{id}/programacion {mac, firmware}
 */
document.addEventListener('DOMContentLoaded', () => {
    'use strict';
    const T = window.TQT;
    const { h, api, icon, toast } = T;
    const $ = (id) => document.getElementById(id);

    T.mountShell({ active: 'programar', sub: 'Programación' });

    const state = { pend: [], active: null, tipo: '', q: '', raw: '', native: false, dupOf: null, fw: { R1: [], R2: [] } };
    const OTRA = '__otra', NADA = '';
    const ROL = { R1: 'Principal', R2: 'Respaldo' };
    const fwKey = (t) => 'tqt.fw.' + t;
    const ultimoFw = (t) => { try { return localStorage.getItem(fwKey(t)) || ''; } catch (e) { return ''; } };
    const recordarFw = (t, v) => { try { localStorage.setItem(fwKey(t), v); } catch (e) { /* modo privado */ } };

    async function loadFw() {
        const r = await api('/api/firmware');
        if (r.ok && r.data) state.fw = { R1: r.data.R1 || [], R2: r.data.R2 || [] };
    }

    // ------------------------------------------------------------------ pendientes
    async function loadPend() {
        const r = await api('/api/pcb?sin_mac=1&limit=1000');
        if (!r.ok) { toast(r.error || 'No se pudieron cargar las pendientes', { kind: 'bad' }); return; }
        state.pend = ((r.data && r.data.items) || [])
            .filter((p) => p.tipo !== 'R3' && !p.mac && p.estado_ciclo !== 'FALLA' && p.estado_ciclo !== 'BAJA')
            .sort((a, b) => a.serie.localeCompare(b.serie) || a.tipo.localeCompare(b.tipo));
        renderList();
    }
    const reloadSoon = T.debounce(loadPend, 300);

    function visible() {
        const q = state.q.trim().toLowerCase();
        return state.pend.filter((p) => (!state.tipo || p.tipo === state.tipo) && (!q || p.nombre.toLowerCase().includes(q) || p.serie.includes(q)));
    }

    function renderList() {
        const box = $('lista');
        const rows = visible();
        box.replaceChildren();
        if (!rows.length) {
            box.className = 'empty';
            box.appendChild(icon('check'));
            box.appendChild(h('b', null, state.pend.length ? 'Sin coincidencias' : 'Todo tiene MAC'));
            box.appendChild(h('span', null, state.pend.length ? 'Prueba con otra serie o quita el filtro.' : 'No hay placas R1 o R2 esperando MAC.'));
            return;
        }
        box.className = 'list';
        rows.forEach((p) => box.appendChild(h('button', {
            class: 'item', type: 'button', 'aria-label': `Capturar MAC de ${p.nombre}`,
            'aria-current': state.active && state.active.id === p.id ? 'true' : null,
            style: state.active && state.active.id === p.id ? 'background:var(--surface-2);box-shadow:inset 3px 0 0 var(--accent)' : null,
            onclick: () => select(p),
        },
            T.tipoChip(p.tipo),
            h('div', null, h('div', { class: 't1' }, p.nombre), h('div', { class: 't2' }, `Hardware V${p.version} · ` + (p.id_tarjeta_num ? `Tarjeta ${p.id_tarjeta_num}` : 'Sin tarjeta todavía'))),
            h('span', { class: 'tail' }, icon('chevron')))));
    }

    // ------------------------------------------------------------------ placa activa
    function select(p) {
        state.active = p; state.raw = (p && p.mac ? p.mac : '').replace(/[^0-9A-F]/gi, '').toUpperCase(); state.dupOf = null;
        renderList(); renderActive();
        const a = $('activo'); if (a && a.scrollIntoView) a.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }

    function nextAfter(p) {
        const rows = visible();
        if (!rows.length) return null;
        const i = rows.findIndex((x) => x.id === (p && p.id));
        return rows[i + 1] || rows.find((x) => !p || x.id !== p.id) || null;
    }

    let field, hint, btnSave, keypad, fwField;
    function renderActive() {
        const box = $('activo');
        box.replaceChildren();
        const p = state.active;
        if (!p) {
            box.className = 'empty';
            box.append(icon('programar'), h('b', null, 'Escanea la placa que acabas de programar'),
                h('span', null, 'Apunta la cámara al QR de una R1 o R2, o elige una de la lista. La R3 no lleva MAC ni firmware.'));
            return;
        }
        if (p.tipo === 'R3') { renderR3(p); return; }
        box.className = 'panel';
        field = h('input', {
            class: 'input mono macfield', id: 'macIn', type: 'text', autocomplete: 'off', autocapitalize: 'characters', spellcheck: 'false',
            inputmode: state.native ? 'text' : 'none', maxlength: 60, placeholder: '00:00:00:00:00:00', 'aria-label': 'Dirección MAC', 'aria-describedby': 'macHint',
            value: T.formatMacProgress(state.raw),
        });
        hint = h('div', { class: 'hint', id: 'macHint', role: 'status', 'aria-live': 'polite' });
        // Firmware con el que se programó la placa: catálogo por rol (R1 Principal, R2 Respaldo) u otra versión escrita a mano
        const cat = (state.fw[p.tipo] || []).slice();
        const previo = p.firmware || ultimoFw(p.tipo);
        if (p.firmware && !cat.includes(p.firmware)) cat.push(p.firmware);
        const inicial = previo ? (cat.includes(previo) ? previo : OTRA) : (cat.length ? NADA : OTRA);
        const fwSel = h('select', { class: 'input mono', id: 'fwSel', 'aria-label': `Firmware ${ROL[p.tipo]} de la ${p.tipo}`, onchange: () => { fwIn.hidden = fwSel.value !== OTRA; if (!fwIn.hidden) fwIn.focus(); } },
            h('option', { value: NADA, selected: inicial === NADA ? '' : null }, 'Sin indicar'),
            ...cat.map((v) => h('option', { value: v, selected: inicial === v ? '' : null }, v)),
            h('option', { value: OTRA, selected: inicial === OTRA ? '' : null }, 'Otra versión…'));
        const fwIn = h('input', { class: 'input mono', id: 'fwIn', type: 'text', maxlength: 40, autocomplete: 'off', spellcheck: 'false', placeholder: 'Ej. 4.1 o 2.3-beta', 'aria-label': 'Otra versión de firmware',
            value: inicial === OTRA ? (previo || '') : '', hidden: inicial === OTRA ? null : true });
        fwField = h('div', { class: 'field' },
            h('label', { for: 'fwSel' }, `Firmware · ${ROL[p.tipo]} (${p.tipo})`), fwSel, fwIn, h('div', { class: 'hint err', id: 'fwHint', role: 'alert' }));
        btnSave = h('button', { class: 'btn btn-primary grow', type: 'button', onclick: save }, icon('check'), 'Guardar MAC y firmware');
        const key = (ch, cls) => h('button', { type: 'button', class: cls || (/[A-F]/.test(ch) ? 'alpha' : ''), 'aria-label': ch, onclick: () => push(ch) }, ch);
        keypad = h('div', { class: 'keypad', role: 'group', 'aria-label': 'Teclado hexadecimal', hidden: state.native ? true : null },
            ...'ABCDEF'.split('').map((c) => key(c)), ...'012345'.split('').map((c) => key(c)),
            ...'6789'.split('').map((c) => key(c)),
            h('button', { type: 'button', class: 'wide', 'aria-label': 'Borrar último dígito', onclick: back }, icon('back'), 'Borrar'));
        field.addEventListener('input', () => {
            const v = field.value;
            // Pegado con texto alrededor ("MAC: 70:4b:..."): 'MAC' contiene A y C, que también son hex; hay que extraer la MAC entera.
            const pegada = /[^0-9A-Fa-f:.\-\s]/.test(v) || v.replace(/[^0-9A-Fa-f]/g, '').length > 12 ? T.parseMac(v) : null;
            state.raw = (pegada ? pegada.replace(/:/g, '') : v.replace(/[^0-9A-Fa-f]/g, '')).toUpperCase().slice(0, 12);
            sync();
        });
        field.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); save(); } });

        const other = p.tarjeta;
        box.append(
            h('div', { style: 'padding:14px 14px 4px', class: 'stack' },
                h('div', { class: 'row' }, T.tipoChip(p.tipo, { lg: true }),
                    h('span', { class: 'mono', style: 'font-size:18px;font-weight:600;overflow-wrap:anywhere' }, p.nombre)),
                h('div', { class: 'hint' }, `Hardware V${p.version} · ` + (p.id_tarjeta_num || (other && other.id_tarjeta_num)
                    ? `Tarjeta ${p.id_tarjeta_num || other.id_tarjeta_num}` : 'Aún no está en una tarjeta')),
                p.mac ? T.banner('warn', 'info', 'Esta placa ya tiene MAC' + (p.firmware ? ' y firmware ' + p.firmware : '') + '. Si guardas, se reemplazan.') : null),
            h('div', { class: 'macbox', style: 'padding:6px 14px 14px' },
                field, hint, fwField,
                h('div', { class: 'row' },
                    h('button', { class: 'btn', type: 'button', onclick: skip }, 'Omitir'),
                    btnSave),
                keypad,
                h('div', { class: 'row', style: 'gap:6px' },
                    h('button', { class: 'btn btn-sm btn-ghost grow', type: 'button', onclick: pasteMac }, icon('paste'), 'Pegar'),
                    h('button', { class: 'btn btn-sm btn-ghost grow', type: 'button', onclick: toggleNative, id: 'btnNative' }, icon('keyboard'), state.native ? 'Propio' : 'Teléfono'),
                    h('button', { class: 'btn btn-sm btn-ghost grow', type: 'button', onclick: () => { state.raw = ''; sync(); } }, 'Limpiar'))),
        );
        sync();
    }

    // La R3 no lleva MAC ni firmware: solo un aviso amable (no hay nada que capturar)
    function renderR3(p) {
        const box = $('activo'); box.className = 'panel';
        box.replaceChildren(h('div', { class: 'stack', style: 'padding:14px' },
            h('div', { class: 'row' }, T.tipoChip('R3', { lg: true }), h('span', { class: 'mono', style: 'font-size:18px;font-weight:600;overflow-wrap:anywhere' }, p.nombre)),
            T.banner('info', 'info', 'La R3 no lleva MAC ni firmware. No hay nada que capturar aquí: escanea una R1 o una R2.'),
            h('div', { class: 'row' }, h('button', { class: 'btn grow', type: 'button', onclick: () => { state.active = null; renderList(); renderActive(); } }, 'Entendido'))));
    }

    function push(ch) { if (state.raw.length < 12) { state.raw += ch; sync(); if (window.Haptics) window.Haptics.vibrate(12); } }
    function back() { state.raw = state.raw.slice(0, -1); sync(); }

    let dupTimer = null;
    function sync() {
        if (!field) return;
        const shown = T.formatMacProgress(state.raw);
        if (field.value !== shown) field.value = shown;
        const n = state.raw.length;
        field.setAttribute('aria-invalid', 'false');
        state.dupOf = null;
        if (n === 12) {
            const mac = shown;
            if (parseInt(state.raw.slice(0, 2), 16) & 1) {
                field.setAttribute('aria-invalid', 'true'); btnSave.disabled = true; clearTimeout(dupTimer);
                hint.className = 'hint err'; hint.textContent = 'MAC inválida: el primer par debe ser par (multicast). Revisa que esté bien copiada.';
                return;
            }
            if (/^(0{12}|F{12})$/.test(state.raw)) {
                field.setAttribute('aria-invalid', 'true'); btnSave.disabled = true; clearTimeout(dupTimer);
                hint.className = 'hint err'; hint.textContent = 'MAC inválida: todo ceros o todo F no es una MAC real.';
                return;
            }
            hint.className = 'hint ok'; hint.textContent = 'MAC completa. Revisando que no esté repetida…';
            btnSave.disabled = false;
            clearTimeout(dupTimer);
            dupTimer = setTimeout(async () => {
                const r = await api(`/api/pcb?q=${encodeURIComponent(mac)}&limit=5`);
                if (state.raw.length !== 12 || T.formatMacProgress(state.raw) !== mac) return;
                const dup = r.ok && r.data && (r.data.items || []).find((x) => x.mac === mac && (!state.active || x.id !== state.active.id));
                if (dup) {
                    state.dupOf = dup; field.setAttribute('aria-invalid', 'true');
                    hint.className = 'hint err'; hint.textContent = `Esta MAC ya pertenece a ${dup.nombre}`;
                    btnSave.disabled = true; window.SoundFX.playDup(); window.Haptics.dup();
                } else { hint.className = 'hint ok'; hint.textContent = 'MAC válida y sin repetir'; }
            }, 200);
        } else {
            btnSave.disabled = true;
            hint.className = 'hint';
            hint.textContent = n === 0 ? 'Teclea los 12 dígitos que muestra el programador.' : `Faltan ${12 - n} dígito${12 - n === 1 ? '' : 's'}`;
        }
    }

    async function pasteMac() {
        try {
            const txt = await navigator.clipboard.readText();
            const mac = T.parseMac(txt);
            if (mac) { state.raw = mac.replace(/:/g, ''); sync(); toast('MAC pegada', { kind: 'ok', ms: 1200 }); return; }
            toast('El portapapeles no tiene una MAC válida', { kind: 'bad' });
        } catch (e) {
            state.native = true; renderActive();
            toast('Pega con el teclado del teléfono (mantén pulsado el campo)', { ms: 3500 });
            const f = $('macIn'); if (f) f.focus();
        }
    }
    function toggleNative() { state.native = !state.native; renderActive(); if (state.native) { const f = $('macIn'); if (f) f.focus(); } }

    let saving = false;
    async function save() {
        const p = state.active;
        if (!p || state.raw.length !== 12 || state.dupOf || saving) return;
        if (btnSave.disabled) return; // MAC inválida (multicast, ceros…) ya marcada en el aviso
        const mac = T.formatMacProgress(state.raw);
        saving = true; btnSave.disabled = true;
        const sel = fwField && p === state.active ? $('fwSel') : null;
        const fw = sel ? (sel.value === OTRA ? ($('fwIn').value || '').trim() : sel.value) : '';
        if (sel && sel.value === OTRA && !fw) {
            saving = false; btnSave.disabled = false; $('fwIn').setAttribute('aria-invalid', 'true');
            $('fwHint').textContent = 'Escribe la versión de firmware o elige "Sin indicar".'; $('fwIn').focus(); return;
        }
        if (sel) { $('fwIn').removeAttribute('aria-invalid'); $('fwHint').textContent = ''; }
        const r = await api(`/api/pcb/${p.id}/programacion`, { method: 'PUT', body: fw ? { mac, firmware: fw } : { mac } });
        const fwMsg = r.ok && fw ? ` · Firmware ${fw}` : '';
        if (r.ok && fw) { recordarFw(p.tipo, fw); await loadFw(); }
        saving = false;
        if (r.ok && state.active !== p) { state.pend = state.pend.filter((x) => x.id !== p.id); renderList(); return; } // cambió de placa mientras guardaba
        if (!r.ok && state.active !== p) { toast(`${p.nombre}: ${r.error}`, { kind: 'bad' }); return; }
        if (!r.ok) {
            window.SoundFX.playError(); window.Haptics.error();
            hint.className = 'hint err'; hint.textContent = r.error; field.setAttribute('aria-invalid', 'true'); btnSave.disabled = false;
            return;
        }
        window.SoundFX.playSuccess(); window.Haptics.success();
        toast(`${p.nombre} · ${mac}${fwMsg}`, { kind: 'ok' });
        const nxt = nextAfter(p);
        state.pend = state.pend.filter((x) => x.id !== p.id);
        state.active = null; state.raw = '';
        if (nxt) select(nxt); else { renderList(); renderActive(); }
    }

    function skip() { const n = nextAfter(state.active); if (n) select(n); else toast('No hay más pendientes'); }

    // ------------------------------------------------------------------ escaneo
    async function onCode(text) {
        const parsed = T.parseNombre(text);
        if (!parsed) { window.SoundFX.playError(); window.Haptics.error(); toast('Código no reconocido', { kind: 'bad' }); return; }
        window.SoundFX.playScan(parsed.tipo); window.Haptics.scan();
        const r = await api(`/api/pcb/por-codigo?codigo=${encodeURIComponent(parsed.nombre)}`);
        if (!r.ok) { window.SoundFX.playError(); window.Haptics.error(); toast(r.status === 404 ? `${parsed.nombre} no está registrada` : r.error, { kind: 'bad' }); return; }
        select(r.data);
    }

    // ------------------------------------------------------------------ filtros y arranque
    $('segTipo').addEventListener('click', (e) => {
        const b = e.target.closest('button'); if (!b) return;
        state.tipo = b.dataset.f;
        $('segTipo').querySelectorAll('button').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
        renderList();
    });
    $('filtro').addEventListener('input', (e) => { state.q = e.target.value; renderList(); });

    const ws = T.ws();
    if (ws) { ['PCB_ACTUALIZADA', 'PCB_ELIMINADA', 'PCB_RECIBIDA', 'RECEPCION_CONFIRMADA', 'TARJETA_ACTUALIZADA'].forEach((e) => ws.on(e, reloadSoon)); }
    T.resync(() => reloadSoon());

    T.mountVisor($('visorHost'), { compact: true, onCode });
    renderActive();
    loadFw().then(() => { if (state.active) renderActive(); });
    loadPend();
    document.addEventListener('tqt:lote-cambiado', (e) => e.preventDefault());   // las pendientes son globales
});
