/* Pruebas TQT: ruta normal en el navegador (Web Serial + Web Bluetooth, K1 window.TQTValWeb);
   respaldo: motor original en el agente Windows. Inventario, eventos y reportes en Docker.
   v1.4.0: banco fijo en modo seguro, 14 etapas fijas, resultado arriba, tarjeta/historial a la derecha,
   semáforo HW/FW, ON/OFF por etapa, ON/OFF BLE, indicadores de conexión, confirmación de identidad. */
(function () {
  "use strict";
  // v1.4.0: nombres de respaldo idénticos a test_station_contract.json para pintar las 14 filas al instante.
  const STEP_NAMES = [
    "Restablecer e identificar R1",
    "Verificar estado inicial del motor",
    "R1 serial · Primer movimiento",
    "R1 serial · Repetición sin movimiento",
    "R1 serial · Movimiento inverso",
    "R1 serial · Repetición inversa",
    "Localizar y conectar R1 BLE",
    "R1 BLE · Primer movimiento",
    "R1 BLE · Repetición sin movimiento",
    "R1 BLE · Movimiento inverso",
    "R1 BLE · Repetición inversa",
    "Desconectar R1 y conectar R2 BLE automáticamente",
    "R2 BLE · Primer movimiento",
    "R2 BLE · Movimiento inverso",
  ];
  const STEP_STATES = {
    pendiente: { k: "pend", icon: "○", txt: "Pendiente" },
    ejecutando: { k: "run", icon: "◐", txt: "En curso" },
    aprobado: { k: "ok", icon: "✓", txt: "Aprobada" },
    fallido: { k: "bad", icon: "✕", txt: "Fallida" },
    no_verificado: { k: "nv", icon: "–", txt: "No verificada" },
    cancelado: { k: "nv", icon: "⊘", txt: "Cancelada" },
  };
  // v1.4.0: compara versiones por sus números (4.10 > 4.9); null si no hay números.
  function verParts(v) {
    const m = String(v ?? "").match(/\d+/g);
    return m ? m.map(Number) : null;
  }
  function cmpVer(a, b) {
    const x = verParts(a), y = verParts(b);
    for (let i = 0; i < Math.max(x.length, y.length); i++) {
      const d = (x[i] || 0) - (y[i] || 0);
      if (d) return d < 0 ? -1 : 1;
    }
    return 0;
  }
  /** Semáforo de vigencia de FW frente al catálogo del rol (R1/R2/R3). */
  function fwSemaforo(registrado, lista) {
    if (!Array.isArray(lista))
      return { k: "unk", txt: "No verificable: catálogo no disponible" };
    const validas = lista.filter((v) => verParts(v));
    if (!validas.length)
      return { k: "unk", txt: "No verificable: sin versiones en el catálogo" };
    const ultima = validas.reduce((a, b) => (cmpVer(a, b) >= 0 ? a : b));
    if (!registrado)
      return { k: "bad", txt: "No programada según el registro", ultima };
    if (!verParts(registrado))
      return { k: "unk", txt: "No verificable: versión registrada ilegible", ultima };
    if (cmpVer(registrado, ultima) >= 0)
      return { k: "ok", txt: "Vigente", ultima };
    return { k: "warn", txt: "Versión anterior · objetivo " + ultima, ultima };
  }
  function montar(host, ctx) {
    const { h, api, T } = ctx;
    let alive = true,
      card = null, // snapshot del inventario para la prueba (/inventory)
      tarjeta = null, // objeto tarjeta de /api/tarjetas (detalle, FW, impresión)
      active = null, // ejecución en curso {id, web}
      lastSeq = 0,
      events = [],
      pollTimer = null,
      tickTimer = null,
      stationId = "",
      stationsCache = [],
      manualBusy = false,
      webAbort = null,
      selSeq = 0,
      listSeq = 0,
      listOffset = 0,
      listQuery = "",
      catalog = undefined, // undefined = cargando, null = falló
      lastRun = null,
      printTarjeta = null,
      lastRunWeb = false,
      contract = { fields: [], help: {}, errors: {} };
    // v1.4.0: estado por ejecución (se reinicia al iniciar; nunca arrastra valores de otra ejecución).
    let run = freshRun();
    function freshRun() {
      return {
        steps: STEP_NAMES.map(() => ({ state: "pendiente", detail: "" })),
        vals: STEP_NAMES.map(() => null),
        current: null,
        started: null,
        ended: null,
        observed: { R1: null, R2: null, card: null, ver: null, hw: null },
        issue: "",
        commands: { serial: 0, ble: 0 },
        cancelRequested: false,
      };
    }
    const checkLabels = {
      card: "Nombre de R1",
      card_id: "Número de R1",
      reported_mac: "MAC R1 del firmware",
      r1_ble_address: "MAC R1 detectada por BLE",
      reported_mac_r2: "MAC R2 del firmware",
      r2_ble_address: "MAC R2 detectada por BLE",
      reported_id_r2: "Identificador de R2",
      state: "Cotejo completo con inventario",
    };
    const web = () => {
      try {
        return !!window.TQTValWeb?.soportado?.();
      } catch (e) {
        return false;
      }
    };
    const status = h("div", { role: "status", "aria-live": "polite" }),
      announcer = h("div", { class: "sr-only", "aria-live": "polite" }),
      port = h("select", { class: "input", "aria-label": "Puerto COM del agente" }),
      stationInfo = h("p", { class: "hint tqt-device-name" });
    const STKEY = "tqt.station.pruebas";
    function savedStation() {
      try { return localStorage.getItem(STKEY) || ""; } catch (e) { return ""; }
    }
    function saveStation(id) {
      try { if (id) localStorage.setItem(STKEY, id); } catch (e) {}
    }
    const search = h("input", {
      class: "input",
      type: "search",
      placeholder: "Número, nombre de R1 o QR",
      "aria-label": "Buscar tarjeta por número, nombre o QR",
    });
    const cardList = h("ul", { class: "tqt-cards", "aria-label": "Tarjetas" }),
      moreBtn = h("button", { class: "btn", type: "button", onclick: () => loadList(true) }, "Cargar más"),
      cardHost = h("div", { class: "tqt-detail" }),
      sensors = h("div", { class: "tqt-sensors" }),
      historyHost = h("div"),
      reportHost = h("div"),
      liveLog = h("pre", { class: "tqt-log tqt-livelog", tabindex: 0 }),
      manualOut = h("p", { class: "hint", "aria-live": "polite" });
    moreBtn.hidden = true;
    // ---- resultado destacado (B.3)
    const sumDot = h("span", { class: "tqt-dot", "aria-hidden": "true" }),
      sumText = h("b", { class: "tqt-sum-text" }, "Sin ejecución"),
      sumCount = h("span", { class: "tqt-sum-count" }, "0/14"),
      sumFacts = h("dl", { class: "tqt-facts" }),
      sumActions = h("div", { class: "row wrap" }),
      printOut = h("p", { class: "hint", "aria-live": "polite" });
    const summary = h(
      "section",
      { class: "prog-panel tqt-card tqt-summary", "data-k": "muted", "aria-label": "Resultado de la ejecución actual" },
      h("div", { class: "tqt-sum-head" }, sumDot, sumText, sumCount),
      sumFacts,
      sumActions,
      printOut,
    );
    const printBtn = h("button", { class: "btn btn-primary", type: "button", onclick: printLabels }, "Imprimir etiquetas");
    const reportBtn = h("button", { class: "btn", type: "button", onclick: () => lastRun && openReport(lastRun.id) }, "Ver reporte completo");
    printBtn.hidden = reportBtn.hidden = true;
    sumActions.append(printBtn, reportBtn);
    // ---- 14 etapas fijas (B.2)
    const steps = h("ol", { class: "tqt-steps", "aria-label": "Etapas de la prueba automática" });
    const rows = STEP_NAMES.map((name, i) => {
      const ind = h("span", { class: "tqt-ind", "aria-hidden": "true" }, "○"),
        nm = h("span", { class: "tqt-step-name" }, i + 1 + ". " + name),
        st = h("span", { class: "tqt-step-state" }, "Pendiente"),
        det = h("span", { class: "tqt-step-detail" }),
        vals = h("span", { class: "tqt-step-vals mono", title: "ON = sensor de CIERRE (1 = perno afuera/bloqueado). OFF = sensor de APERTURA (1 = perno adentro/desbloqueado). No son los comandos PPON/POFF." });
      const li = h("li", { class: "tqt-step", "data-k": "pend" }, ind,
        h("div", { class: "tqt-step-body" }, h("div", { class: "tqt-step-top" }, nm, st), det, vals));
      steps.append(li);
      return { li, ind, nm, st, det, vals };
    });
    const progress = h("progress", { max: 14, value: 0, "aria-label": "Etapas aprobadas" });
    const start = h("button", { class: "btn btn-primary", type: "button", onclick: begin }, "Iniciar las 14 etapas");
    const stop = h(
      "button",
      {
        class: "btn",
        type: "button",
        disabled: true,
        onclick: async () => {
          run.cancelRequested = true;
          if (active?.web) webAbort?.abort();
          else if (active?.id) await call("/runs/" + active.id + "/cancel", {});
          message("Cancelación solicitada. El movimiento actual puede terminar.");
        },
      },
      "Detener prueba",
    );
    // ---- conexiones (B.11)
    function connIndicator(label) {
      const dot = h("span", { class: "tqt-dot", "aria-hidden": "true" }),
        txt = h("span", null, label + ": desconectado"),
        el = h("p", { class: "tqt-conn", "data-k": "off" }, dot, txt);
      return { el, set(k, text) { el.dataset.k = k; txt.textContent = label + ": " + text; } };
    }
    const connSerial = connIndicator("Serial"),
      connBle = connIndicator("Bluetooth");
    const choosePort = h("button", { class: "btn", type: "button", onclick: elegirPuerto }, "Elegir puerto serial");
    const agentBox = h("div", { class: "tqt-agent" });
    const webBox = h("div", { class: "tqt-webbox" }, h("div", { class: "row wrap" }, choosePort));
    const commandSelect = h(
      "select",
      { class: "input", "aria-label": "Comando serial adicional" },
      ...["STATUS", "MOTOR_STATUS", "RESET_BLE", "MAP_QUERY", "MAP_M1_0", "MAP_M1_1", "MAP_M2_0", "MAP_M2_1"].map((x) =>
        h("option", { value: x }, x),
      ),
    );
    const bleOn = h("button", { class: "btn", type: "button", onclick: () => bleManual("ON") }, "ON BLE"),
      bleOff = h("button", { class: "btn", type: "button", onclick: () => bleManual("OFF") }, "OFF BLE");
    const serialManual = h(
      "div",
      { class: "row wrap" },
      button("ON serial", () => cmd("serial", { command: "PPON" })),
      button("OFF serial", () => cmd("serial", { command: "POFF" })),
      button("Reset normal", () => cmd("serial", { command: "RESET" })),
      commandSelect,
      button("Enviar comando", () => cmd("serial", { command: commandSelect.value })),
    );
    agentBox.append(
      stationInfo,
      h("h4", null, "Serial del agente · 57600 baudios · ACK 180 ms"),
      port,
      h(
        "div",
        { class: "row wrap" },
        button("Detectar COM", () => cmd("ports")),
        button("Conectar COM", () => cmd("connect_serial", { port: port.value })),
        button("Desconectar COM", () => cmd("disconnect_serial")),
      ),
      h(
        "div",
        { class: "row wrap" },
        button("Buscar y conectar TQT por BLE", async () => {
          await cmd("scan_ble");
          if (bleFound) await cmd("connect_ble", { address: bleFound });
        }),
        button("Desconectar BLE", () => cmd("disconnect_ble")),
      ),
      h("h4", null, "Comandos serial (agente)"),
      serialManual,
      h(
        "details",
        { class: "tqt-install" },
        h("summary", null, "Instalar agente de pruebas (respaldo)"),
        h("p", { class: "hint" }, "Solo si este navegador no admite Web Serial/Web Bluetooth. Extrae el paquete privado y ejecuta iniciar.cmd una vez."),
        button("Descargar agente de pruebas", install),
      ),
    );
    let bleFound = "";
    const modeHint = h("p", { class: "hint" });
    host.append(
      h("h2", null, "Pruebas TQT"),
      h("p", { class: "hint tqt-bench" }, "Banco de pruebas · modo seguro"),
      modeHint,
      status,
      announcer,
      h(
        "div",
        { class: "tqt-layout" },
        h(
          "div",
          { class: "tqt-col tqt-main" },
          summary,
          h(
            "section",
            { class: "prog-panel tqt-card" },
            h("h3", null, "Prueba automática"),
            h("div", { class: "row wrap" }, start, stop),
            progress,
            h("p", { class: "hint" }, "ON = sensor de cierre · OFF = sensor de apertura (valores crudos 0/1; no son los comandos PPON/POFF)."),
            steps,
            h(
              "details",
              { class: "tqt-livewrap" },
              h("summary", null, "Registro de comandos y respuestas (en vivo)"),
              liveLog,
            ),
          ),
          h(
            "section",
            { class: "prog-panel tqt-card" },
            h("h3", null, "Conexiones"),
            connSerial.el,
            connBle.el,
            webBox,
            agentBox,
          ),
          h(
            "section",
            { class: "prog-panel tqt-card" },
            h("h3", null, "Controles manuales Bluetooth"),
            h("div", { class: "row wrap" }, bleOn, bleOff),
            manualOut,
          ),
          h(
            "section",
            { class: "prog-panel tqt-card" },
            h("h3", null, "Sensores y estados S29"),
            sensors,
          ),
        ),
        h(
          "aside",
          { class: "tqt-col tqt-side" },
          h(
            "section",
            { class: "prog-panel tqt-card" },
            h("h3", null, "Tarjeta e inventario"),
            h("label", { class: "sr-only", for: "tqt-search" }, "Buscar tarjeta"),
            search,
            h(
              "div",
              { class: "row wrap" },
              button("Cargar QR / código", () => scan(search.value)),
            ),
            cardList,
            moreBtn,
            cardHost,
          ),
          h(
            "section",
            { class: "prog-panel tqt-card" },
            h("h3", null, "Historial de la tarjeta seleccionada"),
            historyHost,
          ),
        ),
      ),
      reportHost,
    );
    search.id = "tqt-search";
    function button(text, fn) {
      return h("button", { class: "btn", type: "button", onclick: fn }, text);
    }
    function message(text, bad = false) {
      status.replaceChildren(T.banner(bad ? "bad" : "info", bad ? "alert" : "info", text));
    }
    async function call(path, body) {
      const r = await api("/api/validacion/tqt" + path, body !== undefined ? { method: "POST", body } : undefined);
      if (!r.ok) {
        message(r.error, true);
        throw Error(r.error);
      }
      return r.data;
    }
    const fmtDate = (s) => (s ? new Date(s * 1000).toLocaleString() : "—");
    function fmtDur(s) {
      if (s === null || s === undefined || !isFinite(s) || s < 0) return "—";
      s = Math.round(s);
      return s < 60 ? s + " s" : Math.floor(s / 60) + " min " + (s % 60) + " s";
    }
    const cardNum = (t) => (t ? String(t.id_tarjeta_num ?? t.numero ?? t.id ?? "") : "");
    // ---------------------------------------------------------------- tarjetas (B.4)
    let searchTimer = null;
    search.addEventListener("input", () => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => loadList(false), 300);
    });
    search.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        clearTimeout(searchTimer);
        const v = search.value.trim();
        // Código largo (QR/MAC) → ficha directa; número o nombre → filtro del listado.
        if (v.length > 12) scan(v);
        else loadList(false);
      }
    });
    async function loadList(more) {
      const my = ++listSeq;
      if (!more) {
        listOffset = 0;
        listQuery = search.value.trim();
      }
      const q = new URLSearchParams({ limit: "20", offset: String(listOffset) });
      if (listQuery) q.set("search", listQuery);
      const r = await api("/api/tarjetas?" + q);
      if (my !== listSeq || !alive) return;
      if (!r.ok) {
        cardList.replaceChildren(h("li", { class: "tqt-empty" }, "No se pudo cargar el listado: " + r.error));
        moreBtn.hidden = true;
        return;
      }
      const items = r.data.items || [];
      if (!more) cardList.replaceChildren();
      for (const t of items) cardList.append(cardItem(t));
      listOffset += items.length;
      moreBtn.hidden = listOffset >= (r.data.total || 0);
      if (!cardList.children.length)
        cardList.append(
          h("li", { class: "tqt-empty" }, listQuery ? "Sin tarjetas para «" + listQuery + "» en el lote activo. Prueba con el QR o el nombre completo." : "El lote activo no tiene tarjetas."),
        );
    }
    function cardItem(t) {
      const b = h(
        "button",
        { class: "tqt-cardbtn", type: "button", "aria-pressed": String(tarjeta?.id === t.id), "data-id": t.id, onclick: () => selectCard(t) },
        h("b", null, cardNum(t)),
        h("span", { class: "mono" }, t.r1?.nombre || "R1 sin registrar"),
      );
      return h("li", null, b);
    }
    function markSelected() {
      cardList.querySelectorAll(".tqt-cardbtn").forEach((b) => b.setAttribute("aria-pressed", String(String(tarjeta?.id) === b.dataset.id)));
    }
    async function selectCard(t, opts = {}) {
      if ((active || manualBusy) && !opts.force) {
        message("Prueba en curso: la tarjeta cambia solo al confirmar la identidad detectada.", true);
        return false;
      }
      const my = ++selSeq;
      tarjeta = t;
      card = null;
      markSelected();
      cardHost.replaceChildren(h("p", { class: "hint" }, "Cargando tarjeta " + cardNum(t) + "…"));
      historyHost.replaceChildren(h("p", { class: "hint" }, "Cargando historial…"));
      const [det, inv] = await Promise.all([api("/api/tarjetas/" + t.id), api("/api/validacion/tqt/inventory/" + t.id)]);
      if (my !== selSeq || !alive) return false; // respuesta de una selección anterior: se ignora
      tarjeta = det.ok ? det.data : t;
      card = inv.ok ? inv.data : null;
      paintCard(inv.ok ? "" : inv.error);
      await history(my);
      updateControls();
      return true;
    }
    async function scan(code) {
      code = String(code || "").trim();
      if (!code) return { ok: false, texto: "Escribe o escanea un código." };
      if (active || manualBusy) return { ok: false, texto: "Prueba en curso." };
      const r = await api("/api/consulta?codigo=" + encodeURIComponent(code));
      if (!r.ok) {
        message(r.error, true);
        return { ok: false, texto: r.error };
      }
      const t = r.data.tarjeta || r.data.serie?.tarjeta;
      if (!t) {
        message("No hay una tarjeta emparejada para este código. Regístrala o empareja sus PCB desde Inventario; no se inventan identificadores.", true);
        return { ok: false };
      }
      const ok = await selectCard(t);
      return { ok: ok && !!card };
    }
    function paintCard(err) {
      if (!tarjeta) {
        cardHost.replaceChildren(h("p", { class: "tqt-empty" }, "Selecciona una tarjeta del listado o escanea su QR."));
        return;
      }
      const t = tarjeta;
      const sameRun = run.observed && lastRunCard() === t.id;
      const pcb = (p, rol) => {
        if (!p) return null;
        const sem = fwSemaforo(p.firmware, catalog === undefined ? [] : catalog ? catalog[rol] : null);
        const leido = rol === "R1" && sameRun && run.observed.ver ? run.observed.ver : null;
        const semK = catalog === undefined ? { k: "unk", txt: "Comprobando catálogo…" } : sem;
        return h(
          "div",
          { class: "tqt-pcb" },
          h("div", { class: "tqt-pcb-head" }, h("b", null, rol), h("span", { class: "mono" }, p.nombre || "—")),
          h(
            "dl",
            { class: "tqt-kv" },
            h("dt", null, "HW"), h("dd", null, p.version ? "V" + p.version : "no disponible"),
            h("dt", null, "FW registrado"), h("dd", null, p.firmware || "sin registro"),
            h("dt", null, "FW leído"), h("dd", null, rol === "R1" ? leido || "sin lectura en esta ejecución" : "no disponible"),
            h("dt", null, "Última compatible"), h("dd", null, sem.ultima || "—"),
            rol !== "R3" ? [h("dt", null, "MAC " + rol + " (registrada)"), h("dd", { class: "mono" }, p.mac || "sin registro")] : null,
          ),
          h("p", { class: "tqt-sem", "data-k": semK.k }, h("span", { class: "tqt-dot", "aria-hidden": "true" }), "FW: " + semK.txt),
        );
      };
      cardHost.replaceChildren(
        ...[
          h("h4", { class: "tqt-detail-title" }, "Tarjeta " + cardNum(t)),
          err ? T.banner("bad", "alert", err + " No se puede iniciar la prueba con esta tarjeta.") : null,
          pcb(t.r1, "R1"),
          pcb(t.r2, "R2"),
          pcb(t.r3, "R3"),
        ].filter(Boolean),
      );
    }
    // v1.4.0: tarjeta a la que pertenecen las lecturas físicas de la ejecución mostrada.
    const lastRunCard = () => (active ? active.tarjetaId : lastRun?.tarjeta_id ?? null);
    api("/api/firmware").then((r) => {
      catalog = r.ok && r.data ? r.data : null;
      if (alive) paintCard("");
    });
    // ---------------------------------------------------------------- estaciones (respaldo agente)
    async function stations() {
      if (web()) return;
      const list = await call("/stations");
      stationsCache = list;
      const online = list.filter((s) => s.online);
      // v1.4.0: sin selector; se elige automáticamente la estación en línea (la anterior si sigue conectada).
      const pick =
        online.find((s) => s.id === stationId) ||
        online.find((s) => s.id === savedStation()) ||
        online[0] ||
        list.find((s) => s.id === stationId) ||
        list.find((s) => s.id === savedStation()) ||
        null;
      stationId = pick?.id || "";
      if (pick?.online) saveStation(stationId);
      stationInfo.textContent = pick
        ? "Agente Windows: " + pick.name + (pick.online ? " · en línea" : " · sin conexión") + (online.length > 1 ? " (" + online.length + " en línea; se usa esta)" : "")
        : "No hay agente de pruebas registrado.";
      if (!pick || !pick.online) connSerial.set("off", pick ? "agente sin conexión" : "sin agente");
      else if (pick.serial_connected) connSerial.set("ok", "conectado · " + (pick.port || "COM") + " (agente)");
      else connSerial.set("off", "desconectado (agente en línea)");
      if (pick?.online && pick.ble_address) connBle.set("ok", "conectado · " + pick.ble_address);
      else connBle.set("off", "desconectado");
      if (pick?.fields && !active) paintSensors(pick.fields);
      updateControls();
    }
    const curStation = () => stationsCache.find((s) => s.id === stationId);
    // ---------------------------------------------------------------- ruta web (K1)
    let unsubEstado = null, unsubMonitor = null;
    function paintWebEstado() {
      let e = null;
      try {
        e = window.TQTValWeb?.estado?.();
      } catch (x) {}
      const map = { off: "off", conectando: "wait", ok: "ok", error: "bad" };
      const s = e?.serial || {}, b = e?.ble || {};
      const txt = (o, def) => ({ off: "desconectado", conectando: "conectando…", ok: "conectado", error: "error" })[o.estado] || def;
      connSerial.set(map[s.estado] || "off", txt(s, "desconectado") + (s.puerto ? " · " + s.puerto : "") + (s.texto ? " · " + s.texto : ""));
      connBle.set(map[b.estado] || "off", txt(b, "desconectado") + (b.dispositivo ? " · " + b.dispositivo : "") + (b.texto ? " · " + b.texto : ""));
      updateControls();
    }
    async function elegirPuerto() {
      try {
        await window.TQTValWeb?.elegirPuerto?.();
      } catch (e) {
        message("No se eligió puerto: " + (e?.message || e), true);
      }
      paintWebEstado();
    }
    function confirmarIdentidad({ seleccionada, detectada }) {
      // v1.4.0 (B.12): diálogo que pausa la rutina; true = continuar con la detectada sin reiniciar.
      const sel = typeof seleccionada === "object" && seleccionada ? cardNum(seleccionada) : String(seleccionada ?? "");
      const det = typeof detectada === "object" && detectada ? cardNum(detectada) : String(detectada ?? "");
      return new Promise((resolve) => {
        let done = false;
        const fin = (v) => {
          if (done) return;
          done = true;
          resolve(v);
        };
        T.sheet({
          title: "Tarjeta conectada distinta",
          body: [
            h("p", null, "Seleccionaste la tarjeta " + sel + ", pero está conectada la " + det + ". ¿Deseas continuar con la tarjeta " + det + "?"),
            h("p", { class: "hint" }, "Se registran la selección inicial, la tarjeta detectada y tu consentimiento. El resultado se guarda solo bajo la tarjeta " + det + "."),
          ],
          actions: [
            {
              label: "Continuar con " + det,
              kind: "primary",
              onClick: async () => {
                fin(true);
                const detId = typeof detectada === "object" ? detectada?.tarjeta_id ?? detectada?.id : null;
                if (detId) {
                  if (active) active.tarjetaId = detId;
                  await selectCard({ id: detId, id_tarjeta_num: det }, { force: true });
                }
                message("Continuando con la tarjeta " + det + ".");
              },
            },
            { label: "Cancelar", kind: "ghost", onClick: () => fin(false) },
          ],
          onClose: () => fin(false),
        });
      });
    }
    function solicitarGesto(signal) {
      // v1.4.0: Web Bluetooth necesita un gesto; autorizar() se llama dentro del clic (sin await previo).
      return ({ dispositivo, nombre, autorizar }) =>
        new Promise((resolve, reject) => {
          const Int = window.TQTValWeb?._interno?.Interrupted || Error;
          let done = false, hoja = null;
          const fin = (ok, v) => {
            if (done) return;
            done = true;
            signal?.removeEventListener("abort", ab);
            ok ? resolve(v) : reject(v);
          };
          const ab = () => {
            fin(false, new Int("Prueba detenida por el usuario"));
            try { hoja?.close(); } catch (e) {}
          };
          const txt = h("p", null, "La prueba necesita permiso de Bluetooth para " + dispositivo + ". Pulsa «Autorizar» y elige «" + nombre + "» en el selector del navegador.");
          hoja = T.sheet({
            title: "Autorizar Bluetooth " + dispositivo,
            body: [txt],
            actions: [
              {
                label: "Autorizar " + dispositivo + " BLE",
                kind: "primary",
                onClick: () =>
                  autorizar().then(
                    (d) => fin(true, d),
                    (e) => {
                      txt.textContent = "No se autorizó (" + (e?.message || e) + "). Reintenta o cancela.";
                      return false;
                    },
                  ),
              },
              { label: "Cancelar prueba", kind: "ghost", onClick: () => fin(false, new Int("Cancelada: no se autorizó Bluetooth " + dispositivo)) },
            ],
            onClose: () => fin(false, new Int("Cancelada: no se autorizó Bluetooth " + dispositivo)),
          });
          signal?.addEventListener("abort", ab, { once: true });
        });
    }
    async function bleManual(accion) {
      if (active || manualBusy) return;
      if (!web()) return cmd("ble", { command: accion === "ON" ? "PPON" : "POFF" });
      const dispositivo = window.TQTValWeb?.estado?.()?.ble?.dispositivo;
      if (!dispositivo) {
        manualOut.textContent = "Bluetooth desconectado: conecta R1 o R2 antes de enviar " + accion + ".";
        return;
      }
      manualBusy = true;
      updateControls();
      manualOut.textContent = "Enviando " + accion + " a " + dispositivo + "…";
      try {
        const r = await window.TQTValWeb.bleManual({ dispositivo, accion });
        manualOut.textContent = r?.ok
          ? accion + " → " + dispositivo + " · enviado " + (r.enviado || "—") + " · respuesta " + (r.respuesta || "sin respuesta")
          : accion + " → " + dispositivo + " · error: " + (r?.error || "sin respuesta");
      } catch (e) {
        manualOut.textContent = accion + " → " + dispositivo + " · error: " + (e?.message || e);
      } finally {
        manualBusy = false;
        paintWebEstado();
      }
    }
    // ---------------------------------------------------------------- controles
    function updateControls() {
      const isWeb = web();
      const busy = !!active || manualBusy;
      webBox.hidden = !isWeb;
      agentBox.hidden = isWeb;
      modeHint.textContent = isWeb
        ? "Conexión directa desde este navegador (Web Serial y Web Bluetooth). El inventario conserva cada ejecución."
        : "Este navegador no admite conexión directa: se usa el agente de pruebas de Windows en línea. El inventario conserva cada ejecución.";
      const s = curStation();
      const ready = isWeb ? true : !!(s?.online && s.serial_connected);
      start.disabled = busy || !card || !ready;
      stop.disabled = !active;
      search.disabled = !!active;
      cardList.querySelectorAll("button").forEach((b) => (b.disabled = !!active));
      choosePort.disabled = busy;
      agentBox.querySelectorAll("button,select").forEach((b) => (b.disabled = busy || !s?.online));
      agentBox.querySelectorAll(".tqt-install button").forEach((b) => (b.disabled = busy));
      let dev = null, bleOk = false;
      if (isWeb) {
        const b = window.TQTValWeb?.estado?.()?.ble;
        bleOk = b?.estado === "ok";
        dev = b?.dispositivo || null;
      } else {
        bleOk = !!(s?.online && s.ble_address);
      }
      bleOn.disabled = bleOff.disabled = busy || !bleOk;
      bleOn.textContent = "ON BLE" + (dev ? " · " + dev : "");
      bleOff.textContent = "OFF BLE" + (dev ? " · " + dev : "");
      if (bleOk && manualOut.textContent.startsWith("Bluetooth desconectado")) manualOut.textContent = "";
      if (!bleOk && !busy) manualOut.textContent ||= "Bluetooth desconectado: los controles manuales se habilitan al conectar R1 o R2.";
      if (active) manualOut.textContent = "Bloqueados: la prueba automática usa el transporte.";
      else if (manualOut.textContent.startsWith("Bloqueados")) manualOut.textContent = "";
    }
    // ---------------------------------------------------------------- etapas, eventos y resumen
    function setStep(idx, state, detail) {
      const r = rows[idx];
      if (!r) return;
      const prev = run.steps[idx].state;
      run.steps[idx] = { state, detail: detail || "" };
      if (state === "ejecutando") run.current = idx;
      else if (run.current === idx) run.current = null;
      paintStep(idx);
      if (prev !== state) announcer.textContent = "Etapa " + (idx + 1) + ": " + (STEP_STATES[state]?.txt || state);
      progress.value = run.steps.filter((s) => s.state === "aprobado").length;
    }
    function paintStep(idx) {
      const r = rows[idx], s = run.steps[idx];
      const m = STEP_STATES[s.state] || { k: "nv", icon: "?", txt: s.state };
      r.li.dataset.k = m.k;
      r.ind.textContent = m.icon;
      r.st.textContent = m.txt;
      r.det.textContent = s.detail || "";
      if (s.state === "ejecutando") r.li.setAttribute("aria-current", "step");
      else r.li.removeAttribute("aria-current");
      const v = run.vals[idx];
      if (!v) r.vals.textContent = s.state === "pendiente" ? "" : "ON/OFF: sin dato nuevo";
      else {
        const pair = (p) => "ON " + (p.ON ?? "—") + " · OFF " + (p.OFF ?? "—");
        let t = "Último " + pair(v.last) + " · " + new Date(v.last.t).toLocaleTimeString() + " · fuente S29";
        if (v.first !== v.last && (v.first.ON !== v.last.ON || v.first.OFF !== v.last.OFF)) t += " · inicio " + pair(v.first);
        if (v.last.ON === "1" && v.last.OFF === "1") t += " · conflicto de sensores";
        r.vals.textContent = t;
      }
    }
    function resetSteps() {
      run.steps.forEach((_, i) => {
        run.steps[i] = { state: "pendiente", detail: "" };
        run.vals[i] = null;
        paintStep(i);
      });
      run.current = null;
      progress.value = 0;
    }
    function logLine(text) {
      const lines = (liveLog.textContent ? liveLog.textContent.split("\n") : []).slice(-400);
      lines.push(text);
      liveLog.textContent = lines.join("\n");
      if (/^\s*(>|TX|→)/i.test(text)) /BLE/i.test(text) ? run.commands.ble++ : run.commands.serial++;
    }
    // v1.4.0: un único manejador para eventos del agente (poll) y del motor web (onEvento); misma forma.
    function handleEvent(e) {
      const d = e?.data || e;
      if (!d) return;
      events.push(e);
      const a = d.args || [];
      switch (d.kind) {
        case "status": {
          const fields = a[0]?.fields || {};
          paintSensors(fields);
          if (fields.VER) run.observed.ver = fields.VER;
          if (fields.HW) run.observed.hw = fields.HW;
          if (run.current !== null && (fields.ON !== undefined || fields.OFF !== undefined)) {
            const p = { ON: fields.ON, OFF: fields.OFF, t: Date.now() };
            const v = run.vals[run.current];
            run.vals[run.current] = v ? { first: v.first, last: p } : { first: p, last: p };
            paintStep(run.current);
          }
          break;
        }
        case "step":
          setStep(a[0], a[1], a[2]);
          break;
        case "reset_steps":
          resetSteps();
          break;
        case "log":
          logLine(String(a[0] ?? ""));
          break;
        case "warning":
          logLine("ADVERTENCIA: " + (a[0] ?? ""));
          break;
        case "ble_ident":
          if (a[0] === "R1" || a[0] === "R2") run.observed[a[0]] = { name: a[1], address: a[2], check: a[3] };
          break;
        case "card":
          run.observed.card = a[0];
          break;
        case "done":
          run.issue = a[1] || "";
          // v1.4.0: el motor web marca la cancelación en el tercer argumento ({cancelada}).
          if (a[2]?.cancelada) run.cancelRequested = true;
          break;
        case "identity_prompt":
          // El motor ya escribe la línea IDENTIDAD en el LOG; la UI muestra el diálogo vía confirmarIdentidad.
          announcer.textContent = "Tarjeta conectada distinta: confirma si continúas con la " + cardNum(a[0]?.detectada) + ".";
          break;
        case "identity_change": {
          // v1.4.0 (B.12): identidad confirmada; las evidencias siguientes son de la detectada.
          const det = a[0]?.detectada;
          if (det?.tarjeta_id && active) active.tarjetaId = det.tarjeta_id;
          run.observed.identityChange = a[0] || null;
          break;
        }
      }
      paintSummary();
    }
    function resultView(r) {
      const n = run.steps.filter((s) => s.state === "aprobado").length;
      if (active) return { k: "info", txt: "En curso", n };
      if (!r) return run.started ? { k: "warn", txt: run.cancelRequested ? "Cancelada" : "Incompleta", n } : { k: "muted", txt: "Sin ejecución", n };
      const cot = r.report?.inventory_check?.state;
      if (r.cancel || run.cancelRequested) return { k: "muted", txt: "Cancelada · no verificada", n };
      if (r.state === "interrupted") return { k: "warn", txt: "Interrumpida · no verificada", n };
      if (r.result === "aprobado") return n === 14 && cot === "coincide" ? { k: "ok", txt: "Aprobada", n } : { k: "warn", txt: "No verificada (cotejo o etapas incompletos)", n };
      if (r.result === "aprobado_con_advertencias") return { k: "warn", txt: "Aprobada con advertencias", n };
      if (r.result === "fallido") return { k: "bad", txt: "Fallida", n };
      return { k: "warn", txt: "No verificada", n };
    }
    function paintSummary() {
      const r = active ? null : lastRun;
      const v = resultView(r);
      summary.dataset.k = v.k;
      sumText.textContent = v.txt;
      sumCount.textContent = v.n + "/14";
      const inv = r?.inventory || card || {};
      const rep = r?.report?.source_report || {};
      const o = run.observed;
      const na = "pendiente / no disponible";
      const started = r?.created || run.started;
      const ended = r && !["queued", "running"].includes(r.state) ? r.updated : run.ended;
      const fact = (k, val, mono) => [h("dt", null, k), h("dd", mono ? { class: "mono" } : null, val || na)];
      sumFacts.replaceChildren(
        ...fact("Tarjeta", inv.id_tarjeta_num ? inv.id_tarjeta_num + " · " + (inv.nombre || "") : tarjeta ? cardNum(tarjeta) : ""),
        ...fact("R1 MAC registrada", inv.mac_r1, true),
        ...fact("R1 MAC del firmware", rep.reported_mac, true),
        ...fact("R1 BLE observada", rep.r1_ble_address || o.R1?.address, true),
        ...fact("R2 " + (inv.r2_nombre || "") + " MAC registrada", inv.mac_r2, true),
        ...fact("R2 MAC del firmware", rep.reported_mac_r2, true),
        ...fact("R2 BLE observada", rep.r2_ble_address || o.R2?.address, true),
        ...fact("Inicio", started ? fmtDate(started) : ""),
        ...fact("Duración", started ? fmtDur((ended || Date.now() / 1000) - started) : ""),
        ...fact("HW / FW leídos", rep.hardware || o.hw || rep.firmware || o.ver ? "HW " + (rep.hardware || o.hw || "—") + " · FW " + (rep.firmware || o.ver || "—") : ""),
        ...fact("Interfaz", (active ? active.web : r?.station === "web" || lastRunWeb) ? "Navegador · Web Serial 57600 + Web Bluetooth" : started ? "Agente Windows · serial 57600 + BLE" : ""),
        ...fact("Comandos", started ? run.commands.serial + " serial · " + run.commands.ble + " BLE registrados" + (r ? " · LOG completo en el reporte" : "") : ""),
        ...(run.issue ? fact("Motivo", run.issue) : []),
      );
      const eligible = !!r && r.result === "aprobado" && v.k === "ok";
      printBtn.hidden = !eligible;
      reportBtn.hidden = !r;
    }
    async function finishRun(r) {
      lastRun = r;
      lastRunWeb = !!active?.web;
      active = null;
      clearInterval(tickTimer);
      run.ended = Date.now() / 1000;
      // Sincroniza las filas con el reporte final del servidor (fuente de verdad), sin reconstruir la lista.
      const repSteps = r?.report?.source_report?.steps || [];
      repSteps.forEach((s, i) => {
        if (i < 14 && s?.state && s.state !== run.steps[i].state) setStep(i, s.state, s.detail);
      });
      const why = run.cancelRequested || r?.cancel ? "Cancelada antes de ejecutarse" : "No se ejecutó: " + (run.issue || r?.report?.source_report?.issue || "la ejecución terminó antes");
      run.steps.forEach((s, i) => {
        if (s.state === "pendiente") setStep(i, run.cancelRequested || r?.cancel ? "cancelado" : "no_verificado", why);
        else if (s.state === "ejecutando") setStep(i, "no_verificado", "Interrumpida sin resultado final");
      });
      printTarjeta = null;
      printOut.textContent = "";
      if (r?.tarjeta_id && r.result === "aprobado") {
        const t = await api("/api/tarjetas/" + r.tarjeta_id);
        printTarjeta = t.ok ? t.data : null;
      }
      // Si la identidad confirmada es otra tarjeta, la selección pasa a ella (nunca al revés).
      if (r?.tarjeta_id && tarjeta?.id !== r.tarjeta_id) await selectCard(printTarjeta || { id: r.tarjeta_id }, { force: true });
      paintSummary();
      paintCard("");
      updateControls();
      if (tarjeta) await history(selSeq);
      announcer.textContent = "Prueba terminada: " + sumText.textContent + " " + sumCount.textContent;
    }
    async function printLabels() {
      // v1.4.0 (B.7/8): K2. Evita doble clic; un clic intencional posterior es reimpresión trazable.
      const P = window.TQTDymoImprimir;
      if (!P?.aprobadaYCable) {
        printOut.textContent = "El módulo de impresión DYMO no está disponible en esta página. Recarga o revisa la configuración de DYMO.";
        return;
      }
      if (!printTarjeta) {
        printOut.textContent = "No se pudo cargar la tarjeta confirmada de esta ejecución; no se imprime con datos de otra.";
        return;
      }
      printBtn.disabled = true;
      printOut.textContent = "Imprimiendo etiquetas de la tarjeta " + cardNum(printTarjeta) + "…";
      try {
        // v1.4.0: el clic es un gesto del operador; sin DYMO Connect se usa el diálogo de impresión del navegador.
        const r = await P.aprobadaYCable({ tarjeta: printTarjeta, respaldoNavegador: true });
        const n = (r?.impresas || []).length;
        printOut.textContent = r?.ok && r.via === "navegador"
          ? "Sin DYMO Connect: se abrió el cuadro de impresión del navegador con las 2 etiquetas; elige la LabelWriter y confirma la salida física."
          : r?.ok
          ? "Enviadas " + n + "/2 a la impresora (envío a cola; confirma la salida física)."
          : "Enviadas " + n + "/2. Error: " + (r?.error || "sin detalle") + ". Puedes reintentar.";
        printBtn.textContent = "Reimprimir etiquetas";
      } catch (e) {
        printOut.textContent = "Error al imprimir: " + (e?.message || e) + ". Puedes reintentar.";
      } finally {
        printBtn.disabled = false;
      }
    }
    // ---------------------------------------------------------------- sensores
    function paintSensors(fields) {
      const labels = {
        ON: { 0: "Cierre inactivo", 1: "Sensor de cierre activo" },
        OFF: { 0: "Apertura inactiva", 1: "Sensor de apertura activo" },
        PB: { 0: "Sistema", 1: "Serial / plataforma", 2: "Bluetooth" },
        TQT: { 0: "En espera", 1: "Abriendo", 2: "Abierto", 3: "Cerrando", 4: "Cerrado", 5: "Error" },
      };
      const position = fields.ON === undefined || fields.OFF === undefined
        ? "Sin lectura S29"
        : fields.ON === "0" && fields.OFF === "1" ? "Perno abierto"
          : fields.ON === "1" && fields.OFF === "0" ? "Perno cerrado"
            : fields.ON === "1" && fields.OFF === "1" ? "Conflicto: ambos sensores activos" : "Posición no confirmada por sensores";
      sensors.replaceChildren(
        h("p", { class: "tqt-sensors-summary" }, position),
        ...(contract.fields.length ? contract.fields : Object.keys(fields)).map(
          (key) =>
            h(
              "dl",
              { class: "tqt-sensor", title: contract.help[key] || key,
                "data-error": (key === "err" && ["3", "4"].includes(fields[key])) || (key === "TQT" && fields[key] === "5") ? "true" : "false" },
              h("dt", null, key),
              h("dd", { class: "mono" }, fields[key] ?? "—",
                h("small", { class: "tqt-state-label" }, key === "err" ? contract.errors[fields[key]] || "Sin lectura" : key === "MOV" ? "Movimientos registrados" : labels[key]?.[fields[key]] || "")),
            ),
        ),
      );
    }
    // ---------------------------------------------------------------- comandos del agente (respaldo)
    async function cmd(action, body = {}) {
      if (active || manualBusy || !stationId) return;
      manualBusy = true;
      updateControls();
      try {
        const j = await call("/commands", { station_id: stationId, tarjeta_id: card?.id, action, ...body });
        let result;
        for (let i = 0; i < 90 && alive; i++) {
          const r = await call("/commands/" + j.id);
          if (["done", "error"].includes(r.state)) {
            result = r.result;
            break;
          }
          await new Promise((resolve) => setTimeout(resolve, 1000));
        }
        if (!result?.ok) throw Error(result?.error || "Comando sin resultado; no se repite automáticamente.");
        if (action === "ports") port.replaceChildren(...result.data.map((x) => h("option", { value: x }, x)));
        if (action === "scan_ble") {
          // v1.4.0: se toma la primera TQT encontrada (sin selector); el motor verifica identidad después.
          bleFound = result.data[0]?.address || "";
          if (!bleFound) throw Error("No se encontró ninguna TQT por Bluetooth.");
        }
        if (action === "ble") manualOut.textContent = body.command + " enviado por BLE · " + (result.data ? JSON.stringify(result.data) : "sin respuesta");
        message("Acción completada: " + action);
      } catch (e) {
        if (action === "ble") manualOut.textContent = body.command + " por BLE · error: " + e.message;
        message(e.message, true);
      } finally {
        manualBusy = false;
        await stations().catch(() => {});
        updateControls();
      }
    }
    // ---------------------------------------------------------------- ejecución
    function prepareRun(web_) {
      run = freshRun();
      run.started = Date.now() / 1000;
      lastRun = null;
      lastSeq = 0;
      events = [];
      liveLog.textContent = "";
      printOut.textContent = "";
      printBtn.textContent = "Imprimir etiquetas";
      reportHost.replaceChildren();
      resetSteps();
      active = { id: null, web: web_, tarjetaId: tarjeta?.id ?? null };
      clearInterval(tickTimer);
      tickTimer = setInterval(() => alive && active && paintSummary(), 1000);
      updateControls();
      paintSummary();
    }
    async function begin() {
      if (!card) {
        message("Selecciona una tarjeta con R1 y R2 emparejadas antes de iniciar.", true);
        return;
      }
      // v1.4.0 (B.1): pulsar Iniciar es la intención del operador; contexto fijo de banco seguro.
      if (web()) return beginWeb();
      try {
        prepareRun(false);
        active.id = (await call("/runs", { station_id: stationId, tarjeta_id: card.id, physical_confirmed: true, banco: "seguro" })).id;
        message("Prueba iniciada. No cambies la tarjeta ni envíes comandos desde otro programa.");
        poll();
      } catch (e) {
        active = null;
        clearInterval(tickTimer);
        run.started = null;
        updateControls();
        paintSummary();
      }
    }
    async function beginWeb() {
      prepareRun(true);
      webAbort = new AbortController();
      message("Prueba iniciada en este navegador. No cierres la pestaña ni cambies de tarjeta.");
      let jid = null, err = null;
      try {
        const res = await window.TQTValWeb.iniciar({
          tarjetaId: card.id,
          onEvento: (e) => alive && handleEvent(e),
          confirmarIdentidad,
          solicitarGesto: solicitarGesto(webAbort.signal),
          signal: webAbort.signal,
        });
        jid = res?.jid || null;
        if (active) active.id = jid;
      } catch (e) {
        err = e;
        jid = e?.jid || active?.id || null;
      }
      webAbort = null;
      let r = null;
      if (jid) {
        try {
          r = await call("/runs/" + jid);
        } catch (e) {}
      }
      if (err && !run.cancelRequested) message("La prueba se detuvo: " + (err.message || err), true);
      else if (!err) message("Prueba terminada.");
      await finishRun(r);
    }
    async function poll() {
      if (!alive || !active || active.web) return;
      try {
        const batch = await call("/runs/" + active.id + "/events?after=" + lastSeq);
        for (const e of batch) {
          if (e.seq <= lastSeq) continue;
          lastSeq = e.seq;
          handleEvent(e);
        }
        const r = await call("/runs/" + active.id);
        if (!["queued", "running"].includes(r.state)) {
          await finishRun(r);
          return;
        }
      } catch (e) {
        message("Conexión pendiente. No repitas la prueba; se conserva la evidencia recibida.", true);
      }
      pollTimer = setTimeout(poll, 1000);
    }
    async function history(my = selSeq) {
      if (!tarjeta) return;
      const tid = tarjeta.id;
      let rows_;
      try {
        rows_ = await call("/runs?tarjeta_id=" + tid);
      } catch (e) {
        if (my === selSeq) historyHost.replaceChildren(h("p", { class: "tqt-empty" }, "No se pudo cargar el historial."));
        return;
      }
      if (my !== selSeq || !alive) return; // historial de una selección anterior
      const label = (r) => {
        const map = { aprobado: "Aprobada", aprobado_con_advertencias: "Aprobada con advertencias", fallido: "Fallida", no_verificado: "No verificada" };
        if (["queued", "running"].includes(r.state)) return "En curso";
        return map[r.result] || r.result || r.state;
      };
      const kind = (r) => ({ aprobado: "ok", aprobado_con_advertencias: "warn", fallido: "bad" })[r.result] || "muted";
      historyHost.replaceChildren(
        rows_.length
          ? h(
              "ul",
              { class: "tqt-hist" },
              ...rows_.map((r) =>
                h(
                  "li",
                  { "data-k": kind(r) },
                  h("div", { class: "tqt-hist-top" }, h("span", { class: "tqt-dot", "aria-hidden": "true" }), h("b", null, label(r)), h("span", null, fmtDate(r.created))),
                  h(
                    "p",
                    { class: "hint" },
                    (r.operator || "—") + " · " + (["queued", "running"].includes(r.state) ? "en curso" : fmtDur(r.updated - r.created)) + " · ejecución " + String(r.id).slice(0, 8),
                  ),
                  button("Abrir reporte y LOG", () => openReport(r.id)),
                ),
              ),
            )
          : h("p", { class: "tqt-empty" }, "Esta tarjeta todavía no tiene pruebas guardadas."),
      );
      const running = rows_.find((r) => ["queued", "running"].includes(r.state));
      if (running && !active && !web()) {
        prepareRun(false);
        active.id = running.id;
        active.tarjetaId = tid;
        poll();
      }
    }
    async function openReport(id) {
      const r = await call("/runs/" + id);
      const report = r.report?.source_report || {
          issue:
            "Ejecución interrumpida o sin informe final. El LOG y los eventos disponibles se conservaron.",
          steps: [],
        },
        checks = r.report?.inventory_check || {},
        root = "/api/validacion/tqt/runs/" + id;
      const response = await fetch(root + "/log");
      if (!response.ok) throw Error("No se pudo recuperar el LOG completo.");
      const text = await response.text();
      const log = h("pre", { class: "tqt-log", tabindex: 0 }, text),
        columns = ["Etapa", "Resultado", "Duración", "Detalle"];
      reportHost.replaceChildren(
        h(
          "article",
          { class: "prog-panel tqt-report" },
          h(
            "div",
            { class: "row wrap" },
            h("h2", null, "Reporte · " + (report.card || r.inventory.nombre)),
            button("Imprimir / guardar PDF", () => window.print()),
            button("Cerrar reporte", () => reportHost.replaceChildren()),
          ),
          h(
            "p",
            null,
            new Date(r.created * 1000).toLocaleString() +
              " · " +
              (r.result || r.state) +
              " · " +
              r.operator,
          ),
          h("h3", null, "Identidad e inventario"),
          h(
            "p",
            null,
            "FW " +
              (report.firmware || "—") +
              " · HW " +
              (report.hardware || "—") +
              " · Posición final " +
              (report.ending_position || "—"),
          ),
          h(
            "p",
            { class: "mono" },
            "R1: " +
              (report.reported_mac || "—") +
              " · BLE " +
              (report.r1_ble_address || "—"),
          ),
          h(
            "p",
            { class: "mono" },
            "R2: " +
              (report.reported_mac_r2 || "—") +
              " · BLE " +
              (report.r2_ble_address || "—"),
          ),
          h(
            "dl",
            { class: "tqt-checks" },
            ...Object.entries(checks).flatMap(([k, v]) => [
              h("dt", null, checkLabels[k] || k),
              h("dd", null, v),
            ]),
          ),
          T.banner(
            "info",
            "info",
            "Resultado funcional y liberación son independientes. Esta prueba no autoriza entregar la tarjeta.",
          ),
          h("h3", null, "Comunicación"),
          h(
            "dl",
            { class: "tqt-checks" },
            ...Object.entries({
              frames: "Tramas recibidas",
              retries: "Reintentos ACK",
              partial_warnings: "Advertencias parciales",
              corrupt_frames: "Tramas corruptas",
              ack_errors: "Errores ACK",
            }).flatMap(([key, label]) => [
              h("dt", null, label),
              h(
                "dd",
                { class: "mono" },
                String(report.serial_health?.[key] ?? "—"),
              ),
            ]),
          ),
          h(
            "p",
            null,
            "Calidad: " +
              (report.communication_quality?.state || "no verificada"),
          ),
          h(
            "table",
            { class: "val-cmp" },
            h(
              "thead",
              null,
              h("tr", null, ...columns.map((x) => h("th", null, x))),
            ),
            h(
              "tbody",
              null,
              ...(report.steps || []).map((s) =>
                h(
                  "tr",
                  null,
                  h("td", null, s.name),
                  h("td", null, s.state),
                  h("td", null, (s.duration_s ?? "—") + " s"),
                  h("td", null, s.detail),
                ),
              ),
            ),
          ),
          h("h3", null, "Advertencias y errores"),
          h("p", null, report.issue || "Sin falla informada"),
          h(
            "ul",
            null,
            ...(report.warnings || []).map((x) => h("li", null, x)),
          ),
          h("h3", null, "Parámetros seriales"),
          h(
            "dl",
            { class: "tqt-checks" },
            h("dt", null, "Baudios"),
            h("dd", null, "57600 · 8N1"),
            ...Object.entries({
              ack_delay_ms: "ACK",
              command_quiet_ms: "Guarda de comandos",
              status_quiet_ms: "Espera adicional Status",
            }).flatMap(([key, label]) => [
              h("dt", null, label),
              h("dd", null, String(report.serial_timing?.[key] ?? "—") + " ms"),
            ]),
          ),
          h("a", { class: "btn", href: root + "/json" }, "Descargar JSON"),
          h("h3", null, "LOG original completo"),
          h(
            "div",
            { class: "row wrap" },
            button("Copiar LOG", async () => {
              await navigator.clipboard.writeText(text);
              message("LOG completo copiado.");
            }),
            h("a", { class: "btn", href: root + "/log" }, "Descargar LOG"),
          ),
          log,
        ),
      );
      reportHost.tabIndex = -1;
      reportHost.focus({ preventScroll: true });
      reportHost.firstElementChild.scrollIntoView({ block: "start" });
    }
    async function install() {
      try {
        const response = await fetch("/api/validacion/tqt/installer", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name: "Banco TQT Windows" }),
        });
        if (!response.ok) throw Error("No se pudo descargar el agente.");
        try {
          const m = /filename="?TQT_Pruebas_([^".]+)\.zip/.exec(response.headers.get("Content-Disposition") || "");
          if (m) { saveStation(m[1]); stationId = m[1]; }
        } catch (e) {}
        const url = URL.createObjectURL(await response.blob());
        const a = h("a", { href: url, download: "TQT_Pruebas_Windows.zip" });
        document.body.append(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 5000);
      } catch (e) {
        message(e.message, true);
      }
    }
    fetch("/static/js/test_station_contract.json?v=1400")
      .then((r) => r.json())
      .then((d) => {
        contract = d;
        // Nombres oficiales del contrato; las filas ya existen y solo cambia su texto.
        (d.step_names || []).forEach((n, i) => rows[i] && (rows[i].nm.textContent = i + 1 + ". " + n));
        if (!active) paintSensors({});
      })
      .catch(() => {});
    paintSensors({});
    paintCard("");
    paintSummary();
    updateControls();
    loadList(false);
    if (web()) {
      paintWebEstado();
      try {
        unsubEstado = window.TQTValWeb.onEstado?.(() => alive && paintWebEstado()) || null;
        // v1.4.0: monitor en ruta web: tramas RX y avisos del puerto fuera de la prueba automática.
        unsubMonitor = window.TQTValWeb.onMonitor?.((ev) => {
          if (alive && !active && ev?.text) logLine((ev.kind === "line" ? "RX: " : "") + ev.text);
        }) || null;
      } catch (e) {}
    } else stations().catch(() => {});
    // v1.4.0: cerrar o recargar la pestaña con una prueba web en curso pide confirmación del navegador.
    const antesDeDescargar = (ev) => {
      if (active?.web) {
        ev.preventDefault();
        ev.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", antesDeDescargar);
    const refresh = setInterval(() => {
      if (alive && !active && !manualBusy && !web()) stations().catch(() => {});
    }, 3000);
    const tid = new URLSearchParams(location.hash.split("?")[1] || "").get("tarjeta");
    if (tid) selectCard({ id: Number(tid) || tid }).catch(() => {});
    return {
      escaneo: scan,
      ocupada: () => !!active,
      // v1.4.0: salir de la vista con una prueba web en curso la cancela; se pide confirmación antes.
      confirmarSalida: () =>
        !active?.web ||
        new Promise((resolve) =>
          T.sheet({
            title: "Prueba en curso",
            body: [h("p", null, "Hay una prueba en curso en este navegador. Si sales de Pruebas TQT se cancelará y quedará como no verificada.")],
            actions: [
              { label: "Seguir en la prueba", kind: "ghost", onClick: () => resolve(false) },
              { label: "Salir y cancelar la prueba", kind: "danger", onClick: () => resolve(true) },
            ],
            onClose: () => resolve(false),
          }),
        ),
      actualizar: () => (web() ? paintWebEstado() : stations()),
      desmontar() {
        alive = false;
        clearInterval(refresh);
        clearInterval(tickTimer);
        clearTimeout(pollTimer);
        clearTimeout(searchTimer);
        try { if (typeof unsubEstado === "function") unsubEstado(); } catch (e) {}
        try { if (typeof unsubMonitor === "function") unsubMonitor(); } catch (e) {}
        window.removeEventListener("beforeunload", antesDeDescargar);
        // Una prueba web en curso se cancela al salir de la vista (el motor libera puertos y locks).
        try { webAbort?.abort(); } catch (e) {}
      },
    };
  }
  const def = {
    id: "validacion",
    titulo: "Pruebas TQT",
    icono: "wifi",
    grupo: "operacion",
    orden: 60,
    montar,
  };
  if (window.TQTEscritorio?.registrar) window.TQTEscritorio.registrar(def);
  else (window.__TQTSecciones = window.__TQTSecciones || []).push(def);
})();
