/**
 * sec_lotes.js - Lotes mensuales: lista con sus tarjetas, cuál está activo, ver un lote en la consola, usarlo como activo o crear uno.
 * API: GET /api/lotes · POST /api/lotes · POST /api/lotes/{id}/activar (con contraseña de supervisor si está configurada)
 */
(function () {
    'use strict';
    const E = window.TQTEscritorio;
    E.registrar({
        id: 'lotes', titulo: 'Lotes', icono: 'layers', grupo: 'gestion', orden: 60,
        montar(host, ctx) {
            const { T, api, h, icon, toast, util } = ctx;
            let error = ''; let ocupado = false;
            const cont = h('div', { class: 'esc-narrow stack' });

            async function usar(l) {
                if (ocupado) return; ocupado = true; pintar();
                const r = await api(`/api/lotes/${l.id}/activar`, { method: 'POST' });
                ocupado = false;
                if (!r.ok) { error = r.status === 401 ? 'Tu sesión de supervisor caducó. Entra otra vez para usar este lote.' : r.error; pintar(); return; }
                error = ''; toast(`Lote ${T.loteNombre(l)} activo para todos los celulares`, { kind: 'ok' });
                await ctx.recargarLotes(); ctx.seleccionarLote(l.id); pintar();
            }
            function pintar() {
                const lotes = ctx.lotes(); const sel = ctx.lote();
                cont.replaceChildren();
                cont.append(h('div', { class: 'esc-bar' }, h('p', { class: 'muted grow' }, 'El lote activo es el que usan todos los celulares. "Ver" cambia solo lo que muestra esta consola.'),
                    h('button', { class: 'btn btn-primary', type: 'button', onclick: () => ctx.hojaLotes() }, icon('plus'), 'Usar o crear lote…')));
                if (error) cont.append(T.banner('bad', 'alert', error));
                if (!lotes.length) { cont.append(T.empty('layers', 'Todavía no hay lotes', 'Crea el primero con "Usar o crear lote".')); return; }
                cont.append(h('ul', { class: 'esc-lista', 'aria-label': 'Lotes mensuales' }, lotes.map((l) => h('li', { dataset: { activo: l.activo ? '1' : '' } },
                    h('div', { class: 'grow' }, h('div', { class: 'nm' }, T.loteNombre(l), l.activo ? T.badge('Activo', 'ok', 'check') : null, sel && sel.id === l.id ? T.badge('En pantalla', 'accent', 'monitor') : null),
                        h('div', { class: 't2' }, `${l.tarjetas || 0} tarjeta${l.tarjetas === 1 ? '' : 's'} · ${l.codigo_lote || ''}`)),
                    h('div', { class: 'acc' },
                        sel && sel.id === l.id ? null : h('button', { class: 'btn', type: 'button', 'aria-label': `Ver el lote ${T.loteNombre(l)} en la consola`, onclick: () => { ctx.seleccionarLote(l.id); pintar(); } }, icon('monitor'), 'Ver'),
                        l.activo ? null : h('button', { class: 'btn btn-primary', type: 'button', disabled: ocupado ? '' : null, 'aria-label': `Usar el lote ${T.loteNombre(l)} como activo`, onclick: () => usar(l) }, 'Usar como activo'))))));
            }
            pintar(); host.append(cont);
            ctx.alCambiarLote(pintar);
            return { actualizar() { ctx.recargarLotes().then(pintar); } };
        },
    });
})();
