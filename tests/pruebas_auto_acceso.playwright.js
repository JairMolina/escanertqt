async (page, baseUrl, correo, clave) => {
    // Solo lectura salvo UN intento de login inválido (correo inexistente). El login válido solo corre si se pasan correo y clave.
    // Uso: async (page, 'http://127.0.0.1:PUERTO', [correo], [clave]); sin correo/clave se omite el login válido.
    const base = String(baseUrl || '').replace(/\/+$/, ''), ruta = base + '/pruebas-automaticas/acceso';
    const ok = (x, msg) => { if (!x) throw Error(msg); };
    ok(/^https?:\/\//.test(base), 'Indica la URL base, por ejemplo http://127.0.0.1:8080');
    const browser = page.context().browser(), errores = [], resumen = [];
    const abrir = async (opts, url) => {
        const c = await browser.newContext(Object.assign({ viewport: { width: 1280, height: 800 } }, opts));
        const p = await c.newPage();
        p.on('pageerror', e => errores.push('pageerror: ' + e.message));
        p.on('console', m => { if (m.type() === 'error') errores.push('console: ' + m.text()); });
        const r = await p.goto(url || ruta, { waitUntil: 'load' });
        return { c, p, r };
    };
    const mismaOrigen = (p, url) => new URL(p.url()).origin === new URL(url).origin;
    try {
        // 1. Carga, título, campos con label
        let { c, p, r } = await abrir({});
        try {
            ok(r && r.ok(), 'La página de acceso no responde 2xx: ' + (r && r.status()));
            ok(/Pruebas automáticas/i.test(await p.title()), 'Título sin «Pruebas automáticas»: ' + await p.title());
            const correoCampo = p.getByLabel(/correo/i), claveCampo = p.getByLabel(/contraseña/i).first();
            await correoCampo.first().waitFor(); await claveCampo.waitFor();
            ok(await p.locator('#email[type=email]').count() === 1 && await p.locator('#pass[type=password]').count() === 1, 'Faltan #email / #pass');
            ok(await p.locator('label[for=email]').count() === 1 && await p.locator('label[for=pass]').count() === 1, 'Campos sin <label for>');
            resumen.push('carga/título/labels');

            // 2. Foco visible al tabular
            await p.locator('body').click({ position: { x: 1, y: 1 } });
            const sinFoco = [];
            for (let i = 0; i < 6; i++) {
                await p.keyboard.press('Tab');
                const f = await p.evaluate(() => {
                    const e = document.activeElement;
                    if (!e || e === document.body) return null;
                    const s = getComputedStyle(e), r = e.getBoundingClientRect();
                    const outline = s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) > 0;
                    const sombra = s.boxShadow && s.boxShadow !== 'none';
                    return { id: e.id || e.tagName, visible: r.width > 0 && r.height > 0, marcado: outline || sombra };
                });
                if (f && f.visible && !f.marcado) sinFoco.push(f.id);
            }
            ok(!sinFoco.length, 'Foco no visible en: ' + sinFoco.join(', '));
            resumen.push('foco visible');

            // 3. Login inválido: error accesible, sin redirigir (única escritura)
            await p.fill('#email', 'qa-invalido@example.invalid');
            await p.fill('#pass', 'clave-incorrecta-qa-0000');
            await p.locator('#entrar').click();
            const msg = p.locator('#msg');
            await p.waitForFunction(() => (document.querySelector('#msg')?.textContent || '').trim().length > 0, null, { timeout: 15000 });
            ok(await msg.isVisible(), 'El error de login no es visible');
            const a11y = await msg.evaluate(e => ({ rol: e.getAttribute('role'), live: e.getAttribute('aria-live') }));
            ok(a11y.rol === 'alert' || a11y.live === 'assertive' || a11y.live === 'polite', 'El error no es role=alert ni aria-live');
            ok(new URL(p.url()).pathname.startsWith('/pruebas-automaticas/acceso'), 'Login inválido redirigió a ' + p.url());
            resumen.push('login inválido con error accesible');
        } finally { await c.close(); }

        // 4. Sin scroll horizontal en 320, 768 y 1280
        for (const w of [320, 768, 1280]) {
            ({ c, p } = await abrir({ viewport: { width: w, height: 800 } }));
            try {
                await p.getByLabel(/correo/i).first().waitFor();
                ok(await p.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), 'Scroll horizontal a ' + w + ' px');
            } finally { await c.close(); }
        }
        resumen.push('sin desborde 320/768/1280');

        // 5. Modo oscuro y claro sin errores de consola
        for (const esquema of ['dark', 'light']) {
            ({ c, p } = await abrir({ colorScheme: esquema }));
            try {
                await p.getByLabel(/correo/i).first().waitFor();
                const toggle = p.locator('#tema');
                if (await toggle.count()) { await toggle.click(); await toggle.click(); }
            } finally { await c.close(); }
        }
        ok(!errores.length, 'Errores de consola: ' + errores.join(' | '));
        resumen.push('tema oscuro/claro sin errores');

        // 6. ?next externo se ignora (la página no debe salir del origen al cargar; con credenciales se comprueba tras entrar)
        for (const sig of ['https://evil.test', '//evil.test', '/\\evil.test', 'javascript:alert(1)']) {
            const url = ruta + '?next=' + encodeURIComponent(sig);
            ({ c, p } = await abrir({}, url));
            try {
                ok(mismaOrigen(p, base), '?next=' + sig + ' sacó la página del origen: ' + p.url());
                await p.getByLabel(/correo/i).first().waitFor();
                if (correo && clave) {
                    await p.fill('#email', correo); await p.fill('#pass', clave);
                    await p.locator('#entrar').click();
                    await p.waitForURL(u => !u.pathname.startsWith('/pruebas-automaticas/acceso'), { timeout: 15000 }).catch(() => {});
                    ok(mismaOrigen(p, base), '?next=' + sig + ' redirigió fuera del origen: ' + p.url());
                }
            } finally { await c.close(); }
        }
        resumen.push(correo && clave ? '?next externo ignorado (con login válido)' : '?next externo no navega (login válido omitido: faltan correo/clave)');
        return 'OK: ' + resumen.join('; ');
    } finally { /* contextos cerrados arriba */ }
}
