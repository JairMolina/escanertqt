/**
 * sec_validacion.js - Pruebas y validación: prueba BLE de placas TQT-R2 a través del agente Windows de la laptop.
 * Sin Web Bluetooth ni ventanas emergentes: buscar/conectar/enviar son trabajos del agente (/api/validacion/ble/*).
 * v1.3.64: el código llega por el Botón de escaneo (escaneo(codigo)); la ficha compara BD vs Bluetooth y permite validar (auto/manual).
 * La dirección Bluetooth es la que reporta Windows.
 */
(function () {
    'use strict';
    const E = window.TQTEscritorio;
    function montar(host, ctx) {
        const { T, api, h, icon, util } = ctx; const toast = ctx.toast || T.toast;
        const S = { vivo: true, estaciones: [], coincide: true, station: '', conectado: false, nombre: '', address: '', ble: null, busy: '', buscando: false, devs: null, vistos: null,
            codigo: '', cmp: null, noRec: false, cargandoCmp: false, validando: '', msgVal: null, log: [], resumen: null, seqCmp: 0 };
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
                const sid = /([0-9a-f]{24})/i.exec(nombre)?.[1]; if (sid) guardarMia(sid);
                const u = URL.createObjectURL(await resp.blob()); const a = h('a', { href: u, download: nombre });
                document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(u), 10000);
                toast('Abre ' + nombre + ' una vez: la laptop aparecerá aquí en unos segundos.', { kind: 'ok', ms: 6000 });
            } catch (e) { toast('No se pudo descargar el instalador: ' + e.message, { kind: 'bad' }); }
            btnInst.disabled = false;
        } }, icon('download'), 'Instalar agente en esta laptop');
        const selEst = h('select', { class: 'input', id: 'valEst', 'aria-labelledby': 'valEstL', onchange: () => { S.station = selEst.value; S.devs = null; S.vistos = null; pintarTodo(); sondearEstado(); comparar(); } });
        const estHost = h('div', { class: 'row', 'aria-live': 'polite' });
        const btnBus = h('button', { class: 'btn btn-primary', type: 'button', 'data-escribe': true, onclick: () => buscar() });
        const btnDes = h('button', { class: 'btn', type: 'button', 'data-escribe': true, onclick: () => desconectar() }, icon('x'), 'Desconectar');
        const btnOn = h('button', { class: 'btn val-big val-on', type: 'button', 'data-escribe': true, onclick: () => enviar('PPON') }, icon('flash'), NOMBRE.PPON);
        const btnOff = h('button', { class: 'btn val-big val-off', type: 'button', 'data-escribe': true, onclick: () => enviar('POFF') }, icon('x'), NOMBRE.POFF);
        const logUl = h('ol', { class: 'val-log', 'aria-label': 'Registro de la sesión' });
         const avisos = h('div', { class: 'stack' });
        const estHostAy = h('div', { class: 'hint val-lapay', hidden: true });
        // v1.3.66: «esta laptop» recordada en este navegador (al instalar el agente o al confirmarla)
        const LS_MIA = 'tqt.val.laptop';
        const leerMia = () => { try { return localStorage.getItem(LS_MIA) || ''; } catch (e) { return ''; } };
        function guardarMia(id) { try { localStorage.setItem(LS_MIA, id); } catch (e) { /* nada */ } }
        const lista = h('div', { class: 'val-devs', 'aria-live': 'polite' });
        function agregarLog(txt, kind) {
            if (txt != null) { S.log.unshift({ t: T.hora(), txt, kind: kind || '', u: S.yo }); S.log = S.log.slice(0, 80); }
            // v1.3.65: cada línea indica quién probó (usuario · ID)
            logUl.replaceChildren(...S.log.map((l) => h('li', { dataset: { k: l.kind } }, h('time', null, l.t), h('span', null, l.txt),
                l.u ? h('small', { class: 'val-quien' }, l.u.email + (l.u.id != null ? ' · ID ' + l.u.id : '')) : null)));
        }
        const estOnline = () => S.estaciones.find((s) => s.id === S.station && s.online !== false);
        function pintarEstado() {
            const libre = !S.busy && !S.buscando, ok = !!estOnline();
            estado.replaceChildren(S.conectado ? T.badge('Conectado · ' + (S.nombre || 'TQT'), 'ok', 'check') : T.badge(S.busy ? 'Trabajando…' : 'Desconectado', S.busy ? 'info' : '', S.busy ? 'clock' : 'circle'));
            btnBus.replaceChildren(S.buscando ? h('span', { class: 'val-spin', 'aria-hidden': 'true' }) : icon('wifi'), S.buscando ? 'Buscando placas… ~6 s' : 'Buscar placas');
            btnBus.disabled = !ok || !libre;
            btnDes.disabled = !ok || !libre || !S.conectado;
            btnOn.disabled = btnOff.disabled = !ok || !libre || !S.conectado;
            selEst.disabled = !libre;
            pintarFicha();
        }
        function pintarEstaciones() {
            const hay = S.estaciones.length > 0;
            btnInst.hidden = hay;
            const bt = S.ble === false ? 'Bluetooth no disponible' : (S.ble ? 'Bluetooth listo' : 'comprobando Bluetooth…');
            const nodes = [];
            if (!hay) nodes.push(h('p', { class: 'hint', style: 'margin:0' }, 'No hay laptops con el agente conectadas.'), btnBus, btnInst);
            else if (S.estaciones.length === 1) nodes.push(h('p', { class: 'val-lap', style: 'margin:0' }, 'Esta laptop: ', h('b', null, S.estaciones[0].name), ' · ' + bt), btnBus, btnInst);
            else {
                selEst.replaceChildren(h('option', { value: '' }, 'Elige una laptop'), ...S.estaciones.map((s) => h('option', { value: s.id }, s.name)));
                selEst.value = S.station;
                nodes.push(selEst, btnBus, btnInst);
            }
            estHost.replaceChildren(...nodes);
            const st = S.estaciones.find((x) => x.id === S.station) || (S.estaciones.length === 1 ? S.estaciones[0] : null);
            const avisar = hay && !S.coincide && st;
            estHostAy.replaceChildren(...(avisar ? [
                h('span', null, 'No se pudo confirmar que «' + st.name + '» sea esta laptop' + (S.ip || st.ip ? ' (IP del navegador ' + (S.ip || '—') + ' · IP del agente ' + (st.ip || '—') + ')' : '') +
                    '. Si la placa está junto a otra laptop, instala el agente en ella. '),
                h('button', { class: 'btn btn-ghost', type: 'button', onclick: () => { guardarMia(st.id); S.station = st.id; S.coincide = true; pintarEstaciones(); } }, 'Sí, es esta laptop')] : []));
            estHostAy.hidden = !avisar;
        }
        function pintarAvisos() {
            const a = [];
            if (S.estaciones.length && S.ble === false) a.push(T.banner('warn', 'alert', h('b', null, 'Bluetooth no disponible. '), 'La laptop no tiene Bluetooth listo o falta instalar bleak; reinstala el agente desde Programación › Instalar agente.'));
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
            if (!devs.length) {
                const lap = (S.estaciones.find((x) => x.id === S.station) || {}).name || 'La laptop';
                lista.replaceChildren(h('div', { class: 'val-vacio' }, h('b', null, '«' + lap + '» no encontró placas TQT por Bluetooth.'),
                    h('ul', { class: 'val-tips' }, h('li', null, 'La placa debe estar encendida y cerca de esa laptop (no de esta, si son distintas).'),
                        h('li', null, 'Que no esté conectada al celular ni a otra app Bluetooth: mientras está conectada no se anuncia.'),
                        h('li', null, 'Espera 5 s tras encenderla y pulsa «Buscar placas» otra vez.'))));
                return;
            }
            lista.replaceChildren(...devs.map((d) => {
                const act = S.conectado && d.address === S.address;
                return h('div', { class: 'prog-item val-dev', 'aria-pressed': String(act) },
                    h('span', { class: 'nm' }, h('b', null, d.nombre || 'TQT'), h('span', { class: 'mono val-addr' }, d.address || '')), barras(d.rssi),
                    act ? h('button', { class: 'btn btn-sm', type: 'button', 'data-escribe': true, disabled: ocupado, onclick: () => desconectar() }, 'Desconectar')
                        : h('button', { class: 'btn btn-sm btn-primary', type: 'button', 'data-escribe': true, disabled: ocupado || S.conectado, onclick: () => conectar(d) }, 'Conectar'));
            }));
        }
        function pintarTodo() { pintarEstaciones(); pintarAvisos(); pintarEstado(); pintarLista(); }
        // --- ficha «Tarjeta escaneada»: BD vs Bluetooth ---
        const fichaHost = h('div', { class: 'val-ficha' });
        const msgHost = h('div', { class: 'stack', role: 'alert' });
        const btnAuto = h('button', { class: 'btn btn-primary', type: 'button', 'data-escribe': true, onclick: () => validarAuto() }, icon('check'), 'Validar automático');
        const btnMan = h('button', { class: 'btn', type: 'button', 'data-escribe': true, onclick: () => validarManual() }, icon('edit'), 'Validar manual');
        const checksFallo = (cs) => (cs || []).filter((c) => c.ok === false);
        const lineaCheck = (c) => h('li', null, h('b', null, c.etiqueta || c.campo), ': esperado ', h('span', { class: 'mono' }, c.esperado == null ? '—' : String(c.esperado)), ', Bluetooth ', h('span', { class: 'mono' }, c.actual == null ? '—' : String(c.actual)), c.detalle ? ' (' + c.detalle + ')' : '');
        const modoTxt = (m) => (m === 'manual' ? 'manual' : 'automático');
        function celdaEstado(c) {
            if (c.ok === true) return T.badge('Coincide', 'ok', 'check');
            if (c.ok === false) return T.badge('Difiere', 'bad', 'x');
            return h('span', { class: 'hint' }, 'sin dato');
        }
        function pintarFicha() {
            const c = S.cmp, libre = !S.validando;
            btnAuto.disabled = btnMan.disabled = !c || !c.tarjeta || !libre || !S.station;
            btnAuto.replaceChildren(S.validando === 'auto' ? h('span', { class: 'val-spin', 'aria-hidden': 'true' }) : icon('check'), S.validando === 'auto' ? 'Validando…' : 'Validar automático');
            if (!S.codigo) {
                fichaHost.replaceChildren(h('p', { class: 'val-vacio' }, 'Pulsa «Botón de escaneo» en la cabecera y escanea la tarjeta con el celular.'));
                return;
            }
            if (S.noRec) { fichaHost.replaceChildren(T.banner('warn', 'alert', h('b', null, 'Código no reconocido: '), h('span', { class: 'mono' }, S.codigo), '. Escanea de nuevo la tarjeta.')); return; }
            if (!c) { fichaHost.replaceChildren(h('p', { class: 'hint' }, S.cargandoCmp ? 'Comparando ' + S.codigo + '…' : 'No se pudo comparar. Se reintentará al cambiar la conexión Bluetooth.')); return; }
            const t = c.tarjeta;
            const cab = h('div', { class: 'row val-cab' }, h('b', { class: 'mono' }, t ? 'Tarjeta ' + t.id_tarjeta_num : c.codigo), t && t.estado ? T.badge(t.estado, '') : null,
                c.placa_probada ? h('span', { class: 'hint' }, 'Placa en prueba: ' + c.placa_probada) : null, h('span', { class: 'mono hint' }, c.codigo));
            const placas = (c.placas || []).map((p) => h('li', { class: 'val-pl' }, T.tipoChip(p.tipo), h('b', { class: 'mono' }, p.nombre || '—'),
                h('span', { class: 'hint mono' }, 'MAC ' + (p.mac || '—')), h('span', { class: 'hint mono' }, 'FW ' + (p.firmware || '—')), p.nombre_ble ? h('span', { class: 'hint mono' }, 'BLE ' + p.nombre_ble) : null));
            const ble = c.ble && c.ble.conectado ? T.badge('Bluetooth: ' + (c.ble.nombre || 'conectado') + (c.ble.address ? ' · ' + c.ble.address : ''), 'ok', 'check') : T.badge('Bluetooth sin conexión: conecta la placa para comparar', 'warn', 'alert');
            const filas = (c.checks || []).map((k) => h('tr', { dataset: { k: k.ok === true ? 'ok' : k.ok === false ? 'bad' : '' } },
                h('th', { scope: 'row' }, k.etiqueta || k.campo), h('td', { class: 'mono' }, k.esperado == null || k.esperado === '' ? '—' : String(k.esperado)),
                h('td', { class: 'mono' }, k.actual == null || k.actual === '' ? '—' : String(k.actual)), h('td', null, celdaEstado(k), k.ok === false && k.detalle ? h('span', { class: 'hint val-det' }, k.detalle) : null)));
            const tabla = filas.length ? h('div', { class: 'val-tabla' }, h('table', { class: 'val-cmp' }, h('caption', { class: 'sr-only' }, 'Comparación entre la base de datos y el Bluetooth'),
                h('thead', null, h('tr', null, h('th', { scope: 'col' }, 'Campo'), h('th', { scope: 'col' }, 'En base de datos'), h('th', { scope: 'col' }, 'En Bluetooth'), h('th', { scope: 'col' }, 'Estado'))), h('tbody', null, ...filas))) : null;
            const v = c.validada;
            const estadoVal = v ? h('div', { class: 'row' }, T.badge('Validada · ' + modoTxt(v.modo), 'ok', 'check'), h('span', { class: 'hint' }, (v.operador ? 'por ' + v.operador + ' · ' : '') + (v.creado_en ? util.fecha(v.creado_en) : '')))
                : (c.ok ? T.badge('Todo coincide: lista para validar', 'ok', 'check') : null);
            fichaHost.replaceChildren(cab, placas.length ? h('ul', { class: 'val-placas' }, ...placas) : null, ble, tabla, estadoVal, msgHost, h('div', { class: 'row val-acc' }, btnAuto, btnMan));
        }
        let tCmp = null;
        async function comparar() {
            if (!S.codigo) { S.cmp = null; S.noRec = false; pintarFicha(); return false; }
            const mi = ++S.seqCmp; S.cargandoCmp = true;
            const r = await api('/api/validacion/comparar?codigo=' + encodeURIComponent(S.codigo) + '&station_id=' + encodeURIComponent(S.station || ''));
            if (!S.vivo || mi !== S.seqCmp) return false;
            S.cargandoCmp = false;
            if (r.status === 404) { S.cmp = null; S.noRec = true; } else if (r.ok && r.data) { S.cmp = r.data; S.noRec = false; }
            pintarFicha();
            return !!(r.ok && r.data && r.data.tarjeta);
        }
        function compararSuave() { clearTimeout(tCmp); tCmp = setTimeout(() => { timers.delete(tCmp); if (S.vivo && S.codigo) comparar(); }, 400); timers.add(tCmp); }
        async function fijarCodigo(c) {
            c = String(c || '').trim(); S.codigo = c; S.cmp = null; S.noRec = false; msgHost.replaceChildren();
            const ok = await comparar();
            if (!S.vivo) return { ok: false, texto: '' };
            const t = S.cmp && S.cmp.tarjeta;
            return { ok, texto: t ? 'Tarjeta ' + t.id_tarjeta_num : 'Código no reconocido' };
        }
        async function validar(modo, motivo) {
            if (S.validando || !S.codigo) return false;
            S.validando = modo; msgHost.replaceChildren(); pintarFicha();
            const body = { codigo: S.codigo, station_id: S.station || undefined, modo };
            if (motivo) body.motivo = motivo;
            const r = await api('/api/validacion/validar', { method: 'POST', body, timeout: 15000 });
            if (!S.vivo) return false;
            S.validando = '';
            if (r.ok) {
                toast('Tarjeta validada · ' + modoTxt(modo), { kind: 'ok' }); agregarLog('✓ Tarjeta validada (' + modoTxt(modo) + ').', 'ok');
                await comparar(); cargarResumen(); return true;
            }
            const d = r.data || {}; const dd = d.detail && typeof d.detail === 'object' ? d.detail : {};
            const fallos = checksFallo(d.checks || dd.checks);
            if (r.status === 409) {
                msgHost.replaceChildren(T.banner('bad', 'alert', h('b', null, 'No se pudo validar automáticamente. '), typeof d.detail === 'string' ? d.detail : (dd.mensaje || 'Hay diferencias entre la base de datos y el Bluetooth.'),
                    fallos.length ? h('ul', { class: 'val-fallos' }, ...fallos.map(lineaCheck)) : null));
                comparar();
            } else msgHost.replaceChildren(T.banner('bad', 'alert', h('b', null, 'No se pudo validar. '), r.error || 'Intenta de nuevo.'));
            pintarFicha();
            return false;
        }
        function validarAuto() { validar('auto'); }
        function validarManual() {
            const c = S.cmp; if (!c || !c.tarjeta) return;
            const dif = checksFallo(c.checks), sin = (c.checks || []).filter((k) => k.ok == null);
            const motivo = h('textarea', { class: 'input', id: 'valMotivo', rows: 3, maxlength: 300, placeholder: 'Ej.: la placa ya estaba probada en otra laptop' });
            const body = [
                dif.length ? h('div', null, h('p', { style: 'margin:0 0 6px' }, h('b', null, 'Discrepancias (' + dif.length + ')')), h('ul', { class: 'val-fallos' }, ...dif.map(lineaCheck)))
                    : h('p', { class: 'hint', style: 'margin:0' }, 'No hay discrepancias confirmadas.'),
                sin.length ? h('p', { class: 'hint', style: 'margin:0' }, 'Sin dato: ' + sin.map((k) => k.etiqueta || k.campo).join(', ') + '.') : null,
                h('div', { class: 'field' }, h('label', { for: 'valMotivo' }, 'Motivo (opcional)'), motivo),
            ];
            T.sheet({ title: 'Validar manualmente' + (c.tarjeta.id_tarjeta_num ? ' · tarjeta ' + c.tarjeta.id_tarjeta_num : ''), body, focus: false, actions: [
                { label: 'Cancelar', kind: 'ghost', onClick: () => true },
                { label: 'Confirmar validación manual', kind: 'primary', onClick: async () => ((await validar('manual', motivo.value.trim())) ? true : false) },
            ] });
        }

        // --- estaciones (laptops con el agente) ---
        async function cargarEstaciones() {
            const r = await api('/api/validacion/estaciones'); if (!S.vivo) return;
            const antes = S.station;
            if (r.ok && r.data && Array.isArray(r.data.estaciones)) {
                S.estaciones = r.data.estaciones; S.coincide = r.data.coincide !== false; S.ip = r.data.ip || '';
                const mia = leerMia();
                if (!S.coincide && mia && S.estaciones.some((x) => x.id === mia)) {   // la recordada en este navegador
                    S.estaciones = S.estaciones.filter((x) => x.id === mia); S.coincide = true;
                }
                if (!S.estaciones.some((s) => s.id === S.station)) S.station = '';
                if (!S.station && S.estaciones.length === 1) { S.station = S.estaciones[0].id; sondearEstado(); }
            } else { S.estaciones = []; S.coincide = true; S.station = ''; }
            pintarEstaciones(); pintarAvisos(); pintarEstado(); pintarLista();
            if (S.station !== antes) compararSuave();
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
            pintarTodo(); recargarSuave(); if (r.ok) compararSuave();
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
            pintarAvisos(); pintarEstaciones(); pintarEstado(); if (cambio) { compararSuave(); if (!S.busy && !S.buscando) pintarLista(); }
        }

        function pintarKpis() {
            const r = S.resumen;
            const k = (n, t, kind) => h('div', { class: 'val-kpi', dataset: { k: kind || '' } }, h('b', null, r ? String(n == null ? 0 : n) : '—'), h('span', null, t));
            const u = r && r.ultima ? (typeof r.ultima === 'string' ? r.ultima : (r.ultima.creado_en || r.ultima.creado)) : null;
            kpis.replaceChildren(k(r && r.hoy, 'Pruebas hoy'), k(r && r.ok_hoy, 'OK', 'ok'), k(r && r.error_hoy, 'Errores', 'bad'), k(r && r.dispositivos_hoy, 'Dispositivos'),
                h('div', { class: 'val-kpi' }, h('b', { class: 'val-ult' }, u ? util.fecha(u) : '—'), h('span', null, 'Última prueba')));
        }
        async function cargarResumen() { const r = await api('/api/validacion/resumen'); if (S.vivo && r.ok) { S.resumen = r.data; pintarKpis(); } }
        let tRec = null;
        function recargarSuave() { clearTimeout(tRec); tRec = setTimeout(() => { timers.delete(tRec); if (S.vivo) { cargarResumen(); cargarValidadas(); if (S.codigo) comparar(); } }, 600); timers.add(tRec); }

        // --- v1.3.65: placas validadas (auto/manual) → confirmar sus tarjetas como «Validada» ---
        const PV = { items: [], sel: new Set(), enviando: false };
        const quien = (email, id) => (email || '—') + (id != null ? ' · ID ' + id : '');
        const pvHost = h('div', { class: 'val-pv' });
        const pvBtn = h('button', { class: 'btn btn-primary', type: 'button', 'data-escribe': true, onclick: () => confirmarTarjetas() });
        async function cargarValidadas() {
            const r = await api('/api/validacion/placas-validadas'); if (!S.vivo) return;
            if (r.ok && r.data) {
                PV.items = r.data.items || [];
                if (r.data.yo && !S.yo) { S.yo = r.data.yo; S.log.forEach((l) => { if (!l.u) l.u = S.yo; }); agregarLog(null); }
            }
            const pend = new Set(PV.items.filter((x) => x.tarjeta_id && !x.tarjeta_validada).map((x) => x.tarjeta_id));
            PV.sel.forEach((id) => { if (!pend.has(id)) PV.sel.delete(id); });
            pintarValidadas();
        }
        function pintarValidadas() {
            const its = PV.items;
            const pend = [...new Set(its.filter((x) => x.tarjeta_id && !x.tarjeta_validada).map((x) => x.tarjeta_id))];
            pvBtn.disabled = PV.enviando || !PV.sel.size;
            pvBtn.replaceChildren(icon('check'), PV.sel.size ? 'Marcar ' + PV.sel.size + (PV.sel.size === 1 ? ' tarjeta' : ' tarjetas') + ' como validadas' : 'Marcar tarjetas como validadas');
            if (!its.length) { pvHost.replaceChildren(h('p', { class: 'val-vacio' }, 'Aún no hay placas validadas. Valida una placa en «Tarjeta escaneada» y aparecerá aquí.')); return; }
            const todas = h('input', { type: 'checkbox', 'aria-label': 'Seleccionar todas las tarjetas pendientes', checked: pend.length > 0 && pend.every((id) => PV.sel.has(id)), disabled: !pend.length,
                onchange: (e) => { pend.forEach((id) => (e.target.checked ? PV.sel.add(id) : PV.sel.delete(id))); pintarValidadas(); } });
            const filas = its.map((x) => {
                const pendiente = x.tarjeta_id && !x.tarjeta_validada;
                const cb = pendiente ? h('input', { type: 'checkbox', 'aria-label': 'Seleccionar tarjeta ' + (x.id_tarjeta_num || ''), checked: PV.sel.has(x.tarjeta_id),
                    onchange: (e) => { e.target.checked ? PV.sel.add(x.tarjeta_id) : PV.sel.delete(x.tarjeta_id); pintarValidadas(); } }) : null;
                return h('tr', { dataset: { k: x.tarjeta_validada ? 'ok' : '' } },
                    h('td', null, cb),
                    h('td', null, x.id_tarjeta_num ? h('b', { class: 'mono' }, '#' + x.id_tarjeta_num) : h('span', { class: 'hint' }, 'Sin tarjeta')),
                    h('td', null, h('span', { class: 'val-pl' }, T.tipoChip(x.pcb_tipo), h('span', { class: 'mono' }, x.pcb_nombre || ''))),
                    h('td', null, x.modo === 'manual' ? T.badge('Manual', 'warn') : T.badge('Automática', 'ok')),
                    h('td', null, h('span', { class: 'mono' }, quien(x.probo, x.probo_id)), x.operador && x.operador !== x.probo ? h('div', { class: 'hint' }, 'Validó: ' + quien(x.operador, x.operador_id)) : null),
                    h('td', null, x.creado_en ? util.fecha(x.creado_en) : '—'),
                    h('td', null, x.tarjeta_validada ? T.badge('Validada', 'ok') : (x.tarjeta_id ? T.badge('Por confirmar', 'warn') : '—')));
            });
            pvHost.replaceChildren(h('div', { class: 'val-tabla' }, h('table', { class: 'val-cmp val-pvt' },
                h('thead', null, h('tr', null, h('th', { scope: 'col' }, todas), ...['Tarjeta', 'Placa', 'Validación', 'Probó (usuario · ID)', 'Hora', 'Estado tarjeta'].map((t) => h('th', { scope: 'col' }, t)))),
                h('tbody', null, ...filas))));
        }
        async function confirmarTarjetas() {
            if (!PV.sel.size || PV.enviando) return;
            PV.enviando = true; pintarValidadas();
            const r = await api('/api/validacion/tarjetas/validar', { method: 'POST', body: { tarjeta_ids: [...PV.sel] } });
            PV.enviando = false; if (!S.vivo) return;
            if (r.ok) {
                const n = (r.data && r.data.validadas || []).length;
                toast(n + (n === 1 ? ' tarjeta validada' : ' tarjetas validadas'), { kind: 'ok' });
                agregarLog('✓ ' + n + (n === 1 ? ' tarjeta cambiada' : ' tarjetas cambiadas') + ' a «Validada».', 'ok');
                PV.sel.clear(); cargarValidadas();
            } else { toast(r.error || 'No se pudieron validar las tarjetas.', { kind: 'bad' }); pintarValidadas(); }
        }
        const panelPv = h('section', { class: 'prog-panel', 'aria-labelledby': 'valT4' },
            h('div', { class: 'row' }, h('h2', { id: 'valT4' }, 'Placas validadas'), h('div', { class: 'grow' }), pvBtn),
            h('p', { class: 'hint' }, 'Placas escaneadas, probadas y validadas. Selecciona sus tarjetas y márcalas como «Validada» (se ve en Tarjetas).'), pvHost);

        const dl = h('a', { class: 'btn', href: '/api/validacion/tester.zip', download: '' }, icon('download'), 'Descargar tester Windows');

        const panelFicha = h('section', { class: 'prog-panel', 'aria-labelledby': 'valT0' }, h('h2', { id: 'valT0' }, 'Tarjeta escaneada'), fichaHost);
        const panelPrueba = h('section', { class: 'prog-panel', 'aria-labelledby': 'valT1' },
            h('h2', { id: 'valT1' }, 'Prueba BLE'),
            h('div', { class: 'field' }, h('label', { id: 'valEstL' }, 'Laptop con Bluetooth'), estHost, estHostAy),
            lista,
            h('div', { class: 'row', style: 'margin-top:10px' }, estado, h('div', { class: 'grow' }), btnDes, dl),
            h('div', { class: 'val-cmds' }, btnOn, btnOff));
        const panelLog = h('section', { class: 'prog-panel', 'aria-labelledby': 'valT2' }, h('h2', { id: 'valT2' }, 'Registro de la sesión'), logUl);
        host.append(h('div', { class: 'val' }, avisos, kpis, panelFicha, h('div', { class: 'prog-wrap val-wrap' }, panelPrueba, panelLog), panelPv));
        agregarLog('Listo. Escanea la tarjeta y pulsa «Buscar placas».');
        pintarTodo(); pintarFicha(); pintarKpis(); cargarResumen(); cargarEstaciones(); cargarValidadas();
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
            actualizar() { cargarResumen(); cargarValidadas(); if (S.codigo) comparar(); },
            escaneo(codigo) { return fijarCodigo(codigo); },
            parametros(p) { const c = p.get('codigo'); if (c && c !== S.codigo) fijarCodigo(c); },
            desmontar() {
                S.vivo = false; clearInterval(tEst); clearInterval(tBle);
                timers.forEach((t) => clearTimeout(t)); timers.clear();
                unsubs.forEach((u) => { try { u(); } catch (e) { /* nada */ } });
                host.replaceChildren();
            },
        };
    }
    const def = { id: 'validacion', titulo: 'Pruebas y validación', icono: 'wifi', grupo: 'operacion', orden: 60, montar };
    if (E && E.registrar) E.registrar(def); else { (window.__TQTSecciones = window.__TQTSecciones || []).push(def); }
})();
