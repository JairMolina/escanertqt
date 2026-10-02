/**
 * scanner.js - Lector continuo de QR (incluye QR invertido: blanco sobre negro, como el grabado láser de las PCB).
 *
 * Decodificadores:
 *   1) BarcodeDetector nativo (Chrome/Android, Safari reciente) sobre el <video> directamente.
 *   2) jsQR local, dos pasadas (normal + píxeles invertidos) sobre fotogramas reducidos (fallback y refuerzo).
 * Modo continuo: la cámara nunca se pausa. Un código no se vuelve a emitir mientras siga en cuadro
 * ni durante `repeatMs` después de haber salido.
 * Requiere window.jsQR (js/jsQR.js).
 */
(function () {
    'use strict';

    const NATIVE_FORMATS = ['qr_code', 'data_matrix', 'code_128'];
    const MAX_SIDE = 640;        // lado máximo del fotograma que se le da a jsQR (más grande = más lento y menos fiable)
    const TICK_MS = 75;          // ~13 lecturas/s

    // ------------------------------------------------------------------ decodificación pura (también sirve para pruebas)
    // La opción 'attemptBoth' de jsQR 1.4 falla con imágenes grandes (>~700 px) y 'onlyInvert' lanza excepción.
    // Se lee en dos pasadas explícitas: imagen normal y píxeles invertidos a mano (QR blanco sobre negro).
    let invBuf = null;
    function jsqrSafe(data, w, h) {
        try {
            const r = window.jsQR(data, w, h, { inversionAttempts: 'dontInvert' });
            return r && r.data ? String(r.data).trim() : null;
        } catch (e) { return null; }
    }

    function decodeImageData(imageData) {
        if (!window.jsQR) return null;
        const { data, width, height } = imageData;
        let text = jsqrSafe(data, width, height);
        if (text) return text;
        if (!invBuf || invBuf.length !== data.length) invBuf = new Uint8ClampedArray(data.length);
        for (let i = 0; i < data.length; i += 4) {
            invBuf[i] = 255 - data[i]; invBuf[i + 1] = 255 - data[i + 1]; invBuf[i + 2] = 255 - data[i + 2]; invBuf[i + 3] = 255;
        }
        return jsqrSafe(invBuf, width, height);
    }

    /** Decodifica un canvas ya dibujado; prueba varios tamaños (máx. MAX_SIDE) para tolerar QR grandes o pequeños. */
    function decodeCanvas(canvas) {
        const base = Math.min(1, MAX_SIDE / Math.max(canvas.width, canvas.height));
        for (const f of [1, 0.75, 0.5]) {
            const s = base * f;
            const cv = document.createElement('canvas');
            cv.width = Math.max(64, Math.round(canvas.width * s));
            cv.height = Math.max(64, Math.round(canvas.height * s));
            const c2 = cv.getContext('2d', { willReadFrequently: true });
            c2.drawImage(canvas, 0, 0, cv.width, cv.height);
            const text = decodeImageData(c2.getImageData(0, 0, cv.width, cv.height));
            if (text) return text;
        }
        return null;
    }

    class TQTScanner {
        /**
         * @param {HTMLVideoElement} video
         * @param {{onCode:function(string,object), onError:function(object), onState:function(string),
         *          repeatMs?:number}} opts
         */
        constructor(video, opts = {}) {
            this.video = video;
            this.onCode = opts.onCode || (() => {});
            this.onError = opts.onError || (() => {});
            this.onState = opts.onState || (() => {});
            this.repeatMs = opts.repeatMs || 3000;

            this.stream = null;
            this.running = false;      // hay stream activo
            this.want = false;         // el llamador quiere que esté activo
            this.starting = false;
            this.locked = false;       // bloqueo lógico (no congela el video)
            this.torchOn = false;
            this.torchSupported = false;
            this.cameras = [];
            this.deviceId = null;
            this.seen = new Map();     // texto -> último instante en cuadro
            this.timer = null;
            this.busy = false;
            this.tick = 0;
            this.wakeLock = null;
            this.canvas = document.createElement('canvas');
            this.detector = null;
            this.lastDecodeMs = 0;

            try {
                if ('BarcodeDetector' in window) {
                    const make = (fmts) => { this.detector = new window.BarcodeDetector({ formats: fmts }); };
                    if (window.BarcodeDetector.getSupportedFormats) {
                        window.BarcodeDetector.getSupportedFormats().then((sup) => {
                            const f = NATIVE_FORMATS.filter((x) => sup.includes(x));
                            if (f.length) make(f);
                        }).catch(() => {});
                    } else {
                        make(['qr_code']);
                    }
                }
            } catch (e) { this.detector = null; }

            this._vis = () => this._onVisibility();
            document.addEventListener('visibilitychange', this._vis);
        }

        get engine() { return this.detector ? 'nativo+jsQR' : 'jsQR'; }

        // ---------------------------------------------------------------- ciclo de vida
        async start() {
            this.want = true;
            if (this.running || this.starting) return this.running;

            if (!window.isSecureContext || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
                this._fail({
                    type: 'INSECURE_CONTEXT', title: 'Falta la conexión segura (HTTPS)',
                    message: 'El navegador solo permite la cámara en páginas https://. Abre la dirección segura del servidor y acepta el aviso del certificado.',
                });
                return false;
            }
            this.starting = true;
            this.onState('starting');

            const saved = this.deviceId || readStore('tqt.camera');
            const attempts = [];
            if (saved) attempts.push({ deviceId: { exact: saved } });
            attempts.push({ facingMode: { exact: 'environment' } }, { facingMode: 'environment' }, {});

            let lastErr = null;
            for (const cam of attempts) {
                try {
                    this.stream = await navigator.mediaDevices.getUserMedia({
                        audio: false,
                        video: { ...cam, width: { ideal: 1280 }, height: { ideal: 720 } },
                    });
                    lastErr = null;
                    break;
                } catch (err) {
                    lastErr = err;
                    const kind = classify(err);
                    if (kind === 'PERMISSION_DENIED') break;
                    // La cámara elegida no abre (virtual, infrarroja, sin salida...): se olvida y se prueba la siguiente/la predeterminada.
                    if (cam.deviceId) { this.deviceId = null; writeStore('tqt.camera', ''); }
                }
            }
            this.starting = false;
            if (!this.stream) { this._fail(describe(lastErr)); return false; }

            this.video.setAttribute('playsinline', '');
            this.video.muted = true;
            this.video.srcObject = this.stream;
            try { await this.video.play(); } catch (e) { /* autoplay bloqueado: se reintenta con el primer toque */ }

            this.running = true;
            await this._afterStart();
            this._loop();
            this.onState('scanning');
            return true;
        }

        async stop() {
            this.want = false;
            this._halt();
        }

        _halt() {
            if (this.timer) { clearTimeout(this.timer); this.timer = null; }
            this._releaseWakeLock();
            if (this.stream) this.stream.getTracks().forEach((t) => { try { t.stop(); } catch (e) { /* ya parada */ } });
            this.stream = null;
            this.running = false;
            this.torchOn = false;
            try { this.video.srcObject = null; } catch (e) { /* nada */ }
            this.onState('stopped');
        }

        destroy() {
            document.removeEventListener('visibilitychange', this._vis);
            this.want = false;
            this._halt();
        }

        async restart() {
            this._halt();
            this.want = true;
            return this.start();
        }

        _onVisibility() {
            if (document.hidden) {
                if (this.running) this._halt();       // libera la cámara en segundo plano
            } else if (this.want && !this.running && !this.starting) {
                this.start();
            } else if (this.running) {
                this._requestWakeLock();
            }
        }

        lock() { this.locked = true; }
        unlock() { this.locked = false; }

        // ---------------------------------------------------------------- bucle de lectura
        _loop() {
            if (!this.running) return;
            this.timer = setTimeout(async () => {
                if (!this.running) return;
                if (!this.busy && !this.locked && this.video.readyState >= 2 && this.video.videoWidth) {
                    this.busy = true;
                    try { await this._scanFrame(); } catch (e) { /* fotograma perdido */ }
                    this.busy = false;
                }
                this._loop();
            }, TICK_MS);
        }

        async _scanFrame() {
            this.tick++;
            const t0 = performance.now();
            let text = null;

            if (this.detector) {
                try {
                    const found = await this.detector.detect(this.video);
                    if (found && found.length) text = String(found[0].rawValue || '').trim() || null;
                } catch (e) { /* detector no disponible en este fotograma */ }
            }
            // jsQR: siempre si no hay detector; con detector solo como refuerzo (1 de cada 2) para no gastar CPU.
            if (!text && window.jsQR && (!this.detector || this.tick % 2 === 0)) {
                const vw = this.video.videoWidth, vh = this.video.videoHeight;
                // recorte central (90 %) reducido a MAX_SIDE
                const cw = Math.round(vw * 0.9), ch = Math.round(vh * 0.9);
                const sx = Math.round((vw - cw) / 2), sy = Math.round((vh - ch) / 2);
                const k = Math.min(1, MAX_SIDE / Math.max(cw, ch));
                this.canvas.width = Math.round(cw * k);
                this.canvas.height = Math.round(ch * k);
                const ctx = this.canvas.getContext('2d', { willReadFrequently: true });
                ctx.drawImage(this.video, sx, sy, cw, ch, 0, 0, this.canvas.width, this.canvas.height);
                text = decodeImageData(ctx.getImageData(0, 0, this.canvas.width, this.canvas.height));
            }
            if (text) {
                this.lastDecodeMs = Math.round(performance.now() - t0);
                this._emit(text);
            }
        }

        _emit(text) {
            const now = performance.now();
            const prev = this.seen.get(text);
            this.seen.set(text, now);
            if (this.seen.size > 40) {
                for (const [k, ts] of this.seen) if (now - ts > 15000) this.seen.delete(k);
            }
            if (prev !== undefined && now - prev < this.repeatMs) return; // sigue en cuadro o acaba de salir
            this.onCode(text, { engine: this.engine, ms: this.lastDecodeMs });
        }

        /** Olvida lo visto (p. ej. tras un error que el operador quiere reintentar con el mismo código). */
        forget(text) { if (text === undefined) this.seen.clear(); else this.seen.delete(text); }

        // ---------------------------------------------------------------- cámaras y linterna
        async _afterStart() {
            const track = this._track();
            try {
                if (track) {
                    const s = track.getSettings ? track.getSettings() : {};
                    if (s.deviceId) this.deviceId = s.deviceId;
                    const caps = track.getCapabilities ? track.getCapabilities() : {};
                    this.torchSupported = !!caps.torch;
                    if (caps.focusMode && caps.focusMode.includes && caps.focusMode.includes('continuous')) {
                        await track.applyConstraints({ advanced: [{ focusMode: 'continuous' }] }).catch(() => {});
                    }
                }
            } catch (e) { /* capacidades opcionales */ }
            try {
                const devs = await navigator.mediaDevices.enumerateDevices();
                this.cameras = devs.filter((d) => d.kind === 'videoinput');
            } catch (e) { this.cameras = []; }
            this._requestWakeLock();
            this.onState('ready');
        }

        _track() { return this.stream && this.stream.getVideoTracks ? this.stream.getVideoTracks()[0] : null; }

        async nextCamera() {
            if (this.cameras.length < 2) return false;
            const i = this.cameras.findIndex((c) => c.deviceId === this.deviceId);
            const next = this.cameras[(i + 1) % this.cameras.length];
            this.deviceId = next.deviceId;
            writeStore('tqt.camera', next.deviceId);
            const ok = await this.restart();
            if (!ok) { this.deviceId = null; writeStore('tqt.camera', ''); await this.restart(); }   // vuelve a una cámara que sí funcione
            return ok;
        }

        async setTorch(on) {
            const track = this._track();
            if (!track || !this.torchSupported) return false;
            try {
                await track.applyConstraints({ advanced: [{ torch: !!on }] });
                this.torchOn = !!on;
            } catch (e) { this.torchOn = false; }
            return this.torchOn;
        }
        toggleTorch() { return this.setTorch(!this.torchOn); }

        // ---------------------------------------------------------------- pantalla encendida
        async _requestWakeLock() {
            try {
                if ('wakeLock' in navigator && !this.wakeLock && !document.hidden) {
                    this.wakeLock = await navigator.wakeLock.request('screen');
                    this.wakeLock.addEventListener('release', () => { this.wakeLock = null; });
                }
            } catch (e) { this.wakeLock = null; }
        }
        _releaseWakeLock() {
            try { if (this.wakeLock) this.wakeLock.release(); } catch (e) { /* nada */ }
            this.wakeLock = null;
        }

        _fail(info) {
            this.onError(info);
            this.onState('error');
        }
    }

    // ---------------------------------------------------------------- utilidades
    function readStore(k) { try { return localStorage.getItem(k) || ''; } catch (e) { return ''; } }
    function writeStore(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* modo privado */ } }

    function classify(err) {
        const s = String((err && (err.name || err.message)) || err || '');
        if (/NotAllowed|Permission|denied/i.test(s)) return 'PERMISSION_DENIED';
        if (/NotFound|DevicesNotFound/i.test(s)) return 'NO_CAMERA';
        if (/NotReadable|TrackStart|in use/i.test(s)) return 'CAMERA_IN_USE';
        if (/Overconstrained|Constraint/i.test(s)) return 'OVERCONSTRAINED';
        if (/Security/i.test(s)) return 'INSECURE_CONTEXT';
        return 'UNKNOWN';
    }

    function describe(err) {
        const type = classify(err);
        const map = {
            PERMISSION_DENIED: ['Falta el permiso de cámara', 'Activa la cámara para este sitio en los ajustes del navegador y vuelve a intentar.'],
            NO_CAMERA: ['No hay cámara disponible', 'Este equipo no tiene cámara. Puedes teclear el código a mano.'],
            CAMERA_IN_USE: ['La cámara está ocupada', 'Otra app o pestaña la está usando. Ciérrala y vuelve a intentar.'],
            OVERCONSTRAINED: ['Cámara no compatible', 'No se pudo abrir esa cámara. Elige otra con el botón de cambiar cámara.'],
            INSECURE_CONTEXT: ['Falta la conexión segura (HTTPS)', 'Abre la dirección https:// del servidor y acepta el aviso del certificado.'],
            UNKNOWN: ['No se pudo iniciar la cámara', 'Vuelve a intentar o teclea el código a mano.'],
        };
        const [title, message] = map[type];
        return { type, title, message, raw: String((err && (err.message || err.name)) || err || '') };
    }

    window.TQTScanner = TQTScanner;
    window.TQTScanner.decodeCanvas = decodeCanvas;
    window.TQTScanner.decodeImageData = decodeImageData;
})();
