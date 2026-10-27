/* inicio.js - Portal de módulos (/inicio). Público: no usa common.js (que necesita sesión) ni otras dependencias.
   Constelación: el núcleo "I+D" al centro y los módulos como estrellas en órbitas elípticas; cada una se une al núcleo con un
   arco curvo; la órbita es una sola elipse y su tramo iluminado recorta esa misma elipse (sin trazos paralelos).
   - Datos: GET /api/modulos (público; con sesión trae `sesion` y `permitido` por módulo). Estado del servidor: GET /api/health cada 30 s.
   - Las órbitas giran juntas con requestAnimationFrame; se pausan con la pestaña oculta y con hover/foco en una estrella.
   - prefers-reduced-motion: sin órbitas ni parallax. ≤640 px o pantallas bajas: lista vertical, sin órbitas y fondo estático (ahorra batería). */
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
        candado: '<rect x="5" y="10.5" width="14" height="10" rx="2"/><path d="M8 10.5V8a4 4 0 0 1 8 0v2.5M12 14.5v2.5"/>',
        llanta: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="4.2"/><path d="M12 3v4.8M12 16.2V21M3 12h4.8M16.2 12H21"/>',
        antena: '<circle cx="12" cy="10" r="1.6"/><path d="M12 11.6V21M9 21h6M8.2 6.2a5.4 5.4 0 0 0 0 7.6M15.8 6.2a5.4 5.4 0 0 1 0 7.6M5.4 3.6a9.4 9.4 0 0 0 0 12.8M18.6 3.6a9.4 9.4 0 0 1 0 12.8"/>',
        ave: '<path d="M2.5 9.5c3-4.5 6.5-4.5 9.5 1 3-5.5 6.5-5.5 9.5-1"/><path d="M12 10.5v5.2M12 15.7l-2.6 4.3M12 15.7l2.6 4.3"/>',
        ciudad: '<rect x="7" y="7" width="10" height="10" rx="1.5"/><path d="M10 7V3M14 7V3M10 21v-4M14 21v-4M7 10H3M7 14H3M21 10h-4M21 14h-4"/><circle cx="12" cy="12" r="1.5"/>',   // v1.4.39: chip (antes edificios)
        impresora: '<path d="M7 9V4h10v5"/><rect x="3.5" y="9" width="17" height="8" rx="2"/><path d="M7 14h10v6H7z"/><path d="M16.5 12h.01"/>',
        sol: '<circle cx="12" cy="12" r="4"/><path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6 7 7M17 17l1.4 1.4M5.6 18.4 7 17M17 7l1.4-1.4"/>',
        luna: '<path d="M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5z"/>'
    };
    var ESTADOS = { disponible: 'Disponible', proximamente: 'Próximamente', mantenimiento: 'En mantenimiento' };
    var ROLES = { administrador: 'Administrador', general: 'General', consultor: 'Consultor' };
    var MSG_SIN = 'Tu cuenta no tiene acceso a este módulo. Pídelo a un administrador.';

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

    /* ================= sesión (cabecera) y aviso de acceso denegado ================= */
    var sesionInfo = null;
    function pintarSesion() {
        var box = $('ses');
        pintarNucleo();
        if (!sesionInfo) { box.hidden = true; return; }
        var mail = String(sesionInfo.email || ''), corto = mail.length > 28 ? mail.slice(0, 27) + '…' : mail;
        $('sesMail').textContent = corto; $('sesQuien').title = mail;
        $('sesRol').textContent = ROLES[sesionInfo.rol] || sesionInfo.rol || '';
        box.hidden = false;
    }
    $('salir').addEventListener('click', function () {
        this.disabled = true;
        var fin = function () { location.reload(); };
        fetch('/api/auth/logout', { method: 'POST', credentials: 'same-origin' }).then(fin, fin);
    });
    /* ?denegado=escaner-tqt: el servidor te devuelve aquí si la cuenta no tiene el módulo. Se muestra el aviso y se limpia la URL. */
    (function () {
        var q = new URLSearchParams(location.search), d = q.get('denegado');
        if (d === null) return;
        q.delete('denegado');
        try { history.replaceState(null, '', location.pathname + (q.toString() ? '?' + q.toString() : '') + location.hash); } catch (e) { /* sin history */ }
        if (d !== 'escaner-tqt') return;
        $('denTxt').textContent = 'Tu cuenta no tiene acceso a Escáner TQT. Pide a un administrador que te lo asigne.';
        $('denegado').hidden = false;
    })();
    $('denX').addEventListener('click', function () { $('denegado').hidden = true; $('modulos').focus(); });

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
        if (lista) n = Math.min(n, 90);                     // móvil: menos puntos (se pinta una sola vez)
        while (fondo.length < n) fondo.push({ u: Math.random(), v: Math.random(), z: .15 + Math.random() * .85, r: .5 + Math.random() * 1.1, f: Math.random() * TAU, s: .5 + Math.random() * 1.1, k: Math.random() < .1 ? 1 : Math.random() < .12 ? 2 : 0 });
        fondo.length = n;
        if (!corriendo()) pintarCampo(0);
    }
    function pintarCampo(t) {
        cx2.clearRect(0, 0, W, H);
        var ox = par.x * 14, oy = par.y * 14, claro = col.claro, fijo = quieto || lista, i, s, x, y, a;
        for (i = 0; i < fondo.length; i++) {
            s = fondo[i];
            x = s.u * (W + 48) - 24 + ox * s.z; y = s.v * (H + 48) - 24 + oy * s.z;
            a = claro ? .16 + .34 * s.z : .22 + .66 * s.z;
            if (!fijo) a *= .8 + .2 * Math.sin(t * s.s + s.f);
            cx2.globalAlpha = a; cx2.fillStyle = s.k === 1 ? col.a : s.k === 2 ? col.i : col.t;
            if (claro && s.z > .72) { cx2.fillRect(x - 4, y - .5, 8, 1); cx2.fillRect(x - .5, y - 4, 1, 8); }   // plano técnico: marcas "+"
            else { cx2.beginPath(); cx2.arc(x, y, claro ? s.r * .8 : s.r, 0, TAU); cx2.fill(); }
            if (!claro && s.z > .9) { cx2.globalAlpha = a * .35; cx2.fillRect(x - 5, y - .4, 10, .8); cx2.fillRect(x - .4, y - 5, .8, 10); }
        }
        cx2.globalAlpha = 1;
    }
    addEventListener('pointermove', function (e) {
        if (quieto || lista || e.pointerType === 'touch') return;
        par.tx = (e.clientX / innerWidth - .5) * 2; par.ty = (e.clientY / innerHeight - .5) * 2;
    }, { passive: true });
    document.documentElement.addEventListener('pointerleave', function () { par.tx = 0; par.ty = 0; });

    /* ================= constelación ================= */
    var items = [], orbs = [], lay = { W: 0, H: 0, cx: 0, cy: 0 };
    var act = null, fichaItem = null, fw = 0, fh = 0, entrando = false;
    var st = { hov: null, foc: null, tap: null, esc: false, t: 0, silencio: false };
    var TILT = -0.2, TILT_G = TILT * 180 / Math.PI;
    // v1.4.38: órbitas realistas. Cada módulo tiene su propia órbita; las interiores giran más rápido (3.ª ley de Kepler,
    // ω ∝ r^-1.5) y la inclinación da profundidad: al pasar por detrás del núcleo la estrella se ve más chica y tenue.
    var ORO = 2.39996, PERIODO_EXT = 150;                   // ángulo áureo para repartir las fases iniciales; vuelta de la órbita exterior (s)
    var vel = 1;

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

    /* Con sesión, un módulo con aplicación (disponible o en mantenimiento) que la cuenta no tiene asignado se marca "Sin acceso". "Próximamente" no cambia. */
    function bloqueado(m) { return !!(sesionInfo && m.permitido === false && m.estado !== 'proximamente'); }
    function estadoTxt(m) { return bloqueado(m) ? 'Sin acceso' : (ESTADOS[m.estado] || esc(m.estado)); }
    var CANDADO = '<svg class="cand" viewBox="0 0 24 24" focusable="false"><rect x="5" y="10.5" width="14" height="10" rx="2"/><path d="M8 10.5V8a4 4 0 0 1 8 0v2.5"/></svg>';

    /* Lunas: submódulos que orbitan su estrella (fuera del botón). Con `url` y acceso al módulo son enlaces. */
    var LUNA_ICO = '<svg class="luna-ico" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" d="M20 12a8 8 0 1 1-2.3-5.6M20 4v4.5h-4.5"/></svg>';   // ciclo: pruebas que se repiten
    function lunasHtml(ls, entra) {
        if (!Array.isArray(ls) || !ls.length) return '';
        return '<span class="lunas">' + ls.slice(0, 3).map(function (l, j, a) {
            // toda la luna es el enlace; su nombre solo se muestra al pasar el cursor por ella (o al enfocarla con teclado)
            var url = entra && destino(l && l.url), tag = url ? 'a' : 'span';
            return '<span class="luna-sis" style="--j:' + (j / a.length) + '"><' + tag + ' class="luna"' + (url ? ' href="' + esc(url) + '"' : '') + '>' +
                '<i class="luna-esf" aria-hidden="true"></i><span class="luna-nom">' + LUNA_ICO + esc(l && l.nombre) + '</span></' + tag + '></span>';
        }).join('') + '</span>';
    }
    function construir(mods) {
        // disponibles primero (estable): la estrella principal es la primera y el recorrido con flechas empieza ahí
        var base = mods.map(function (m, i) { return { m: m, i: i }; });
        base.sort(function (a, b) { return (a.m.estado === 'disponible' ? 0 : 1) - (b.m.estado === 'disponible' ? 0 : 1) || a.i - b.i; });
        listaEl.textContent = ''; $('orbitas').textContent = ''; $('lineas').textContent = '';
        items = []; orbs = []; act = null; fichaItem = null;
        st.hov = st.foc = st.tap = null; st.esc = false; ocultarFicha();

        base.forEach(function (b, n) {
            var m = b.m, disp = m.estado === 'disponible', li = document.createElement('li'), sin = bloqueado(m), entra = disp && !sin;
            li.className = 'mod'; li.dataset.estado = m.estado; if (sin) li.dataset.permiso = 'no';
            li.style.setProperty('--a', acentoOk(m.acento)); li.style.setProperty('--i', n);
            li.innerHTML = '<button class="est" type="button" tabindex="-1" data-i="' + n + '"' + (entra ? '' : ' aria-disabled="true"') + ' aria-labelledby="mn' + n + ' mt' + n + '" aria-describedby="md' + n + '">' +
                '<span class="astro" aria-hidden="true"><i class="halo"></i><i class="onda"></i><svg class="ico" viewBox="0 0 24 24" focusable="false">' + (ICONOS[m.icono] || ICONOS.caja) + '</svg>' + (sin ? CANDADO : '') + '</span>' +
                '<span class="rot"><span class="nom" id="mn' + n + '">' + esc(m.nombre) + '</span><span class="tag" id="mt' + n + '"><i aria-hidden="true"></i>' + estadoTxt(m) + '</span></span>' +
                '<span class="desc" id="md' + n + '">' + esc(m.descripcion) + (sin ? ' ' + MSG_SIN : '') + '</span>' +
                (entra ? '<span class="go" aria-hidden="true">Entrar</span>' : '') + '</button>' +
                lunasHtml(m.lunas, entra);
            listaEl.appendChild(li);
            items.push({ m: m, li: li, btn: li.firstChild, orb: null, off: 0, x: 0, y: 0, acento: acentoOk(m.acento), sin: sin });
        });

        // una órbita por módulo, de adentro hacia afuera en el orden de la lista (disponibles primero). La elipse base, el tramo
        // iluminado (lz) y el cometa (gl) son la MISMA elipse; lz y gl solo recortan con dasharray.
        items.forEach(function (it, j) {
            var el = document.createElementNS(NS, 'ellipse'), lz = document.createElementNS(NS, 'ellipse'), gl = document.createElementNS(NS, 'ellipse');
            el.setAttribute('class', 'orb'); el.setAttribute('stroke', 'url(#gOrb)'); lz.setAttribute('class', 'tray'); gl.setAttribute('class', 'glow');
            lz.setAttribute('pathLength', '1'); gl.setAttribute('pathLength', '1'); gl.style.setProperty('--n', j);
            $('orbitas').appendChild(el); $('orbitas').appendChild(lz); $('orbitas').appendChild(gl);
            var o = { tam: j, n: 1, rx: 0, ry: 0, k: 1, w: 0, el: el, lz: lz, gl: gl };
            it.orb = o; it.ang = .6 + j * ORO;
            orbs.push(o);
        });
        if (!$('gOrb')) {   // trazo de órbita: tenue por detrás (arriba) y más visible por delante (abajo)
            var defs = document.createElementNS(NS, 'defs'), gr = document.createElementNS(NS, 'linearGradient');
            gr.id = 'gOrb'; gr.setAttribute('x1', '0'); gr.setAttribute('y1', '0'); gr.setAttribute('x2', '0'); gr.setAttribute('y2', '1');
            [['0', '.25'], ['.5', '.55'], ['1', '1']].forEach(function (s) {
                var sp = document.createElementNS(NS, 'stop'); sp.setAttribute('offset', s[0]);
                sp.setAttribute('style', 'stop-color: var(--line-2); stop-opacity: ' + s[1]); gr.appendChild(sp);
            });
            defs.appendChild(gr); $('trazas').insertBefore(defs, $('trazas').firstChild);
        }

        // por estrella: solo el brazo curvo al núcleo (base + luz sobre exactamente el mismo trazo)
        items.forEach(function (it, k) {
            var g = document.createElementNS(NS, 'g');
            g.setAttribute('class', 'lin brazo'); g.style.setProperty('--k', k);
            var b1 = document.createElementNS(NS, 'path'), b2 = document.createElementNS(NS, 'path');
            b1.setAttribute('class', 'base'); b2.setAttribute('class', 'luz');
            b1.setAttribute('pathLength', '1'); b2.setAttribute('pathLength', '1');
            g.appendChild(b1); g.appendChild(b2);
            $('lineas').appendChild(g);
            it.g = g; it.bb = b1; it.bl = b2;
        });

        roving(0);
        calcular(); colocar();
    }

    function roving(i) { items.forEach(function (it, k) { it.btn.tabIndex = k === i ? 0 : -1; }); }

    /* Tamaño de las órbitas según el espacio disponible (sin desbordar entre 641 y 1920 px). En pantallas altas y angostas la elipse se redondea. */
    function calcular() {
        var w = escena.clientWidth, h = escena.clientHeight;
        if (!w || !h) return;
        lay.W = w; lay.H = h; lay.cx = w / 2; lay.cy = h / 2 - 12;
        escena.style.setProperty('--cy', r1(lay.cy) + 'px');
        if (lista || !orbs.length) return;
        var c = Math.cos(TILT), s = Math.sin(TILT), aw = w / 2 - 88, ah = Math.min(lay.cy - 46, h - lay.cy - 74);
        var ratio = Math.max(.46, Math.min(.8, ah / aw * .8));
        var hw1 = Math.sqrt(c * c + ratio * ratio * s * s), hh1 = Math.sqrt(s * s + ratio * ratio * c * c);
        var rx = Math.max(Math.min(aw / hw1, ah / hh1, 640), 150), ry = rx * ratio;
        var kin = Math.max(.42, Math.min(.6, 118 / ry)), n1 = Math.max(1, orbs.length - 1);
        orbs.forEach(function (o, j) {
            var k = kin + (1 - kin) * Math.pow(j / n1, .85); o.k = k; o.rx = rx * k; o.ry = ry * k;
            o.w = TAU / PERIODO_EXT * Math.pow(k, -1.5);   // Kepler: la interior da ~3.5 vueltas por cada vuelta de la exterior
            [o.el, o.lz, o.gl].forEach(function (e) {
                e.setAttribute('cx', r1(lay.cx)); e.setAttribute('cy', r1(lay.cy)); e.setAttribute('rx', r1(o.rx)); e.setAttribute('ry', r1(o.ry));
                e.setAttribute('transform', 'rotate(' + r1(TILT_G) + ' ' + r1(lay.cx) + ' ' + r1(lay.cy) + ')');
            });
        });
        // longitud de arco acumulada de la elipse (misma forma para todas las órbitas): pasa del ángulo paramétrico a la fracción de trazo (pathLength 1)
        var N = 240, q = ratio, tab = [0], i, a;
        for (i = 0; i < N; i++) { a = (i + .5) / N * TAU; tab.push(tab[i] + Math.sqrt(Math.sin(a) * Math.sin(a) + q * q * Math.cos(a) * Math.cos(a))); }
        lay.tab = tab;
        if (fichaItem) medirFicha();
    }
    function frac(a) {
        var T = lay.tab, n = T.length - 1; a = ((a % TAU) + TAU) % TAU;
        var f = a / TAU * n, i = Math.min(n - 1, Math.floor(f));
        return (T[i] + (T[i + 1] - T[i]) * (f - i)) / T[n];
    }
    /* Tramo iluminado de la órbita de la estrella activa: recorta con dasharray/dashoffset la propia elipse (sin trazo paralelo). */
    function luzOrbita(it) {
        if (!lay.tab || !it || !it.orb) return;
        var o = it.orb, a = it.ang, w = .5, f1 = frac(a - w), len = (((frac(a + w) - f1) % 1) + 1) % 1;
        o.lz.style.strokeDasharray = len.toFixed(4) + ' ' + (1 - len).toFixed(4); o.lz.style.strokeDashoffset = (-f1).toFixed(4);
    }

    function pt(o, a) {
        var ex = o.rx * Math.cos(a), ey = o.ry * Math.sin(a), c = Math.cos(TILT), s = Math.sin(TILT);
        return [lay.cx + ex * c - ey * s, lay.cy + ex * s + ey * c];
    }
    /* Brazo del núcleo a la estrella: curva cuadrática que se arquea hacia atrás del sentido de giro (como el brazo de una espiral). */
    function brazo(x, y) {
        var dx = x - lay.cx, dy = y - lay.cy, qx = lay.cx + dx / 2 + dy * .24, qy = lay.cy + dy / 2 - dx * .24;
        return 'M' + r1(lay.cx) + ' ' + r1(lay.cy) + 'Q' + r1(qx) + ' ' + r1(qy) + ' ' + r1(x) + ' ' + r1(y);
    }

    function colocar() {
        if (lista) { items.forEach(function (it) { it.li.style.transform = ''; }); return; }
        items.forEach(function (it) {
            var o = it.orb, a = it.ang, p = pt(o, a), d = (1 + Math.sin(a)) / 2;   // d: 0 = detrás del núcleo, 1 = al frente
            it.x = p[0]; it.y = p[1]; it.d = d;
            it.li.style.transform = 'translate3d(' + r1(it.x) + 'px,' + r1(it.y) + 'px,0)';
            it.li.style.zIndex = String(Math.round(d * 100));
            it.li.style.setProperty('--p', (.72 + .28 * d).toFixed(3));
            var br = brazo(it.x, it.y); it.bb.setAttribute('d', br); it.bl.setAttribute('d', br);
        });
        // etiquetas que se enciman: la de atrás se atenúa (como un planeta que pasa detrás de otro)
        items.forEach(function (a) { a.tapa = false; });
        for (var i = 0; i < items.length; i++) for (var k = i + 1; k < items.length; k++) {
            var A = items[i], B = items[k];
            if (Math.abs(A.x - B.x) < 130 && Math.abs(A.y - B.y) < 46) (A.d < B.d ? A : B).tapa = true;
        }
        items.forEach(function (a) { if (a.tapa && a !== act) a.li.setAttribute('data-tapada', ''); else a.li.removeAttribute('data-tapada'); });
        if (act) luzOrbita(act);
        if (fichaItem && ficha.dataset.abierta === 'true') posFicha();
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
        function libre(px, py) {      // que la ficha no tape a otra estrella ni su etiqueta
            return items.every(function (o) { return o === it || o.x + 76 < px || o.x - 76 > px + w || o.y + 72 < py || o.y - 20 > py + h; });
        }
        for (var i = 0; i < lados.length && !elegido; i++) if (cabeX(lados[i][1]) && libre(lados[i][1], vy)) elegido = [lados[i][1], vy];
        if (!elegido && cabeY(B) && libre(hx, B)) elegido = [hx, B];
        if (!elegido && cabeY(A) && libre(hx, A)) elegido = [hx, A];
        for (i = 0; i < lados.length && !elegido; i++) if (cabeX(lados[i][1])) elegido = [lados[i][1], vy];
        if (!elegido && cabeY(B)) elegido = [hx, B];
        if (!elegido && cabeY(A)) elegido = [hx, A];
        if (!elegido) elegido = [clamp(lados[0][1], 8, Math.max(8, W2 - w - 8)), vy];
        x = elegido[0]; y = elegido[1];
        ficha.style.transform = 'translate3d(' + Math.round(x) + 'px,' + Math.round(y) + 'px,0)';
    }
    function mostrarFicha(it) {
        if (fichaItem !== it) {
            fichaItem = it; var m = it.m;
            ficha.style.setProperty('--a', it.acento); ficha.dataset.e = it.sin ? 'sin' : m.estado;
            $('fIco').innerHTML = ICONOS[m.icono] || ICONOS.caja;
            $('fNom').textContent = m.nombre; $('fEst').textContent = it.sin ? 'Sin acceso' : (ESTADOS[m.estado] || m.estado); $('fDesc').textContent = m.descripcion;
            var av = $('fAviso'), txt = it.sin ? MSG_SIN : m.estado === 'mantenimiento' ? 'Este módulo está en mantenimiento. Vuelve a intentarlo más tarde.' : '';
            av.hidden = !txt; av.textContent = txt;
            $('fEntrar').hidden = m.estado !== 'disponible' || it.sin;
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
        items.forEach(function (x) {
            var on = x === it;
            if (on) x.btn.setAttribute('data-on', ''); else x.btn.removeAttribute('data-on');
            x.g.classList.toggle('on', on);
            if (on) x.g.style.setProperty('--a', it.acento);
        });
        orbs.forEach(function (o) { var on = !!(it && it.orb === o); o.lz.classList.toggle('on', on); if (on) o.lz.style.setProperty('--a', it.acento); });
        if (it) luzOrbita(it);
        if (it) escena.setAttribute('data-act', ''); else escena.removeAttribute('data-act');
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
        if (it.sin) { avisar('Tu cuenta no tiene acceso a ' + m.nombre + '. Pídelo a un administrador.'); return; }
        var url = destino(m.url);
        if (!url) { avisar('No se pudo abrir ' + m.nombre + '.'); return; }
        if (sesionInfo || m.publico) { location.href = url; return; }       // con sesión y permiso, o módulo público (v1.4.39): directo
        if (entrando) return;
        entrando = true; it.btn.setAttribute('data-cargando', ''); avisar('Comprobando tu sesión…');
        var acceso = (destino(m.login) || '/login') + '?next=' + encodeURIComponent(url);   // v1.4.17: cada módulo con su pantalla de acceso
        fetch('/api/auth/yo', { credentials: 'same-origin', cache: 'no-store' }).then(function (r) {
            location.href = r.ok ? url : acceso;   // 401: a iniciar sesión; después vuelve al módulo
        }, function () { location.href = acceso; });
    }
    addEventListener('pageshow', function (e) {
        if (e.persisted) { entrando = false; items.forEach(function (it) { it.btn.removeAttribute('data-cargando'); }); avisar(''); }
    });

    /* ---- eventos de las estrellas (delegados en la lista) ---- */
    function itemDe(el) { var b = el.closest && el.closest('.est'); return b ? items[+b.dataset.i] : null; }
    // la luna solo frena la órbita para poder pulsarla; no activa su estrella ni abre la ficha (que taparía su nombre)
    var lunaHov = false;
    function lunaDe(el) { return el && el.closest ? el.closest('.luna') : null; }
    listaEl.addEventListener('pointerover', function (e) {
        if (e.pointerType === 'touch') return;
        if (lunaDe(e.target)) { lunaHov = true; return; }
        var it = itemDe(e.target); if (it && !it.btn.contains(e.relatedTarget)) entrarHover(items.indexOf(it));
    });
    listaEl.addEventListener('pointerout', function (e) {
        if (e.pointerType === 'touch') return;
        var l = lunaDe(e.target); if (l) { if (!l.contains(e.relatedTarget)) lunaHov = false; return; }
        var it = itemDe(e.target); if (it && !it.btn.contains(e.relatedTarget)) salirHover();
    });
    listaEl.addEventListener('click', function (e) {
        var it = itemDe(e.target); if (!it) return;
        if (e.pointerType === 'touch' && !lista && st.tap !== items.indexOf(it)) {    // en tableta el primer toque muestra la ficha; el segundo (o "Entrar") abre. En móvil (lista) un solo toque entra
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
        return cargarModulos();
    }
    function cargarModulos() {
        estadoMsg('carga', 'Cargando módulos…', null); escena.setAttribute('aria-busy', 'true');
        return fetch('/api/modulos', { cache: 'no-store', credentials: 'same-origin' }).then(function (r) {
            if (!r.ok) throw new Error('http ' + r.status);
            return r.json();
        }).then(function (d) {
            sesionInfo = d && d.sesion && typeof d.sesion === 'object' ? d.sesion : null; pintarSesion();
            var ms = d && Array.isArray(d.modulos) ? d.modulos : [];
            if (!ms.length) { construir([]); estadoMsg('vacio', 'Todavía no hay módulos publicados.', 'Actualizar'); return; }
            construir(ms); estadoMsg('', '', null);
        }).catch(function () {
            sesionInfo = null; pintarSesion();
            construir([]); estadoMsg('error', 'No se pudo cargar la lista de módulos. Revisa la conexión e inténtalo de nuevo.', 'Reintentar');
        }).then(function () { escena.setAttribute('aria-busy', 'false'); if (!cc.abierto) arrancar(); });
    }

    /* ================= bucle de animación (solo escritorio con movimiento permitido) ================= */
    var raf = 0, ult = 0;
    function corriendo() { return raf !== 0; }
    function bucle(ts) {
        raf = requestAnimationFrame(bucle);
        var dt = Math.min(.1, (ts - ult) / 1000 || 0); ult = ts;
        var k = 1 - Math.exp(-dt * 4);
        par.x += (par.tx - par.x) * k; par.y += (par.ty - par.y) * k;
        if (orbs.length) {
            var quietas = act || lunaHov;
            vel += ((quietas ? 0 : 1) - vel) * (1 - Math.exp(-dt * (quietas ? 6 : 2.4)));     // frena y arranca con suavidad con una estrella activa o la luna bajo el cursor
            if (vel < .002) vel = 0; else if (vel > .998) vel = 1;
            if (vel > 0) { items.forEach(function (it) { it.ang += it.orb.w * vel * dt; }); colocar(); }
        }
        pintarCampo(ts / 1000);
    }
    function detener() { if (raf) cancelAnimationFrame(raf); raf = 0; }
    function arrancar() {
        detener();
        if (cc.abierto) return;                                   // centro de control abierto: la constelación queda en pausa
        if (quieto || lista || document.hidden) { par.x = par.y = par.tx = par.ty = 0; colocar(); pintarCampo(0); return; }   // móvil / sin movimiento: nada corre (ahorra batería)
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

    /* ================= centro de control (solo administradores) =================
       El núcleo "I+D" es siempre un botón. Administrador: despliega la matriz cuentas × módulos. Sin sesión (o sin ser administrador): despliega el
       formulario «Acceso de administrador» desde el mismo núcleo y, tras entrar, ese mismo contenedor pasa a la matriz. POST /api/plataforma/entrar.
       API (solo administradores): GET /api/plataforma/cuentas, PATCH /api/plataforma/cuentas/{email}, POST /api/plataforma/modulos/{id}/todos. */
    var cc = { vista: 'acceso', entrando: false, mods: [], roles: [], cuentas: [], q: '', abierto: false, pend: 0, cola: Promise.resolve(), menu: null, conf: null, smtp: true, busy: {} };
    var ccEl = $('cc'), ccPanel = $('ccPanel'), nucBtn = $('nucBtn'), portal = document.querySelector('.portal'), nucleo = document.querySelector('.nucleo');
    var ccMenu = $('ccMenu'), ccConf = $('ccConf'), tCerrar = 0, tCcAviso = 0, menuBtn = null;

    function esAdmin() { return !!(sesionInfo && sesionInfo.rol === 'administrador'); }
    function pintarNucleo() {
        var ad = esAdmin();
        nucBtn.hidden = false;                                       // el núcleo siempre es un botón; sin sesión de administrador pide el acceso
        if (ad) nucleo.setAttribute('data-admin', ''); else nucleo.removeAttribute('data-admin');
        if (!ad && cc.abierto && cc.vista === 'cuentas' && !cc.entrando) ccCerrar(false);
    }
    function esYo(c) { return !!(sesionInfo && String(c.email).toLowerCase() === String(sesionInfo.email || '').toLowerCase()); }

    function detalle(d, s) {
        var x = d && d.detail;
        if (typeof x === 'string' && x) return x;
        if (Array.isArray(x)) { var t = x.map(function (i) { return i && i.msg ? i.msg : ''; }).filter(Boolean).join(' '); if (t) return t; }
        if (s === 403) return 'Solo los administradores pueden gestionar cuentas.';
        if (s === 401) return 'Tu sesión expiró. Vuelve a iniciar sesión.';
        return 'No se pudo completar la operación (' + s + ').';
    }
    function api(met, url, cuerpo) {
        var o = { method: met, credentials: 'same-origin', cache: 'no-store', headers: {} };
        if (cuerpo !== undefined) { o.headers['Content-Type'] = 'application/json'; o.body = JSON.stringify(cuerpo); }
        return fetch(url, o).then(null, function () { throw new Error('Sin conexión con el servidor. Inténtalo de nuevo.'); }).then(function (r) {
            return r.json().then(null, function () { return null; }).then(function (d) {
                if (!r.ok) { var e = new Error(detalle(d, r.status)); e.status = r.status; throw e; }
                return d;
            });
        });
    }
    function ccAvisar(txt, mal) {
        var a = $('ccAviso'); clearTimeout(tCcAviso); a.textContent = ''; a.dataset.k = mal ? 'bad' : 'ok';
        if (!txt) return;
        setTimeout(function () { a.textContent = txt; }, 30);
        tCcAviso = setTimeout(function () { a.textContent = ''; }, mal ? 8000 : 3000);
    }
    function ccEstado(e, txt, boton) {
        $('ccCuerpo').dataset.e = e; $('ccCuerpo').setAttribute('aria-busy', e === 'carga' ? 'true' : 'false');
        $('ccEstTxt').textContent = txt || ''; var b = $('ccEstBtn'); b.hidden = !boton; if (boton) b.textContent = boton;
    }

    /* ---- datos ---- */
    function aplicar(d) {
        if (!d || !Array.isArray(d.cuentas)) throw new Error('Respuesta inesperada del servidor.');
        if (typeof d.smtp === 'boolean') cc.smtp = d.smtp;
        var nuevos = Array.isArray(d.modulos) ? d.modulos : [];
        var mismos = nuevos.length === cc.mods.length && nuevos.every(function (m, i) { return cc.mods[i] && cc.mods[i].id === m.id; });
        cc.mods = nuevos; cc.roles = Array.isArray(d.roles) && d.roles.length ? d.roles : ['administrador', 'general', 'consultor'];
        cc.cuentas = d.cuentas.map(function (c) { c.modulos = Array.isArray(c.modulos) ? c.modulos : []; return c; });
        if (!mismos) { menuCerrar(false); ccCabecera(); }
        $('ccInv').disabled = !cc.mods.length;
        if (!$('ccInvForm').hidden) invAviso();
        ccRender();
    }
    function ccCargar(silencioso) {
        if (!silencioso) ccEstado('carga', 'Cargando cuentas…', null);
        return api('GET', '/api/plataforma/cuentas').then(function (d) { aplicar(d); }).then(null, function (e) {
            if (!silencioso) ccEstado('error', e.message, 'Reintentar');
        });
    }
    /* Operaciones en serie (la matriz cambia rápido): cada una se envía cuando termina la anterior. Si falla, se revierte y se resincroniza. */
    function encolar(fn, revertir, alTerminar) {
        cc.pend++;
        cc.cola = cc.cola.then(fn).then(function (d) {
            cc.pend--;
            if (cc.pend === 0) { try { aplicar(d); } catch (e) { /* forma distinta: se conserva lo optimista */ } }
            ccAvisar('Guardado', false);
            if (alTerminar) alTerminar();
        }, function (e) {
            cc.pend--;
            if (revertir) revertir();
            ccRender(); ccAvisar(e.message, true);
            if (cc.pend === 0) ccCargar(true);
        });
    }

    /* ---- vista ---- */
    function ico(m) { return '<svg class="cc-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">' + (ICONOS[m.icono] || ICONOS.chip) + '</svg>'; }
    function tiene(c, id) { return c.rol === 'administrador' || c.modulos.indexOf(id) >= 0; }
    function ccCabecera() {
        var h = '<tr><th scope="col" class="cc-h-cta">Cuenta</th><th scope="col" class="cc-h-rol">Rol</th><th scope="col" class="cc-h-c cc-h-t">Todos</th>', t = '';
        cc.mods.forEach(function (m) {
            var pron = m.estado === 'proximamente', nom = esc(m.nombre);
            var b = '<button type="button" class="cc-mh" data-menu="' + esc(m.id) + '" style="--a:' + acentoOk(m.acento) + '" aria-haspopup="menu" aria-expanded="false"' + (pron ? ' data-pron="1"' : '') +
                ' aria-label="' + nom + (pron ? ' (próximamente)' : '') + ': dar o quitar a todas las cuentas">' + ico(m) + '<span class="cc-mn">' + nom + '</span>' + (pron ? '<small>Pronto</small>' : '') + '</button>';
            h += '<th scope="col" class="cc-h-c">' + b + '</th>'; t += b;
        });
        $('ccHead').innerHTML = h + '</tr>'; $('ccMods').innerHTML = t;
    }
    function accionesPend(c, mail) {
        if (!c.pendiente) return '';
        var oc = !!cc.busy[String(c.email).toLowerCase()], d = oc ? ' disabled' : '';
        return '<span class="cc-pacc"><button type="button" class="cc-lnk" data-f="i|' + mail + '|r" data-inv="reenviar" data-e="' + mail + '"' + d + '>' + (oc ? 'Reenviando…' : 'Reenviar') + '</button>' +
            '<button type="button" class="cc-lnk cc-lnk-bad" data-f="i|' + mail + '|c" data-inv="cancelar" data-e="' + mail + '"' + d + ' aria-label="Cancelar invitación de ' + mail + '">Cancelar invitación</button></span>';
    }
    function chips(c) {
        return (c.pendiente ? '<span class="cc-chip" data-k="info">Pendiente</span>' : '') + (c.activo === false ? '<span class="cc-chip" data-k="warn">Inactiva</span>' : '');
    }
    function ccRender() {
        var ae = document.activeElement, clave = ae && ae.dataset && ae.dataset.f && ccPanel.contains(ae) ? ae.dataset.f : null;
        var q = cc.q.trim().toLowerCase(), todas = cc.cuentas;
        var ls = q ? todas.filter(function (c) { return String(c.email).toLowerCase().indexOf(q) >= 0; }) : todas;
        $('ccCuenta').textContent = (ls.length === todas.length ? ls.length : ls.length + ' de ' + todas.length) + (todas.length === 1 ? ' cuenta' : ' cuentas');
        var filas = '', tarj = '';
        ls.forEach(function (c) {
            var adm = c.rol === 'administrador', mail = esc(c.email);
            var n = c.modulos.filter(function (id) { return cc.mods.some(function (m) { return m.id === id; }); }).length;
            var todos = adm || (cc.mods.length > 0 && n === cc.mods.length), parcial = !todos && n > 0;
            var nota = adm ? '<span class="cc-nota">Todos (administrador)</span>' : '';
            var opts = cc.roles.map(function (r) { return '<option value="' + esc(r) + '"' + (r === c.rol ? ' selected' : '') + '>' + esc(ROLES[r] || r) + '</option>'; }).join('');
            var sel = function (v) { return '<select class="input cc-rol" data-e="' + mail + '" data-f="r|' + mail + '|' + v + '" aria-label="Rol de ' + mail + '">' + opts + '</select>'; };
            var tod = function (v) { return '<input type="checkbox" class="cc-todos" data-e="' + mail + '" data-f="t|' + mail + '|' + v + '" aria-label="Todos los módulos para ' + mail + '"' + (todos ? ' checked' : '') + (parcial ? ' data-ind="1"' : '') + (adm ? ' disabled' : '') + '>'; };
            filas += '<tr><th scope="row" class="cc-cta"><span class="cc-mail" title="' + mail + '">' + mail + '</span>' + chips(c) + accionesPend(c, mail) + nota + '</th><td>' + sel('t') + '</td><td class="cc-c"><label class="cc-cl">' + tod('t') + '</label></td>';
            tarj += '<li class="cc-card"><div class="cc-chead"><span class="cc-mail">' + mail + '</span>' + chips(c) + '</div>' + accionesPend(c, mail) + nota +
                '<div class="cc-crow"><label class="cc-rl"><span>Rol</span>' + sel('m') + '</label><label class="cc-pill">' + tod('m') + '<span class="cc-pb"><b>Todos</b></span></label></div><div class="cc-pills">';
            cc.mods.forEach(function (m) {
                var at = 'class="cc-chk" data-e="' + mail + '" data-m="' + esc(m.id) + '" aria-label="' + esc(m.nombre) + ' para ' + mail + '"' + (tiene(c, m.id) ? ' checked' : '') + (adm ? ' disabled' : '');
                filas += '<td class="cc-c"><label class="cc-cl"><input type="checkbox" ' + at + ' data-f="c|' + mail + '|' + esc(m.id) + '|t"></label></td>';
                tarj += '<label class="cc-pill" style="--a:' + acentoOk(m.acento) + '"' + (m.estado === 'proximamente' ? ' data-pron="1"' : '') + '><input type="checkbox" ' + at + ' data-f="c|' + mail + '|' + esc(m.id) + '|m"><span class="cc-pb">' + ico(m) + '<b>' + esc(m.nombre) + '</b></span></label>';
            });
            filas += '</tr>'; tarj += '</div></li>';
        });
        var sc = $('ccScroll'), top = sc.scrollTop, izq = sc.scrollLeft;
        $('ccFilas').innerHTML = filas; $('ccTarjetas').innerHTML = tarj;
        sc.scrollTop = top; sc.scrollLeft = izq;
        Array.prototype.forEach.call(ccPanel.querySelectorAll('[data-ind]'), function (i) { i.indeterminate = true; });
        if (!todas.length) ccEstado('vacio', 'Todavía no hay cuentas registradas.', 'Actualizar');
        else if (!ls.length) ccEstado('vacio', 'Ninguna cuenta coincide con «' + cc.q.trim() + '».', 'Limpiar búsqueda');
        else ccEstado('ok', '', null);
        if (clave) {
            var cand = ccPanel.querySelectorAll('[data-f="' + clave.replace(/["\\]/g, '\\$&') + '"]'), k;
            for (k = 0; k < cand.length; k++) if (cand[k].offsetParent !== null) { cand[k].focus(); break; }
        }
    }
    function cuentaDe(mail) { var l = String(mail).toLowerCase(); return cc.cuentas.filter(function (c) { return String(c.email).toLowerCase() === l; })[0]; }

    /* ---- cambios (optimistas, con reversión si fallan) ---- */
    function ccCambioModulos(c, nuevos) {
        var antes = c.modulos.slice(); c.modulos = nuevos; ccRender();
        encolar(function () { return api('PATCH', '/api/plataforma/cuentas/' + encodeURIComponent(c.email), { modulos: nuevos }); }, function () { c.modulos = antes; });
    }
    function ccCambioRol(c, rol) {
        var antes = c.rol, yo = esYo(c); c.rol = rol; ccRender();
        encolar(function () { return api('PATCH', '/api/plataforma/cuentas/' + encodeURIComponent(c.email), { rol: rol }); }, function () { c.rol = antes; }, yo ? function () { cargar(); } : null);
    }
    ccPanel.addEventListener('change', function (e) {
        var t = e.target, c = t.dataset && t.dataset.e ? cuentaDe(t.dataset.e) : null;
        if (!c) return;
        if (t.classList.contains('cc-rol')) { ccCambioRol(c, t.value); return; }
        if (t.classList.contains('cc-chk')) {
            var id = t.dataset.m, sin = c.modulos.filter(function (x) { return x !== id; });
            ccCambioModulos(c, t.checked ? sin.concat(id) : sin);
        } else if (t.classList.contains('cc-todos')) {
            ccCambioModulos(c, t.checked ? cc.mods.map(function (m) { return m.id; }) : []);
        }
    });
    $('ccBuscar').addEventListener('input', function () { cc.q = this.value; ccRender(); });

    /* ---- menú por columna + confirmación en línea (sin alert/confirm del navegador) ---- */
    function menuCerrar(devolver) {
        if (ccMenu.hidden) return;
        ccMenu.hidden = true;
        if (menuBtn) { menuBtn.setAttribute('aria-expanded', 'false'); if (devolver) menuBtn.focus(); }
    }
    function menuAbrir(btn) {
        if (menuBtn === btn && !ccMenu.hidden) { menuCerrar(true); return; }
        menuCerrar(false); menuBtn = btn; cc.menu = btn.dataset.menu;
        var m = cc.mods.filter(function (x) { return x.id === cc.menu; })[0]; if (!m) return;
        ccMenu.setAttribute('aria-label', 'Acciones para ' + m.nombre);
        ccMenu.hidden = false; btn.setAttribute('aria-expanded', 'true');
        var r = btn.getBoundingClientRect(), w = ccMenu.offsetWidth, h = ccMenu.offsetHeight, abajo = r.bottom + 4;
        ccMenu.style.left = Math.max(8, Math.min(innerWidth - w - 8, r.left + r.width / 2 - w / 2)) + 'px';
        ccMenu.style.top = (abajo + h > innerHeight - 8 ? Math.max(8, r.top - h - 4) : abajo) + 'px';
        ccMenu.firstElementChild.focus();
    }
    function confCerrar(devolver) {
        if (ccConf.hidden) return;
        var k = cc.conf; ccConf.hidden = true; cc.conf = null;
        if (!devolver) return;
        if (k && k.inv) enfocarF('i|' + k.inv + '|c', 'ccInv'); else if (menuBtn) menuBtn.focus();
    }
    function enfocarF(clave, alt) {
        var c = ccPanel.querySelectorAll('[data-f="' + clave.replace(/["\\]/g, '\\$&') + '"]'), k;
        for (k = 0; k < c.length; k++) if (c[k].offsetParent !== null && !c[k].disabled) { c[k].focus(); return; }
        if (alt && !$(alt).disabled) $(alt).focus(); else ccPanel.focus({ preventScroll: true });
    }
    function confInv(mail) {
        cc.conf = { inv: mail };
        $('ccConfTxt').textContent = '¿Cancelar la invitación a ' + mail + '? El enlace enviado dejará de funcionar.';
        var ok = $('ccConfOk'); ok.textContent = 'Cancelar invitación'; ok.className = 'btn btn-sm btn-danger';
        $('ccConfNo').textContent = 'Conservar';
        ccConf.hidden = false; $('ccConfNo').focus();
    }
    function confAbrir(id, activo) {
        var m = cc.mods.filter(function (x) { return x.id === id; })[0]; if (!m) return;
        cc.conf = { id: id, activo: activo };
        $('ccConfTxt').textContent = (activo ? '¿Dar «' : '¿Quitar «') + m.nombre + '» a todas las cuentas que no son administradoras?';
        var ok = $('ccConfOk'); ok.textContent = activo ? 'Dar a todos' : 'Quitar a todos'; ok.className = 'btn btn-sm ' + (activo ? 'btn-primary' : 'btn-danger'); $('ccConfNo').textContent = 'Cancelar';
        ccConf.hidden = false; $('ccConfNo').focus();
    }
    $('ccConfNo').addEventListener('click', function () { confCerrar(true); });
    $('ccConfOk').addEventListener('click', function () {
        var k = cc.conf; if (!k) return;
        if (k.inv) { confCerrar(false); invCancelar(k.inv); return; }
        confCerrar(true); ccAvisar('Aplicando…', false);
        encolar(function () { return api('POST', '/api/plataforma/modulos/' + encodeURIComponent(k.id) + '/todos', { activo: k.activo }); }, null);
    });
    ccMenu.addEventListener('click', function (e) {
        var b = e.target.closest && e.target.closest('[data-ac]'); if (!b) return;
        var id = cc.menu; menuCerrar(false);
        if (b.dataset.ac === 'invitar') invAbrir(id); else confAbrir(id, b.dataset.ac === 'dar');
    });
    ccMenu.addEventListener('keydown', function (e) {
        var its = Array.prototype.slice.call(ccMenu.querySelectorAll('[role=menuitem]')), i = its.indexOf(document.activeElement);
        if (e.key === 'ArrowDown') { e.preventDefault(); its[(i + 1) % its.length].focus(); }
        else if (e.key === 'ArrowUp') { e.preventDefault(); its[(i - 1 + its.length) % its.length].focus(); }
        else if (e.key === 'Home') { e.preventDefault(); its[0].focus(); }
        else if (e.key === 'End') { e.preventDefault(); its[its.length - 1].focus(); }
        else if (e.key === 'Tab') { e.preventDefault(); menuCerrar(true); }
    });
    /* ---- invitaciones por correo: POST /api/plataforma/invitaciones, .../{email}/reenviar, DELETE .../{email} ---- */
    var invForm = $('ccInvForm'), invMail = $('ccInvMail'), invRol = $('ccInvRol'), invEnv = false, invAdm = false, invPrev = [], enlEl = $('ccEnl');
    function invAviso() { $('ccInvSmtp').hidden = cc.smtp !== false; }
    function invError(txt, campo) {
        var e = $('ccInvErr'); e.textContent = txt || ''; e.hidden = !txt;
        invMail.removeAttribute('aria-invalid'); if (txt && campo) campo.setAttribute('aria-invalid', 'true');
    }
    function invEstado(env) { invEnv = env; $('ccInvEnv').disabled = env; $('ccInvEnv').textContent = env ? 'Enviando…' : 'Enviar invitación'; invForm.setAttribute('aria-busy', env ? 'true' : 'false'); }
    function invRolCambio() {
        var adm = invRol.value === 'administrador', its = Array.prototype.slice.call(invForm.querySelectorAll('.cc-inv-chk'));
        if (adm && !invAdm) invPrev = its.filter(function (i) { return i.checked; }).map(function (i) { return i.value; });     // «todos»: se recuerda la elección previa
        its.forEach(function (i) { if (adm) i.checked = true; else if (invAdm) i.checked = invPrev.indexOf(i.value) >= 0; i.disabled = adm; });
        invAdm = adm;
    }
    function invAbrir(modId) {
        if (!cc.mods.length) return;
        menuCerrar(false); confCerrar(false); enlCerrar(false);
        invRol.innerHTML = cc.roles.map(function (r) { return '<option value="' + esc(r) + '">' + esc(ROLES[r] || r) + '</option>'; }).join('');
        invRol.value = cc.roles.indexOf('general') >= 0 ? 'general' : (cc.roles.filter(function (r) { return r !== 'administrador'; })[0] || cc.roles[0]);
        var pre = modId && cc.mods.some(function (m) { return m.id === modId; }) ? modId : (cc.mods.filter(function (m) { return m.estado === 'disponible'; })[0] || cc.mods[0]).id;
        $('ccInvMods').innerHTML = cc.mods.map(function (m) {
            return '<label class="cc-im" style="--a:' + acentoOk(m.acento) + '"' + (m.estado === 'proximamente' ? ' data-pron="1"' : '') + '><input type="checkbox" class="cc-inv-chk" value="' + esc(m.id) + '"' + (m.id === pre ? ' checked' : '') + '>' + ico(m) + '<span>' + esc(m.nombre) + '</span></label>';
        }).join('');
        invMail.value = ''; invAdm = false; invError('', null); invEstado(false); invAviso(); invRolCambio();
        invForm.hidden = false; $('ccInv').setAttribute('aria-expanded', 'true');
        invMail.focus({ preventScroll: true }); invForm.scrollIntoView({ block: 'nearest' });
    }
    function invCerrar(devolver) {
        if (invForm.hidden) return;
        invForm.hidden = true; $('ccInv').setAttribute('aria-expanded', 'false');
        if (devolver) $('ccInv').focus();
    }
    function enlCerrar(devolver) {
        if (enlEl.hidden) return;
        enlEl.hidden = true;
        if (devolver) $('ccInv').focus();
    }
    /* Resultado de enviar / reenviar: enviado → aviso; si no, tarjeta con el enlace para compartir a mano y el motivo. */
    function invResultado(d, mail, reenvio) {
        if (cc.pend === 0) { try { aplicar(d); } catch (e) { ccCargar(true); } }
        if (d && d.enviado) { enlCerrar(false); ccAvisar((reenvio ? 'Invitación reenviada a ' : 'Invitación enviada a ') + mail, false); return true; }
        if (!d || !d.enlace) { ccAvisar((d && d.error) || 'No se pudo enviar la invitación.', true); return false; }
        $('ccEnlTit').textContent = 'Invitación para ' + mail + ': comparte este enlace.';
        $('ccEnlMot').textContent = 'No se envió el correo' + (d.error ? ': ' + d.error : '.');
        $('ccEnlUrl').value = d.enlace; $('ccEnlCop').textContent = 'Copiar enlace';
        enlEl.hidden = false; $('ccEnlCop').focus({ preventScroll: true }); enlEl.scrollIntoView({ block: 'nearest' });
        ccAvisar('Invitación creada: falta compartir el enlace', false);
        return true;
    }
    function invCopiar() {
        var u = $('ccEnlUrl'), b = $('ccEnlCop');
        var ok = function () { b.textContent = 'Copiado'; ccAvisar('Enlace copiado', false); };
        var resp = function () {
            u.focus(); u.select(); u.setSelectionRange(0, u.value.length);
            var bien = false; try { bien = document.execCommand('copy'); } catch (e) { bien = false; }
            if (bien) ok(); else ccAvisar('Selecciona el enlace y cópialo manualmente.', true);
        };
        if (navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(u.value).then(ok, resp); else resp();
    }
    function invCancelar(mail) {
        ccAvisar('Cancelando…', false);
        api('DELETE', '/api/plataforma/invitaciones/' + encodeURIComponent(mail)).then(function (d) {
            if (cc.pend === 0) { try { aplicar(d); } catch (e) { ccCargar(true); } }
            ccAvisar('Invitación a ' + mail + ' cancelada', false); enfocarF('x', 'ccInv');
        }).then(null, function (e) { ccAvisar(e.message, true); ccCargar(true); });
    }
    function invReenviar(mail) {
        var k = mail.toLowerCase(); if (cc.busy[k]) return;
        cc.busy[k] = true; ccRender(); ccAvisar('Reenviando…', false);
        api('POST', '/api/plataforma/invitaciones/' + encodeURIComponent(mail) + '/reenviar').then(function (d) {
            delete cc.busy[k]; var enl = invResultado(d, mail, true) && !enlEl.hidden; ccRender();
            if (!enl) enfocarF('i|' + mail + '|r', 'ccInv');
        }).then(null, function (e) { delete cc.busy[k]; ccRender(); ccAvisar(e.message, true); });
    }
    $('ccInv').addEventListener('click', function () { if (invForm.hidden) invAbrir(null); else invCerrar(true); });
    $('ccInvNo').addEventListener('click', function () { invCerrar(true); });
    invRol.addEventListener('change', invRolCambio);
    $('ccEnlCop').addEventListener('click', invCopiar);
    $('ccEnlX').addEventListener('click', function () { enlCerrar(true); });
    $('ccEnlUrl').addEventListener('focus', function () { this.select(); });
    invForm.addEventListener('submit', function (ev) {
        ev.preventDefault();
        if (invEnv) return;
        var mail = invMail.value.trim(), adm = invRol.value === 'administrador';
        var mods = Array.prototype.filter.call(invForm.querySelectorAll('.cc-inv-chk'), function (i) { return i.checked; }).map(function (i) { return i.value; });
        if (!mail || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(mail)) { invError(mail ? 'Escribe un correo válido.' : 'Escribe el correo de la persona.', invMail); invMail.focus(); return; }
        if (!adm && !mods.length) { invError('Elige al menos un módulo.', null); return; }
        invError('', null); invEstado(true);
        api('POST', '/api/plataforma/invitaciones', { email: mail, rol: invRol.value, modulos: mods }).then(function (d) {
            invEstado(false); invCerrar(false); invResultado(d, mail, false);
            if (enlEl.hidden) $('ccInv').focus();
        }).then(null, function (e) {
            invEstado(false); invError(e.message, e.status === 422 ? invMail : null); invMail.focus();
        });
    });
    ccPanel.addEventListener('click', function (e) {
        var bi = e.target.closest && e.target.closest('[data-inv]');
        if (bi && !bi.disabled) { menuCerrar(false); if (bi.dataset.inv === 'reenviar') invReenviar(bi.dataset.e); else confInv(bi.dataset.e); return; }
        var b = e.target.closest && e.target.closest('[data-menu]');
        if (b) { confCerrar(false); menuAbrir(b); return; }
        if (!ccMenu.hidden && !ccMenu.contains(e.target)) menuCerrar(false);
    });
    $('ccEstBtn').addEventListener('click', function () {
        if (cc.cuentas.length && cc.q.trim()) { cc.q = ''; $('ccBuscar').value = ''; ccRender(); $('ccBuscar').focus(); } else ccCargar();
    });
    $('ccX').addEventListener('click', function () { ccCerrar(true); });

    /* ---- abrir / cerrar: foco atrapado dentro y devuelto al núcleo ---- */
    function ccAbrir() {
        if (cc.abierto) return;
        cc.abierto = true; clearTimeout(tCerrar);
        ccVista(esAdmin() ? 'cuentas' : 'acceso');
        nucBtn.setAttribute('aria-expanded', 'true');
        var r = nucBtn.getBoundingClientRect();
        ccEl.hidden = false;
        ccPanel.style.setProperty('--ox', Math.round(r.left + r.width / 2 - ccPanel.offsetLeft) + 'px');
        ccPanel.style.setProperty('--oy', Math.round(r.top + r.height / 2 - ccPanel.offsetTop) + 'px');
        void ccPanel.offsetWidth;                                   // fija el estado inicial antes de animar
        ccEl.dataset.abierto = 'true';
        portal.inert = true; escena.setAttribute('data-cc', ''); detener();
        if (cc.vista === 'acceso') accPreparar(); else { ccPanel.focus({ preventScroll: true }); ccCargar(); }
    }
    function ccVista(v) {
        cc.vista = v; ccEl.dataset.vista = v;
        $('ccTit').textContent = v === 'acceso' ? 'Acceso de administrador' : 'Cuentas y módulos';
        $('ccSub').textContent = v === 'acceso' ? 'Entra para administrar cuentas y módulos.' : 'Los cambios se guardan al instante.';
    }

    /* ---- vista «acceso»: formulario de administrador ---- */
    var accEmail = $('ccEmail'), accPass = $('ccPass'), accBtn = $('ccEntrar'), accErr = $('ccErr'), accEnv = false;
    function accError(txt, enlace, campo) {
        $('ccErrTxt').textContent = txt || ''; $('ccErrLink').hidden = !enlace; accErr.hidden = !txt;
        accEmail.removeAttribute('aria-invalid'); accPass.removeAttribute('aria-invalid');
        if (campo) campo.setAttribute('aria-invalid', 'true');
    }
    function accPreparar() {
        accError('', false); accPass.value = ''; accVer(false);
        var n = $('ccSesNota');
        if (sesionInfo) { n.textContent = 'Tu sesión (' + (sesionInfo.email || '') + ' · ' + (ROLES[sesionInfo.rol] || sesionInfo.rol || '') + ') no es de administrador.'; n.hidden = false; } else n.hidden = true;
        accEstado(false);
        accEmail.focus({ preventScroll: true });
    }
    function accEstado(env) {
        accEnv = env; accBtn.disabled = env; accBtn.textContent = env ? 'Entrando…' : 'Entrar';
        $('ccAcc').setAttribute('aria-busy', env ? 'true' : 'false');
    }
    function accVer(ver) {
        accPass.type = ver ? 'text' : 'password';
        var b = $('ccVer'); b.textContent = ver ? 'Ocultar' : 'Ver'; b.setAttribute('aria-pressed', ver ? 'true' : 'false'); b.setAttribute('aria-label', ver ? 'Ocultar la contraseña' : 'Mostrar la contraseña');
    }
    $('ccVer').addEventListener('click', function () { accVer(accPass.type === 'password'); accPass.focus(); });
    $('ccAcc').addEventListener('submit', function (ev) {
        ev.preventDefault();
        if (accEnv) return;
        var mail = accEmail.value.trim(), clave = accPass.value;
        if (!mail) { accError('Escribe tu correo.', false, accEmail); accEmail.focus(); return; }
        if (!clave) { accError('Escribe tu contraseña.', false, accPass); accPass.focus(); return; }
        accError('', false); accEstado(true);
        api('POST', '/api/plataforma/entrar', { email: mail, password: clave }).then(function (d) {
            var rol = d && d.rol;
            if (rol !== 'administrador') { var e = new Error('Esta cuenta no es de administrador.'); e.status = 403; throw e; }
            var ses = { email: (d && d.email) || mail, rol: rol };
            accPass.value = ''; accEstado(false);
            if (!cc.abierto || cc.vista !== 'acceso') { cargarModulos(); return; }
            cc.entrando = true; sesionInfo = ses; pintarSesion();      // sesión provisional; /api/modulos la confirma y trae permisos
            ccVista('cuentas'); ccEstado('carga', 'Cargando cuentas…', null); ccAvisar('', false);
            ccCargar();
            ccPanel.focus({ preventScroll: true });
            cargarModulos().then(function () {
                cc.entrando = false;
                if (!esAdmin()) { sesionInfo = ses; pintarSesion(); }
            });
        }).then(null, function (e) {
            accEstado(false);
            var st = e && e.status;
            accError(e && e.message ? e.message : 'No se pudo entrar. Inténtalo de nuevo.', st === 409, st === 401 ? accPass : null);
            if (st === 401) { accPass.select(); accPass.focus(); }
        });
    });
    function ccCerrar(devolver) {
        if (!cc.abierto) return;
        cc.abierto = false; menuCerrar(false); confCerrar(false); invCerrar(false); enlCerrar(false);
        nucBtn.setAttribute('aria-expanded', 'false');
        ccEl.dataset.abierto = 'false';
        tCerrar = setTimeout(function () { ccEl.hidden = true; }, mqQuieto.matches ? 0 : 280);
        portal.inert = false; escena.removeAttribute('data-cc'); arrancar();
        if (devolver !== false && !nucBtn.hidden) nucBtn.focus();
    }
    nucBtn.addEventListener('click', function () { if (cc.abierto) ccCerrar(true); else ccAbrir(); });
    var ccDown = false;
    ccEl.addEventListener('pointerdown', function (e) { ccDown = e.target === ccEl; });
    ccEl.addEventListener('click', function (e) { if (ccDown && e.target === ccEl) ccCerrar(true); ccDown = false; });
    document.addEventListener('keydown', function (e) {
        if (!cc.abierto) return;
        if (e.key === 'Escape') {
            e.preventDefault();
            if (!ccMenu.hidden) menuCerrar(true); else if (!ccConf.hidden) confCerrar(true); else if (!invForm.hidden) invCerrar(true); else if (!enlEl.hidden) enlCerrar(true); else ccCerrar(true);
            return;
        }
        if (e.key !== 'Tab') return;
        var f = Array.prototype.filter.call(ccPanel.querySelectorAll('button, input, select, a[href]'), function (x) { return !x.disabled && x.getClientRects().length > 0; });
        if (!f.length) { e.preventDefault(); return; }
        var a = document.activeElement, p = f[0], u = f[f.length - 1];
        if (!ccPanel.contains(a) || a === ccPanel) { e.preventDefault(); (e.shiftKey ? u : p).focus(); }
        else if (e.shiftKey && a === p) { e.preventDefault(); u.focus(); }
        else if (!e.shiftKey && a === u) { e.preventDefault(); p.focus(); }
    });
    addEventListener('resize', function () { menuCerrar(false); });

    /* ================= arranque ================= */
    leerColores(); ajustarCampo(); pintarCampo(0);
    cargar();
})();

/* v1.4.63: easter egg. Cinco estrellas del fondo destellan suave, una tras otra; al tocarlas en ese orden (ratón o dedo)
   aparece el crédito. Son botones pequeños en los márgenes (no tapan módulos); un toque fuera de orden reinicia la cuenta. */
(function () {
    'use strict';
    var POS = [[3.5, 30], [96.5, 22], [95.5, 60], [4.5, 74], [50, 97]];   // % de ancho / alto, en orden de destello
    var capa = document.createElement('div'), paso = 0, reinicio = 0;
    capa.className = 'egg-capa'; capa.setAttribute('aria-hidden', 'true');
    POS.forEach(function (p, i) {
        var b = document.createElement('button');
        b.type = 'button'; b.tabIndex = -1; b.className = 'egg-est';
        b.style.left = p[0] + '%'; b.style.top = p[1] + '%'; b.style.setProperty('--n', i);
        b.addEventListener('click', function (e) {
            e.stopPropagation();
            clearTimeout(reinicio);
            if (i !== paso) { paso = i === 0 ? 1 : 0; marcar(); return; }
            paso++; marcar();
            if (paso === POS.length) { paso = 0; marcar(); credito(); return; }
            reinicio = setTimeout(function () { paso = 0; marcar(); }, 8000);   // si se deja a medias, vuelve a empezar
        });
        capa.appendChild(b);
    });
    function marcar() {
        Array.prototype.forEach.call(capa.children, function (b, j) { b.classList.toggle('egg-ok', j < paso); });
    }
    function credito() {
        var prev = document.getElementById('eggCred');
        if (prev) prev.remove();
        var d = document.createElement('div');
        d.id = 'eggCred'; d.className = 'egg-fondo';
        d.innerHTML = '<div class="egg-pop" role="dialog" aria-modal="true" aria-labelledby="eggT">' +
            '<span class="egg-brillo" aria-hidden="true">✦</span>' +
            '<p id="eggT" class="egg-t">Creado y desarrollado por<br><b>Jair Molina Arce</b></p>' +
            '<a class="egg-link" target="_blank" rel="noopener">jairmolina.dev</a>' +
            '<button type="button" class="egg-x">Cerrar</button></div>';
        function cerrar() { d.remove(); document.removeEventListener('keydown', esc); }
        function esc(e) { if (e.key === 'Escape') cerrar(); }
        d.addEventListener('click', function (e) { if (e.target === d) cerrar(); });
        d.querySelector('.egg-x').addEventListener('click', cerrar);
        document.addEventListener('keydown', esc);
        d.querySelector('.egg-link').href = 'https://jairmolina.dev';   // enlace a un sitio (no un recurso): se asigna por propiedad por la regla de QA de recursos externos
        document.body.appendChild(d);
        d.querySelector('.egg-link').focus();
    }
    document.body.appendChild(capa);
})();
