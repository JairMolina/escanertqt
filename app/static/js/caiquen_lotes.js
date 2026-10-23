/* caiquen_lotes.js - Lotes (consola Caiquén): cada lote con sus placas por estado, fechas de la primera y la última, ver sus
 * placas en Inventario y renombrarlo (el consultor solo ve). En Caiquén el lote es un texto libre que se pone al recibir.
 * API: GET /api/caiquen/lotes · POST /api/caiquen/lotes/renombrar {de, a} */
(function () {
    'use strict';
    const T = window.TQT, P = window.CQ;
    const { h, icon, api } = T;
    const $ = (id) => document.getElementById(id);
    const n = (v) => Number(v || 0).toLocaleString('es-MX');
    const PARTES = [['programadas', 'Programadas', 'p'], ['recibidas', 'Sin programar', 'r'], ['falla', 'Falla', 'f'], ['baja', 'Baja', 'b']];
    let sec = null, cuerpo = null, viejo = false, seq = 0;

    function tarjeta(l) {
        const nombre = l.lote || 'Sin lote', total = l.placas || 0, ro = P.soloLectura();
        const idT = 'lt' + Math.random().toString(36).slice(2, 8), idRo = idT + 'ro';
        return h('li', { class: 'l-lote', 'aria-labelledby': idT },
            h('div', { class: 'l-cab' },
                h('h2', { id: idT, class: l.lote ? '' : 'l-sin' }, nombre),
                h('span', { class: 'l-total' }, h('b', { class: 'mono' }, n(total)), total === 1 ? ' placa' : ' placas')),
            h('div', { class: 'l-barra', role: 'img', 'aria-label': PARTES.map(([k, t]) => `${t}: ${n(l[k])}`).join(', ') },
                PARTES.filter(([k]) => l[k]).map(([k, , c]) => h('span', { class: 'l-seg ' + c, style: `flex-grow:${l[k]}` }))),
            h('ul', { class: 'l-partes' }, PARTES.map(([k, t, c]) => h('li', null, h('i', { class: 'l-sw ' + c, 'aria-hidden': 'true' }), `${t} `, h('b', { class: 'mono' }, n(l[k]))))),
            h('p', { class: 'l-fechas' }, l.primera ? `Del ${P.fecha(l.primera, false)} al ${P.fecha(l.ultima, false)}` : 'Sin fechas'),
            h('div', { class: 'l-acc' },
                l.lote ? h('button', { class: 'btn btn-sm', type: 'button', onclick: () => P.abrir('inventario', { lote: l.lote }) }, icon('list'), 'Ver en Inventario') : null,
                h('button', { class: 'btn btn-sm btn-ghost', type: 'button', disabled: ro, 'aria-describedby': ro ? idRo : null, onclick: () => renombrar(l) },
                    icon('edit'), l.lote ? 'Renombrar' : 'Asignar lote'),
                ro ? h('span', { class: 'l-ro', id: idRo }, 'Solo lectura con tu rol') : null));
    }

    async function cargar() {
        const k = ++seq;
        cuerpo.setAttribute('aria-busy', 'true');
        cuerpo.replaceChildren(h('div', { class: 'i-skel', 'aria-hidden': 'true' }, [1, 2, 3].map(() => h('span'))), h('p', { class: 'sr-only' }, 'Cargando lotes'));
        const r = await api('/api/caiquen/lotes');
        if (k !== seq) return;
        cuerpo.removeAttribute('aria-busy');
        if (!r.ok) { $('lCuenta').textContent = ''; cuerpo.replaceChildren(P.error((r.error || 'No se pudieron cargar los lotes') + '. Revisa la conexión con el servidor.', cargar)); return; }
        const items = ((r.data && r.data.items) || []).slice().sort((a, b) => (a.lote === '') - (b.lote === '') || String(b.ultima || '').localeCompare(String(a.ultima || '')));
        const conNombre = items.filter((l) => l.lote).length;
        $('lCuenta').textContent = conNombre === 1 ? '1 lote' : `${conNombre} lotes`;
        if (!items.length) {
            cuerpo.replaceChildren(h('div', { class: 'c-vacio' }, icon('layers'), h('b', null, 'Aún no hay lotes'),
                h('span', null, 'El lote se escribe en Recibir antes de escanear; las placas quedan agrupadas aquí.'),
                P.soloLectura() ? null : h('button', { class: 'btn', type: 'button', onclick: () => P.abrir('recibir') }, icon('recibir'), 'Ir a Recibir')));
            return;
        }
        cuerpo.replaceChildren(h('ul', { class: 'l-lista' }, items.map(tarjeta)));
    }

    function renombrar(l) {
        if (P.soloLectura()) return;
        const inp = h('input', { class: 'input', id: 'lNuevo', type: 'text', autocomplete: 'off', maxlength: '60', list: 'dlLotes', value: l.lote || '' });
        const err = h('p', { class: 'hoja-err', role: 'alert' });
        const de = l.lote || '';
        T.sheet({
            title: de ? `Renombrar «${de}»` : 'Asignar lote a las placas sin lote',
            body: [
                h('p', null, `Cambia el lote de ${l.placas === 1 ? 'la placa' : `las ${n(l.placas)} placas`}. Si escribes un lote que ya existe, se juntan.`),
                h('div', { class: 'field' }, h('label', { for: 'lNuevo' }, 'Nuevo nombre del lote'), inp),
                err,
            ],
            actions: [
                { label: 'Cancelar', kind: 'ghost', onClick: () => true },
                { label: 'Guardar nombre', kind: 'primary', icon: 'check', onClick: async () => {
                    const a = inp.value.trim();
                    if (a === de) { inp.setAttribute('aria-invalid', 'true'); err.textContent = 'Escribe un nombre distinto al actual.'; inp.focus(); return false; }
                    const r = await api('/api/caiquen/lotes/renombrar', { method: 'POST', body: { de, a } });
                    if (!r.ok) { err.textContent = (r.error || 'No se pudo renombrar el lote.') + ' Inténtalo otra vez.'; return false; }
                    const af = (r.data && r.data.afectadas) || 0;
                    T.toast(`${af === 1 ? '1 placa movida' : `${n(af)} placas movidas`} a ${a ? '«' + a + '»' : 'sin lote'}`, { kind: 'ok' });
                    P.cambio(); cargar();
                    return true;
                } },
            ],
        });
    }

    P.registrar('lotes', {
        montar(el) {
            sec = el; cuerpo = $('lCuerpo');
            document.addEventListener('caiquen:cambio', () => { if (sec.hidden) viejo = true; });
            P.yo.then(() => { if (!sec.hidden && cuerpo.querySelector('.l-lista')) cargar(); });
            cargar();
        },
        entrar() { if (viejo) { viejo = false; cargar(); } },
    });
})();
