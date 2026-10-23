/* materiales.js - Pestaña «Materiales» (v1.4.35): inventario de componentes del módulo con el criterio de Inventario TQTR.
 * Existencias = entradas − salidas − consumo; cada placa programada descuenta la lista de materiales de su tarjeta (Costos).
 * Se configura con el <script>: data-ns="SF" y data-base="/api/sigfox/materiales". El consultor solo lee.
 * Sin activar, el módulo queda preparado: lista de materiales con existencias en cero y botón «Activar inventario». */
(function () {
    'use strict';
    const cfg = document.currentScript.dataset;
    const T = window.TQT, P = window[cfg.ns], B = cfg.base;
    const { h, icon, api } = T;
    const $ = (id) => document.getElementById(id);
    const num = (v) => Number(v || 0).toLocaleString('es-MX', { maximumFractionDigits: 3 });
    let d = null;

    async function cargar() {
        const r = await api(B);
        if (!r.ok) { $('mtCuerpo').replaceChildren(h('p', { class: 'x-intro', role: 'alert' }, 'No se pudo cargar el inventario: ' + r.error, ' ', h('button', { class: 'btn', type: 'button', onclick: cargar }, 'Reintentar'))); return; }
        d = r.data; pintar();
    }
    async function enviar(ruta, metodo, body, ok) {
        const r = await api(B + ruta, { method: metodo, body });
        if (!r.ok) { T.toast(r.error, { kind: 'bad', ms: 6000 }); return false; }
        d = r.data; pintar(); if (ok) T.toast(ok, { kind: 'ok' });
        return true;
    }
    const kpi = (t, v, n, clase) => h('div', { class: 'c-kpi' + (clase ? ' ' + clase : '') }, h('span', { class: 'c-kpi-t' }, t), h('strong', { class: 'mono' }, v), n ? h('span', { class: 'c-kpi-n' }, n) : null);

    function pintar() {
        const ro = P.soloLectura();
        const partes = [];
        if (!d.activo) {
            const f = h('input', { class: 'input mono', id: 'mtDesde', type: 'date', value: new Date().toISOString().slice(0, 10) });
            partes.push(h('div', { class: 'x-caja mt-aviso' },
                h('p', { class: 'x-intro' }, h('strong', null, 'Inventario preparado, sin activar. '),
                    'La lista de materiales ya está lista (sale de Costos). Cuando tengan existencias, registra las entradas y activa el inventario: desde esa fecha cada placa programada descontará los materiales de su tarjeta. Las placas programadas antes no descuentan.'),
                ro ? null : h('div', { class: 'c-barra' }, h('div', { class: 'field c-tc' }, h('label', { for: 'mtDesde' }, 'Descontar desde'), f),
                    h('button', { class: 'btn btn-primary', type: 'button', onclick: () => enviar('/activar', 'POST', { desde: f.value }, 'Inventario activado') }, icon('check'), 'Activar inventario'))));
        }
        const kpis = d.tarjetas.map((t) => kpi(`Tarjetas ${t} posibles`, d.posibles[t] == null ? '—' : num(d.posibles[t]), d.posibles[t] == null ? 'sin lista de materiales' : 'con el material disponible'));
        d.tarjetas.forEach((t) => kpis.push(kpi(`${t} descontadas`, num(d.realizadas[t]), d.activo ? `desde ${d.consumo_desde}` : 'inventario sin activar')));
        kpis.push(kpi('Bajo mínimo', num(d.bajo_minimo), 'materiales por comprar', d.bajo_minimo ? 'mt-alerta' : ''));
        partes.push(h('div', { class: 'c-kpis' }, ...kpis));
        if (d.pendientes.length) partes.push(pendientes(ro));
        partes.push(tabla(ro), historial(ro));
        $('mtCuerpo').replaceChildren(...partes);
    }

    function pendientes(ro) {
        const ids = d.pendientes.map((p) => p.id);
        const botones = (pids, chico) => ro ? null : h('div', { class: 'ban-acc mt-asig' }, ...d.tarjetas.map((t) => h('button', { class: 'btn' + (chico ? ' btn-sm' : ''), type: 'button', onclick: () => enviar('/asignar', 'POST', { pcb_ids: pids, tarjeta: t }, `Asignada${pids.length > 1 ? 's' : ''} como ${t}`) }, chico ? t : `Todas ${t}`)));
        return h('section', { class: 'x-caja mt-aviso', 'aria-label': 'Placas por asignar' },
            h('h2', { class: 'c-grupo-t' }, `Placas programadas sin tarjeta (${d.pendientes.length})`, botones(ids, false)),
            h('p', { class: 'x-intro' }, `Cada QR es una tarjeta: indica si es ${d.tarjetas.join(' o ')} para descontar sus materiales.`),
            h('ul', { class: 'mt-lista' }, ...d.pendientes.map((p) => h('li', null, h('span', { class: 'mono' }, p.nombre), botones([p.id], true)))));
    }

    function tabla(ro) {
        if (!d.materiales.length) return h('div', { class: 'x-caja' }, h('p', { class: 'x-intro' }, 'No hay materiales: primero carga la lista en la pestaña Costos (Importar Excel o Agregar material).'));
        return h('section', { class: 'c-grupo', 'aria-label': 'Existencias' },
            h('h2', { class: 'c-grupo-t' }, 'Existencias'),
            h('div', { class: 'i-tabla' }, h('table', { class: 'grid mt-tabla' },
                h('thead', null, h('tr', null, ...['Material', 'Tarjetas', 'Entradas', 'Salidas', 'Consumido', 'Disponible', 'Mínimo', ''].map((x) => h('th', { scope: 'col' }, x)))),
                h('tbody', null, ...d.materiales.map((m) => {
                    const min = h('input', { class: 'input mono mt-min', type: 'number', min: '0', step: 'any', value: String(m.minimo || 0), disabled: ro, 'aria-label': `Mínimo de ${m.descripcion}` });
                    min.addEventListener('change', () => enviar('/minimo', 'PATCH', { descripcion: m.descripcion, minimo: Number(min.value || 0) }, 'Mínimo guardado'));
                    return h('tr', { 'data-bajo': m.bajo_minimo ? '1' : null },
                        h('th', { scope: 'row', 'data-l': 'Material' }, m.descripcion, m.en_bom ? null : h('span', { class: 'c-kpi-n' }, ' (ya no está en Costos)')),
                        h('td', { 'data-l': 'Tarjetas' }, m.tarjetas.join(', ') || '—'),
                        h('td', { class: 'mono', 'data-l': 'Entradas' }, num(m.entradas)),
                        h('td', { class: 'mono', 'data-l': 'Salidas' }, num(m.salidas)),
                        h('td', { class: 'mono', 'data-l': 'Consumido' }, num(m.consumido)),
                        h('td', { class: 'mono mt-disp', 'data-l': 'Disponible' }, `${num(m.disponible)} ${m.unidad || ''}`, m.bajo_minimo ? T.badge('Bajo mínimo', 'bad') : null),
                        h('td', { 'data-l': 'Mínimo' }, min),
                        h('td', null, ro ? null : h('button', { class: 'btn btn-sm', type: 'button', onclick: () => movimiento(m) }, icon('plus'), 'Movimiento')));
                })))));
    }

    function historial(ro) {
        const movs = d.movimientos.map((x) => h('li', null,
            h('span', null, `${x.creado_en.slice(0, 16)} · ${x.tipo} · `, h('strong', null, `${num(x.cantidad)} ${x.descripcion}`), x.nota ? ` · ${x.nota}` : '', x.operador ? ` · ${x.operador}` : ''),
            ro ? null : h('button', { class: 'iconbtn', type: 'button', 'aria-label': 'Eliminar movimiento', title: 'Eliminar movimiento', onclick: (e) => borrarMov(e.currentTarget, x) }, icon('trash'))));
        const cons = d.consumos.map((x) => h('li', null, h('span', null, `${x.creado_en.slice(0, 16)} · `, h('strong', { class: 'mono' }, x.pcb_nombre), ` · ${x.tarjeta} · ${x.materiales} materiales · `, x.estado === 'activo' ? 'descontado' : 'devuelto')));
        return h('div', { class: 'mt-hist' },
            h('details', null, h('summary', null, `Movimientos recientes (${d.movimientos.length})`), movs.length ? h('ul', { class: 'mt-lista' }, ...movs) : h('p', { class: 'x-intro' }, 'Sin movimientos.')),
            h('details', null, h('summary', null, `Consumo por placa (${d.consumos.length})`), cons.length ? h('ul', { class: 'mt-lista' }, ...cons) : h('p', { class: 'x-intro' }, d.activo ? 'Ninguna placa programada desde la activación.' : 'Se llenará al activar el inventario.')));
    }

    function borrarMov(btn, x) {
        if (btn.dataset.armado !== '1') { btn.dataset.armado = '1'; T.toast(`Pulsa otra vez el bote para eliminar «${x.tipo} ${num(x.cantidad)} ${x.descripcion}».`, { kind: 'warn', ms: 5000 }); setTimeout(() => { btn.dataset.armado = ''; }, 5000); return; }
        enviar(`/movimientos/${x.id}`, 'DELETE', undefined, 'Movimiento eliminado');
    }

    function movimiento(m) {
        const tipo = h('select', { class: 'input', id: 'mvTipo' }, h('option', { value: 'entrada' }, 'Entrada (llegó material)'), h('option', { value: 'salida' }, 'Salida (merma, préstamo, otro uso)'), h('option', { value: 'ajuste' }, 'Ajuste de conteo (+/−)'));
        const cant = h('input', { class: 'input mono', id: 'mvCant', type: 'number', step: 'any', inputmode: 'decimal', required: true });
        const nota = h('input', { class: 'input', id: 'mvNota', maxlength: '300', placeholder: 'Factura, proveedor, motivo…' });
        const err = h('p', { class: 'c-err', role: 'alert' });
        const cerrar = () => { dlg.close(); dlg.remove(); };
        const form = h('form', { class: 'c-form', novalidate: true },
            h('h2', { class: 'c-grupo-t' }, m.descripcion, h('span', { class: 'mono' }, `${num(m.disponible)} ${m.unidad || ''}`)),
            h('div', { class: 'c-campos' },
                h('div', { class: 'field' }, h('label', { for: 'mvTipo' }, 'Tipo'), tipo),
                h('div', { class: 'field' }, h('label', { for: 'mvCant' }, `Cantidad${m.unidad ? ' (' + m.unidad + ')' : ''}`), cant),
                h('div', { class: 'field mt-ancho' }, h('label', { for: 'mvNota' }, 'Nota'), nota)),
            err,
            h('div', { class: 'ban-acc c-form-acc' }, h('button', { class: 'btn', type: 'button', onclick: cerrar }, 'Cancelar'), h('button', { class: 'btn btn-primary', type: 'submit' }, icon('check'), 'Registrar')));
        const dlg = h('dialog', { class: 'c-dlg', 'aria-label': `Movimiento de ${m.descripcion}` }, form);
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const n = Number(cant.value);
            if (!cant.value || !n || (tipo.value !== 'ajuste' && n < 0)) { err.textContent = tipo.value === 'ajuste' ? 'Escribe la diferencia (negativa si faltó material).' : 'Escribe una cantidad mayor a cero.'; cant.focus(); return; }
            if (await enviar('/movimientos', 'POST', { descripcion: m.descripcion, tipo: tipo.value, cantidad: n, nota: nota.value.trim() }, 'Movimiento registrado')) cerrar();
        });
        dlg.addEventListener('cancel', (e) => { e.preventDefault(); cerrar(); });
        document.body.append(dlg); dlg.showModal(); cant.focus();
    }

    P.registrar('materiales', {
        montar() { $('mtCuerpo').replaceChildren(h('p', { class: 'x-intro' }, 'Cargando inventario…')); },
        entrar() { cargar(); },
    });
    if (cfg.evento) document.addEventListener(cfg.evento, () => { if (d && document.querySelector('[data-vista="materiales"]:not([hidden])')) cargar(); });
})();
