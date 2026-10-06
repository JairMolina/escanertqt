/**
 * sec_tarjetas.js - Tarjetas del lote: búsqueda, estado (completa / incompleta / sin MAC), detalle en panel lateral
 * con las placas R1/R2/R3 (Hardware, Firmware y MAC), etiqueta DYMO y ficha.
 * Emparejar (todas las completas) y desemparejar (una, varias o todas).
 * API: GET /api/tarjetas?lote_id= · POST /api/emparejar/auto · POST /api/tarjetas/disolver
 */
(function () {
    'use strict';
    const E = window.TQTEscritorio;
    E.registrar({
        id: 'tarjetas', titulo: 'Tarjetas', icono: 'card', grupo: 'operacion', orden: 30,
        montar(host, ctx) {
            const { T, api, h, icon, toast, sheet, util } = ctx;
            const P = ctx.params();
            const st = { tars: null, error: '', estado: ['completa', 'incompleta', 'sin_mac'].includes(P.get('estado')) ? P.get('estado') : '', q: P.get('q') || '', sort: { id: 'num', dir: 'asc' }, sug: null, limit: 200, abierta: P.get('id') ? +P.get('id') : null, sel: new Set() };
            const conFw = (t, s) => { const p = t[s]; return p ? Object.assign({}, p, { firmware: p.firmware || t['firmware_' + s] || null }) : null; };

            const q = h('input', { class: 'input', type: 'search', id: 'tarQ', placeholder: 'Número, serie o MAC', 'aria-label': 'Buscar tarjeta por número, nombre de placa o MAC', 'data-buscar': '1', value: st.q, autocomplete: 'off' });
            const opts = [['', 'Todas'], ...T.TARJETA_ESTADOS.map((g) => [g.key, g.label])];
            const segBtns = opts.map(([v, l]) => h('button', { type: 'button', 'aria-pressed': String(st.estado === v), dataset: { v }, onclick: () => { st.estado = v; st.limit = 200; segBtns.forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.v === v))); lista(); } }, l));
            const info = h('span', { class: 'info', role: 'status', 'aria-live': 'polite' });
            const sugBox = h('section', { class: 'esc-blk', 'aria-labelledby': 'sugT' }); const tw = h('div'); const split = h('div', { class: 'esc-split' }, tw);
            let panel = null;
            const r3Guardado = () => { try { return localStorage.getItem('tqt.r3modo') === 'auto' ? 'auto' : 'manual'; } catch (e) { return 'manual'; } };
            const selR3 = h('select', { class: 'input', id: 'tarR3', 'aria-label': 'Cómo emparejar las R3', title: 'Manual: la R3 se asigna a mano en cada tarjeta. Automática: par e impar por número.',
                onchange: (e) => { try { localStorage.setItem('tqt.r3modo', e.target.value); } catch (er) { /* sin almacenamiento */ } cargarSug(); } },
                h('option', { value: 'manual' }, 'R3 manual'), h('option', { value: 'auto' }, 'R3 automática (par e impar)'));
            selR3.value = r3Guardado();
            const btnEmp = h('button', { class: 'btn btn-primary', type: 'button', onclick: emparejarTodas }, icon('link'), 'Emparejar completas');
            const btnTodas = h('button', { class: 'btn btn-danger', type: 'button', onclick: () => desemparejar(null) }, icon('unlink'), 'Desemparejar todas');
            const btnSel = h('button', { class: 'btn btn-danger', type: 'button', onclick: () => desemparejar([...st.sel]) }, icon('unlink'), 'Desemparejar');
            const btnLimpiar = h('button', { class: 'btn btn-ghost', type: 'button', onclick: () => { st.sel.clear(); lista(); } }, 'Quitar selección');
            const barSel = h('div', { class: 'esc-sel', hidden: true }, h('b', { class: 'cnt' }), h('div', { class: 'grow' }), btnSel, btnLimpiar);
            q.addEventListener('input', T.debounce(() => { st.q = q.value; st.limit = 200; lista(); }, 180));

            const norm = (s) => String(s || '').toLowerCase();
            function filtradas() {
                const txt = norm(st.q).trim(); const hex = txt.replace(/[^0-9a-f]/g, '');
                return st.tars.filter((t) => (!st.dia || st.dia.has(t.id)) && (!st.estado || T.estadoTarjeta(t).key === st.estado)
                    && (!txt || String(t.id_tarjeta_num).includes(txt) || [t.nombre_r1, t.nombre_r2, t.nombre_r3].some((n) => norm(n).includes(txt)) || (hex.length >= 2 && [t.mac_r1, t.mac_r2].some((m) => norm(m).replace(/:/g, '').includes(hex)))));
            }
            const COLS = [
                { id: 'num', titulo: 'Tarjeta', cel: (t) => h('span', { class: 'mono', style: 'font-size:15px;font-weight:600' }, t.id_tarjeta_num), sort: (a, b) => util.cmp(a.id_tarjeta_num, b.id_tarjeta_num) },
                { id: 'r1', titulo: 'R1', cel: (t) => util.placaCelda(conFw(t, 'r1'), 'R1'), valor: (t) => t.nombre_r1 },
                { id: 'r2', titulo: 'R2', cel: (t) => util.placaCelda(conFw(t, 'r2'), 'R2'), valor: (t) => t.nombre_r2 },
                { id: 'r3', titulo: 'R3', cls: 'c-2', cel: (t) => util.placaCelda(t.r3, 'R3'), valor: (t) => t.nombre_r3 },
                { id: 'entrega', titulo: 'Entrega', cls: 'c-3', cel: (t) => (t.fecha_real ? h('span', { class: 'mono' }, t.fecha_real) : h('span', { class: 'muted' }, '—')), valor: (t) => t.fecha_real || '' },
                { id: 'gab', titulo: 'Gabinete', cls: 'c-3', cel: (t) => (t.gabinete ? T.badge(t.gabinete, 'info') : h('span', { class: 'muted' }, '—')), valor: (t) => t.gabinete || '' },
                { id: 'estado', titulo: 'Estado', cel: (t) => T.tarjetaBadge(t), valor: (t) => T.estadoTarjeta(t).label },
                { id: 'acc', titulo: '', sr: 'Acciones', sortable: false, cls: 'act c-3', cel: (t) => h('span', null,
                    h('a', { class: 'btn btn-sm btn-ghost', href: `/dymo?tarjeta_id=${t.id}`, 'aria-label': `Etiqueta DYMO de la tarjeta ${t.id_tarjeta_num}` }, icon('printer'), 'Etiqueta'),
                    h('a', { class: 'btn btn-sm btn-ghost', href: `#/consultar?codigo=${encodeURIComponent((t.r1 || t.r2 || t.r3 || {}).nombre || String(t.id_tarjeta_num))}`, 'aria-label': `Ficha de la tarjeta ${t.id_tarjeta_num}` }, icon('consultar'), 'Ficha')) },
            ];
            function lista() {
                if (!st.tars) return;
                const rows = filtradas();
                const pintarInfo = () => { const n = st.sel.size; info.textContent = n ? `${n} seleccionada${n === 1 ? '' : 's'} de ${rows.length}` : `${rows.length} tarjeta${rows.length === 1 ? '' : 's'}${rows.length !== st.tars.length ? ` de ${st.tars.length}` : ''}`; barSel.hidden = !n; barSel.querySelector('.cnt').textContent = `${n} seleccionada${n === 1 ? '' : 's'}`; };
                pintarInfo(); btnTodas.disabled = !st.tars.length;
                util.pintarTabla(tw, { cols: COLS, rows, key: (t) => t.id, sel: st.sel, onSel: pintarInfo, sort: st.sort, onSort: (id) => { st.sort = util.alternarOrden(st.sort, id); lista(); },
                    onOpen: (t) => abrir(t.id, true), abierta: st.abierta, label: (t) => `Tarjeta ${t.id_tarjeta_num}, ${T.estadoTarjeta(t).label}`, limit: st.limit, onMas: () => { st.limit += 200; lista(); }, caption: 'Tarjetas del lote',
                    vacio: { icono: 'card', titulo: st.tars.length ? 'Ninguna tarjeta coincide' : 'Este lote todavía no tiene tarjetas', texto: st.tars.length ? 'Cambia el estado o la búsqueda.' : 'Las placas por emparejar están arriba, en «Por emparejar». Pulsa «Emparejar completas» o arma una a mano.' } });
            }
            /** Fechas de llegada / finalizado / entrega y gabinete (Quintalock o Translock) de la tarjeta; se guardan en la base y salen al Excel. */
            function bloqueEntrega(t) {
                const hoy = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; };
                const fecha = (id, etq, v) => h('div', { class: 'field' }, h('label', { for: id }, etq), h('input', { class: 'input mono', type: 'date', id, value: v || '' }));
                const iLle = fecha('entLle', 'Llegada', t.fecha_llegada), iFin = fecha('entFin', 'Finalizado', t.fecha_finalizado), iEnt = fecha('entEnt', 'Entrega', t.fecha_real);
                const gab = h('select', { class: 'input', id: 'entGab', 'aria-label': 'Gabinete' }, h('option', { value: '' }, 'Sin definir'),
                    ['Quintalock', 'Translock'].map((g) => h('option', { value: g, selected: t.gabinete === g ? '' : null }, g)));
                async function guardar(extra) {
                    const val = (el) => el.querySelector('input').value;
                    const body = Object.assign({ fecha_llegada: val(iLle), fecha_finalizado: val(iFin), fecha_real: val(iEnt), gabinete: gab.value }, extra || {});
                    const r = await api(`/api/tarjetas/${t.id}`, { method: 'PATCH', body });
                    if (!r.ok) { toast(r.error, { kind: 'bad' }); return; }
                    toast('Entrega guardada', { kind: 'ok' }); ctx.actualizar();
                }
                return h('section', { class: 'esc-entrega', 'aria-label': 'Fechas y entrega', style: 'display:flex;flex-direction:column;gap:10px;margin:12px 0' },
                    h('div', { class: 'silk' }, 'Fechas y entrega'),
                    h('div', { style: 'display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px' }, iLle, iFin, iEnt),
                    h('div', { class: 'field' }, h('label', { for: 'entGab' }, 'Se entrega como'), gab),
                    h('div', { class: 'row', style: 'gap:6px;flex-wrap:wrap' },
                        h('button', { class: 'btn btn-primary btn-sm', type: 'button', onclick: () => guardar() }, icon('check'), 'Guardar'),
                        h('button', { class: 'btn btn-sm', type: 'button', onclick: () => { if (!gab.value) { toast('Elige Quintalock o Translock antes de marcar la entrega', { kind: 'bad' }); gab.focus(); return; } guardar({ fecha_real: hoy() }); } }, icon('box'), 'Marcar entregada hoy')));
            }
            function pintarPanel(enfocar) {
                const t = st.abierta && st.tars ? st.tars.find((x) => x.id === st.abierta) : null;
                if (panel) { panel.remove(); panel = null; }
                split.dataset.panel = t ? '1' : '';
                if (!t) return;
                const num = h('span', { class: 'num' }, t.id_tarjeta_num);
                const cerrar = h('button', { class: 'iconbtn', type: 'button', 'aria-label': 'Cerrar el detalle (Esc)', title: 'Cerrar (Esc)', onclick: () => cerrarPanel(true) }, icon('x'));
                panel = h('section', { class: 'esc-panel', 'aria-labelledby': 'tarPanelT', tabindex: '-1' },
                    h('header', null, h('div', null, h('div', { class: 'silk', style: 'margin-bottom:3px' }, 'Tarjeta'), h('span', { id: 'tarPanelT', class: 'sr-only' }, `Detalle de la tarjeta ${t.id_tarjeta_num}`), num), h('div', { class: 'grow' }), T.tarjetaBadge(t), cerrar),
                    h('div', { class: 'cuerpo' },
                        h('div', { class: 'esc-placas' }, ['r1', 'r2', 'r3'].map((s) => util.placaCard(s.toUpperCase(), conFw(t, s)))),
                        bloqueEntrega(t),
                        window.TQTMateriales ? window.TQTMateriales.bloque(t.id, ctx) : null,
                        h('div', { class: 'acciones' },
                            ['R1', 'R2', 'R3'].map((sl) => h('div', { class: 'row', style: 'gap:6px' },
                                h('button', { class: 'btn btn-sm', type: 'button', onclick: () => elegirPlaca(sl, `${t[sl.toLowerCase()] ? 'Cambiar' : 'Asignar'} ${sl} de la tarjeta ${t.id_tarjeta_num}`, async (np) => {
                                    const r = await api(`/api/tarjetas/${t.id}/asignar`, { method: 'PUT', body: { ranura: sl, pcb_id: np.id } });
                                    if (!r.ok) { toast(r.error, { kind: 'bad' }); return; } toast(`${sl} ${t[sl.toLowerCase()] ? 'cambiada' : 'asignada'}: ${np.nombre}`, { kind: 'ok' }); ctx.actualizar();
                                }) }, icon('link'), `${t[sl.toLowerCase()] ? 'Cambiar' : 'Asignar'} ${sl}`),
                                t[sl.toLowerCase()] ? h('button', { class: 'btn btn-sm btn-ghost', type: 'button', 'aria-label': `Quitar la ${sl} de la tarjeta ${t.id_tarjeta_num}`, onclick: async () => {
                                    const r = await api(`/api/tarjetas/${t.id}/asignar`, { method: 'PUT', body: { ranura: sl, pcb_id: null } });
                                    if (!r.ok) { toast(r.error, { kind: 'bad' }); return; } toast(`${sl} quitada: quedó suelta`, { kind: 'ok' }); ctx.actualizar();
                                } }, icon('unlink'), 'Quitar') : null)),
                            h('a', { class: 'btn btn-primary', href: `/dymo?tarjeta_id=${t.id}` }, icon('printer'), 'Etiqueta DYMO'),
                            h('a', { class: 'btn', href: `#/consultar?codigo=${encodeURIComponent((t.r1 || t.r2 || t.r3 || {}).nombre || String(t.id_tarjeta_num))}` }, icon('consultar'), 'Ver ficha'),
                            h('button', { class: 'btn btn-danger', type: 'button', onclick: () => desemparejar([t.id]) }, icon('unlink'), 'Desemparejar'),
                            h('button', { class: 'btn', type: 'button', onclick: () => util.copiar(util.resumenTarjeta(Object.assign({}, t, { r1: conFw(t, 'r1'), r2: conFw(t, 'r2') })), 'Datos copiados') }, icon('paste'), 'Copiar datos'))));
                split.append(panel);
                if (enfocar) panel.focus({ preventScroll: true });
            }
            function abrir(id, enfocar) {
                st.abierta = id; lista(); pintarPanel(enfocar);
                const url = `#/tarjetas?id=${id}`; if (location.hash !== url) history.replaceState(null, '', url);
            }
            function cerrarPanel(volver) {
                const id = st.abierta; st.abierta = null; lista(); pintarPanel(false);
                if (location.hash.startsWith('#/tarjetas?id=')) history.replaceState(null, '', '#/tarjetas');
                if (volver && id !== null) { const tr = [...tw.querySelectorAll('tr[data-k]')].find((x) => x.dataset.k === String(id)); if (tr) tr.focus(); }
            }
            const onEsc = (e) => { if (e.key === 'Escape' && st.abierta && !document.querySelector('.sheet') && panel && (panel.contains(document.activeElement) || tw.contains(document.activeElement) || document.activeElement === document.body)) { e.preventDefault(); cerrarPanel(true); } };
            document.addEventListener('keydown', onEsc);

            // ---- por emparejar (vista previa de lo que hará «Emparejar completas») y armado a mano
            async function cargarSug() {
                const r = await api(`/api/emparejar/sugerencias?r3=${selR3.value}${loteId() ? `&lote_id=${loteId()}` : ''}`);
                st.sug = r.ok ? r.data : null; pintarSug(r.ok ? '' : r.error);
            }
            function pintarSug(error) {
                const g = st.sug;
                if (!g) { sugBox.replaceChildren(h('div', { class: 'esc-h' }, h('h2', { id: 'sugT' }, 'Por emparejar')), error ? util.errorBox(error, cargarSug) : util.cargando('Leyendo las placas sueltas…')); return; }
                const sueltas = ['R1', 'R2', 'R3'].map((tp) => (g.sueltas[tp] || []).length);
                const imp = g.impares || [];
                const filas = [...g.completas.map((x) => Object.assign({ tipo: 'Pareja' }, x)), ...imp.map((x) => Object.assign({ tipo: 'Impar' }, x))];
                const cols = [
                    { id: 'n', titulo: 'Tarjeta', cel: (x) => h('span', { class: 'mono', style: 'font-weight:600' }, x.id_tarjeta_num), sort: (a, b) => util.cmp(a.id_tarjeta_num, b.id_tarjeta_num) },
                    { id: 't', titulo: 'Tipo', cel: (x) => T.badge(x.tipo, x.tipo === 'Pareja' ? 'ok' : 'info'), valor: (x) => x.tipo },
                    { id: 'r1', titulo: 'R1', cel: (x) => util.placaCelda(x.r1, 'R1'), sortable: false },
                    { id: 'r2', titulo: 'R2', cel: (x) => util.placaCelda(x.r2, 'R2'), sortable: false },
                    { id: 'r3', titulo: 'R3', cls: 'c-2', cel: (x) => (x.r3 ? util.placaCelda(x.r3, 'R3') : h('span', { class: 'muted' }, selR3.value === 'auto' ? 'sin R3' : 'a mano')), sortable: false },
                    { id: 'acc', titulo: '', sr: 'Acciones', sortable: false, cls: 'act', cel: (x) => (x.tipo === 'Pareja' ? h('button', { class: 'btn btn-sm', type: 'button', 'aria-label': `Unir la tarjeta ${x.id_tarjeta_num}`, onclick: () => unir(x.serie) }, icon('link'), 'Unir') : null) },
                ];
                const tabla = h('div');
                const pl = (n, uno, varios) => `${n} ${n === 1 ? uno : varios}`;
                sugBox.replaceChildren(
                    h('div', { class: 'esc-h' }, h('h2', { id: 'sugT' }, 'Por emparejar')),
                    h('p', { class: 'muted' }, `Placas sueltas: ${sueltas[0]} R1 · ${sueltas[1]} R2 · ${sueltas[2]} R3. Se crearán ${pl(g.completas.length, 'pareja', 'parejas')} y ${pl(imp.length, 'impar', 'impares')}`
                        + (g.r3_pendientes && g.r3_pendientes.length ? `, y se montarán ${g.r3_pendientes.length} R3 en tarjetas existentes` : '') + '. '
                        + (selR3.value === 'manual' ? 'La R3 se asigna a mano en cada tarjeta.' : '')),
                    filas.length ? tabla : h('p', { class: 'muted' }, sueltas[0] + sueltas[1] + sueltas[2] ? 'No hay R1 y R2 por emparejar; las sueltas se pueden armar a mano.' : 'No hay placas sueltas: recíbelas y confírmalas con el celular.'),
                    h('div', { class: 'row wrap' }, h('button', { class: 'btn', type: 'button', onclick: armarMano }, icon('plus'), 'Armar a mano (impar)')));
                if (filas.length) util.pintarTabla(tabla, { cols, rows: filas, key: (x) => x.id_tarjeta_num, sort: { id: 'n', dir: 'asc' }, onSort: () => {}, label: (x) => `Tarjeta ${x.id_tarjeta_num}`, limit: 50, onMas: () => {}, caption: 'Tarjetas que se crearán al emparejar' });
            }
            async function unir(serie) {
                const r = await api('/api/emparejar/auto', { method: 'POST', body: { lote_id: loteId(), series: [serie], r3: selR3.value } });
                if (!r.ok) { toast(r.error || 'No se pudo unir', { kind: 'bad' }); return; }
                const n = (r.data.creadas || []).length; toast(n ? `Tarjeta ${serie} creada` : `No se pudo unir ${serie}: ${(r.data.omitidas[0] || {}).motivo || ''}`, { kind: n ? 'ok' : 'bad' }); ctx.actualizar();
            }
            /** Elige una placa DISPONIBLE del tipo dado (lista con búsqueda). */
            function elegirPlaca(tipo, titulo, onPick) {
                const busca = h('input', { class: 'input', type: 'search', placeholder: 'Buscar por número', 'aria-label': 'Buscar placa', autocomplete: 'off' });
                const lst = h('div', { class: 'stack', style: 'max-height:42vh;overflow:auto;gap:4px' });
                let items = []; let sh = null;
                const pinta = () => {
                    const q2 = busca.value.trim().toLowerCase();
                    const rows = items.filter((p) => !q2 || p.nombre.toLowerCase().includes(q2));
                    lst.replaceChildren(...(rows.length ? rows.map((p) => h('button', { class: 'btn btn-ghost', type: 'button', style: 'justify-content:flex-start', onclick: () => { sh.close(); onPick(p); } }, T.tipoChip(p.tipo), h('span', { class: 'mono' }, p.nombre)))
                        : [h('p', { class: 'muted' }, `No hay ${tipo} sueltas${q2 ? ' con esa búsqueda' : ''}.`)]));
                };
                busca.addEventListener('input', pinta);
                sh = sheet({ title: titulo, body: [busca, lst], actions: [{ label: 'Cancelar', kind: 'ghost', onClick: () => true }] });
                api(`/api/pcb?tipo=${tipo}&estado_ciclo=DISPONIBLE&limit=1000`).then((r) => { items = (r.ok && r.data && r.data.items) || []; pinta(); });
            }
            function armarMano() {
                const pick = { R1: null, R2: null, R3: null }; const err = h('div', { class: 'hint err', role: 'alert' });
                const num = h('input', { class: 'input mono', id: 'amNum', inputmode: 'numeric', maxlength: 4, placeholder: 'Igual al de la R1', 'aria-label': 'Número de tarjeta' });
                num.addEventListener('input', () => { num.value = num.value.replace(/\D/g, ''); num.dataset.tocado = '1'; });
                const fila = (sl) => {
                    const nm = h('span', { class: 'mono' }, 'Sin elegir');
                    return h('div', { class: 'row', style: 'gap:10px' }, T.tipoChip(sl, { empty: true }), nm, h('div', { class: 'grow' }),
                        h('button', { class: 'btn btn-sm', type: 'button', onclick: () => elegirPlaca(sl, `Elegir ${sl}`, (p) => { pick[sl] = p; nm.textContent = p.nombre; if (sl === 'R1' && !num.dataset.tocado) num.value = p.serie; }) }, 'Elegir'));
                };
                sheet({ title: 'Armar tarjeta a mano', body: [h('p', { class: 'hint' }, 'Sirve para tarjetas impares: cualquier R1, R2 y R3 sueltas, aunque tengan números distintos.'), fila('R1'), fila('R2'), fila('R3'),
                    h('div', { class: 'field' }, h('label', { for: 'amNum' }, 'Número de tarjeta'), num), err],
                actions: [{ label: 'Cancelar', kind: 'ghost', onClick: () => true }, { label: 'Crear tarjeta', kind: 'primary', keepOpen: true, onClick: async () => {
                    err.textContent = ''; if (!pick.R1 && !pick.R2 && !pick.R3) { err.textContent = 'Elige al menos una placa.'; return false; }
                    const body = { lote_id: loteId(), r1_id: pick.R1 && pick.R1.id, r2_id: pick.R2 && pick.R2.id, r3_id: pick.R3 && pick.R3.id };
                    if (num.value) body.id_tarjeta_num = num.value.padStart(4, '0');
                    const r = await api('/api/tarjetas', { method: 'POST', body }); if (!r.ok) { err.textContent = r.error; return false; }
                    toast(`Tarjeta ${r.data.id_tarjeta_num} creada`, { kind: 'ok' }); ctx.actualizar(); return true;
                } }] });
            }

            // ---- emparejar / desemparejar
            const loteId = () => (ctx.lote() ? ctx.lote().id : undefined);
            async function emparejarTodas() {
                btnEmp.disabled = true;
                try {
                    const r = await api('/api/emparejar/auto', { method: 'POST', body: { lote_id: loteId(), r3: selR3.value } });
                    if (!r.ok) { toast(r.error || 'No se pudo emparejar', { kind: 'bad' }); return; }
                    const n = ((r.data && r.data.creadas) || []).length; const n3 = ((r.data && r.data.r3_asignadas) || []).length; const om = (r.data && r.data.omitidas) || [];
                    toast(n || n3 ? [n ? `${n} tarjeta${n === 1 ? '' : 's'} creada${n === 1 ? '' : 's'}` : '', n3 ? `${n3} R3 montada${n3 === 1 ? '' : 's'}` : ''].filter(Boolean).join(' · ') : 'No hay nada por emparejar (R1 + R2 confirmadas)', { kind: n || n3 ? 'ok' : 'bad' });
                    if (om.length) toast(`${om.length} omitida${om.length === 1 ? '' : 's'}: ${om.slice(0, 3).map((o) => `${o.serie} (${o.motivo})`).join(', ')}`, { ms: 5000 });
                    ctx.actualizar();
                } finally { btnEmp.disabled = false; }
            }
            /** ids = lista de tarjetas; null = todas las del lote. */
            function desemparejar(ids) {
                const items = ids ? st.tars.filter((t) => ids.includes(t.id)) : st.tars;
                if (!items.length) return;
                const forzar = h('input', { type: 'checkbox', id: 'desForzar' });
                const err = h('div', { class: 'hint err', role: 'alert' });
                const nums = items.slice(0, 12).map((t) => t.id_tarjeta_num).join(', ') + (items.length > 12 ? ` y ${items.length - 12} más` : '');
                const n = items.length;
                sheet({ title: ids ? `¿Desemparejar ${n} tarjeta${n === 1 ? '' : 's'}?` : `¿Desemparejar TODAS las tarjetas (${n})?`, body: [
                    h('p', null, 'Las placas R1/R2/R3 vuelven al inventario como sueltas y se pueden emparejar otra vez. Las placas y sus MAC no se borran.'),
                    h('p', { class: 'mono muted', style: 'max-height:96px;overflow:auto' }, nums),
                    h('label', { class: 'esc-chk', for: 'desForzar' }, forzar, 'Incluir las que ya tienen pruebas registradas'), err],
                actions: [{ label: 'Conservar', kind: 'ghost', onClick: () => true }, { label: `Desemparejar ${n}`, kind: 'danger', keepOpen: true, onClick: async () => {
                    const body = ids ? { ids, forzar: forzar.checked } : { todas: true, lote_id: loteId(), forzar: forzar.checked };
                    const r = await api('/api/tarjetas/disolver', { method: 'POST', body });
                    if (!r.ok) { err.textContent = r.error; return false; }
                    const d = r.data.disueltas.length; const om = r.data.omitidas.length;
                    st.sel.clear(); if (st.abierta && r.data.disueltas.some((x) => x.id === st.abierta)) st.abierta = null;
                    toast(`${d} tarjeta${d === 1 ? '' : 's'} desemparejada${d === 1 ? '' : 's'}: ${r.data.liberadas} placa${r.data.liberadas === 1 ? '' : 's'} quedaron sueltas${om ? `; ${om} omitida${om === 1 ? '' : 's'} (tienen pruebas)` : ''}`, { kind: om && !d ? 'bad' : 'ok' });
                    ctx.actualizar(); return true;
                } }] });
            }

            async function cargar(mostrar) {
                if (mostrar && !st.tars) tw.replaceChildren(util.cargando('Cargando las tarjetas…'));
                try { st.tars = await ctx.tarjetas(); st.error = ''; } catch (e) { st.error = e.message; }
                if (st.error && !st.tars) { tw.replaceChildren(util.errorBox(st.error, () => cargar(true))); return; }
                if (st.abierta && !st.tars.find((t) => t.id === st.abierta)) st.abierta = null;
                lista(); pintarPanel(false); cargarSug(); if (diaIn.value) reporteDia();
            }
            // ---- reporte por fecha (v1.3.35): completadas (fecha de finalizado) y entregadas (fecha real) ese día, de todos los lotes
            const hoy = new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10);
            const diaIn = h('input', { class: 'input', type: 'date', id: 'tarDia', value: P.get('fecha') || '', max: hoy, 'aria-label': 'Fecha del reporte' });
            const diaRes = h('div', { class: 'esc-dia-res', role: 'status', 'aria-live': 'polite' });
            const btnXls = h('a', { class: 'btn btn-primary', hidden: true, download: '' }, icon('download'), 'Exportar Excel');
            const btnMailDia = T.botonCorreo(() => (diaIn.value ? { tipo: 'reporte_dia', fecha: diaIn.value, titulo: `Reporte de tarjetas del ${diaIn.value}` } : null));
            const btnQuitarDia = h('button', { class: 'btn btn-ghost', type: 'button', hidden: true, onclick: () => { diaIn.value = ''; reporteDia(); } }, 'Quitar fecha');
            const kpiDia = (n, t, cls) => h('div', { class: 'esc-dia-kpi ' + cls }, h('b', {}, String(n)), h('span', {}, t));
            async function reporteDia() {
                const f = diaIn.value; st.dia = null; btnXls.hidden = btnQuitarDia.hidden = btnMailDia.hidden = !f;
                if (!f) { diaRes.replaceChildren(h('span', { class: 'muted' }, 'Elige un día para ver cuántas tarjetas se completaron o entregaron.')); lista(); return; }
                diaRes.replaceChildren(h('span', { class: 'muted' }, 'Consultando…'));
                const r = await api(`/api/reporte-dia?fecha=${f}`);
                if (!r.ok) { diaRes.replaceChildren(h('span', { class: 'hint err' }, r.error)); lista(); return; }
                const d = r.data; st.dia = new Set(d.items.map((t) => t.id));
                const enLote = st.tars ? st.tars.filter((t) => st.dia.has(t.id)).length : 0;
                btnXls.href = `/api/reporte-dia/excel?fecha=${f}`; btnXls.setAttribute('download', `Tarjetas_${f}.xlsx`);
                diaRes.replaceChildren(kpiDia(d.completadas, 'completadas', 'ok'), kpiDia(d.entregadas, 'entregadas', 'info'),
                    h('span', { class: 'muted' }, d.items.length ? `${enLote} de ${d.items.length} en este lote · la tabla muestra solo esas` : 'Sin movimientos ese día'));
                lista();
            }
            diaIn.addEventListener('change', reporteDia);
            const diaBox = h('section', { class: 'esc-blk esc-dia', 'aria-label': 'Reporte por fecha' },
                h('div', { class: 'esc-dia-bar' }, h('label', { for: 'tarDia', class: 'esc-dia-lbl' }, icon('clock'), 'Reporte por fecha'), diaIn, diaRes, h('div', { class: 'grow' }), btnQuitarDia, btnXls, btnMailDia));
            host.append(h('div', { class: 'esc-bar' }, h('div', { class: 'esc-buscar' }, icon('search'), q), h('div', { class: 'esc-seg', role: 'group', 'aria-label': 'Estado de la tarjeta' }, segBtns), h('div', { class: 'grow' }), selR3, btnEmp, btnTodas, info), diaBox, barSel, sugBox, split);
            reporteDia();
            cargar(true);
            return {
                actualizar() { cargar(false); },
                parametros(p) { const id = +p.get('id') || null; if (id !== st.abierta) { st.abierta = id; lista(); pintarPanel(false); } if (p.get('estado') !== null) { st.estado = p.get('estado') || ''; segBtns.forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.v === st.estado))); lista(); } },
                desmontar() { document.removeEventListener('keydown', onEsc); },
            };
        },
    });
})();
