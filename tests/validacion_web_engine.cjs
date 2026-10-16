// v1.4.0: pruebas del motor web de Validación (port de station/test_station/tests/test_engine_fake.py).
// Ejecutar: node tests/validacion_web_engine.cjs  (sin dependencias, sin hardware)
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert');

const src = fs.readFileSync(path.join(__dirname, '../app/static/js/validacion_web.js'), 'utf8');
const ctx = { window: { isSecureContext: true }, navigator: {}, TextEncoder, TextDecoder, performance, setTimeout, clearTimeout,
    setInterval, clearInterval, console, Promise, JSON, sessionStorage: { getItem() { return null; }, setItem() {}, removeItem() {} } };
vm.createContext(ctx);
vm.runInContext(src, ctx);
const W = ctx.window.TQTValWeb, I = W._interno;
const CFG = { ackMs: 5, quietMs: 20, repeatVerifyMs: 300 };

class Fixture {
    constructor(over = {}) {
        this.values = Object.fromEntries(I.FIELDS.map(k => [k, '0']));
        Object.assign(this.values, { VER: '4.3', HW: '3.0', MAC: 'AA:BB:CC:DD:EE:FF', MACR: '11:22:33:44:55:66', ID: '0011', IDR: 'R2',
            Mensaje: '1.0', ON: '0', OFF: '1', TQT: '0', PB: '0', MOV: '0', SEN_MOT: '0', MOTOR: '0' }, over);
        this.name = 'TQT_R1_V3_0_0011';
        this.writes = []; this.link = null; this.active = '';
    }
    line(text) {   // entrega fragmentada: trozos de 7 bytes en ticks distintos
        const bytes = Buffer.from(text + '\r\n');
        for (let i = 0; i < bytes.length; i += 7) { const chunk = Uint8Array.from(bytes.subarray(i, i + 7)); setTimeout(() => this.link.feed(chunk), 1); }
    }
    emit() { this.line('AT$POST=1,0,"S29|' + I.FIELDS.map(k => k + ';' + this.values[k]).join('|') + '"'); }
    move(cmd, origin) {
        const target = cmd === 'POFF' ? 'cerrado' : 'abierto', old = this.values.ON === '1' ? 'cerrado' : 'abierto';
        this.values.PB = String(origin);
        this.values.ON = target === 'cerrado' ? '1' : '0'; this.values.OFF = target === 'abierto' ? '1' : '0';
        if (target !== old) {
            if (origin === 1 || origin === 2) this.values.MOV = String(+this.values.MOV + 1);
            else this.values.err = target === 'cerrado' ? '14' : '13';
        }
        this.emit();
    }
    write(text) {
        this.writes.push(text);
        const cmd = text.trim();
        if (cmd === '$OK') return;
        if (cmd === '$SMSG=Reset_44') { this.line('AT$POST=1,0,"' + this.name + ' - Lista para usarse "'); this.emit(); }
        else if (cmd === '$SMSG=Status') this.emit();
        else if (cmd === '$SMSG=ON') this.move('PPON', 1);
        else if (cmd === '$SMSG=OFF') this.move('POFF', 1);
    }
}

function montar(fx, hooks = {}) {
    const events = [];
    const link = new I.SerialLink({ cfg: CFG, onLine: l => motor.on_line(l), onInfo: t => motor.log(t) });
    fx.link = link;
    link.attach({ activo: () => true, descripcion: 'FAKE', escribir: async b => { setTimeout(() => fx.write(Buffer.from(b).toString()), 1); return b.length; } }, 'FAKE');
    const ble = {
        connected: true, nombre: '', dispositivo: null,
        localizar: async ({ nombre }) => ({ name: nombre, id: 'opaco-123' }),
        connect: async (d, disp) => { fx.active = disp; },
        send: async cmd => { if (!fx.active) throw new Error('sin BLE'); setTimeout(() => fx.move(cmd, fx.active === 'R1' ? 2 : 3), 1); },
        disconnect: async () => { fx.active = ''; },
        macDeclarada: async () => hooks.macR2 || null,
    };
    let seq = 0;
    const motor = new I.Motor({ serial: link, ble, cfg: CFG, ui: (kind, ...args) => events.push({ seq: ++seq, data: { kind, args } }),
        hooks: Object.assign({ gesto: async () => null, confirmar: async () => false, identidad: async () => { throw new Error('no'); } }, hooks) });
    return { motor, link, events };
}
const INV = { nombre: 'TQT-R1-V30-0011', mac_r1: 'AABBCCDDEEFF', mac_r2: '112233445566', r2_nombre: 'TQT_R2_V3_0_0011', r1_serie: '0011' };

