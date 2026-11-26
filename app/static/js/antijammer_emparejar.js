/* antijammer_emparejar.js - Emparejar (consola Skudo AntiJammer, v1.4.103): cada equipo es una placa RX + una TX (sin R1/R2/R3).
 * Escanea o elige dos placas; la primera va a RX y la segunda a TX (o la ranura activa). Las placas que ya tienen RX/TX en
 * Materiales van solas a su ranura. Deshacer conserva el RX/TX de cada placa.
 * API: GET /api/antijammer/parejas?mes=AAAA-MM · POST /api/antijammer/parejas {rx, tx} · DELETE /api/antijammer/parejas/{id} */
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
        const par = !suelta && datos && datos.parejas.find((x) => x.rx.id === pcb.id || x.tx.id === pcb.id);
        if (par) { msg.textContent = `${pcb.nombre} ya está en la pareja #${par.id}. Deshazla primero.`; return { ok: false, texto: msg.textContent }; }
        msg.textContent = '';
        poner(suelta || { id: pcb.id, nombre: pcb.nombre, tipo: '' });
        return { ok: true, texto: `${pcb.nombre} lista` };
    }

    async function emparejar() {
        if (!sel.rx || !sel.tx || P.soloLectura()) return;
        const b = $('epOk'); b.disabled = true;
        const r = await api('/api/antijammer/parejas', { method: 'POST', body: { rx: '#' + sel.rx.id, tx: '#' + sel.tx.id } });
        b.disabled = false;
        if (!r.ok) { $('epMsg').textContent = (r.error || 'No se pudo emparejar') + '.'; return; }
        T.toast(`Pareja #${r.data.id}: ${sel.rx.nombre} (RX) + ${sel.tx.nombre} (TX)`, { kind: 'ok' });
        sel.rx = sel.tx = null; activa = 'rx';
        P.cambio(); cargar();
    }

    function deshacer(par) {
        if (P.soloLectura()) return;
        T.sheet({
            title: `Deshacer la pareja #${par.id}`,
            body: [h('p', null, `${par.rx.nombre} (RX) y ${par.tx.nombre} (TX) quedan sin pareja. Cada placa conserva si es RX o TX.`)],
            actions: [
                { label: 'Cancelar', kind: 'ghost', onClick: () => true },
                { label: `Deshacer pareja #${par.id}`, kind: 'danger', icon: 'unlink', onClick: async () => {
                    const r = await api('/api/antijammer/parejas/' + par.id, { method: 'DELETE' });
                    if (!r.ok) { T.toast((r.error || 'No se pudo deshacer la pareja') + '. Inténtalo otra vez.', { kind: 'bad' }); return false; }
                    T.toast(`Pareja #${par.id} deshecha`, { kind: 'ok' });
                    P.cambio(); cargar();
                    return true;
                } },
            ],
        });
    }

    function pintar() {
        if (!datos) return;
        const ro = P.soloLectura();
        const elegidas = new Set([sel.rx && sel.rx.id, sel.tx && sel.tx.id]);
        $('epRanuras').replaceChildren(ranura('rx'), h('span', { class: 'ep-union', 'aria-hidden': 'true' }, icon('link')), ranura('tx'));
        $('epOk').disabled = ro || !(sel.rx && sel.tx);
        const sueltas = datos.sin_pareja.filter((p) => !elegidas.has(p.id));
        const nRx = datos.sin_pareja.filter((p) => p.tipo === 'RX').length, nTx = datos.sin_pareja.filter((p) => p.tipo === 'TX').length;
        $('epSueltasT').textContent = `Sin pareja · ${datos.sin_pareja.length}` + (nRx || nTx ? ` (${nRx} RX, ${nTx} TX)` : '');
        $('epSueltas').replaceChildren(sueltas.length
            ? h('ul', { class: 'ep-chips' }, sueltas.map((p) => h('li', null, h('button', {
                class: 'ep-chip', type: 'button', disabled: ro, onclick: () => { $('epMsg').textContent = ''; poner(p); },
                'aria-label': `Elegir ${p.nombre}${p.tipo ? ' (' + p.tipo + ')' : ''}`,
            }, h('span', { class: 'mono' }, p.nombre), p.tipo ? h('span', { class: 'ep-tipo ep-' + p.tipo.toLowerCase() }, p.tipo) : null))))
            : h('p', { class: 'ep-nada' }, datos.sin_pareja.length ? 'Las placas sin pareja ya están en las ranuras.' : 'Todas las placas de este periodo tienen pareja.'));
        $('epParT').textContent = `Parejas · ${datos.parejas.length}`;
        $('epPar').replaceChildren(datos.parejas.length
            ? h('ul', { class: 'ep-lista' }, datos.parejas.map((par) => h('li', { class: 'ep-par' },
                h('span', { class: 'ep-num mono' }, '#' + par.id),
                h('span', { class: 'ep-lado' }, h('span', { class: 'ep-tipo ep-rx' }, 'RX'), h('b', { class: 'mono' }, par.rx.nombre)),
                h('span', { class: 'ep-lado' }, h('span', { class: 'ep-tipo ep-tx' }, 'TX'), h('b', { class: 'mono' }, par.tx.nombre)),
                h('span', { class: 'ep-fecha' }, P.fecha(par.creada_en, false)),
                ro ? null : h('button', { class: 'btn btn-sm btn-ghost', type: 'button', onclick: () => deshacer(par),
                    'aria-label': `Deshacer la pareja #${par.id}` }, icon('unlink'), 'Deshacer'))))
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
        ['rx', 'tx'].forEach((x) => { if (sel[x] && !libres.has(sel[x].id) && datos.parejas.some((p) => p.rx.id === sel[x].id || p.tx.id === sel[x].id)) sel[x] = null; });
        $('epCuenta').textContent = `${datos.parejas.length} ${datos.parejas.length === 1 ? 'pareja' : 'parejas'} · ${datos.sin_pareja.length} sin pareja`;
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
            $('epLimpiar').addEventListener('click', () => { sel.rx = sel.tx = null; activa = 'rx'; $('epMsg').textContent = ''; pintar(); });
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
