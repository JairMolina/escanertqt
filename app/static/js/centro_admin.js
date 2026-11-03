/**
 * centro_admin.js (v1.4.88) - Secciones de datos del Centro de administración (portal /inicio).
 * Migradas desde /admin: Resumen, Movimientos, Borrado, Clave, exportar Excel y envío por correo.
 * Doble control: se abre con la sesión de administrador del portal y las acciones piden además la contraseña de /admin
 * (POST /api/admin/login -> token X-Admin-Token; mismo sessionStorage 'tqt.admin' que usa /admin).
 * Todo texto del servidor entra por textContent (helper h), nunca por innerHTML.
 */
(function () {
    'use strict';
    var KEY = 'tqt.admin', SESION_MS = 30 * 60 * 1000;
    var ccEl = document.getElementById('cc');
    if (!ccEl) return;
    var $ = function (id) { return document.getElementById(id); };
    var SECCIONES = ['cuentas', 'resumen', 'modulos', 'movimientos', 'borrado', 'clave'];
    var CON_LOTE = { movimientos: 1 };
    var S = { sec: 'cuentas', token: null, exp: 0, timer: null, lotes: [], resumen: null, mov: nuevoMov(), mo: nuevoMo(), cargado: {} };

    function nuevoMo() { return { mods: [], mod: '', col: '', cols: [], items: [], total: 0, sel: {}, nsel: 0, pedido: 0, error: '', listo: false }; }
    function nuevoMov() { return { items: [], total: 0, conteo: {}, categorias: {}, categoria: '', pedido: 0, error: '' }; }
    function h(tag, attrs) {
        var el = document.createElement(tag), i, k;
        for (k in (attrs || {})) {
            var v = attrs[k];
            if (v === null || v === undefined || v === false) continue;
            if (k === 'class') el.className = v; else if (k === 'text') el.textContent = v;
            else if (k.slice(0, 2) === 'on') el.addEventListener(k.slice(2), v);
            else if (k === 'dataset') Object.keys(v).forEach(function (d) { el.dataset[d] = v[d]; });
            else el.setAttribute(k, v === true ? '' : v);
        }
        for (i = 2; i < arguments.length; i++) add(el, arguments[i]);
        return el;
    }
    function add(el, c) {
        if (c === null || c === undefined || c === false) return;
        if (Array.isArray(c)) { c.forEach(function (x) { add(el, x); }); return; }
        el.appendChild(c.nodeType ? c : document.createTextNode(String(c)));
    }
    function limpiar(el) { while (el.firstChild) el.removeChild(el.firstChild); }
    function bonito(k) { var s = String(k).replace(/_/g, ' ').trim(); return s.charAt(0).toUpperCase() + s.slice(1); }
    function badge(t, k) { return h('span', { class: 'badge', dataset: { k: k || '' } }, t); }
    function vacio(t) { return h('p', { class: 'muted adm-vacio' }, t); }
    function banner(k, nodos) { return h('div', { class: 'banner', dataset: { k: k }, role: k === 'bad' ? 'alert' : 'status' }, h('div', { class: 'grow' }, nodos)); }
    function msg(texto, mal) { var m = $('admMsg'); m.textContent = ''; m.dataset.k = mal ? 'bad' : 'ok'; if (texto) setTimeout(function () { m.textContent = texto; }, 30); }
    function descargar(blob, nombre) {
        var url = URL.createObjectURL(blob), a = h('a', { href: url, download: nombre, style: 'display:none' });
        document.body.appendChild(a); a.click(); setTimeout(function () { a.remove(); URL.revokeObjectURL(url); }, 2000);
    }
    function nombreArchivo(res, def) {
        var m = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(res.headers.get('Content-Disposition') || '');
        return m ? decodeURIComponent(m[1]) : def;
    }

    /* ---------------- sesión de administración ---------------- */
    function expDeToken(t) {
        try { var c = String(t).split('.')[0].replace(/-/g, '+').replace(/_/g, '/'); var d = JSON.parse(atob(c + '='.repeat((4 - c.length % 4) % 4))); if (Number(d.exp) > 0) return Number(d.exp) * 1000; } catch (e) { /* nada */ }
        return 0;
    }
    function guardar() { try { sessionStorage.setItem(KEY, JSON.stringify({ t: S.token, e: S.exp })); } catch (e) { /* solo memoria */ } }
    function restaurar() {
        try { var v = JSON.parse(sessionStorage.getItem(KEY) || 'null'), e = v && v.t ? expDeToken(v.t) : 0; if (e > Date.now()) { S.token = v.t; S.exp = e; return true; } } catch (e) { /* nada */ }
        try { sessionStorage.removeItem(KEY); } catch (e) { /* nada */ }
        return false;
    }
    function olvidarDatos() {
        S.lotes = []; S.resumen = null; S.mov = nuevoMov(); S.mo = nuevoMo(); S.cargado = {};
        ['adm-resumen', 'mLista', 'mCats', 'admMsg', 'admDlg', 'moLista', 'moCols', 'moMod'].forEach(function (id) { limpiar($(id)); });
        $('admDlg').hidden = true; $('moSel').hidden = true; $('moMas').hidden = true; $('moEstado').textContent = ''; $('moQ').value = '';
    }
    function bloquear(motivo, mantenerToken) {
        clearInterval(S.timer);
        if (!mantenerToken) { S.token = null; S.exp = 0; try { sessionStorage.removeItem(KEY); } catch (e) { /* nada */ } }
        olvidarDatos();
        $('admBody').hidden = true; $('admGate').hidden = false; $('admPass').value = '';
        errGate(motivo || '');
    }
    function errGate(t) { var e = $('admGateErr'); e.textContent = t || ''; e.hidden = !t; }

    function adm(path, opts) {
        opts = opts || {};
        var headers = { 'X-Admin-Token': S.token || '' };
        if (opts.lote) headers['X-TQT-Lote'] = vistaLote();
        if (opts.body !== undefined) headers['Content-Type'] = 'application/json';
        var ctrl = new AbortController(), t = setTimeout(function () { ctrl.abort(); }, opts.timeout || 30000);
        return fetch(path, { method: opts.method || 'GET', headers: headers, credentials: 'same-origin', body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined, signal: ctrl.signal }).then(function (res) {
            if (res.status === 401 && !opts.noAuthRedirect) { bloquear('La sesión de administración ya no es válida. Escribe la contraseña de nuevo.'); return { ok: false, status: 401, error: 'Sesión caducada' }; }
            if (opts.raw) {
                if (res.ok) return { ok: true, status: res.status, res: res };
                return res.clone().json().then(function (j) { return j && typeof j.detail === 'string' ? j.detail : 'Error ' + res.status; }, function () { return 'Error ' + res.status; })
                    .then(function (e) { return { ok: false, status: res.status, error: e, res: res }; });
            }
            return res.json().then(null, function () { return null; }).then(function (data) {
                var d = data && data.detail, err = res.ok ? '' : (typeof d === 'string' ? d : Array.isArray(d) ? d.map(function (x) { return x.msg || JSON.stringify(x); }).join('; ') : d ? JSON.stringify(d) : 'Error ' + res.status);
                return { ok: res.ok, status: res.status, data: data, error: err, res: res };
            });
        }, function () { return { ok: false, status: 0, error: 'Sin conexión con el servidor' }; }).then(function (r) { clearTimeout(t); return r; });
    }
    function sesionApp(path) {      // rutas con la sesión de usuario (no admin): /api/tarjetas, /api/pcb, /api/lotes
        return fetch(path, { credentials: 'same-origin', cache: 'no-store', headers: { 'X-TQT-Lote': vistaLote() } }).then(function (r) { return r.json(); }).then(null, function () { return null; });
    }
    function vistaLote() { var v = $('admLote').value; return v === '0' || !v ? 'all' : v; }

    function tick() {
        var ms = S.exp - Date.now();
        if (ms <= 0) { bloquear('La sesión de administración caducó. Escribe la contraseña de nuevo.'); return; }
        var m = Math.floor(ms / 60000), s = Math.floor(ms % 60000 / 1000), el = $('admSes');
        el.textContent = 'Sesión ' + m + ':' + (s < 10 ? '0' : '') + s; el.dataset.k = ms < 5 * 60000 ? 'warn' : '';
    }
    function abrirCuerpo() {
        $('admGate').hidden = true; $('admBody').hidden = false;
        clearInterval(S.timer); S.timer = setInterval(tick, 1000); tick();
        S.cargado = {};
        cargarLotes().then(function () { mostrarSeccion(); });
    }
    $('admGate').addEventListener('submit', function (ev) {
        ev.preventDefault();
        var b = $('admGateBtn'), pw = $('admPass').value;
        if (!pw.trim()) { errGate('Escribe la contraseña.'); return; }
        b.disabled = true; b.textContent = 'Comprobando…'; errGate('');
        S.token = '';
        adm('/api/admin/login', { method: 'POST', body: { password: pw }, noAuthRedirect: true, timeout: 15000 }).then(function (r) {
            b.disabled = false; b.textContent = 'Desbloquear'; $('admPass').value = '';
            if (r.ok && r.data && r.data.token) { S.token = r.data.token; S.exp = expDeToken(r.data.token) || Date.now() + SESION_MS; guardar(); abrirCuerpo(); return; }
            S.token = null;
            errGate(r.status === 0 ? r.error : (r.error || 'No se pudo entrar.'));
            var espera = r.res && parseInt(r.res.headers.get('Retry-After') || '0', 10);
            if (r.status === 429 && espera) { b.disabled = true; var n = espera, iv = setInterval(function () { n--; b.textContent = n > 0 ? 'Espera ' + n + ' s' : 'Desbloquear'; if (n <= 0) { clearInterval(iv); b.disabled = false; } }, 1000); b.textContent = 'Espera ' + n + ' s'; }
            $('admPass').focus();
        });
    });
    $('admSalir').addEventListener('click', function () {
        adm('/api/admin/logout', { method: 'POST', noAuthRedirect: true, timeout: 4000 }).then(function () { bloquear('Sesión de administración bloqueada.'); $('admPass').focus(); });
    });

    /* ---------------- pestañas ---------------- */
    function irSeccion(sec) {
        if (SECCIONES.indexOf(sec) < 0) sec = 'cuentas';
        S.sec = sec; ccEl.dataset.sec = sec;
        Array.prototype.forEach.call($('ccTabs').querySelectorAll('[role=tab]'), function (b) { b.setAttribute('aria-selected', String(b.dataset.sec === sec)); b.tabIndex = b.dataset.sec === sec ? 0 : -1; });
        $('ccAdm').hidden = sec === 'cuentas';
        if (sec === 'cuentas') return;
        $('admLoteWrap').hidden = !CON_LOTE[sec];
        if (S.token && S.exp > Date.now() && !$('admBody').hidden) { mostrarSeccion(); return; }
        $('admBody').hidden = true; $('admGate').hidden = false;
        if (restaurar()) {      // token de la pestaña: se valida con el servidor antes de enseñar datos
            adm('/api/admin/resumen', { noAuthRedirect: true, timeout: 10000 }).then(function (r) {
                if (r.ok) abrirCuerpo(); else { bloquear(r.status === 401 ? 'La sesión guardada ya no es válida. Escribe la contraseña.' : (r.error || '')); }
            });
        } else setTimeout(function () { $('admPass').focus(); }, 30);
    }
    $('ccTabs').addEventListener('click', function (e) { var b = e.target.closest && e.target.closest('[role=tab]'); if (b) irSeccion(b.dataset.sec); });
    $('ccTabs').addEventListener('keydown', function (e) {
        var tabs = Array.prototype.slice.call($('ccTabs').querySelectorAll('[role=tab]')), i = tabs.indexOf(document.activeElement);
        if (i < 0) return;
        var n = e.key === 'ArrowRight' ? (i + 1) % tabs.length : e.key === 'ArrowLeft' ? (i - 1 + tabs.length) % tabs.length : e.key === 'Home' ? 0 : e.key === 'End' ? tabs.length - 1 : -1;
        if (n < 0) return;
        e.preventDefault(); tabs[n].focus(); irSeccion(tabs[n].dataset.sec);
    });
    function mostrarSeccion() {
        ['resumen', 'modulos', 'movimientos', 'borrado', 'clave'].forEach(function (k) { $('adm-' + k).hidden = k !== S.sec; });
        $('admLoteWrap').hidden = !CON_LOTE[S.sec];
        if (S.cargado[S.sec]) return;
        S.cargado[S.sec] = true;
        if (S.sec === 'resumen') cargarResumen(); else if (S.sec === 'movimientos') cargarMov(true); else if (S.sec === 'modulos') cargarModulos();
    }
    // Al cerrar el panel no queda ningún dato de administración en el DOM; al reabrirlo se pide la sección de cuentas.
    new MutationObserver(function () {
        if (ccEl.dataset.abierto === 'false') { clearInterval(S.timer); olvidarDatos(); if (S.sec !== 'cuentas') irSeccion('cuentas'); }
    }).observe(ccEl, { attributes: true, attributeFilter: ['data-abierto'] });

    /* ---------------- lotes ---------------- */
    function nombreLote(l) {
        var MESES = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'];
        if (l.mes >= 1 && l.mes <= 12 && l.anio && (l.tipo_lote || 'mes') === 'mes') return MESES[l.mes - 1] + ' ' + l.anio;
        return l.codigo_lote || 'Lote ' + l.id;
    }
    function cargarLotes() {
        return fetch('/api/lotes', { credentials: 'same-origin', cache: 'no-store' }).then(function (r) { return r.json(); }).then(null, function () { return []; }).then(function (r) {
            S.lotes = Array.isArray(r) ? r : [];
            var guardado = ''; try { guardado = localStorage.getItem('tqt.lote.vista') || ''; } catch (e) { /* nada */ }
            var prev = $('admLote').value || (guardado === 'all' ? '0' : guardado);
            [$('admLote'), $('vLote')].forEach(function (sel, i) {
                limpiar(sel);
                if (i === 0) sel.appendChild(h('option', { value: '0' }, 'Todos los lotes'));
                S.lotes.forEach(function (l) { sel.appendChild(h('option', { value: String(l.id) }, nombreLote(l) + (l.activo ? ' · activo' : ''))); });
                var quiere = i === 0 ? prev : '';
                if (quiere && Array.prototype.some.call(sel.options, function (o) { return o.value === quiere; })) sel.value = quiere;
                else { var a = S.lotes.filter(function (l) { return l.activo; })[0] || S.lotes[0]; if (a) sel.value = String(a.id); }
            });
        });
    }
    $('admLote').addEventListener('change', function () {
        try { localStorage.setItem('tqt.lote.vista', $('admLote').value === '0' ? 'all' : $('admLote').value); } catch (e) { /* nada */ }
        S.cargado = {}; mostrarSeccion();
    });

    /* ---------------- diálogo en línea (sin confirm() nativo) ---------------- */
    function dialogo(o) {
        var d = $('admDlg'), prev = document.activeElement;
        limpiar(d);
        var err = h('div', { class: 'adm-hint', role: 'alert' });
        var cerrar = function (dev) { d.hidden = true; limpiar(d); if (dev && prev && prev.focus && document.contains(prev)) prev.focus(); };
        var ok = h('button', { class: 'btn btn-sm ' + (o.peligro ? 'btn-danger' : 'btn-primary'), type: 'button', onclick: function () {
            ok.disabled = true; err.textContent = '';
            Promise.resolve(o.confirmar()).then(function (r) { ok.disabled = o.habilitado ? !o.habilitado() : false; if (r === true) cerrar(false); else if (typeof r === 'string') err.textContent = r; });
        } }, o.boton);
        if (o.habilitado) ok.disabled = !o.habilitado();
        d.appendChild(h('h3', { id: 'admDlgTit' }, o.titulo));
        add(d, o.cuerpo); d.appendChild(err);
        d.appendChild(h('div', { class: 'adm-dlg-acc' }, ok, h('button', { class: 'btn btn-sm btn-ghost', type: 'button', onclick: function () { cerrar(true); } }, 'Cancelar')));
        d.hidden = false; d.scrollIntoView({ block: 'nearest' });
        var f = d.querySelector('input'); (f || ok).focus();
        return { ok: ok, cerrar: cerrar };
    }

    /* ---------------- resumen ---------------- */
    function kb(n) { return n >= 1048576 ? (n / 1048576).toFixed(1) + ' MB' : Math.max(1, Math.round(n / 1024)) + ' KB'; }
    function tabla(cols, filas, etiqueta) {
        return h('div', { class: 'tablewrap', tabindex: '0', role: 'region', 'aria-label': etiqueta }, h('table', { class: 'grid' },
            h('thead', null, h('tr', null, cols.map(function (c) { return h('th', null, c); }))), h('tbody', null, filas)));
    }
    function tit(t) { return h('h3', { class: 'adm-tit' }, t); }
    function cargarResumen() {
        var box = $('adm-resumen');
        return adm('/api/admin/resumen', { lote: true }).then(function (r) {
            limpiar(box);
            if (!r.ok) { if (r.status !== 401) box.appendChild(banner('bad', ['No se pudo leer el resumen: ', r.error])); return; }
            var d = r.data || {}, tot = d.totales || {}; S.resumen = d;
            box.appendChild(h('div', null, tit('Totales'), h('div', { class: 'kpis' },
                [['Tarjetas', tot.tarjetas], ['PCB en inventario', tot.pcb], ['Movimientos registrados', tot.bitacora]].filter(function (x) { return typeof x[1] === 'number'; })
                    .map(function (x) { return h('div', { class: 'kpi' }, h('span', { class: 'lbl' }, x[0]), h('span', { class: 'v' }, String(x[1]))); }),
                typeof d.bd_bytes === 'number' ? h('div', { class: 'kpi' }, h('span', { class: 'lbl' }, 'Tamaño de la base'), h('span', { class: 'v' }, kb(d.bd_bytes))) : null)));
            var ult = h('div', { class: 'adm-ult' });
            box.appendChild(h('div', null, h('div', { class: 'adm-fila-sb' }, tit('Últimos movimientos'), h('button', { class: 'btn btn-sm', type: 'button', onclick: function () { irSeccion('movimientos'); } }, 'Ver movimientos')), ult));
            cargarUltimos(ult);
            var lotes = Array.isArray(d.lotes) ? d.lotes : [];
            if (lotes.length) box.appendChild(h('div', null, tit('Lotes'), tabla(['Lote', 'Activo', 'Tarjetas', 'Por estado'], lotes.map(function (l) {
                return h('tr', null, h('td', null, nombreLote(l), h('span', { class: 'mono t2' }, ' · ' + l.codigo_lote)), h('td', null, l.activo ? 'Sí' : 'No'), h('td', { class: 'mono' }, String(l.tarjetas)),
                    h('td', null, Object.keys(l.por_estado || {}).map(function (k) { return k + ' ' + l.por_estado[k]; }).join(' · ') || '—'));
            }), 'Tabla de lotes')));
            var inv = d.inventario || {}, tipos = Object.keys(inv).sort();
            if (tipos.length) {
                var ciclos = []; tipos.forEach(function (t) { Object.keys(inv[t]).forEach(function (c) { if (ciclos.indexOf(c) < 0) ciclos.push(c); }); }); ciclos.sort();
                box.appendChild(h('div', null, tit('Inventario de PCB'), tabla(['Tipo'].concat(ciclos.map(function (c) { return bonito(c.toLowerCase()); })), tipos.map(function (t) {
                    return h('tr', null, h('td', { class: 'mono' }, t), ciclos.map(function (c) { return h('td', { class: 'mono' }, String(inv[t][c] || 0)); }));
                }), 'Tabla de inventario de PCB')));
            }
            return adm('/api/admin/dymo/cable-r3-auto', { timeout: 8000 }).then(function (cr3) {
                if (cr3.ok && cr3.data) box.appendChild(bloqueCableR3(cr3.data));
                var btnBd = h('button', { class: 'btn', type: 'button', onclick: function () { descargarBd(btnBd); } }, 'Descargar copia de la base (.db)');
                box.appendChild(h('div', null, tit('Copia de la base de datos'), h('p', { class: 'muted' }, 'Copia completa y verificada de la base, hecha al momento (incluye usuarios y contraseñas cifradas). Úsala para restaurar en otro equipo.'), btnBd));
                var resp = Array.isArray(d.respaldos) ? d.respaldos : [];
                box.appendChild(h('div', null, tit('Últimos respaldos'), resp.length
                    ? tabla(['Archivo', 'Tamaño'], resp.map(function (x) { return h('tr', null, h('td', { class: 'mono' }, x.nombre), h('td', { class: 'mono' }, kb(x.bytes))); }), 'Tabla de respaldos')
                    : h('p', { class: 'muted' }, 'Todavía no hay respaldos: se crea uno antes de cada borrado.')));
            });
        });
    }
    function descargarBd(btn) {
        btn.disabled = true;
        adm('/api/admin/respaldo/descargar', { raw: true, timeout: 120000 }).then(function (r) {
            btn.disabled = false;
            if (!r.ok) { if (r.status !== 401) msg('No se pudo descargar la base: ' + (r.error || r.status), true); return; }
            r.res.blob().then(function (b) { var n = nombreArchivo(r.res, 'tqt_produccion.db'); descargar(b, n); msg('Descargado: ' + n + '. Contiene datos y cuentas reales: guárdalo en un lugar seguro.', false); });
        });
    }
    function bloqueCableR3(d0) {
        var chk = h('input', { type: 'checkbox', id: 'cableR3Auto', checked: d0.activo ? true : null }), est = h('p', { class: 'muted', 'aria-live': 'polite' });
        var pintar = function (d) { est.textContent = (d.activo ? 'Activada. ' : 'Desactivada. ') + (d.dymo_disponible ? 'DYMO compartida en línea.' : 'La DYMO compartida no está en línea: mientras siga así no se imprimirá (se reintenta en la siguiente actualización de la tarjeta).'); };
        pintar(d0);
        chk.addEventListener('change', function () {
            chk.disabled = true;
            adm('/api/admin/dymo/cable-r3-auto', { method: 'PUT', body: { activo: chk.checked }, timeout: 15000 }).then(function (r) {
                chk.disabled = false;
                if (!r.ok) { chk.checked = !chk.checked; if (r.status !== 401) msg('No se pudo guardar: ' + (r.error || r.status), true); return; }
                pintar(r.data);
                msg(r.data.activo ? 'Cable R3 automático activado' + (r.data.marcadas ? ' (' + r.data.marcadas + ' tarjetas que ya tenían R3 no se imprimirán)' : '') + '.' : 'Cable R3 automático desactivado.', false);
            });
        });
        return h('div', null, tit('Etiqueta «Cable R3» automática'),
            h('p', { class: 'muted' }, 'Al asignar una R3 a una TQT (emparejar, armar o cambiar placa), el servidor envía sola la etiqueta «TQT: 0000 / R3: 0000» a la DYMO compartida (Raspberry). Cada pareja TQT + R3 se imprime una sola vez; si se cambia la R3, sale la etiqueta nueva.'),
            h('label', { class: 'adm-chk', for: 'cableR3Auto' }, chk, 'Imprimir el cable R3 automáticamente'), est);
    }

    function debounce(fn, ms) { var t = 0; return function () { clearTimeout(t); t = setTimeout(fn, ms); }; }
    function recargarTodo() { S.cargado = {}; mostrarSeccion(); }
    function avisoRespaldo(d, base) { msg((base || 'Listo.') + (d && d.respaldo ? ' Respaldo guardado: ' + d.respaldo : ''), false); }

    /* ---------------- movimientos ---------------- */
    var MV_PAGINA = 50, MES_CORTO = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];
    var MV_CAT = { alta: ['Alta', 'ok'], edicion: ['Edición', 'warn'], eliminacion: ['Eliminación', 'bad'], sesion: ['Sesión', ''], excel: ['Excel', 'info'], otro: ['Otro', ''] };
    var MV_ORDEN = ['alta', 'edicion', 'eliminacion', 'sesion', 'excel', 'otro'];
    function dos(n) { return (n < 10 ? '0' : '') + n; }
    function cuando(s) {
        var d = s ? new Date(String(s).replace(' ', 'T')) : null;
        if (!d || isNaN(d)) return { texto: '—', completo: '' };
        var hm = dos(d.getHours()) + ':' + dos(d.getMinutes()), hoy = new Date(); hoy.setHours(0, 0, 0, 0);
        var dia = new Date(d); dia.setHours(0, 0, 0, 0); var dif = Math.round((hoy - dia) / 86400000);
        var completo = d.getDate() + ' ' + MES_CORTO[d.getMonth()] + ' ' + d.getFullYear() + ' ' + hm + ':' + dos(d.getSeconds());
        if (dif === 0) return { texto: 'hoy ' + hm, completo: completo };
        if (dif === 1) return { texto: 'ayer ' + hm, completo: completo };
        return { texto: d.getDate() + ' ' + MES_CORTO[d.getMonth()] + (d.getFullYear() !== hoy.getFullYear() ? ' ' + d.getFullYear() : '') + ' ' + hm, completo: completo };
    }
    function mvBadge(c) { var m = MV_CAT[c] || MV_CAT.otro; return badge(m[0], m[1]); }
    function mvQuery(extra) {
        var p = new URLSearchParams(), q = $('mQ').value.trim();
        if (S.mov.categoria) p.set('categoria', S.mov.categoria);
        if (q) p.set('q', q);
        if ($('mDesde').value) p.set('desde', $('mDesde').value);
        if ($('mHasta').value) p.set('hasta', $('mHasta').value);
        if ($('admLote').value) p.set('lote_id', $('admLote').value);
        Object.keys(extra || {}).forEach(function (k) { p.set(k, String(extra[k])); });
        return p.toString();
    }
    function mvFiltrado() { return !!(S.mov.categoria || $('mQ').value.trim() || $('mDesde').value || $('mHasta').value || ($('admLote').value && $('admLote').value !== '0')); }
    function cargarMov(reset) {
        var M = S.mov, id = ++M.pedido, d1 = $('mDesde').value, d2 = $('mHasta').value;
        if (d1 && d2 && d1 > d2) { M.items = []; M.total = 0; M.error = 'La fecha «Desde» es posterior a «Hasta». Corrígela para ver resultados.'; pintarMov(); return Promise.resolve(); }
        M.error = ''; if (reset) $('mEstado').textContent = 'Cargando movimientos…'; $('mMas').disabled = true;
        return adm('/api/admin/movimientos?' + mvQuery({ limite: MV_PAGINA, desplazamiento: reset ? 0 : M.items.length }), { lote: true }).then(function (r) {
            if (id !== M.pedido || r.status === 401) return;
            if (!r.ok) { M.error = r.status === 0 ? r.error : 'No se pudieron leer los movimientos: ' + r.error; if (reset) { M.items = []; M.total = 0; } pintarMov(); return; }
            var d = r.data || {};
            M.total = d.total || 0; M.conteo = d.conteo || {}; M.categorias = d.categorias || M.categorias;
            M.items = reset ? (d.items || []) : M.items.concat(d.items || []);
            pintarMov();
        });
    }
    function pintarMov() {
        var M = S.mov, cats = $('mCats'); limpiar(cats);
        var orden = MV_ORDEN.filter(function (k) { return k in M.categorias || k in M.conteo; });
        var suma = orden.reduce(function (a, k) { return a + (M.conteo[k] || 0); }, 0);
        var chip = function (clave, texto, n) { return h('button', { class: 'mv-cat', type: 'button', 'aria-pressed': String(M.categoria === clave), onclick: function () { M.categoria = clave; cargarMov(true); } }, texto, ' ', h('b', null, String(n))); };
        cats.appendChild(chip('', 'Todos', suma));
        orden.forEach(function (k) { cats.appendChild(chip(k, M.categorias[k] || (MV_CAT[k] || [k])[0], M.conteo[k] || 0)); });
        var host = $('mLista'); limpiar(host);
        if (M.error) host.appendChild(banner('bad', M.error));
        else if (!M.items.length) host.appendChild(vacio(mvFiltrado() ? 'Todavía no hay movimientos con esos filtros. Prueba con otro tipo, otra fecha o quita los filtros.' : 'Aquí aparecerán las altas, ediciones, eliminaciones, sesiones y exportaciones.'));
        else {
            host.appendChild(tabla(['Cuándo', 'Tipo', 'Movimiento', 'Detalle', 'Operador', 'Lote'], M.items.map(function (m) {
                var c = cuando(m.fecha);
                return h('tr', { dataset: { cat: m.categoria } }, h('td', { class: 'mv-fecha' }, h('time', { datetime: m.fecha || null, title: c.completo }, c.texto)), h('td', null, mvBadge(m.categoria)), h('td', null, m.titulo || m.evento),
                    h('td', { class: 'mv-det' }, m.valor ? h('span', { class: 'mono' }, m.valor) : null, m.detalle ? h('span', { class: 'd' }, m.detalle) : null, !m.valor && !m.detalle ? '—' : null),
                    h('td', null, m.operador || '—'), h('td', { class: 'mono' }, m.lote || '—'));
            }), 'Tabla de movimientos'));
        }
        $('mEstado').textContent = M.error ? '' : M.items.length + ' de ' + M.total + ' movimiento' + (M.total === 1 ? '' : 's');
        var mas = $('mMas'); mas.hidden = M.error !== '' || M.items.length >= M.total; mas.disabled = false; mas.textContent = 'Cargar más (' + Math.min(MV_PAGINA, M.total - M.items.length) + ')';
    }
    function cargarUltimos(host) {
        return adm('/api/admin/movimientos?limite=5', { lote: true }).then(function (r) {
            if (!r.ok) { if (r.status !== 401) host.appendChild(vacio('No se pudieron leer los movimientos.')); return; }
            var its = (r.data && r.data.items) || [];
            if (!its.length) { host.appendChild(vacio('Todavía no hay movimientos.')); return; }
            host.appendChild(h('ul', { class: 'mv-resumen-lista', 'aria-label': 'Últimos cinco movimientos' }, its.map(function (m) {
                return h('li', null, h('span', { class: 'when' }, cuando(m.fecha).texto), mvBadge(m.categoria), h('span', null, m.titulo || m.evento), m.valor ? h('span', { class: 'mono muted' }, m.valor) : null);
            })));
        });
    }
    $('mQ').addEventListener('input', debounce(function () { cargarMov(true); }, 300));
    ['mDesde', 'mHasta'].forEach(function (id) { $(id).addEventListener('change', function () { cargarMov(true); }); });
    $('mMas').addEventListener('click', function () { cargarMov(false); });
    $('mAct').addEventListener('click', function () { cargarMov(true); });
    $('mLimpiar').addEventListener('click', function () { S.mov.categoria = ''; ['mQ', 'mDesde', 'mHasta'].forEach(function (id) { $(id).value = ''; }); cargarMov(true); });
    $('mCsv').addEventListener('click', function () {      // CSV de lo filtrado (hasta 5000); neutraliza fórmulas (=, +, -, @) para Excel
        var b = $('mCsv'), filas = [];
        b.disabled = true;
        (function pagina(off) {
            adm('/api/admin/movimientos?' + mvQuery({ limite: 200, desplazamiento: off }), { lote: true }).then(function (r) {
                if (!r.ok) { b.disabled = false; if (r.status !== 401) msg('No se pudo exportar: ' + r.error, true); return; }
                filas = filas.concat(r.data.items);
                if (filas.length < r.data.total && r.data.items.length && off + 200 < 5000) { pagina(off + 200); return; }
                b.disabled = false;
                var cel = function (v) { var s = v === null || v === undefined ? '' : String(v); if (/^[=+\-@\t\r]/.test(s)) s = "'" + s; return '"' + s.replace(/"/g, '""') + '"'; };
                var lin = [['Fecha', 'Tipo', 'Movimiento', 'Valor', 'Detalle', 'Operador', 'Lote']].concat(filas.map(function (m) { return [m.fecha, (MV_CAT[m.categoria] || MV_CAT.otro)[0], m.titulo, m.valor, m.detalle, m.operador, m.lote]; }));
                var nombre = 'movimientos_' + new Date().toISOString().slice(0, 10) + '.csv';
                descargar(new Blob(['﻿' + lin.map(function (f) { return f.map(cel).join(','); }).join('\r\n')], { type: 'text/csv;charset=utf-8' }), nombre);
                msg('Descargado: ' + nombre + ' (' + filas.length + ' movimientos)', false);
            });
        })(0);
    });

    /* ---------------- módulos: datos por colección (ver y eliminar filas) ---------------- */
    var MO_PAGINA = 50, MO_RUTA = '/api/plataforma/admin/modulos';
    function moModulo() { return S.mo.mods.filter(function (m) { return m.id === S.mo.mod; })[0] || null; }
    function moColeccion() { var m = moModulo(); return m ? (m.colecciones || []).filter(function (c) { return c.id === S.mo.col; })[0] || null : null; }
    function moPath() { return MO_RUTA + '/' + encodeURIComponent(S.mo.mod) + '/colecciones/' + encodeURIComponent(S.mo.col); }
    function cargarModulos() {
        var M = S.mo, id = ++M.pedido;
        $('moEstado').textContent = 'Cargando módulos…';
        return adm(MO_RUTA, { timeout: 15000 }).then(function (r) {
            if (id !== M.pedido || r.status === 401) return;
            if (!r.ok) { M.error = 'No se pudieron leer los módulos: ' + r.error; M.listo = false; S.cargado.modulos = false; pintarMo(); return; }
            M.mods = Array.isArray(r.data) ? r.data : []; M.error = ''; M.listo = true;
            var sel = $('moMod'); limpiar(sel);
            M.mods.forEach(function (m) { sel.appendChild(h('option', { value: m.id }, m.nombre || m.id)); });
            if (!moModulo()) M.mod = M.mods.length ? M.mods[0].id : '';
            sel.value = M.mod;
            elegirModulo(M.mod);
        });
    }
    function elegirModulo(id) {
        var M = S.mo; M.mod = id; M.sel = {}; M.nsel = 0; M.items = []; M.total = 0;
        var m = moModulo(), cols = m ? (m.colecciones || []) : [];
        M.col = cols.length ? cols[0].id : '';
        $('moQ').value = '';
        pintarColecciones(); cargarFilas(true);
    }
    function pintarColecciones() {
        var M = S.mo, box = $('moCols'), m = moModulo(); limpiar(box);
        ((m && m.colecciones) || []).forEach(function (c) {
            box.appendChild(h('button', { class: 'mv-cat', type: 'button', 'aria-pressed': String(c.id === M.col), onclick: function () {
                if (M.col === c.id) return;
                M.col = c.id; M.sel = {}; M.nsel = 0; $('moQ').value = ''; pintarColecciones(); cargarFilas(true);
            } }, c.nombre || c.id, c.solo_lectura ? badge('Solo lectura', '') : null));
        });
        box.hidden = !box.firstChild;
    }
    function cargarFilas(reset) {
        var M = S.mo, id = ++M.pedido, q = $('moQ').value.trim();
        if (!M.mod || !M.col) { M.items = []; M.total = 0; M.cols = []; M.error = ''; pintarMo(); return Promise.resolve(); }
        M.error = ''; if (reset) { $('moEstado').textContent = 'Cargando datos…'; }
        $('moMas').disabled = true;
        var p = new URLSearchParams({ limit: MO_PAGINA, offset: reset ? 0 : M.items.length }); if (q) p.set('q', q);
        return adm(moPath() + '?' + p.toString(), { timeout: 20000 }).then(function (r) {
            if (id !== M.pedido || r.status === 401) return;
            if (!r.ok) { M.error = r.status === 0 ? r.error : 'No se pudieron leer los datos: ' + r.error; if (reset) { M.items = []; M.total = 0; } pintarMo(); return; }
            var d = r.data || {};
            M.cols = Array.isArray(d.columnas) ? d.columnas : M.cols;
            M.total = d.total || 0;
            M.items = reset ? (d.items || []) : M.items.concat(d.items || []);
            if (reset) { M.sel = {}; M.nsel = 0; }
            pintarMo();
        });
    }
    function moSoloLectura() { var c = moColeccion(); return !c || !!c.solo_lectura; }
    function moActualizarSel() {
        var M = S.mo, bar = $('moSel'), ro = moSoloLectura();
        bar.hidden = ro || M.nsel === 0;
        $('moSelN').textContent = M.nsel + ' seleccionada' + (M.nsel === 1 ? '' : 's');
        var todas = $('moTodas'); if (todas) { var vis = M.items.length; todas.checked = vis > 0 && M.nsel >= vis && M.items.every(function (x) { return M.sel[x.id]; }); todas.indeterminate = M.nsel > 0 && !todas.checked; }
    }
    function pintarMo() {
        var M = S.mo, host = $('moLista'), ro = moSoloLectura(), q = $('moQ').value.trim(); limpiar(host);
        var m = moModulo();
        if (M.error) host.appendChild(banner('bad', M.error));
        else if (!M.mods.length) host.appendChild(vacio('No hay módulos con datos administrables.'));
        else if (!m || !(m.colecciones || []).length) host.appendChild(vacio('Este módulo no tiene colecciones de datos para administrar.'));
        else if (!M.items.length) host.appendChild(vacio(q ? 'No hay resultados para esa búsqueda. Prueba con otro texto o bórralo.' : 'Esta colección todavía no tiene datos.'));
        else {
            var cols = M.cols.length ? M.cols : Object.keys(M.items[0]).filter(function (k) { return k !== 'id'; }).map(function (k) { return { k: k, label: bonito(k) }; });
            var todas = ro ? null : h('input', { type: 'checkbox', id: 'moTodas', 'aria-label': 'Seleccionar todas las filas cargadas', onchange: function () {
                M.items.forEach(function (x) { if (todas.checked) M.sel[x.id] = true; else delete M.sel[x.id]; });
                M.nsel = todas.checked ? M.items.length : 0;
                Array.prototype.forEach.call(host.querySelectorAll('tbody tr'), function (tr) { tr.dataset.sel = todas.checked ? '1' : ''; var c = tr.querySelector('input'); if (c) c.checked = todas.checked; });
                moActualizarSel();
            } });
            var filas = M.items.map(function (x) {
                var tr = h('tr', { dataset: { sel: M.sel[x.id] ? '1' : '' } });
                if (!ro) tr.appendChild(h('td', { class: 'col-check' }, h('input', { type: 'checkbox', checked: M.sel[x.id] ? true : null, 'aria-label': 'Seleccionar fila ' + x.id, onchange: function (ev) {
                    if (ev.target.checked) { if (!M.sel[x.id]) M.nsel++; M.sel[x.id] = true; } else if (M.sel[x.id]) { M.nsel--; delete M.sel[x.id]; }
                    tr.dataset.sel = ev.target.checked ? '1' : ''; moActualizarSel();
                } })));
                cols.forEach(function (c) { var v = x[c.k]; tr.appendChild(h('td', { class: c.mono ? 'mono' : null }, v === null || v === undefined || v === '' ? '—' : String(v))); });
                return tr;
            });
            var t = tabla([], filas, 'Tabla de ' + ((moColeccion() || {}).nombre || 'datos')), trh = t.querySelector('thead tr');
            if (!ro) trh.appendChild(h('th', { class: 'col-check' }, todas));
            cols.forEach(function (c) { trh.appendChild(h('th', null, c.label || bonito(c.k))); });
            host.appendChild(t);
        }
        $('moEstado').textContent = M.error || !M.items.length ? '' : M.items.length + ' de ' + M.total + ' fila' + (M.total === 1 ? '' : 's') + (ro ? ' · solo lectura' : '');
        var mas = $('moMas'); mas.hidden = M.error !== '' || M.items.length >= M.total; mas.disabled = false; mas.textContent = 'Cargar más (' + Math.min(MO_PAGINA, M.total - M.items.length) + ')';
        moActualizarSel();
    }
    function eliminarSeleccion() {
        var M = S.mo, ids = Object.keys(M.sel).map(Number).filter(function (n) { return isFinite(n); }), c = moColeccion(), m = moModulo();
        if (!ids.length || !c || c.solo_lectura) return;
        dialogo({ titulo: 'Eliminar ' + ids.length + ' fila' + (ids.length === 1 ? '' : 's'), peligro: true, boton: 'Eliminar ' + ids.length,
            cuerpo: [h('p', null, 'Se eliminarán ' + ids.length + ' fila' + (ids.length === 1 ? '' : 's') + ' de «' + (c.nombre || c.id) + '» (' + (m.nombre || m.id) + '). No se puede deshacer desde la app.'),
                banner('warn', 'Antes de borrar se crea un respaldo automático de la base de datos.')],
            confirmar: function () {
                return adm(moPath(), { method: 'DELETE', body: { ids: ids }, timeout: 120000 }).then(function (r) {
                    if (!r.ok) return r.error || 'No se pudo eliminar.';
                    var n = (r.data && r.data.eliminados) || 0;
                    avisoRespaldo(r.data, n + ' fila' + (n === 1 ? '' : 's') + ' eliminada' + (n === 1 ? '.' : 's.'));
                    cargarFilas(true); return true;
                });
            } });
    }
    $('moMod').addEventListener('change', function () { elegirModulo($('moMod').value); });
    $('moQ').addEventListener('input', debounce(function () { S.mo.sel = {}; S.mo.nsel = 0; cargarFilas(true); }, 300));
    $('moMas').addEventListener('click', function () { cargarFilas(false); });
    $('moAct').addEventListener('click', function () { if (S.mo.listo) cargarFilas(true); else cargarModulos(); });
    $('moNinguna').addEventListener('click', function () { S.mo.sel = {}; S.mo.nsel = 0; pintarMo(); });
    $('moEliminar').addEventListener('click', eliminarSeleccion);

    /* ---------------- borrado con palabra ---------------- */
    function conteoLote(id) {
        var d = S.resumen || {}, l = (Array.isArray(d.lotes) ? d.lotes : []).filter(function (x) { return String(x.id) === String(id); })[0];
        return l ? Object.keys(l).filter(function (k) { return typeof l[k] === 'number' && ['id', 'mes', 'anio', 'activo'].indexOf(k) < 0; }).map(function (k) { return [k, l[k]]; }) : [];
    }
    function confirmarPalabra(o) {
        var inp = h('input', { class: 'input mono', id: 'palabra', autocomplete: 'off', autocapitalize: 'characters', spellcheck: 'false', placeholder: o.palabra, 'aria-describedby': 'palHint' });
        var dlg = dialogo({ titulo: o.titulo, peligro: true, boton: o.boton, habilitado: function () { return inp.value.trim() === o.palabra; },
            cuerpo: [h('p', null, o.texto),
                o.resumen.length ? h('div', { class: 'kpis' }, o.resumen.map(function (x) { return h('div', { class: 'kpi', dataset: { k: 'bad' } }, h('span', { class: 'lbl' }, bonito(x[0])), h('span', { class: 'v' }, String(x[1]))); })) : null,
                banner('warn', 'Antes de borrar se crea un respaldo automático de la base de datos.'),
                h('div', { class: 'field' }, h('label', { for: 'palabra' }, 'Escribe ' + o.palabra + ' para confirmar'), inp, h('div', { class: 'hint', id: 'palHint' }, 'Mayúsculas, exactamente como se muestra.'))],
            confirmar: function () {
                return adm(o.ruta, { method: 'POST', body: o.cuerpo, timeout: 120000 }).then(function (r) {
                    if (!r.ok) return r.error || 'No se pudo completar.';
                    var d = r.data || {}; avisoRespaldo({ respaldo: d.respaldo || d.backup || d.archivo_respaldo || d.respaldo_nombre }, d.mensaje || 'Datos borrados.'); recargarTodo(); return true;
                });
            } });
        inp.addEventListener('input', function () { dlg.ok.disabled = inp.value.trim() !== o.palabra; });
    }
    $('btnVaciar').addEventListener('click', function () {
        var id = $('vLote').value, l = S.lotes.filter(function (x) { return String(x.id) === id; })[0]; if (!l) return;
        var res = conteoLote(id); if (!res.length && l.registradas != null) res.push(['tarjetas', l.registradas]);
        confirmarPalabra({ titulo: 'Vaciar ' + nombreLote(l), texto: 'Se borrarán las tarjetas de este lote. Sus PCB vuelven al inventario como sueltas.', palabra: 'VACIAR', resumen: res, boton: 'Vaciar lote', ruta: '/api/admin/lote/' + l.id + '/vaciar', cuerpo: { confirmar: 'VACIAR' } });
    });
    $('btnReset').addEventListener('click', function () {
        var run = function () {
            var d = (S.resumen || {}).totales || {}, res = Object.keys(d).filter(function (k) { return typeof d[k] === 'number' && k !== 'bitacora'; }).map(function (k) { return [k, d[k]]; });
            confirmarPalabra({ titulo: 'Borrar TODO', texto: 'Se borran todas las tarjetas y PCB. Se conservan los lotes, la contraseña y los movimientos. Esta acción no se puede deshacer desde la app.', palabra: 'BORRAR TODO', resumen: res, boton: 'Borrar todo', ruta: '/api/admin/reset', cuerpo: { confirmar: 'BORRAR TODO' } });
        };
        if (S.resumen) run(); else adm('/api/admin/resumen', { lote: true }).then(function (r) { if (r.ok) S.resumen = r.data; run(); });
    });
    // el resumen alimenta los conteos del borrado: se carga al entrar en la sección
    var mostrarBase = mostrarSeccion;
    mostrarSeccion = function () { mostrarBase(); if (S.sec === 'borrado' && !S.resumen) adm('/api/admin/resumen', { lote: true }).then(function (r) { if (r.ok) S.resumen = r.data; }); };

    /* ---------------- exportar Excel y correo ---------------- */
    function loteExport() {
        var id = $('admLote').value, l = S.lotes.filter(function (x) { return String(x.id) === String(id); })[0];
        return l || S.lotes.filter(function (x) { return x.activo; })[0] || S.lotes[0] || null;
    }
    $('admExcel').addEventListener('click', function () {
        var l = loteExport(), b = $('admExcel'); b.disabled = true;
        adm('/api/admin/export/excel' + (l ? '?lote_id=' + l.id : ''), { raw: true, timeout: 120000, lote: true }).then(function (r) {
            b.disabled = false;
            if (!r.ok) { if (r.status !== 401) msg('No se pudo exportar. ' + (r.status === 423 ? 'El Excel está abierto; ciérralo y reintenta.' : r.error), true); return; }
            r.res.blob().then(function (blob) { var n = nombreArchivo(r.res, 'Control_Produccion_TQT.xlsx'); descargar(blob, n); msg('Descargado: ' + n, false); });
        });
    });
    $('admExcelMail').addEventListener('click', function () {
        var l = loteExport(), b = $('admExcelMail'); b.disabled = true;
        fetch('/api/correo/destinatarios', { credentials: 'same-origin', cache: 'no-store' }).then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); }).then(null, function () { return { ok: false, d: null }; }).then(function (r) {
            b.disabled = false;
            if (!r.ok) { msg('No se pudieron leer los destinatarios.', true); return; }
            var d = r.d, marcas = (d.items || []).map(function (u) { return { cb: h('input', { type: 'checkbox', value: u.email }), email: u.email }; });
            var otros = h('input', { class: 'input', type: 'text', inputmode: 'email', autocapitalize: 'none', spellcheck: 'false', placeholder: 'otra@empresa.com, otro@correo.com', 'aria-label': 'Correos sin cuenta' });
            var txt = h('textarea', { class: 'input', rows: '2', maxlength: '1000', placeholder: 'Mensaje (opcional)', 'aria-label': 'Mensaje opcional' });
            dialogo({ titulo: 'Enviar por correo', boton: 'Enviar',
                cuerpo: [h('p', { class: 'muted' }, 'Se adjunta: Control de producción · ' + (l ? nombreLote(l) : 'lote activo') + '. Cada destinatario recibe su propio correo.'),
                    d.smtp ? null : banner('warn', 'El correo SMTP no está configurado en el servidor: no se podrá enviar.'),
                    h('div', { class: 'adm-correos' }, marcas.length ? marcas.map(function (m) { return h('label', { class: 'adm-chk' }, m.cb, h('span', { class: 'mono' }, m.email)); }) : h('span', { class: 'muted' }, 'No hay cuentas a las que enviar.')),
                    h('div', { class: 'field' }, h('label', null, 'Correos sin cuenta'), otros), h('div', { class: 'field' }, h('label', null, 'Mensaje'), txt)],
                confirmar: function () {
                    var extra = otros.value.split(/[\s,;]+/).map(function (x) { return x.trim(); }).filter(Boolean);
                    var para = marcas.filter(function (m) { return m.cb.checked; }).map(function (m) { return m.email; }).concat(extra).filter(function (x, i, a) { return a.indexOf(x) === i; });
                    if (!para.length) return 'Elige al menos una cuenta o escribe un correo.';
                    if (d.max && para.length > d.max) return 'Máximo ' + d.max + ' destinatarios por envío.';
                    var malo = extra.filter(function (x) { return !/^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/.test(x); })[0];
                    if (malo) return 'Correo no válido: ' + malo;
                    return adm('/api/correo/excel', { method: 'POST', timeout: 60000, body: { tipo: 'lote', lote_id: l ? l.id : null, fecha: null, desde: null, hasta: null, mensaje: txt.value || null, para: para } }).then(function (x) {
                        if (!x.ok) return x.status === 401 ? 'Para enviar el Excel del lote hace falta la contraseña de administración.' : (x.error || 'No se pudo enviar.');
                        var f = (x.data && x.data.fallos) || [];
                        msg((x.data.archivo || 'Excel') + ' enviado a ' + (x.data.enviados || []).length + ' destinatario' + ((x.data.enviados || []).length === 1 ? '' : 's') + (f.length ? ' · ' + f.length + ' falló' : ''), false);
                        return true;
                    });
                } });
        });
    });

    /* ---------------- cambiar contraseña de administración ---------------- */
    $('formClave').addEventListener('submit', function (ev) {
        ev.preventDefault();
        var err = $('cErr'), a = $('cActual').value, n = $('cNueva').value, rep = $('cRep').value;
        err.textContent = ''; err.dataset.k = 'bad';
        if (!a) { err.textContent = 'Escribe la contraseña actual.'; return; }
        if (n.length < 8) { err.textContent = 'La contraseña nueva debe tener al menos 8 caracteres.'; return; }
        if (n !== rep) { err.textContent = 'La confirmación no coincide.'; return; }
        if (n === a) { err.textContent = 'La nueva debe ser distinta de la actual.'; return; }
        var b = $('btnClave'); b.disabled = true;
        adm('/api/admin/cambiar-clave', { method: 'POST', body: { actual: a, nueva: n }, noAuthRedirect: true }).then(function (r) {
            b.disabled = false;
            if (r.status === 401 && !/actual no es correcta/i.test(r.error || '')) { bloquear('La sesión de administración ya no es válida. Escribe la contraseña de nuevo.'); return; }
            if (!r.ok) { err.textContent = r.error || 'No se pudo cambiar la contraseña.'; return; }
            if (r.data && r.data.token) { S.token = r.data.token; S.exp = expDeToken(r.data.token) || Date.now() + SESION_MS; guardar(); }   // el servidor invalida los anteriores
            ['cActual', 'cNueva', 'cRep'].forEach(function (id) { $(id).value = ''; });
            err.dataset.k = 'ok'; err.textContent = 'Contraseña actualizada.'; msg('Contraseña de administración actualizada', false);
        });
    });

    irSeccion('cuentas');
    /* Enlaces antiguos /admin (redirigen a /inicio?centro=1[&next=/monitor]#seccion): abren el Centro en esa sección y,
       tras desbloquear, vuelven al monitor si venían de allí. */
    var NEXT_OK = ['/monitor', '/monitor#/excel?descargar=1'], destinoNext = null, pidioCentro = false;
    try {
        var qs = new URLSearchParams(location.search);
        pidioCentro = qs.has('centro');
        if (NEXT_OK.indexOf(qs.get('next')) >= 0) destinoNext = qs.get('next');
    } catch (e) { /* nada */ }
    var abrirBase = abrirCuerpo;
    abrirCuerpo = function () { if (destinoNext) { location.replace(destinoNext); return; } abrirBase(); };
    if (pidioCentro) {
        var hash = String(location.hash || '').replace('#', ''), sec = SECCIONES.indexOf(hash) >= 0 ? hash : (destinoNext ? 'resumen' : 'resumen'), nuc = $('nucBtn'), hecho = false;
        var nucleo = document.querySelector('.nucleo');
        var abrir = function () {
            if (hecho || nuc.hidden) return; hecho = true; obs.disconnect(); clearTimeout(plazo);
            nuc.click(); irSeccion(sec);
            try { history.replaceState(null, '', location.pathname); } catch (e) { /* nada */ }
        };
        // espera a que el portal sepa si la sesión es de administrador (lo marca el núcleo con data-admin); si no llega, muestra el acceso
        var obs = new MutationObserver(function () { if (nucleo && nucleo.hasAttribute('data-admin')) abrir(); });
        var plazo = setTimeout(abrir, 4000);
        if (nucleo) obs.observe(nucleo, { attributes: true, attributeFilter: ['data-admin'] });
        if (nucleo && nucleo.hasAttribute('data-admin')) abrir();
    }
    window.CentroAdmin = { irSeccion: irSeccion };
})();
