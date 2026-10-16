/* v1.4.2: DYMO compartida (window.TQTDymoRemoto). Encola la etiqueta en el servidor; la imprime la Raspberry.
 *   await TQTDymoRemoto.imprimir({ tipo:'tarjeta'|'aprobada'|'cable'|'r3', tarjeta_id, numero, nombres, copias }, onEstado)
 * Resuelve cuando la Raspberry confirma «impresa»; lanza Error si quedó en error/cancelada/desconocido o sin confirmar. */
(function () {
    'use strict';
    const VALOR = '__remota__';
    const API = '/api/dymo/remoto';
    const FINALES = ['impresa', 'error', 'desconocido', 'cancelada'];
    const dormir = (ms) => new Promise((r) => setTimeout(r, ms));
    async function req(url, body) {
        let res;
        try {
            res = await fetch(url, body === undefined ? { cache: 'no-store' }
                : { method: 'POST', cache: 'no-store', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
        } catch (e) { throw new Error('Sin conexión con el servidor.'); }
        const data = await res.json().catch(() => null);
        if (!res.ok) throw new Error((data && (typeof data.detail === 'string' ? data.detail : null)) || `El servidor respondió ${res.status}.`);
        return data;
    }
    async function estado() {
        try { return await req(API + '/estado'); } catch (e) { return { disponible: false, agentes: [], en_cola: 0, error: e.message }; }
    }
    async function imprimir(pedido, onEstado) {
        const cb = typeof onEstado === 'function' ? onEstado : () => {};
        let j = await req(API + '/trabajos', Object.assign({}, pedido, { copias: Math.max(1, Math.min(20, pedido.copias || 1)) }));
        const fin = Date.now() + 120000;
        while (!FINALES.includes(j.estado)) {
            cb(j);
            if (Date.now() > fin) throw new Error('La DYMO compartida no confirmó a tiempo; revisa la impresora antes de reintentar (puede haber salido).');
            await dormir(1500);
            try { j = await req(API + '/trabajos/' + j.id); } catch (e) { /* reintenta en el siguiente ciclo */ }
        }
        cb(j);
        if (j.estado !== 'impresa') throw new Error('DYMO compartida: ' + (j.detalle || j.estado));
        return j;
    }
    window.TQTDymoRemoto = { VALOR, estado, imprimir };
})();
