"""Outbound Windows bridge. The original 0.6.3 engine owns serial/BLE timing."""

import argparse, json, sqlite3, threading, time, urllib.request, urllib.parse, ssl
from pathlib import Path
from dataclasses import asdict
from tqtstation.engine import TestStation, NoVerification
from tqtstation.serial_port import SerialLink
from tqtstation.ble import BLELink
from tqtstation.native_ble import execute as execute_native_ble
from tqtstation.protocol import serial_action, normalize_mac


def norm(x):
    return "".join(c for c in str(x or "").upper() if c.isalnum())


class Bridge:
    def __init__(self, cfg, folder):
        self.cfg, self.folder = cfg, folder
        self.folder.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.active = None
        self.sequence = 0
        self.expected = None
        self.latest = {}
        self.ready = ""
        self.devices = []
        self.store = sqlite3.connect(folder / "outbox.db", check_same_thread=False)
        self.store.execute(
            "CREATE TABLE IF NOT EXISTS outbox(id INTEGER PRIMARY KEY,path TEXT NOT NULL,body TEXT NOT NULL)"
        )
        self.store.commit()
        self.serial = SerialLink(self.line, self.info)
        self.ble = BLELink(self.info)
        self.engine = TestStation(self.serial, self.ble, self.event)
        self.original_send = self.serial.send
        self.serial.send = self.safe_send
        self.command_thread = None

    def safe_send(self, data):
        if self.engine.running and data in (
            serial_action("PPON"),
            serial_action("POFF"),
        ):
            d = self.expected
            v = self.latest
            if (
                not d
                or norm(v.get("MAC")) != norm(d["mac_r1"])
                or norm(v.get("MACR")) != norm(d["mac_r2"])
                or norm(self.ready) != norm(d["nombre"])
            ):
                raise NoVerification(
                    "Identidad/MAC no coincide con la tarjeta seleccionada; movimiento bloqueado."
                )
        self.original_send(data)

    def line(self, line):
        self.engine.on_line(line)

    def info(self, text):
        self.engine.log(text)

    def put(self, path, body):
        with self.lock:
            self.store.execute(
                "INSERT INTO outbox(path,body) VALUES(?,?)",
                (path, json.dumps(body, ensure_ascii=False)),
            )
            self.store.commit()

    def event(self, kind, *args):
        with self.lock:
            if kind == "status":
                self.latest = dict(args[0].fields)
                args = (asdict(args[0]),)
            if kind == "card":
                self.ready = args[0]
            if self.active:
                self.sequence += 1
                self.put(
                    "runs/" + self.active + "/events",
                    {
                        "items": [
                            {"seq": self.sequence, "data": {"kind": kind, "args": args}}
                        ]
                    },
                )
                if kind == "done":
                    path = self.engine.report_files.get("log") or self.engine._log_path
                    if path:
                        self.sequence += 1
                        text = Path(path).read_bytes().decode("utf-8")
                        self.put(
                            "runs/" + self.active + "/events",
                            {
                                "items": [
                                    {
                                        "seq": self.sequence,
                                        "data": {"kind": "full_log", "text": text},
                                    }
                                ]
                            },
                        )
                    report = dict(self.engine.report)
                    report["status_final"] = dict(self.latest)
                    self.put("runs/" + self.active + "/result", report)
                    self.active = None

    def api(self, path, body):
        url = self.cfg["server"].rstrip("/") + "/api/stm32/agent/tests/" + path
        request = urllib.request.Request(
            url,
            data=json.dumps(body).encode(),
            headers={
                "Authorization": "Bearer " + self.cfg["token"],
                "Content-Type": "application/json",
                "User-Agent": "TQT-Test-Station/0.6.3-web",
            },
        )
        with urllib.request.urlopen(request, timeout=10) as r:
            return json.load(r)

    def flush(self):
        # Persistent ordered retries never repeat a command or a test run.
        for _ in range(100):
            with self.lock:
                row = self.store.execute(
                    "SELECT id,path,body FROM outbox ORDER BY id LIMIT 1"
                ).fetchone()
            if not row:
                return
            self.api(row[1], json.loads(row[2]))
            with self.lock:
                self.store.execute("DELETE FROM outbox WHERE id=?", (row[0],))
                self.store.commit()

    def execute(self, cmd):
        data = json.loads(cmd["body"])
        action = cmd["action"]
        try:
            if self.engine.running:
                raise RuntimeError("Prueba automática activa; comando bloqueado.")
            if self.cfg.get('ble_only') and action != 'ble_bridge':
                raise ValueError('Este puente solo permite Bluetooth; no abre serial.')
            if action in ("serial", "ble") and data.get("command") in ("PPON", "POFF"):
                d = data.get("inventory") or {}
                if (
                    normalize_mac(self.latest.get("MAC", ""))
                    != normalize_mac(d.get("mac_r1", ""))
                    or normalize_mac(self.latest.get("MACR", ""))
                    != normalize_mac(d.get("mac_r2", ""))
                    or not d
                ):
                    raise NoVerification(
                        "Solicita un Status nuevo y selecciona la tarjeta correcta; identidad/MAC no verificada para mover."
                    )
                if action == "ble" and normalize_mac(self.ble.address) not in (
                    normalize_mac(d["mac_r1"]),
                    normalize_mac(d["mac_r2"]),
                ):
                    raise NoVerification(
                        "BLE conectado a una tarjeta diferente de la seleccionada."
                    )
            if action == 'ble_bridge':
                if self.serial.connected:
                    raise ValueError('El puente BLE no puede poseer el puerto serial.')
                result = execute_native_ble(self.ble, lambda: self.api('ble/' + cmd['id'] + '/authorize', {}))
            elif action == "ports":
                result = self.serial.ports()
            elif action == "connect_serial":
                if data["port"] not in self.serial.ports():
                    raise ValueError("El COM no existe en esta laptop.")
                self.latest = {}
                self.ready = ""
                self.serial.connect(data["port"], 57600)
                result = {"port": data["port"]}
            elif action == "disconnect_serial":
                self.serial.disconnect()
                self.latest = {}
                self.ready = ""
                result = {}
            elif action == "scan_ble":
                self.devices = [asdict(d) for d in self.ble.scan()]
                result = self.devices
            elif action == "connect_ble":
                if data["address"] not in [d["address"] for d in self.devices]:
                    raise ValueError("Selecciona un dispositivo del escaneo actual.")
                self.ble.connect(data["address"])
                result = {"address": self.ble.address}
            elif action == "disconnect_ble":
                self.ble.disconnect()
                result = {}
            elif action == "ble":
                if data["command"] not in ("PPON", "POFF"):
                    raise ValueError("Comando BLE inválido.")
                self.ble.send(data["command"])
                result = {}
            elif action == "serial":
                if data["command"] == "RESET_FACTORY":
                    raise ValueError(
                        "Restablecimiento de fábrica reservado a la secuencia automática confirmada."
                    )
                self.serial.send(serial_action(data["command"]))
                result = {}
            else:
                raise ValueError("Acción desconocida.")
            self.put("commands/" + cmd["id"] + "/result", {"ok": True, "data": result})
        except Exception as e:
            self.put(
                "commands/" + cmd["id"] + "/result", {"ok": False, "error": str(e)}
            )

    def start(self, job):
        if self.engine.running:
            raise RuntimeError("Ya hay una prueba activa.")
        self.expected = job["inventory"]
        self.active = job["id"]
        self.sequence = 0
        self.ready = ""
        self.latest = {}
        self.engine.output_dir = self.folder / "runs" / job["id"]
        # Database rows are supplied by the server; never load a manual CSV.
        self.engine.inventory_records = {
            str(int(self.expected["r1_serie"])): dict(
                id=self.expected["id_tarjeta_num"],
                nombre=self.expected["nombre"],
                mac_r1=self.expected["mac_r1"],
                mac_r2=self.expected["mac_r2"],
            )
        }
        self.engine.inventory_source = "Inventario TQT SQLite; snapshot al iniciar"
        try:
            self.engine.start(self.serial.port_name)
        except Exception as e:
            self.put(
                "runs/" + job["id"] + "/result",
                {"result": "no_verificado", "issue": str(e), "steps": []},
            )
            self.active = None

    def loop(self):
        while True:
            try:
                self.flush()
                state = {
                    "ble_bridge": 1,
                    "ble_only": bool(self.cfg.get('ble_only')),
                    "serial_connected": self.serial.connected,
                    "port": self.serial.port_name,
                    "ble_address": self.ble.address,
                    "running": self.engine.running,
                    "run_id": self.active,
                    "fields": self.latest,
                    "card": self.ready,
                }
                job = self.api("claim", state)
                if job.get("cancel") and self.engine.running:
                    self.engine.stop()
                if job.get("run") and not self.cfg.get('ble_only'):
                    self.start(job["run"])
                if job.get("command"):
                    self.command_thread = threading.Thread(
                        target=self.execute, args=(job["command"],), daemon=True
                    )
                    self.command_thread.start()
            except KeyboardInterrupt:
                if self.engine.running:
                    self.engine.stop()
                    self.engine._run_thread.join(timeout=25)
                self.serial.disconnect()
                self.ble.disconnect()
                try:
                    self.flush()
                except Exception:
                    pass
                return
            except Exception as e:
                print("Reporte/conexión pendiente:", str(e), flush=True)
            time.sleep(0.25 if self.cfg.get('ble_only') else 1)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--config", default="config.json")
    p.add_argument("--background", action="store_true")
    a = p.parse_args()
    path = Path(a.config).resolve()
    cfg = json.loads(path.read_text(encoding="utf-8"))
    if a.background:
        import sys

        sys.stdout = sys.stderr = (path.parent / "agent.log").open(
            "a", encoding="utf-8", buffering=1
        )
    url = urllib.parse.urlsplit(cfg["server"])
    if url.scheme != "https" and not (
        url.scheme == "http" and url.hostname in ("127.0.0.1", "localhost")
    ):
        raise ValueError("Solo HTTPS o HTTP de loopback local.")
    if __import__("os").name == "nt":
        import ctypes

        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.CreateMutexW.restype = ctypes.c_void_p
        k.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
        mutex = k.CreateMutexW(None, False, "Local\\TQTTests_" + cfg["id"])
        if not mutex or ctypes.get_last_error() == 183:
            raise RuntimeError("Esta estación ya está iniciada.")
    Bridge(cfg, path.parent / "evidence").loop()


if __name__ == "__main__":
    main()
