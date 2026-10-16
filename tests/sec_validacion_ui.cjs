// v1.4.0: prueba de humo de la UI de Validación con un DOM mínimo (node puro, sin dependencias).
// Comprueba: 14 filas desde el inicio, actualización in situ por eventos K1, diálogo de identidad,
// botón «Imprimir etiquetas» solo tras «aprobado» 14/14 con cotejo, y llamada a K2.
"use strict";
const assert = require("assert");
const fs = require("fs");
const path = require("path");

class El {
  constructor(tag) {
    this.tagName = tag.toUpperCase();
    this.children = [];
    this.attrs = {};
    this.dataset = {};
    this.listeners = {};
    this.parent = null;
    this._text = "";
    this.hidden = false;
    this.disabled = false;
    this.className = "";
  }
  appendChild(c) {
    if (c.parent) c.parent.children.splice(c.parent.children.indexOf(c), 1);
    c.parent = this;
    this.children.push(c);
    return c;
  }
  append(...cs) { cs.forEach((c) => this.appendChild(typeof c === "string" ? new Text(c) : c)); }
  replaceChildren(...cs) { this.children.forEach((c) => (c.parent = null)); this.children = []; this.append(...cs); }
  remove() { if (this.parent) { this.parent.children.splice(this.parent.children.indexOf(this), 1); this.parent = null; } }
  setAttribute(k, v) { this.attrs[k] = String(v); if (k === "disabled") this.disabled = true; if (k === "hidden") this.hidden = true; }
  getAttribute(k) { return this.attrs[k] ?? null; }
  removeAttribute(k) { delete this.attrs[k]; }
  addEventListener(t, f) { (this.listeners[t] ||= []).push(f); }
  removeEventListener() {}
  click() { (this.listeners.click || []).forEach((f) => f({ currentTarget: this, preventDefault() {} })); }
  focus() {}
  scrollIntoView() {}
  get firstElementChild() { return this.children.find((c) => c instanceof El) || null; }
  get textContent() { return this._text + this.children.map((c) => c.textContent).join(""); }
  set textContent(v) { this.children = []; this._text = String(v); }
  get value() { return this._value ?? ""; }
  set value(v) { this._value = v; }
  matches(sel) {
    const s = sel.trim();
    if (s.startsWith(".")) return this.className.split(/\s+/).includes(s.slice(1));
    return this.tagName === s.toUpperCase();
  }
  closestMatch(sel) { let p = this.parent; while (p) { if (p.matches(sel)) return true; p = p.parent; } return false; }
  all() { return this.children.filter((c) => c instanceof El).flatMap((c) => [c, ...c.all()]); }
  querySelectorAll(sel) {
    const parts = sel.split(",").map((x) => x.trim());
    return this.all().filter((e) => parts.some((p) => {
      const [a, b] = p.split(/\s+/);
      return b ? e.matches(b) && e.closestMatch(a) : e.matches(a);
    }));
  }
  querySelector(sel) { return this.querySelectorAll(sel)[0] || null; }
}
class Text { constructor(t) { this.textContent = t; this.parent = null; } }
global.Node = El;
global.document = { createElement: (t) => new El(t), createTextNode: (t) => new Text(t), body: new El("body") };
global.location = { hash: "#/validacion" };
global.localStorage = { getItem: () => "", setItem() {} };
global.fetch = async () => ({ ok: true, json: async () => ({ fields: [], help: {}, errors: {} }), text: async () => "" });
const timers = [];
global.setInterval = (f) => (timers.push(f), timers.length);
global.clearInterval = () => {};

