/* costeo.js - Pestaña «Costos» (v1.4.34): el cotizador del proyecto dentro de su módulo. Una sola vista para todos los
 * módulos; se configura con el <script> que la carga: data-ns="SF" (namespace del shell) y data-base="/api/sigfox/costos".
 * Costo por tarjeta (cada QR es una tarjeta), tipo de cambio del módulo, recurrentes aparte (no suman a producción),
 * alta/edición/baja de materiales, importar el Excel del cotizador y descargarlo con fórmulas. El consultor solo lee. */
(function () {
    'use strict';
    const cfg = document.currentScript.dataset;
    const T = window.TQT, P = window[cfg.ns], B = cfg.base;
    const { h, icon, api } = T;
    const $ = (id) => document.getElementById(id);
    const mxn = (v) => Number(v || 0).toLocaleString('es-MX', { style: 'currency', currency: 'MXN' });
    const num = (v, d) => Number(v || 0).toLocaleString('es-MX', { maximumFractionDigits: d == null ? 4 : d });
    let d = null, ui = {}, filtro = '';

    async function cargar() {
        const r = await api(B);
        if (!r.ok) { $('cCuerpo').replaceChildren(h('p', { class: 'x-intro', role: 'alert' }, 'No se pudo cargar el cotizador: ' + r.error, ' ', h('button', { class: 'btn', type: 'button', onclick: cargar }, 'Reintentar'))); return; }
        d = r.data; pintar();
    }

    function tarjetaKpi(titulo, valor, nota, fuerte) {
        return h('div', { class: 'c-kpi' + (fuerte ? ' c-kpi-fuerte' : '') }, h('span', { class: 'c-kpi-t' }, titulo), h('strong', { class: 'mono' }, valor), nota ? h('span', { class: 'c-kpi-n' }, nota) : null);
    }

    function pintar() {
        const ro = P.soloLectura();
        const kpis = d.tarjetas.map((t) => tarjetaKpi(`Tarjeta ${t}`, mxn(d.por_tarjeta[t]), 'costo por QR'));
        if (d.tarjetas.length > 1) kpis.push(tarjetaKpi('Equipo completo', mxn(d.total_produccion), d.tarjetas.join(' + '), true));
        if (d.recurrente) kpis.push(tarjetaKpi('Recurrente (aparte)', mxn(d.recurrente), 'no suma a producción'));
        const tc = h('input', { class: 'input mono', id: 'cTc', type: 'number', min: '1', max: '1000', step: '0.01', value: String(d.tipo_cambio), disabled: ro, 'aria-describedby': 'cTcAyuda' });
        tc.addEventListener('change', async () => {
            const r = await api(B + '/parametros', { method: 'PATCH', body: { tipo_cambio: Number(tc.value) } });
            if (!r.ok) { T.toast(r.error, { kind: 'bad' }); tc.value = String(d.tipo_cambio); return; }
            d = r.data; pintar(); T.toast('Tipo de cambio actualizado', { kind: 'ok' });
        });
        const arch = h('input', { type: 'file', accept: '.xlsx', hidden: true, onchange: () => importar(arch) });
        const acciones = h('div', { class: 'ban-acc' },
            h('a', { class: 'btn', href: B + '/exportar', download: '' }, icon('download'), 'Descargar cotizador'),
            ro ? null : h('button', { class: 'btn', type: 'button', onclick: () => arch.click() }, icon('excel'), 'Importar Excel'),
            ro ? null : h('button', { class: 'btn btn-primary', type: 'button', onclick: () => editor(null) }, icon('plus'), 'Agregar material'), arch);
        ui.q = h('input', { class: 'input', id: 'cQ', type: 'search', placeholder: 'Material, categoría o proveedor', value: filtro, autocomplete: 'off' });
        ui.q.addEventListener('input', T.debounce(() => { filtro = ui.q.value.trim().toLowerCase(); ui.zona.replaceChildren(...tablas()); }, 200));
        ui.zona = h('div', { class: 'c-zona' }, ...tablas());
        $('cCuerpo').replaceChildren(
            h('div', { class: 'c-kpis' }, ...kpis),
            h('div', { class: 'c-barra' },
                h('div', { class: 'field c-tc' }, h('label', { for: 'cTc' }, 'Tipo de cambio (MXN por USD)'), tc, h('span', { class: 'c-kpi-n', id: 'cTcAyuda' }, 'Solo afecta a este módulo')),
                h('div', { class: 'field c-q' }, h('label', { for: 'cQ' }, 'Buscar'), ui.q), acciones),
            ui.zona);
    }

    function tablas() {
        const ro = P.soloLectura();
        const ver = d.items.filter((it) => !filtro || [it.descripcion, it.categoria, it.proveedor].join(' ').toLowerCase().includes(filtro));
        if (!d.items.length) return [h('div', { class: 'x-caja' }, h('p', { class: 'x-intro' }, 'Aún no hay materiales. Importa el Excel del cotizador (hoja «Componentes») o agrégalos uno por uno.'))];
        if (!ver.length) return [h('p', { class: 'x-intro' }, 'Ningún material coincide con la búsqueda.')];
        const grupos = d.tarjetas.map((t) => [`Tarjeta ${t}`, ver.filter((it) => it.tarjeta === t && it.tipo !== 'recurrente'), d.por_tarjeta[t]]);
        grupos.push(['Costos recurrentes (aparte)', ver.filter((it) => it.tipo === 'recurrente'), d.recurrente]);
        return grupos.filter(([, filas]) => filas.length).map(([titulo, filas, total]) => h('section', { class: 'c-grupo', 'aria-label': titulo },
            h('h2', { class: 'c-grupo-t' }, titulo, h('span', { class: 'mono' }, mxn(total))),
            h('div', { class: 'i-tabla' }, h('table', { class: 'grid' },
                h('thead', null, h('tr', null, ...['Material', 'Categoría', 'Proveedor', 'Cant.', 'Costo unitario', 'Subtotal (MXN)', ''].map((x) => h('th', { scope: 'col' }, x)))),
                h('tbody', null, ...filas.map((it) => h('tr', null,
                    h('th', { scope: 'row', 'data-l': 'Material' }, it.descripcion),
                    h('td', { 'data-l': 'Categoría' }, it.categoria || '—'),
                    h('td', { 'data-l': 'Proveedor' }, it.proveedor || '—'),
                    h('td', { class: 'mono', 'data-l': 'Cant.' }, `${num(it.cantidad)} ${it.unidad || ''}`),
                    h('td', { class: 'mono', 'data-l': 'Costo unitario' }, `${num(it.costo_unitario, 2)} ${it.moneda}`),
                    h('td', { class: 'mono', 'data-l': 'Subtotal (MXN)' }, mxn(it.subtotal_mxn)),
                    h('td', null, ro ? null : h('button', { class: 'iconbtn', type: 'button', 'aria-label': `Editar ${it.descripcion}`, title: 'Editar', onclick: () => editor(it) }, icon('edit'))))))))));
    }

    // Reemplazar es destructivo: con materiales cargados se confirma con el botón del aviso (sin diálogos del navegador).
    function importar(arch) {
        const f = arch.files[0]; arch.value = '';
        if (!f) return;
        if (!d.items.length) { subir(f); return; }
        T.toast(`Importar «${f.name}» reemplaza los ${d.items.length} materiales actuales.`, { kind: 'warn', ms: 9000, action: { label: 'Reemplazar', onClick: () => subir(f) } });
    }
    async function subir(f) {
        let r;
        try {
            const res = await fetch(B + '/importar?reemplazar=true', { method: 'POST', headers: { 'Content-Type': 'application/octet-stream' }, body: f });
            const data = await res.json().catch(() => null);
            r = { ok: res.ok, data, error: res.ok ? '' : ((data && data.detail) || `Error ${res.status}`) };
        } catch (e) { r = { ok: false, error: 'Sin conexión con el servidor' }; }
        if (!r.ok) { T.toast('No se importó: ' + r.error, { kind: 'bad', ms: 6000 }); return; }
        d = r.data; pintar(); T.toast(`Cotizador importado: ${r.data.importados} materiales`, { kind: 'ok' });
    }

    function editor(it) {
        const nuevo = !it; it = it || { tarjeta: d.tarjetas[0], moneda: 'MXN', tipo: 'produccion', cantidad: 1, cantidad_lote: 1, costo_unitario: 0 };
        const campo = (id, etq, el) => h('div', { class: 'field' }, h('label', { for: id }, etq), el);
        const inp = (id, v, extra) => h('input', Object.assign({ class: 'input', id, value: v == null ? '' : String(v), autocomplete: 'off' }, extra || {}));
        const sel = (id, v, ops) => { const s = h('select', { class: 'input', id }, ...ops.map(([k, t]) => h('option', { value: k }, t))); s.value = v; return s; };
        const f = {
            descripcion: inp('ceDesc', it.descripcion, { maxlength: '300', required: true }),
            tarjeta: sel('ceTar', it.tarjeta, d.tarjetas.map((t) => [t, t])),
            categoria: inp('ceCat', it.categoria, { maxlength: '120' }),
            proveedor: inp('ceProv', it.proveedor, { maxlength: '120' }),
            cantidad: inp('ceCant', it.cantidad, { type: 'number', min: '0', step: 'any', inputmode: 'decimal' }),
            unidad: inp('ceUni', it.unidad, { maxlength: '20', placeholder: 'pza, m…' }),
            cantidad_lote: inp('ceLote', it.cantidad_lote, { type: 'number', min: '0', step: 'any', inputmode: 'decimal' }),
            costo_unitario: inp('ceCosto', it.costo_unitario, { type: 'number', min: '0', step: 'any', inputmode: 'decimal' }),
            moneda: sel('ceMon', it.moneda, d.monedas.map((m) => [m, m])),
            tipo: sel('ceTipo', it.tipo, [['produccion', 'Producción (suma al costo de la tarjeta)'], ['recurrente', 'Recurrente (aparte, p. ej. licencia anual)']]),
            notas: inp('ceNotas', it.notas, { maxlength: '300' }),
        };
        const err = h('p', { class: 'c-err', role: 'alert' });
        const guardar = h('button', { class: 'btn btn-primary', type: 'submit' }, icon('check'), nuevo ? 'Agregar' : 'Guardar');
        const borrar = nuevo ? null : h('button', { class: 'btn btn-danger', type: 'button' }, icon('trash'), 'Eliminar');
        const cerrar = () => { dlg.close(); dlg.remove(); };
        const form = h('form', { class: 'c-form', novalidate: true },
            h('h2', { class: 'c-grupo-t' }, nuevo ? 'Agregar material' : 'Editar material'),
            h('div', { class: 'c-campos' },
                campo('ceDesc', 'Descripción del material', f.descripcion), campo('ceTar', 'Tarjeta', f.tarjeta),
                campo('ceCat', 'Categoría', f.categoria), campo('ceProv', 'Proveedor', f.proveedor),
                campo('ceCant', 'Cantidad por tarjeta', f.cantidad), campo('ceUni', 'Unidad', f.unidad),
                campo('ceLote', 'Cantidad por caja/bobina/lote', f.cantidad_lote), campo('ceCosto', 'Costo unitario', f.costo_unitario),
                campo('ceMon', 'Moneda', f.moneda), campo('ceTipo', 'Tipo de costo', f.tipo), campo('ceNotas', 'Notas', f.notas)),
            err,
            h('div', { class: 'ban-acc c-form-acc' }, borrar, h('button', { class: 'btn', type: 'button', onclick: cerrar }, 'Cancelar'), guardar));
        const dlg = h('dialog', { class: 'c-dlg', 'aria-label': nuevo ? 'Agregar material' : 'Editar material' }, form);
        form.addEventListener('submit', async (e) => {
            e.preventDefault(); err.textContent = '';
            if (!f.descripcion.value.trim()) { err.textContent = 'Escribe la descripción del material.'; f.descripcion.focus(); return; }
            const body = {};
            Object.keys(f).forEach((k) => { body[k] = ['cantidad', 'cantidad_lote', 'costo_unitario'].includes(k) ? Number(f[k].value || 0) : f[k].value.trim(); });
            guardar.disabled = true;
            const r = await api(nuevo ? B : `${B}/${it.id}`, { method: nuevo ? 'POST' : 'PATCH', body });
            guardar.disabled = false;
            if (!r.ok) { err.textContent = r.error; return; }
            cerrar(); T.toast(nuevo ? 'Material agregado' : 'Cambios guardados', { kind: 'ok' }); cargar();
        });
        if (borrar) {
            let armado = false;
            borrar.addEventListener('click', async () => {
                if (!armado) { armado = true; err.textContent = `Se eliminará «${it.descripcion}» de la tarjeta ${it.tarjeta}. Pulsa otra vez para confirmar.`; borrar.lastChild.textContent = 'Confirmar eliminación'; return; }
                const r = await api(`${B}/${it.id}`, { method: 'DELETE' });
                if (!r.ok) { err.textContent = r.error; return; }
                cerrar(); T.toast('Material eliminado', { kind: 'ok' }); cargar();
            });
        }
        dlg.addEventListener('cancel', (e) => { e.preventDefault(); cerrar(); });
        document.body.append(dlg); dlg.showModal(); f.descripcion.focus();
    }

    P.registrar('costos', {
        montar() { $('cCuerpo').replaceChildren(h('p', { class: 'x-intro' }, 'Cargando cotizador…')); },
        entrar() { cargar(); },
    });
})();
