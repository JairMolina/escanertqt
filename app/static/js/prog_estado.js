/* v1.4.0: plantilla visual única de estado/progreso de Programación (R1, R2 y R3).
 * Solo presentación: no conoce protocolos ni grabación.
 * TQTProgEstado.crear() -> contenedor; TQTProgEstado.pintar(box, d) lo rellena con:
 *   estado: 'ok'|'warn'|'bad'|'err'   (indicador; además siempre va con texto)
 *   etiqueta, fase, conexion, fw, hw, instalado, vigente, metodo, resultado, error, cancelada
 * Los campos vacíos no se muestran. */
(function () {
    'use strict';
    const h = (tag, attrs, ...kids) => {
        const el = document.createElement(tag);
        for (const [k, v] of Object.entries(attrs || {})) {
            if (v == null || v === false) continue;
            if (k === 'dataset') Object.assign(el.dataset, v); else el.setAttribute(k, v === true ? '' : v);
        }
        kids.flat().forEach(c => { if (c != null && c !== false) el.append(c.nodeType ? c : document.createTextNode(String(c))); });
        return el;
    };
    const ETQ = { ok: 'Programada', warn: 'Programando…', bad: 'Sin programar', err: 'Error al programar' };
    function crear() { return h('div', { class: 'prog-estado', role: 'status', 'aria-live': 'polite' }); }
    function fila(k, v) { return v ? [h('dt', null, k), h('dd', null, v)] : []; }
    function pintar(box, d) {
        if (!box) return;
        d = d || {};
        const s = ETQ[d.estado] ? d.estado : 'bad';
        box.dataset.s = s;
        const fwTxt = d.fw ? 'FW ' + d.fw + (d.hw ? ' · HW ' + d.hw : '') : (d.hw ? 'HW ' + d.hw : '');
        const filas = [
            ...fila('Fase', d.fase),
            ...fila('Conexión', d.conexion),
            ...fila('Firmware', fwTxt),
            ...fila('Instalado / vigente', d.instalado || d.vigente ? (d.instalado || 'sin verificar') + ' / ' + (d.vigente || '—') : ''),
            ...fila('Método', d.metodo),
            ...fila('Resultado', d.resultado),
            ...fila('Error', d.error),
            ...fila('Cancelación', d.cancelada ? 'Programación cancelada' : '')
        ];
        box.replaceChildren(
            h('span', { class: 'prog-luz', 'aria-hidden': 'true' }),
            h('span', { class: 'prog-luz-txt' }, d.etiqueta || ETQ[s]),
            ...(filas.length ? [h('dl', { class: 'prog-est-dl' }, ...filas)] : []));
    }
    window.TQTProgEstado = { crear, pintar, ETIQUETAS: ETQ };
})();
