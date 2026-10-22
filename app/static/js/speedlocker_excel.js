/* speedlocker_excel.js - Exportar a Excel (consola SpeedLocker): mismos filtros que Inventario (parte de los que estén puestos ahí),
 * conteo de lo que saldrá y enlace de descarga. El consultor también puede exportar.
 * API: GET /api/speedlocker/exportar?estado=&version=&firmware=&lote=&q= (.xlsx) · GET /api/speedlocker/pcb?…&limit=1 (conteo) */
(function () {
    'use strict';
    const T = window.TQT, P = window.SL;
    const { h, icon, api } = T;
    const $ = (id) => document.getElementById(id);
    const CLAVES = ['q', 'estado', 'version', 'firmware', 'lote'];
    const f = { q: '', estado: '', version: '', firmware: '', lote: '' };
    let ui = {}, seq = 0;
    const n = (v) => Number(v || 0).toLocaleString('es-MX');
    const consulta = () => { const q = new URLSearchParams(); CLAVES.forEach((k) => { if (f[k]) q.set(k, f[k]); }); return q; };

    function sel(id, etq, clave) {
        const s = h('select', { class: 'input', id, onchange: () => { f[clave] = s.value; actualizar(); } });
        return { s, campo: h('div', { class: 'field' }, h('label', { for: id }, etq), s) };
    }
    async function opciones() {
        const d = await P.resumen();
        const op = (v, t, c) => h('option', { value: v }, c == null ? t : `${t} (${n(c)})`);
        const pon = (x, ops, clave) => {
            if (f[clave] && !ops.some((o) => o.value === f[clave])) ops.push(op(f[clave], f[clave] === '__sin' ? 'Sin firmware' : f[clave]));
            x.s.replaceChildren(op('', 'Todos'), ...ops); x.s.value = f[clave];
        };
        const pe = (d && d.por_estado) || {};
        pon(ui.est, Object.keys(P.ESTADOS).map((k) => op(k, P.ESTADOS[k].txt, d ? pe[k] || 0 : null)), 'estado');
        pon(ui.ver, ((d && d.versiones) || []).map((x) => op(String(x.version), P.hw(x.version), x.n)), 'version');
        const fws = (d && d.firmwares) || [], sin = fws.find((x) => !x.firmware);
        pon(ui.fw, [op('__sin', 'Sin firmware', sin ? sin.n : null)].concat(fws.filter((x) => x.firmware).map((x) => op(x.firmware, x.firmware, x.n))), 'firmware');
        pon(ui.lote, ((d && d.lotes) || []).filter((x) => x.lote).map((x) => op(x.lote, x.lote, x.n)), 'lote');
    }

    async function actualizar() {
        const q = consulta();
        ui.bajar.href = '/api/speedlocker/exportar' + (q.toString() ? '?' + q.toString() : '');
        const k = ++seq;
        ui.cuenta.textContent = 'Contando placas…';
        q.set('limit', '1');
        const r = await api('/api/speedlocker/pcb?' + q.toString());
        if (k !== seq) return;
        if (!r.ok) { ui.cuenta.textContent = 'No se pudo contar las placas; el archivo se puede descargar igual.'; return; }
        const t = (r.data && r.data.total) || 0;
        ui.cuenta.textContent = t === 1 ? 'Saldrá 1 placa en la hoja Placas.' : `Saldrán ${n(t)} placas en la hoja Placas.`;
    }

    P.registrar('excel', {
        montar() {
            ui.q = h('input', { class: 'input', id: 'xQ', type: 'search', autocomplete: 'off', spellcheck: 'false', maxlength: '80', placeholder: 'Nombre, serie, firmware o nota' });
            ui.q.addEventListener('input', T.debounce(() => { f.q = ui.q.value.trim(); actualizar(); }, 300));
            ui.est = sel('xEst', 'Estado', 'estado'); ui.ver = sel('xVer', 'Hardware', 'version');
            ui.fw = sel('xFw', 'Firmware', 'firmware'); ui.lote = sel('xLote', 'Lote', 'lote');
            ui.cuenta = h('p', { class: 'x-cuenta', role: 'status', 'aria-live': 'polite' });
            ui.bajar = h('a', { class: 'btn btn-primary x-bajar', href: '/api/speedlocker/exportar', download: '' }, icon('download'), 'Descargar Excel');
            $('xCuerpo').replaceChildren(h('div', { class: 'x-caja' },
                h('p', { class: 'x-intro' }, 'El archivo trae dos hojas: Placas (nombre, hardware, serie, firmware, estado, lote, nota, operador y fechas) y Movimientos (los últimos 2000).'),
                h('div', { class: 'i-filtros x-filtros', role: 'group', 'aria-label': 'Qué placas exportar' },
                    h('div', { class: 'field i-f-q' }, h('label', { for: 'xQ' }, 'Buscar'), ui.q),
                    ui.est.campo, ui.ver.campo, ui.fw.campo, ui.lote.campo),
                h('div', { class: 'x-pie' }, ui.cuenta,
                    h('div', { class: 'ban-acc' }, ui.bajar,
                        h('button', { class: 'btn', type: 'button', onclick: () => P.abrir('inventario', Object.assign({}, f)) }, icon('list'), 'Ver estas placas en Inventario')))));
        },
        entrar() {
            // parte de los filtros que haya puestos en Inventario
            const inv = P.filtrosInventario ? P.filtrosInventario() : null;
            if (inv) CLAVES.forEach((k) => { f[k] = inv[k] || ''; });
            ui.q.value = f.q;
            opciones(); actualizar();
        },
    });
})();
