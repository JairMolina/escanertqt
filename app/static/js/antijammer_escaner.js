/* antijammer_escaner.js - «Botón de escaneo» de Skudo AntiJammer (v1.4.30), igual que el de la consola de Escáner TQT (escritorio.js):
 * muestra un QR; el celular lo abre (/escaner?s=token), queda vinculado y cada lectura llega por WebSocket (ESCANEO_REMOTO)
 * con respaldo por HTTP. La lectura va a la pestaña abierta (AJ.escaneo): Recibir registra, Consultar busca y el resto
 * abre Consultar. La respuesta vuelve al celular (/api/escaner/{token}/resultado). API compartida: /api/escaner/*. */
(function () {
    'use strict';
    const T = window.TQT, P = window.AJ;
    const { h, icon, api } = T;
    const $ = (id) => document.getElementById(id);
    const CLAVE = 'tqt.antijammer.escaner.sesion';
    const TITULOS = { dashboard: 'Dashboard', recibir: 'Recibir', programar: 'Programar', consultar: 'Consultar', inventario: 'Inventario', lotes: 'Lotes', movimientos: 'Movimientos', excel: 'Excel' };
    const RS = { token: null, id: null, moviles: 0, ultN: 0, hoja: null, estado: null };
    const bEsc = $('bEsc');

    const seccion = () => { const v = P.actual(); return { seccion: 'antijammer-' + (v || ''), titulo: 'Skudo AntiJammer · ' + (TITULOS[v] || 'Consola') }; };
    function guardar() { try { if (RS.token) sessionStorage.setItem(CLAVE, JSON.stringify({ token: RS.token, id: RS.id })); else sessionStorage.removeItem(CLAVE); } catch (e) { /* nada */ } }
    function pintaBoton() {
        bEsc.dataset.on = RS.token && RS.moviles ? '1' : (RS.token ? 'esp' : '');
        bEsc.title = RS.token && RS.moviles ? 'Celular vinculado: lo que escanees aparece aquí' : 'Botón de escaneo: vincula tu celular con un QR';
    }
    function pintaEstado() {
        if (!RS.estado) return;
        RS.estado.dataset.on = RS.moviles ? '1' : '';
        RS.estado.replaceChildren(RS.moviles ? icon('check') : h('i', { class: 'tp-qr-pulso', 'aria-hidden': 'true' }),
            h('span', null, RS.moviles ? `Celular vinculado${RS.moviles > 1 ? ` (${RS.moviles})` : ''}. Lo que escanees llegará a la pestaña abierta.` : 'Esperando al celular…'));
    }
    function olvidar() { RS.token = null; RS.id = null; RS.moviles = 0; guardar(); pintaBoton(); }
    function avisarSeccion() {
        if (!RS.token) return;
        api(`/api/escaner/${RS.token}/seccion`, { method: 'POST', body: seccion() }).then((r) => { if (!r.ok && r.status === 404) olvidar(); });
    }
    async function restaurar() {
        let g = null; try { g = JSON.parse(sessionStorage.getItem(CLAVE) || 'null'); } catch (e) { g = null; }
        if (!g || !g.token) return;
        const r = await api(`/api/escaner/${g.token}`);
        if (r.ok && r.data) { RS.token = g.token; RS.id = r.data.id; RS.moviles = r.data.moviles || 0; RS.ultN = r.data.n || 0; pintaBoton(); avisarSeccion(); } else olvidar();
    }
    function qrSvg(texto) {
        const q = window.qrcode(0, 'M'); q.addData(texto); q.make();
        const box = h('div', { class: 'tp-qr', role: 'img', 'aria-label': 'Código QR para vincular el celular' });
        box.innerHTML = q.createSvgTag({ cellSize: 6, margin: 2, scalable: true });
        return box;
    }
    async function copiar(texto) {
        let ok = false;
        try { if (navigator.clipboard && window.isSecureContext) { await navigator.clipboard.writeText(texto); ok = true; } } catch (e) { ok = false; }
        T.toast(ok ? 'Enlace copiado' : 'No se pudo copiar. Selecciona el enlace y cópialo.', { kind: ok ? 'ok' : 'warn' });
    }

    async function abrir() {
        if (!window.qrcode) { T.toast('No se pudo cargar el generador de QR. Recarga la página.', { kind: 'bad' }); return; }
        if (!RS.token) {
            const r = await api('/api/escaner/sesion', { method: 'POST', body: seccion() });
            if (!r.ok) { T.toast(r.error || 'No se pudo crear la vinculación. Revisa la conexión e inténtalo de nuevo.', { kind: 'bad' }); return; }
            RS.token = r.data.token; RS.id = r.data.id; RS.moviles = 0; RS.ultN = 0; guardar(); pintaBoton();
        }
        const url = `${location.origin}/escaner?s=${encodeURIComponent(RS.token)}`;
        const local = /^(localhost|127\.|\[::1\])/i.test(location.hostname);
        RS.estado = h('div', { class: 'tp-qr-est', role: 'status', 'aria-live': 'polite' });
        pintaEstado();
        const body = h('div', { class: 'tp-qr-hoja' },
            qrSvg(url),
            h('div', { class: 'tp-qr-txt' },
                h('ol', null,
                    h('li', null, 'En el celular escanea este QR con la cámara (o en la app: ', h('b', null, 'Más opciones › Escáner para la consola'), ').'),
                    h('li', null, 'Inicia sesión si te lo pide. El celular queda como escáner de esta pantalla.'),
                    h('li', null, 'Escanea la placa Skudo AntiJammer: en Recibir se registra y en Consultar se abre su ficha. Desde otra pestaña se abre en Consultar.')),
                local ? T.banner('warn', 'alert', h('b', null, 'Abriste Skudo AntiJammer como "localhost". '), 'El celular no puede llegar a esa dirección: abre Skudo AntiJammer con la IP de esta PC (por ejemplo https://192.168.x.x:8443/antijammer) y vuelve a generar el QR.') : null,
                RS.estado,
                h('details', null, h('summary', null, 'Enlace manual'), h('code', { class: 'mono tp-qr-url' }, url),
                    h('button', { class: 'btn btn-sm', type: 'button', onclick: () => copiar(url) }, icon('paste'), 'Copiar'))));
        RS.hoja = T.sheet({
            title: 'Botón de escaneo · vincular celular', body, focus: false,
            onClose: () => { RS.hoja = null; RS.estado = null; },
            actions: [
                { label: 'Desvincular', kind: 'ghost', icon: 'unlink', onClick: async () => { const tk = RS.token; olvidar(); if (tk) await api(`/api/escaner/${tk}`, { method: 'DELETE' }); T.toast('Celular desvinculado', { kind: 'ok' }); return true; } },
                { label: 'Listo', kind: 'primary', onClick: () => true },
            ],
        });
        RS.hoja.el.classList.add('tp-hoja-ancha');
    }

    async function recibir(d) {
        const codigo = String((d && d.codigo) || '').trim(); if (!codigo) return;
        if (d.n) { if (d.n <= RS.ultN) return; RS.ultN = d.n; }   // ya atendido (llegó por WebSocket y por el sondeo)
        let res = null;
        try { res = await P.escaneo(codigo); } catch (e) { console.error(e); }
        if (!res) res = { ok: false, texto: 'Skudo AntiJammer no pudo procesar el código.' };
        T.toast(res.texto, { kind: res.ok ? 'ok' : 'warn' });
        if (RS.token) api(`/api/escaner/${RS.token}/resultado`, { method: 'POST', body: { n: d.n || 0, ok: !!res.ok, texto: String(res.texto || '').slice(0, 300) } });
    }

    bEsc.addEventListener('click', abrir);
    document.addEventListener('antijammer:vista', avisarSeccion);
    const ws = T.ws('monitor');
    if (ws) {
        ws.on('ESCANER_VINCULADO', (d) => {
            if (!d || d.id !== RS.id) return;
            RS.moviles = d.moviles || RS.moviles + 1; pintaBoton(); pintaEstado();
            T.toast('Celular vinculado: ya puedes escanear', { kind: 'ok' });
            if (RS.hoja) { const hj = RS.hoja; setTimeout(() => { if (RS.hoja === hj) hj.close(); }, 1600); }
        });
        ws.on('ESCANEO_REMOTO', (d) => { if (d && d.id === RS.id) recibir(d); });
        ws.on('ESCANER_CERRADO', (d) => { if (d && d.id === RS.id) { olvidar(); T.toast('Se cerró la vinculación con el celular', { kind: 'warn' }); } });
    }
    // respaldo por HTTP: si el WebSocket se cayó, los códigos del celular no se pierden
    setInterval(async () => {
        if (!RS.token || document.hidden) return;
        const r = await api(`/api/escaner/${RS.token}/codigos?desde=${RS.ultN}`);
        if (!r.ok) { if (r.status === 404) olvidar(); return; }
        if (r.data.moviles !== RS.moviles) { RS.moviles = r.data.moviles || 0; pintaBoton(); pintaEstado(); }
        for (const c of r.data.items || []) await recibir({ id: RS.id, n: c.n, codigo: c.codigo });
    }, 2500);
    pintaBoton();
    restaurar();
})();
