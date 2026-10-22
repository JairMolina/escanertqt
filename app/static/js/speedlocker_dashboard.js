/* speedlocker_dashboard.js - Dashboard (consola SpeedLocker): placas por estado, recibidas hoy, actividad de 14 días (recibidas y
 * programadas por día), distribución por hardware y por firmware, y últimos movimientos. Cada cifra lleva a Inventario
 * filtrado. API: GET /api/speedlocker/resumen (v1.4.28b: actividad, ultimos). */
(function () {
    'use strict';
    const T = window.TQT, P = window.SL;
    const { h, icon } = T;
    const $ = (id) => document.getElementById(id);
    const n = (v) => Number(v || 0).toLocaleString('es-MX');
    const ACCION = { RECIBIDA: 'Recibida', PROGRAMADA: 'Programada', EDITADA: 'Editada', ELIMINADA: 'Eliminada', MASA: 'Cambio en masa' };
    let sec = null, cuerpo = null, viejo = false;

    function diaCorto(ymd) {
        const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(ymd || ''); if (!m) return ymd || '';
        return `${+m[3]} ${T.MESES[+m[2] - 1].slice(0, 3).toLowerCase()}`;
    }

    // ------------------------------------------------------------------ piezas
    function tile(etq, valor, k, filtro, ayuda) {
        const cont = [h('span', { class: 'd-t-n mono' }, n(valor)), h('span', { class: 'd-t-l' }, etq), ayuda ? h('span', { class: 'd-t-a' }, ayuda) : null];
        return filtro
            ? h('button', { class: 'd-tile', type: 'button', dataset: { k: k || '' }, 'aria-label': `${etq}: ${n(valor)}. Ver en Inventario`, onclick: () => P.abrir('inventario', filtro) }, cont)
            : h('div', { class: 'd-tile', dataset: { k: k || '' } }, cont);
    }

    /** Barras agrupadas por día (recibidas en naranja, programadas en gris), con leyenda y tabla equivalente. */
    function actividad(dias) {
        const max = Math.max(1, ...dias.map((d) => Math.max(d.recibidas || 0, d.programadas || 0)));
        const totR = dias.reduce((a, d) => a + (d.recibidas || 0), 0), totP = dias.reduce((a, d) => a + (d.programadas || 0), 0);
        const barra = (v, cls) => h('span', { class: 'd-b ' + cls, style: `height:${v ? Math.max(4, Math.round((v / max) * 100)) : 0}%` });
        return h('section', { class: 'd-panel d-act', 'aria-labelledby': 'dActT' },
            h('div', { class: 'd-panel-cab' },
                h('h2', { id: 'dActT' }, 'Actividad de 14 días'),
                h('ul', { class: 'd-leyenda' },
                    h('li', null, h('i', { class: 'd-sw r' }), `Recibidas (${n(totR)})`),
                    h('li', null, h('i', { class: 'd-sw p' }), `Programadas (${n(totP)})`))),
            h('ol', { class: 'd-barras', 'aria-label': 'Placas por día' }, dias.map((d) => {
                const txt = `${diaCorto(d.dia)}: ${n(d.recibidas)} recibidas, ${n(d.programadas)} programadas`;
                return h('li', { tabindex: '0', title: txt, 'aria-label': txt },
                    h('span', { class: 'd-col', 'aria-hidden': 'true' }, barra(d.recibidas, 'r'), barra(d.programadas, 'p')),
                    h('span', { class: 'd-dia', 'aria-hidden': 'true' }, diaCorto(d.dia).split(' ')[0]));
            })),
            h('details', { class: 'd-tabla' }, h('summary', null, 'Ver como tabla'),
                h('div', { class: 'i-tabla' }, h('table', { class: 'grid' },
                    h('thead', null, h('tr', null, h('th', { scope: 'col' }, 'Día'), h('th', { scope: 'col' }, 'Recibidas'), h('th', { scope: 'col' }, 'Programadas'))),
                    h('tbody', null, dias.map((d) => h('tr', null, h('th', { scope: 'row' }, diaCorto(d.dia)), h('td', { class: 'mono' }, n(d.recibidas)), h('td', { class: 'mono' }, n(d.programadas)))))))));
    }

    /** Barras horizontales de una sola serie: etiqueta, barra y valor (cada fila filtra Inventario). */
    function distribucion(id, titulo, filas, vacio) {
        const max = Math.max(1, ...filas.map((f) => f.n));
        return h('section', { class: 'd-panel', 'aria-labelledby': id },
            h('h2', { id }, titulo),
            filas.length
                ? h('ul', { class: 'd-dist' }, filas.map((f) => h('li', null,
                    h('button', { class: 'd-dist-b', type: 'button', 'aria-label': `${f.etq}: ${n(f.n)} placas. Ver en Inventario`, onclick: () => P.abrir('inventario', f.filtro) },
                        h('span', { class: 'd-dist-l' + (f.mono ? ' mono' : '') }, f.etq),
                        h('span', { class: 'd-dist-v mono' }, n(f.n)),
                        h('span', { class: 'd-dist-pista', 'aria-hidden': 'true' }, h('span', { class: 'd-dist-bar', style: `width:${Math.max(2, Math.round((f.n / max) * 100))}%` }))))))
                : h('p', { class: 'hist-vacio' }, vacio));
    }

    function ultimos(evs) {
        return h('section', { class: 'd-panel d-ult', 'aria-labelledby': 'dUltT' },
            h('div', { class: 'd-panel-cab' }, h('h2', { id: 'dUltT' }, 'Últimos movimientos'),
                h('a', { class: 'btn btn-sm btn-ghost', href: '#movimientos' }, 'Ver todos')),
            evs.length
                ? h('ol', { class: 'd-feed' }, evs.map((e) => h('li', null,
                    h('span', { class: 'd-feed-a' }, ACCION[e.accion] || e.accion || 'Evento'),
                    e.nombre && e.accion !== 'ELIMINADA'
                        ? h('button', { class: 'i-nom mono', type: 'button', onclick: () => P.abrir('consultar', e.nombre) }, e.nombre)
                        : h('span', { class: 'mono' }, e.nombre || ''),
                    e.detalle ? h('span', { class: 'd-feed-d' }, e.detalle) : null,
                    h('span', { class: 'd-feed-m' }, P.fecha(e.creado_en) + (e.operador ? ' · ' + e.operador : '')))))
                : h('p', { class: 'hist-vacio' }, 'Todavía no hay movimientos.'));
    }

    // ------------------------------------------------------------------ carga
    async function cargar() {
        cuerpo.setAttribute('aria-busy', 'true');
        if (!cuerpo.firstChild || cuerpo.querySelector('.banner')) cuerpo.replaceChildren(h('div', { class: 'i-skel d-skel', 'aria-hidden': 'true' }, [1, 2, 3, 4].map(() => h('span'))), h('p', { class: 'sr-only' }, 'Cargando el dashboard'));
        const d = await P.resumen(true);
        cuerpo.removeAttribute('aria-busy');
        if (!d) { $('dAct').textContent = ''; cuerpo.replaceChildren(P.error('No se pudo cargar el resumen. Revisa la conexión con el servidor.', cargar)); return; }
        $('dAct').textContent = 'Actualizado ' + new Date().toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit' });
        if (!d.total) {
            cuerpo.replaceChildren(h('div', { class: 'c-vacio' }, icon('box'), h('b', null, 'Aún no hay placas SpeedLocker'),
                h('span', null, 'El dashboard se llena cuando se reciben placas por QR o se dan de alta a mano.'),
                P.soloLectura() ? null : h('button', { class: 'btn btn-primary', type: 'button', onclick: () => P.abrir('recibir') }, icon('recibir'), 'Ir a Recibir')));
            return;
        }
        const pe = d.por_estado || {};
        const fws = (d.firmwares || []).map((x) => ({ etq: x.firmware || 'Sin firmware', n: x.n, mono: !!x.firmware, filtro: { firmware: x.firmware || '__sin' } })).sort((a, b) => b.n - a.n);
        const vers = (d.versiones || []).map((x) => ({ etq: P.hw(x.version), n: x.n, mono: true, filtro: { version: String(x.version) } }));
        cuerpo.replaceChildren(
            h('div', { class: 'd-tiles' },
                tile('Placas en total', d.total, 'total', {}),
                tile('Recibidas hoy', d.hoy, 'hoy', null, 'desde las 00:00'),
                tile('Sin programar', pe.RECIBIDA, 'RECIBIDA', { estado: 'RECIBIDA' }),
                tile('Programadas', pe.PROGRAMADA, 'PROGRAMADA', { estado: 'PROGRAMADA' }),
                tile('Con falla', pe.FALLA, 'FALLA', { estado: 'FALLA' }),
                tile('De baja', pe.BAJA, 'BAJA', { estado: 'BAJA' })),
            h('div', { class: 'd-rejilla' },
                Array.isArray(d.actividad) && d.actividad.length ? actividad(d.actividad) : h('section', { class: 'd-panel d-act' }, h('h2', null, 'Actividad de 14 días'), h('p', { class: 'hist-vacio' }, 'El servidor todavía no envía la actividad diaria.')),
                ultimos(d.ultimos || []),
                distribucion('dHwT', 'Por hardware', vers, 'Sin datos de hardware.'),
                distribucion('dFwT', 'Por firmware', fws, 'Sin datos de firmware.')));
    }

    P.registrar('dashboard', {
        montar(el) {
            sec = el; cuerpo = $('dCuerpo');
            $('bDRef').addEventListener('click', cargar);
            document.addEventListener('speedlocker:cambio', () => { viejo = true; });
        },
        entrar() { viejo = false; cargar(); },
    });
    // si algo cambia mientras se ve el dashboard, se refresca sin esperar a salir
    document.addEventListener('speedlocker:cambio', () => { if (sec && !sec.hidden && viejo) { viejo = false; setTimeout(cargar, 300); } });
})();
