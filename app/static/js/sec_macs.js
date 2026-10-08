/**
 * sec_macs.js - Sección "MAC y firmware" (#/macs) de la consola de escritorio.
 * Captura con teclado de la MAC (y firmware) de las R1/R2: tabla de pendientes, pegado masivo y corrección de las que ya tienen MAC.
 * Las R3 (sin MAC) también aparecen en Pendientes / Con MAC: quedan programadas al guardar su firmware (v1.3.45).
 * Se registra con window.TQTEscritorio.registrar({...}) (contrato en docs/ESCRITORIO.md). Sin cámara, sin dependencias externas.
 */
(function () {
    'use strict';

    const MAC_RE = /(^|[^0-9A-Fa-f])((?:[0-9A-Fa-f]{2}[:\-.]?){5}[0-9A-Fa-f]{2})(?![0-9A-Fa-f])/;
    const MAC_ESPACIOS_RE = /(^|[^0-9A-Za-z])((?:[0-9A-Fa-f]{2}[ \t]+){5}[0-9A-Fa-f]{2})(?![0-9A-Za-z])/;
    const NOMBRE_RE = /TQT[\s_-]*R([123])[\s_-]*V([0-9]{1,3}(?:[._][0-9](?=[\s_-]))?)(?:[\s_-]+[A-Za-z][A-Za-z0-9]*)*[\s_-]+([0-9]{1,4})(?![0-9])/i;
    const execNombre = (s) => { const m = NOMBRE_RE.exec(s); if (m) m[2] = m[2].replace(/\D/g, ''); return m; };   // V2_0 → 20
    const OTRA = '__otra';
    const MAX_LOTE = 500;

    function montar(host, ctx) {
        const T = ctx.T || window.TQT;
        const h = ctx.h || T.h;
        const api = ctx.api || T.api;
        const icon = ctx.icon || T.icon;
        const toast = ctx.toast || T.toast;

        // ------------------------------------------------------------ estado
        const S = {
            tab: 'pend', fw: { R1: [], R2: [], R3: [] }, macBD: new Map(), vivo: true,
            sonido: T.store.get('tqt.macs.sonido', '0') === '1',
            hoy: { n: 0 },
        };
        const timers = new Set();
        const unsubs = [];

        // "Guardadas hoy": lo cuenta el servidor (todos los operarios y equipos), no este navegador
        let hoyTimer = null;
        async function cargarHoy() {
            const r = await api('/api/programacion/hoy');
            if (r.ok && r.data && S.vivo) { S.hoy.n = r.data.guardadas || 0; contHoy.textContent = String(S.hoy.n); }
        }
        function sumarHoy() { clearTimeout(hoyTimer); hoyTimer = setTimeout(cargarHoy, 300); timers.add(hoyTimer); }
        const ultimoFw = (tipo) => T.store.get('tqt.macs.fw.' + tipo, '') || '';
        const recordarFw = (tipo, v) => { if (v) T.store.set('tqt.macs.fw.' + tipo, v); };
        const tarjetaTxt = (p) => (p.id_tarjeta_num ? '#' + String(p.id_tarjeta_num).padStart(4, '0') : 'Suelta');

        // ------------------------------------------------------------ sonido opcional (apagado por defecto)
        let actx = null;
        function pitar(ok) {
            if (!S.sonido) return;
            try {
                const AC = window.AudioContext || window.webkitAudioContext; if (!AC) return;
                actx = actx || new AC();
                const seq = ok ? [[880, 0, 0.07]] : [[220, 0, 0.12], [180, 0.14, 0.14]];
                seq.forEach(([f, t0, d]) => {
                    const o = actx.createOscillator(), g = actx.createGain();
                    o.frequency.value = f; g.gain.value = 0.05; o.connect(g); g.connect(actx.destination);
                    o.start(actx.currentTime + t0); o.stop(actx.currentTime + t0 + d);
                });
            } catch (e) { /* sin audio */ }
        }

        const vivo = h('div', { class: 'sr-only', 'aria-live': 'polite', 'aria-atomic': 'true' });
        const anunciar = (t) => { vivo.textContent = ''; setTimeout(() => { vivo.textContent = t; }, 30); };

        // ------------------------------------------------------------ MAC: máscara y validación
        /** Texto libre -> 'XX:XX:...' (completa si trae una MAC entera en cualquier formato, si no parcial con los dígitos hex). */
        function normalizar(raw) {
            const full = T.parseMac(raw);
            if (full) return full;
            const hex = String(raw || '').replace(/MAC/gi, '').replace(/[^0-9A-Fa-f]/g, '').toUpperCase().slice(0, 12);
            return (hex.match(/.{1,2}/g) || []).join(':');
        }
        const hexDe = (s) => String(s || '').replace(/[^0-9A-Fa-f]/g, '');
        function extraerMac(txt) {
            let m = MAC_RE.exec(txt);
            if (!m) m = MAC_ESPACIOS_RE.exec(txt);
            if (!m) return null;
            const hex = hexDe(m[2]).toUpperCase();
            if (/^0{12}$/.test(hex) || /^F{12}$/.test(hex)) return { mac: null, texto: hex, span: m[2], relleno: true };
            return { mac: hex.match(/.{2}/g).join(':'), texto: m[2], span: m[2] };
        }
        function errorFormato(mac) {
            const hex = hexDe(mac);
            if (/^0+$/.test(hex) || /^[Ff]+$/.test(hex)) return 'MAC de relleno (solo ceros o solo F): no es una MAC real.';
            if (parseInt(hex.slice(0, 2), 16) & 1) return 'El primer octeto es impar (multicast): revisa que la MAC esté completa.';
            return '';
        }

        // ------------------------------------------------------------ piezas
        const ICONO_ESTADO = { incompleta: 'clock', valida: 'check', repetida: 'alert', error: 'alert', guardada: 'check', guardando: 'refresh', revisando: 'refresh', obsoleta: 'alert' };
        function celdaEstado(r) {
            r.st = h('div', { class: 'macs-st', id: 'st' + r.uid, dataset: { e: 'vacia' } });
            return r.st;
        }
        function setEstado(r, e, msg) {
            r.estado = e; r.msg = msg || '';
            r.tr.dataset.e = e; r.inp.dataset.e = e;
            if (e === 'error' || e === 'repetida') r.inp.setAttribute('aria-invalid', 'true'); else r.inp.removeAttribute('aria-invalid');
            r.st.dataset.e = e; r.st.title = r.msg;
            r.st.replaceChildren();
            if (r.msg) { if (ICONO_ESTADO[e]) r.st.appendChild(icon(ICONO_ESTADO[e])); r.st.appendChild(h('span', null, r.msg)); }
        }

        function fwWidget(rol, valor, nombre, onChange) {
            const cat = S.fw[rol] || [];
            const sel = h('select', { 'aria-label': `Firmware de ${nombre}` });
            sel.appendChild(h('option', { value: '' }, 'Elegir…'));
            cat.forEach((v) => sel.appendChild(h('option', { value: v }, v)));
            sel.appendChild(h('option', { value: OTRA }, 'Otra versión…'));
            const otro = h('input', { type: 'text', maxlength: 40, placeholder: 'Ej. 4.1', 'aria-label': `Otra versión de firmware de ${nombre}`, hidden: true, autocomplete: 'off', spellcheck: 'false' });
            const w = {
                el: h('div', { class: 'macs-fw' }, sel, otro), sel, otro,
                get() { return sel.value === OTRA ? otro.value.trim() : sel.value; },
                set(v) {
                    v = v || '';
                    if (!v) { sel.value = ''; otro.hidden = true; return; }
                    if (cat.includes(v)) { sel.value = v; otro.hidden = true; return; }
                    sel.value = OTRA; otro.hidden = false; otro.value = v;
                },
            };
            sel.addEventListener('change', () => {
                if (sel.value === OTRA) { otro.hidden = false; otro.focus(); } else { otro.hidden = true; }
                onChange(w.get());
            });
            otro.addEventListener('change', () => onChange(w.get()));
            w.set(valor);
            return w;
        }

        // ------------------------------------------------------------ vistas de tabla (pendientes / con MAC)
        let uidSeq = 0;
        function crearVista(modo) {
            const V = {
                modo, rows: new Map(), cargado: false, error: '', filtro: { tipo: '', q: '', tj: '', orden: 'serie' }, visibles: [],
                tbody: h('tbody'), aviso: h('div'), cont: null, tbl: null,
            };

            // ---- validación de una fila
            V.duenoPantalla = (r) => {
                for (const o of V.rows.values()) if (o !== r && o.mac === r.mac && o.mac.length === 17) return o;
                return null;
            };
            V.revalidar = (r) => {
                if (r.busy || r.saved || r.esR3) return;
                const m = r.mac;
                if (r.obsoleta) return setEstado(r, 'obsoleta', r.obsoleta);
                if (r.srv) return setEstado(r, 'error', r.srv);
                if (!m) return setEstado(r, modo === 'mac' ? 'incompleta' : 'vacia', modo === 'mac' ? 'Vacío: usa «Borrar MAC» para quitarla, o Esc para volver.' : '');
                if (modo === 'mac' && m === r.orig) return setEstado(r, 'vacia', '');
                const hex = hexDe(m);
                if (hex.length < 12) return setEstado(r, 'incompleta', `Faltan ${12 - hex.length} ${12 - hex.length === 1 ? 'dígito' : 'dígitos'}`);
                const ef = errorFormato(m);
                if (ef) return setEstado(r, 'error', ef);
                const otro = V.duenoPantalla(r);
                if (otro) return setEstado(r, 'repetida', `Repetida en esta pantalla: la misma MAC está en ${otro.pcb.nombre}.`);
                const bd = S.macBD.get(m);
                if (bd && bd.id !== r.id) return setEstado(r, 'repetida', `Ya está registrada en ${bd.nombre}.`);
                if (bd === undefined) V.chequearBD(r);
                setEstado(r, 'valida', modo === 'mac' ? 'Enter guarda el cambio' : 'Lista · Enter guarda');
            };
            V.chequearBD = (r) => {
                clearTimeout(r.tBD);
                r.tBD = setTimeout(async () => {
                    timers.delete(r.tBD);
                    const m = r.mac;
                    if (m.length !== 17 || S.macBD.has(m) || !S.vivo) return;
                    const res = await api('/api/pcb?limit=5&q=' + encodeURIComponent(m));
                    if (!res.ok || !S.vivo) return;
                    const it = ((res.data && res.data.items) || []).find((p) => p.mac === m);
                    S.macBD.set(m, it ? { id: it.id, nombre: it.nombre } : null);
                    if (r.mac === m) V.revalidar(r);
                }, 300);
                timers.add(r.tBD);
            };
            V.revalidarCompletas = () => { V.rows.forEach((o) => { if (o.mac.length === 17) V.revalidar(o); }); };

            // ---- navegación por teclado
            V.mover = (r, dir) => {
                const l = V.visibles.filter((x) => !x.saved || x === r);
                const i = l.indexOf(r);
                const n = l[i + dir];
                if (n) { n.inp.focus(); if (n.inp.select) n.inp.select(); n.tr.scrollIntoView({ block: 'nearest' }); return true; }
                return false;
            };

            // ---- guardar
            V.guardar = async (r) => {
                if (r.busy) return;
                if (r.estado !== 'valida' && r.estado !== 'error') return;
                if (!r.mac || r.mac.length !== 17) return;
                const mac = r.mac, fw = r.fw.get();
                r.busy = true; setEstado(r, 'guardando', 'Guardando…');
                const res = await api(`/api/pcb/${r.id}/programacion`, { method: 'PUT', body: { mac, firmware: fw || null } });
                r.busy = false;
                if (!S.vivo) return;
                if (res.ok) {
                    r.srv = null; r.pcb = Object.assign({}, r.pcb, res.data || {});
                    S.macBD.set(mac, { id: r.id, nombre: r.pcb.nombre });
                    recordarFw(r.pcb.tipo, fw);
                    if (fw && !(S.fw[r.pcb.tipo] || []).includes(fw)) cargarFw();
                    pitar(true);
                    if (modo === 'pend') {
                        r.saved = true; r.inp.readOnly = true; sumarHoy();
                        setEstado(r, 'guardada', `Guardada${fw ? ' · firmware ' + fw : ' · sin firmware'}`);
                    } else {
                        r.orig = mac;
                        setEstado(r, 'guardada', 'MAC guardada');
                    }
                    anunciar(`${r.pcb.nombre}: MAC ${mac} guardada`);
                    refrescarContadores();
                } else {
                    r.srv = res.network ? 'Sin conexión con el servidor: no se guardó. Pulsa Enter para reintentar.' : res.error;
                    setEstado(r, 'error', r.srv);
                    pitar(false); anunciar(`${r.pcb.nombre}: ${r.srv}`);
                    refrescarContadores();
                }
            };

            // ---- crear fila
            V.crearFila = (pcb) => {
                const r = { uid: ++uidSeq, id: pcb.id, pcb, v: V, mac: '', orig: pcb.mac || '', estado: 'vacia', msg: '', saved: false, busy: false, srv: null, obsoleta: '' };
                r.tr = h('tr', { dataset: { id: pcb.id, e: 'vacia' } });
                if (pcb.tipo === 'R3') return V.crearFilaR3(r, pcb);
                r.inp = h('input', {
                    class: 'macs-in', type: 'text', autocomplete: 'off', spellcheck: 'false', placeholder: '12 dígitos',
                    'aria-label': `MAC de ${pcb.nombre}`, 'aria-describedby': 'st' + r.uid, dataset: { e: 'vacia' },
                });
                r.inp.addEventListener('focus', () => { S.ultFila = r; });   // escáner remoto: una MAC leída va a la última fila tocada
                r.fw = fwWidget(pcb.tipo, pcb.firmware || (modo === 'pend' ? ultimoFw(pcb.tipo) : ''), pcb.nombre, (val) => {
                    if (modo === 'pend') { recordarFw(pcb.tipo, val); return; }
                    guardarFw(r, val);
                });
                r.cTj = h('td', { class: 'c-tj mono' + (pcb.id_tarjeta_num ? '' : ' dim') }, tarjetaTxt(pcb));
                r.st = celdaEstado(r);
                const acc = h('td', { class: 'c-acc' });
                r.acc = acc;
                if (modo === 'mac') acc.appendChild(botonBorrar(r));
                r.tr.append(
                    h('td', { class: 'c-placa' }, h('div', { class: 'macs-placa' }, T.tipoChip(pcb.tipo), h('span', { class: 'nm' }, pcb.nombre))),
                    r.cTj,
                    h('td', { class: 'c-hw mono' }, 'V' + pcb.version),
                    h('td', { class: 'c-fw' }, r.fw.el),
                    h('td', { class: 'c-mac' }, r.inp),
                    h('td', { class: 'c-est' }, r.st),
                );
                r.tr.appendChild(acc);
                if (modo === 'mac') { r.inp.value = r.orig; r.mac = r.orig; }

                r.inp.addEventListener('input', (ev) => {
                    const antes = r.mac;
                    const pos = r.inp.selectionStart;
                    const digitos = hexDe(r.inp.value.slice(0, pos)).length;
                    const f = normalizar(r.inp.value);
                    if (f !== r.inp.value) {
                        r.inp.value = f;
                        if (!(ev.inputType || '').includes('paste') && pos < r.inp.value.length) {   // conserva el cursor si se edita a mitad
                            let cuenta = 0, i = 0;
                            while (i < f.length && cuenta < digitos) { if (/[0-9A-F]/.test(f[i])) cuenta++; i++; }
                            r.inp.setSelectionRange(i, i);
                        }
                    }
                    r.mac = f; r.srv = null;
                    V.revalidar(r);
                    if (antes.length === 17 || f.length === 17) V.revalidarCompletas();
                    refrescarContadores();
                });
                r.inp.addEventListener('keydown', (ev) => {
                    if (ev.isComposing) return;
                    if (ev.key === 'Enter') {
                        ev.preventDefault();
                        if (modo === 'pend' && (r.saved || !r.mac)) { V.mover(r, 1); return; }
                        if (r.estado === 'valida') { V.guardar(r); if (modo === 'pend') V.mover(r, 1); else V.mover(r, 1); }
                        else if (r.estado === 'error' && r.srv) { V.guardar(r); }
                        else if (r.msg) anunciar(`${pcb.nombre}: ${r.msg}`);
                        else if (modo === 'mac') V.mover(r, 1);
                    } else if (ev.key === 'ArrowDown' || ev.key === 'ArrowUp') {
                        ev.preventDefault(); V.mover(r, ev.key === 'ArrowDown' ? 1 : -1);
                    } else if (ev.key === 'Escape') {
                        if (modo === 'pend' && !r.saved && r.inp.value) {
                            ev.preventDefault(); ev.stopPropagation();
                            r.inp.value = ''; r.mac = ''; r.srv = null; V.revalidar(r); V.revalidarCompletas(); refrescarContadores();
                        } else if (modo === 'mac' && r.mac !== r.orig) {
                            ev.preventDefault(); ev.stopPropagation();
                            r.inp.value = r.orig; r.mac = r.orig; r.srv = null; V.revalidar(r); V.revalidarCompletas();
                        }
                    }
                });
                if (modo === 'mac') setEstado(r, 'vacia', '');
                return r;
            };

            // ---- fila R3 (v1.3.45): no lleva MAC; queda programada al guardar su firmware (se guarda al elegirlo)
            V.crearFilaR3 = (r, pcb) => {
                r.esR3 = true;
                const quitar = h('button', { class: 'btn btn-sm btn-ghost', type: 'button', title: 'Quitar el firmware: la R3 vuelve a «Sin firmware»', hidden: !pcb.firmware,
                    onclick: () => guardarR3(null) }, icon('x'), 'Quitar firmware');
                const guardarR3 = async (val) => {
                    if (r.busy || (val || null) === (r.pcb.firmware || null)) return;
                    r.busy = true; setEstado(r, 'guardando', val ? 'Guardando firmware…' : 'Quitando firmware…');
                    const res = await api(`/api/pcb/${r.id}/firmware`, { method: 'PUT', body: { firmware: val } });
                    r.busy = false;
                    if (!S.vivo) return;
                    if (res.ok) {
                        r.pcb = Object.assign({}, r.pcb, res.data || {}, { firmware: val });
                        quitar.hidden = !val;
                        if (!val) {
                            r.fw.set(''); r.saved = false;
                            setEstado(r, 'vacia', 'Firmware quitado: vuelve a «Sin firmware»');
                            pitar(true); anunciar(`${pcb.nombre}: firmware quitado`); refrescarContadores(); recargarSuave();
                            return;
                        }
                        recordarFw('R3', val);
                        if (!(S.fw.R3 || []).includes(val)) cargarFw();
                        if (modo === 'pend') { r.saved = true; sumarHoy(); }
                        setEstado(r, 'guardada', `Programada · firmware ${val}`);
                        pitar(true); anunciar(`${pcb.nombre}: firmware ${val}, programada`);
                    } else {
                        setEstado(r, 'error', res.network ? 'Sin conexión con el servidor: el firmware no se guardó.' : res.error);
                        pitar(false); anunciar(`${pcb.nombre}: ${r.msg}`);
                    }
                    refrescarContadores();
                };
                r.fw = fwWidget('R3', pcb.firmware, pcb.nombre, (val) => { if (val) guardarR3(val); });
                r.inp = r.fw.sel;   // el foco de la fila es su selector de firmware
                r.inp.addEventListener('focus', () => { S.ultFila = r; });
                r.inp.addEventListener('keydown', (ev) => {   // ↑/↓/Enter navegan entre filas (no cambian el firmware)
                    if (ev.key === 'ArrowDown' || ev.key === 'ArrowUp') { ev.preventDefault(); V.mover(r, ev.key === 'ArrowDown' ? 1 : -1); }
                    else if (ev.key === 'Enter') { ev.preventDefault(); V.mover(r, 1); }
                });
                r.cTj = h('td', { class: 'c-tj mono' + (pcb.id_tarjeta_num ? '' : ' dim') }, tarjetaTxt(pcb));
                r.st = celdaEstado(r); r.acc = h('td', { class: 'c-acc' }, quitar);
                r.tr.append(
                    h('td', { class: 'c-placa' }, h('div', { class: 'macs-placa' }, T.tipoChip(pcb.tipo), h('span', { class: 'nm' }, pcb.nombre))),
                    r.cTj, h('td', { class: 'c-hw mono' }, 'V' + pcb.version), h('td', { class: 'c-fw' }, r.fw.el),
                    h('td', { class: 'c-mac' }, h('span', { class: 'muted' }, 'No lleva MAC')), h('td', { class: 'c-est' }, r.st), r.acc);
                setEstado(r, pcb.firmware ? 'guardada' : 'vacia', pcb.firmware ? `Programada · firmware ${pcb.firmware}` : 'Sin firmware: elígelo y queda programada');
                return r;
            };

            // ---- filtros y orden
            V.filtradas = () => {
                const f = V.filtro, q = f.q.trim().toLowerCase(), tj = f.tj.trim().replace(/^#/, '');
                const l = [...V.rows.values()].filter((r) => {
                    const p = r.pcb;
                    if (f.tipo && p.tipo !== f.tipo) return false;
                    if (tj && !(p.id_tarjeta_num && Number(p.id_tarjeta_num) === Number(tj))) return false;
                    if (q) {
                        const t = `${p.nombre} ${p.serie} ${p.id_tarjeta_num ? '#' + p.id_tarjeta_num : ''} ${modo === 'mac' ? (r.orig || '') + ' ' + (r.orig || '').replace(/:/g, '') : ''}`.toLowerCase();
                        if (!t.includes(q.replace(/:/g, '')) && !t.includes(q)) return false;
                    }
                    return true;
                });
                const num = (x) => (x === null || x === undefined || x === '' ? Infinity : Number(x));
                l.sort(f.orden === 'tarjeta'
                    ? (a, b) => num(a.pcb.id_tarjeta_num) - num(b.pcb.id_tarjeta_num) || a.pcb.tipo.localeCompare(b.pcb.tipo) || num(a.pcb.serie) - num(b.pcb.serie)
                    : (a, b) => num(a.pcb.serie) - num(b.pcb.serie) || a.pcb.tipo.localeCompare(b.pcb.tipo));
                return l;
            };

            // ---- pintar (sin recrear las filas: no se pierde lo que se está tecleando)
            V.pintar = () => {
                const l = V.filtradas();
                V.visibles = l;
                const tope = modo === 'mac' ? V.limite : Infinity;
                const mostrar = l.slice(0, tope);
                const deseadas = new Set(mostrar.map((r) => r.tr));
                [...V.tbody.children].forEach((tr) => { if (!deseadas.has(tr)) tr.remove(); });
                mostrar.forEach((r, i) => { if (V.tbody.children[i] !== r.tr) V.tbody.insertBefore(r.tr, V.tbody.children[i] || null); });
                V.tbl.hidden = !mostrar.length;
                V.aviso.replaceChildren();
                if (V.error) V.aviso.appendChild(T.banner('bad', 'alert', V.error, ' ', h('button', { class: 'btn btn-sm', type: 'button', onclick: () => V.cargar() }, 'Reintentar')));
                else if (!V.cargado) V.aviso.appendChild(h('p', { class: 'muted' }, 'Cargando…'));
                else if (!V.rows.size) V.aviso.appendChild(modo === 'pend'
                    ? T.empty('check', 'No hay placas pendientes de MAC o firmware', 'Cuando lleguen placas nuevas o se emparejen, aparecerán aquí solas.')
                    : T.empty('list', 'Todavía no hay MAC registradas', 'Las que guardes en «Pendientes» aparecerán aquí para corregirlas.'));
                else if (!l.length) V.aviso.appendChild(T.empty('search', 'Ninguna placa coincide con el filtro', 'Cambia el tipo o borra la búsqueda.'));
                if (modo === 'mac' && l.length > mostrar.length) {
                    V.aviso.appendChild(h('div', { class: 'row', style: 'padding:10px 0' },
                        h('span', { class: 'muted' }, `Mostrando ${mostrar.length} de ${l.length}.`),
                        h('button', { class: 'btn btn-sm', type: 'button', onclick: () => { V.limite += 200; V.pintar(); } }, 'Mostrar 200 más')));
                }
                refrescarContadores();
            };

            V.limite = 200;

            // ---- cargar del servidor y conciliar
            V.cargar = async () => {
                const url = modo === 'pend' ? '/api/pcb?sin_mac=1&limit=5000' : '/api/pcb?limit=5000';
                const [res, r3] = await Promise.all([api(url), modo === 'pend' ? api('/api/pcb?tipo=R3&sin_firmware=1&limit=5000') : null]);
                if (res.ok && r3 && r3.ok && r3.data && res.data) res.data.items = (res.data.items || []).concat(r3.data.items || []);
                if (!S.vivo) return;
                if (!res.ok) { V.error = res.network ? 'Sin conexión con el servidor.' : `No se pudieron cargar las placas: ${res.error}`; V.pintar(); return; }
                V.error = '';
                S.macBD.clear();
                const items = ((res.data && res.data.items) || []).filter((p) => (p.tipo === 'R3'
                    ? (modo === 'pend' ? !p.firmware && p.estado_ciclo !== 'FALLA' && p.estado_ciclo !== 'BAJA' : !!p.firmware && p.estado_ciclo !== 'BAJA')
                    : (p.tipo === 'R1' || p.tipo === 'R2') && (modo === 'pend' ? !p.mac && p.estado_ciclo !== 'FALLA' && p.estado_ciclo !== 'BAJA' : !!p.mac && p.estado_ciclo !== 'BAJA')));
                const vistos = new Set();
                items.forEach((p) => {
                    vistos.add(p.id);
                    let r = V.rows.get(p.id);
                    if (!r) { r = V.crearFila(p); V.rows.set(p.id, r); return; }
                    r.pcb = p; r.cTj.textContent = tarjetaTxt(p); r.cTj.className = 'c-tj mono' + (p.id_tarjeta_num ? '' : ' dim');
                    if (modo === 'mac' && r.mac === r.orig && p.mac !== r.orig && document.activeElement !== r.inp) {   // otra persona la cambió
                        r.orig = p.mac; r.mac = p.mac; r.inp.value = p.mac; V.revalidar(r);
                    }
                    if (p.firmware && document.activeElement !== r.fw.sel && !r.fw.otro.matches(':focus') && r.fw.get() !== p.firmware && (modo === 'mac' || !r.mac)) r.fw.set(p.firmware);
                });
                [...V.rows.values()].forEach((r) => {
                    if (vistos.has(r.id)) return;
                    if (r.saved) return;   // guardada aquí: se queda con su ✓ hasta «Quitar guardadas»
                    const sucia = modo === 'pend' ? !!r.mac : r.mac !== r.orig;
                    if (sucia && !r.busy) { r.obsoleta = modo === 'pend' ? 'Esta placa ya no está pendiente (otra persona la guardó o cambió). Revisa antes de teclear.' : 'Esta placa cambió en otra parte (MAC borrada o placa dada de baja).'; V.revalidar(r); return; }
                    if (r.busy) return;
                    r.tr.remove(); V.rows.delete(r.id);
                });
                V.cargado = true;
                V.pintar();
                V.revalidarCompletas();
            };
            return V;
        }

        // ---- acciones específicas de "Con MAC"
        async function guardarFw(r, val) {
            r.busy = true; setEstado(r, 'guardando', 'Guardando firmware…');
            const res = await api(`/api/pcb/${r.id}/firmware`, { method: 'PUT', body: { firmware: val || null } });
            r.busy = false;
            if (!S.vivo) return;
            if (res.ok) {
                r.pcb = Object.assign({}, r.pcb, res.data || {});
                if (val && !(S.fw[r.pcb.tipo] || []).includes(val)) cargarFw();
                setEstado(r, 'guardada', val ? `Firmware ${val} guardado` : 'Firmware borrado'); pitar(true);
                anunciar(`${r.pcb.nombre}: firmware ${val || 'borrado'}`);
            } else {
                r.srv = res.network ? 'Sin conexión con el servidor: el firmware no se guardó.' : res.error;
                setEstado(r, 'error', r.srv); pitar(false); anunciar(`${r.pcb.nombre}: ${r.srv}`);
            }
        }
        function botonBorrar(r) {
            const b = h('button', { class: 'btn btn-danger', type: 'button', 'aria-label': `Borrar la MAC de ${r.pcb.nombre}` }, icon('trash'), 'Borrar MAC');
            b.addEventListener('click', () => {
                const cancelar = h('button', { class: 'btn', type: 'button' }, 'Cancelar');
                const borrar = h('button', { class: 'btn btn-danger', type: 'button' }, 'Borrar');
                const cerrar = () => { r.acc.replaceChildren(b); b.focus(); r.srv = null; vMac.revalidar(r); };
                cancelar.addEventListener('click', cerrar);
                borrar.addEventListener('click', async () => {
                    borrar.disabled = true;
                    const res = await api(`/api/pcb/${r.id}/mac`, { method: 'PUT', body: { mac: '' } });
                    if (!S.vivo) return;
                    if (res.ok) {
                        vMac.rows.delete(r.id); r.tr.remove(); vMac.pintar(); S.macBD.clear();
                        toast(`MAC de ${r.pcb.nombre} borrada. Vuelve a estar pendiente.`);
                        anunciar(`MAC de ${r.pcb.nombre} borrada`);
                        vPend.cargar();
                    } else {
                        r.acc.replaceChildren(b); r.srv = res.network ? 'Sin conexión con el servidor: no se borró.' : res.error; setEstado(r, 'error', r.srv); b.focus();
                    }
                });
                const caja = h('div', { class: 'macs-conf', role: 'group', 'aria-label': `Confirmar borrado de la MAC de ${r.pcb.nombre}`, onkeydown: (ev) => { if (ev.key === 'Escape') { ev.stopPropagation(); cerrar(); } } }, borrar, cancelar);
                r.acc.replaceChildren(caja);
                setEstado(r, 'error', `¿Borrar la MAC ${r.orig}? La placa volverá a Pendientes.`);
                r.st.dataset.e = 'obsoleta';
                cancelar.focus();
            });
            return b;
        }

        // El flasheo por USB (Web Serial) vive en su propia sección "Programación" (sec_programacion.js).

        // ------------------------------------------------------------ armazón de la sección
        const vPend = crearVista('pend');
        const vMac = crearVista('mac');
        let cargandoFw = null;
        async function cargarFw() {
            const res = await api('/api/firmware');
            if (res.ok && res.data) { S.fw = { R1: res.data.R1 || [], R2: res.data.R2 || [], R3: res.data.R3 || [] }; }
        }

        const cont = { pend: h('div', { class: 'stack', role: 'tabpanel', id: 'macs-p-pend', 'aria-labelledby': 'macs-t-pend' }),
            pegar: h('div', { class: 'stack', role: 'tabpanel', id: 'macs-p-pegar', 'aria-labelledby': 'macs-t-pegar', hidden: true }),
            mac: h('div', { class: 'stack', role: 'tabpanel', id: 'macs-p-mac', 'aria-labelledby': 'macs-t-mac', hidden: true }),
            r3: h('div', { class: 'stack', role: 'tabpanel', id: 'macs-p-r3', 'aria-labelledby': 'macs-t-r3', hidden: true }) };
        const nPend = h('span', { class: 'n' }, '–'), nMac = h('span', { class: 'n' }, '–'), nR3 = h('span', { class: 'n' }, '–');
        const tabBtn = (id, txt, extra) => h('button', { type: 'button', role: 'tab', id: 'macs-t-' + id, 'aria-controls': 'macs-p-' + id, 'aria-selected': 'false', tabindex: '-1', dataset: { tab: id } }, txt, extra || null);
        const tabs = { pend: tabBtn('pend', 'Pendientes ', nPend), pegar: tabBtn('pegar', 'Pegar varias'), mac: tabBtn('mac', 'Con MAC ', nMac), r3: tabBtn('r3', 'R3 firmware ', nR3) };
        const contFaltan = h('b', null, '0'), contHoy = h('b', null, String(S.hoy.n)), contErr = h('span', { class: 'err' });
        const contador = h('div', { class: 'macs-counter' },
            h('span', null, 'Faltan ', contFaltan), h('span', { class: 'ok' }, 'Guardadas hoy ', contHoy), contErr);

        function refrescarContadores() {
            const pend = [...vPend.rows.values()].filter((r) => !r.saved && !r.obsoleta);
            contFaltan.textContent = String(pend.length);
            contHoy.textContent = String(S.hoy.n);
            const errs = [...vPend.rows.values()].filter((r) => r.estado === 'error' || r.estado === 'repetida').length;
            contErr.textContent = errs ? `· ${errs} con error` : '';
            contErr.style.color = errs ? 'var(--bad)' : '';
            nPend.textContent = String(pend.length);
            nMac.textContent = vMac.cargado ? String(vMac.rows.size) : '–';
            if (vPend.resumen) vPend.resumen();
        }

        const head = h('div', { class: 'macs-head' },
            h('div', { class: 'macs-tabs', role: 'tablist', 'aria-label': 'Vistas de MAC y firmware' }, tabs.pend, tabs.pegar, tabs.mac, tabs.r3),
            contador);
        tabs.pend.parentNode.addEventListener('keydown', (ev) => {
            const ids = ['pend', 'pegar', 'mac', 'r3'], i = ids.indexOf(S.tab);
            if (ev.key === 'ArrowRight' || ev.key === 'ArrowLeft') {
                ev.preventDefault();
                const n = ids[(i + (ev.key === 'ArrowRight' ? 1 : ids.length - 1)) % ids.length];
                irTab(n); tabs[n].focus();
            }
        });
        Object.entries(tabs).forEach(([id, b]) => b.addEventListener('click', () => irTab(id)));

        function irTab(id) {
            S.tab = id;
            Object.entries(tabs).forEach(([k, b]) => { b.setAttribute('aria-selected', String(k === id)); b.tabIndex = k === id ? 0 : -1; cont[k].hidden = k !== id; });
            T.store.set('tqt.macs.tab', id);
            if (id === 'mac' && !vMac.cargado) vMac.cargar();
            if (id === 'r3' && !R3.cargado) cargarR3();
            if (id === 'pegar') actualizarPegar();
        }

        // ---- barra de filtros común
        function barra(V, opts) {
            const seg = h('div', { class: 'seg', role: 'group', 'aria-label': 'Tipo de placa' });
            [['', 'Todas'], ['R1', 'R1 Principal'], ['R2', 'R2 Respaldo'], ['R3', 'R3']].forEach(([v, t]) => {
                const b = h('button', { type: 'button', 'aria-pressed': String(V.filtro.tipo === v), onclick: () => {
                    V.filtro.tipo = v; seg.querySelectorAll('button').forEach((x, i) => x.setAttribute('aria-pressed', String(['', 'R1', 'R2', 'R3'][i] === v))); V.pintar();
                } }, t);
                seg.appendChild(b);
            });
            const q = h('input', { class: 'input', type: 'search', id: 'macs-q-' + V.modo, autocomplete: 'off', placeholder: V.modo === 'mac' ? 'Placa, serie, MAC…' : 'Placa, serie o tarjeta…', oninput: (e) => { V.filtro.q = e.target.value; V.pintar(); } });
            const bar = h('div', { class: 'macs-bar', role: 'search' },
                h('div', { class: 'field' }, h('span', { class: 'lbl' }, 'Tipo'), seg),
                h('div', { class: 'field' }, h('label', { for: q.id }, 'Buscar'), q));
            if (V.modo === 'pend') {
                const tj = h('input', { class: 'input mono num', type: 'text', inputmode: 'numeric', id: 'macs-tj', placeholder: 'Nº', autocomplete: 'off', oninput: (e) => { V.filtro.tj = e.target.value; V.pintar(); } });
                const ord = h('select', { class: 'input', id: 'macs-ord', onchange: (e) => { V.filtro.orden = e.target.value; V.pintar(); } },
                    h('option', { value: 'serie' }, 'Por serie'), h('option', { value: 'tarjeta' }, 'Por tarjeta'));
                bar.append(h('div', { class: 'field' }, h('label', { for: 'macs-tj' }, 'Solo tarjeta'), tj),
                    h('div', { class: 'field' }, h('label', { for: 'macs-ord' }, 'Orden'), ord));
            }
            return bar;
        }

        // ---- pestaña Pendientes
        function montarPend() {
            const bar = barra(vPend);
            // firmware por defecto de todas las visibles de cada rol
            ['R1', 'R2'].forEach((rol) => {
                const sel = h('select', { class: 'input', id: 'macs-fwd-' + rol, title: `Pone este firmware a todas las ${rol} (${rol === 'R1' ? 'Principal' : 'Respaldo'}) de la lista` });
                const pintarOpc = () => {
                    sel.replaceChildren(h('option', { value: '' }, 'Elegir…'), ...(S.fw[rol] || []).map((v) => h('option', { value: v }, v)));
                    sel.value = ultimoFw(rol);
                };
                pintarOpc(); vPend.fwSel = vPend.fwSel || {}; vPend.fwSel[rol] = pintarOpc;
                sel.addEventListener('change', () => {
                    recordarFw(rol, sel.value);
                    if (!sel.value) return;
                    vPend.rows.forEach((r) => { if (r.pcb.tipo === rol && !r.saved && !r.busy) r.fw.set(sel.value); });
                    toast(`Firmware ${sel.value} aplicado a las ${rol} de la lista.`);
                });
                bar.appendChild(h('div', { class: 'field' }, h('label', { for: sel.id }, `Aplicar firmware ${rol}`), sel));
            });
            const snd = h('button', { class: 'btn btn-ghost', type: 'button', 'aria-pressed': String(S.sonido), title: 'Sonido al guardar o fallar (apagado por defecto)' },
                icon(S.sonido ? 'vol' : 'muted'), h('span', null, S.sonido ? 'Sonido activado' : 'Sonido apagado'));
            snd.addEventListener('click', () => {
                S.sonido = !S.sonido; T.store.set('tqt.macs.sonido', S.sonido ? '1' : '0');
                snd.setAttribute('aria-pressed', String(S.sonido)); snd.replaceChildren(icon(S.sonido ? 'vol' : 'muted'), h('span', null, S.sonido ? 'Sonido activado' : 'Sonido apagado'));
                pitar(true);
            });
            const limp = h('button', { class: 'btn', type: 'button', onclick: () => {
                [...vPend.rows.values()].filter((r) => r.saved).forEach((r) => { r.tr.remove(); vPend.rows.delete(r.id); });
                vPend.pintar();
            } }, icon('check'), 'Quitar guardadas');
            const act = h('button', { class: 'btn', type: 'button', onclick: () => { vPend.cargar(); vMac.cargado && vMac.cargar(); } }, icon('refresh'), 'Actualizar');
            const lr3 = h('button', { class: 'btn', type: 'button', title: 'Escanea varias R3 y ponles un solo firmware', onclick: () => loteR3Abrir() }, icon('layers'), 'Lote R3 (escanear)');
            bar.append(h('div', { class: 'row macs-acts' }, lr3, limp, snd, act));

            vPend.tbl = tabla(vPend.tbody, true);
            const wrap = h('div', { class: 'macs-wrap' }, vPend.tbl);
            const pie = h('div', { class: 'macs-foot macs-kbd' },
                h('span', null, h('kbd', null, 'Enter'), ' guarda y baja a la siguiente'), h('span', null, h('kbd', null, '↑'), ' ', h('kbd', null, '↓'), ' cambian de fila'),
                h('span', null, h('kbd', null, 'Esc'), ' borra el campo'), h('span', null, 'Pega la MAC en cualquier formato: se ordena sola.'));
            vPend.resumen = () => { /* el contador ya está en la cabecera */ };
            cont.pend.append(bar, vPend.aviso, wrap, pie);
        }
        function tabla(tbody, conAcc) {
            const th = (c, t) => h('th', { class: c, scope: 'col' }, t);
            const t = h('table', { class: 'macs-tbl' },
                h('thead', null, h('tr', null, th('c-placa', 'Placa'), th('c-tj', 'Tarjeta'), th('c-hw', 'Hardware'), th('c-fw', 'Firmware'), th('c-mac', 'MAC'), th('c-est', 'Estado'), conAcc ? h('th', { class: 'c-acc', scope: 'col' }, h('span', { class: 'sr-only' }, 'Acciones')) : null)),
                tbody);
            return t;
        }

        // ---- pestaña Con MAC
        function montarMac() {
            const bar = barra(vMac);
            bar.append(h('div', { class: 'row macs-acts' }, h('button', { class: 'btn', type: 'button', onclick: () => vMac.cargar() }, icon('refresh'), 'Actualizar')));
            vMac.tbl = tabla(vMac.tbody, true);
            const wrap = h('div', { class: 'macs-wrap' }, vMac.tbl);
            const pie = h('div', { class: 'macs-foot macs-kbd' },
                h('span', null, 'Cambia la MAC y pulsa ', h('kbd', null, 'Enter'), ' para guardarla'), h('span', null, h('kbd', null, 'Esc'), ' vuelve al valor guardado'),
                h('span', null, 'El firmware se guarda al elegirlo.'));
            cont.mac.append(bar, vMac.aviso, wrap, pie);
        }

        // ---- pestaña R3 (v1.3.44): la R3 no lleva MAC pero sí se programa; aquí se registra su firmware (programada = con firmware)
        const R3 = { cargado: false, items: [], soloSin: true, q: '', tbody: h('tbody'), aviso: h('div'), filas: new Map() };
        async function cargarR3() {
            const res = await api('/api/pcb?tipo=R3&limit=5000');
            if (!S.vivo) return;
            if (!res.ok) { R3.aviso.replaceChildren(T.banner('bad', 'alert', res.error || 'No se pudieron cargar las R3.')); return; }
            R3.aviso.replaceChildren();
            R3.items = ((res.data && res.data.items) || []).filter((p) => p.estado_ciclo !== 'BAJA' && p.estado_ciclo !== 'FALLA')
                .sort((a, b) => String(a.serie).localeCompare(String(b.serie)) || String(a.version).localeCompare(String(b.version)));
            R3.cargado = true; pintarR3();
        }
        function filaR3(p) {
            const st = h('div', { class: 'macs-st', dataset: { e: p.firmware ? 'guardada' : 'vacia' } }, p.firmware ? 'Programada' : 'Sin firmware');
            const quitar = h('button', { class: 'btn btn-sm btn-ghost', type: 'button', title: 'Quitar el firmware: la R3 vuelve a «Sin firmware»', hidden: !p.firmware, onclick: async () => {
                st.dataset.e = 'guardando'; st.textContent = 'Quitando firmware…';
                const res = await api(`/api/pcb/${p.id}/firmware`, { method: 'PUT', body: { firmware: null } });
                if (!S.vivo) return;
                if (res.ok) { p.firmware = null; fw.set(''); quitar.hidden = true; st.dataset.e = 'vacia'; st.textContent = 'Firmware quitado · sin firmware'; nR3.textContent = String(R3.items.filter((x) => !x.firmware).length); recargarSuave(); }
                else { st.dataset.e = 'error'; st.textContent = res.network ? 'Sin conexión con el servidor.' : res.error; }
            } }, icon('x'), 'Quitar firmware');
            const fw = fwWidget('R3', p.firmware, p.nombre, async (val) => {
                if (!val || val === p.firmware) return;
                st.dataset.e = 'guardando'; st.textContent = 'Guardando firmware…';
                const res = await api(`/api/pcb/${p.id}/firmware`, { method: 'PUT', body: { firmware: val } });
                if (!S.vivo) return;
                if (res.ok) {
                    Object.assign(p, res.data || { firmware: val });
                    if (!(S.fw.R3 || []).includes(val)) cargarFw();
                    recordarFw('R3', val);
                    st.dataset.e = 'guardada'; st.textContent = `Firmware ${val} guardado · programada`; pitar(true); quitar.hidden = false;
                    anunciar(`${p.nombre}: firmware ${val}`); nR3.textContent = String(R3.items.filter((x) => !x.firmware).length);
                } else {
                    st.dataset.e = 'error'; st.textContent = res.network ? 'Sin conexión con el servidor: el firmware no se guardó.' : res.error; pitar(false);
                    anunciar(`${p.nombre}: ${st.textContent}`);
                }
            });
            const tr = h('tr', { dataset: { id: String(p.id) } },
                h('td', { class: 'c-placa mono' }, p.nombre), h('td', { class: 'c-tj mono' }, tarjetaTxt(p)), h('td', { class: 'c-hw mono' }, 'V' + p.version),
                h('td', { class: 'c-fw' }, fw.el), h('td', { class: 'c-est' }, st), h('td', { class: 'c-acc' }, quitar));
            const f = { p, tr, fw };
            R3.filas.set(p.id, f);
            return f;
        }
        function pintarR3() {
            const q = R3.q.trim().toLowerCase();
            R3.filas.clear();
            const vis = R3.items.filter((p) => (!R3.soloSin || !p.firmware) && (!q || p.nombre.toLowerCase().includes(q) || String(p.serie).includes(q) || String(p.id_tarjeta_num || '').includes(q)));
            R3.tbody.replaceChildren(...vis.map((p) => filaR3(p).tr));
            if (!vis.length) R3.tbody.appendChild(h('tr', null, h('td', { colspan: 6, class: 'muted' }, R3.soloSin ? 'Todas las R3 tienen firmware.' : 'Sin coincidencias.')));
            nR3.textContent = String(R3.items.filter((p) => !p.firmware).length);
        }
        function montarR3() {
            const q = h('input', { class: 'input', type: 'search', id: 'macs-q-r3', autocomplete: 'off', placeholder: 'Placa, serie o tarjeta…', oninput: (e) => { R3.q = e.target.value; pintarR3(); } });
            const solo = h('input', { type: 'checkbox', id: 'macs-r3-solo', checked: true, onchange: (e) => { R3.soloSin = e.target.checked; pintarR3(); } });
            const bar = h('div', { class: 'macs-bar', role: 'search' },
                h('div', { class: 'field' }, h('label', { for: q.id }, 'Buscar'), q),
                h('div', { class: 'field' }, h('label', { for: solo.id }, solo, ' Solo sin firmware')),
                h('div', { class: 'row macs-acts' }, h('button', { class: 'btn', type: 'button', onclick: () => loteR3Abrir() }, icon('layers'), 'Lote R3 (escanear)'),
                    h('button', { class: 'btn', type: 'button', onclick: () => cargarR3() }, icon('refresh'), 'Actualizar')));
            const th = (c, t) => h('th', { class: c, scope: 'col' }, t);
            const tbl = h('table', { class: 'macs-tbl' }, h('thead', null, h('tr', null, th('c-placa', 'Placa'), th('c-tj', 'Tarjeta'), th('c-hw', 'Hardware'), th('c-fw', 'Firmware'), th('c-est', 'Estado'), h('th', { class: 'c-acc', scope: 'col' }, h('span', { class: 'sr-only' }, 'Acciones')))), R3.tbody);
            cont.r3.append(T.banner('info', 'info', 'La R3 no lleva MAC: queda programada al registrar su firmware (se guarda al elegirlo).'), bar, R3.aviso, h('div', { class: 'macs-wrap' }, tbl));
        }

        // ------------------------------------------------------------ pestaña Pegar varias
        const P = { fase: 'editando', lineas: [], resultados: null, confirmando: false };
        const ta = h('textarea', { id: 'macs-ta', spellcheck: 'false', autocomplete: 'off', wrap: 'off',
            placeholder: 'TQT-R1-V30-0021  70:4b:ca:5b:9f:6e  4.1\nTQT-R2-V30-0010;704bca5b9ca2\n0021 R1 704bca5b9f6e' });
        const modoAuto = h('input', { type: 'radio', name: 'macs-modo', value: 'auto', checked: true });
        const modoOrden = h('input', { type: 'radio', name: 'macs-modo', value: 'orden' });
        const fwPeg = {};
        const preview = h('div');
        const btnRev = h('button', { class: 'btn btn-primary', type: 'button' }, icon('search'), 'Revisar (no guarda)');
        const btnLimp = h('button', { class: 'btn btn-ghost', type: 'button' }, 'Limpiar');
        const infoTxt = h('span', { class: 'hint', 'aria-live': 'polite' });

        function montarPegar() {
            ['R1', 'R2'].forEach((rol) => {
                const sel = h('select', { class: 'input', id: 'macs-pfw-' + rol });
                fwPeg[rol] = { sel, pintar() { sel.replaceChildren(h('option', { value: '' }, 'Sin firmware'), ...(S.fw[rol] || []).map((v) => h('option', { value: v }, v))); sel.value = ultimoFw(rol); } };
                fwPeg[rol].pintar();
                sel.addEventListener('change', () => { recordarFw(rol, sel.value); invalidar(); });
            });
            const panel = h('div', { class: 'macs-panel' },
                h('h2', null, 'Pega lo que sale del programador o de Excel'),
                h('p', { class: 'hint' }, 'Una placa por línea. Sirve separar con espacio, tabulador, coma o punto y coma. La MAC puede venir con «:», «-», «.» o sin separadores.'),
                h('div', { class: 'field' }, h('label', { for: 'macs-ta' }, 'Texto'), ta),
                h('fieldset', { class: 'macs-radio' }, h('legend', null, 'Cómo se reconocen las placas'),
                    h('label', null, modoAuto, h('span', null, 'Cada línea trae la placa ', h('span', { class: 'muted' }, '(TQT-R1-V30-0021, o «0021 R1»)'))),
                    h('label', null, modoOrden, h('span', null, 'Solo MAC: asignar en orden a las pendientes que se ven en «Pendientes» ', h('span', { class: 'muted' }, '(respeta el filtro y el orden de esa lista)')))),
                h('div', { class: 'row wrap' },
                    h('div', { class: 'field' }, h('label', { for: 'macs-pfw-R1' }, 'Firmware R1 si la línea no lo trae'), fwPeg.R1.sel),
                    h('div', { class: 'field' }, h('label', { for: 'macs-pfw-R2' }, 'Firmware R2 si la línea no lo trae'), fwPeg.R2.sel)),
                h('div', { class: 'row wrap' }, btnRev, btnLimp, infoTxt));
            cont.pegar.append(h('div', { class: 'macs-paste' }, panel, h('div', { class: 'macs-panel', 'aria-live': 'polite' }, h('h2', null, 'Vista previa'), preview)));
            pintarPreview();
            ta.addEventListener('input', invalidar);
            modoAuto.addEventListener('change', invalidar); modoOrden.addEventListener('change', invalidar);
            btnRev.addEventListener('click', revisar);
            btnLimp.addEventListener('click', () => { ta.value = ''; invalidar(); ta.focus(); });
        }
        function actualizarPegar() {
            ['R1', 'R2'].forEach((r) => { if (fwPeg[r]) { const v = fwPeg[r].sel.value; fwPeg[r].pintar(); if (v) fwPeg[r].sel.value = v; } });
        }
        function invalidar() {
            if (P.fase === 'editando' && !P.resultados) return;
            P.fase = 'editando'; P.resultados = null; P.confirmando = false; pintarPreview();
        }

        /** Una línea -> {n, crudo, tipo, serie, nombre, mac, fw, err} (parseo tolerante). */
        function parsearLinea(crudo, n, modo) {
            const L = { n, crudo, nombre: null, mac: null, fw: '', err: '' };
            let s = crudo.replace(/\bMAC\b\s*[:=]?/gi, ' ').replace(/\b(?:fw|firmware)\b\s*[:=]?/gi, ' ');
            const mm = extraerMac(s);
            if (mm && mm.relleno) { L.err = 'MAC de relleno (solo ceros o solo F).'; }
            if (mm && mm.mac) {
                L.mac = mm.mac;
                s = s.replace(mm.span, ' ');
            }
            if (modo === 'orden') {
                if (!L.mac && !L.err) L.err = 'No hay una MAC en esta línea.';
                return L;
            }
            const mn = execNombre(s);
            if (mn) {
                const pn = T.parseNombre(mn[0]);
                if (pn) { L.nombre = pn.nombre; L.tipo = pn.tipo; s = s.replace(mn[0], ' '); } else if (!L.err) L.err = 'El nombre de la placa no es válido (versión o serie en cero).';
            } else {
                let m2 = /(?:^|[\s,;|])(R[12])(?:[\s_-]*V(\d{1,3}))?[\s_-]*(\d{1,4})(?![0-9A-Za-z:.\-])/i.exec(s);
                let m3 = m2 ? null : /(?:^|[\s,;|])(\d{1,4})(?![0-9A-Za-z:.\-])[\s,;|_-]+(R[12])(?![0-9A-Za-z])/i.exec(s);
                if (m2 || m3) {
                    const tipo = (m2 ? m2[1] : m3[2]).toUpperCase(), ver = String(Number(m2 && m2[2] ? m2[2] : (T.VERSION_DEFAULT || '30'))), serie = String(m2 ? m2[3] : m3[1]).padStart(4, '0');
                    if (!Number(serie)) L.err = L.err || 'La serie no puede ser 0000.';
                    L.nombre = T.nombreDe(tipo, ver, serie); L.tipo = tipo;
                    s = s.replace((m2 || m3)[0], ' ');
                } else {
                    const m4 = /^\s*(\d{1,4})(?![0-9A-Za-z:.\-])/.exec(s);
                    if (m4) {
                        const serie = m4[1].padStart(4, '0');
                        const cand = [...vPend.rows.values()].filter((r) => r.pcb.serie === serie && !r.saved);
                        if (cand.length === 1) { L.nombre = cand[0].pcb.nombre; L.tipo = cand[0].pcb.tipo; s = s.replace(m4[0], ' '); }
                        else L.err = L.err || (cand.length > 1 ? `La serie ${serie} tiene R1 y R2: escribe «${serie} R1» o «${serie} R2».` : `No hay una placa pendiente con la serie ${serie}: escribe el nombre completo (TQT-R1-V30-${serie}).`);
                    }
                }
            }
            if (!L.nombre && !L.err) L.err = 'No se reconoce la placa (esperaba algo como TQT-R1-V30-0021 o «0021 R1»).';
            if (!L.mac && !L.err) L.err = 'No hay una MAC válida de 12 dígitos en esta línea.';
            const resto = s.split(/[\s,;|]+/).filter(Boolean);
            if (resto.length) {
                const f = resto.find((x) => /\d/.test(x));
                if (f) { if (/^[A-Za-z0-9._+-]{1,40}$/.test(f)) L.fw = f.replace(/^v(?=\d)/i, ''); else L.err = L.err || `Firmware no reconocido: «${f}».`; }
            }
            return L;
        }

        function tipoFila(L) { return L.tipo; }

        async function revisar() {
            const texto = ta.value;
            const modo = modoOrden.checked ? 'orden' : 'auto';
            const crudas = texto.split(/\r?\n/).map((x) => x.trim()).filter((x) => x && !x.startsWith('#'));
            if (!crudas.length) { infoTxt.textContent = 'Pega primero algún texto.'; infoTxt.className = 'hint err'; ta.focus(); return; }
            infoTxt.textContent = ''; infoTxt.className = 'hint';
            const lineas = crudas.map((c, i) => parsearLinea(c, i + 1, modo));
            if (modo === 'orden') {
                const dest = vPend.visibles.filter((r) => !r.saved && !r.obsoleta && !r.esR3);
                let k = 0;
                lineas.forEach((L) => {
                    if (L.err) return;
                    const r = dest[k++];
                    if (!r) { L.err = 'Sobra: no hay más pendientes visibles donde asignarla.'; return; }
                    L.nombre = r.pcb.nombre; L.tipo = r.pcb.tipo; L.pcb_id = r.id;
                });
            }
            const visto = new Map();
            lineas.forEach((L) => {
                if (L.err) return;
                const previa = visto.get(L.mac);
                if (previa) { L.err = `misma MAC que la línea ${previa}.`; L.codigoCli = 409; return; }
                visto.set(L.mac, L.n);
                if (L.tipo === 'R3') { L.err = 'las R3 no llevan MAC (su firmware se registra en la pestaña R3 firmware).'; L.codigoCli = 'r3'; return; }
                if (!L.fw) L.fw = (fwPeg[L.tipo] && fwPeg[L.tipo].sel.value) || '';
            });
            const enviar = lineas.filter((L) => !L.err);
            P.lineas = lineas; P.resultados = null; P.fase = 'revisando'; P.confirmando = false;
            btnRev.disabled = true; pintarPreview();
            const okSrv = await enviarLote(enviar, true);
            btnRev.disabled = false;
            if (!S.vivo) return;
            if (okSrv.error) { P.fase = 'editando'; P.error = okSrv.error; pintarPreview(); return; }
            P.error = '';
            P.fase = 'previsto'; P.resultados = true;
            pintarPreview();
            const b = preview.querySelector('[data-accion="guardar"]'); if (b && !b.disabled) b.focus();
        }

        /** Envía en tandas de 500. Rellena L.res = {ok, error, codigo}. Devuelve {error?}. */
        async function enviarLote(ls, simular) {
            for (let i = 0; i < ls.length; i += MAX_LOTE) {
                const tanda = ls.slice(i, i + MAX_LOTE);
                const items = tanda.map((L) => { const it = { mac: L.mac, firmware: L.fw || null }; if (L.pcb_id) it.pcb_id = L.pcb_id; else it.nombre = L.nombre; return it; });
                const res = await api('/api/programacion/lote', { method: 'POST', body: { items, simular }, timeout: 60000 });
                if (!res.ok) return { error: res.network ? 'Sin conexión con el servidor. No se guardó nada.' : `El servidor rechazó el lote: ${res.error}` };
                (res.data.resultados || []).forEach((f) => { tanda[f.indice].res = f; });
            }
            return {};
        }

        function estadoLinea(L) {
            if (L.guardada) return { e: 'guardada', t: 'Guardada' };
            if (L.err) return { e: L.codigoCli === 409 ? 'repetida' : 'error', t: L.codigoCli === 409 ? 'Repetida' : (L.codigoCli === 'r3' ? 'R3 no lleva MAC' : 'Formato'), d: L.err };
            const f = L.res;
            if (!f) return { e: 'vacia', t: '' };
            if (f.ok) return { e: 'valida', t: 'OK' };
            if (f.codigo === 409) return { e: 'repetida', t: 'Repetida', d: f.error };
            if (f.codigo === 404) return { e: 'error', t: 'No registrada', d: f.error };
            if (/\bR3\b/.test(f.error || '')) return { e: 'error', t: 'R3 no lleva MAC', d: f.error };
            return { e: 'error', t: 'Formato', d: f.error };
        }

        function pintarPreview() {
            preview.replaceChildren();
            if (P.fase === 'editando' && !P.error) {
                preview.appendChild(h('p', { class: 'hint' }, 'Pulsa «Revisar» para ver, línea por línea, qué se guardaría. Revisar no guarda nada.'));
                return;
            }
            if (P.error) { preview.appendChild(T.banner('bad', 'alert', P.error)); if (P.fase === 'editando') return; }
            if (P.fase === 'revisando') { preview.appendChild(h('p', { class: 'muted' }, 'Revisando…')); return; }
            const ok = P.lineas.filter((L) => !L.guardada && estadoLinea(L).e === 'valida');
            const guardadas = P.lineas.filter((L) => L.guardada).length;
            const mal = P.lineas.length - ok.length - guardadas;
            const res = h('div', { class: 'macs-sum' },
                h('span', { class: 'ok', style: 'color:var(--ok)' }, h('b', null, String(guardadas ? guardadas : ok.length)), guardadas ? ' guardadas' : ' correctas'),
                h('span', { style: mal ? 'color:var(--bad)' : '' }, h('b', null, String(mal)), ' con problema'),
                h('span', { class: 'muted' }, `${P.lineas.length} líneas`));
            preview.appendChild(res);
            if (P.fase === 'guardado') {
                preview.appendChild(T.banner(mal ? 'warn' : 'ok', mal ? 'alert' : 'check', `Se guardaron ${guardadas} MAC. ${mal ? `${mal} línea(s) no se guardaron: revisa el motivo en cada una.` : 'Todo quedó registrado.'} Puedes corregirlas en «Con MAC».`));
            }
            const t = h('table', { class: 'macs-tbl' },
                h('thead', null, h('tr', null, h('th', { style: 'width:44px' }, 'Lín.'), h('th', { style: 'width:200px' }, 'Placa'), h('th', { style: 'width:170px' }, 'MAC'), h('th', { style: 'width:70px' }, 'FW'), h('th', null, 'Estado'))),
                h('tbody', null, P.lineas.map((L) => {
                    const st = estadoLinea(L);
                    return h('tr', { dataset: { e: st.e === 'valida' ? '' : st.e === 'guardada' ? 'guardada' : '' } },
                        h('td', { class: 'mono dim' }, String(L.n)),
                        h('td', null, L.nombre ? h('div', { class: 'macs-placa' }, tipoFila(L) ? T.tipoChip(tipoFila(L)) : null, h('span', { class: 'nm' }, L.nombre)) : h('span', { class: 'dim' }, '—')),
                        h('td', { class: 'mono' }, L.mac || '—'),
                        h('td', { class: 'mono' }, L.fw || '—'),
                        h('td', null, h('div', { class: 'macs-st', dataset: { e: st.e }, title: st.d || '' }, ICONO_ESTADO[st.e] ? icon(ICONO_ESTADO[st.e]) : null, h('span', null, h('b', null, st.t), st.d && !/^R3/.test(st.t) ? ' · ' + st.d : ''))));
                })));
            preview.appendChild(h('div', { class: 'macs-wrap macs-prev' }, t));

            if (P.fase === 'previsto') {
                const acc = h('div', { class: 'row wrap' });
                if (!P.confirmando) {
                    const b = h('button', { class: 'btn btn-primary', type: 'button', 'data-accion': 'guardar', disabled: !ok.length }, icon('check'), `Guardar las ${ok.length} correctas`);
                    b.addEventListener('click', () => { P.confirmando = true; pintarPreview(); const c = preview.querySelector('[data-accion="confirmar"]'); if (c) c.focus(); });
                    acc.appendChild(b);
                    if (mal) acc.appendChild(h('span', { class: 'hint' }, `Las ${mal} con problema no se guardan.`));
                } else {
                    const c = h('button', { class: 'btn btn-primary', type: 'button', 'data-accion': 'confirmar' }, `Sí, guardar ${ok.length} MAC`);
                    const x = h('button', { class: 'btn', type: 'button' }, 'Cancelar');
                    c.addEventListener('click', () => guardarLote(ok));
                    x.addEventListener('click', () => { P.confirmando = false; pintarPreview(); const b = preview.querySelector('[data-accion="guardar"]'); if (b) b.focus(); });
                    acc.append(T.banner('warn', 'alert', 'Esto guarda las MAC de forma definitiva. No hay botón de deshacer (después solo puedes corregir cada una en «Con MAC»).'), c, x);
                }
                preview.appendChild(acc);
            }
        }

        async function guardarLote(ok) {
            const c = preview.querySelector('[data-accion="confirmar"]'); if (c) c.disabled = true;
            const r = await enviarLote(ok, false);
            if (!S.vivo) return;
            if (r.error) { P.error = r.error; P.confirmando = false; pintarPreview(); return; }
            let n = 0;
            ok.forEach((L) => { if (L.res && L.res.ok) { L.guardada = true; n++; if (L.fw) recordarFw(L.tipo, L.fw); } });
            for (let i = 0; i < n; i++) sumarHoy();
            P.fase = 'guardado'; P.confirmando = false; P.error = '';
            pintarPreview(); refrescarContadores();
            anunciar(`Se guardaron ${n} de ${ok.length} MAC`);
            pitar(n === ok.length);
            S.macBD.clear();
            vPend.cargar(); if (vMac.cargado) vMac.cargar(); cargarFw();
        }

        // ------------------------------------------------------------ montaje
        montarPend(); montarMac(); montarPegar(); montarR3();
        host.classList.add('macs');
        host.append(head, cont.pend, cont.pegar, cont.mac, cont.r3, vivo);
        vPend.pintar(); vMac.pintar();
        let inicial = T.store.get('tqt.macs.tab', 'pend'); if (!tabs[inicial]) inicial = 'pend';
        irTab(inicial);
        cargarFw().then(() => {
            if (!S.vivo) return;
            ['R1', 'R2'].forEach((rol) => { if (vPend.fwSel && vPend.fwSel[rol]) vPend.fwSel[rol](); });
            actualizarPegar();
            return vPend.cargar();
        }).then(() => {
            if (S.vivo && S.tab === 'pend' && (!document.activeElement || document.activeElement === document.body)) {
                const p = vPend.visibles.find((r) => !r.saved && !r.esR3); if (p) p.inp.focus({ preventScroll: true });
            }
        });

        // ------------------------------------------------------------ tiempo real
        let tRec = null;
        function recargarSuave() {
            clearTimeout(tRec);
            tRec = setTimeout(() => { timers.delete(tRec); if (!S.vivo) return; vPend.cargar(); if (vMac.cargado) vMac.cargar(); if (R3.cargado && !cont.r3.contains(document.activeElement)) cargarR3(); }, 250);
            timers.add(tRec);
        }
        const wsc = ctx.ws || (T.ws && T.ws());
        if (wsc && wsc.on) ['PCB_ACTUALIZADA', 'PCB_RECIBIDA', 'PCB_ELIMINADA'].forEach((ev) => { unsubs.push(wsc.on(ev, recargarSuave)); unsubs.push(wsc.on(ev, sumarHoy)); });
        if (ctx.alCambiarLote) ctx.alCambiarLote(() => recargarSuave());
        cargarHoy();

        // ------------------------------------------------------------ escáner remoto (v1.3.43): el celular lee la PCB y aquí se ubica su fila
        function ubicar(V, tab, r) {
            irTab(tab);
            const panel = cont[tab];
            if (V.filtro.tipo) { const todas = panel.querySelector('.seg button'); if (todas) todas.click(); }
            V.filtro.tj = ''; const tj = panel.querySelector('#macs-tj'); if (tj) tj.value = '';
            V.filtro.q = r.pcb.nombre; const q = panel.querySelector('#macs-q-' + V.modo); if (q) q.value = r.pcb.nombre;
            V.pintar();
            r.tr.scrollIntoView({ block: 'center', behavior: 'smooth' });
            r.tr.classList.remove('macs-flash'); void r.tr.offsetWidth; r.tr.classList.add('macs-flash');
            r.inp.focus({ preventScroll: true }); if (r.inp.select) r.inp.select();
            S.ultFila = r;
        }
        // ---- hoja "Lote R3" (v1.3.45): cada R3 escaneada se agrega a la lista y a todas se les pone un mismo firmware
        const LR = { items: new Map(), hoja: null, lista: null, fw: null, info: null, inp: null };
        async function loteR3Agregar(ver, serie, verTxt) {
            if (!R3.cargado) await cargarR3();
            const p = R3.items.find((x) => Number(x.serie) === serie && Number(String(x.version).replace(/\D/g, '')) === ver);
            const nombre = `TQT-R3-V${verTxt}-${String(serie).padStart(4, '0')}`;
            if (!p) return { ok: false, texto: `${nombre} no aparece entre las R3 activas (¿está registrada?).` };
            loteR3Abrir();
            if (LR.items.has(p.id)) { loteR3Pintar(); return { ok: true, texto: `${p.nombre} ya estaba en el lote R3 (${LR.items.size}).` }; }
            LR.items.set(p.id, p); loteR3Pintar(); pitar(true);
            return { ok: true, texto: `${p.nombre} agregada al lote R3 (${LR.items.size})${p.firmware ? ' · ya tenía firmware ' + p.firmware : ''}` };
        }
        function loteR3Pintar() {
            if (!LR.lista) return;
            const l = [...LR.items.values()];
            LR.lista.replaceChildren(...(l.length ? l.map((p) => h('div', { class: 'row', style: 'gap:8px;align-items:center;flex-wrap:nowrap' },
                T.tipoChip('R3'), h('span', { class: 'mono grow' }, p.nombre), h('span', { class: 'hint' }, p.firmware ? 'firmware ' + p.firmware : 'sin firmware'),
                h('button', { class: 'btn btn-sm btn-ghost', type: 'button', 'aria-label': `Quitar ${p.nombre}`, onclick: () => { LR.items.delete(p.id); loteR3Pintar(); } }, icon('x'))))
                : [h('p', { class: 'muted', style: 'margin:0' }, 'Escanea las R3 (celular vinculado o lector USB en el campo de arriba).')]));
            LR.info.textContent = `${l.length} R3 en el lote`;
        }
        function loteR3Abrir() {
            if (LR.hoja) return;
            LR.lista = h('div', { class: 'stack', style: 'gap:6px;max-height:45vh;overflow:auto' });
            LR.info = h('b');
            LR.fw = fwWidget('R3', ultimoFw('R3'), 'el lote R3', () => {});
            LR.inp = h('input', { class: 'input mono', type: 'text', autocomplete: 'off', spellcheck: 'false', placeholder: 'Escanea o escribe TQT-R3-V30-0001 y Enter' });
            LR.inp.addEventListener('keydown', async (ev) => {
                if (ev.key !== 'Enter') return;
                ev.preventDefault();
                const v = LR.inp.value; LR.inp.value = '';
                const nm = execNombre(v);
                if (!nm || nm[1] !== '3') { toast('Eso no es una R3 (TQT-R3-V30-0001).', { kind: 'warn' }); return; }
                const res = await loteR3Agregar(Number(nm[2]), Number(nm[3]), nm[2]);
                if (res && !res.ok) toast(res.texto, { kind: 'warn' });
            });
            const body = h('div', { class: 'stack', style: 'gap:12px' },
                h('p', { class: 'hint', style: 'margin:0' }, 'La R3 no lleva MAC: queda programada al guardar su firmware. Escanea todas las del lote y aplica un solo firmware.'),
                h('div', { class: 'field' }, h('label', null, 'Agregar R3'), LR.inp),
                h('div', { class: 'row', style: 'justify-content:space-between' }, LR.info, h('button', { class: 'btn btn-sm btn-ghost', type: 'button', onclick: () => { LR.items.clear(); loteR3Pintar(); } }, 'Vaciar')),
                LR.lista,
                h('div', { class: 'field' }, h('label', null, 'Firmware para todas'), LR.fw.el));
            LR.hoja = T.sheet({
                title: 'Lote R3 · un firmware para todas', body,
                onClose: () => { LR.hoja = null; LR.lista = null; },
                actions: [
                    { label: 'Cerrar', kind: 'ghost', onClick: () => true },
                    { label: 'Aplicar firmware a todas', kind: 'primary', icon: 'check', onClick: async () => {
                        const fw = LR.fw.get(); const l = [...LR.items.values()];
                        if (!l.length) { toast('Escanea al menos una R3.', { kind: 'warn' }); return false; }
                        if (!fw) { toast('Elige el firmware.', { kind: 'warn' }); return false; }
                        const fallos = [];
                        for (const p of l) {
                            LR.info.textContent = `Guardando ${l.indexOf(p) + 1} de ${l.length}…`;
                            const res = await api(`/api/pcb/${p.id}/firmware`, { method: 'PUT', body: { firmware: fw } });
                            if (res.ok) { Object.assign(p, res.data || { firmware: fw }); LR.items.delete(p.id); }
                            else fallos.push(`${p.nombre}: ${res.error}`);
                        }
                        recordarFw('R3', fw);
                        if (!(S.fw.R3 || []).includes(fw)) cargarFw();
                        recargarSuave(); if (R3.cargado) cargarR3();
                        const ok = l.length - fallos.length;
                        pitar(!fallos.length);
                        toast(`${ok} R3 programada${ok === 1 ? '' : 's'} con firmware ${fw}${fallos.length ? ` · ${fallos.length} con error` : ''}`, { kind: fallos.length ? 'warn' : 'ok' });
                        loteR3Pintar();
                        if (fallos.length) { LR.info.textContent = fallos.slice(0, 3).join(' · '); return false; }
                        return true;
                    } },
                ],
            });
            loteR3Pintar();
        }

        async function escaneo(codigo) {
            const txt = String(codigo || '');
            const nm = execNombre(txt);
            const mac = extraerMac(txt);
            if (!nm && mac && mac.mac) {   // se leyó una MAC: va a la placa ubicada antes
                const r = S.ultFila;
                if (!r || r.saved || !r.tr.isConnected) return { ok: false, texto: 'Escanea primero el QR de la placa y después su MAC.' };
                if (r.esR3) return { ok: false, texto: `${r.pcb.nombre} es R3: no lleva MAC, solo firmware.` };
                r.inp.value = mac.mac; r.inp.dispatchEvent(new Event('input', { bubbles: true })); r.inp.focus();
                return { ok: true, texto: `MAC ${mac.mac.toLowerCase()} puesta en ${r.pcb.nombre}: revisa y pulsa Enter para guardar.` };
            }
            if (!nm) return null;   // no es una placa: lo resuelve la consola (ficha)
            const tipo = 'R' + nm[1], ver = Number(nm[2]), serie = Number(nm[3]);
            if (tipo === 'R3') return loteR3Agregar(ver, serie, nm[2]);
            const buscar = (V) => [...V.rows.values()].find((r) => r.pcb.tipo === tipo && Number(r.pcb.serie) === serie && Number(String(r.pcb.version).replace(/\D/g, '')) === ver);
            let r = buscar(vPend);
            if (r && !r.saved) { ubicar(vPend, 'pend', r); return { ok: true, texto: r.esR3 ? `${r.pcb.nombre} ubicada: elige su firmware en la consola (la R3 no lleva MAC).` : `${r.pcb.nombre} ubicada: captura su MAC en la consola.` }; }
            if (!vMac.cargado) await vMac.cargar();
            r = buscar(vMac);
            if (r) { ubicar(vMac, 'mac', r); return { ok: true, texto: r.esR3 ? `${r.pcb.nombre} ya está programada (firmware ${r.pcb.firmware}): puedes cambiarlo.` : `${r.pcb.nombre} ya tiene MAC ${String(r.orig || '').toLowerCase()}: puedes corregirla.` }; }
            return { ok: false, texto: `TQT-${tipo}-V${nm[2]}-${String(serie).padStart(4, '0')} no aparece en MAC y firmware (¿está registrada?).` };
        }

        return {
            escaneo,
            actualizar() { vPend.cargar(); if (vMac.cargado) vMac.cargar(); if (R3.cargado) cargarR3(); cargarFw(); },
            desmontar() {
                S.vivo = false;
                timers.forEach((t) => clearTimeout(t)); timers.clear();
                unsubs.forEach((u) => { try { if (typeof u === 'function') u(); } catch (e) { /* nada */ } });
                host.replaceChildren();
            },
        };
    }

    const def = { id: 'macs', titulo: 'MAC y firmware', icono: 'programar', grupo: 'operacion', orden: 40, montar };
    if (window.TQTEscritorio && window.TQTEscritorio.registrar) window.TQTEscritorio.registrar(def);
    else { (window.__TQTSecciones = window.__TQTSecciones || []).push(def); }
})();
