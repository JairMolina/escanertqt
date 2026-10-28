"""Outbound Windows bridge. The original 0.6.3 engine owns serial/BLE timing."""

import argparse, hashlib, http.client, io, json, os, platform, socket, sqlite3, subprocess, sys, threading, time, urllib.request, urllib.parse, ssl, zipfile
import urllib.error
from pathlib import Path
from dataclasses import asdict
from tqtstation.engine import TestStation, NoVerification
from tqtstation.serial_port import SerialLink
from tqtstation.ble import BLELink
from tqtstation.native_ble import execute as execute_native_ble
from tqtstation.protocol import serial_action, normalize_mac


AGENT_VERSION = "1.4.67"   # se muestra en /pruebas-automaticas; si el servidor anuncia otra, Windows se autoactualiza
LOG_MAX = 256 * 1024                      # cola de agent.log que se sube cuando la web la pide
# v1.4.64: la autoactualización nunca sobrescribe lo propio de esta instalación.
PROTEGIDOS = {"config.json", "puerto_serie.txt", "agent.log", "outbox.db", ".agent.lock"}
CARPETAS_PROTEGIDAS = {".venv", "evidence", "__pycache__"}
CANDADO = None   # v1.4.64: candado fcntl del agente Linux (se suelta al autoactualizarse)


def plataforma_actualizable():
    """v1.4.64: «nt» (Windows), «linux» (Raspberry) o None (otra: no se autoactualiza)."""
    if os.name == "nt":
        return "nt"
    return "linux" if sys.platform.startswith("linux") else None


def instalar_paquete(base, raw):
    """Extrae el ZIP del servidor sobre base sin tocar config.json/.venv/puerto_serie.txt/agent.log.
    Devuelve True si requirements.txt cambió."""
    base = Path(base).resolve()
    req = base / "requirements.txt"
    antes = hashlib.sha256(req.read_bytes()).hexdigest() if req.exists() else ""
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        nombres = [i for i in z.infolist() if not i.is_dir()]
        if "agent.py" not in {i.filename for i in nombres}:
            raise ValueError("paquete sin agent.py")
        for info in nombres:
            rel = Path(info.filename)
            destino = (base / rel).resolve()
            if base not in destino.parents:
                raise ValueError("ruta inválida en el paquete: " + info.filename)
            if rel.name in PROTEGIDOS or CARPETAS_PROTEGIDAS & set(rel.parts):
                continue
            destino.parent.mkdir(parents=True, exist_ok=True)
            tmp = destino.with_name(destino.name + ".nuevo")
            tmp.write_bytes(z.read(info))
            os.replace(tmp, destino)
    despues = hashlib.sha256(req.read_bytes()).hexdigest() if req.exists() else ""
    return antes != despues


def serial_ports():
    """Puertos con nombre estable: en Linux, /dev/serial/by-id/... apunta al ttyUSB/ttyACM real (no cambia al reconectar)."""
    from serial.tools.list_ports import comports
    by_id = {}
    base = Path("/dev/serial/by-id")
    if base.is_dir():
        for link in base.iterdir():
            by_id[os.path.realpath(link)] = str(link)
    return [
        {"device": p.device, "by_id": by_id.get(os.path.realpath(p.device), ""),
         "description": p.description if p.description and p.description != "n/a" else "", "hwid": p.hwid or ""}
        for p in sorted(comports(), key=lambda x: x.device)
    ]


def norm(x):
    return "".join(c for c in str(x or "").upper() if c.isalnum())


class StationRevokedError(RuntimeError):
    pass


