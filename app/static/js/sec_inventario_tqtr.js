/**
 * sec_inventario_tqtr.js - Inventario TQTR (réplica del Excel INVENTARIO_TQTR_26_v.xlsx): materiales, consumibles y producto final.
 * Pestañas: Dashboard (existencias, ensambles posibles, alertas, costos), Registro (movimientos), Componentes (BOM), Costos (Costos_Produccion_TQTR.xlsx) y Configuración.
 * API: GET /api/inventario-tqtr/{dashboard|registros|componentes|configuracion|export} · POST/PATCH/DELETE registros, componentes, configuracion, productos
 */
(function () {
    'use strict';
    const E = window.TQTEscritorio;
    const B = '/api/inventario-tqtr';
    const ESTADOS_TARJETA = { activa: ['Completa', 'ok', 'check'], disuelta: ['Disuelta', 'warn', 'unlink'], borrada: ['Borrada', 'bad', 'trash'], pendiente: ['Sin completar', '', 'clock'], anterior: ['Antes del inicio', '', 'clock'] };
    const ESTADOS_MAT = { activo: ['Consumido', 'ok'], disuelta: ['Consumo de tarjeta disuelta', 'warn'], devuelto: ['Devuelto', ''] };
    const mxnF = (v) => (v === null || v === undefined ? '—' : Number(v).toLocaleString('es-MX', { style: 'currency', currency: 'MXN' }));
    const numF = (v) => (v === null || v === undefined || v === '' ? '—' : Number(v).toLocaleString('es-MX', { maximumFractionDigits: 3 }));

    /** Ficha de materiales de una tarjeta (estándar vs real, costo y merma). La usan la pestaña Consumo y el panel de Tarjetas. */
    function fichaMateriales(tarjetaId, ctx, opciones) {
        const { T, api, h, toast } = ctx; const o = opciones || {};
        const cont = h('section', { class: 'esc-card itq-ficha', 'aria-label': 'Materiales de la tarjeta' }, h('div', { class: 'esc-h' }, h('h2', null, 'Materiales')), h('p', { class: 'muted' }, 'Cargando la ficha de materiales…'));
        async function cargar() {
            const r = await api(`${B}/tarjetas/${tarjetaId}/materiales`);
            if (!r.ok) { cont.replaceChildren(h('div', { class: 'esc-h' }, h('h2', null, 'Materiales')), h('p', { class: 'muted' }, r.status === 404 ? 'Sin ficha de materiales.' : r.error)); return; }
            pintar(r.data);
        }
        function pintar(f) {
            const et = ESTADOS_TARJETA[f.tarjeta.estado] || ESTADOS_TARJETA.pendiente;
            const cab = h('div', { class: 'esc-h' }, h('h2', null, 'Materiales'), T.badge(et[0], et[1], et[2]));
            if (!f.items.length) {
                cont.replaceChildren(cab, h('p', { class: 'muted' }, f.tarjeta.estado === 'anterior'
                    ? `Se completó antes del ${f.consumo_desde}, fecha desde la que se descuenta material.` : 'Los materiales de R1 + R2 + R3 se descuentan del inventario cuando la tarjeta queda completa; la caja y el actuador, al asignarle gabinete.'));
                return;
            }
            const inputs = new Map();
            const filas = f.items.map((i) => {
                const em = ESTADOS_MAT[i.estado] || ESTADOS_MAT.activo;
                const editable = f.editable && i.estado === 'activo';
                const inp = editable ? h('input', { class: 'input mono itq-real', type: 'number', min: '0', step: 'any', inputmode: 'decimal', value: i.cantidad_real, 'aria-label': `Cantidad real de ${i.descripcion}` }) : null;
                if (inp) inputs.set(i.id, inp);
                return h('tr', { dataset: { estado: i.estado } },
                    h('td', null, h('div', { class: 'itq-mat' }, i.descripcion), i.nota ? h('span', { class: 'muted' }, i.nota) : null),
                    h('td', { class: 'c-3' }, i.origen === 'placas' ? 'Placas' : 'Gabinete'),
                    h('td', { class: 'num mono' }, numF(i.cantidad_estandar), ' ', h('span', { class: 'muted' }, i.unidad || '')),
                    h('td', { class: 'num' }, inp || h('span', { class: 'mono' }, numF(i.cantidad_real))),
                    h('td', { class: 'num mono', dataset: { k: i.merma > 0 ? 'bad' : i.merma < 0 ? 'ok' : '' } }, i.merma ? (i.merma > 0 ? '+' : '') + numF(i.merma) : '—'),
                    h('td', { class: 'num mono' }, mxnF(i.costo_real)),
                    h('td', { class: 'c-2' }, T.badge(em[0], em[1])));
            });
            const t = f.totales;
            const err = h('div', { class: 'hint err', role: 'alert' });
            const guardar = f.editable ? h('button', { class: 'btn btn-primary', type: 'button', onclick: async () => {
                err.textContent = '';
                const items = []; for (const [id, inp] of inputs) { const v = inp.value.trim(); if (v === '' || Number(v) < 0) { err.textContent = 'Las cantidades reales deben ser números iguales o mayores que cero.'; inp.focus(); return; } items.push({ id, cantidad_real: Number(v) }); }
                const r = await api(`${B}/tarjetas/${tarjetaId}/materiales`, { method: 'PATCH', body: { items } });
                if (!r.ok) { err.textContent = r.error; return; }
                toast('Cantidades reales guardadas', { kind: 'ok' }); pintar(r.data); if (o.alGuardar) o.alGuardar(r.data);
            } }, 'Guardar cantidades reales') : null;
            cont.replaceChildren(cab,
                h('div', { class: 'esc-tw' }, h('table', { class: 'esc-t itq-t' }, h('caption', { class: 'sr-only' }, `Materiales de la tarjeta ${f.tarjeta.id_tarjeta_num}`),
                    h('thead', null, h('tr', null, ['Material', 'Origen', 'Estándar', 'Real', 'Merma', 'Costo real', 'Estado'].map((x, i) => h('th', { scope: 'col', class: [null, 'c-3', 'num', 'num', 'num', 'num', 'c-2'][i] }, x)))),
                    h('tbody', null, filas))),
                h('dl', { class: 'itq-tot' }, h('div', null, h('dt', null, 'Costo estándar'), h('dd', { class: 'mono' }, mxnF(t.costo_estandar))),
                    h('div', null, h('dt', null, 'Costo real'), h('dd', { class: 'mono' }, mxnF(t.costo_real))),
                    h('div', null, h('dt', null, 'Merma'), h('dd', { class: 'mono', dataset: { k: t.merma_costo > 0 ? 'bad' : t.merma_costo < 0 ? 'ok' : '' } }, mxnF(t.merma_costo)))),
                f.editable ? h('p', { class: 'hint' }, 'Cambia la cantidad real si se usó más o menos material (merma); la existencia y el costo real se ajustan.') : null,
                err, guardar ? h('div', { class: 'row' }, guardar) : null);
        }
        cargar();
        return cont;
    }
    window.TQTMateriales = { bloque: (tarjetaId, ctx, opciones) => fichaMateriales(tarjetaId, ctx, opciones) };

    /** Contador de materiales a comprar junto al enlace de la sección en la barra lateral (sin tocar escritorio.js). */
    function badgeLateral(n) {
        const a = document.querySelector('a.esc-ni[data-id="inventario_tqtr"]');
        if (!a) return;
        let b = a.querySelector('.itq-nav-badge');
        if (!n) { if (b) b.remove(); return; }
        if (!b) { b = document.createElement('span'); b.className = 'itq-nav-badge'; a.append(b); }
        b.textContent = String(n); b.title = `${n} material${n === 1 ? '' : 'es'} en stock mínimo`;
        b.setAttribute('aria-label', b.title);
    }
    async function revisarBadge() {
        try { const r = await fetch(`${B}/stock-minimo`, { headers: { Accept: 'application/json' } }); if (r.ok) badgeLateral((await r.json()).a_comprar.length); } catch (e) { /* sin conexión: sin contador */ }
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => setTimeout(revisarBadge, 1500)); else setTimeout(revisarBadge, 1500);
    setInterval(revisarBadge, 10 * 60 * 1000);
    const PESTANAS = [['dashboard', 'Dashboard'], ['registro', 'Registro'], ['componentes', 'Componentes'], ['costos', 'Costos'], ['consumo', 'Consumo'], ['stock', 'Stock mínimo'], ['configuracion', 'Configuración']];
    const TIPOS = [['categoria', 'Categorías'], ['movimiento', 'Tipos de movimiento'], ['condicion', 'Condición'], ['unidad', 'Unidades']];
    const ESTADOS = { ok: ['Con existencia', 'ok', 'check'], bajo: ['Bajo mínimo', 'warn', 'alert'], insuficiente: ['No alcanza para 1', 'warn', 'alert'], agotado: ['Agotado', 'bad', 'x'] };

    E.registrar({
        id: 'inventario_tqtr', titulo: 'Inventario TQTR', icono: 'tag', grupo: 'gestion', orden: 55,
        montar(host, ctx) {
            const { T, api, h, icon, toast, sheet, util } = ctx;
            const P = ctx.params ? ctx.params() : new URLSearchParams();
            const st = {
                tab: PESTANAS.some(([k]) => k === P.get('tab')) ? P.get('tab') : 'dashboard',
                dash: null, conf: null, comps: null, regs: null, costos: null, cons: null, stock: null, error: '',
                f: { q: '', movimiento: '', categoria: '', desde: '', hasta: '' }, sort: { id: 'fecha_entrada', dir: 'desc' }, limit: 200, csort: { id: 'orden', dir: 'asc' },
            };
            const fmt = (v) => (v === null || v === undefined || v === '' ? '—' : typeof v === 'number' ? v.toLocaleString('es-MX', { maximumFractionDigits: 2 }) : String(v));
            const mxn = (v) => (v === null || v === undefined ? '—' : Number(v).toLocaleString('es-MX', { style: 'currency', currency: 'MXN' }));
            const muted = (t) => h('span', { class: 'muted' }, t);
            const estadoBadge = (e) => { const x = ESTADOS[e] || ESTADOS.ok; return T.badge(x[0], x[1], x[2]); };
            const grupoNombre = (g) => (st.dash && st.dash.grupos && st.dash.grupos[g]) || g || '—';

            // ---------------------------------------------------------------- armazón: pestañas + acciones
            const panel = h('div', { class: 'itq-panel', role: 'tabpanel', id: 'itqPanel', tabindex: '-1' });
            const tabs = PESTANAS.map(([k, l]) => h('button', { type: 'button', role: 'tab', id: `itqTab-${k}`, 'aria-controls': 'itqPanel', 'aria-selected': String(st.tab === k), tabindex: st.tab === k ? '0' : '-1', onclick: () => irTab(k) }, l));
            const tablist = h('div', { class: 'itq-tabs', role: 'tablist', 'aria-label': 'Vistas del inventario TQTR' }, tabs);
            tablist.addEventListener('keydown', (e) => {
                const i = PESTANAS.findIndex(([k]) => k === st.tab); let j = -1;
                if (e.key === 'ArrowRight') j = (i + 1) % PESTANAS.length; else if (e.key === 'ArrowLeft') j = (i - 1 + PESTANAS.length) % PESTANAS.length;
                if (j >= 0) { e.preventDefault(); irTab(PESTANAS[j][0]); tabs[j].focus(); }
            });
            const bExport = h('button', { class: 'btn', type: 'button', onclick: exportar }, icon('download'), h('span', null, 'Descargar .xlsx'));
            const bNuevo = h('button', { class: 'btn btn-primary', type: 'button', onclick: () => editarMov(null) }, icon('plus'), 'Nuevo movimiento');
            host.append(h('div', { class: 'itq stack' }, h('div', { class: 'esc-bar itq-top' }, tablist, h('div', { class: 'grow' }), bExport, T.botonCorreo(() => ({ tipo: 'inventario_tqtr', titulo: 'Inventario TQTR' })), bNuevo), panel));

            function irTab(k) {
                st.tab = k;
                tabs.forEach((b, i) => { const on = PESTANAS[i][0] === k; b.setAttribute('aria-selected', String(on)); b.tabIndex = on ? 0 : -1; });
                panel.setAttribute('aria-labelledby', `itqTab-${k}`);
                pintar(); cargar();
            }

            async function obtener(url) { const r = await api(url); if (!r.ok) throw new Error(r.error); return r.data; }
            async function cargar() {
                try {
                    if (!st.conf) st.conf = await obtener(`${B}/configuracion`);
                    if (st.tab === 'dashboard') { st.dash = await obtener(`${B}/dashboard`); contarStock(st.dash.stock ? st.dash.stock.a_comprar : 0); }
                    else if (st.tab === 'registro') {
                        const q = new URLSearchParams({ limit: '5000' }); Object.entries(st.f).forEach(([k, v]) => { if (v) q.set(k, v); });
                        st.regs = await obtener(`${B}/registros?${q}`);
                    } else if (st.tab === 'stock') { st.stock = await obtener(`${B}/stock-minimo`); contarStock(st.stock.a_comprar.length); }
                    else if (st.tab === 'consumo') { st.cons = await obtener(`${B}/consumos`); }
                    else if (st.tab === 'costos') { st.costos = await obtener(`${B}/costos`); if (!st.comps) st.comps = await obtener(`${B}/componentes`); }
                    else if (st.tab === 'componentes') { st.comps = await obtener(`${B}/componentes`); if (!st.dash) st.dash = await obtener(`${B}/dashboard`); }
                    else st.conf = await obtener(`${B}/configuracion`);
                    st.error = '';
                } catch (e) { st.error = e.message; }
                pintar();
            }
            async function recargarTodo() { st.conf = null; st.dash = null; st.comps = null; st.costos = null; await cargar(); }

            function pintar() {
                if (st.error) { panel.replaceChildren(util.errorBox(st.error, () => { st.error = ''; cargar(); })); return; }
                const listo = { dashboard: st.dash, registro: st.regs, componentes: st.comps, costos: st.costos && st.comps, consumo: st.cons, stock: st.stock, configuracion: st.conf }[st.tab];
                if (!listo) { panel.replaceChildren(util.cargando('Cargando el inventario TQTR…')); return; }
                panel.replaceChildren(...[].concat({ dashboard: vistaDashboard, registro: vistaRegistro, componentes: vistaComponentes, costos: vistaCostos, consumo: vistaConsumo, stock: vistaStock, configuracion: vistaConfig }[st.tab]()));
            }

            // ---------------------------------------------------------------- Dashboard
            function kpi(label, valor, kind, sub) {
                return h('div', { class: 'esc-kpi', dataset: { k: kind || '' } }, h('span', { class: 'l' }, label), h('span', { class: 'v' }, fmt(valor)), sub ? h('span', { class: 's' }, sub) : null);
            }
            const kindN = (n) => (n === null || n === undefined ? '' : n <= 0 ? 'bad' : n < 5 ? 'warn' : 'ok');
            function bloque(titulo, ...kids) { return h('section', { class: 'esc-blk' }, h('div', { class: 'esc-h' }, h('h2', null, titulo)), ...kids); }
            function barra(valor, max, kind) {
                const pct = max > 0 ? Math.max(0, Math.min(100, (valor / max) * 100)) : 0;
                return h('span', { class: 'itq-bar', dataset: { k: kind || '' }, 'aria-hidden': 'true' }, h('span', { style: `width:${pct.toFixed(1)}%` }));
            }
            function vistaDashboard() {
                const d = st.dash; const k = d.kpis; const pc = d.pcba_posibles || {};
                const out = [];
                if (d.stock && d.stock.a_comprar) {
                    out.push(T.banner('warn', 'alert', h('b', null, `${d.stock.a_comprar} material${d.stock.a_comprar === 1 ? '' : 'es'} en stock mínimo: `),
                        d.stock.items.map((x) => x.descripcion).join(', '), d.stock.a_comprar > d.stock.items.length ? '…' : '', ' ',
                        h('button', { class: 'btn btn-sm', type: 'button', onclick: () => irTab('stock') }, 'Ver qué comprar')));
                }
                out.push(bloque('Producto final posible', h('div', { class: 'esc-kpis', dataset: { n: 6 } },
                    kpi('TQT R1 + R2 + R3', d.producto_final_posible, kindN(d.producto_final_posible), 'mínimo de las tres PCBA'),
                    kpi('PCBA posibles · R1', pc.R1, kindN(pc.R1)), kpi('PCBA posibles · R2', pc.R2, kindN(pc.R2)), kpi('PCBA posibles · R3', pc.R3, kindN(pc.R3)),
                    kpi('Quintalock', d.quintalock, kindN(d.quintalock), 'caja + actuador'), kpi('Translock', d.translock, kindN(d.translock), 'caja + actuador'))));
                out.push(bloque('Movimientos', h('div', { class: 'esc-kpis', dataset: { n: 5 } },
                    kpi('Registros', k.movimientos, 'info'), kpi('Suman existencia', k.entradas, 'ok'), kpi('Salidas', k.salidas, ''),
                    kpi('Componentes', k.componentes, ''), kpi('En alerta', k.alertas, k.alertas ? 'warn' : 'ok', k.alertas ? 'ver lista a la derecha' : 'todo con existencia'))));
                const cs = d.costos;
                if (cs) {
                    out.push(bloque(`Costos (MXN) · producto ${cs.parametros.producto} · tipo de cambio ${fmt(cs.parametros.tipo_cambio)}`, h('div', { class: 'esc-kpis', dataset: { n: 4 } },
                        kpi('Costo por armado', mxn(cs.armado.total), 'info', 'R1 + R2 + R3 + gabinete y actuador'),
                        kpi('Inventario en existencia', mxn(cs.valor_existencia), '', 'disponible × costo unitario'),
                        kpi('Armados que alcanzan', cs.armados_posibles.cantidad, kindN(cs.armados_posibles.cantidad), `cuestan ${mxn(cs.armados_posibles.costo)}`),
                        kpi('Producido', mxn(cs.producido.costo), '', `${cs.producido.tarjetas} tarjeta${cs.producido.tarjetas === 1 ? '' : 's'} completa${cs.producido.tarjetas === 1 ? '' : 's'}`))));
                }
                if (d.consumo) {
                    out.push(bloque(`Consumo de tarjetas completas (desde ${d.consumo.consumo_desde})`, h('div', { class: 'esc-kpis', dataset: { n: 4 } },
                        kpi('Tarjetas con consumo', d.consumo.tarjetas, 'info', d.consumo.disueltas ? `${d.consumo.disueltas} disueltas` : 'ninguna disuelta'),
                        kpi('Costo estándar', mxn(d.consumo.costo_estandar), ''), kpi('Costo real', mxn(d.consumo.costo_real), ''),
                        kpi('Merma', mxn(d.consumo.merma_costo), d.consumo.merma_costo > 0 ? 'warn' : 'ok'))));
                }
                if (d.sin_coincidencia && d.sin_coincidencia.length) {
                    out.push(T.banner('warn', 'alert', h('b', null, 'Modelos del registro sin componente: '), d.sin_coincidencia.join(', '), '. No cuentan en el dashboard; usa exactamente el Tipo / Modelo del catálogo.'));
                }
                const izq = h('div', { class: 'stack' });
                Object.keys(d.grupos).forEach((g) => {
                    const filas = d.componentes.filter((f) => f.grupo === g);
                    if (!filas.length) return;
                    const max = Math.max(...filas.map((f) => Math.max(0, f.disponible) + f.consumida), 0);
                    izq.append(bloque(grupoNombre(g) + (pc[g] !== undefined ? ` · ${fmt(pc[g])} PCBA posibles` : ''), h('div', { class: 'esc-tw' }, h('table', { class: 'esc-t itq-t' },
                        h('caption', { class: 'sr-only' }, `Existencias ${grupoNombre(g)}`),
                        h('thead', null, h('tr', null, ['Material', 'Proveedor', 'Disponible', 'Consumida', 'Ensambles', 'Estado'].map((t, i) => h('th', { scope: 'col', class: i >= 2 && i <= 4 ? 'num' : null }, t)))),
                        h('tbody', null, filas.map((f) => h('tr', null,
                            h('td', null, h('div', { class: 'itq-mat' }, f.descripcion), barra(Math.max(0, f.disponible), max, ESTADOS[f.estado] ? ESTADOS[f.estado][1] : '')),
                            h('td', null, f.proveedor || muted('—')),
                            h('td', { class: 'num mono' }, fmt(f.disponible), ' ', muted(f.unidad || '')),
                            h('td', { class: 'num mono' }, fmt(f.consumida)),
                            h('td', { class: 'num mono' }, fmt(f.ensambles)),
                            h('td', null, estadoBadge(f.estado)))))))));
                });
                const der = h('div', { class: 'stack' });
                der.append(bloque('Alertas de existencia', d.alertas.length
                    ? h('ul', { class: 'itq-lista' }, d.alertas.map((a) => h('li', null, estadoBadge(a.estado), h('span', { class: 'grow' }, a.descripcion), h('span', { class: 'mono' }, fmt(a.disponible), ' ', muted(a.unidad || '')))))
                    : T.empty('check', 'Sin alertas', 'Todos los componentes alcanzan al menos para un ensamble.')));
                der.append(bloque('Productos finales según la BOM', h('ul', { class: 'itq-lista' }, d.productos.map((p) => h('li', null,
                    h('span', { class: 'grow' }, h('b', null, p.producto), h('br'), muted(p.limitante ? `Limita: ${p.limitante}` : 'Sin componentes en la BOM')),
                    h('span', { class: 'mono itq-n', dataset: { k: kindN(p.posibles) } }, fmt(p.posibles)))))));
                const maxMes = Math.max(1, ...d.por_mes.map((m) => m.entradas + m.salidas + m.otros));
                der.append(bloque('Movimientos por mes', h('ul', { class: 'itq-lista itq-meses' }, d.por_mes.map((m) => h('li', null,
                    h('span', { class: 'mono' }, m.mes),
                    h('span', { class: 'itq-apilada grow', 'aria-label': `${m.entradas} que suman, ${m.salidas} salidas` },
                        h('span', { dataset: { k: 'ok' }, style: `width:${(m.entradas / maxMes) * 100}%` }), h('span', { dataset: { k: 'bad' }, style: `width:${(m.salidas / maxMes) * 100}%` }), h('span', { style: `width:${(m.otros / maxMes) * 100}%` })),
                    h('span', { class: 'mono' }, `+${m.entradas} / −${m.salidas}`)))),
                    h('p', { class: 'muted itq-ley' }, h('i', { dataset: { k: 'ok' } }), 'suman existencia ', h('i', { dataset: { k: 'bad' } }), 'salidas')));
                der.append(bloque('Por tipo de movimiento', h('ul', { class: 'itq-lista' }, d.por_tipo.map((t) => h('li', null,
                    h('span', { class: 'grow' }, t.movimiento), muted(t.efecto > 0 ? 'suma' : t.efecto < 0 ? 'resta' : 'no afecta'), h('span', { class: 'mono' }, `${t.movimientos} reg.`))))));
                der.append(bloque('Últimos movimientos', h('ul', { class: 'itq-lista' }, d.recientes.map((r) => h('li', null,
                    h('span', { class: 'mono' }, r.fecha_entrada || '—'), h('span', { class: 'grow' }, r.modelo), muted(r.movimiento), h('span', { class: 'mono' }, fmt(r.cantidad)))))));
                const rev = d.componentes.filter((f) => f.en_revision > 0);
                if (rev.length) {
                    out.push(bloque('Devueltas / en revisión (no suman a disponible)', h('ul', { class: 'itq-lista' }, rev.map((f) => h('li', null,
                        h('span', { class: 'grow' }, h('b', null, f.descripcion), h('br'), muted(`Disponible ${fmt(f.disponible)} · en revisión ${fmt(f.en_revision)} ${f.unidad || ''}`)),
                        h('button', { class: 'btn btn-sm', type: 'button', onclick: () => reclasificar(f, 'disponible') }, icon('check'), 'Pasar a disponible'),
                        h('button', { class: 'btn btn-sm btn-ghost', type: 'button', onclick: () => reclasificar(f, 'baja') }, icon('trash'), 'Dar de baja'))))));
                }
                out.push(h('div', { class: 'itq-dash' }, izq, der));
                return out;
            }

            function reclasificar(f, accion) {
                const disp = accion === 'disponible';
                const inp = h('input', { class: 'input mono', type: 'number', id: 'rcCant', min: '1', max: String(f.en_revision), step: 'any', value: f.en_revision });
                const nota = h('input', { class: 'input', id: 'rcNota', maxlength: 500, placeholder: disp ? 'Revisada, funciona' : 'Dañada, sin reparación' });
                const err = h('div', { class: 'hint err', role: 'alert' });
                sheet({ title: `${disp ? 'Pasar a disponible' : 'Dar de baja'} · ${f.descripcion}`, body: [
                    h('p', { class: 'muted' }, disp ? 'Las piezas revisadas suman a la existencia disponible. Queda un movimiento en el Registro.' : 'Las piezas salen de revisión sin sumar a disponible. Queda un movimiento en el Registro.'),
                    campo('rcCant', `Cantidad (en revisión: ${fmt(f.en_revision)})`, inp), campo('rcNota', 'Nota', nota), err],
                    actions: [{ label: 'Cancelar', kind: 'ghost', onClick: () => true }, { label: disp ? 'Pasar a disponible' : 'Dar de baja', kind: disp ? 'primary' : 'danger', keepOpen: true, onClick: async () => {
                        const r = await api(`${B}/componentes/${f.id}/reclasificar`, { method: 'POST', body: { accion, cantidad: Number(inp.value), nota: nota.value } });
                        if (!r.ok) { err.textContent = r.error; return false; }
                        toast(disp ? 'Pasaron a disponible' : 'Dadas de baja', { kind: 'ok' }); st.dash = null; st.comps = null; st.regs = null; cargar(); return true;
                    } }] });
            }

            // ---------------------------------------------------------------- Registro
            const sel = (id, label, opciones, valor, onchange, vacio) => h('select', { class: 'input', id, 'aria-label': label, onchange },
                vacio !== undefined ? h('option', { value: '' }, vacio) : null, opciones.map((o) => h('option', { value: o, selected: o === valor ? '' : null }, o)));
            const valores = (tipo) => ((st.conf && st.conf.catalogos[tipo]) || []).map((x) => x.valor);
            function vistaRegistro() {
                const f = st.f;
                const q = h('input', { class: 'input', type: 'search', id: 'itqQ', placeholder: 'Modelo, código, destino o notas', 'aria-label': 'Buscar en el registro', 'data-buscar': '1', value: f.q, autocomplete: 'off' });
                q.addEventListener('input', T.debounce(() => { f.q = q.value; cargar().then(() => { const n = document.getElementById('itqQ'); if (n) { n.focus(); n.setSelectionRange(n.value.length, n.value.length); } }); }, 250));
                const fecha = (id, label, k) => h('label', { class: 'itq-fecha', for: id }, h('span', { class: 'muted' }, label), h('input', { class: 'input', type: 'date', id, value: f[k], onchange: (e) => { f[k] = e.target.value; cargar(); } }));
                const items = st.regs.items;
                const COLS = [
                    { id: 'fecha_entrada', titulo: 'Fecha', cel: (r) => h('span', { class: 'mono' }, r.fecha_entrada || '—'), sort: (a, b) => util.cmp(a.fecha_entrada || '', b.fecha_entrada || '') || a.id - b.id },
                    { id: 'codigo', titulo: 'ID / Código', cls: 'c-2', cel: (r) => (r.codigo ? h('span', { class: 'mono' }, r.codigo) : muted('—')) },
                    { id: 'categoria', titulo: 'Categoría', cls: 'c-3', cel: (r) => r.categoria || muted('—') },
                    { id: 'modelo', titulo: 'Tipo / Modelo', cel: (r) => r.modelo },
                    { id: 'movimiento', titulo: 'Movimiento', cel: (r) => { const ef = efectoDe(r.movimiento); return T.badge(r.movimiento, ef > 0 ? 'ok' : ef < 0 ? 'warn' : '', ef > 0 ? 'plus' : ef < 0 ? 'minus' : 'circle'); } },
                    { id: 'cantidad', titulo: 'Cantidad', cls: 'num', cel: (r) => h('span', { class: 'mono' }, fmt(r.cantidad), ' ', muted(r.unidad || '')), sort: (a, b) => a.cantidad - b.cantidad },
                    { id: 'condicion', titulo: 'Condición', cls: 'c-3', cel: (r) => r.condicion || muted('—') },
                    { id: 'fecha_salida', titulo: 'Salida', cls: 'c-2', cel: (r) => (r.fecha_salida ? h('span', { class: 'mono' }, r.fecha_salida) : muted('—')) },
                    { id: 'destino', titulo: 'Ubicación / Destino', cel: (r) => r.destino || muted('—') },
                    { id: 'acc', titulo: '', sr: 'Acciones', sortable: false, cls: 'act', cel: (r) => h('button', { class: 'btn btn-sm btn-ghost', type: 'button', 'aria-label': `Editar movimiento ${r.id}`, onclick: () => editarMov(r) }, icon('edit'), 'Editar') },
                ];
                const tw = h('div');
                const pintarT = () => util.pintarTabla(tw, { cols: COLS, rows: items, key: (r) => r.id, sort: st.sort, onSort: (id) => { st.sort = util.alternarOrden(st.sort, id); pintarT(); },
                    onOpen: editarMov, label: (r) => `${r.fecha_entrada || ''} ${r.movimiento} ${r.cantidad} ${r.modelo}`, limit: st.limit, onMas: () => { st.limit += 200; pintarT(); }, caption: 'Registro de inventario TQTR',
                    vacio: { icono: 'list', titulo: st.regs.total ? 'Ningún movimiento coincide' : 'Sin movimientos', texto: 'Cambia los filtros o registra un movimiento nuevo.' } });
                pintarT();
                const hayFiltro = Object.values(f).some(Boolean);
                return [h('div', { class: 'esc-bar' },
                    h('div', { class: 'esc-buscar' }, icon('search'), q),
                    sel('itqMov', 'Tipo de movimiento', valores('movimiento'), f.movimiento, (e) => { f.movimiento = e.target.value; cargar(); }, 'Todos los movimientos'),
                    sel('itqCat', 'Categoría', valores('categoria'), f.categoria, (e) => { f.categoria = e.target.value; cargar(); }, 'Todas las categorías'),
                    fecha('itqDesde', 'Desde', 'desde'), fecha('itqHasta', 'Hasta', 'hasta'),
                    hayFiltro ? h('button', { class: 'btn btn-ghost', type: 'button', onclick: () => { st.f = { q: '', movimiento: '', categoria: '', desde: '', hasta: '' }; cargar(); } }, 'Quitar filtros') : null,
                    h('div', { class: 'grow' }), h('span', { class: 'info', role: 'status', 'aria-live': 'polite' }, `${st.regs.total} movimiento${st.regs.total === 1 ? '' : 's'}`)), tw];
            }
            function efectoDe(mov) { const x = ((st.conf && st.conf.catalogos.movimiento) || []).find((m) => m.valor === mov); return x ? Number(x.efecto || 0) : 0; }

            function campo(id, label, control, hint) { return h('div', { class: 'field grow' }, h('label', { for: id }, label), control, hint ? h('p', { class: 'hint' }, hint) : null); }
            function confirmarBorrado(btn, err, texto, accion) {
                if (!btn._armado) {
                    btn._armado = true; err.textContent = texto; const orig = btn.lastChild.textContent; btn.lastChild.textContent = 'Confirmar y eliminar';
                    setTimeout(() => { btn._armado = false; if (btn.isConnected) { btn.lastChild.textContent = orig; err.textContent = ''; } }, 6000);
                    return false;
                }
                return accion();
            }

            function editarMov(r) {
                const nuevo = !r; const v = r || { fecha_entrada: new Date().toLocaleDateString('sv-SE'), condicion: valores('condicion')[0] || '', movimiento: 'Entrada' };
                const modelos = st.conf.modelos.includes(v.modelo) || !v.modelo ? st.conf.modelos : [v.modelo, ...st.conf.modelos];
                const c = {
                    fecha_entrada: h('input', { class: 'input', type: 'date', id: 'mFe', value: v.fecha_entrada || '' }),
                    modelo: sel('mMod', 'Tipo / Modelo', modelos, v.modelo, null, 'Elige el material o producto…'),
                    movimiento: sel('mMov', 'Tipo de movimiento', valores('movimiento'), v.movimiento),
                    cantidad: h('input', { class: 'input mono', type: 'number', id: 'mCant', min: '0', step: 'any', inputmode: 'decimal', value: v.cantidad ?? '' }),
                    unidad: sel('mUni', 'Unidad', valores('unidad'), v.unidad, null, 'La del componente'),
                    categoria: sel('mCat', 'Categoría', valores('categoria'), v.categoria, null, 'La del componente'),
                    condicion: sel('mCond', 'Condición', valores('condicion'), v.condicion, null, '—'),
                    fecha_salida: h('input', { class: 'input', type: 'date', id: 'mFs', value: v.fecha_salida || '' }),
                    destino: h('input', { class: 'input', id: 'mDest', value: v.destino || '', maxlength: 200, placeholder: 'I+D, Producción semana 35…' }),
                    codigo: h('input', { class: 'input mono', id: 'mCod', value: v.codigo || '', maxlength: 200, placeholder: 'GAB-QL-N-0001' }),
                    notas: h('input', { class: 'input', id: 'mNotas', value: v.notas || '', maxlength: 500 }),
                };
                const err = h('div', { class: 'hint err', role: 'alert' });
                const acciones = [];
                if (!nuevo) acciones.push({ label: 'Eliminar', kind: 'danger', icon: 'trash', keepOpen: 'always', onClick: (btn) => confirmarBorrado(btn, err, 'Se eliminará este movimiento y cambiarán las existencias. Pulsa otra vez para confirmar.', async () => {
                    const x = await api(`${B}/registros/${r.id}`, { method: 'DELETE' });
                    if (!x.ok && x.status !== 204) { err.textContent = x.error; return false; }
                    toast('Movimiento eliminado', { kind: 'ok' }); s.close(); st.dash = null; cargar(); return false;
                }) });
                acciones.push({ label: nuevo ? 'Registrar' : 'Guardar', kind: 'primary', keepOpen: true, onClick: async () => {
                    err.textContent = '';
                    const body = {}; Object.entries(c).forEach(([k, el]) => { body[k] = el.value === '' ? null : el.value; });
                    if (!body.modelo) { err.textContent = 'Elige el Tipo / Modelo.'; c.modelo.focus(); return false; }
                    if (!(Number(body.cantidad) > 0)) { err.textContent = 'La cantidad debe ser mayor que cero.'; c.cantidad.focus(); return false; }
                    body.cantidad = Number(body.cantidad);
                    if (!nuevo) ['codigo', 'destino', 'notas', 'categoria', 'condicion', 'unidad'].forEach((k) => { if (body[k] === null) body[k] = ''; });
                    if (nuevo) Object.keys(body).forEach((k) => { if (body[k] === null) delete body[k]; });
                    const x = await api(nuevo ? `${B}/registros` : `${B}/registros/${r.id}`, { method: nuevo ? 'POST' : 'PATCH', body });
                    if (!x.ok) { err.textContent = x.error; return false; }
                    toast(nuevo ? 'Movimiento registrado' : 'Cambios guardados', { kind: 'ok' }); st.dash = null; cargar(); return true;
                } });
                const s = sheet({
                    title: nuevo ? 'Nuevo movimiento' : `Editar movimiento ${r.id}`,
                    body: [
                        h('div', { class: 'row wrap itq-form' }, campo('mFe', 'Fecha de entrada', c.fecha_entrada), campo('mMov', 'Tipo de movimiento', c.movimiento)),
                        campo('mMod', 'Tipo / Modelo', c.modelo, 'Debe ser exactamente el del catálogo para que cuente en el dashboard.'),
                        h('div', { class: 'row wrap itq-form' }, campo('mCant', 'Cantidad', c.cantidad), campo('mUni', 'Unidad', c.unidad)),
                        h('div', { class: 'row wrap itq-form' }, campo('mCat', 'Categoría', c.categoria), campo('mCond', 'Condición', c.condicion)),
                        h('div', { class: 'row wrap itq-form' }, campo('mFs', 'Fecha de salida', c.fecha_salida), campo('mDest', 'Ubicación / Destino', c.destino)),
                        h('div', { class: 'row wrap itq-form' }, campo('mCod', 'ID / Código', c.codigo), campo('mNotas', 'Notas', c.notas)), err],
                    actions: acciones,
                });
            }

            // ---------------------------------------------------------------- Componentes
            function vistaComponentes() {
                const prods = st.comps.productos.map((p) => p.nombre);
                const COLS = [
                    { id: 'grupo', titulo: 'Grupo', cel: (c) => h('span', { class: 'mono' }, c.grupo || '—') },
                    { id: 'categoria', titulo: 'Categoría', cls: 'c-3', cel: (c) => c.categoria || muted('—') },
                    { id: 'descripcion', titulo: 'Descripción del material', cel: (c) => h('span', null, c.descripcion, c.en_dashboard ? null : h('span', { class: 'muted' }, ' · fuera del dashboard')) },
                    { id: 'cantidad_lote', titulo: 'Por caja / bobina / lote', cls: 'num', cel: (c) => h('span', { class: 'mono' }, fmt(c.cantidad_lote), ' ', muted(c.unidad_lote || '')) },
                    { id: 'cantidad_ensamble', titulo: 'Por ensamble', cls: 'num', cel: (c) => h('span', { class: 'mono' }, fmt(c.cantidad_ensamble), ' ', muted(c.unidad || '')) },
                    { id: 'rendimiento_lote', titulo: 'Rendimiento por lote', cls: 'num c-2', cel: (c) => h('span', { class: 'mono' }, fmt(c.rendimiento_lote)) },
                    { id: 'acumulado', titulo: 'Acumulado', cls: 'num', cel: (c) => h('span', { class: 'mono' }, fmt(c.acumulado)) },
                    { id: 'disponible', titulo: 'Disponible', cls: 'num', cel: (c) => h('span', { class: 'mono' }, fmt(c.disponible)) },
                    { id: 'en_revision', titulo: 'En revisión', cls: 'num c-2', cel: (c) => (c.en_revision ? h('button', { class: 'btn btn-sm btn-ghost mono', type: 'button', title: 'Pasar a disponible', 'aria-label': `${c.en_revision} devueltas de ${c.descripcion}: pasar a disponible`, onclick: () => reclasificar(c, 'disponible') }, fmt(c.en_revision)) : muted('—')) },
                    { id: 'stock_minimo', titulo: 'Mínimo', cls: 'num c-2', cel: (c) => h('span', { class: 'mono' }, c.stock_minimo ? fmt(c.stock_minimo) : '—') },
                    { id: 'bom', titulo: 'En productos', cls: 'c-3', sortable: false, cel: (c) => h('span', { class: 'itq-bom' }, prods.map((p, i) => h('span', { class: 'mono', title: p, dataset: { on: c.bom[p] ? '1' : '' } }, c.bom[p] ? fmt(c.bom[p]) : '·'))) },
                    { id: 'acc', titulo: '', sr: 'Acciones', sortable: false, cls: 'act', cel: (c) => h('button', { class: 'btn btn-sm btn-ghost', type: 'button', 'aria-label': `Editar ${c.descripcion}`, onclick: () => editarComp(c) }, icon('edit'), 'Editar') },
                ];
                const tw = h('div');
                const pintarT = () => util.pintarTabla(tw, { cols: COLS, rows: st.comps.items, key: (c) => c.id, sort: st.csort, onSort: (id) => { st.csort = util.alternarOrden(st.csort, id); pintarT(); },
                    onOpen: editarComp, label: (c) => c.descripcion, caption: 'Lista de componentes (BOM)', vacio: { icono: 'box', titulo: 'Sin componentes', texto: 'Agrega el primero.' } });
                pintarT();
                return [h('div', { class: 'esc-bar' }, h('p', { class: 'muted grow' }, 'BOM de materiales y cantidades por ensamble. "En productos" muestra la cantidad que lleva cada producto final, en este orden: ',
                    prods.map((p, i) => h('span', null, i ? ' · ' : '', h('b', null, `${i + 1}. `), p))),
                h('button', { class: 'btn', type: 'button', onclick: () => editarComp(null) }, icon('plus'), 'Nuevo componente')), tw];
            }

            function editarComp(cp) {
                const nuevo = !cp; const v = cp || { grupo: '', en_dashboard: true, bom: {} };
                const prods = (st.comps ? st.comps.productos : st.conf.productos).map((p) => p.nombre);
                const grupos = Object.keys((st.dash && st.dash.grupos) || { R1: 1, R2: 1, R3: 1, A: 1, G: 1 });
                const num = (id, val) => h('input', { class: 'input mono', type: 'number', id, min: '0', step: 'any', inputmode: 'decimal', value: val ?? '' });
                const txt = (id, val, ph) => h('input', { class: 'input', id, value: val || '', maxlength: 200, placeholder: ph || '' });
                const c = {
                    descripcion: txt('cDesc', v.descripcion), grupo: sel('cGrupo', 'Grupo', grupos, v.grupo, null, 'Sin grupo'), categoria: sel('cCat', 'Categoría', valores('categoria'), v.categoria, null, '—'),
                    proveedor: txt('cProv', v.proveedor, 'JLCPCB, Digikey…'), cantidad_lote: num('cLote', v.cantidad_lote), unidad_lote: txt('cUL', v.unidad_lote, 'pza, m, l'),
                    cantidad_ensamble: num('cEns', v.cantidad_ensamble), unidad: txt('cU', v.unidad, 'pza, m, ml'), unidad_inventario: sel('cUI', 'Unidad de inventario', valores('unidad'), v.unidad_inventario, null, '—'),
                    stock_minimo: num('cMin', v.stock_minimo || ''), notas: txt('cNotas', v.notas),
                };
                const chk = h('input', { type: 'checkbox', id: 'cDash', checked: v.en_dashboard ? '' : null });
                const bom = prods.map((p, i) => [p, num(`cBom${i}`, (v.bom || {})[p] || '')]);
                const err = h('div', { class: 'hint err', role: 'alert' });
                const acciones = [];
                if (!nuevo) acciones.push({ label: 'Eliminar', kind: 'danger', icon: 'trash', keepOpen: 'always', onClick: (btn) => confirmarBorrado(btn, err, `Se dará de baja «${cp.descripcion}». Pulsa otra vez para confirmar.`, async () => {
                    const x = await api(`${B}/componentes/${cp.id}`, { method: 'DELETE' });
                    if (!x.ok && x.status !== 204) { err.textContent = x.error; return false; }
                    toast('Componente eliminado', { kind: 'ok' }); s.close(); recargarTodo(); return false;
                }) });
                acciones.push({ label: nuevo ? 'Agregar' : 'Guardar', kind: 'primary', keepOpen: true, onClick: async () => {
                    err.textContent = '';
                    const body = { en_dashboard: chk.checked, bom: {} };
                    Object.entries(c).forEach(([k, el]) => { const val = el.value.trim(); body[k] = ['cantidad_lote', 'cantidad_ensamble', 'stock_minimo'].includes(k) ? (val === '' ? 0 : Number(val)) : val; });
                    if (!body.descripcion) { err.textContent = 'Escribe la descripción del material.'; c.descripcion.focus(); return false; }
                    bom.forEach(([p, el]) => { body.bom[p] = el.value === '' ? 0 : Number(el.value); });
                    const x = await api(nuevo ? `${B}/componentes` : `${B}/componentes/${cp.id}`, { method: nuevo ? 'POST' : 'PATCH', body });
                    if (!x.ok) { err.textContent = x.error; return false; }
                    toast(nuevo ? 'Componente agregado' : 'Componente guardado', { kind: 'ok' }); recargarTodo(); return true;
                } });
                const s = sheet({
                    title: nuevo ? 'Nuevo componente' : `Editar ${cp.descripcion}`,
                    body: [
                        campo('cDesc', 'Descripción del material', c.descripcion, nuevo ? null : 'Si la cambias, los movimientos del registro con el nombre anterior se renombran.'),
                        h('div', { class: 'row wrap itq-form' }, campo('cGrupo', 'Grupo (tarjeta)', c.grupo), campo('cCat', 'Categoría', c.categoria)),
                        h('div', { class: 'row wrap itq-form' }, campo('cProv', 'Proveedor', c.proveedor), campo('cUI', 'Unidad de inventario', c.unidad_inventario)),
                        h('div', { class: 'row wrap itq-form' }, campo('cLote', 'Cantidad por caja / bobina / lote', c.cantidad_lote), campo('cUL', 'Unidad del lote', c.unidad_lote)),
                        h('div', { class: 'row wrap itq-form' }, campo('cEns', 'Cantidad por ensamble', c.cantidad_ensamble), campo('cU', 'Unidad', c.unidad)),
                        h('div', { class: 'row wrap itq-form' }, campo('cMin', 'Stock mínimo (alerta)', c.stock_minimo), campo('cNotas', 'Notas', c.notas)),
                        h('label', { class: 'esc-chk', for: 'cDash' }, chk, 'Cuenta para las PCBA posibles del dashboard'),
                        h('fieldset', { class: 'itq-bomset' }, h('legend', null, 'Cantidad en cada producto final (BOM)'),
                            h('div', { class: 'itq-bomgrid' }, bom.map(([p, el], i) => campo(`cBom${i}`, p, el)))), err],
                    actions: acciones,
                });
            }

            // ---------------------------------------------------------------- Costos
            function vistaCostos() {
                const cs = st.costos; const par = cs.parametros; const a = cs.armado;
                const tcIn = h('input', { class: 'input mono itq-tc', type: 'number', id: 'itqTc', min: '0', step: 'any', value: par.tipo_cambio, 'aria-label': 'Tipo de cambio MXN por USD' });
                const guardarPar = async (body) => {
                    const r = await api(`${B}/costos/parametros`, { method: 'PATCH', body });
                    if (!r.ok) { toast(r.error, { kind: 'bad' }); return; }
                    toast('Parámetros de costo guardados', { kind: 'ok' }); st.dash = null; cargar();
                };
                const segProd = par.variantes.map((v) => h('button', { type: 'button', 'aria-pressed': String(par.producto === v), onclick: () => { if (par.producto !== v) guardarPar({ producto: v }); } }, v));
                tcIn.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); guardarPar({ tipo_cambio: Number(tcIn.value) }); } });
                const out = [h('div', { class: 'esc-bar' },
                    h('span', { class: 'muted' }, 'Producto de costeo'), h('div', { class: 'esc-seg', role: 'group', 'aria-label': 'Producto de costeo' }, segProd),
                    h('label', { class: 'itq-fecha', for: 'itqTc' }, h('span', { class: 'muted' }, 'Tipo de cambio (MXN/USD)'), tcIn),
                    h('button', { class: 'btn', type: 'button', onclick: () => guardarPar({ tipo_cambio: Number(tcIn.value) }) }, 'Aplicar'),
                    h('div', { class: 'grow' }), h('button', { class: 'btn', type: 'button', onclick: () => editarCosto(null) }, icon('plus'), 'Nuevo costo'))];
                out.push(bloque(`Costo por armado · ${par.producto} (juego R1 + R2 + R3)`, h('div', { class: 'esc-kpis', dataset: { n: 5 } },
                    kpi('Total por armado', mxn(a.total), 'info', par.variantes.filter((v) => v !== par.producto).map((v) => `${v}: ${mxn(cs.por_variante[v].total)}`).join(' · ')),
                    ...par.grupos.map((g) => kpi(g === 'Otros' ? 'Gabinete y actuador' : `Tarjeta ${g}`, mxn(a.por_grupo[g]), '', a.total ? `${((a.por_grupo[g] / a.total) * 100).toFixed(1)} % del armado` : '')))));
                out.push(bloque('Inventario y producción', h('div', { class: 'esc-kpis', dataset: { n: 4 } },
                    kpi('Inventario en existencia', mxn(cs.valor_existencia), '', 'disponible × costo unitario (MXN)'),
                    kpi('Armados que alcanzan', cs.armados_posibles.cantidad, kindN(cs.armados_posibles.cantidad), `producto final y gabinete ${par.producto}`),
                    kpi('Costo de esos armados', mxn(cs.armados_posibles.costo), ''),
                    kpi('Producido', mxn(cs.producido.costo), '', `${cs.producido.tarjetas} tarjetas completas${Object.keys(cs.producido.por_gabinete).length ? ' · ' + Object.entries(cs.producido.por_gabinete).map(([g, n]) => `${g} ${n}`).join(', ') : ''}`))));
                if (cs.sin_componente.length) out.push(T.banner('warn', 'alert', h('b', null, 'Costos sin componente del inventario: '), cs.sin_componente.join(', '), '. No suman al valor en existencia.'));
                if (cs.componentes_sin_costo.length) out.push(T.banner('warn', 'alert', h('b', null, 'Componentes sin costo: '), cs.componentes_sin_costo.join(', '), '.'));
                const COLS = [
                    { id: 'grupo', titulo: 'Tarjeta', cel: (d) => h('span', { class: 'mono' }, d.grupo) },
                    { id: 'descripcion', titulo: 'Material', cel: (d) => h('span', null, h('div', { class: 'itq-mat' }, d.componente || d.descripcion), d.componente && d.componente !== d.descripcion ? muted(`En el Excel de costos: ${d.descripcion}`) : (!d.componente ? muted('Sin componente del inventario') : null)) },
                    { id: 'proveedor', titulo: 'Proveedor', cls: 'c-3', cel: (d) => d.proveedor || muted('—') },
                    { id: 'costo_unitario', titulo: 'Costo unitario', cls: 'num', cel: (d) => h('span', { class: 'mono' }, fmt(d.costo_unitario), ' ', muted(`${d.moneda}${d.unidad ? '/' + d.unidad : ''}`)) },
                    { id: 'cantidad_armado', titulo: 'Por armado', cls: 'num', cel: (d) => h('span', { class: 'mono' }, fmt(d.cantidad_armado)) },
                    { id: 'costo_armado_mxn', titulo: 'Costo por armado', cls: 'num', cel: (d) => h('span', { class: 'mono', dataset: { fuera: d.incluido && (!d.variante || d.variante === par.producto) ? '' : '1' } }, mxn(d.costo_armado_mxn)) },
                    { id: 'variante', titulo: 'Aplica a', cls: 'c-2', cel: (d) => (!d.incluido ? T.badge('No se suma', 'warn', 'minus') : d.variante ? T.badge(d.variante, d.variante === par.producto ? 'ok' : '', 'tag') : muted('Todos')), valor: (d) => (d.incluido ? d.variante : 'zz') },
                    { id: 'valor_existencia', titulo: 'En existencia', cls: 'num c-2', cel: (d) => h('span', { class: 'mono' }, d.valor_existencia === null ? '—' : mxn(d.valor_existencia)), sort: (x, y) => (x.valor_existencia || 0) - (y.valor_existencia || 0) },
                    { id: 'acc', titulo: '', sr: 'Acciones', sortable: false, cls: 'act', cel: (d) => h('button', { class: 'btn btn-sm btn-ghost', type: 'button', 'aria-label': `Editar costo de ${d.descripcion}`, onclick: () => editarCosto(d) }, icon('edit'), 'Editar') },
                ];
                const tw = h('div');
                st.ksort = st.ksort || { id: 'grupo', dir: 'asc' };
                const pintarT = () => util.pintarTabla(tw, { cols: COLS, rows: cs.items, key: (d) => d.id, sort: st.ksort, onSort: (id) => { st.ksort = util.alternarOrden(st.ksort, id); pintarT(); },
                    onOpen: editarCosto, label: (d) => d.descripcion, caption: 'Costos por componente', vacio: { icono: 'tag', titulo: 'Sin costos', texto: 'Agrega el primero con "Nuevo costo".' } });
                pintarT();
                out.push(bloque('Costos por componente', tw));
                if (cs.diferencias && cs.diferencias.length) {
                    out.push(bloque('Diferencias entre los dos Excel (cantidad por armado)', h('div', { class: 'esc-tw' }, h('table', { class: 'esc-t itq-t' },
                        h('caption', { class: 'sr-only' }, 'Diferencias de cantidad por armado'),
                        h('thead', null, h('tr', null, ['Componente', 'Excel de costos', 'Excel de inventario', 'Se descuenta por tarjeta'].map((x, i) => h('th', { scope: 'col', class: i ? 'num' : null }, x)))),
                        h('tbody', null, cs.diferencias.map((x) => h('tr', null, h('td', null, x.componente),
                            h('td', { class: 'num mono' }, fmt(x.costos), ' ', muted(x.unidad_costos || '')), h('td', { class: 'num mono' }, fmt(x.inventario), ' ', muted(x.unidad_inventario || '')),
                            h('td', { class: 'num mono' }, h('b', null, fmt(x.consumo)))))))),
                        h('p', { class: 'muted' }, 'El estándar por armado es el del Excel de costos; el catalizador usa la del inventario porque Costos lo mide en ml y el stock está en piezas. Los "ensambles posibles" del Dashboard siguen la cantidad por ensamble del inventario.')));
                }
                return out;
            }

            function editarCosto(d) {
                const nuevo = !d; const v = d || { grupo: 'Otros', moneda: 'MXN', incluido: true, variante: '' };
                const par = st.costos.parametros;
                const comps = st.comps ? st.comps.items : [];
                const cSel = h('select', { class: 'input', id: 'kComp' }, h('option', { value: '' }, 'Sin componente del inventario'),
                    comps.map((x) => h('option', { value: x.id, selected: x.id === v.componente_id ? '' : null }, x.descripcion)));
                const num = (id, val) => h('input', { class: 'input mono', type: 'number', id, min: '0', step: 'any', inputmode: 'decimal', value: val ?? '' });
                const c = {
                    descripcion: h('input', { class: 'input', id: 'kDesc', value: v.descripcion || '', maxlength: 200, placeholder: 'Igual que el componente si lo dejas vacío' }),
                    grupo: sel('kGrupo', 'Tarjeta', par.grupos, v.grupo), proveedor: h('input', { class: 'input', id: 'kProv', value: v.proveedor || '', maxlength: 200 }),
                    costo_unitario: num('kCosto', v.costo_unitario), moneda: sel('kMon', 'Moneda', par.monedas, v.moneda), unidad: h('input', { class: 'input', id: 'kUni', value: v.unidad || '', maxlength: 40, placeholder: 'pza, m, l' }),
                    cantidad_armado: num('kCant', v.cantidad_armado), variante: sel('kVar', 'Aplica a', par.variantes, v.variante, null, 'Todos los productos'),
                    notas: h('input', { class: 'input', id: 'kNotas', value: v.notas || '', maxlength: 500 }),
                };
                const chk = h('input', { type: 'checkbox', id: 'kIncl', checked: v.incluido ? '' : null });
                const prev = h('p', { class: 'hint mono' });
                const upd = () => { const t = (Number(c.costo_unitario.value) || 0) * (Number(c.cantidad_armado.value) || 0) * (c.moneda.value === 'USD' ? par.tipo_cambio : 1); prev.textContent = `Costo por armado: ${mxn(t)}`; };
                [c.costo_unitario, c.cantidad_armado, c.moneda].forEach((el) => { el.addEventListener('input', upd); el.addEventListener('change', upd); }); upd();
                const err = h('div', { class: 'hint err', role: 'alert' });
                const acciones = [];
                if (!nuevo) acciones.push({ label: 'Eliminar', kind: 'danger', icon: 'trash', keepOpen: 'always', onClick: (btn) => confirmarBorrado(btn, err, `Se eliminará el costo de «${d.descripcion}». Pulsa otra vez para confirmar.`, async () => {
                    const x = await api(`${B}/costos/${d.id}`, { method: 'DELETE' });
                    if (!x.ok && x.status !== 204) { err.textContent = x.error; return false; }
                    toast('Costo eliminado', { kind: 'ok' }); s.close(); st.dash = null; cargar(); return false;
                }) });
                acciones.push({ label: nuevo ? 'Agregar' : 'Guardar', kind: 'primary', keepOpen: true, onClick: async () => {
                    err.textContent = '';
                    const body = { componente_id: cSel.value ? Number(cSel.value) : null, incluido: chk.checked };
                    Object.entries(c).forEach(([k, el]) => { const val = el.value.trim(); body[k] = ['costo_unitario', 'cantidad_armado'].includes(k) ? (val === '' ? 0 : Number(val)) : val; });
                    if (!body.descripcion && !body.componente_id) { err.textContent = 'Escribe la descripción o elige un componente.'; return false; }
                    if (!body.descripcion) delete body.descripcion;
                    const x = await api(nuevo ? `${B}/costos` : `${B}/costos/${d.id}`, { method: nuevo ? 'POST' : 'PATCH', body });
                    if (!x.ok) { err.textContent = x.error; return false; }
                    toast(nuevo ? 'Costo agregado' : 'Costo guardado', { kind: 'ok' }); st.dash = null; cargar(); return true;
                } });
                const s = sheet({
                    title: nuevo ? 'Nuevo costo' : `Costo de ${d.componente || d.descripcion}`,
                    body: [
                        campo('kComp', 'Componente del inventario', cSel, 'Liga el costo con su existencia para valorar el inventario.'),
                        campo('kDesc', 'Descripción', c.descripcion),
                        h('div', { class: 'row wrap itq-form' }, campo('kGrupo', 'Tarjeta', c.grupo), campo('kProv', 'Proveedor', c.proveedor)),
                        h('div', { class: 'row wrap itq-form' }, campo('kCosto', 'Costo unitario', c.costo_unitario), campo('kMon', 'Moneda', c.moneda), campo('kUni', 'Unidad', c.unidad)),
                        h('div', { class: 'row wrap itq-form' }, campo('kCant', 'Cantidad por armado', c.cantidad_armado), campo('kVar', 'Aplica a', c.variante)),
                        campo('kNotas', 'Notas', c.notas),
                        h('label', { class: 'esc-chk', for: 'kIncl' }, chk, 'Se suma al costo por armado'), prev, err],
                    actions: acciones,
                });
            }

            // ---------------------------------------------------------------- Stock mínimo
            function contarStock(n) {
                const i = PESTANAS.findIndex(([k]) => k === 'stock');
                tabs[i].textContent = n ? `Stock mínimo (${n})` : 'Stock mínimo';
                badgeLateral(n);
            }
            function vistaStock() {
                const sm = st.stock; const comprar = sm.a_comprar;
                const objIn = h('input', { class: 'input mono itq-tc', type: 'number', id: 'itqObj', min: '1', step: '1', value: sm.armados_objetivo });
                const aplicarObj = async () => {
                    const r = await api(`${B}/stock-minimo`, { method: 'PATCH', body: { armados_objetivo: Number(objIn.value) } });
                    if (!r.ok) { toast(r.error, { kind: 'bad' }); return; }
                    st.stock = r.data; toast('Armados objetivo actualizados', { kind: 'ok' }); pintar();
                };
                const dias = (x) => (x.dias_cobertura === null ? muted('sin consumo') : h('span', { class: 'mono', dataset: { k: x.margen_dias !== null && x.margen_dias <= 0 ? 'bad' : '' } }, `${fmt(x.dias_cobertura)} d`));
                const entrega = (x) => (x.entrega_dias ? h('span', null, h('span', { class: 'mono' }, `${x.entrega_dias} d`), x.entrega_nota ? muted(` · ${x.entrega_nota}`) : null) : muted('sin definir'));
                const COLS = [
                    { id: 'descripcion', titulo: 'Material', cel: (x) => h('span', null, h('div', { class: 'itq-mat' }, x.descripcion), x.bajo_minimo ? T.badge(x.disponible <= 0 ? 'Agotado' : 'Comprar', x.disponible <= 0 ? 'bad' : 'warn', 'alert') : null) },
                    { id: 'disponible', titulo: 'Disponible', cls: 'num', cel: (x) => h('span', { class: 'mono' }, fmt(x.disponible), ' ', muted(x.unidad || '')) },
                    { id: 'stock_minimo', titulo: 'Mínimo', cls: 'num', cel: (x) => h('span', { class: 'mono' }, x.stock_minimo ? fmt(x.stock_minimo) : '—') },
                    { id: 'punto_reorden', titulo: 'Reorden', cls: 'num', cel: (x) => h('span', { class: 'mono' }, x.punto_reorden ? fmt(x.punto_reorden) : '—') },
                    { id: 'dias_cobertura', titulo: 'Cobertura', cls: 'num c-2', cel: dias, sort: (a, b) => (a.dias_cobertura ?? 1e9) - (b.dias_cobertura ?? 1e9) },
                    { id: 'entrega_dias', titulo: 'Entrega', cel: entrega },
                    { id: 'sugerida', titulo: 'Comprar', cls: 'num', cel: (x) => h('span', { class: 'mono' }, x.sugerida ? fmt(x.sugerida) : '—'), sort: (a, b) => a.sugerida - b.sugerida },
                    { id: 'proveedor', titulo: 'Proveedor', cls: 'c-3', cel: (x) => x.proveedor || muted('—') },
                    { id: 'acc', titulo: '', sr: 'Acciones', sortable: false, cls: 'act', cel: (x) => h('button', { class: 'btn btn-sm btn-ghost', type: 'button', 'aria-label': `Editar stock mínimo de ${x.descripcion}`, onclick: () => editarStock(x) }, icon('edit'), 'Editar') },
                ];
                const out = [h('div', { class: 'esc-bar' },
                    h('p', { class: 'muted grow' }, `Cobertura = disponible ÷ consumo diario de los últimos ${sm.dias_ritmo} días. "Comprar" cubre los armados objetivo más el mínimo. Al cruzar el mínimo se avisa por correo a los administradores (una vez por cruce).`),
                    h('label', { class: 'itq-fecha', for: 'itqObj' }, h('span', { class: 'muted' }, 'Armados objetivo'), objIn),
                    h('button', { class: 'btn', type: 'button', onclick: aplicarObj }, 'Aplicar'))];
                out.push(h('div', { class: 'esc-kpis', dataset: { n: 4 } },
                    kpi('A comprar', comprar.length, comprar.length ? 'warn' : 'ok', comprar.length ? 'en o bajo el mínimo' : 'nada pendiente'),
                    kpi('Agotados', comprar.filter((x) => x.disponible <= 0).length, comprar.some((x) => x.disponible <= 0) ? 'bad' : 'ok'),
                    kpi('Sin cubrir la entrega', comprar.filter((x) => x.margen_dias !== null && x.margen_dias <= 0).length, '', 'cobertura ≤ tiempo de entrega'),
                    kpi('Con mínimo definido', sm.items.filter((x) => x.stock_minimo || x.punto_reorden).length, 'info', `de ${sm.items.length} componentes`)));
                const tc = h('div'); const ta = h('div');
                util.pintarTabla(tc, { cols: COLS, rows: comprar, key: (x) => x.id, onOpen: editarStock, label: (x) => x.descripcion, caption: 'Materiales a comprar por urgencia',
                    vacio: { icono: 'check', titulo: 'Nada que comprar', texto: 'Define el stock mínimo o el punto de reorden de cada material para recibir avisos.' } });
                st.ssort = st.ssort || { id: 'descripcion', dir: 'asc' };
                const pintarA = () => util.pintarTabla(ta, { cols: COLS, rows: sm.items, key: (x) => x.id, sort: st.ssort, onSort: (id) => { st.ssort = util.alternarOrden(st.ssort, id); pintarA(); },
                    onOpen: editarStock, label: (x) => x.descripcion, caption: 'Stock mínimo por componente' });
                pintarA();
                out.push(bloque('Materiales a comprar (por urgencia)', tc), bloque('Todos los componentes', ta));
                return out;
            }
            function editarStock(x) {
                const num = (id, v, paso) => h('input', { class: 'input mono', type: 'number', id, min: '0', step: paso || 'any', inputmode: 'decimal', value: v ?? '' });
                const c = { stock_minimo: num('sMin', x.stock_minimo), punto_reorden: num('sReo', x.punto_reorden), armados_objetivo: num('sObj', x.objetivo_propio ? x.armados_objetivo : '', '1'),
                    entrega_dias: num('sDias', x.entrega_dias, '1'), entrega_nota: h('input', { class: 'input', id: 'sNota', value: x.entrega_nota || '', maxlength: 500, placeholder: 'Importación, pedido semanal…' }),
                    proveedor: h('input', { class: 'input', id: 'sProv', value: x.proveedor || '', maxlength: 200 }) };
                const err = h('div', { class: 'hint err', role: 'alert' });
                sheet({ title: `Stock mínimo · ${x.descripcion}`, body: [
                    h('p', { class: 'muted' }, `Disponible: ${fmt(x.disponible)} ${x.unidad || ''} · ${fmt(x.cantidad_por_armado)} por armado · consumo ${fmt(x.consumo_diario)} por día.`),
                    h('div', { class: 'row wrap itq-form' }, campo('sMin', `Stock mínimo (${x.unidad || 'unidades'})`, c.stock_minimo), campo('sReo', 'Punto de reorden', c.punto_reorden)),
                    h('div', { class: 'row wrap itq-form' }, campo('sObj', 'Armados objetivo (vacío = general)', c.armados_objetivo), campo('sDias', 'Tiempo de entrega (días)', c.entrega_dias)),
                    campo('sNota', 'Nota de entrega', c.entrega_nota), campo('sProv', 'Proveedor', c.proveedor), err],
                    actions: [{ label: 'Cancelar', kind: 'ghost', onClick: () => true }, { label: 'Guardar', kind: 'primary', keepOpen: true, onClick: async () => {
                        const body = { stock_minimo: Number(c.stock_minimo.value || 0), punto_reorden: Number(c.punto_reorden.value || 0), armados_objetivo: c.armados_objetivo.value ? Number(c.armados_objetivo.value) : null,
                            entrega_dias: Number(c.entrega_dias.value || 0), entrega_nota: c.entrega_nota.value, proveedor: c.proveedor.value };
                        const r = await api(`${B}/stock-minimo/${x.id}`, { method: 'PATCH', body });
                        if (!r.ok) { err.textContent = r.error; return false; }
                        toast('Stock mínimo guardado', { kind: 'ok' }); st.dash = null; st.comps = null; cargar(); return true;
                    } }] });
            }

            // ---------------------------------------------------------------- Consumo por tarjeta
            async function guardarDesde(valor) {
                if (!valor) { toast('Elige una fecha.', { kind: 'bad' }); return; }
                const r = await api(`${B}/consumos/parametros`, { method: 'PATCH', body: { consumo_desde: valor } });
                if (!r.ok) { toast(r.error, { kind: 'bad' }); return; }
                toast(`Se descuenta material de tarjetas completadas desde el ${valor}`, { kind: 'ok' }); st.cons = r.data; st.dash = null; st.conf = null; cargar();
            }
            function vistaConsumo() {
                const cs = st.cons; const t = cs.totales;
                const desde = h('input', { class: 'input', type: 'date', id: 'itqDesdeC', value: cs.consumo_desde || '' });
                const out = [h('div', { class: 'esc-bar' },
                    h('p', { class: 'muted grow' }, 'Al quedar completa una tarjeta (R1 + R2 + R3 y MAC) se descuentan sus materiales; con gabinete asignado, también la caja y el actuador. Si se desempareja o se borra, solo vuelven la caja y el actuador.'),
                    h('label', { class: 'itq-fecha', for: 'itqDesdeC' }, h('span', { class: 'muted' }, 'Contar desde'), desde),
                    h('button', { class: 'btn', type: 'button', onclick: () => guardarDesde(desde.value) }, 'Aplicar'))];
                out.push(h('div', { class: 'esc-kpis', dataset: { n: 4 } },
                    kpi('Tarjetas completas', t.tarjetas, 'info', t.disueltas ? `${t.disueltas} disueltas o borradas` : 'ninguna disuelta'),
                    kpi('Costo estándar', mxn(t.costo_estandar), ''), kpi('Costo real', mxn(t.costo_real), ''),
                    kpi('Merma', mxn(t.merma_costo), t.merma_costo > 0 ? 'warn' : 'ok', 'real − estándar')));
                const COLS = [
                    { id: 'tarjeta_num', titulo: 'Tarjeta', cel: (x) => (x.estado === 'borrada' ? h('span', { class: 'mono' }, x.tarjeta_num) : h('a', { class: 'mono', href: `#/tarjetas?id=${x.tarjeta_id}` }, x.tarjeta_num)) },
                    { id: 'gabinete', titulo: 'Gabinete', cel: (x) => x.gabinete || muted('sin gabinete') },
                    { id: 'fecha_finalizado', titulo: 'Completada', cls: 'c-2', cel: (x) => h('span', { class: 'mono' }, x.fecha_finalizado || '—') },
                    { id: 'estado', titulo: 'Estado', cel: (x) => { const e = ESTADOS_TARJETA[x.estado] || ESTADOS_TARJETA.pendiente; return T.badge(e[0], e[1], e[2]); } },
                    { id: 'costo_estandar', titulo: 'Costo estándar', cls: 'num', cel: (x) => h('span', { class: 'mono' }, mxn(x.costo_estandar)) },
                    { id: 'costo_real', titulo: 'Costo real', cls: 'num', cel: (x) => h('span', { class: 'mono' }, mxn(x.costo_real)) },
                    { id: 'merma_costo', titulo: 'Merma', cls: 'num', cel: (x) => h('span', { class: 'mono', dataset: { k: x.merma_costo > 0 ? 'bad' : x.merma_costo < 0 ? 'ok' : '' } }, x.merma_costo ? mxn(x.merma_costo) : '—') },
                    { id: 'acc', titulo: '', sr: 'Acciones', sortable: false, cls: 'act', cel: (x) => h('button', { class: 'btn btn-sm btn-ghost', type: 'button', 'aria-label': `Ficha de materiales de la tarjeta ${x.tarjeta_num}`, onclick: () => abrirFicha(x) }, icon('list'), 'Ficha') },
                ];
                const tw = h('div');
                st.usort = st.usort || { id: 'fecha_finalizado', dir: 'desc' };
                const pintarT = () => util.pintarTabla(tw, { cols: COLS, rows: cs.items, key: (x) => x.tarjeta_id, sort: st.usort, onSort: (id) => { st.usort = util.alternarOrden(st.usort, id); pintarT(); },
                    onOpen: abrirFicha, label: (x) => `Tarjeta ${x.tarjeta_num}`, caption: 'Consumo de material por tarjeta',
                    vacio: { icono: 'list', titulo: 'Todavía no hay consumos', texto: `Aparecen cuando una tarjeta queda completa a partir del ${cs.consumo_desde}.` } });
                pintarT();
                out.push(tw);
                return out;
            }
            function abrirFicha(x) {
                sheet({ title: `Materiales de la tarjeta ${x.tarjeta_num}`, body: [fichaMateriales(x.tarjeta_id, ctx, { alGuardar: () => { st.dash = null; cargar(); } })],
                    actions: [{ label: 'Cerrar', kind: 'ghost', onClick: () => true }] });
            }

            // ---------------------------------------------------------------- Configuración
            function vistaConfig() {
                const cat = st.conf.catalogos;
                const tarjetas = TIPOS.map(([tipo, titulo]) => {
                    const inp = h('input', { class: 'input', id: `cfg-${tipo}`, maxlength: 200, placeholder: 'Nuevo valor', 'aria-label': `Nuevo valor de ${titulo}` });
                    const ef = tipo === 'movimiento' ? sel(`cfgEf-${tipo}`, 'Efecto en la existencia', [], '', null) : null;
                    if (ef) [['1', 'Suma'], ['-1', 'Resta'], ['0', 'No afecta']].forEach(([v, l]) => ef.append(h('option', { value: v }, l)));
                    const agregar = async () => {
                        if (!inp.value.trim()) { inp.focus(); return; }
                        const x = await api(`${B}/configuracion`, { method: 'POST', body: { tipo, valor: inp.value, efecto: ef ? Number(ef.value) : null } });
                        if (!x.ok) { toast(x.error, { kind: 'bad' }); return; }
                        toast('Agregado al catálogo', { kind: 'ok' }); st.conf = null; cargar();
                    };
                    inp.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); agregar(); } });
                    return h('section', { class: 'esc-card' }, h('div', { class: 'esc-h' }, h('h2', null, titulo), h('span', { class: 'muted' }, String((cat[tipo] || []).length))),
                        h('ul', { class: 'itq-lista' }, (cat[tipo] || []).map((x) => h('li', null,
                            h('span', { class: 'grow' }, x.valor),
                            tipo === 'movimiento' ? sel(`ef-${x.id}`, `Efecto de ${x.valor}`, [], '', async (e) => {
                                const r = await api(`${B}/configuracion/${x.id}`, { method: 'PATCH', body: { efecto: Number(e.target.value) } });
                                if (!r.ok) { toast(r.error, { kind: 'bad' }); return; }
                                toast(`«${x.valor}» ahora ${e.target.selectedOptions[0].textContent.toLowerCase()}`, { kind: 'ok' }); st.conf = null; st.dash = null; cargar();
                            }) : null,
                            h('button', { class: 'btn btn-sm btn-ghost', type: 'button', 'aria-label': `Renombrar ${x.valor}`, onclick: () => renombrar(x) }, icon('edit')),
                            h('button', { class: 'btn btn-sm btn-ghost', type: 'button', 'aria-label': `Quitar ${x.valor}`, onclick: () => quitar(`${B}/configuracion/${x.id}`, x.valor) }, icon('trash'))))),
                        h('div', { class: 'row' }, inp, ef, h('button', { class: 'btn', type: 'button', onclick: agregar }, icon('plus'), 'Agregar')));
                });
                // valores de efecto en los selects de movimiento
                tarjetas[1].querySelectorAll('select[id^="ef-"]').forEach((s, i) => {
                    const x = cat.movimiento[i]; [['1', 'Suma'], ['-1', 'Resta'], ['0', 'No afecta']].forEach(([v, l]) => s.append(h('option', { value: v, selected: Number(x.efecto || 0) === Number(v) ? '' : null }, l)));
                });
                const pin = h('input', { class: 'input', id: 'cfgProd', maxlength: 200, placeholder: 'Nuevo producto final', 'aria-label': 'Nuevo producto final' });
                const addProd = async () => {
                    if (!pin.value.trim()) { pin.focus(); return; }
                    const x = await api(`${B}/productos`, { method: 'POST', body: { nombre: pin.value } });
                    if (!x.ok) { toast(x.error, { kind: 'bad' }); return; }
                    toast('Producto final agregado; define su BOM en Componentes', { kind: 'ok' }); recargarTodo();
                };
                const productos = h('section', { class: 'esc-card' }, h('div', { class: 'esc-h' }, h('h2', null, 'Productos finales')),
                    h('p', { class: 'muted' }, 'Una salida de un producto final descuenta de cada componente la cantidad de su BOM.'),
                    h('ul', { class: 'itq-lista' }, st.conf.productos.map((p) => h('li', null, h('span', { class: 'grow' }, p.nombre),
                        h('button', { class: 'btn btn-sm btn-ghost', type: 'button', 'aria-label': `Quitar ${p.nombre}`, onclick: () => quitar(`${B}/productos/${p.id}`, p.nombre) }, icon('trash'))))),
                    h('div', { class: 'row' }, pin, h('button', { class: 'btn', type: 'button', onclick: addProd }, icon('plus'), 'Agregar')));
                const reglas = h('section', { class: 'esc-card' }, h('div', { class: 'esc-h' }, h('h2', null, 'Reglas de inventario')),
                    h('dl', { class: 'itq-reglas' }, (cat.regla || []).map((r) => [h('dt', null, r.valor), h('dd', null, r.descripcion)])));
                const modelos = h('section', { class: 'esc-card' }, h('div', { class: 'esc-h' }, h('h2', null, 'Tipo / Modelo'), h('span', { class: 'muted' }, String(st.conf.modelos.length))),
                    h('p', { class: 'muted' }, 'Se forma con los componentes y los productos finales.'),
                    h('ul', { class: 'itq-lista itq-compacta' }, st.conf.modelos.map((m) => h('li', null, m))));
                const dIn = h('input', { class: 'input', type: 'date', id: 'cfgDesde', value: st.conf.consumo_desde || '', 'aria-label': 'Fecha desde la que se descuenta material' });
                const consumo = h('section', { class: 'esc-card' }, h('div', { class: 'esc-h' }, h('h2', null, 'Consumo por tarjeta')),
                    h('p', { class: 'muted' }, 'Solo las tarjetas completadas desde esta fecha descuentan material del inventario.'),
                    h('div', { class: 'row' }, dIn, h('button', { class: 'btn', type: 'button', onclick: () => guardarDesde(dIn.value) }, 'Aplicar')));
                const cv = st.conf.conversiones || {};
                const cvIn = (id, k) => h('input', { class: 'input mono', type: 'number', id, min: '0', step: 'any', value: cv[k] ?? '' });
                const gIn = cvIn('cvG', 'conv_silicon_g_por_envase'); const mlIn = cvIn('cvMl', 'conv_catalizador_ml_por_envase'); const pIn = cvIn('cvP', 'precio_silicon_envase');
                const conversion = h('section', { class: 'esc-card' }, h('div', { class: 'esc-h' }, h('h2', null, 'Silicón y catalizador')),
                    h('p', { class: 'muted' }, 'El silicón se maneja en gramos y el catalizador en ml. Lo registrado antes en litros o piezas se tomó como envases del kit P-53; ajusta los factores si la presentación real es otra y se recalcula todo.'),
                    h('div', { class: 'row wrap itq-form' }, campo('cvG', 'Gramos por envase de silicón', gIn), campo('cvMl', 'ml por envase de catalizador', mlIn), campo('cvP', 'Precio por envase de silicón (MXN)', pIn)),
                    h('div', { class: 'row' }, h('button', { class: 'btn', type: 'button', onclick: async () => {
                        const r = await api(`${B}/conversiones`, { method: 'PATCH', body: { conv_silicon_g_por_envase: Number(gIn.value), conv_catalizador_ml_por_envase: Number(mlIn.value), precio_silicon_envase: Number(pIn.value) } });
                        if (!r.ok) { toast(r.error, { kind: 'bad' }); return; }
                        toast('Factores aplicados; existencias y costos recalculados', { kind: 'ok' }); recargarTodo();
                    } }, 'Aplicar factores')));
                return [h('div', { class: 'itq-cfg' }, consumo, conversion, ...tarjetas, productos, reglas, modelos)];
            }
            function renombrar(x) {
                const inp = h('input', { class: 'input', id: 'rnVal', value: x.valor, maxlength: 200 }); const err = h('div', { class: 'hint err', role: 'alert' });
                sheet({ title: `Renombrar «${x.valor}»`, body: [campo('rnVal', 'Nuevo nombre', inp, 'Los movimientos del registro que lo usan se actualizan también.'), err],
                    actions: [{ label: 'Cancelar', kind: 'ghost', onClick: () => true }, { label: 'Guardar', kind: 'primary', keepOpen: true, onClick: async () => {
                        const r = await api(`${B}/configuracion/${x.id}`, { method: 'PATCH', body: { valor: inp.value } });
                        if (!r.ok) { err.textContent = r.error; return false; }
                        toast('Catálogo actualizado', { kind: 'ok' }); recargarTodo(); return true;
                    } }] });
            }
            function quitar(url, nombre) {
                const err = h('div', { class: 'hint err', role: 'alert' });
                sheet({ title: `¿Quitar «${nombre}»?`, body: [h('p', null, 'Deja de aparecer en las listas. No se puede quitar si el registro lo usa.'), err],
                    actions: [{ label: 'Conservar', kind: 'ghost', onClick: () => true }, { label: 'Quitar', kind: 'danger', keepOpen: true, onClick: async () => {
                        const r = await api(url, { method: 'DELETE' });
                        if (!r.ok && r.status !== 204) { err.textContent = r.error; return false; }
                        toast(`«${nombre}» quitado`, { kind: 'ok' }); recargarTodo(); return true;
                    } }] });
            }

            // ---------------------------------------------------------------- export
            async function exportar() {
                bExport.disabled = true; bExport.lastChild.textContent = 'Preparando…';
                try {
                    const res = await fetch(`${B}/export`);
                    if (!res.ok) { toast(`No se pudo descargar (error ${res.status}).`, { kind: 'bad' }); return; }
                    const blob = await res.blob();
                    const m = /filename="?([^";]+)"?/i.exec(res.headers.get('Content-Disposition') || '');
                    const url = URL.createObjectURL(blob); const a = h('a', { href: url, download: m ? m[1] : 'INVENTARIO_TQTR.xlsx' });
                    document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 4000);
                    toast('Inventario TQTR descargado', { kind: 'ok' });
                } catch (e) { toast('Sin conexión: no se pudo descargar.', { kind: 'bad' }); } finally { bExport.disabled = false; bExport.lastChild.textContent = 'Descargar .xlsx'; }
            }

            irTab(st.tab);
            return {
                actualizar() { st.dash = null; st.comps = null; st.conf = null; st.costos = null; st.cons = null; st.stock = null; cargar(); },
                parametros(p) { const t = p.get('tab'); if (t && PESTANAS.some(([k]) => k === t) && t !== st.tab) irTab(t); },
            };
        },
    });
})();
