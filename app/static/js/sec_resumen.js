/**
 * sec_resumen.js - Resumen: KPIs de tarjetas y de PCB, avance por tipo (recibidas -> asignadas -> con MAC),
 * estado de tarjetas y placas (partes de un todo), tarjetas que necesitan atención y actividad en vivo.
 */
(function () {
    'use strict';
    const E = window.TQTEscritorio;
    E.registrar({
        id: 'resumen', titulo: 'Resumen', icono: 'dash', grupo: 'operacion', orden: 10,
        montar(host, ctx) {
            const { T, h, icon, util } = ctx;
            let tars = null, pcbs = null, cargandoAhora = false, otra = false, error = '';
            const feedUl = h('ol', { class: 'esc-feed', 'aria-label': 'Actividad reciente', 'aria-live': 'polite' });
            const n = (v) => Number(v).toLocaleString('es-MX');
            const pct = (a, b) => (b ? Math.round((a / b) * 100) : 0);

            function kpi(label, valor, kind, sub) {
                return h('div', { class: 'esc-kpi', dataset: { k: kind || '' } }, h('span', { class: 'l' }, label), h('span', { class: 'v' }, n(valor)), sub ? h('span', { class: 's' }, sub) : null);
            }
            function bloque(titulo, ...kids) {
                return h('section', { class: 'esc-blk' }, h('div', { class: 'esc-h' }, h('h2', null, titulo)), ...kids);
            }
            function fila(etq, valor, total, color, extra) {
                const w = total ? Math.max(valor ? 2 : 0, (valor / total) * 100) : 0;
                return h('li', null, h('span', { class: 'n' }, etq),
                    h('div', { class: 'esc-pista', role: 'img', 'aria-label': `${etq}: ${valor} de ${total}` }, h('i', { style: `width:${w.toFixed(1)}%;--c:${color}` })),
                    h('span', { class: 'v' }, n(valor), ' ', h('small', null, `${pct(valor, total)}%`)), extra || null);
            }
            function avanceTipo(tp, lista) {
                const all = lista.filter((p) => p.tipo === tp && p.estado_ciclo !== 'BAJA');
                const rec = all.length, asg = all.filter((p) => p.estado_ciclo === 'ASIGNADA').length;
                const mac = tp === 'R3' ? null : all.filter((p) => p.mac).length;
                const base = `var(--${tp.toLowerCase()})`;
                const mezcla = (p) => `color-mix(in srgb, ${base} ${p}%, var(--surface-2))`;
                const ul = h('ul', { class: 'esc-av' },
                    fila('Recibidas', rec, rec, mezcla(38)), fila('Asignadas', asg, rec, mezcla(68)),
                    tp === 'R3' ? h('li', null, h('span', { class: 'nota' }, 'La R3 no lleva MAC ni firmware.')) : fila('Con MAC', mac, rec, mezcla(100)));
                return { rec, asg, mac, card: h('article', { class: 'esc-card', 'aria-label': `Avance de ${tp}` }, h('header', null, T.tipoChip(tp, { lg: true }), h('h3', null, `${rec} placa${rec === 1 ? '' : 's'}`)), ul) };
            }
            function partes(titulo, items, total, vacio) {
                const vis = items.filter((i) => i.v > 0);
                return h('article', { class: 'esc-card' }, h('header', null, h('h3', null, titulo), h('div', { class: 'grow' }), h('span', { class: 'muted mono' }, n(total))),
                    total ? h('div', { class: 'esc-seg-bar', role: 'img', 'aria-label': `${titulo}: ${items.map((i) => `${i.v} ${i.l.toLowerCase()}`).join(', ')}` },
                        vis.map((i) => h('i', { style: `flex:${i.v} 1 0;--c:var(--${i.c})`, title: `${i.l}: ${i.v}` }))) : h('span', { class: 'muted' }, vacio),
                    h('ul', { class: 'esc-leyenda' }, items.map((i) => h('li', null, h('i', { style: `--c:var(--${i.c})` }), h('b', null, n(i.v)), h('span', null, i.l)))));
            }
            function atencion() {
                const att = tars.filter((t) => T.estadoTarjeta(t).key !== 'completa');
                const sueltas = (pcbs || []).filter((p) => p.estado_ciclo === 'DISPONIBLE').length;
                const porEmparejar = sueltas ? h('a', { class: 'btn btn-primary', href: '#/tarjetas' }, `${sueltas} placa${sueltas === 1 ? '' : 's'} suelta${sueltas === 1 ? '' : 's'}: ir a emparejar`) : null;
                if (!tars.length) {
                    const e = T.empty('card', 'Todavía no hay tarjetas en este lote', sueltas ? 'Las placas recibidas siguen sueltas: empareja R1 + R2 (+ R3) para crear las tarjetas.' : 'Recibe y confirma placas con el celular; después se emparejan en tarjetas.');
                    if (porEmparejar) e.append(porEmparejar);
                    return e;
                }
                if (!att.length) {
                    const e = T.empty('check', 'Tarjetas al día', `Las ${tars.length} tarjetas del lote tienen R1, R2 y R3 y sus MAC capturadas.`);
                    if (porEmparejar) e.append(porEmparejar);
                    return e;
                }
                const cols = [
                    { id: 'n', titulo: 'Tarjeta', cel: (t) => h('span', { class: 'mono' }, t.id_tarjeta_num), valor: (t) => t.id_tarjeta_num },
                    { id: 'e', titulo: 'Estado', cel: (t) => T.tarjetaBadge(t), valor: (t) => T.estadoTarjeta(t).label },
                    { id: 'r1', titulo: 'R1', cel: (t) => util.placaCelda(t.r1, 'R1'), sortable: false },
                    { id: 'r2', titulo: 'R2', cel: (t) => util.placaCelda(t.r2, 'R2'), sortable: false },
                ];
                const wrap = h('div');
                util.pintarTabla(wrap, { cols, rows: att.slice(0, 8), key: (t) => t.id, onOpen: (t) => ctx.ir('tarjetas', { id: t.id }), label: (t) => `Tarjeta ${t.id_tarjeta_num}, ${T.estadoTarjeta(t).label}`, caption: 'Tarjetas que necesitan atención' });
                return h('div', { class: 'stack' }, wrap, att.length > 8 ? h('a', { class: 'btn', href: '#/tarjetas?estado=incompleta' }, `Ver las ${att.length} tarjetas con pendientes`) : null);
            }
            function pintarFeed(lista) {
                feedUl.replaceChildren();
                if (!lista.length) { feedUl.append(h('li', null, h('span'), h('span'), h('span', { class: 'muted' }, 'Sin actividad todavía'))); return; }
                const ic = { ok: 'check', warn: 'alert', bad: 'alert', info: 'info' };
                lista.slice(0, 40).forEach((f) => feedUl.append(h('li', { dataset: { k: f.kind } }, h('time', null, f.t), icon(ic[f.kind] || 'info'), h('span', null, f.text))));
            }

            function pintar() {
                host.replaceChildren();
                if (error && !tars) { host.append(util.errorBox(error, () => cargar(true))); return; }
                if (!tars || !pcbs) { host.append(util.cargando('Cargando el resumen…')); return; }
                const lote = ctx.lote();
                const g = (k) => tars.filter((t) => T.estadoTarjeta(t).key === k).length;
                const c = (s) => pcbs.filter((p) => p.estado_ciclo === s).length;
                const tot = tars.length, comp = g('completa'), inc = g('incompleta'), sm = g('sin_mac');
                // Conteos independientes (una tarjeta puede estar a la vez sin R3 y con MAC al día)
                const conMacAl = tars.filter((t) => t.r1 && t.r2 && !(t.sin_mac || []).length).length;
                const sinMacAl = tars.filter((t) => (t.sin_mac || []).length).length;
                const sinPlaca = tars.filter((t) => !t.r1 || !t.r2 || !t.r3).length;
                const sinMac = pcbs.filter((p) => p.tipo !== 'R3' && !p.mac && ['RECIBIDA', 'ASIGNADA', 'DISPONIBLE'].includes(p.estado_ciclo)).length;   // misma regla que ?sin_mac=1 del servidor
                const av = ['R1', 'R2', 'R3'].map((tp) => avanceTipo(tp, pcbs));
                const tabla = h('details', { class: 'esc-tabvista' }, h('summary', null, 'Ver el avance como tabla'),
                    h('table', null, h('caption', { class: 'sr-only' }, 'Avance por tipo de placa'), h('thead', null, h('tr', null, ['Tipo', 'Recibidas', 'Asignadas', 'Con MAC'].map((x) => h('th', { scope: 'col' }, x)))),
                        h('tbody', null, ['R1', 'R2', 'R3'].map((tp, i) => h('tr', null, h('th', { scope: 'row' }, tp), h('td', null, av[i].rec), h('td', null, av[i].asg), h('td', null, av[i].mac === null ? 'no aplica' : av[i].mac))))));
                host.append(
                    bloque(`Tarjetas del lote ${T.loteNombre(lote)}`, h('div', { class: 'esc-kpis', dataset: { n: 5 } },
                        kpi('Tarjetas', tot, '', 'R1 + R2 + R3 por número'), kpi('Completas', comp, 'ok', `${pct(comp, tot)}% del lote`),
                        kpi('Con MAC', conMacAl, 'ok', 'R1 y R2 con MAC capturada'), kpi('Sin MAC', sinMacAl, 'info', 'falta la MAC de R1 o R2'),
                        kpi('Falta placa', sinPlaca, 'warn', 'sin R1, R2 o R3'))),
                    bloque('Inventario de PCB', h('div', { class: 'esc-kpis', dataset: { n: 6 } },
                        kpi('En inventario', pcbs.length, '', 'todas las recibidas'), kpi('Sin confirmar', c('RECIBIDA'), 'warn', 'recepción abierta'), kpi('Sueltas', c('DISPONIBLE'), 'info', 'listas para emparejar'),
                        kpi('Asignadas', c('ASIGNADA'), 'ok', 'montadas en tarjetas'), kpi('En falla', c('FALLA'), 'bad', 'apartadas'), kpi('Sin MAC (R1/R2)', sinMac, 'warn', 'por capturar'))),
                    bloque('Avance por tipo', h('div', { class: 'esc-3' }, av.map((a) => a.card)), tabla),
                    h('div', { class: 'esc-2' },
                        partes('Estado de las tarjetas', [{ l: 'Completas', v: comp, c: 'ok' }, { l: 'Sin MAC', v: sm, c: 'info' }, { l: 'Falta placa', v: inc, c: 'warn' }], tot, 'Todavía no hay tarjetas en este lote.'),
                        partes('Estado de las placas', [{ l: 'Asignadas', v: c('ASIGNADA'), c: 'ok' }, { l: 'Sueltas', v: c('DISPONIBLE'), c: 'info' }, { l: 'Sin confirmar', v: c('RECIBIDA'), c: 'warn' }, { l: 'En falla', v: c('FALLA'), c: 'bad' }], pcbs.length, 'Todavía no hay placas recibidas.')),
                    h('div', { class: 'esc-2 esc-2-lado' },
                        bloque('Tarjetas que necesitan atención', atencion()),
                        bloque('Actividad en vivo', h('div', { class: 'esc-card' }, feedUl))));
                pintarFeed(ctx.feed());
            }

            async function cargar(mostrar) {
                if (cargandoAhora) { otra = true; return; }
                cargandoAhora = true;
                if (mostrar) { error = ''; tars = null; pintar(); }
                try { [tars, pcbs] = await Promise.all([ctx.tarjetas(), ctx.pcbs()]); error = ''; }
                catch (e) { error = e.message; }
                cargandoAhora = false;
                pintar();
                if (otra) { otra = false; cargar(false); }
            }
            ctx.alActividad(pintarFeed);
            cargar(true);
            return { actualizar() { cargar(false); }, desmontar() { /* los listeners los limpia el armazón */ } };
        },
    });
})();
