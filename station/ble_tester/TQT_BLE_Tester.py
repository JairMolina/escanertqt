"""TQT BLE Tester: Windows GUI for TQT ESP32 BLE devices.

Scans only BLE peripherals whose advertised name contains TQT (case-insensitive),
displays their advertised name and Bluetooth address, and writes PPON/POFF to
the established TQT R2 GATT service/characteristic.
"""

from __future__ import annotations

import asyncio
import queue
import threading
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, scrolledtext, ttk
from typing import Any

from bleak import BleakClient, BleakScanner

APP_NAME = "TQT BLE Tester"
APP_VERSION = "1.1"
NAME_FILTER = "TQT"  # Match anywhere in the advertised name, case-insensitive.
SERVICE_UUID = "4fafc201-1fb5-459e-8fcc-c5c9c331914b"
CHARACTERISTIC_UUID = "beb5483e-36e1-4688-b7f5-ea07361b26a8"
SCAN_SECONDS = 7.0

# These are exact commands, without a line terminator.
COMMANDS = {"PPON": b"PPON", "POFF": b"POFF"}

BG = "#0b1220"
PANEL = "#141f31"
PANEL_LIGHT = "#1b2a40"
TEXT = "#f1f5f9"
MUTED = "#a5b4c7"
CYAN = "#38bdf8"
GREEN = "#22c55e"
RED = "#fb7185"
AMBER = "#fbbf24"
BORDER = "#334155"


def match_tqt(name: str | None) -> bool:
    return NAME_FILTER in (name or "").upper()


class BLEWorker:
    """Keep WinRT/Bleak on a separate asyncio loop, never blocking Tkinter."""

    def __init__(self, events: queue.Queue[tuple[Any, ...]]) -> None:
        self.events = events
        self.loop = asyncio.new_event_loop()
        self.devices: dict[str, Any] = {}
        self.client: BleakClient | None = None
        self.char: Any | None = None
        self.current_address: str | None = None
        self.thread = threading.Thread(target=self._run, name="tqt-ble", daemon=True)
        self.thread.start()

    def _run(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def emit(self, *event: Any) -> None:
        self.events.put(event)

    def submit(self, coro: Any) -> None:
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)

        def report_unexpected_error(fut: Any) -> None:
            try:
                fut.result()
            except Exception as exc:
                self.emit("error", f"Error interno: {type(exc).__name__}: {exc}")

        future.add_done_callback(report_unexpected_error)

    async def scan(self) -> None:
        if self.client and self.client.is_connected:
            self.emit("error", "Desconecta primero el dispositivo antes de buscar nuevamente.")
            return
        self.emit("log", f"Buscando dispositivos BLE durante {SCAN_SECONDS:.0f} segundos...")
        try:
            results = await BleakScanner.discover(timeout=SCAN_SECONDS, return_adv=True)
            devices: dict[str, Any] = {}
            rows: list[tuple[str, str]] = []
            for device, advertisement in results.values():
                name = (advertisement.local_name or device.name or "").strip()
                if not match_tqt(name):
                    continue
                address = device.address.upper()
                devices[address] = device
                rows.append((name, address))
            self.devices = devices
            rows.sort(key=lambda item: (item[0].upper(), item[1]))
            self.emit("devices", rows)
            self.emit("log", f"Búsqueda terminada: {len(rows)} dispositivo(s) TQT encontrado(s).")
        except Exception as exc:
            self.emit("scan_failed", f"No se pudo buscar BLE: {type(exc).__name__}: {exc}")

    async def connect(self, address: str) -> None:
        device = self.devices.get(address)
        if device is None:
            self.emit("connect_failed", "Dispositivo no encontrado. Ejecuta otra búsqueda.")
            return
        if self.client and self.client.is_connected:
            self.emit("connect_failed", "Ya existe una conexión BLE activa.")
            return

        self.emit("log", f"Conectando con {device.name or address} ({address})...")
        client = BleakClient(device, disconnected_callback=self._on_disconnected, timeout=15.0)
        self.client = client
        self.current_address = address
        try:
            await client.connect()
            # Never guess a writable characteristic; only use the TQT R2 UUIDs.
            service = client.services.get_service(SERVICE_UUID)
            if service is None:
                raise RuntimeError("No existe el servicio BLE esperado de TQT R2.")
            characteristic = next(
                (c for c in service.characteristics if c.uuid.lower() == CHARACTERISTIC_UUID), None
            )
            if characteristic is None:
                raise RuntimeError("No existe la característica BLE esperada de TQT R2.")
            props = {p.lower() for p in characteristic.properties}
            if not ({"write", "write-without-response"} & props):
                raise RuntimeError("La característica TQT no permite escribir comandos.")
            self.char = characteristic
            if "notify" in props or "indicate" in props:
                try:
                    await client.start_notify(characteristic, self._on_notification)
                    self.emit("log", "Notificaciones BLE activadas.")
                except Exception as exc:
                    self.emit("log", f"Aviso: no se activaron notificaciones ({exc}).")
            self.emit("connected", address)
            self.emit("log", "Conectado. Listo para enviar PPON o POFF.")
        except Exception as exc:
            self.emit("connect_failed", f"Conexión fallida: {type(exc).__name__}: {exc}")
            try:
                if client.is_connected:
                    await client.disconnect()
            except Exception:
                pass
            if self.client is client:
                self.client = None
                self.current_address = None
                self.char = None

    def _on_notification(self, _sender: Any, data: bytearray) -> None:
        raw = bytes(data)
        decoded = raw.decode("utf-8", errors="replace").strip()
        self.emit("log", f"RX BLE: {decoded if decoded else raw.hex(' ').upper()}")

    def _on_disconnected(self, client: BleakClient) -> None:
        if client is self.client:
            self.char = None
            self.emit("disconnected", "La conexión BLE terminó.")

    async def disconnect(self) -> None:
        client = self.client
        self.client = None
        self.char = None
        self.current_address = None
        if client is not None:
            try:
                if client.is_connected:
                    await client.disconnect()
            except Exception as exc:
                self.emit("log", f"Aviso al desconectar: {exc}")
        self.emit("disconnected", "Dispositivo desconectado.")

    async def send(self, command: str) -> None:
        if command not in COMMANDS:
            self.emit("error", "Comando no permitido.")
            return
        client = self.client
        characteristic = self.char
        if client is None or not client.is_connected or characteristic is None:
            self.emit("error", "No hay un dispositivo TQT conectado.")
            return
        try:
            properties = {p.lower() for p in characteristic.properties}
            # Prefer acknowledged GATT writes when the peripheral supports them.
            with_response = "write" in properties
            await client.write_gatt_char(characteristic, COMMANDS[command], response=with_response)
            mode = "confirmada por GATT" if with_response else "enviada sin confirmación GATT"
            self.emit("log", f"TX BLE: {command} ({mode}).")
        except Exception as exc:
            self.emit("error", f"No se pudo enviar {command}: {type(exc).__name__}: {exc}")


class TesterApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(f"{APP_NAME}  |  v{APP_VERSION}")
        self.root.geometry("790x670")
        self.root.minsize(680, 560)
        self.root.configure(bg=BG)
        self.events: queue.Queue[tuple[Any, ...]] = queue.Queue()
        self.worker = BLEWorker(self.events)
        self.busy = False
        self.connected = False
        self.selected_address: str | None = None
        self.connected_address: str | None = None
        self.rows: dict[str, str] = {}

        self._create_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(100, self.process_events)
        self.root.after(350, self.scan)

    def _create_ui(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("TQT.Treeview", background=PANEL, fieldbackground=PANEL,
                        foreground=TEXT, rowheight=31, borderwidth=0, font=("Segoe UI", 10))
        style.configure("TQT.Treeview.Heading", background=PANEL_LIGHT, foreground=TEXT,
                        borderwidth=0, padding=(10, 9), font=("Segoe UI", 10, "bold"))
        style.map("TQT.Treeview", background=[("selected", "#164e63")],
                  foreground=[("selected", "#ffffff")])
        style.map("TQT.Treeview.Heading", background=[("active", "#26435d")])

        header = tk.Frame(self.root, bg=BG)
        header.pack(fill="x", padx=24, pady=(20, 12))
        tk.Label(header, text="TQT  /  BLE TESTER", font=("Segoe UI", 21, "bold"),
                 fg=TEXT, bg=BG).pack(anchor="w")
        tk.Label(header, text="Escáner y control de comandos para TQT R2",
                 font=("Segoe UI", 10), fg=MUTED, bg=BG).pack(anchor="w", pady=(2, 0))

        top = tk.Frame(self.root, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        top.pack(fill="x", padx=24, pady=(0, 12))
        content = tk.Frame(top, bg=PANEL)
        content.pack(fill="x", padx=14, pady=13)
        self.status_label = tk.Label(content, text="●  SIN CONEXIÓN", font=("Segoe UI", 10, "bold"),
                                     fg=AMBER, bg=PANEL)
        self.status_label.pack(side="left")
        self.scan_button = tk.Button(content, text="⟳  BUSCAR TQT", command=self.scan,
                                     bg="#075985", fg="white", activebackground="#0369a1",
                                     activeforeground="white", relief="flat", cursor="hand2",
                                     font=("Segoe UI", 10, "bold"), padx=16, pady=9)
        self.scan_button.pack(side="right")

        list_panel = tk.Frame(self.root, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        list_panel.pack(fill="both", expand=True, padx=24, pady=(0, 12))
        tk.Label(list_panel, text="DISPOSITIVOS DISPONIBLES", font=("Segoe UI", 10, "bold"),
                 fg=TEXT, bg=PANEL).pack(anchor="w", padx=15, pady=(13, 10))
        table_area = tk.Frame(list_panel, bg=PANEL)
        table_area.pack(fill="both", expand=True, padx=12, pady=(0, 10))
        self.tree = ttk.Treeview(table_area, columns=("name", "mac"), show="headings",
                                 selectmode="browse", style="TQT.Treeview", height=5)
        self.tree.heading("name", text="NOMBRE BLE")
        self.tree.heading("mac", text="DIRECCIÓN / MAC BLE")
        self.tree.column("name", minwidth=220, width=345, anchor="w")
        self.tree.column("mac", minwidth=195, width=280, anchor="w")
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(table_area, orient="vertical", command=self.tree.yview)
        scrollbar.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.bind("<<TreeviewSelect>>", self.on_selection)
        self.tree.bind("<Double-1>", lambda _evt: self.connect())

        connect_bar = tk.Frame(list_panel, bg=PANEL)
        connect_bar.pack(fill="x", padx=12, pady=(0, 12))
        self.counter = tk.Label(connect_bar, text="0 dispositivos TQT", bg=PANEL, fg=MUTED,
                                font=("Segoe UI", 9))
        self.counter.pack(side="left", padx=4)
        self.disconnect_button = tk.Button(connect_bar, text="DESCONECTAR", command=self.disconnect,
                                           bg=PANEL_LIGHT, fg=TEXT, relief="flat", cursor="hand2",
                                           font=("Segoe UI", 9, "bold"), padx=14, pady=8)
        self.disconnect_button.pack(side="right")
        self.connect_button = tk.Button(connect_bar, text="CONECTAR", command=self.connect,
                                        bg="#0e7490", fg="white", relief="flat", cursor="hand2",
                                        font=("Segoe UI", 9, "bold"), padx=20, pady=8)
        self.connect_button.pack(side="right", padx=(0, 8))
        self.copy_mac_button = tk.Button(
            connect_bar, text="COPIAR MAC", command=self.copy_selected_mac,
            bg="#334155", fg=TEXT, activebackground="#475569",
            activeforeground="white", relief="flat", cursor="hand2",
            font=("Segoe UI", 9, "bold"), padx=12, pady=8,
        )
        self.copy_mac_button.pack(side="right", padx=(0, 8))

        cmd_panel = tk.Frame(self.root, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        cmd_panel.pack(fill="x", padx=24, pady=(0, 12))
        tk.Label(cmd_panel, text="COMANDOS FIJOS", font=("Segoe UI", 10, "bold"),
                 fg=TEXT, bg=PANEL).pack(anchor="w", padx=15, pady=(12, 10))
        command_row = tk.Frame(cmd_panel, bg=PANEL)
        command_row.pack(fill="x", padx=15, pady=(0, 14))
        self.on_button = tk.Button(command_row, text="PPON", command=lambda: self.send("PPON"),
                                   bg="#166534", activebackground="#15803d", fg="white",
                                   activeforeground="white", relief="flat", font=("Segoe UI", 12, "bold"),
                                   cursor="hand2", pady=12)
        self.on_button.pack(side="left", fill="x", expand=True, padx=(0, 7))
        self.off_button = tk.Button(command_row, text="POFF", command=lambda: self.send("POFF"),
                                    bg="#9f1239", activebackground="#be123c", fg="white",
                                    activeforeground="white", relief="flat", font=("Segoe UI", 12, "bold"),
                                    cursor="hand2", pady=12)
        self.off_button.pack(side="left", fill="x", expand=True, padx=(7, 0))

        log_panel = tk.Frame(self.root, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        log_panel.pack(fill="both", expand=True, padx=24, pady=(0, 15))
        log_head = tk.Frame(log_panel, bg=PANEL)
        log_head.pack(fill="x", padx=15, pady=(10, 6))
        tk.Label(log_head, text="REGISTRO DE PRUEBAS", font=("Segoe UI", 10, "bold"),
                 fg=TEXT, bg=PANEL).pack(side="left")
        tk.Button(log_head, text="Limpiar", command=self.clear_log,
                  bg=PANEL_LIGHT, fg=MUTED, relief="flat", cursor="hand2",
                  padx=12, pady=3).pack(side="right")
        self.log_box = scrolledtext.ScrolledText(log_panel, height=7, state="disabled",
                                                wrap="word", bg="#101928", fg="#a7f3d0",
                                                insertbackground="white", relief="flat",
                                                font=("Consolas", 9), padx=10, pady=10)
        self.log_box.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.log("Iniciando TQT BLE Tester...")
        self.log("Filtro de nombre: contiene TQT (sin distinguir mayúsculas/minúsculas).")
        self.update_controls()

    def log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_box.configure(state="normal")
        self.log_box.insert("end", f"[{timestamp}] {message}\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def clear_log(self) -> None:
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

    def status(self, text: str, color: str) -> None:
        self.status_label.configure(text=f"●  {text}", fg=color)

    def update_controls(self) -> None:
        self.scan_button.config(state="disabled" if self.busy or self.connected else "normal")
        self.connect_button.config(state="normal" if self.selected_address and not self.busy and not self.connected else "disabled")
        # The MAC can be copied even when already connected: no BLE I/O is required.
        self.copy_mac_button.config(state="normal" if self.selected_address else "disabled")
        self.disconnect_button.config(state="normal" if self.connected and not self.busy else "disabled")
        self.on_button.config(state="normal" if self.connected and not self.busy else "disabled")
        self.off_button.config(state="normal" if self.connected and not self.busy else "disabled")

    def scan(self) -> None:
        if self.busy or self.connected:
            return
        self.busy = True
        self.status("BUSCANDO BLE...", CYAN)
        self.selected_address = None
        self.rows.clear()
        for child in self.tree.get_children():
            self.tree.delete(child)
        self.counter.configure(text="Buscando...")
        self.update_controls()
        self.worker.submit(self.worker.scan())

    def on_selection(self, _event: Any) -> None:
        selected = self.tree.selection()
        self.selected_address = self.rows.get(selected[0]) if selected else None
        self.copy_mac_button.config(text="COPIAR MAC")
        self.update_controls()

    def copy_selected_mac(self) -> None:
        """Copy only the selected table row's MAC, without requiring BLE connection."""
        selected = self.tree.selection()
        address = self.rows.get(selected[0]) if selected else None
        if not address:
            return
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(address)
            # Make clipboard content available after the window closes.
            self.root.update_idletasks()
        except tk.TclError as exc:
            self.log(f"No se pudo copiar la MAC: {exc}")
            return
        self.log(f"MAC copiada al portapapeles: {address}")
        self.copy_mac_button.config(text="✓ COPIADA")
        self.root.after(1400, self.restore_copy_label)

    def restore_copy_label(self) -> None:
        self.copy_mac_button.config(text="COPIAR MAC")

    def connect(self) -> None:
        if self.busy or self.connected or not self.selected_address:
            return
        self.busy = True
        self.status("CONECTANDO...", CYAN)
        self.update_controls()
        self.worker.submit(self.worker.connect(self.selected_address))

    def disconnect(self) -> None:
        if not self.connected or self.busy:
            return
        self.busy = True
        self.status("DESCONECTANDO...", AMBER)
        self.update_controls()
        self.worker.submit(self.worker.disconnect())

    def send(self, command: str) -> None:
        if self.connected and not self.busy:
            self.worker.submit(self.worker.send(command))

    def process_events(self) -> None:
        try:
            while True:
                event, *data = self.events.get_nowait()
                if event == "log":
                    self.log(data[0])
                elif event == "devices":
                    rows = data[0]
                    for name, address in rows:
                        item_id = self.tree.insert("", "end", values=(name, address))
                        self.rows[item_id] = address
                    self.counter.configure(text=f"{len(rows)} dispositivo(s) TQT")
                    self.busy = False
                    self.status("LISTO PARA CONECTAR" if rows else "SIN DISPOSITIVOS TQT", GREEN if rows else AMBER)
                elif event == "scan_failed":
                    self.busy = False
                    self.counter.configure(text="Error durante la búsqueda")
                    self.status("ERROR DE BÚSQUEDA", RED)
                    self.log(data[0])
                elif event == "connected":
                    self.connected = True
                    self.connected_address = data[0]
                    self.busy = False
                    self.status(f"CONECTADO  |  {data[0]}", GREEN)
                elif event == "connect_failed":
                    self.connected = False
                    self.connected_address = None
                    self.busy = False
                    self.status("CONEXIÓN FALLIDA", RED)
                    self.log(data[0])
                elif event == "disconnected":
                    # An unexpected drop or a requested disconnect.
                    if self.connected or self.busy:
                        self.log(data[0])
                    self.connected = False
                    self.connected_address = None
                    self.busy = False
                    self.status("SIN CONEXIÓN", AMBER)
                elif event == "error":
                    self.log(f"ERROR: {data[0]}")
                self.update_controls()
        except queue.Empty:
            pass
        self.root.after(100, self.process_events)

    def close(self) -> None:
        # The BLE loop runs as a daemon; request a graceful disconnect.
        try:
            self.worker.submit(self.worker.disconnect())
        except Exception:
            pass
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    TesterApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
