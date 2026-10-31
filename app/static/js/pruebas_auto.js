/* pruebas_auto.js - Pruebas automáticas (luna de Escáner TQT): campañas de resistencia en UN banco, la Raspberry.
   Pantalla: preparar el banco (agente · Raspberry · puerto R1) → campaña en curso o nueva campaña → registro en vivo,
   log del agente e historial. API: /api/pruebas-auto (banco, agente, puerto, campañas, logs .txt).
   Refresco: banco y campañas cada 5 s; /vivo cada 2 s solo con campaña activa; nada con la pestaña oculta. */
(function () {
    'use strict';
    var T = window.TQT, $ = function (id) { return document.getElementById(id); }, esc = T.esc;
    var ESTADO = { activa: 'Activa', pausada: 'Pausada', terminada: 'Terminada', fallida: 'Fallida', detenida: 'Detenida' };
    var ESTADO_K = { activa: 'run', pausada: 'warn', terminada: 'ok', fallida: 'bad', detenida: 'pend' };
    var RES = { aprobado: 'Aprobado', aprobado_con_advertencias: 'Aprobado con advertencias', fallido: 'Fallido', no_verificado: 'No verificado' };
    var SOL = 'M12 3v2M12 19v2M5.6 5.6l1.4 1.4M17 17l1.4 1.4M3 12h2M19 12h2M5.6 18.4 7 17M17 7l1.4-1.4M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8Z';
    var LUNA = 'M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5Z';
    var REDUCIDO = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
    var tarjeta = null, abierta = null, banco = null, esperaLog = 0, puertoElegido = '', cambiarPuerto = false, instAuto = false;
    var campLista = [], detCache = {}, repetirNum = '', listoBanco = null;

    function fecha(s) { return s ? new Date(s * 1000).toLocaleString('es-MX', { dateStyle: 'short', timeStyle: 'short' }) : '—'; }
    function hora(s) { return new Date(s * 1000).toLocaleTimeString('es-MX', { hour: '2-digit', minute: '2-digit', second: '2-digit' }); }
    function hace(s) { if (!s) return 'nunca'; var d = Math.max(0, Date.now() / 1000 - s); return d < 60 ? 'hace ' + Math.round(d) + ' s' : d < 3600 ? 'hace ' + Math.round(d / 60) + ' min' : fecha(s); }
    function dur(s) {
        s = Math.max(0, Math.round(s));
        if (s < 60) return s + ' s';
        if (s < 3600) return Math.floor(s / 60) + ' min' + (s % 60 ? ' ' + (s % 60) + ' s' : '');
        return Math.floor(s / 3600) + ' h ' + String(Math.round((s % 3600) / 60)).padStart(2, '0') + ' min';
    }
    // escribe solo si cambió: evita parpadeo, pérdida de foco y avisos repetidos de lectores de pantalla
    function setHTML(el, html) { if (el._h !== html) { el._h = html; el.innerHTML = html; } }
    function setTxt(el, t) { if (el.textContent !== t) el.textContent = t; }

    /* ---- sesiones separadas: la Raspberry es de una sola cuenta a la vez. Si la usa otra, la API responde 409 con
       quién la tiene y la página se tapa con «Raspberry ocupada» hasta que se libere (entonces se toma sola). ---- */
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
        if (!o && !liberada) tomar();   // libre: se reserva para esta cuenta (salvo que la acabes de liberar)
        $('enUso').hidden = !o && !liberada;
        // v1.4.67: tras «Liberar» te quedas en la página; el botón pasa a «Usar la Raspberry»
        setTxt($('enUsoTxt'), o ? 'En uso por ti' + (o.campana ? ' · campaña en curso' : '') : 'Raspberry libre');
        setTxt($('liberar'), o ? 'Liberar' : 'Usar la Raspberry');
        $('liberar').disabled = !!(o && o.campana);
        $('liberar').title = o && o.campana ? 'Detén tu campaña para liberar la Raspberry'
            : o ? 'Deja la Raspberry libre para otra cuenta (sigues en esta página)' : 'Vuelve a reservar la Raspberry para tu cuenta';
    }
    var liberada = false;
    $('liberar').addEventListener('click', function () {
        if (liberada) { liberada = false; tomar(); setTimeout(refrescar, 400); return; }
        api('/api/pruebas-auto/banco/liberar', { method: 'POST' }).then(function (r) {
            if (!r.ok) { T.toast(r.error, { kind: 'bad' }); return; }
            liberada = true;
            T.toast('Raspberry liberada: otra cuenta ya puede usarla. Puedes seguir aquí viendo el historial.');
            refrescar();
        });
    });
    // confirmación en dos pasos dentro de la pantalla (sin confirm() nativo)
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

    /* ---- tema claro/oscuro (misma preferencia que el resto de Escáner TQT: tqt.tema) ---- */
    function pintarTema() {
        var claro = T.currentTheme() === 'light';
        $('temaIco').setAttribute('d', claro ? LUNA : SOL);
        $('tema').setAttribute('aria-label', claro ? 'Cambiar a modo oscuro' : 'Cambiar a modo claro');
    }
    $('tema').addEventListener('click', function () { T.toggleTheme(); pintarTema(); });
    pintarTema();

    /* ---- preparar el banco: agente, Raspberry y puerto ---- */
    function abrirInst(v) {
        $('instPanel').hidden = !v;
        $('iAbrir').setAttribute('aria-expanded', String(v));
        $('prep').dataset.listo = String(!v && !!(listoBanco && listoBanco.listo));
    }
    $('iAbrir').addEventListener('click', function () {
        var abrir = $('instPanel').hidden; abrirInst(abrir);
        if (abrir) $('iPuerto').focus();
    });

    function pintarBanco(b) {
        banco = b;
        var e = b.estado || {}, reg = !!b.registrado, en = reg && !!b.en_linea, conectado = en && !!e.serial_connected, run = !!e.running;
        var ver = e.agent_version || '';
        // nombre corto del puerto: /dev/ttyUSB0 en vez de la ruta larga by-id (la ruta completa queda en el title)
        var psL = Array.isArray(e.ports) ? e.ports : [], pAct = conectado ? e.port : e.auto_port;
        var pM = psL.find(function (x) { return pAct && (x.by_id === pAct || x.device === pAct); });
        var pCorto = pAct ? (pM ? pM.device : String(pAct).split('/').pop()) : '';

        // agente
        var cA = $('cAgente');
        cA.dataset.k = !reg ? 'warn' : !en ? 'bad' : ver ? 'ok' : 'warn';
        cA.querySelector('.pa-conn').dataset.k = cA.dataset.k;
        setTxt($('aEstado'), !reg ? 'Sin instalar' : (en ? 'En línea' : 'Sin señal') + (ver ? ' · versión ' + ver : ''));
        setTxt($('aHint'), !reg ? 'Instálalo con un solo comando en la Raspberry; aquí verás el avance.'
            : !ver ? 'Versión anterior a Pruebas automáticas: actualízalo.'
            : en ? 'Registrado el ' + fecha(b.creado) + '. Se actualiza solo.'
            : 'Última señal ' + hace(b.visto) + '. Revisa que la Raspberry esté encendida y con red.');
        setTxt($('iAbrirTxt'), reg ? 'Actualizar' : 'Instalar agente');
        $('iAbrir').title = reg ? 'Reinstala o actualiza el agente; conserva el mismo banco' : 'Genera el comando de instalación para la Raspberry';
        if (!reg && !instAuto) { instAuto = true; abrirInst(true); }

        // Raspberry
        var cR = $('cRasp');
        cR.dataset.k = en ? 'ok' : reg ? 'bad' : 'pend';
        cR.querySelector('.pa-conn').dataset.k = cR.dataset.k;
        setTxt($('rEstado'), en ? (run ? 'En línea · ejecutando un ciclo' : 'En línea') : reg ? 'Sin señal · ' + hace(b.visto) : 'Esperando al agente');
        setTxt($('rHint'), reg ? [e.host, e.platform].filter(Boolean).join(' · ') + (en ? ' · última señal ' + hace(b.visto) : '')
            : 'Aparece aquí cuando el agente se conecte por primera vez.');

        // puerto de la R1
        var cP = $('cPuerto');
        cP.dataset.k = conectado ? 'ok' : en ? 'warn' : 'pend';
        cP.querySelector('.pa-conn').dataset.k = cP.dataset.k;
        setHTML($('p3Actual'), !en ? 'Disponible cuando la Raspberry esté en línea'
            : conectado ? 'Conectado a <code title="' + esc(e.port) + '">' + esc(pCorto) + '</code>' + (pM && pM.description ? ' · ' + esc(pM.description) : '')
            : e.auto_port ? 'Reintentando <code title="' + esc(e.auto_port) + '">' + esc(pCorto) + '</code>…' : 'Sin puerto conectado: elige uno y pulsa Conectar');
        // comandos serie: solo con el puerto de la R1 conectado y sin ciclo en curso
        document.querySelectorAll('#kOn,#kOff,#kReset,#kEnviar').forEach(function (x) { x.disabled = !conectado; });
        $('kSel').disabled = !conectado;
        $('kMeta').textContent = !en ? 'Raspberry sin señal' : !conectado ? 'Conecta el puerto de la R1' : run ? 'Ciclo en curso: al enviar se pausa la campaña y se corta el ciclo' : 'Listos';
        var sel = $('pPuerto'), ps = Array.isArray(e.ports) ? e.ports : [];
        if (document.activeElement !== sel) {
            var prev = puertoElegido || e.port || e.auto_port || '';
            setHTML(sel, ps.length ? ps.map(function (p) {
                var v = p.by_id || p.device, nom = p.device + (p.description ? ' · ' + p.description : '') + (p.by_id ? ' · ' + p.by_id.split('/').pop() : '');
                return '<option value="' + esc(v) + '">' + esc(nom) + '</option>';
            }).join('') : '<option value="">' + (en ? 'No hay puertos USB serie: conecta la R1 a la Raspberry' : '—') + '</option>');
            ps.forEach(function (p) { if (prev && (prev === p.device || prev === p.by_id)) sel.value = p.by_id || p.device; });
        }
        $('pFila').hidden = !en || (conectado && !cambiarPuerto);
        $('pSec').hidden = !conectado;
        $('pCambiar').setAttribute('aria-expanded', String(cambiarPuerto));
        $('pCambiar').textContent = cambiarPuerto ? 'Cancelar cambio' : 'Cambiar puerto';
        $('pConectar').disabled = !en || !ps.length || run;
        $('pConectar').title = !en ? 'La Raspberry está sin señal' : !ps.length ? 'No hay puertos USB serie detectados' : run ? 'Espera a que termine el ciclo en curso' : 'Conecta el agente a este puerto';
        $('pDesconectar').disabled = !conectado || run;
        $('pDesconectar').title = run ? 'Espera a que termine el ciclo en curso' : 'Suelta el puerto serie de la R1';
        $('pCambiar').disabled = run;

        // chip de la barra superior
        var chip = $('chipBanco');
        chip.dataset.k = !reg ? 'warn' : en ? 'ok' : 'bad';
        setTxt($('chipTxt'), !reg ? 'Sin agente en la Raspberry'
            : en ? 'Raspberry en línea' + (ver ? ' · agente ' + ver : '') + ' · ' + (conectado ? pCorto : 'sin puerto')
            : 'Raspberry sin señal · ' + hace(b.visto));

        // resumen
        var faltan = [];
        if (!reg) faltan.push('instalar el agente');
        else if (!en) faltan.push('que la Raspberry vuelva a estar en línea');
        else if (!conectado) faltan.push('conectar el puerto de la R1');
        var res = $('prepRes');
        res.dataset.k = faltan.length ? 'warn' : 'ok';
        setTxt($('prepResTxt'), faltan.length ? 'Falta ' + faltan.join(' y ') + '.' : 'Banco listo: agente en línea y puerto de la R1 conectado.');
        listoBanco = { reg: reg, en: en, conectado: conectado, run: run, listo: !faltan.length };
        $('prep').dataset.listo = String(!faltan.length && $('instPanel').hidden);
        return listoBanco;
    }

    function cargarBanco() {
        return api('/api/pruebas-auto/banco').then(function (r) {
            if (!r.ok) { $('chipBanco').dataset.k = 'bad'; setTxt($('chipTxt'), r.error || 'No se pudo consultar el banco'); return null; }
            pintarOcupacion(r.data);
            var l = pintarBanco(r.data);
            if (esperaLog && r.data.log_ts && r.data.log_ts * 1000 >= esperaLog) { esperaLog = 0; verLog(); }
            return l;
        });
    }

    $('pPuerto').addEventListener('change', function () { puertoElegido = this.value; });
    $('pCambiar').addEventListener('click', function () { cambiarPuerto = !cambiarPuerto; if (banco) pintarBanco(banco); if (cambiarPuerto) $('pPuerto').focus(); });
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
                        $('pMsg').textContent = err ? err : accion === 'conectar' ? 'Puerto conectado. El agente vuelve a él solo tras reiniciar la Raspberry o reconectar el USB.' : 'Puerto desconectado.';
                        if (!err) cambiarPuerto = false;
                        refrescar();
                    } else if (++n < 20) setTimeout(sondeo, 700); else $('pMsg').textContent = 'La Raspberry no respondió; revisa el log del agente.';
                });
            })();
        });
    }
    /* v1.4.78: comandos serie manuales por la Raspberry (ON/OFF = PPON/POFF); mismo sondeo que el puerto. */
    function comando(nombre) {
        var e = banco && banco.estado || {};
        if (!e.running) { enviarComando(nombre); return; }
        // ciclo en curso: el motor rechaza comandos, así que se pausa la campaña, se corta el ciclo y luego se envía
        if (!vivoId) { $('kMsg').textContent = 'Hay un ciclo en curso que no es de una campaña: espera a que termine.'; return; }
        if (!window.confirm('Hay un ciclo en curso. Se pausará la campaña y se cancelará el ciclo actual (el firmware termina el movimiento que ya empezó); ' +
            'ese ciclo no cuenta como falla. Después se enviará ' + nombre + ' y tú reanudas la campaña. ¿Continuar?')) return;
        $('kMsg').textContent = 'Pausando la campaña y cortando el ciclo…';
        api('/api/pruebas-auto/campanas/' + encodeURIComponent(vivoId) + '/accion', { method: 'POST', body: { accion: 'interrumpir' } }).then(function (r) {
            if (!r.ok) { $('kMsg').textContent = r.error; return; }
            var n = 0;
            (function espera() {
                cargarBanco().then(function () {
                    var st = banco && banco.estado || {};
                    if (!st.running) { enviarComando(nombre); refrescar(); }
                    else if (++n < 60) setTimeout(espera, 1500); else $('kMsg').textContent = 'El ciclo no terminó a tiempo; la campaña quedó pausada. Reintenta en un momento.';
                });
            })();
        });
    }
    function enviarComando(nombre) {
        var necesita = nombre === 'PPON' || nombre === 'POFF';
        // con campaña activa o pausada el servidor usa su tarjeta; sin campaña, la elegida en «Nueva campaña»
        $('kMsg').textContent = 'Enviando ' + nombre + '…';
        api('/api/pruebas-auto/comando', { method: 'POST', body: { comando: nombre, tarjeta_id: necesita && tarjeta ? tarjeta.id : null } }).then(function (r) {
            if (!r.ok) { $('kMsg').textContent = r.error; return; }
            var n = 0, id = r.data.id;
            (function sondeo() {
                T.api('/api/validacion/tqt/commands/' + id).then(function (c) {
                    var st = c.ok && c.data.state;
                    if (st === 'done' || st === 'error') {
                        var err = c.data.result && c.data.result.error;
                        $('kMsg').textContent = err ? nombre + ': ' + err : nombre + ' enviado a la R1 por la Raspberry. La respuesta aparece en el log del agente.';
                    } else if (++n < 20) setTimeout(sondeo, 700); else $('kMsg').textContent = 'La Raspberry no respondió; revisa el log del agente.';
                });
            })();
        });
    }
    ['kOn', 'kOff', 'kReset'].forEach(function (id) { $(id).addEventListener('click', function () { comando(this.dataset.cmd); }); });
    $('kEnviar').addEventListener('click', function () { comando($('kSel').value); });
    $('pConectar').addEventListener('click', function () { puerto('conectar'); });
    $('pDesconectar').addEventListener('click', function () { puerto('desconectar'); });

    /* ---- instalación en segundo plano: comando de un solo uso (curl … | sh) para la Raspberry; el instalador reporta
       sus etapas y aquí se ve «Instalando…» hasta que el agente nuevo está en línea («✓ Todo correcto»). ---- */
    var instSeq = 0;
    var ETAPA = { extrayendo: 'copiando archivos', python: 'preparando Python', dependencias: 'instalando pyserial y bleak',
        arrancando: 'arrancando el agente', listo: 'instalado; esperando a que se conecte' };
    function avance(k, txt) { var el = $('iAvance'); el.hidden = !txt; el.dataset.k = k; el.textContent = txt; }
    function cuerpoInst(formato) { return { puerto_serie: $('iPuerto').value.trim() || null, formato: formato }; }
    function seguirInstalacion(inicio) {
        var my = ++instSeq, hasta = Date.now() + 30 * 60000, previo = null;
        (function sondeo() {
            if (my !== instSeq) return;
            if (Date.now() > hasta) { avance('bad', 'No llegó confirmación de la Raspberry. Revisa ~/tqt-pruebas-instalar.log en la Raspberry y genera otro comando.'); return; }
            api('/api/pruebas-auto/agente/instalacion').then(function (r) {
                if (my !== instSeq) return;
                if (r.ok) {
                    var e = r.data, nuevo = e.ts >= inicio - 5;   // avance de ESTA instalación
                    if (previo === null) previo = !!e.listo;
                    if (nuevo && e.etapa === 'error') { avance('bad', 'No se pudo instalar: ' + (e.mensaje || 'revisa ~/tqt-pruebas-instalar.log') + '. Corrígelo y genera otro comando.'); return; }
                    if (e.listo && (nuevo || !previo)) {
                        avance('ok', '✓ Todo correcto: agente ' + (e.agent_version || '') + ' en línea en la Raspberry y listo para usar. Sigue con el puerto de la R1.');
                        $('iCmdBox').hidden = true;
                        T.toast('Agente instalado y en línea.', { kind: 'ok' });
                        setTimeout(function () { abrirInst(false); }, 4000);
                        refrescar();
                        return;
                    }
                    if (nuevo && ETAPA[e.etapa]) avance('run', 'Instalando… ' + ETAPA[e.etapa] + '.' + (e.mensaje && e.etapa !== 'listo' ? ' ' + e.mensaje : ''));
                }
                setTimeout(sondeo, 2000);
            });
        })();
    }
    $('fInst').addEventListener('submit', function (e) {
        e.preventDefault();
        var inicio = Date.now() / 1000;
        avance('run', 'Generando el comando…');
        api('/api/pruebas-auto/agente', { method: 'POST', body: cuerpoInst('comando') }).then(function (r) {
            if (!r.ok) { avance('bad', r.error || 'No se pudo generar el comando.'); return; }
            $('iCmd').textContent = r.data.comando;
            $('iCmdExp').textContent = r.data.expira ? 'a las ' + new Date(r.data.expira * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : 'en 15 min';
            $('iCmdBox').hidden = false;
            avance('run', 'Esperando a que pegues el comando en la Raspberry…');
            seguirInstalacion(inicio);
        });
    });
    $('iCopiar').addEventListener('click', function () {
        var txt = $('iCmd').textContent;
        (navigator.clipboard ? navigator.clipboard.writeText(txt) : Promise.reject()).then(function () { T.toast('Comando copiado. Pégalo en la terminal de la Raspberry.'); },
            function () { var r = document.createRange(); r.selectNodeContents($('iCmd')); var sel = getSelection(); sel.removeAllRanges(); sel.addRange(r); T.toast('Selecciona y copia el comando (Ctrl+C).'); });
    });
    $('iSh').addEventListener('click', function (e) {
        e.preventDefault();
        var inicio = Date.now() / 1000;
        fetch('/api/pruebas-auto/agente', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Cliente': 'pruebas-auto' },
            body: JSON.stringify(cuerpoInst('sh')) })
            .then(function (r) { if (!r.ok) return r.json().then(function (d) { throw new Error(d && d.detail && (d.detail.mensaje || d.detail) || 'Error ' + r.status); }); return r.blob(); })
            .then(function (b) {
                var a = document.createElement('a'); a.href = URL.createObjectURL(b); a.download = 'instalar_tqt_pruebas.sh'; a.click();
                setTimeout(function () { URL.revokeObjectURL(a.href); }, 4000);
                avance('run', 'Instalador descargado. Cópialo a la Raspberry y corre: sh instalar_tqt_pruebas.sh');
                seguirInstalacion(inicio);
            }, function (err) { avance('bad', String(err.message || err)); });
    });

    /* ---- nueva campaña ---- */
    function elegirTarjeta(b) {
        tarjeta = b ? b._t : null;
        $('cTarjetas').querySelectorAll('.pa-op').forEach(function (x) { x.setAttribute('aria-selected', String(x === b)); });
    }
    var buscar = T.debounce(function () {
        var q = $('cBusca').value.trim();
        if (!q) { $('cTarjetas').innerHTML = ''; return; }
        api('/api/pruebas-auto/tarjetas?q=' + encodeURIComponent(q)).then(function (r) {
            var l = r.ok ? r.data : [];
            $('cTarjetas').innerHTML = l.length ? l.map(function (t) {
                return '<button type="button" role="option" class="pa-op" data-id="' + t.id + '" aria-selected="' + (tarjeta && tarjeta.id === t.id) + '">' +
                    '<b>Tarjeta ' + esc(t.id_tarjeta_num) + '</b><small>' + esc(t.r1) + ' + ' + esc(t.r2) + (t.firmware ? ' · FW ' + esc(t.firmware) : '') + ' · ' + esc(T.loteEtiqueta(t)) + '</small></button>';
            }).join('') : '<p class="hint">' + (r.ok ? 'Sin tarjetas armadas con R1 y R2 y sus MAC.' : esc(r.error)) + '</p>';
            l.forEach(function (t) { var b = $('cTarjetas').querySelector('[data-id="' + t.id + '"]'); if (b) b._t = t; });
            if (repetirNum) {   // «Repetir»: se elige sola la misma tarjeta
                var t = l.find(function (x) { return String(x.id_tarjeta_num) === repetirNum; });
                repetirNum = '';
                if (t) elegirTarjeta($('cTarjetas').querySelector('[data-id="' + t.id + '"]'));
            }
        });
    }, 250);
    $('cBusca').addEventListener('input', function () { tarjeta = null; repetirNum = ''; buscar(); });
    $('cTarjetas').addEventListener('click', function (e) { var b = e.target.closest('.pa-op'); if (b) elegirTarjeta(b); });
    function pintarReq(l) {
        var bt = $('nIniciar'), req = $('nReq'), msg = '', k = 'warn', bloquea = false;
        if (!l) return;
        if (!l.reg) { msg = 'Instala el agente en la Raspberry («Instalar agente», arriba) para poder iniciar una campaña.'; bloquea = true; }
        else if (!l.en) { msg = 'La Raspberry está sin señal: no se puede iniciar una campaña hasta que vuelva a estar en línea.'; bloquea = true; }
        else if (!l.conectado) { msg = 'El puerto de la R1 no está conectado: la campaña esperará a que lo conectes.'; k = 'info'; }
        req.hidden = !msg; req.dataset.k = k; setTxt($('nReqTxt'), msg);
        bt.disabled = bloquea;
        bt.title = bloquea ? msg : 'Crea la campaña; la Raspberry empieza el primer ciclo en cuanto esté libre y con el puerto conectado';
    }
    $('fNueva').addEventListener('submit', function (e) {
        e.preventDefault();
        var msg = $('nMsg');
        if (!$('cNombre').value.trim()) { msg.textContent = 'Escribe un nombre para la campaña.'; $('cNombre').focus(); return; }
        if (!$('cFw').value.trim()) { msg.textContent = 'Escribe el firmware que se valida.'; $('cFw').focus(); return; }
        if (!tarjeta) { msg.textContent = 'Busca y elige la tarjeta de la lista.'; $('cBusca').focus(); return; }
        if (!$('cConf').checked) { msg.textContent = 'Confirma la tarjeta física y el banco libre.'; $('cConf').focus(); return; }
        msg.textContent = 'Creando…';
        api('/api/pruebas-auto/campanas', { method: 'POST', body: {
            nombre: $('cNombre').value, firmware: $('cFw').value, tarjeta_id: tarjeta.id,
            ciclos: +$('cCiclos').value, pausa_s: +$('cPausa').value, detener_en_falla: $('cDetener').checked, physical_confirmed: $('cConf').checked,
        } }).then(function (r) {
            msg.textContent = r.ok ? 'Campaña creada: la Raspberry empieza el primer ciclo en cuanto esté libre y con el puerto conectado.' : r.error;
            if (r.ok) { $('cConf').checked = false; refrescar(); }
        });
    });
    function repetir(id) {
        var c = campLista.find(function (x) { return String(x.id) === String(id); }); if (!c) return;
        $('cNombre').value = c.nombre || ''; $('cFw').value = c.firmware || '';
        $('cCiclos').value = c.ciclos || 50; $('cPausa').value = c.pausa_s != null ? c.pausa_s : 60;
        $('cDetener').checked = !!c.detener_en_falla; $('cConf').checked = false;
        tarjeta = null; $('cTarjetas').innerHTML = '';
        if (c.tarjeta && c.tarjeta.id_tarjeta_num != null) { repetirNum = String(c.tarjeta.id_tarjeta_num); $('cBusca').value = repetirNum; buscar(); }
        $('nMsg').textContent = 'Datos de «' + c.nombre + '» cargados. Revisa la tarjeta, confirma el banco y pulsa «Iniciar campaña».';
        $('nueva').scrollIntoView({ behavior: REDUCIDO ? 'auto' : 'smooth', block: 'start' });
        $('cNombre').focus({ preventScroll: true });
    }

    /* ---- historial de campañas ---- */
    function barra(k, ciclos) {
        var tot = Math.max(ciclos, 1);
        return '<i data-k="ok" style="width:' + (100 * k.aprobados / tot) + '%"></i><i data-k="bad" style="width:' + (100 * k.fallidos / tot) + '%"></i>' +
            '<i data-k="warn" style="width:' + (100 * k.no_verificados / tot) + '%"></i><i data-k="run" style="width:' + (100 * k.en_curso / tot) + '%"></i>';
    }
    function barraLbl(k, ciclos) { return k.aprobados + ' aprobados, ' + k.fallidos + ' fallidos, ' + k.no_verificados + ' no verificados de ' + ciclos + ' ciclos'; }
    function campanas() {
        return api('/api/pruebas-auto/campanas').then(function (r) {
            var l = r.ok && Array.isArray(r.data) ? r.data : [];
            campLista = l;
            var act = l.find(function (c) { return c.estado === 'activa' || c.estado === 'pausada'; });
            pintarHistorial();
            if (!r.ok) setHTML($('campanas'), '<p class="pa-vacio">' + esc(r.error) + '</p>');
            if (abierta) detalle(abierta);
            vivoId = act ? String(act.id) : null; vivoCamp = act || null;
            $('vivo').hidden = !act; $('nueva').hidden = !!act;
            if (act) { pintarCabecera(act); cargarDetVivo(); pintarVivo(); }
            else { vivoDet = null; setHTML($('vLogPre'), 'Sin campaña en curso. Aquí aparecen las líneas del ciclo mientras corre.'); setTxt($('vLogMeta'), ''); }
            return true;
        });
    }
    /* v1.4.67: historial agrupado por tarjeta (plegable) y cada campaña plegable; búsqueda por nombre de prueba o tarjeta.
       Lo abierto se recuerda entre refrescos (Set por id). Por defecto se abre la tarjeta y la campaña en curso. */
    var abiertasT = new Set(), abiertasC = new Set(), tocados = new Set();
    function tarjetaDe(c) { return c.tarjeta && c.tarjeta.id_tarjeta_num != null ? String(c.tarjeta.id_tarjeta_num) : '?'; }
    function campanaHTML(c, act) {
        var k = c.conteo, vivo = c.estado === 'activa' || c.estado === 'pausada', id = esc(c.id);
        var abierta_ = abiertasC.has(String(c.id)) || (!tocados.has('c' + c.id) && vivo);
        return '<details class="pa-camp" data-estado="' + esc(c.estado) + '" data-cid="' + id + '"' + (abierta_ ? ' open' : '') + '>' +
            '<summary class="pa-camp-h"><div class="pa-camp-t"><div><b>' + esc(c.nombre) + '</b><span class="pa-badge" data-k="' + (ESTADO_K[c.estado] || 'pend') + '">' +
            esc(vivo ? (c.estado === 'activa' ? 'En curso' : 'Pausada') : ESTADO[c.estado] || c.estado) + '</span></div>' +
            '<p class="pa-camp-meta">' + k.hechos + ' de ' + c.ciclos + ' ciclos · <span class="pa-ok">' + k.aprobados + ' ✓</span> · <span class="pa-bad">' + k.fallidos + ' ✗</span>' +
            (k.no_verificados ? ' · <span class="pa-warn">' + k.no_verificados + ' sin verificar</span>' : '') + ' · ' + esc(fecha(c.creado)) + '</p>' +
            (c.ultimo_fallo ? '<p class="pa-fallo-corto">' + esc(textoFallo(c.ultimo_fallo, true)) + '</p>' : '') + '</div>' +
            '<span class="pa-i pa-chev" data-i="chev" aria-hidden="true"></span></summary>' +
            '<div class="pa-camp-body">' +
            '<p class="pa-camp-meta">' + esc(c.firmware) + ' · ' + (c.tarjeta && c.tarjeta.nombre ? esc(c.tarjeta.nombre) + ' · ' + esc(T.loteEtiqueta(c.tarjeta)) + ' · ' : '') + esc(c.operador) + '</p>' +
            '<div class="pa-barra" role="img" aria-label="' + barraLbl(k, c.ciclos) + '">' + barra(k, c.ciclos) + '</div>' +
            '<div class="pa-res"><span>Pausa ' + esc(c.pausa_s) + ' s · ' + (c.detener_en_falla ? 'se detiene al primer fallo' : 'sigue aunque falle') + '</span></div>' +
            (c.ultimo_fallo ? '<div class="pa-fallo"><b>Por qué falló</b><p>' + esc(textoFallo(c.ultimo_fallo)) + '</p></div>' : '') +
            (c.motivo ? '<p class="pa-motivo">' + esc(c.motivo) + '</p>' : '') +
            '<div class="pa-acc">' +
            (k.hechos ? '<a class="btn pa-link" href="/api/pruebas-auto/campanas/' + id + '/log.txt" download><span class="pa-i" data-i="download" aria-hidden="true"></span>LOG .txt</a>' : '') +
            '<button class="btn" type="button" data-ver="' + id + '" aria-expanded="' + (abierta === String(c.id)) + '" aria-controls="d' + id + '"><span class="pa-i" data-i="list" aria-hidden="true"></span>Ciclos</button>' +
            (vivo ? '' : '<button class="btn" type="button" data-rep="' + id + '"' + (act ? ' disabled title="Termina o detén la campaña en curso para repetir otra"' : ' title="Carga estos mismos datos en «Nueva campaña»"') +
                '><span class="pa-i" data-i="repeat" aria-hidden="true"></span>Repetir</button>') +
            (vivo || !c.mia ? '' : '<button class="btn pa-link pa-del" type="button" data-del="' + id + '" title="Quita esta campaña del historial (sus pruebas siguen en el historial de la tarjeta en Pruebas TQT)"><span class="pa-i" data-i="x" aria-hidden="true"></span><span>Eliminar</span></button>') +
            '</div>' +
            '<div class="pa-ciclos" id="d' + id + '">' + (abierta === String(c.id) && detCache[c.id] ? detCache[c.id] : '') + '</div></div></details>';
    }
    function textoFallo(f, corto) {
        var res = f.resultado === 'no_verificado' ? 'no verificado' : f.resultado === 'interrupted' ? 'interrumpido' : 'falló';
        var et = f.etapa ? 'etapa ' + f.etapa + (f.nombre ? ' «' + f.nombre + '»' : '') : '';
        return corto ? 'Ciclo ' + f.n + ' ' + res + (et ? ' en ' + et : '') + (f.detalle ? ': ' + f.detalle : '')
            : 'Ciclo ' + f.n + ' ' + res + (et ? ' en la ' + et : '') + '. ' + (f.detalle || 'Sin detalle en el reporte; baja el LOG del ciclo.');
    }
    function pintarHistorial() {
        var l = campLista || [], q = ($('hBusca') ? $('hBusca').value : '').trim().toLowerCase();
        var act = l.find(function (c) { return c.estado === 'activa' || c.estado === 'pausada'; });
        var f = q ? l.filter(function (c) {
            return (c.nombre + ' ' + c.firmware + ' ' + tarjetaDe(c) + ' ' + (c.tarjeta && c.tarjeta.nombre || '')).toLowerCase().indexOf(q) >= 0;
        }) : l;
        setTxt($('hCuenta'), q ? f.length + ' de ' + l.length : String(l.length));
        var grupos = {}, orden = [];
        f.forEach(function (c) { var t = tarjetaDe(c); if (!grupos[t]) { grupos[t] = []; orden.push(t); } grupos[t].push(c); });
        setHTML($('campanas'), orden.length ? orden.map(function (t) {
            var cs = grupos[t], ult = cs[0], hayVivo = cs.some(function (c) { return c.estado === 'activa' || c.estado === 'pausada'; });
            var ap = cs.reduce(function (a, c) { return a + c.conteo.aprobados; }, 0), fa = cs.reduce(function (a, c) { return a + c.conteo.fallidos; }, 0);
            var abierto = abiertasT.has(t) || (!tocados.has('t' + t) && (hayVivo || !!q || orden.length === 1));
            return '<details class="pa-tgrupo" data-t="' + esc(t) + '"' + (abierto ? ' open' : '') + '><summary>' +
                '<span class="pa-tg-ico"><span class="pa-i" data-i="board" aria-hidden="true"></span></span>' +
                '<span class="pa-tg-t"><b>Tarjeta ' + esc(t) + '</b><small>' + esc(ult.tarjeta && ult.tarjeta.nombre || '') + '</small></span>' +
                '<span class="pa-tg-res">' + cs.length + ' campaña' + (cs.length === 1 ? '' : 's') + ' · <span class="pa-ok">' + ap + ' ✓</span> · <span class="pa-bad">' + fa + ' ✗</span>' +
                (hayVivo ? ' · <span class="pa-badge" data-k="run">En curso</span>' : ' · última ' + esc(ESTADO[ult.estado] || ult.estado).toLowerCase()) + '</span>' +
                '<span class="pa-i pa-chev" data-i="chev" aria-hidden="true"></span></summary>' +
                '<div class="pa-tg-body">' + cs.map(function (c) { return campanaHTML(c, act); }).join('') + '</div></details>';
        }).join('') : '<p class="pa-vacio">' + (q ? 'Ninguna campaña coincide con «' + esc(q) + '».' : 'Aún no hay campañas. Crea la primera con «Nueva campaña».') + '</p>');
    }
    // recordar lo que el usuario abre/cierra (el evento toggle no burbujea: se captura)
    $('campanas').addEventListener('toggle', function (e) {
        var d = e.target;
        if (d.classList.contains('pa-tgrupo')) { tocados.add('t' + d.dataset.t); d.open ? abiertasT.add(d.dataset.t) : abiertasT.delete(d.dataset.t); }
        else if (d.classList.contains('pa-camp')) { tocados.add('c' + d.dataset.cid); d.open ? abiertasC.add(d.dataset.cid) : abiertasC.delete(d.dataset.cid); }
    }, true);
    if ($('hBusca')) $('hBusca').addEventListener('input', pintarHistorial);
    function tablaCiclos(det) {
        return det.length ? '<table class="pa-tabla"><thead><tr><th scope="col">Ciclo</th><th scope="col">Resultado</th><th scope="col">Inicio</th><th scope="col">Fin</th><th scope="col">Duración</th><th scope="col">Motivo</th><th scope="col">LOG</th></tr></thead><tbody>' +
            det.map(function (x) {
                var fin = x.state === 'finished' || x.state === 'interrupted';
                var res = x.state === 'queued' ? 'En cola' : x.state === 'running' ? 'Probando' : (RES[x.result] || x.result || (x.state === 'interrupted' ? 'Interrumpido' : '—'));
                return '<tr><td>' + x.n + '</td><td data-r="' + esc(x.result || x.state) + '">' + esc(res) + '</td><td>' + fecha(x.created) + '</td><td>' +
                    (fin ? fecha(x.updated) : '—') + '</td><td>' + (fin && x.updated && x.created ? dur(x.updated - x.created) : '—') + '</td><td class="pa-td-motivo">' +
                    (x.motivo ? esc((x.motivo.etapa ? 'Etapa ' + x.motivo.etapa + ' · ' : '') + (x.motivo.detalle || x.motivo.nombre || '')) : x.state === 'interrupted' ? 'Interrumpido' : '—') + '</td><td>' +
                    (fin ? '<a href="/api/pruebas-auto/ciclos/' + esc(x.run) + '/log.txt" download>.txt</a>' : '') + '</td></tr>';
            }).join('') + '</tbody></table>' : '<p class="hint">Esperando el primer ciclo.</p>';
    }
    function detalle(id) {
        return api('/api/pruebas-auto/campanas/' + id).then(function (r) {
            var box = $('d' + id); if (!box) return;
            if (!r.ok) { box.textContent = r.error; return; }
            detCache[id] = tablaCiclos(r.data.ciclos_detalle || []);
            if (abierta === String(id)) setHTML(box, detCache[id]);
        });
    }
    $('campanas').addEventListener('click', function (e) {
        var b = e.target.closest('button'); if (!b) return;
        if (b.dataset.ver) {
            var id = b.dataset.ver;
            abierta = abierta === id ? null : id;
            b.setAttribute('aria-expanded', String(abierta === id));
            if (abierta) detalle(id); else setHTML($('d' + id), '');
            return;
        }
        if (b.dataset.rep) repetir(b.dataset.rep);
        if (b.dataset.del) {
            var lbl = b.querySelector('span:last-child');
            if (!b.dataset.seguro) {
                b.dataset.seguro = '1'; lbl.textContent = 'Confirmar: eliminar del historial';
                setTimeout(function () { delete b.dataset.seguro; lbl.textContent = 'Eliminar'; }, 6000);
                return;
            }
            b.disabled = true;
            api('/api/pruebas-auto/campanas/' + encodeURIComponent(b.dataset.del), { method: 'DELETE' }).then(function (r) {
                T.toast(r.ok ? 'Campaña eliminada del historial.' : r.error, { kind: r.ok ? 'ok' : 'bad' });
                if (!r.ok) b.disabled = false;
                refrescar();
            });
        }
    });

    /* ---- campaña en curso: ciclo, métricas y estimación, etapa actual, 14 etapas en 4 bloques, sensores y registro ---- */
    var vivoId = null, vivoCamp = null, vivoDet = null, PASOS = [], HELP = {}, ERRS = {};
    var ST = { aprobado: 'ok', fallido: 'bad', no_verificado: 'nv', ejecutando: 'run' };
    var ST_TXT = { ok: 'Aprobada', bad: 'Falló', nv: 'No verificada', run: 'En curso', pend: 'Pendiente' };
    var GRUPOS = [
        { t: 'Identificación y estado inicial', i: [0, 1] },
        { t: 'R1 por serial', i: [2, 3, 4, 5] },
        { t: 'R1 por Bluetooth', i: [6, 7, 8, 9, 10] },
        { t: 'R2 por Bluetooth', i: [11, 12, 13] },
    ];
    var LBL = {
        ON: { 0: 'Cierre inactivo', 1: 'Cierre activo' },
        OFF: { 0: 'Apertura inactiva', 1: 'Apertura activa' },
        PB: { 0: 'Sistema', 1: 'Serial / plataforma', 2: 'Bluetooth' },
        TQT: { 0: 'En espera', 1: 'Abriendo', 2: 'Abierto', 3: 'Cerrando', 4: 'Cerrado', 5: 'Error' },
    };
    var grupoAuto = -1, ultimoVivo = null;
    /* v1.4.66: por dónde va cada etapa. 1–6: terminal serial a R1 (la Raspberry escribe por el USB-serial);
       7–11: Bluetooth a R1; 12: cambia de R1 a R2; 13–14: Bluetooth a R2 (R1 solo observa por serial). */
    function canal(i) {
        if (i <= 5) return { c: 'serial', t: i <= 1 ? 'Terminal serial · R1' : 'Terminal serial → R1', title: 'Comando por el puerto serie (USB) de la Raspberry a la R1' };
        if (i <= 10) return { c: 'ble', t: i === 6 ? 'Bluetooth · conecta R1' : 'Bluetooth → R1', title: 'Comando por el Bluetooth de la Raspberry a la R1; la confirmación llega por serial' };
        return { c: 'ble', t: i === 11 ? 'Bluetooth · cambia a R2' : 'Bluetooth → R2', title: 'Comando por el Bluetooth de la Raspberry a la R2; la R1 lo reporta por serial' };
    }
    function chipCanal(i) {
        var k = canal(i);
        return '<span class="pa-canal" data-c="' + k.c + '" title="' + esc(k.title) + '"><span class="pa-i" data-i="' + (k.c === 'serial' ? 'cable' : 'bluetooth') + '" aria-hidden="true"></span>' + esc(k.t) + '</span>';
    }
    function nombrePaso(i) { return (PASOS[i] || 'Etapa ' + (i + 1)); }
    function nombreCorto(i) { return nombrePaso(i).replace(/^R[12] (serial|BLE) · /, ''); }
    function construirGrupos() {
        $('vGrupos').innerHTML = GRUPOS.map(function (g, gi) {
            return '<details class="pa-group" id="g' + gi + '" data-k="pend"><summary>' +
                '<span class="pa-group-num" aria-hidden="true">' + String(gi + 1).padStart(2, '0') + '</span>' +
                '<span class="pa-group-title"><b>' + esc(g.t) + '</b><small>Etapas ' + (g.i[0] + 1) + '–' + (g.i[g.i.length - 1] + 1) + '</small></span>' +
                '<span class="pa-group-count" id="gc' + gi + '">0/' + g.i.length + '</span></summary>' +
                '<ol class="pa-steps">' + g.i.map(function (i) {
                    return '<li class="pa-step" id="st' + i + '" data-k="pend"><span class="pa-ind" data-n="' + (i + 1) + '" aria-hidden="true"></span>' +
                        '<div class="pa-step-body"><div class="pa-step-top"><span class="pa-step-name-wrap"><span class="pa-step-name">' + (i + 1) + '. ' + esc(nombreCorto(i)) + '</span>' + chipCanal(i) + '</span>' +
                        '<span class="pa-step-state">Pendiente</span></div><span class="pa-step-detail"></span></div></li>';
                }).join('') + '</ol></details>';
        }).join('');
        grupoAuto = -1;
        if (ultimoVivo) pintarEtapas(ultimoVivo);
    }
    construirGrupos();
    fetch('/static/js/test_station_contract.json?v=1400').then(function (r) { return r.json(); }).then(function (d) {
        PASOS = d.step_names || []; HELP = d.help || {}; ERRS = d.errors || {}; construirGrupos();
    }).catch(function () {});

    function pintarCabecera(c) {
        var k = c.conteo, pausada = c.estado === 'pausada';
        $('vivo').dataset.k = c.estado;
        setTxt($('vNombre'), c.nombre);
        setTxt($('vEyebrow'), pausada ? 'Campaña en pausa' : 'Campaña en curso');
        var est = $('vEstado'); est.dataset.k = pausada ? 'warn' : 'run'; setTxt(est, pausada ? 'Pausada' : 'Activa');
        setTxt($('vMeta'), 'Tarjeta ' + (c.tarjeta ? c.tarjeta.id_tarjeta_num : '?') + (c.tarjeta && c.tarjeta.nombre ? ' (' + c.tarjeta.nombre + ')' : '') +
            ' · ' + c.firmware + ' · ' + c.operador + ' · iniciada ' + fecha(c.creado) + ' · pausa ' + c.pausa_s + ' s' + (c.detener_en_falla ? ' · se detiene al primer fallo' : ''));
        var puedo = c.mia !== false;   // v1.4.77: historial compartido; solo el dueño o un administrador actúa
        Array.prototype.forEach.call($('vivo').querySelectorAll('[data-a]'), function (x) { x.hidden = !puedo; });
        var bp = $('vPausa');
        if (!bp.disabled) {
            bp.dataset.a = pausada ? 'reanudar' : 'pausar';
            bp.querySelector('.pa-i').dataset.i = pausada ? 'play' : 'pause';
            setTxt(bp.querySelector('span:last-child'), pausada ? 'Reanudar' : 'Pausar');
            bp.title = pausada ? 'Vuelve a encolar ciclos' : 'Termina el ciclo actual y no encola otro hasta reanudar';
        }
        $('vLogTxt').href = '/api/pruebas-auto/campanas/' + encodeURIComponent(c.id) + '/log.txt';
        $('vLogTxt').hidden = !k.hechos;
        setTxt($('vTotal'), String(c.ciclos));
        setTxt($('vAprob'), String(k.aprobados)); setTxt($('vFall'), String(k.fallidos)); setTxt($('vNv'), String(k.no_verificados));
        var b = $('vBarra'); setHTML(b, barra(k, c.ciclos)); b.setAttribute('aria-label', barraLbl(k, c.ciclos));
        estimar();
    }
    function cargarDetVivo() {
        var id = vivoId;
        api('/api/pruebas-auto/campanas/' + id).then(function (r) {
            if (id !== vivoId || !r.ok) return;
            vivoDet = r.data.ciclos_detalle || [];
            if (abierta === id) { detCache[id] = tablaCiclos(vivoDet); var box = $('d' + id); if (box) setHTML(box, detCache[id]); }
            estimar();
        });
    }
    // estimación: duración media de los ciclos terminados + la pausa configurada por cada ciclo que falta
    function estimar() {
        var c = vivoCamp; if (!c) return;
        var det = vivoDet || [], ahora = Date.now() / 1000;
        var fin = det.filter(function (x) { return (x.state === 'finished' || x.state === 'interrupted') && x.updated > x.created; });
        if (!fin.length) { setTxt($('vMedia'), '—'); setTxt($('vResta'), '—'); setTxt($('vEstim'), 'La estimación de tiempo aparece al terminar el primer ciclo.'); return; }
        var media = fin.reduce(function (s, x) { return s + (x.updated - x.created); }, 0) / fin.length;
        var enCurso = det.find(function (x) { return x.state === 'running'; });
        var faltan = Math.max(0, c.ciclos - c.conteo.hechos - (enCurso ? 1 : 0));
        var resta = faltan * (media + (+c.pausa_s || 0)) + (enCurso ? Math.max(0, media - (ahora - enCurso.created)) : 0);
        setTxt($('vMedia'), dur(media));
        setTxt($('vResta'), resta > 0 ? '≈ ' + dur(resta) : 'último ciclo');
        setTxt($('vEstim'), c.estado === 'pausada' ? 'En pausa: la estimación corre de nuevo al reanudar.'
            : 'Estimación con la media de ' + fin.length + (fin.length === 1 ? ' ciclo' : ' ciclos') + ' y la pausa de ' + c.pausa_s + ' s · fin aproximado ' +
              new Date((ahora + resta) * 1000).toLocaleString('es-MX', { weekday: 'short', hour: '2-digit', minute: '2-digit' }));
    }
    function pintarEtapas(v) {
        var p = v.pasos || {}, idxRun = -1;
        for (var i = 0; i < 14; i++) {
            var li = $('st' + i); if (!li) continue;
            var e = p[i] ? (ST[p[i].estado] || 'pend') : 'pend';
            if (e === 'run') idxRun = i;
            li.dataset.k = e;
            setTxt(li.querySelector('.pa-step-state'), ST_TXT[e]);
            setTxt(li.querySelector('.pa-step-detail'), p[i] && p[i].detalle ? p[i].detalle : '');
            li.title = (i + 1) + '. ' + nombrePaso(i);
        }
        GRUPOS.forEach(function (g, gi) {
            var ks = g.i.map(function (i) { return p[i] ? (ST[p[i].estado] || 'pend') : 'pend'; });
            var hechos = ks.filter(function (k) { return k === 'ok' || k === 'nv' || k === 'bad'; }).length;
            var k = ks.indexOf('bad') >= 0 ? 'bad' : ks.indexOf('run') >= 0 ? 'run' : hechos === ks.length ? 'ok' : 'pend';
            var d = $('g' + gi); d.dataset.k = k;
            setTxt($('gc' + gi), hechos + '/' + ks.length);
            if (k === 'bad' && !d.dataset.auto) { d.open = true; d.dataset.auto = '1'; }
        });
        // abre solo el bloque que se está ejecutando (y cierra el que se abrió solo antes); lo que abra la persona se respeta
        var gRun = idxRun < 0 ? -1 : GRUPOS.findIndex(function (g) { return g.i.indexOf(idxRun) >= 0; });
        if (gRun >= 0 && gRun !== grupoAuto) {
            if (grupoAuto >= 0 && $('g' + grupoAuto).dataset.k !== 'bad') $('g' + grupoAuto).open = false;
            $('g' + gRun).open = true; grupoAuto = gRun;
        }
        return idxRun;
    }
    function pintarSensores(sn) {
        if (!sn) { setHTML($('vSens'), '<p class="hint">Sin lectura de sensores todavía.</p>'); return; }
        var on = sn.ON, off = sn.OFF;
        var perno = on === '1' && off === '0' ? ['cerrado', 'Perno cerrado'] : on === '0' && off === '1' ? ['abierto', 'Perno abierto']
            : on === '1' && off === '1' ? ['err', 'Conflicto: ambos sensores activos'] : ['mov', 'En movimiento o sin confirmar'];
        function tile(key, nombre, sub, err) {
            var v = sn[key] == null || sn[key] === '' ? '—' : String(sn[key]);
            return '<dl class="pa-sensor"' + (err ? ' data-k="err"' : '') + ' title="' + esc(HELP[key] || key) + '"><dt>' + esc(nombre) + '</dt><dd>' + esc(v) + '</dd><small>' + esc(sub || '') + '</small></dl>';
        }
        var err = String(sn.err == null ? '' : sn.err);
        setHTML($('vSens'),
            '<dl class="pa-sensor pa-perno" data-k="' + perno[0] + '" title="Posición deducida de los sensores ON (cierre) y OFF (apertura)"><dt>Posición del perno</dt><dd>' + esc(perno[1]) + '</dd>' +
            '<small>ON ' + esc(on == null ? '—' : on) + ' · OFF ' + esc(off == null ? '—' : off) + '</small></dl>' +
            tile('ON', 'ON · sensor de cierre', LBL.ON[on]) +
            tile('OFF', 'OFF · sensor de apertura', LBL.OFF[off]) +
            tile('TQT', 'TQT · estado', LBL.TQT[sn.TQT], sn.TQT === '5') +
            tile('MOV', 'MOV · movimientos', 'Contador de movimientos') +
            tile('err', 'err · último error', ERRS[err] || (err ? 'Código ' + err : 'Sin lectura'), err === '3' || err === '4') +
            tile('PB', 'PB · origen', LBL.PB[sn.PB]));
    }
    function pintarLog(v, ci) {
        var pre = $('vLogPre'), abajo = pre.scrollTop + pre.clientHeight >= pre.scrollHeight - 8;
        var l = v.log || [];
        setHTML(pre, l.length ? l.map(function (x) {
            var m = /^\S+T(\d\d:\d\d:\d\d)\.?\d*\S*\s\|\s(.*)$/.exec(x);
            var t = m ? '<span class="t">' + m[1] + '</span> ' : '', txt = m ? m[2] : x;
            return '<span' + (/fall|error|✗/i.test(txt) ? ' class="e"' : '') + '>' + t + esc(txt) + '</span>';
        }).join('\n') : 'Esperando las primeras líneas del ciclo…');
        if (abajo) pre.scrollTop = pre.scrollHeight;
        setTxt($('vLogMeta'), (ci ? 'Ciclo ' + ci.n + ' · ' : '') + 'actualizado ' + hora(Date.now() / 1000));
    }
    function pintarVivo() {
        if (!vivoId) return;
        var id = vivoId;
        api('/api/pruebas-auto/campanas/' + id + '/vivo').then(function (r) {
            if (id !== vivoId) return;
            if (!r.ok) { setTxt($('vEtapaN'), ''); setTxt($('vEtapaT'), r.error || 'No se pudo leer la campaña.'); $('vEtapa').dataset.k = 'bad'; return; }
            var v = r.data, ci = v.ciclo, p = v.pasos || {};
            ultimoVivo = v;
            setTxt($('vCiclo'), String(ci ? ci.n : 0));
            if (v.ciclos) setTxt($('vTotal'), String(v.ciclos));
            var idx = pintarEtapas(v), fallo = -1;
            Object.keys(p).forEach(function (k) { if (p[k].estado === 'fallido') fallo = +k; });
            var box = $('vEtapa');
            if (idx >= 0) {
                box.dataset.k = 'run';
                setTxt($('vEtapaN'), 'Etapa ' + (idx + 1) + ' de 14 · ' + GRUPOS.find(function (g) { return g.i.indexOf(idx) >= 0; }).t);
                setTxt($('vEtapaT'), nombrePaso(idx));
                setTxt($('vEtapaD'), p[idx].detalle || '');
                $('vEtapaC').innerHTML = chipCanal(idx);
            } else if (fallo >= 0 && ci && ci.state === 'running') {
                box.dataset.k = 'bad';
                setTxt($('vEtapaN'), 'Ciclo ' + ci.n + ' · etapa ' + (fallo + 1) + ' falló');
                setTxt($('vEtapaT'), nombrePaso(fallo));
                setTxt($('vEtapaD'), p[fallo].detalle || '');
                $('vEtapaC').innerHTML = chipCanal(fallo);
            } else {
                $('vEtapaC').innerHTML = '';
                box.dataset.k = 'pend';
                setTxt($('vEtapaN'), ci ? 'Ciclo ' + ci.n : 'Sin ciclos todavía');
                // v1.4.71: entre ciclos, cuenta atrás hasta el siguiente (fin del ciclo + pausa configurada)
                var entre = v.estado === 'activa' && ci && ci.state !== 'queued' && ci.state !== 'running' && ci.updated;
                pausa = entre && (!v.ciclos || ci.n < v.ciclos)
                    ? { n: ci.n + 1, hasta: (ci.updated + (+(vivoCamp && vivoCamp.pausa_s) || 0)) * 1000, seg: +(vivoCamp && vivoCamp.pausa_s) || 0 } : null;
                if (pausa) { box.dataset.k = 'wait'; tickPausa(); }
                else {
                    setTxt($('vEtapaT'), ci && ci.state === 'queued' ? 'Ciclo en cola: esperando a la Raspberry…'
                        : ci && ci.state === 'running' ? 'Preparando el ciclo…'
                        : v.estado === 'pausada' ? 'Pausada: no se encola otro ciclo hasta reanudar.'
                        : entre ? 'Último ciclo terminado: cerrando la campaña…' : 'Entre ciclos.');
                    setTxt($('vEtapaD'), v.motivo || '');
                }
            }
            // v1.4.80: solo un ciclo en marcha cancela la cuenta atrás; un ciclo ya terminado con etapa fallida seguía
            // borrándola y el temporizador de 1 s ocultaba la barra hasta el siguiente sondeo (parpadeo)
            if (idx >= 0 || (fallo >= 0 && ci && ci.state === 'running')) pausa = null;
            pintarSensores(v.sensores);
            pintarBarra(v, ci, idx);
            pintarLog(v, ci);
            estimar();
        });
    }
    /* v1.4.66: barra fija con «Detener ahora» y «Detener al terminar el ciclo», visible al desplazarse */
    function pintarBarra(v, ci, idx) {
        var bar = $('vBarra');
        if (!bar) {
            bar = document.createElement('div');
            bar.id = 'vBarra'; bar.className = 'pa-stopbar'; bar.setAttribute('role', 'region'); bar.setAttribute('aria-label', 'Detener la campaña');
            bar.innerHTML = '<div class="pa-stopbar-txt"><b id="vBarraT"></b><span id="vBarraS"></span></div>' +
                '<button class="btn" type="button" data-a="detener" title="Termina el ciclo actual y no inicia otro"><span class="pa-i" data-i="stop" aria-hidden="true"></span><span>Detener al terminar el ciclo</span></button>' +
                '<button class="btn pa-btn-danger" type="button" data-a="detener_ahora" title="Cancela el ciclo en curso; el firmware termina el movimiento actual"><span class="pa-i" data-i="alert" aria-hidden="true"></span><span>Detener ahora</span></button>';
            $('vivo').appendChild(bar);   // dentro de #vivo: usa el mismo manejador de clics y se oculta con él
            document.querySelector('.pa-main') && document.querySelector('.pa-main').classList.add('pa-main-pad');
        }
        setTxt($('vBarraT'), (v.estado === 'pausada' ? 'Pausada' : 'En curso') + ' · ciclo ' + (ci ? ci.n : 0) + ' de ' + (v.ciclos || '?'));
        setTxt($('vBarraS'), idx >= 0 ? 'Etapa ' + (idx + 1) + ' de 14 · ' + nombrePaso(idx) + ' · ' + canal(idx).t
            : pausa ? textoPausa() : (ci && ci.state === 'queued' ? 'Ciclo en cola' : 'Entre ciclos'));
    }
    /* v1.4.71: cuenta atrás de la pausa entre ciclos (se actualiza cada segundo sin pedir nada al servidor) */
    var pausa = null;
    function mmss(seg) { seg = Math.max(0, Math.round(seg)); return Math.floor(seg / 60) + ':' + String(seg % 60).padStart(2, '0'); }
    function textoPausa() {
        var r = (pausa.hasta - Date.now()) / 1000;
        return r > 0 ? 'Siguiente ciclo (' + pausa.n + ') en ' + mmss(r) : 'Iniciando el ciclo ' + pausa.n + '…';
    }
    function tickPausa() {
        if (!pausa) return;
        var r = (pausa.hasta - Date.now()) / 1000;
        setTxt($('vEtapaN'), 'Pausa entre ciclos · ' + pausa.seg + ' s');
        setTxt($('vEtapaT'), r > 0 ? 'El ciclo ' + pausa.n + ' empieza en ' + mmss(r) : 'Iniciando el ciclo ' + pausa.n + ': esperando a la Raspberry…');
        setTxt($('vEtapaD'), r > 0 ? 'Hacia las ' + new Date(pausa.hasta).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) +
            '. «Detener al terminar el ciclo» evita que empiece.' : 'La Raspberry lo toma en su próxima consulta (unos segundos).');
        var bar = $('vPausaBar');
        if (bar) { bar.hidden = false; bar.style.width = (pausa.seg ? Math.min(100, 100 * (1 - Math.max(0, r) / pausa.seg)) : 100) + '%'; }
        if ($('vBarraS')) setTxt($('vBarraS'), textoPausa());
    }
    setInterval(function () {
        if (pausa && !document.hidden) tickPausa();
        else if (!pausa && $('vPausaBar')) $('vPausaBar').hidden = true;
    }, 1000);
    var ACC_OK = {
        pausar: 'Campaña pausada: el ciclo actual termina y no se encola otro hasta reanudar.',
        reanudar: 'Campaña reanudada.',
        detener: 'Campaña detenida; el ciclo actual termina y no se inicia otro.',
        detener_ahora: 'Campaña detenida; se canceló el ciclo en curso.',
    };
    $('vivo').addEventListener('click', function (e) {
        var b = e.target.closest('button[data-a]'); if (!b || !vivoId) return;
        var a = b.dataset.a, lbl = b.querySelector('span:last-child');
        if (a === 'detener_ahora' && !b.dataset.seguro) {   // confirmación en dos pasos, sin confirm()
            b.dataset.seguro = '1'; lbl.textContent = 'Confirmar: cancelar el ciclo en curso';
            setTimeout(function () { delete b.dataset.seguro; lbl.textContent = 'Detener ahora'; }, 6000);
            return;
        }
        delete b.dataset.seguro; if (a === 'detener_ahora') lbl.textContent = 'Detener ahora';
        b.disabled = true;
        api('/api/pruebas-auto/campanas/' + encodeURIComponent(vivoId) + '/accion', { method: 'POST', body: { accion: a } }).then(function (r) {
            b.disabled = false;
            T.toast(r.ok ? ACC_OK[a] : r.error, { kind: r.ok ? 'ok' : 'bad' });
            refrescar();
        });
    });
    $('vVerCiclos').addEventListener('click', function () {
        if (!vivoId) return;
        abierta = vivoId;
        campanas().then(function () {
            var box = $('d' + vivoId); if (!box) return;
            box.closest('.pa-camp').scrollIntoView({ behavior: REDUCIDO ? 'auto' : 'smooth', block: 'start' });
        });
    });

    /* ---- log del agente ---- */
    function verLog() {
        api('/api/pruebas-auto/agente/log').then(function (r) {
            if (!r.ok) { $('lMeta').textContent = r.error; return; }
            var pre = $('lTexto'), abajo = pre.scrollTop + pre.clientHeight >= pre.scrollHeight - 8;
            var txt = r.data.texto || '';
            logTexto = txt;
            var mk = marcaLog(), desde = 0;
            if (mk) { var i = txt.lastIndexOf(mk); desde = i >= 0 ? i + mk.length : 0; }
            var vis = txt.slice(desde).replace(/^\n+/, '');
            $('lTodo').hidden = !mk;
            if (vis) pre.innerHTML = terminal(vis);
            else pre.textContent = mk ? 'Vista limpia. Aquí aparecerán las líneas nuevas del agente (pulsa «Traer log»).' : '';
            if (abajo) pre.scrollTop = pre.scrollHeight;
            $('lMeta').textContent = r.data.ts ? 'Recibido ' + hace(r.data.ts) : '';
        });
    }
    /* v1.4.73: terminal legible: líneas repetidas seguidas se agrupan («× 23»), color por tipo (error, conexión,
       arranque/actualización, puerto) y opción de ocultar los reintentos de conexión con el servidor. */
    var CLAVE_RED = 'pa.log.sinred';
    function sinRed() { try { return localStorage.getItem(CLAVE_RED) === '1'; } catch (e) { return false; } }
    function tipoLinea(l) {
        if (/^Reporte\/conexión pendiente|urlopen error|timed out|Bad Gateway|name resolution/i.test(l)) return 'red';
        if (/Traceback|Error|ERROR|RuntimeError|eliminado desde la web/.test(l)) return 'bad';
        if (/Autoactualización|iniciado en/.test(l)) return 'ok';
        if (/Puerto serie|puerto|BLE|Bluetooth/i.test(l)) return 'info';
        if (/^\s+(File |\^|~)/.test(l)) return 'bad';
        return '';
    }
    function terminal(txt) {
        var lineas = txt.split('\n'), out = [], ocultas = 0, filtrar = sinRed();
        lineas = lineas.slice(-1500);
        for (var i = 0; i < lineas.length; i++) {
            var l = lineas[i]; if (!l.trim()) continue;
            var k = tipoLinea(l);
            if (filtrar && k === 'red') { ocultas++; continue; }
            var n = 1; while (i + 1 < lineas.length && lineas[i + 1] === l) { n++; i++; }
            var m = /^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\s+(.*)$/.exec(l);
            out.push('<span class="pa-tl" data-k="' + k + '">' + (m ? '<span class="pa-tl-ts">' + esc(m[1]) + '</span> ' + esc(m[2]) : esc(l)) +
                (n > 1 ? ' <span class="pa-tl-rep">× ' + n + '</span>' : '') + '</span>');
        }
        if (ocultas) out.unshift('<span class="pa-tl" data-k="nota">' + ocultas + ' líneas de reintento de conexión ocultas</span>');
        return out.slice(-400).join('');   // cada línea es un bloque: sin saltos extra
    }
    $('lRed').checked = sinRed();
    $('lRed').addEventListener('change', function () {
        try { localStorage.setItem(CLAVE_RED, this.checked ? '1' : '0'); } catch (e) { /* nada */ }
        verLog();
    });
    /* v1.4.67: «Limpiar» vacía la vista: se recuerda el final actual del log (en este navegador) y solo se muestran las
       líneas nuevas. «Mostrar todo» lo deshace. No borra nada en la Raspberry ni en el servidor (el .txt sigue completo). */
    var logTexto = '', CLAVE_LOG = 'pa.log.limpio';
    function marcaLog() { try { return localStorage.getItem(CLAVE_LOG) || ''; } catch (e) { return ''; } }
    $('lLimpiar').addEventListener('click', function () {
        var mk = logTexto.slice(-240);
        try { if (mk) localStorage.setItem(CLAVE_LOG, mk); } catch (e) { /* sin almacenamiento: solo se vacía ahora */ }
        $('lTexto').textContent = 'Vista limpia. Aquí aparecerán las líneas nuevas del agente (pulsa «Traer log»).';
        $('lTodo').hidden = false;
    });
    $('lTodo').addEventListener('click', function () {
        try { localStorage.removeItem(CLAVE_LOG); } catch (e) { /* nada */ }
        verLog();
    });
    $('lPedir').addEventListener('click', function () {
        api('/api/pruebas-auto/agente/log', { method: 'POST' }).then(function (r) {
            if (!r.ok) { T.toast(r.error, { kind: 'bad' }); return; }
            esperaLog = Date.now() - 1000;
            $('lMeta').textContent = r.data.en_linea ? 'Pidiendo el log a la Raspberry…' : 'La Raspberry está sin señal: el log llegará cuando vuelva.';
        });
    });

    function refrescar() {
        return Promise.all([cargarBanco(), campanas()]).then(function (v) { pintarReq(v[0]); });
    }
    refrescar(); verLog();
    setInterval(function () { if (!document.hidden) refrescar(); }, 5000);
    setInterval(function () { if (!document.hidden && vivoId) pintarVivo(); }, 2000);
    document.addEventListener('visibilitychange', function () { if (!document.hidden) refrescar(); });
})();
