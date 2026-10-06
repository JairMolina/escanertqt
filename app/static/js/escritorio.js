/**
 * escritorio.js - Armazón de la consola de escritorio (PC, SIN cámara).
 * Barra lateral colapsable, cabecera (título, lote, conexión, tema), router por hash (#/seccion?param=x),
 * registro de secciones (window.TQTEscritorio.registrar) y utilidades compartidas (tablas, carga, error, copiar).
 * Contrato completo: docs/ESCRITORIO.md. Cada sección vive en js/sec_<id>.js.
 */
(function () {
    'use strict';
    const T = window.TQT;
    const { h, api, icon, toast } = T;

    const GRUPOS = { operacion: 'Operación', gestion: 'Gestión' };
    const ATAJOS = { r: 'resumen', i: 'inventario', t: 'tarjetas', m: 'macs', c: 'consultar', l: 'lotes', x: 'excel', o: 'movimientos', e: 'etiquetas', a: 'admin' };
    const ETQ_ATAJO = {}; Object.keys(ATAJOS).forEach((k) => { ETQ_ATAJO[ATAJOS[k]] = k; });

    const secciones = new Map();
    const S = {
        lotes: [], lote: null, cur: null, params: new URLSearchParams(), feed: [], feedFns: new Set(), sesion: { admin: false },
        cache: { pcb: null, tar: null, tarLote: undefined, pP: null, pT: null, gen: 0 }, lat: 'max', menu: null, primera: true,
    };
    let refs = {};

    function registrar(def) {
        if (!def || !def.id) return;
        secciones.set(def.id, Object.assign({ grupo: 'operacion', orden: 500, icono: 'circle', titulo: def.id }, def));
    }

    // ------------------------------------------------------------------ datos compartidos (con caché que se invalida por WS/lote)
    async function fetchAll(url, size) {
        const items = []; let total = Infinity;
        while (items.length < total) {
            const r = await api(`${url}${url.includes('?') ? '&' : '?'}limit=${size}&offset=${items.length}`, { timeout: 20000 });
            if (!r.ok) throw new Error(r.error || 'No se pudieron cargar los datos');
            if (!r.data || !Array.isArray(r.data.items)) return items;
            if (!r.data.items.length) break;
            items.push(...r.data.items); total = r.data.total;
        }
        return items;
    }
    function cargarPcb() {
        const c = S.cache;
        if (c.pcb) return Promise.resolve(c.pcb);
        if (c.pP) return c.pP;
        const gen = c.gen;
        c.pP = fetchAll('/api/pcb', 1000).then((items) => { if (gen === c.gen) c.pcb = items; return items; }).finally(() => { if (gen === c.gen) c.pP = null; });
        return c.pP;
    }
    function cargarTarjetas() {
        const c = S.cache; const lid = S.lote ? S.lote.id : null;
        if (c.tar && c.tarLote === lid) return Promise.resolve(c.tar);
        if (c.pT && c.tarLote === lid) return c.pT;
        const gen = c.gen; c.tarLote = lid;
        c.pT = fetchAll(`/api/tarjetas${lid ? `?lote_id=${lid}` : ''}`, 500).then((items) => { if (gen === c.gen) c.tar = items; return items; }).finally(() => { if (gen === c.gen) c.pT = null; });
        return c.pT;
    }
    function invalidar() { const c = S.cache; c.gen++; c.pcb = null; c.tar = null; c.pP = null; c.pT = null; }

    // ------------------------------------------------------------------ utilidades para las secciones
    function cargando(texto) {
        return h('div', { class: 'esc-cargando', role: 'status' }, h('span', { class: 'sr-only' }, texto || 'Cargando…'),
            h('div', { class: 'sk', style: 'height:44px' }), h('div', { class: 'sk', style: 'height:260px' }));
    }
    function errorBox(msg, reintentar) {
        return h('div', { class: 'esc-error' }, T.banner('bad', 'alert', h('b', null, 'No se pudieron cargar los datos. '), msg || 'Revisa la conexión.'),
            reintentar ? h('button', { class: 'btn', type: 'button', onclick: reintentar }, icon('refresh'), 'Reintentar') : null);
    }
    function copiar(texto, ok) {
        const mal = () => toast('No se pudo copiar: selecciona el texto y cópialo', { kind: 'bad' });
        if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(texto).then(() => toast(ok || 'Copiado', { kind: 'ok', ms: 1400 }), mal); else mal();
    }
    const MESES_C = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];
    function fecha(s) {
        if (!s) return '—';
        const d = new Date(String(s).replace(' ', 'T'));
        if (isNaN(d)) return String(s);
        const hoy = new Date();
        const base = `${T.hora(s)}`;
        if (d.toDateString() === hoy.toDateString()) return `hoy ${base}`;
        return `${d.getDate()} ${MESES_C[d.getMonth()]} ${base}`;
    }
    const cmp = (a, b) => (a === b ? 0 : a === null || a === undefined || a === '' ? 1 : b === null || b === undefined || b === '' ? -1 : String(a).localeCompare(String(b), 'es', { numeric: true }));

    /** Placa (R1/R2/R3) resumida para tablas y paneles: nombre en mono; MAC y firmware solo en R1/R2. */
    function placaCelda(p, slot) {
        if (!p) return h('span', { class: 'muted' }, '—');
        const r3 = slot === 'R3' || p.tipo === 'R3';
        return h('div', { class: 'esc-placa' }, h('span', { class: 'mono nm' }, p.nombre),
            r3 ? null : h('span', { class: 'mono sub' }, p.mac ? String(p.mac).toLowerCase() : 'sin MAC', p.firmware ? h('span', { class: 'fw' }, ` · fw ${p.firmware}`) : null));
    }

    /**
     * tabla({cols:[{id,titulo,cls,sort(a,b),cel(fila)}], rows, key(fila), sel:Set|null, onSel(), onOpen(fila), sort:{id,dir}, onSort(id),
     *        label(fila), abierta:key, limit, onMas(), vacio:{icono,titulo,texto}, caption})
     * Devuelve un nodo <div>. Teclado: flechas/Inicio/Fin mueven entre filas, Enter abre, Espacio marca.
     */
    function tabla(o) {
        const cols = o.cols;
        let rows = o.rows || [];
        if (o.sort && o.sort.id) {
            const c = cols.find((x) => x.id === o.sort.id);
            if (c) { const f = c.sort || ((a, b) => cmp(c.valor ? c.valor(a) : a[c.id], c.valor ? c.valor(b) : b[c.id])); const d = o.sort.dir === 'desc' ? -1 : 1; rows = rows.slice().sort((a, b) => d * f(a, b)); }
        }
        if (!rows.length) return h('div', { class: 'esc-tw' }, T.empty((o.vacio && o.vacio.icono) || 'box', (o.vacio && o.vacio.titulo) || 'Sin resultados', o.vacio && o.vacio.texto));
        const lim = o.limit || 200;
        const shown = rows.slice(0, lim);
        const keyOf = (f) => String(o.key(f));
        const t = h('table', { class: 'esc-t' });
        if (o.caption) t.append(h('caption', { class: 'sr-only' }, o.caption));
        const all = o.sel ? h('input', { type: 'checkbox', 'aria-label': 'Seleccionar todas las filas mostradas', tabindex: '-1', onchange: (e) => {
            shown.forEach((f) => { if (e.target.checked) o.sel.add(o.key(f)); else o.sel.delete(o.key(f)); });
            body.querySelectorAll('tr').forEach((tr) => { const on = o.sel.has(tr._f); tr.dataset.sel = on ? '1' : ''; const cb = tr.querySelector('input[type=checkbox]'); if (cb) cb.checked = on; });
            o.onSel && o.onSel();
        } }) : null;
        const sincro = () => { if (!all) return; const n = shown.filter((f) => o.sel.has(o.key(f))).length; all.checked = n > 0 && n === shown.length; all.indeterminate = n > 0 && n < shown.length; };
        t.append(h('thead', null, h('tr', null,
            o.sel ? h('th', { class: 'chk', scope: 'col' }, all) : null,
            cols.map((c) => {
                const on = o.sort && o.sort.id === c.id;
                const th = h('th', { scope: 'col', class: c.cls || null, 'aria-sort': c.sortable === false ? null : (on ? (o.sort.dir === 'desc' ? 'descending' : 'ascending') : 'none') });
                if (c.sortable === false) { th.append(c.titulo || h('span', { class: 'sr-only' }, c.sr || 'Acciones')); return th; }
                th.append(h('button', { class: 'esc-th', type: 'button', dataset: { col: c.id }, onclick: () => o.onSort && o.onSort(c.id) }, c.titulo, on ? h('span', { class: 'flecha', 'aria-hidden': 'true' }, o.sort.dir === 'desc' ? '▼' : '▲') : null));
                return th;
            }))));
        const body = h('tbody');
        shown.forEach((f, i) => {
            const k = keyOf(f);
            const tr = h('tr', { tabindex: i === 0 ? '0' : '-1', dataset: { k, sel: o.sel && o.sel.has(o.key(f)) ? '1' : '', abierta: o.abierta !== undefined && o.abierta !== null && String(o.abierta) === k ? '1' : '' }, 'aria-label': o.label ? o.label(f) : null });
            tr._f = o.key(f);
            if (o.sel) tr.append(h('td', { class: 'chk' }, h('input', { type: 'checkbox', tabindex: '-1', 'aria-label': `Marcar ${o.label ? o.label(f) : k}`, checked: o.sel.has(o.key(f)) ? '' : null, onchange: (e) => {
                if (e.target.checked) o.sel.add(o.key(f)); else o.sel.delete(o.key(f)); tr.dataset.sel = e.target.checked ? '1' : ''; sincro(); o.onSel && o.onSel();
            } })));
            cols.forEach((c) => tr.append(h('td', { class: c.cls || null }, c.cel(f))));
            tr.addEventListener('click', (e) => { if (e.target.closest('a,button,input,label,select')) return; o.onOpen && o.onOpen(f); });
            body.append(tr);
        });
        body.addEventListener('focusin', (e) => {
            const tr = e.target.closest('tr'); if (!tr) return;
            body.querySelectorAll('tr[tabindex="0"]').forEach((x) => { if (x !== tr) x.tabIndex = -1; });
            tr.tabIndex = 0;
        });
        body.addEventListener('keydown', (e) => {
            const tr = e.target.closest('tr'); if (!tr || e.target !== tr) return;
            const trs = [...body.querySelectorAll('tr')]; const i = trs.indexOf(tr);
            let dest = null;
            if (e.key === 'ArrowDown') dest = trs[Math.min(i + 1, trs.length - 1)];
            else if (e.key === 'ArrowUp') dest = trs[Math.max(i - 1, 0)];
            else if (e.key === 'Home') dest = trs[0];
            else if (e.key === 'End') dest = trs[trs.length - 1];
            else if (e.key === 'PageDown') dest = trs[Math.min(i + 10, trs.length - 1)];
            else if (e.key === 'PageUp') dest = trs[Math.max(i - 10, 0)];
            else if (e.key === 'Enter') { const f = shown[i]; if (o.onOpen && f) { e.preventDefault(); o.onOpen(f); } return; }
            else if (e.key === ' ' && o.sel) { e.preventDefault(); const cb = tr.querySelector('input[type=checkbox]'); if (cb) { cb.checked = !cb.checked; cb.dispatchEvent(new Event('change')); } return; }
            if (dest) { e.preventDefault(); dest.focus(); }
        });
        t.append(body);
        sincro();
        const wrap = h('div', { class: 'esc-tw' }, t);
        if (rows.length > lim) wrap.append(h('div', { class: 'esc-mas' }, h('span', { class: 'muted' }, `Mostrando ${lim} de ${rows.length}`),
            h('button', { class: 'btn', type: 'button', onclick: () => o.onMas && o.onMas() }, `Mostrar ${Math.min(200, rows.length - lim)} más`)));
        return wrap;
    }
    /** Reemplaza el contenido de host por la tabla, conservando el foco (fila o cabecera) si estaba dentro. */
    function pintarTabla(host, o) {
        const act = document.activeElement; let fila = null, col = null;
        if (host.contains(act)) {
            const tr = act.closest && act.closest('tr[data-k]');
            if (act.tagName === 'TR' && tr) fila = tr.dataset.k;
            else if (act.classList && act.classList.contains('esc-th')) col = act.dataset.col;
        }
        host.replaceChildren(tabla(o));
        if (fila !== null) { const tr = [...host.querySelectorAll('tr[data-k]')].find((x) => x.dataset.k === fila); if (tr) tr.focus(); }
        else if (col) { const b = host.querySelector(`.esc-th[data-col="${col}"]`); if (b) b.focus(); }
    }
    /** Alterna orden: misma columna invierte, otra empieza ascendente. */
    function alternarOrden(actual, id) { return actual && actual.id === id ? { id, dir: actual.dir === 'asc' ? 'desc' : 'asc' } : { id, dir: 'asc' }; }

    /** Ficha de una placa: tipo, nombre, estado, Hardware V30, serie y (solo R1/R2) MAC y Firmware. slot = 'R1'|'R2'|'R3'. */
    function placaCard(slot, p, hit) {
        if (!p) {
            return h('article', { class: 'esc-pl', dataset: { t: slot, vacia: '1' }, 'aria-label': `${slot} sin asignar` },
                h('header', null, T.tipoChip(slot, { lg: true, empty: true }), h('span', { class: 'nm muted', style: 'font-family:var(--font-ui);font-weight:500' }, 'Sin placa asignada')));
        }
        const campo = (l, v) => h('div', null, h('dt', null, l), h('dd', null, v === null || v === undefined || v === '' ? h('span', { class: 'muted' }, '—') : v));
        const cab = h('header', null, T.tipoChip(slot, { lg: true }), h('span', { class: 'nm' }, p.nombre), T.cicloBadge(p.estado_ciclo, Object.assign({ tipo: slot }, p)));
        const art = (kids) => h('article', { class: 'esc-pl', dataset: { t: slot, hit: hit ? '1' : '' }, 'aria-label': `${slot} ${p.nombre}` }, cab, kids);
        if (slot === 'R3') {
            return art([h('dl', null, campo('Hardware', 'V' + p.version), campo('Serie', p.serie)), h('p', { class: 'nota' }, icon('info'), 'La R3 no lleva MAC ni firmware.')]);
        }
        const mac = p.mac ? String(p.mac).toLowerCase() : '';
        const macBox = mac
            ? h('div', { class: 'mac' }, h('span', { class: 'val', 'aria-label': 'MAC ' + mac.split(':').join(' ') }, mac),
                h('button', { class: 'btn btn-sm', type: 'button', 'aria-label': `Copiar la MAC de ${p.nombre}`, title: 'Copiar MAC', onclick: () => copiar(mac, 'MAC copiada') }, icon('paste')))
            : h('div', { class: 'mac' }, h('span', { class: 'soft' }, icon('clock'), 'Sin MAC todavía'));
        const fw = p.firmware ? h('span', null, p.firmware) : h('span', { class: 'soft' }, icon('clock'), 'Sin firmware');
        return art([macBox, h('dl', null, campo('Hardware', 'V' + p.version), campo('Firmware', fw), campo('Serie', p.serie))]);
    }
    /** Texto plano de una tarjeta (para copiar). */
    function resumenTarjeta(t) {
        const l = [`Tarjeta ${t.id_tarjeta_num}`];
        ['r1', 'r2', 'r3'].forEach((s) => {
            const p = t[s]; if (!p) return;
            if (s === 'r3') { l.push(`R3 ${p.nombre} · Hardware V${p.version} (sin MAC ni firmware)`); return; }
            l.push(`${s.toUpperCase()} ${p.nombre} · Hardware V${p.version}${p.mac ? ' · MAC ' + String(p.mac).toLowerCase() : ''}${p.firmware ? ' · Firmware ' + p.firmware : ''}`);
        });
        if (t.fecha_llegada || t.fecha_finalizado || t.fecha_real || t.gabinete) l.push(`Llegada ${t.fecha_llegada || '—'} · Finalizado ${t.fecha_finalizado || '—'} · Entrega ${t.fecha_real || '—'} · Gabinete ${t.gabinete || '—'}`);
        return l.join('\n');
    }

    const util = { cargando, errorBox, copiar, fecha, cmp, tabla, pintarTabla, alternarOrden, placaCelda, placaCard, resumenTarjeta };

    // ------------------------------------------------------------------ actividad en vivo (global, sobrevive al cambio de sección)
    function pushFeed(kind, text) {
        S.feed.unshift({ kind, text, t: T.hora() }); S.feed = S.feed.slice(0, 60);
        S.feedFns.forEach((fn) => { try { fn(S.feed); } catch (e) { /* nada */ } });
    }

    // ------------------------------------------------------------------ lotes
    async function cargarLotes() {
        const r = await api('/api/lotes');
        if (!r.ok) { S.errorLotes = r.error; return false; }
        S.errorLotes = '';
        S.lotes = (r.data || []).slice().sort((a, b) => (b.anio - a.anio) || (b.mes - a.mes));
        const activo = S.lotes.find((l) => l.activo) || S.lotes[0] || null;
        S.activoId = activo ? activo.id : null;
        if (!S.lote) {
            const q = +new URLSearchParams(location.search).get('lote');
            S.lote = (q && S.lotes.find((l) => l.id === q)) || activo;
        } else S.lote = S.lotes.find((l) => l.id === S.lote.id) || activo;
        pintarLote();
        return true;
    }
    function pintarLote() {
        if (!refs.loteTxt) return;
        refs.loteTxt.textContent = T.loteNombre(S.lote);
        refs.loteEst.replaceChildren(S.lote && S.lote.activo ? 'activo' : (S.lote ? 'solo vista' : ''));
        refs.loteEst.dataset.a = S.lote && S.lote.activo ? '1' : '';
        refs.loteBtn.setAttribute('aria-label', `Lote: ${T.loteNombre(S.lote)}${S.lote && S.lote.activo ? ', activo' : ''}. Cambiar de lote`);
    }
    function seleccionarLote(id) {
        const l = S.lotes.find((x) => x.id === id); if (!l || (S.lote && S.lote.id === id)) return;
        S.lote = l; pintarLote(); invalidar();
        if (S.cur) { S.cur.alLote.forEach((fn) => { try { fn(l); } catch (e) { console.error(e); } }); if (S.cur.inst && S.cur.inst.actualizar) S.cur.inst.actualizar(); }
    }
    const shim = { setSub() {}, refresh() {} };
    function cerrarMenu(foco) {
        if (!S.menu) return;
        S.menu.remove(); S.menu = null; refs.loteBtn.setAttribute('aria-expanded', 'false');
        document.removeEventListener('click', clicFuera, true);
        if (foco) refs.loteBtn.focus();
    }
    function clicFuera(e) { if (S.menu && !S.menu.contains(e.target) && !refs.loteBtn.contains(e.target)) cerrarMenu(false); }
    function abrirMenu() {
        if (S.menu) { cerrarMenu(true); return; }
        const item = (l) => h('button', { class: 'esc-mi', type: 'button', role: 'menuitemradio', 'aria-checked': S.lote && S.lote.id === l.id ? 'true' : 'false', onclick: () => { cerrarMenu(true); seleccionarLote(l.id); } },
            h('span', { class: 'nm' }, T.loteNombre(l)), l.activo ? T.badge('Activo', 'ok') : null, h('span', { class: 'mono t2' }, `${l.tarjetas || 0} tarj.`));
        S.menu = h('div', { class: 'esc-menu', role: 'menu', 'aria-label': 'Lotes' },
            S.lotes.length ? S.lotes.map(item) : h('div', { class: 'esc-mi-vacio muted' }, 'Todavía no hay lotes'),
            h('div', { class: 'esc-sep', role: 'separator' }),
            h('button', { class: 'esc-mi acc', type: 'button', role: 'menuitem', onclick: () => { cerrarMenu(false); T.openLotes(shim); } }, icon('plus'), 'Usar o crear lote…'));
        S.menu.addEventListener('keydown', (e) => {
            const its = [...S.menu.querySelectorAll('button')]; const i = its.indexOf(document.activeElement);
            if (e.key === 'ArrowDown') { e.preventDefault(); its[(i + 1) % its.length].focus(); }
            else if (e.key === 'ArrowUp') { e.preventDefault(); its[(i - 1 + its.length) % its.length].focus(); }
            else if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); cerrarMenu(true); }
            else if (e.key === 'Tab') cerrarMenu(false);
        });
        refs.loteWrap.append(S.menu); refs.loteBtn.setAttribute('aria-expanded', 'true');
        (S.menu.querySelector('[aria-checked="true"]') || S.menu.querySelector('button')).focus();
        setTimeout(() => document.addEventListener('click', clicFuera, true), 0);
    }

    // ------------------------------------------------------------------ router y montaje de secciones
    function leerHash() {
        const m = /^#\/([a-z0-9_-]+)(?:\?(.*))?$/i.exec(location.hash);
        return m ? { id: m[1].toLowerCase(), params: new URLSearchParams(m[2] || '') } : null;
    }
    function ir(id, params) {
        const qs = params ? new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '')).toString() : '';
        const dest = `#/${id}${qs ? '?' + qs : ''}`;
        if (location.hash === dest) { ruta(); return; }
        location.hash = dest;
    }
    function titulo(t) { refs.titulo.textContent = t; document.title = `${t} · Consola · Escáner TQT`; }
    function anunciar(t) { refs.anuncio.textContent = ''; setTimeout(() => { refs.anuncio.textContent = t; }, 30); }

    function crearCtx(cur) {
        return {
            T, api, h, icon, toast, sheet: T.sheet, ws: T.ws('monitor'), util,
            lote: () => S.lote, alCambiarLote(fn) { cur.alLote.push(fn); },
            lotes: () => S.lotes, seleccionarLote, recargarLotes: cargarLotes, hojaLotes: () => T.openLotes(shim),
            ir, sesion: S.sesion, titulo, params: () => S.params,
            pcbs: cargarPcb, tarjetas: cargarTarjetas, invalidar,
            actualizar() { invalidar(); if (cur.inst && cur.inst.actualizar) cur.inst.actualizar(); },
            feed: () => S.feed, alActividad(fn) { S.feedFns.add(fn); cur.limpiar.push(() => S.feedFns.delete(fn)); },
            alEvento(evs, fn) { const ws = T.ws('monitor'); if (!ws) return; [].concat(evs).forEach((ev) => { ws.on(ev, fn); cur.limpiar.push(() => ws.off(ev, fn)); }); },
        };
    }
    function desmontar() {
        const c = S.cur; if (!c) return;
        try { c.inst && c.inst.desmontar && c.inst.desmontar(); } catch (e) { console.error(e); }
        c.limpiar.forEach((fn) => { try { fn(); } catch (e) { /* nada */ } });
        S.cur = null;
    }
    function marcarNav(id) {
        refs.nav.querySelectorAll('a[data-id]').forEach((a) => { if (a.dataset.id === id) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current'); });
    }
    function montar(def, params) {
        desmontar();
        const host = h('section', { class: 'esc-sec', id: 'sec-' + def.id, 'aria-labelledby': 'escTitulo', dataset: { sec: def.id } });
        refs.main.replaceChildren(host);
        const cur = { id: def.id, def, host, inst: null, limpiar: [], alLote: [] };
        S.cur = cur; S.params = params;
        titulo(def.titulo);
        marcarNav(def.id);
        try { cur.inst = def.montar(host, crearCtx(cur)) || {}; }
        catch (e) { console.error(e); cur.inst = {}; host.replaceChildren(errorBox('Esta sección tuvo un problema al abrirse. Recarga la página.')); }
        if (!S.primera) { refs.titulo.focus({ preventScroll: true }); anunciar(`Sección ${def.titulo}`); }
        S.primera = false;
        window.scrollTo({ top: 0 });
    }
    function ruta() {
        cerrarMenu(false);
        let r = leerHash();
        if (!r) { r = { id: 'resumen', params: new URLSearchParams() }; history.replaceState(null, '', '#/resumen'); }
        const def = secciones.get(r.id);
        if (!def) { history.replaceState(null, '', '#/resumen'); r = { id: 'resumen', params: new URLSearchParams() }; return montarId(r); }
        montarId(r);
    }
    function montarId(r) {
        const def = secciones.get(r.id);
        if (def.href) { location.href = def.href; return; }
        if (S.cur && S.cur.id === r.id) { S.params = r.params; if (S.cur.inst && S.cur.inst.parametros) S.cur.inst.parametros(r.params); return; }
        montar(def, r.params);
    }
    function irSeccion(id) { const d = secciones.get(id); if (!d) return; if (d.href) location.href = d.href; else ir(id); }

    // ------------------------------------------------------------------ armazón (DOM)
    function brandMark() {
        const NS = 'http://www.w3.org/2000/svg';
        const svg = document.createElementNS(NS, 'svg'); svg.setAttribute('viewBox', '0 0 32 32'); svg.setAttribute('class', 'brand-mark'); svg.setAttribute('aria-hidden', 'true');
        ['M3 3h11v11H3z', 'M18 3h11v11H18z', 'M3 18h11v11H3z'].forEach((d) => { const p = document.createElementNS(NS, 'path'); p.setAttribute('d', d); p.setAttribute('fill', 'none'); p.setAttribute('stroke', 'currentColor'); p.setAttribute('stroke-width', '2.4'); svg.appendChild(p); });
        const dots = document.createElementNS(NS, 'path'); dots.setAttribute('d', 'M7 7h3v3H7zM22 7h3v3h-3zM7 22h3v3H7zM19 19h3v3h-3zM25 19h4v3h-4zM19 25h4v4h-4zM26 25h3v4h-3z'); dots.setAttribute('fill', 'currentColor'); svg.appendChild(dots);
        return svg;
    }
    function pintarNav() {
        refs.nav.replaceChildren();
        Object.keys(GRUPOS).forEach((g) => {
            const defs = [...secciones.values()].filter((d) => d.grupo === g).sort((a, b) => a.orden - b.orden);
            if (!defs.length) return;
            const gid = 'escG-' + g;
            refs.nav.append(h('div', { class: 'esc-grp', id: gid }, GRUPOS[g]),
                h('ul', { 'aria-labelledby': gid }, defs.map((d) => {
                    const ext = !!d.href;
                    const a = h('a', { href: d.href || `#/${d.id}`, dataset: { id: d.id }, title: d.titulo, 'aria-label': d.titulo, class: 'esc-ni' }, icon(d.icono), h('span', { class: 'esc-nl' }, d.titulo), ext ? icon('external', 'ext') : null);
                    const at = ETQ_ATAJO[d.id];
                    if (at) a.append(h('kbd', { class: 'esc-k', 'aria-hidden': 'true' }, at));
                    if (at) a.setAttribute('aria-keyshortcuts', 'g ' + at);
                    return h('li', null, a);
                })));
        });
    }
    function fijarLat(v, guardar) {
        S.lat = v; refs.root.dataset.lat = v;
        if (guardar) T.store.set('tqt.esc.lat', v);
        if (refs.latBtn) { refs.latBtn.setAttribute('aria-expanded', String(v === 'max')); refs.latTxt.textContent = v === 'max' ? 'Contraer menú' : 'Expandir menú'; refs.latBtn.setAttribute('aria-label', v === 'max' ? 'Contraer el menú lateral' : 'Expandir el menú lateral'); }
    }
    function atajosSheet() {
        const fila = (k, t) => h('div', { class: 'esc-atajo' }, h('span', { class: 'ks' }, k.split(' ').map((x) => h('kbd', { class: 'esc-k' }, x))), h('span', null, t));
        const irs = Object.keys(ATAJOS).filter((k) => secciones.has(ATAJOS[k])).map((k) => fila('g ' + k, 'Ir a ' + secciones.get(ATAJOS[k]).titulo));
        T.sheet({ title: 'Atajos de teclado', body: h('div', { class: 'esc-atajos' }, fila('/', 'Buscar en la sección'), fila('[', 'Contraer o expandir el menú'), fila('Esc', 'Cerrar el panel o la ventana'), fila('↑ ↓', 'Moverse entre filas de una tabla'), fila('Enter', 'Abrir la fila'), fila('Espacio', 'Marcar la fila'), irs, fila('?', 'Ver esta lista')),
            actions: [{ label: 'Cerrar', kind: 'primary', onClick: () => true }] });
    }
    function versionMovil() { try { localStorage.setItem('tqt.vista', 'movil'); } catch (e) { /* nada */ } location.href = '/'; }

    function construir() {
        const root = document.getElementById('esc'); refs.root = root;
        const temaBtn = h('button', { class: 'iconbtn', type: 'button', 'aria-label': 'Cambiar entre tema claro y oscuro', onclick: (e) => { const t = T.toggleTheme(); e.currentTarget.replaceChildren(icon(t === 'light' ? 'moon' : 'sun')); } }, icon(T.currentTheme() === 'light' ? 'moon' : 'sun'));
        refs.loteTxt = h('span', { class: 'nm' }); refs.loteEst = h('span', { class: 'est' });
        refs.loteBtn = h('button', { class: 'esc-lote', type: 'button', 'aria-haspopup': 'menu', 'aria-expanded': 'false', onclick: abrirMenu }, h('span', { class: 'tx' }, h('span', { class: 'lbl' }, 'Lote'), refs.loteTxt), refs.loteEst, icon('chevron', 'chev'));
        refs.loteWrap = h('div', { class: 'esc-lotewrap' }, refs.loteBtn);
        refs.sol = h('button', { class: 'iconbtn esc-sol', type: 'button', hidden: '', 'aria-label': 'Solicitudes de contraseña', title: 'Solicitudes de contraseña', onclick: solicitudesSheet }, icon('shield'), h('span', { class: 'esc-sol-n' }, '0'));
        refs.titulo = document.getElementById('escTitulo') || h('h1', { id: 'escTitulo', tabindex: '-1' }); refs.titulo.className = 'esc-titulo'; refs.titulo.textContent = 'Consola';
        refs.anuncio = h('div', { class: 'sr-only', 'aria-live': 'polite', role: 'status' });
        refs.nav = h('nav', { class: 'esc-nav', 'aria-label': 'Secciones' });
        refs.latTxt = h('span', { class: 'esc-nl' }, 'Contraer menú');
        refs.latBtn = h('button', { class: 'esc-ni esc-lat-btn', type: 'button', 'aria-expanded': 'true', onclick: () => fijarLat(S.lat === 'max' ? 'min' : 'max', true) }, icon('sidebar'), refs.latTxt, h('kbd', { class: 'esc-k', 'aria-hidden': 'true' }, '['));
        refs.main = h('main', { class: 'esc-main', id: 'escMain', tabindex: '-1' });
        refs.g = h('div', { class: 'esc-g', hidden: true, 'aria-hidden': 'true' }, h('kbd', { class: 'esc-k' }, 'g'), ' luego ', h('span', { class: 'mono' }, 'r i t m c l x'));
        const conn = h('div', { class: 'conn', dataset: { s: 'connecting' }, role: 'status', title: 'Conexión en tiempo real' }, h('i'), h('span', null, 'Conectando'));

        root.replaceChildren(
            h('button', { class: 'esc-skip', type: 'button', onclick: () => refs.main.focus() }, 'Saltar al contenido'),
            h('aside', { class: 'esc-lat' },
                h('div', { class: 'esc-brand' }, h('a', { href: '#/resumen', class: 'esc-logo', 'aria-label': 'Escáner TQT, ir al resumen' }, brandMark(), h('span', { class: 'esc-brand-t' }, h('b', null, 'Escáner TQT'), h('small', null, 'Consola')))),
                refs.nav, h('div', { class: 'esc-lat-pie' }, refs.latBtn, h('div', { class: 'esc-ver', title: 'Versión de Escáner TQT' }, h('span', { class: 'esc-ver-n' }, 'Escáner TQT '), h('b', { 'data-version': '' })))),
            h('div', { class: 'esc-col' },
                h('header', { class: 'esc-top' }, refs.titulo, h('div', { class: 'grow' }), refs.loteWrap,
                    h('button', { class: 'iconbtn', type: 'button', 'aria-label': 'Actualizar los datos', title: 'Actualizar', onclick: () => { invalidar(); cargarLotes(); if (S.cur && S.cur.inst && S.cur.inst.actualizar) S.cur.inst.actualizar(); toast('Datos actualizados', { kind: 'ok', ms: 1200 }); } }, icon('refresh')),
                    conn, temaBtn,
                    refs.sol,
                    h('a', { class: 'iconbtn', href: '/login?cambiar=1', 'aria-label': 'Cambiar mi contraseña', title: 'Cambiar mi contraseña' }, icon('lock')),
                    h('button', { class: 'iconbtn', type: 'button', 'aria-label': 'Cerrar sesión', title: 'Cerrar sesión', onclick: () => T.cerrarSesion() }, icon('logout')),
                    h('button', { class: 'iconbtn', type: 'button', 'aria-label': 'Atajos de teclado', title: 'Atajos de teclado (?)', onclick: atajosSheet }, icon('help')),
                    h('button', { class: 'btn esc-hb', type: 'button', onclick: versionMovil, title: 'Ir a la versión móvil (con cámara)' }, icon('phone'), h('span', { class: 'hb-t' }, 'Versión móvil')),),
                refs.main, refs.anuncio, refs.g));
        const guardado = T.store.get('tqt.esc.lat');
        fijarLat(guardado === 'min' || guardado === 'max' ? guardado : (innerWidth < 1180 ? 'min' : 'max'), false);
        T.versionP.then((v) => { if (v) document.querySelectorAll('[data-version]').forEach((e) => { e.textContent = 'v' + v; }); });
        window.addEventListener('resize', T.debounce(() => { const g = T.store.get('tqt.esc.lat'); if (g !== 'min' && g !== 'max') fijarLat(innerWidth < 1180 ? 'min' : 'max', false); }, 150));
    }

    // ------------------------------------------------------------------ teclado
    function teclado() {
        let g = false, gt = null;
        const fin = () => { g = false; clearTimeout(gt); refs.g.hidden = true; };
        document.addEventListener('keydown', (e) => {
            if (e.defaultPrevented || e.ctrlKey || e.metaKey || e.altKey) return;
            const tg = e.target;
            if (tg && tg.closest && tg.closest('input,textarea,select,[contenteditable="true"]')) return;
            if (document.querySelector('.sheet')) return;
            const k = e.key;
            if (g) { const id = ATAJOS[k.toLowerCase()]; fin(); if (id && secciones.has(id)) { e.preventDefault(); irSeccion(id); } return; }
            if (k === 'g') { g = true; refs.g.hidden = false; gt = setTimeout(fin, 1400); return; }
            if (k === '/') { const b = refs.main.querySelector('[data-buscar]'); if (b) { e.preventDefault(); b.focus(); if (b.select) b.select(); } }
            else if (k === '[') fijarLat(S.lat === 'max' ? 'min' : 'max', true);
            else if (k === '?') { e.preventDefault(); atajosSheet(); }
        });
    }

    // ------------------------------------------------------------------ tiempo real
    const EV = {
        PCB_RECIBIDA: (d) => ['ok', d && d.pcb ? `Recibida ${d.pcb.nombre}` : 'Placa recibida'],
        PCB_ACTUALIZADA: (d) => ['info', d && d.pcb ? `Actualizada ${d.pcb.nombre}${d.pcb.mac ? ' · ' + String(d.pcb.mac).toLowerCase() : ''}${d.pcb.firmware ? ' · fw ' + d.pcb.firmware : ''}` : 'Placa actualizada'],
        PCB_ELIMINADA: (d) => ['warn', d && d.nombre ? `Eliminada ${d.nombre}` : 'Placa eliminada'],
        RECEPCION_CONFIRMADA: (d) => ['ok', `Recepción confirmada${d && d.confirmadas ? ` (${d.confirmadas} placas)` : ''}`],
        TARJETA_EMPAREJADA: (d) => ['ok', d && d.tarjeta ? `Tarjeta ${d.tarjeta.id_tarjeta_num} emparejada` : 'Tarjeta emparejada'],
        TARJETA_ACTUALIZADA: (d) => ['info', d && d.tarjeta ? `Tarjeta ${d.tarjeta.id_tarjeta_num} actualizada` : (d && d.eliminada ? `Tarjeta ${d.id_tarjeta_num || ''} eliminada` : 'Tarjeta actualizada')],
        ADMIN_CAMBIO: () => ['warn', 'Cambio de administración'],
        EXCEL_IMPORTADO: () => ['info', 'Excel importado'],
        SYNC_EXCEL_COMPLETO: () => ['info', 'Excel sincronizado'],
    };
    // Tarjetas concluidas (R1+R2+R3 con MAC; la base ya sella su "Fecha Finalizado") que aún no tienen fecha real de entrega:
    // se pide la fecha en una hoja. "Más tarde" las pospone solo en esta pestaña; al guardar salen de la lista y van al Excel.
    const POSPUESTAS = 'tqt.entrega.pospuesta';
    const leerPospuestas = () => { try { return JSON.parse(sessionStorage.getItem(POSPUESTAS) || '[]'); } catch (e) { return []; } };
    async function pedirEntregas() {
        if (!S.lote || document.querySelector('.sheet')) return;
        const r = await api(`/api/tarjetas?lote_id=${S.lote.id}&limit=500`); if (!r.ok || !r.data) return;
        const pospuestas = leerPospuestas();
        const pend = (r.data.items || []).filter((t) => !t.fecha_real && T.estadoTarjeta(t).key === 'completa' && !pospuestas.includes(t.id))
            .sort((a, b) => String(a.id_tarjeta_num).localeCompare(String(b.id_tarjeta_num)));
        if (!pend.length) return;
        const ymd = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
        const filas = pend.map((t) => {
            const fecha = h('input', { class: 'input mono', type: 'date', 'aria-label': `Entrega de la tarjeta ${t.id_tarjeta_num}`, value: t.fecha_proyectada || ymd(new Date()) });
            const gab = h('select', { class: 'input', 'aria-label': `Gabinete de la tarjeta ${t.id_tarjeta_num}` }, h('option', { value: '' }, 'Sin definir'),
                ['Quintalock', 'Translock'].map((g) => h('option', { value: g, selected: t.gabinete === g ? '' : null }, g)));
            const sel = h('input', { type: 'checkbox', 'aria-label': `Seleccionar tarjeta ${t.id_tarjeta_num}`, style: 'width:20px;height:20px' });
            return { t, fecha, gab, sel, el: h('div', { style: 'display:grid;grid-template-columns:auto minmax(0,1fr) 150px 140px;gap:8px;align-items:center' },
                sel, h('div', {}, h('b', { class: 'mono' }, `#${t.id_tarjeta_num}`), h('div', { class: 'muted' }, `Concluida ${t.fecha_finalizado || 'hoy'}`)), fecha, gab) };
        });
        // Aplicar en bloque: se marcan una, varias o todas y se les pone la misma fecha y/o gabinete
        const todas = h('input', { type: 'checkbox', 'aria-label': 'Seleccionar todas', style: 'width:20px;height:20px' });
        const cuenta = h('span', { class: 'muted' }, '0 seleccionadas');
        const bFecha = h('input', { class: 'input mono', type: 'date', 'aria-label': 'Fecha para las seleccionadas', value: ymd(new Date()) });
        const bGab = h('select', { class: 'input', 'aria-label': 'Gabinete para las seleccionadas' }, h('option', { value: '' }, 'Gabinete (sin cambiar)'),
            ['Quintalock', 'Translock'].map((g) => h('option', { value: g }, g)));
        const bAplicar = h('button', { class: 'btn', type: 'button', disabled: '' }, 'Aplicar');
        const refrescarSel = () => {
            const n = filas.filter((f) => f.sel.checked).length;
            cuenta.textContent = `${n} seleccionada${n === 1 ? '' : 's'}`; bAplicar.disabled = !n;
            todas.checked = n === filas.length; todas.indeterminate = n > 0 && n < filas.length;
        };
        todas.addEventListener('change', () => { filas.forEach((f) => { f.sel.checked = todas.checked; }); refrescarSel(); });
        filas.forEach((f) => f.sel.addEventListener('change', refrescarSel));
        bAplicar.addEventListener('click', () => {
            filas.filter((f) => f.sel.checked).forEach((f) => { if (bFecha.value) f.fecha.value = bFecha.value; if (bGab.value) f.gab.value = bGab.value; });
            toast('Aplicado a las seleccionadas', { kind: 'ok' });
        });
        const barra = h('div', { style: 'display:flex;flex-wrap:wrap;gap:8px;align-items:center;padding:8px 0;border-bottom:1px solid var(--line, rgba(128,128,128,.3))' },
            h('label', { class: 'row', style: 'gap:6px;cursor:pointer' }, todas, h('b', {}, 'Todas')), cuenta, h('span', { style: 'flex:1' }), bFecha, bGab, bAplicar);
        T.sheet({
            title: `${pend.length === 1 ? 'Tarjeta concluida' : pend.length + ' tarjetas concluidas'}: ¿cuándo se entrega?`,
            body: h('div', { style: 'display:flex;flex-direction:column;gap:10px' },
                h('p', { class: 'muted' }, 'Ya tienen R1, R2, R3 y las MAC. Indica la fecha real de entrega (se propone la proyectada o la de hoy) y el gabinete. Para varias a la vez, selecciónalas y usa "Aplicar".'), barra, filas.map((f) => f.el)),
            actions: [
                { label: 'Más tarde', onClick: () => { try { sessionStorage.setItem(POSPUESTAS, JSON.stringify(pospuestas.concat(pend.map((t) => t.id)))); } catch (e) { /* sin almacenamiento */ } return true; } },
                { label: 'Guardar fechas de entrega', kind: 'primary', icon: 'check', onClick: async () => {
                    let ok = 0; let fallo = '';
                    for (const f of filas) {
                        if (!f.fecha.value) continue;
                        const g = await api(`/api/tarjetas/${f.t.id}`, { method: 'PATCH', body: { fecha_real: f.fecha.value, gabinete: f.gab.value } });
                        if (g.ok) ok++; else fallo = g.error;
                    }
                    if (ok) toast(`${ok} entrega${ok === 1 ? '' : 's'} guardada${ok === 1 ? '' : 's'}`, { kind: 'ok' });
                    if (fallo) { toast(fallo, { kind: 'bad' }); return false; }
                    invalidar(); if (S.cur && S.cur.inst && S.cur.inst.actualizar) S.cur.inst.actualizar();
                    return true;
                } },
            ],
        });
    }
    // ------------------------------------------------------------------ solicitudes de contraseña (otra cuenta aprueba)
    // Quien olvidó su contraseña la pide en /login; aquí otra cuenta con sesión la aprueba y recibe un código de 6 dígitos que le dicta en persona.
    async function revisarSolicitudes() {
        const r = await api('/api/auth/solicitudes');
        const items = r.ok && r.data && Array.isArray(r.data.items) ? r.data.items : [];
        if (refs.sol) { refs.sol.hidden = !items.length; refs.sol.querySelector('.esc-sol-n').textContent = String(items.length); }
        return items;
    }
    async function solicitudesSheet() {
        const lista = h('div', { class: 'stack' });
        const hoja = T.sheet({ title: 'Solicitudes de contraseña', body: lista, actions: [{ label: 'Cerrar', kind: 'ghost', onClick: () => true }], focus: false });
        const hace = (sg) => (sg < 90 ? 'hace un momento' : `hace ${Math.round(sg / 60)} min`);
        async function resolver(it, aprobar) {
            const r = await api(`/api/auth/solicitudes/${it.id}/${aprobar ? 'aprobar' : 'rechazar'}`, { method: 'POST' });
            if (!r.ok) { toast(r.error || 'No se pudo completar', { kind: 'bad' }); pintar(await revisarSolicitudes()); return; }
            revisarSolicitudes();
            if (!aprobar) { toast('Solicitud rechazada', { kind: 'ok' }); pintar(await revisarSolicitudes()); return; }
            lista.replaceChildren(h('div', { class: 'esc-cod' }, h('span', { class: 'muted' }, `Código para ${it.email}`), h('b', { class: 'mono', 'aria-label': `Código ${r.data.codigo.split('').join(' ')}` }, r.data.codigo),
                h('span', { class: 'muted' }, 'Válido 10 minutos. Díctalo en persona: no se vuelve a mostrar.')));
        }
        function pintar(items) {
            lista.replaceChildren();
            if (!items.length) { lista.append(T.empty('check', 'Sin solicitudes', 'Nadie ha pedido ayuda con su contraseña.')); return; }
            lista.append(h('p', { class: 'muted' }, 'Aprueba solo si la persona está contigo y la reconoces. Después le dictas el código.'),
                ...items.map((it) => h('div', { class: 'esc-sol-fila' }, h('div', null, h('b', { class: 'mono' }, it.email), h('div', { class: 'muted' }, hace(it.hace_seg))),
                    h('button', { class: 'btn btn-sm', type: 'button', onclick: () => resolver(it, false) }, 'Rechazar'),
                    h('button', { class: 'btn btn-sm btn-primary', type: 'button', onclick: () => resolver(it, true) }, 'Aprobar'))));
        }
        pintar(await revisarSolicitudes());
    }

    function tiempoReal() {
        const ws = T.ws('monitor'); if (!ws) return;
        const refrescar = T.debounce(() => { if (S.cur && S.cur.inst && S.cur.inst.actualizar) S.cur.inst.actualizar(); }, 350);
        const revisar = T.debounce(() => { pedirEntregas().catch((e) => console.error(e)); }, 1200);
        Object.keys(EV).forEach((ev) => ws.on(ev, (d) => { const [k, t] = EV[ev](d); pushFeed(k, t); invalidar(); refrescar(); if (ev !== 'ADMIN_CAMBIO') revisar(); }));
        setTimeout(revisar, 2500);
        ws.on('CLAVE_SOLICITADA', (d) => { pushFeed('warn', `${(d && d.email) || 'Una cuenta'} pidió restablecer su contraseña`); toast('Solicitud de contraseña pendiente', { kind: 'warn' }); revisarSolicitudes(); });
        revisarSolicitudes();   // al abrir la consola: tarjetas que ya estaban concluidas sin fecha
        // Red de seguridad: reconexión del WS, regreso a la pestaña y refresco periódico (sin tocar la actividad en vivo)
        T.resync(() => { revisarSolicitudes(); if (document.querySelector('.sheet')) return; invalidar(); refrescar(); });
        ws.on('LOTE_CAMBIADO', async () => {
            const prev = S.activoId; const seguia = !S.lote || S.lote.id === prev;
            await cargarLotes(); if (seguia && S.activoId && S.lote && S.lote.id !== S.activoId) seleccionarLote(S.activoId);
            pushFeed('info', 'Cambió el lote activo'); invalidar(); refrescar();
        });
    }

    // ------------------------------------------------------------------ arranque
    async function iniciar() {
        if (!secciones.has('macs')) {
            registrar({ id: 'macs', titulo: 'MAC y firmware', icono: 'programar', grupo: 'operacion', orden: 40, montar(host) {
                host.append(T.empty('programar', 'Próximamente', 'Aquí se capturarán con teclado las MAC y el firmware de las R1 y R2.'));
                return {};
            } });
        }
        const est = await api('/api/admin/estado');
        S.sesion.admin = !!(est.ok && est.data && est.data.habilitado);
        construir(); pintarNav(); teclado();
        T.ws('monitor');
        document.addEventListener('tqt:lote-cambiado', (e) => {   // la hoja de lotes de common.js avisa; aquí no se recarga la página
            e.preventDefault(); const l = e.detail && e.detail.lote;
            cargarLotes().then(() => { if (l) { S.lote = S.lotes.find((x) => x.id === l.id) || S.lote; pintarLote(); } invalidar(); if (S.cur) { S.cur.alLote.forEach((fn) => fn(S.lote)); if (S.cur.inst && S.cur.inst.actualizar) S.cur.inst.actualizar(); } });
        });
        pushFeed('info', 'Consola conectada');
        tiempoReal();
        await cargarLotes();
        window.addEventListener('hashchange', ruta);
        ruta();
        if (S.errorLotes) toast(S.errorLotes, { kind: 'bad' });
    }

    window.TQTEscritorio = { registrar, iniciar, util, ir, secciones };
})();