class Bridge:
    def __init__(self, cfg, folder):
        self.cfg, self.folder = cfg, folder
        self.folder.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self._http = threading.local()   # v1.4.56: una conexión HTTPS keep-alive por hilo
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
        self.port_file = self.folder.parent / "puerto_serie.txt"
        remembered = self.port_file.read_text(encoding="utf-8").strip() if self.port_file.exists() else ""
        self.auto_port = remembered or cfg.get("serial_port") or ""
        self.ports_cache, self.ports_at = [], 0
        self.config_path = self.folder.parent / "config.json"
        self.update_tried = set()   # v1.4.64: una sola autoactualización por versión y arranque

    def download(self, path):
        url = self.cfg["server"].rstrip("/") + "/api/stm32/agent/tests/" + path
        rq = urllib.request.Request(url, headers={"Authorization": "Bearer " + self.cfg["token"],
                                                  "User-Agent": "TQT-Test-Station/" + AGENT_VERSION})
        with urllib.request.urlopen(rq, timeout=60) as r:
            return r.read()

    def maybe_update(self, version):
        """v1.4.64: Windows y Linux (Raspberry). Si el servidor trae otra versión: paquete nuevo, pip si cambió
        requirements, relanza con la misma config y termina. Un intento por versión; los fallos quedan en agent.log."""
        plataforma = plataforma_actualizable()
        linux = plataforma == "linux"
        if not plataforma or not version or version == AGENT_VERSION or version in self.update_tried:
            return False
        if self.engine.running or self.ble.address or (self.command_thread and self.command_thread.is_alive()):
            return False   # se espera a que termine la prueba/comando o se suelte el Bluetooth
        self.update_tried.add(version)
        base = Path(__file__).resolve().parent
        print(time.strftime("%Y-%m-%d %H:%M:%S"), "Autoactualización", AGENT_VERSION, "->", version, flush=True)
        try:
            cambio_req = instalar_paquete(base, self.download("package"))
            exe = Path(sys.executable)
            if linux:
                self.relanzar_linux(base, cambio_req)   # no vuelve si sale bien
            if cambio_req:
                py = exe.with_name("python.exe") if exe.with_name("python.exe").exists() else exe
                r = subprocess.run([str(py), "-m", "pip", "install", "--disable-pip-version-check", "-q", "-r",
                                    str(base / "requirements.txt")], capture_output=True, text=True, timeout=900,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                if r.returncode != 0:
                    raise RuntimeError("pip falló: " + (r.stderr or r.stdout)[-400:])
            pyw = exe.with_name("pythonw.exe") if exe.with_name("pythonw.exe").exists() else exe
            flags = (getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                     | getattr(subprocess, "CREATE_NO_WINDOW", 0))
            subprocess.Popen([str(pyw), "-u", str(base / "agent.py"), "--config", str(self.config_path), "--background"],
                             cwd=str(base), creationflags=flags, close_fds=True)
        except Exception as e:
            print(time.strftime("%Y-%m-%d %H:%M:%S"), "Autoactualización fallida (se sigue con", AGENT_VERSION + "):",
                  str(e), flush=True)
            return False
        print(time.strftime("%Y-%m-%d %H:%M:%S"), "Autoactualización instalada; relanzando el agente.", flush=True)
        self.serial.disconnect()
        os._exit(0)

    def relanzar_linux(self, base, cambio_req):
        """v1.4.64 (Raspberry): pip con la misma venv si cambió requirements; suelta puerto, Bluetooth y el candado
        fcntl y relanza con setsid (sesión nueva, sobrevive a este proceso). El nuevo espera el candado (main())."""
        global CANDADO
        if cambio_req:
            r = subprocess.run([sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "-q", "-r",
                                str(base / "requirements.txt")], capture_output=True, text=True, timeout=900)
            if r.returncode != 0:
                raise RuntimeError("pip falló: " + (r.stderr or r.stdout)[-400:])
        self.serial.disconnect()
        if CANDADO is not None:
            import fcntl
            fcntl.flock(CANDADO, fcntl.LOCK_UN)
        try:
            subprocess.Popen([sys.executable, "-u", str(base / "agent.py"), "--config", str(self.config_path), "--background"],
                             cwd=str(base), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             close_fds=True, start_new_session=True)
        except Exception:
            if CANDADO is not None:   # no se pudo relanzar: este proceso sigue siendo el agente
                import fcntl
                fcntl.flock(CANDADO, fcntl.LOCK_EX | fcntl.LOCK_NB)
            raise
        print(time.strftime("%Y-%m-%d %H:%M:%S"), "Autoactualización instalada; relanzando el agente.", flush=True)
        os._exit(0)

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
        # v1.4.56: antes cada petición abría TLS nuevo (el puente BLE, 4 por segundo) con 10 s de espera; un handshake
        # atascado bastaba para que un comando BLE venciera sin atenderse. Ahora se reusa la conexión y el claim espera 5 s.
        url = self.cfg["server"].rstrip("/") + "/api/stm32/agent/tests/" + path
        u = urllib.parse.urlsplit(url)
        data = json.dumps(body).encode()
        headers = {
            "Authorization": "Bearer " + self.cfg["token"],
            "Content-Type": "application/json",
            "User-Agent": "TQT-Test-Station/0.6.3-web",
        }
        timeout = 5 if path == "claim" else 15
        for intento in (0, 1):
            conn = getattr(self._http, "conn", None)
            reusada = conn is not None
            if conn is None:
                cls = http.client.HTTPSConnection if u.scheme == "https" else http.client.HTTPConnection
                conn = self._http.conn = cls(u.netloc, timeout=timeout)
            conn.timeout = timeout
            if conn.sock is not None:
                conn.sock.settimeout(timeout)
            try:
                conn.request("POST", u.path, body=data, headers=headers)
                r = conn.getresponse()
                raw = r.read()
            except (http.client.RemoteDisconnected, ConnectionError) as e:
                conn.close(); self._http.conn = None
                if reusada and intento == 0:
                    continue   # el servidor cerró la conexión inactiva: se reintenta una vez con una nueva
                raise urllib.error.URLError(e) from e
            except Exception:
                conn.close(); self._http.conn = None
                raise
            if r.status >= 400:
                if r.status == 410:
                    raise StationRevokedError('Agente eliminado desde la web; se detiene sin borrar su historial.')
                raise urllib.error.HTTPError(url, r.status, r.reason, r.headers, io.BytesIO(raw))
            return json.loads(raw or b"null")

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
                reales = {os.path.realpath(x) for x in self.serial.ports()}
                if data["port"] not in self.serial.ports() and os.path.realpath(data["port"]) not in reales:
                    raise ValueError("El puerto serie no existe en este equipo.")
                self.latest = {}
                self.ready = ""
                self.serial.connect(data["port"], 57600)
                self.auto_port = data["port"]   # se recuerda: tras reinicio o desconexión del USB vuelve a este puerto
                self.port_file.write_text(data["port"], encoding="utf-8")
                result = {"port": data["port"]}
            elif action == "disconnect_serial":
                self.auto_port = ""   # desconexión manual: no reconectar solo
                self.port_file.unlink(missing_ok=True)
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

    def serial_alive(self):
        """Conectado DE VERDAD: al desconectar el USB el hilo RX se detiene pero pyserial sigue diciendo is_open."""
        return self.serial.connected and self.serial._running.is_set()

    def auto_serial(self):
        """v1.4.51 (banco fijo, p. ej. Raspberry): con `serial_port` en config.json se conecta solo y reintenta cada 10 s."""
        if self.serial.connected and not self.serial_alive() and not self.engine.running:
            print("Puerto serie perdido (USB desconectado); se cierra para reconectar.", flush=True)
            self.serial.disconnect()
            self.latest = {}
            self.ready = ""
        port = self.auto_port
        if not port or self.cfg.get("ble_only") or self.serial.connected or self.engine.running:
            return
        if self.command_thread and self.command_thread.is_alive():
            return
        if time.time() - getattr(self, "_auto_try", 0) < 10:
            return
        self._auto_try = time.time()
        try:
            self.latest = {}
            self.ready = ""
            self.serial.connect(port, 57600)
            print("Puerto serie conectado:", port, flush=True)
        except Exception as e:
            msg = port + ": " + str(e)
            if msg != getattr(self, "_auto_err", ""):   # sin repetir el mismo aviso cada 10 s en agent.log
                print("Puerto serie no disponible:", msg, flush=True)
            self._auto_err = msg

    def ports(self):
        if time.time() - self.ports_at > 10:
            try:
                self.ports_cache = serial_ports()
            except Exception as e:
                print("No se pudieron listar los puertos:", str(e), flush=True)
            self.ports_at = time.time()
        return self.ports_cache

    def upload_log(self):
        path = self.folder.parent / "agent.log"
        text = ""
        if path.exists():
            with path.open("rb") as f:
                f.seek(max(0, path.stat().st_size - LOG_MAX))
                text = f.read().decode("utf-8", "replace")
        self.api("agent-log", {"texto": text or "(agent.log vacío)"})

    def loop(self):
        while True:
            try:
                self.flush()
                self.auto_serial()
                state = {
                    "ble_bridge": 1,
                    "ble_only": bool(self.cfg.get('ble_only')),
                    "serial_connected": self.serial_alive(),
                    "port": self.serial.port_name,
                    "ble_address": self.ble.address,
                    "running": self.engine.running,
                    "run_id": self.active,
                    "fields": self.latest,
                    "card": self.ready,
                    "agent_version": AGENT_VERSION,
                    "platform": platform.system() + " " + platform.machine(),
                    "host": socket.gethostname(),
                    "auto_port": self.auto_port,
                    "ports": self.ports(),
                }
                job = self.api("claim", state)
                self.maybe_update(job.get("agent_version"))
                if job.get("subir_log"):
                    self.upload_log()
                if job.get("cancel") and self.engine.running:
                    self.engine.stop()
                if job.get("run") and not self.cfg.get('ble_only'):
                    self.start(job["run"])
                if job.get("command"):
                    self.command_thread = threading.Thread(
                        target=self.execute, args=(job["command"],), daemon=True
                    )
                    self.command_thread.start()
            except StationRevokedError as e:
                print(str(e), flush=True)
                self.serial.disconnect()
                self.ble.disconnect()
                return
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
    if __import__("os").name != "nt":   # v1.4.51: Linux/Raspberry; un solo agente por estación (candado de archivo)
        import fcntl

        global CANDADO
        CANDADO = (path.parent / ".agent.lock").open("w")
        # v1.4.64: tras autoactualizarse, el proceso viejo suelta el candado al relanzar; se espera hasta 20 s.
        for _ in range(20):
            try:
                fcntl.flock(CANDADO, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                time.sleep(1)
        else:
            raise RuntimeError("Esta estación ya está iniciada.")
    if __import__("os").name == "nt":
        import ctypes

        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.CreateMutexW.restype = ctypes.c_void_p
        k.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
        # v1.4.64: tras autoactualizarse, el proceso viejo suelta el mutex en un instante; se espera hasta 20 s.
        for _ in range(20):
            mutex = k.CreateMutexW(None, False, "Local\\TQTTests_" + cfg["id"])
            if mutex and ctypes.get_last_error() != 183:
                break
            if mutex:
                k.CloseHandle(ctypes.c_void_p(mutex))
            time.sleep(1)
        else:
            raise RuntimeError("Esta estación ya está iniciada.")
    print(time.strftime("%Y-%m-%d %H:%M:%S"), "Agente", AGENT_VERSION, "iniciado en", socket.gethostname(),
          "(" + platform.system() + " " + platform.machine() + ")", "->", cfg["server"], flush=True)
    bridge = Bridge(cfg, path.parent / "evidence")
    bridge.config_path = path
    bridge.loop()


if __name__ == "__main__":
    main()
