/* login.js - Acceso con correo y contraseña. Único script público: no usa common.js (que necesita sesión). */
(function () {
    'use strict';
    const $ = (id) => document.getElementById(id);
    const params = new URLSearchParams(location.search);

    // ---- tema claro / oscuro (mismo ajuste `tqt.tema` que el resto de la app)
    const ICONOS = { sol: '<circle cx="12" cy="12" r="4"/><path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6 7 7M17 17l1.4 1.4M5.6 18.4 7 17M17 7l1.4-1.4"/>',
                     luna: '<path d="M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5z"/>' };
    function pintarTema() {
        const claro = document.documentElement.dataset.theme === 'light';
        $('icoTema').innerHTML = claro ? ICONOS.luna : ICONOS.sol;   // el icono muestra a qué tema se cambia
        const m = document.querySelector('meta[name="theme-color"]'); if (m) m.setAttribute('content', claro ? '#E9ECF1' : '#0A1020');
        $('tema').setAttribute('aria-pressed', String(claro));
    }
    $('tema').addEventListener('click', () => {
        const n = document.documentElement.dataset.theme === 'light' ? 'dark' : 'light';
        document.documentElement.dataset.theme = n;
        try { localStorage.setItem('tqt.tema', n); } catch (e) { /* sin almacenamiento */ }
        pintarTema();
    });
    pintarTema();

    /** Solo se vuelve a rutas internas de la app (nunca a otro sitio): evita redirecciones abiertas. */
    function destino() {
        const n = params.get('next') || '/';
        return /^\/(?!\/)[^\\\r\n]*$/.test(n) && !n.startsWith('/login') ? n : '/';
    }
    function post(url, body) {
        return fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), credentials: 'same-origin' })
            .then(async (r) => { let d = null; try { d = await r.json(); } catch (e) { d = null; } return { ok: r.ok, status: r.status, data: d }; })
            .catch(() => ({ ok: false, status: 0, data: null }));
    }
    const texto = (r) => (r.status === 0 ? 'Sin conexión con el servidor.' : r.status === 429 ? ((r.data && r.data.detail) || 'Demasiados intentos. Espera unos minutos.')
        : (r.data && typeof r.data.detail === 'string' ? r.data.detail : `Error ${r.status}`));

    function mostrarClave(aviso) {
        $('fLogin').hidden = true; $('fClave').hidden = false;
        $('sub').textContent = 'Cambiar contraseña';
        if (aviso) $('avisoClave').textContent = aviso;
        $('actual').focus();
    }

    $('ver').addEventListener('click', () => {
        const v = $('pass').type === 'password'; $('pass').type = v ? 'text' : 'password';
        $('ver').textContent = v ? 'Ocultar' : 'Ver'; $('ver').setAttribute('aria-pressed', String(v));
    });

    $('fLogin').addEventListener('submit', async (e) => {
        e.preventDefault();
        const email = $('email').value.trim(), password = $('pass').value;
        if (!email || !password) { $('msg').textContent = 'Escribe tu correo y tu contraseña.'; return; }
        $('entrar').disabled = true; $('msg').textContent = '';
        const r = await post('/api/auth/login', { email, password });
        $('entrar').disabled = false;
        if (!r.ok) { $('msg').textContent = texto(r); $('pass').value = ''; $('pass').focus(); return; }
        $('pass').value = '';
        if (r.data && r.data.debe_cambiar) { mostrarClave('Tu contraseña es la inicial. Cámbiala ahora (mínimo 10 caracteres) o hazlo más tarde.'); $('actual').value = ''; return; }
        location.replace(destino());
    });

    $('fClave').addEventListener('submit', async (e) => {
        e.preventDefault();
        const nueva = $('nueva').value;
        if (nueva !== $('repite').value) { $('msgClave').textContent = 'Las contraseñas nuevas no coinciden.'; return; }
        $('guardar').disabled = true; $('msgClave').textContent = '';
        const r = await post('/api/auth/cambiar-clave', { actual: $('actual').value, nueva });
        $('guardar').disabled = false;
        if (!r.ok) { $('msgClave').textContent = texto(r); return; }
        $('msgClave').className = 'msg ok'; $('msgClave').textContent = 'Contraseña cambiada.';
        setTimeout(() => location.replace(destino()), 700);
    });
    $('luego').addEventListener('click', () => location.replace(destino()));

    // ¿Ya hay sesión? Con ?cambiar=1 se abre directo el cambio de contraseña; si no, se entra a la app.
    fetch('/api/auth/yo', { credentials: 'same-origin' }).then((r) => (r.ok ? r.json() : null)).then((u) => {
        if (!u) return;
        if (params.get('cambiar') === '1') { $('email').value = u.email; mostrarClave(); } else location.replace(destino());
    }).catch(() => { /* sin sesión: se queda el formulario */ });
})();