const pruebas = [];
const prueba = (n, f) => pruebas.push([n, f]);

prueba('protocolo: S29, Lista para usarse y comandos idénticos a protocol.py', () => {
    const fx = new Fixture();
    const raw = 'AT$POST=1,0,"S29|' + I.FIELDS.map(k => k + ':' + fx.values[k]).join('|') + '"';
    const st = I.parseStatus(raw);
    assert.strictEqual(st.fields.MAC, 'AA:BB:CC:DD:EE:FF');
    assert.strictEqual(I.position(st), 'abierto');
    assert.strictEqual(I.parseStatus(raw.slice(0, -12)), null);
    assert.strictEqual(I.readReady('AT$POST=1,0,"TQT_R1_V3_0_0011 - Lista para usarse "'), 'TQT_R1_V3_0_0011');
    assert.strictEqual(I.serialAction('PPON'), '$SMSG=ON\r\n');
    assert.strictEqual(I.serialAction('POFF'), '$SMSG=OFF\r\n');
    assert.strictEqual(I.serialAction('RESET_FACTORY'), '$SMSG=Reset_44\r\n');
    assert.throws(() => I.serialAction('FLASH'));
    assert.strictEqual(I.CFG.ackMs, 180); assert.strictEqual(I.CFG.quietMs, 300); assert.strictEqual(I.CFG.repeatVerifyMs, 5000);
    assert.strictEqual(I.STEP_NAMES.length, 14);
    const contract = JSON.parse(fs.readFileSync(path.join(__dirname, '../app/static/js/test_station_contract.json'), 'utf8'));
    assert.deepStrictEqual(Array.from(I.STEP_NAMES), contract.step_names);
    assert.deepStrictEqual(Array.from(I.FIELDS), contract.fields);
});

prueba('14 etapas aprobadas con RX fragmentado, ACK por trama y eventos con forma del agente', async () => {
    const fx = new Fixture();
    const { motor, events } = montar(fx);
    const r = await motor.run({ expected: INV, portName: 'FAKE' });
    assert.strictEqual(r.result, 'aprobado', r.issue);
    assert.strictEqual(r.steps.length, 14);
    assert.ok(r.steps.every(s => s.state === 'aprobado'));
    assert.strictEqual(r.r1_ble_address, null, 'nunca se inventa MAC BLE');
    assert.strictEqual(r.ble_identity.r1.id_opaco_navegador, 'opaco-123');
    assert.strictEqual(r.mac_comparison, 'vinculo_funcional');
    assert.strictEqual(r.inventory_check.state, 'coincide');
    assert.strictEqual(r.communication_quality.state, 'limpia');
    assert.ok(fx.writes.filter(w => w === '$OK\r\n').length >= r.serial_health.frames - 1, 'ACK por cada AT$POST');
    const st = events.find(e => e.data.kind === 'status');
    assert.ok(st.data.args[0].fields && st.data.args[0].raw.startsWith('AT$POST'));
    const step = events.find(e => e.data.kind === 'step');
    assert.deepStrictEqual(step.data.args.slice(0, 2), [0, 'ejecutando']);
    assert.ok(events.some(e => e.data.kind === 'ble_ident' && e.data.args[0] === 'R2'));
    assert.strictEqual(events[events.length - 1].data.kind, 'done');
    assert.strictEqual(events[events.length - 1].data.args[0], 'aprobado');
    // Status previo a Reset_44 para identificar sin efectos.
    assert.strictEqual(fx.writes.findIndex(w => w.startsWith('$SMSG=Status')) < fx.writes.indexOf('$SMSG=Reset_44\r\n'), true);
});

