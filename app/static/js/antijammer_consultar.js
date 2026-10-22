/* antijammer_consultar.js - Pestaña Consultar: escanear/teclear una placa → ficha (hardware, firmware, estado, lote, fechas,
 * operador) e historial de eventos. Solo lectura: sirve también al rol consultor.
 * API: GET /api/antijammer/pcb/por-codigo?codigo= → {pcb, eventos} | 404 */
(function () {
    'use strict';
    const T = window.TQT, P = window.AJ;
    const { h, icon } = T;
    const ACCION = { RECIBIDA: 'Recibida', PROGRAMADA: 'Programada', EDITADA: 'Editada', ELIMINADA: 'Eliminada', MASA: 'Cambio en masa' };
    let sec = null, ui = {}, ultimo = '', seq = 0;

    function inicial() {
        ui.res.replaceChildren(h('div', { class: 'c-vacio' },
            icon('consultar'), h('b', null, 'Busca una placa'),
            h('span', null, 'Escanea su QR o escribe el nombre o la serie para ver su ficha y su historial.')));
    }

    async function buscar(texto) {
        const codigo = P.normal(texto);
        if (!codigo) return { ok: false, texto: 'Código vacío' };
        const otro = P.ajeno(codigo);
        if (otro) { ++seq; P.sonar.mal(); ui.res.replaceChildren(h('div', { class: 'c-vacio' }, icon('alert'), h('b', null, 'Ese código no es de Skudo AntiJammer'), h('span', null, otro))); return { ok: false, texto: otro }; }
        ultimo = codigo; const n = ++seq;
        P.cam.bloquear();
        ui.res.setAttribute('aria-busy', 'true');
        ui.res.replaceChildren(h('div', { class: 'tp-carga' }, h('span', { class: 'tp-giro', 'aria-hidden': 'true' }), 'Buscando ' + codigo + '…'));
        const r = await P.porCodigo(codigo);
        if (n !== seq) return { ok: true, texto: 'Consultando ' + codigo };   // llegó otra búsqueda
        P.cam.liberar(); ui.res.removeAttribute('aria-busy');
        if (r.status === 404) {
            P.sonar.mal();
            ui.res.replaceChildren(h('div', { class: 'c-vacio' }, icon('alert'), h('b', null, `${codigo} no está registrada`),
                h('span', null, 'Revisa la serie o regístrala en Recibir si es una placa nueva.'),
                P.soloLectura() ? null : h('button', { class: 'btn', type: 'button', onclick: () => P.abrir('recibir') }, icon('recibir'), 'Ir a Recibir')));
            return { ok: false, texto: `${codigo} no está registrada en Skudo AntiJammer` };
        }
        if (!r.ok) { P.sonar.mal(); ui.res.replaceChildren(P.error((r.error || 'No se pudo consultar la placa.') + ' Revisa la conexión.', () => buscar(ultimo))); return { ok: false, texto: r.error || 'No se pudo consultar la placa' }; }
        P.sonar.ok();
        ficha(r.data.pcb, r.data.eventos || []);
        return { ok: true, texto: `Ficha de ${r.data.pcb.nombre} abierta` };
    }

    function dato(t, v, mono) { return h('div', null, h('dt', null, t), h('dd', { class: mono ? 'mono' : null }, v == null || v === '' ? '—' : v)); }

    function ficha(p, eventos) {
        const evs = eventos.slice().sort((a, b) => String(b.creado_en || '').localeCompare(String(a.creado_en || '')));
        ui.res.replaceChildren(
            h('article', { class: 'c-ficha', dataset: { estado: p.estado || '' }, 'aria-labelledby': 'cNom' },
                h('header', { class: 'c-cab' },
                    h('h2', { class: 'c-nom mono', id: 'cNom' }, p.nombre),
                    P.estadoBadge(p.estado)),
                h('dl', { class: 'c-datos' },
                    dato('Hardware', P.hw(p.version), true),
                    dato('Firmware', p.firmware || 'Sin firmware', true),
                    dato('Serie', p.serie, true),
                    dato('Lote', p.lote),
                    dato('Recibida', P.fecha(p.recibida_en)),
                    dato('Programada', p.programada_en ? P.fecha(p.programada_en) : 'Aún no'),
                    dato('Última actualización', P.fecha(p.actualizado_en)),
                    dato('Operador', p.operador),
                    p.nota ? dato('Nota', p.nota) : null,
                    dato('Código leído', p.codigo_qr, true)),
                P.soloLectura() ? null : h('div', { class: 'c-acc' },
                    h('button', { class: 'btn', type: 'button', onclick: () => P.abrir('programar', p.nombre) }, icon('programar'), 'Programar esta placa'))),
            h('section', { class: 'c-hist', 'aria-labelledby': 'cHistT' },
                h('h2', { id: 'cHistT' }, 'Historial'),
                evs.length
                    ? h('ol', { class: 'c-linea' }, evs.map((e) => h('li', null,
                        h('span', { class: 'c-acc-n' }, ACCION[e.accion] || e.accion || 'Evento'),
                        e.detalle ? h('span', { class: 'c-det' }, e.detalle) : null,
                        h('span', { class: 'c-meta' }, P.fecha(e.creado_en) + (e.operador ? ' · ' + e.operador : '')))))
                    : h('p', { class: 'hist-vacio' }, 'Esta placa todavía no tiene eventos registrados.')));
    }

    P.registrar('consultar', {
        montar(el) {
            sec = el;
            ui.cod = h('input', { class: 'input mono', id: 'cCod', type: 'text', autocomplete: 'off', autocapitalize: 'characters', spellcheck: 'false', maxlength: '300', enterkeyhint: 'search', 'aria-describedby': 'cCodAy' });
            ui.res = h('div', { class: 'c-res', 'aria-live': 'polite' });
            const f = h('form', { class: 'p-buscar', novalidate: true, onsubmit: (e) => {
                e.preventDefault();
                if (!ui.cod.value.trim()) { ui.cod.focus(); T.toast('Escribe el código o la serie de la placa', { kind: 'warn' }); return; }
                buscar(ui.cod.value);
            } }, h('div', { class: 'field' }, h('label', { for: 'cCod' }, 'Placa'),
                h('div', { class: 'man-fila' }, ui.cod, h('button', { class: 'btn', type: 'submit' }, icon('search'), 'Consultar')),
                h('p', { class: 'ayuda', id: 'cCodAy' }, 'QR, nombre (SJ-V1-0004) o solo la serie.')));
            el.querySelector('#cLado').replaceChildren(f, ui.res);
            inicial();
            document.addEventListener('antijammer:cambio', () => { if (sec.hidden && ultimo && ui.res.querySelector('.c-ficha')) ui.stale = true; });   // se refresca al volver
        },
        entrar() {
            P.cam.unir(sec.querySelector('.cam-slot'), {
                pista: 'Apunta al QR de la placa para ver su ficha.',
                onCode: (t) => { ui.cod.value = ''; buscar(t); },
                onManual: () => ui.cod.focus(),
            });
            if (ui.stale && ultimo) { ui.stale = false; buscar(ultimo); }
        },
        recibirDato(codigo) { if (codigo) { ui.cod.value = codigo; buscar(codigo); } },
        /** v1.4.30: lectura del celular vinculado (botón de escaneo). */
        escaneo(texto) { ui.cod.value = ''; return buscar(texto); },
    });
})();
