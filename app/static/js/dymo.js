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
    const ESC = { tarjetas: new Map(), r3: [], token: null, id: null, moviles: 0, est: null };   // v1.3.45: lote escaneado

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
        $('btnEscPrint').disabled = state.busy || !dym || !(ESC.tarjetas.size + ESC.r3.length);
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
    // ------------------------------------------------------------------ etiquetas R3 (v1.3.44): DOS R3 por etiqueta, una por mitad
    // La R3 es muy pequeña: la etiqueta se corta por la mitad y cada mitad lleva el QR y el nombre de una R3.
    // Origen: las R3 de las tarjetas de un lote (como el lote de R1/R2) o un rango de series.
    const soloDig = (e) => { e.target.value = e.target.value.replace(/\D/g, ''); };
    const r3Serie = (v) => { const n = parseInt(v, 10); return Number.isFinite(n) && n >= 0 && n <= 9999 ? n : null; };
    const r3st = { lote: [], cargando: false, error: '' };
    const esLote = () => $('r3Origen').value === 'lote';
    function r3Nombres() {
        const ver = ($('r3Ver').value || '').replace(/\D/g, '') || '30';
        if (esLote()) return { ver, lista: r3st.lote.map((x) => x.nombre), error: r3st.error || (r3st.cargando ? 'Cargando las R3 del lote…' : (!r3st.lote.length && $('r3Lote').value ? 'No hay R3 en las tarjetas del lote ni R3 sueltas.' : '')) };
        const d = r3Serie($('r3Desde').value); if (d === null) return { ver, lista: [] };
        const hRaw = $('r3Hasta').value.trim(); const hh = hRaw ? r3Serie(hRaw) : d;
        if (hh === null || hh < d) return { ver, lista: [], error: '"Serie hasta" debe ser mayor o igual que "desde".' };
        if (hh - d >= 1000) return { ver, lista: [], error: 'Máximo 1000 R3 (500 etiquetas) por tanda.' };
        const lista = []; for (let n = d; n <= hh; n++) lista.push(`TQT-R3-V${ver}-${String(n).padStart(4, '0')}`);
        return { ver, lista };
    }
    const pares = (lista) => { const out = []; for (let i = 0; i < lista.length; i += 2) out.push(lista.slice(i, i + 2)); return out; };
    function mitad(nombre) {
        if (!nombre) return h('div', { class: 'r3m' }, h('span', { class: 'r3m-vacia' }, 'Mitad libre'));
        const svg = qrSvg(nombre);
        const total = +svg.getAttribute('viewBox').split(' ')[2];
        let ppm = 6; while (ppm > 3 && total * ppm / 11.811 > 13) ppm--;   // igual que calcular_diseno_r3 del servidor (tira de 16 mm)
        const mm = (total * ppm / 11.811).toFixed(2) + 'mm'; svg.setAttribute('width', mm); svg.setAttribute('height', mm);
        return h('div', { class: 'r3m' }, h('div', { class: 'dymo-qr' }, svg), h('span', { class: 'dymo-l n' }, nombre));
    }
    function r3Vista() {
        document.querySelectorAll('.r3-serie').forEach((e) => { e.hidden = esLote(); });
        document.querySelectorAll('.r3-lote').forEach((e) => { e.hidden = !esLote(); });
        const { ver, lista, error } = r3Nombres();
        const par = lista.length ? lista.slice(0, 2) : [`TQT-R3-V${ver}-0000`];
        $('r3Ejemplo').textContent = par.join(' + ');
        $('r3Label').replaceChildren(h('div', { class: 'dymo-label r3doble', role: 'img', 'aria-label': `Etiqueta R3: ${par.join(' y ')}` }, mitad(par[0]), mitad(par[1])));
        $('r3ZoomHost').style.transform = `scale(${state.zoom})`;
        const lbl = $('r3Label').firstChild; $('r3ZoomHost').style.width = `${lbl.offsetWidth * state.zoom}px`; $('r3ZoomHost').style.height = `${lbl.offsetHeight * state.zoom}px`;
        const n = pares(lista).length;
        $('r3Info').textContent = error || (lista.length ? `${lista.length} R3 → ${n} etiqueta${n === 1 ? '' : 's'} (${lista[0]} … ${lista[lista.length - 1]})${lista.length % 2 ? ' · la última lleva una sola R3' : ''}` : 'Vista previa · 57 × 32 mm, dos mitades');
        $('btnR3Print').disabled = $('btnR3Open').disabled = !lista.length || state.busy;
        $('btnR3Print').lastChild.textContent = esLote() ? ' Imprimir lote R3 en DYMO…' : ' Imprimir R3 en DYMO';
    }
    async function cargarLotesR3() {
        const [rl, st] = await Promise.all([api('/api/lotes'), api('/api/status')]);
        const sel = $('r3Lote');
        if (!rl.ok) { sel.replaceChildren(h('option', { value: '' }, 'No se pudieron cargar los lotes')); return; }
        const activo = st.ok && st.data && st.data.active_lote ? st.data.active_lote.id : null;
        const lotes = T.ordenarLotes ? T.ordenarLotes(rl.data || []) : (rl.data || []);
        sel.replaceChildren(...lotes.map((l) => h('option', { value: String(l.id), selected: l.id === activo ? '' : null }, T.loteNombre(l) + (l.activo ? ' (activo)' : ''))));
        if (!lotes.length) sel.replaceChildren(h('option', { value: '' }, 'Todavía no hay lotes'));
        await cargarR3Lote();
    }
    async function cargarR3Lote() {
        const id = $('r3Lote').value; r3st.lote = []; r3st.error = '';
        if (!id) { r3Vista(); return; }
        r3st.cargando = true; r3Vista();
        // v1.3.44: las R3 de las tarjetas del lote y TODAS las R3 sueltas (registradas pero sin emparejar)
        const [r, rp] = await Promise.all([api(`/api/tarjetas?lote_id=${encodeURIComponent(id)}&limit=500`), api('/api/pcb?tipo=R3&limit=5000', { timeout: 20000 })]);
        r3st.cargando = false;
        if (!r.ok) r3st.error = r.error || 'No se pudieron cargar las tarjetas del lote.';
        else {
            const vistos = new Set();
            r3st.lote = (r.data.items || []).map((t) => ({ nombre: (t.r3 && t.r3.nombre) || t.nombre_r3, num: t.id_tarjeta_num, prog: !!(t.r3 && t.r3.firmware) }))
                .filter((x) => /^TQT-R3-V\d{1,3}-\d{4}$/.test(x.nombre || '') && !vistos.has(x.nombre) && vistos.add(x.nombre))
                .sort((a, b) => a.nombre.localeCompare(b.nombre, 'es', { numeric: true }));
            const sueltas = (rp.ok && rp.data && rp.data.items ? rp.data.items : [])
                .filter((p) => p.tipo === 'R3' && !p.tarjeta_id && !['BAJA', 'FALLA'].includes(p.estado_ciclo) && !vistos.has(p.nombre) && vistos.add(p.nombre))
                .map((p) => ({ nombre: p.nombre, num: null, suelta: true, prog: !!p.firmware }))
                .sort((a, b) => a.nombre.localeCompare(b.nombre, 'es', { numeric: true }));
            r3st.lote = r3st.lote.concat(sueltas);
        }
        r3Vista();
    }
    $('r3Origen').addEventListener('change', r3Vista);
    $('r3Lote').addEventListener('change', cargarR3Lote);
    ['r3Ver', 'r3Desde', 'r3Hasta', 'r3Copias'].forEach((id) => $(id).addEventListener('input', (e) => { soloDig(e); r3Vista(); }));
    $('selZoom').addEventListener('change', r3Vista);
    const qsR3 = (par) => par.map((n) => `nombre=${encodeURIComponent(n)}`).join('&');
    async function xmlR3(par, tipo) {
        let res;
        try { res = await fetch(`/api/dymo/r3/xml?${qsR3(par)}&tipo=${tipo}`, { cache: 'no-store' }); } catch (e) { throw new Error('Sin conexión con el servidor.'); }
        if (!res.ok) throw new Error(`El servidor respondió ${res.status}.`);
        const txt = await res.text();
        if (!D.esXmlEtiqueta(txt)) throw new Error('El servidor no devolvió un XML de etiqueta válido.');
        return txt;
    }
    async function imprimirR3(printer, par, c) {
        let primero = null;
        for (const tipo of ['label', 'dymo']) {
            try { await D.print(printer, await xmlR3(par, tipo), c); return; }
            catch (e) { if (/no respondi|no encuentra|Elige|cargó|Sin conexión/i.test(e.message)) throw e; if (!primero) primero = e; }
        }
        throw primero;
    }
    async function imprimirParesR3(lista) {
        const etiquetas = pares(lista);
        const printer = $('selPrinter').value; const c = Math.max(1, Math.min(99, parseInt($('r3Copias').value || '1', 10) || 1));
        state.busy = true; refrescarBotones(); r3Vista(); let hechas = 0; const fallos = [];
        for (const par of etiquetas) {
            progreso(hechas, etiquetas.length, `Imprimiendo ${hechas + 1} de ${etiquetas.length}: ${par.join(' + ')}…`);
            try { await imprimirR3(printer, par, c); hechas++; }
            catch (e) { fallos.push(`${par.join(' + ')}: ${e.message}`); if (/no respondió|DYMO Connect|servicio/i.test(e.message)) break; }
        }
        progreso(hechas, etiquetas.length, `${hechas} de ${etiquetas.length} etiquetas R3 enviadas.`);
        if (fallos.length) $('aviso').prepend(T.banner('bad', 'alert', h('b', null, `${fallos.length} etiqueta${fallos.length === 1 ? '' : 's'} R3 sin imprimir. `), fallos.slice(0, 4).join(' · ')));
        else toast(`${hechas} etiqueta${hechas === 1 ? '' : 's'} R3 (${lista.length} placas) enviada${hechas === 1 ? '' : 's'} a la DYMO`, { kind: 'ok' });
        ocultarProg(4000); state.busy = false; refrescarBotones(); r3Vista();
    }
    // Lote: hoja con TODAS las R3 del lote para marcar cuáles imprimir (igual que "Imprimir lote en DYMO…" de R1/R2)
    function hojaLoteR3() {
        const todas = r3st.lote.slice();
        if (!todas.length) { toast('No hay R3 en el lote ni sueltas', { kind: 'bad' }); return; }
        const marcadas = new Set(todas.map((x) => x.nombre));
        const cajas = new Map();
        const cuenta = h('b', { 'aria-live': 'polite' });
        const filtro = h('input', { class: 'input mono', type: 'search', inputmode: 'numeric', placeholder: 'Buscar (ej. 21)', 'aria-label': 'Buscar R3 o tarjeta', autocomplete: 'off', maxlength: '4' });
        const lista = h('div', { role: 'group', 'aria-label': 'R3 a imprimir', style: 'display:flex;flex-direction:column;gap:6px;max-height:min(52vh,420px);overflow:auto;padding:2px' });
        const sinCeros = (v) => String(v || '').replace(/^0+/, '');
        const visibles = () => { const f = sinCeros(filtro.value.replace(/\D/g, '')); return todas.filter((x) => !f || sinCeros(x.nombre.slice(-4)).includes(f) || sinCeros(x.num).includes(f)); };
        let btnImp = null;
        const actualizarCuenta = () => {
            const n = marcadas.size, et = Math.ceil(n / 2);
            cuenta.textContent = `${n} de ${todas.length} R3 seleccionada${n === 1 ? '' : 's'} → ${et} etiqueta${et === 1 ? '' : 's'}${n % 2 ? ' (la última con una sola R3)' : ''}`;
            if (btnImp) btnImp.disabled = !n;
        };
        function pintarLista() {
            lista.replaceChildren(); cajas.clear();
            const v = visibles();
            if (!v.length) { lista.append(h('p', { class: 'muted' }, 'Ninguna R3 coincide.')); return; }
            v.forEach((x) => {
                const cb = h('input', { type: 'checkbox', checked: marcadas.has(x.nombre) ? '' : null, style: 'width:22px;height:22px;flex:none;accent-color:var(--accent,#D9A441)',
                    onchange: (e) => { if (e.target.checked) marcadas.add(x.nombre); else marcadas.delete(x.nombre); actualizarCuenta(); } });
                cajas.set(x.nombre, cb);
                lista.append(h('label', { style: 'display:flex;align-items:center;gap:12px;padding:10px 12px;border-radius:8px;cursor:pointer;border:1px solid var(--line);background:var(--surface-2,transparent)' },
                    cb, h('b', { class: 'mono', style: 'min-width:54px' }, x.num ? `#${x.num}` : '—'), h('span', { class: 'mono grow' }, x.nombre),
                    x.suelta ? T.badge('Suelta', 'info') : null,
                    T.badge(x.prog ? 'Programada' : 'Sin firmware', x.prog ? 'ok' : 'warn')));
            });
        }
        const marcarVisibles = (on) => { visibles().forEach((x) => { if (on) marcadas.add(x.nombre); else marcadas.delete(x.nombre); const cb = cajas.get(x.nombre); if (cb) cb.checked = on; }); actualizarCuenta(); };
        filtro.addEventListener('input', pintarLista);
        const c = Math.max(1, Math.min(99, parseInt($('r3Copias').value || '1', 10) || 1));
        const nomLote = $('r3Lote').selectedOptions[0] ? $('r3Lote').selectedOptions[0].textContent : '';
        const cuerpo = h('div', { class: 'stack', style: 'display:flex;flex-direction:column;gap:12px' },
            h('p', { class: 'muted' }, `Lote ${nomLote}. Aparecen las R3 de sus tarjetas y las R3 sueltas (sin emparejar). Marca las que quieres imprimir: van dos por etiqueta, en orden (${c} copia${c === 1 ? '' : 's'} de cada etiqueta).`),
            h('div', { class: 'row wrap', style: 'display:flex;gap:8px;align-items:center;flex-wrap:wrap' }, filtro,
                h('button', { class: 'btn btn-sm', type: 'button', onclick: () => marcarVisibles(true) }, 'Marcar todas'),
                h('button', { class: 'btn btn-sm', type: 'button', onclick: () => marcarVisibles(false) }, 'Quitar todas'),
                h('button', { class: 'btn btn-sm', type: 'button', onclick: () => { todas.forEach((x) => { if (x.prog) marcadas.add(x.nombre); else marcadas.delete(x.nombre); }); pintarLista(); actualizarCuenta(); } }, 'Solo programadas'),
                h('button', { class: 'btn btn-sm', type: 'button', onclick: () => { todas.forEach((x) => { if (!x.suelta) marcadas.add(x.nombre); else marcadas.delete(x.nombre); }); pintarLista(); actualizarCuenta(); } }, 'Solo de tarjetas'),
                h('button', { class: 'btn btn-sm', type: 'button', onclick: () => { todas.forEach((x) => { if (x.suelta) marcadas.add(x.nombre); else marcadas.delete(x.nombre); }); pintarLista(); actualizarCuenta(); } }, 'Solo sueltas')),
            cuenta, lista);
        pintarLista();
        const hoja = T.sheet({
            title: 'Imprimir lote de R3 en DYMO', body: cuerpo,
            actions: [
                { label: 'Cancelar', onClick: () => true },
                { label: 'Imprimir seleccionadas', kind: 'primary', icon: 'layers', onClick: () => {
                    const elegidas = todas.filter((x) => marcadas.has(x.nombre)).map((x) => x.nombre);
                    if (!elegidas.length) return false;
                    imprimirParesR3(elegidas);
                    return true;
                } },
            ],
        });
        btnImp = hoja.el.querySelector('.actions .btn-primary');
        actualizarCuenta();
    }
    $('btnR3Print').addEventListener('click', () => {
        if (esLote()) { hojaLoteR3(); return; }
        const { lista } = r3Nombres(); if (lista.length) imprimirParesR3(lista);
    });
    $('btnR3Open').addEventListener('click', () => {
        const { lista } = r3Nombres(); if (!lista.length) return;
        const etiquetas = pares(lista);
        etiquetas.slice(0, 20).forEach((par, i) => setTimeout(() => bajar(`/api/dymo/r3/archivo?${qsR3(par)}&tipo=label`, `TQT_R3_${par.map((n) => n.slice(-4)).join('_')}.label`), i * 300));
        toast(etiquetas.length > 20 ? 'Se descargaron las primeras 20. Para más, imprime directo en DYMO.' : 'Archivo .label descargado. Ábrelo con DYMO Label (o DYMO Connect).', { ms: 4000 });
    });
    r3Vista();
    cargarLotesR3();

    // ------------------------------------------------------------------ v1.3.45: escanear un lote pequeño para imprimir
    // R1/R2 → la etiqueta de su tarjeta (R1 + R2); R3 → etiqueta R3 doble, de dos en dos (si queda una sola, la otra mitad va vacía).
    // El celular se vincula como en la consola (misma vinculación guardada en la pestaña) o se usa un lector USB en el campo.
    const ESC_KEY = 'tqt.escaner.sesion';
    const primera = (c) => String(c || '').split(/\r?\n/).map((x) => x.trim()).filter(Boolean)[0] || '';
    function escGuardar() { try { if (ESC.token) sessionStorage.setItem(ESC_KEY, JSON.stringify({ token: ESC.token, id: ESC.id })); else sessionStorage.removeItem(ESC_KEY); } catch (e) { /* nada */ } }
    function escOlvidar() { ESC.token = null; ESC.id = null; ESC.moviles = 0; escGuardar(); escBoton(); }
    function escBoton() {
        const on = Boolean(ESC.token && ESC.moviles);
        $('btnEscVinc').dataset.on = on ? '1' : '';
        $('escVincTxt').textContent = on ? 'Celular vinculado' : 'Botón de escaneo (celular)';
        if (ESC.est) ESC.est.textContent = on ? 'Celular vinculado: lo que escanees se agrega a la lista.' : 'Esperando al celular…';
    }
    function escAvisar() {
        if (ESC.token) api(`/api/escaner/${ESC.token}/seccion`, { method: 'POST', body: { seccion: 'dymo', titulo: 'Etiquetas DYMO' } }).then((r) => { if (!r.ok && r.status === 404) escOlvidar(); });
    }
    async function escRestaurar() {
        let g = null; try { g = JSON.parse(sessionStorage.getItem(ESC_KEY) || 'null'); } catch (e) { g = null; }
        if (!g || !g.token) return;
        const r = await api(`/api/escaner/${g.token}`);
        if (r.ok && r.data) { ESC.token = g.token; ESC.id = r.data.id; ESC.moviles = r.data.moviles || 0; escBoton(); escAvisar(); } else escOlvidar();
    }
    async function escVincular() {
        if (!window.qrcode) { toast('No se pudo cargar el generador de QR. Recarga la página.', { kind: 'bad' }); return; }
        if (!ESC.token) {
            const r = await api('/api/escaner/sesion', { method: 'POST', body: { seccion: 'dymo', titulo: 'Etiquetas DYMO' } });
            if (!r.ok) { toast(r.error || 'No se pudo crear la vinculación', { kind: 'bad' }); return; }
            ESC.token = r.data.token; ESC.id = r.data.id; ESC.moviles = 0; escGuardar();
        }
        const url = `${location.origin}/escaner?s=${encodeURIComponent(ESC.token)}`;
        const q = window.qrcode(0, 'M'); q.addData(url); q.make();
        const qr = h('div', { style: 'background:#fff;padding:10px;border-radius:8px;width:220px;max-width:100%', role: 'img', 'aria-label': 'Código QR para vincular el celular' });
        qr.innerHTML = q.createSvgTag({ cellSize: 6, margin: 2, scalable: true });
        ESC.est = h('p', { role: 'status', 'aria-live': 'polite', style: 'font-weight:600;margin:0' });
        const partes = [qr, h('p', { class: 'hint', style: 'margin:0' }, 'Escanea este QR con el celular (o en la app: Más opciones › Escáner para la consola). Después escanea las placas o etiquetas que quieres imprimir.')];
        if (/^(localhost|127\.|\[::1\])/i.test(location.hostname)) partes.push(T.banner('warn', 'alert', 'Abriste la página como "localhost": el celular no llega a esa dirección. Ábrela con la IP de esta PC y vuelve a generar el QR.'));
        partes.push(ESC.est);
        escBoton();
        T.sheet({
            title: 'Botón de escaneo · vincular celular', focus: false, body: h('div', { class: 'stack', style: 'align-items:center;gap:12px' }, ...partes),
            onClose: () => { ESC.est = null; },
            actions: [
                { label: 'Desvincular', kind: 'ghost', onClick: async () => { const tk = ESC.token; escOlvidar(); if (tk) await api(`/api/escaner/${tk}`, { method: 'DELETE' }); toast('Celular desvinculado', { kind: 'ok' }); return true; } },
                { label: 'Listo', kind: 'primary', onClick: () => true },
            ],
        });
    }
    async function escAgregar(codigo) {
        const txt = primera(codigo); if (!txt) return null;
        const r = await api(`/api/consulta?codigo=${encodeURIComponent(String(codigo).trim())}`);
        if (!r.ok) return { ok: false, texto: r.network ? 'Sin conexión con el servidor.' : (r.error || `"${txt}" no se encontró`) };
        const d = r.data || {}; const p = d.pcb; const t = d.tarjeta;
        if (p && p.tipo === 'R3') {
            if (ESC.r3.includes(p.nombre)) return { ok: true, texto: `${p.nombre} ya estaba en la lista` };
            ESC.r3.push(p.nombre); escPintar();
            return { ok: true, texto: `${p.nombre} agregada (etiqueta R3)` };
        }
        if (!t) return { ok: false, texto: p ? `${p.nombre} no está emparejada: no tiene etiqueta de tarjeta.` : `"${txt}" no es una placa ni una tarjeta.` };
        const tj = state.tarjetas.find((x) => x.id === t.id) || t;
        if (modo(tj).k === 'NO') return { ok: false, texto: `Tarjeta ${tj.id_tarjeta_num}: falta R1 o R2, no se puede etiquetar.` };
        if (ESC.tarjetas.has(tj.id)) return { ok: true, texto: `Tarjeta ${tj.id_tarjeta_num} ya estaba en la lista` };
        ESC.tarjetas.set(tj.id, tj); escPintar();
        return { ok: true, texto: `Tarjeta ${tj.id_tarjeta_num} agregada (R1 + R2)` };
    }
    function escPintar() {
        const tj = [...ESC.tarjetas.values()];
        const quitar = (fn, lbl) => h('button', { class: 'btn btn-sm btn-ghost', type: 'button', 'aria-label': lbl, title: lbl, onclick: () => { fn(); escPintar(); } }, T.icon('x'));
        const fila = (...c) => h('div', { class: 'row', style: 'gap:8px;align-items:center;flex-wrap:nowrap;min-width:0' }, ...c);
        const filas = tj.map((t) => {
            const l = lineas(t); const fin = modo(t).k === 'FINAL';
            return fila(T.tipoChip('R1'), h('span', { class: 'mono grow', style: 'min-width:0;overflow-wrap:anywhere' }, `Tarjeta ${t.id_tarjeta_num} · ${l[0]} + ${l[2]}`),
                h('span', { class: 'hint' }, fin ? 'final' : 'identificación'), quitar(() => ESC.tarjetas.delete(t.id), `Quitar tarjeta ${t.id_tarjeta_num}`));
        });
        pares(ESC.r3).forEach((par, i) => {
            filas.push(fila(T.tipoChip('R3'), h('span', { class: 'mono grow', style: 'min-width:0;overflow-wrap:anywhere' }, `Etiqueta R3 ${i + 1} · ${par.join(' + ')}${par.length === 1 ? ' (mitad libre)' : ''}`),
                ...par.map((n) => quitar(() => { ESC.r3 = ESC.r3.filter((x) => x !== n); }, `Quitar ${n}`))));
        });
        const nR3 = pares(ESC.r3).length;
        $('escLista').replaceChildren(...(filas.length ? filas : [h('p', { class: 'muted', style: 'margin:0' }, 'Todavía no has escaneado nada.')]));
        $('escResumen').textContent = filas.length ? `${tj.length} tarjeta${tj.length === 1 ? '' : 's'} (R1 + R2) · ${ESC.r3.length} R3 en ${nR3} etiqueta${nR3 === 1 ? '' : 's'} → ${tj.length + nR3} etiqueta${tj.length + nR3 === 1 ? '' : 's'} en total` : '';
        refrescarBotones();
    }
    $('btnEscVinc').addEventListener('click', escVincular);
    $('btnEscVaciar').addEventListener('click', () => { ESC.tarjetas.clear(); ESC.r3 = []; escPintar(); });
    $('escIn').addEventListener('keydown', async (e) => {
        if (e.key !== 'Enter') return;
        e.preventDefault();
        const v = e.target.value.trim(); e.target.value = '';
        if (!v) return;
        const res = await escAgregar(v);
        if (res) toast(res.texto, { kind: res.ok ? 'ok' : 'warn' });
    });
    $('btnEscPrint').addEventListener('click', async () => {
        const tj = [...ESC.tarjetas.values()]; const r3 = ESC.r3.slice();
        if (tj.length) await imprimirSeleccion(tj);
        if (r3.length) await imprimirParesR3(r3);
    });
    const wsc = T.ws && T.ws('monitor');
    if (wsc && wsc.on) {
        wsc.on('ESCANER_VINCULADO', (d) => { if (d && d.id === ESC.id) { ESC.moviles = d.moviles || ESC.moviles + 1; escBoton(); toast('Celular vinculado: ya puedes escanear', { kind: 'ok' }); } });
        wsc.on('ESCANER_CERRADO', (d) => { if (d && d.id === ESC.id) { escOlvidar(); toast('Se cerró la vinculación con el celular', { kind: 'warn' }); } });
        wsc.on('ESCANEO_REMOTO', async (d) => {
            if (!d || d.id !== ESC.id || !d.codigo) return;
            let res; try { res = await escAgregar(d.codigo); } catch (e) { res = null; }
            res = res || { ok: false, texto: 'No se pudo procesar el código.' };
            toast(res.texto, { kind: res.ok ? 'ok' : 'warn' });
            if (ESC.token) api(`/api/escaner/${ESC.token}/resultado`, { method: 'POST', body: { n: d.n || 0, ok: res.ok, texto: String(res.texto).slice(0, 300) } });
        });
    }
    escPintar(); escRestaurar();

    load().then(() => { state.listo = true; }); conectar(false);
});
