/**
 * dymo_imprimir.js - v1.4.0: impresión de aprobación desde Validación (contrato K2), sin salir de /monitor.
 *
 *   const r = await TQTDymoImprimir.aprobadaYCable({ tarjeta, onProgreso, impresora, respaldoNavegador });
 *   -> { ok, impresas: [{ tipo:'tarjeta'|'cable', numero, estado:'enviada'|'error', error? }], error }
 *
 * 1) Etiqueta de la tarjeta (mismo formato 30334 y datos de /dymo) con la leyenda «Aprobada» debajo (?aprobada=1).
 * 2) Etiqueta de cable con el número de la tarjeta (endpoint existente /api/dymo/cable/xml, modo simple, sin pareja R1/R2).
 * Usa DYMO Connect (TQTDymo, dymo_connect.js). 'enviada' = aceptada por la cola de DYMO; el SDK no confirma salida física.
 * Sin DYMO Connect NO se abre window.print() por sí solo ni se finge éxito: se devuelve error con el motivo. El respaldo del
 * diálogo del navegador existe solo con { respaldoNavegador: true } (acción explícita del operador; no es silencioso).
 * Dependencias: common.js (opcional, T.store), vendor/dymo.connect.framework.js y dymo_connect.js.
 */
(function () {
    'use strict';
    const D = () => window.TQTDymo;
    let ocupado = false;   // evita doble clic / dos tandas simultáneas
    const FATAL = /no respondi|no encuentra|Elige|cargó|Sin conexión/i;

    const numeroCable = (t) => String(t.id_tarjeta_num == null ? '' : t.id_tarjeta_num).replace(/\D/g, '').padStart(4, '0').slice(-6);

    async function xml(url) {
        let res;
        try { res = await fetch(url, { cache: 'no-store' }); } catch (e) { throw new Error('Sin conexión con el servidor.'); }
        if (!res.ok) throw new Error(`El servidor respondió ${res.status}.`);
        const txt = await res.text();
        if (!D().esXmlEtiqueta(txt)) throw new Error('El servidor no devolvió un XML de etiqueta válido.');
        return txt;
    }
    /** Igual que dymo.js: primero el XML v8 (servicio DLS) y, si lo rechaza, el de DYMO Connect (.dymo). */
    async function imprimirXml(printer, urlDe) {
        let primero = null;
        for (const tipo of ['label', 'dymo']) {
            try { await D().print(printer, await xml(urlDe(tipo)), 1); return; }
            catch (e) { if (FATAL.test(e.message)) throw e; if (!primero) primero = e; }
        }
        throw primero;
    }

    /** Respaldo explícito: SVG a escala real del servidor en un iframe + cuadro de impresión del navegador. */
    function imprimirNavegador(urls) {
        return new Promise((resolve) => {
            const fr = document.createElement('iframe');
            fr.setAttribute('title', 'Impresión de etiquetas'); fr.setAttribute('aria-hidden', 'true');
            fr.style.cssText = 'position:fixed;right:0;bottom:0;width:0;height:0;border:0';
            document.body.append(fr);
            const doc = fr.contentDocument; doc.open();
            doc.write('<!doctype html><html><head><meta charset="utf-8"><title>Etiquetas TQT</title><style>@page{size:57mm 32mm;margin:0}html,body{margin:0;background:#fff}img{display:block;width:57mm;height:32mm;break-after:page;page-break-after:always}img:last-child{break-after:auto;page-break-after:auto}</style></head><body>'
                + urls.map((u) => `<img src="${u}" alt="">`).join('') + '</body></html>');
            doc.close();
            const imgs = [...doc.images]; let n = imgs.length;
            const listo = () => { if (--n > 0) return; setTimeout(() => { try { fr.contentWindow.focus(); fr.contentWindow.print(); } finally { setTimeout(() => { fr.remove(); resolve(); }, 1000); } }, 100); };
            imgs.forEach((i) => { if (i.complete) listo(); else { i.onload = listo; i.onerror = listo; } });
        });
    }

    async function aprobadaYCable(op) {
        const o = op || {}; const t = o.tarjeta;
        const prog = typeof o.onProgreso === 'function' ? o.onProgreso : () => {};
        const impresas = [];
        if (!t || t.id == null) return { ok: false, impresas, error: 'Falta la tarjeta a imprimir.' };
        if (ocupado) return { ok: false, impresas, error: 'Ya hay una impresión en curso.' };
        const num = numeroCable(t);
        if (!/^[0-9]{1,6}$/.test(num)) return { ok: false, impresas, error: 'La tarjeta no tiene un número válido para la etiqueta de cable.' };
        if (!D()) return { ok: false, impresas, error: 'Falta el módulo de DYMO Connect (dymo_connect.js).' };
        ocupado = true;
        try {
            const d = await D().detect();
            const urlTarjeta = (tipo) => `/api/dymo/label/${t.id}/xml?tipo=${tipo}&aprobada=1`;
            const urlCable = (tipo) => `/api/dymo/cable/xml?numero=${encodeURIComponent(num)}&tipo=${tipo}`;
            if (d.estado !== 'listo') {
                if (!o.respaldoNavegador || d.estado === 'movil') {
                    const motivo = { movil: 'Los celulares no pueden imprimir directo en la DYMO.', no_servicio: 'No se encontró DYMO Connect en esta PC. Instálalo o ábrelo para imprimir con un clic.', sin_impresoras: 'DYMO Connect no ve ninguna LabelWriter.', sin_framework: 'No se cargó el módulo de DYMO.' }[d.estado] || d.detalle || 'DYMO no disponible.';
                    return { ok: false, impresas, error: motivo, estado: d.estado };
                }
                prog(1, 2, 'Abriendo el cuadro de impresión del navegador…');
                await imprimirNavegador([`/api/dymo/svg/${t.id}?aprobada=1&guia=false`, `/api/dymo/cable/svg?numero=${encodeURIComponent(num)}`]);
                impresas.push({ tipo: 'tarjeta', numero: num, estado: 'enviada' }, { tipo: 'cable', numero: num, estado: 'enviada' });
                return { ok: true, impresas, error: null, via: 'navegador' };
            }
            let printer = o.impresora;
            if (!printer) { try { printer = window.TQT && window.TQT.store && window.TQT.store.get('tqt.dymo.impresora'); } catch (e) { /* nada */ } }
            if (!printer || !d.printers.some((p) => p.name === printer)) printer = d.preferred;
            const pasos = [['tarjeta', 'etiqueta Aprobada', urlTarjeta], ['cable', `cable ${num}`, urlCable]];
            let error = null;
            for (let i = 0; i < pasos.length; i++) {
                const [tipo, nombre, url] = pasos[i];
                prog(i + 1, 2, `Imprimiendo ${i + 1}/2: ${nombre}…`);
                try { await imprimirXml(printer, url); impresas.push({ tipo, numero: num, estado: 'enviada' }); prog(i + 1, 2, `Enviada ${i + 1}/2: ${nombre}.`); }
                catch (e) { impresas.push({ tipo, numero: num, estado: 'error', error: e.message }); error = error || `${nombre}: ${e.message}`; }   // si falla una no se repite la otra
            }
            return { ok: !error, impresas, error, via: 'dymo_connect', impresora: printer };
        } catch (e) {
            return { ok: false, impresas, error: String((e && e.message) || e) };
        } finally { ocupado = false; }
    }

    window.TQTDymoImprimir = { aprobadaYCable, numeroCable, ocupado: () => ocupado };
})();
