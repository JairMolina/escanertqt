/**
 * sec_inventario.js - Inventario de PCB: filtros (tipo, estado, hardware, sin MAC, búsqueda), orden, selección múltiple,
 * edición de una placa, cambio de versión de hardware en masa y eliminación con confirmación en pantalla.
 * API: GET /api/pcb · PATCH/DELETE /api/pcb/{id} · PUT /api/pcb/{id}/mac|firmware · POST /api/pcb/version · GET /api/firmware
 */
(function () {
    'use strict';
    const E = window.TQTEscritorio;
    E.registrar({
        id: 'inventario', titulo: 'Inventario de PCB', icono: 'box', grupo: 'gestion', orden: 52,
        montar(host, ctx) {
            const { T, api, h, icon, toast, sheet, util } = ctx;
            const P = ctx.params();
            const st = { pcbs: null, error: '', tipo: ['R1', 'R2', 'R3'].includes(P.get('tipo')) ? P.get('tipo') : '', ciclo: P.get('estado') || '', ver: '', sinMac: P.get('sin_mac') === '1', q: P.get('q') || '', sort: { id: 'nombre', dir: 'asc' }, limit: 200, sel: new Set() };
            const CICLOS = [['RECIBIDA', 'Sin confirmar'], ['DISPONIBLE', 'Sueltas'], ['PROGRAMADA', 'Programadas'], ['ASIGNADA', 'Asignadas'], ['FALLA', 'Falla'], ['BAJA', 'Baja']];

            const q = h('input', { class: 'input', type: 'search', id: 'invQ', placeholder: 'Serie, nombre o MAC', 'aria-label': 'Buscar placa por serie, nombre o MAC', 'data-buscar': '1', value: st.q, autocomplete: 'off' });
            const segBtns = [['', 'Todas'], ['R1', 'R1'], ['R2', 'R2'], ['R3', 'R3']].map(([v, l]) => h('button', { type: 'button', 'aria-pressed': String(st.tipo === v), dataset: { v }, onclick: () => { st.tipo = v; st.limit = 200; segBtns.forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.v === v))); lista(); } }, l));
            const selCiclo = h('select', { class: 'input', id: 'invCiclo', 'aria-label': 'Estado de la placa', onchange: (e) => { st.ciclo = e.target.value; st.limit = 200; lista(); } },
                h('option', { value: '' }, 'Todos los estados'), CICLOS.map(([v, l]) => h('option', { value: v, selected: st.ciclo === v ? '' : null }, l)));
            const selVer = h('select', { class: 'input', id: 'invVer', 'aria-label': 'Versión de hardware', onchange: (e) => { st.ver = e.target.value; st.limit = 200; lista(); } }, h('option', { value: '' }, 'Todo el hardware'));
            const chkMac = h('input', { type: 'checkbox', id: 'invSinMac', checked: st.sinMac ? '' : null, onchange: (e) => { st.sinMac = e.target.checked; st.limit = 200; lista(); } });
            const info = h('span', { class: 'info', role: 'status', 'aria-live': 'polite' });
            const btnVer = h('button', { class: 'btn', type: 'button', 'data-escribe': true, onclick: versionMasa }, icon('edit'), 'Cambiar hardware');
            const btnDel = h('button', { class: 'btn btn-danger', type: 'button', 'data-escribe': true, onclick: eliminarMasa }, icon('trash'), 'Eliminar');
            const btnLimpiar = h('button', { class: 'btn btn-ghost', type: 'button', onclick: () => { st.sel.clear(); lista(); } }, 'Quitar selección');
            const barSel = h('div', { class: 'esc-sel', hidden: true }, h('b', { class: 'cnt' }), h('div', { class: 'grow' }), btnVer, btnDel, btnLimpiar);
            const tw = h('div');
            q.addEventListener('input', T.debounce(() => { st.q = q.value; st.limit = 200; lista(); }, 180));

            const norm = (s) => String(s || '').toLowerCase();
            function filtradas() {
                const txt = norm(st.q).trim(); const hex = txt.replace(/[^0-9a-f]/g, '');
                return st.pcbs.filter((p) => (!st.tipo || p.tipo === st.tipo) && (!st.ciclo || (st.ciclo === 'PROGRAMADA' ? T.programada(p) && ['RECIBIDA', 'DISPONIBLE'].includes(p.estado_ciclo) : p.estado_ciclo === st.ciclo)) && (!st.ver || p.version === st.ver)
                    && (!st.sinMac || (p.tipo !== 'R3' && !p.mac && ['RECIBIDA', 'DISPONIBLE', 'ASIGNADA'].includes(p.estado_ciclo)))
                    && (!txt || norm(p.nombre).includes(txt) || String(p.serie).includes(txt) || (hex.length >= 2 && norm(p.mac).replace(/:/g, '').includes(hex))));
            }
            const COLS = [
                { id: 'tipo', titulo: 'Tipo', cel: (p) => T.tipoChip(p.tipo), valor: (p) => p.tipo },
                { id: 'nombre', titulo: 'Nombre', cel: (p) => h('span', { class: 'mono' }, p.nombre), sort: (a, b) => util.cmp(a.serie, b.serie) || util.cmp(a.tipo, b.tipo) },
                { id: 'version', titulo: 'Hardware', cel: (p) => h('span', { class: 'mono' }, 'V' + p.version), sort: (a, b) => (+a.version) - (+b.version) },
                { id: 'firmware', titulo: 'Firmware', cel: (p) => (p.firmware ? h('span', { class: 'mono' }, p.firmware) : h('span', { class: 'muted' }, 'sin firmware')), valor: (p) => p.firmware || '' },
                { id: 'mac', titulo: 'MAC', cel: (p) => (p.tipo === 'R3' ? h('span', { class: 'muted' }, 'no aplica') : p.mac ? h('span', { class: 'mono' }, String(p.mac).toLowerCase()) : h('span', { class: 'muted' }, 'sin MAC')), valor: (p) => (p.tipo === 'R3' ? '' : p.mac) },
                { id: 'estado_ciclo', titulo: 'Estado', cel: (p) => T.cicloBadge(p.estado_ciclo, p) },
                { id: 'tarjeta', titulo: 'Tarjeta', cls: 'c-3', cel: (p) => (p.id_tarjeta_num ? h('a', { class: 'mono', href: `#/tarjetas?id=${p.tarjeta_id}` }, p.id_tarjeta_num) : h('span', { class: 'muted' }, '—')), valor: (p) => p.id_tarjeta_num },
                { id: 'recibida_en', titulo: 'Recibida', cls: 'c-2', cel: (p) => h('span', { class: 'mono' }, util.fecha(p.recibida_en)), valor: (p) => p.recibida_en },
                { id: 'acc', titulo: '', sr: 'Acciones', sortable: false, cls: 'act', cel: (p) => h('button', { class: 'btn btn-sm btn-ghost', type: 'button', 'data-escribe': true, 'aria-label': `Editar ${p.nombre}`, onclick: () => editar(p) }, icon('edit'), 'Editar') },
            ];
            function pintarInfo(n) {
                const s = st.sel.size;
                info.textContent = s ? `${s} seleccionada${s === 1 ? '' : 's'} de ${n}` : `${n} placa${n === 1 ? '' : 's'}${st.pcbs && n !== st.pcbs.length ? ` de ${st.pcbs.length}` : ''}`;
                barSel.hidden = !s; barSel.querySelector('.cnt').textContent = `${s} seleccionada${s === 1 ? '' : 's'}`;
            }
            function lista() {
                if (!st.pcbs) return;
                const rows = filtradas();
                pintarInfo(rows.length);
                util.pintarTabla(tw, { cols: COLS, rows, key: (p) => p.id, sel: st.sel, onSel: () => pintarInfo(rows.length), sort: st.sort, onSort: (id) => { st.sort = util.alternarOrden(st.sort, id); lista(); },
                    onOpen: editar, label: (p) => p.nombre, limit: st.limit, onMas: () => { st.limit += 200; lista(); }, caption: 'Inventario de placas',
                    vacio: { icono: 'box', titulo: st.pcbs.length ? 'Ninguna placa coincide con los filtros' : 'Todavía no hay placas', texto: st.pcbs.length ? 'Cambia el tipo, el estado o la búsqueda.' : 'Aparecen aquí cuando se reciben con el celular.' } });
            }
            function opcionesVersion() {
                const cur = selVer.value; const vs = [...new Set(st.pcbs.map((p) => p.version))].sort((a, b) => a - b);
                selVer.replaceChildren(h('option', { value: '' }, 'Todo el hardware'), vs.map((v) => h('option', { value: v, selected: v === cur ? '' : null }, 'Hardware V' + v)));
                if (cur && !vs.includes(cur)) st.ver = '';
            }

            // ---- editar una placa
            async function editar(p) {
                if (T.acceso.rol === 'consultor') { T.avisoAcceso('accion', 'Tu cuenta es de consulta: puede ver el inventario, pero no editar ni eliminar placas.'); return; }   // v1.3.44
                let tipo = p.tipo; let armado = false;
                const cat = await api('/api/firmware');   // la R3 también lleva firmware (no MAC)
                const opciones = cat && cat.ok && cat.data ? (cat.data[p.tipo] || []) : [];
                const inVer = h('input', { class: 'input mono', id: 'eVer', inputmode: 'numeric', maxlength: 3, value: p.version });
                const inSer = h('input', { class: 'input mono', id: 'eSer', inputmode: 'numeric', maxlength: 4, value: p.serie });
                const err = h('div', { class: 'hint err', role: 'alert' });
                const prev = h('div', { class: 'mono', style: 'font-weight:600;font-size:17px' });
                const montada = p.estado_ciclo === 'ASIGNADA';
                const aviso = h('p', { class: 'hint', hidden: true }, `Al guardar, ${p.nombre} sale de la tarjeta ${p.id_tarjeta_num} y queda suelta con su nuevo tipo; vuelve a emparejarla después.`);
                const upd = () => { prev.textContent = T.nombreDe(tipo, inVer.value || '?', inSer.value || '?'); aviso.hidden = !(montada && tipo !== p.tipo); };
                const segB = ['R1', 'R2', 'R3'].map((t) => h('button', { type: 'button', 'aria-pressed': String(t === tipo), onclick: () => { tipo = t; segB.forEach((b, i) => b.setAttribute('aria-pressed', String(['R1', 'R2', 'R3'][i] === t))); upd(); } }, t));
                [inVer, inSer].forEach((i) => i.addEventListener('input', () => { i.value = i.value.replace(/\D/g, ''); upd(); }));
                upd();
                const macIn = p.tipo === 'R3' ? null : h('input', { class: 'input mono', id: 'eMac', maxlength: 17, placeholder: 'sin MAC', value: p.mac ? String(p.mac).toLowerCase() : '' });
                if (macIn) macIn.addEventListener('input', () => { macIn.value = T.formatMacProgress(macIn.value).toLowerCase(); });
                const fwSel = h('select', { class: 'input', id: 'eFw' }, h('option', { value: '' }, 'Sin firmware'),
                    [...new Set([...opciones, ...(p.firmware ? [p.firmware] : [])])].map((v) => h('option', { value: v, selected: v === p.firmware ? '' : null }, v)),
                    h('option', { value: '__otra' }, 'Otra versión…'));
                // v1.3.44: si el catálogo no tiene la versión (p. ej. R3 sin catálogo), se escribe a mano
                const fwOtra = h('input', { class: 'input mono', id: 'eFwOtra', maxlength: 40, placeholder: 'Versión de firmware, ej. 2.1', hidden: true, autocomplete: 'off', 'aria-label': 'Otra versión de firmware' });
                fwSel.addEventListener('change', () => { fwOtra.hidden = fwSel.value !== '__otra'; if (!fwOtra.hidden) fwOtra.focus(); });
                const fwValor = () => (fwSel.value === '__otra' ? fwOtra.value.trim() : fwSel.value);
                const s = sheet({
                    title: `Editar ${p.nombre}`,
                    body: [
                        h('div', { class: 'field' }, h('span', { class: 'lbl' }, 'Tipo'), h('div', { class: 'seg', role: 'group', 'aria-label': 'Tipo de placa' }, segB)),
                        h('div', { class: 'row' }, h('div', { class: 'field grow' }, h('label', { for: 'eVer' }, 'Hardware (V)'), inVer), h('div', { class: 'field grow' }, h('label', { for: 'eSer' }, 'Serie'), inSer)),
                        macIn ? h('div', { class: 'field' }, h('label', { for: 'eMac' }, 'MAC'), macIn) : null,
                        h('div', { class: 'field' }, h('label', { for: 'eFw' }, 'Firmware'), fwSel, fwOtra),
                        macIn ? null : h('p', { class: 'hint' }, 'La R3 no lleva MAC.'),
                        h('div', { class: 'field' }, h('span', { class: 'lbl' }, 'Quedará como'), prev),
                        montada ? h('p', { class: 'hint' }, `Está en la tarjeta ${p.id_tarjeta_num}: el cambio se refleja allí y en el Excel.`) : null, aviso, err,
                    ],
                    actions: [
                        { label: 'Eliminar', kind: 'danger', icon: 'trash', keepOpen: 'always', onClick: async (btn) => {
                            if (!armado) {
                                armado = true; err.textContent = `Se eliminará ${p.nombre}. No se puede deshacer. Pulsa otra vez para confirmar.`; btn.lastChild.textContent = 'Confirmar y eliminar';
                                setTimeout(() => { armado = false; if (btn.isConnected) { btn.lastChild.textContent = 'Eliminar'; err.textContent = ''; } }, 6000);
                                return false;
                            }
                            const r = await api(`/api/pcb/${p.id}`, { method: 'DELETE' });
                            if (!r.ok && r.status !== 204) { err.textContent = r.status === 409 ? `${p.nombre} está montada en una tarjeta. Sácala de la tarjeta antes de eliminarla.` : r.error; return false; }
                            toast(`${p.nombre} eliminada`, { kind: 'ok' }); st.sel.delete(p.id); ctx.actualizar(); s.close(); return false;
                        } },
                        { label: 'Guardar', kind: 'primary', keepOpen: true, onClick: async () => {
                            err.textContent = ''; const body = {};
                            if (tipo !== p.tipo) { body.tipo = tipo; if (montada) body.liberar = true; }
                            if (inVer.value !== p.version) body.version = inVer.value;
                            if (inSer.value !== p.serie) body.serie = inSer.value.padStart(4, '0');
                            if (Object.keys(body).length) { const r = await api(`/api/pcb/${p.id}`, { method: 'PATCH', body }); if (!r.ok) { err.textContent = r.error; return false; } }
                            if (macIn && (macIn.value || '').toLowerCase() !== (p.mac || '').toLowerCase()) {
                                const m = macIn.value ? T.parseMac(macIn.value) : null;
                                if (macIn.value && !m) { err.textContent = 'La MAC está incompleta: son 12 dígitos (0-9, A-F).'; return false; }
                                const r = await api(`/api/pcb/${p.id}/mac`, { method: 'PUT', body: { mac: m } }); if (!r.ok) { err.textContent = r.error; return false; }
                            }
                            if (fwSel.value === '__otra' && !fwValor()) { err.textContent = 'Escribe la versión de firmware.'; fwOtra.focus(); return false; }
                            if (fwSel && (fwValor() || '') !== (p.firmware || '')) { const r = await api(`/api/pcb/${p.id}/firmware`, { method: 'PUT', body: { firmware: fwValor() || null } }); if (!r.ok) { err.textContent = r.error; return false; } }
                            toast('Cambios guardados', { kind: 'ok' }); ctx.actualizar(); return true;
                        } },
                    ],
                });
            }

            // ---- acciones en masa
            function versionMasa() {
                const ids = [...st.sel]; const inp = h('input', { class: 'input mono', id: 'mVer', inputmode: 'numeric', maxlength: 3, placeholder: '30' }); const err = h('div', { class: 'hint err', role: 'alert' });
                inp.addEventListener('input', () => { inp.value = inp.value.replace(/\D/g, ''); });
                sheet({ title: `Cambiar el hardware de ${ids.length} placa${ids.length === 1 ? '' : 's'}`, body: [h('div', { class: 'field' }, h('label', { for: 'mVer' }, 'Nueva versión de hardware (V)'), inp), h('p', { class: 'hint' }, 'Se cambia el V de los nombres (por ejemplo TQT-R1-V30-0021 pasa a V31). Si una choca con otra placa, no se cambia ninguna.'), err],
                    actions: [{ label: 'Cancelar', kind: 'ghost', onClick: () => true }, { label: 'Aplicar', kind: 'primary', keepOpen: true, onClick: async () => {
                        if (!inp.value) { err.textContent = 'Escribe la versión de hardware, por ejemplo 30.'; return false; }
                        const r = await api('/api/pcb/version', { method: 'POST', body: { ids, version: inp.value } });
                        if (!r.ok) { err.textContent = r.error; return false; }
                        st.sel.clear(); toast(`Hardware V${inp.value} aplicado a ${ids.length}`, { kind: 'ok' }); ctx.actualizar(); return true;
                    } }] });
            }
            function eliminarMasa() {
                const ids = [...st.sel]; const items = st.pcbs.filter((p) => st.sel.has(p.id)); const err = h('div', { class: 'hint err', role: 'alert' });
                const asignadas = items.filter((p) => p.estado_ciclo === 'ASIGNADA').length;
                sheet({ title: `¿Eliminar ${ids.length} placa${ids.length === 1 ? '' : 's'}?`, body: [
                    h('p', null, 'Se quitan del inventario y no se pueden recuperar.'),
                    asignadas ? T.banner('warn', 'alert', `${asignadas} está${asignadas === 1 ? '' : 'n'} montada${asignadas === 1 ? '' : 's'} en una tarjeta y no se ${asignadas === 1 ? 'eliminará' : 'eliminarán'}: primero sácala${asignadas === 1 ? '' : 's'} de la tarjeta.`) : null,
                    h('p', { class: 'mono muted', style: 'max-height:96px;overflow:auto' }, items.slice(0, 12).map((p) => p.nombre).join(', ') + (items.length > 12 ? ` y ${items.length - 12} más` : '')), err],
                    actions: [{ label: 'Conservar', kind: 'ghost', onClick: () => true }, { label: `Eliminar ${ids.length}`, kind: 'danger', keepOpen: true, onClick: async () => {
                        let ok = 0, fail = 0;
                        for (const id of ids) { const r = await api(`/api/pcb/${id}`, { method: 'DELETE' }); if (r.ok || r.status === 204) { ok++; st.sel.delete(id); } else fail++; }
                        toast(`${ok} eliminada${ok === 1 ? '' : 's'}${fail ? `; ${fail} no se pudieron eliminar (montadas en una tarjeta)` : ''}`, { kind: fail ? 'bad' : 'ok' }); ctx.actualizar(); return true;
                    } }] });
            }

            async function cargar(mostrar) {
                if (mostrar && !st.pcbs) tw.replaceChildren(util.cargando('Cargando el inventario…'));
                try { st.pcbs = await ctx.pcbs(); st.error = ''; } catch (e) { st.error = e.message; }
                if (st.error && !st.pcbs) { tw.replaceChildren(util.errorBox(st.error, () => cargar(true))); return; }
                const ids = new Set(st.pcbs.map((p) => p.id)); [...st.sel].forEach((i) => { if (!ids.has(i)) st.sel.delete(i); });
                opcionesVersion(); lista();
            }

            host.append(
                h('div', { class: 'esc-bar' },
                    h('div', { class: 'esc-buscar' }, icon('search'), q),
                    h('div', { class: 'esc-seg', role: 'group', 'aria-label': 'Tipo de placa' }, segBtns), selCiclo, selVer,
                    h('label', { class: 'esc-chk', for: 'invSinMac' }, chkMac, 'Solo sin MAC'), h('div', { class: 'grow' }), info),
                barSel, tw);
            cargar(true);
            return {
                actualizar() { cargar(false); },
                parametros(p) { st.tipo = p.get('tipo') || ''; st.ciclo = p.get('estado') || ''; st.sinMac = p.get('sin_mac') === '1'; st.q = p.get('q') || ''; q.value = st.q; selCiclo.value = st.ciclo; chkMac.checked = st.sinMac; segBtns.forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.v === st.tipo))); lista(); },
            };
        },
    });
})();