function h(tag, attrs, ...kids) {
  const el = new El(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "dataset") Object.assign(el.dataset, v);
    else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
    else if (k.startsWith("data-")) el.dataset[k.slice(5)] = String(v);
    else if (v === true) el.setAttribute(k, "");
    else el.setAttribute(k, String(v));
  }
  const add = (c) => { if (c === null || c === undefined || c === false) return; if (Array.isArray(c)) c.forEach(add); else if (c instanceof El || c instanceof Text) el.appendChild(c); else el.appendChild(new Text(String(c))); };
  kids.forEach(add);
  return el;
}
let sheetOpts = null;
const T = { banner: (k, i, ...t) => h("div", { class: "banner" }, t), sheet: (o) => { sheetOpts = o; return { close() {} }; } };
const T42 = { id: 42, id_tarjeta_num: "0042", r1: { nombre: "TQT_R1_V30_0042", version: "30", firmware: "4.9", mac: "AA" }, r2: { nombre: "TQT_R2_V30_0042", version: "30", firmware: "4.10", mac: "BB" }, r3: null };
const T44 = { ...T42, id: 44, id_tarjeta_num: "0044" };
const runRow = { id: "run1", tarjeta_id: 44, requested_card: 42, state: "finished", result: "aprobado", created: 1000, updated: 1100, operator: "op", inventory: { id_tarjeta_num: "0044", nombre: "TQT_R1_V30_0044", mac_r1: "AA", mac_r2: "BB" }, report: { inventory_check: { state: "coincide" }, source_report: { steps: Array.from({ length: 14 }, () => ({ state: "aprobado" })) } } };
async function api(p) {
  if (p.startsWith("/api/tarjetas?")) return { ok: true, data: { items: [T42], total: 1 } };
  if (p === "/api/tarjetas/42") return { ok: true, data: T42 };
  if (p === "/api/tarjetas/44") return { ok: true, data: T44 };
  if (p.startsWith("/api/validacion/tqt/inventory/")) return { ok: true, data: { id: Number(p.split("/").pop()), id_tarjeta_num: "0042", mac_r1: "AA", mac_r2: "BB" } };
  if (p.startsWith("/api/validacion/tqt/runs?")) return { ok: true, data: [] };
  if (p === "/api/validacion/tqt/runs/run1") return { ok: true, data: runRow };
  if (p === "/api/firmware") return { ok: true, data: { R1: ["4.2", "4.10", "4.9"], R2: ["4.10"], R3: [] } };
  return { ok: false, error: "no simulado " + p };
}
let printed = null, ident = null;
global.window = {
  TQTValWeb: {
    soportado: () => true,
    estado: () => ({ serial: { estado: "ok", puerto: "USB" }, ble: { estado: "off", dispositivo: null } }),
    onEstado: () => () => {},
    async iniciar({ tarjetaId, onEvento, confirmarIdentidad }) {
      assert.strictEqual(tarjetaId, 42);
      onEvento({ data: { kind: "step", args: [0, "ejecutando", ""] } });
      ident = await confirmarIdentidad({ seleccionada: "0042", detectada: { id: 44, id_tarjeta_num: "0044" } });
      onEvento({ data: { kind: "status", args: [{ fields: { ON: "1", OFF: "0", VER: "4.9" } }] } });
      for (let i = 0; i < 14; i++) onEvento({ data: { kind: "step", args: [i, "aprobado", "ok"] } });
      return { jid: "run1", resultado: "aprobado" };
    },
  },
  TQTDymoImprimir: { async aprobadaYCable({ tarjeta }) { printed = tarjeta; return { ok: true, impresas: ["tarjeta", "cable"] }; } },
};
let def = null;
window.TQTEscritorio = { registrar: (d) => (def = d) };
eval(fs.readFileSync(path.join(__dirname, "../app/static/js/sec_validacion.js"), "utf8"));

(async () => {
  const host = new El("div");
  const sec = def.montar(host, { h, api, T });
  const lis = () => host.querySelectorAll(".tqt-step");
  assert.strictEqual(lis().length, 14, "14 filas visibles desde el inicio");
  const first = lis()[0];
  assert.ok(lis().every((li) => li.dataset.k === "pend"));
  await new Promise((r) => setTimeout(r, 10));
  const cardBtn = host.querySelector(".tqt-cardbtn");
  assert.ok(cardBtn, "listado de tarjetas");
  cardBtn.click();
  await new Promise((r) => setTimeout(r, 10));
  assert.ok(host.textContent.includes("Versión anterior · objetivo 4.10"), "semáforo naranja R1 (4.9 < 4.10)");
  assert.ok(host.textContent.includes("Vigente"), "semáforo verde R2");
  const start = host.querySelectorAll("button").find((b) => b.textContent === "Iniciar las 14 etapas");
  assert.ok(!start.disabled, "Iniciar habilitado sin casilla de confirmación");
  start.click();
  await new Promise((r) => setTimeout(r, 10));
  assert.ok(sheetOpts && sheetOpts.body[0].textContent.includes("Seleccionaste la tarjeta 0042, pero está conectada la 0044"));
  await sheetOpts.actions[0].onClick();
  await new Promise((r) => setTimeout(r, 30));
  assert.strictEqual(ident, true);
  assert.strictEqual(lis()[0], first, "las filas no se reconstruyen");
  assert.ok(lis().every((li) => li.dataset.k === "ok"));
  assert.ok(lis()[0].textContent.includes("Último ON 1 · OFF 0"), "último par ON/OFF por etapa");
  assert.ok(host.textContent.includes("Aprobada") && host.textContent.includes("14/14"));
  const print = host.querySelectorAll("button").find((b) => b.textContent === "Imprimir etiquetas");
  assert.ok(print && !print.hidden, "botón de impresión visible tras aprobar");
  print.click();
  await new Promise((r) => setTimeout(r, 10));
  assert.strictEqual(printed.id, 44, "imprime la tarjeta confirmada, no la seleccionada al inicio");
  sec.desmontar();
  // Respaldo por agente: estación elegida automáticamente, sin selector ni casilla.
  window.TQTValWeb = undefined;
  const host2 = new El("div");
  const api2 = async (p) => p === "/api/validacion/tqt/stations"
    ? { ok: true, data: [{ id: "a".repeat(24), name: "Laptop banco", online: true, serial_connected: true, port: "COM3", ble_address: "", fields: {} }] }
    : api(p);
  const sec2 = def.montar(host2, { h, api: api2, T });
  await new Promise((r) => setTimeout(r, 20));
  assert.ok(host2.textContent.includes("Agente Windows: Laptop banco · en línea"));
  assert.ok(host2.textContent.includes("Serial: conectado · COM3 (agente)"));
  assert.ok(!host2.querySelectorAll("input").some((i) => i.attrs.type === "checkbox"), "sin casilla de confirmación");
  sec2.desmontar();
  console.log("sec_validacion_ui: OK");
})().catch((e) => { console.error(e); process.exit(1); });
