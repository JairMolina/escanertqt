/* antijammer_etiquetas.js - Etiquetas DYMO del gabinete (consola Skudo AntiJammer): elegir una o varias placas (código, buscador,
 * lote o escáner), vista previa a escala 57x32 mm e impresión por DYMO compartida (cola de la Raspberry), DYMO Connect local
 * o diálogo del navegador. Cada QR es una tarjeta: SJ-V1-0052.
 * API: GET /api/antijammer/etiquetas/vista?codigos= · /etiquetas/{nombre}/xml · /etiquetas/estado · POST /etiquetas/imprimir
 *      GET /api/antijammer/pcb/por-codigo · /pcb?q=&lote=&limit= (selección) */
(function () {
    'use strict';
    const T = window.TQT, P = window.AJ;
    const { h, icon, api } = T;
    const $ = (id) => document.getElementById(id);
    const MAX = 100;
    const enc = encodeURIComponent;
    const esMovil = matchMedia('(pointer: coarse) and (max-width: 900px)').matches;
    const sel = [];            // nombres canónicos elegidos
    const svgs = new Map();    // nombre -> svg (vista previa)
    let ui = {}, seq = 0, ocupado = false;
    const nTxt = (n, s, p) => `${n} ${n === 1 ? s : p}`;
    const cargados = {};
    function cargaScript(src) {
        if (!cargados[src]) {
            cargados[src] = new Promise((ok, ko) => {
                const s = document.createElement('script'); s.src = src; s.onload = ok;
                s.onerror = () => { delete cargados[src]; ko(new Error('No se pudo cargar ' + src.split('?')[0])); };
                document.head.appendChild(s);
            });
        }
        return cargados[src];
    }

    function msg(k, texto) {
        ui.msg.hidden = !texto; ui.msg.dataset.k = k || ''; ui.msg.textContent = texto || '';
    }

    // ------------------------------------------------------------------ selección
    function agrega(nombres) {
        let nuevos = 0, lleno = false;
        nombres.forEach((n) => {
            if (!n || sel.includes(n)) return;
            if (sel.length >= MAX) { lleno = true; return; }
            sel.push(n); nuevos++;
        });
        if (lleno) msg('warn', `Se alcanzó el máximo de ${MAX} etiquetas por tanda.`);
        else if (nuevos) msg('', '');
        pintaSel();
        return nuevos;
    }
    function quita(n) { const i = sel.indexOf(n); if (i >= 0) sel.splice(i, 1); pintaSel(); }

    async function agregaPorCodigo(texto) {
        const c = P.normal(texto);
        if (!c) return { ok: false, texto: 'Escribe o escanea un código.' };
        const r = await P.porCodigo(c);
        if (!r.ok) { P.sonar.mal(); msg('bad', r.error || 'No se encontró esa placa.'); return { ok: false, texto: r.error || 'No se encontró esa placa.' }; }
        const n = r.data.pcb.nombre;
        const nuevo = agrega([n]);
        (nuevo ? P.sonar.ok : P.sonar.dup)();
        return { ok: true, texto: nuevo ? `${n} agregada a las etiquetas` : `${n} ya estaba en la lista` };
    }

    const sugiere = T.debounce(async () => {
        const q = ui.q.value.trim();
        if (q.length < 2) { ui.sug.replaceChildren(); ui.sug.hidden = true; return; }
        const r = await api('/api/antijammer/pcb?limit=8&q=' + enc(q));
        const items = r.ok ? (r.data.items || []) : [];
        ui.sug.hidden = !items.length;
        ui.sug.replaceChildren(...items.map((p) => h('button', { class: 'et-sug-op', type: 'button', onclick: () => { agrega([p.nombre]); ui.q.value = ''; ui.sug.hidden = true; ui.q.focus(); } },
            h('b', { class: 'mono' }, p.nombre), h('small', null, [p.lote ? 'Lote ' + p.lote : '', P.fecha(p.recibida_en, false)].filter(Boolean).join(' · ')))));
    }, 250);

    async function agregaLote() {
        const lote = ui.lote.value;
        if (!lote) return;
        const r = await api('/api/antijammer/pcb?limit=' + MAX + '&lote=' + enc(lote));
        if (!r.ok) { msg('bad', r.error || 'No se pudo leer el lote.'); return; }
        const items = (r.data.items || []).map((p) => p.nombre).reverse();
        const nuevos = agrega(items);
        if (r.data.total > MAX) msg('warn', `El lote tiene ${r.data.total} placas; se tomaron las ${MAX} más recientes.`);
        else if (!nuevos) msg('info', 'Esas placas ya estaban en la lista.');
    }

    async function cargaLotes() {
        const d = await P.resumen();
        const lotes = ((d && d.lotes) || []).filter((x) => x.lote);
        ui.lote.replaceChildren(h('option', { value: '' }, lotes.length ? 'Elige un lote' : 'Sin lotes'), ...lotes.map((x) => h('option', { value: x.lote }, `${x.lote} (${x.n})`)));
        ui.lote.disabled = ui.bLote.disabled = !lotes.length;
    }

    // ------------------------------------------------------------------ vista previa
    function pintaSel() {
        const n = sel.length;
        ui.cuenta.textContent = n ? nTxt(n, 'etiqueta', 'etiquetas') + ' en la lista' : 'Aún no hay placas elegidas';
        ui.vacio.hidden = n > 0;
        ui.bImp.disabled = ocupado || !n; ui.bVaciar.disabled = !n;
        ui.grilla.replaceChildren(...sel.map((nom) => {
            const caja = h('div', { class: 'et-lamina', 'data-nombre': nom });
            const s = svgs.get(nom);
            if (s) caja.innerHTML = s;   // SVG generado por el servidor con el texto escapado
            else caja.appendChild(h('span', { class: 'et-carga' }, 'Cargando…'));
            return h('figure', { class: 'et-item' }, caja,
                h('figcaption', null, h('span', { class: 'mono' }, nom),
                    h('button', { class: 'iconbtn et-quita', type: 'button', 'aria-label': 'Quitar ' + nom, title: 'Quitar', onclick: () => quita(nom) }, icon('x'))));
        }));
        vista();
    }
    async function vista() {
        const faltan = sel.filter((x) => !svgs.has(x));
        if (!faltan.length) return;
        const k = ++seq;
        const r = await api('/api/antijammer/etiquetas/vista?codigos=' + enc(faltan.join(',')));
        if (k !== seq) return;
        if (!r.ok) { msg('bad', r.error || 'No se pudo generar la vista previa.'); return; }
        (r.data.items || []).forEach((it) => svgs.set(it.nombre, it.svg));
        (r.data.faltan || []).forEach((c) => { const i = sel.indexOf(c); if (i >= 0) sel.splice(i, 1); });
        pintaSel();
    }

    // ------------------------------------------------------------------ impresión
    function bloquea(v) { ocupado = v; ui.bImp.disabled = v || !sel.length; ui.via.disabled = ui.copias.disabled = v; }
    const copias = () => Math.min(5, Math.max(1, parseInt(ui.copias.value, 10) || 1));

    async function imprime() {
        if (ocupado || !sel.length) return;
        const via = ui.via.value, lista = sel.slice(), c = copias();
        bloquea(true);
        try {
            if (via === 'compartida') {
                msg('info', 'Enviando a la DYMO compartida…');
                const r = await api('/api/antijammer/etiquetas/imprimir', { method: 'POST', body: { codigos: lista, copias: c }, timeout: 120000 });
                if (!r.ok) { msg('bad', r.error || 'No se pudo enviar a imprimir'); return; }
                const er = r.data.errores || [], ok = r.data.encolados || 0;
                const det = er.slice(0, 4).map((e) => `${e.codigo}: ${e.detail}`).join(' · ') + (er.length > 4 ? ` · y ${er.length - 4} más` : '');
                msg(er.length ? 'warn' : 'ok', `${nTxt(ok, 'etiqueta encolada', 'etiquetas encoladas')} en la DYMO compartida.` + (er.length ? ` ${nTxt(er.length, 'con error', 'con errores')}: ${det}` : ''));
                if (ok) T.toast(`${nTxt(ok, 'etiqueta encolada', 'etiquetas encoladas')}`, { kind: 'ok' });
                estado();
            } else if (via === 'connect') {
                msg('info', 'Buscando DYMO Connect en este equipo…');
                await cargaScript('/static/js/vendor/dymo.connect.framework.js?v=1316'); await cargaScript('/static/js/dymo_connect.js?v=1389');
                const d = await window.TQTDymo.detect();
                if (d.estado !== 'listo') {
                    msg('bad', { movil: 'Desde un celular no se puede imprimir directo en la DYMO.', sin_framework: 'No se pudo cargar el componente de DYMO Connect.',
                        no_servicio: 'No se encontró DYMO Connect en este equipo. Ábrelo (o instálalo) y vuelve a intentar.', sin_impresoras: 'DYMO Connect no ve ninguna LabelWriter. Conéctala y enciéndela.' }[d.estado] || d.detalle);
                    return;
                }
                let hechas = 0;
                for (const nom of lista) {
                    const rx = await fetch(`/api/antijammer/etiquetas/${enc(nom)}/xml`, { cache: 'no-store' });
                    if (!rx.ok) { let det = ''; try { det = (await rx.json()).detail; } catch (e) { /* nada */ } msg('bad', `${nom}: ${det || 'el servidor respondió ' + rx.status}`); return; }
                    msg('info', `Imprimiendo ${nom} en ${d.preferred} (${hechas + 1}/${lista.length})…`);
                    await window.TQTDymo.print(d.preferred, await rx.text(), c);
                    hechas++;
                }
                msg('ok', `${nTxt(hechas, 'etiqueta enviada', 'etiquetas enviadas')} a ${d.preferred}.`);
                T.toast(`${nTxt(hechas, 'etiqueta enviada', 'etiquetas enviadas')}`, { kind: 'ok' });
            } else {
                msg('info', 'Preparando las etiquetas…');
                const faltan = lista.filter((x) => !svgs.has(x));
                if (faltan.length) { await vista(); }
                const hojas = lista.filter((x) => svgs.has(x)).flatMap((x) => Array(c).fill(svgs.get(x)));
                const fr = h('iframe', { style: 'position:fixed;right:0;bottom:0;width:0;height:0;border:0', 'aria-hidden': 'true', tabindex: '-1', title: 'Impresión' });
                document.body.appendChild(fr);
                const doc = fr.contentWindow.document; doc.open();
                doc.write('<!doctype html><html><head><meta charset="utf-8"><title>Etiquetas AntiJammer</title><style>@page{size:57mm 32mm;margin:0}html,body{margin:0;background:#fff}'
                    + '.p{width:57mm;height:32mm;overflow:hidden;page-break-after:always;break-after:page}svg{display:block}</style></head><body>'
                    + hojas.map((s) => `<div class="p">${s}</div>`).join('') + '</body></html>');
                doc.close();
                fr.contentWindow.focus(); fr.contentWindow.print();
                setTimeout(() => fr.remove(), 2000);
                msg('info', 'Se abrió el diálogo de impresión del navegador (tamaño 57 x 32 mm, sin márgenes).');
            }
        } catch (e) {
            msg('bad', (e && e.message) || 'No se pudo imprimir');
        } finally {
            bloquea(false);
        }
    }

    async function estado() {
        const r = await api('/api/antijammer/etiquetas/estado');
        const d = r.ok ? r.data : null;
        ui.estado.textContent = !d ? 'No se pudo consultar la DYMO compartida.'
            : d.disponible ? 'DYMO compartida en línea y lista.' : 'DYMO compartida no disponible ahora (puedes usar DYMO Connect o el navegador).';
        ui.estado.dataset.k = !d ? '' : d.disponible ? 'ok' : 'warn';
    }

    P.registrar('etiquetas', {
        montar() {
            ui.q = h('input', { class: 'input', id: 'etQ', type: 'search', autocomplete: 'off', spellcheck: 'false', maxlength: '80', placeholder: 'SJ-V1-0052, serie o lote' });
            ui.q.addEventListener('input', sugiere);
            ui.q.addEventListener('keydown', async (e) => {
                if (e.key !== 'Enter') return;
                e.preventDefault();
                const t = ui.q.value; ui.q.value = ''; ui.sug.hidden = true;
                await agregaPorCodigo(t);
            });
            ui.sug = h('div', { class: 'et-sug', hidden: true });
            ui.lote = h('select', { class: 'input', id: 'etLote', 'aria-label': 'Lote' });
            ui.bLote = h('button', { class: 'btn', type: 'button', onclick: agregaLote }, icon('layers'), 'Agregar lote');
            ui.cuenta = h('p', { class: 'et-cuenta', role: 'status', 'aria-live': 'polite' });
            ui.vacio = h('p', { class: 'et-vacio' }, 'Escribe un código y pulsa Enter, busca por serie o lote, agrega un lote completo o escanea el QR de la placa. Cada QR es una tarjeta.');
            ui.grilla = h('div', { class: 'et-grilla' });
            ui.via = h('select', { class: 'input', id: 'etVia' },
                h('option', { value: 'compartida' }, 'DYMO compartida'),
                esMovil ? null : h('option', { value: 'connect' }, 'DYMO Connect (este equipo)'),
                h('option', { value: 'navegador' }, 'Navegador (diálogo del sistema)'));
            ui.copias = h('input', { class: 'input', id: 'etCop', type: 'number', min: '1', max: '5', value: '1', inputmode: 'numeric' });
            ui.estado = h('p', { class: 'et-estado', role: 'status' });
            ui.msg = h('p', { class: 'et-msg', role: 'status', 'aria-live': 'polite', hidden: true });
            ui.bImp = h('button', { class: 'btn btn-primary', type: 'button', onclick: imprime, disabled: true }, icon('printer'), 'Imprimir etiquetas');
            ui.bVaciar = h('button', { class: 'btn', type: 'button', disabled: true, onclick: () => { sel.length = 0; pintaSel(); msg('', ''); } }, 'Vaciar lista');
            $('etCuerpo').replaceChildren(h('div', { class: 'et-caja' },
                h('p', { class: 'x-intro' }, 'Etiqueta DYMO 30334 (57 x 32 mm) para el gabinete de cada tarjeta: QR con su identificador, «SKUDO ANTIJAMMER», lote y fecha de recepción.'),
                h('div', { class: 'et-elige' },
                    h('div', { class: 'field et-f-q' }, h('label', { for: 'etQ' }, 'Agregar placa'), h('div', { class: 'et-q' }, ui.q, ui.sug)),
                    h('div', { class: 'field' }, h('label', { for: 'etLote' }, 'O un lote completo'), h('div', { class: 'et-lote' }, ui.lote, ui.bLote))),
                h('div', { class: 'et-barra' }, ui.cuenta, ui.bVaciar),
                ui.vacio, ui.grilla,
                h('div', { class: 'et-imp' },
                    h('div', { class: 'field' }, h('label', { for: 'etVia' }, 'Imprimir en'), ui.via),
                    h('div', { class: 'field et-f-cop' }, h('label', { for: 'etCop' }, 'Copias'), ui.copias),
                    ui.bImp),
                ui.estado, ui.msg));
            pintaSel();
        },
        entrar() { cargaLotes(); estado(); },
        /** Lectura del celular vinculado (botón de escaneo): agrega la placa a la lista. */
        escaneo(texto) { return agregaPorCodigo(texto); },
    });
})();
