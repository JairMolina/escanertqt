/* planetas.js - Planetas 3D del portal (/inicio). Cada estrella de módulo es una esfera dibujada con WebGL:
   relieve procedural (ruido 3D sobre la superficie, sin texturas externas), normal perturbada por ese relieve, luz desde
   arriba-izquierda con terminador suave, atmósfera en el borde y rotación lenta. Tres tipos, como antes en CSS:
   gigante con bandas (posición 3n+1, su anillo sigue en CSS), rocoso con cráteres (3n+2) y tormenta en bandas (3n).
   Rendimiento (v1.4.75):
   - UN solo contexto WebGL compartido. El ruido caro se calcula UNA vez por planeta en un mapa equirectangular
     (normal + tono) y cada cuadro solo lo muestrea.
   - La compilación de los shaders no bloquea: se sondea con KHR_parallel_shader_compile y la tubería avanza cuando están listos.
   - La tubería empieza después de cargar la página y en tiempo inactivo; los planetas CSS de respaldo se ven mientras tanto.
   - 15 cuadros/s (la rotación es lenta). En móvil (modo lista) y con prefers-reduced-motion se dibuja una vez y no gira.
   - Sin WebGL, o si se pierde el contexto, queda el CSS de siempre.
   inicio.js llama a Planetas.limpiar() antes de reconstruir la lista y a Planetas.montar(lista) al final. */
