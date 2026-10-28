"""v1.4.56: el agente reusa su conexión HTTPS (keep-alive) para no abrir TLS en cada claim; errores 4xx y 410 intactos."""
import json, sys, threading, unittest, urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import agent


class Servidor(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    puertos = []
    cerrar = False   # cierra la conexión tras responder sin avisar (como un servidor con keep-alive vencido)

    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        Servidor.puertos.append(self.client_address[1])
        code = {"claim": 200, "malo": 400, "revocado": 410}[self.path.rsplit("/", 1)[1]]
        out = json.dumps({"ok": True}).encode()
        self.send_response(code); self.send_header("Content-Length", str(len(out))); self.end_headers(); self.wfile.write(out)
        self.close_connection = Servidor.cerrar

    def log_message(self, *a):
        pass


class AgenteHttp(unittest.TestCase):
    def setUp(self):
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), Servidor)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.b = object.__new__(agent.Bridge)
        self.b.cfg = {"server": "http://127.0.0.1:%d" % self.srv.server_port, "token": "t"}
        self.b._http = threading.local()
        Servidor.puertos, Servidor.cerrar = [], False

    def tearDown(self):
        self.srv.shutdown(); self.srv.server_close()

    def test_reusa_la_conexion(self):
        for _ in range(5):
            self.assertEqual(self.b.api("claim", {}), {"ok": True})
        self.assertEqual(len(set(Servidor.puertos)), 1)

    def test_reconecta_si_el_servidor_cerro(self):
        Servidor.cerrar = True
        self.b.api("claim", {})
        Servidor.cerrar = False
        self.assertEqual(self.b.api("claim", {}), {"ok": True})
        self.assertEqual(len(set(Servidor.puertos)), 2)

    def test_errores_http(self):
        with self.assertRaises(urllib.error.HTTPError) as e:
            self.b.api("malo", {})
        self.assertEqual(e.exception.code, 400)
        e.exception.close()
        with self.assertRaises(agent.StationRevokedError):
            self.b.api("revocado", {})


class Autoactualizacion(unittest.TestCase):
    """v1.4.64: el paquete del servidor se extrae sin tocar config/.venv/puerto/log; un intento por versión."""

    def paquete(self, req="bleak\n"):
        import io, zipfile
        s = io.BytesIO()
        with zipfile.ZipFile(s, "w") as z:
            z.writestr("agent.py", "nuevo"); z.writestr("requirements.txt", req)
            z.writestr("tqtstation/x.py", "x"); z.writestr("config.json", "MALO"); z.writestr(".venv/a", "MALO")
        return s.getvalue()

    def test_instala_sin_tocar_lo_propio(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            (base / "config.json").write_text("CFG"); (base / "requirements.txt").write_bytes(b"bleak\n")
            self.assertFalse(agent.instalar_paquete(base, self.paquete()))
            self.assertEqual((base / "config.json").read_text(), "CFG")
            self.assertEqual((base / "agent.py").read_text(), "nuevo")
            self.assertFalse((base / ".venv").exists())
            self.assertTrue(agent.instalar_paquete(base, self.paquete("bleak\npyserial\n")))

    def test_cola_de_eventos_viaja_en_lotes(self):
        """v1.4.73: eventos seguidos de la misma prueba van en un solo POST; otro destino corta el lote y sigue el orden."""
        import sqlite3
        from unittest import mock
        b = object.__new__(agent.Bridge)
        b.lock = threading.RLock()
        b.store = sqlite3.connect(":memory:", check_same_thread=False)
        b.store.execute("CREATE TABLE outbox(id INTEGER PRIMARY KEY,path TEXT NOT NULL,body TEXT NOT NULL)")
        for i in range(1, 4):
            b.store.execute("INSERT INTO outbox(path,body) VALUES(?,?)", ("runs/r1/events", json.dumps({"items": [{"seq": i, "data": {}}]})))
        b.store.execute("INSERT INTO outbox(path,body) VALUES(?,?)", ("runs/r1/finish", json.dumps({"x": 1})))
        b.store.execute("INSERT INTO outbox(path,body) VALUES(?,?)", ("runs/r1/events", json.dumps({"items": [{"seq": 4, "data": {}}]})))
        b.api = mock.Mock(return_value={"ok": True})
        b.flush()
        envios = [(c.args[0], c.args[1]) for c in b.api.call_args_list]
        self.assertEqual([p for p, _ in envios], ["runs/r1/events", "runs/r1/finish", "runs/r1/events"])
        self.assertEqual([x["seq"] for x in envios[0][1]["items"]], [1, 2, 3])
        self.assertEqual(b.store.execute("SELECT COUNT(*) FROM outbox").fetchone()[0], 0)

    def test_linux_decide_actualizar_y_relanza(self):
        """v1.4.64: la Raspberry (Linux) también se autoactualiza; espera a que no haya prueba/comando/BLE."""
        from unittest import mock
        b = object.__new__(agent.Bridge)
        b.update_tried, b.command_thread = set(), None
        b.engine = mock.Mock(running=True); b.ble = mock.Mock(address="")
        b.download = mock.Mock(return_value=b"zip")
        b.relanzar_linux = mock.Mock(side_effect=RuntimeError("pip falló"))
        with mock.patch.object(agent, "plataforma_actualizable", return_value="linux"), \
                mock.patch.object(agent, "instalar_paquete", return_value=True) as inst:
            self.assertFalse(b.maybe_update("9.9.9"))   # prueba en curso: no actualiza todavía
            b.download.assert_not_called()
            b.engine.running = False
            self.assertFalse(b.maybe_update("9.9.9"))   # relanzar falló: sigue con la versión actual
            self.assertFalse(b.maybe_update("9.9.9"))   # un intento por versión y arranque
        inst.assert_called_once()
        b.relanzar_linux.assert_called_once()
        self.assertTrue(b.relanzar_linux.call_args[0][1])   # requirements cambió → pip

    def test_un_intento_y_nunca_en_otro_posix(self):
        from unittest import mock
        b = object.__new__(agent.Bridge)
        b.update_tried, b.command_thread = set(), None
        b.engine = mock.Mock(running=False); b.ble = mock.Mock(address="")
        b.download = mock.Mock(side_effect=OSError("sin red"))
        with mock.patch.object(agent.os, "name", "posix"), mock.patch.object(agent.sys, "platform", "darwin"):
            self.assertIsNone(agent.plataforma_actualizable())
        with mock.patch.object(agent.sys, "platform", "linux"), mock.patch.object(agent.os, "name", "posix"):
            self.assertEqual(agent.plataforma_actualizable(), "linux")
        with mock.patch.object(agent, "plataforma_actualizable", return_value=None):
            self.assertFalse(b.maybe_update("9.9.9"))
        b.download.assert_not_called()
        with mock.patch.object(agent.os, "name", "nt"):
            self.assertFalse(b.maybe_update(agent.AGENT_VERSION))
            self.assertFalse(b.maybe_update("9.9.9"))   # falla y queda registrado
            self.assertFalse(b.maybe_update("9.9.9"))   # no reintenta en bucle
        self.assertEqual(b.download.call_count, 1)


if __name__ == "__main__":
    unittest.main()
