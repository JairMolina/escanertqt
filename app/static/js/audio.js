/**
 * audio.js - Motor de Audio Feedback Sin Latencia para Escaner TQT
 * Utiliza Web Audio API con osciladores nativos.
 * Latencia < 15ms, 100% offline, sin archivos de audio externos.
 */

class AudioManager {
    constructor() {
        this.ctx = null;
        this.isUnlocked = false;
        this.enabled = true;
        this._initListeners();
    }

    /**
     * Inicializa o resume el AudioContext tras la primera interacción del operador
     * (requerido por las políticas de autoplay de iOS Safari y Chrome Android).
     */
    _initContext() {
        if (!this.ctx) {
            const AudioContextClass = window.AudioContext || window.webkitAudioContext;
            if (AudioContextClass) {
                this.ctx = new AudioContextClass();
            }
        }
        if (this.ctx && this.ctx.state === 'suspended') {
            this.ctx.resume().catch(() => {});
        }
    }

    _initListeners() {
        // iOS Safari solo libera el audio dentro de un gesto del usuario: se reproduce un buffer
        // vacío en el primer toque para "armar" el AudioContext y se re-arma si vuelve a suspenderse.
        const unlock = () => {
            if (this.ctx && this.ctx.state === 'running') { this.isUnlocked = true; return; }   // se re-arma solo si vuelve a suspenderse
            this._initContext();
            if (this.ctx) {
                try {
                    const src = this.ctx.createBufferSource();
                    src.buffer = this.ctx.createBuffer(1, 1, 22050);
                    src.connect(this.ctx.destination);
                    src.start(0);
                } catch (e) { /* no crítico */ }
                if (this.ctx.state === 'running') this.isUnlocked = true;
            }
        };

        ['pointerdown', 'touchstart', 'touchend', 'click', 'keydown'].forEach((ev) => {
            window.addEventListener(ev, unlock, { capture: true, passive: true });
        });
        document.addEventListener('visibilitychange', () => {
            if (!document.hidden && this.ctx && this.ctx.state !== 'running') this.ctx.resume().catch(() => {});
        });
    }

    /**
     * Forzar desbloqueo programático
     */
    unlock() {
        this._initContext();
        if (this.ctx && this.ctx.state === 'suspended') {
            return this.ctx.resume();
        }
        return Promise.resolve();
    }

    /** Estado real del audio: 'running' cuando ya se puede sonar (en iOS solo tras un toque). */
    get state() { return this.ctx ? this.ctx.state : 'none'; }

    /** Ejecuta fn cuando el contexto corre: ya, o tras resume() (un contexto suspendido tiene el reloj congelado y el sonido se pierde). */
    _go(fn) {
        if (!this.enabled) return;
        this._initContext();
        if (!this.ctx) return;
        const run = () => { try { fn(); } catch (e) { /* audio no crítico */ } };
        if (this.ctx.state === 'running') { run(); return; }
        Promise.race([this.ctx.resume(), new Promise((r) => setTimeout(r, 400))]).then(() => { if (this.ctx.state === 'running') run(); }).catch(() => {});
    }

    _tone(freq, start, dur, type = 'triangle', vol = 0.3) {
        const now = this.ctx.currentTime + start;
        const osc = this.ctx.createOscillator();
        const gain = this.ctx.createGain();
        osc.type = type;
        osc.frequency.setValueAtTime(freq, now);
        gain.gain.setValueAtTime(0.0001, now);
        gain.gain.exponentialRampToValueAtTime(vol, now + 0.008);
        gain.gain.exponentialRampToValueAtTime(0.0001, now + dur);
        osc.connect(gain); gain.connect(this.ctx.destination);
        osc.start(now); osc.stop(now + dur + 0.02);
    }

