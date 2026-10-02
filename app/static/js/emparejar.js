/**
 * emparejar.js - Armado de tarjetas: R1 + R2 + R3.
 * Por defecto se unen por el mismo número de serie; las fallas se reemplazan con otra placa suelta
 * del mismo tipo (tarjetas "impares", p. ej. R1 0021 + R2 0010).
 * API: GET /api/emparejar/sugerencias · POST /api/emparejar/auto · GET/POST/DELETE /api/tarjetas
 *      PUT /api/tarjetas/{id}/asignar · POST /api/pcb/{id}/falla · GET /api/pcb
 */
document.addEventListener('DOMContentLoaded', () => {
    'use strict';
    const T = window.TQT;
    const { h, api, icon, toast, sheet } = T;
    const $ = (id) => document.getElementById(id);

    T.hydrateIcons();
    T.mountShell({ active: 'emparejar', sub: 'Emparejar' });

    const r3Guardado = () => { try { return localStorage.getItem('tqt.r3modo') === 'auto' ? 'auto' : 'manual'; } catch (e) { return 'manual'; } };
    const state = { r3: r3Guardado(), loteId: null, sug: { completas: [], impares: [], r3_pendientes: [], incompletas: [], sueltas: { R1: [], R2: [], R3: [] } }, tarjetas: [], q: '' };
    const SLOTS = ['R1', 'R2', 'R3'];
    const slotPcb = (t, s) => t[s.toLowerCase()] || null;

    // ------------------------------------------------------------------ carga
    async function loadLote() {
        const r = await api('/api/status');
        if (r.ok && r.data && r.data.active_lote) state.loteId = r.data.active_lote.id;
    }
    async function loadAll() {
        const q = state.loteId ? `?lote_id=${state.loteId}` : '';
        const [s, t] = await Promise.all([api(`/api/emparejar/sugerencias?r3=${state.r3}${state.loteId ? `&lote_id=${state.loteId}` : ''}`), api(`/api/tarjetas?limit=500${state.loteId ? `&lote_id=${state.loteId}` : ''}`)]);
        if (s.ok && s.data) state.sug = { completas: s.data.completas || [], impares: s.data.impares || [], r3_pendientes: s.data.r3_pendientes || [], incompletas: s.data.incompletas || [], sueltas: Object.assign({ R1: [], R2: [], R3: [] }, s.data.sueltas || {}) };
        else toast(s.error || 'No se pudo leer el inventario', { kind: 'bad' });
        if (t.ok && t.data) state.tarjetas = t.data.items || [];
        render();
    }
    const reloadSoon = T.debounce(loadAll, 300);

    // ------------------------------------------------------------------ vistas
    /** Chip del tipo + serie. Con `grupo` se omite la serie cuando coincide con la de la fila (no se repite 3 veces). */
    const chipSerie = (tipo, p, grupo) => {
        const verTxt = p && p.version !== T.VERSION_DEFAULT ? `v${p.version}` : '';
        const txt = !p ? '—' : (grupo && p.serie === grupo ? verTxt : p.serie + (verTxt ? ' ' + verTxt : ''));
        return h('span', { class: 'row', style: 'gap:5px' }, T.tipoChip(tipo, { empty: !p }),
            txt ? h('span', { class: 'mono', style: `font-size:13px;${p ? '' : 'color:var(--faint)'}` }, txt) : null);
    };

    function render() {
        const { completas, impares, r3_pendientes, incompletas, sueltas } = state.sug;
        const porHacer = completas.length + impares.length + r3_pendientes.length;
        $('nComp').textContent = String(completas.length);
        $('nInc').textContent = String(incompletas.length);
        $('nSue').textContent = String(SLOTS.reduce((n, s) => n + (sueltas[s] || []).length, 0));
        $('nTar').textContent = String(state.tarjetas.length);
        $('autoCount').textContent = String(porHacer);
        $('btnAuto').disabled = !porHacer;
        $('btnDesTodas').disabled = !state.tarjetas.length;

        const comp = $('comp'); comp.replaceChildren();
        if (!completas.length) {
            comp.className = 'empty'; comp.removeAttribute('role');
            comp.append(icon('link'), h('b', null, 'No hay series completas'), h('span', null, 'Recibe y confirma placas en Recibir, o arma una tarjeta a mano.'));
        } else {
            comp.className = 'list'; comp.setAttribute('role', 'list');
            completas.forEach((c) => comp.appendChild(h('div', { class: 'item', role: 'listitem', style: 'grid-template-columns:auto 1fr auto' },
                h('span', { class: 'mono', style: 'font-size:24px;font-weight:600' }, c.serie),
                h('div', { class: 'row wrap', style: 'gap:6px 10px' }, chipSerie('R1', c.r1, c.serie), chipSerie('R2', c.r2, c.serie), chipSerie('R3', c.r3, c.serie)),
                h('button', { class: 'btn btn-sm', type: 'button', onclick: () => autoPair([c.serie]) }, 'Unir'))));
        }

        // impares: R1 y R2 de distinto número que sobran, emparejadas en orden
        const imp = $('imp'); imp.replaceChildren();
        $('secImp').hidden = !impares.length;
        impares.forEach((c) => imp.appendChild(h('div', { class: 'item', role: 'listitem', style: 'grid-template-columns:auto 1fr' },
            h('span', { class: 'mono', style: 'font-size:22px;font-weight:600' }, c.serie),
            h('div', { class: 'row wrap', style: 'gap:6px 10px' }, chipSerie('R1', c.r1), chipSerie('R2', c.r2), chipSerie('R3', c.r3)))));
        imp.className = 'list';

        const inc = $('inc'); inc.replaceChildren();
        $('secInc').hidden = !incompletas.length;
        incompletas.forEach((c) => inc.appendChild(h('div', { class: 'item', role: 'listitem', style: 'grid-template-columns:auto 1fr auto' },
            h('span', { class: 'mono', style: 'font-size:22px;font-weight:600;color:var(--muted)' }, c.serie),
            h('div', { class: 'row wrap', style: 'gap:6px 10px' }, chipSerie('R1', c.r1, c.serie), chipSerie('R2', c.r2, c.serie), chipSerie('R3', c.r3, c.serie)),
            h('span', { class: 't2' }, `Falta ${(c.faltan || []).join(', ')}`))));
        inc.className = 'list';

        renderTarjetas();
    }

    function tarjetaRow(t) {
        const r1 = slotPcb(t, 'R1'), r2 = slotPcb(t, 'R2'), r3 = slotPcb(t, 'R3');
        const series = [r1, r2, r3].filter(Boolean).map((p) => p.serie);
        const impar = new Set(series).size > 1 || (r1 && r1.serie !== t.id_tarjeta_num);
        const flags = [];
        if (!(r1 && r2 && r3)) flags.push(T.badge('Incompleta', 'warn'));
        if ((t.sin_mac || []).length) flags.push(T.badge('Sin MAC', 'warn'));
        if (impar) flags.push(T.badge('Impar', 'info'));
        return h('button', { class: 'item', type: 'button', style: 'grid-template-columns:auto 1fr auto', 'aria-label': `Tarjeta ${t.id_tarjeta_num}. Abrir`, onclick: () => openCard(t.id) },
            h('span', { class: 'mono', style: 'font-size:24px;font-weight:600' }, t.id_tarjeta_num),
            h('div', { class: 'stack', style: 'gap:6px' },
                h('div', { class: 'row wrap', style: 'gap:6px 10px' }, chipSerie('R1', r1, t.id_tarjeta_num), chipSerie('R2', r2, t.id_tarjeta_num), chipSerie('R3', r3, t.id_tarjeta_num)),
                flags.length ? h('div', { class: 'row wrap', style: 'gap:6px' }, flags) : null),
            h('span', { class: 'tail' }, T.tarjetaBadge(t)));
    }

    function renderTarjetas() {
        const box = $('tar'); box.replaceChildren();
        const q = state.q.trim().toLowerCase();
        const rows = state.tarjetas.slice().sort((a, b) => String(a.id_tarjeta_num).localeCompare(String(b.id_tarjeta_num))).filter((t) => !q || [t.id_tarjeta_num, t.nombre_r1, t.nombre_r2, t.nombre_r3, t.mac_r1, t.mac_r2].some((v) => String(v || '').toLowerCase().includes(q)));
        if (!rows.length) {
            box.className = 'empty';
            box.append(icon('box'), h('b', null, state.tarjetas.length ? 'Sin coincidencias' : 'Aún no hay tarjetas'), h('span', null, state.tarjetas.length ? 'Cambia la búsqueda.' : 'Empareja las series completas para crear la primera.'));
            return;
        }
        box.className = 'list';
        rows.forEach((t) => box.appendChild(tarjetaRow(t)));
    }

    // ------------------------------------------------------------------ emparejar en automático
    let pairing = false;
    async function autoPair(series) {
        if (pairing) return;
        pairing = true;
        try { await autoPair1(series); } finally { pairing = false; }
    }
    async function autoPair1(series) {
        const body = { lote_id: state.loteId || undefined, r3: state.r3 };
        if (series) body.series = series;
        const r = await api('/api/emparejar/auto', { method: 'POST', body });
        if (!r.ok) { window.SoundFX.playError(); toast(r.error || 'No se pudo emparejar', { kind: 'bad' }); return; }
        const n = ((r.data && r.data.creadas) || []).length;
        const n3 = ((r.data && r.data.r3_asignadas) || []).length;
        const om = (r.data && r.data.omitidas) || [];
        if (n || n3) { window.SoundFX.playComplete(); window.Haptics.success(); }
        toast(n || n3 ? [n ? `${n} tarjeta${n === 1 ? '' : 's'} creada${n === 1 ? '' : 's'}` : '', n3 ? `${n3} R3 montada${n3 === 1 ? '' : 's'}` : ''].filter(Boolean).join(' · ') : 'No se creó ninguna tarjeta', { kind: n || n3 ? 'ok' : 'bad' });
        if (om.length) toast(`${om.length} omitida${om.length === 1 ? '' : 's'}: ${om.slice(0, 3).map((o) => `${o.serie} (${o.motivo})`).join(', ')}`, { ms: 5000 });
        loadAll();
    }
    $('btnAuto').addEventListener('click', () => autoPair(null));

    // R3: manual (por defecto, se asigna a mano en cada tarjeta) o automática (par e impar por número)
    function pintarR3() {
        $('segR3').querySelectorAll('button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.v === state.r3)));
        $('hintR3').textContent = state.r3 === 'auto'
            ? 'Las R3 se unen solas: la del mismo número y, en las impares, la siguiente que sobre en orden. También se montan las que llegaron después.'
            : 'Solo se emparejan R1 y R2. La R3 la asignas tú en cada tarjeta (Abrir tarjeta → Asignar R3).';
    }
    $('segR3').addEventListener('click', (e) => {
        const b = e.target.closest('button[data-v]'); if (!b || b.dataset.v === state.r3) return;
        state.r3 = b.dataset.v; try { localStorage.setItem('tqt.r3modo', state.r3); } catch (er) { /* sin almacenamiento */ }
        pintarR3(); loadAll();
    });
    pintarR3();

    // ------------------------------------------------------------------ desemparejar todas
    $('btnDesTodas').addEventListener('click', () => {
        const n = state.tarjetas.length; if (!n) return;
        const forzar = h('input', { type: 'checkbox', id: 'dtForzar' });
        const err = h('div', { class: 'hint err', role: 'alert' });
        sheet({
            title: `¿Desemparejar las ${n} tarjetas?`,
            body: [
                h('p', null, 'Todas las placas vuelven a quedar sueltas para emparejarlas otra vez. No se borra ninguna placa ni MAC.'),
                h('label', { class: 'row', for: 'dtForzar', style: 'gap:8px' }, forzar, 'Incluir las que ya tienen pruebas registradas'), err,
            ],
            actions: [
                { label: 'Conservar', kind: 'ghost', onClick: () => true },
                { label: `Desemparejar ${n}`, kind: 'danger', keepOpen: true, onClick: async () => {
                    const r = await api('/api/tarjetas/disolver', { method: 'POST', body: { todas: true, lote_id: state.loteId || undefined, forzar: forzar.checked } });
                    if (!r.ok) { err.textContent = r.error; return false; }
                    const d = r.data.disueltas.length, om = r.data.omitidas.length;
                    toast(`${d} tarjeta${d === 1 ? '' : 's'} desemparejada${d === 1 ? '' : 's'}${om ? `; ${om} omitida${om === 1 ? '' : 's'} (tienen pruebas)` : ''}`, { kind: om && !d ? 'bad' : 'ok' });
                    loadAll(); return true;
                } },
            ],
        });
    });

    // ------------------------------------------------------------------ selector de placas sueltas
    /** Elige una PCB DISPONIBLE del tipo dado, por lista o escaneando su QR. */
    function pickPcb({ tipo, title, onPick }) {
        let items = []; let q = '';
        const list = h('div', { class: 'list', style: 'max-height:38dvh;overflow:auto' });
        const search = h('input', { class: 'input', type: 'search', inputmode: 'numeric', placeholder: 'Buscar serie', 'aria-label': 'Buscar placa', autocomplete: 'off' });
        const host = h('div', { hidden: true });
        let visor = null;
        const draw = () => {
            list.replaceChildren();
            const rows = items.filter((p) => !q || p.nombre.toLowerCase().includes(q));
            if (!rows.length) { list.className = 'empty'; list.append(icon('box'), h('b', null, 'No hay placas sueltas'), h('span', null, `No queda ninguna ${tipo} disponible${q ? ' con esa búsqueda' : ''}.`)); return; }
            list.className = 'list';
            rows.forEach((p) => list.appendChild(h('button', { class: 'item', type: 'button', onclick: () => choose(p) },
                T.tipoChip(p.tipo), h('div', null, h('div', { class: 't1' }, p.nombre), h('div', { class: 't2' }, `Recibida ${T.hora(p.recibida_en)}`)), icon('chevron'))));
        };
        const sh = sheet({
            title,
            body: [
                h('div', { class: 'row' }, search, h('button', { class: 'btn btn-sm', type: 'button', onclick: () => {
                    host.hidden = !host.hidden;
                    if (!host.hidden && !visor) visor = T.mountVisor(host, { compact: true, onCode });
                    else if (host.hidden && visor) { visor.stop(); visor = null; host.replaceChildren(); }
                } }, icon('qr'), 'Escanear')),
                host, list,
            ],
            focus: false,
            onClose: () => { if (visor) visor.stop(); },
        });
        function choose(p) { sh.close(); onPick(p); }
        function onCode(text) {
            const parsed = T.parseNombre(text);
            const hit = parsed && items.find((p) => p.nombre === parsed.nombre);
            if (hit) { window.SoundFX.playScan(hit.tipo); window.Haptics.scan(); choose(hit); }
            else { window.SoundFX.playError(); window.Haptics.error(); toast(parsed ? `${parsed.nombre} no está disponible como ${tipo}` : 'Código no reconocido', { kind: 'bad' }); }
        }
        search.addEventListener('input', () => { search.value = search.value.replace(/[^0-9a-zA-Z-]/g, ''); q = search.value.toLowerCase(); draw(); });
        api(`/api/pcb?tipo=${tipo}&estado_ciclo=DISPONIBLE&limit=500`).then((r) => { items = (r.ok && r.data && r.data.items) || []; draw(); });
        return sh;
    }

    // ------------------------------------------------------------------ tarjeta abierta
    async function openCard(id) {
        const r = await api(`/api/tarjetas/${id}`);
        if (!r.ok) { toast(r.error || 'No se pudo abrir la tarjeta', { kind: 'bad' }); return; }
        const t = r.data;
        const err = h('div', { class: 'hint err', role: 'alert' });
        let sh; let forceDissolve = false;
        const reopen = async () => { if (sh) sh.close(); await loadAll(); openCard(id); };

        const slotRow = (s) => {
            const p = slotPcb(t, s);
            const acts = h('div', { class: 'row', style: 'gap:6px' });
            if (p) {
                acts.append(
                    h('button', { class: 'btn btn-sm', type: 'button', onclick: () => pickPcb({ tipo: s, title: `Reemplazar ${s}`, onPick: async (np) => {
                        const u = await api(`/api/tarjetas/${id}/asignar`, { method: 'PUT', body: { ranura: s, pcb_id: np.id } });
                        if (!u.ok) { toast(u.error, { kind: 'bad' }); return; } toast(`${s} reemplazada`, { kind: 'ok' }); reopen();
                    } }) }, 'Cambiar'),
                    h('button', { class: 'btn btn-sm btn-danger', type: 'button', onclick: () => openFalla(p, s) }, 'Falla'));
            } else {
                acts.append(h('button', { class: 'btn btn-sm btn-primary', type: 'button', onclick: () => pickPcb({ tipo: s, title: `Asignar ${s}`, onPick: async (np) => {
                    const u = await api(`/api/tarjetas/${id}/asignar`, { method: 'PUT', body: { ranura: s, pcb_id: np.id } });
                    if (!u.ok) { toast(u.error, { kind: 'bad' }); return; } toast(`${s} asignada`, { kind: 'ok' }); reopen();
                } }) }, 'Asignar'));
            }
            return h('div', { class: 'slot', dataset: { empty: p ? '' : '1' }, style: 'grid-template-columns:auto 1fr;row-gap:8px' },
                T.tipoChip(s, { lg: true, empty: !p }),
                h('div', null, h('div', { class: 'nm' }, p ? p.nombre : 'Sin placa asignada'), p ? h('div', { class: 'mc' }, ['Hardware V' + p.version, s !== 'R3' ? (p.mac || 'sin MAC todavía') : null, s !== 'R3' && (p.firmware || t['firmware_' + s.toLowerCase()]) ? 'Firmware ' + (p.firmware || t['firmware_' + s.toLowerCase()]) : null].filter(Boolean).join(' · ')) : null),
                h('span'), acts);
        };

        function openFalla(p, s) {
            let repl = null;
            const motivo = h('input', { class: 'input', id: 'fMot', maxlength: 120, placeholder: 'Motivo (opcional)', 'aria-label': 'Motivo de la falla' });
            const replInfo = h('div', { class: 'mono', style: 'font-weight:600' }, 'Sin reemplazo por ahora');
            const ferr = h('div', { class: 'hint err', role: 'alert' });
            sheet({
                title: `Falla en ${p.nombre}`,
                body: [
                    h('p', { class: 'muted' }, 'La placa sale de la tarjeta y queda marcada como FALLA. Puedes poner otra suelta en su lugar ahora o después.'),
                    h('div', { class: 'field' }, h('label', { for: 'fMot' }, 'Motivo'), motivo),
                    h('div', { class: 'field' }, h('label', null, 'Reemplazo'), replInfo,
                        h('button', { class: 'btn btn-sm', type: 'button', onclick: () => pickPcb({ tipo: s, title: `Reemplazo para ${s}`, onPick: (np) => { repl = np; replInfo.textContent = np.nombre; } }) }, 'Elegir reemplazo')),
                    ferr,
                ],
                actions: [
                    { label: 'Cancelar', kind: 'ghost', onClick: () => true },
                    { label: 'Marcar falla', kind: 'danger', keepOpen: true, onClick: async () => {
                        const u = await api(`/api/pcb/${p.id}/falla`, { method: 'POST', body: { motivo: motivo.value || undefined, reemplazo_id: repl ? repl.id : undefined } });
                        if (!u.ok) { ferr.textContent = u.error; return false; }
                        window.SoundFX.playDup(); toast(`${p.nombre} marcada en falla${repl ? ` · reemplazo ${repl.nombre}` : ''}`, { kind: 'ok' }); reopen(); return true;
                    } },
                ],
            });
        }

        sh = sheet({
            title: `Tarjeta ${t.id_tarjeta_num}`,
            body: [
                h('div', { class: 'row wrap' }, T.tarjetaBadge(t)),
                h('div', { class: 'card-t' }, SLOTS.map(slotRow)),
                err,
            ],
            actions: [
                { label: 'Disolver tarjeta', kind: 'danger', icon: 'unlink', keepOpen: true, onClick: async (btn) => {
                    const u = await api(`/api/tarjetas/${id}${forceDissolve ? '?forzar=1' : ''}`, { method: 'DELETE' });
                    if (u.status === 409 && !forceDissolve) {
                        forceDissolve = true;
                        err.textContent = `${u.error} Toca otra vez para disolver de todos modos.`;
                        btn.textContent = 'Disolver de todos modos';
                        return false;
                    }
                    if (!u.ok && u.status !== 204) { err.textContent = u.error; return false; }
                    toast(`Tarjeta ${t.id_tarjeta_num} disuelta: sus placas quedaron sueltas`, { kind: 'ok' }); loadAll(); return true;
                } },
                { label: 'Listo', kind: 'primary', onClick: () => true },
            ],
            focus: false,
        });
    }

    // ------------------------------------------------------------------ armar a mano
    $('btnArmar').addEventListener('click', () => {
        const pick = { R1: null, R2: null, R3: null };
        const num = h('input', { class: 'input mono', id: 'bNum', inputmode: 'numeric', maxlength: 4, placeholder: 'Igual al de la R1', 'aria-label': 'Número de tarjeta' });
        num.addEventListener('input', () => { num.value = num.value.replace(/\D/g, ''); num.dataset.touched = '1'; });
        const err = h('div', { class: 'hint err', role: 'alert' });
        const cells = {};
        const row = (s) => {
            const nm = h('span', { class: 'mono', style: 'font-weight:600' }, 'Sin elegir'); cells[s] = nm;
            return h('div', { class: 'slot', style: 'grid-template-columns:auto 1fr auto' }, T.tipoChip(s, { lg: true, empty: true }), nm,
                h('button', { class: 'btn btn-sm', type: 'button', onclick: () => pickPcb({ tipo: s, title: `Elegir ${s}`, onPick: (p) => {
                    pick[s] = p; nm.textContent = p.nombre; nm.style.color = '';
                    if (s === 'R1' && !num.dataset.touched) num.value = p.serie;
                } }) }, 'Elegir'));
        };
        sheet({
            title: 'Armar tarjeta a mano',
            body: [
                h('p', { class: 'muted' }, 'Sirve para tarjetas impares: cualquier R1, R2 y R3 sueltas, aunque tengan números distintos.'),
                h('div', { class: 'card-t' }, SLOTS.map(row)),
                h('div', { class: 'field' }, h('label', { for: 'bNum' }, 'Número de tarjeta'), num), err,
            ],
            actions: [
                { label: 'Cancelar', kind: 'ghost', onClick: () => true },
                { label: 'Crear tarjeta', kind: 'primary', keepOpen: true, onClick: async () => {
                    err.textContent = '';
                    if (!pick.R1 && !pick.R2 && !pick.R3) { err.textContent = 'Elige al menos una placa'; return false; }
                    const body = { lote_id: state.loteId || undefined, r1_id: pick.R1 && pick.R1.id, r2_id: pick.R2 && pick.R2.id, r3_id: pick.R3 && pick.R3.id };
                    if (num.value) body.id_tarjeta_num = num.value.padStart(4, '0');
                    const r = await api('/api/tarjetas', { method: 'POST', body });
                    if (!r.ok) { err.textContent = r.error; window.SoundFX.playError(); return false; }
                    window.SoundFX.playComplete(); toast(`Tarjeta ${r.data.id_tarjeta_num} creada`, { kind: 'ok' }); loadAll(); return true;
                } },
            ],
        });
    });

    $('filtro').addEventListener('input', (e) => { state.q = e.target.value; renderTarjetas(); });

    const ws = T.ws();
    if (ws) ['TARJETA_ACTUALIZADA', 'PCB_ACTUALIZADA', 'PCB_ELIMINADA', 'PCB_RECIBIDA', 'RECEPCION_CONFIRMADA', 'EXCEL_IMPORTADO'].forEach((e) => ws.on(e, reloadSoon));
    T.resync(() => reloadSoon());

    loadLote().then(loadAll);
});
