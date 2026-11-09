/* Plan de producción sobre la misma lectura de BOM y existencias. No reserva ni mueve material. */
(() => {
    'use strict';
    const { h, icon } = window.TQT;
    const formato = new Intl.NumberFormat('es-MX', { maximumSignificantDigits: 15 });
    const limpio = n => Number(n.toPrecision(15));

    function calcular(datos, cantidades, conStock) {
        const tipos = datos.tarjetas.filter(t => cantidades[t] > 0), cat = datos.catalogo || 'Costos';
        if (!tipos.length) return { aviso: 'Indica cuántas tarjetas quieres fabricar.' };
        for (const t of tipos) {
            if (!datos.materiales.some(m => m.en_bom && m.tarjetas.includes(t))) {
                return { aviso: 'Falta la lista de materiales de ' + t + '. Cárgala en ' + cat + ' para calcular la solicitud.' };
            }
        }
        const filas = [];
        for (const m of datos.materiales) {
            const usan = tipos.filter(t => m.en_bom && m.tarjetas.includes(t));
            if (!usan.length) continue;
            if (m.unidad_ambigua) return { aviso: 'Revisa «' + m.descripcion + '» en ' + cat + ': está registrada con unidades diferentes.' };
            const falta = usan.find(t => !(m.por_tarjeta?.[t] > 0));
            if (falta) return { aviso: 'Falta la cantidad de «' + m.descripcion + '» por tarjeta ' + falta + '. Revisa la lista en ' + cat + '.' };
            const necesario = limpio(usan.reduce((n, t) => n + m.por_tarjeta[t] * cantidades[t], 0));
            const disponible = m.disponible;
            const pedir = conStock ? Math.max(0, limpio(necesario - Math.max(0, disponible))) : necesario;
            filas.push({ nombre: m.descripcion, unidad: m.unidad, necesario, disponible, pedir });
        }
        return { filas };
    }

    function descargar(datos, filas, conStock, cantidades, porSolicitar) {
        const celda = v => {
            let s = String(v ?? '');
            if (typeof v !== 'number' && /^\s*[=+@-]|^[\t\r\n]/.test(s)) s = "'" + s;
            return '"' + s.replace(/"/g, '""') + '"';
        };
        const modo = conStock ? 'Descontando existencias' : 'Sin descontar existencias';
        const series = datos.tarjetas.map(t => t + ': ' + (cantidades[t] || 0)).join(' / ');
        const contenido = [['N.º', 'Componente', 'Unidad', 'Necesario', ...(conStock ? ['Disponible'] : []), 'A solicitar', 'Tarjetas', 'Cálculo',
            'Componentes para solicitar', 'Total de componentes'],
            ...filas.map((f, i) => [i + 1, f.nombre, f.unidad, f.necesario, ...(conStock ? [f.disponible] : []), f.pedir, series, modo,
                porSolicitar, filas.length])];
        const csv = '\uFEFF' + contenido.map(r => r.map(celda).join(',')).join('\r\n');
        const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
        const a = h('a', { download: 'Solicitud-' + datos.modulo + '-' + (conStock ? 'con-existencias' : 'total') + '.csv', href: url });
        document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    }

    window.TQT.solicitudMateriales = function (datos, estado, recargar) {
        const resultado = h('div', { class: 'mt-resultado' });
        const aviso = h('p', { class: 'x-intro', role: 'status' });
        const notaStock = h('p', { class: 'c-kpi-n' }, !datos.activo ?
            'El consumo automático no está activo. El disponible refleja los movimientos registrados.' :
            'Hay PCB pendientes de asignar a ' + datos.tarjetas.join(' o ') + '; sus consumos aún no se reflejan en el disponible.');
        const inputs = datos.tarjetas.map((t, i) => {
            const id = 'mtTarjeta' + i;
            const input = h('input', { class: 'input mono', id, type: 'number', min: 0, max: 1000000, step: 1,
                inputmode: 'numeric', placeholder: '0', value: estado.cantidades[t] ?? '', oninput: actualizar });
            return { t, input, campo: h('div', { class: 'field' }, h('label', { for: id }, (datos.etiqueta || 'Tarjetas') + ' ' + t), input) };
        });
        const opciones = [[true, 'Descontar existencias', 'Pide solo lo que falta.'], [false, 'Ignorar existencias', 'Pide todo lo necesario.']];
        const modos = h('fieldset', { class: 'mt-modos' }, h('legend', null, 'Cómo calcular la solicitud'),
            opciones.map(([valor, titulo, nota]) => h('label', null,
                h('input', { type: 'radio', name: 'mtModo', checked: estado.conStock === valor,
                    onchange: () => { estado.conStock = valor; actualizar(); } }), h('span', null, h('strong', null, titulo), h('small', null, nota)))));
        function actualizar() {
            notaStock.hidden = !estado.conStock || (datos.activo && !datos.pendientes.length);
            const cantidades = {};
            let invalido = false;
            inputs.forEach(({ t, input }) => {
                estado.cantidades[t] = input.value;
                cantidades[t] = Number(input.value || 0);
                const ok = input.validity.valid && Number.isSafeInteger(cantidades[t]);
                input.setAttribute('aria-invalid', String(!ok)); invalido ||= !ok;
            });
            const calc = invalido ? { aviso: 'Usa cantidades enteras entre 0 y 1,000,000 por tipo de tarjeta.' } :
                calcular(datos, cantidades, estado.conStock);
            if (calc.aviso) { aviso.textContent = calc.aviso; resultado.replaceChildren(); return; }
            const filas = calc.filas, conStock = estado.conStock, n = filas.filter(f => f.pedir > 0).length;
            const resumen = `${formato.format(n)} de ${formato.format(filas.length)} ${filas.length === 1 ? 'componente' : 'componentes'} para solicitar.`;
            aviso.textContent = n ? resumen : resumen + ' El stock cubre todas las tarjetas.';
            const cols = ['N.º', 'Componente', 'Unidad', 'Necesario', ...(conStock ? ['Disponible'] : []), 'A solicitar'];
            const numero = (label, v, clase = '') => h('td', { 'data-l': label, class: 'mono ' + clase }, formato.format(v));
            resultado.replaceChildren(h('div', { class: 'i-tabla' }, h('table', { class: 'grid mt-tabla', 'aria-label': 'Desglose de la solicitud' },
                h('thead', null, h('tr', null, cols.map(c => h('th', { scope: 'col' }, c)))),
                h('tbody', null, filas.map((f, i) => h('tr', null, numero('N.º', i + 1), h('th', { class: 'i-c-nom', scope: 'row' }, f.nombre),
                    h('td', { 'data-l': 'Unidad' }, f.unidad || '—'), numero('Necesario', f.necesario),
                    conStock ? numero('Disponible', f.disponible) : null, numero('A solicitar', f.pedir, 'mt-pedir')))))),
                h('button', { type: 'button', class: 'btn', onclick: () => descargar(datos, filas, conStock, cantidades, n) }, icon('download'), 'Descargar solicitud CSV'));
        }
        actualizar();
        return h('section', { class: 'mt-plan' },
            h('div', { class: 'x-caja' }, h('h2', { class: 'c-grupo-t' }, 'Solicitud de material'),
                h('p', { class: 'x-intro' }, datos.tarjetas.length > 1 ? 'Indica ' + (datos.etiqueta ? 'los productos' : 'las tarjetas') + ' que vas a fabricar. Para equipos completos, pon la misma cantidad en ' + datos.tarjetas.join(' y ') + '.' : 'Indica cuántas ' + (datos.etiqueta ? 'unidades' : 'tarjetas') + ' vas a fabricar.'),
                h('div', { class: 'mt-cantidades' }, inputs.map(x => x.campo)), modos),
            h('div', { class: 'mt-plan-bar' }, aviso,
                h('button', { type: 'button', class: 'btn btn-sm', onclick: recargar }, icon('refresh'), 'Actualizar existencias')),
            notaStock,
            resultado, h('p', { class: 'c-kpi-n' }, 'Es una estimación: no reserva material ni genera movimientos.'));
    };
})();
