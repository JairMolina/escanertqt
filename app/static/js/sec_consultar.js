/**
 * sec_consultar.js - Consulta SIN cámara: se escribe o pega el número de tarjeta, el nombre de una PCB, una MAC
 * o el texto de 4 líneas de la etiqueta DYMO y se muestra la ficha con las tres placas (Hardware, Firmware, MAC).
 * API: GET /api/consulta?codigo=   ·   URL: #/consultar?codigo=<texto>
 */
(function () {
    'use strict';
    const E = window.TQTEscritorio;
    const CLAVE = 'tqt.consultas';
    E.registrar({
        id: 'consultar', titulo: 'Consultar', icono: 'consultar', grupo: 'operacion', orden: 50,
        montar(host, ctx) {
            const { T, api, h, icon, util } = ctx;
            const st = { ultimo: '', busy: false, hist: [] };
            try { const j = JSON.parse(localStorage.getItem(CLAVE) || '[]'); if (Array.isArray(j)) st.hist = j.filter((x) => typeof x === 'string').slice(0, 12); } catch (e) { st.hist = []; }
            const guardar = () => { try { localStorage.setItem(CLAVE, JSON.stringify(st.hist)); } catch (e) { /* modo privado */ } };

            const q = h('textarea', { class: 'input', id: 'consQ', rows: '5', 'data-buscar': '1', spellcheck: 'false', autocomplete: 'off', 'aria-describedby': 'consAyuda',
                placeholder: 'TQT-R1-V30-0021\n70:4b:ca:5b:9f:6e\nTQT-R2-V30-0010\n70:4b:ca:5b:9c:a2' });
            const btn = h('button', { class: 'btn btn-primary', type: 'submit' }, icon('search'), 'Consultar');
            const out = h('div', { 'aria-live': 'polite', 'aria-busy': 'false' });
            const histUl = h('ul', { class: 'esc-hist', 'aria-label': 'Consultas recientes' });
            const histCard = h('section', { class: 'esc-card', hidden: true, 'aria-labelledby': 'consHT' },
                h('header', null, h('h2', { id: 'consHT' }, 'Consultas recientes'), h('div', { class: 'grow' }), h('button', { class: 'btn btn-sm btn-ghost', type: 'button', onclick: () => { st.hist = []; guardar(); pintarHist(); } }, 'Borrar')), histUl);

            function pintarHist() {
                histUl.replaceChildren(...st.hist.map((t) => h('li', null, h('button', { type: 'button', title: t, onclick: () => { q.value = t; buscar(t); } }, t.split(/\r?\n/).filter(Boolean).join(' · ')))));
                histCard.hidden = !st.hist.length;
            }
            function recordar(t) { st.hist = [t, ...st.hist.filter((x) => x !== t)].slice(0, 12); guardar(); pintarHist(); }

            function vacio() {
                out.replaceChildren(h('div', { class: 'esc-pista-vacia' }, T.empty('consultar', 'Escribe o pega un código', 'Sirve el número de tarjeta (0011), el nombre de una PCB, una MAC o las 4 líneas de la etiqueta. Se busca al pulsar Enter.')));
            }
            function ficha(d) {
                const t = d.tarjeta; const leidos = new Set((d.leidas || []).map((x) => x.nombre).filter(Boolean));
                const cuerpo = h('div', { class: 'esc-ficha' });
                (d.avisos || []).forEach((a) => cuerpo.append(T.banner('warn', 'alert', a)));
                const nueva = h('button', { class: 'btn btn-ghost', type: 'button', onclick: () => { st.ultimo = ''; q.value = ''; vacio(); history.replaceState(null, '', '#/consultar'); q.focus(); } }, icon('refresh'), 'Nueva consulta');
                const ORIGEN = { etiqueta: 'Leída de la etiqueta', pcb: 'Encontrada por el nombre de una PCB', mac: 'Encontrada por MAC', tarjeta: 'Encontrada por número', serie: 'Placas con ese número' };
                if (t) {
                    const conFw = (s) => { const p = t[s]; return p ? Object.assign({}, p, { firmware: p.firmware || t['firmware_' + s] || null }) : null; };
                    cuerpo.append(h('div', { class: 'esc-ficha-cab' },
                        h('div', null, h('div', { class: 'silk', style: 'margin-bottom:4px' }, 'Tarjeta'), h('div', { class: 'num', 'aria-label': 'Tarjeta ' + t.id_tarjeta_num }, t.id_tarjeta_num)),
                        h('div', { class: 'meta' }, T.tarjetaBadge(t), h('span', { class: 'hint' }, ORIGEN[d.origen] || ''))),
                        T.estatusTarjeta(t, { onGuardado: () => { ctx.invalidar(); if (st.ultimo) buscar(st.ultimo, true); } }),
                        h('div', { class: 'esc-placas' }, ['r1', 'r2', 'r3'].map((s) => { const p = conFw(s); return util.placaCard(s.toUpperCase(), p, p && leidos.has(p.nombre)); })),
                        h('div', { class: 'esc-bar' },
                            h('a', { class: 'btn btn-primary', href: `/dymo?tarjeta_id=${t.id}` }, icon('printer'), 'Etiqueta DYMO'),
                            h('button', { class: 'btn', type: 'button', onclick: () => util.copiar(util.resumenTarjeta(Object.assign({}, t, { r1: conFw('r1'), r2: conFw('r2') })), 'Datos copiados') }, icon('paste'), 'Copiar datos'),
                            h('a', { class: 'btn', href: `#/tarjetas?id=${t.id}` }, icon('card'), 'Ver en Tarjetas'), nueva));
                } else if (d.serie) {   // número sin tarjeta: las placas que tienen ese número
                    cuerpo.append(h('div', { class: 'esc-ficha-cab' },
                        h('div', null, h('div', { class: 'silk', style: 'margin-bottom:4px' }, 'Número'), h('div', { class: 'num', 'aria-label': 'Número ' + d.serie.numero }, d.serie.numero)),
                        h('div', { class: 'meta' }, T.badge('Sin tarjeta', 'warn', 'alert'), h('span', { class: 'hint' }, ORIGEN.serie))),
                        h('div', { class: 'esc-placas' }, ['r1', 'r2', 'r3'].map((s) => util.placaCard(s.toUpperCase(), d.serie[s], false))),
                        h('div', { class: 'esc-bar' }, h('a', { class: 'btn btn-primary', href: '#/tarjetas', 'data-escribe': true }, icon('link'), 'Ir a emparejar'), nueva));
                } else if (d.pcb) {
                    cuerpo.append(h('div', { class: 'esc-ficha-cab' }, h('div', null, h('div', { class: 'silk', style: 'margin-bottom:4px' }, 'Placa suelta'), h('div', { class: 'hint' }, 'Esta placa todavía no está en una tarjeta.'))),
                        h('div', { class: 'esc-placas', style: 'grid-template-columns:minmax(0,420px)' }, util.placaCard(d.pcb.tipo, d.pcb, true)), h('div', { class: 'esc-bar' }, nueva));
                }
                out.replaceChildren(cuerpo);
            }
            async function buscar(texto, silencioso) {
                const c = String(texto || '').trim();
                if (!c) { q.focus(); return; }
                if (st.busy) return;
                if (silencioso && document.activeElement && document.activeElement.closest('.estatus-entrega')) return;   // no borrar lo que se está capturando
                st.busy = true; btn.disabled = true; out.setAttribute('aria-busy', 'true');
                if (!silencioso) out.replaceChildren(h('div', { class: 'stack', role: 'status' }, h('span', { class: 'sr-only' }, 'Buscando…'), h('div', { class: 'sk', style: 'height:90px;width:60%' }), h('div', { class: 'sk', style: 'height:160px' })));
                const r = await api(`/api/consulta?codigo=${encodeURIComponent(c)}`);
                st.busy = false; btn.disabled = false; out.setAttribute('aria-busy', 'false');
                st.ultimo = c;
                const dest = `#/consultar?codigo=${encodeURIComponent(c)}`; if (location.hash !== dest && decodeURIComponent(location.hash) !== decodeURIComponent(dest)) history.replaceState(null, '', dest);
                if (!r.ok) {
                    const causa = r.network ? 'No hay conexión con el servidor. Revisa la red y vuelve a intentar.' : (r.error || 'Intenta de nuevo.');
                    out.replaceChildren(h('div', { class: 'stack' },
                        T.banner('bad', 'alert', h('b', null, r.status === 404 ? 'No encontramos ese código. ' : r.status === 400 ? 'No se reconoce ese código. ' : r.network ? 'Sin conexión. ' : 'No se pudo consultar. '), causa),
                        T.empty('consultar', 'Revisa el código', 'Escribe el número de tarjeta (0011), el nombre completo de la PCB (TQT-R1-V30-0021), la MAC o pega las 4 líneas de la etiqueta.')));
                    return;
                }
                recordar(c); ficha(r.data);
            }
            const form = h('form', { class: 'esc-cons-form', onsubmit: (e) => { e.preventDefault(); buscar(q.value); } },
                h('div', { class: 'field' }, h('label', { for: 'consQ' }, 'Código a consultar'), q),
                h('p', { class: 'hint', id: 'consAyuda' }, 'Número de tarjeta, nombre de PCB, MAC o las 4 líneas de la etiqueta. ',
                    h('kbd', { class: 'esc-k' }, 'Enter'), ' consulta; ', h('kbd', { class: 'esc-k' }, 'Shift'), '+', h('kbd', { class: 'esc-k' }, 'Enter'), ' agrega una línea.'),
                h('div', { class: 'row' }, btn, h('button', { class: 'btn btn-ghost', type: 'button', onclick: () => { q.value = ''; q.focus(); } }, 'Limpiar')), histCard);
            q.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); buscar(q.value); } });

            host.append(h('div', { class: 'esc-cons' }, form, out));
            pintarHist(); vacio();
            const inicial = ctx.params().get('codigo');
            if (inicial) { q.value = inicial; buscar(inicial); } else q.focus();
            return {
                actualizar() { if (st.ultimo) buscar(st.ultimo, true); },
                parametros(p) { const c = p.get('codigo'); if (c && c !== st.ultimo) { q.value = c; buscar(c); } else if (!c) { st.ultimo = ''; q.value = ''; vacio(); } },
            };
        },
    });
})();
