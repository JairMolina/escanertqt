/**
 * admin.js - Pantalla de administración (borrado, exportación y contraseña).
 * Sesión: POST /api/admin/login -> token (memoria + sessionStorage) enviado como cabecera X-Admin-Token.
 * Un 401 devuelve al login. La sesión dura 30 min; se avisa antes de que caduque.
 * Todo texto del servidor entra por textContent (helper h), nunca por innerHTML.
 */
document.addEventListener('DOMContentLoaded', () => {
    'use strict';
    const T = window.TQT;
    const { h, icon, toast, sheet } = T;
    const $ = (id) => document.getElementById(id);
    const KEY = 'tqt.admin';
    const SESION_MS = 30 * 60 * 1000;

    T.hydrateIcons();
    $('btnTheme').replaceChildren(icon(T.currentTheme() === 'light' ? 'moon' : 'sun'));
    $('btnTheme').addEventListener('click', () => { const t = T.toggleTheme(); $('btnTheme').replaceChildren(icon(t === 'light' ? 'moon' : 'sun')); });
    function marca() {
        const NS = 'http://www.w3.org/2000/svg';
        const svg = document.createElementNS(NS, 'svg'); svg.setAttribute('viewBox', '0 0 32 32'); svg.setAttribute('class', 'brand-mark'); svg.setAttribute('aria-hidden', 'true');
        ['M3 3h11v11H3z', 'M18 3h11v11H18z', 'M3 18h11v11H3z'].forEach((d) => { const p = document.createElementNS(NS, 'path'); p.setAttribute('d', d); p.setAttribute('fill', 'none'); p.setAttribute('stroke', 'currentColor'); p.setAttribute('stroke-width', '2.4'); svg.appendChild(p); });
        const dots = document.createElementNS(NS, 'path'); dots.setAttribute('d', 'M7 7h3v3H7zM22 7h3v3h-3zM7 22h3v3H7zM19 19h3v3h-3zM25 19h4v3h-4zM19 25h4v4h-4zM26 25h3v4h-3z'); dots.setAttribute('fill', 'currentColor'); svg.appendChild(dots);
        return svg;
    }
    $('brandMark').replaceWith(marca()); $('loginMark').replaceWith(marca()); $('cerradaMark').replaceWith(marca());

    const nuevoMov = () => ({ items: [], total: 0, conteo: {}, categorias: {}, categoria: '', pedido: 0, cargando: false, error: '' });
    const S = { token: null, exp: 0, lotes: [], tarjetas: [], pcbs: [], selT: new Set(), selP: new Set(), timer: null, avisado: false, mov: nuevoMov() };
    // Cerrar sesión en una pestaña de administración cierra también las demás (el token vive en sessionStorage, por pestaña).
    let canal = null; try { canal = new BroadcastChannel('tqt-admin'); } catch (e) { canal = null; }
    if (canal) canal.onmessage = (ev) => { if (ev.data === 'logout' && !$('adminView').hidden) verLogin(null, { cerrada: true }); };

    // ------------------------------------------------------------------ sesión
    function guardar() { try { sessionStorage.setItem(KEY, JSON.stringify({ t: S.token, e: S.exp })); } catch (e) { /* solo memoria */ } }
    /** Caducidad real: sale del propio token firmado (campo exp, en segundos), no de lo que diga sessionStorage. */
    function expDeToken(t) {
        try { const c = String(t).split('.')[0].replace(/-/g, '+').replace(/_/g, '/'); const d = JSON.parse(atob(c + '='.repeat((4 - c.length % 4) % 4))); if (Number(d.exp) > 0) return Number(d.exp) * 1000; } catch (e) { /* nada */ }
        return 0;
    }
    /** Token guardado en la pestaña (solo candidato: se valida con el servidor antes de mostrar nada). */
    function restaurar() {
        try { const v = JSON.parse(sessionStorage.getItem(KEY) || 'null'); const e = v && v.t ? expDeToken(v.t) : 0; if (e > Date.now()) { S.token = v.t; S.exp = e; return true; } } catch (e) { /* nada */ }
        try { sessionStorage.removeItem(KEY); } catch (e) { /* nada */ }
        return false;
    }
    /** Destino tras el login: solo rutas internas conocidas (nada de //, http: ni otras). */
    function destinoNext() {
        try { const n = new URLSearchParams(location.search).get('next'); if (n === '/monitor') return n; } catch (e) { /* nada */ }
        return null;
    }
    function irNext() { const n = destinoNext(); if (n) { location.replace(n); return true; } return false; }
    function expiraEn(v) {
        if (typeof v === 'number') return Date.now() + (v > 1e12 ? v - Date.now() : v * 1000);
        if (typeof v === 'string' && v) { const d = Date.parse(v); if (!isNaN(d)) return d; const n = Number(v); if (!isNaN(n)) return Date.now() + n * 1000; }
        return Date.now() + SESION_MS;
    }
    /** Pantalla de acceso. opts.cerrada: el usuario acaba de cerrar sesión (no es un error) -> "Sesión cerrada" con dos salidas. */
    function verLogin(msg, opts) {
        opts = opts || {};
        S.token = null; S.exp = 0; try { sessionStorage.removeItem(KEY); } catch (e) { /* nada */ }
        clearInterval(S.timer); S.selT.clear(); S.selP.clear(); $('pass').value = '';
        S.tarjetas = []; S.pcbs = []; S.lotes = []; S.resumen = null; S.mov = nuevoMov();   // sin datos en memoria ni en el DOM tras salir
        ['resumenBox', 'tTabla', 'pTabla', 'banner', 'mLista', 'mCats'].forEach((id) => $(id).replaceChildren());
        ['mQ', 'mDesde', 'mHasta'].forEach((id) => { $(id).value = ''; }); $('mLote').replaceChildren(); $('mEstado').textContent = ''; $('mMas').hidden = true;
        document.querySelectorAll('.scrim, .sheet').forEach((n) => n.remove());   // hojas abiertas (p. ej. un 401 a mitad de borrado)
        $('adminView').hidden = true; $('loginView').hidden = false;
        setVista('resumen');
        if (opts.cerrada) {
            // Se quita ?next= de la URL: tras cerrar sesión ya no hay "destino pendiente" ni motivo que explicar.
            try { if (location.search) history.replaceState(null, '', location.pathname); } catch (e) { /* nada */ }
            $('loginForm').hidden = true; $('cerradaBox').hidden = false; $('loginErr').hidden = true;
            setTimeout(() => $('cerradaEscaner').focus(), 30);
            return;
        }
        mostrarFormLogin();
        if (msg) mostrarLoginErr(msg, opts.kind); else $('loginErr').hidden = true;
        setTimeout(() => $('pass').focus(), 30);
    }
    function mostrarFormLogin() {
        $('cerradaBox').hidden = true; $('loginForm').hidden = false;
        $('loginMotivo').hidden = !destinoNext();   // ?next=/monitor: se explica por qué se pide la contraseña
    }
    $('cerradaVolver').addEventListener('click', () => { mostrarFormLogin(); $('loginErr').hidden = true; $('pass').focus(); });
    function loginDeshabilitado(msg) {
        $('pass').disabled = true; $('btnLogin').disabled = true; mostrarLoginErr(msg);
    }
    function mostrarLoginErr(msg, kind) { const b = $('loginErr'); b.dataset.k = kind === 'warn' ? 'warn' : 'bad'; b.replaceChildren(icon('alert'), h('div', { class: 'grow' }, msg)); b.hidden = false; }
    function verAdmin() {
        $('loginView').hidden = true; $('adminView').hidden = false; S.avisado = false;
        clearInterval(S.timer); S.timer = setInterval(tick, 1000); tick();
        cargarTodo();
    }
    function tick() {
        const ms = S.exp - Date.now();
        if (ms <= 0) { verLogin('La sesión caducó. Vuelve a entrar.', { kind: 'warn' }); return; }
        const m = Math.floor(ms / 60000), s = Math.floor(ms % 60000 / 1000);
        const el = $('sesion'); el.textContent = `Sesión ${m}:${String(s).padStart(2, '0')}`; el.dataset.k = ms < 5 * 60000 ? 'warn' : '';
        if (ms < 5 * 60000 && !S.avisado) {
            S.avisado = true;
            const bx = $('banner'); bx.prepend(T.banner('warn', 'alert', h('b', null, 'La sesión caduca en menos de 5 minutos. '), 'Termina lo que estás haciendo o vuelve a entrar después.'));
        }
    }

    /** Llamada autenticada: {ok,status,data,error,headers}. 401 -> login. */
    async function adm(path, opts = {}) {
        const headers = { 'X-Admin-Token': S.token || '' };
        if (opts.body !== undefined) headers['Content-Type'] = 'application/json';
        const ctrl = new AbortController(); const timer = setTimeout(() => ctrl.abort(), opts.timeout || 30000);
        try {
            const res = await fetch(path, { method: opts.method || 'GET', headers, body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined, signal: ctrl.signal });
            if (res.status === 401 && !opts.noAuthRedirect) { verLogin('La sesión ya no es válida. Vuelve a entrar.', { kind: 'warn' }); return { ok: false, status: 401, data: null, error: 'Sesión no válida', res }; }
            if (opts.raw) {
                let error = ''; if (!res.ok) { error = `Error ${res.status}`; try { const j = await res.clone().json(); if (j && typeof j.detail === 'string') error = j.detail; } catch (e) { /* sin JSON */ } }
                return { ok: res.ok, status: res.status, res, error };
            }
            let data = null; try { data = await res.json(); } catch (e) { data = null; }
            const d = data && data.detail; const error = res.ok ? '' : (typeof d === 'string' ? d : Array.isArray(d) ? d.map((x) => x.msg || JSON.stringify(x)).join('; ') : d ? JSON.stringify(d) : `Error ${res.status}`);
            return { ok: res.ok, status: res.status, data, error, res };
        } catch (e) { return { ok: false, status: 0, data: null, error: 'Sin conexión con el servidor', res: null }; }
        finally { clearTimeout(timer); }
    }

    // ------------------------------------------------------------------ login
    let bloqueoTmr = null;
    $('loginForm').addEventListener('submit', async (ev) => {
        ev.preventDefault();
        if ($('btnLogin').disabled) return;
        const pw = $('pass').value; if (!pw.trim()) { mostrarLoginErr('Escribe la contraseña.'); return; }
        const b = $('btnLogin'); b.disabled = true; b.textContent = 'Entrando…';
        S.token = ''; const r = await adm('/api/admin/login', { method: 'POST', body: { password: pw }, noAuthRedirect: true, timeout: 15000 });
        b.textContent = 'Entrar'; b.disabled = false;
        if (r.ok && r.data && r.data.token) {
            S.token = r.data.token; S.exp = expDeToken(r.data.token) || Math.min(expiraEn(r.data.expira_en), Date.now() + SESION_MS); guardar(); $('pass').value = ''; if (irNext()) return; verAdmin(); return;
        }
        S.token = null; $('pass').value = '';
        mostrarLoginErr(r.status === 0 ? r.error : (r.error || 'No se pudo entrar.'));
        const espera = r.res && parseInt(r.res.headers.get('Retry-After') || '0', 10);
        if (r.status === 429 || espera) {
            b.disabled = true; let n = espera || 0; clearInterval(bloqueoTmr);
            if (n > 0) { b.textContent = `Espera ${n} s`; bloqueoTmr = setInterval(() => { n--; b.textContent = n > 0 ? `Espera ${n} s` : 'Entrar'; if (n <= 0) { clearInterval(bloqueoTmr); b.disabled = false; } }, 1000); }
            else setTimeout(() => { b.disabled = false; }, 5000);
        }
        $('pass').focus();
    });
    $('btnLogout').addEventListener('click', async () => {
        $('btnLogout').disabled = true;
        await adm('/api/admin/logout', { method: 'POST', noAuthRedirect: true, timeout: 4000 });   // borra la cookie de sesión
        $('btnLogout').disabled = false;
        if (canal) { try { canal.postMessage('logout'); } catch (e) { /* nada */ } }
        verLogin(null, { cerrada: true });
    });

    // ------------------------------------------------------------------ pestañas
    function setVista(v) {
        ['resumen', 'tarjetas', 'pcb', 'movimientos', 'riesgo', 'cuenta'].forEach((k) => { $('v-' + k).hidden = k !== v; });
        document.querySelectorAll('.desk-nav [role=tab]').forEach((b) => b.setAttribute('aria-selected', String(b.dataset.v === v)));
    }
    document.querySelector('.desk-nav').addEventListener('click', (e) => { const b = e.target.closest('[role=tab]'); if (b) { setVista(b.dataset.v); if (b.dataset.v === 'movimientos' && S.token) cargarMov(true); } });

    // ------------------------------------------------------------------ datos
    const bonito = (k) => { const s = String(k).replace(/_/g, ' ').trim(); return s.charAt(0).toUpperCase() + s.slice(1); };
    async function cargarTodo() {
        await Promise.all([cargarLotes(), cargarResumen()]);
        await Promise.all([cargarTarjetas(), cargarPcbs(), cargarMov(true)]);
    }
    async function cargarLotes() {
        const r = await fetch('/api/lotes').then((x) => x.json()).catch(() => []);
        S.lotes = Array.isArray(r) ? r : [];
        const fill = (sel, withAll) => {
            const keep = sel.value; sel.replaceChildren();
            if (withAll) sel.append(h('option', { value: '' }, 'Todos los lotes'));
            S.lotes.forEach((l) => sel.append(h('option', { value: String(l.id) }, T.loteNombre(l) + (l.activo ? ' · activo' : ''))));
            if (keep && [...sel.options].some((o) => o.value === keep)) sel.value = keep; else if (!withAll) { const a = S.lotes.find((l) => l.activo) || S.lotes[0]; if (a) sel.value = String(a.id); }
        };
        fill($('tLote'), false); fill($('vLote'), false); fill($('mLote'), true);
    }

    async function cargarResumen() {
        const box = $('resumenBox'); const r = await adm('/api/admin/resumen');
        box.replaceChildren();
        if (!r.ok) { if (r.status !== 401) box.append(T.banner('bad', 'alert', 'No se pudo leer el resumen: ', r.error)); return; }
        const d = r.data || {}; S.resumen = d;
        const tit = (t) => h('h2', { class: 'silk', style: 'margin-bottom:10px' }, t);
        const kb = (n) => n >= 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`;
        const tot = d.totales || {};
        box.append(h('div', null, tit('Totales'), h('div', { class: 'kpis' },
            [['Tarjetas', tot.tarjetas], ['PCB en inventario', tot.pcb], ['Movimientos registrados', tot.bitacora]].filter(([, v]) => typeof v === 'number').map(([k, v]) => h('div', { class: 'kpi' }, h('span', { class: 'lbl' }, k), h('span', { class: 'v' }, String(v)))),
            typeof d.bd_bytes === 'number' ? h('div', { class: 'kpi' }, h('span', { class: 'lbl' }, 'Tamaño de la base'), h('span', { class: 'v' }, kb(d.bd_bytes))) : null)));
        const ult = h('div', { class: 'stack', style: 'gap:8px' });
        box.append(h('div', null, h('div', { class: 'row', style: 'justify-content:space-between;margin-bottom:10px' }, h('h2', { class: 'silk' }, 'Últimos movimientos'),
            h('button', { class: 'btn btn-sm', type: 'button', id: 'verMov', onclick: () => { setVista('movimientos'); cargarMov(true); } }, 'Ver movimientos')), ult));
        cargarUltimos(ult);
        const lotes = Array.isArray(d.lotes) ? d.lotes : [];
        if (lotes.length) box.append(h('div', null, tit('Lotes'), h('div', { class: 'tablewrap', tabindex: '0', role: 'region', 'aria-label': 'Tabla de lotes' }, h('table', { class: 'grid' },
            h('thead', null, h('tr', null, ['Lote', 'Activo', 'Tarjetas', 'Por estado'].map((x) => h('th', null, x)))),
            h('tbody', null, lotes.map((l) => h('tr', null, h('td', { class: 'mono' }, l.codigo_lote), h('td', null, l.activo ? 'Sí' : 'No'), h('td', { class: 'mono' }, String(l.tarjetas)),
                h('td', null, Object.entries(l.por_estado || {}).map(([k, v]) => `${k} ${v}`).join(' · ') || '—'))))))));
        const inv = d.inventario || {}; const tipos = Object.keys(inv).sort();
        if (tipos.length) { const ciclos = [...new Set(tipos.flatMap((t) => Object.keys(inv[t])))].sort();
            box.append(h('div', null, tit('Inventario de PCB'), h('div', { class: 'tablewrap', tabindex: '0', role: 'region', 'aria-label': 'Tabla de inventario de PCB' }, h('table', { class: 'grid' },
                h('thead', null, h('tr', null, h('th', null, 'Tipo'), ciclos.map((c) => h('th', null, bonito(c.toLowerCase()))))),
                h('tbody', null, tipos.map((t) => h('tr', null, h('td', { class: 'mono' }, t), ciclos.map((c) => h('td', { class: 'mono' }, String(inv[t][c] || 0)))))))))); }
        const resp = Array.isArray(d.respaldos) ? d.respaldos : [];
        box.append(h('div', null, tit('Últimos respaldos'), resp.length
            ? h('div', { class: 'tablewrap', tabindex: '0', role: 'region', 'aria-label': 'Tabla de respaldos' }, h('table', { class: 'grid' }, h('thead', null, h('tr', null, h('th', null, 'Archivo'), h('th', null, 'Tamaño'))),
                h('tbody', null, resp.map((x) => h('tr', null, h('td', { class: 'mono' }, x.nombre), h('td', { class: 'mono' }, kb(x.bytes)))))))
            : h('p', { class: 'muted' }, 'Todavía no hay respaldos: se crea uno antes de cada borrado.')));
        if (!box.childNodes.length) box.append(T.empty('info', 'Sin datos de resumen', 'El servidor no devolvió totales.'));
    }

    async function cargarTarjetas() {
        const id = $('tLote').value;
        const r = await fetch(`/api/tarjetas?limit=500${id ? `&lote_id=${encodeURIComponent(id)}` : ''}`).then((x) => x.json()).catch(() => ({}));
        S.totalT = (r && r.total) || 0; S.tarjetas = (r && r.items) || []; S.selT = new Set([...S.selT].filter((i) => S.tarjetas.some((t) => t.id === i))); pintarTarjetas();
    }
    async function cargarPcbs() {
        const r = await fetch('/api/pcb?limit=5000').then((x) => x.json()).catch(() => ({}));
        S.totalP = (r && r.total) || 0; S.pcbs = (r && r.items) || []; S.selP = new Set([...S.selP].filter((i) => S.pcbs.some((p) => p.id === i))); pintarPcbs();
    }

    // ------------------------------------------------------------------ tarjetas
    $('tEstado').append(...T.TARJETA_ESTADOS.map((g) => h('option', { value: g.key }, g.label)));
    const tVis = () => { const est = $('tEstado').value, q = $('tQ').value.trim().toLowerCase();
        return S.tarjetas.filter((t) => (!est || T.estadoTarjeta(t).key === est) && (!q || [t.id_tarjeta_num, t.nombre_r1, t.nombre_r2, t.nombre_r3, t.mac_r1, t.mac_r2].some((v) => String(v || '').toLowerCase().includes(q)))); };
    function pintarTarjetas() {
        const rows = tVis(); const host = $('tTabla'); host.replaceChildren();
        if (!rows.length) host.append(T.empty('box', 'No hay tarjetas con esos filtros'));
        else {
            const all = h('input', { type: 'checkbox', 'aria-label': 'Seleccionar todas las visibles', onchange: (e) => { rows.forEach((t) => e.target.checked ? S.selT.add(t.id) : S.selT.delete(t.id)); pintarTarjetas(); } });
            all.checked = rows.every((t) => S.selT.has(t.id));
            const tb = h('tbody', null, rows.map((t) => h('tr', null,
                h('td', { class: 'col-check' }, h('input', { type: 'checkbox', 'aria-label': `Seleccionar tarjeta ${t.id_tarjeta_num}`, checked: S.selT.has(t.id) ? '' : null, onchange: (e) => { e.target.checked ? S.selT.add(t.id) : S.selT.delete(t.id); actTSel(); } })),
                h('td', { class: 'mono', style: 'font-size:16px;font-weight:600' }, t.id_tarjeta_num), h('td', { class: 'mono' }, t.nombre_r1 || '—'), h('td', { class: 'mono' }, t.nombre_r2 || '—'), h('td', { class: 'mono' }, t.nombre_r3 || '—'),
                h('td', null, T.tarjetaBadge(t)))));
            host.append(h('table', { class: 'grid' }, h('thead', null, h('tr', null, h('th', { class: 'col-check' }, all), ['Tarjeta', 'R1', 'R2', 'R3', 'Estado'].map((x) => h('th', null, x)))), tb));
        }
        if (S.totalT > S.tarjetas.length) host.append(h('p', { class: 'muted' }, `Se muestran ${S.tarjetas.length} de ${S.totalT} tarjetas del lote (tope de la pantalla).`));
        actTSel();
    }
    function actTSel() { const n = S.selT.size; $('tSel').textContent = `${n} seleccionada${n === 1 ? '' : 's'} de ${tVis().length} visibles`; $('tDel').disabled = !n; }
    ['tLote'].forEach((id) => $(id).addEventListener('change', () => { S.selT.clear(); cargarTarjetas(); }));
    $('tEstado').addEventListener('change', pintarTarjetas); $('tQ').addEventListener('input', T.debounce(pintarTarjetas, 200));
    $('tAllLote').addEventListener('click', () => { S.tarjetas.forEach((t) => S.selT.add(t.id)); pintarTarjetas(); });
    $('tNone').addEventListener('click', () => { S.selT.clear(); pintarTarjetas(); });

    $('tDel').addEventListener('click', () => {
        const ids = [...S.selT]; const n = ids.length; if (!n) return;
        const chk = h('input', { type: 'checkbox', id: 'liberar', checked: '', style: 'width:22px;height:22px;accent-color:var(--accent)' });
        const err = h('div', { class: 'hint err', role: 'alert' });
        const muestra = S.tarjetas.filter((t) => S.selT.has(t.id)).slice(0, 8).map((t) => t.id_tarjeta_num).join(', ');
        sheet({
            title: `Eliminar ${n} tarjeta${n === 1 ? '' : 's'}`,
            body: [h('p', { class: 'muted' }, `Tarjetas: ${muestra}${n > 8 ? ` y ${n - 8} más` : ''}.`),
                h('label', { class: 'row', for: 'liberar', style: 'gap:12px;min-height:48px' }, chk, h('span', null, h('b', null, 'Devolver las PCB al inventario'), h('br'), h('span', { class: 'muted' }, 'Si lo quitas, las PCB quedan dadas de baja.'))), err],
            actions: [{ label: 'Cancelar', kind: 'ghost', onClick: () => true }, { label: `Eliminar ${n}`, kind: 'danger', keepOpen: true, onClick: async () => {
                const r = await adm('/api/admin/tarjetas', { method: 'DELETE', body: { ids, liberar_pcb: chk.checked } });
                if (!r.ok) { err.textContent = r.error; return false; }
                const d = r.data || {}; const k = d.tarjetas_borradas ?? n; toast(`${k} tarjeta${k === 1 ? '' : 's'} eliminada${k === 1 ? '' : 's'}`, { kind: 'ok' });
                if (d.respaldo) $('banner').prepend(T.banner('ok', 'check', h('b', null, 'Listo. '), ' Respaldo guardado: ', h('code', { class: 'k' }, String(d.respaldo))));
                S.selT.clear(); cargarTodo(); return true;
            } }],
        });
    });

    // ------------------------------------------------------------------ PCB
    const pVis = (contar) => { const tipo = $('pTipo').value, ciclo = $('pCiclo').value, q = $('pQ').value.trim().toLowerCase();
        return S.pcbs.filter((p) => (!tipo || p.tipo === tipo) && (!ciclo || p.estado_ciclo === ciclo) && (!q || p.nombre.toLowerCase().includes(q) || (p.mac || '').toLowerCase().includes(q) || p.serie.includes(q))).sort((a, b) => a.serie.localeCompare(b.serie) || a.tipo.localeCompare(b.tipo)).slice(0, contar ? Infinity : 800); };
    function pintarPcbs() {
        const rows = pVis(); const host = $('pTabla'); host.replaceChildren();
        if (!rows.length) host.append(T.empty('box', 'No hay placas con esos filtros'));
        else {
            const all = h('input', { type: 'checkbox', 'aria-label': 'Seleccionar todas las visibles', onchange: (e) => { rows.forEach((p) => e.target.checked ? S.selP.add(p.id) : S.selP.delete(p.id)); pintarPcbs(); } });
            all.checked = rows.every((p) => S.selP.has(p.id));
            host.append(h('table', { class: 'grid' }, h('thead', null, h('tr', null, h('th', { class: 'col-check' }, all), ['Tipo', 'Nombre', 'MAC', 'Estado', 'Tarjeta'].map((x) => h('th', null, x)))),
                h('tbody', null, rows.map((p) => h('tr', null,
                    h('td', { class: 'col-check' }, h('input', { type: 'checkbox', 'aria-label': `Seleccionar ${p.nombre}`, checked: S.selP.has(p.id) ? '' : null, onchange: (e) => { e.target.checked ? S.selP.add(p.id) : S.selP.delete(p.id); actPSel(); } })),
                    h('td', null, T.tipoChip(p.tipo)), h('td', { class: 'mono' }, p.nombre), h('td', { class: 'mono' }, (p.tipo === 'R3' ? '—' : (p.mac || 'sin MAC'))), h('td', null, T.cicloBadge(p.estado_ciclo)), h('td', { class: 'mono' }, p.id_tarjeta_num || '—'))))));
        }
        const tot = pVis(true).length; if (tot > rows.length || S.totalP > S.pcbs.length) host.append(h('p', { class: 'muted' }, `Se muestran ${rows.length} de ${Math.max(tot, S.totalP)} placas: usa los filtros para ver el resto.`));
        actPSel();
    }
    function actPSel() { const n = S.selP.size; $('pSel').textContent = `${n} seleccionada${n === 1 ? '' : 's'}`; $('pDel').disabled = !n; }
    ['pTipo', 'pCiclo'].forEach((id) => $(id).addEventListener('change', pintarPcbs)); $('pQ').addEventListener('input', T.debounce(pintarPcbs, 200));
    $('pNone').addEventListener('click', () => { S.selP.clear(); pintarPcbs(); });
    $('pDel').addEventListener('click', () => {
        const ids = [...S.selP]; const n = ids.length; if (!n) return; const err = h('div', { class: 'hint err', role: 'alert' });
        const asig = S.pcbs.filter((p) => S.selP.has(p.id) && p.estado_ciclo === 'ASIGNADA').length;
        sheet({ title: `Eliminar ${n} placa${n === 1 ? '' : 's'}`,
            body: [h('p', { class: 'muted' }, 'Desaparecen del inventario y de las tarjetas donde estén.'), asig ? T.banner('warn', 'alert', `${asig} están asignadas a una tarjeta; esa tarjeta quedará incompleta.`) : null, err],
            actions: [{ label: 'Cancelar', kind: 'ghost', onClick: () => true }, { label: `Eliminar ${n}`, kind: 'danger', keepOpen: true, onClick: async () => {
                const r = await adm('/api/admin/pcb', { method: 'DELETE', body: { ids } });
                if (!r.ok) { err.textContent = r.error; return false; }
                const d = r.data || {}; const k = d.pcb_eliminadas ?? n; toast(`${k} placa${k === 1 ? '' : 's'} eliminada${k === 1 ? '' : 's'}`, { kind: 'ok' });
                if (d.respaldo) $('banner').prepend(T.banner('ok', 'check', h('b', null, 'Listo. '), ' Respaldo guardado: ', h('code', { class: 'k' }, String(d.respaldo))));
                S.selP.clear(); cargarTodo(); return true;
            } }] });
    });

    // ------------------------------------------------------------------ borrado con palabra
    function conteoLote(id) {
        const d = S.resumen || {}; const l = (Array.isArray(d.lotes) ? d.lotes : []).find((x) => String(x.id) === String(id));
        return l ? Object.entries(l).filter(([k, v]) => typeof v === 'number' && k !== 'id' && k !== 'mes' && k !== 'anio' && k !== 'activo') : [];
    }
    function confirmarPalabra({ titulo, texto, palabra, resumen, boton, ruta, cuerpo }) {
        const inp = h('input', { class: 'input mono', id: 'palabra', autocomplete: 'off', autocapitalize: 'characters', spellcheck: 'false', 'aria-describedby': 'palHint', placeholder: palabra });
        const err = h('div', { class: 'hint err', role: 'alert' });
        const sh = sheet({
            title: titulo,
            body: [h('p', null, texto),
                resumen.length ? h('div', { class: 'kpis' }, resumen.map(([k, v]) => h('div', { class: 'kpi', dataset: { k: 'bad' } }, h('span', { class: 'lbl' }, bonito(k)), h('span', { class: 'v' }, String(v))))) : null,
                T.banner('warn', 'info', 'Antes de borrar se crea un respaldo automático de la base de datos.'),
                h('div', { class: 'field' }, h('label', { for: 'palabra' }, `Escribe ${palabra} para confirmar`), inp, h('div', { class: 'hint', id: 'palHint' }, 'Mayúsculas, exactamente como se muestra.')), err],
            actions: [{ label: 'Cancelar', kind: 'ghost', onClick: () => true }, { label: boton, kind: 'danger', keepOpen: true, onClick: async () => {
                const r = await adm(ruta, { method: 'POST', body: cuerpo, timeout: 120000 });
                if (!r.ok) { err.textContent = r.error; return false; }
                const d = r.data || {}; const resp = d.respaldo || d.backup || d.archivo_respaldo || d.respaldo_nombre || '';
                $('banner').prepend(T.banner('ok', 'check', h('b', null, 'Listo. '), d.mensaje || 'Datos borrados.', resp ? [' Respaldo guardado: ', h('code', { class: 'k' }, String(resp))] : null));
                S.selT.clear(); S.selP.clear(); cargarTodo(); return true;
            } }],
            focus: true,
        });
        const btn = sh.el.querySelector('.actions .btn-danger'); btn.disabled = true;
        inp.addEventListener('input', () => { const ok = inp.value.trim() === palabra; btn.disabled = !ok; });
        // keepOpen + disabled reset: el helper reactiva el botón tras cada clic; se vuelve a evaluar la palabra.
        btn.addEventListener('click', () => setTimeout(() => { btn.disabled = inp.value.trim() !== palabra; }, 0));
        return sh;
    }
    $('btnVaciar').addEventListener('click', () => {
        const id = $('vLote').value; const l = S.lotes.find((x) => String(x.id) === id); if (!l) return;
        const t = S.tarjetas.length && $('tLote').value === id ? S.tarjetas.length : (l.registradas ?? null);
        const res = conteoLote(id); if (!res.length && t !== null) res.push(['tarjetas', t]);
        confirmarPalabra({ titulo: `Vaciar ${T.loteNombre(l)}`, texto: 'Se borrarán las tarjetas de este lote. Sus PCB vuelven al inventario como sueltas.', palabra: 'VACIAR', resumen: res, boton: 'Vaciar lote', ruta: `/api/admin/lote/${l.id}/vaciar`, cuerpo: { confirmar: 'VACIAR' } });
    });
    $('btnReset').addEventListener('click', () => {
        const d = (S.resumen || {}).totales || {}; const res = Object.entries(d).filter(([k, v]) => typeof v === 'number' && k !== 'bitacora');   // los movimientos no se borran
        confirmarPalabra({ titulo: 'Borrar TODO', texto: 'Se borran todas las tarjetas y PCB. Se conservan los lotes, la contraseña y los movimientos. Esta acción no se puede deshacer desde la app.', palabra: 'BORRAR TODO', resumen: res, boton: 'Borrar todo', ruta: '/api/admin/reset', cuerpo: { confirmar: 'BORRAR TODO' } });
    });

    // ------------------------------------------------------------------ movimientos (tabla escaneos: qué se hizo, cuándo y quién)
    const MV_PAGINA = 50;
    const MV_CAT = {   // categoría -> insignia (color + icono + texto: nunca solo color)
        alta: { t: 'Alta', k: 'ok', i: 'plus' }, edicion: { t: 'Edición', k: 'warn', i: 'edit' }, eliminacion: { t: 'Eliminación', k: 'bad', i: 'trash' },
        sesion: { t: 'Sesión', k: '', i: 'info' }, excel: { t: 'Excel', k: 'info', i: 'excel' }, otro: { t: 'Otro', k: '', i: 'circle' },
    };
    const MV_ORDEN = ['alta', 'edicion', 'eliminacion', 'sesion', 'excel', 'otro'];
    const MES_CORTO = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];
    const dos = (n) => String(n).padStart(2, '0');
    /** "2026-09-24 10:32:05" -> {texto:'hoy 10:32', completo:'24 sep 2026 10:32:05'}; nunca lanza. */
    function cuando(s) {
        const d = s ? new Date(String(s).replace(' ', 'T')) : null;
        if (!d || isNaN(d)) return { texto: '—', completo: '' };
        const hm = `${dos(d.getHours())}:${dos(d.getMinutes())}`, hoy = new Date(); hoy.setHours(0, 0, 0, 0);
        const dia = new Date(d); dia.setHours(0, 0, 0, 0); const dif = Math.round((hoy - dia) / 86400000);
        const completo = `${d.getDate()} ${MES_CORTO[d.getMonth()]} ${d.getFullYear()} ${hm}:${dos(d.getSeconds())}`;
        if (dif === 0) return { texto: `hoy ${hm}`, completo };
        if (dif === 1) return { texto: `ayer ${hm}`, completo };
        return { texto: `${d.getDate()} ${MES_CORTO[d.getMonth()]}${d.getFullYear() !== hoy.getFullYear() ? ' ' + d.getFullYear() : ''} ${hm}`, completo };
    }
    const mvBadge = (c) => { const m = MV_CAT[c] || MV_CAT.otro; return T.badge(m.t, m.k, m.i); };
    function mvQuery(extra) {
        const p = new URLSearchParams(); const q = $('mQ').value.trim();
        if (S.mov.categoria) p.set('categoria', S.mov.categoria);
        if (q) p.set('q', q);
        if ($('mDesde').value) p.set('desde', $('mDesde').value);
        if ($('mHasta').value) p.set('hasta', $('mHasta').value);
        if ($('mLote').value) p.set('lote_id', $('mLote').value);
        Object.entries(extra || {}).forEach(([k, v]) => p.set(k, String(v)));
        return p.toString();
    }
    const mvFiltrado = () => !!(S.mov.categoria || $('mQ').value.trim() || $('mDesde').value || $('mHasta').value || $('mLote').value);
    /** Carga la primera página (reset) o la siguiente ("Cargar más"). Respuestas viejas se descartan. */
    async function cargarMov(reset) {
        const M = S.mov; const id = ++M.pedido;
        const d1 = $('mDesde').value, d2 = $('mHasta').value;
        if (d1 && d2 && d1 > d2) { M.items = []; M.total = 0; M.error = 'La fecha «Desde» es posterior a «Hasta». Corrígela para ver resultados.'; pintarMov(); return; }
        M.cargando = true; M.error = ''; if (reset) $('mEstado').textContent = 'Cargando movimientos…'; $('mMas').disabled = true;
        const r = await adm(`/api/admin/movimientos?${mvQuery({ limite: MV_PAGINA, desplazamiento: reset ? 0 : M.items.length })}`);
        if (id !== M.pedido) return;
        M.cargando = false;
        if (r.status === 401) return;
        if (!r.ok) { M.error = r.status === 0 ? r.error : `No se pudieron leer los movimientos: ${r.error}`; if (reset) { M.items = []; M.total = 0; } pintarMov(); return; }
        const d = r.data || {};
        M.total = d.total || 0; M.conteo = d.conteo || {}; M.categorias = d.categorias || M.categorias;
        M.items = reset ? (d.items || []) : M.items.concat(d.items || []);
        pintarMov();
    }
    function pintarMov() {
        const M = S.mov; const cats = $('mCats'); cats.replaceChildren();
        const orden = MV_ORDEN.filter((k) => k in M.categorias || k in M.conteo);
        const suma = orden.reduce((a, k) => a + (M.conteo[k] || 0), 0);
        const chip = (clave, texto, n) => h('button', { class: 'mv-cat', type: 'button', 'aria-pressed': String(M.categoria === clave), dataset: { cat: clave },
            onclick: () => { M.categoria = clave; cargarMov(true); } }, texto, ' ', h('b', null, String(n)));
        cats.append(chip('', 'Todos', suma), ...orden.map((k) => chip(k, M.categorias[k] || (MV_CAT[k] || {}).t || k, M.conteo[k] || 0)));
        const host = $('mLista'); host.replaceChildren();
        if (M.error) host.append(T.banner('bad', 'alert', M.error));
        else if (!M.items.length) host.append(T.empty('list', 'Todavía no hay movimientos con esos filtros', mvFiltrado() ? 'Prueba con otro tipo, otra fecha o quita los filtros.' : 'Aquí aparecerán las altas, ediciones, eliminaciones, sesiones y exportaciones.'));
        else {
            const detalle = (m) => [m.valor, m.detalle].filter((x) => x !== null && x !== undefined && String(x) !== '');
            host.append(
                h('div', { class: 'tablewrap mv-table-wrap', tabindex: '0', role: 'region', 'aria-label': 'Tabla de movimientos' }, h('table', { class: 'grid mv-table' },
                    h('thead', null, h('tr', null, ['Cuándo', 'Tipo', 'Movimiento', 'Detalle', 'Operador', 'Lote'].map((x) => h('th', null, x)))),
                    h('tbody', null, M.items.map((m) => { const c = cuando(m.fecha);
                        return h('tr', { dataset: { cat: m.categoria } },
                            h('td', { class: 'mv-fecha' }, h('time', { datetime: m.fecha || null, title: c.completo }, c.texto)),
                            h('td', null, mvBadge(m.categoria)), h('td', null, m.titulo || m.evento),
                            h('td', { class: 'mv-det' }, m.valor ? h('span', { class: 'mono' }, m.valor) : null, m.detalle ? h('span', { class: 'd' }, m.detalle) : null, !m.valor && !m.detalle ? '—' : null),
                            h('td', null, m.operador || '—'), h('td', { class: 'mono' }, m.lote || '—')); })))),
                h('ul', { class: 'mv-cards', 'aria-label': 'Lista de movimientos' }, M.items.map((m) => { const c = cuando(m.fecha); const dt = detalle(m);
                    return h('li', { class: 'mv-card', dataset: { c: m.categoria } },
                        h('div', { class: 'top' }, mvBadge(m.categoria), h('time', { class: 'when', datetime: m.fecha || null, title: c.completo }, c.texto)),
                        h('div', { class: 'tit' }, m.titulo || m.evento),
                        m.valor ? h('div', { class: 'mono' }, m.valor) : null, m.detalle ? h('div', { class: 'meta' }, m.detalle) : null,
                        h('div', { class: 'meta' }, `Operador: ${m.operador || '—'} · Lote: ${m.lote || '—'}`)); })));
        }
        $('mEstado').textContent = M.error ? '' : `${M.items.length} de ${M.total} movimiento${M.total === 1 ? '' : 's'}`;
        const mas = $('mMas'); mas.hidden = M.error !== '' || M.items.length >= M.total; mas.disabled = false; mas.textContent = `Cargar más (${Math.min(MV_PAGINA, M.total - M.items.length)})`;
    }
    async function cargarUltimos(host) {
        const r = await adm('/api/admin/movimientos?limite=5');
        if (!r.ok) { if (r.status !== 401) host.append(h('p', { class: 'muted' }, 'No se pudieron leer los movimientos.')); return; }
        const its = (r.data && r.data.items) || [];
        if (!its.length) { host.append(h('p', { class: 'muted' }, 'Todavía no hay movimientos.')); return; }
        host.append(h('ul', { class: 'mv-resumen-lista', 'aria-label': 'Últimos cinco movimientos' }, its.map((m) => h('li', null,
            h('span', { class: 'when' }, cuando(m.fecha).texto), mvBadge(m.categoria), h('span', null, m.titulo || m.evento), m.valor ? h('span', { class: 'mono muted' }, m.valor) : null))));
    }
    const mvRecargar = T.debounce(() => cargarMov(true), 300);
    $('mQ').addEventListener('input', mvRecargar);
    ['mDesde', 'mHasta', 'mLote'].forEach((id) => $(id).addEventListener('change', () => cargarMov(true)));
    $('mMas').addEventListener('click', () => cargarMov(false));
    $('mAct').addEventListener('click', () => cargarMov(true));
    $('mLimpiar').addEventListener('click', () => { S.mov.categoria = ''; ['mQ', 'mDesde', 'mHasta', 'mLote'].forEach((id) => { $(id).value = ''; }); cargarMov(true); });
    /** CSV de lo filtrado: pide todas las páginas (200 por vez, tope 5000). Neutraliza fórmulas (=, +, -, @) para Excel. */
    $('mCsv').addEventListener('click', async () => {
        const b = $('mCsv'); b.disabled = true; const filas = []; let total = 0;
        for (let off = 0; off < 5000; off += 200) {
            const r = await adm(`/api/admin/movimientos?${mvQuery({ limite: 200, desplazamiento: off })}`);
            if (!r.ok) { b.disabled = false; if (r.status !== 401) $('banner').prepend(T.banner('bad', 'alert', h('b', null, 'No se pudo exportar. '), r.error)); return; }
            total = r.data.total; filas.push(...r.data.items); if (filas.length >= total || !r.data.items.length) break;
        }
        b.disabled = false;
        const cel = (v) => { let s = v === null || v === undefined ? '' : String(v); if (/^[=+\-@\t\r]/.test(s)) s = "'" + s; return `"${s.replace(/"/g, '""')}"`; };
        const lin = [['Fecha', 'Tipo', 'Movimiento', 'Valor', 'Detalle', 'Operador', 'Lote']].concat(filas.map((m) => [m.fecha, (MV_CAT[m.categoria] || MV_CAT.otro).t, m.titulo, m.valor, m.detalle, m.operador, m.lote]));
        const blob = new Blob(['﻿' + lin.map((f) => f.map(cel).join(',')).join('\r\n')], { type: 'text/csv;charset=utf-8' });
        const url = URL.createObjectURL(blob); const nombre = `movimientos_${new Date().toISOString().slice(0, 10)}.csv`;
        const a = h('a', { href: url, download: nombre, style: 'display:none' }); document.body.append(a); a.click();
        setTimeout(() => { a.remove(); URL.revokeObjectURL(url); }, 2000);
        toast(`Descargado: ${nombre} (${filas.length} movimientos)`, { kind: 'ok', ms: 4000 });
    });

    // ------------------------------------------------------------------ exportar Excel (fetch + blob con el token)
    $('btnExport').addEventListener('click', async () => {
        const id = $('tLote').value || $('vLote').value; const l = S.lotes.find((x) => String(x.id) === String(id)) || S.lotes.find((x) => x.activo) || S.lotes[0];
        const b = $('btnExport'); b.disabled = true;
        const r = await adm(`/api/admin/export/excel${l ? `?lote_id=${l.id}` : ''}`, { raw: true, timeout: 120000 });
        b.disabled = false;
        if (!r.ok) { if (r.status !== 401) $('banner').prepend(T.banner('bad', 'alert', h('b', null, 'No se pudo exportar. '), r.status === 423 ? 'El Excel está abierto; ciérralo y reintenta.' : r.error)); return; }
        const blob = await r.res.blob();
        const cd = r.res.headers.get('Content-Disposition') || ''; const m = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(cd);
        const nombre = m ? decodeURIComponent(m[1]) : `Control_Produccion_TQT_${l ? T.MESES[l.mes - 1] + '_' + l.anio : 'lote'}.xlsx`;
        const url = URL.createObjectURL(blob); const a = h('a', { href: url, download: nombre, style: 'display:none' }); document.body.append(a); a.click();
        setTimeout(() => { a.remove(); URL.revokeObjectURL(url); }, 2000);
        toast(`Descargado: ${nombre}`, { kind: 'ok', ms: 4000 });
    });

    // ------------------------------------------------------------------ cambiar contraseña
    $('formClave').addEventListener('submit', async (ev) => {
        ev.preventDefault(); const err = $('cErr'); err.textContent = ''; err.className = 'hint err';
        const a = $('cActual').value, n = $('cNueva').value, rep = $('cRep').value;
        if (!a) { err.textContent = 'Escribe la contraseña actual.'; return; }
        if (n.length < 8) { err.textContent = 'La contraseña nueva debe tener al menos 8 caracteres.'; return; }
        if (n !== rep) { err.textContent = 'La confirmación no coincide.'; return; }
        if (n === a) { err.textContent = 'La nueva debe ser distinta de la actual.'; return; }
        const b = $('btnClave'); b.disabled = true;
        const r = await adm('/api/admin/cambiar-clave', { method: 'POST', body: { actual: a, nueva: n }, noAuthRedirect: true }); b.disabled = false;
        // 401 = clave actual mal escrita (se queda en la pantalla) o sesión caducada (al login); el servidor las distingue por el texto.
        if (r.status === 401 && !/actual no es correcta/i.test(r.error || '')) { verLogin('La sesión ya no es válida. Vuelve a entrar.'); return; }
        if (!r.ok) { err.textContent = r.error || 'No se pudo cambiar la contraseña.'; return; }
        // El servidor invalida los tokens anteriores y devuelve uno nuevo: se adopta para no expulsar al admin en la siguiente acción.
        if (r.data && r.data.token) { S.token = r.data.token; S.exp = expDeToken(r.data.token) || Math.min(expiraEn(r.data.expira_en), Date.now() + SESION_MS); S.avisado = false; guardar(); }
        ['cActual', 'cNueva', 'cRep'].forEach((id) => { $(id).value = ''; }); err.className = 'hint ok'; err.textContent = 'Contraseña actualizada.';
        toast('Contraseña actualizada', { kind: 'ok' });
    });

    // ------------------------------------------------------------------ arranque
    /** Arranque: 1) ¿admin habilitado? 2) si hay token guardado, se VALIDA con el servidor antes de enseñar el panel. */
    async function arrancar() {
        $('loginView').hidden = false; $('adminView').hidden = true;
        let est = null; try { est = await fetch('/api/admin/estado', { cache: 'no-store' }).then((x) => x.json()); } catch (e) { /* sin red */ }
        if (est && est.habilitado === false) { verLogin(); loginDeshabilitado(est.mensaje || 'La administración está deshabilitada.'); return; }
        if (restaurar()) {
            const r = await adm('/api/admin/resumen', { noAuthRedirect: true, timeout: 10000 });
            if (r.ok) { if (irNext()) return; $('loginView').hidden = true; S.resumen = null; verAdmin(); return; }
            verLogin(r.status === 401 || r.status === 503 ? 'La sesión guardada ya no es válida. Vuelve a entrar.' : (r.error || 'No se pudo comprobar la sesión.'), { kind: r.status === 401 ? 'warn' : 'bad' });
            return;
        }
        verLogin();
        if (!est) mostrarLoginErr('Sin conexión con el servidor.');
    }
    // Atrás/Adelante desde la caché del navegador: nunca enseñar datos de una sesión ya cerrada.
    window.addEventListener('pageshow', (ev) => { if (ev.persisted) location.reload(); });
    arrancar();
});
