/* speedlocker_recibir.js - Pestaña Recibir: alta de placas SpeedLocker por QR, lector USB o serie tecleada (POST /api/speedlocker/escanear).
 * Lote por dispositivo (localStorage), contador de recibidas hoy (GET /api/speedlocker/resumen → hoy) e historial de la sesión
 * (sessionStorage, se borra al cerrar sesión). */
(function () {
    'use strict';
    const T = window.TQT, P = window.SL;
    const { h, icon, api } = T;
    const $ = (id) => document.getElementById(id);
    const CLAVE = 'tqt.speedlocker.historial', CLAVE_LOTE = 'tqt.speedlocker.lote', MAX = 12;
    const ORIGEN = { camara: 'Cámara', manual: 'Escrito a mano', remoto: 'Celular vinculado' };
    const RES = { AGREGADA: ['ok', 'registrada'], REPETIDA: ['warn', 'ya estaba registrada'], INVALIDA: ['bad', ''] };
    let sec = null;

    function leeHist() {
        try { const a = JSON.parse(sessionStorage.getItem(CLAVE) || '[]'); return Array.isArray(a) ? a.slice(0, MAX) : []; } catch (e) { return []; }
    }
    function guardaHist() { try { sessionStorage.setItem(CLAVE, JSON.stringify(hist)); } catch (e) { /* modo privado: queda en memoria */ } }
    let hist = leeHist();
    const fmtHora = (ms) => { try { return new Date(ms).toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit', second: '2-digit' }); } catch (e) { return ''; } };

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
        $('hLista').replaceChildren(...hist.map((x) => h('li', null,
            h('div', { class: 'dato' },
                h('span', { class: 'cod', title: x.codigo }, x.codigo),
                h('span', { class: 'meta' }, fmtHora(x.t) + ' · ' + (ORIGEN[x.origen] || ''),
                    x.veces > 1 ? h('span', { class: 'veces' }, ` · ×${x.veces}`) : null)),
            h('button', { class: 'iconbtn', type: 'button', 'aria-label': 'Copiar ' + x.codigo, title: 'Copiar código', onclick: () => copiar(x.codigo) }, icon('paste')))));
        $('hVacio').hidden = hist.length > 0;
        $('bVaciar').hidden = hist.length === 0;
        $('hCuenta').textContent = hist.length ? `(${hist.length})` : '';
    }
    async function pintaHoy() {
        const d = await P.resumen();
        $('rHoyN').textContent = d && typeof d.hoy === 'number' ? String(d.hoy) : '–';
        $('rHoy').title = d ? '' : 'No se pudo leer el conteo del servidor';
    }

    function pintaEstado(k, txt) { const e = $('uEstado'); e.hidden = !txt; e.dataset.k = k; e.textContent = txt; }

    async function darDeAlta(codigo) {
        if (P.soloLectura()) { pintaEstado('bad', 'Tu rol es de consulta: no puedes registrar placas.'); return { ok: false, texto: 'Rol de consulta: no puede registrar placas' }; }
        const otro = P.ajeno(codigo);
        if (otro) { pintaEstado('bad', otro); P.sonar.mal(); return { ok: false, texto: otro }; }
        pintaEstado('', 'Registrando…');
        const r = await api('/api/speedlocker/escanear', { method: 'POST', body: { codigo, lote: $('loteSl').value.trim() } });
        const vigente = !hist[0] || hist[0].codigo === codigo;   // si ya llegó otra lectura, no se pinta esta
        if (!r.ok) {
            const msg = (r.error || 'No se pudo registrar.') + ' Revisa la conexión y vuelve a leer el código.';
            if (vigente) { pintaEstado('bad', msg); P.sonar.mal(); }
            return { ok: false, texto: msg };
        }
        const d = r.data || {}, [k, txt] = RES[d.resultado] || ['bad', ''];
        const texto = d.pcb ? `${d.pcb.nombre} · ${txt}${d.pcb.lote ? ' · lote ' + d.pcb.lote : ''}` : (d.mensaje || 'Código no válido');
        if (vigente) { pintaEstado(k, texto); if (k === 'bad') P.sonar.mal(); }
        if (d.resultado === 'AGREGADA') { P.cambio(); }
        return { ok: k !== 'bad', texto };
    }

    /** Registra una lectura: si ya estaba, sube al inicio y cuenta otra vez (aviso de repetido). */
    function registrar(texto, origen) {
        const codigo = origen === 'manual' ? P.normal(texto) : String(texto || '').replace(/[\r\n\t]+/g, ' ').trim().slice(0, 300);
        if (!codigo) return false;
        const i = hist.findIndex((x) => x.codigo === codigo);
        const previo = i >= 0 ? hist.splice(i, 1)[0] : null;
        hist.unshift({ codigo, origen, t: Date.now(), veces: previo ? (previo.veces || 1) + 1 : 1 });
        hist = hist.slice(0, MAX);
        guardaHist();
        pintaUltimo(true); pintaLista();
        if (previo) P.sonar.dup(); else P.sonar.ok();
        return darDeAlta(codigo);   // promesa {ok, texto} (la usa el botón de escaneo)
    }

    P.registrar('recibir', {
        montar(el) {
            sec = el;
            const inLote = $('loteSl');
            try { inLote.value = localStorage.getItem(CLAVE_LOTE) || ''; } catch (e) { /* nada */ }
            inLote.addEventListener('change', () => { try { localStorage.setItem(CLAVE_LOTE, inLote.value.trim()); } catch (e) { /* nada */ } });
            $('bCopiar').addEventListener('click', () => { if (hist[0]) copiar(hist[0].codigo); });
            $('bVaciar').addEventListener('click', () => {
                hist = []; guardaHist(); pintaUltimo(false); pintaLista(); pintaEstado('', '');
                P.cam.olvidar();
                T.toast('Lecturas borradas de este dispositivo');
            });
            $('fManual').addEventListener('submit', (e) => {
                e.preventDefault();
                const inp = $('manCod');
                if (!inp.value.trim()) { inp.focus(); T.toast('Escribe el código o la serie de la placa', { kind: 'warn' }); return; }
                if (registrar(inp.value, 'manual')) { inp.value = ''; inp.focus(); }
            });
            document.addEventListener('speedlocker:cambio', () => { if (!sec.hidden) pintaHoy(); });
            pintaUltimo(false); pintaLista();
        },
        entrar() {
            P.cam.unir(sec.querySelector('.cam-slot'), {
                pista: 'Apunta al código QR de la placa para registrarla.',
                onCode: (t) => registrar(t, 'camara'),
                onManual: () => $('manCod').focus(),
            });
            pintaHoy();
        },
        /** v1.4.30: lectura del celular vinculado (botón de escaneo). */
        escaneo(texto) { return registrar(texto, 'remoto') || { ok: false, texto: 'Código vacío' }; },
    });
})();
