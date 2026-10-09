/**
 * sec_validacion.js - Pruebas y validación: prueba BLE de placas TQT-R2 a través del agente Windows de la laptop.
 * Sin Web Bluetooth ni ventanas emergentes: buscar/conectar/enviar son trabajos del agente (/api/validacion/ble/*).
 * El historial lo crea el backend; aquí solo se muestra. La dirección Bluetooth es la que reporta Windows.
 */
(function () {
    'use strict';
    const E = window.TQTEscritorio;
    function montar(host, ctx) {
        const { T, api, h, icon, util } = ctx; const toast = ctx.toast || T.toast;
        const S = { vivo: true, estaciones: [], station: '', conectado: false, nombre: '', address: '', ble: null, busy: '', buscando: false, devs: null, vistos: null,
            codigo: '', placa: null, tarjeta: null, log: [], items: [], total: 0, resumen: null, tq: null };
        const unsubs = []; const timers = new Set();
        // nombres de pantalla; al agente se siguen enviando exactamente PPON / POFF
        const NOMBRE = { PPON: 'ON · Meter perno', POFF: 'OFF · Sacar perno' };
        const nom = (c) => NOMBRE[c] || c;
        const esperar = (ms) => new Promise((ok) => { const t = setTimeout(() => { timers.delete(t); ok(); }, ms); timers.add(t); });

        const kpis = h('div', { class: 'val-kpis', role: 'group', 'aria-label': 'Resumen de pruebas de hoy' });
        const estado = h('div', { class: 'val-estado', role: 'status', 'aria-live': 'polite' });
        // v1.3.63: el Bluetooth lo usa el agente de la laptop; si no hay ninguno conectado se instala desde aquí mismo
        const btnInst = h('button', { class: 'btn', type: 'button', 'data-escribe': true, hidden: true, title: 'Descarga Instalar_TQT y ábrelo una vez en esta laptop', onclick: async () => {
            btnInst.disabled = true;
            try {
                const resp = await fetch('/api/stm32/stations/installer', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: 'Laptop pruebas BLE' }) });
                if (!resp.ok) { let m = 'Error ' + resp.status; try { m = (await resp.json()).detail || m; } catch (e) { /* nada */ } throw new Error(m); }
                const nombre = /filename="([^"]+)"/.exec(resp.headers.get('Content-Disposition') || '')?.[1] || 'Instalar_TQT.cmd';
                const u = URL.createObjectURL(await resp.blob()); const a = h('a', { href: u, download: nombre });
                document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(u), 10000);
                toast('Abre ' + nombre + ' una vez: la laptop aparecerá aquí en unos segundos.', { kind: 'ok', ms: 6000 });
            } catch (e) { toast('No se pudo descargar el instalador: ' + e.message, { kind: 'bad' }); }
            btnInst.disabled = false;
        } }, icon('download'), 'Instalar agente en esta laptop');
        const selEst = h('select', { class: 'input', id: 'valEst', 'aria-label': 'Laptop con Bluetooth', onchange: () => { S.station = selEst.value; S.devs = null; S.vistos = null; pintarTodo(); sondearEstado(); } });
        const btnBus = h('button', { class: 'btn btn-primary', type: 'button', 'data-escribe': true, onclick: () => buscar() });
        const btnDes = h('button', { class: 'btn', type: 'button', 'data-escribe': true, onclick: () => desconectar() }, icon('x'), 'Desconectar');
        const btnOn = h('button', { class: 'btn val-big val-on', type: 'button', 'data-escribe': true, onclick: () => enviar('PPON') }, icon('flash'), NOMBRE.PPON);
        const btnOff = h('button', { class: 'btn val-big val-off', type: 'button', 'data-escribe': true, onclick: () => enviar('POFF') }, icon('x'), NOMBRE.POFF);
        const logUl = h('ol', { class: 'val-log', 'aria-label': 'Registro de la sesión' });
        const histHost = h('div', { class: 'val-hist' });
        const avisos = h('div', { class: 'stack' });
        const lista = h('div', { class: 'val-devs', 'aria-live': 'polite' });
        const qInp = h('input', { class: 'input', id: 'valQ', type: 'search', placeholder: 'Buscar en historial', 'aria-label': 'Buscar en el historial', 'data-buscar': '1', autocomplete: 'off', oninput: () => { clearTimeout(S.tq); S.tq = setTimeout(cargarHist, 300); } });
        const codInp = h('input', { class: 'input', id: 'valCod', type: 'text', spellcheck: 'false', autocomplete: 'off', placeholder: 'TQT-R2-V30-0021 o 0021', 'aria-describedby': 'valCodAy',
            onkeydown: (e) => { if (e.key === 'Enter') { e.preventDefault(); fijarCodigo(codInp.value); } }, onchange: () => fijarCodigo(codInp.value) });
        const placaOut = h('div', { class: 'val-placa', 'aria-live': 'polite' });

        function agregarLog(txt, kind) {
            S.log.unshift({ t: T.hora(), txt, kind: kind || '' }); S.log = S.log.slice(0, 80);
            logUl.replaceChildren(...S.log.map((l) => h('li', { dataset: { k: l.kind } }, h('time', null, l.t), h('span', null, l.txt))));
        }
        const estOnline = () => S.estaciones.find((s) => s.id === S.station && s.online);
        function pintarEstado() {
            const libre = !S.busy && !S.buscando, ok = !!estOnline();
            estado.replaceChildren(S.conectado ? T.badge('Conectado · ' + (S.nombre || 'TQT'), 'ok', 'check') : T.badge(S.busy ? 'Trabajando…' : 'Desconectado', S.busy ? 'info' : '', S.busy ? 'clock' : 'circle'));
            btnBus.replaceChildren(S.buscando ? h('span', { class: 'val-spin', 'aria-hidden': 'true' }) : icon('wifi'), S.buscando ? 'Buscando placas… ~6 s' : 'Buscar placas');
            btnBus.disabled = !ok || !libre;
            btnDes.disabled = !ok || !libre || !S.conectado;
            btnOn.disabled = btnOff.disabled = !ok || !libre || !S.conectado;
            selEst.disabled = !libre;
        }
        function pintarEstaciones() {
            const hay = S.estaciones.some((s) => s.online);
            btnInst.hidden = hay;
            selEst.replaceChildren(h('option', { value: '' }, hay ? 'Elige una laptop' : 'Sin laptops conectadas'), ...S.estaciones.map((s) => h('option', { value: s.id }, s.name + (s.online ? ' · conectada' : ' · desconectada'))));
            selEst.value = S.station;
        }
        function pintarAvisos() {
            const a = [];
            if (S.estaciones.some((s) => s.online) && S.ble === false) a.push(T.banner('warn', 'alert', h('b', null, 'Bluetooth no disponible. '), 'La laptop no tiene Bluetooth listo o falta instalar bleak; reinstala el agente desde Programación › Instalar agente.'));
            avisos.replaceChildren(...a);
        }
        const barras = (rssi) => {
            const n = rssi == null ? 0 : rssi > -60 ? 4 : rssi > -70 ? 3 : rssi > -80 ? 2 : 1;
            return h('span', { class: 'val-rssi', title: rssi == null ? 'Sin señal' : rssi + ' dBm' },
                h('span', { class: 'val-bars', 'aria-hidden': 'true' }, ...[1, 2, 3, 4].map((i) => h('i', { class: i <= n ? 'on' : '' }))), h('span', { class: 'mono' }, rssi == null ? '—' : rssi + ' dBm'));
        };
        function pintarLista() {
            const ocupado = !!S.busy || S.buscando;
            if (S.devs === null && !S.conectado) { lista.replaceChildren(h('p', { class: 'hint', style: 'margin:0' }, 'Pulsa «Buscar placas» para ver las placas TQT cercanas a la laptop.')); return; }
            let devs = S.devs || [];
            if (S.conectado && S.address && !devs.some((d) => d.address === S.address)) devs = [{ nombre: S.nombre, address: S.address, rssi: null }, ...devs];
            if (!devs.length) { lista.replaceChildren(T.empty ? T.empty('wifi', 'No se encontraron placas TQT. Enciéndela y vuelve a buscar.') : h('p', { class: 'hint' }, 'No se encontraron placas TQT. Enciéndela y vuelve a buscar.')); return; }
            lista.replaceChildren(...devs.map((d) => {
                const act = S.conectado && d.address === S.address;
                return h('div', { class: 'prog-item val-dev', 'aria-pressed': String(act) },
                    h('span', { class: 'nm' }, h('b', null, d.nombre || 'TQT'), h('span', { class: 'mono val-addr' }, d.address || '')), barras(d.rssi),
                    act ? h('button', { class: 'btn btn-sm', type: 'button', 'data-escribe': true, disabled: ocupado, onclick: () => desconectar() }, 'Desconectar')
                        : h('button', { class: 'btn btn-sm btn-primary', type: 'button', 'data-escribe': true, disabled: ocupado || S.conectado, onclick: () => conectar(d) }, 'Conectar'));
            }));
        }
        function pintarTodo() { pintarEstaciones(); pintarAvisos(); pintarEstado(); pintarLista(); }
        function pintarPlaca() {
            if (!S.codigo) { placaOut.replaceChildren(h('span', { class: 'hint' }, 'Sin placa vinculada: la prueba se guarda solo con el nombre BLE.')); return; }
            const p = S.placa, t = S.tarjeta;
            if (!p && !t) { placaOut.replaceChildren(T.badge('No reconocida: ' + S.codigo, 'warn', 'alert')); return; }
            placaOut.replaceChildren(p ? T.tipoChip(p.tipo) : null, h('b', { class: 'mono' }, p ? p.nombre : ''), t ? h('span', { class: 'hint' }, 'Tarjeta ' + t.id_tarjeta_num) : null);
        }
        async function fijarCodigo(c) {
            c = String(c || '').trim(); S.codigo = c; codInp.value = c;
            S.placa = S.tarjeta = null;
            if (c) {
                const r = await api('/api/consulta?codigo=' + encodeURIComponent(c));
                if (!S.vivo) return { ok: false, texto: '' };
                if (r.ok && r.data) {
                    const d = r.data; S.tarjeta = d.tarjeta || null;
                    S.placa = d.pcb || (d.tarjeta && (d.tarjeta.r2 || d.tarjeta.r1)) || null;
                    if (S.placa && !S.placa.tipo) S.placa.tipo = 'R2';
                }
            }
            pintarPlaca(); cargarHist();
            return { ok: !!(S.placa || S.tarjeta), texto: S.placa ? 'Placa vinculada: ' + S.placa.nombre : (S.tarjeta ? 'Tarjeta ' + S.tarjeta.id_tarjeta_num : 'Código no reconocido') };
        }

        // --- estaciones (laptops con el agente) ---
        async function cargarEstaciones() {
            const r = await api('/api/stm32/stations'); if (!S.vivo) return;
            if (r.ok && Array.isArray(r.data)) {
                S.estaciones = r.data;
                if (!S.estaciones.some((s) => s.id === S.station)) S.station = '';
                if (!S.station) { const on = S.estaciones.filter((s) => s.online); if (on.length === 1) { S.station = on[0].id; sondearEstado(); } }
            } else S.estaciones = [];
            pintarEstaciones(); pintarAvisos(); pintarEstado(); pintarLista();
        }
        // --- trabajos del agente: POST + sondeo cada 500 ms, máx. 20 s ---
        async function trabajo(accion, extra) {
            const cuerpo = Object.assign({ station_id: S.station, accion }, extra || {});
            if (S.codigo) cuerpo.codigo = S.codigo;
            const r = await api('/api/validacion/ble/trabajos', { method: 'POST', body: cuerpo });
            if (!r.ok || !r.data) return { ok: false, error: r.error || 'No se pudo enviar el trabajo a la laptop.' };
            const id = r.data.id; const fin = Date.now() + 20000;
            while (S.vivo && Date.now() < fin) {
                await esperar(500); if (!S.vivo) break;
                const q = await api('/api/validacion/ble/trabajos/' + encodeURIComponent(id));
                if (!q.ok || !q.data) continue;
                const d = q.data;
                if (d.estado === 'ok') return { ok: true, resultado: d.resultado || {} };
                if (d.estado === 'error') return { ok: false, error: d.error || 'La laptop reportó un error.' };
            }
            return { ok: false, error: S.vivo ? 'La laptop no respondió a tiempo (20 s).' : '' };
        }
        async function correr(accion, extra, antes, despues) {
            if (!S.station || S.busy || S.buscando) return;
            if (accion === 'escanear') S.buscando = true; else S.busy = accion;
            if (antes) agregarLog(antes);
            pintarEstado(); pintarLista();
            const r = await trabajo(accion, extra);
            if (!S.vivo) return;
            S.busy = ''; S.buscando = false;
            if (r.ok) despues(r.resultado); else agregarLog(r.error, 'bad');
            pintarTodo(); recargarSuave();
        }
        function buscar() {
            correr('escanear', null, 'Buscando placas TQT cerca de la laptop…', (res) => {
                S.devs = (res.dispositivos || []).filter((d) => /TQT/i.test(d.nombre || '') || !d.nombre).sort((a, b) => (b.rssi || -999) - (a.rssi || -999));
                agregarLog(S.devs.length ? 'Encontradas ' + S.devs.length + ' placa(s).' : 'No se encontraron placas TQT.', S.devs.length ? 'ok' : 'warn');
            });
        }
        function conectar(d) {
            correr('conectar', { address: d.address }, 'Conectando a ' + (d.nombre || d.address) + '…', (res) => {
                S.conectado = !!res.conectado; S.nombre = res.nombre || d.nombre || ''; S.address = res.address || d.address || '';
                agregarLog(S.conectado ? 'Conectado a ' + (S.nombre || 'dispositivo') + '.' : 'No se pudo conectar.', S.conectado ? 'ok' : 'bad');
            });
        }
        function desconectar() {
            correr('desconectar', null, 'Desconectando…', () => { S.conectado = false; S.nombre = S.address = ''; agregarLog('Desconectado.', 'warn'); });
        }
        function enviar(cmd) {
            if (!S.conectado) return;
            correr('enviar', { comando: cmd, address: S.address || undefined }, '→ ' + nom(cmd), (res) => { agregarLog('✓ ' + nom(cmd) + (res.respuesta ? ' · ← ' + res.respuesta : ''), 'ok'); });
        }
        // --- estado del agente: sondeo cada 2 s + WS BLE_ESTADO ---
        function aplicarConexion(d) {
            const antes = S.conectado + '|' + S.address;
            S.conectado = !!d.conectado; S.nombre = d.conectado ? (d.nombre || '') : ''; S.address = d.conectado ? (d.address || '') : '';
            return antes !== S.conectado + '|' + S.address;
        }
        let sondeando = false;
        async function sondearEstado() {
            if (!S.station || sondeando) return; sondeando = true;
            const r = await api('/api/validacion/ble/estado?station_id=' + encodeURIComponent(S.station)); sondeando = false;
            if (!S.vivo || !r.ok || !r.data) return;
            const d = r.data; S.ble = d.ble_disponible !== false;
            const cambio = aplicarConexion(d);
            const evs = Array.isArray(d.eventos) ? d.eventos : [];
            const clave = (e) => String(e.t) + '|' + (e.texto || '');
            if (S.vistos === null) S.vistos = new Set(evs.map(clave));
            else evs.filter((e) => !S.vistos.has(clave(e))).sort((a, b) => (a.t > b.t ? 1 : -1)).forEach((e) => { S.vistos.add(clave(e)); agregarLog('← ' + (e.texto || e.tipo), e.tipo === 'error' ? 'bad' : 'rx'); });
            pintarAvisos(); pintarEstado(); if (cambio && !S.busy && !S.buscando) pintarLista();
        }

        function pintarKpis() {
            const r = S.resumen;
            const k = (n, t, kind) => h('div', { class: 'val-kpi', dataset: { k: kind || '' } }, h('b', null, r ? String(n == null ? 0 : n) : '—'), h('span', null, t));
            const u = r && r.ultima ? (typeof r.ultima === 'string' ? r.ultima : (r.ultima.creado_en || r.ultima.creado)) : null;
            kpis.replaceChildren(k(r && r.hoy, 'Pruebas hoy'), k(r && r.ok_hoy, 'OK', 'ok'), k(r && r.error_hoy, 'Errores', 'bad'), k(r && r.dispositivos_hoy, 'Dispositivos'),
                h('div', { class: 'val-kpi' }, h('b', { class: 'val-ult' }, u ? util.fecha(u) : '—'), h('span', null, 'Última prueba')));
        }
        async function cargarResumen() { const r = await api('/api/validacion/resumen'); if (S.vivo && r.ok) { S.resumen = r.data; pintarKpis(); } }
        async function cargarHist() {
            const p = new URLSearchParams({ limit: '100' });
            if (qInp.value.trim()) p.set('q', qInp.value.trim());
            if (S.tarjeta) p.set('tarjeta_id', S.tarjeta.id); else if (S.placa && S.placa.id) p.set('pcb_id', S.placa.id);
            const r = await api('/api/validacion/registros?' + p);
            if (!S.vivo) return;
            if (!r.ok) { histHost.replaceChildren(T.banner('bad', 'alert', 'No se pudo cargar el historial. ', r.error || 'Revisa la conexión.')); return; }
            S.items = r.data.items || []; S.total = r.data.total || S.items.length;
            const cols = [
                { id: 'creado_en', titulo: 'Hora', cel: (f) => util.fecha(f.creado_en || f.creado) },
                { id: 'dispositivo', titulo: 'Dispositivo', cel: (f) => h('span', { class: 'mono' }, f.dispositivo || '—') },
                { id: 'placa', titulo: 'Placa / tarjeta', cel: (f) => h('span', { class: 'val-pl' }, f.pcb ? T.tipoChip(f.pcb.tipo) : null, f.pcb ? h('span', { class: 'mono' }, f.pcb.nombre) : null, f.tarjeta ? h('span', { class: 'hint' }, '#' + f.tarjeta.id_tarjeta_num) : null, !f.pcb && !f.tarjeta ? '—' : null) },
                { id: 'comando', titulo: 'Comando', cel: (f) => h('span', { class: 'mono' }, nom(f.comando)) },
                { id: 'resultado', titulo: 'Resultado', cel: (f) => (f.resultado === 'ok' ? T.badge('OK', 'ok', 'check') : T.badge('Error', 'bad', 'alert')) },
                { id: 'respuesta', titulo: 'Respuesta', cel: (f) => h('span', { class: 'mono' }, f.respuesta || f.detalle || '—') },
            ];
            util.pintarTabla(histHost, { cols, rows: S.items, key: (f) => f.id, vacio: { icono: 'list', titulo: 'Sin pruebas registradas', texto: 'Conecta una placa y envía ON (meter perno) u OFF (sacar perno).' } });
            if (S.total > S.items.length) histHost.append(h('p', { class: 'hint' }, `Mostrando ${S.items.length} de ${S.total}.`));
        }
        let tRec = null;
        function recargarSuave() { clearTimeout(tRec); tRec = setTimeout(() => { timers.delete(tRec); if (S.vivo) { cargarResumen(); cargarHist(); } }, 600); timers.add(tRec); }

        const dl = h('a', { class: 'btn', href: '/api/validacion/tester.zip', download: '' }, icon('download'), 'Descargar tester Windows');

        const panelPrueba = h('section', { class: 'prog-panel', 'aria-labelledby': 'valT1' },
            h('h2', { id: 'valT1' }, 'Prueba BLE'),
            h('div', { class: 'field' }, h('label', { for: 'valCod' }, 'Tarjeta o placa'), codInp,
                h('p', { class: 'hint', id: 'valCodAy' }, 'Opcional. Escribe o escanea el código con el celular para vincular la prueba.'), placaOut),
            h('div', { class: 'field' }, h('label', { for: 'valEst' }, 'Laptop con Bluetooth'), h('div', { class: 'row' }, selEst, btnBus, btnInst)),
            lista,
            h('div', { class: 'row', style: 'margin-top:10px' }, estado, h('div', { class: 'grow' }), btnDes, dl),
            h('div', { class: 'val-cmds' }, btnOn, btnOff));
        const panelLog = h('section', { class: 'prog-panel', 'aria-labelledby': 'valT2' }, h('h2', { id: 'valT2' }, 'Registro de la sesión'), logUl);
        const panelHist = h('section', { class: 'prog-panel val-histp', 'aria-labelledby': 'valT3' },
            h('div', { class: 'row' }, h('h2', { id: 'valT3' }, 'Historial de pruebas'), h('div', { class: 'grow' }), qInp,
                h('button', { class: 'btn btn-ghost', type: 'button', 'aria-label': 'Actualizar historial', onclick: () => { cargarResumen(); cargarHist(); } }, icon('refresh'))), histHost);

        host.append(h('div', { class: 'val' }, avisos, kpis, h('div', { class: 'prog-wrap val-wrap' }, panelPrueba, panelLog), panelHist));
        agregarLog('Listo. Elige la laptop y pulsa «Buscar placas».');
        pintarTodo(); pintarPlaca(); pintarKpis(); cargarResumen(); cargarHist(); cargarEstaciones();
        const tEst = setInterval(() => { if (S.vivo) cargarEstaciones(); }, 5000);
        const tBle = setInterval(() => { if (S.vivo) sondearEstado(); }, 2000);
        const wsc = ctx.ws || (T.ws && T.ws());
        if (wsc && wsc.on) {
            unsubs.push(wsc.on('VALIDACION_BLE', recargarSuave));
            unsubs.push(wsc.on('BLE_ESTADO', (m) => {
                const d = (m && m.data) || m || {};
                if (!S.vivo || (d.station_id && d.station_id !== S.station)) return;
                if (aplicarConexion(d)) { agregarLog(S.conectado ? 'Conectado a ' + (S.nombre || 'dispositivo') + '.' : 'El dispositivo se desconectó.', S.conectado ? 'ok' : 'warn'); pintarEstado(); pintarLista(); }
            }));
        }
        const ini = ctx.params && ctx.params().get('codigo'); if (ini) fijarCodigo(ini);

        return {
            actualizar() { cargarResumen(); cargarHist(); },
            escaneo(codigo) { return fijarCodigo(codigo); },
            parametros(p) { const c = p.get('codigo'); if (c && c !== S.codigo) fijarCodigo(c); },
            desmontar() {
                S.vivo = false; clearInterval(tEst); clearInterval(tBle);
                timers.forEach((t) => clearTimeout(t)); timers.clear(); clearTimeout(S.tq);
                unsubs.forEach((u) => { try { u(); } catch (e) { /* nada */ } });
                host.replaceChildren();
            },
        };
    }
    const def = { id: 'validacion', titulo: 'Pruebas y validación', icono: 'wifi', grupo: 'operacion', orden: 60, montar };
    if (E && E.registrar) E.registrar(def); else { (window.__TQTSecciones = window.__TQTSecciones || []).push(def); }
})();
