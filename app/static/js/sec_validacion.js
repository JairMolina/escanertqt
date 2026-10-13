/* Pruebas TQT: original serial/BLE engine in Windows; inventory and reports in Docker. */
(function () {
  "use strict";
  function montar(host, ctx) {
    const { h, api, T } = ctx;
    let alive = true,
      card = null,
      active = null,
      lastSeq = 0,
      events = [],
      pollTimer = null,
      stationId = "",
      manualBusy = false,
      contract = { fields: [], help: {}, errors: {} };
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
    const status = h("div", { role: "status", "aria-live": "polite" }),
      sel = h("select", {
        class: "input",
        "aria-label": "Estación de pruebas",
      }),
      port = h("select", { class: "input", "aria-label": "Puerto COM" });
    const search = h("input", {
      class: "input",
      placeholder: "Tarjeta, nombre de R1 o QR",
      "aria-label": "Buscar tarjeta para pruebas",
    });
    const cardHost = h("div"),
      sensors = h("div", { class: "tqt-sensors" }),
      steps = h("ol", { class: "tqt-steps" }),
      historyHost = h("div"),
      reportHost = h("div");
    const bleSelect = h("select", {
        class: "input",
        "aria-label": "Dispositivo Bluetooth",
      }),
      manual = h("div", { class: "row wrap" });
    const progress = h("progress", {
      max: 14,
      value: 0,
      "aria-label": "Etapas de la prueba automática",
    });
    const start = h(
      "button",
      { class: "btn btn-primary", type: "button", onclick: begin },
      "Iniciar las 14 etapas",
    );
    const stop = h(
      "button",
      {
        class: "btn",
        type: "button",
        disabled: true,
        onclick: async () => {
          await call("/runs/" + active.id + "/cancel", {});
          message(
            "Cancelación solicitada. El movimiento actual puede terminar.",
          );
        },
      },
      "Detener prueba",
    );
    const confirm = h("input", {
      type: "checkbox",
      "aria-label": "Confirmar tarjeta conectada y banco libre",
    });
    const commandSelect = h(
      "select",
      { class: "input", "aria-label": "Comando serial adicional" },
      ...[
        "STATUS",
        "MOTOR_STATUS",
        "RESET_BLE",
        "MAP_QUERY",
        "MAP_M1_0",
        "MAP_M1_1",
        "MAP_M2_0",
        "MAP_M2_1",
      ].map((x) => h("option", { value: x }, x)),
    );
    host.append(
      h("h2", null, "Pruebas TQT"),
      h(
        "p",
        { class: "hint" },
        "Motor TQT Test Station 0.6.3 · Windows maneja COM y Bluetooth; el inventario conserva cada ejecución.",
      ),
      status,
      h(
        "div",
        { class: "prog-wrap" },
        h(
          "section",
          { class: "prog-panel" },
          h("h3", null, "Tarjeta e inventario"),
          search,
          h(
            "button",
            { class: "btn", onclick: () => scan(search.value) },
            "Buscar / cargar QR",
          ),
          cardHost,
          h("h3", null, "Estación Windows"),
          sel,
          h(
            "button",
            { class: "btn", onclick: install },
            "Descargar agente de pruebas",
          ),
          h(
            "p",
            { class: "hint" },
            "Extrae el paquete privado y ejecuta iniciar.cmd una vez. Cierra el programa de escritorio si usa el mismo puerto.",
          ),
          h("h3", null, "Conexión serial · 57600 baudios · ACK 180 ms"),
          port,
          h(
            "div",
            { class: "row wrap" },
            button("Detectar COM", () => cmd("ports")),
            button("Conectar COM", () =>
              cmd("connect_serial", { port: port.value }),
            ),
            button("Desconectar COM", () => cmd("disconnect_serial")),
          ),
          h("h3", null, "Bluetooth R1 / R2"),
          bleSelect,
          h(
            "div",
            { class: "row wrap" },
            button("Buscar TQT", () => cmd("scan_ble")),
            button("Conectar BLE", () =>
              cmd("connect_ble", { address: bleSelect.value }),
            ),
            button("Desconectar BLE", () => cmd("disconnect_ble")),
          ),
          manual,
        ),
        h(
          "section",
          { class: "prog-panel" },
          h("h3", null, "Prueba automática"),
          h(
            "label",
            null,
            confirm,
            " Confirmo la tarjeta conectada y el banco libre. La secuencia restablece ajustes y mueve el perno.",
          ),
          h("div", { class: "row wrap" }, start, stop),
          progress,
          steps,
          h("h3", null, "Sensores y estados S29"),
          sensors,
        ),
      ),
      h(
        "section",
        { class: "prog-panel" },
        h("h3", null, "Historial de esta tarjeta"),
        historyHost,
      ),
      reportHost,
    );
    manual.append(
      button("ON serial", () => cmd("serial", { command: "PPON" })),
      button("OFF serial", () => cmd("serial", { command: "POFF" })),
      button("Reset normal", () => cmd("serial", { command: "RESET" })),
      commandSelect,
      button("Enviar comando", () =>
        cmd("serial", { command: commandSelect.value }),
      ),
      button("ON BLE", () => cmd("ble", { command: "PPON" })),
      button("OFF BLE", () => cmd("ble", { command: "POFF" })),
    );
    function button(text, fn) {
      return h("button", { class: "btn", type: "button", onclick: fn }, text);
    }
    function message(text, bad = false) {
      status.replaceChildren(
        T.banner(bad ? "bad" : "info", bad ? "alert" : "info", text),
      );
    }
    async function call(path, body) {
      const r = await api(
        "/api/validacion/tqt" + path,
        body !== undefined ? { method: "POST", body } : undefined,
      );
      if (!r.ok) {
        message(r.error, true);
        throw Error(r.error);
      }
      return r.data;
    }
    async function scan(code) {
      if (active || manualBusy) return { ok: false, texto: "Prueba en curso." };
      const r = await api("/api/consulta?codigo=" + encodeURIComponent(code));
      if (!r.ok) {
        message(r.error, true);
        return { ok: false, texto: r.error };
      }
      const t = r.data.tarjeta || r.data.serie?.tarjeta;
      if (!t) {
        message(
          "No hay una tarjeta emparejada para este código. Regístrala o empareja sus PCB desde Inventario; no se inventan identificadores.",
          true,
        );
        return { ok: false };
      }
      try {
        card = await call("/inventory/" + t.id);
        cardHost.replaceChildren(
          h("h4", null, "Tarjeta " + card.id_tarjeta_num),
          h("p", { class: "mono" }, card.nombre),
          h("p", { class: "mono" }, "R1 " + card.mac_r1),
          h("p", { class: "mono" }, card.r2_nombre + " · " + card.mac_r2),
        );
        confirm.checked = false;
        await history();
      } catch (e) {
        card = null;
      }
      return { ok: !!card };
    }
    async function stations() {
      const list = await call("/stations");
      sel.replaceChildren(
        h("option", { value: "" }, "Selecciona la laptop"),
        ...list.map((s) =>
          h(
            "option",
            { value: s.id },
            s.name + (s.online ? " · conectada" : " · desconectada"),
          ),
        ),
      );
      if (list.some((s) => s.id === stationId)) sel.value = stationId;
      else if (list.filter((s) => s.online).length === 1)
        sel.value = list.find((s) => s.online).id;
      stationId = sel.value;
      const s = list.find((s) => s.id === stationId);
      if (s?.fields) paintSensors(s.fields);
      start.disabled = !!active || !s?.online || !s.serial_connected || !card;
    }
    sel.addEventListener("change", () => {
      stationId = sel.value;
    });
    function paintSensors(fields) {
      sensors.replaceChildren(
        ...(contract.fields.length ? contract.fields : Object.keys(fields)).map(
          (key) =>
            h(
              "div",
              { class: "tqt-sensor", title: contract.help[key] || key },
              h("dt", null, key),
              h("dd", { class: "mono" }, fields[key] ?? "—"),
              key === "err"
                ? h(
                    "small",
                    null,
                    contract.errors[fields[key]] || "Sin lectura",
                  )
                : null,
            ),
        ),
      );
    }
    async function cmd(action, body = {}) {
      if (active || manualBusy) return;
      manualBusy = true;
      host.querySelectorAll("button").forEach((b) => (b.disabled = true));
      try {
        const j = await call("/commands", {
          station_id: sel.value,
          tarjeta_id: card?.id,
          action,
          ...body,
        });
        let result;
        for (let i = 0; i < 90 && alive; i++) {
          const r = await call("/commands/" + j.id);
          if (["done", "error"].includes(r.state)) {
            result = r.result;
            break;
          }
          await new Promise((resolve) => setTimeout(resolve, 1000));
        }
        if (!result?.ok)
          throw Error(
            result?.error ||
              "Comando sin resultado; no se repite automáticamente.",
          );
        if (action === "ports")
          port.replaceChildren(
            ...result.data.map((x) => h("option", { value: x }, x)),
          );
        if (action === "scan_ble")
          bleSelect.replaceChildren(
            ...result.data.map((x) =>
              h("option", { value: x.address }, x.name + " · " + x.address),
            ),
          );
        message("Acción completada: " + action);
      } catch (e) {
        message(e.message, true);
      } finally {
        manualBusy = false;
        host.querySelectorAll("button").forEach((b) => (b.disabled = false));
        stop.disabled = !active;
        await stations();
      }
    }
    async function begin() {
      if (!card || !confirm.checked) {
        message(
          "Selecciona la tarjeta y confirma la conexión física y el banco libre.",
          true,
        );
        return;
      }
      try {
        active = await call("/runs", {
          station_id: sel.value,
          tarjeta_id: card.id,
          physical_confirmed: true,
        });
        confirm.checked = false;
        confirm.disabled = true;
        sel
          .closest("section")
          .querySelectorAll("button,input,select")
          .forEach((b) => (b.disabled = true));
        lastSeq = 0;
        events = [];
        progress.value = 0;
        steps.replaceChildren();
        manual
          .querySelectorAll("button,select")
          .forEach((b) => (b.disabled = true));
        sel.disabled = search.disabled = true;
        start.disabled = true;
        stop.disabled = false;
        message(
          "Prueba iniciada. No cambies la tarjeta ni envíes comandos desde otro programa.",
        );
        poll();
      } catch (e) {}
    }
    async function poll() {
      if (!alive || !active) return;
      try {
        const batch = await call(
          "/runs/" + active.id + "/events?after=" + lastSeq,
        );
        for (const e of batch) {
          lastSeq = e.seq;
          events.push(e);
          if (e.data.kind === "status") paintSensors(e.data.args[0].fields);
          if (e.data.kind === "step") {
            const [idx, state, detail] = e.data.args;
            let row = steps.children[idx];
            if (!row) {
              while (steps.children.length <= idx)
                steps.append(h("li", null, "Pendiente"));
              row = steps.children[idx];
            }
            row.textContent =
              (contract.step_names?.[idx] || "Etapa " + (idx + 1)) +
              " · " +
              state +
              " · " +
              detail;
            progress.value = [...steps.children].filter((x) =>
              x.textContent.includes("aprobado"),
            ).length;
          }
        }
        const r = await call("/runs/" + active.id);
        if (!["queued", "running"].includes(r.state)) {
          const id = active.id;
          active = null;
          confirm.disabled = false;
          sel
            .closest("section")
            .querySelectorAll("button,input,select")
            .forEach((b) => (b.disabled = false));
          sel.disabled = search.disabled = false;
          manual
            .querySelectorAll("button,select")
            .forEach((b) => (b.disabled = false));
          stop.disabled = true;
          await stations();
          await history();
          await openReport(id);
          return;
        }
      } catch (e) {
        message(
          "Conexión pendiente. No repitas la prueba; se conserva la evidencia recibida.",
          true,
        );
      }
      pollTimer = setTimeout(poll, 1000);
    }
    async function history() {
      if (!card) return;
      const rows = await call("/runs?tarjeta_id=" + card.id);
      historyHost.replaceChildren(
        rows.length
          ? h(
              "table",
              { class: "val-cmp" },
              h(
                "thead",
                null,
                h(
                  "tr",
                  null,
                  ...["Fecha", "Resultado", "Operador", "Reporte"].map((x) =>
                    h("th", null, x),
                  ),
                ),
              ),
              h(
                "tbody",
                null,
                ...rows.map((r) =>
                  h(
                    "tr",
                    null,
                    h("td", null, new Date(r.created * 1000).toLocaleString()),
                    h("td", null, r.result || r.state),
                    h("td", null, r.operator),
                    h(
                      "td",
                      null,
                      button("Abrir reporte", () => openReport(r.id)),
                    ),
                  ),
                ),
              ),
            )
          : h("p", null, "Esta tarjeta todavía no tiene pruebas guardadas."),
      );
      const running = rows.find((r) => ["queued", "running"].includes(r.state));
      if (running && !active) {
        active = running;
        lastSeq = 0;
        events = [];
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
    fetch("/static/js/test_station_contract.json?v=tqt063-final")
      .then((r) => r.json())
      .then((d) => {
        contract = d;
        paintSensors({});
      })
      .catch(() => {});
    stations().catch(() => {});
    const refresh = setInterval(() => {
      if (alive && !active && !manualBusy) stations().catch(() => {});
    }, 3000);
    const tid = new URLSearchParams(location.hash.split("?")[1] || "").get(
      "tarjeta",
    );
    if (tid)
      call("/inventory/" + tid)
        .then(async (d) => {
          card = d;
          cardHost.replaceChildren(
            h("h4", null, "Tarjeta " + d.id_tarjeta_num),
            h("p", null, d.nombre),
          );
          await history();
        })
        .catch(() => {});
    return {
      escaneo: scan,
      ocupada: () => !!active,
      actualizar: () => stations(),
      desmontar() {
        alive = false;
        clearInterval(refresh);
        clearTimeout(pollTimer);
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