prueba('tarjeta distinta: cancelar no envía Reset_44 ni movimientos', async () => {
    const fx = new Fixture();
    let preguntado = null;
    const { motor } = montar(fx, {
        identidad: async (det, confirmar) => ({ seleccionada: { nombre: 'TQT-R1-V30-0042' }, detectada: { nombre: 'TQT-R1-V30-0011' } }),
        confirmar: async q => { preguntado = q; return false; },
    });
    const r = await motor.run({ expected: Object.assign({}, INV, { nombre: 'TQT-R1-V30-0042', mac_r1: '000000000042' }), portName: 'FAKE' });
    assert.strictEqual(preguntado.detectada.nombre, 'TQT-R1-V30-0011');
    assert.strictEqual(r.result, 'no_verificado');
    assert.strictEqual(r.cancelled, true);
    assert.ok(!fx.writes.some(w => /Reset_44|SMSG=ON|SMSG=OFF/.test(w)), fx.writes.join(','));
});

prueba('tarjeta distinta confirmada: continúa sin otro Iniciar con el inventario detectado', async () => {
    const fx = new Fixture();
    let llamadas = [];
    const { motor, events } = montar(fx, {
        identidad: async (det, confirmar) => {
            llamadas.push(confirmar);
            const base = { seleccionada: { nombre: 'TQT-R1-V30-0042' }, detectada: { nombre: 'TQT-R1-V30-0011' } };
            return confirmar ? Object.assign(base, { inventory: INV, identity_change: { detectada: { nombre: INV.nombre } } }) : base;
        },
        confirmar: async () => true,
    });
    const r = await motor.run({ expected: Object.assign({}, INV, { nombre: 'TQT-R1-V30-0042', mac_r1: '000000000042' }), portName: 'FAKE' });
    assert.deepStrictEqual(llamadas, [false, true]);
    assert.strictEqual(r.result, 'aprobado', r.issue);
    assert.ok(r.identity_change);
    assert.ok(events.some(e => e.data.kind === 'identity_change'));
});

prueba('reintento ACK (Mensaje n.1) impide aprobar', async () => {
    const fx = new Fixture({ Mensaje: '5.1' });
    const { motor } = montar(fx);
    const r = await motor.run({ expected: INV, portName: 'FAKE' });
    assert.strictEqual(r.communication_quality.state, 'no_verificable');
    assert.notStrictEqual(r.result, 'aprobado');
});

prueba('MAC declarada por R2 distinta de MACR: falla sin comandos R2', async () => {
    const fx = new Fixture();
    const { motor } = montar(fx, { macR2: '99:99:99:99:99:99' });
    const r = await motor.run({ expected: INV, portName: 'FAKE' });
    assert.strictEqual(r.steps[11].state, 'fallido');
    assert.strictEqual(r.result, 'fallido');
});

prueba('cancelación durante la prueba: no verificado y sin más comandos', async () => {
    const fx = new Fixture();
    const { motor } = montar(fx);
    const p = motor.run({ expected: INV, portName: 'FAKE' });
    await new Promise(r => setTimeout(r, 150));
    motor.stop('Prueba detenida por el usuario');
    const n = fx.writes.filter(w => w !== '$OK\r\n').length;
    const r = await p;
    assert.strictEqual(r.result, 'no_verificado');
    assert.strictEqual(r.cancelled, true);
    await new Promise(res => setTimeout(res, 100));
    assert.ok(fx.writes.filter(w => w !== '$OK\r\n').length <= n + 1);
});

prueba('publicador: lotes ordenados, latido vacío y aviso de cancelación', async () => {
    const enviados = []; let cancel = 0;
    const pub = new I.Publicador('j1', () => cancel++, async (p, body) => { enviados.push(body.items.map(i => i.seq)); return { ok: true, cancel: enviados.length > 1 }; });
    for (let i = 0; i < 130; i++) pub.push({ kind: 'log', args: [String(i)] });
    await pub.drenar();
    pub.cerrar();
    assert.deepStrictEqual(enviados.map(x => x.length), [100, 30]);
    assert.strictEqual(enviados[1][0], 101);
    assert.strictEqual(cancel, 1);
});

(async () => {
    let fallos = 0;
    for (const [n, f] of pruebas) {
        try { await f(); console.log('ok  -', n); }
        catch (e) { fallos++; console.log('FAIL-', n, '\n', e && e.stack || e); }
    }
    console.log(fallos ? fallos + ' fallo(s)' : 'todas las pruebas pasan');
    process.exit(fallos ? 1 : 0);
})();
