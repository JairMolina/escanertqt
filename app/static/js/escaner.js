/**
 * escaner.js - Escáner para la consola (v1.3.43): el celular queda vinculado a una consola de escritorio y le envía lo que lee.
 * Sin ?s=token la cámara busca el QR de la consola ("Botón de escaneo"); con token cada lectura va a
 * POST /api/escaner/<token>/codigo y la consola responde por WebSocket (ESCANER_RESULTADO) qué hizo con ella.
 */
document.addEventListener('DOMContentLoaded', () => {
    'use strict';
    const T = window.TQT;
    const { h, api, icon, toast } = T;
    const $ = (id) => document.getElementById(id);

    T.mountShell({ active: '', sub: 'Escáner para la consola' });

    const st = { token: new URLSearchParams(location.search).get('s') || '', id: '', titulo: '', last: '', at: 0, envios: new Map(), tempranos: new Map() };
    const estado = $('remEstado');
    const lista = $('remLista');

    function tokenDe(texto) {
        const m = /\/escaner\?(?:[^#\s]*&)?s=([A-Za-z0-9_-]{10,})/.exec(String(texto || ''));
        return m ? m[1] : '';
    }
    function pintarEstado(tipo, extra) {
        estado.dataset.e = tipo;
        if (tipo === 'emparejar') {
            estado.replaceChildren(h('div', { class: 'rem-ico' }, icon('qr')), h('div', null, h('b', null, 'Escanea el QR de la consola'),
                h('p', { class: 'hint' }, 'En la PC pulsa "Botón de escaneo" (arriba, en cualquier sección) y apunta la cámara al QR que aparece.')));
        } else if (tipo === 'uniendo') {
            estado.replaceChildren(h('div', { class: 'rem-ico' }, icon('refresh')), h('div', null, h('b', null, 'Vinculando con la consola…')));
        } else if (tipo === 'ok') {
            estado.replaceChildren(h('div', { class: 'rem-ico' }, icon('monitor')), h('div', { class: 'grow' }, h('b', null, 'Vinculado a la consola'),
                h('p', { class: 'hint' }, st.titulo ? ['Sección abierta en la PC: ', h('b', null, st.titulo)] : 'Escanea una PCB o una etiqueta y se ubicará en la PC.')),
            h('button', { class: 'btn btn-sm btn-ghost', type: 'button', onclick: salir }, icon('unlink'), 'Salir'));
        } else {
            estado.replaceChildren(h('div', { class: 'rem-ico' }, icon('alert')), h('div', { class: 'grow' }, h('b', null, 'Sin vinculación'), h('p', { class: 'hint' }, extra || '')),
                h('button', { class: 'btn btn-sm', type: 'button', onclick: () => { olvidar(); pintarEstado('emparejar'); } }, 'Escanear QR'));
        }
    }
    function olvidar() {
        st.token = ''; st.id = ''; st.titulo = '';
        history.replaceState(null, '', '/escaner');
    }
    function salir() { olvidar(); pintarEstado('emparejar'); toast('Saliste del modo escáner', { kind: 'ok' }); }

    async function unir(token) {
        st.token = token; pintarEstado('uniendo');
        const r = await api(`/api/escaner/${encodeURIComponent(token)}/unir`, { method: 'POST' });
        if (!r.ok) { olvidar(); pintarEstado('error', r.status === 404 ? 'Ese QR ya caducó o la consola lo cerró. Genera uno nuevo en la PC.' : (r.error || 'No se pudo vincular.')); if (window.SoundFX) window.SoundFX.playError(); return; }
        st.id = r.data.id; st.titulo = r.data.titulo || '';
        history.replaceState(null, '', `/escaner?s=${encodeURIComponent(token)}`);
        pintarEstado('ok');
        if (window.SoundFX) window.SoundFX.playSuccess();
        if (window.Haptics) window.Haptics.success();
    }

    function filaEnvio(codigo) {
        const txt = h('span', { class: 'hint' }, 'Enviando…');
        const li = h('li', { dataset: { e: 'env' } }, h('span', { class: 'mono rem-cod' }, String(codigo).split(/\r?\n/).filter(Boolean).join(' · ')), txt);
        lista.prepend(li);
        while (lista.children.length > 15) lista.lastChild.remove();
        return { li, txt };
    }
    async function enviar(codigo) {
        const c = String(codigo || '').trim();
        if (!c || !st.token) return;
        const f = filaEnvio(c);
        const r = await api(`/api/escaner/${encodeURIComponent(st.token)}/codigo`, { method: 'POST', body: { codigo: c } });
        if (!r.ok) {
            f.li.dataset.e = 'bad'; f.txt.textContent = r.network ? 'Sin conexión: no llegó a la consola.' : (r.error || 'No se envió');
            if (window.SoundFX) window.SoundFX.playError();
            if (r.status === 404) { olvidar(); pintarEstado('error', 'La consola cerró la vinculación. Escanea de nuevo su QR.'); }
            return;
        }
        f.li.dataset.e = 'env'; f.txt.textContent = 'Enviado · esperando a la consola…';
        st.envios.set(r.data.n, f);
        if (st.tempranos.has(r.data.n)) { aplicar(f, st.tempranos.get(r.data.n)); st.tempranos.delete(r.data.n); }   // la consola respondió antes que el POST
        setTimeout(() => { if (st.envios.get(r.data.n) === f && f.li.dataset.e === 'env') { f.txt.textContent = 'Enviado (la consola no respondió: ¿está abierta?)'; f.li.dataset.e = 'warn'; } }, 6000);
        if (window.SoundFX) window.SoundFX.playScan('R1');
        if (window.Haptics) window.Haptics.scan();
    }

    function aplicar(f, d) {
        f.li.dataset.e = d.ok ? 'ok' : 'warn'; f.txt.textContent = d.texto || (d.ok ? 'Recibido en la consola' : 'La consola no lo encontró');
        if (!d.ok && window.SoundFX) window.SoundFX.playError();
    }

    function onCode(text) {
        const ahora = Date.now();
        if (text === st.last && ahora - st.at < 3000) return;   // la misma etiqueta sigue frente a la cámara
        st.last = text; st.at = ahora;
        const tk = tokenDe(text);
        if (tk) { if (tk !== st.token) unir(tk); return; }   // QR de una consola: (re)vincular
        if (!st.token) { toast('Primero escanea el QR de la consola', { kind: 'warn' }); return; }
        enviar(text);
    }

    $('remForm').addEventListener('submit', (e) => {
        e.preventDefault();
        const v = $('remQ').value.trim(); if (!v) return;
        const tk = tokenDe(v);
        if (tk) unir(tk); else if (!st.token) toast('Primero escanea el QR de la consola', { kind: 'warn' }); else enviar(v);
        $('remQ').value = '';
    });

    const ws = T.ws();
    if (ws) {
        ws.on('ESCANER_RESULTADO', (d) => {
            if (!d || d.id !== st.id) return;
            const f = st.envios.get(d.n);
            if (f) aplicar(f, d); else st.tempranos.set(d.n, d);
        });
        ws.on('ESCANER_SECCION', (d) => { if (d && d.id === st.id) { st.titulo = d.titulo || ''; pintarEstado('ok'); } });
        ws.on('ESCANER_CERRADO', (d) => { if (d && d.id === st.id) { olvidar(); pintarEstado('error', 'La consola cerró la vinculación. Escanea de nuevo su QR para seguir.'); } });
    }

    T.mountVisor($('visorHost'), { compact: true, onCode, vinculo: true });   // aquí el QR de la consola lo maneja onCode (sin recargar)
    if (st.token) unir(st.token); else pintarEstado('emparejar');
});
