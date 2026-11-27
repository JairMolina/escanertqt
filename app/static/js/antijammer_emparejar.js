/* antijammer_emparejar.js - Emparejar (consola Skudo AntiJammer, v1.4.103): cada equipo es una placa RX + una TX (sin R1/R2/R3).
 * Escanea o elige dos placas; la primera va a RX y la segunda a TX (o la ranura activa). Las placas que ya tienen RX/TX en
 * Materiales van solas a su ranura. Deshacer conserva el RX/TX de cada placa.
 * v1.4.104: cada pareja tiene un NÚMERO (el que se le da al programar; aquí se puede escribir a mano o usar el siguiente libre).
 * Una pareja incompleta (solo RX o solo TX, de Programar) se completa eligiendo su placa y la que falta.
 * v1.4.105: botón «Número» en cada pareja para cambiar su número a mano (el orden de emparejado no es el número real).
 * API: GET /api/antijammer/parejas?mes=AAAA-MM · POST /api/antijammer/parejas {rx, tx, numero} · PUT /api/antijammer/parejas/{id} {numero}
 *      · DELETE /api/antijammer/parejas/{id} */
(function () {
    'use strict';
    const T = window.TQT, P = window.AJ;
    const { h, icon, api } = T;
    const $ = (id) => document.getElementById(id);
    const MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];
    const nomMes = (m) => { const [a, n] = String(m).split('-'); return `${MESES[(+n || 1) - 1]} ${a}`; };
    let sec = null, datos = null, mes = null, activa = 'rx', fijada = false, viejo = false, seq = 0;
    const sel = { rx: null, tx: null };

    function ranura(k) {
        const p = sel[k], etiqueta = k.toUpperCase();
        return h('button', {
            class: 'ep-ranura ep-' + k + (activa === k ? ' activa' : ''), type: 'button', 'aria-pressed': String(activa === k),
            'aria-label': p ? `${etiqueta}: ${p.nombre}. Pulsa para cambiarla` : `${etiqueta}: vacía. Pulsa para elegirla`,
            onclick: () => { activa = k; fijada = true; pintar(); $('epCod').focus(); },
        },
            h('span', { class: 'ep-k' }, etiqueta),
            p ? h('b', { class: 'mono' }, p.nombre) : h('span', { class: 'ep-vacia' }, 'Escanea o elige una placa'),
            p ? h('span', { class: 'ep-quitar', role: 'button', tabindex: '0', 'aria-label': `Quitar ${p.nombre}`,
                onclick: (e) => { e.stopPropagation(); sel[k] = null; activa = k; pintar(); } }, icon('x')) : null);
    }

    function poner(p) {
        if (!p) return;
        ['rx', 'tx'].forEach((x) => { if (sel[x] && sel[x].id === p.id) sel[x] = null; });
        // ranura pulsada a mano > RX/TX ya asignado en Materiales > la ranura vacía (primero RX)
        let k = fijada ? activa : p.tipo === 'RX' ? 'rx' : p.tipo === 'TX' ? 'tx' : (sel[activa] ? (sel.rx ? 'tx' : 'rx') : activa);
        sel[k] = p; fijada = false;
        activa = !sel.rx ? 'rx' : !sel.tx ? 'tx' : k;
        pintar();
    }

    async function leer(texto) {
        const c = String(texto || '').trim();
        const msg = $('epMsg');
        if (!c) return null;
        const ajeno = P.ajeno(c);
        if (ajeno) { msg.textContent = ajeno; P.sonar && P.sonar(false); return { ok: false, texto: ajeno }; }
        const r = await P.porCodigo(c);
        if (!r.ok) { msg.textContent = (r.error || 'No se encontró la placa') + '.'; return { ok: false, texto: msg.textContent }; }
        const pcb = r.data.pcb;
        const suelta = ((datos && datos.sin_pareja) || []).find((x) => x.id === pcb.id);
        const par = !suelta && datos && datos.parejas.find((x) => (x.rx && x.rx.id === pcb.id) || (x.tx && x.tx.id === pcb.id));
        if (par && par.completa) { msg.textContent = `${pcb.nombre} ya está en la pareja ${par.numero}. Deshazla primero.`; return { ok: false, texto: msg.textContent }; }
        msg.textContent = '';
        if (par) { completar(par); return { ok: true, texto: `Pareja ${par.numero}: falta la ${par.rx ? 'TX' : 'RX'}` }; }
        poner(suelta || { id: pcb.id, nombre: pcb.nombre, tipo: '' });
        return { ok: true, texto: `${pcb.nombre} lista` };
    }

    /** Pareja incompleta de Programar: su placa va a su ranura con su número; falta elegir la otra. */
    function completar(par) {
        const k = par.rx ? 'rx' : 'tx', otra = k === 'rx' ? 'tx' : 'rx';
        sel[k] = Object.assign({}, par[k], { tipo: k.toUpperCase() });
        if (sel[otra] && sel[otra].id === sel[k].id) sel[otra] = null;
        $('epNum').value = par.numero; activa = otra; fijada = false;
        pintar(); $('epCod').focus();
    }

    async function emparejar() {
        if (!sel.rx || !sel.tx || P.soloLectura()) return;
        const n = $('epNum').value.trim();
        if (n && !/^\d{1,4}$/.test(n)) { $('epNum').setAttribute('aria-invalid', 'true'); $('epMsg').textContent = 'El número de pareja va de 1 a 9999.'; $('epNum').focus(); return; }
        const b = $('epOk'); b.disabled = true;
        const body = { rx: '#' + sel.rx.id, tx: '#' + sel.tx.id };
        if (n) body.numero = +n;
        const r = await api('/api/antijammer/parejas', { method: 'POST', body });
        b.disabled = false;
        if (!r.ok) { $('epMsg').textContent = (r.error || 'No se pudo emparejar') + '.'; return; }
        T.toast(`Pareja ${r.data.numero}: ${sel.rx.nombre} (RX) + ${sel.tx.nombre} (TX)`, { kind: 'ok' });
        sel.rx = sel.tx = null; activa = 'rx'; $('epNum').value = '';
        P.cambio(); cargar();
    }

    function deshacer(par) {
        if (P.soloLectura()) return;
        T.sheet({
            title: `Deshacer la pareja ${par.numero}`,
            body: [h('p', null, `${[par.rx && par.rx.nombre + ' (RX)', par.tx && par.tx.nombre + ' (TX)'].filter(Boolean).join(' y ')} quedan sin pareja ni número. Cada placa conserva si es RX o TX.`)],
            actions: [
                { label: 'Cancelar', kind: 'ghost', onClick: () => true },
                { label: `Deshacer pareja ${par.numero}`, kind: 'danger', icon: 'unlink', onClick: async () => {
                    const r = await api('/api/antijammer/parejas/' + par.id, { method: 'DELETE' });
                    if (!r.ok) { T.toast((r.error || 'No se pudo deshacer la pareja') + '. Inténtalo otra vez.', { kind: 'bad' }); return false; }
                    T.toast(`Pareja ${par.numero} deshecha`, { kind: 'ok' });
                    P.cambio(); cargar();
                    return true;
                } },
            ],
        });
    }

    /** v1.4.105: cambiar a mano el número de una pareja (PUT /api/antijammer/parejas/{id} {numero}). */
    function renumerar(par) {
        if (P.soloLectura()) return;
        const inp = h('input', { class: 'input mono', id: 'epRenum', type: 'text', inputmode: 'numeric', pattern: '[0-9]*', maxlength: '4',
            autocomplete: 'off', value: String(par.numero), 'aria-describedby': 'epRenumAy', 'data-escribe': '' });
        const err = h('p', { class: 'ayuda', id: 'epRenumAy', 'aria-live': 'polite' },
            'De 1 a 9999. Si otra pareja incompleta ya tiene ese número y le falta justo esta placa, se unen.');
        const nombres = [par.rx && par.rx.nombre + ' (RX)', par.tx && par.tx.nombre + ' (TX)'].filter(Boolean).join(' y ');
        const guardar = async () => {
            const v = inp.value.trim();
            if (!/^\d{1,4}$/.test(v) || +v < 1) { inp.setAttribute('aria-invalid', 'true'); err.textContent = 'Escribe un número de 1 a 9999.'; inp.focus(); return false; }
            if (+v === par.numero) return true;
            const r = await api('/api/antijammer/parejas/' + par.id, { method: 'PUT', body: { numero: +v } });
            if (!r.ok) { inp.setAttribute('aria-invalid', 'true'); err.textContent = (r.error || 'No se pudo cambiar el número') + '.'; inp.focus(); return false; }
            T.toast(`Pareja ${par.numero} ahora es la pareja ${r.data.numero}`, { kind: 'ok' });
            P.cambio(); cargar();
            return true;
        };
        inp.addEventListener('input', () => inp.removeAttribute('aria-invalid'));
        const hoja = T.sheet({
            title: `Cambiar el número de la pareja ${par.numero}`,
            body: [h('p', null, nombres + '. La etiqueta DYMO toma el número nuevo al imprimirla.'),
                h('div', { class: 'field' }, h('label', { for: 'epRenum' }, 'Número nuevo'), inp, err)],
            actions: [
                { label: 'Cancelar', kind: 'ghost', onClick: () => true },
                { label: 'Guardar número', kind: 'primary', icon: 'check', onClick: guardar },
            ],
        });
        inp.addEventListener('keydown', async (e) => { if (e.key === 'Enter') { e.preventDefault(); if (await guardar()) hoja.close(); } });
        setTimeout(() => { try { inp.select(); } catch (e) { /* nada */ } }, 40);
    }

    function pintar() {
        if (!datos) return;
        const ro = P.soloLectura();
        const elegidas = new Set([sel.rx && sel.rx.id, sel.tx && sel.tx.id]);
        $('epRanuras').replaceChildren(ranura('rx'), h('span', { class: 'ep-union', 'aria-hidden': 'true' }, icon('link')), ranura('tx'));
        $('epOk').disabled = ro || !(sel.rx && sel.tx);
        $('epNum').placeholder = String(datos.siguiente || '');
        $('epNum').disabled = ro;
        const sueltas = datos.sin_pareja.filter((p) => !elegidas.has(p.id));
        const nRx = datos.sin_pareja.filter((p) => p.tipo === 'RX').length, nTx = datos.sin_pareja.filter((p) => p.tipo === 'TX').length;
        $('epSueltasT').textContent = `Sin pareja · ${datos.sin_pareja.length}` + (nRx || nTx ? ` (${nRx} RX, ${nTx} TX)` : '');
        $('epSueltas').replaceChildren(sueltas.length
            ? h('ul', { class: 'ep-chips' }, sueltas.map((p) => h('li', null, h('button', {
                class: 'ep-chip', type: 'button', disabled: ro, onclick: () => { $('epMsg').textContent = ''; poner(p); },
                'aria-label': `Elegir ${p.nombre}${p.tipo ? ' (' + p.tipo + ')' : ''}`,
            }, h('span', { class: 'mono' }, p.nombre), p.tipo ? h('span', { class: 'ep-tipo ep-' + p.tipo.toLowerCase() }, p.tipo) : null))))
            : h('p', { class: 'ep-nada' }, datos.sin_pareja.length ? 'Las placas sin pareja ya están en las ranuras.' : 'Todas las placas de este periodo tienen pareja.'));
        const nInc = datos.parejas.filter((p) => !p.completa).length;
        $('epParT').textContent = `Parejas · ${datos.parejas.length - nInc}` + (nInc ? ` (+${nInc} incompletas)` : '');
        const lado = (par, k) => h('span', { class: 'ep-lado' }, h('span', { class: 'ep-tipo ep-' + k }, k.toUpperCase()),
            par[k] ? h('b', { class: 'mono' }, par[k].nombre) : h('span', { class: 'ep-falta' }, 'Falta'));
        $('epPar').replaceChildren(datos.parejas.length
            ? h('ul', { class: 'ep-lista' }, datos.parejas.map((par) => h('li', { class: 'ep-par' + (par.completa ? '' : ' incompleta') },
                h('span', { class: 'ep-num mono', title: 'Número de pareja' }, 'P' + par.numero),
                lado(par, 'rx'), lado(par, 'tx'),
                h('span', { class: 'ep-fecha' }, P.fecha(par.creada_en, false)),
                h('span', { class: 'ep-btns' },
                    par.completa || ro ? null : h('button', { class: 'btn btn-sm', type: 'button', onclick: () => completar(par),
                        'aria-label': `Completar la pareja ${par.numero}` }, icon('link'), 'Completar'),
                    ro ? null : h('button', { class: 'btn btn-sm btn-ghost', type: 'button', onclick: () => renumerar(par),
                        'aria-label': `Cambiar el número de la pareja ${par.numero}` }, icon('edit'), 'Número'),
                    h('button', { class: 'btn btn-sm btn-ghost', type: 'button', onclick: () => P.abrir('etiquetas', (par.rx || par.tx).nombre),
                        'aria-label': `Imprimir las etiquetas de la pareja ${par.numero}` }, icon('printer'), 'Etiquetas'),
                    ro ? null : h('button', { class: 'btn btn-sm btn-ghost', type: 'button', onclick: () => deshacer(par),
                        'aria-label': `Deshacer la pareja ${par.numero}` }, icon('unlink'), 'Deshacer')))))
            : h('p', { class: 'ep-nada' }, 'Aún no hay parejas en este periodo.'));
    }

    async function cargar() {
        const k = ++seq;
        const q = mes ? '?mes=' + encodeURIComponent(mes) : '';
        $('epCuerpo').setAttribute('aria-busy', 'true');
        const r = await api('/api/antijammer/parejas' + q);
        if (k !== seq) return;
        $('epCuerpo').removeAttribute('aria-busy');
        $('epError').replaceChildren();
        if (!r.ok) { $('epError').replaceChildren(P.error((r.error || 'No se pudieron cargar las parejas') + '. Revisa la conexión con el servidor.', cargar)); return; }
        datos = r.data;
        if (mes === null) { mes = datos.meses[0] || ''; if (mes) return cargar(); }   // por omisión, el mes más reciente
        const s = $('epMes');
        s.replaceChildren(h('option', { value: '' }, 'Todos los meses'), ...datos.meses.map((m) => h('option', { value: m }, nomMes(m))));
        s.value = mes || '';
        // lo elegido que ya no está suelto (otra sesión lo emparejó) se suelta de la ranura
        const libres = new Set(datos.sin_pareja.map((p) => p.id));
        ['rx', 'tx'].forEach((x) => { if (sel[x] && !libres.has(sel[x].id) && datos.parejas.some((p) => p.completa && (p.rx.id === sel[x].id || p.tx.id === sel[x].id))) sel[x] = null; });
        const nOk = datos.parejas.filter((p) => p.completa).length;
        $('epCuenta').textContent = `${nOk} ${nOk === 1 ? 'pareja' : 'parejas'} · ${datos.sin_pareja.length} sin pareja`;
        pintar();
    }

    P.registrar('emparejar', {
        montar(el) {
            sec = el;
            $('epMes').addEventListener('change', (e) => { mes = e.target.value; cargar(); });
            $('epForm').addEventListener('submit', async (e) => {
                e.preventDefault();
                const inp = $('epCod'), v = inp.value; inp.value = '';
                await leer(v); inp.focus();
            });
            $('epOk').addEventListener('click', emparejar);
            $('epNum').addEventListener('input', (e) => e.target.removeAttribute('aria-invalid'));
            $('epLimpiar').addEventListener('click', () => { sel.rx = sel.tx = null; activa = 'rx'; $('epNum').value = ''; $('epMsg').textContent = ''; pintar(); });
            document.addEventListener('antijammer:cambio', () => { if (sec.hidden) viejo = true; });
            cargar();
        },
        entrar() {
            P.cam.unir(sec.querySelector('.cam-slot'), {
                pista: 'Escanea la RX y después la TX.',
                onCode: (t) => leer(t),
                onManual: () => $('epCod').focus(),
            });
            if (viejo) { viejo = false; cargar(); }
        },
        /** Lectura del celular vinculado (botón de escaneo). */
        escaneo(texto) { return leer(texto); },
    });
})();