    /**
     * Pitido de lectura por tipo de PCB: el operador sabe qué leyó la cámara sin mirar.
     * R1 grave (G5→D6), R2 medio (B5→F#6), R3 agudo (D6→A6): mismas quintas, distinta altura.
     */
    playScan(tipo) {
        if (!this.enabled) return;
        this._initContext();
        if (!this.ctx) return;
        const pairs = { R1: [784, 1174.7], R2: [987.8, 1480], R3: [1174.7, 1760] };
        const [a, b] = pairs[tipo] || pairs.R1;
        try { this._tone(a, 0, 0.07, 'triangle', 0.32); this._tone(b, 0.065, 0.13, 'sine', 0.34); } catch (e) { /* audio no crítico */ }
    }

    /** "Ya registrada": un toque grave y corto, distinto del error. */
    playDup() {
        if (!this.enabled) return;
        this._initContext();
        if (!this.ctx) return;
        try { this._tone(415, 0, 0.09, 'square', 0.14); this._tone(415, 0.13, 0.09, 'square', 0.14); } catch (e) { /* no crítico */ }
    }

    /**
     * Tono corto de paso intermedio (pip limpio a 700Hz)
     */
    playStep() {
        if (!this.enabled) return;
        this._initContext();
        if (!this.ctx) return;

        try {
            const now = this.ctx.currentTime;
            const osc = this.ctx.createOscillator();
            const gain = this.ctx.createGain();

            osc.type = 'sine';
            osc.frequency.setValueAtTime(720, now);
            osc.frequency.exponentialRampToValueAtTime(880, now + 0.05);

            gain.gain.setValueAtTime(0.25, now);
            gain.gain.exponentialRampToValueAtTime(0.001, now + 0.07);

            osc.connect(gain);
            gain.connect(this.ctx.destination);

            osc.start(now);
            osc.stop(now + 0.07);
        } catch (e) {
            console.warn('[Audio] Error al reproducir step:', e);
        }
    }

    /**
     * Tono de éxito de doble frecuencia armónica aguda y brillante (880Hz -> 1320Hz)
     * Latencia < 20 ms
     */
    playSuccess() {
        if (!this.enabled) return;
        this._initContext();
        if (!this.ctx) return;

        try {
            const now = this.ctx.currentTime;
            
            // Primer tono (880 Hz - La 5)
            const osc1 = this.ctx.createOscillator();
            const gain1 = this.ctx.createGain();
            osc1.type = 'triangle';
            osc1.frequency.setValueAtTime(880, now);

            gain1.gain.setValueAtTime(0.3, now);
            gain1.gain.exponentialRampToValueAtTime(0.01, now + 0.09);

            osc1.connect(gain1);
            gain1.connect(this.ctx.destination);
            osc1.start(now);
            osc1.stop(now + 0.09);

            // Segundo tono (1320 Hz - Mi 6) con ligero delay
            const osc2 = this.ctx.createOscillator();
            const gain2 = this.ctx.createGain();
            osc2.type = 'sine';
            osc2.frequency.setValueAtTime(1320, now + 0.08);

            gain2.gain.setValueAtTime(0.001, now);
            gain2.gain.setValueAtTime(0.35, now + 0.08);
            gain2.gain.exponentialRampToValueAtTime(0.001, now + 0.22);

            osc2.connect(gain2);
            gain2.connect(this.ctx.destination);
            osc2.start(now + 0.08);
            osc2.stop(now + 0.22);
        } catch (e) {
            console.warn('[Audio] Error al reproducir éxito:', e);
        }
    }

