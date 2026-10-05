/**
 * sec_excel.js - Excel del lote: sincronizar el lote con su Excel mensual y descargar una copia.
 * API: POST /api/sync/excel?lote_id= (423 = Excel abierto) · GET /api/admin/export/excel?lote_id= (fetch + blob: exige sesión)
 */
(function () {
    'use strict';
    const E = window.TQTEscritorio;
    const historial = [];   // resultados de esta sesión de la consola (sobrevive al cambio de sección)
    E.registrar({
        id: 'excel', titulo: 'Excel', icono: 'excel', grupo: 'gestion', orden: 90,
        montar(host, ctx) {
            const { T, api, h, icon, toast } = ctx;
            const salida = h('div', { class: 'stack', 'aria-live': 'polite' });
            const histUl = h('ul', { class: 'esc-hist-sync', 'aria-label': 'Resultados de esta sesión' });
            const histCard = h('section', { class: 'esc-card', hidden: true, 'aria-labelledby': 'xlHT' }, h('header', null, h('h2', { id: 'xlHT' }, 'Esta sesión')), histUl);
            const lote = () => ctx.lote();
            const loteQ = () => (lote() ? `?lote_id=${lote().id}` : '');
            const bSync = h('button', { class: 'btn btn-primary', type: 'button', onclick: sincronizar }, icon('excel'), h('span', null, 'Sincronizar Excel'));
            const bDown = h('button', { class: 'btn', type: 'button', onclick: descargar }, icon('download'), h('span', null, 'Descargar copia (.xlsx)'));
            const titulo = h('b', { class: 'nm', style: 'font-size:18px' });
            const tarj = h('span', { class: 'muted' });

            function anotar(kind, texto) {
                historial.unshift({ kind, texto, t: T.hora() }); historial.length = Math.min(historial.length, 12); pintarHist();
            }
            function pintarHist() {
                histUl.replaceChildren(...historial.map((x) => h('li', null, h('time', null, x.t), h('span', null, x.texto))));
                histCard.hidden = !historial.length;
            }
            function pintarLote() { const l = lote(); titulo.textContent = l ? `Lote ${T.loteNombre(l)}` : 'Sin lote'; tarj.textContent = l ? `${l.tarjetas || 0} tarjetas${l.activo ? ' · lote activo' : ''}` : ''; bSync.disabled = !l; bDown.disabled = !l; }

            async function sincronizar() {
                const l = lote(); if (!l) return;
                bSync.disabled = true; bSync.lastChild.textContent = 'Sincronizando…'; salida.replaceChildren(h('div', { class: 'sk', style: 'height:56px', role: 'status' }, h('span', { class: 'sr-only' }, 'Sincronizando con el Excel…')));
                const r = await api(`/api/sync/excel${loteQ()}`, { method: 'POST', timeout: 90000 });
                bSync.disabled = false; bSync.lastChild.textContent = 'Sincronizar Excel'; salida.replaceChildren();
                const d = r.data || {};
                if (r.ok && d.success !== false) {
                    const n = d.total_tarjetas !== undefined ? d.total_tarjetas : (d.exported_tarjetas || 0);
                    salida.append(T.banner('ok', 'check', h('b', null, d.mensaje || `Excel sincronizado con ${n} tarjetas.`), d.filename ? ` Archivo: ${d.filename}.` : ''));
                    const av = (d.avisos || []).filter(Boolean);
                    if (av.length) salida.append(T.banner('warn', 'alert', h('div', null, h('b', null, `${av.length} aviso${av.length === 1 ? '' : 's'} del Excel`), h('ul', { class: 'esc-avisos' }, av.map((a) => h('li', null, a))))));
                    anotar('ok', `${T.loteNombre(l)}: sincronizado (${n} tarjetas${av.length ? `, ${av.length} avisos` : ''})`);
                } else {
                    const tit = r.status === 423 ? 'El Excel está abierto. ' : r.network ? 'Sin conexión. ' : 'No se pudo sincronizar. ';
                    salida.append(T.banner('bad', 'alert', h('b', null, tit), r.status === 423 ? 'Ciérralo en Excel y vuelve a sincronizar.' : (r.error || 'Intenta de nuevo.')));
                    anotar('bad', `${T.loteNombre(l)}: ${tit.trim()}`);
                }
            }
            async function descargar() {
                const l = lote(); if (!l) return;
                bDown.disabled = true; bDown.lastChild.textContent = 'Preparando…'; salida.replaceChildren();
                try {
                    const res = await fetch(`/api/admin/export/excel${loteQ()}`);
                    if (res.status === 401) { location.href = '/admin?next=' + encodeURIComponent('/monitor#/excel?descargar=1'); return; }
                    if (!res.ok) {
                        let det = ''; try { const j = await res.json(); det = typeof j.detail === 'string' ? j.detail : ''; } catch (e) { det = ''; }
                        salida.append(T.banner('bad', 'alert', h('b', null, res.status === 404 ? 'Todavía no hay Excel de este lote. ' : 'No se pudo descargar. '), det || (res.status === 404 ? 'Pulsa "Sincronizar Excel" primero.' : `Error ${res.status}.`)));
                        return;
                    }
                    const blob = await res.blob();
                    const cd = res.headers.get('Content-Disposition') || ''; const m = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(cd);
                    const nombre = m ? decodeURIComponent(m[1]) : `Control_Produccion_TQT_${T.loteNombre(l).replace(' ', '_')}.xlsx`;
                    const url = URL.createObjectURL(blob); const a = h('a', { href: url, download: nombre }); document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 4000);
                    salida.append(T.banner('ok', 'check', h('b', null, 'Copia descargada. '), `${nombre} (${Math.max(1, Math.round(blob.size / 1024))} KB). El archivo mensual en uso no se tocó.`));
                    anotar('ok', `${T.loteNombre(l)}: copia descargada`);
                    toast('Copia del Excel descargada', { kind: 'ok' });
                } catch (e) {
                    salida.append(T.banner('bad', 'alert', h('b', null, 'Sin conexión. '), 'No se pudo descargar la copia.'));
                } finally { bDown.disabled = false; bDown.lastChild.textContent = 'Descargar copia (.xlsx)'; }
            }

            host.append(h('div', { class: 'esc-narrow stack' },
                h('section', { class: 'esc-card', 'aria-labelledby': 'xlT' },
                    h('header', null, icon('excel'), h('h2', { id: 'xlT' }, 'Excel mensual del lote')),
                    h('div', { class: 'row wrap' }, titulo, tarj),
                    h('p', { class: 'muted' }, 'Sincronizar escribe las tarjetas del lote en su archivo mensual (fórmulas y validaciones intactas). La copia descargable es una plantilla nueva con los datos del lote; no toca el archivo en uso.'),
                    h('div', { class: 'row wrap' }, bSync, bDown)),
                salida, histCard));
            pintarLote(); pintarHist();
            // Volvemos del login de administración con la descarga pendiente: se hace sola (una vez) y se limpia la marca de la URL
            if (/[?&]descargar=1/.test(location.hash)) { try { history.replaceState(null, '', '#/excel'); } catch (e) { /* nada */ } if (lote()) descargar(); }
            ctx.alCambiarLote(() => { pintarLote(); salida.replaceChildren(); });
            return { actualizar() { ctx.recargarLotes().then(pintarLote); } };
        },
    });
})();