(function () {
    'use strict';
    var PREC = '#ifdef GL_FRAGMENT_PRECISION_HIGH\nprecision highp float;\n#else\nprecision mediump float;\n#endif\n';

    /* horneado: el cuadrado completo es el mapa (x = longitud, y = latitud) */
    var VS_MAPA = 'attribute vec2 aPos; varying vec2 vP; void main(){ vP = aPos; gl_Position = vec4(aPos, 0.0, 1.0); }';
    var FS_MAPA = PREC +
        'varying vec2 vP;' +
        'uniform float uTipo; uniform float uSeed; uniform float uBump;' +
        'float hash(vec3 p){ p = fract(p * 0.3183099 + vec3(0.71, 0.113, 0.419)); p *= 17.0; return fract(p.x * p.y * p.z * (p.x + p.y + p.z)); }' +
        'float vn(vec3 x){' +
        '  vec3 i = floor(x); vec3 f = fract(x); f = f * f * (3.0 - 2.0 * f);' +
        '  return mix(mix(mix(hash(i), hash(i + vec3(1,0,0)), f.x), mix(hash(i + vec3(0,1,0)), hash(i + vec3(1,1,0)), f.x), f.y),' +
        '             mix(mix(hash(i + vec3(0,0,1)), hash(i + vec3(1,0,1)), f.x), mix(hash(i + vec3(0,1,1)), hash(i + vec3(1,1,1)), f.x), f.y), f.z);' +
        '}' +
        'float fbm(vec3 p){ float s = 0.0; float a = 0.5; for (int i = 0; i < 5; i++) { s += a * vn(p); p = p * 2.03 + vec3(1.7, 9.2, 3.1); a *= 0.5; } return s; }' +
        /* devuelve x = altura (relieve) e y = mezcla de color 0 (oscuro) .. 1 (claro) */
        'vec2 alto(vec3 p){' +
        '  if (uTipo < 0.5) {' +
        '    float banda = sin(p.y * 30.0 + 3.0 * fbm(p * vec3(1.5, 4.0, 1.5) + uSeed));' +
        '    float tor = smoothstep(0.34, 0.12, distance(p, normalize(vec3(0.3, -0.25, 0.92))));' +
        '    float t = 0.5 + 0.32 * banda + 0.32 * tor + 0.14 * (fbm(p * 5.0 + uSeed) - 0.5);' +
        '    return vec2(0.02 * fbm(p * 8.0 + uSeed) + 0.02 * tor, clamp(t, 0.0, 1.0));' +
        '  }' +
        '  if (uTipo < 1.5) {' +
        '    float lat = p.y + 0.22 * (fbm(p * vec3(2.5, 1.2, 2.5) + uSeed) - 0.5);' +
        '    float fino = fbm(p * vec3(4.0, 22.0, 4.0) + uSeed);' +
        '    float t = 0.5 + 0.4 * sin(lat * 15.0) + 0.2 * (fino - 0.5);' +
        '    return vec2(0.03 * fino, clamp(t, 0.0, 1.0));' +
        '  }' +
        '  float c = fbm(p * 1.6 + uSeed);' +
        '  float cr = vn(p * 3.2 + uSeed * 0.5);' +
        '  float crater = smoothstep(0.80, 0.92, cr);' +
        '  float grano = fbm(p * 6.0 + uSeed) - 0.5;' +
        '  float h = 0.8 * c + 0.1 * grano - 0.5 * crater;' +
        '  float mar = smoothstep(0.45, 0.6, c);' +
        '  float t = 0.3 + 0.45 * c - 0.25 * mar + 0.12 * grano - 0.3 * crater;' +
        '  return vec2(h, clamp(t, 0.0, 1.0));' +
        '}' +
        'void main(){' +
        '  float lon = vP.x * 3.14159265; float lat = vP.y * 1.57079633;' +
        '  vec3 p = vec3(cos(lat) * sin(lon), sin(lat), cos(lat) * cos(lon));' +
        '  vec2 h0 = alto(p); float e = 0.02;' +
        '  vec3 g = vec3(alto(p + vec3(e,0,0)).x - h0.x, alto(p + vec3(0,e,0)).x - h0.x, alto(p + vec3(0,0,e)).x - h0.x) / e;' +
        '  vec3 po = normalize(p - uBump * (g - dot(g, p) * p));' +
        '  gl_FragColor = vec4(po * 0.5 + 0.5, h0.y);' +
        '}';

    /* cada cuadro: esfera que muestrea el mapa girado uT */
    var VS = 'attribute vec2 aPos; varying vec2 vP; void main(){ vP = aPos * 1.2; gl_Position = vec4(aPos, 0.0, 1.0); }';
    var FS = PREC +
        'varying vec2 vP;' +
        'uniform sampler2D uMapa; uniform float uT; uniform float uTipo;' +
        'uniform vec3 uOsc; uniform vec3 uMed; uniform vec3 uCla; uniform vec3 uAtm;' +
        'void main(){' +
        '  float r2 = dot(vP, vP); float r = sqrt(r2);' +
        '  float disco = 1.0 - smoothstep(0.985, 1.0, r);' +
        '  float brillo = 0.55 * exp(-max(r - 1.0, 0.0) * 10.0);' +
        '  if (r > 1.0) { gl_FragColor = vec4(uAtm * brillo, brillo); return; }' +
        '  vec3 n = vec3(vP, sqrt(max(1.0 - r2, 0.0)));' +
        '  float c = cos(uT); float s = sin(uT);' +
        '  vec3 p = vec3(c * n.x + s * n.z, n.y, -s * n.x + c * n.z);' +
        '  vec2 uv = vec2(atan(p.x, p.z) * 0.15915494 + 0.5, asin(clamp(p.y, -1.0, 1.0)) * 0.31830989 + 0.5);' +
        '  vec4 m = texture2D(uMapa, uv);' +
        '  vec3 po = normalize(m.rgb * 2.0 - 1.0);' +
        '  vec3 nv = vec3(c * po.x - s * po.z, po.y, s * po.x + c * po.z);' +
        '  vec3 L = normalize(vec3(-0.55, 0.62, 0.56));' +
        '  float d = dot(nv, L);' +
        '  float lit = 0.07 + 0.93 * smoothstep(-0.2, 0.6, d);' +
        '  vec3 alb = mix(mix(uOsc, uMed, smoothstep(0.0, 0.5, m.a)), uCla, smoothstep(0.5, 1.0, m.a));' +
        '  vec3 col = alb * lit;' +
        '  col += vec3(pow(max(dot(nv, normalize(L + vec3(0.0, 0.0, 1.0))), 0.0), 36.0) * 0.07 * (1.0 - 0.3 * uTipo));' +
        '  col += uAtm * pow(1.0 - nv.z, 3.0) * 0.4 * (0.35 + 0.65 * smoothstep(-0.4, 0.6, d));' +
        '  gl_FragColor = vec4(col * disco + uAtm * brillo * (1.0 - disco), disco + brillo * (1.0 - disco));' +
        '}';

    var MW = 256, MH = 128;              // mapa equirectangular por planeta (potencia de 2: REPEAT en longitud)
    var FPS = 15;
    var ctx = null;                      // contexto compartido; false = sin WebGL (o perdido): queda el CSS
    var tam = 0, pl = [], cola = [], raf = 0, ult = 0, ultDib = 0, rafCola = 0;
    var mqQuieto = window.matchMedia ? matchMedia('(prefers-reduced-motion: reduce)') : null;
    var mqLista = window.matchMedia ? matchMedia('(max-width: 640px), (max-height: 540px)') : null;   // mismo corte que el modo lista del CSS

    function quieto() { return (mqQuieto && mqQuieto.matches) || (mqLista && mqLista.matches); }

    function rgb(hex) {
        var m = /^#([0-9a-f]{6}|[0-9a-f]{3})(?![0-9a-f])/i.exec(hex || '');
        var h = m ? m[1] : 'D9A441';
        if (h.length === 3) h = h.replace(/./g, '$&$&');
        return [0, 2, 4].map(function (i) { return parseInt(h.substr(i, 2), 16) / 255; });
    }
    function mezcla(c, o, t) { return [c[0] + (o[0] - c[0]) * t, c[1] + (o[1] - c[1]) * t, c[2] + (o[2] - c[2]) * t]; }

    /* crear el programa no bloquea: la compilación y el enlace se comprueban después (comprobar) */
    function programa(gl, vsSrc, fsSrc, nombres) {
        var p = gl.createProgram();
        [[gl.VERTEX_SHADER, vsSrc], [gl.FRAGMENT_SHADER, fsSrc]].forEach(function (par) {
            var s = gl.createShader(par[0]); gl.shaderSource(s, par[1]); gl.compileShader(s); gl.attachShader(p, s);
        });
        gl.bindAttribLocation(p, 0, 'aPos'); gl.linkProgram(p);
        return { p: p, nombres: nombres, estado: 0 };   // estado: 0 compilando, 1 listo, -1 fallo
    }
    function comprobar(gl, u, ext) {
        if (u.estado) return u.estado === 1;
        if (ext && !gl.getProgramParameter(u.p, ext.COMPLETION_STATUS_KHR)) return false;
        u.estado = gl.getProgramParameter(u.p, gl.LINK_STATUS) ? 1 : -1;
        if (u.estado === 1) u.nombres.forEach(function (n) { u[n] = gl.getUniformLocation(u.p, n); });
        return u.estado === 1;
    }

    function iniciar() {
        if (ctx !== null) return ctx;
        var cv = document.createElement('canvas');
        var gl = cv.getContext('webgl', { alpha: true, premultipliedAlpha: true, antialias: false, depth: false, stencil: false, powerPreference: 'low-power' });
        if (!gl) return (ctx = false);
        var mapa = programa(gl, VS_MAPA, FS_MAPA, ['uTipo', 'uSeed', 'uBump']);
        var esfera = programa(gl, VS, FS, ['uMapa', 'uT', 'uTipo', 'uOsc', 'uMed', 'uCla', 'uAtm']);
        var buf = gl.createBuffer();
        gl.bindBuffer(gl.ARRAY_BUFFER, buf);
        gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
        gl.enableVertexAttribArray(0); gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
        cv.addEventListener('webglcontextlost', function (e) { e.preventDefault(); perder(); });
        return (ctx = { gl: gl, cv: cv, mapa: mapa, esfera: esfera, fbo: gl.createFramebuffer(), ext: gl.getExtension('KHR_parallel_shader_compile'), ok: false });
    }

    /* true cuando ambos programas están listos; sin bloquear mientras compilan. Si fallan, se queda el CSS */
    function listo() {
        if (!ctx) return false;
        if (ctx.ok) return true;
        var a = comprobar(ctx.gl, ctx.mapa, ctx.ext), b = comprobar(ctx.gl, ctx.esfera, ctx.ext);
        if (ctx.mapa.estado < 0 || ctx.esfera.estado < 0) { ctx = false; cola = []; return false; }
        ctx.ok = a && b;
        return ctx.ok;
    }

    /* contexto perdido: se quitan los canvas y vuelve el planeta CSS */
    function perder() {
        parar(); cola = [];
        pl.forEach(function (p) { p.astro.classList.remove('gl'); if (p.cv.parentNode) p.cv.parentNode.removeChild(p.cv); });
        pl = []; ctx = false;
    }

    function hornear(it) {
        var gl = ctx.gl;
        var tex = gl.createTexture();
        gl.bindTexture(gl.TEXTURE_2D, tex);
        gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, MW, MH, 0, gl.RGBA, gl.UNSIGNED_BYTE, null);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.REPEAT);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
        gl.bindFramebuffer(gl.FRAMEBUFFER, ctx.fbo);
        gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, tex, 0);
        var m = ctx.mapa;
        gl.useProgram(m.p);
        gl.uniform1f(m.uTipo, it.tipo);
        gl.uniform1f(m.uSeed, it.seed * 17.31);
        gl.uniform1f(m.uBump, it.tipo === 2 ? 0.55 : it.tipo === 1 ? 0.2 : 0.35);
        gl.viewport(0, 0, MW, MH);
        gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
        gl.bindFramebuffer(gl.FRAMEBUFFER, null);

        var cv = document.createElement('canvas');
        cv.className = 'pl-cv'; cv.width = tam; cv.height = tam;
        var c = rgb(it.color);
        return {
            astro: it.astro, cv: cv, c2: cv.getContext('2d'), tex: tex, tipo: it.tipo,
            osc: mezcla(c, [0, 0, 0], 0.5), med: c, cla: mezcla(c, [1, 1, 1], 0.45),
            t: it.seed * 1.9, vel: (it.tipo === 1 ? 0.07 : it.tipo === 2 ? 0.05 : 0.085) * (0.8 + 0.4 * ((it.seed * 0.618) % 1))
        };
    }

    function pintar(p) {
        var gl = ctx.gl, e = ctx.esfera;
        gl.useProgram(e.p);
        gl.viewport(0, 0, tam, tam);
        gl.clearColor(0, 0, 0, 0); gl.clear(gl.COLOR_BUFFER_BIT);
        gl.bindTexture(gl.TEXTURE_2D, p.tex);
        gl.uniform1i(e.uMapa, 0); gl.uniform1f(e.uT, p.t); gl.uniform1f(e.uTipo, p.tipo);
        gl.uniform3fv(e.uOsc, p.osc); gl.uniform3fv(e.uMed, p.med); gl.uniform3fv(e.uCla, p.cla); gl.uniform3fv(e.uAtm, p.med);
        gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
        p.c2.clearRect(0, 0, tam, tam);
        p.c2.drawImage(ctx.cv, 0, 0);    // mismo turno que el dibujo: el búfer sigue vigente
    }
    function pintarTodos() { if (ctx && ctx.ok) pl.forEach(pintar); }

    /* un mapa por cuadro: la página responde mientras tanto y cada planeta aparece en cuanto está listo */
    function siguiente() {
        rafCola = 0;
        if (!ctx) return;
        if (!listo()) { if (ctx) rafCola = requestAnimationFrame(siguiente); return; }   // compilando: se vuelve a mirar en el siguiente cuadro
        var it = cola.shift();
        if (it && it.astro.isConnected && !it.astro.querySelector('.pl-cv')) {
            var p = hornear(it);
            pl.push(p);
            pintar(p);
            it.astro.insertBefore(p.cv, it.astro.querySelector('svg.ico'));
            it.astro.classList.add('gl');
        }
        if (cola.length) rafCola = requestAnimationFrame(siguiente);
        else arrancar();
    }

    function bucle(ahora) {
        raf = requestAnimationFrame(bucle);
        if (ahora - ultDib < 1000 / FPS - 2) return;
        var dt = ult ? Math.min((ahora - ult) / 1000, 0.1) : 0;
        ult = ultDib = ahora;
        pl.forEach(function (p) { p.t += dt * p.vel; pintar(p); });
    }
    function arrancar() {
        if (raf || !pl.length || quieto() || document.hidden) return;
        ult = 0; raf = requestAnimationFrame(bucle);
    }
    function parar() { if (raf) cancelAnimationFrame(raf); raf = 0; }
    function cambio() { parar(); pintarTodos(); arrancar(); }

    /* la tubería no compite con la carga de la página: empieza al cargar y en tiempo inactivo */
    function cuandoInactivo(fn) {
        var ir = function () {
            requestAnimationFrame(function () {
                (window.requestIdleCallback || function (f) { setTimeout(f, 50); })(fn, { timeout: 1000 });
            });
        };
        if (document.readyState === 'complete') ir(); else window.addEventListener('load', ir, { once: true });
    }

    document.addEventListener('visibilitychange', function () { if (document.hidden) parar(); else arrancar(); });
    [mqQuieto, mqLista].forEach(function (mq) {
        if (mq && mq.addEventListener) mq.addEventListener('change', cambio);
        else if (mq && mq.addListener) mq.addListener(cambio);
    });

    window.Planetas = {
        /* lista: [{ astro: elemento .astro, color: '#rrggbb', tipo: 0 tormenta | 1 gigante | 2 rocoso, seed: n }] */
        montar: function (lista) {
            // ?planetas=css: sin 3D (para comparar rendimiento); queda el planeta CSS de siempre
            if (/[?&]planetas=css\b/.test(location.search)) return;
            lista = lista.filter(function (it) { return it.astro; });
            if (!lista.length) return;
            // resolución del canvas: el planeta más grande en pantalla (activo crece 1,4) por la densidad de píxeles; tope 128
            var dpr = Math.min(window.devicePixelRatio || 1, 2), d = 0;
            lista.forEach(function (it) { d = Math.max(d, parseFloat(getComputedStyle(it.astro).getPropertyValue('--d')) || 26); });
            var nuevo = Math.max(32, Math.min(128, Math.ceil(d * 1.2 * (quieto() ? 1 : 1.4) * dpr)));
            cola = cola.concat(lista);
            cuandoInactivo(function () {
                if (!iniciar()) { cola = []; return; }
                if (nuevo !== tam) { tam = nuevo; ctx.cv.width = ctx.cv.height = tam; pl.forEach(function (p) { p.cv.width = p.cv.height = tam; }); pintarTodos(); }
                if (!rafCola) rafCola = requestAnimationFrame(siguiente);
            });
        },
        limpiar: function () {
            parar();
            if (rafCola) cancelAnimationFrame(rafCola);
            rafCola = 0; cola = []; ult = 0;
            if (ctx && ctx.gl) pl.forEach(function (p) { ctx.gl.deleteTexture(p.tex); });
            pl = [];
        }
    };
})();