    /**
     * Fanfarria triunfal de tarjeta emparejada por completo (Arpegio C6 -> E6 -> G6 -> C7)
     */
    playComplete() {
        if (!this.enabled) return;
        this._initContext();
        if (!this.ctx) return;

        try {
            const notes = [
                { f: 1046.50, t: 0.00, d: 0.08 }, // C6
                { f: 1318.51, t: 0.07, d: 0.08 }, // E6
                { f: 1567.98, t: 0.14, d: 0.09 }, // G6
                { f: 2093.00, t: 0.21, d: 0.25 }, // C7
            ];

            const now = this.ctx.currentTime;
            notes.forEach(note => {
                const osc = this.ctx.createOscillator();
                const gain = this.ctx.createGain();

                osc.type = 'triangle';
                osc.frequency.setValueAtTime(note.f, now + note.t);

                gain.gain.setValueAtTime(0.001, now);
                gain.gain.setValueAtTime(0.3, now + note.t);
                gain.gain.exponentialRampToValueAtTime(0.001, now + note.t + note.d);

                osc.connect(gain);
                gain.connect(this.ctx.destination);

                osc.start(now + note.t);
                osc.stop(now + note.t + note.d);
            });
        } catch (e) {
            console.warn('[Audio] Error al reproducir complete:', e);
        }
    }

    /**
     * Tono grave descendente y disonante de error / advertencia (320Hz -> 130Hz)
     * Utiliza onda 'sawtooth' para sonar claro e inconfundible en ambiente de taller.
     */
    playError() {
        if (!this.enabled) return;
        this._initContext();
        if (!this.ctx) return;

        try {
            const now = this.ctx.currentTime;
            
            // Oscilador 1: tono descendente áspero
            const osc1 = this.ctx.createOscillator();
            const gain1 = this.ctx.createGain();
            osc1.type = 'sawtooth';
            osc1.frequency.setValueAtTime(320, now);
            osc1.frequency.linearRampToValueAtTime(140, now + 0.28);

            gain1.gain.setValueAtTime(0.35, now);
            gain1.gain.exponentialRampToValueAtTime(0.01, now + 0.30);

            // Oscilador 2: disonancia armónica para llamar la atención del operador
            const osc2 = this.ctx.createOscillator();
            const gain2 = this.ctx.createGain();
            osc2.type = 'square';
            osc2.frequency.setValueAtTime(295, now);
            osc2.frequency.linearRampToValueAtTime(125, now + 0.28);

            gain2.gain.setValueAtTime(0.18, now);
            gain2.gain.exponentialRampToValueAtTime(0.01, now + 0.30);

            osc1.connect(gain1);
            gain1.connect(this.ctx.destination);
            osc2.connect(gain2);
            gain2.connect(this.ctx.destination);

            osc1.start(now);
            osc1.stop(now + 0.30);
            osc2.start(now);
            osc2.stop(now + 0.30);
        } catch (e) {
            console.warn('[Audio] Error al reproducir error:', e);
        }
    }

    /**
     * Campanilla suave para notificación en Monitor de escritorio
     */
    playChime() {
        if (!this.enabled) return;
        this._initContext();
        if (!this.ctx) return;

        try {
            const now = this.ctx.currentTime;
            const osc = this.ctx.createOscillator();
            const gain = this.ctx.createGain();

            osc.type = 'sine';
            osc.frequency.setValueAtTime(1174.66, now); // D6
            osc.frequency.exponentialRampToValueAtTime(1760.00, now + 0.12); // A6

            gain.gain.setValueAtTime(0.2, now);
            gain.gain.exponentialRampToValueAtTime(0.001, now + 0.35);

            osc.connect(gain);
            gain.connect(this.ctx.destination);

            osc.start(now);
            osc.stop(now + 0.35);
        } catch (e) {
            console.warn('[Audio] Error al reproducir chime:', e);
        }
    }

    toggle() {
        this.enabled = !this.enabled;
        return this.enabled;
    }
}

// Todos los sonidos pasan por _go: si el audio estaba suspendido esperan al resume en vez de perderse.
['playScan', 'playDup', 'playStep', 'playSuccess', 'playComplete', 'playError', 'playChime'].forEach((n) => {
    const orig = AudioManager.prototype[n];
    AudioManager.prototype[n] = function (...a) { this._go(() => orig.apply(this, a)); };
});

// Instancia global
window.SoundFX = new AudioManager();
