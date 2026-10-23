/* documentacion.js — Documentación TEAM HW: presentación cinematográfica de los proyectos de la Plataforma I+D (GSAP 3.12.5 + ScrollTrigger,
 * servidos desde /static/documentacion/vendor). Cada módulo es un «distrito» con su color: mapa que se desliza en horizontal,
 * un capítulo por proyecto (foto que se abre, texto que se arma, aura del color del distrito) y botón magnético final.
 * El estado de cada módulo (disponible / sin acceso) sale de /api/modulos. Con «reducir movimiento» (o sin GSAP) la página
 * queda completa y quieta: solo funcionan el menú, los enlaces y el botón. */
(function () {
    'use strict';
    const $ = (s, r = document) => r.querySelector(s);
    const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
    const reducir = matchMedia('(prefers-reduced-motion: reduce)').matches;
    const conGsap = !!(window.gsap && window.ScrollTrigger);
    const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

    // ---------- los proyectos (id = el de app/modulos.py) ----------
    const PROYECTOS = [
        { id: 'escaner-tqt', nombre: 'Escáner TQT', color: '#D9A441', url: '/', img: 'tqt.jpg', distrito: 'Distrito Ámbar', lema: 'El taller de las tarjetas',
          desc: 'Recepción por QR, emparejado de MAC, programación de tarjetas R1, R2 y R3 con J-Link y entrega con etiqueta DYMO.',
          puntos: ['Recibir y emparejar por QR', 'Programar R1, R2 y R3', 'Inventario TQTR con consumo y pedidos'],
          alt: 'Tarjeta electrónica con chips y pistas de cobre' },
        { id: 'tpms', nombre: 'TPMS', color: '#FF6A00', url: '/tpms', img: 'tpms.jpg', distrito: 'Distrito Naranja', lema: 'La presión bajo control',
          desc: 'Sensores de presión de llantas: alta de cada placa por QR, firmware, lotes, inventario y costo por tarjeta.',
          puntos: ['Alta de placas por QR', 'Firmware y estado por placa', 'Costos e inventario de materiales'],
          alt: 'Auto deportivo gris al atardecer con la llanta en primer plano' },
        { id: 'skudo-antijammer', nombre: 'Skudo AntiJammer', color: '#39FF14', url: '/antijammer', img: 'garage.jpg', distrito: 'Distrito Verde', lema: 'Nadie apaga la señal',
          desc: 'Equipos contra inhibidores de señal: tarjetas RX y TX, cada una con su costo, sus materiales y su historial.',
          puntos: ['Tarjetas RX y TX por separado', 'Lotes, movimientos y Excel', 'Materiales que se descuentan al programar'],
          alt: 'Auto deportivo con faros encendidos en un estacionamiento con luz de neón' },
        { id: 'speedlocker', nombre: 'SpeedLocker', color: '#38BDF8', url: '/speedlocker', img: 'speed.jpg', distrito: 'Distrito Celeste', lema: 'La velocidad tiene límite',
          desc: 'Control y seguimiento de equipos SpeedLocker, desde el QR de la placa hasta su programación y su costo.',
          puntos: ['QR de placa a nombre único', 'Programación con firmware', 'Costo por tarjeta'],
          alt: 'Conductor al volante con la ciudad iluminada al fondo' },
        { id: 'skudo-sigfox', nombre: 'Skudo Sigfox', color: '#A855F7', url: '/sigfox', img: 'sigfox.jpg', distrito: 'Distrito Violeta', lema: 'Mensajes cortos, alcance largo',
          desc: 'Equipos Skudo con red Sigfox: alta, validación y la licencia anual separada del costo de producción.',
          puntos: ['Alta y validación de placas', 'Licencia anual aparte', 'Inventario de materiales'],
          alt: 'Circuito con pistas iluminadas en la oscuridad' },
        { id: 'caiquen', nombre: 'Caiquén', color: '#EF4444', url: '/caiquen', img: 'caiquen.jpg', distrito: 'Distrito Rojo', lema: 'La computadora del tractocamión',
          desc: 'Lectura de datos del motor por J1939: RPM, velocidad, temperaturas y códigos de falla de cada unidad y su remolque.',
          puntos: ['Puerto de diagnóstico J1939', 'Motor, velocidad y temperaturas', 'Códigos de falla por unidad'],
          alt: 'Tractocamión con remolque en una carretera al atardecer' },
        { id: 'impresora', nombre: 'Impresora', color: '#B8B8C8', url: '/impresora', img: 'impresora.jpg', distrito: 'Distrito Plata', lema: 'Cada activo con su etiqueta',
          desc: 'Libro de activos con etiqueta DYMO y QR: cualquiera lo escanea con el celular y ve su ficha.',
          puntos: ['Etiqueta DYMO con QR', 'Importar desde Excel', 'Impresión individual y por lote'],
          alt: 'Pasillo de almacén con estantes llenos de cajas' },
    ];

    // ---------- construir mapa, capítulos y cinta ----------
    $('#pista').innerHTML = PROYECTOS.map((p, i) => `
        <li class="parada" style="--c:${p.color}">
            <a href="#d-${p.id}"><span class="p-num">${String(i + 1).padStart(2, '0')}</span>
            <span class="p-dist">${esc(p.distrito)}</span><b class="p-nom">${esc(p.nombre)}</b><span class="p-lema">${esc(p.lema)}</span>
            <span class="p-ir" aria-hidden="true">→</span></a>
        </li>`).join('');
    $('#distritos').innerHTML = PROYECTOS.map((p, i) => `
        <section class="distrito${i % 2 ? ' par' : ''}" id="d-${p.id}" style="--c:${p.color}" aria-labelledby="t-${p.id}">
            <div class="d-foto"><div class="d-mueve"><img class="zoom" src="/static/documentacion/img/${p.img}" alt="${esc(p.alt)}" loading="lazy" decoding="async"></div></div>
            <div class="d-txt">
                <p class="d-num d-l"><span>${String(i + 1).padStart(2, '0')}</span> ${esc(p.distrito)}</p>
                <h2 class="d-nom d-l" id="t-${p.id}">${esc(p.nombre)}</h2>
                <p class="d-lema d-l">${esc(p.lema)}</p>
                <p class="d-desc d-l">${esc(p.desc)}</p>
                <ul class="d-puntos">${p.puntos.map((x) => `<li class="d-l">${esc(x)}</li>`).join('')}</ul>
                <p class="d-acc d-l"><a class="d-btn" href="${p.url}">Abrir ${esc(p.nombre)} <span aria-hidden="true">→</span></a><span class="d-est" data-id="${p.id}"></span></p>
            </div>
        </section>`).join('');
    const nombres = PROYECTOS.map((p) => p.nombre.toUpperCase());
    $('#cinta1').textContent = (nombres.join(' ✦ ') + ' ✦ ').repeat(2);
    $('#cinta2').textContent = (PROYECTOS.map((p) => p.distrito.toUpperCase()).join(' ✦ ') + ' ✦ ').repeat(2);

    // estado real de cada módulo para la cuenta (disponible, sin acceso, mantenimiento)
    fetch('/api/modulos', { credentials: 'same-origin', cache: 'no-store' }).then((r) => (r.ok ? r.json() : null)).then((d) => {
        const lista = d && (d.modulos || d);
        if (!Array.isArray(lista)) return;
        lista.forEach((m) => {
            const el = $(`.d-est[data-id="${m.id}"]`); if (!el) return;
            const sin = m.permitido === false, txt = sin ? 'Sin acceso' : m.estado === 'disponible' ? 'Disponible' : m.estado === 'mantenimiento' ? 'En mantenimiento' : 'Próximamente';
            el.textContent = txt; el.dataset.k = sin ? 'no' : m.estado;
        });
    }).catch(() => { /* sin estado: los botones siguen funcionando */ });

    // ---------- título partido en letras y frase en palabras ----------
    $$('#titulo .linea').forEach((l) => {
        const txt = l.textContent; l.textContent = ''; l.setAttribute('aria-hidden', 'true');
        for (const ch of txt) { const s = document.createElement('span'); s.className = 'letra'; s.textContent = ch === ' ' ? ' ' : ch; /* el espacio de «TEAM HW» no colapsa */ l.append(s); }
    });
    $('#titulo').setAttribute('aria-label', 'Documentación TEAM HW');
    const frase = $('.frase');
    frase.innerHTML = frase.textContent.trim().split(/\s+/).map((p) => `<span class="pal">${esc(p)}</span>`).join(' ');

    // ---------- menú (celular) ----------
    const nav = $('#nav'), burger = $('#burger');
    function menu(abrir) {
        nav.classList.toggle('abierta', abrir);
        burger.setAttribute('aria-expanded', String(abrir));
        burger.setAttribute('aria-label', abrir ? 'Cerrar menú' : 'Abrir menú');
        document.body.style.overflow = abrir ? 'hidden' : '';
    }
    burger.addEventListener('click', () => menu(burger.getAttribute('aria-expanded') !== 'true'));
    $$('#menu a').forEach((a) => a.addEventListener('click', () => menu(false)));
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && nav.classList.contains('abierta')) { menu(false); burger.focus(); } });
    const fondoNav = () => nav.classList.toggle('solida', scrollY > 40);
    addEventListener('scroll', fondoNav, { passive: true }); fondoNav();

    // ---------- botón final: estallido de luces y entrada a la plataforma ----------
    const iman = $('#iman'), imanT = $('#imanT'), estado = $('#estado');
    let yendo = false;
    iman.addEventListener('click', () => {
        if (yendo) return; yendo = true;
        imanT.textContent = 'BIENVENIDO';
        estado.textContent = 'Abriendo la plataforma…';
        const ir = () => { location.href = '/inicio'; };
        if (reducir || !conGsap) { ir(); return; }
        const zona = $('#botonZona');
        PROYECTOS.concat(PROYECTOS, PROYECTOS, PROYECTOS).forEach((p, i, arr) => {
            const c = document.createElement('i'); c.className = 'chispa'; c.style.background = p.color; zona.append(c);
            const ang = (i / arr.length) * Math.PI * 2, dist = 150 + Math.random() * 140;
            gsap.set(c, { rotation: (ang * 180) / Math.PI + 90 });
            gsap.to(c, { x: Math.cos(ang) * dist, y: Math.sin(ang) * dist, opacity: 0, scale: .4, duration: 1 + Math.random() * .5, ease: 'expo.out', onComplete: () => c.remove() });
        });
        gsap.fromTo(iman, { scale: .9 }, { scale: 1, duration: .8, ease: 'elastic.out(1, .4)' });
        setTimeout(ir, 1100);
    });
    addEventListener('pageshow', (e) => { if (e.persisted) { yendo = false; imanT.textContent = 'ENTRAR A LA PLATAFORMA'; estado.textContent = ''; } });

    if (reducir || !conGsap) { document.documentElement.classList.add('quieto'); return; }

    gsap.registerPlugin(ScrollTrigger);
    gsap.defaults({ ease: 'power3.out' });

    // ---------- intro ----------
    gsap.timeline({ defaults: { ease: 'expo.out' } })
        .from('#heroImg', { scale: 1.35, duration: 2.6, ease: 'power2.out' }, 0)
        .from('.nav', { y: -30, opacity: 0, duration: 1 }, .4)
        .from('#titulo .letra', { yPercent: 115, rotate: 6, duration: 1.4, stagger: .06 }, .35)
        .from('[data-intro]', { y: 24, opacity: 0, duration: 1, stagger: .15 }, 1.1);

    // ---------- parallax con el ratón (solo puntero fino) ----------
    const fino = matchMedia('(pointer: fine)').matches;
    if (fino) {
        const capas = [['#heroBg', 22], ['#heroSol', -50], ['#heroTxt', -12]].map(([s, f]) => ({
            f, x: gsap.quickTo(s, 'x', { duration: 1.2, ease: 'power3' }), y: gsap.quickTo(s, 'y', { duration: 1.2, ease: 'power3' }),
        }));
        $('.hero').addEventListener('pointermove', (e) => {
            const nx = e.clientX / innerWidth - .5, ny = e.clientY / innerHeight - .5;
            capas.forEach((c) => { c.x(nx * c.f); c.y(ny * c.f); });
        });
    }

    // ---------- hero con el scroll ----------
    gsap.to('#heroImg', { yPercent: 16, ease: 'none', scrollTrigger: { trigger: '.hero', start: 'top top', end: 'bottom top', scrub: true } });
    gsap.to('#heroTxt', { yPercent: -35, opacity: 0, ease: 'none', scrollTrigger: { trigger: '.hero', start: 'top top', end: '80% top', scrub: true } });

    // ---------- apariciones ----------
    ScrollTrigger.batch('.revela', { start: 'top 88%', once: true, onEnter: (els) => gsap.from(els, { y: 50, opacity: 0, duration: 1.1, stagger: .12 }) });
    gsap.fromTo('.frase .pal', { opacity: .12 }, { opacity: 1, ease: 'none', stagger: .1, scrollTrigger: { trigger: '.frase', start: 'top 80%', end: 'bottom 45%', scrub: true } });
    $$('.cuenta').forEach((el) => {
        const o = { v: 0 };
        gsap.to(o, { v: +el.dataset.n, duration: 1.6, ease: 'power2.out', snap: { v: 1 }, onUpdate: () => { el.textContent = o.v; }, scrollTrigger: { trigger: el, start: 'top 90%', once: true } });
    });
    gsap.fromTo('#ventana', { clipPath: 'inset(14% 18% 14% 18% round 28px)' }, { clipPath: 'inset(0% 0% 0% 0% round 0px)', ease: 'none',
        scrollTrigger: { trigger: '#ventana', start: 'top 85%', end: 'center 50%', scrub: true } });
    gsap.fromTo('#ventana img', { scale: 1.35 }, { scale: 1, ease: 'none', scrollTrigger: { trigger: '#ventana', start: 'top bottom', end: 'bottom top', scrub: true } });

    const mm = gsap.matchMedia();
    // ---------- mapa: en escritorio la pista se fija y se desliza en horizontal ----------
    mm.add('(min-width: 821px)', () => {
        const pista = $('#pista');
        const dist = () => pista.scrollWidth - innerWidth + 64;
        gsap.to(pista, { x: () => -dist(), ease: 'none', scrollTrigger: { trigger: '.mapa', start: 'top top', end: () => '+=' + dist(), scrub: 1, pin: true, invalidateOnRefresh: true } });
    });
    gsap.from('.parada', { y: 80, opacity: 0, duration: 1, stagger: .08, scrollTrigger: { trigger: '.pista', start: 'top 85%', once: true } });

    // ---------- capítulos: foto que se abre, texto que se arma, aura del color del distrito ----------
    const aura = $('#aura');
    $$('.distrito').forEach((d) => {
        const foto = $('.d-foto', d), par = d.classList.contains('par');
        gsap.fromTo(foto, { clipPath: par ? 'inset(0 0 0 100%)' : 'inset(0 100% 0 0)' }, { clipPath: 'inset(0 0% 0 0%)', duration: 1.4, ease: 'expo.inOut', scrollTrigger: { trigger: d, start: 'top 70%', once: true } });
        gsap.fromTo($('.d-mueve', d), { yPercent: -10 }, { yPercent: 10, ease: 'none', scrollTrigger: { trigger: d, start: 'top bottom', end: 'bottom top', scrub: true } });
        gsap.from($$('.d-l', d), { y: 40, opacity: 0, duration: .9, stagger: .07, scrollTrigger: { trigger: d, start: 'top 62%', once: true } });
        ScrollTrigger.create({ trigger: d, start: 'top 55%', end: 'bottom 45%', onToggle: (s) => { if (s.isActive) gsap.to(aura, { '--c': getComputedStyle(d).getPropertyValue('--c'), opacity: 1, duration: .8 }); } });
    });
    ScrollTrigger.create({ trigger: '#distritos', start: 'top 60%', end: 'bottom 40%', onLeave: () => gsap.to(aura, { opacity: 0, duration: .8 }), onLeaveBack: () => gsap.to(aura, { opacity: 0, duration: .8 }) });

    // ---------- cinta ----------
    gsap.to('.f1', { xPercent: -25, ease: 'none', scrollTrigger: { trigger: '.cinta', start: 'top bottom', end: 'bottom top', scrub: true } });
    gsap.fromTo('.f2', { xPercent: -25 }, { xPercent: 0, ease: 'none', scrollTrigger: { trigger: '.cinta', start: 'top bottom', end: 'bottom top', scrub: true } });

    // ---------- botón magnético ----------
    if (fino) {
        const zona = $('#botonZona');
        const bx = gsap.quickTo(iman, 'x', { duration: .6, ease: 'power3' }), by = gsap.quickTo(iman, 'y', { duration: .6, ease: 'power3' });
        const tx = gsap.quickTo(imanT, 'x', { duration: .6, ease: 'power3' }), ty = gsap.quickTo(imanT, 'y', { duration: .6, ease: 'power3' });
        zona.addEventListener('pointermove', (e) => {
            const r = iman.getBoundingClientRect(), dx = e.clientX - (r.left + r.width / 2), dy = e.clientY - (r.top + r.height / 2);
            bx(dx * .35); by(dy * .35); tx(dx * .15); ty(dy * .15);
        });
        zona.addEventListener('pointerleave', () => { bx(0); by(0); tx(0); ty(0); });
    }
    gsap.from('.final-luz', { opacity: 0, scale: .6, ease: 'none', scrollTrigger: { trigger: '.final', start: 'top bottom', end: 'center center', scrub: true } });

    addEventListener('load', () => ScrollTrigger.refresh());
})();
