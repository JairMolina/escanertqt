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


if __name__ == "__main__":
    unittest.main()
