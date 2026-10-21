/* tpms.js - Módulo TPMS: escaneo de QR con cámara y alta de placas TPMS (POST /api/tpms/escanear, v1.4.27).
 * Reutiliza el visor compartido (visor.js + scanner.js + jsQR), sonido (audio.js) y vibración/anillo (haptics.js).
 * El historial vive en sessionStorage de esta pestaña y se borra al cerrar sesión (cerrarSesion limpia sessionStorage). */
(function () {
    'use strict';
    const T = window.TQT;
    const { h, icon, api } = T;
    const $ = (id) => document.getElementById(id);
    const ROLES = { administrador: 'Administrador', general: 'General', consultor: 'Consulta' };
    const CLAVE = 'tqt.tpms.historial';
    const MAX = 12;

    // El tema lo fija el <head>; common.js lo pisa a "oscuro" si no hay ajuste guardado: se restablece la preferencia del sistema.
    (function () {
        let g = null; try { g = localStorage.getItem('tqt.tema'); } catch (e) { /* nada */ }
        T.applyTheme(g === 'light' || g === 'dark' ? g : (matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark'));
    })();
    T.hydrateIcons();

    // ------------------------------------------------------------------ cabecera
    function pintaTema() { $('bTema').replaceChildren(icon(T.currentTheme() === 'light' ? 'moon' : 'sun')); }
    $('bTema').addEventListener('click', () => { T.toggleTheme(); pintaTema(); });
    pintaTema();
    $('bSalir').addEventListener('click', () => { if (visor) visor.stop(); T.cerrarSesion(); });

    (async function cargaYo() {
        const r = await api('/api/auth/yo');
        if (!r.ok || !r.data) return;
        $('uMail').textContent = r.data.email || '';
        $('uRol').textContent = ROLES[r.data.rol] || r.data.rol || '';
        $('usuario').hidden = !r.data.email;
    })();

    // ------------------------------------------------------------------ historial (memoria de la sesión)
    function leeHist() {
        try { const a = JSON.parse(sessionStorage.getItem(CLAVE) || '[]'); return Array.isArray(a) ? a.slice(0, MAX) : []; } catch (e) { return []; }
    }
    function guardaHist() { try { sessionStorage.setItem(CLAVE, JSON.stringify(hist)); } catch (e) { /* modo privado: queda en memoria */ } }
    let hist = leeHist();

    const fmtHora = (ms) => { try { return new Date(ms).toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit', second: '2-digit' }); } catch (e) { return ''; } };
    const ORIGEN = { camara: 'Cámara', manual: 'Escrito a mano' };

    async function copiar(texto) {
        let ok = false;
        try { if (navigator.clipboard && window.isSecureContext) { await navigator.clipboard.writeText(texto); ok = true; } } catch (e) { ok = false; }
        if (!ok) {
            const ta = h('textarea', { readonly: '', style: 'position:fixed;top:-100px;opacity:0' }); ta.value = texto;
            document.body.appendChild(ta); ta.select();
            try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
            ta.remove();
        }
        T.toast(ok ? 'Código copiado' : 'No se pudo copiar. Mantén presionado el código para copiarlo.', { kind: ok ? 'ok' : 'warn' });
    }

    function pintaUltimo(animar) {
        const u = hist[0], box = $('ultimo');
        box.dataset.vacio = u ? '0' : '1';
        $('uCodigo').textContent = u ? u.codigo : 'Aún no hay lecturas';
        $('uOrigen').textContent = u ? ORIGEN[u.origen] || '' : '';
        $('uHora').textContent = u ? fmtHora(u.t) + (u.veces > 1 ? ` · leído ${u.veces} veces` : '') : '';
        $('bCopiar').disabled = !u;
        if (animar) { box.classList.remove('nuevo'); void box.offsetWidth; box.classList.add('nuevo'); }
    }

    function pintaLista() {
        const lista = $('hLista');
        lista.replaceChildren(...hist.map((x) => h('li', null,
            h('div', { class: 'dato' },
                h('span', { class: 'cod', title: x.codigo }, x.codigo),
                h('span', { class: 'meta' }, fmtHora(x.t) + ' · ' + (ORIGEN[x.origen] || ''),
                    x.veces > 1 ? h('span', { class: 'veces' }, ` · ×${x.veces}`) : null)),
            h('button', { class: 'iconbtn', type: 'button', 'aria-label': 'Copiar ' + x.codigo, title: 'Copiar código', onclick: () => copiar(x.codigo) }, icon('paste')))));
        $('hVacio').hidden = hist.length > 0;
        $('bVaciar').hidden = hist.length === 0;
        $('hCuenta').textContent = hist.length ? `(${hist.length})` : '';
    }

    // ------------------------------------------------------------------ lote (por dispositivo) y alta en el servidor
    const CLAVE_LOTE = 'tqt.tpms.lote', inLote = $('loteTpms');
    try { inLote.value = localStorage.getItem(CLAVE_LOTE) || ''; } catch (e) { /* nada */ }
    inLote.addEventListener('change', () => { try { localStorage.setItem(CLAVE_LOTE, inLote.value.trim()); } catch (e) { /* nada */ } });
    const RES = { AGREGADA: ['ok', 'registrada'], REPETIDA: ['warn', 'ya estaba registrada'], INVALIDA: ['bad', ''] };
    function pintaEstado(k, txt) { const e = $('uEstado'); e.hidden = !txt; e.dataset.k = k; e.textContent = txt; }

    async function darDeAlta(codigo) {
        pintaEstado('', 'Registrando…');
        const r = await api('/api/tpms/escanear', { method: 'POST', body: { codigo, lote: inLote.value.trim() } });
        if (hist[0] && hist[0].codigo !== codigo) return;   // ya llegó otra lectura
        if (!r.ok) { pintaEstado('bad', r.error || 'No se pudo registrar. Revisa la conexión e inténtalo otra vez.'); if (window.SoundFX) window.SoundFX.playError(); return; }
        const d = r.data || {}, [k, txt] = RES[d.resultado] || ['bad', ''];
        pintaEstado(k, d.pcb ? `${d.pcb.nombre} · ${txt}${d.pcb.lote ? ' · lote ' + d.pcb.lote : ''}` : d.mensaje);
        if (k === 'bad') { if (window.SoundFX) window.SoundFX.playError(); if (window.Haptics) window.Haptics.error(); }
    }

    /** Registra una lectura: si ya estaba, sube al inicio y cuenta otra vez (aviso de repetido). */
    function registrar(texto, origen) {
        let codigo = String(texto || '').replace(/[\r\n\t]+/g, ' ').trim().slice(0, 300);
        if (origen === 'manual' && /^[0-9]{1,4}$/.test(codigo)) codigo = 'TPMS_V1_' + codigo.padStart(4, '0');   // solo la serie
        if (!codigo) return false;
        const i = hist.findIndex((x) => x.codigo === codigo);
        const previo = i >= 0 ? hist.splice(i, 1)[0] : null;
        hist.unshift({ codigo, origen, t: Date.now(), veces: previo ? (previo.veces || 1) + 1 : 1 });
        hist = hist.slice(0, MAX);
        guardaHist();
        pintaUltimo(true); pintaLista();
        if (previo) {
            if (window.SoundFX) window.SoundFX.playDup();
            if (window.Haptics) window.Haptics.dup();
        } else {
            if (window.SoundFX) window.SoundFX.playScan('R2');
            if (window.Haptics) window.Haptics.scan();
        }
        darDeAlta(codigo);
        return true;
    }

    $('bCopiar').addEventListener('click', () => { if (hist[0]) copiar(hist[0].codigo); });
    $('bVaciar').addEventListener('click', () => {
        hist = []; guardaHist(); pintaUltimo(false); pintaLista();
        if (visor) visor.forget();
        T.toast('Lecturas borradas de este dispositivo');
    });

    // ------------------------------------------------------------------ entrada manual / lector USB
    $('fManual').addEventListener('submit', (e) => {
        e.preventDefault();
        const inp = $('manCod');
        if (!inp.value.trim()) { inp.focus(); T.toast('Escribe el código del sensor', { kind: 'warn' }); return; }
        if (registrar(inp.value, 'manual')) { inp.value = ''; inp.focus(); }
    });

    // ------------------------------------------------------------------ cámara
    let visor = null;
    const marco = $('marcoCam'), bCam = $('bCam');
    function pintaBoton(on) {
        marco.dataset.cam = on ? 'on' : 'off';
        bCam.setAttribute('aria-pressed', String(on));
        $('bCamT').textContent = on ? 'Detener cámara' : 'Iniciar cámara';
        bCam.querySelector('.svg-i').replaceWith(icon(on ? 'x' : 'camera'));
    }
    visor = T.mountVisor($('camHost'), {
        autoStart: false, vinculo: true, repeatMs: 2500,
        onManual: () => { apagar(); $('manCod').focus(); },
        onCode: (texto) => registrar(texto, 'camara'),
    });
    async function encender() {
        if (window.SoundFX) window.SoundFX.unlock();   // el toque del usuario habilita el audio del navegador
        pintaBoton(true);
        await visor.start();
    }
    function apagar() { if (visor) visor.stop(); pintaBoton(false); }
    bCam.addEventListener('click', () => { if (marco.dataset.cam === 'on') apagar(); else encender(); });
    window.addEventListener('pagehide', () => { if (visor) visor.stop(); });

    pintaUltimo(false); pintaLista();
})();
