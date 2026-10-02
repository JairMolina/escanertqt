/**
 * consultar.js - Ficha completa de una tarjeta al escanear su etiqueta DYMO (4 líneas), el QR de una PCB o una MAC.
 * Muestra la pareja (R1, R2, R3): hardware (V30), serie, MAC y firmware (R1/R2; la R3 no lleva ni MAC ni firmware).
 * Acepta: etiqueta DYMO, QR de una PCB, MAC o el NÚMERO de tarjeta (0011). Sin tarjeta con ese número, muestra sus placas sueltas.
 * API: GET /api/consulta?codigo=...   (también acepta ?codigo= en la URL, p. ej. desde el monitor)
 */
document.addEventListener('DOMContentLoaded', () => {
    'use strict';
    const T = window.TQT;
    const { h, api, icon, toast } = T;
    const $ = (id) => document.getElementById(id);

    T.mountShell({ active: 'consultar', sub: 'Consulta' });

    const SLOTS = ['r1', 'r2', 'r3'];
    const state = { last: '', at: 0, busy: false, data: null };
    const CLAVE = 'tqt.consultas.movil';
    const recientes = () => { try { const j = JSON.parse(localStorage.getItem(CLAVE) || '[]'); return Array.isArray(j) ? j.filter((x) => typeof x === 'string').slice(0, 6) : []; } catch (e) { return []; } };
    const recordar = (q) => { const t = String(q).split(/\r?\n/).filter(Boolean)[0]; if (!t || t.length > 40) return; try { localStorage.setItem(CLAVE, JSON.stringify([t, ...recientes().filter((x) => x !== t)].slice(0, 6))); } catch (e) { /* sin almacenamiento */ } };

    function copiar(texto, ok) {
        const fallback = () => toast('No se pudo copiar: selecciona el texto y cópialo', { kind: 'bad' });
        if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(texto).then(() => toast(ok || 'Copiado', { kind: 'ok', ms: 1400 }), fallback);
        else fallback();
    }

    const page = $('consulta');
    const box = $('ficha');
    // Con resultado en pantalla el visor se reduce a una franja y la ficha sube (data-has="1"); "Nueva consulta" lo devuelve.
    function setHas(v) { page.dataset.has = v ? '1' : '0'; }
    function setBusy(v) { box.setAttribute('aria-busy', String(v)); }

    function vacio() {
        setHas(false); setBusy(false); box.replaceChildren();
        box.append(T.empty('consultar', 'Escanea una etiqueta', 'Apunta la cámara al QR de la etiqueta o de cualquier PCB. También puedes escribir el número de tarjeta (0011), el nombre de la PCB o la MAC.'));
        const rec = recientes();
        if (rec.length) box.append(h('div', { class: 'stack' }, h('div', { class: 'silk' }, 'Consultas recientes'),
            h('div', { class: 'row wrap', style: 'gap:8px' }, rec.map((t) => h('button', { class: 'btn btn-sm', type: 'button', onclick: () => { $('q').value = t; state.last = ''; buscar(t, false); } }, t)))));
    }

    function nueva() {
        state.data = null; state.last = ''; $('q').value = ''; vacio();
        window.scrollTo({ top: 0 });
        $('q').focus({ preventScroll: true });
    }

    function cargando(q) {
        setHas(true); setBusy(true); box.replaceChildren();
        box.append(h('div', { class: 'skel-ficha', role: 'status' }, h('span', { class: 'sr-only' }, 'Buscando ' + q + '…'),
            h('div', { class: 'sk sk-num' }), h('div', { class: 'sk sk-card' }), h('div', { class: 'sk sk-card' })));
    }

    function campo(label, valor, extra) {
        return h('div', { class: 'dato' + (extra && extra.wide ? ' wide' : '') },
            h('dt', null, label), h('dd', null, valor === null || valor === undefined || valor === '' ? h('span', { class: 'muted' }, '—') : valor));
    }

    function tarjetaPcb(slot, p, hit) {
        const S = slot.toUpperCase();
        if (!p) {
            return h('article', { class: 'pcbf', dataset: { t: S, empty: '1' }, 'aria-label': `${S} sin asignar` },
                h('header', null, T.tipoChip(S, { lg: true, empty: true }), h('span', { class: 'nm muted' }, 'Sin placa asignada')));
        }
        const head = h('header', null, T.tipoChip(S, { lg: true }), h('span', { class: 'nm' }, p.nombre), T.cicloBadge(p.estado_ciclo));
        if (S === 'R3') {   // la R3 no lleva MAC ni firmware
            return h('article', { class: 'pcbf', dataset: { t: S, hit: hit ? '1' : '' }, 'aria-label': `${S} ${p.nombre}` }, head,
                h('dl', null, campo('Hardware', 'V' + p.version), campo('Serie', p.serie)),
                h('p', { class: 'pcbf-nota' }, icon('info'), 'La R3 no lleva MAC ni firmware'));
        }
        const mac = p.mac ? String(p.mac).toLowerCase() : '';
        const macBox = mac
            ? h('div', { class: 'macline' }, h('span', { class: 'macval mono', 'aria-label': 'MAC ' + mac.split(':').join(' ') }, mac),
                h('button', { class: 'btn btn-sm', type: 'button', 'aria-label': `Copiar MAC de ${p.nombre}`, title: 'Copiar MAC', onclick: () => copiar(mac, 'MAC copiada') }, icon('paste')))
            : h('span', { class: 'soft' }, icon('clock'), 'Sin MAC todavía');
        const fwBox = p.firmware ? h('span', { class: 'mono' }, p.firmware) : h('span', { class: 'soft' }, icon('clock'), 'Sin firmware');
        return h('article', { class: 'pcbf', dataset: { t: S, hit: hit ? '1' : '' }, 'aria-label': `${S} ${p.nombre}` }, head,
            h('div', { class: 'macwrap' }, h('div', { class: 'dt-l' }, 'MAC'), macBox),
            h('dl', null, campo('Hardware', 'V' + p.version), campo('Firmware', fwBox), campo('Serie', p.serie)));
    }

    function resumenTexto(t) {
        const l = [`Tarjeta ${t.id_tarjeta_num}`];
        SLOTS.forEach((s) => {
            const p = t[s]; if (!p) return;
            if (s === 'r3') { l.push(`R3 ${p.nombre} (Hardware V${p.version}; sin MAC ni firmware)`); return; }
            l.push(`${s.toUpperCase()} ${p.nombre} · Hardware V${p.version}${p.mac ? ' · MAC ' + String(p.mac).toLowerCase() : ''}${p.firmware ? ' · Firmware ' + p.firmware : ''}`);
        });
        return l.join('\n');
    }

    const ORIGEN = { etiqueta: 'Leída de la etiqueta', pcb: 'Leída del QR de una PCB', mac: 'Encontrada por MAC', tarjeta: 'Encontrada por número', serie: 'Placas con ese número' };

    function render(d) {
        state.data = d;
        setHas(true); setBusy(false); box.replaceChildren();
        const t = d.tarjeta;
        const leidos = new Set((d.leidas || []).map((x) => x.nombre).filter(Boolean));
        const cuerpo = h('div', { class: 'ficha-in stack' });
        (d.avisos || []).forEach((a) => cuerpo.append(T.banner('warn', 'alert', a)));
        if (t) {
            cuerpo.append(h('div', { class: 'fichahead' },
                h('div', { class: 'fh-num' }, h('div', { class: 'silk' }, 'Tarjeta'), h('div', { class: 'num', 'aria-label': 'Tarjeta ' + t.id_tarjeta_num }, t.id_tarjeta_num)),
                h('div', { class: 'fh-meta' }, T.tarjetaBadge(t), h('div', { class: 'hint' }, ORIGEN[d.origen] || ''),
                    h('button', { class: 'btn btn-sm btn-ghost', type: 'button', onclick: nueva }, icon('refresh'), 'Nueva consulta'))));
            cuerpo.append(h('div', { class: 'fichagrid' }, SLOTS.map((s) => tarjetaPcb(s, t[s], t[s] && leidos.has(t[s].nombre)))));
            cuerpo.append(h('div', { class: 'fichaacts' },
                h('a', { class: 'btn btn-primary act-main', href: `/dymo?tarjeta_id=${t.id}` }, icon('printer'), 'Etiqueta DYMO'),
                h('button', { class: 'btn', type: 'button', onclick: () => copiar(resumenTexto(t), 'Datos copiados') }, icon('paste'), 'Copiar datos'),
                ));
        } else if (d.serie) {   // número sin tarjeta: las placas que tienen ese número
            cuerpo.append(h('div', { class: 'fichahead' },
                h('div', { class: 'fh-num' }, h('div', { class: 'silk' }, 'Número'), h('div', { class: 'num', 'aria-label': 'Número ' + d.serie.numero }, d.serie.numero)),
                h('div', { class: 'fh-meta' }, T.badge('Sin tarjeta', 'warn', 'alert'), h('div', { class: 'hint' }, ORIGEN.serie),
                    h('button', { class: 'btn btn-sm btn-ghost', type: 'button', onclick: nueva }, icon('refresh'), 'Nueva consulta'))));
            cuerpo.append(h('div', { class: 'fichagrid' }, SLOTS.map((s) => tarjetaPcb(s, d.serie[s], false))));
            cuerpo.append(h('div', { class: 'fichaacts' }, h('a', { class: 'btn btn-primary act-main', href: '/emparejar' }, icon('link'), 'Ir a emparejar')));
        } else if (d.pcb) {
            cuerpo.append(h('div', { class: 'fichagrid solo' }, tarjetaPcb(d.pcb.tipo.toLowerCase(), d.pcb, true)));
            cuerpo.append(h('div', { class: 'fichaacts' }, h('button', { class: 'btn btn-primary act-main', type: 'button', onclick: nueva }, icon('refresh'), 'Nueva consulta')));
        }
        box.append(cuerpo);
        window.scrollTo({ top: 0, behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
    }

    function tipoDe(d) { const p = d && (d.pcb || (d.tarjeta && (d.tarjeta.r1 || d.tarjeta.r2)) || (d.serie && (d.serie.r1 || d.serie.r2 || d.serie.r3))); return p && p.tipo ? p.tipo : 'R1'; }

    async function buscar(texto, desdeCamara, silencioso) {
        const q = String(texto || '').trim();
        if (!q || state.busy) return;
        state.busy = true; if (!silencioso) cargando(q);
        const r = await api(`/api/consulta?codigo=${encodeURIComponent(q)}`);
        state.busy = false;
        if (!r.ok) {
            if (window.SoundFX) window.SoundFX.playError();
            if (window.Haptics) window.Haptics.error();
            setBusy(false); box.replaceChildren();
            const causa = r.network ? 'No hay conexión con el servidor. Revisa la red y vuelve a intentar.' : (r.error || 'Intenta de nuevo.');
            box.append(h('div', { class: 'ficha-in stack' },
                T.banner('bad', 'alert', h('b', null, r.status === 404 ? 'No encontramos ese código. ' : r.status === 400 ? 'No se reconoce ese código. ' : r.network ? 'Sin conexión. ' : 'No se pudo consultar. '), causa),
                T.empty('consultar', 'Revisa el código', 'Escribe el número de tarjeta (0011), el nombre completo de la PCB (TQT-R1-V30-0021) o la MAC, o escanea la etiqueta.'),
                h('div', { class: 'fichaacts' }, h('button', { class: 'btn btn-primary act-main', type: 'button', onclick: nueva }, icon('refresh'), 'Nueva consulta'))));
            return;
        }
        if (window.SoundFX) window.SoundFX.playScan(tipoDe(r.data));
        if (window.Haptics) window.Haptics.scan();
        recordar(q); render(r.data);
    }

    function onCode(text) {
        const ahora = Date.now();
        if (text === state.last && ahora - state.at < 3000) return;   // la misma etiqueta sigue frente a la cámara
        state.last = text; state.at = ahora;
        buscar(text, true);
    }

    $('formBuscar').addEventListener('submit', (e) => { e.preventDefault(); state.last = ''; buscar($('q').value, false); });

    const ws = T.ws();
    if (ws) ['PCB_ACTUALIZADA', 'TARJETA_ACTUALIZADA', 'PCB_ELIMINADA', 'EXCEL_IMPORTADO'].forEach((ev) => ws.on(ev, () => { if (state.last) buscar(state.last, true, true); }));
    T.resync(() => { if (state.last) buscar(state.last, true, true); });

    document.addEventListener('tqt:lote-cambiado', (e) => e.preventDefault());   // las placas son globales: no hace falta recargar
    T.mountVisor($('visorHost'), { compact: true, onCode });
    vacio();
    const inicial = new URLSearchParams(location.search).get('codigo');
    if (inicial) { $('q').value = inicial; state.last = inicial; state.at = Date.now(); buscar(inicial, false); }
});
