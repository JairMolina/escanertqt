/**
 * dymo.js - Etiqueta DYMO 30334 (57 × 32 mm, apaisada, 300 dpi, térmica B/N).
 * La vista previa es a escala real; la impresión NO usa el navegador: se envía el XML a DYMO Connect
 * (TQTDymo, js/dymo_connect.js) o se descarga el archivo .dymo para abrirlo con la app.
 *
 * Trama (texto exacto, 4 líneas, sin línea final; MAC en minúsculas):
 *     TQT-R1-V30-0021 / 70:4b:ca:5b:9f:6e / TQT-R2-V30-0010 / 70:4b:ca:5b:9c:a2
 * Es el texto impreso y el contenido del QR. Si falta una MAC, su línea queda vacía (nunca se inventa).
 * API: GET /api/tarjetas · GET /api/dymo/label/{id}/xml · GET /api/dymo/label/{id}/archivo
 */
document.addEventListener('DOMContentLoaded', () => {
    'use strict';
    const T = window.TQT;
    const D = window.TQTDymo;
    const { h, api, toast } = T;
    const $ = (id) => document.getElementById(id);
    T.hydrateIcons();

    const MODULE_MM = 25.4 / 300 * 6;     // 6 puntos por módulo a 300 dpi (igual que el servidor)
    const QUIET = 2;
    const NS = 'http://www.w3.org/2000/svg';
    const state = { tarjetas: [], cur: null, zoom: 3, dymo: { estado: 'buscando', printers: [], preferred: null }, busy: false };

    // ------------------------------------------------------------------ trama y modo
    const pcbDe = (t, s) => t[s] || (t[`nombre_${s}`] ? { nombre: t[`nombre_${s}`], mac: t[`mac_${s}`], estado_pcb: t[`estado_pcb_${s}`] } : null);
    function lineas(t) {
        const r1 = pcbDe(t, 'r1'), r2 = pcbDe(t, 'r2');
        const mac = (p) => (p && p.mac ? String(p.mac).toLowerCase() : '');
        return [r1 ? r1.nombre : '', mac(r1), r2 ? r2.nombre : '', mac(r2)];
    }
    const trama = (t) => lineas(t).join('\n');
    function modo(t) {
        const r1 = pcbDe(t, 'r1'), r2 = pcbDe(t, 'r2');
        if (!r1 || !r2) return { k: 'NO', faltas: ['falta asignar R1 o R2'] };
        const faltas = [];
        if (!r1.mac) faltas.push('falta la MAC de R1');
        if (!r2.mac) faltas.push('falta la MAC de R2');
        return { k: faltas.length ? 'IDENTIFICACION' : 'FINAL', faltas };
    }

    // ------------------------------------------------------------------ vista previa (QR vectorial)
    function qrSvg(text) {
        const qr = window.qrcode(0, 'M'); qr.addData(text); qr.make();
        const n = qr.getModuleCount(), total = n + 2 * QUIET;
        let d = '';
        for (let r = 0; r < n; r++) for (let c = 0; c < n; c++) if (qr.isDark(r, c)) d += `M${c + QUIET} ${r + QUIET}h1v1h-1z`;
        const svg = document.createElementNS(NS, 'svg');
        svg.setAttribute('viewBox', `0 0 ${total} ${total}`);
        svg.setAttribute('width', `${(total * MODULE_MM).toFixed(2)}mm`); svg.setAttribute('height', `${(total * MODULE_MM).toFixed(2)}mm`);
        svg.setAttribute('role', 'img'); svg.setAttribute('aria-label', 'Código QR de la etiqueta');
        const bg = document.createElementNS(NS, 'rect'); bg.setAttribute('width', total); bg.setAttribute('height', total); bg.setAttribute('fill', '#fff');
        const p = document.createElementNS(NS, 'path'); p.setAttribute('d', d); p.setAttribute('fill', '#000');
        svg.append(bg, p);
        return svg;
    }
    function buildLabel(t) {
        const [n1, m1, n2, m2] = lineas(t);
        return h('div', { class: 'dymo-label', role: 'img', 'aria-label': `Etiqueta de la tarjeta ${t.id_tarjeta_num}` },
            h('div', { class: 'dymo-qr' }, qrSvg(trama(t))),
            h('div', { class: 'dymo-trama' },
                h('div', { class: 'dymo-par' }, h('span', { class: 'dymo-l n' }, n1), h('span', { class: 'dymo-l m' }, m1)),
                h('div', { class: 'dymo-par' }, h('span', { class: 'dymo-l n' }, n2), h('span', { class: 'dymo-l m' }, m2))));
    }
    function aplicarZoom() {
        const z = state.zoom; const host = $('zoomHost');
        host.style.transform = `scale(${z})`; host.style.width = '57mm'; host.style.height = '32mm';
        const wrap = $('unico'); wrap.style.width = `calc(57mm * ${z})`; wrap.style.height = `calc(32mm * ${z})`;
    }
    function medir() {
        const el = document.querySelector('#dymoLabelContainer .dymo-label'); const out = [];
        if (!el) { $('medidas').textContent = ''; return out; }
        el.querySelectorAll('.dymo-l').forEach((l) => { const pt = parseFloat(getComputedStyle(l).fontSize) * 72 / 96; if (pt < 7) out.push(`texto de ${pt.toFixed(1)} pt (mínimo 7 pt)`); });
        const cont = el.querySelector('.dymo-trama').getBoundingClientRect();
        el.querySelectorAll('.dymo-l').forEach((l) => { if (l.scrollWidth > l.clientWidth + 1 || l.getBoundingClientRect().right > cont.right + 1) out.push(`"${l.textContent}" no cabe en la zona segura`); });
        const q = el.querySelector('.dymo-qr svg'); $('medidas').textContent = `QR ${(q ? parseFloat(q.getAttribute('width')) : 0).toFixed(1)} mm · texto 9.5 pt`;
        return out;
    }

    // ------------------------------------------------------------------ conexión con DYMO Connect
    function setPill(k, txt) { $('pill').dataset.k = k; $('pillTxt').textContent = txt; }

    function ayuda() {
        const box = $('ayuda'); box.replaceChildren();
        const e = state.dymo.estado;
        if (e === 'listo') {
            const p = impresora();
            if (p && !p.isConnected) box.append(T.banner('warn', 'alert', h('b', null, `${p.name} aparece desconectada. `), 'Enciéndela, revisa el cable USB y pulsa Actualizar. Si tienes otra LabelWriter conectada, elígela en la lista.'));
            if (!D.enLocalhost()) box.append(T.banner('warn', 'info', h('b', null, 'Consejo: '), `abre esta pantalla como https://localhost:${location.port || 8443}/dymo en la PC de la impresora. Con la dirección de red (${location.hostname}) Chrome puede pedir un permiso extra.`));
            return;
        }
        if (e === 'buscando') return;
        if (e === 'movil') {
            box.append(T.banner('warn', 'info', h('b', null, 'Desde el celular no se imprime directo. '), 'Usa "Abrir en DYMO" para bajar el archivo, o entra a esta pantalla desde la PC que tiene la DYMO conectada.'));
            return;
        }
        const titulo = { sin_framework: 'No se cargó el módulo de DYMO', no_servicio: 'No se detecta DYMO Label / DYMO Connect', sin_impresoras: 'DYMO Connect no ve la impresora' }[e] || 'Sin conexión';
        const pasos = e === 'sin_impresoras'
            ? ['Enciende la LabelWriter y revisa el cable USB.', 'En DYMO Label o DYMO Connect confirma que aparece la impresora y pulsa Actualizar aquí.']
            : e === 'sin_framework' ? ['Recarga la página con Ctrl+F5.', 'Si sigue igual, falta el archivo js/vendor/dymo.connect.framework.js del proyecto.']
                : [h('span', null, h('b', null, 'Abre DYMO Label (o DYMO Connect)'), ' en esta PC y deja la impresora conectada.'),
                    h('span', null, 'La primera vez abre ', h('a', { href: D.CHECK_URL, target: '_blank', rel: 'noopener' }, D.CHECK_URL), ' y acepta el certificado (Avanzado → Continuar). Debe verse una respuesta corta.'),
                    h('span', null, 'Vuelve a esta página y pulsa ', h('b', null, 'Actualizar'), '.'),
                    D.enLocalhost() ? null : h('span', null, `Abre esta pantalla desde https://localhost:${location.port || 8443}/dymo en vez de la dirección de red.`)];
        box.append(T.banner('bad', 'alert', h('b', null, titulo + '. '), state.dymo.detalle || ''),
            h('ol', { class: 'pasos' }, pasos.filter(Boolean).map((p) => h('li', null, p))));
    }

    async function conectar(force) {
        setPill('', 'Buscando DYMO Connect…'); state.dymo = { estado: 'buscando', printers: [], preferred: null };
        const sel = $('selPrinter'); sel.disabled = true; refrescarBotones();
        const d = await D.detect(force); state.dymo = d;
        sel.replaceChildren();
        if (d.estado === 'listo') {
            d.printers.forEach((p) => sel.append(h('option', { value: p.name, selected: p.name === d.preferred ? '' : null }, `${p.name}${p.isConnected ? '' : ' (desconectada)'}`)));
            const saved = T.store.get('tqt.dymo.impresora'); if (saved && d.printers.some((p) => p.name === saved)) sel.value = saved;
            sel.disabled = false; pillListo();
        } else {
            sel.append(h('option', null, d.estado === 'movil' ? 'No disponible en celulares' : 'Sin impresora'));
            setPill(d.estado === 'movil' ? 'warn' : 'bad', { no_servicio: 'DYMO Connect no detectado', sin_impresoras: 'Impresora no encontrada', sin_framework: 'Módulo DYMO no cargado', movil: 'Celular: solo descarga' }[d.estado] || 'Sin conexión');
        }
        ayuda(); refrescarBotones();
    }
    /** La impresora elegida en el selector (objeto del diagnóstico) o null. */
    const impresora = () => state.dymo.printers.find((p) => p.name === $('selPrinter').value) || null;
    function pillListo() {
        const p = impresora(); const n = state.dymo.printers.length;
        if (p && !p.isConnected) setPill('warn', 'DYMO Connect detectado · impresora desconectada');
        else setPill('ok', `DYMO Connect detectado · ${n} impresora${n === 1 ? '' : 's'}`);
        ayuda();
    }
    $('selPrinter').addEventListener('change', () => { T.store.set('tqt.dymo.impresora', $('selPrinter').value); pillListo(); refrescarBotones(); });
    $('btnRefresh').addEventListener('click', () => conectar(true));

    // ------------------------------------------------------------------ estado de botones y avisos
    function refrescarBotones() {
        const t = state.cur; const ok = Boolean(t) && modo(t).k !== 'NO';
        const pr = state.dymo.estado === 'listo' ? impresora() : null; const dym = Boolean(pr && pr.isConnected);
        $('btnPrint').disabled = state.busy || !ok || !dym;
        $('btnOpen').disabled = state.busy || !t;
        $('btnPrintAll').disabled = state.busy || !dym || !state.tarjetas.some((x) => modo(x).k !== 'NO');
        $('btnDownAll').disabled = state.busy || !state.tarjetas.some((x) => modo(x).k !== 'NO');
        $('btnPrint').title = dym ? '' : 'Requiere DYMO Connect y una impresora conectada en esta PC';
    }
    async function refresh() {
        const t = state.cur; const box = $('dymoLabelContainer'); box.replaceChildren();
        const aviso = $('aviso'); aviso.replaceChildren();
        refrescarBotones();
        if (!t) { box.append(T.empty('printer', 'No hay tarjetas', 'Empareja placas en Emparejar para poder etiquetarlas.')); return; }
        box.append(buildLabel(t)); aplicarZoom();
        const m = modo(t);
        if (m.k === 'NO') aviso.append(T.banner('bad', 'alert', h('b', null, 'No se puede etiquetar: '), m.faltas.join(', ')));
        else if (m.k === 'IDENTIFICACION') aviso.append(T.banner('warn', 'alert', h('b', null, 'Etiqueta de identificación. '), `Pendiente: ${m.faltas.join(', ')}. Se puede imprimir; la línea de una MAC que falte sale vacía.`));
        else aviso.append(T.banner('ok', 'check', h('b', null, 'Etiqueta final. '), 'R1 y R2 tienen MAC.'));
        const prob = medir();
        if (prob.length) aviso.append(T.banner('bad', 'alert', h('b', null, 'Revisa la etiqueta: '), prob.join('; ')));
    }

    // ------------------------------------------------------------------ servidor: XML y archivo .dymo
    async function xmlDe(t, tipo) {
        let res;
        try { res = await fetch(`/api/dymo/label/${t.id}/xml?tipo=${tipo || 'label'}`, { cache: 'no-store' }); } catch (e) { throw new Error('Sin conexión con el servidor.'); }
        if (!res.ok) throw new Error(res.status === 404 ? 'El servidor no tiene todavía el XML de la etiqueta (actualiza el servidor).' : `El servidor respondió ${res.status}.`);
        let txt = await res.text();
        if (txt.trim().startsWith('{')) { try { const j = JSON.parse(txt); txt = j.xml || j.dymo_xml || ''; } catch (e) { txt = ''; } }
        if (!D.esXmlEtiqueta(txt)) throw new Error('El servidor no devolvió un XML de etiqueta válido.');
        return txt;
    }
    /** Imprime una tarjeta. Prueba primero el XML de DYMO Label v8 (servicio DLS, el de las LabelWriter 450/4xx) y, si el
     *  servicio lo rechaza, el de DYMO Connect (.dymo). El framework solo devuelve "Error: 400", sin detalle, por eso se
     *  prueban ambos formatos en vez de adivinar cuál software tiene instalado la PC. */
    // Etiquetas ya impresas: se guardan en la base (tarjeta.etiqueta_firma). La firma incluye estado de MAC y pareja:
    // si la tarjeta cambia después de imprimir, vuelve a figurar pendiente.
    const firma = (t) => `${modo(t).k}|${t.nombre_r1 || ''}|${t.nombre_r2 || ''}`;
    const yaImpresa = (t) => !!t.etiqueta_firma && t.etiqueta_firma === firma(t);
    function marcarImpresa(t) { t.etiqueta_firma = firma(t); api('/api/dymo/impresas', { method: 'POST', body: { marcas: [{ id: t.id, firma: t.etiqueta_firma }] } }); }
    async function imprimirTarjeta(printer, t, c) {
        let primero = null;
        for (const tipo of ['label', 'dymo']) {
            try { await D.print(printer, await xmlDe(t, tipo), c); marcarImpresa(t); return; }
            catch (e) { if (/no respondi|no encuentra|Elige|cargó|Sin conexión/i.test(e.message)) throw e; if (!primero) primero = e; }
        }
        throw primero;
    }
    function bajar(url, nombre) {
        const a = h('a', { href: url, download: nombre || '', style: 'display:none' }); document.body.append(a); a.click(); setTimeout(() => a.remove(), 500);
    }
    const copias = () => Math.max(1, Math.min(99, parseInt($('inCopias').value || '1', 10) || 1));
    $('inCopias').addEventListener('input', (e) => { e.target.value = e.target.value.replace(/\D/g, ''); });

    function progreso(n, total, txt) {
        $('prog').hidden = false; $('progBar').style.width = `${total ? Math.round(n / total * 100) : 0}%`; $('progTxt').textContent = txt;
    }
    function ocultarProg(ms) { setTimeout(() => { $('prog').hidden = true; }, ms); }

    // ------------------------------------------------------------------ acciones
    $('btnPrint').addEventListener('click', async () => {
        const t = state.cur; if (!t) return;
        state.busy = true; refrescarBotones(); progreso(0, 1, 'Preparando etiqueta…');
        try {
            progreso(0.5, 1, `Enviando a ${$('selPrinter').value}…`);
            await imprimirTarjeta($('selPrinter').value, t, copias());
            progreso(1, 1, `Etiqueta de la tarjeta ${t.id_tarjeta_num} enviada a la impresora.`); toast('Enviada a la DYMO', { kind: 'ok' }); ocultarProg(2500);
        } catch (e) {
            progreso(0, 1, ''); $('prog').hidden = true;
            $('aviso').prepend(T.banner('bad', 'alert', h('b', null, 'No se pudo imprimir. '), e.message));
            if (/DYMO Connect|servicio|respond/i.test(e.message)) conectar(true);
        } finally { state.busy = false; refrescarBotones(); }
    });

    $('btnOpen').addEventListener('click', () => {
        const t = state.cur; if (!t) return;
        bajar(`/api/dymo/label/${t.id}/archivo?tipo=label`, `Etiqueta_TQT_${t.id_tarjeta_num}.label`);
        toast('Archivo .label descargado. Ábrelo con DYMO Label (o DYMO Connect).', { ms: 4000 });
    });

    function lista() {
        const solo = $('selLoteModo').value === 'final';
        return state.tarjetas.filter((t) => (solo ? modo(t).k === 'FINAL' : modo(t).k !== 'NO'));
    }

    /** Imprime las tarjetas indicadas, una por una, con barra de progreso y resumen de fallos. */
    async function imprimirSeleccion(list) {
        state.busy = true; refrescarBotones(); const printer = $('selPrinter').value; const c = copias(); let hechas = 0; const fallos = [];
        for (const t of list) {
            progreso(hechas, list.length, `Imprimiendo ${hechas + 1} de ${list.length}: tarjeta ${t.id_tarjeta_num}…`);
            try { await imprimirTarjeta(printer, t, c); hechas++; }
            catch (e) { fallos.push(`${t.id_tarjeta_num}: ${e.message}`); if (/no respondió|DYMO Connect|servicio/i.test(e.message)) break; }
        }
        progreso(hechas, list.length, `${hechas} de ${list.length} etiquetas enviadas.`);
        if (fallos.length) $('aviso').prepend(T.banner('bad', 'alert', h('b', null, `${fallos.length} sin imprimir. `), fallos.slice(0, 4).join(' · ')));
        else toast(`${hechas} etiqueta${hechas === 1 ? '' : 's'} enviada${hechas === 1 ? '' : 's'} a la DYMO`, { kind: 'ok' });
        ocultarProg(4000); state.busy = false; refrescarBotones();
    }

    /** Ventana para elegir qué tarjetas imprimir: una casilla por tarjeta (las de etiqueta final vienen marcadas). */
    $('btnPrintAll').addEventListener('click', () => {
        const todas = state.tarjetas.filter((t) => modo(t).k !== 'NO').slice().sort((a, b) => (parseInt(a.id_tarjeta_num, 10) || 0) - (parseInt(b.id_tarjeta_num, 10) || 0));
        if (!todas.length) { toast('No hay tarjetas con R1 y R2', { kind: 'bad' }); return; }
        const soloFinal = $('selLoteModo').value === 'final';
        const marcadas = new Set(todas.filter((t) => !soloFinal || modo(t).k === 'FINAL').map((t) => t.id));
        const cajas = new Map();   // id -> checkbox
        const cuenta = h('b', { 'aria-live': 'polite' });
        const filtro = h('input', { class: 'input mono', type: 'search', inputmode: 'numeric', placeholder: 'Buscar pareja (ej. 21)', 'aria-label': 'Buscar pareja', autocomplete: 'off', maxlength: '4' });
        const lista = h('div', { role: 'group', 'aria-label': 'Tarjetas a imprimir', style: 'display:flex;flex-direction:column;gap:6px;max-height:min(52vh,420px);overflow:auto;padding:2px' });

        const visibles = () => { const f = filtro.value.replace(/\D/g, '').replace(/^0+/, ''); return todas.filter((t) => !f || String(t.id_tarjeta_num).replace(/^0+/, '').includes(f)); };
        const actualizarCuenta = () => {
            const n = [...marcadas].length, ya = todas.filter(yaImpresa).length;
            cuenta.textContent = `${n} de ${todas.length} seleccionada${n === 1 ? '' : 's'}` + (ya ? ` · ${ya} ya impresa${ya === 1 ? '' : 's'}` : '');
            if (btnImp) btnImp.disabled = !n;
        };
        let btnImp = null;
        function pintarLista() {
            lista.replaceChildren(); cajas.clear();
            const v = visibles();
            if (!v.length) { lista.append(h('p', { class: 'muted' }, 'Ninguna tarjeta coincide.')); return; }
            v.forEach((t) => {
                const m = modo(t);
                const cb = h('input', { type: 'checkbox', checked: marcadas.has(t.id) ? '' : null, style: 'width:22px;height:22px;flex:none;accent-color:var(--accent,#D9A441)',
                    onchange: (e) => { if (e.target.checked) marcadas.add(t.id); else marcadas.delete(t.id); actualizarCuenta(); } });
                cajas.set(t.id, cb);
                const ya = yaImpresa(t);
                const estilo = ya ? 'border:1px solid var(--info,#4C8DFF);background:color-mix(in srgb, var(--info,#4C8DFF) 16%, transparent)' : 'border:1px solid var(--line);background:var(--surface-2,transparent)';
                lista.append(h('label', { title: ya ? 'Ya impresa' : '', style: `display:flex;align-items:center;gap:12px;padding:10px 12px;border-radius:8px;cursor:pointer;${estilo}` },
                    cb, h('b', { class: 'mono', style: 'min-width:54px' }, `#${t.id_tarjeta_num}`),
                    h('span', { class: 'mono muted grow', style: 'font-size:12px' }, `${t.nombre_r1 || ''} · ${t.nombre_r2 || ''}`),
                    ya ? T.badge('Impresa', 'info') : null,
                    T.badge(m.k === 'FINAL' ? 'Con MAC' : 'Sin MAC', m.k === 'FINAL' ? 'ok' : 'warn')));
            });
        }
        const marcarVisibles = (on) => { visibles().forEach((t) => { if (on) marcadas.add(t.id); else marcadas.delete(t.id); const cb = cajas.get(t.id); if (cb) cb.checked = on; }); actualizarCuenta(); };
        filtro.addEventListener('input', pintarLista);

        const cuerpo = h('div', { class: 'stack', style: 'display:flex;flex-direction:column;gap:12px' },
            h('p', { class: 'muted' }, `Marca las tarjetas que quieres imprimir (${copias()} copia${copias() === 1 ? '' : 's'} de cada una).`),
            h('div', { class: 'row wrap', style: 'display:flex;gap:8px;align-items:center;flex-wrap:wrap' }, filtro,
                h('button', { class: 'btn btn-sm', type: 'button', onclick: () => marcarVisibles(true) }, 'Marcar todas'),
                h('button', { class: 'btn btn-sm', type: 'button', onclick: () => marcarVisibles(false) }, 'Quitar todas'),
                h('button', { class: 'btn btn-sm', type: 'button', onclick: () => { todas.forEach((t) => { if (modo(t).k === 'FINAL') marcadas.add(t.id); else marcadas.delete(t.id); }); pintarLista(); actualizarCuenta(); } }, 'Solo con MAC')),
            cuenta, lista);
        pintarLista();
        const hoja = T.sheet({
            title: 'Imprimir lote en DYMO', body: cuerpo,
            actions: [
                { label: 'Cancelar', onClick: () => true },
                { label: 'Imprimir seleccionadas', kind: 'primary', icon: 'layers', onClick: () => {
                    const elegidas = todas.filter((t) => marcadas.has(t.id));
                    if (!elegidas.length) return false;
                    imprimirSeleccion(elegidas);   // sigue con la barra de progreso de la página
                    return true;
                } },
            ],
        });
        btnImp = hoja.el.querySelector('.actions .btn-primary');
        actualizarCuenta();
    });

    $('btnDownAll').addEventListener('click', async () => {
        const list = lista(); if (!list.length) { toast('No hay etiquetas para descargar', { kind: 'bad' }); return; }
        const ids = list.map((t) => t.id).join(',');
        // Un solo ZIP con un .dymo por tarjeta (el navegador no pide permiso para "varias descargas").
        if (list.length > 1) { bajar(`/api/dymo/lote/archivo?tipo=label&ids=${ids}`, 'Etiquetas_TQT_lote.zip'); toast(`ZIP con ${list.length} etiquetas descargado. Ábrelas con DYMO Label o DYMO Connect.`, { ms: 4000 }); return; }
        state.busy = true; refrescarBotones();
        for (let i = 0; i < list.length; i++) { progreso(i, list.length, `Descargando ${i + 1} de ${list.length}…`); bajar(`/api/dymo/label/${list[i].id}/archivo?tipo=label`, `Etiqueta_TQT_${list[i].id_tarjeta_num}.label`); await new Promise((r) => setTimeout(r, 450)); }
        progreso(list.length, list.length, `${list.length} archivos descargados. Si el navegador pidió permiso para varias descargas, acéptalo.`); ocultarProg(5000);
        state.busy = false; refrescarBotones();
    });

    // ------------------------------------------------------------------ carga
    async function load() {
        const p = new URLSearchParams(location.search);
        const st = await api('/api/status'); const lote = p.get('lote_id') || (st.ok && st.data && st.data.active_lote ? st.data.active_lote.id : '');
        const r = await api(`/api/tarjetas?limit=500${lote ? `&lote_id=${encodeURIComponent(lote)}` : ''}`);
        if (!r.ok) { $('aviso').append(T.banner('bad', 'alert', 'No se pudieron cargar las tarjetas: ', r.error)); return; }
        state.tarjetas = (r.data && r.data.items) || [];
        state.tarjetas.sort((a, b) => (parseInt(a.id_tarjeta_num, 10) || 0) - (parseInt(b.id_tarjeta_num, 10) || 0));
        state.cur = state.tarjetas.find((t) => String(t.id) === p.get('tarjeta_id')) || state.tarjetas.find((t) => modo(t).k !== 'NO') || state.tarjetas[0] || null;
        llenarTarjetas();
        refresh();
    }
    /** Rellena el menú de tarjetas (de menor a mayor) con las que coinciden con el filtro tecleado. */
    function llenarTarjetas() {
        const sel = $('selTarjeta'); const f = ($('inFiltro').value || '').replace(/\D/g, '');
        const lista = state.tarjetas.filter((t) => !f || String(t.id_tarjeta_num).replace(/^0+/, '').includes(f.replace(/^0+/, '') || '0'));
        sel.replaceChildren();
        lista.forEach((t) => { const k = modo(t).k; sel.append(h('option', { value: String(t.id) }, `#${t.id_tarjeta_num} · ${k === 'FINAL' ? 'final' : k === 'NO' ? 'incompleta' : 'identificación'}`)); });
        $('filtroInfo').textContent = f ? `${lista.length} de ${state.tarjetas.length}` : '';
        if (!lista.length) { sel.append(h('option', { value: '' }, 'Sin coincidencias')); return; }
        const actual = lista.find((t) => state.cur && t.id === state.cur.id) || lista[0];
        sel.value = String(actual.id);
        if (!state.cur || state.cur.id !== actual.id) { state.cur = actual; if (state.listo) refresh(); }
    }
    $('inFiltro').addEventListener('input', llenarTarjetas);
    $('inFiltro').addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); $('selTarjeta').focus(); } });
    $('selTarjeta').addEventListener('change', () => { state.cur = state.tarjetas.find((t) => String(t.id) === $('selTarjeta').value) || null; refresh(); });
    $('selZoom').addEventListener('change', () => { state.zoom = +$('selZoom').value; aplicarZoom(); });

    // En pantallas estrechas 3x (171 mm) no cabe: se empieza a 2x/1x según el ancho útil para ver la etiqueta entera.
    const ancho = Math.min(window.innerWidth, 1100) - 72;
    const zFit = Math.max(1, Math.min(3, Math.floor(ancho / (57 * 96 / 25.4))));
    state.zoom = zFit; $('selZoom').value = String(zFit);
    load().then(() => { state.listo = true; }); conectar(false);
});
