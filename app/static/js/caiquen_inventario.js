/* caiquen_inventario.js - Pestaña Inventario: filtros (búsqueda, estado, hardware, firmware, lote con conteo), tabla que en
 * móvil se vuelve lista, selección múltiple acotada a lo filtrado, acciones en masa (firmware, hardware, lote, estado,
 * eliminar con confirmación nombrada), edición de una placa y alta manual. El consultor solo ve.
 * API: GET /api/caiquen/pcb · POST /api/caiquen/pcb/masa · PATCH|DELETE /api/caiquen/pcb/{id} · PUT /api/caiquen/pcb/{id}/firmware
 *      POST /api/caiquen/pcb/manual · GET /api/caiquen/resumen (conteos de los filtros) */
(function () {
    'use strict';
    const T = window.TQT, P = window.CQ;
    const { h, icon, api } = T;
    const $ = (id) => document.getElementById(id);
    const LIMITE = 1000, SIN = '__sin';
    const st = { f: { q: '', estado: '', version: '', firmware: '', lote: '' }, items: [], total: 0, sel: new Set(), seq: 0, estado: 'carga', error: '' };
    let sec = null, ui = {};
    const plural = (n, s, p) => `${n} ${n === 1 ? s : (p || s + 's')}`;
    const hayFiltros = () => Object.values(st.f).some((v) => v !== '');

    // ------------------------------------------------------------------ filtros
    function opcion(valor, texto, n) { return h('option', { value: valor }, n == null ? texto : `${texto} (${n})`); }
    function selectFiltro(id, etiqueta, clave) {
        const s = h('select', { class: 'input', id, onchange: () => { st.f[clave] = s.value; cargar(); } });
        return { s, campo: h('div', { class: 'field' }, h('label', { for: id }, etiqueta), s) };
    }
    async function pintaOpciones() {
        const d = await P.resumen();
        // el valor deseado es el del filtro (puede venir de otra sección antes de que haya opciones)
        const pon = (sel, base, ops, clave) => {
            const v = st.f[clave];
            if (v && !ops.some((o) => o.value === v)) ops.push(opcion(v, v === SIN ? 'Sin firmware' : v));
            sel.replaceChildren(base, ...ops); sel.value = v;
        };
        const pe = (d && d.por_estado) || {};
        pon(ui.fEstado.s, opcion('', 'Todos'), Object.keys(P.ESTADOS).map((k) => opcion(k, P.ESTADOS[k].txt, d ? pe[k] || 0 : null)), 'estado');
        pon(ui.fVer.s, opcion('', 'Todos'), ((d && d.versiones) || []).map((x) => opcion(String(x.version), P.hw(x.version), x.n)), 'version');
        const fws = (d && d.firmwares) || [], sinFw = fws.find((x) => !x.firmware);
        pon(ui.fFw.s, opcion('', 'Todos'), [opcion(SIN, 'Sin firmware', sinFw ? sinFw.n : null)].concat(fws.filter((x) => x.firmware).map((x) => opcion(x.firmware, x.firmware, x.n))), 'firmware');
        pon(ui.fLote.s, opcion('', 'Todos'), ((d && d.lotes) || []).filter((x) => x.lote).map((x) => opcion(x.lote, x.lote, x.n)), 'lote');
    }
    function limpiar() {
        st.f = { q: '', estado: '', version: '', firmware: '', lote: '' };
        ui.q.value = ''; [ui.fEstado, ui.fVer, ui.fFw, ui.fLote].forEach((x) => { x.s.value = ''; });
        cargar();
    }

    // ------------------------------------------------------------------ datos
    async function cargar() {
        const n = ++st.seq;
        st.estado = 'carga'; pinta();
        const q = new URLSearchParams({ limit: String(LIMITE) });
        Object.entries(st.f).forEach(([k, v]) => { if (v !== '') q.set(k, v); });
        const r = await api('/api/caiquen/pcb?' + q.toString(), { timeout: 15000 });
        if (n !== st.seq) return;   // llegó otra consulta
        if (!r.ok) { st.estado = 'error'; st.error = r.error || 'No se pudo cargar el inventario'; pinta(); return; }
        st.items = (r.data && r.data.items) || [];
        st.total = (r.data && typeof r.data.total === 'number') ? r.data.total : st.items.length;
        const visibles = new Set(st.items.map((p) => p.id));
        [...st.sel].forEach((id) => { if (!visibles.has(id)) st.sel.delete(id); });   // la selección no sale de lo filtrado
        st.estado = 'ok'; pinta();
    }

    // ------------------------------------------------------------------ pintado
    function pinta() {
        ui.limpiar.hidden = !hayFiltros();
        const ro = P.soloLectura();
        if (st.estado === 'carga') {
            ui.cuenta.textContent = 'Cargando…';
            ui.zona.setAttribute('aria-busy', 'true');
            ui.zona.replaceChildren(h('div', { class: 'i-skel', 'aria-hidden': 'true' }, [1, 2, 3, 4, 5].map(() => h('span'))), h('p', { class: 'sr-only' }, 'Cargando placas'));
            pintaMasa(); return;
        }
        ui.zona.removeAttribute('aria-busy');
        if (st.estado === 'error') {
            ui.cuenta.textContent = '';
            ui.zona.replaceChildren(P.error(st.error + '. Revisa la conexión con el servidor.', cargar));
            pintaMasa(); return;
        }
        const n = st.items.length;
        ui.cuenta.textContent = st.total > n ? `Mostrando ${n} de ${st.total} placas` : plural(n, 'placa');
        if (!n) {
            ui.zona.replaceChildren(hayFiltros()
                ? h('div', { class: 'c-vacio' }, icon('search'), h('b', null, 'Ninguna placa coincide'), h('span', null, 'Prueba con otra búsqueda o quita los filtros.'),
                    h('button', { class: 'btn', type: 'button', onclick: limpiar }, icon('x'), 'Quitar filtros'))
                : h('div', { class: 'c-vacio' }, icon('box'), h('b', null, 'Aún no hay placas Caiquén'), h('span', null, 'Las placas aparecen aquí cuando se reciben por QR o se dan de alta a mano.'),
                    ro ? null : h('div', { class: 'ban-acc' },
                        h('button', { class: 'btn btn-primary', type: 'button', onclick: alta }, icon('plus'), 'Dar de alta'),
                        h('button', { class: 'btn', type: 'button', onclick: () => P.abrir('recibir') }, icon('recibir'), 'Ir a Recibir'))));
            pintaMasa(); return;
        }
        const todas = !ro && st.items.every((p) => st.sel.has(p.id));
        const chkTodas = ro ? null : h('input', { type: 'checkbox', class: 'i-chk', 'aria-label': `Seleccionar las ${n} placas mostradas`, onchange: (e) => {
            st.items.forEach((p) => { if (e.target.checked) st.sel.add(p.id); else st.sel.delete(p.id); }); pinta();
        } });
        if (chkTodas) { chkTodas.checked = todas; chkTodas.indeterminate = !todas && st.items.some((p) => st.sel.has(p.id)); }
        const filas = st.items.map((p) => {
            const sel = st.sel.has(p.id);
            return h('tr', { dataset: { sel: sel ? '1' : '0' } },
                ro ? null : h('td', { class: 'i-c-chk' }, h('input', { type: 'checkbox', class: 'i-chk', checked: sel, 'aria-label': 'Seleccionar ' + p.nombre, onchange: (e) => {
                    if (e.target.checked) st.sel.add(p.id); else st.sel.delete(p.id); pinta();
                } })),
                h('th', { scope: 'row', class: 'i-c-nom' }, h('button', { class: 'i-nom mono', type: 'button', title: 'Ver ficha e historial', onclick: () => P.abrir('consultar', p.nombre) }, p.nombre)),
                h('td', { class: 'mono', 'data-l': 'Hardware' }, P.hw(p.version)),
                h('td', { class: 'mono', 'data-l': 'Firmware' }, p.firmware || h('span', { class: 'i-nada' }, 'Sin firmware')),
                h('td', { class: 'i-c-est', 'data-l': 'Estado' }, P.estadoBadge(p.estado)),
                h('td', { 'data-l': 'Lote' }, p.lote || h('span', { class: 'i-nada' }, '—')),
                h('td', { 'data-l': 'Recibida' }, P.fecha(p.recibida_en, false)),
                ro ? null : h('td', { class: 'i-c-acc' }, h('button', { class: 'btn btn-sm btn-ghost', type: 'button', 'aria-label': 'Editar ' + p.nombre, onclick: () => editar(p) }, icon('edit'), h('span', null, 'Editar'))));
        });
        ui.zona.replaceChildren(h('div', { class: 'i-tabla' }, h('table', { class: 'grid' },
            h('caption', { class: 'sr-only' }, 'Placas Caiquén' + (hayFiltros() ? ' filtradas' : '')),
            h('thead', null, h('tr', null,
                ro ? null : h('th', { class: 'i-c-chk', scope: 'col' }, chkTodas),
                h('th', { scope: 'col' }, 'Placa'), h('th', { scope: 'col' }, 'Hardware'), h('th', { scope: 'col' }, 'Firmware'),
                h('th', { scope: 'col' }, 'Estado'), h('th', { scope: 'col' }, 'Lote'), h('th', { scope: 'col' }, 'Recibida'),
                ro ? null : h('th', { scope: 'col' }, h('span', { class: 'sr-only' }, 'Acciones')))),
            h('tbody', null, filas))));
        pintaMasa();
    }

    function pintaMasa() {
        const n = st.sel.size;
        ui.masa.hidden = n === 0 || P.soloLectura();
        ui.masaN.textContent = plural(n, 'seleccionada');
    }

    // ------------------------------------------------------------------ acciones en masa
    const seleccionadas = () => st.items.filter((p) => st.sel.has(p.id));
    async function masa(accion, valor, err) {
        const ids = [...st.sel];
        const body = { ids, accion };
        if (accion !== 'eliminar') body.valor = valor;
        const r = await api('/api/caiquen/pcb/masa', { method: 'POST', body, timeout: 20000 });
        if (!r.ok) { err.textContent = (r.error || 'No se aplicó el cambio.') + ' No se modificó ninguna placa; inténtalo otra vez.'; return false; }
        const a = (r.data && r.data.afectadas) != null ? r.data.afectadas : ids.length;
        T.toast(accion === 'eliminar' ? `${plural(a, 'placa eliminada', 'placas eliminadas')}` : `${plural(a, 'placa actualizada', 'placas actualizadas')}`, { kind: 'ok' });
        st.sel.clear(); P.cambio(); cargar();
        return true;
    }
    function hojaMasa(titulo, campo, accion, leerValor, ayuda) {
        const n = st.sel.size, err = h('p', { class: 'hoja-err', role: 'alert' });
        T.sheet({
            title: titulo,
            body: [h('p', null, `Se aplicará a ${plural(n, 'placa seleccionada', 'placas seleccionadas')}.`), campo, ayuda ? h('p', { class: 'ayuda' }, ayuda) : null, err],
            actions: [
                { label: 'Cancelar', kind: 'ghost', onClick: () => true },
                { label: `Aplicar a ${plural(n, 'placa')}`, kind: 'primary', icon: 'check', onClick: () => {
                    const v = leerValor(err); if (v === undefined) return false;
                    return masa(accion, v, err);
                } },
            ],
        });
    }
    function campoTexto(id, etiqueta, valor, extra) {
        const i = h('input', Object.assign({ class: 'input', id, type: 'text', autocomplete: 'off', value: valor || '' }, extra || {}));
        return { i, f: h('div', { class: 'field' }, h('label', { for: id }, etiqueta), i) };
    }
    function campoEstado(id, valor) {
        const s = h('select', { class: 'input', id }, Object.keys(P.ESTADOS).map((k) => h('option', { value: k }, P.ESTADOS[k].txt)));
        s.value = valor || 'RECIBIDA';
        return { s, f: h('div', { class: 'field' }, h('label', { for: id }, 'Estado'), s) };
    }
    const masaFw = () => { const c = campoTexto('mFw', 'Firmware', '', { list: 'dlFirmwares', class: 'input mono', maxlength: '80' }); hojaMasa('Cambiar firmware', c.f, 'firmware', () => c.i.value.trim() || null, 'Déjalo vacío para quitar el firmware. Las recibidas con firmware pasan a programadas.'); };
    const masaVer = () => {
        const c = campoTexto('mVer', 'Hardware (versión)', '', { inputmode: 'numeric', class: 'input mono', maxlength: '3' });
        hojaMasa('Cambiar hardware', c.f, 'version', (err) => {
            const v = c.i.value.trim().replace(/^v/i, '');
            if (!/^[0-9]{1,2}$/.test(v) || !Number(v)) { c.i.setAttribute('aria-invalid', 'true'); err.textContent = 'Escribe la versión de hardware como número, por ejemplo 1.'; return undefined; }
            return v;
        }, 'Cambia el nombre de las placas (CQ-V1-0004 → CQ-V2-0004). Si ya existe una con ese nombre no se cambia ninguna.');
    };
    const masaLote = () => { const c = campoTexto('mLote', 'Lote', '', { list: 'dlLotes', maxlength: '60' }); hojaMasa('Mover a lote', c.f, 'lote', () => c.i.value.trim(), 'Déjalo vacío para dejarlas sin lote.'); };
    const masaEstado = () => { const c = campoEstado('mEst', 'RECIBIDA'); hojaMasa('Cambiar estado', c.f, 'estado', () => c.s.value); };
    function masaEliminar() {
        const ps = seleccionadas(), n = ps.length, err = h('p', { class: 'hoja-err', role: 'alert' });
        const nombres = ps.slice(0, 10).map((p) => h('li', { class: 'mono' }, p.nombre));
        T.sheet({
            title: `Eliminar ${plural(n, 'placa')}`,
            body: [
                h('p', null, 'Se borrarán del inventario junto con su firmware y su lote. No se puede deshacer.'),
                h('ul', { class: 'hoja-lista' }, nombres, n > 10 ? h('li', null, `y ${n - 10} más`) : null),
                err,
            ],
            actions: [
                { label: 'Cancelar', kind: 'ghost', onClick: () => true },
                { label: `Eliminar ${plural(n, 'placa')}`, kind: 'danger', icon: 'trash', onClick: () => masa('eliminar', null, err) },
            ],
        });
    }

    // ------------------------------------------------------------------ editar una placa
    function editar(p) {
        const cVer = campoTexto('eVer', 'Hardware (versión)', p.version, { inputmode: 'numeric', class: 'input mono', maxlength: '3' });
        const cSer = campoTexto('eSer', 'Serie', p.serie, { inputmode: 'numeric', class: 'input mono', maxlength: '4' });
        const cFw = campoTexto('eFw', 'Firmware', p.firmware || '', { list: 'dlFirmwares', class: 'input mono', maxlength: '80' });
        const cLote = campoTexto('eLote', 'Lote', p.lote || '', { list: 'dlLotes', maxlength: '60' });
        const cEst = campoEstado('eEst', p.estado);
        const nota = h('textarea', { class: 'input', id: 'eNota', rows: '2', maxlength: '300' }); nota.value = p.nota || '';
        const err = h('p', { class: 'hoja-err', role: 'alert' });
        let armado = false;
        T.sheet({
            title: 'Editar ' + p.nombre,
            body: [
                h('div', { class: 'hoja-dos' }, cVer.f, cSer.f),
                cFw.f, h('div', { class: 'hoja-dos' }, cEst.f, cLote.f),
                h('div', { class: 'field' }, h('label', { for: 'eNota' }, 'Nota'), nota),
                err,
            ],
            actions: [
                { label: `Eliminar ${p.nombre}`, kind: 'danger', icon: 'trash', onClick: async (btn) => {
                    if (!armado) { armado = true; err.textContent = `Se eliminará ${p.nombre}. No se puede deshacer. Pulsa otra vez para confirmar.`; btn.lastChild.textContent = `Confirmar: eliminar ${p.nombre}`; return false; }
                    const r = await api(`/api/caiquen/pcb/${p.id}`, { method: 'DELETE' });
                    if (!r.ok) { err.textContent = (r.error || 'No se pudo eliminar.') + ' Inténtalo otra vez.'; return false; }
                    T.toast(`${p.nombre} eliminada`, { kind: 'ok' }); st.sel.delete(p.id); P.cambio(); cargar();
                    return true;
                } },
                { label: 'Guardar cambios', kind: 'primary', icon: 'check', onClick: async () => {
                    err.textContent = '';
                    const ver = cVer.i.value.trim().replace(/^v/i, ''), ser = cSer.i.value.trim();
                    if (!/^[0-9]{1,2}$/.test(ver) || !Number(ver)) { cVer.i.setAttribute('aria-invalid', 'true'); err.textContent = 'La versión de hardware es un número, por ejemplo 1.'; cVer.i.focus(); return false; }
                    if (!/^[0-9]{1,4}$/.test(ser) || !Number(ser)) { cSer.i.setAttribute('aria-invalid', 'true'); err.textContent = 'La serie son de 1 a 4 dígitos, por ejemplo 0004.'; cSer.i.focus(); return false; }
                    const fw = cFw.i.value.trim() || null;
                    if ((fw || null) !== (p.firmware || null)) {
                        const r = await api(`/api/caiquen/pcb/${p.id}/firmware`, { method: 'PUT', body: { firmware: fw } });
                        if (!r.ok) { err.textContent = (r.error || 'No se guardó el firmware.') + ' Inténtalo otra vez.'; return false; }
                        if (r.data && r.data.pcb) p = r.data.pcb;
                    }
                    const body = {};
                    if (ver !== String(p.version)) body.version = ver;
                    if (Number(ser) !== Number(p.serie)) body.serie = ser;
                    if (cLote.i.value.trim() !== (p.lote || '')) body.lote = cLote.i.value.trim();
                    if (cEst.s.value !== p.estado) body.estado = cEst.s.value;
                    if (nota.value.trim() !== (p.nota || '')) body.nota = nota.value.trim();
                    if (Object.keys(body).length) {
                        const r = await api(`/api/caiquen/pcb/${p.id}`, { method: 'PATCH', body });
                        if (!r.ok) { err.textContent = r.status === 409 ? 'Ya existe otra placa con ese hardware y serie. Cambia uno de los dos.' : (r.error || 'No se guardaron los cambios.') + ' Inténtalo otra vez.'; return false; }
                    }
                    T.toast('Cambios guardados', { kind: 'ok' }); P.cambio(); cargar();
                    return true;
                } },
            ],
        });
    }

    // ------------------------------------------------------------------ alta manual
    function alta() {
        let loteDisp = ''; try { loteDisp = localStorage.getItem('tqt.caiquen.lote') || ''; } catch (e) { /* nada */ }
        const cVer = campoTexto('aVer', 'Hardware (versión)', '1', { inputmode: 'numeric', class: 'input mono', maxlength: '3' });
        const cSer = campoTexto('aSer', 'Serie', '', { inputmode: 'numeric', class: 'input mono', maxlength: '4', 'aria-describedby': 'aSerAy' });
        const cLote = campoTexto('aLote', 'Lote', loteDisp, { list: 'dlLotes', maxlength: '60' });
        const err = h('div', { class: 'hoja-err', role: 'alert' });
        T.sheet({
            title: 'Dar de alta una placa',
            body: [
                h('p', null, 'Para placas cuyo QR no se puede leer. La placa queda como recibida.'),
                h('div', { class: 'hoja-dos' }, cVer.f, h('div', null, cSer.f, h('p', { class: 'ayuda', id: 'aSerAy' }, 'La impresa en la placa, ej. 0004.'))),
                cLote.f, err,
            ],
            actions: [
                { label: 'Cancelar', kind: 'ghost', onClick: () => true },
                { label: 'Dar de alta', kind: 'primary', icon: 'plus', onClick: async () => {
                    const ver = cVer.i.value.trim().replace(/^v/i, ''), ser = cSer.i.value.trim();
                    if (!/^[0-9]{1,2}$/.test(ver) || !Number(ver)) { cVer.i.setAttribute('aria-invalid', 'true'); err.textContent = 'La versión de hardware es un número, por ejemplo 1.'; cVer.i.focus(); return false; }
                    if (!/^[0-9]{1,4}$/.test(ser) || !Number(ser)) { cSer.i.setAttribute('aria-invalid', 'true'); err.textContent = 'Escribe la serie de 1 a 4 dígitos, por ejemplo 0004.'; cSer.i.focus(); return false; }
                    const r = await api('/api/caiquen/pcb/manual', { method: 'POST', body: { version: ver, serie: ser, lote: cLote.i.value.trim() } });
                    if (r.status === 409) {
                        const nom = `CQ-V${Number(ver)}-${ser.padStart(4, '0')}`;
                        err.replaceChildren(h('span', null, `${nom} ya está registrada. `),
                            h('button', { class: 'btn btn-sm', type: 'button', onclick: () => { document.querySelector('.scrim')?.click(); P.abrir('consultar', nom); } }, 'Ver su ficha'));
                        return false;
                    }
                    if (!r.ok) { err.textContent = (r.error || 'No se pudo dar de alta.') + ' Revisa los datos e inténtalo otra vez.'; return false; }
                    const pcb = (r.data && r.data.pcb) || {};
                    T.toast(`${pcb.nombre || 'Placa'} dada de alta`, { kind: 'ok' }); P.cambio(); cargar();
                    return true;
                } },
            ],
        });
    }

    // ------------------------------------------------------------------ montaje
    function montar(el) {
        sec = el;
        ui.cuenta = $('iCuenta');
        $('bAlta').addEventListener('click', alta);
        ui.q = h('input', { class: 'input', id: 'iQ', type: 'search', autocomplete: 'off', spellcheck: 'false', maxlength: '80', placeholder: 'Nombre, serie, firmware o nota' });
        const buscar = T.debounce(() => { st.f.q = ui.q.value.trim(); cargar(); }, 300);
        ui.q.addEventListener('input', buscar);
        ui.fEstado = selectFiltro('iEst', 'Estado', 'estado');
        ui.fVer = selectFiltro('iVer', 'Hardware', 'version');
        ui.fFw = selectFiltro('iFw', 'Firmware', 'firmware');
        ui.fLote = selectFiltro('iLote', 'Lote', 'lote');
        ui.limpiar = h('button', { class: 'btn btn-ghost', type: 'button', onclick: limpiar, hidden: true }, icon('x'), 'Quitar filtros');
        ui.zona = h('div', { class: 'i-zona', 'aria-live': 'polite' });
        ui.masaN = h('b', { 'aria-live': 'polite' });
        ui.masa = h('div', { class: 'i-masa', role: 'region', 'aria-label': 'Acciones con la selección', hidden: true },
            ui.masaN,
            h('div', { class: 'i-masa-acc' },
                h('button', { class: 'btn btn-sm', type: 'button', onclick: masaFw }, icon('programar'), 'Firmware'),
                h('button', { class: 'btn btn-sm', type: 'button', onclick: masaVer }, icon('edit'), 'Hardware'),
                h('button', { class: 'btn btn-sm', type: 'button', onclick: masaLote }, icon('box'), 'Lote'),
                h('button', { class: 'btn btn-sm', type: 'button', onclick: masaEstado }, icon('tag'), 'Estado'),
                h('button', { class: 'btn btn-sm btn-danger', type: 'button', onclick: masaEliminar }, icon('trash'), 'Eliminar'),
                h('button', { class: 'btn btn-sm btn-ghost', type: 'button', onclick: () => { st.sel.clear(); pinta(); } }, icon('x'), 'Quitar selección')));
        $('iCuerpo').replaceChildren(
            h('div', { class: 'i-filtros', role: 'search', 'aria-label': 'Filtrar placas' },
                h('div', { class: 'field i-f-q' }, h('label', { for: 'iQ' }, 'Buscar'), ui.q),
                ui.fEstado.campo, ui.fVer.campo, ui.fFw.campo, ui.fLote.campo,
                h('div', { class: 'i-f-limpiar' }, ui.limpiar)),
            ui.zona, ui.masa);
        document.addEventListener('caiquen:cambio', () => { pintaOpciones(); if (sec.hidden) st.viejo = true; });
        P.yo.then(() => { if (!sec.hidden) pinta(); });
        pintaOpciones();
        cargar();
    }

    /** Filtros actuales (los usa Excel para exportar lo mismo que se ve). */
    P.filtrosInventario = () => Object.assign({}, st.f);

    P.registrar('inventario', {
        montar,
        /** Abrir el inventario ya filtrado: {estado, version, firmware, lote, q}. */
        recibirDato(f) {
            if (!f || typeof f !== 'object') return;
            st.f = Object.assign({ q: '', estado: '', version: '', firmware: '', lote: '' }, f);
            ui.q.value = st.f.q; st.sel.clear(); st.viejo = false;
            pintaOpciones(); cargar();
        },
        entrar() { if (st.viejo) { st.viejo = false; cargar(); } },
    });
})();
