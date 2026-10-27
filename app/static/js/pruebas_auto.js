/* pruebas_auto.js - Pruebas automáticas (luna de Escáner TQT): campañas de resistencia en UN banco, la Raspberry.
   5 pasos: 1 agente · 2 Raspberry en línea · 3 puerto serie · 4 campaña · 5 seguimiento y logs.
   API: /api/pruebas-auto (banco, agente, puerto, campañas, logs .txt). Refresca cada 5 s con la pestaña visible. */
(function () {
    'use strict';
    var T = window.TQT, $ = function (id) { return document.getElementById(id); }, esc = T.esc;
    var ESTADO = { activa: 'Activa', pausada: 'Pausada', terminada: 'Terminada', fallida: 'Fallida', detenida: 'Detenida' };
    var RES = { aprobado: 'Aprobado', aprobado_con_advertencias: 'Aprobado con advertencias', fallido: 'Fallido', no_verificado: 'No verificado' };
    var SOL = 'M12 3v2M12 19v2M5.6 5.6l1.4 1.4M17 17l1.4 1.4M3 12h2M19 12h2M5.6 18.4 7 17M17 7l1.4-1.4M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8Z';
    var LUNA = 'M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5Z';
    var tarjeta = null, abierta = null, banco = null, esperaLog = 0, puertoElegido = '';

    /* v1.4.52: sesiones separadas. La Raspberry es de una sola cuenta a la vez: si la usa otra, la API responde 409 con
       quién la tiene y la página se tapa con «Raspberry ocupada» hasta que se libere (entonces se toma sola). */
    var ocupadaVisible = false, tomando = false;
    function api(url, opts) {
        return T.api(url, opts).then(function (r) {
            var d = r.data && r.data.detail;
            if (r.status === 409 && d && d.ocupacion) { r.error = d.mensaje; mostrarOcupada(d.ocupacion, banco && banco.admin); }
            return r;
        });
    }
    function mostrarOcupada(o, admin) {
        var c = o.campana;
        $('ocQuien').textContent = o.por;
        $('ocDesde').textContent = fecha(o.desde);
        $('ocQue').textContent = c ? 'Campaña «' + c.nombre + '» (' + c.firmware + ') · ' + c.hechos + ' de ' + c.ciclos + ' ciclos' +
            (c.en_curso ? ' · ciclo en curso' : '') + (c.estado === 'pausada' ? ' · pausada' : '')
            : 'Sesión abierta en Pruebas automáticas (sin campaña en curso).';
        $('ocForzar').hidden = !admin;
        if (!ocupadaVisible) {
            ocupadaVisible = true; $('ocupada').hidden = false;
            document.querySelector('.app.pa').setAttribute('inert', '');
            $('ocVolver').focus();
        }
    }
    function ocultarOcupada() {
        if (!ocupadaVisible) return;
        ocupadaVisible = false; $('ocupada').hidden = true;
        document.querySelector('.app.pa').removeAttribute('inert');
        T.toast('La Raspberry quedó libre y ahora es tuya.');
    }
    function tomar() {
        if (tomando) return; tomando = true;
        api('/api/pruebas-auto/banco/tomar', { method: 'POST' }).then(function () { tomando = false; });
    }
    function pintarOcupacion(b) {
        var o = b.ocupacion;
        if (o && !o.mio) { mostrarOcupada(o, b.admin); $('enUso').hidden = true; return; }
        ocultarOcupada();
        if (!o) tomar();   // libre: se reserva para esta cuenta
        $('enUso').hidden = !o;
        $('enUsoTxt').textContent = 'Raspberry en uso por ti' + (o && o.campana ? ' · campaña en curso' : '');
        $('liberar').disabled = !!(o && o.campana);
        $('liberar').title = o && o.campana ? 'Detén tu campaña para liberar la Raspberry' : 'Deja la Raspberry libre para otra cuenta';
    }
    $('liberar').addEventListener('click', function () {
        api('/api/pruebas-auto/banco/liberar', { method: 'POST' }).then(function (r) {
            if (!r.ok) { T.toast(r.error, { kind: 'bad' }); return; }
            location.href = '/inicio';
        });
    });
    // v1.4.56: confirmación en dos pasos dentro de la pantalla (sin confirm() nativo)
    $('ocForzar').addEventListener('click', function () {
        var bt = $('ocForzar');
        if (!bt.dataset.seguro) {
            bt.dataset.seguro = '1';
            bt.textContent = 'Confirmar: detener la campaña de ' + $('ocQuien').textContent + ' y liberar';
            setTimeout(function () { delete bt.dataset.seguro; bt.textContent = 'Detener y liberar (administrador)'; }, 6000);
            return;
        }
        delete bt.dataset.seguro; bt.textContent = 'Detener y liberar (administrador)';
        api('/api/pruebas-auto/banco/liberar', { method: 'POST' }).then(function (r) {
            if (!r.ok) T.toast(r.error, { kind: 'bad' }); refrescar();
        });
    });

    function fecha(s) { return s ? new Date(s * 1000).toLocaleString('es-MX', { dateStyle: 'short', timeStyle: 'medium' }) : '—'; }
    function hace(s) { if (!s) return 'nunca'; var d = Math.max(0, Date.now() / 1000 - s); return d < 60 ? 'hace ' + Math.round(d) + ' s' : d < 3600 ? 'hace ' + Math.round(d / 60) + ' min' : fecha(s); }

    /* ---- tema claro/oscuro (misma preferencia que el resto de Escáner TQT: tqt.tema) ---- */
    function pintarTema() {
        var claro = T.currentTheme() === 'light';
        $('temaIco').setAttribute('d', claro ? LUNA : SOL);
        $('tema').setAttribute('aria-label', claro ? 'Cambiar a modo oscuro' : 'Cambiar a modo claro');
    }
    $('tema').addEventListener('click', function () { T.toggleTheme(); pintarTema(); });
    pintarTema();

    function pasos(listo) {
        var actual = 0;
        document.querySelectorAll('.pa-pasos li').forEach(function (li) {
            var n = +li.dataset.paso, ok = !!listo[n];
            li.toggleAttribute('data-ok', ok);
            if (!ok && !actual) { actual = n; li.setAttribute('aria-current', 'step'); } else li.removeAttribute('aria-current');
        });
    }

    /* ---- pasos 1-3: banco, Raspberry y puerto ---- */
    function pintarBanco(b) {
        banco = b;
        var e = b.estado || {}, en = b.registrado && b.en_linea;
        $('p1Estado').innerHTML = b.registrado
            ? 'Agente registrado el ' + esc(fecha(b.creado)) + (en ? ' · <b class="pa-ok">en línea</b>' : ' · <b class="pa-bad">sin señal</b> (' + esc(hace(b.visto)) + ')')
            : 'Aún no hay agente para la Raspberry. Descárgalo e instálalo.';
        $('p1Sum').textContent = b.registrado ? 'Reinstalar el agente (genera una credencial nueva)' : 'Descargar e instalar el agente';
        if (!b.registrado) $('p1Det').open = true;

        var filas = b.registrado ? [
            ['Estado', en ? (e.running ? 'Probando' : 'En línea') : 'Sin señal'],
            ['Última señal', hace(b.visto)],
            ['Equipo', e.host || '—'],
            ['Sistema', e.platform || '—'],
            ['Versión del agente', e.agent_version || 'anterior a Pruebas automáticas (reinstala)'],
        ] : [['Estado', 'Esperando la instalación del paso 1']];
        $('p2Datos').innerHTML = filas.map(function (f) { return '<dt>' + esc(f[0]) + '</dt><dd>' + esc(f[1]) + '</dd>'; }).join('');
        $('p2').dataset.k = en ? 'ok' : 'bad';

        var conectado = en && e.serial_connected;
        $('p3Actual').innerHTML = !en ? 'La Raspberry debe estar en línea para ver sus puertos.'
            : conectado ? 'Conectado a <code>' + esc(e.port) + '</code>' : e.auto_port ? 'Reintentando <code>' + esc(e.auto_port) + '</code>…' : 'Sin puerto conectado.';
        var sel = $('pPuerto'), ps = Array.isArray(e.ports) ? e.ports : [];
        if (document.activeElement !== sel) {
            var prev = puertoElegido || e.port || e.auto_port || '';
            sel.innerHTML = ps.length ? ps.map(function (p) {
                var v = p.by_id || p.device, nom = p.device + (p.description ? ' · ' + p.description : '') + (p.by_id ? ' · ' + p.by_id.split('/').pop() : '');
                return '<option value="' + esc(v) + '">' + esc(nom) + '</option>';
            }).join('') : '<option value="">' + (en ? 'No hay puertos USB serie: conecta la R1 a la Raspberry' : '—') + '</option>';
            ps.forEach(function (p) { if (prev && (prev === p.device || prev === p.by_id)) sel.value = p.by_id || p.device; });
        }
        $('pConectar').disabled = !en || !ps.length || !!e.running;
        $('pDesconectar').disabled = !conectado || !!e.running;
        return { 1: b.registrado, 2: en, 3: conectado };
    }

    function cargarBanco() {
        return api('/api/pruebas-auto/banco').then(function (r) {
            if (!r.ok) { $('p1Estado').textContent = r.error; return {}; }
            pintarOcupacion(r.data);
            var l = pintarBanco(r.data);
            if (esperaLog && r.data.log_ts && r.data.log_ts * 1000 >= esperaLog) { esperaLog = 0; verLog(); }
            return l;
        });
    }

    $('pPuerto').addEventListener('change', function () { puertoElegido = this.value; });
    function puerto(accion) {
        $('pMsg').textContent = accion === 'conectar' ? 'Conectando…' : 'Desconectando…';
        api('/api/pruebas-auto/puerto', { method: 'POST', body: { accion: accion, puerto: accion === 'conectar' ? $('pPuerto').value : '' } }).then(function (r) {
            if (!r.ok) { $('pMsg').textContent = r.error; return; }
            var n = 0, id = r.data.id;
            (function sondeo() {
                T.api('/api/validacion/tqt/commands/' + id).then(function (c) {
                    var st = c.ok && c.data.state;
                    if (st === 'done' || st === 'error') {
                        var err = c.data.result && c.data.result.error;
                        $('pMsg').textContent = err ? err : accion === 'conectar' ? 'Puerto conectado.' : 'Puerto desconectado.';
                        refrescar();
                    } else if (++n < 20) setTimeout(sondeo, 700); else $('pMsg').textContent = 'La Raspberry no respondió; revisa el log del agente.';
                });
            })();
        });
    }
    $('pConectar').addEventListener('click', function () { puerto('conectar'); });
    $('pDesconectar').addEventListener('click', function () { puerto('desconectar'); });

    $('fInst').addEventListener('submit', function (e) {
        e.preventDefault();
        fetch('/api/pruebas-auto/agente', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Cliente': 'pruebas-auto' },
            body: JSON.stringify({ puerto_serie: $('iPuerto').value.trim() || null }) })
            .then(function (r) { if (!r.ok) return r.json().then(function (d) { throw new Error(d && d.detail || 'Error ' + r.status); }); return r.blob(); })
            .then(function (b) {
                var a = document.createElement('a'); a.href = URL.createObjectURL(b); a.download = 'TQT_Pruebas_Raspberry.zip'; a.click();
                setTimeout(function () { URL.revokeObjectURL(a.href); }, 4000);
                T.toast('Agente descargado. Instálalo en la Raspberry con los comandos de abajo.'); refrescar();
            }, function (err) { T.toast(String(err.message || err), { kind: 'bad' }); });
    });

    /* ---- paso 4: campaña ---- */
    var buscar = T.debounce(function () {
        var q = $('cBusca').value.trim();
        if (!q) { $('cTarjetas').innerHTML = ''; return; }
        api('/api/pruebas-auto/tarjetas?q=' + encodeURIComponent(q)).then(function (r) {
            var l = r.ok ? r.data : [];
            $('cTarjetas').innerHTML = l.length ? l.map(function (t) {
                return '<button type="button" role="option" class="pa-op" data-id="' + t.id + '" aria-selected="' + (tarjeta && tarjeta.id === t.id) + '">' +
                    '<b>Tarjeta ' + esc(t.id_tarjeta_num) + '</b> · ' + esc(t.r1) + ' + ' + esc(t.r2) + (t.firmware ? ' · FW ' + esc(t.firmware) : '') + '</button>';
            }).join('') : '<p class="hint">' + (r.ok ? 'Sin tarjetas armadas con R1 y R2 y sus MAC.' : esc(r.error)) + '</p>';
            l.forEach(function (t) { var b = $('cTarjetas').querySelector('[data-id="' + t.id + '"]'); if (b) b._t = t; });
        });
    }, 250);
    $('cBusca').addEventListener('input', function () { tarjeta = null; buscar(); });
    $('cTarjetas').addEventListener('click', function (e) {
        var b = e.target.closest('.pa-op'); if (!b) return;
        tarjeta = b._t;
        $('cTarjetas').querySelectorAll('.pa-op').forEach(function (x) { x.setAttribute('aria-selected', String(x === b)); });
    });
    $('fNueva').addEventListener('submit', function (e) {
        e.preventDefault();
        var msg = $('nMsg');
        if (!tarjeta) { msg.textContent = 'Elige una tarjeta de la lista.'; $('cBusca').focus(); return; }
        msg.textContent = 'Creando…';
        api('/api/pruebas-auto/campanas', { method: 'POST', body: {
            nombre: $('cNombre').value, firmware: $('cFw').value, tarjeta_id: tarjeta.id,
            ciclos: +$('cCiclos').value, pausa_s: +$('cPausa').value, detener_en_falla: $('cDetener').checked, physical_confirmed: $('cConf').checked,
        } }).then(function (r) {
            msg.textContent = r.ok ? 'Campaña creada: la Raspberry empieza el primer ciclo en cuanto esté libre y con el puerto conectado.' : r.error;
            if (r.ok) { $('cConf').checked = false; abierta = r.data.id; refrescar(); }
        });
    });

    /* ---- paso 5: campañas y logs ---- */
    function barra(c) {
        var k = c.conteo, tot = Math.max(c.ciclos, 1);
        return '<div class="pa-barra" role="img" aria-label="' + k.aprobados + ' aprobados, ' + k.fallidos + ' fallidos, ' + k.no_verificados + ' no verificados de ' + c.ciclos + '">' +
            '<i data-k="ok" style="width:' + (100 * k.aprobados / tot) + '%"></i><i data-k="bad" style="width:' + (100 * k.fallidos / tot) + '%"></i>' +
            '<i data-k="warn" style="width:' + (100 * k.no_verificados / tot) + '%"></i><i data-k="run" style="width:' + (100 * k.en_curso / tot) + '%"></i></div>';
    }
    function campanas() {
        return api('/api/pruebas-auto/campanas').then(function (r) {
            var l = r.ok && Array.isArray(r.data) ? r.data : [];
            $('campanas').innerHTML = l.length ? l.map(function (c) {
                var k = c.conteo, act = c.estado === 'activa' || c.estado === 'pausada';
                return '<article class="pa-camp" data-estado="' + esc(c.estado) + '">' +
                    '<div class="pa-camp-h"><div><b>' + esc(c.nombre) + '</b> <span class="pa-estado">' + esc(ESTADO[c.estado] || c.estado) + '</span>' +
                    '<div class="hint">' + esc(c.firmware) + ' · Tarjeta ' + esc(c.tarjeta ? c.tarjeta.id_tarjeta_num : '?') + ' · ' + esc(c.operador) + ' · ' + esc(fecha(c.creado)) + '</div></div>' +
                    '<div class="pa-acc">' +
                    (c.estado === 'activa' ? '<button class="btn btn-sm" data-a="pausar" data-id="' + c.id + '">Pausar</button>' : '') +
                    (c.estado === 'pausada' ? '<button class="btn btn-sm" data-a="reanudar" data-id="' + c.id + '">Reanudar</button>' : '') +
                    (act ? '<button class="btn btn-sm btn-danger" data-a="detener" data-id="' + c.id + '">Detener</button>' : '') +
                    (k.hechos ? '<a class="btn btn-sm btn-ghost" href="/api/pruebas-auto/campanas/' + c.id + '/log.txt" download>LOG .txt</a>' : '') +
                    '<button class="btn btn-sm btn-ghost" data-ver="' + c.id + '" aria-expanded="' + (abierta === c.id) + '">Ciclos</button></div></div>' +
                    barra(c) +
                    '<div class="hint">' + k.hechos + ' de ' + c.ciclos + ' ciclos · ' + k.aprobados + ' aprobados · ' + k.fallidos + ' fallidos · ' + k.no_verificados + ' no verificados' +
                    (k.en_curso ? ' · 1 en curso' : '') + (c.motivo ? ' · ' + esc(c.motivo) : '') + '</div>' +
                    '<div class="pa-ciclos" id="d' + c.id + '"></div></article>';
            }).join('') : '<p class="hint">' + (r.ok ? 'Aún no hay campañas.' : esc(r.error)) + '</p>';
            if (abierta) detalle(abierta);
            return l.length > 0;
        });
    }
    function detalle(id) {
        var box = $('d' + id); if (!box) return;
        api('/api/pruebas-auto/campanas/' + id).then(function (r) {
            if (!r.ok) { box.textContent = r.error; return; }
            box.innerHTML = r.data.ciclos_detalle.length ? '<table class="pa-tabla"><thead><tr><th>Ciclo</th><th>Resultado</th><th>Inicio</th><th>Fin</th><th>LOG</th></tr></thead><tbody>' +
                r.data.ciclos_detalle.map(function (x) {
                    var res = x.state === 'queued' ? 'En cola' : x.state === 'running' ? 'Probando' : (RES[x.result] || x.result || '—');
                    return '<tr><td>' + x.n + '</td><td data-r="' + esc(x.result || x.state) + '">' + esc(res) + '</td><td>' + fecha(x.created) + '</td><td>' +
                        (x.state === 'finished' || x.state === 'interrupted' ? fecha(x.updated) : '—') + '</td><td>' +
                        (x.state === 'finished' || x.state === 'interrupted' ? '<a href="/api/pruebas-auto/ciclos/' + esc(x.run) + '/log.txt" download>.txt</a>' : '') + '</td></tr>';
                }).join('') + '</tbody></table>' : '<p class="hint">Esperando el primer ciclo.</p>';
        });
    }
    $('campanas').addEventListener('click', function (e) {
        var b = e.target.closest('button'); if (!b) return;
        if (b.dataset.ver) {
            abierta = abierta === b.dataset.ver ? null : b.dataset.ver;
            b.setAttribute('aria-expanded', String(abierta === b.dataset.ver));
            if (abierta) detalle(abierta); else $('d' + b.dataset.ver).innerHTML = '';
            return;
        }
        if (!b.dataset.a) return;
        b.disabled = true;
        api('/api/pruebas-auto/campanas/' + b.dataset.id + '/accion', { method: 'POST', body: { accion: b.dataset.a } }).then(function (r) {
            if (!r.ok) T.toast(r.error, { kind: 'bad' });
            refrescar();
        });
    });

    function verLog() {
        api('/api/pruebas-auto/agente/log').then(function (r) {
            if (!r.ok) { $('lMeta').textContent = r.error; return; }
            var pre = $('lTexto'), abajo = pre.scrollTop + pre.clientHeight >= pre.scrollHeight - 8;
            pre.textContent = r.data.texto ? r.data.texto.split('\n').slice(-400).join('\n') : 'Sin log todavía. Pulsa «Traer log».';
            if (abajo) pre.scrollTop = pre.scrollHeight;
            $('lMeta').textContent = r.data.ts ? 'Recibido ' + hace(r.data.ts) : '';
        });
    }
    $('lPedir').addEventListener('click', function () {
        api('/api/pruebas-auto/agente/log', { method: 'POST' }).then(function (r) {
            if (!r.ok) { T.toast(r.error, { kind: 'bad' }); return; }
            esperaLog = Date.now() - 1000;
            $('lMeta').textContent = r.data.en_linea ? 'Pidiendo el log a la Raspberry…' : 'La Raspberry está sin señal: el log llegará cuando vuelva.';
        });
    });

    function refrescar() {
        Promise.all([cargarBanco(), campanas()]).then(function (v) { var l = v[0] || {}; l[4] = v[1]; l[5] = v[1]; pasos(l); });
    }
    refrescar(); verLog();
    setInterval(function () { if (!document.hidden) refrescar(); }, 5000);
})();
