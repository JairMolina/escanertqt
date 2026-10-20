/**
 * impresora.js (v1.4.16) - Módulo IMPRESORA (/impresora): activos, número ACT 0000, etiqueta DYMO con QR.
 * Lista + ficha, alta/edición, impresión por 4 vías, escaneo (lector USB, celular vinculado, cámara del teléfono).
 * Depende de common.js (TQT.h/api/icon/toast) y ws_client.js. Carga bajo demanda: qrcode-generator, DYMO Connect y el visor de cámara.
 */
(function () {
    'use strict';
    const T = window.TQT;
    const { h, api, icon } = T;
    const $ = (id) => document.getElementById(id);
    const desk = window.matchMedia('(min-width: 900px)');

    // ------------------------------------------------------------------ utilidades
    const pad4 = (n) => String(n).padStart(4, '0');
    const etq = (c) => String(c || '').replace('-', ' ');
    const lleno = (v) => v !== null && v !== undefined && String(v).trim() !== '';
    const enc = encodeURIComponent;
    const ESTADOS_FB = [{ id: 'activo', nombre: 'Activo' }, { id: 'resguardo', nombre: 'En resguardo' }, { id: 'reparacion', nombre: 'En reparación' }, { id: 'baja', nombre: 'Baja' }];
    const ROLES = { administrador: 'Administrador', general: 'General', consultor: 'Consulta' };
    const esMovil = /Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent || '');
    const fFecha = (s) => { const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s || ''); if (!m) return ''; return new Date(+m[1], +m[2] - 1, +m[3]).toLocaleDateString('es-MX', { day: 'numeric', month: 'short', year: 'numeric' }); };
    const fHora = (s) => {
        const d = s ? new Date(String(s).replace(' ', 'T')) : null; if (!d || isNaN(d)) return '';
        const o = { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }; if (d.getFullYear() !== new Date().getFullYear()) o.year = 'numeric';
        return d.toLocaleString('es-MX', o);
    };
    const fValor = (v) => (v === null || v === undefined || v === '' || isNaN(Number(v))) ? '' : Number(v).toLocaleString('es-MX', { style: 'currency', currency: 'MXN' });
    const anuncia = (t) => { const a = $('anuncio'); a.textContent = ''; setTimeout(() => { a.textContent = t; }, 30); };
    const toast = (m, o) => T.toast(m, o);

    // El tema lo fija el <head>; common.js lo pisa a "oscuro" si no hay ajuste guardado: se restablece la preferencia del sistema.
    (function () {
        let g = null; try { g = localStorage.getItem('tqt.tema'); } catch (e) { /* nada */ }
        T.applyTheme(g === 'light' || g === 'dark' ? g : (matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark'));
    })();
    T.hydrateIcons();

    const cargados = {};
    function cargaScript(src) {
        if (cargados[src]) return cargados[src];
        cargados[src] = new Promise((ok, ko) => {
            const s = document.createElement('script'); s.src = src; s.onload = ok;
            s.onerror = () => { delete cargados[src]; ko(new Error('No se pudo cargar ' + src.split('?')[0])); };
            document.head.appendChild(s);
        });
        return cargados[src];
    }

    // ------------------------------------------------------------------ estado
    const S = { ro: false, yo: null, items: [], total: 0, siguiente: null, cat: { categorias: [], departamentos: [], ubicaciones: [], responsables: [], estados: ESTADOS_FB },
        q: '', estado: '', categoria: '', departamento: '', soloCodigos: null, cargando: true, error: '', seq: 0, sel: null, act: null, selSeq: 0, edit: null, imprimiendo: false };
    const nombreEstado = (id) => ((S.cat.estados || ESTADOS_FB).find((e) => e.id === id) || ESTADOS_FB.find((e) => e.id === id) || { nombre: id || '—' }).nombre;
    const nm = (x) => (typeof x === 'string' ? x : (x && (x.nombre || x.id)) || '');
    const chip = (estado) => { const c = h('span', { class: 'chip', dataset: { e: estado || '' } }, nombreEstado(estado)); return c; };
    const placa = (txt, cls) => h('span', { class: 'placa' + (cls ? ' ' + cls : '') }, h('span', null, txt));

    // ------------------------------------------------------------------ cabecera: tema y usuario
    function pintaTema() { $('bTema').replaceChildren(icon(T.currentTheme() === 'light' ? 'moon' : 'sun')); }
    $('bTema').addEventListener('click', () => { T.toggleTheme(); pintaTema(); });
    pintaTema();

    async function cargaYo() {
        const r = await api('/api/auth/yo');
        if (!r.ok || !r.data) return;
        S.yo = r.data; S.ro = r.data.rol === 'consultor';
        if (S.ro) document.body.dataset.ro = '1';
        $('uMail').textContent = r.data.email || ''; $('uRol').textContent = ROLES[r.data.rol] || r.data.rol || '';
        $('usuario').hidden = !r.data.email;
    }

    // ------------------------------------------------------------------ catálogos y filtros
    function llenaSelect(sel, vacio, vals, fn) {
        const cur = sel.value; sel.replaceChildren(h('option', { value: '' }, vacio));
        vals.forEach((v) => { const o = fn(v); sel.appendChild(h('option', { value: o[0] }, o[1])); }); sel.value = cur;
    }
    async function cargaCatalogos() {
        const r = await api('/api/activos/catalogos');
        if (r.ok && r.data) S.cat = Object.assign(S.cat, r.data, { estados: (r.data.estados && r.data.estados.length) ? r.data.estados : ESTADOS_FB });
        pintaCatalogos();
    }
    function pintaCatalogos() {
        llenaSelect($('fEst'), 'Todos los estados', S.cat.estados, (e) => [e.id, e.nombre]);
        llenaSelect($('fDep'), 'Todos los deptos.', S.cat.departamentos || [], (c) => [nm(c), nm(c)]);
        llenaSelect($('fCat'), 'Todas las categ.', S.cat.categorias || [], (c) => [nm(c), nm(c)]);
        const dl = (id, arr) => $(id).replaceChildren(...(arr || []).map((v) => h('option', { value: nm(v) })));
        dl('dlDep', S.cat.departamentos); dl('dlCat', S.cat.categorias); dl('dlUbi', S.cat.ubicaciones); dl('dlRes', S.cat.responsables);
        const es = $('fEstado2'); es.replaceChildren(...S.cat.estados.map((e) => h('option', { value: e.id }, e.nombre)));
    }

    // ------------------------------------------------------------------ lista
    const hayFiltro = () => !!(S.q || S.estado || S.categoria || S.departamento || S.soloCodigos);
    async function cargaLista(opts = {}) {
        const mi = ++S.seq; S.cargando = true; S.error = '';
        if (!S.items.length || !opts.silencio) pintaLista();
        $('lista').setAttribute('aria-busy', 'true');
        const qs = new URLSearchParams(); if (S.q) qs.set('q', S.q); if (S.estado) qs.set('estado', S.estado); if (S.categoria) qs.set('categoria', S.categoria); if (S.departamento) qs.set('departamento', S.departamento);
        const r = await api('/api/activos' + (qs.toString() ? '?' + qs : ''));
        if (mi !== S.seq) return;
        S.cargando = false; $('lista').setAttribute('aria-busy', 'false');
        if (r.ok && r.data) { S.items = r.data.items || []; S.total = r.data.total != null ? r.data.total : S.items.length;
            if (S.soloCodigos) { S.items = S.items.filter((x) => S.soloCodigos.has(x.codigo)); S.total = S.items.length; } S.siguiente = r.data.siguiente || S.siguiente; S.error = ''; }
        else { S.items = opts.silencio ? S.items : []; S.error = r.error || 'No se pudo cargar la lista'; }
        pintaLista(!opts.silencio);
    }

    function filaDe(a, i) {
        const sub = [a.marca, a.modelo].filter(lleno).join(' · ');
        const meta = (v) => h('span', { 'data-vacio': lleno(v) ? null : '1' }, lleno(v) ? v : '—');
        return h('li', null, h('button', {
            class: 'fila', type: 'button', dataset: { codigo: a.codigo }, style: `--i:${Math.min(i, 14)}`, 'aria-current': S.sel === a.codigo ? 'true' : null,
            onclick: () => abre(a.codigo, { push: !desk.matches }),
        },
        h('span', { class: 'c-cod' }, placa(a.etiqueta || etq(a.codigo))),
        h('span', { class: 'c-nom' }, h('b', null, a.nombre), sub ? h('small', null, sub) : null),
        h('span', { class: 'c-meta' }, meta(a.departamento), meta(a.categoria), meta(a.ubicacion), meta(a.responsable)),
        chip(a.estado),
        h('span', { class: 'c-imp mono', title: 'Veces impresa' }, String(a.impresiones || 0))));
    }

    function pintaLista(anim) {
        const ul = $('lista'), est = $('estado');
        ul.dataset.anim = anim ? '1' : '';
        est.hidden = true; est.replaceChildren(); delete est.dataset.k;
        $('loteFiltro').hidden = !S.soloCodigos; if (S.soloCodigos) $('loteTxt').textContent = `Mostrando solo los ${S.soloCodigos.size} activos de la última importación.`;
        const sig = S.siguiente && (S.siguiente.codigo || S.siguiente.numero != null) ? etq(S.siguiente.codigo || ('ACT-' + pad4(S.siguiente.numero))) : '';
        $('proximo').hidden = S.ro || !sig; $('proximoN').textContent = sig;
        if (S.cargando && !S.items.length) {
            ul.replaceChildren(...[0, 1, 2, 3, 4, 5].map(() => h('li', { 'aria-hidden': 'true' }, h('div', { class: 'sk sk-fila' }))));
            $('total').textContent = 'Cargando…'; return;
        }
        if (S.error) {
            ul.replaceChildren(); $('total').textContent = '';
            est.hidden = false; est.dataset.k = 'error';
            est.append(h('h2', null, 'No se pudo cargar la lista'), h('p', null, S.error), h('button', { class: 'btn', type: 'button', onclick: () => cargaLista() }, icon('refresh'), 'Reintentar'));
            return;
        }
        if (!S.items.length) {
            ul.replaceChildren(); $('total').textContent = hayFiltro() ? 'Sin coincidencias' : '0 activos';
            est.hidden = false;
            if (hayFiltro()) {
                est.append(h('h2', null, 'Ningún activo coincide'), h('p', null, 'Prueba con otro texto, otro estado u otra categoría.'),
                    h('button', { class: 'btn', type: 'button', onclick: limpiaFiltros }, 'Quitar filtros'));
            } else {
                est.append(placa(sig || 'ACT 0001', 'placa-lg fantasma'), h('h2', null, 'Aún no hay activos'),
                    h('p', null, S.ro ? 'Cuando el encargado registre el primero, aparecerá aquí.' : 'Registra el primero: se le asigna su número, se imprime la etiqueta DYMO con QR y se pega en el equipo. Después basta con escanearla para ver su ficha.'));
                if (!S.ro) est.append(h('button', { class: 'btn btn-primary', type: 'button', onclick: () => abreForm(null) }, icon('plus'), 'Registrar el primer activo'));
            }
            return;
        }
        ul.replaceChildren(...S.items.map(filaDe));
        const n = S.items.length;
        $('total').textContent = hayFiltro() ? `${n} de ${S.total} activos` : `${S.total} ${S.total === 1 ? 'activo' : 'activos'}`;
    }
    function limpiaFiltros() { S.q = S.estado = S.categoria = S.departamento = ''; S.soloCodigos = null; $('q').value = ''; $('fEst').value = ''; $('fCat').value = ''; $('fDep').value = ''; cargaLista(); }

    const lanzaBusqueda = T.debounce(() => cargaLista(), 260);
    $('q').addEventListener('input', (e) => { S.q = e.target.value.trim(); lanzaBusqueda(); });
    $('fEst').addEventListener('change', (e) => { S.estado = e.target.value; cargaLista(); });
    $('fCat').addEventListener('change', (e) => { S.categoria = e.target.value; cargaLista(); });
    $('fDep').addEventListener('change', (e) => { S.departamento = e.target.value; cargaLista(); });
    $('loteQuitar').addEventListener('click', limpiaFiltros);
    $('lista').addEventListener('keydown', (e) => {   // flechas entre filas
        if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
        const filas = [...$('lista').querySelectorAll('.fila')], i = filas.indexOf(document.activeElement); if (i < 0) return;
        const t = filas[i + (e.key === 'ArrowDown' ? 1 : -1)]; if (t) { e.preventDefault(); t.focus(); }
    });

    // ------------------------------------------------------------------ ficha
    const bgInerte = (v) => { ['.cab', '.barra', '#lista-col', '#bCam'].forEach((s) => { const el = document.querySelector(s); if (el) el.inert = !!v; }); };
    const fichaAbierta = () => document.body.dataset.ficha === '1';
    function ponUrl(codigo, push) {
        try {
            const u = new URL(location.href);
            if (codigo) u.searchParams.set('activo', codigo); else u.searchParams.delete('activo');
            if (push) history.pushState({ a: codigo }, '', u); else history.replaceState(codigo ? { a: codigo } : null, '', u);
        } catch (e) { /* nada */ }
    }
    function marcaFila() {
        $('lista').querySelectorAll('.fila[aria-current]').forEach((b) => b.removeAttribute('aria-current'));
        if (S.sel) { const b = $('lista').querySelector(`.fila[data-codigo="${CSS.escape(S.sel)}"]`); if (b) b.setAttribute('aria-current', 'true'); }
    }
    function muestraFicha(estado) {   // 'vacia' | 'error' | 'cont'
        $('fVacia').hidden = estado !== 'vacia'; $('fError').hidden = estado !== 'error'; $('fCont').hidden = estado !== 'cont';
    }

    async function abre(codigo, o = {}) {
        if (!codigo) return;
        const mi = ++S.selSeq; S.sel = codigo; S.act = null; marcaFila();
        const antes = fichaAbierta();
        document.body.dataset.ficha = '1';
        if (!desk.matches) bgInerte(true);
        if (o.push !== undefined && !o.noUrl) { if (o.push && !antes) ponUrl(codigo, true); else ponUrl(codigo, false); }
        setMsg($('fMsg'), '');
        let datos = o.datos || null;
        if (datos) pintaFicha(datos);
        else {
            const prev = S.items.find((x) => x.codigo === codigo);
            if (prev) pintaFicha(prev, null, true); else pintaCarga(codigo);
            const r = await api(`/api/activos/${enc(codigo)}`);
            if (mi !== S.selSeq) return;
            if (!r.ok) {
                muestraFicha('error'); $('fErrorT').textContent = r.status === 404 ? `No existe el activo ${etq(codigo)}.` : (r.error || 'No se pudo cargar la ficha');
                $('fReintentar').onclick = () => abre(codigo, { noUrl: true }); return;
            }
            datos = r.data; pintaFicha(datos);
        }
        anuncia(`Ficha de ${datos.etiqueta}: ${datos.nombre}`);
        if (!desk.matches || o.foco) setTimeout(() => { if (mi === S.selSeq) $('fNombre').focus({ preventScroll: true }); }, 60);
        if (o.scroll) { const b = $('lista').querySelector(`.fila[data-codigo="${CSS.escape(codigo)}"]`); if (b) b.scrollIntoView({ block: 'nearest' }); }
    }
    function cierraFicha(o = {}) {
        const cod = S.sel; S.sel = null; S.act = null; S.selSeq++;
        delete document.body.dataset.ficha; bgInerte(false); marcaFila(); muestraFicha('vacia');
        if (o.url !== false) { if (history.state && history.state.a) history.back(); else ponUrl(null, false); }
        if (o.foco !== false && !desk.matches) { const b = cod && $('lista').querySelector(`.fila[data-codigo="${CSS.escape(cod)}"]`); (b || $('lista')).focus({ preventScroll: true }); }
    }
    function pintaCarga(codigo) {
        muestraFicha('cont'); $('fCont').dataset.carga = '1'; $('fCont').setAttribute('aria-busy', 'true');
        $('fCodigo').textContent = etq(codigo); $('fNombre').textContent = 'Cargando ficha…'; $('fSub').textContent = ''; $('fEstado').textContent = ''; $('fEstado').dataset.e = '';
        $('fDatos').replaceChildren(...[0, 1, 2, 3].map(() => h('div', null, h('div', { class: 'sk sk-dd' }))));
    }

    function pintaFicha(a, eventos, parcial) {
        const ev = eventos !== undefined ? eventos : a.eventos;
        S.act = parcial ? null : a;
        muestraFicha('cont');
        const c = $('fCont'); c.dataset.carga = parcial ? '1' : ''; c.setAttribute('aria-busy', parcial ? 'true' : 'false');
        $('fCodigo').textContent = a.etiqueta || etq(a.codigo);
        $('fNombre').textContent = a.nombre; $('fNombre').style.color = '';
        $('fSub').textContent = [a.marca, a.modelo].filter(lleno).join(' · '); $('fSub').hidden = !$('fSub').textContent;
        const e = $('fEstado'); e.dataset.e = a.estado || ''; e.textContent = nombreEstado(a.estado);
        const filas = [['Departamento', a.departamento], ['Categoría', a.categoria], ['Ubicación', a.ubicacion], ['Responsable', a.responsable], ['Número de serie', a.serie, 'mono'],
            ['Adquisición', fFecha(a.fecha_adquisicion)], ['Valor', fValor(a.valor), 'mono'], ['Notas', a.notas, 'notas ancho']];
        $('fDatos').replaceChildren(...filas.map(([k, v, cls]) => h('div', { class: (cls || '').includes('ancho') ? 'ancho' : null },
            h('dt', null, k), h('dd', { class: lleno(v) ? (cls || '').replace('ancho', '').trim() : 'nada' }, lleno(v) ? v : '—'))));
        // características (pares etiqueta / valor)
        const cars = (a.caracteristicas || []).filter((x) => x && lleno(x.etiqueta));
        $('fCarSec').hidden = !cars.length;
        $('fCar').replaceChildren(...cars.map((x) => h('div', null, h('dt', null, x.etiqueta), h('dd', null, lleno(x.valor) ? String(x.valor) : '—'))));
        // etiqueta
        const papel = document.querySelector('#fCont .papel'); papel.dataset.err = '';
        const img = $('fSvg'); img.alt = `Vista previa de la etiqueta ${a.etiqueta || ''}`;
        img.onerror = () => { papel.dataset.err = '1'; };
        img.src = `/api/activos/${enc(a.codigo)}/etiqueta.svg?v=${enc(a.actualizado_en || a.impresiones || '0')}`;
        const imp = a.impresiones || 0;
        $('fEtqMeta').textContent = imp ? `Impresa ${imp} ${imp === 1 ? 'vez' : 'veces'}${a.ultima_impresion ? ' · última ' + fHora(a.ultima_impresion) : ''}` : 'Aún sin imprimir';
        // historial
        const hist = $('fHist');
        if (ev === null || ev === undefined) hist.replaceChildren(h('li', null, h('p', { class: 'hist-vacio' }, 'Cargando historial…')));
        else if (!ev.length) hist.replaceChildren(h('li', null, h('p', { class: 'hist-vacio' }, 'Sin movimientos registrados.')));
        else hist.replaceChildren(...ev.map((x) => {
            const t = String(x.evento || '').replace(/_/g, ' '); const quien = [x.por, fHora(x.creado_en)].filter(lleno).join(' · ');
            return h('li', null, h('b', null, t.charAt(0).toUpperCase() + t.slice(1)), lleno(x.detalle) ? h('p', null, x.detalle) : null, quien ? h('span', { class: 'quien' }, quien) : null);
        }));
    }
    $('fVolver').addEventListener('click', () => cierraFicha());
    $('bEditar').addEventListener('click', () => { if (S.act) abreForm(S.act); });
    window.addEventListener('popstate', () => {
        const c = new URLSearchParams(location.search).get('activo');
        if (c) abre(c, { noUrl: true }); else if (fichaAbierta()) cierraFicha({ url: false });
    });
    desk.addEventListener('change', () => { bgInerte(fichaAbierta() && !desk.matches); });
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && fichaAbierta() && !desk.matches && !document.querySelector('dialog[open]') && !document.querySelector(':popover-open')) cierraFicha();
    });

    /** Actualiza un activo ya mostrado (tras imprimir o editar) sin perder el lugar. */
    async function refresca(codigo) {
        const r = await api(`/api/activos/${enc(codigo)}`); if (!r.ok || !r.data) return null;
        const i = S.items.findIndex((x) => x.codigo === codigo);
        if (i >= 0) { S.items[i] = r.data; const li = $('lista').querySelector(`.fila[data-codigo="${CSS.escape(codigo)}"]`); if (li) { const nuevo = filaDe(r.data, 0); nuevo.firstChild.style.animation = 'none'; li.parentNode.replaceWith(nuevo); marcaFila(); } }
        if (S.sel === codigo) pintaFicha(r.data);
        return r.data;
    }

    // ------------------------------------------------------------------ mensajes en línea
    function setMsg(el, k, texto, acts) {
        if (!texto) { el.hidden = true; el.replaceChildren(); return; }
        el.hidden = false; el.dataset.k = k || '';
        el.replaceChildren(h('span', null, texto), acts && acts.length ? h('span', { class: 'acts' }, acts.map((a) => h('button', { class: 'btn btn-sm', type: 'button', onclick: a.fn }, a.t))) : null);
    }

    // ------------------------------------------------------------------ impresión
    const VIAS = [
        { id: 'compartida', t: 'DYMO compartida', d: 'La impresora DYMO de la oficina, desde cualquier equipo', ico: 'printer' },
        { id: 'connect', t: 'DYMO Connect (este equipo)', d: 'Una DYMO conectada por USB a esta computadora', ico: 'monitor' },
        { id: 'archivo', t: 'Descargar .dymo', d: 'Ábrela en DYMO Connect e imprime', ico: 'download' },
        { id: 'navegador', t: 'Imprimir desde el navegador', d: 'Etiqueta SVG a escala, con el diálogo del sistema', ico: 'external' },
    ];
    const viasVisibles = () => VIAS.filter((v) => !(v.id === 'connect' && esMovil));
    const itemVia = (v, fn, menu) => h('button', { class: 'via', type: 'button', role: menu ? 'menuitem' : null, dataset: { via: v.id }, onclick: () => fn(v.id) },
        h('span', { class: 'ic' }, icon(v.ico)), h('b', null, v.t), h('small', null, v.d));

    async function marcaImpreso(codigo) { return api(`/api/activos/${enc(codigo)}/impreso`, { method: 'POST' }); }
    async function finImpresion(a, msg, el) {
        const r = await refresca(a.codigo);
        setMsg(el, 'ok', msg + (r && r.impresiones ? ` · ${r.impresiones} ${r.impresiones === 1 ? 'impresión' : 'impresiones'}` : '')); toast(msg, { kind: 'ok' });
    }

    async function imprime(via, a, el) {
        if (!a || S.imprimiendo) return;
        const menu = $('menuImp'); if (menu.matches(':popover-open')) menu.hidePopover();
        const cod = a.codigo, ruta = `/api/activos/${enc(cod)}`;
        const descarga = { t: 'Descargar .dymo', fn: () => imprime('archivo', a, el) };
        S.imprimiendo = true; $('bImpSub').textContent = 'Enviando…'; document.querySelectorAll('.via, #bImp, #bMas').forEach((b) => { b.disabled = true; });
        try {
            if (via === 'compartida') {
                setMsg(el, 'info', 'Enviando a la DYMO compartida…');
                const r = await api(`${ruta}/imprimir`, { method: 'POST', timeout: 30000 });
                if (!r.ok) { setMsg(el, 'bad', r.network ? r.error : `No se imprimió: ${r.error}`, [descarga]); toast(r.error || 'No se pudo imprimir', { kind: 'bad' }); return; }
                await finImpresion(a, `Etiqueta ${a.etiqueta} enviada a la DYMO compartida`, el); estadoImpresora();
            } else if (via === 'connect') {
                setMsg(el, 'info', 'Buscando DYMO Connect en este equipo…');
                await cargaScript('/static/js/vendor/dymo.connect.framework.js?v=1316'); await cargaScript('/static/js/dymo_connect.js?v=1389');
                const d = await window.TQTDymo.detect();
                if (d.estado !== 'listo') {
                    const m = { movil: 'Desde un celular no se puede imprimir directo en la DYMO.', sin_framework: 'No se pudo cargar el componente de DYMO Connect.',
                        no_servicio: 'No se encontró DYMO Connect en este equipo. Ábrelo (o instálalo) y vuelve a intentar.', sin_impresoras: 'DYMO Connect no ve ninguna LabelWriter. Conéctala y enciéndela.' }[d.estado] || d.detalle;
                    setMsg(el, 'bad', m, [descarga]); return;
                }
                const rx = await fetch(`${ruta}/etiqueta/xml`, { cache: 'no-store' });
                if (!rx.ok) { let det = ''; try { det = (await rx.json()).detail; } catch (e) { /* nada */ } setMsg(el, 'bad', det || `El servidor respondió ${rx.status}.`); return; }
                setMsg(el, 'info', `Imprimiendo en ${d.preferred}…`);
                await window.TQTDymo.print(d.preferred, await rx.text(), 1);
                const ri = await marcaImpreso(cod);
                if (!ri.ok) toast('Se imprimió, pero no se pudo registrar: ' + ri.error, { kind: 'warn' });
                await finImpresion(a, `Etiqueta ${a.etiqueta} enviada a ${d.preferred}`, el);
            } else if (via === 'archivo') {
                const l = h('a', { href: `${ruta}/etiqueta/archivo?formato=dymo`, download: '' }); document.body.appendChild(l); l.click(); l.remove();
                setMsg(el, 'info', 'Archivo .dymo descargado. Ábrelo con DYMO Connect e imprime; no cuenta como impresa hasta que la registres.', [{ t: 'Ya la imprimí', fn: async () => { await marcaImpreso(cod); await finImpresion(a, `Impresión de ${a.etiqueta} registrada`, el); } }]);
            } else if (via === 'navegador') {
                setMsg(el, 'info', 'Preparando la etiqueta…');
                const fr = h('iframe', { style: 'position:fixed;right:0;bottom:0;width:0;height:0;border:0', 'aria-hidden': 'true', tabindex: '-1', title: 'Impresión' });
                document.body.appendChild(fr);
                const doc = fr.contentWindow.document; doc.open();
                doc.write(`<!doctype html><html><head><meta charset="utf-8"><title>${a.etiqueta}</title><style>@page{margin:0}html,body{margin:0;background:#fff}img{display:block}</style></head><body><img id="e" alt="" src="${ruta}/etiqueta.svg"></body></html>`);
                doc.close();
                await new Promise((ok, ko) => { const im = doc.getElementById('e'); if (im.complete && im.naturalWidth) ok(); else { im.onload = ok; im.onerror = () => ko(new Error('No se pudo cargar la etiqueta')); } });
                fr.contentWindow.focus(); fr.contentWindow.print();
                setTimeout(() => fr.remove(), 1500);
                setMsg(el, 'info', 'Se abrió el diálogo de impresión. Si la etiqueta salió, regístrala para llevar la cuenta.', [{ t: 'Sí, se imprimió', fn: async () => { await marcaImpreso(cod); await finImpresion(a, `Impresión de ${a.etiqueta} registrada`, el); } }]);
            }
        } catch (e) {
            setMsg(el, 'bad', (e && e.message) || 'No se pudo imprimir', via === 'connect' ? [descarga] : null);
        } finally {
            S.imprimiendo = false; pintaImpSub(); document.querySelectorAll('.via, #bImp, #bMas').forEach((b) => { b.disabled = false; });
        }
    }

    // menú de impresión (popover)
    const menuImp = $('menuImp');
    menuImp.addEventListener('beforetoggle', (e) => { if (e.newState === 'open') menuImp.replaceChildren(...viasVisibles().filter((v) => v.id !== 'compartida').map((v) => itemVia(v, (id) => imprime(id, S.act, $('fMsg')), true))); });
    menuImp.addEventListener('toggle', (e) => {
        const b = $('bMas'); b.setAttribute('aria-expanded', String(e.newState === 'open'));
        if (e.newState !== 'open') return;
        if (desk.matches) {
            const r = b.getBoundingClientRect(), m = menuImp.getBoundingClientRect();
            let left = Math.min(r.left, innerWidth - m.width - 12), top = r.bottom + 6;
            if (top + m.height > innerHeight - 12) top = Math.max(12, r.top - m.height - 6);
            menuImp.style.left = Math.max(12, left) + 'px'; menuImp.style.top = top + 'px';
        }
        const p = menuImp.querySelector('button'); if (p) p.focus();
    });
    menuImp.addEventListener('keydown', (e) => {
        const bs = [...menuImp.querySelectorAll('button')], i = bs.indexOf(document.activeElement);
        if (e.key === 'ArrowDown') { e.preventDefault(); bs[(i + 1) % bs.length].focus(); }
        else if (e.key === 'ArrowUp') { e.preventDefault(); bs[(i - 1 + bs.length) % bs.length].focus(); }
        else if (e.key === 'Home') { e.preventDefault(); bs[0].focus(); }
        else if (e.key === 'End') { e.preventDefault(); bs[bs.length - 1].focus(); }
        else if (e.key === 'Tab') menuImp.hidePopover();
    });

    // ------------------------------------------------------------------ alta / edición
    const CAMPOS = ['nombre', 'departamento', 'categoria', 'estado', 'marca', 'modelo', 'serie', 'ubicacion', 'responsable', 'fecha_adquisicion', 'valor', 'notas'];
    const ID_CAMPO = { nombre: 'fNom', departamento: 'fDepto', categoria: 'fCateg', estado: 'fEstado2', marca: 'fMarca', modelo: 'fModelo', serie: 'fSerie', ubicacion: 'fUbic', responsable: 'fResp', fecha_adquisicion: 'fFecha', valor: 'fValor', notas: 'fNotas' };
    const hoja = $('hoja');
    const numTxt = () => { const n = parseInt($('fNum').value, 10); return 'ACT ' + (isNaN(n) ? '0000' : pad4(n)); };
    const parseValor = (s) => { const t = String(s || '').replace(/[$,\s]/g, ''); return t === '' ? null : Number(t); };

    function errCampo(id, msg) {
        const el = $(id), e = $(id + 'E'); if (!el) return;
        el.setAttribute('aria-invalid', msg ? 'true' : 'false');
        if (e) { e.hidden = !msg; e.textContent = msg || ''; }
    }
    function valida(id) {
        const v = $(id).value.trim(); let m = '';
        if (id === 'fNom' && !v) m = 'Escribe el nombre del activo.';
        if (id === 'fNum' && !S.edit) { const n = Number(v); if (!/^\d+$/.test(v) || n < 1 || n > 999999) m = 'Escribe un número entre 1 y 999999.'; }
        if (id === 'fValor' && v) { const n = parseValor(v); if (n === null || isNaN(n) || n < 0) m = 'Escribe un importe válido, por ejemplo 1250.50.'; }
        errCampo(id, m); return !m;
    }
    ['fNum', 'fNom', 'fValor'].forEach((id) => $(id).addEventListener('blur', () => valida(id)));
    $('fNum').addEventListener('input', (e) => { e.target.value = e.target.value.replace(/\D/g, ''); $('fNumVivo').textContent = numTxt(); errCampo('fNum', ''); });
    ['fNom', 'fValor'].forEach((id) => $(id).addEventListener('input', () => { if ($(id).getAttribute('aria-invalid') === 'true') valida(id); }));

    // editor de características: filas etiqueta + valor (multilínea), con quitar y agregar
    function filaCar(c) {
        const et = h('input', { class: 'input', type: 'text', maxlength: '80', list: 'dlCarEt', value: c ? String(c.etiqueta || '') : '', 'aria-label': 'Nombre de la característica', placeholder: 'Nombre (ej. Procesador)' });
        const va = h('textarea', { class: 'input', rows: '2', maxlength: '1000', 'aria-label': 'Valor de la característica', placeholder: 'Valor' }); va.value = c && c.valor != null ? String(c.valor) : '';
        const fila = h('div', { class: 'car-fila' }, et, h('button', { class: 'iconbtn', type: 'button', 'aria-label': 'Quitar esta característica', title: 'Quitar', onclick: () => { const sig = fila.nextElementSibling || fila.previousElementSibling; fila.remove(); (sig ? sig.querySelector('input') : $('carAdd')).focus(); } }, icon('trash')), va);
        return fila;
    }
    function pintaCarEd(arr) { $('carLista').replaceChildren(...(arr || []).map(filaCar)); }
    function leeCarEd() {
        return [...$('carLista').querySelectorAll('.car-fila')].map((f) => ({ etiqueta: f.querySelector('input').value.trim(), valor: f.querySelector('textarea').value.trim() })).filter((x) => x.etiqueta);
    }
    $('carAdd').addEventListener('click', () => { const f = filaCar(null); $('carLista').appendChild(f); f.querySelector('input').focus(); });

    async function abreForm(a) {
        S.edit = a || null;
        hoja.dataset.paso = 'form'; $('hErr').hidden = true; $('hErr').textContent = '';
        ['fNum', 'fNom', 'fValor'].forEach((id) => errCampo(id, ''));
        $('form').reset(); pintaCarEd(a ? a.caracteristicas : []);
        $('hKicker').textContent = a ? a.etiqueta : 'Nuevo activo'; $('hTit').textContent = a ? 'Editar activo' : 'Registrar activo';
        $('hGuardar').firstChild.textContent = a ? 'Guardar cambios' : 'Guardar activo';
        const num = $('fNum'); num.readOnly = !!a;
        $('fNumAy').textContent = a ? 'El número no se puede cambiar: ya está impreso en la etiqueta.' : 'Sugerido por el sistema. Cámbialo solo si ya tienes una etiqueta con otro número.';
        if (a) {
            num.value = String(a.numero); CAMPOS.forEach((k) => { const el = $(ID_CAMPO[k]); const v = a[k]; el.value = v === null || v === undefined ? '' : String(v); });
            $('fNumVivo').textContent = a.etiqueta;
        } else {
            $('fEstado2').value = 'activo';
            const sug = S.siguiente && S.siguiente.numero != null ? S.siguiente : null;
            if (sug) num.value = String(sug.numero);
            $('fNumVivo').textContent = numTxt();
            api('/api/activos/siguiente').then((r) => { if (r.ok && r.data && !S.edit && hoja.open && !num.dataset.tocado) { num.value = String(r.data.numero); $('fNumVivo').textContent = numTxt(); } });
        }
        num.addEventListener('input', () => { num.dataset.tocado = '1'; }, { once: true }); delete num.dataset.tocado;
        if (!hoja.open) hoja.showModal();
        setTimeout(() => $('fNom').focus(), 40);
    }
    const cierraForm = () => { if (hoja.open) hoja.close(); };
    $('hX').addEventListener('click', cierraForm); $('hCancel').addEventListener('click', cierraForm); $('hhX').addEventListener('click', cierraForm);
    $('bNuevo').addEventListener('click', () => abreForm(null));

    $('form').addEventListener('submit', async (ev) => {
        ev.preventDefault();
        const ids = ['fNom', 'fValor']; if (!S.edit) ids.unshift('fNum');
        const malos = ids.filter((id) => !valida(id));
        if (malos.length) { $(malos[0]).focus(); return; }
        const val = {}; CAMPOS.forEach((k) => { val[k] = $(ID_CAMPO[k]).value.trim(); });
        const btn = $('hGuardar'), txt = btn.firstChild.textContent; $('hErr').hidden = true;
        let r;
        if (!S.edit) {
            const body = { numero: Number($('fNum').value) }; const cs = leeCarEd(); if (cs.length) body.caracteristicas = cs;
            CAMPOS.forEach((k) => { if (k === 'valor') { const n = parseValor(val.valor); if (n !== null) body.valor = n; } else if (lleno(val[k])) body[k] = val[k]; });
            btn.disabled = true; btn.firstChild.textContent = 'Guardando…';
            r = await api('/api/activos', { method: 'POST', body });
        } else {
            const body = {}; CAMPOS.forEach((k) => {
                const orig = S.edit[k] === null || S.edit[k] === undefined ? '' : String(S.edit[k]);
                if (k === 'valor') { const n = parseValor(val.valor); if (String(n === null ? '' : n) !== orig) body.valor = n; } else if (val[k] !== orig) body[k] = val[k];
            });
            const cs = leeCarEd(), co = (S.edit.caracteristicas || []).map((x) => ({ etiqueta: String(x.etiqueta || '').trim(), valor: String(x.valor == null ? '' : x.valor).trim() })).filter((x) => x.etiqueta);
            if (JSON.stringify(cs) !== JSON.stringify(co)) body.caracteristicas = cs;
            if (!Object.keys(body).length) { cierraForm(); toast('No hay cambios que guardar'); return; }
            btn.disabled = true; btn.firstChild.textContent = 'Guardando…';
            r = await api(`/api/activos/${enc(S.edit.codigo)}`, { method: 'PATCH', body });
        }
        btn.disabled = false; btn.firstChild.textContent = txt;
        if (!r.ok) {
            if (r.status === 409) { errCampo('fNum', r.error || 'Ese número ya está ocupado.'); $('fNum').focus(); }
            else { const e = $('hErr'); e.hidden = false; e.textContent = r.error || 'No se pudo guardar'; e.scrollIntoView({ block: 'nearest' }); }
            return;
        }
        const a = r.data;
        await Promise.all([cargaLista({ silencio: true }), cargaCatalogos()]);
        if (S.edit) {
            cierraForm(); await abre(a.codigo, { push: false, noUrl: false, scroll: true });
            toast(`Cambios en ${a.etiqueta} guardados`, { kind: 'ok', action: { label: 'Imprimir etiqueta', onClick: () => { imprime('compartida', a, $('fMsg')); } } });
        } else pasoHecho(a);
    });

    function pasoHecho(a) {
        hoja.dataset.paso = 'hecho'; S.nuevo = a;
        $('hhTit').textContent = `${a.etiqueta} registrado`; $('hhCodigo').textContent = a.etiqueta; $('hhNombre').textContent = a.nombre;
        $('hhSvg').alt = `Vista previa de la etiqueta ${a.etiqueta}`; $('hhSvg').src = `/api/activos/${enc(a.codigo)}/etiqueta.svg?v=${enc(a.actualizado_en || '0')}`;
        setMsg($('hhMsg'), '');
        $('hhVias').replaceChildren(...viasVisibles().map((v) => itemVia(v, (id) => imprime(id, a, $('hhMsg')))));
        setTimeout(() => $('hhTit').focus(), 40);
    }
    $('hhListo').addEventListener('click', () => { const a = S.nuevo; cierraForm(); if (a) abre(a.codigo, { push: false, scroll: true }); });
    $('hhOtro').addEventListener('click', async () => { const a = S.nuevo; if (a) await abre(a.codigo, { push: false, noUrl: false }); abreForm(null); });

    // ------------------------------------------------------------------ importar activos desde Excel (vista previa → importar → etiquetas)
    const dImp = $('hojaImp');
    const IMP = { archivo: null, tot: null, codigos: [], ocupado: false };
    const MAX_XLSX = 10 * 1024 * 1024;
    const TIT_IMP = { elige: ['Paso 1 de 3', 'Importar desde Excel'], revisa: ['Paso 2 de 3', 'Revisa antes de importar'], listo: ['Paso 3 de 3', 'Importación terminada'] };
    const pasoImp = (p) => { dImp.dataset.paso = p; $('iKicker').textContent = TIT_IMP[p][0]; $('iTit').textContent = TIT_IMP[p][1]; };
    const nTxt = (n, uno, varios) => `${n} ${n === 1 ? uno : varios}`;
    const detalleDe = (d) => (typeof d === 'string' ? d : Array.isArray(d) ? d.map((x) => (x && x.msg) || JSON.stringify(x)).join('; ') : '');

    function eligeArchivo(f) {
        const err = $('iErr'); err.hidden = true;
        if (!f) return;
        if (!/\.xlsx$/i.test(f.name)) { err.hidden = false; err.textContent = 'El archivo debe ser un Excel con extensión .xlsx.'; return; }
        if (f.size > MAX_XLSX) { err.hidden = false; err.textContent = 'El archivo pasa de 10 MB. Divide el Excel o quita imágenes.'; return; }
        IMP.archivo = f; $('iNombre').hidden = false; $('iNombre').textContent = `${f.name} · ${Math.max(1, Math.round(f.size / 1024))} KB`; $('iRevisar').disabled = false;
    }
    function abreImp() {
        IMP.archivo = null; IMP.codigos = []; $('iArchivo').value = ''; $('iNombre').hidden = true; $('iRevisar').disabled = true;
        $('iErr').hidden = true; $('iErr2').hidden = true; $('iBarra').hidden = true; setMsg($('iMsg'), '');
        pasoImp('elige'); if (!dImp.open) dImp.showModal();
    }
    async function subeExcel(aplicar) {
        const fd = new FormData();
        fd.append('archivo', IMP.archivo, IMP.archivo.name); fd.append('solo_verdes', $('iVerdes').checked ? '1' : '0'); fd.append('aplicar', aplicar ? '1' : '0');
        let res; try { res = await fetch('/api/activos/importar', { method: 'POST', body: fd }); } catch (e) { return { ok: false, error: 'Sin conexión con el servidor' }; }
        let data = null; try { data = await res.json(); } catch (e) { data = null; }
        if (!res.ok) return { ok: false, status: res.status, error: detalleDe(data && data.detail) || (res.status === 413 ? 'El archivo es demasiado grande (máximo 10 MB).' : `Error ${res.status}`) };
        return { ok: true, data: data || {} };
    }
    function pintaPrev(d) {
        const t = d.totales || { nuevos: 0, actualizar: 0, omitidos: 0 }; IMP.tot = t;
        $('iArchResumen').textContent = `${IMP.archivo.name} · ${$('iVerdes').checked ? 'solo filas marcadas en verde' : 'todas las filas'}`;
        $('iTotales').replaceChildren(...[['nuevos', t.nuevos, 'Nuevos'], ['actualizar', t.actualizar, 'A actualizar'], ['omitidos', t.omitidos, 'Omitidos']].map(([k, n, l]) => h('div', { class: 'tot', dataset: { k } }, h('b', null, String(n || 0)), h('span', null, l))));
        const hojas = d.hojas || [];
        $('iHojas').replaceChildren(...(hojas.length ? hojas.map((x) => h('tr', null, h('td', null, x.hoja, x.formato ? h('span', { class: 'muted' }, ' · ' + x.formato) : null),
            h('td', { class: 'n' }, String(x.filas_verdes || 0)), h('td', { class: 'n' }, String(x.nuevos || 0)), h('td', { class: 'n' }, String(x.actualizar || 0)), h('td', { class: 'n' }, String((x.omitidos || []).length)))) : [h('tr', null, h('td', { colspan: '5' }, 'El archivo no tiene hojas con activos reconocibles.'))]));
        $('iOmit').replaceChildren(...hojas.filter((x) => (x.omitidos || []).length).map((x) => {
            const om = x.omitidos, ver = om.slice(0, 50);
            return h('details', { class: 'omit' }, h('summary', null, `${x.hoja}: ${nTxt(om.length, 'fila omitida', 'filas omitidas')}`),
                h('ul', null, ver.map((o) => h('li', null, `Fila ${o.fila}: ${o.motivo}`)), om.length > ver.length ? h('li', null, `… y ${om.length - ver.length} más`) : null));
        }));
        const m = d.muestra || [];
        $('iMuestraT').textContent = m.length ? `Muestra (${m.length} de ${(t.nuevos || 0) + (t.actualizar || 0)})` : 'Muestra';
        $('iMuestra').replaceChildren(...(m.length ? m.map((a) => h('tr', null, h('td', { class: 'cod' }, a.etiqueta || (a.codigo ? etq(a.codigo) : 'Nuevo')), h('td', null, a.nombre || '—'), h('td', null, a.departamento || '—'), h('td', null, a.responsable || '—')))
            : [h('tr', null, h('td', { colspan: '4' }, 'Sin activos que mostrar con estos criterios.'))]));
        const n = (t.nuevos || 0) + (t.actualizar || 0);
        const ap = $('iAplicar'); ap.disabled = !n; ap.firstChild.textContent = n ? `Importar ${nTxt(n, 'activo', 'activos')}` : 'Nada que importar';
    }
    $('bImportar').addEventListener('click', abreImp);
    ['iX', 'iCancel', 'iCerrar'].forEach((id) => $(id).addEventListener('click', () => dImp.close()));
    $('iArchivo').addEventListener('change', (e) => eligeArchivo(e.target.files[0]));
    (function () {
        const dz = $('drop');
        ['dragenter', 'dragover'].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.dataset.sobre = '1'; }));
        ['dragleave', 'drop'].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.dataset.sobre = ''; }));
        dz.addEventListener('drop', (e) => { const f = e.dataTransfer && e.dataTransfer.files[0]; if (f) eligeArchivo(f); });
    })();
    $('iRevisar').addEventListener('click', async () => {
        if (!IMP.archivo || IMP.ocupado) return; IMP.ocupado = true;
        const b = $('iRevisar'); b.disabled = true; b.firstChild.textContent = 'Revisando…'; $('iErr').hidden = true;
        const r = await subeExcel(false);
        IMP.ocupado = false; b.disabled = false; b.firstChild.textContent = 'Revisar archivo';
        if (!r.ok) { $('iErr').hidden = false; $('iErr').textContent = r.error; return; }
        $('iErr2').hidden = true; pintaPrev(r.data); pasoImp('revisa'); $('iTit').focus();
    });
    $('iOtro').addEventListener('click', () => { if (!IMP.ocupado) { pasoImp('elige'); $('iTit').focus(); } });
    $('iAplicar').addEventListener('click', async () => {
        if (IMP.ocupado) return; IMP.ocupado = true;
        const b = $('iAplicar'), txt = b.firstChild.textContent; b.disabled = true; $('iOtro').disabled = true; b.firstChild.textContent = 'Importando…'; $('iBarra').hidden = false; $('iErr2').hidden = true;
        const r = await subeExcel(true);
        IMP.ocupado = false; $('iOtro').disabled = false; $('iBarra').hidden = true; b.disabled = false; b.firstChild.textContent = txt;
        if (!r.ok) { $('iErr2').hidden = false; $('iErr2').textContent = r.error; return; }
        const t = r.data.totales || IMP.tot || {}; IMP.codigos = r.data.codigos || [];
        const q = (n) => h('b', { class: 'mono' }, String(n || 0));
        $('iResT').replaceChildren('Se importaron ', q(t.nuevos), t.nuevos === 1 ? ' nuevo' : ' nuevos', ' y se actualizaron ', q(t.actualizar), '.');
        $('iResS').textContent = (t.omitidos ? `${nTxt(t.omitidos, 'fila se omitió', 'filas se omitieron')}. ` : '') + (IMP.codigos.length ? 'Ya puedes imprimir las etiquetas de lo importado.' : '');
        ['iImpLote', 'iZip', 'iVer'].forEach((id) => { $(id).hidden = !IMP.codigos.length; });
        $('iZip').href = `/api/activos/etiquetas.zip?codigos=${IMP.codigos.map(enc).join(',')}`;
        setMsg($('iMsg'), ''); pasoImp('listo'); $('iResT').focus();
        S.soloCodigos = null; await Promise.all([cargaLista({ silencio: true }), cargaCatalogos()]);
    });
    $('iImpLote').addEventListener('click', async () => {
        const b = $('iImpLote'); if (b.disabled || !IMP.codigos.length) return; b.disabled = true; setMsg($('iMsg'), 'info', `Enviando ${nTxt(IMP.codigos.length, 'etiqueta', 'etiquetas')} a la DYMO compartida…`);
        const r = await api('/api/activos/imprimir-lote', { method: 'POST', body: { codigos: IMP.codigos }, timeout: 120000 });
        b.disabled = false;
        const zip = [{ t: 'Descargar .zip', fn: () => $('iZip').click() }];
        if (!r.ok) { setMsg($('iMsg'), 'bad', r.error || 'No se pudo enviar a imprimir', zip); return; }
        const er = (r.data && r.data.errores) || [], ok = (r.data && r.data.encolados) || 0;
        const det = er.slice(0, 5).map((e) => `${e.codigo}: ${e.detail}`).join(' · ') + (er.length > 5 ? ` · y ${er.length - 5} más` : '');
        setMsg($('iMsg'), er.length ? 'warn' : 'ok', `${nTxt(ok, 'etiqueta encolada', 'etiquetas encoladas')} en la DYMO compartida.` + (er.length ? ` ${nTxt(er.length, 'con error', 'con errores')}: ${det}` : ''), er.length ? zip : null);
        if (ok) toast(`${nTxt(ok, 'etiqueta encolada', 'etiquetas encoladas')}`, { kind: 'ok' });
    });
    $('iVer').addEventListener('click', () => {
        if (!IMP.codigos.length) return;
        S.q = S.estado = S.categoria = S.departamento = ''; $('q').value = ''; $('fEst').value = ''; $('fCat').value = ''; $('fDep').value = '';
        S.soloCodigos = new Set(IMP.codigos); dImp.close(); cargaLista();
    });


    // ------------------------------------------------------------------ estado de la impresora compartida (cabecera y botón Imprimir)
    const PR = { disponible: null, e: '?', txt: 'comprobando…', detalle: '' };
    function pintaImpSub() { $('bImpSub').textContent = `DYMO compartida · ${PR.txt}`; }
    async function estadoImpresora() {
        const r = await api('/api/activos/impresora/estado', { timeout: 6000 });
        let e = 'off', txt = 'sin conexión', det = '';
        if (r.ok && r.data) {
            const ags = r.data.agentes || [], en = ags.find((a) => a.en_linea);
            PR.disponible = !!r.data.disponible;
            if (r.data.disponible) { e = 'ok'; txt = 'lista' + (r.data.en_cola ? ` · ${r.data.en_cola} en cola` : ''); }
            else if (en) { e = 'warn'; txt = 'en línea, no lista'; det = en.detalle || ''; }
            else det = ags.length ? 'La estación de impresión no responde.' : 'No hay estación de impresión registrada.';
        } else if (r.network) { PR.disponible = false; det = 'Sin conexión con el servidor.'; }
        else { PR.disponible = null; e = '?'; txt = 'sin datos'; det = r.error || ''; }
        PR.e = e; PR.txt = txt; PR.detalle = det;
        const b = $('bEstImp'); b.dataset.e = e; $('estImpT').textContent = txt;
        b.title = `Impresora compartida: ${txt}${det ? ' — ' + det : ''}. Toca para volver a comprobar.`;
        if (!S.imprimiendo) pintaImpSub();
        return PR;
    }
    $('bEstImp').addEventListener('click', () => { $('estImpT').textContent = 'comprobando…'; estadoImpresora(); });
    setInterval(() => { if (!document.hidden) estadoImpresora(); }, 20000);
    document.addEventListener('visibilitychange', () => { if (!document.hidden) estadoImpresora(); });
    $('bImp').addEventListener('click', () => { if (S.act) imprime('compartida', S.act, $('fMsg')); });

    // ------------------------------------------------------------------ imprimir lote (selección → envío → progreso por trabajo)
    const dLote = $('hojaLote');
    const LT = { items: [], sel: new Set(), seq: 0, job: new Map(), err: new Map(), timer: null, enviando: false, codigos: [] };
    const MAX_LOTE = 500;
    const ymd = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
    const diaRel = (n) => { const d = new Date(); d.setDate(d.getDate() + n); return ymd(d); };
    const modoFecha = () => (document.querySelector('input[name="lFecha"]:checked') || {}).value || 'todas';
    function paramsLote() {
        const qs = new URLSearchParams(), m = modoFecha();
        if (m === 'hoy' || m === 'ayer') { const d = diaRel(m === 'hoy' ? 0 : -1); qs.set('desde', d); qs.set('hasta', d); }
        else if (m === 'dia' && $('lDia').value) { qs.set('desde', $('lDia').value); qs.set('hasta', $('lDia').value); }
        else if (m === 'rango') { if ($('lDesde').value) qs.set('desde', $('lDesde').value); if ($('lHasta').value) qs.set('hasta', $('lHasta').value); }
        if ($('lSinImp').checked) qs.set('impresa', '0');
        if ($('lDep').value) qs.set('departamento', $('lDep').value);
        if ($('lQ').value.trim()) qs.set('q', $('lQ').value.trim());
        return qs;
    }
    const pasoLote = (p) => {
        dLote.dataset.paso = p;
        $('lKicker').textContent = p === 'elige' ? 'Impresión por lote · paso 1 de 2' : 'Impresión por lote · paso 2 de 2';
        $('lTit').textContent = p === 'elige' ? 'Elegir etiquetas' : 'Imprimiendo etiquetas';
    };
    function avisoLote(msg, k, comprobar) {
        const a = $('lAviso');
        if (!msg && PR.disponible === false) { msg = `La impresora compartida no está disponible${PR.detalle ? ` (${PR.detalle})` : ''}. Puedes descargar las etiquetas en .zip o volver a comprobar.`; k = 'warn'; comprobar = true; }
        if (!msg) { a.hidden = true; a.replaceChildren(); return; }
        a.hidden = false; a.dataset.k = k || '';
        a.replaceChildren(h('span', null, msg), comprobar ? h('button', { class: 'btn btn-sec', type: 'button', onclick: async () => { await estadoImpresora(); avisoLote(); } }, icon('refresh'), 'Volver a comprobar') : null);
    }
    function actualizaLote() {
        const n = LT.sel.size, tot = LT.items.length;
        $('lCuenta').textContent = LT.cargando ? 'Buscando…' : (tot ? `${n} de ${tot} ${tot === 1 ? 'etiqueta seleccionada' : 'etiquetas seleccionadas'}` : 'Sin activos para imprimir');
        const t = $('lTodos'); t.checked = !!tot && n === tot; t.indeterminate = n > 0 && n < tot; t.disabled = !tot;
        const sinImp = PR.disponible === false, mucho = n > MAX_LOTE, e = $('lEnviar');
        e.disabled = !n || mucho || sinImp || LT.enviando;
        e.lastChild.textContent = n ? `Enviar ${n} ${n === 1 ? 'etiqueta' : 'etiquetas'} a la impresora` : 'Enviar etiquetas a la impresora';
        e.title = sinImp ? 'La impresora compartida no está disponible' : (mucho ? `El máximo por envío es ${MAX_LOTE}` : '');
        const z = $('lZip'); z.setAttribute('aria-disabled', n && !mucho ? 'false' : 'true');
        z.href = n && !mucho ? `/api/activos/etiquetas.zip?codigos=${[...LT.sel].map(enc).join(',')}` : '#';
        if (mucho) avisoLote(`Elegiste ${n}: el máximo por envío es ${MAX_LOTE}. Acota la fecha o el departamento, o desmarca algunas.`, 'warn', false);
        else if (!$('lAviso').hidden && $('lAviso').dataset.k === 'warn' && n <= MAX_LOTE && PR.disponible !== false) avisoLote();
    }
    function pintaLote() {
        const ul = $('lLista'), est = $('lEstado'); est.hidden = true; est.replaceChildren();
        ul.setAttribute('aria-busy', LT.cargando ? 'true' : 'false');
        if (LT.cargando && !LT.items.length) { ul.replaceChildren(...[0, 1, 2, 3].map(() => h('li', { 'aria-hidden': 'true' }, h('div', { class: 'sk', style: 'height:64px;border:0;border-radius:0' })))); actualizaLote(); return; }
        if (LT.error) { ul.replaceChildren(); est.hidden = false; est.dataset.k = 'error'; est.append(h('h2', null, 'No se pudo cargar'), h('p', null, LT.error), h('button', { class: 'btn', type: 'button', onclick: cargaLote }, icon('refresh'), 'Reintentar')); actualizaLote(); return; }
        if (!LT.items.length) { ul.replaceChildren(); est.hidden = false; delete est.dataset.k; est.append(h('h2', null, 'Ningún activo coincide'), h('p', null, 'Prueba con otra fecha, quita «Solo sin imprimir» o cambia el departamento.')); actualizaLote(); return; }
        ul.replaceChildren(...LT.items.map((a) => {
            const imp = a.impresiones || 0, cb = h('input', { type: 'checkbox', 'aria-label': `Seleccionar ${a.etiqueta}`, dataset: { c: a.codigo } }); cb.checked = LT.sel.has(a.codigo);
            const det = [a.departamento, a.creado_en ? 'alta ' + fFecha(a.creado_en) : '', imp ? `impresa ${imp} ${imp === 1 ? 'vez' : 'veces'}` : 'sin imprimir'].filter(lleno).join(' · ');
            return h('li', null, h('label', { class: 'lote-fila' }, cb,
                h('img', { src: `/api/activos/${enc(a.codigo)}/etiqueta.svg?v=${enc(a.actualizado_en || '0')}`, alt: '', loading: 'lazy', decoding: 'async', width: '104' }),
                h('span', { class: 'lf-t' }, h('b', { class: 'mono' }, a.etiqueta || etq(a.codigo)), h('span', null, a.nombre), h('small', null, det))));
        }));
        actualizaLote();
    }
    async function cargaLote() {
        const mi = ++LT.seq; LT.cargando = true; LT.error = ''; pintaLote();
        const r = await api('/api/activos?' + paramsLote(), { timeout: 15000 });
        if (mi !== LT.seq) return;
        LT.cargando = false;
        if (r.ok && r.data) { LT.items = r.data.items || []; LT.sel = new Set(LT.items.map((a) => a.codigo)); } else { LT.items = []; LT.sel = new Set(); LT.error = r.error || 'Error al cargar'; }
        pintaLote();
    }
    const cargaLoteDeb = T.debounce(cargaLote, 280);
    function abreLote() {
        LT.items = []; LT.sel = new Set(); LT.error = ''; $('lFiltros').reset(); $('lDiaW').hidden = true; $('lRangoW').hidden = true;
        llenaSelect($('lDep'), 'Todos', S.cat.departamentos || [], (c) => [nm(c), nm(c)]);
        paraSondeo(); pasoLote('elige'); avisoLote(); if (!dLote.open) dLote.showModal();
        estadoImpresora().then(() => { avisoLote(); actualizaLote(); }); cargaLote();
    }
    $('bLote').addEventListener('click', abreLote);
    ['lX', 'lListo'].forEach((id) => $(id).addEventListener('click', () => dLote.close()));
    dLote.addEventListener('close', paraSondeo);
    $('lFiltros').addEventListener('submit', (e) => e.preventDefault());
    $('lFiltros').addEventListener('change', (e) => {
        if (e.target.name === 'lFecha') {
            const m = modoFecha(); $('lDiaW').hidden = m !== 'dia'; $('lRangoW').hidden = m !== 'rango';
            if (m === 'dia' && !$('lDia').value) $('lDia').value = diaRel(0);
            if (m === 'dia') $('lDia').focus();
        }
        cargaLote();
    });
    $('lQ').addEventListener('input', cargaLoteDeb);
    $('lLista').addEventListener('change', (e) => { const c = e.target.dataset && e.target.dataset.c; if (!c) return; if (e.target.checked) LT.sel.add(c); else LT.sel.delete(c); actualizaLote(); });
    $('lTodos').addEventListener('change', (e) => {
        LT.sel = e.target.checked ? new Set(LT.items.map((a) => a.codigo)) : new Set();
        $('lLista').querySelectorAll('input[data-c]').forEach((cb) => { cb.checked = LT.sel.has(cb.dataset.c); }); actualizaLote();
    });
    $('lZip').addEventListener('click', (e) => { if ($('lZip').getAttribute('aria-disabled') === 'true') e.preventDefault(); });

    // envío
    function paraSondeo() { clearTimeout(LT.timer); LT.timer = null; }
    const ETQ_JOB = { pendiente: 'En cola', imprimiendo: 'Imprimiendo', impresa: 'Impresa', error: 'Error' };
    function pintaProgreso() {
        const js = [...LT.job.entries()];
        const imp = js.filter(([, j]) => j.estado === 'impresa').length, cola = js.filter(([, j]) => j.estado === 'pendiente' || j.estado === 'imprimiendo').length;
        const err = js.filter(([, j]) => j.estado === 'error').length + LT.err.size, tot = js.length + LT.err.size;
        const pct = tot ? Math.round(((imp + err) / tot) * 100) : 0;
        $('lBarra').style.width = pct + '%'; $('lBarraW').setAttribute('aria-valuenow', String(pct));
        $('lTot').replaceChildren(...[['impresas', imp, 'Impresas'], ['cola', cola, 'En cola'], ['error', err, 'Con error']].map(([k, n, l]) => h('div', { class: 'tot', dataset: { k } }, h('b', null, String(n)), h('span', null, l))));
        const fin = cola === 0;
        $('lResT').textContent = fin ? (err ? `Terminó: ${nTxt(imp, 'etiqueta impresa', 'etiquetas impresas')} y ${nTxt(err, 'con error', 'con errores')}` : `Listo: ${nTxt(imp, 'etiqueta impresa', 'etiquetas impresas')}`) : `Imprimiendo ${nTxt(tot - err, 'etiqueta', 'etiquetas')}…`;
        $('lReintentar').hidden = !(fin && err);
        const filas = [...LT.err.entries()].map(([c, d]) => ({ c, e: 'error', d })).concat(js.filter(([, j]) => j.estado !== 'impresa').map(([, j]) => ({ c: j.codigo, e: j.estado, d: j.detalle || (j.delante ? `${j.delante} por delante` : '') })));
        filas.sort((a, b) => (a.e === 'error' ? -1 : 1) - (b.e === 'error' ? -1 : 1));
        $('lJobs').replaceChildren(...filas.slice(0, 80).map((f) => h('li', null, h('b', { class: 'mono' }, etq(f.c)), h('span', { class: 'chip', dataset: { e: f.e === 'error' ? 'error' : 'cola' } }, ETQ_JOB[f.e] || f.e), f.d ? h('small', null, f.d) : null)),
            filas.length > 80 ? [h('li', null, h('small', null, `… y ${filas.length - 80} más`))] : []);
        return fin;
    }
    async function sondeaLote() {
        LT.timer = null; if (!dLote.open || dLote.dataset.paso !== 'progreso') return;
        const pend = [...LT.job.entries()].filter(([, j]) => j.estado === 'pendiente' || j.estado === 'imprimiendo').map(([id]) => id);
        if (pend.length) {
            for (let i = 0; i < pend.length; i += 60) {
                const r = await api('/api/activos/lote/estado?trabajos=' + pend.slice(i, i + 60).map(enc).join(','), { timeout: 8000 });
                if (r.ok && r.data) (r.data.trabajos || []).forEach((t) => { const j = LT.job.get(t.trabajo_id); if (j) { j.estado = t.estado; j.detalle = t.detalle || ''; j.delante = t.delante; } });
                else if (r.status === 403 || r.status === 404) { setMsg($('lMsg'), 'warn', 'No se pudo consultar el avance: ' + (r.error || r.status)); }
            }
        }
        if (!dLote.open) return;
        if (pintaProgreso()) { cargaLista({ silencio: true }); estadoImpresora(); return; }
        LT.timer = setTimeout(sondeaLote, 2000);
    }
    async function enviaLote(codigos, reintento) {
        if (LT.enviando) return; LT.enviando = true; actualizaLote();
        const b = reintento ? $('lReintentar') : $('lEnviar'); b.disabled = true;
        const r = await api('/api/activos/imprimir-lote', { method: 'POST', body: { codigos }, timeout: 120000 });
        LT.enviando = false; b.disabled = false;
        if (!r.ok) {
            const m = r.status === 503 ? `${r.error} La impresora compartida no está disponible.` : (r.status === 404 ? 'Ningún activo coincide con la selección.' : r.error || 'No se pudo enviar el lote');
            if (r.status === 503) estadoImpresora();
            if (reintento) setMsg($('lMsg'), 'bad', m); else { avisoLote(m, 'bad', r.status === 503); actualizaLote(); } return;
        }
        if (!reintento) { LT.job = new Map(); LT.err = new Map(); }
        else { [...LT.job].forEach(([id, j]) => { if (j.estado === 'error') LT.job.delete(id); }); LT.err = new Map(); }
        ((r.data && r.data.trabajos) || []).forEach((t) => LT.job.set(t.trabajo_id, { codigo: t.codigo, estado: 'pendiente', detalle: '', delante: null }));
        ((r.data && r.data.errores) || []).forEach((e) => LT.err.set(e.codigo, e.detail || 'No se pudo encolar'));
        setMsg($('lMsg'), ''); pasoLote('progreso'); pintaProgreso(); $('lResT').focus();
        paraSondeo(); LT.timer = setTimeout(sondeaLote, 1200);
    }
    $('lEnviar').addEventListener('click', () => { if (LT.sel.size && LT.sel.size <= MAX_LOTE) enviaLote([...LT.sel], false); });
    $('lReintentar').addEventListener('click', () => {
        const fall = [...LT.err.keys()].concat([...LT.job.values()].filter((j) => j.estado === 'error').map((j) => j.codigo));
        if (fall.length) enviaLote(fall, true);
    });
    $('lVolver').addEventListener('click', () => { paraSondeo(); pasoLote('elige'); avisoLote(); cargaLote(); $('lTit').focus(); });

    // ------------------------------------------------------------------ buscar por código (lector, celular, cámara)
    async function buscaCodigo(texto, opts = {}) {
        const t = String(texto || '').trim(); if (!t) return { ok: false };
        const r = await api(`/api/activos/buscar?codigo=${enc(t)}`);
        if (r.ok && r.data) {
            await abre(r.data.codigo, { datos: r.data, push: !desk.matches && !fichaAbierta(), scroll: true, foco: true });
            if (!opts.silencio) toast(`${r.data.etiqueta} · ${r.data.nombre}`, { kind: 'ok' });
            return { ok: true, activo: r.data, texto: `${r.data.etiqueta} · ${r.data.nombre}` };
        }
        const msg = r.status === 404 ? 'No existe' : (r.error || 'No se pudo buscar');
        toast(r.status === 404 ? `No existe un activo con el código «${t.length > 40 ? t.slice(0, 40) + '…' : t}»` : msg, { kind: 'warn' });
        return { ok: false, texto: msg };
    }
    // lector USB / teclado: el campo "Escanear etiqueta" (Enter busca) y, sin foco, ráfagas rápidas de teclas terminadas en Enter
    $('scan').addEventListener('keydown', async (e) => {
        if (e.key !== 'Enter') return; e.preventDefault();
        const v = e.target.value; e.target.value = ''; await buscaCodigo(v);
    });
    (function () {
        let buf = '', ult = 0;
        document.addEventListener('keydown', (e) => {
            const t = e.target; if (t && (t.matches && t.matches('input,textarea,select,[contenteditable]'))) return;
            if (e.ctrlKey || e.metaKey || e.altKey || document.querySelector('dialog[open]')) return;
            const ahora = Date.now(); if (ahora - ult > 80) buf = ''; ult = ahora;
            if (e.key === 'Enter') { if (buf.length >= 4) { e.preventDefault(); const v = buf; buf = ''; buscaCodigo(v); } buf = ''; }
            else if (e.key.length === 1) buf += e.key;
        });
    })();

    // ------------------------------------------------------------------ celular vinculado como escáner
    const RS_KEY = 'tqt.impresora.escaner';
    const RS = { token: null, id: null, moviles: 0, ultN: 0, ws: false };
    const guardaRS = () => { try { if (RS.token) localStorage.setItem(RS_KEY, JSON.stringify({ token: RS.token, id: RS.id })); else localStorage.removeItem(RS_KEY); } catch (e) { /* nada */ } };
    function pintaCel() {
        const b = $('bCel'), on = RS.token && RS.moviles;
        b.dataset.estado = on ? 'on' : (RS.token ? 'esp' : '');
        b.querySelector('.t').textContent = on ? 'Celular vinculado' : (RS.token ? 'Esperando celular' : 'Vincular celular');
        b.title = on ? 'Lo que escanee el celular se abre aquí' : 'Vincula tu celular como escáner con un QR';
        const est = $('celEst'); est.dataset.on = on ? '1' : '';
        est.textContent = on ? `Celular vinculado${RS.moviles > 1 ? ` (${RS.moviles})` : ''}. Lo que escanees se abre aquí.` : 'Esperando al celular…';
    }
    function olvidaRS() { RS.token = null; RS.id = null; RS.moviles = 0; RS.ultN = 0; guardaRS(); pintaCel(); }
    function conectaWs() {
        if (RS.ws) return; const ws = T.ws('monitor'); if (!ws) return; RS.ws = true;
        ws.on('ESCANER_VINCULADO', (d) => {
            if (!d || d.id !== RS.id) return; RS.moviles = d.moviles || RS.moviles + 1; pintaCel(); toast('Celular vinculado: ya puedes escanear', { kind: 'ok' });
            if ($('hojaCel').open) setTimeout(() => { if ($('hojaCel').open) $('hojaCel').close(); }, 1500);
        });
        ws.on('ESCANEO_REMOTO', (d) => { if (d && d.id === RS.id) recibeEscaneo(d); });
        ws.on('ESCANER_CERRADO', (d) => { if (d && d.id === RS.id) { olvidaRS(); toast('Se cerró la vinculación con el celular', { kind: 'warn' }); } });
        setInterval(async () => {   // respaldo por HTTP si el WebSocket se cayó
            if (!RS.token || document.hidden) return;
            const r = await api(`/api/escaner/${RS.token}/codigos?desde=${RS.ultN}`);
            if (!r.ok) { if (r.status === 404) olvidaRS(); return; }
            if ((r.data.moviles || 0) !== RS.moviles) { RS.moviles = r.data.moviles || 0; pintaCel(); }
            for (const c of r.data.items || []) await recibeEscaneo({ id: RS.id, n: c.n, codigo: c.codigo });
        }, 2500);
    }
    async function recibeEscaneo(d) {
        const codigo = String((d && d.codigo) || '').trim(); if (!codigo) return;
        if (d.n) { if (d.n <= RS.ultN) return; RS.ultN = d.n; }
        const res = await buscaCodigo(codigo, { silencio: false });
        api(`/api/escaner/${RS.token}/resultado`, { method: 'POST', body: { n: d.n || 0, ok: !!res.ok, texto: String(res.texto || '').slice(0, 300) } });
    }
    async function restauraRS() {
        let g = null; try { g = JSON.parse(localStorage.getItem(RS_KEY) || 'null'); } catch (e) { g = null; }
        if (!g || !g.token) { pintaCel(); return; }
        const r = await api(`/api/escaner/${g.token}`);
        if (r.ok && r.data) { Object.assign(RS, { token: g.token, id: r.data.id, moviles: r.data.moviles || 0, ultN: r.data.n || 0 }); pintaCel(); conectaWs(); }
        else if (r.status === 404 || r.status === 410) olvidaRS(); else pintaCel();
    }
    async function abreCel() {
        const dlg = $('hojaCel'); $('celErr').hidden = true;
        $('celLocal').hidden = !/^(localhost|127\.|\[::1\])/i.test(location.hostname);
        conectaWs();
        try { await cargaScript('/static/js/qrcode-generator.js?v=1316'); } catch (e) { $('celErr').hidden = false; $('celErr').textContent = 'No se pudo cargar el generador de QR. Recarga la página.'; }
        if (RS.token) { const v = await api(`/api/escaner/${RS.token}`); if (!v.ok && (v.status === 404 || v.status === 410)) olvidaRS(); }
        if (!RS.token) {
            const r = await api('/api/escaner/sesion', { method: 'POST', body: { seccion: 'impresora', titulo: 'Impresora · Activos' } });
            if (r.ok && r.data) { Object.assign(RS, { token: r.data.token, id: r.data.id, moviles: 0, ultN: 0 }); guardaRS(); }
            else { $('celErr').hidden = false; $('celErr').textContent = r.error || 'No se pudo crear la vinculación'; }
        }
        const qr = $('celQr'), url = RS.token ? `${location.origin}/escaner?s=${enc(RS.token)}` : '';
        qr.replaceChildren();
        if (url && window.qrcode) { const q = window.qrcode(0, 'M'); q.addData(url); q.make(); qr.innerHTML = q.createSvgTag({ cellSize: 6, margin: 2, scalable: true }); }
        $('celUrl').textContent = url; $('cDesv').hidden = !RS.token; pintaCel();
        if (!dlg.open) dlg.showModal();
    }
    $('bCel').addEventListener('click', abreCel);
    $('cX').addEventListener('click', () => $('hojaCel').close()); $('cListo').addEventListener('click', () => $('hojaCel').close());
    $('cDesv').addEventListener('click', async () => { const tk = RS.token; olvidaRS(); $('hojaCel').close(); if (tk) await api(`/api/escaner/${tk}`, { method: 'DELETE' }); toast('Celular desvinculado', { kind: 'ok' }); });

    // ------------------------------------------------------------------ cámara del teléfono (visor reutilizado)
    let visor = null;
    const dlgCam = $('hojaCam');
    async function abreCam() {
        $('camMsg').textContent = 'Iniciando cámara…'; dlgCam.showModal();
        try {
            for (const s of ['audio.js?v=1321', 'haptics.js?v=1321', 'jsQR.js?v=1321', 'scanner.js?v=1321', 'visor.js?v=1344']) await cargaScript('/static/js/' + s);
        } catch (e) { $('camMsg').textContent = 'No se pudo cargar el lector de cámara. Teclea el código abajo.'; return; }
        $('camMsg').textContent = 'Apunta al QR de la etiqueta del activo.';
        if (!visor) visor = T.mountVisor($('camHost'), { vinculo: true, onManual: () => $('camCod').focus(), onCode: async (texto) => {
            visor.lock();
            const r = await buscaCodigo(texto, { silencio: true });
            if (r.ok) { visor.flash('ok'); dlgCam.close(); } else { visor.flash('warn'); $('camMsg').textContent = 'No existe ese activo. Sigue apuntando o teclea el código.'; setTimeout(() => visor.unlock(), 1300); }
        } });
        else { visor.unlock(); visor.start(); }
    }
    dlgCam.addEventListener('close', () => { if (visor) visor.stop(); });
    $('bCam').addEventListener('click', abreCam); $('camX').addEventListener('click', () => dlgCam.close());
    $('camForm').addEventListener('submit', async (e) => { e.preventDefault(); const v = $('camCod').value; const r = await buscaCodigo(v, { silencio: true }); if (r.ok) { $('camCod').value = ''; dlgCam.close(); } });

    // ------------------------------------------------------------------ arranque
    document.addEventListener('visibilitychange', () => { if (!document.hidden && !hoja.open && S.items.length) cargaLista({ silencio: true }); });
    (async function () {
        pintaLista();
        const cod = new URLSearchParams(location.search).get('activo');
        const yo = cargaYo();
        if (cod) abre(cod, { noUrl: true });
        await Promise.all([yo, cargaCatalogos(), cargaLista()]);
        if (S.ro) pintaLista();
        restauraRS(); estadoImpresora();
    })();
})();
