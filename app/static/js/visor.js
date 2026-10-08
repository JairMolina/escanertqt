/**
 * visor.js - Visor de cámara reutilizable (Recibir, Programar, Consultar, selectores de PCB).
 * Crea el video, el marco de esquinas, linterna / cambio de cámara / sonido y el panel de error de permisos.
 *   const v = TQT.mountVisor(host, { compact:false, onCode:(text, meta)=>{} });
 *   v.lock()/unlock()  bloqueo lógico (no congela el video) · v.flash('ok'|'warn'|'error') · v.stop()/start()
 */
(function () {
    'use strict';
    const { h, icon, store } = window.TQT;

    function mountVisor(host, opts = {}) {
        const video = h('video', { playsinline: '', muted: '', autoplay: '', 'aria-label': 'Vista de la cámara' });
        const frame = h('div', { class: 'frame', 'aria-hidden': 'true' }, h('i'), h('i'), h('i'), h('i'));
        const btnTorch = h('button', { class: 'iconbtn is-torch', type: 'button', 'aria-label': 'Linterna', 'aria-pressed': 'false', hidden: true }, icon('flash'));
        const btnFlip = h('button', { class: 'iconbtn', type: 'button', 'aria-label': 'Cambiar de cámara', hidden: true }, icon('flip'));
        const soundOn = store.get('tqt.sonido', '1') !== '0';
        const btnSound = h('button', { class: 'iconbtn', type: 'button', 'aria-label': 'Sonido', 'aria-pressed': String(soundOn) }, icon(soundOn ? 'vol' : 'muted'));
        const status = h('button', { class: 'status', type: 'button', style: 'border:0;cursor:default' }, 'Iniciando cámara…');
        const el = h('div', { class: 'visor' + (opts.compact ? ' compact' : ''), dataset: { state: 'idle' } },
            video, frame, h('div', { class: 'tools' }, btnTorch, btnFlip, btnSound), status);
        host.appendChild(el);

        if (window.SoundFX) window.SoundFX.enabled = soundOn;
        if (window.Haptics) window.Haptics.setTarget(el);

        let failPanel = null;
        const clearFail = () => { if (failPanel) { failPanel.remove(); failPanel = null; } };

        const scanner = new window.TQTScanner(video, {
            repeatMs: opts.repeatMs || 3000,
            onCode: (text, meta) => {
                // v1.3.44: el QR del "Botón de escaneo" de la consola se reconoce desde CUALQUIER cámara (Recibir, Emparejar,
                // Programar, Consultar): se pasa directo al modo escáner vinculado, sin ir antes a "Escáner para la consola".
                const vinc = /\/escaner\?(?:[^#\s]*&)?s=([A-Za-z0-9_-]{10,})/.exec(String(text || ''));
                if (vinc && !opts.vinculo) {
                    scanner.lock(); el.dataset.state = 'locked';
                    if (window.TQT && window.TQT.toast) window.TQT.toast('QR de la consola: vinculando este celular…', { kind: 'ok' });
                    location.href = '/escaner?s=' + encodeURIComponent(vinc[1]);
                    return;
                }
                if (opts.onCode) opts.onCode(text, meta);
            },
            onState: (s) => {
                if (s === 'scanning' || s === 'ready') { clearFail(); el.dataset.state = 'scanning'; }
                else if (s === 'starting') el.dataset.state = 'idle';
                else if (s === 'stopped') el.dataset.state = 'idle';
                else if (s === 'error') el.dataset.state = 'error';
                if (s === 'ready' || s === 'scanning') {
                    btnTorch.hidden = !scanner.torchSupported;
                    btnFlip.hidden = scanner.cameras.length < 2;
                }
                refreshStatus();
            },
            onError: (info) => {
                clearFail();
                failPanel = h('div', { class: 'fail', role: 'alert' },
                    icon('camera'), h('b', null, info.title), h('p', null, info.message),
                    h('div', { class: 'row wrap', style: 'justify-content:center' },
                        info.type === 'INSECURE_CONTEXT' ? null : h('button', { class: 'btn btn-primary', type: 'button', onclick: () => scanner.start() }, icon('refresh'), 'Reintentar'),
                        opts.onManual ? h('button', { class: 'btn', type: 'button', onclick: opts.onManual }, icon('keyboard'), 'Teclear código') : null));
                el.appendChild(failPanel);
            },
        });

        function refreshStatus() {
            const audioReady = !window.SoundFX || window.SoundFX.state === 'running' || !window.SoundFX.enabled;
            if (el.dataset.state === 'error') { status.textContent = 'Cámara no disponible'; return; }
            if (!audioReady) { status.textContent = 'Toca aquí para activar el sonido'; status.style.cursor = 'pointer'; return; }
            status.style.cursor = 'default';
            status.textContent = el.dataset.state === 'locked' ? 'Procesando…' : (scanner.running ? 'Buscando código' : 'Iniciando cámara…');
        }
        status.addEventListener('click', () => { if (window.SoundFX) window.SoundFX.unlock().then(refreshStatus); });
        setInterval(refreshStatus, 1500);

        btnTorch.addEventListener('click', async () => {
            const on = await scanner.toggleTorch();
            btnTorch.setAttribute('aria-pressed', String(on));
        });
        btnFlip.addEventListener('click', () => scanner.nextCamera());
        btnSound.addEventListener('click', () => {
            const on = !(window.SoundFX && window.SoundFX.enabled);
            if (window.SoundFX) { window.SoundFX.enabled = on; if (on) { window.SoundFX.unlock(); window.SoundFX.playStep(); } }
            store.set('tqt.sonido', on ? '1' : '0');
            btnSound.setAttribute('aria-pressed', String(on));
            btnSound.replaceChildren(icon(on ? 'vol' : 'muted'));
            refreshStatus();
        });

        if (opts.autoStart !== false) scanner.start();

        return {
            el, scanner,
            start: () => scanner.start(),
            stop: () => scanner.stop(),
            lock() { scanner.lock(); el.dataset.state = 'locked'; refreshStatus(); },
            unlock() { scanner.unlock(); if (el.dataset.state === 'locked') el.dataset.state = 'scanning'; refreshStatus(); },
            flash: (k) => window.Haptics && window.Haptics.flash(k),
            forget: (t) => scanner.forget(t),
        };
    }

    window.TQT.mountVisor = mountVisor;
})();
