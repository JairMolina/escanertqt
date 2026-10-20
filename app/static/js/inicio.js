/* inicio.js - Portal de módulos (/inicio). Público: no usa common.js (que necesita sesión) ni otras dependencias.
   Constelación: el núcleo "TQT" al centro y los módulos como estrellas en órbitas elípticas unidas por trazas.
   - Datos: GET /api/modulos (público). Estado del servidor: GET /api/health cada 30 s.
   - Órbitas con requestAnimationFrame; se pausan con la pestaña oculta y, por órbita, con hover/foco en una estrella.
   - prefers-reduced-motion: sin órbitas ni parallax (posiciones fijas). ≤640 px o pantallas bajas: lista vertical, sin órbitas. */
(function () {
    'use strict';
    var $ = function (id) { return document.getElementById(id); };
    var NS = 'http://www.w3.org/2000/svg';
    var TAU = Math.PI * 2;
    var mqLista = matchMedia('(max-width: 640px), (max-height: 540px)');   // mismo criterio que el CSS ("modo lista")
    var mqQuieto = matchMedia('(prefers-reduced-motion: reduce)');
    var lista = mqLista.matches, quieto = mqQuieto.matches;

    var ICONOS = {
        chip: '<rect x="6" y="6" width="12" height="12" rx="2"/><path d="M9 3v3M15 3v3M9 18v3M15 18v3M3 9h3M3 15h3M18 9h3M18 15h3"/><path d="M9.5 12h2l1-2 1 4 1-2h.5"/>',
        caja: '<path d="M3 7.5 12 3l9 4.5v9L12 21l-9-4.5z"/><path d="M3 7.5 12 12l9-4.5M12 12v9"/>',
        escudo: '<path d="M12 3 4.5 6v5.5c0 4.5 3 8 7.5 9.5 4.5-1.5 7.5-5 7.5-9.5V6z"/><path d="m8.8 12 2.4 2.4 4-4.4"/>',
        grafica: '<path d="M4 20V4M4 20h16"/><path d="m7.5 15 3.5-4 3 2.5 4.5-6"/>',
        sol: '<circle cx="12" cy="12" r="4"/><path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6 7 7M17 17l1.4 1.4M5.6 18.4 7 17M17 7l1.4-1.4"/>',
        luna: '<path d="M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5z"/>'
    };
    var ESTADOS = { disponible: 'Disponible', proximamente: 'Próximamente', mantenimiento: 'En mantenimiento' };

    function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
    function r1(n) { return Math.round(n * 10) / 10; }
    function acentoOk(a) { return typeof a === 'string' && /^#[0-9a-f]{3,8}$/i.test(a) ? a : '#D9A441'; }
    /* Solo rutas internas (nunca otro sitio): evita redirecciones abiertas. */
    function destino(u) { return typeof u === 'string' && u.charAt(0) === '/' && u.charAt(1) !== '/' && u.indexOf('\\') < 0 ? u : null; }

    var escena = $('escena'), listaEl = $('lista'), ficha = $('ficha');

    /* ================= tema claro / oscuro (mismo ajuste `tqt.tema` que el resto de la app) ================= */
    function pintarTema() {
        var claro = document.documentElement.dataset.theme === 'light';
        $('icoTema').innerHTML = claro ? ICONOS.luna : ICONOS.sol;   // el icono muestra a qué tema se cambia
        var m = document.querySelector('meta[name="theme-color"]'); if (m) m.setAttribute('content', claro ? '#E9ECF1' : '#0A1020');
        $('tema').setAttribute('aria-pressed', String(claro));
    }
    $('tema').addEventListener('click', function () {
        var n = document.documentElement.dataset.theme === 'light' ? 'dark' : 'light';
        document.documentElement.dataset.theme = n;
        try { localStorage.setItem('tqt.tema', n); } catch (e) { /* sin almacenamiento */ }
        pintarTema(); leerColores(); if (!corriendo()) pintarCampo(0);
    });
    pintarTema();

    /* ================= saludo, fecha y reloj ================= */
    var ultMin = '';
    function reloj() {
        var d = new Date(), h = d.getHours(), m = d.getMinutes();
        var hm = (h < 10 ? '0' : '') + h + ':' + (m < 10 ? '0' : '') + m;
        if (hm === ultMin) return;
        ultMin = hm;
        $('reloj').textContent = hm;
        $('hola').textContent = h < 6 ? 'Buenas noches' : h < 12 ? 'Buenos días' : h < 19 ? 'Buenas tardes' : 'Buenas noches';
        try { $('fecha').textContent = d.toLocaleDateString('es-MX', { weekday: 'long', day: 'numeric', month: 'long' }); } catch (e) { $('fecha').textContent = d.toLocaleDateString(); }
    }
    reloj(); setInterval(function () { if (!document.hidden) reloj(); }, 1000);

    /* ================= pulso del servidor (público) ================= */
    function salud() {
        if (document.hidden) return;
        fetch('/api/health', { cache: 'no-store' }).then(function (r) { return r.ok; }, function () { return false; }).then(function (ok) {
            $('punto').dataset.s = ok ? 'on' : 'off';
            $('srvTxt').textContent = ok ? 'Servidor en línea' : 'Sin conexión con el servidor';
        });
    }
    salud(); setInterval(salud, 30000);

    /* ================= campo de estrellas (canvas de fondo, parallax leve) ================= */
    var cv = $('campo'), cx2 = cv.getContext('2d');
    var W = 0, H = 0, dpr = 1, fondo = [], par = { x: 0, y: 0, tx: 0, ty: 0 };
    var col = { t: '#E9EEF5', a: '#D9A441', i: '#5AA9FF', claro: false };
    function leerColores() {
        var cs = getComputedStyle(document.documentElement), claro = document.documentElement.dataset.theme === 'light';
        col.claro = claro;
        col.t = cs.getPropertyValue(claro ? '--line-2' : '--text').trim() || (claro ? '#69758F' : '#E9EEF5');
        col.a = cs.getPropertyValue(claro ? '--accent-text' : '--accent').trim() || '#D9A441';
        col.i = cs.getPropertyValue('--info').trim() || '#5AA9FF';
    }
    function ajustarCampo() {
        var w = innerWidth, h = innerHeight;
        if (w === W && Math.abs(h - H) < 100) return;       // la barra de direcciones del móvil cambia la altura: no rehacer por eso
        W = w; H = h; dpr = Math.min(window.devicePixelRatio || 1, 2);
        cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr);
        cx2.setTransform(dpr, 0, 0, dpr, 0, 0);
        var n = Math.max(60, Math.min(280, Math.round(W * H / 7500)));
        while (fondo.length < n) fondo.push({ u: Math.random(), v: Math.random(), z: .15 + Math.random() * .85, r: .5 + Math.random() * 1.1, f: Math.random() * TAU, s: .5 + Math.random() * 1.1, k: Math.random() < .1 ? 1 : Math.random() < .12 ? 2 : 0 });
        fondo.length = n;
        if (!corriendo()) pintarCampo(0);
    }
    function pintarCampo(t) {
        cx2.clearRect(0, 0, W, H);
        var ox = par.x * 14, oy = par.y * 14, claro = col.claro, i, s, x, y, a;
        for (i = 0; i < fondo.length; i++) {
            s = fondo[i];
            x = s.u * (W + 48) - 24 + ox * s.z; y = s.v * (H + 48) - 24 + oy * s.z;
            a = claro ? .16 + .34 * s.z : .22 + .66 * s.z;
            if (!quieto) a *= .8 + .2 * Math.sin(t * s.s + s.f);
            cx2.globalAlpha = a; cx2.fillStyle = s.k === 1 ? col.a : s.k === 2 ? col.i : col.t;
            if (claro && s.z > .72) { cx2.fillRect(x - 4, y - .5, 8, 1); cx2.fillRect(x - .5, y - 4, 1, 8); }   // plano técnico: marcas "+"
            else { cx2.beginPath(); cx2.arc(x, y, claro ? s.r * .8 : s.r, 0, TAU); cx2.fill(); }
            if (!claro && s.z > .9) { cx2.globalAlpha = a * .35; cx2.fillRect(x - 5, y - .4, 10, .8); cx2.fillRect(x - .4, y - 5, .8, 10); }
        }
        cx2.globalAlpha = 1;
    }
    addEventListener('pointermove', function (e) {
        if (quieto || e.pointerType === 'touch') return;
        par.tx = (e.clientX / innerWidth - .5) * 2; par.ty = (e.clientY / innerHeight - .5) * 2;
    }, { passive: true });
    document.documentElement.addEventListener('pointerleave', function () { par.tx = 0; par.ty = 0; });

    /* ================= constelación ================= */
    var items = [], orbs = [], aristas = [], lay = { W: 0, H: 0, cx: 0, cy: 0 };
    var act = null, fichaItem = null, fw = 0, fh = 0, entrando = false;
    var st = { hov: null, foc: null, tap: null, esc: false, t: 0, silencio: false };
    var TILT = -0.2;

    function estadoMsg(k, txt, boton) {
        var m = $('msg'); m.dataset.k = k || ''; $('msgTxt').textContent = txt || '';
        var b = $('msgBtn'); b.hidden = !boton; if (boton) b.textContent = boton;
    }
    var tAviso = 0;
    function avisar(txt) {
        var a = $('aviso'); clearTimeout(tAviso); a.textContent = '';
        if (!txt) return;
        setTimeout(function () { a.textContent = txt; }, 40);
        tAviso = setTimeout(function () { a.textContent = ''; }, 5000);
    }

    function construir(mods) {
        // disponibles primero (estable): la estrella principal es la primera y el recorrido con flechas empieza ahí
        var base = mods.map(function (m, i) { return { m: m, i: i }; });
        base.sort(function (a, b) { return (a.m.estado === 'disponible' ? 0 : 1) - (b.m.estado === 'disponible' ? 0 : 1) || a.i - b.i; });
        listaEl.textContent = ''; $('orbitas').textContent = ''; $('lineas').textContent = '';
        items = []; orbs = []; aristas = []; act = null; fichaItem = null;
        st.hov = st.foc = st.tap = null; st.esc = false; ocultarFicha();

        base.forEach(function (b, n) {
            var m = b.m, disp = m.estado === 'disponible', li = document.createElement('li');
            var nombre = esc(m.nombre), estTxt = ESTADOS[m.estado] || esc(m.estado);
            li.className = 'mod'; li.dataset.estado = m.estado;
            li.style.setProperty('--a', acentoOk(m.acento)); li.style.setProperty('--i', n);
            li.innerHTML = '<button class="est" type="button" tabindex="-1" data-i="' + n + '"' + (disp ? '' : ' aria-disabled="true"') + ' aria-labelledby="mn' + n + ' mt' + n + '" aria-describedby="md' + n + '">' +
                '<span class="astro" aria-hidden="true"><i class="halo"></i><i class="onda"></i><svg class="ico" viewBox="0 0 24 24" focusable="false">' + (ICONOS[m.icono] || ICONOS.chip) + '</svg></span>' +
                '<span class="rot"><span class="nom" id="mn' + n + '">' + nombre + '</span><span class="tag" id="mt' + n + '"><i aria-hidden="true"></i>' + estTxt + '</span></span>' +
                '<span class="desc" id="md' + n + '">' + esc(m.descripcion) + '</span>' +
                (disp ? '<span class="go" aria-hidden="true">Entrar</span>' : '') + '</button>';
            listaEl.appendChild(li);
            items.push({ m: m, li: li, btn: li.firstChild, orb: null, off: 0, x: 0, y: 0, acento: acentoOk(m.acento) });
        });

        // dos órbitas: los disponibles (hasta 3) en la interior; el resto en la exterior
        var dentro = items.filter(function (it) { return it.m.estado === 'disponible'; }).slice(0, 3);
        var fuera = items.filter(function (it) { return dentro.indexOf(it) < 0; });
        function orbita(arr, tam, dir, periodo, th0) {
            if (!arr.length) return;
            var el = document.createElementNS(NS, 'ellipse'); $('orbitas').appendChild(el);
            var o = { tam: tam, dir: dir, w: TAU / periodo, v: 1, th: th0, parada: false, rx: 0, ry: 0, el: el };
            arr.forEach(function (it, j) { it.orb = o; it.off = j * TAU / arr.length; });
            orbs.push(o);
        }
        orbita(dentro, 'in', 1, 70, -0.55);
        orbita(fuera, 'out', -1, 110, 2.5);
        if (orbs.length === 1) orbs[0].tam = 'out';

        // trazas tipo PCB: núcleo -> principal -> siguiente -> …
        if (items.length) aristas.push({ a: null, b: items[0] });
        for (var i = 0; i < items.length - 1; i++) aristas.push({ a: items[i], b: items[i + 1] });
        aristas.forEach(function (e, k) {
            var g = document.createElementNS(NS, 'g'), p1 = document.createElementNS(NS, 'path'), p2 = document.createElementNS(NS, 'path');
            g.setAttribute('class', 'lin'); g.style.setProperty('--k', k);
            p1.setAttribute('class', 'base'); p2.setAttribute('class', 'luz');
            p1.setAttribute('pathLength', '1'); p2.setAttribute('pathLength', '1');
            g.appendChild(p1); g.appendChild(p2); $('lineas').appendChild(g);
            e.g = g; e.p1 = p1; e.p2 = p2;
        });

        roving(0);
        calcular(); colocar();
    }

    function roving(i) { items.forEach(function (it, k) { it.btn.tabIndex = k === i ? 0 : -1; }); }

    /* Tamaño de las órbitas según el espacio disponible (sin desbordar entre 375 y 1920 px). */
    function calcular() {
        var w = escena.clientWidth, h = escena.clientHeight;
        if (!w || !h) return;
        lay.W = w; lay.H = h; lay.cx = w / 2; lay.cy = h / 2 - 12;
        escena.style.setProperty('--cy', r1(lay.cy) + 'px');
        if (lista || !orbs.length) return;
        var ratio = .46, c = Math.cos(TILT), s = Math.sin(TILT);
        var hw1 = Math.sqrt(c * c + ratio * ratio * s * s), hh1 = Math.sqrt(s * s + ratio * ratio * c * c);
        var rx = Math.min((w / 2 - 88) / hw1, Math.min(lay.cy - 46, h - lay.cy - 74) / hh1, 640);
        rx = Math.max(rx, 150);
        var ry = rx * ratio, k = Math.max(.5, Math.min(.8, 104 / ry));
        orbs.forEach(function (o) {
            o.rx = o.tam === 'in' ? rx * k : rx; o.ry = o.tam === 'in' ? ry * k : ry;
            o.el.setAttribute('cx', r1(lay.cx)); o.el.setAttribute('cy', r1(lay.cy));
            o.el.setAttribute('rx', r1(o.rx)); o.el.setAttribute('ry', r1(o.ry));
            o.el.setAttribute('transform', 'rotate(' + r1(TILT * 180 / Math.PI) + ' ' + r1(lay.cx) + ' ' + r1(lay.cy) + ')');
        });
        if (fichaItem) medirFicha();
    }

    function colocar() {
        if (lista) { items.forEach(function (it) { it.li.style.transform = ''; }); return; }
        var c = Math.cos(TILT), s = Math.sin(TILT);
        items.forEach(function (it) {
            var o = it.orb, a = o.th + it.off, ex = o.rx * Math.cos(a), ey = o.ry * Math.sin(a);
            it.x = lay.cx + ex * c - ey * s; it.y = lay.cy + ex * s + ey * c;
            it.li.style.transform = 'translate3d(' + r1(it.x) + 'px,' + r1(it.y) + 'px,0)';
        });
        aristas.forEach(function (e) {
            var d = traza(e.a || { x: lay.cx, y: lay.cy }, e.b);
            e.p1.setAttribute('d', d); e.p2.setAttribute('d', d);
        });
        if (fichaItem && ficha.dataset.abierta === 'true') posFicha();
    }

    /* Traza ortogonal con quiebre a 45 grados, como una pista de PCB. */
    function traza(a, b) {
        var dx = b.x - a.x, dy = b.y - a.y, ax = Math.abs(dx), ay = Math.abs(dy), p = 'M' + r1(a.x) + ' ' + r1(a.y);
        if (ax >= ay) return p + 'H' + r1(a.x + (dx < 0 ? -1 : 1) * (ax - ay)) + 'L' + r1(b.x) + ' ' + r1(b.y);
        return p + 'V' + r1(a.y + (dy < 0 ? -1 : 1) * (ay - ax)) + 'L' + r1(b.x) + ' ' + r1(b.y);
    }

    /* ---- ficha de detalle ---- */
    function medirFicha() { fw = ficha.offsetWidth; fh = ficha.offsetHeight; }
    function posFicha() {
        var it = fichaItem, w = fw, h = fh, W2 = lay.W, H2 = lay.H, gx = 80, x, y;   // 80 px: deja libre la etiqueta de la estrella (hasta 148 px de ancho)
        
        function cabeX(px) { return px >= 8 && px + w <= W2 - 8; }
        function cabeY(py) { return py >= 8 && py + h <= H2 - 8; }
        function clamp(v, mn, mx) { return Math.max(mn, Math.min(mx, v)); }
        var vy = clamp(it.y - h / 2, 8, Math.max(8, H2 - h - 8)), hx = clamp(it.x - w / 2, 8, Math.max(8, W2 - w - 8));
        var R = it.x + gx, L = it.x - gx - w, B = it.y + 62, A = it.y - 46 - h;
        var lados = it.x >= lay.cx ? [['R', R], ['L', L]] : [['L', L], ['R', R]], elegido = null;
        for (var i = 0; i < lados.length && !elegido; i++) if (cabeX(lados[i][1])) elegido = [lados[i][1], vy];
        if (!elegido && cabeY(B)) elegido = [hx, B];
        if (!elegido && cabeY(A)) elegido = [hx, A];
        if (!elegido) elegido = [clamp(lados[0][1], 8, Math.max(8, W2 - w - 8)), vy];
        x = elegido[0]; y = elegido[1];
        ficha.style.transform = 'translate3d(' + Math.round(x) + 'px,' + Math.round(y) + 'px,0)';
    }
    function mostrarFicha(it) {
        if (fichaItem !== it) {
            fichaItem = it; var m = it.m;
            ficha.style.setProperty('--a', it.acento); ficha.dataset.e = m.estado;
            $('fIco').innerHTML = ICONOS[m.icono] || ICONOS.chip;
            $('fNom').textContent = m.nombre; $('fEst').textContent = ESTADOS[m.estado] || m.estado; $('fDesc').textContent = m.descripcion;
            var av = $('fAviso'); av.hidden = m.estado !== 'mantenimiento'; av.textContent = m.estado === 'mantenimiento' ? 'Este módulo está en mantenimiento. Vuelve a intentarlo más tarde.' : '';
            $('fEntrar').hidden = m.estado !== 'disponible';
            medirFicha();
        }
        posFicha(); ficha.dataset.abierta = 'true'; $('fEntrar').tabIndex = 0;
    }
    function ocultarFicha() { ficha.dataset.abierta = 'false'; $('fEntrar').tabIndex = -1; }

    /* ---- estado activo: cursor, foco de teclado o toque ---- */
    function actualizar() {
        var it = st.hov != null ? items[st.hov] : st.tap != null ? items[st.tap] : (st.foc != null && !st.esc ? items[st.foc] : null);
        it = it || null;
        if (it === act) return;
        act = it;
        items.forEach(function (x) { if (x === it) x.btn.setAttribute('data-on', ''); else x.btn.removeAttribute('data-on'); });
        orbs.forEach(function (o) { o.parada = !!(it && it.orb === o); });
        if (it) escena.setAttribute('data-act', ''); else escena.removeAttribute('data-act');
        aristas.forEach(function (e) {
            var on = !!(it && (e.a === it || e.b === it));
            e.g.classList.toggle('on', on); if (on) e.g.style.setProperty('--a', it.acento);
        });
        if (it && !lista) mostrarFicha(it); else ocultarFicha();
    }
    function entrarHover(i) { clearTimeout(st.t); st.hov = i; st.esc = false; actualizar(); }
    function salirHover() { clearTimeout(st.t); st.t = setTimeout(function () { st.hov = null; actualizar(); }, 220); }   // margen para pasar de la estrella a la ficha

    /* ---- abrir un módulo ---- */
    function abrir(it) {
        var m = it.m;
        if (m.estado !== 'disponible') {
            avisar(m.estado === 'mantenimiento' ? m.nombre + ' está en mantenimiento. Vuelve a intentarlo más tarde.' : m.nombre + ' estará disponible próximamente.');
            return;
        }
        var url = destino(m.url);
        if (!url) { avisar('No se pudo abrir ' + m.nombre + '.'); return; }
        if (!m.sesion) { location.href = url; return; }
        if (entrando) return;
        entrando = true; it.btn.setAttribute('data-cargando', ''); avisar('Comprobando tu sesión…');
        fetch('/api/auth/yo', { credentials: 'same-origin', cache: 'no-store' }).then(function (r) {
            location.href = r.ok ? url : '/login?next=' + encodeURIComponent(url);   // 401: a iniciar sesión; después vuelve a "/", que decide rol y dispositivo
        }, function () { location.href = '/login?next=' + encodeURIComponent(url); });
    }
    addEventListener('pageshow', function (e) {
        if (e.persisted) { entrando = false; items.forEach(function (it) { it.btn.removeAttribute('data-cargando'); }); avisar(''); }
    });

    /* ---- eventos de las estrellas (delegados en la lista) ---- */
    function itemDe(el) { var b = el.closest && el.closest('.est'); return b ? items[+b.dataset.i] : null; }
    listaEl.addEventListener('pointerover', function (e) {
        if (e.pointerType === 'touch') return;
        var it = itemDe(e.target); if (it && !it.btn.contains(e.relatedTarget)) entrarHover(items.indexOf(it));
    });
    listaEl.addEventListener('pointerout', function (e) {
        if (e.pointerType === 'touch') return;
        var it = itemDe(e.target); if (it && !it.btn.contains(e.relatedTarget)) salirHover();
    });
    listaEl.addEventListener('click', function (e) {
        var it = itemDe(e.target); if (!it) return;
        if (e.pointerType === 'touch' && !lista && st.tap !== items.indexOf(it)) {    // en tableta el primer toque muestra la ficha; el segundo (o "Entrar") abre
            st.tap = items.indexOf(it); actualizar(); return;
        }
        abrir(it);
    });
    listaEl.addEventListener('focusin', function (e) {
        var it = itemDe(e.target); if (!it) return;
        var i = items.indexOf(it); roving(i);
        if (st.silencio) return;
        var visible = true; try { visible = it.btn.matches(':focus-visible'); } catch (x) { /* navegador viejo: se asume teclado */ }
        st.foc = visible ? i : null; st.esc = false; actualizar();
    });
    listaEl.addEventListener('focusout', function (e) {
        if (e.relatedTarget && (ficha.contains(e.relatedTarget) || listaEl.contains(e.relatedTarget))) return;
        st.foc = null; actualizar();
    });
    ficha.addEventListener('focusout', function (e) {
        if (e.relatedTarget && (ficha.contains(e.relatedTarget) || listaEl.contains(e.relatedTarget))) return;
        st.foc = null; actualizar();
    });
    ficha.addEventListener('pointerenter', function () { clearTimeout(st.t); });
    ficha.addEventListener('pointerleave', function (e) { if (e.pointerType !== 'touch') salirHover(); });
    $('fEntrar').addEventListener('click', function () { if (fichaItem) abrir(fichaItem); });
    document.addEventListener('pointerdown', function (e) {
        if (e.pointerType === 'touch' && st.tap != null && !(e.target.closest && (e.target.closest('.est') || e.target.closest('.ficha')))) { st.tap = null; actualizar(); }
    });

    /* ---- teclado: flechas recorren los módulos (roving tabindex), Enter/Espacio abren (botón nativo), Escape cierra la ficha ---- */
    listaEl.addEventListener('keydown', function (e) {
        var it = itemDe(e.target); if (!it || e.altKey || e.ctrlKey || e.metaKey) return;
        var i = items.indexOf(it), n = items.length, j;
        if (e.key === 'ArrowRight' || e.key === 'ArrowDown') j = (i + 1) % n;
        else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') j = (i - 1 + n) % n;
        else if (e.key === 'Home') j = 0;
        else if (e.key === 'End') j = n - 1;
        else return;
        e.preventDefault(); items[j].btn.focus();
    });
    document.addEventListener('keydown', function (e) {
        if (e.key !== 'Escape' || !act) return;
        var a = act;
        st.hov = null; st.tap = null; st.esc = true;
        if (ficha.contains(document.activeElement)) { st.silencio = true; a.btn.focus(); st.silencio = false; }
        actualizar();
    });

    $('msgBtn').addEventListener('click', cargar);

    function cargar() {
        estadoMsg('carga', 'Cargando módulos…', null); escena.setAttribute('aria-busy', 'true');
        fetch('/api/modulos', { cache: 'no-store' }).then(function (r) {
            if (!r.ok) throw new Error('http ' + r.status);
            return r.json();
        }).then(function (d) {
            var ms = d && Array.isArray(d.modulos) ? d.modulos : [];
            if (!ms.length) { construir([]); estadoMsg('vacio', 'Todavía no hay módulos publicados.', 'Actualizar'); return; }
            construir(ms); estadoMsg('', '', null);
        }).catch(function () {
            construir([]); estadoMsg('error', 'No se pudo cargar la lista de módulos. Revisa la conexión e inténtalo de nuevo.', 'Reintentar');
        }).then(function () { escena.setAttribute('aria-busy', 'false'); arrancar(); });
    }

    /* ================= bucle de animación ================= */
    var raf = 0, ult = 0;
    function corriendo() { return raf !== 0; }
    function bucle(ts) {
        raf = requestAnimationFrame(bucle);
        var dt = Math.min(.1, (ts - ult) / 1000 || 0); ult = ts;
        var k = 1 - Math.exp(-dt * 4);
        par.x += (par.tx - par.x) * k; par.y += (par.ty - par.y) * k;
        if (!lista && orbs.length) {
            var mov = false;
            orbs.forEach(function (o) {
                o.v += ((o.parada ? 0 : 1) - o.v) * (1 - Math.exp(-dt * 9));     // frena y arranca con suavidad
                if (o.v < .002) o.v = 0; else if (o.v > .998) o.v = 1;
                if (o.v > 0) { o.th += o.dir * o.w * o.v * dt; mov = true; }
            });
            if (mov) colocar();
        }
        pintarCampo(ts / 1000);
    }
    function detener() { if (raf) cancelAnimationFrame(raf); raf = 0; }
    function arrancar() {
        detener();
        if (quieto || document.hidden) { par.x = par.y = par.tx = par.ty = 0; colocar(); pintarCampo(0); return; }
        ult = performance.now(); raf = requestAnimationFrame(bucle);
    }
    document.addEventListener('visibilitychange', function () { if (document.hidden) detener(); else { arrancar(); salud(); reloj(); } });
    mqQuieto.addEventListener('change', function () { quieto = mqQuieto.matches; arrancar(); });
    mqLista.addEventListener('change', function () {
        lista = mqLista.matches; st.tap = null; calcular(); colocar(); act = null; actualizar(); arrancar();
    });
    var pendiente = 0;
    function refrescar() {
        if (pendiente) return;
        pendiente = requestAnimationFrame(function () { pendiente = 0; ajustarCampo(); calcular(); colocar(); if (!corriendo()) pintarCampo(0); });
    }
    if (window.ResizeObserver) new ResizeObserver(refrescar).observe(escena);
    addEventListener('resize', refrescar);

    /* ================= arranque ================= */
    leerColores(); ajustarCampo(); pintarCampo(0);
    cargar();
})();
