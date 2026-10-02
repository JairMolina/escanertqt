/**
 * dymo_connect.js - Envoltorio del DYMO Connect Framework (js/vendor/dymo.connect.framework.js).
 * Habla con el servicio web local de DYMO Connect (https://127.0.0.1:41951-41960) desde el navegador de la PC
 * que tiene la impresora conectada. No funciona desde celulares.
 *
 *   const d = await TQTDymo.detect();      // {estado, printers, preferred, detalle}
 *   await TQTDymo.print(nombreImpresora, xml, copias);
 *
 * Estados de detect(): 'movil' · 'sin_framework' · 'no_servicio' · 'sin_impresoras' · 'listo'
 */
(function () {
    'use strict';

    const CHECK_URL = 'https://127.0.0.1:41951/DYMO/DLS/Printing/Check';
    const T_INIT = 7000, T_PRINTERS = 8000, T_PRINT = 25000;

    const isMobile = () => {
        try { if (navigator.userAgentData && navigator.userAgentData.mobile) return true; } catch (e) { /* nada */ }
        return /Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent || '');
    };
    /** Chrome puede bloquear el acceso a 127.0.0.1 desde una IP de la LAN; desde localhost no hay problema. */
    const enLocalhost = () => ['localhost', '127.0.0.1', '[::1]'].includes(location.hostname);

    function withTimeout(p, ms, msg) {
        return new Promise((resolve, reject) => {
            const t = setTimeout(() => reject(new Error(msg)), ms);
            Promise.resolve(p).then((v) => { clearTimeout(t); resolve(v); }, (e) => { clearTimeout(t); reject(e); });
        });
    }

    let fw = null;
    let initPromise = null;
    function framework() {
        if (fw) return fw;
        fw = window.dymo && window.dymo.label && window.dymo.label.framework ? window.dymo.label.framework : null;
        return fw;
    }

    /** Inicializa el framework una sola vez (busca el servicio en los puertos 41951-41960). */
    function init(force) {
        const f = framework();
        if (!f) return Promise.reject(new Error('El framework de DYMO no se cargó'));
        if (initPromise && !force) return initPromise;
        initPromise = new Promise((resolve) => {
            let done = false;
            const fin = () => { if (!done) { done = true; resolve(); } };
            try {
                if (typeof f.init === 'function') f.init(fin); else fin();
            } catch (e) { fin(); }
            setTimeout(fin, T_INIT);
        });
        return initPromise;
    }

    function listPrinters(collection) {
        const out = []; const seen = new Set();
        const push = (p) => { if (p && p.name && !seen.has(p.name)) { seen.add(p.name); out.push(p); } };
        if (Array.isArray(collection)) collection.forEach(push);
        else if (collection && typeof collection === 'object') Object.keys(collection).forEach((k) => push(collection[k]));
        return out;
    }
    const esLabelWriter = (p) => (!p.printerType || p.printerType === 'LabelWriterPrinter') && /LabelWriter/i.test(`${p.modelName || ''} ${p.name || ''} ${p.printerType || ''}`) ;
    const es550 = (p) => /550/.test(`${p.modelName || ''} ${p.name || ''}`);

    /** Diagnóstico completo. Nunca lanza. */
    async function detect(force) {
        if (isMobile()) return { estado: 'movil', printers: [], preferred: null, detalle: 'Los celulares no pueden imprimir directo en la DYMO.' };
        const f = framework();
        if (!f) return { estado: 'sin_framework', printers: [], preferred: null, detalle: 'No se cargó js/vendor/dymo.connect.framework.js.' };
        try { await init(force); } catch (e) { return { estado: 'sin_framework', printers: [], preferred: null, detalle: String(e.message || e) }; }

        let env = null;
        try { env = f.checkEnvironment(); } catch (e) { env = null; }
        if (env && env.isWebServicePresent === false) {
            return { estado: 'no_servicio', printers: [], preferred: null, detalle: (env.errorDetails || 'No responde el servicio de DYMO Connect.'), env };
        }
        let raw;
        try { raw = await withTimeout(f.getPrintersAsync(), T_PRINTERS, 'DYMO Connect no respondió a tiempo'); }
        catch (e) { return { estado: 'no_servicio', printers: [], preferred: null, detalle: String((e && e.message) || e), env }; }

        const printers = listPrinters(raw).filter(esLabelWriter);
        if (!printers.length) return { estado: 'sin_impresoras', printers: [], preferred: null, detalle: 'DYMO Connect responde, pero no ve ninguna LabelWriter.', env };
        const preferred = (printers.find((p) => es550(p) && p.isConnected) || printers.find((p) => p.isConnected) || printers.find(es550) || printers[0]).name;
        return { estado: 'listo', printers: printers.map((p) => ({ name: p.name, modelName: p.modelName || '', isConnected: p.isConnected !== false })), preferred, detalle: '', env };
    }

    /** Etiqueta DYMO Connect (<DesktopLabel>, formato .dymo) o de DYMO Label v8 (<DieCutLabel>). */
    const esXmlEtiqueta = (xml) => typeof xml === 'string' && (xml.indexOf('<DesktopLabel') >= 0 || xml.indexOf('<DieCutLabel') >= 0);

    /** Valida el XML con el framework antes de imprimir. Devuelve null si es válido o un texto con el motivo. */
    function validarXml(xml) {
        const f = framework();
        try {
            const label = f.openLabelXml(xml);
            if (label && typeof label.isValidLabel === 'function' && !label.isValidLabel()) return 'DYMO Connect no reconoce el XML de esta etiqueta.';
            return null;
        } catch (e) { return `El XML de la etiqueta no es válido: ${(e && e.message) || e}`; }
    }

    /** Imprime `copias` copias de una etiqueta. Lanza Error con un mensaje accionable si falla. */
    async function print(printerName, xml, copias) {
        const f = framework();
        if (!f) throw new Error('El framework de DYMO no está cargado.');
        if (!printerName) throw new Error('Elige una impresora DYMO.');
        if (!esXmlEtiqueta(xml)) throw new Error('El servidor no devolvió un XML de etiqueta válido.');
        const bad = validarXml(xml);
        if (bad) throw new Error(bad);
        const params = `<LabelWriterPrintParams><Copies>${Math.max(1, Math.min(99, copias || 1))}</Copies></LabelWriterPrintParams>`;
        try {
            await withTimeout(f.printLabelAsync(printerName, params, xml, ''), T_PRINT, 'La impresora no respondió (tiempo agotado).');
        } catch (e) {
            const m = String((e && e.message) || e || '');
            if (/no responde|timeout|tiempo/i.test(m)) throw new Error('La impresora no respondió. Revisa que esté encendida, con rollo y sin atasco, y vuelve a intentar.');
            if (/printer/i.test(m) && /not|no/i.test(m)) throw new Error(`DYMO Connect no encuentra la impresora "${printerName}". Actualiza la lista.`);
            throw new Error(m || 'DYMO Connect rechazó la impresión.');
        }
    }

    window.TQTDymo = { detect, print, init, validarXml, esXmlEtiqueta, isMobile, enLocalhost, CHECK_URL };
})();
