/**
 * haptics.js - Feedback táctil y visual de respaldo.
 * navigator.vibrate no existe en iOS/Safari: el anillo de color alrededor del visor confirma siempre
 * (sin destellos a pantalla completa, apto para fotosensibilidad).
 */
class HapticsManager {
    constructor() {
        this.supported = 'vibrate' in navigator && typeof navigator.vibrate === 'function';
        this.enabled = true;
        this.target = null;
    }

    setTarget(el) { this.target = el; }

    vibrate(pattern) {
        if (!this.supported || !this.enabled) return false;
        // Chrome bloquea vibrate (y lo registra como error en consola) hasta que el usuario toque la página.
        if (navigator.userActivation && !navigator.userActivation.hasBeenActive) return false;
        try { return navigator.vibrate(pattern); } catch (e) { return false; }
    }

    /** kind: 'ok' | 'warn' | 'error' */
    flash(kind) {
        const el = this.target || document.querySelector('.visor');
        if (!el) return;
        const cls = kind === 'error' ? 'fx-err' : kind === 'warn' ? 'fx-warn' : 'fx-ok';
        el.classList.remove('fx-ok', 'fx-warn', 'fx-err');
        void el.offsetWidth; // reinicia la transición
        el.classList.add(cls);
        setTimeout(() => el.classList.remove(cls), 550);
    }

    scan() { this.vibrate(35); this.flash('ok'); }
    step() { this.vibrate(40); this.flash('ok'); }
    success() { this.vibrate(80); this.flash('ok'); }
    dup() { this.vibrate([30, 60, 30]); this.flash('warn'); }
    error() { this.vibrate([100, 50, 200]); this.flash('error'); }

    toggle() { this.enabled = !this.enabled; return this.enabled; }
}

window.Haptics = new HapticsManager();
