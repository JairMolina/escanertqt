/* speedlocker_movimientos.js - Movimientos (consola SpeedLocker): eventos de las placas con filtros (acción, búsqueda, fechas) y
 * paginación. API: GET /api/speedlocker/eventos?accion=&q=&desde=&hasta=&limit=&offset= → {items, total} */
(function () {
    'use strict';
    const T = window.TQT, P = window.SL;
    const { h, icon, api } = T;
    const $ = (id) => document.getElementById(id);
    const POR_PAG = 50;
    const ACCIONES = [['RECIBIDA', 'Recibida'], ['PROGRAMADA', 'Programada'], ['EDITADA', 'Editada'], ['ELIMINADA', 'Eliminada'], ['MASA', 'Cambio en masa']];
    const TXT = Object.fromEntries(ACCIONES);
    const st = { f: { accion: '', q: '', desde: '', hasta: '' }, pag: 0, items: [], total: 0, seq: 0 };
    let sec = null, ui = {}, viejo = false;
    const n = (v) => Number(v || 0).toLocaleString('es-MX');
    const hayFiltros = () => Object.values(st.f).some((v) => v !== '');

    function campo(id, etq, el) { return h('div', { class: 'field' }, h('label', { for: id }, etq), el); }

    async function cargar() {
        const k = ++st.seq;
        ui.zona.setAttribute('aria-busy', 'true');
        ui.zona.replaceChildren(h('div', { class: 'i-skel', 'aria-hidden': 'true' }, [1, 2, 3, 4, 5].map(() => h('span'))), h('p', { class: 'sr-only' }, 'Cargando movimientos'));
        ui.pag.hidden = true;
        const q = new URLSearchParams({ limit: String(POR_PAG), offset: String(st.pag * POR_PAG) });
        Object.entries(st.f).forEach(([c, v]) => { if (v) q.set(c, v); });
        const r = await api('/api/speedlocker/eventos?' + q.toString(), { timeout: 15000 });
        if (k !== st.seq) return;
        ui.zona.removeAttribute('aria-busy');
        ui.limpiar.hidden = !hayFiltros();
        if (!r.ok) { $('mCuenta').textContent = ''; ui.zona.replaceChildren(P.error((r.error || 'No se pudieron cargar los movimientos') + '. Revisa la conexión con el servidor.', cargar)); return; }
        st.items = (r.data && r.data.items) || [];
        st.total = (r.data && typeof r.data.total === 'number') ? r.data.total : st.items.length;
        $('mCuenta').textContent = st.total === 1 ? '1 movimiento' : `${n(st.total)} movimientos`;
        if (!st.items.length) {
            ui.zona.replaceChildren(hayFiltros()
                ? h('div', { class: 'c-vacio' }, icon('search'), h('b', null, 'Ningún movimiento coincide'), h('span', null, 'Cambia las fechas o la búsqueda, o quita los filtros.'),
                    h('button', { class: 'btn', type: 'button', onclick: limpiar }, icon('x'), 'Quitar filtros'))
                : h('div', { class: 'c-vacio' }, icon('clock'), h('b', null, 'Todavía no hay movimientos'), h('span', null, 'Aquí queda cada placa recibida, programada, editada o eliminada.')));
            return;
        }
        ui.zona.replaceChildren(h('div', { class: 'i-tabla m-tabla' }, h('table', { class: 'grid' },
            h('caption', { class: 'sr-only' }, 'Movimientos de placas SpeedLocker'),
            h('thead', null, h('tr', null, ['Placa', 'Acción', 'Detalle', 'Operador', 'Fecha'].map((t) => h('th', { scope: 'col' }, t)))),
            h('tbody', null, st.items.map((e) => h('tr', null,
                h('th', { scope: 'row', class: 'i-c-nom' }, e.nombre && e.accion !== 'ELIMINADA'
                    ? h('button', { class: 'i-nom mono', type: 'button', title: 'Ver ficha e historial', onclick: () => P.abrir('consultar', e.nombre) }, e.nombre)
                    : h('span', { class: 'mono' }, e.nombre || '—')),
                h('td', { 'data-l': 'Acción', class: 'm-acc' }, TXT[e.accion] || e.accion || '—'),
                h('td', { 'data-l': 'Detalle', class: 'm-det' }, e.detalle || '—'),
                h('td', { 'data-l': 'Operador' }, e.operador || '—'),
                h('td', { 'data-l': 'Fecha', class: 'm-fecha' }, P.fecha(e.creado_en))))))));
        const desde = st.pag * POR_PAG + 1, hasta = desde + st.items.length - 1;
        ui.pagT.textContent = `${n(desde)}–${n(hasta)} de ${n(st.total)}`;
        ui.ant.disabled = st.pag === 0;
        ui.sig.disabled = hasta >= st.total;
        ui.pag.hidden = st.total <= POR_PAG;
    }
    function filtrar() { st.pag = 0; cargar(); }
    function limpiar() {
        st.f = { accion: '', q: '', desde: '', hasta: '' };
        ui.acc.value = ''; ui.q.value = ''; ui.desde.value = ''; ui.hasta.value = '';
        filtrar();
    }

    P.registrar('movimientos', {
        montar(el) {
            sec = el;
            ui.acc = h('select', { class: 'input', id: 'mAcc', onchange: () => { st.f.accion = ui.acc.value; filtrar(); } },
                h('option', { value: '' }, 'Todas'), ACCIONES.map(([v, t]) => h('option', { value: v }, t)));
            ui.q = h('input', { class: 'input', id: 'mQ', type: 'search', autocomplete: 'off', spellcheck: 'false', maxlength: '80', placeholder: 'Placa, detalle u operador' });
            ui.q.addEventListener('input', T.debounce(() => { st.f.q = ui.q.value.trim(); filtrar(); }, 300));
            const fechaCambio = () => {
                if (ui.desde.value && ui.hasta.value && ui.desde.value > ui.hasta.value) { ui.hasta.setAttribute('aria-invalid', 'true'); T.toast('La fecha final es anterior a la inicial', { kind: 'warn' }); return; }
                ui.hasta.removeAttribute('aria-invalid');
                st.f.desde = ui.desde.value; st.f.hasta = ui.hasta.value; filtrar();
            };
            ui.desde = h('input', { class: 'input', id: 'mDesde', type: 'date', onchange: fechaCambio });
            ui.hasta = h('input', { class: 'input', id: 'mHasta', type: 'date', onchange: fechaCambio });
            ui.limpiar = h('button', { class: 'btn btn-ghost', type: 'button', onclick: limpiar, hidden: true }, icon('x'), 'Quitar filtros');
            ui.zona = h('div', { class: 'i-zona', 'aria-live': 'polite' });
            ui.pagT = h('span', { class: 'm-pag-t mono', 'aria-live': 'polite' });
            ui.ant = h('button', { class: 'btn btn-sm', type: 'button', onclick: () => { if (st.pag > 0) { st.pag--; cargar(); sec.querySelector('h1').focus(); } } }, icon('back'), 'Anterior');
            ui.sig = h('button', { class: 'btn btn-sm', type: 'button', onclick: () => { st.pag++; cargar(); sec.querySelector('h1').focus(); } }, 'Siguiente', icon('chevron'));
            ui.pag = h('nav', { class: 'm-pag', 'aria-label': 'Páginas de movimientos', hidden: true }, ui.ant, ui.pagT, ui.sig);
            $('mCuerpo').replaceChildren(
                h('div', { class: 'i-filtros m-filtros', role: 'search', 'aria-label': 'Filtrar movimientos' },
                    h('div', { class: 'i-f-q' }, campo('mQ', 'Buscar', ui.q)),
                    campo('mAcc', 'Acción', ui.acc), campo('mDesde', 'Desde', ui.desde), campo('mHasta', 'Hasta', ui.hasta),
                    h('div', { class: 'i-f-limpiar' }, ui.limpiar)),
                ui.zona, ui.pag);
            document.addEventListener('speedlocker:cambio', () => { if (sec.hidden) viejo = true; });
            cargar();
        },
        entrar() { if (viejo) { viejo = false; cargar(); } },
    });
})();
