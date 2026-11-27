/* antijammer_programar.js - Pestaña Programar: escanear/teclear la placa → firmware (recordado por dispositivo) → guardar.
 * Modo lote: cada placa leída se guarda con el firmware escrito sin confirmar. Botón para marcar FALLA (o quitarla).
 * v1.4.104: RX/TX y número de pareja que se le dio al programarla; la pareja se forma sola cuando la RX y la TX comparten número.
 * API: GET /api/antijammer/pcb/por-codigo · PUT /api/antijammer/pcb/{id}/firmware {firmware, tipo, pareja} · PATCH /api/antijammer/pcb/{id} {estado, nota} */
(function () {
    'use strict';
    const T = window.TQT, P = window.AJ;
    const { h, icon, api } = T;
    const CLAVE_FW = 'tqt.antijammer.fw', CLAVE_LOTE = 'tqt.antijammer.prog.lote';
    const st = { placa: null, ocupado: false, sesion: [] };
    let sec = null, ui = {};

    const leer = (k, d) => { try { return localStorage.getItem(k) ?? d; } catch (e) { return d; } };
    const escribir = (k, v) => { try { localStorage.setItem(k, v); } catch (e) { /* nada */ } };

    function aviso(k, txt) { ui.aviso.dataset.k = k || ''; ui.aviso.textContent = txt || ''; ui.aviso.hidden = !txt; }

    function pintaPlaca() {
        const p = st.placa;
        ui.guardar.disabled = !p || st.ocupado;
        ui.falla.disabled = !p || st.ocupado;
        if (!p) {
            ui.placa.replaceChildren(h('p', { class: 'p-vacio' }, 'Escanea el QR o teclea la serie de una placa para empezar.'));
            ui.falla.lastChild.textContent = 'Marcar falla';
            return;
        }
        const enFalla = p.estado === 'FALLA';
        ui.falla.lastChild.textContent = enFalla ? 'Quitar falla' : 'Marcar falla';
        ui.placa.replaceChildren(...[   // replaceChildren no ignora null: se filtra
            h('div', { class: 'p-cab' }, h('b', { class: 'p-nom mono' }, p.nombre), P.estadoBadge(p.estado)),
            h('dl', { class: 'p-datos' },
                h('div', null, h('dt', null, 'Hardware'), h('dd', { class: 'mono' }, P.hw(p.version))),
                h('div', null, h('dt', null, 'Firmware actual'), h('dd', { class: 'mono' }, p.firmware || 'Sin firmware')),
                h('div', null, h('dt', null, 'Lote'), h('dd', null, p.lote || '—')),
                h('div', null, h('dt', null, 'Pareja'), h('dd', { class: 'mono' }, p.pareja ? `${p.pareja.numero} (${p.pareja.tipo})` : 'Sin número'))),
            enFalla || p.estado === 'BAJA' ? h('p', { class: 'p-nota' }, `Esta placa está en ${P.ESTADOS[p.estado].txt.toLowerCase()}. Guardar firmware no cambia ese estado.`) : null].filter(Boolean));
    }

    function pintaSesion() {
        ui.sesN.textContent = st.sesion.length ? `(${st.sesion.length})` : '';
        ui.sesLista.replaceChildren(...st.sesion.slice(0, 15).map((x) => h('li', null,
            h('span', { class: 'cod mono' }, x.nombre), h('span', { class: 'meta mono' }, x.firmware))));
        ui.sesVacio.hidden = st.sesion.length > 0;
    }

    async function cargar(texto) {
        const codigo = P.normal(texto);
        if (!codigo || st.ocupado) return;
        st.ocupado = true; st.placa = null; pintaPlaca();
        aviso('', 'Buscando ' + codigo + '…');
        P.cam.bloquear();
        const r = await P.porCodigo(codigo);
        st.ocupado = false; P.cam.liberar();
        if (r.status === 404) {
            P.sonar.mal(); pintaPlaca();
            aviso('bad', `${codigo} no está registrada. Regístrala primero en Recibir.`);
            ui.placa.replaceChildren(h('div', { class: 'p-vacio' }, h('span', null, 'Placa no encontrada.'),
                h('button', { class: 'btn btn-sm', type: 'button', onclick: () => P.abrir('recibir') }, icon('recibir'), 'Ir a Recibir')));
            return;
        }
        if (!r.ok) {
            P.sonar.mal(); pintaPlaca(); aviso('', '');
            ui.placa.replaceChildren(P.error((r.error || 'No se pudo buscar la placa.') + ' Revisa la conexión.', () => cargar(codigo)));
            return;
        }
        st.placa = Object.assign({}, r.data.pcb, { pareja: r.data.pareja || null }); pintaPlaca();
        if (st.placa.pareja && !ui.num.value) { ui.tipo.value = st.placa.pareja.tipo; ui.num.value = st.placa.pareja.numero; }
        if (ui.lote.checked && ui.fw.value.trim()) { await guardar(); return; }
        P.sonar.ok();
        aviso('', `${st.placa.nombre} lista. Revisa el firmware y guarda.`);
        ui.fw.focus({ preventScroll: true });
    }

    async function guardar() {
        const p = st.placa, fw = ui.fw.value.trim();
        if (!p || st.ocupado) return;
        if (!fw) { ui.fw.setAttribute('aria-invalid', 'true'); aviso('bad', 'Escribe el firmware con el que programaste la placa.'); ui.fw.focus(); return; }
        const tipo = ui.tipo.value, num = ui.num.value.trim();
        if (num && !tipo) { ui.tipo.setAttribute('aria-invalid', 'true'); aviso('bad', 'Elige si la placa es RX o TX para darle el número de pareja.'); ui.tipo.focus(); return; }
        if (num && !/^\d{1,4}$/.test(num)) { ui.num.setAttribute('aria-invalid', 'true'); aviso('bad', 'El número de pareja va de 1 a 9999.'); ui.num.focus(); return; }
        const body = { firmware: fw };
        if (tipo) body.tipo = tipo;
        if (num) body.pareja = +num;
        st.ocupado = true; pintaPlaca(); aviso('', 'Guardando…');
        const r = await api(`/api/antijammer/pcb/${p.id}/firmware`, { method: 'PUT', body });
        st.ocupado = false;
        if (!r.ok) { P.sonar.mal(); pintaPlaca(); aviso('bad', (r.error || 'No se guardó el firmware.') + ' Inténtalo otra vez.'); return; }
        escribir(CLAVE_FW, fw);
        const par = r.data && r.data.pareja;
        st.placa = Object.assign({}, (r.data && r.data.pcb) || Object.assign({}, p, { firmware: fw }),
            { pareja: par ? { numero: par.numero, tipo: tipo } : p.pareja || null });
        const meta = fw + (par ? ` · P${par.numero} ${tipo}` : tipo ? ` · ${tipo}` : '');
        st.sesion = [{ nombre: st.placa.nombre, firmware: meta }].concat(st.sesion.filter((x) => x.nombre !== st.placa.nombre));
        let extra = '';
        if (par && par.completa) {   // pareja lista: el siguiente número se escribe a mano
            extra = ` Pareja ${par.numero} completa: ${par.rx.nombre} (RX) + ${par.tx.nombre} (TX).`;
            ui.num.value = ''; ui.tipo.value = 'RX';
        } else if (par) {             // falta la otra: se deja lista la otra mitad con el mismo número
            extra = ` Pareja ${par.numero}: falta la ${tipo === 'RX' ? 'TX' : 'RX'}.`;
            ui.tipo.value = tipo === 'RX' ? 'TX' : 'RX';
        }
        P.sonar.ok(); P.cam.destello('ok');
        aviso('ok', `${st.placa.nombre} programada con ${fw}.${extra}${ui.lote.checked ? ' Escanea la siguiente.' : ''}`);
        pintaPlaca(); pintaSesion(); P.cambio();
        ui.cod.value = '';
    }

    function falla() {
        const p = st.placa;
        if (!p) return;
        if (p.estado === 'FALLA') {
            const destino = p.firmware ? 'PROGRAMADA' : 'RECIBIDA';
            return parchar(p, { estado: destino }, `${p.nombre} ya no está en falla (${P.ESTADOS[destino].txt.toLowerCase()}).`);
        }
        const nota = h('textarea', { class: 'input', id: 'pfNota', rows: '3', maxlength: '300' });
        const err = h('p', { class: 'hoja-err', role: 'alert' });
        T.sheet({
            title: 'Marcar falla',
            body: [
                h('p', null, `${p.nombre} quedará en estado Falla y dejará de contar como lista.`),
                h('div', { class: 'field' }, h('label', { for: 'pfNota' }, 'Qué falló (opcional)'), nota),
                err,
            ],
            actions: [
                { label: 'Cancelar', kind: 'ghost', onClick: () => true },
                { label: `Marcar ${p.nombre} como falla`, kind: 'danger', icon: 'alert', onClick: async () => {
                    const body = { estado: 'FALLA' };
                    if (nota.value.trim()) body.nota = nota.value.trim();
                    const ok = await parchar(p, body, `${p.nombre} marcada como falla.`);
                    if (!ok) { err.textContent = 'No se pudo marcar la falla. Revisa la conexión e inténtalo otra vez.'; return false; }
                    return true;
                } },
            ],
        });
    }
    async function parchar(p, body, msg) {
        const r = await api(`/api/antijammer/pcb/${p.id}`, { method: 'PATCH', body });
        if (!r.ok) { aviso('bad', r.error || 'No se pudo cambiar el estado.'); return false; }
        st.placa = (r.data && r.data.pcb) || Object.assign({}, p, body);
        aviso(body.estado === 'FALLA' ? 'warn' : 'ok', msg);
        pintaPlaca(); P.cambio();
        return true;
    }

    function montar(el) {
        sec = el;
        const lado = el.querySelector('#pLado');
        ui.cod = h('input', { class: 'input mono', id: 'pCod', type: 'text', autocomplete: 'off', autocapitalize: 'characters', spellcheck: 'false', maxlength: '300', enterkeyhint: 'search', 'aria-describedby': 'pCodAy' });
        ui.fw = h('input', { class: 'input mono', id: 'pFw', type: 'text', autocomplete: 'off', spellcheck: 'false', maxlength: '80', list: 'dlFirmwares', 'aria-describedby': 'pFwAy' });
        ui.fw.value = leer(CLAVE_FW, '');
        ui.fw.addEventListener('input', () => { ui.fw.removeAttribute('aria-invalid'); });
        ui.tipo = h('select', { class: 'input', id: 'pTipo', 'aria-describedby': 'pParAy' },
            h('option', { value: '' }, 'Sin indicar'), h('option', { value: 'RX' }, 'RX'), h('option', { value: 'TX' }, 'TX'));
        ui.num = h('input', { class: 'input mono', id: 'pNum', type: 'text', inputmode: 'numeric', pattern: '[0-9]*', maxlength: '4', autocomplete: 'off', 'aria-describedby': 'pParAy' });
        [ui.tipo, ui.num].forEach((x) => x.addEventListener('input', () => x.removeAttribute('aria-invalid')));
        ui.lote = h('input', { type: 'checkbox', id: 'pLote' });
        ui.lote.checked = leer(CLAVE_LOTE, '0') === '1';
        ui.lote.addEventListener('change', () => { escribir(CLAVE_LOTE, ui.lote.checked ? '1' : '0'); aviso('', ui.lote.checked ? 'Modo lote activo: cada placa que leas se guarda con este firmware.' : ''); });
        ui.placa = h('div', { class: 'p-placa' });
        ui.aviso = h('p', { class: 'p-aviso', role: 'status', 'aria-live': 'polite', hidden: true });
        ui.guardar = h('button', { class: 'btn btn-primary', type: 'submit', form: 'pForm' }, icon('check'), 'Guardar firmware');
        ui.falla = h('button', { class: 'btn btn-danger', type: 'button', onclick: falla }, icon('alert'), h('span', null, 'Marcar falla'));
        ui.sesN = h('span', { class: 'cuenta mono' });
        ui.sesLista = h('ol', { class: 'lista' });
        ui.sesVacio = h('p', { class: 'hist-vacio' }, 'Las placas que programes aparecen aquí con su firmware.');

        const fBuscar = h('form', { class: 'p-buscar', novalidate: true, onsubmit: (e) => {
            e.preventDefault();
            if (!ui.cod.value.trim()) { ui.cod.focus(); T.toast('Escribe el código o la serie de la placa', { kind: 'warn' }); return; }
            cargar(ui.cod.value);
        } },
        h('div', { class: 'field' }, h('label', { for: 'pCod' }, 'Placa'),
            h('div', { class: 'man-fila' }, ui.cod, h('button', { class: 'btn', type: 'submit' }, icon('search'), 'Buscar')),
            h('p', { class: 'ayuda', id: 'pCodAy' }, 'QR, nombre (SJ-V1-0004) o solo la serie.')));

        const fGuardar = h('form', { class: 'p-fw', id: 'pForm', novalidate: true, onsubmit: (e) => { e.preventDefault(); guardar(); } },
            h('div', { class: 'field' }, h('label', { for: 'pFw' }, 'Firmware'), ui.fw,
                h('p', { class: 'ayuda', id: 'pFwAy' }, 'Se recuerda el último firmware que guardaste en este dispositivo.')),
            h('div', { class: 'p-par' },
                h('div', { class: 'field' }, h('label', { for: 'pTipo' }, 'Tarjeta'), ui.tipo),
                h('div', { class: 'field' }, h('label', { for: 'pNum' }, 'Número de pareja'), ui.num)),
            h('p', { class: 'ayuda', id: 'pParAy' }, 'El número que le diste al programarla. Cuando la RX y la TX tienen el mismo número, quedan emparejadas solas.'),
            h('label', { class: 'chk', for: 'pLote' }, ui.lote,
                h('span', null, h('b', null, 'Programar en lote'), h('small', null, 'Cada placa que leas se guarda con este firmware sin pedir confirmación.'))));

        lado.replaceChildren(
            fBuscar,
            h('section', { class: 'p-tarjeta', 'aria-label': 'Placa seleccionada' }, ui.placa, ui.aviso),
            fGuardar,
            h('div', { class: 'p-acc' }, ui.guardar, ui.falla),
            h('section', { class: 'historial', 'aria-labelledby': 'tPSes' },
                h('div', { class: 'hist-cab' }, h('h2', { id: 'tPSes' }, 'Programadas en esta sesión ', ui.sesN)),
                ui.sesLista, ui.sesVacio));
        pintaPlaca(); pintaSesion();
    }

    P.registrar('programar', {
        montar,
        entrar() {
            if (P.soloLectura()) return;
            P.cam.unir(sec.querySelector('.cam-slot'), {
                pista: 'Apunta al QR de la placa que vas a programar.',
                onCode: (t) => cargar(t),
                onManual: () => ui.cod.focus(),
            });
        },
        recibirDato(codigo) { if (codigo) { ui.cod.value = codigo; cargar(codigo); } },
    });
})();
