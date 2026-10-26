/* manual.js — Manual de usuario de la Plataforma I+D dentro de «Documentación TEAM HW» (v1.4.39).
 * Lee guias/indice.json y carga cada guía (guias/<id>.json) bajo demanda. Vistas: portada del manual, guía, resultados de búsqueda.
 * Enlaces profundos: #<guia>, #<guia>/<seccion>, #<guia>/<seccion>/<paso>. Progreso «leído» por sección en localStorage.
 * Todo el texto de las guías se pinta con textContent (nunca innerHTML); el único innerHTML son los íconos SVG constantes.
 * GSAP (vendor/gsap.min.js) es opcional: con «reducir movimiento» o sin GSAP no hay animaciones. */
(function () {
    'use strict';
    const BASE = '/static/documentacion/';
    const $ = (s, r = document) => r.querySelector(s);
    const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
    const reducir = matchMedia('(prefers-reduced-motion: reduce)').matches;
    const gs = !reducir && window.gsap ? window.gsap : null;
    const fino = matchMedia('(hover: hover) and (pointer: fine)').matches;
    const escritorio = matchMedia('(min-width: 1024px)');

    // ---------- utilidades ----------
    function h(tag, attrs, ...hijos) {
        const el = document.createElement(tag);
        if (attrs) for (const [k, v] of Object.entries(attrs)) {
            if (v == null || v === false) continue;
            if (k === 'class') el.className = v;
            else if (k === 'style') for (const [p, val] of Object.entries(v)) el.style.setProperty(p, String(val));
            else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
            else el.setAttribute(k, v === true ? '' : String(v));
        }
        for (const x of hijos.flat(Infinity)) { if (x == null || x === false || x === '') continue; el.append(x instanceof Node ? x : String(x)); }
        return el;
    }
    const txt = (v) => (typeof v === 'string' ? v.trim() : typeof v === 'number' ? String(v) : '');
    const arr = (v) => (Array.isArray(v) ? v : []);
    const obj = (v) => !!v && typeof v === 'object' && !Array.isArray(v);
    const num = (v) => { const n = Number(v); return Number.isFinite(n) ? n : null; };
    const lim = (v, a, b) => Math.min(b, Math.max(a, v));
    const dos = (n) => String(n).padStart(2, '0');
    const color = (c, d = '#FF2E88') => (typeof c === 'string' && /^#(?:[0-9a-f]{3}|[0-9a-f]{6})$/i.test(c.trim()) ? c.trim() : d);
    const rutaSegura = (r) => (typeof r === 'string' && /^\/(?!\/)[\w\-./?=&#%]*$/.test(r.trim()) ? r.trim() : null);
    const srcSeguro = (s) => {
        if (typeof s !== 'string' || !/^[\w\-./]+$/.test(s) || s.includes('..')) return null;
        if (s.startsWith('/static/')) return s;
        return s.startsWith('/') ? null : BASE + s;
    };
    const idSeguro = (v, d) => txt(v).toLowerCase().replace(/[^a-z0-9_-]+/g, '-').replace(/^-+|-+$/g, '') || d;
    const norm = (s) => String(s).normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
    const parrafos = (v) => (typeof v === 'string' ? [v] : arr(v).map(txt)).filter(Boolean);
    const ROLES = { administrador: 'Administrador', general: 'General', consultor: 'Consultor' };

    const I = (p) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" focusable="false">${p}</svg>`;
    const ICONOS = {
        brujula: I('<circle cx="12" cy="12" r="9"/><path d="m15.5 8.5-2 5-5 2 2-5z"/>'),
        llave: I('<circle cx="8" cy="15" r="4"/><path d="m10.8 12.2 8.7-8.7M16 7l2.5 2.5M14 9l2 2"/>'),
        chip: I('<rect x="6" y="6" width="12" height="12" rx="1.5"/><rect x="9.5" y="9.5" width="5" height="5"/><path d="M9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4"/>'),
        llanta: I('<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3.5"/><path d="M12 3v5.5M12 15.5V21M3 12h5.5M15.5 12H21"/>'),
        escudo: I('<path d="M12 3 5 6v5c0 4.5 3 8.3 7 10 4-1.7 7-5.5 7-10V6z"/><path d="m9 12 2 2 4-4"/>'),
        candado: I('<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3M12 15v2"/>'),
        antena: I('<path d="M12 12v9M8 21h8"/><circle cx="12" cy="10" r="2"/><path d="M8.5 6.5a5 5 0 0 0 0 7M15.5 6.5a5 5 0 0 1 0 7M5.6 3.6a9 9 0 0 0 0 12.8M18.4 3.6a9 9 0 0 1 0 12.8"/>'),
        camion: I('<path d="M2 6h11v10H2zM13 9h4.5l3.5 3.5V16h-8z"/><circle cx="6" cy="17.5" r="2"/><circle cx="17" cy="17.5" r="2"/>'),
        caja: I('<path d="M21 8 12 3 3 8v8l9 5 9-5z"/><path d="m3 8 9 5 9-5M12 13v8"/>'),
        impresora: I('<path d="M7 8V3h10v5"/><rect x="3" y="8" width="18" height="9" rx="2"/><path d="M7 14h10v7H7z"/>'),
        libro: I('<path d="M4 5a2 2 0 0 1 2-2h14v16H6a2 2 0 0 0-2 2z"/><path d="M4 21V5"/>'),
        buscar: I('<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>'),
        menu: I('<path d="M4 7h16M4 12h16M4 17h16"/>'),
        cerrar: I('<path d="M6 6l12 12M18 6 6 18"/>'),
        ampliar: I('<path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7"/>'),
        mas: I('<path d="M12 5v14M5 12h14"/>'),
        menos: I('<path d="M5 12h14"/>'),
        izq: I('<path d="m15 18-6-6 6-6"/>'),
        der: I('<path d="m9 18 6-6-6-6"/>'),
        check: I('<path d="m5 12.5 4.5 4.5L19 7"/>'),
        reloj: I('<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>'),
        capas: I('<path d="m12 3 9 5-9 5-9-5z"/><path d="m3 13 9 5 9-5"/>'),
        abrir: I('<path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>'),
        enlace: I('<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>'),
        ajustar: I('<path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/>'),
        info: I('<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>'),
        marca: I('<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3"/>'),
    };
    const ico = (n, clase) => { const s = h('span', { class: 'ico' + (clase ? ' ' + clase : ''), 'aria-hidden': 'true' }); s.innerHTML = ICONOS[n] || ICONOS.libro; return s; };

    const aviso = $('#aviso');
    let avisoT = 0;
    function anunciar(t) { clearTimeout(avisoT); aviso.textContent = ''; avisoT = setTimeout(() => { aviso.textContent = t; }, 60); }

    // ---------- progreso (localStorage, siempre con try/catch) ----------
    const LS = 'tqt.manual.leidas';
    let prog = {};
    try { const v = JSON.parse(localStorage.getItem(LS) || '{}'); if (obj(v)) prog = v; } catch (e) { prog = {}; }
    function guardar() { try { localStorage.setItem(LS, JSON.stringify(prog)); } catch (e) { /* sin almacenamiento: el progreso dura la visita */ } }
    const leida = (g, s) => Array.isArray(prog[g]) && prog[g].includes(s);
    function marcarLeida(g, s, si) {
        const l = Array.isArray(prog[g]) ? prog[g].filter((x) => x !== s) : [];
        if (si) l.push(s);
        prog[g] = l; guardar();
    }
    function avance(gd) { const t = gd.secciones.length; const n = gd.secciones.filter((s) => leida(gd.id, s.id)).length; return { n, t, p: t ? n / t : 0 }; }

    // ---------- datos ----------
    let indice = null;
    const cache = new Map();
    const meta = (id) => (indice ? indice.guias.find((g) => g.id === id) : null);
    function normIndice(d) {
        const grupos = arr(d && d.grupos).filter(obj).map((g) => ({ id: txt(g.id), titulo: txt(g.titulo) || txt(g.id) }));
        const guias = arr(d && d.guias).filter(obj).map((g) => ({ id: idSeguro(g.id, ''), titulo: txt(g.titulo), subtitulo: txt(g.subtitulo), color: color(g.color), grupo: txt(g.grupo), icono: txt(g.icono) }))
            .filter((g) => g.id).map((g) => ({ ...g, titulo: g.titulo || g.id }));
        guias.forEach((g) => { if (!grupos.some((x) => x.id === g.grupo)) { if (!grupos.some((x) => x.id === '_otras')) grupos.push({ id: '_otras', titulo: 'Más guías' }); g.grupo = '_otras'; } });
        return { titulo: txt(d && d.titulo) || 'Manual de usuario', grupos, guias };
    }
    function capNorm(c) {
        if (!obj(c)) return null;
        const src = srcSeguro(c.src); if (!src) return null;
        const ancho = num(c.ancho) > 0 ? num(c.ancho) : 1440, alto = num(c.alto) > 0 ? num(c.alto) : 900;
        const marcas = arr(c.marcas).filter(obj).map((m, i) => {
            const x = lim(num(m.x) || 0, 0, 100), y = lim(num(m.y) || 0, 0, 100);
            return { n: num(m.n) || i + 1, x, y, w: lim(num(m.w) || 0, 0, 100 - x), h: lim(num(m.h) || 0, 0, 100 - y), texto: txt(m.texto) };
        });
        return { src, ancho, alto, alt: txt(c.alt), marcas };
    }
    function normGuia(g, id) {
        if (!obj(g)) return null;
        const m = meta(id) || {};
        const vistos = new Set();
        const secciones = arr(g.secciones).filter(obj).map((s, i) => {
            let sid = idSeguro(s.id, 'seccion-' + (i + 1));
            while (vistos.has(sid)) sid += '-' + (i + 1);
            vistos.add(sid);
            const pasos = arr(s.pasos).filter(obj).map((p) => ({ titulo: txt(p.titulo), texto: txt(p.texto), nota: txt(p.nota), cap: capNorm(p.captura), gi: -1 }));
            return { raw: s, id: sid, tipo: txt(s.tipo) || 'texto', titulo: txt(s.titulo) || 'Sección ' + (i + 1), intro: txt(s.intro), parrafos: parrafos(s.parrafos), cap: capNorm(s.captura), gi: -1, pasos };
        });
        const gd = {
            id, titulo: txt(g.titulo) || m.titulo || id, subtitulo: txt(g.subtitulo) || m.subtitulo || '', color: color(g.color, m.color || '#FF2E88'),
            icono: m.icono || txt(g.icono), ruta: rutaSegura(g.ruta), resumen: txt(g.resumen), roles: obj(g.roles) ? g.roles : {},
            secciones, relacionadas: arr(g.relacionadas).map((x) => idSeguro(x, '')).filter(Boolean),
        };
        const palabras = norm(JSON.stringify(g)).split(/\s+/).length;
        gd.tiempo = num(g.tiempo_lectura) > 0 ? Math.round(num(g.tiempo_lectura)) : Math.max(1, Math.round(palabras / 180));
        return gd;
    }
    function cargarGuia(id) {
        if (!/^[a-z0-9_-]+$/.test(id)) return Promise.resolve(null);
        if (!cache.has(id)) {
            cache.set(id, fetch(BASE + 'guias/' + id + '.json', { cache: 'no-cache', credentials: 'same-origin' })
                .then((r) => (r.ok ? r.json() : null)).then((g) => normGuia(g, id)).catch(() => null));
        }
        return cache.get(id);
    }
    function cargarTodas() { return Promise.all(indice.guias.map((g) => cargarGuia(g.id))); }
    const datoYa = new Map();   // id -> guía cargada (o null) para pintar sin esperar
    function recordar(id, g) { datoYa.set(id, g); return g; }

    // ---------- elementos fijos ----------
    const vista = $('#vista'), main = $('#contenido'), lateral = $('#lateral'), latNav = $('#latNav'), velo = $('#velo');
    const menuBtn = $('#menuBtn'), q = $('#q');
    const estado = { vista: '', guia: null, busqueda: '', galeria: [], spy: null };

    // ---------- barra lateral ----------
    function pintarLateral() {
        if (!indice) return;
        const filtro = estado.busqueda ? new Set(estado.coincidencias || []) : null;
        const frag = document.createDocumentFragment();
        frag.append(h('a', { class: 'lat-inicio', href: '#', 'aria-current': estado.vista === 'inicio' ? 'page' : null }, ico('libro'), 'Inicio del manual'));
        indice.grupos.forEach((gr) => {
            const guias = indice.guias.filter((g) => g.grupo === gr.id && (!filtro || filtro.has(g.id)));
            if (!guias.length) return;
            const ul = h('ul', { class: 'lat-lista' });
            guias.forEach((m) => {
                const d = datoYa.get(m.id), actual = estado.guia && estado.guia.id === m.id;
                const av = d ? avance(d) : null;
                const li = h('li', { class: actual ? 'actual' : null, style: { '--c': m.color } },
                    h('a', { class: 'lat-guia', href: '#' + m.id, 'aria-current': actual && estado.vista === 'guia' ? 'page' : null },
                        h('span', { class: 'lat-punto', 'aria-hidden': 'true' }),
                        h('span', { class: 'lat-t' }, m.titulo),
                        datoYa.has(m.id) ? (d ? h('span', { class: 'lat-av' + (av.t && av.n === av.t ? ' completa' : '') }, av.t && av.n === av.t ? ico('check') : null,
                            h('span', { class: 'sr' }, 'Leído: '), `${av.n}/${av.t}`) : h('span', { class: 'lat-pronto' }, 'Pronto')) : null,
                        d && av.t ? h('span', { class: 'lat-barra', 'aria-hidden': 'true' }, h('i', { style: { width: Math.round(av.p * 100) + '%' } })) : null));
                if (actual && estado.vista === 'guia' && estado.guia.secciones.length) {
                    li.append(h('ol', { class: 'toc', 'aria-label': 'Secciones de ' + m.titulo },
                        estado.guia.secciones.map((s, i) => h('li', null, h('a', { class: 'toc-a' + (leida(m.id, s.id) ? ' leida' : ''), href: `#${m.id}/${s.id}`, 'data-sec': s.id },
                            h('span', { class: 'toc-n', 'aria-hidden': 'true' }, dos(i + 1)), h('span', { class: 'toc-t' }, s.titulo),
                            leida(m.id, s.id) ? h('span', { class: 'toc-ok' }, ico('check'), h('span', { class: 'sr' }, '(leída)')) : null)))));
                }
                ul.append(li);
            });
            frag.append(h('h2', { class: 'lat-grupo' }, gr.titulo), ul);
        });
        if (filtro && !filtro.size) frag.append(h('p', { class: 'lat-vacio' }, 'Ninguna guía coincide.'));
        latNav.replaceChildren(frag);
        const total = indice.guias.reduce((a, m) => { const d = datoYa.get(m.id); if (d) { const v = avance(d); a.n += v.n; a.t += v.t; } return a; }, { n: 0, t: 0 });
        $('#latProg').replaceChildren(total.t ? h('div', null, h('p', null, h('b', null, Math.round((total.n / total.t) * 100) + ' %'), ' del manual leído'),
            h('span', { class: 'lat-barra grande', 'aria-hidden': 'true' }, h('i', { style: { width: Math.round((total.n / total.t) * 100) + '%' } }))) : '');
        if (estado.spyActual) resaltarToc(estado.spyActual);
    }

    // cajón en celular
    function cajon(abrir) {
        if (escritorio.matches) abrir = false;
        lateral.classList.toggle('abierta', abrir);
        velo.hidden = !abrir;
        menuBtn.setAttribute('aria-expanded', String(abrir));
        main.inert = abrir; $('.barra').inert = false;
        document.body.classList.toggle('sin-scroll', abrir);
        if (abrir) {
            const a = $('.toc-a.activa', lateral) || $('[aria-current="page"]', lateral) || q;
            setTimeout(() => { (a === q ? q : a).focus({ preventScroll: false }); }, 30);
        }
    }
    menuBtn.addEventListener('click', () => cajon(!lateral.classList.contains('abierta')));
    $('#latCerrar').addEventListener('click', () => { cajon(false); menuBtn.focus(); });
    velo.addEventListener('click', () => cajon(false));
    lateral.addEventListener('click', (e) => { if (e.target.closest('a') && !escritorio.matches) cajon(false); });
    escritorio.addEventListener('change', () => cajon(false));
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && lateral.classList.contains('abierta')) { cajon(false); menuBtn.focus(); }
        if (e.key === '/' && !e.target.closest('input, textarea, [contenteditable], dialog')) { e.preventDefault(); if (!escritorio.matches) cajon(true); q.focus(); }
    });
    $('.salto').addEventListener('click', (e) => { e.preventDefault(); main.focus(); });

    // ---------- marcas sobre capturas ----------
    function crearMarcas(cap, marco, lista, enVisor) {
        const items = new Map();
        let fija = null;
        function activar(n, si) {
            items.forEach(({ b, li }, k) => { const on = si && k === n; b.classList.toggle('activa', on); if (li) li.classList.toggle('activa', on); });
            const it = items.get(n);
            if (si && it) {
                const tip = $('.marca-tip', it.b); tip.style.setProperty('--dx', '0px');
                const r = tip.getBoundingClientRect(); let dx = 0;
                if (r.right > innerWidth - 8) dx = innerWidth - 8 - r.right;
                if (r.left + dx < 8) dx = 8 - r.left;
                tip.style.setProperty('--dx', dx + 'px');
            }
        }
        const soltar = () => activar(fija, fija != null);
        cap.marcas.forEach((m) => {
            const punto = m.w < 2.5 && m.h < 2.5;
            const st = punto ? { left: m.x + m.w / 2 + '%', top: m.y + m.h / 2 + '%' } : { left: m.x + '%', top: m.y + '%', width: m.w + '%', height: m.h + '%' };
            const clases = ['marca', punto ? 'punto' : '', m.y + m.h > 70 ? 'arriba' : 'abajo', m.x + m.w / 2 > 55 ? 'der' : 'izq', m.x < 2 ? 'bx' : '', m.y < 3 ? 'by' : ''].filter(Boolean).join(' ');
            const b = h('button', { type: 'button', class: clases, style: st, 'aria-label': `Marca ${m.n}: ${m.texto || 'sin descripción'}` },
                h('span', { class: 'marca-n', 'aria-hidden': 'true' }, m.n),
                m.texto ? h('span', { class: 'marca-tip', 'aria-hidden': 'true' }, h('b', null, m.n), m.texto) : null);
            let li = null;
            if (lista) {
                li = h('li', null, h('button', { type: 'button', class: 'mli', 'aria-label': `Señalar marca ${m.n} en la captura: ${m.texto}` },
                    h('span', { class: 'mn', 'aria-hidden': 'true' }, m.n), h('span', { 'aria-hidden': 'true' }, m.texto || 'Sin descripción')));
                const lb = li.firstChild;
                lb.addEventListener('pointerenter', () => activar(m.n, true));
                lb.addEventListener('pointerleave', soltar);
                lb.addEventListener('focus', () => activar(m.n, true));
                lb.addEventListener('blur', soltar);
                lb.addEventListener('click', () => { fija = fija === m.n ? null : m.n; soltar(); });
                lista.append(li);
            }
            if (fino) { b.addEventListener('pointerenter', () => activar(m.n, true)); b.addEventListener('pointerleave', soltar); }
            b.addEventListener('focus', () => activar(m.n, true));
            b.addEventListener('blur', () => setTimeout(soltar, 0));
            b.addEventListener('click', (e) => { e.stopPropagation(); fija = fija === m.n ? null : m.n; soltar(); if (fija != null && m.texto) anunciar(`Marca ${m.n}: ${m.texto}`); });
            items.set(m.n, { b, li });
            marco.append(b);
        });
        if (enVisor) marco.addEventListener('click', (e) => { if (!e.target.closest('.marca')) { fija = null; soltar(); } });
    }

    function figura(cap, gi) {
        const vertical = cap.alto > cap.ancho * 1.1;
        const fig = h('figure', { class: 'cap' + (vertical ? ' vertical' : ''), style: { '--ar': cap.ancho + ' / ' + cap.alto } });
        const img = h('img', { src: cap.src, alt: cap.alt, width: cap.ancho, height: cap.alto, loading: 'lazy', decoding: 'async' });
        img.addEventListener('error', () => { fig.classList.add('rota'); });
        const marco = h('div', { class: 'cap-marco' }, img, h('p', { class: 'cap-rota', 'aria-hidden': 'true' }, 'Captura no disponible'));
        const abrir = () => abrirVisor(gi, fig.querySelector('.cap-ampliar'));
        img.addEventListener('click', abrir);
        const lista = cap.marcas.length ? h('ol', { class: 'cap-marcas', 'aria-label': 'Marcas de la captura' }) : null;
        crearMarcas(cap, marco, lista, false);
        marco.append(h('button', { type: 'button', class: 'cap-ampliar', onclick: abrir, 'aria-label': 'Ampliar captura' + (cap.alt ? ': ' + cap.alt : '') }, ico('ampliar'), h('span', null, 'Ampliar')));
        fig.append(marco);
        if (lista) fig.append(h('figcaption', null, lista));
        return fig;
    }

    // ---------- tipos de sección ----------
    function bloquesTexto(s) {
        const out = [];
        if (s.intro) out.push(h('p', { class: 'intro' }, s.intro));
        s.parrafos.forEach((p) => out.push(h('p', null, p)));
        const lista = parrafos(s.raw.lista);
        if (lista.length) out.push(h('ul', { class: 'lista' }, lista.map((x) => h('li', null, x))));
        return out;
    }
    function secPasos(s, gd) {
        const pasos = s.pasos;
        const cont = h('div', { class: 'pasos' });
        if (!pasos.length) return cont;
        let i = 0;
        const nav = h('ol', { class: 'pasos-nav', 'aria-label': 'Pasos de ' + s.titulo });
        const botones = pasos.map((p, k) => {
            const b = h('button', { type: 'button', class: 'pnum', 'aria-label': `Paso ${k + 1}: ${p.titulo || ''}` },
                h('span', { class: 'pnum-n', 'aria-hidden': 'true' }, k + 1), h('span', { class: 'pnum-t', 'aria-hidden': 'true' }, p.titulo || 'Paso ' + (k + 1)));
            b.addEventListener('click', () => ir(k, k > i ? 1 : -1, true));
            nav.append(h('li', null, b));
            return b;
        });
        const panel = h('div', { class: 'paso-panel' });
        const ant = h('button', { type: 'button', class: 'btn btn-sec', onclick: () => ir(i - 1, -1, true) }, ico('izq'), h('span', null, 'Anterior'));
        const sig = h('button', { type: 'button', class: 'btn btn-c', onclick: () => ir(i + 1, 1, true) }, h('span', null, 'Siguiente'), ico('der'));
        const cuenta = h('span', { class: 'pasos-cuenta', 'aria-hidden': 'true' });
        function ir(k, dir, avisar) {
            k = lim(k, 0, pasos.length - 1);
            i = k;
            const p = pasos[k];
            botones.forEach((b, j) => { b.toggleAttribute('aria-current', false); if (j === k) b.setAttribute('aria-current', 'step'); b.classList.toggle('hecho', j < k); });
            nav.style.setProperty('--av', pasos.length > 1 ? k / (pasos.length - 1) : 1);
            panel.replaceChildren(
                h('div', { class: 'paso-txt' },
                    h('p', { class: 'paso-num' }, `Paso ${k + 1} de ${pasos.length}`),
                    h('h3', { tabindex: '-1' }, p.titulo || 'Paso ' + (k + 1)),
                    p.texto ? h('p', null, p.texto) : null,
                    p.nota ? h('p', { class: 'nota' }, ico('info'), h('span', null, p.nota)) : null),
                p.cap ? figura(p.cap, p.gi) : null);
            ant.disabled = k === 0;
            sig.disabled = k === pasos.length - 1;
            cuenta.textContent = `${k + 1} / ${pasos.length}`;
            const act = botones[k]; if (act && act.scrollIntoView && nav.scrollWidth > nav.clientWidth) nav.scrollTo({ left: act.offsetLeft - nav.clientWidth / 2 + act.offsetWidth / 2, behavior: reducir ? 'auto' : 'smooth' });
            if (avisar) anunciar(`Paso ${k + 1} de ${pasos.length}: ${p.titulo}`);
            if (gs && dir) gs.from(panel, { opacity: 0, x: dir * 28, duration: .38, ease: 'power2.out', clearProps: 'all' });
        }
        cont.addEventListener('keydown', (e) => {
            if (!e.target.closest('.pnum, .pasos-ctl')) return;
            if (e.key === 'ArrowRight') { e.preventDefault(); ir(i + 1, 1, true); (e.target.closest('.pnum') ? botones[i] : e.target).focus(); }
            if (e.key === 'ArrowLeft') { e.preventDefault(); ir(i - 1, -1, true); (e.target.closest('.pnum') ? botones[i] : e.target).focus(); }
        });
        cont.append(nav, panel, h('div', { class: 'pasos-ctl' }, ant, cuenta, sig));
        cont.irAPaso = (k) => ir(k, 0, false);
        ir(0, 0, false);
        return cont;
    }
    function secFicha(s) {
        const filas = arr(s.raw.filas).map((f) => (Array.isArray(f) ? f : obj(f) ? Object.values(f) : [f]).map(txt));
        if (!filas.length) return null;
        return h('div', { class: 'ficha-marco' }, h('table', { class: 'ficha' }, h('caption', { class: 'sr' }, s.titulo),
            h('tbody', null, filas.map((c) => h('tr', null, h('th', { scope: 'row' }, c[0] || ''), c.slice(1).map((v) => h('td', null, v)))))));
    }
    function secFaq(s) {
        const items = arr(s.raw.items).filter(obj);
        return h('div', { class: 'faqs' }, items.map((it) => h('details', { class: 'faq' },
            h('summary', null, h('span', null, txt(it.p)), ico('mas', 'faq-ico')),
            h('div', { class: 'faq-r' }, parrafos(it.r).map((p) => h('p', null, p))))));
    }
    function secGlosario(s) {
        const t = arr(s.raw.terminos).filter(obj);
        return h('dl', { class: 'glosario' }, t.map((x) => h('div', null, h('dt', null, txt(x.t)), h('dd', null, txt(x.d)))));
    }

    // ---------- portada del manual ----------
    function tarjeta(m) {
        const d = datoYa.get(m.id);
        const a = h('a', { class: 'tarjeta', href: '#' + m.id, style: { '--c': m.color } },
            h('span', { class: 't-ico' }, ico(m.icono)),
            h('span', { class: 't-titulo' }, m.titulo),
            m.subtitulo ? h('span', { class: 't-sub' }, m.subtitulo) : null,
            h('span', { class: 't-meta' }),
            h('span', { class: 't-ir', 'aria-hidden': 'true' }, ico('der')));
        const llenar = (g) => {
            const mt = $('.t-meta', a);
            if (!g) { mt.replaceChildren(h('span', { class: 'chip' }, 'En preparación')); a.classList.add('pronto'); return; }
            const av = avance(g);
            mt.replaceChildren(h('span', null, ico('reloj'), `${g.tiempo} min`), h('span', null, ico('capas'), `${g.secciones.length} secciones`),
                av.n ? h('span', { class: 'chip ok' }, av.n === av.t ? 'Completa' : `${av.n}/${av.t} leídas`) : null,
                h('span', { class: 't-barra', 'aria-hidden': 'true' }, h('i', { style: { width: Math.round(av.p * 100) + '%' } })));
        };
        if (datoYa.has(m.id)) llenar(d); else cargarGuia(m.id).then((g) => { recordar(m.id, g); llenar(g); });
        return a;
    }
    function pintarInicio() {
        estado.vista = 'inicio'; estado.guia = null; estado.galeria = []; estado.spyActual = null;
        document.title = 'Manual de usuario · Documentación TEAM HW';
        document.documentElement.style.setProperty('--c', '#FF2E88');
        const primera = indice.guias[0];
        const total = indice.guias.reduce((a, m) => { const d = datoYa.get(m.id); if (d) { const v = avance(d); a.n += v.n; a.t += v.t; } return a; }, { n: 0, t: 0 });
        const sigue = total.n ? indice.guias.find((m) => { const d = datoYa.get(m.id); return d && avance(d).n < d.secciones.length; }) : null;
        const cta = sigue || primera;
        const vistaInicio = h('div', { class: 'inicio' },
            h('header', { class: 'm-hero' },
                h('p', { class: 'kicker' }, 'Plataforma I+D · Documentación TEAM HW'),
                h('h1', { class: 'm-titulo', tabindex: '-1' }, h('span', null, 'Manual'), h('span', null, 'de usuario')),
                h('p', { class: 'm-bajada' }, 'Todo para usar la plataforma: el portal, tu cuenta y cada módulo, con capturas reales, marcas numeradas y paso a paso.'),
                h('div', { class: 'm-acciones' },
                    cta ? h('a', { class: 'btn btn-c grande', href: '#' + cta.id }, h('span', null, sigue ? `Continuar con ${sigue.titulo}` : `Empieza por ${cta.titulo}`), ico('der')) : null,
                    h('a', { class: 'btn btn-sec grande', href: '/documentacion' }, h('span', null, 'Volver a la portada'))),
                total.t ? h('div', { class: 'm-prog' }, h('p', null, h('b', null, `${total.n} de ${total.t}`), ' secciones leídas en este navegador'),
                    h('span', { class: 'lat-barra grande', 'aria-hidden': 'true' }, h('i', { style: { width: Math.round((total.n / total.t) * 100) + '%' } }))) : null),
            h('section', { class: 'm-tips', 'aria-labelledby': 'tTips' },
                h('h2', { id: 'tTips', class: 'sr' }, 'Cómo leer este manual'),
                h('div', { class: 'tip' }, ico('marca'), h('div', null, h('h3', null, 'Marcas numeradas'), h('p', null, 'Pasa el cursor o toca un número sobre la captura para saber qué es.'))),
                h('div', { class: 'tip' }, ico('ampliar'), h('div', null, h('h3', null, 'Amplía y haz zoom'), h('p', null, 'Haz clic en una captura para verla en grande; usa la rueda o pellizca.'))),
                h('div', { class: 'tip' }, ico('check'), h('div', null, h('h3', null, 'Tu avance'), h('p', null, 'Marca cada sección como leída. Se guarda solo en este navegador.')))),
            indice.grupos.map((gr) => {
                const guias = indice.guias.filter((g) => g.grupo === gr.id);
                if (!guias.length) return null;
                return h('section', { class: 'm-grupo', 'aria-labelledby': 'g-' + gr.id },
                    h('h2', { id: 'g-' + gr.id, class: 'eyebrow' }, gr.titulo),
                    h('ul', { class: 'tarjetas' }, guias.map((m) => h('li', null, tarjeta(m)))));
            }),
            total.n ? h('p', { class: 'm-reinicio' }, h('button', { type: 'button', class: 'enlace', onclick: () => {
                if (confirm('¿Borrar tu progreso de lectura del manual en este navegador?')) { prog = {}; guardar(); pintarLateral(); pintarInicio(); anunciar('Progreso borrado'); }
            } }, 'Borrar mi progreso de lectura')) : null);
        vista.replaceChildren(vistaInicio);
        pintarLateral();
        if (gs) {
            gs.from('.m-hero > *', { y: 26, opacity: 0, duration: .7, stagger: .07, ease: 'power3.out', clearProps: 'all' });
            gs.from('.tarjeta', { y: 22, opacity: 0, duration: .55, stagger: .04, delay: .2, ease: 'power3.out', clearProps: 'all' });
        }
    }

    // ---------- guía ----------
    function galeriaDe(gd) {
        const gal = [];
        gd.secciones.forEach((s) => {
            if (s.cap) { s.gi = gal.length; gal.push({ cap: s.cap, titulo: s.titulo }); }
            s.pasos.forEach((p, k) => { if (p.cap) { p.gi = gal.length; gal.push({ cap: p.cap, titulo: `${s.titulo} · Paso ${k + 1}${p.titulo ? ': ' + p.titulo : ''}` }); } });
        });
        return gal;
    }
    function botonLeido(gd, s) {
        const b = h('button', { type: 'button', class: 'leido', 'aria-pressed': String(leida(gd.id, s.id)) }, ico('check'), h('span'));
        const pintar = () => { const si = leida(gd.id, s.id); b.setAttribute('aria-pressed', String(si)); b.lastChild.textContent = si ? 'Leída' : 'Marcar como leída'; b.classList.toggle('si', si); };
        b.addEventListener('click', () => {
            const si = !leida(gd.id, s.id);
            marcarLeida(gd.id, s.id, si); pintar(); pintarLateral(); actualizarCabProgreso(gd);
            const av = avance(gd);
            anunciar(si ? `«${s.titulo}» marcada como leída. ${av.n} de ${av.t} en esta guía.` : `«${s.titulo}» ya no está marcada.`);
            if (si && gs) gs.fromTo(b, { scale: .92 }, { scale: 1, duration: .5, ease: 'back.out(3)', clearProps: 'transform' });
        });
        pintar();
        return b;
    }
    function actualizarCabProgreso(gd) {
        const av = avance(gd), el = $('#gProg');
        if (!el) return;
        el.replaceChildren(h('span', { class: 'anillo', style: { '--p': av.p }, 'aria-hidden': 'true' }), `${av.n} de ${av.t} leídas`);
        const sigue = gd.secciones.find((s) => !leida(gd.id, s.id));
        const c = $('#gContinuar');
        if (c) { c.hidden = !sigue || av.n === 0; if (sigue) c.setAttribute('href', `#${gd.id}/${sigue.id}`); }
    }
    function cabecera(gd, m, pos) {
        const grupo = indice.grupos.find((x) => m && x.id === m.grupo);
        const roles = Object.entries(gd.roles).map(([k, v]) => [ROLES[k] || (k.charAt(0).toUpperCase() + k.slice(1)), txt(v)]).filter(([, v]) => v);
        return h('header', { class: 'g-cab' },
            h('p', { class: 'g-grupo' }, grupo ? grupo.titulo : 'Guía', pos ? h('span', null, ` · Guía ${dos(pos.i)} de ${dos(pos.t)}`) : null),
            h('div', { class: 'g-tit' }, h('span', { class: 'g-ico' }, ico(gd.icono)), h('h1', { class: 'g-titulo', tabindex: '-1' }, gd.titulo)),
            gd.subtitulo ? h('p', { class: 'g-sub' }, gd.subtitulo) : null,
            gd.resumen ? h('p', { class: 'g-resumen' }, gd.resumen) : null,
            h('ul', { class: 'g-meta', 'aria-label': 'Datos de la guía' },
                h('li', null, ico('reloj'), `${gd.tiempo} min de lectura`),
                h('li', null, ico('capas'), `${gd.secciones.length} secciones`),
                h('li', { id: 'gProg' })),
            h('div', { class: 'g-acciones' },
                gd.ruta ? h('a', { class: 'btn btn-c', href: gd.ruta }, h('span', null, 'Abrir el módulo'), ico('abrir')) : null,
                h('a', { class: 'btn btn-sec', id: 'gContinuar', href: '#' + gd.id, hidden: true }, h('span', null, 'Continuar leyendo'), ico('der'))),
            roles.length ? h('section', { class: 'g-roles', 'aria-labelledby': 'tRoles' }, h('h2', { id: 'tRoles' }, 'Qué puede hacer cada rol'),
                h('dl', null, roles.map(([k, v]) => h('div', null, h('dt', null, k), h('dd', null, v))))) : null);
    }
    function pieGuia(gd) {
        const out = [];
        const rel = gd.relacionadas.map(meta).filter(Boolean).filter((m) => m.id !== gd.id);
        if (rel.length) out.push(h('section', { class: 'g-rel', 'aria-labelledby': 'tRel' }, h('h2', { id: 'tRel', class: 'eyebrow' }, 'Guías relacionadas'),
            h('ul', { class: 'tarjetas chicas' }, rel.map((m) => h('li', null, tarjeta(m))))));
        const i = indice.guias.findIndex((m) => m.id === gd.id);
        const ant = i > 0 ? indice.guias[i - 1] : null, sig = i >= 0 && i < indice.guias.length - 1 ? indice.guias[i + 1] : null;
        if (ant || sig) out.push(h('nav', { class: 'g-vecinas', 'aria-label': 'Otras guías' },
            ant ? h('a', { class: 'vecina ant', href: '#' + ant.id, style: { '--c': ant.color } }, h('span', { class: 'v-et' }, ico('izq'), 'Anterior'), h('b', null, ant.titulo)) : h('span'),
            sig ? h('a', { class: 'vecina sig', href: '#' + sig.id, style: { '--c': sig.color } }, h('span', { class: 'v-et' }, 'Siguiente', ico('der')), h('b', null, sig.titulo)) : h('span')));
        return out;
    }
    async function pintarGuia(id) {
        const token = (estado.token = (estado.token || 0) + 1);
        const m = meta(id);
        vista.replaceChildren(h('div', { class: 'cargando', role: 'status' }, h('span', { class: 'giro', 'aria-hidden': 'true' }), 'Cargando la guía…'));
        const gd = recordar(id, await cargarGuia(id));
        if (token !== estado.token) return false;
        estado.vista = 'guia'; estado.spyActual = null;
        const pos = m ? { i: indice.guias.indexOf(m) + 1, t: indice.guias.length } : null;
        if (!gd) {
            estado.guia = m ? { id, secciones: [] } : null;
            document.title = (m ? m.titulo : 'Guía no encontrada') + ' · Manual de usuario';
            document.documentElement.style.setProperty('--c', m ? m.color : '#FF2E88');
            const art = h('article', { class: 'guia', style: { '--c': m ? m.color : '#FF2E88' } },
                h('header', { class: 'g-cab' },
                    h('p', { class: 'g-grupo' }, m ? 'En preparación' : 'Sin resultados'),
                    h('div', { class: 'g-tit' }, h('span', { class: 'g-ico' }, ico(m ? m.icono : 'libro')), h('h1', { class: 'g-titulo', tabindex: '-1' }, m ? m.titulo : 'No encontramos esa guía')),
                    m && m.subtitulo ? h('p', { class: 'g-sub' }, m.subtitulo) : null),
                h('div', { class: 'vacio' }, ico(m ? 'reloj' : 'buscar'),
                    h('h2', null, m ? 'Esta guía está en preparación' : 'El enlace no lleva a ninguna guía'),
                    h('p', null, m ? 'El equipo la está escribiendo. Mientras tanto, revisa las demás guías del manual.' : 'Revisa el enlace o elige una guía en la lista.'),
                    h('a', { class: 'btn btn-c', href: '#' }, h('span', null, 'Ir al inicio del manual'))),
                m ? pieGuia({ id, relacionadas: [] }) : null);
            vista.replaceChildren(art);
            pintarLateral();
            return true;
        }
        estado.guia = gd;
        estado.galeria = galeriaDe(gd);
        document.title = gd.titulo + ' · Manual de usuario';
        document.documentElement.style.setProperty('--c', gd.color);
        const secciones = gd.secciones.map((s, i) => {
            let cuerpo;
            switch (s.tipo) {
                case 'pasos': cuerpo = [bloquesTexto(s), secPasos(s, gd)]; break;
                case 'ficha': cuerpo = [bloquesTexto(s), secFicha(s)]; break;
                case 'faq': cuerpo = [bloquesTexto(s), secFaq(s)]; break;
                case 'glosario': cuerpo = [bloquesTexto(s), secGlosario(s)]; break;
                default: cuerpo = bloquesTexto(s);
            }
            const el = h('section', { class: 'sec tipo-' + idSeguro(s.tipo, 'texto'), id: 'sec-' + s.id, 'data-sec': s.id, 'aria-labelledby': 'h-' + s.id },
                h('header', { class: 'sec-cab' },
                    h('span', { class: 'sec-num', 'aria-hidden': 'true' }, dos(i + 1)),
                    h('h2', { id: 'h-' + s.id, tabindex: '-1' }, s.titulo),
                    h('a', { class: 'sec-ancla', href: `#${gd.id}/${s.id}`, 'aria-label': 'Enlace directo a ' + s.titulo, title: 'Enlace directo a esta sección' }, ico('enlace'))),
                cuerpo,
                s.cap ? figura(s.cap, s.gi) : null,
                h('footer', { class: 'sec-pie' }, botonLeido(gd, s)));
            return el;
        });
        const barra = h('div', { class: 'g-barra' },
            h('button', { type: 'button', class: 'g-barra-btn', 'aria-label': 'Ver secciones de la guía', onclick: () => cajon(true) }, ico('menu')),
            h('span', { class: 'g-barra-t', id: 'gBarraT' }, gd.titulo),
            h('span', { class: 'g-barra-av', 'aria-hidden': 'true' }, h('i', { id: 'gBarraAv' })));
        const art = h('article', { class: 'guia', style: { '--c': gd.color } }, barra, cabecera(gd, m, pos),
            gd.secciones.length ? secciones : h('div', { class: 'vacio' }, ico('reloj'), h('h2', null, 'Esta guía aún no tiene secciones'), h('p', null, 'Vuelve pronto.')),
            pieGuia(gd));
        vista.replaceChildren(art);
        actualizarCabProgreso(gd);
        pintarLateral();
        if (gs) gs.from('.g-cab > *', { y: 22, opacity: 0, duration: .6, stagger: .06, ease: 'power3.out', clearProps: 'all' });
        return true;
    }

    // ---------- índice de secciones: resalta la visible ----------
    function resaltarToc(sid) {
        $$('.toc-a', lateral).forEach((a) => { const on = a.dataset.sec === sid; a.classList.toggle('activa', on); if (on) a.setAttribute('aria-current', 'location'); else a.removeAttribute('aria-current'); });
    }
    let spyRaf = 0;
    function spy() {
        spyRaf = 0;
        if (estado.vista !== 'guia' || !estado.guia || !estado.guia.secciones) return;
        const secs = $$('.sec', vista); if (!secs.length) return;
        const lineaY = 70 + innerHeight * 0.22;
        let act = null;
        for (const s of secs) { if (s.getBoundingClientRect().top <= lineaY) act = s; else break; }
        if (innerHeight + scrollY >= document.documentElement.scrollHeight - 4) act = secs[secs.length - 1];
        const sid = act ? act.dataset.sec : null;
        const doc = document.documentElement, total = doc.scrollHeight - innerHeight;
        const av = $('#gBarraAv'); if (av) av.style.width = (total > 0 ? Math.round((scrollY / total) * 100) : 0) + '%';
        if (sid === estado.spyActual) return;
        estado.spyActual = sid;
        resaltarToc(sid);
        const t = $('#gBarraT');
        if (t) { const i = estado.guia.secciones.findIndex((s) => s.id === sid); t.textContent = i >= 0 ? `${dos(i + 1)} · ${estado.guia.secciones[i].titulo}` : estado.guia.titulo; }
        const nuevo = '#' + estado.guia.id + (sid ? '/' + sid : '');
        if (location.hash !== nuevo && !estado.busqueda) { try { history.replaceState(null, '', nuevo); } catch (e) { /* sin history */ } }
    }
    addEventListener('scroll', () => { if (!spyRaf) spyRaf = requestAnimationFrame(spy); }, { passive: true });
    addEventListener('resize', () => { if (!spyRaf) spyRaf = requestAnimationFrame(spy); });

    function irASeccion(sid, paso, suave) {
        const el = sid ? document.getElementById('sec-' + sid) : null;
        if (!el) { window.scrollTo({ top: 0, behavior: 'auto' }); const t = $('.g-titulo, .m-titulo', vista); if (t) t.focus({ preventScroll: true }); return; }
        const p = $('.pasos', el);
        if (p && p.irAPaso && paso > 0) p.irAPaso(paso - 1);
        const off = escritorio.matches ? 84 : 124;
        window.scrollTo({ top: el.getBoundingClientRect().top + scrollY - off, behavior: suave && !reducir ? 'smooth' : 'auto' });
        $('h2', el).focus({ preventScroll: true });
        estado.spyActual = null; spy();
    }

    // ---------- búsqueda en todas las guías ----------
    let entradas = null;
    function construirEntradas(guias) {
        const E = [];
        const capTxt = (c) => (c ? [c.alt, ...c.marcas.map((m) => m.texto)] : []);
        guias.forEach((g) => {
            if (!g) return;
            const push = (s, paso, titulo, partes) => { const texto = partes.filter(Boolean).join(' · '); E.push({ g, s, paso, titulo, texto, nt: norm(titulo), nx: norm(texto) }); };
            push('', 0, g.titulo, [g.subtitulo, g.resumen, ...Object.values(g.roles).map(txt)]);
            g.secciones.forEach((s) => {
                const r = s.raw;
                const extra = [];
                arr(r.filas).forEach((f) => extra.push((Array.isArray(f) ? f : obj(f) ? Object.values(f) : [f]).map(txt).join(': ')));
                arr(r.items).filter(obj).forEach((it) => extra.push(txt(it.p), ...parrafos(it.r)));
                arr(r.terminos).filter(obj).forEach((t) => extra.push(txt(t.t) + ': ' + txt(t.d)));
                push(s.id, 0, s.titulo, [s.intro, ...s.parrafos, ...parrafos(r.lista), ...extra, ...capTxt(s.cap)]);
                s.pasos.forEach((p, k) => push(s.id, k + 1, `${s.titulo} › Paso ${k + 1}${p.titulo ? ': ' + p.titulo : ''}`, [p.texto, p.nota, ...capTxt(p.cap)]));
            });
        });
        return E;
    }
    function resaltar(texto, terms) {
        const n = norm(texto);
        if (n.length !== texto.length) return [texto];
        const rangos = [];
        terms.forEach((t) => { let i = n.indexOf(t); while (i >= 0 && t) { rangos.push([i, i + t.length]); i = n.indexOf(t, i + t.length); } });
        rangos.sort((a, b) => a[0] - b[0]);
        const out = []; let pos = 0;
        rangos.forEach(([a, b]) => { if (a < pos) return; if (a > pos) out.push(texto.slice(pos, a)); out.push(h('mark', null, texto.slice(a, b))); pos = b; });
        if (pos < texto.length) out.push(texto.slice(pos));
        return out;
    }
    function fragmento(e, terms) {
        const t = e.texto;
        if (!t) return '';
        let i = -1; for (const x of terms) { const k = e.nx.indexOf(x); if (k >= 0 && (i < 0 || k < i)) i = k; }
        if (i < 0) return t.length > 170 ? t.slice(0, 170) + '…' : t;
        const a = Math.max(0, i - 60), b = Math.min(t.length, i + 130);
        return (a > 0 ? '…' : '') + t.slice(a, b) + (b < t.length ? '…' : '');
    }
    let buscarT = 0;
    q.addEventListener('input', () => { clearTimeout(buscarT); buscarT = setTimeout(buscar, 140); });
    q.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && q.value) { e.preventDefault(); e.stopPropagation(); q.value = ''; buscar(); }
        if (e.key === 'Enter') { e.preventDefault(); if (!escritorio.matches) { cajon(false); } const r = $('.res-a', vista); if (r && escritorio.matches) r.focus(); }
    });
    $('#qLimpiar').addEventListener('click', () => { q.value = ''; buscar(); q.focus(); });
    async function buscar() {
        const texto = q.value.trim();
        $('#qLimpiar').hidden = !texto;
        const terms = norm(texto).split(/\s+/).filter((x) => x.length >= 2);
        if (!terms.length) {
            if (estado.busqueda) { estado.busqueda = ''; estado.coincidencias = null; await ruta(true); }
            return;
        }
        const primera = !estado.busqueda;
        estado.busqueda = texto;
        if (!entradas) { const gs2 = await cargarTodas(); indice.guias.forEach((m, i) => recordar(m.id, gs2[i])); entradas = construirEntradas(gs2); }
        if (q.value.trim() !== texto) return;
        const res = entradas.map((e) => {
            if (!terms.every((t) => e.nt.includes(t) || e.nx.includes(t))) return null;
            const score = terms.reduce((a, t) => a + (e.nt.includes(t) ? 3 : 0) + (e.nx.includes(t) ? 1 : 0), 0) + (e.s ? 0 : 2);
            return { e, score };
        }).filter(Boolean);
        const porGuia = new Map();
        res.forEach((r) => { const k = r.e.g.id; if (!porGuia.has(k)) porGuia.set(k, []); porGuia.get(k).push(r); });
        estado.coincidencias = [...porGuia.keys()];
        estado.vista = 'buscar';
        const orden = indice.guias.map((m) => m.id).filter((id) => porGuia.has(id)).concat([...porGuia.keys()].filter((id) => !meta(id)));
        const lista = orden.map((id) => {
            const rs = porGuia.get(id).sort((a, b) => b.score - a.score).slice(0, 8), g = rs[0].e.g;
            return h('section', { class: 'res-guia', style: { '--c': g.color } },
                h('h2', null, h('span', { class: 'lat-punto', 'aria-hidden': 'true' }), g.titulo, h('span', { class: 'res-n' }, `${porGuia.get(id).length}`)),
                h('ul', null, rs.map(({ e }) => h('li', null, h('a', { class: 'res-a', href: '#' + g.id + (e.s ? '/' + e.s + (e.paso ? '/' + e.paso : '') : '') },
                    h('span', { class: 'res-t' }, e.s ? resaltar(e.titulo, terms) : 'Inicio de la guía'),
                    h('span', { class: 'res-f' }, resaltar(fragmento(e, terms), terms)))))));
        });
        vista.replaceChildren(h('div', { class: 'resultados' },
            h('p', { class: 'eyebrow' }, 'Búsqueda'),
            h('h1', { class: 'res-titulo' }, `Resultados para «${texto}»`),
            h('p', { class: 'res-total', role: 'status' }, res.length ? `${res.length} coincidencia${res.length === 1 ? '' : 's'} en ${porGuia.size} guía${porGuia.size === 1 ? '' : 's'}` : ''),
            res.length ? lista : h('div', { class: 'vacio' }, ico('buscar'), h('h2', null, `No hay resultados para «${texto}»`),
                h('p', null, 'Prueba con otra palabra, por ejemplo «lote», «QR» o «permisos».'),
                h('button', { type: 'button', class: 'btn btn-sec', onclick: () => { q.value = ''; buscar(); q.focus(); } }, 'Limpiar búsqueda'))));
        pintarLateral();
        if (primera) window.scrollTo({ top: 0, behavior: 'auto' });
    }

    // ---------- visor a pantalla completa con zoom ----------
    const V = { el: $('#visor'), lienzo: $('#vLienzo'), capa: $('#vCapa'), lista: $('#vMarcas'), titulo: $('#vTitulo'), cont: $('#vCont'), zoom: $('#vZoom'),
        i: 0, s: 1, tx: 0, ty: 0, fw: 0, fh: 0, desde: null, ptrs: new Map(), pinch: null, ini: null };
    function abrirVisor(i, desde) {
        if (!estado.galeria[i]) return;
        V.i = i; V.desde = desde;
        if (!V.el.open) { V.el.showModal(); document.body.classList.add('sin-scroll'); }
        pintarVisor();
        if (gs) gs.from(V.capa, { opacity: 0, scale: .96, duration: .35, ease: 'power2.out', clearProps: 'opacity' });
    }
    function pintarVisor() {
        const it = estado.galeria[V.i]; if (!it) return;
        const cap = it.cap;
        V.titulo.textContent = it.titulo + (cap.alt ? ' — ' + cap.alt : '');
        V.cont.textContent = `${V.i + 1} / ${estado.galeria.length}`;
        const img = h('img', { src: cap.src, alt: cap.alt, width: cap.ancho, height: cap.alto, draggable: 'false' });
        V.capa.replaceChildren(img);
        V.lista.replaceChildren();
        crearMarcas(cap, V.capa, V.lista, true);
        V.lista.hidden = !cap.marcas.length;
        const varias = estado.galeria.length > 1;
        $('#vAnt').disabled = !varias || V.i === 0; $('#vSig').disabled = !varias || V.i === estado.galeria.length - 1;
        V.s = 1; V.tx = 0; V.ty = 0;
        medir();
    }
    function medir() {
        const it = estado.galeria[V.i]; if (!it || !V.el.open) return;
        const r = V.lienzo.getBoundingClientRect(), ar = it.cap.ancho / it.cap.alto, pad = innerWidth < 600 ? 8 : 32;
        let w = Math.max(50, r.width - pad * 2), hh = Math.max(50, r.height - pad * 2);
        if (w / hh > ar) w = hh * ar; else hh = w / ar;
        V.fw = w; V.fh = hh;
        Object.assign(V.capa.style, { width: w + 'px', height: hh + 'px', marginLeft: -w / 2 + 'px', marginTop: -hh / 2 + 'px' });
        aplicar();
    }
    function aplicar() {
        const r = V.lienzo.getBoundingClientRect();
        const mx = Math.max(0, (V.fw * V.s - r.width) / 2 + 24), my = Math.max(0, (V.fh * V.s - r.height) / 2 + 24);
        if (V.s <= 1) { V.tx = 0; V.ty = 0; } else { V.tx = lim(V.tx, -mx, mx); V.ty = lim(V.ty, -my, my); }
        V.capa.style.transform = `translate(${V.tx}px, ${V.ty}px) scale(${V.s})`;
        V.capa.style.setProperty('--s', V.s);
        V.zoom.textContent = Math.round(V.s * 100) + ' %';
        V.lienzo.classList.toggle('con-zoom', V.s > 1);
        $('#vMenos').disabled = V.s <= 1; $('#vMas').disabled = V.s >= 5;
    }
    function puntoCentro(cx, cy) { const r = V.lienzo.getBoundingClientRect(); return [cx - (r.left + r.width / 2), cy - (r.top + r.height / 2)]; }
    function zoomA(s2, qx = 0, qy = 0) {
        s2 = lim(s2, 1, 5);
        const k = s2 / V.s;
        V.tx = qx - k * (qx - V.tx); V.ty = qy - k * (qy - V.ty); V.s = s2;
        aplicar();
    }
    function cambiar(d) { const n = V.i + d; if (n < 0 || n >= estado.galeria.length) return; V.i = n; pintarVisor(); if (gs) gs.from(V.capa, { opacity: 0, x: d * 40, duration: .3, ease: 'power2.out', clearProps: 'opacity' }); anunciar(`Captura ${V.i + 1} de ${estado.galeria.length}`); }
    $('#vCerrar').addEventListener('click', () => V.el.close());
    $('#vMas').addEventListener('click', () => zoomA(V.s * 1.4));
    $('#vMenos').addEventListener('click', () => zoomA(V.s / 1.4));
    $('#vAjustar').addEventListener('click', () => zoomA(1));
    $('#vAnt').addEventListener('click', () => cambiar(-1));
    $('#vSig').addEventListener('click', () => cambiar(1));
    V.el.addEventListener('close', () => {
        document.body.classList.remove('sin-scroll');
        V.capa.replaceChildren();
        if (V.desde && V.desde.isConnected) V.desde.focus();
    });
    V.el.addEventListener('keydown', (e) => {
        const paso = 70;
        if (e.key === '+' || e.key === '=') { e.preventDefault(); zoomA(V.s * 1.4); }
        else if (e.key === '-' || e.key === '_') { e.preventDefault(); zoomA(V.s / 1.4); }
        else if (e.key === '0') { e.preventDefault(); zoomA(1); }
        else if (e.key === 'ArrowLeft') { e.preventDefault(); if (V.s > 1) { V.tx += paso; aplicar(); } else cambiar(-1); }
        else if (e.key === 'ArrowRight') { e.preventDefault(); if (V.s > 1) { V.tx -= paso; aplicar(); } else cambiar(1); }
        else if (e.key === 'ArrowUp' && V.s > 1) { e.preventDefault(); V.ty += paso; aplicar(); }
        else if (e.key === 'ArrowDown' && V.s > 1) { e.preventDefault(); V.ty -= paso; aplicar(); }
    });
    V.lienzo.addEventListener('wheel', (e) => { e.preventDefault(); const [x, y] = puntoCentro(e.clientX, e.clientY); zoomA(V.s * Math.exp(-e.deltaY * 0.0018), x, y); }, { passive: false });
    V.lienzo.addEventListener('dblclick', (e) => { if (e.target.closest('.marca')) return; const [x, y] = puntoCentro(e.clientX, e.clientY); zoomA(V.s > 1 ? 1 : 2.5, x, y); });
    V.lienzo.addEventListener('pointerdown', (e) => {
        if (e.target.closest('.marca')) return;
        V.lienzo.setPointerCapture(e.pointerId);
        V.ptrs.set(e.pointerId, { x: e.clientX, y: e.clientY });
        if (V.ptrs.size === 1) V.ini = { x: e.clientX, y: e.clientY, t: Date.now() };
        if (V.ptrs.size === 2) { const [a, b] = [...V.ptrs.values()]; V.pinch = { d: Math.hypot(a.x - b.x, a.y - b.y) || 1, s: V.s }; V.ini = null; }
    });
    V.lienzo.addEventListener('pointermove', (e) => {
        const prev = V.ptrs.get(e.pointerId); if (!prev) return;
        const cur = { x: e.clientX, y: e.clientY }; V.ptrs.set(e.pointerId, cur);
        if (V.ptrs.size === 2 && V.pinch) {
            const [a, b] = [...V.ptrs.values()];
            const [x, y] = puntoCentro((a.x + b.x) / 2, (a.y + b.y) / 2);
            zoomA(V.pinch.s * (Math.hypot(a.x - b.x, a.y - b.y) / V.pinch.d), x, y);
        } else if (V.ptrs.size === 1 && V.s > 1) { V.tx += cur.x - prev.x; V.ty += cur.y - prev.y; aplicar(); }
    });
    const finPuntero = (e) => {
        if (!V.ptrs.has(e.pointerId)) return;
        V.ptrs.delete(e.pointerId);
        if (V.ptrs.size < 2) V.pinch = null;
        if (V.ini && V.s <= 1 && V.ptrs.size === 0) {
            const dx = e.clientX - V.ini.x, dy = e.clientY - V.ini.y;
            if (Math.abs(dx) > 60 && Math.abs(dx) > Math.abs(dy) * 1.5 && Date.now() - V.ini.t < 700) cambiar(dx < 0 ? 1 : -1);
        }
        if (!V.ptrs.size) V.ini = null;
    };
    V.lienzo.addEventListener('pointerup', finPuntero);
    V.lienzo.addEventListener('pointercancel', finPuntero);
    addEventListener('resize', () => { if (V.el.open) medir(); });

    // ---------- rutas: #guia, #guia/seccion, #guia/seccion/paso ----------
    function leerHash() {
        let raw = location.hash.replace(/^#/, '');
        try { raw = decodeURIComponent(raw); } catch (e) { /* hash mal formado */ }
        const [g = '', s = '', p = ''] = raw.split('/');
        return { g: idSeguro(g, ''), s: idSeguro(s, ''), p: parseInt(p, 10) || 0 };
    }
    async function ruta(forzar) {
        if (!indice) return;
        if (V.el.open) V.el.close();
        if (estado.busqueda && !forzar) { estado.busqueda = ''; estado.coincidencias = null; q.value = ''; $('#qLimpiar').hidden = true; forzar = true; }
        const { g, s, p } = leerHash();
        if (!g) { if (forzar || estado.vista !== 'inicio') { pintarInicio(); } window.scrollTo({ top: 0, behavior: 'auto' }); const t = $('.m-titulo'); if (t && document.activeElement !== q) t.focus({ preventScroll: true }); return; }
        const nueva = forzar || estado.vista !== 'guia' || !estado.guia || estado.guia.id !== g;
        if (nueva) { const ok = await pintarGuia(g); if (!ok) return; }
        if (document.activeElement === q) { if (s) irASeccion(s, p, false); else window.scrollTo({ top: 0, behavior: 'auto' }); q.focus(); return; }
        if (nueva) requestAnimationFrame(() => irASeccion(s, p, false)); else irASeccion(s, p, true);
    }
    addEventListener('hashchange', () => ruta(false));
    // un enlace al mismo hash no dispara hashchange (p. ej. tras actualizarlo al hacer scroll): se navega igual
    document.addEventListener('click', (e) => {
        const a = e.target.closest('a[href^="#"]');
        if (!a || e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey) return;
        const href = a.getAttribute('href');
        if (href === location.hash || (href === '#' && !location.hash)) { e.preventDefault(); ruta(!!estado.busqueda); }
    });

    // ---------- arranque ----------
    async function iniciar() {
        try {
            const r = await fetch(BASE + 'guias/indice.json', { cache: 'no-cache', credentials: 'same-origin' });
            if (!r.ok) throw new Error(String(r.status));
            indice = normIndice(await r.json());
        } catch (e) {
            vista.replaceChildren(h('div', { class: 'vacio' }, ico('info'), h('h1', null, 'No se pudo cargar el manual'),
                h('p', null, 'Revisa tu conexión y vuelve a intentarlo. Si sigue igual, avisa al equipo de hardware.'),
                h('button', { type: 'button', class: 'btn btn-c', onclick: () => location.reload() }, 'Reintentar')));
            return;
        }
        $('#lateral').setAttribute('aria-busy', 'false');
        pintarLateral();
        await ruta(true);
        cargarTodas().then((gs2) => { indice.guias.forEach((m, i) => recordar(m.id, gs2[i])); pintarLateral(); });
    }
    iniciar();
})();
