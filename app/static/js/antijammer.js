/* antijammer.js - Módulo Skudo AntiJammer: shell de 4 pestañas (Recibir · Programar · Consultar · Inventario) con hash (#recibir…).
 * En escritorio (≥1024px) es una consola con riel agrupado (Operación / Gestión) y Dashboard por defecto; en celular,
 * barra inferior con «Más» (Dashboard, Lotes, Movimientos, Excel).
 * Expone window.AJ para las vistas (antijammer_recibir.js, antijammer_programar.js, antijammer_consultar.js, antijammer_inventario.js):
 *   AJ.registrar(nombre, {montar(el), entrar(), salir()}) · AJ.cam.unir(slot, {onCode, onManual, pista}) · AJ.cam.apagar()
 *   AJ.resumen(forzar) · AJ.cambio() (avisa 'antijammer:cambio') · AJ.porCodigo(codigo) · AJ.soloLectura() · utilidades de formato.
 * Un solo visor de cámara (visor.js) se mueve a la pestaña activa y se apaga al salir de ella.
 * API: contrato /api/antijammer v1.4.28 (consultor solo GET). */
(function () {
    'use strict';
    const T = window.TQT;
    const { h, icon, api } = T;
    const $ = (id) => document.getElementById(id);
    const ROLES = { administrador: 'Administrador', general: 'General', consultor: 'Consulta' };
    const VISTAS = ['dashboard', 'recibir', 'programar', 'consultar', 'inventario', 'lotes', 'movimientos', 'materiales', 'costos', 'excel'];
    const MAS = { dashboard: 'Dashboard', lotes: 'Lotes', movimientos: 'Movimientos', materiales: 'Materiales', costos: 'Costos', excel: 'Excel' };   // en celular, dentro de «Más»
    const escritorio = () => matchMedia('(min-width: 1024px)').matches;

    // El tema lo fija el <head>; common.js lo pisa a "oscuro" si no hay ajuste guardado: se restablece la preferencia del sistema.
    (function () {
        let g = null; try { g = localStorage.getItem('tqt.tema'); } catch (e) { /* nada */ }
        T.applyTheme(g === 'light' || g === 'dark' ? g : (matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark'));
    })();
    T.hydrateIcons();

    // ------------------------------------------------------------------ utilidades compartidas
    const ESTADOS = {
        RECIBIDA: { txt: 'Recibida', k: 'info' },
        PROGRAMADA: { txt: 'Programada', k: 'ok' },
        FALLA: { txt: 'Falla', k: 'bad' },
        BAJA: { txt: 'Baja', k: '' },
    };
    const estadoBadge = (e) => { const x = ESTADOS[e] || { txt: e || '—', k: '' }; return T.badge(x.txt, x.k); };
    const hw = (v) => (v ? 'V' + v : '—');
    function fecha(s, conHora) {
        if (!s) return '—';
        const d = new Date(String(s).replace(' ', 'T'));
        if (isNaN(d)) return String(s);
        try {
            return d.toLocaleString('es-MX', conHora === false ? { day: 'numeric', month: 'short', year: 'numeric' } : { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
        } catch (e) { return String(s); }
    }
    /** Texto leído/tecleado → código para el servidor. Solo dígitos = serie de una V1. */
    function normal(texto) {
        let c = String(texto || '').replace(/[\r\n\t]+/g, ' ').trim().slice(0, 300);
        if (/^[0-9]{1,4}$/.test(c)) c = 'SJ-V1-' + c.padStart(4, '0');
        return c;
    }
    const sonar = {
        ok: () => { if (window.SoundFX) window.SoundFX.playScan('R2'); if (window.Haptics) window.Haptics.scan(); },
        dup: () => { if (window.SoundFX) window.SoundFX.playDup(); if (window.Haptics) window.Haptics.dup(); },
        mal: () => { if (window.SoundFX) window.SoundFX.playError(); if (window.Haptics) window.Haptics.error(); },
    };

    let resumenP = null;   // /resumen (v1.4.28b: también actividad 14 días y últimos eventos)
    function resumen(forzar) {
        if (!resumenP || forzar) {
            resumenP = api('/api/antijammer/resumen').then((r) => {
                if (!r.ok) { resumenP = null; return null; }
                pintaListas(r.data);
                return r.data;
            });
        }
        return resumenP;
    }
    /** Datalists de lotes y firmwares (sugerencias en los campos). */
    function pintaListas(d) {
        if (!d) return;
        $('dlLotes').replaceChildren(...(d.lotes || []).filter((x) => x.lote).map((x) => h('option', { value: x.lote })));
        $('dlFirmwares').replaceChildren(...(d.firmwares || []).filter((x) => x.firmware).map((x) => h('option', { value: x.firmware })));
    }
    /** Algo cambió en el servidor: se recalcula el resumen y se avisa a las vistas. */
    function cambio() { resumen(true); document.dispatchEvent(new CustomEvent('antijammer:cambio')); }

    async function porCodigo(codigo) {
        return api('/api/antijammer/pcb/por-codigo?codigo=' + encodeURIComponent(codigo));
    }

    // Bloque de error con salida (reintentar y, si se da, otra acción).
    function error(msg, reintentar, extra) {
        return T.banner('bad', 'alert', h('p', { class: 'ban-t' }, msg),
            h('div', { class: 'ban-acc' },
                reintentar ? h('button', { class: 'btn btn-sm', type: 'button', onclick: reintentar }, icon('refresh'), 'Reintentar') : null,
                extra || null));
    }

    // ------------------------------------------------------------------ usuario y rol
    let rol = null;
    const soloLectura = () => rol === 'consultor';
    const yoP = api('/api/auth/yo').then((r) => {
        if (!r.ok || !r.data) return null;
        rol = r.data.rol || null;
        document.documentElement.dataset.rol = rol || '';
        $('uMail').textContent = r.data.email || '';
        $('uRol').textContent = ROLES[rol] || rol || '';
        $('usuario').hidden = !r.data.email;
        document.querySelectorAll('.solo-lectura').forEach((p) => { p.hidden = !soloLectura(); });
        return rol;
    });

    // ------------------------------------------------------------------ cabecera
    function pintaTema() { $('bTema').replaceChildren(icon(T.currentTheme() === 'light' ? 'moon' : 'sun')); }
    $('bTema').addEventListener('click', () => { T.toggleTheme(); pintaTema(); });
    pintaTema();
    $('bSalir').addEventListener('click', () => { cam.apagar(); T.cerrarSesion(); });

    // ------------------------------------------------------------------ cámara compartida
    const cam = (function () {
        const caja = $('camara'), marco = $('marcoCam'), bCam = $('bCam');
        let manejador = null, visor = null;
        function pintaBoton(on) {
            marco.dataset.cam = on ? 'on' : 'off';
            bCam.setAttribute('aria-pressed', String(on));
            $('bCamT').textContent = on ? 'Detener cámara' : 'Iniciar cámara';
            const ic = bCam.querySelector('.svg-i'); if (ic) ic.replaceWith(icon(on ? 'x' : 'camera'));
        }
        function asegurar() {
            if (visor) return visor;
            visor = T.mountVisor($('camHost'), {
                autoStart: false, vinculo: true, repeatMs: 2500,
                onManual: () => { apagar(); if (manejador && manejador.onManual) manejador.onManual(); },
                onCode: (texto) => { if (manejador && manejador.onCode) manejador.onCode(texto); },
            });
            return visor;
        }
        async function encender() {
            if (window.SoundFX) window.SoundFX.unlock();   // el toque del usuario habilita el audio del navegador
            pintaBoton(true);
            await asegurar().start();
        }
        function apagar() { if (visor) visor.stop(); pintaBoton(false); }
        bCam.addEventListener('click', () => { if (marco.dataset.cam === 'on') apagar(); else encender(); });
        window.addEventListener('pagehide', apagar);
        document.addEventListener('visibilitychange', () => { if (document.hidden) apagar(); });
        return {
            /** Lleva el visor a `slot` (contenedor de la vista) y dirige las lecturas a `opts`. */
            unir(slot, opts) {
                manejador = opts || null;
                if (slot && caja.parentNode !== slot) slot.appendChild(caja);
                $('camPista').textContent = (opts && opts.pista) || 'Apunta al código QR de la placa.';
                asegurar();
            },
            soltar() { apagar(); manejador = null; },
            apagar,
            olvidar(t) { if (visor) visor.forget(t); },
            bloquear() { if (visor) visor.lock(); },
            liberar() { if (visor) visor.unlock(); },
            destello(k) { if (visor) visor.flash(k); },
        };
    })();

    // ------------------------------------------------------------------ pestañas
    const vistas = {};
    let actual = null;
    function registrar(nombre, def) { vistas[nombre] = { def, montada: false }; }

    function ir(nombre, enfocar) {
        if (!VISTAS.includes(nombre)) nombre = escritorio() ? 'dashboard' : (soloLectura() ? 'consultar' : 'recibir');
        if (actual === nombre) return;
        const previa = actual && vistas[actual];
        if (previa && previa.def.salir) { try { previa.def.salir(); } catch (e) { console.error(e); } }
        cam.soltar();
        actual = nombre;
        VISTAS.forEach((v) => { $('v-' + v).hidden = v !== nombre; });
        document.querySelectorAll('#pestanas a').forEach((a) => {
            if (a.dataset.tab === nombre) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
        });
        $('bMas').classList.toggle('activa', !!MAS[nombre]);
        $('bMas').querySelector('span').textContent = MAS[nombre] || 'Más';
        const sec = $('v-' + nombre), v = vistas[nombre];
        if (v) {
            if (!v.montada) { v.montada = true; try { v.def.montar(sec); } catch (e) { console.error(e); } }
            if (v.def.entrar) { try { v.def.entrar(); } catch (e) { console.error(e); } }
        }
        if (enfocar) { const t = sec.querySelector('h1'); if (t) t.focus({ preventScroll: true }); window.scrollTo(0, 0); }
        document.dispatchEvent(new CustomEvent('antijammer:vista', { detail: nombre }));   // v1.4.30: el botón de escaneo avisa al celular
    }
    // «Más» (celular): hoja con las secciones de consola que no caben en la barra
    $('bMas').addEventListener('click', () => {
        let hoja = null;
        const enlaces = Object.keys(MAS).map((k) => h('a', {
            class: 'mas-op', href: '#' + k, 'aria-current': actual === k ? 'page' : null,
            onclick: () => { if (hoja) hoja.close(); },
        }, icon({ dashboard: 'dash', lotes: 'layers', movimientos: 'clock', materiales: 'box', costos: 'tag', excel: 'excel' }[k]), h('span', null, MAS[k])));
        hoja = T.sheet({ title: 'Más secciones', body: h('nav', { class: 'mas-lista', 'aria-label': 'Más secciones' }, enlaces) });
    });
    function desdeHash(enfocar) { ir((location.hash || '').replace(/^#/, '').split('?')[0], enfocar); }
    window.addEventListener('hashchange', () => desdeHash(true));
    /** Navegar a otra vista con un dato (p. ej. abrir una placa en Consultar). */
    function abrir(nombre, dato) {
        const v = vistas[nombre];
        if (location.hash !== '#' + nombre) history.pushState(null, '', '#' + nombre);   // pushState no dispara hashchange
        ir(nombre, true);
        if (v && v.def.recibirDato) v.def.recibirDato(dato);
    }
    /** v1.4.30: lectura del celular vinculado → la vista abierta (`escaneo(codigo)` → {ok, texto}); si no la maneja
     *  (o es Recibir con rol de consulta), se abre en Consultar. */
    function escaneo(codigo) {
        let v = vistas[actual];
        if (!v || !v.def.escaneo || (actual === 'recibir' && soloLectura())) { abrir('consultar'); v = vistas.consultar; }
        return v && v.def.escaneo ? v.def.escaneo(codigo) : null;
    }

    /** Código de otro producto (Escáner TQT, TPMS, SpeedLocker o Skudo Sigfox) → mensaje de rechazo; '' si puede ser de Skudo AntiJammer.
     *  El servidor también lo rechaza; esto solo da un aviso claro sin esperar la red. */
    function ajeno(codigo) {
        const c = String(codigo || '').trim();
        if (!c || (T.esAntijammer && T.esAntijammer(c))) return '';
        if (T.esSigfox && T.esSigfox(c)) return `${c} es una placa Skudo Sigfox: regístrala en el módulo Skudo Sigfox, no en Skudo AntiJammer.`;   // v1.4.33
        if (T.esSpeedlocker && T.esSpeedlocker(c)) return `${c} es una placa SpeedLocker: regístrala en el módulo SpeedLocker, no en Skudo AntiJammer.`;   // v1.4.32
        if (T.esTpms && T.esTpms(c)) return `${c} es una placa TPMS: regístrala en el módulo TPMS, no en Skudo AntiJammer.`;
        if (T.parseNombre && T.parseNombre(c)) return `${c} es una tarjeta de Escáner TQT: regístrala en Escáner TQT, no en Skudo AntiJammer.`;
        return '';
    }

    window.AJ = {
        registrar, ir, abrir, cam, escaneo, actual: () => actual, resumen, cambio, porCodigo, soloLectura, yo: yoP,
        ESTADOS, estadoBadge, hw, fecha, normal, sonar, error, ajeno,
    };

    // Las vistas se registran en sus scripts (cargados después); al terminar el documento se elige la pestaña.
    document.addEventListener('DOMContentLoaded', async () => {
        resumen();
        if (!location.hash) { await Promise.race([yoP, new Promise((r) => setTimeout(r, 1200))]); }
        desdeHash(false);
    });
})();
