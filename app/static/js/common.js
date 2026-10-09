(function () {
    // Sesión de usuario caducada o cerrada en otro equipo: cualquier respuesta 401 marcada por el servidor lleva al login.
    const _fetch = window.fetch.bind(window);
    window.fetch = async function (...a) {
        const r = await _fetch(...a);
        if (r.status === 401 && r.headers.get('X-Auth') === 'login' && location.pathname !== '/login') {
            location.href = '/login?next=' + encodeURIComponent(location.pathname + location.search + location.hash);
        }
        return r;
    };
})();
/**
 * common.js - Base compartida de todas las pantallas (window.TQT)
 * Escapado, almacenamiento seguro, cliente REST, parsers (nombre de PCB y MAC), vocabulario de calidad,
 * iconos SVG propios, hojas inferiores, avisos, tema claro/oscuro y el armazón común (cabecera + pestañas).
 * Sin dependencias externas.
 */
(function () {
    'use strict';

    const MESES = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto',
        'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'];

    // ---------------------------------------------------------------- seguridad y DOM
    const ESC_MAP = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
    function esc(v) { return String(v === null || v === undefined ? '' : v).replace(/[&<>"']/g, (c) => ESC_MAP[c]); }

    /** h('div', {class:'x', onclick:fn, dataset:{a:1}}, 'texto', nodo, [hijos]) — todo texto entra como textContent. */
    function h(tag, attrs, ...kids) {
        const el = document.createElement(tag);
        if (attrs) {
            for (const [k, v] of Object.entries(attrs)) {
                if (v === null || v === undefined || v === false) continue;
                if (k === 'class') el.className = v;
                else if (k === 'dataset') Object.assign(el.dataset, v);
                else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
                else if (k === 'text') el.textContent = v;
                else if (v === true) el.setAttribute(k, '');
                else el.setAttribute(k, String(v));
            }
        }
        const add = (c) => {
            if (c === null || c === undefined || c === false) return;
            if (Array.isArray(c)) c.forEach(add);
            else if (c instanceof Node) el.appendChild(c);
            else el.appendChild(document.createTextNode(String(c)));
        };
        kids.forEach(add);
        return el;
    }

    const store = {
        get(key, fallback = null) { try { const v = localStorage.getItem(key); return v === null ? fallback : v; } catch (e) { return fallback; } },
        set(key, value) { try { localStorage.setItem(key, value); } catch (e) { /* modo privado */ } },
        getJSON(key, fallback = null) { try { const v = sessionStorage.getItem(key); return v ? JSON.parse(v) : fallback; } catch (e) { return fallback; } },
        setJSON(key, value) {
            try { if (value === null) sessionStorage.removeItem(key); else sessionStorage.setItem(key, JSON.stringify(value)); } catch (e) { /* ignorar */ }
        },
    };

    // ---------------------------------------------------------------- REST
    function detailText(d) {
        if (!d) return '';
        if (typeof d === 'string') return d;
        if (Array.isArray(d)) return d.map((x) => (x && x.msg) || JSON.stringify(x)).join('; ');
        return JSON.stringify(d);
    }

    // Marca anónima de este equipo (sin cuentas): el servidor separa con ella el lote de recepción de cada persona.
    const clienteId = (() => {
        try {
            let v = localStorage.getItem('tqt.cliente');
            if (!v) { v = (crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2) + Date.now().toString(36)).replace(/[^A-Za-z0-9]/g, '').slice(0, 32); localStorage.setItem('tqt.cliente', v); }
            return v;
        } catch (e) { return Math.random().toString(36).slice(2, 14); }   // sin almacenamiento: marca solo de esta carga de página
    })();

    /** api(path,{method,body,timeout}) -> {ok,status,data,network,error}. Nunca lanza. */
    async function api(path, opts = {}) {
        const ctrl = new AbortController();
        const timer = setTimeout(() => ctrl.abort(), opts.timeout || 8000);
        try {
            const res = await fetch(path, {
                method: opts.method || 'GET',
                headers: opts.body !== undefined ? { 'Content-Type': 'application/json', 'X-Cliente': clienteId } : { 'X-Cliente': clienteId },
                body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
                signal: ctrl.signal,
            });
            let data = null;
            try { data = await res.json(); } catch (e) { data = null; }
            // Sesión de supervisor caducada en el monitor: volver a pedir la contraseña (después regresa aquí)
            if (res.status === 401 && location.pathname === '/monitor') { location.href = '/admin?next=/monitor'; }
            return { ok: res.ok, status: res.status, data, network: false, error: res.ok ? '' : (detailText(data && data.detail) || `Error ${res.status}`) };
        } catch (e) {
            return { ok: false, status: 0, data: null, network: true, error: 'Sin conexión con el servidor' };
        } finally {
            clearTimeout(timer);
        }
    }

    // ---------------------------------------------------------------- parsers (espejo del backend)
    const NOMBRE_RE = /TQT[\s_-]*R([123])[\s_-]*V([0-9]{1,3}(?:[._][0-9](?=[\s_-]))?)(?:[\s_-]+[A-Za-z][A-Za-z0-9]*)*[\s_-]+([0-9]{1,4})(?![0-9])/i;  // igual que el servidor (v1.3.46: acepta 'PCB_TQT_R3_V2_0_TIMER_0073' → V20)
    const VERSION_DEFAULT = '30';

    /** {tipo:'R3', version:'30', serie:'0084', nombre:'TQT-R3-V30-0084'} o null. */
    function parseNombre(raw) {
        const m = NOMBRE_RE.exec(String(raw || ''));
        if (!m) return null;
        if (!Number(m[2].replace(/\D/g, '')) || !Number(m[3])) return null;   // versión 0 o serie 0000 no existen
        const serie = m[3].padStart(4, '0'), version = String(Number(m[2].replace(/\D/g, '')));   // V030 == V30 · V2_0 == V20
        return { tipo: 'R' + m[1], version, serie, nombre: `TQT-R${m[1]}-V${version}-${serie}` };
    }
    const nombreDe = (tipo, version, serie) => `TQT-${tipo}-V${version}-${String(serie).padStart(4, '0')}`;

    /** Solo dígitos hex (máx. 12) -> 'AA:BB:...' parcial mientras se teclea. */
    function formatMacProgress(raw) {
        const hex = String(raw || '').replace(/[^0-9A-Fa-f]/g, '').toUpperCase().slice(0, 12);
        return hex.match(/.{1,2}/g) ? hex.match(/.{1,2}/g).join(':') : '';
    }
    /** MAC completa canónica o null (acepta AA:BB.., AA-BB.., AABB.CCDD.EEFF, 12 hex, con texto alrededor). */
    function parseMac(raw) {
        let txt = String(raw || '').replace(/MAC/gi, ' ');
        let m = /(^|[^0-9A-Fa-f])((?:[0-9A-Fa-f]{2}[:\-.]?){5}[0-9A-Fa-f]{2})(?![0-9A-Fa-f])/.exec(txt);
        if (!m && /^[0-9A-Fa-f\s:.\-]+$/.test(txt)) m = /^()((?:[0-9A-Fa-f]{2}[:\-.]?){5}[0-9A-Fa-f]{2})$/.exec(txt.replace(/\s+/g, '')); // '70 4b ca 5b 9f 6e'
        if (!m) return null;
        const hex = m[2].replace(/[^0-9A-Fa-f]/g, '').toUpperCase();
        if (/^0{12}$/.test(hex) || /^F{12}$/.test(hex)) return null;
        return hex.match(/.{2}/g).join(':');
    }

    // ---------------------------------------------------------------- estado de las placas y de la tarjeta
    const CICLO_LABEL = { RECIBIDA: 'Sin confirmar', DISPONIBLE: 'Suelta', ASIGNADA: 'Asignada', FALLA: 'Falla', BAJA: 'Baja' };
    const CICLO_KIND = { RECIBIDA: 'warn', DISPONIBLE: 'info', ASIGNADA: 'ok', FALLA: 'bad', BAJA: '' };

    /** Estado real de una tarjeta. Orden de prioridad: falta R1 o R2 -> incompleta; falta alguna MAC de R1/R2 -> sin_mac
     *  (aunque además falte la R3: la R3 llega tarde y no debe esconder el avance de las MAC); falta solo la R3 -> incompleta;
     *  todo presente y con MAC -> completa. */
    function estadoTarjeta(t) {
        const x = t || {};
        const falta = ['r1', 'r2', 'r3'].filter((r) => !x[r]).map((r) => r.toUpperCase());
        const sm = x.sin_mac || [];
        if (falta.includes('R1') || falta.includes('R2')) return { key: 'incompleta', label: 'Falta ' + falta.join(', '), kind: 'warn', icon: 'alert' };
        if (sm.length) return { key: 'sin_mac', label: 'Sin MAC: ' + sm.join(', ') + (falta.length ? ' · falta ' + falta.join(', ') : ''), kind: 'info', icon: 'clock' };
        if (falta.length) return { key: 'incompleta', label: 'Falta ' + falta.join(', '), kind: 'warn', icon: 'alert' };
        return tarjetaProgramada(x) ? { key: 'completa', programada: true, label: 'Completa · programada', kind: 'ok', icon: 'check' } : { key: 'completa', label: 'Completa', kind: 'ok', icon: 'check' };
    }
    /** v1.3.52: tarjeta PROGRAMADA = R1, R2 y R3 presentes y las tres programadas (misma regla por placa que `programada`: R1/R2 con MAC y firmware, R3 con firmware).
     *  Es un avance dentro de «completa» (nunca hay programada sin MAC ni sin las 3 placas). Orden: Falta placa → Sin MAC → Programada → Completa. */
    function tarjetaProgramada(t) { const x = t || {}; return !!(x.r1 && x.r2 && x.r3) && ['r1', 'r2', 'r3'].every((r) => programada(Object.assign({}, x[r], { firmware: x[r].firmware || x['firmware_' + r] || null }))); }
    /** Filtro por estado: 'programada' es derivado; el resto usa estadoTarjeta().key. */
    const cumpleEstado = (t, key) => !key || (key === 'programada' ? tarjetaProgramada(t) : estadoTarjeta(t).key === key);
    const TARJETA_ESTADOS = [{ key: 'incompleta', label: 'Falta placa' }, { key: 'sin_mac', label: 'Sin MAC' }, { key: 'programada', label: 'Programadas' }, { key: 'completa', label: 'Completas' }];
    // v1.3.44: lote de mes ("Septiembre 2026"), semana ("Semana 40 · 28 sep–4 oct 2026") o día ("15 sep 2026").
    const MES_CORTO = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];
    function fechaLote(s) { const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s || ''); return m ? new Date(Date.UTC(+m[1], +m[2] - 1, +m[3])) : null; }
    function semanaIso(d) { const t = new Date(d); t.setUTCDate(t.getUTCDate() + 3 - ((t.getUTCDay() + 6) % 7)); const y = t.getUTCFullYear(); const s = new Date(Date.UTC(y, 0, 4)); return { anio: y, sem: 1 + Math.round(((t - s) / 864e5 - 3 + ((s.getUTCDay() + 6) % 7)) / 7) }; }
    function loteNombre(l) {
        if (!l) return 'Sin lote';
        const f = fechaLote(l.fecha_inicio), tipo = l.tipo_lote || 'mes';
        if (tipo === 'semana' && f) {
            const fin = new Date(f.getTime() + 6 * 864e5);
            const ini = `${f.getUTCDate()} ${MES_CORTO[f.getUTCMonth()]}` + (f.getUTCFullYear() !== fin.getUTCFullYear() ? ' ' + f.getUTCFullYear() : '');
            return `Semana ${semanaIso(f).sem} · ${ini}–${fin.getUTCDate()} ${MES_CORTO[fin.getUTCMonth()]} ${fin.getUTCFullYear()}`;
        }
        if (tipo === 'dia' && f) return `${f.getUTCDate()} ${MES_CORTO[f.getUTCMonth()]} ${f.getUTCFullYear()}`;
        if (l.mes >= 1 && l.mes <= 12 && l.anio) return `${MESES[l.mes - 1]} ${l.anio}`;
        return l.codigo_lote || 'Lote';
    }
    // Del más reciente al más antiguo por fecha de inicio (los lotes viejos sin fecha usan el día 1 de su mes).
    function loteInicio(l) { return l.fecha_inicio || `${l.anio || 0}-${String(l.mes || 1).padStart(2, '0')}-01`; }
    function ordenarLotes(arr) { return (arr || []).slice().sort((a, b) => loteInicio(b).localeCompare(loteInicio(a)) || (b.id - a.id)); }
    function debounce(fn, ms) { let t = null; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; }
    // Un solo Intl.DateTimeFormat: toLocaleTimeString() crea uno nuevo en cada llamada (con 300 filas son ~100 ms por repintado).
    let HORA_FMT = null;
    try { HORA_FMT = new Intl.DateTimeFormat('es-MX', { hour: '2-digit', minute: '2-digit' }); } catch (e) { HORA_FMT = null; }
    function hora(s) {
        const d = s ? new Date(String(s).replace(' ', 'T')) : new Date();
        if (isNaN(d)) return '';
        return HORA_FMT ? HORA_FMT.format(d) : d.toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit' });
    }

    // ---------------------------------------------------------------- iconos (trazo propio, rejilla 24)
    const ICONS = {
        recibir: 'M4 8V5a1 1 0 0 1 1-1h3M16 4h3a1 1 0 0 1 1 1v3M20 16v3a1 1 0 0 1-1 1h-3M8 20H5a1 1 0 0 1-1-1v-3M4 12h16',
        emparejar: 'M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1',
        programar: 'M7 7h10v10H7zM9 3v4M15 3v4M9 17v4M15 17v4M3 9h4M3 15h4M17 9h4M17 15h4',
        consultar: 'M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14zM21 21l-5.2-5.2M8 11h6M11 8v6',
        camera: 'M3 8a1 1 0 0 1 1-1h3l1.5-2h7L17 7h3a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1zM12 10a3.2 3.2 0 1 0 0 6.4 3.2 3.2 0 0 0 0-6.4z',
        flip: 'M4 9V6a1 1 0 0 1 1-1h11M13 2l3 3-3 3M20 15v3a1 1 0 0 1-1 1H8M11 22l-3-3 3-3',
        flash: 'M13 3 5 13.5h6L10 21l8-10.5h-6z',
        vol: 'M4 9v6h4l5 4V5L8 9zM16.5 8.5a5 5 0 0 1 0 7M19 6a8.5 8.5 0 0 1 0 12',
        muted: 'M4 9v6h4l5 4V5L8 9zM17 9l5 6M22 9l-5 6',
        plus: 'M12 5v14M5 12h14',
        minus: 'M5 12h14',
        trash: 'M4 7h16M10 11v6M14 11v6M6 7l1 12a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1l1-12M9 7V4h6v3',
        edit: 'M4 20h4L19 9l-4-4L4 16zM13.5 6.5l4 4',
        check: 'M5 12.5l4.5 4.5L19 7',
        x: 'M6 6l12 12M18 6L6 18',
        alert: 'M12 4 21 20H3zM12 10v4M12 17.3v.01',
        info: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 11v5M12 7.6v.01',
        sun: 'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8zM12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.4 1.4M17.6 17.6 19 19M5 19l1.4-1.4M17.6 6.4 19 5',
        moon: 'M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z',
        printer: 'M7 9V4h10v5M7 17H5a1 1 0 0 1-1-1v-5a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v5a1 1 0 0 1-1 1h-2M7 14h10v6H7z',
        refresh: 'M20 11a8 8 0 1 0-2.3 5.7M20 5v6h-6',
        search: 'M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14zM20 20l-4-4',
        monitor: 'M3 5h18v11H3zM8 20h8M12 16v4',
        more: 'M5 12h.01M12 12h.01M19 12h.01',
        back: 'M15 5l-7 7 7 7',
        undo: 'M9 14 4 9l5-5M4 9h9a6 6 0 0 1 0 12h-3',
        qr: 'M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h2v2h-2zM18 14h2M14 18h2M18 18h2v2',
        box: 'M3 8l9-5 9 5v8l-9 5-9-5zM3 8l9 5 9-5M12 13v8',
        circle: 'M12 6a6 6 0 1 0 0 12 6 6 0 0 0 0-12z',
        clock: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 7v5l3 2',
        lock: 'M6 11h12v9H6zM8.5 11V8a3.5 3.5 0 0 1 7 0v3',
        tag: 'M3 12V4h8l9 9-8 8zM7.5 8.5v.01',
        download: 'M12 4v11M7 11l5 5 5-5M5 20h14',
        mail: 'M3 6h18v12H3zM3 7l9 6 9-6',
        keyboard: 'M3 6h18v12H3zM7 10h.01M11 10h.01M15 10h.01M7 14h10',
        paste: 'M9 4h6v3H9zM7 5H5a1 1 0 0 0-1 1v14a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1V6a1 1 0 0 0-1-1h-2',
        link: 'M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1',
        unlink: 'M9 15 6 18a4 4 0 0 1-5.7-5.7l3-3M15 9l3-3a4 4 0 0 1 5.7 5.7l-3 3M8 8 6 6M16 16l2 2M4 20l3-3M17 7l3-3',
        layers: 'M12 3 3 8l9 5 9-5zM3 13l9 5 9-5M3 17.5l9 5 9-5',
        list: 'M8 6h13M8 12h13M8 18h13M3.5 6h.01M3.5 12h.01M3.5 18h.01',
        excel: 'M6 3h9l4 4v14H6zM14 3v5h5M9 12l4 5M13 12l-4 5',
        chevron: 'M9 6l6 6-6 6',
        wifi: 'M2 9a15 15 0 0 1 20 0M5.5 12.5a10 10 0 0 1 13 0M9 16a5 5 0 0 1 6 0M12 19.5v.01',
        // consola de escritorio
        dash: 'M4 4h7v9H4zM13 4h7v5h-7zM13 11h7v9h-7zM4 15h7v5H4z',
        card: 'M3 6a1 1 0 0 1 1-1h16a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1zM3 10h18M7 15h4',
        shield: 'M12 3l8 3v6c0 4.5-3.2 8-8 9-4.8-1-8-4.5-8-9V6zM9 12l2.2 2.2L15.5 10',
        logout: 'M10 4H5a1 1 0 0 0-1 1v14a1 1 0 0 0 1 1h5M15 8l4 4-4 4M19 12H9',
        phone: 'M8 3h8a1 1 0 0 1 1 1v16a1 1 0 0 1-1 1H8a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1zM11 18h2',
        sidebar: 'M4 5h16v14H4zM9 5v14M14 10l-2 2 2 2',
        external: 'M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5',
        help: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM9.6 9.5a2.5 2.5 0 1 1 3.4 2.3c-.7.3-1 .9-1 1.6M12 16.8v.01',
        sort: 'M8 5v14M5 16l3 3 3-3M16 19V5M13 8l3-3 3 3',
    };
    function icon(name, extra) {
        const NS = 'http://www.w3.org/2000/svg';
        const svg = document.createElementNS(NS, 'svg');
        svg.setAttribute('viewBox', '0 0 24 24');
        svg.setAttribute('class', 'svg-i' + (extra ? ' ' + extra : ''));
        svg.setAttribute('aria-hidden', 'true');
        const p = document.createElementNS(NS, 'path');
        p.setAttribute('d', ICONS[name] || ICONS.circle);
        svg.appendChild(p);
        return svg;
    }

    // ---------------------------------------------------------------- piezas visuales
    function tipoChip(tipo, opts = {}) {
        const c = h('span', { class: 'tipo' + (opts.lg ? ' lg' : ''), dataset: { t: tipo || '' } }, tipo || '—');
        if (!tipo || opts.empty) c.dataset.empty = '1';
        return c;
    }
    function badge(text, kind, iconName) {
        const b = h('span', { class: 'badge', dataset: { k: kind || '' } });
        if (iconName) b.appendChild(icon(iconName));
        b.appendChild(document.createTextNode(text));
        return b;
    }
    const tarjetaBadge = (t) => { const e = estadoTarjeta(t); return badge(e.label, e.kind, e.icon); };
    /** R1/R2 con MAC y firmware guardados = programada (v1.3.40). La R3 no lleva MAC: programada = tiene firmware (v1.3.44). */
    const programada = (p) => !!p && !!p.firmware && (p.tipo === 'R3' || !!p.mac);
    const cicloBadge = (c, p) => {
        if (programada(p) && (c === 'RECIBIDA' || c === 'DISPONIBLE')) return badge('Programada', 'ok');
        if (programada(p) && c === 'ASIGNADA') return badge('Asignada · programada', 'ok');
        return badge(CICLO_LABEL[c] || c || '—', CICLO_KIND[c] || '');
    };
    function banner(kind, iconName, ...kids) {
        return h('div', { class: 'banner', dataset: { k: kind }, role: kind === 'bad' ? 'alert' : 'status' }, icon(iconName), h('div', { class: 'grow' }, kids));
    }
    function empty(iconName, title, text) {
        return h('div', { class: 'empty' }, icon(iconName), h('b', null, title), text ? h('span', null, text) : null);
    }

    // ---------------------------------------------------------------- avisos
    let toastHost = null;
    function toast(msg, opts = {}) {
        if (!toastHost) { toastHost = h('div', { class: 'toasts', 'aria-live': 'polite' }); document.body.appendChild(toastHost); }
        const t = h('div', { class: 'toast', role: 'status', dataset: { k: opts.kind || '' } }, h('span', null, msg));
        const kill = () => { if (t.parentNode) t.remove(); };
        if (opts.action) t.appendChild(h('button', { class: 'btn', type: 'button', onclick: () => { kill(); opts.action.onClick(); } }, opts.action.label));
        toastHost.appendChild(t);
        setTimeout(kill, opts.ms || (opts.action ? 6000 : 2800));
        return kill;
    }

    // ---------------------------------------------------------------- hoja inferior (sin confirm()/prompt())
    /** sheet({title, body:Node|Node[], actions:[{label,kind,onClick,keepOpen}], onClose}) -> {el, close} */
    function sheet(opts) {
        const prev = document.activeElement;
        const scrim = h('div', { class: 'scrim' });
        const titleId = 'sh' + Math.random().toString(36).slice(2, 7);
        const box = h('div', { class: 'sheet', role: 'dialog', 'aria-modal': 'true', 'aria-labelledby': titleId },
            h('div', { class: 'grip' }),
            opts.title ? h('h2', { id: titleId }, opts.title) : null,
            h('div', { class: 'stack' }, opts.body),
        );
        let closed = false;
        const close = () => {
            if (closed) return; closed = true;
            scrim.remove(); box.remove(); document.removeEventListener('keydown', onKey);
            if (prev && prev.focus) { try { prev.focus(); } catch (e) { /* nada */ } }
            if (opts.onClose) opts.onClose();
        };
        const onKey = (e) => { if (e.key === 'Escape') close(); };
        if (opts.actions && opts.actions.length) {
            const bar = h('div', { class: 'actions' });
            opts.actions.forEach((a) => bar.appendChild(h('button', {
                class: `btn ${a.kind ? 'btn-' + a.kind : ''}`, type: 'button',
                onclick: async (ev) => {
                    const btn = ev.currentTarget; btn.disabled = true;
                    let res; try { res = await a.onClick(btn); } finally { btn.disabled = false; }
                    // Se cierra salvo que onClick devuelva false (error/validación). keepOpen:'always' no cierra nunca.
                    if (res !== false && a.keepOpen !== 'always') close();
                },
            }, a.icon ? icon(a.icon) : null, a.label)));
            box.appendChild(bar);
        }
        scrim.addEventListener('click', close);
        document.addEventListener('keydown', onKey);
        document.body.append(scrim, box);
        const first = box.querySelector('input,select,textarea,button:not(.grip)');
        if (first && opts.focus !== false) setTimeout(() => { try { first.focus(); } catch (e) { /* nada */ } }, 30);
        return { el: box, close };
    }

    // ---------------------------------------------------------------- tema
    async function cerrarSesion() {
        try { await fetch('/api/admin/logout', { method: 'POST' }); } catch (e) { /* sin red: igual se va al login */ }   // también cierra la sesión de supervisor
        try { sessionStorage.clear(); } catch (e) { /* nada */ }
        try { await fetch('/api/auth/logout', { method: 'POST' }); } catch (e) { /* sin red: igual se va al login */ }
        location.href = '/login';
    }
    function applyTheme(t) {
        document.documentElement.dataset.theme = t;
        const m = document.querySelector('meta[name="theme-color"]');
        if (m) m.setAttribute('content', t === 'light' ? '#E9ECF1' : '#0A1020');
    }
    function currentTheme() { return document.documentElement.dataset.theme || 'dark'; }
    function toggleTheme() {
        const n = currentTheme() === 'light' ? 'dark' : 'light';
        store.set('tqt.tema', n); applyTheme(n); return n;
    }
    applyTheme(store.get('tqt.tema', 'dark') === 'light' ? 'light' : 'dark');

    // ---------------------------------------------------------------- WebSocket compartido
    let wsClient = null;
    function ws(clientType) {
        if (!wsClient && window.TQTWebSocketClient) {
            wsClient = new window.TQTWebSocketClient(clientType || 'operador_movil');
            wsClient.onStatus((s) => document.querySelectorAll('.conn').forEach((c) => {
                c.dataset.s = s;
                const lbl = c.querySelector('span');
                if (lbl) lbl.textContent = { connected: 'En línea', connecting: 'Conectando', disconnected: 'Sin red', error: 'Sin red' }[s] || s;
            }));
            wsClient.connect();
        }
        return wsClient;
    }

    /** Red de seguridad contra datos viejos: ejecuta `fn` al reconectarse el WebSocket (los avisos perdidos mientras estuvo
     *  caído no se reenvían), al volver a la pestaña y cada `ms` mientras la pestaña está visible. */
    function resync(fn, ms) {
        let vistoConectado = false;
        const w = ws();
        if (w && w.onStatus) w.onStatus((st) => { if (st === 'connected') { if (vistoConectado) fn('reconexion'); vistoConectado = true; } });
        document.addEventListener('visibilitychange', () => { if (!document.hidden) fn('visible'); });
        setInterval(() => { if (!document.hidden) fn('periodico'); }, ms || 45000);
    }

    // ---------------------------------------------------------------- armazón móvil (cabecera + pestañas)
    const TABS = [
        { id: 'recibir', href: '/', label: 'Recibir', icon: 'recibir' },
        { id: 'emparejar', href: '/static/emparejar.html', label: 'Emparejar', icon: 'emparejar' },
        { id: 'programar', href: '/static/programar.html', label: 'Programar', icon: 'programar' },
        { id: 'consultar', href: '/consultar', label: 'Consultar', icon: 'consultar' },
    ];

    function brandMark() {
        const NS = 'http://www.w3.org/2000/svg';
        const svg = document.createElementNS(NS, 'svg');
        svg.setAttribute('viewBox', '0 0 32 32'); svg.setAttribute('class', 'brand-mark'); svg.setAttribute('aria-hidden', 'true');
        const parts = [['M3 3h11v11H3z', 'currentColor'], ['M18 3h11v11H18z', 'currentColor'], ['M3 18h11v11H3z', 'currentColor']];
        parts.forEach(([d]) => {
            const p = document.createElementNS(NS, 'path'); p.setAttribute('d', d); p.setAttribute('fill', 'none'); p.setAttribute('stroke', 'currentColor'); p.setAttribute('stroke-width', '2.4'); svg.appendChild(p);
        });
        [['7', '7'], ['22', '7'], ['7', '22']].forEach(([x, y]) => {
            const r = document.createElementNS(NS, 'rect'); r.setAttribute('x', x); r.setAttribute('y', y); r.setAttribute('width', '3'); r.setAttribute('height', '3'); r.setAttribute('fill', 'currentColor'); svg.appendChild(r);
        });
        const dots = document.createElementNS(NS, 'path'); dots.setAttribute('d', 'M19 19h3v3h-3zM25 19h4v3h-4zM19 25h4v4h-4zM26 25h3v4h-3z'); dots.setAttribute('fill', 'currentColor'); svg.appendChild(dots);
        return svg;
    }

    /** mountShell({active, sub}) crea cabecera y pestañas dentro de .app. Devuelve {setSub, setLote}. */
    function mountShell(opts) {
        const app = document.querySelector('.app');
        const subTxt = h('span', null, opts.sub || '');
        // El logo lleva a "/", el sub-título abre la hoja de lotes (dos controles separados, cada uno con su nombre)
        const sub = h('button', { class: 'brand-sub', type: 'button', 'aria-haspopup': 'dialog', 'aria-label': 'Lotes: ' + (opts.sub || 'elegir lote'), onclick: () => openLotes(api2) }, subTxt, icon('chevron'));
        const top = h('header', { class: 'topbar' },
            h('div', { class: 'brandbox' },
                h('a', { class: 'brand-logo', href: '/', 'aria-label': 'Escáner TQT, inicio', tabindex: '-1' }, brandMark()),
                h('a', { class: 'brand', href: '/', 'aria-label': 'Escáner TQT, inicio' }, h('span', { class: 'brand-name' }, 'Escáner TQT')),
                sub),
            h('div', { class: 'spacer' }),
            h('div', { class: 'conn', dataset: { s: 'connecting' }, role: 'status' }, h('i'), h('span', null, 'Conectando')),
            h('button', { class: 'iconbtn', type: 'button', 'aria-label': 'Cambiar entre tema claro y oscuro', onclick: (e) => {
                const t = toggleTheme(); const b = e.currentTarget; b.replaceChildren(icon(t === 'light' ? 'moon' : 'sun'));
            } }, icon(currentTheme() === 'light' ? 'moon' : 'sun')),
            h('button', { class: 'iconbtn', type: 'button', 'aria-label': 'Cerrar sesión', title: 'Cerrar sesión', onclick: cerrarSesion }, icon('logout')),
            h('button', { class: 'iconbtn', type: 'button', 'aria-label': 'Más opciones', onclick: openMenu }, icon('more')),
        );
        app.prepend(top);
        const nav = h('nav', { class: 'tabbar', 'aria-label': 'Secciones' }, TABS.map((t) => h('a', {
            class: 'tab', href: t.href, 'aria-current': t.id === opts.active ? 'page' : null,
        }, icon(t.icon), h('span', null, t.label))));
        app.appendChild(nav);
        const principal = app.querySelector('main');
        if (principal) {
            const pie = h('p', { class: 'verpie' }, 'Escáner TQT ', h('b', { 'data-version': '' }));
            principal.appendChild(pie);
            versionP.then((v) => { if (v) pie.querySelector('b').textContent = 'v' + v; });
        }
        ws(opts.client);

        const setSub = (t) => { subTxt.textContent = t; sub.setAttribute('aria-label', 'Lotes: ' + t); };
        const api2 = { setSub, refresh };
        function refresh() {
            return api('/api/status').then((r) => {
                if (r.ok && r.data && r.data.active_lote) setSub('Lote ' + loteNombre(r.data.active_lote));
            });
        }
        refresh();
        return api2;
    }

    // ---------------------------------------------------------------- hoja "Lotes" (elegir, usar, crear)
    /** Cambio de lote hecho desde este celular: avisa a la pantalla (evento cancelable) y, si nadie lo atiende, recarga. */
    function loteCambiado(shell, lote) {
        if (lote) shell.setSub('Lote ' + loteNombre(lote)); else shell.refresh();
        const ev = new CustomEvent('tqt:lote-cambiado', { detail: { lote }, cancelable: true });
        if (document.dispatchEvent(ev)) setTimeout(() => location.reload(), 350);
    }

    const esAdmin = () => !acceso.rol || acceso.rol === 'administrador';   // sin dato aún: se muestra todo y el servidor decide
    function openLotes(shell) {
        const body = h('div', { class: 'stack lotes' });
        const s = sheet({ title: 'Lotes', body, focus: false, actions: [{ label: 'Cerrar', kind: 'ghost', onClick: () => true }] });
        let lotes = null, error = '', pendiente = null, authErr = '', busy = false;
        const anioAct = new Date().getFullYear(), mesAct = new Date().getMonth() + 1;
        const mesSel = h('select', { class: 'input', id: 'nlMes', 'aria-label': 'Mes' }, MESES.map((m, i) => h('option', { value: String(i + 1), selected: i + 1 === mesAct ? '' : null }, m)));
        const anioIn = h('input', { class: 'input mono', id: 'nlAnio', type: 'number', inputmode: 'numeric', min: '2020', max: '2100', value: String(anioAct), 'aria-label': 'Año' });
        const nlErr = h('div', { class: 'hint err', role: 'alert' });
        const hoyIso = (() => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; })();
        const tipoSel = h('select', { class: 'input', id: 'nlTipo', 'aria-label': 'Tipo de lote', onchange: () => pintar() },
            [['mes', 'Mes'], ['semana', 'Semana'], ['dia', 'Día']].map(([v, t]) => h('option', { value: v }, t)));
        const fechaIn = h('input', { class: 'input mono', id: 'nlFecha', type: 'date', value: hoyIso, min: '2020-01-01', max: '2100-12-31' });

        async function cargar() {
            const r = await api('/api/lotes');
            if (r.ok) { lotes = ordenarLotes(r.data); error = ''; } else error = r.error;
            pintar();
        }

        // Ejecuta una acción de supervisor; si responde 401 pide la contraseña en la propia hoja y reintenta.
        async function conClave(fn) {
            if (busy) return null;
            busy = true; pintar();
            let r = await fn();
            busy = false;
            if (r.status === 401 && acceso.rol && acceso.rol !== 'administrador') {   // v1.3.42: sin rol de administrador no sirve la clave
                pintar(); avisoAcceso('lotes'); return null;
            }
            if (r.status === 401) {
                const ok = await new Promise((resolve) => { pendiente = { resolve }; authErr = ''; pintar(); const p = body.querySelector('#lotePass'); if (p) p.focus(); });
                if (!ok) { pintar(); return null; }
                busy = true; pintar(); r = await fn(); busy = false;
            }
            pintar();
            return r;
        }

        async function entrar() {
            const inp = body.querySelector('#lotePass'); const pass = inp ? inp.value : '';
            if (!pass) { authErr = 'Escribe la contraseña del supervisor.'; pintar(); return; }
            const r = await api('/api/admin/login', { method: 'POST', body: { password: pass } });
            if (!r.ok) { authErr = r.status === 429 ? r.error : (r.status === 401 ? 'Contraseña incorrecta.' : r.error); pintar(); const p = body.querySelector('#lotePass'); if (p) p.focus(); return; }
            const p = pendiente; pendiente = null; authErr = ''; p.resolve(true);
        }
        function cancelarClave() { const p = pendiente; pendiente = null; if (p) p.resolve(false); }

        async function usar(l) {
            const r = await conClave(() => api(`/api/lotes/${l.id}/activar`, { method: 'POST' }));
            if (!r) return;
            if (!r.ok) { error = r.error; pintar(); return; }
            toast(`Lote ${loteNombre(l)} activo para todos los celulares`, { kind: 'ok' });
            s.close(); loteCambiado(shell, (r.data && r.data.lote) || l);
        }
        async function crear() {
            nlErr.textContent = '';
            const tipo = tipoSel.value, mes = +mesSel.value, anio = +anioIn.value, fecha = fechaIn.value;
            let cuerpo;
            if (tipo === 'mes') {
                if (!(anio >= 2020 && anio <= 2100)) { nlErr.textContent = 'Escribe un año entre 2020 y 2100.'; anioIn.setAttribute('aria-invalid', 'true'); return; }
                anioIn.removeAttribute('aria-invalid');
                cuerpo = { tipo_lote: 'mes', mes, anio, activo: true };
            } else {
                if (!/^\d{4}-\d{2}-\d{2}$/.test(fecha) || fecha < '2020-01-01' || fecha > '2100-12-31') { nlErr.textContent = 'Elige una fecha válida.'; fechaIn.setAttribute('aria-invalid', 'true'); return; }
                fechaIn.removeAttribute('aria-invalid');
                cuerpo = { tipo_lote: tipo, fecha_inicio: fecha, activo: true };
            }
            const r = await conClave(() => api('/api/lotes', { method: 'POST', body: cuerpo, timeout: 30000 }));
            if (!r) return;
            if (!r.ok) { nlErr.textContent = r.status === 409 ? `${r.error} Búscalo en la lista y pulsa "Usar este lote".` : r.error; return; }
            toast(`Lote ${loteNombre(r.data)} creado y activo para todos`, { kind: 'ok' });
            s.close(); loteCambiado(shell, r.data);
        }

        function pintar() {
            body.replaceChildren();
            body.append(h('p', { class: 'muted lotes-intro' }, 'Elige con qué lote se trabaja. Al usar otro lote, cambia en todos los celulares y en el monitor.'));
            if (pendiente) {
                body.append(h('form', { class: 'panel pad stack lote-auth', onsubmit: (e) => { e.preventDefault(); entrar(); } },
                    h('b', null, 'Estas acciones las hace el supervisor'),
                    h('div', { class: 'field' }, h('label', { for: 'lotePass' }, 'Contraseña del supervisor'),
                        h('input', { class: 'input', id: 'lotePass', type: 'password', autocomplete: 'current-password', 'aria-describedby': 'lotePassErr', 'aria-invalid': authErr ? 'true' : null })),
                    h('div', { class: 'hint err', id: 'lotePassErr', role: 'alert' }, authErr),
                    h('div', { class: 'row' }, h('button', { class: 'btn grow', type: 'button', onclick: cancelarClave }, 'Cancelar'), h('button', { class: 'btn btn-primary grow', type: 'submit' }, 'Entrar y continuar'))));
            }
            if (error) body.append(banner('bad', 'alert', error));
            if (!lotes) body.append(h('div', { class: 'skel', role: 'status' }, 'Cargando lotes…'));
            else if (!lotes.length) body.append(empty('layers', 'Todavía no hay lotes', 'Crea el primero con el formulario de abajo.'));
            else body.append(h('ul', { class: 'lote-list' }, lotes.map((l) => h('li', { class: 'lote', dataset: { activo: l.activo ? '1' : '' } },
                h('div', { class: 'lote-info' },
                    h('div', { class: 'lote-nom' }, loteNombre(l), l.activo ? badge('Activo', 'ok', 'check') : null),
                    h('div', { class: 't2' }, `${l.tarjetas || 0} tarjeta${l.tarjetas === 1 ? '' : 's'}`)),
                h('div', { class: 'lote-acc' },
                    l.activo || !esAdmin() ? null : h('button', { class: 'btn btn-sm btn-primary', type: 'button', disabled: busy ? '' : null, 'aria-label': `Usar el lote ${loteNombre(l)}`, onclick: () => usar(l) }, 'Usar este lote'),
                    h('a', { class: 'btn btn-sm', href: `/monitor?lote=${l.id}`, 'aria-label': `Ver el lote ${loteNombre(l)} en el monitor` }, icon('monitor'), 'Ver en el monitor'))))));
            if (!esAdmin()) {   // v1.3.42: cambiar o crear lotes es de administradores; se explica en vez de mostrar botones que fallan
                body.append(h('div', { class: 'acceso-aviso' }, h('span', { class: 'acceso-ico' }, icon('lock')),
                    h('div', null, h('b', null, 'Solo un administrador puede cambiar o crear lotes.'), h('p', { class: 'muted' }, 'Puedes ver los lotes; pide a un administrador que active el que necesitas.'))));
                return;
            }
            body.append(h('section', { class: 'panel pad stack', 'aria-labelledby': 'nlTit' },
                h('h3', { class: 'silk', id: 'nlTit' }, 'Nuevo lote'),
                h('div', { class: 'field' }, h('label', { for: 'nlTipo' }, 'Tipo'), tipoSel),
                tipoSel.value === 'mes'
                    ? h('div', { class: 'row' }, h('div', { class: 'field grow' }, h('label', { for: 'nlMes' }, 'Mes'), mesSel), h('div', { class: 'field', style: 'width:110px' }, h('label', { for: 'nlAnio' }, 'Año'), anioIn))
                    : h('div', { class: 'field' }, h('label', { for: 'nlFecha' }, tipoSel.value === 'semana' ? 'Cualquier día de la semana' : 'Día'), fechaIn,
                        tipoSel.value === 'semana' ? h('div', { class: 'hint' }, 'La semana va de lunes a domingo.') : null),
                nlErr,
                h('button', { class: 'btn btn-primary', type: 'button', disabled: busy ? '' : null, onclick: crear }, icon('plus'), 'Crear y usar este lote')));
        }
        pintar(); cargar();
    }

    function openMenu() {
        const link = (href, ic, t, s, onclick) => h('a', { class: 'item', href, onclick }, icon(ic), h('div', null, h('div', { style: 'font-weight:700' }, t), h('div', { class: 't2' }, s)), icon('chevron'));
        sheet({
            title: 'Más opciones',
            body: h('div', { class: 'list' },
                link('/monitor', 'monitor', 'Versión de escritorio', 'Consola para PC: consulta, MAC y administración (sin cámara)', () => { try { localStorage.setItem('tqt.vista', 'escritorio'); } catch (e) { /* nada */ } }),
                link('/escaner', 'qr', 'Escáner para la consola', 'Vincula este celular con la PC (QR del "Botón de escaneo") y escanea desde aquí'),
                link('/dymo', 'printer', 'Etiquetas DYMO', 'Vista previa e impresión'),
                link('/admin', 'info', 'Administración', 'Borrado, exportación y contraseña (requiere clave)')),
            focus: false,
        });
    }

    /** Sustituye <span class="svg-slot" data-i="nombre"> por el icono SVG (evita repetir SVG en el HTML). */
    function hydrateIcons(root) {
        (root || document).querySelectorAll('.svg-slot').forEach((s) => s.replaceWith(icon(s.dataset.i)));
    }

    // Versión de la app (una sola fuente: el servidor). Se muestra en el pie (móvil), la barra lateral (consola) y en [data-version].
    const versionP = fetch('/api/config', { cache: 'no-store' }).then((r) => r.json()).then((x) => (x && x.version) || '').catch(() => '');
    versionP.then((v) => {
        if (!v) return;
        const pon = () => document.querySelectorAll('[data-version]').forEach((e) => { e.textContent = 'v' + v; });
        if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', pon); else pon();
    });

    /** Enviar por correo un Excel que genera el servidor (v1.3.37).
     *  opts: { tipo: 'lote'|'reporte_dia'|'inventario_tqtr', lote_id?, fecha?, desde?, hasta?, titulo, adminToken? }
     *  Muestra las cuentas activas como casillas y un campo para correos sin cuenta (separados por coma o espacio). */
    async function enviarExcel(opts) {
        const r = await api('/api/correo/destinatarios');
        if (!r.ok) { toast(r.error, { kind: 'bad' }); return; }
        const d = r.data;
        const marcas = d.items.map((u) => {
            const cb = h('input', { type: 'checkbox', value: u.email });
            return { cb, el: h('label', { class: 'row', style: 'gap:10px;padding:6px 0;cursor:pointer' }, cb, h('span', { class: 'mono grow', style: 'overflow-wrap:anywhere' }, u.email), h('span', { class: 'muted', style: 'font-size:12px' }, u.rol)) };
        });
        const otros = h('input', { class: 'input', type: 'text', inputmode: 'email', autocapitalize: 'none', spellcheck: 'false', placeholder: 'otra@empresa.com, otro@correo.com', 'aria-label': 'Correos sin cuenta' });
        const msj = h('textarea', { class: 'input', rows: 2, maxlength: 1000, placeholder: 'Mensaje (opcional)', 'aria-label': 'Mensaje opcional', style: 'resize:vertical' });
        const err = h('div', { class: 'hint err', role: 'alert' });
        const body = [
            h('p', { class: 'muted', style: 'margin:0' }, 'Se adjunta: ', h('b', null, opts.titulo || 'Excel'), '. Cada destinatario recibe su propio correo.'),
            d.smtp ? null : banner('warn', 'alert', 'El correo SMTP no está configurado en el servidor: no se podrá enviar.'),
            h('div', { class: 'silk' }, 'Cuentas de la app'),
            h('div', { style: 'max-height:240px;overflow:auto;border:1px solid var(--line);border-radius:10px;padding:4px 12px' }, marcas.length ? marcas.map((m) => m.el) : h('span', { class: 'muted' }, 'No hay cuentas activas.')),
            h('div', { class: 'field' }, h('label', null, 'Correos sin cuenta'), otros),
            h('div', { class: 'field' }, h('label', null, 'Mensaje'), msj),
            err,
        ];
        sheet({
            title: 'Enviar por correo', body, actions: [
                { label: 'Cancelar', kind: 'ghost', onClick: () => true },
                { label: 'Enviar', kind: 'primary', icon: 'mail', onClick: async (btn) => {
                    const extra = otros.value.split(/[\s,;]+/).map((x) => x.trim()).filter(Boolean);
                    const para = [...new Set([...marcas.filter((m) => m.cb.checked).map((m) => m.cb.value), ...extra])];
                    if (!para.length) { err.textContent = 'Elige al menos una cuenta o escribe un correo.'; return false; }
                    if (para.length > d.max) { err.textContent = `Máximo ${d.max} destinatarios por envío.`; return false; }
                    const malo = extra.find((x) => !/^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/.test(x));
                    if (malo) { err.textContent = `Correo no válido: ${malo}`; return false; }
                    err.textContent = ''; btn.textContent = 'Enviando…';
                    const headers = { 'Content-Type': 'application/json', 'X-Cliente': clienteId };
                    if (opts.adminToken) headers['X-Admin-Token'] = opts.adminToken;
                    let res, data = null;
                    try {
                        res = await fetch('/api/correo/excel', { method: 'POST', headers, body: JSON.stringify({ tipo: opts.tipo, lote_id: opts.lote_id || null, fecha: opts.fecha || null, desde: opts.desde || null, hasta: opts.hasta || null, mensaje: msj.value || null, para }) });
                        try { data = await res.json(); } catch (e) { data = null; }
                    } catch (e) { btn.textContent = 'Enviar'; err.textContent = 'Sin conexión con el servidor.'; return false; }
                    btn.textContent = 'Enviar';
                    if (!res.ok) {
                        err.textContent = res.status === 401 ? 'Para enviar el Excel del lote primero entra a Administración (contraseña de supervisor).' : (detailText(data && data.detail) || `Error ${res.status}`);
                        return false;
                    }
                    const f = data.fallos || [];
                    toast(`${data.archivo} enviado a ${data.enviados.length} destinatario${data.enviados.length === 1 ? '' : 's'}` + (f.length ? ` · ${f.length} falló` : ''), { kind: f.length ? 'warn' : 'ok', ms: 5000 });
                    return true;
                } },
            ],
        });
    }
    /** Botón "Enviar por correo" para poner junto a un botón de exportar. getOpts() se evalúa al pulsar. */
    const botonCorreo = (getOpts, cls) => h('button', { class: cls || 'btn', type: 'button', 'data-escribe': true, title: 'Enviar este Excel por correo', onclick: () => { const o = getOpts(); if (o) enviarExcel(o); } }, icon('mail'), h('span', null, 'Enviar por correo'));

    // ---------------------------------------------------------------- acceso por rol (v1.3.42)
    // El servidor decide (middleware `_permiso_rol`); aquí solo se EXPLICA: aviso al intentar entrar a una zona sin permiso,
    // candados en pestañas/menús y el mismo aviso cuando la API responde 403 con `X-Acceso: rol`.
    const ROL_TXT = { administrador: 'Administrador', general: 'General', consultor: 'Consultor' };
    const ZONA_TXT = {
        admin: 'Administración', recibir: 'Recibir', emparejar: 'Emparejar', programar: 'Programar', monitor: 'la consola de escritorio',
        dymo: 'Etiquetas DYMO', movimientos: 'Movimientos', lotes: 'el cambio o la creación de lotes', otra: 'esa página',
        seccion: 'esa sección de la consola',
    };
    const PUEDE_TXT = {
        general: 'Puedes usar Recibir, Emparejar, Programar, Consultar y la consola de escritorio. Administración (cuentas, movimientos, borrados, respaldos, cambio de lote ) es solo para administradores. Las descargas de Excel no piden contraseña.',
        consultor: 'Tu cuenta es de consulta: en el celular puedes escanear y ver fichas en Consultar; en la consola de escritorio, ver el Dashboard, Tarjetas, Inventario de PCB, Consultar y descargar Excel. No puedes registrar, emparejar, programar, editar, enviar ni borrar datos.',
    };
    const acceso = { rol: null, listo: Promise.resolve(null) };   // listo: promesa con el rol (v1.3.44, la consola la espera)
    /** Zona de una ruta de página (para saber si el rol puede abrirla). */
    function zonaDe(path) {
        const p = path.replace(/\/+$/, '') || '/';
        if (p === '/admin' || p === '/static/admin.html') return 'admin';
        if (p === '/' || p === '/static/index.html') return 'recibir';
        if (p === '/emparejar' || p === '/static/emparejar.html') return 'emparejar';
        if (p === '/programar' || p === '/static/programar.html') return 'programar';
        if (p === '/monitor' || p === '/static/monitor.html') return 'monitor';
        if (p === '/dymo' || p === '/static/dymo_preview.html') return 'dymo';
        return null;
    }
    function zonaPermitida(zona, rol) {
        if (!zona || !rol || rol === 'administrador') return true;
        if (zona === 'admin' || zona === 'movimientos' || zona === 'lotes') return false;
        return rol !== 'consultor' || zona === 'monitor';   // v1.3.44: el consultor entra a la consola (solo algunas secciones)
    }
    let avisoAbierto = null, avisoUlt = 0;
    /** Hoja "Acceso restringido": qué intentó, por qué no puede y qué sí puede hacer su rol. */
    function avisoAcceso(zona, detalle) {
        if (avisoAbierto || Date.now() - avisoUlt < 1200) return;
        avisoUlt = Date.now();
        const rol = acceso.rol;
        const que = zona === 'accion' ? null : (ZONA_TXT[zona] || (/^sec:/.test(zona || '') ? zona.slice(4) : ZONA_TXT.otra));   // 'sec:<título>' = sección de la consola
        const titular = que ? `Tu cuenta${rol ? ` (${ROL_TXT[rol] || rol})` : ''} no tiene acceso a ${que}.` : (detalle || 'Tu cuenta no tiene permiso para hacer esto.');
        avisoAbierto = sheet({
            title: 'Acceso restringido',
            body: [
                h('div', { class: 'acceso-aviso' }, h('span', { class: 'acceso-ico' }, icon('lock')), h('div', null, h('b', null, titular),
                    que && zona === 'admin' ? h('p', { class: 'muted' }, 'Solo las cuentas con rol Administrador pueden entrar.') : null)),
                rol && PUEDE_TXT[rol] ? h('p', { class: 'muted', style: 'margin:0' }, PUEDE_TXT[rol]) : null,
                h('p', { class: 'muted', style: 'margin:0' }, 'Si necesitas este acceso, pide a un administrador que cambie tu rol en Administración › Cuentas.'),
            ],
            actions: [{ label: 'Entendido', kind: 'primary', onClick: () => true }],
            onClose: () => { avisoAbierto = null; },
        });
    }
    // 403 por rol en CUALQUIER petición (api(), fetch directos, descargas): se muestra el aviso además del error de quien llamó
    if (window.fetch && !window.fetch.__tqtAcceso) {
        const fetch0 = window.fetch.bind(window);
        const envuelto = async (...args) => {
            const r = await fetch0(...args);
            if (r.status === 403 && r.headers.get('X-Acceso') === 'rol') {
                const url = String((args[0] && args[0].url) || args[0] || '');
                if (!/\/api\/admin\/logout/.test(url)) {
                    r.clone().json().then((d) => avisoAcceso((d && d.zona) || 'accion', d && d.detail)).catch(() => avisoAcceso('accion'));
                }
            }
            return r;
        };
        envuelto.__tqtAcceso = true;
        window.fetch = envuelto;
    }
    // Enlaces a zonas sin permiso: aviso en vez de navegar (fase de captura: antes que los manejadores de cada página)
    document.addEventListener('click', (e) => {
        if (!acceso.rol || acceso.rol === 'administrador' || e.defaultPrevented || e.button !== 0) return;
        const a = e.target.closest && e.target.closest('a[href]');
        if (!a || a.hasAttribute('download')) return;
        let u; try { u = new URL(a.href, location.href); } catch (err) { return; }
        if (u.origin !== location.origin) return;
        const zona = (u.pathname === '/admin' && /movimientos/.test(u.hash)) ? 'movimientos' : zonaDe(u.pathname);
        if (zonaPermitida(zona, acceso.rol)) return;
        e.preventDefault(); e.stopImmediatePropagation();
        avisoAcceso(zona);
    }, true);
    function aplicarRol(rol) {
        acceso.rol = rol;
        document.documentElement.dataset.rol = rol;
        // ¿Venimos de una redirección del servidor por falta de permiso? (?denegado=<zona>)
        const q = new URLSearchParams(location.search);
        const den = q.get('denegado');
        if (den) {
            q.delete('denegado');
            const resto = q.toString();
            history.replaceState(history.state, '', location.pathname + (resto ? '?' + resto : '') + location.hash);
            const mostrar = () => avisoAcceso(den);
            if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mostrar); else setTimeout(mostrar, 50);
        }
        marcarCandados();
    }
    /** Candado en pestañas, menú y barra lateral que llevan a zonas sin permiso (se vuelve a llamar al pintar). */
    function marcarCandados(root) {
        if (!acceso.rol || acceso.rol === 'administrador') return;
        if (acceso.rol === 'consultor') (root || document).querySelectorAll('a.brand, a.brand-logo').forEach((a) => { if (a.getAttribute('href') !== '/consultar') a.href = '/consultar'; });   // su inicio es Consultar
        (root || document).querySelectorAll('a[href]').forEach((a) => {
            let u; try { u = new URL(a.href, location.href); } catch (e) { return; }
            if (u.origin !== location.origin) return;
            const zona = (u.pathname === '/admin' && /movimientos/.test(u.hash)) ? 'movimientos' : zonaDe(u.pathname);
            const bloqueado = !zonaPermitida(zona, acceso.rol);
            a.classList.toggle('acceso-bloq', bloqueado);
            if (bloqueado) { a.setAttribute('aria-disabled', 'true'); a.title = `Sin acceso con tu rol (${ROL_TXT[acceso.rol] || acceso.rol})`; }
        });
    }
    if (!/^\/(login|invitacion)/.test(location.pathname)) {
        acceso.listo = fetch('/api/auth/yo', { cache: 'no-store' }).then((r) => (r.ok ? r.json() : null)).then((u) => {
            if (!u || !u.rol) return null;
            acceso.rol = u.rol; document.documentElement.dataset.rol = u.rol;   // ya, para que la consola filtre secciones y botones
            const listo = () => aplicarRol(u.rol);
            if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', listo); else listo();
            // la barra lateral y los menús se pintan después: re-marcar cuando cambie el DOM (barato, con espera)
            if (u.rol !== 'administrador' && window.MutationObserver) {
                let t = null;
                new MutationObserver(() => { clearTimeout(t); t = setTimeout(() => marcarCandados(), 120); }).observe(document.documentElement, { childList: true, subtree: true });
            }
            return u.rol;
        }).catch(() => null);   // sin red: el servidor sigue protegiendo
    }

    // ---------------------------------------------------------------- estatus de la tarjeta (v1.3.43, Consultar móvil y escritorio)
    const ymdHoy = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; };
    const fechaCorta = (s) => { const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s || ''); return m ? `${+m[3]} ${MESES[+m[2] - 1].slice(0, 3).toLowerCase()} ${m[1]}` : ''; };
    /** Estatus de la tarjeta en el ciclo: emparejada → programada (MAC) → completa → entregada. */
    function estatusCiclo(t) {
        const e = estadoTarjeta(t);
        const prog = tarjetaProgramada(t);
        const pasos = [
            { k: 'emp', t: 'Emparejada', ok: true, f: (t.created_at || '').slice(0, 10) },
            { k: 'prog', t: 'Programada', ok: prog, f: '' },
            { k: 'comp', t: 'Completa', ok: e.key === 'completa', f: t.fecha_finalizado || '' },
            { k: 'ent', t: 'Entregada', ok: e.key === 'completa' && !!t.fecha_real, f: t.fecha_real || '' },
        ];
        let actual;
        if (pasos[3].ok) actual = { label: 'Entregada', kind: 'ok', icon: 'check' };
        else if (pasos[2].ok) actual = { label: 'Completa · por entregar', kind: 'ok', icon: 'clock' };
        else if (e.key === 'sin_mac') actual = { label: 'En programación', kind: 'info', icon: 'clock' };
        else actual = { label: 'Incompleta', kind: 'warn', icon: 'alert' };
        return { pasos, actual, completa: e.key === 'completa', detalle: e.label };
    }
    /** Panel "Estatus": pasos, fechas y (si está completa y el rol puede editar) la fecha real de entrega y el gabinete.
     *  opts.onGuardado(tarjeta) se llama al guardar. */
    function estatusTarjeta(t, opts = {}) {
        const c = estatusCiclo(t);
        const sec = h('section', { class: 'estatus', 'aria-label': 'Estatus de la tarjeta' });
        sec.append(h('div', { class: 'estatus-cab' }, h('span', { class: 'silk' }, 'Estatus'), badge(c.actual.label, c.actual.kind, c.actual.icon),
            c.completa ? null : h('span', { class: 'hint' }, c.detalle)));
        sec.append(h('ol', { class: 'estatus-pasos' }, c.pasos.map((p, i) => h('li', { dataset: { ok: p.ok ? '1' : '', sig: !p.ok && (i === 0 || c.pasos[i - 1].ok) ? '1' : '' } },
            h('i', { 'aria-hidden': 'true' }, p.ok ? icon('check') : String(i + 1)), h('span', null, p.t), p.f ? h('small', { class: 'mono' }, fechaCorta(p.f)) : null,
            h('span', { class: 'sr-only' }, p.ok ? ' (hecho)' : ' (pendiente)')))));
        const dato = (l, v) => h('div', null, h('dt', null, l), h('dd', null, v || h('span', { class: 'muted' }, '—')));
        sec.append(h('dl', { class: 'estatus-datos' }, dato('Llegada', fechaCorta(t.fecha_llegada)), dato('Finalizada', fechaCorta(t.fecha_finalizado)),
            dato('Proyectada', fechaCorta(t.fecha_proyectada)), dato('Entrega', fechaCorta(t.fecha_real)), dato('Gabinete', t.gabinete)));
        if (!c.completa) return sec;
        if (acceso.rol === 'consultor') { sec.append(h('p', { class: 'hint' }, icon('lock'), ' La fecha de entrega la registra una cuenta General o Administrador.')); return sec; }
        const idF = 'entF' + t.id, idG = 'entG' + t.id;
        const fecha = h('input', { class: 'input mono', type: 'date', id: idF, value: t.fecha_real || t.fecha_proyectada || ymdHoy() });
        const gab = h('select', { class: 'input', id: idG }, h('option', { value: '' }, 'Sin definir'),
            ['Quintalock', 'Translock'].map((g) => h('option', { value: g, selected: t.gabinete === g ? '' : null }, g)));
        const msg = h('span', { class: 'hint', role: 'status', 'aria-live': 'polite' });
        const btn = h('button', { class: 'btn btn-primary', type: 'submit' }, icon('check'), t.fecha_real ? 'Actualizar entrega' : 'Guardar entrega');
        const form = h('form', { class: 'estatus-entrega', onsubmit: async (e) => {
            e.preventDefault();
            if (!fecha.value) { msg.textContent = 'Elige la fecha de entrega.'; fecha.focus(); return; }
            btn.disabled = true; msg.textContent = 'Guardando…';
            const r = await api(`/api/tarjetas/${t.id}`, { method: 'PATCH', body: { fecha_real: fecha.value, gabinete: gab.value } });
            btn.disabled = false;
            if (!r.ok) { msg.textContent = ''; toast(r.error || 'No se pudo guardar la entrega', { kind: 'bad' }); return; }
            msg.textContent = '';
            toast(`Entrega de la tarjeta ${t.id_tarjeta_num} guardada`, { kind: 'ok' });
            if (opts.onGuardado) opts.onGuardado(r.data);
        } },
            h('div', { class: 'estatus-entrega-t' }, h('b', null, t.fecha_real ? 'Entrega registrada' : '¿Cuándo se entrega?'),
                h('span', { class: 'hint' }, t.fecha_real ? 'Puedes corregir la fecha o el gabinete.' : 'Tiene R1, R2, R3 y las MAC: indica la fecha real de entrega y el gabinete.')),
            h('div', { class: 'field' }, h('label', { for: idF }, 'Fecha de entrega'), fecha),
            h('div', { class: 'field' }, h('label', { for: idG }, 'Gabinete'), gab),
            h('div', { class: 'estatus-entrega-b' }, btn, msg));
        sec.append(form);
        return sec;
    }

    window.TQT = {
        versionP,
        hydrateIcons, MESES, esc, h, store, api, parseNombre, nombreDe, parseMac, formatMacProgress, VERSION_DEFAULT,
        CICLO_LABEL, estadoTarjeta, tarjetaProgramada, cumpleEstado, TARJETA_ESTADOS,
        loteNombre, ordenarLotes, debounce, hora,
        icon, tipoChip, badge, tarjetaBadge, cicloBadge, programada, banner, empty,
        toast, sheet, enviarExcel, botonCorreo, estatusTarjeta, estatusCiclo, avisoAcceso, acceso, zonaPermitida, applyTheme, currentTheme, toggleTheme, ws, resync, cerrarSesion, mountShell, openLotes,
    };
})();
