"""WebSockets en tiempo real (handshake, PING/PONG, broadcast de cada evento) y CRUD directo sobre SQLite.

Toda espera de mensaje usa `recibir_ws` con timeout: un evento que nunca llega hace FALLAR el test en segundos en vez de
colgar la suite (antes un ws.receive_text() sin timeout bloqueaba para siempre).
"""
import _aislamiento  # noqa: F401  (debe ser lo primero)
import json
import unittest

from fastapi.testclient import TestClient

from app.database import db, inventario as inv
from app.main import app
from app.routers.ws import manager

from _aislamiento import crear_par, mac_unica, nuevo_lote, num_unico, recibir_ws, verificar_aislamiento


class TestWebSocket(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        verificar_aislamiento()
        db.init_db()
        cls.client = TestClient(app)
        cls.lote_id = nuevo_lote()["id"]

    def ws(self):
        ws = self.client.websocket_connect("/ws?client_type=monitor")
        conn = ws.__enter__()
        self.addCleanup(lambda: ws.__exit__(None, None, None))
        self.assertEqual(recibir_ws(conn)["evento"], "CONEXION_ESTABLECIDA")
        return conn

    def test_01_handshake_y_estado_inicial(self):
        with self.client.websocket_connect("/ws?client_type=operador") as ws:
            msg = json.loads(ws.receive_text())
            self.assertEqual(msg["evento"], "CONEXION_ESTABLECIDA")
            for k in ("lote_activo", "stats", "total_clientes"):
                self.assertIn(k, msg["data"])
            self.assertGreaterEqual(manager.count(), 1)
        self.assertEqual(manager.count(), 0)

    def test_02_ping_pong_y_stats(self):
        ws = self.ws()
        ws.send_text(json.dumps({"action": "PING"}))
        self.assertEqual(recibir_ws(ws)["evento"], "PONG")
        ws.send_text("PING")
        self.assertEqual(recibir_ws(ws)["evento"], "PONG")
        ws.send_text(json.dumps({"action": "GET_STATS"}))
        self.assertEqual(recibir_ws(ws)["evento"], "ESTADISTICAS_ACTUALIZADAS")
        ws.send_text(json.dumps({"action": "OTRA"}))
        self.assertEqual(recibir_ws(ws)["data"]["recibido"], "OTRA")

    def test_03_pcb_recibida_al_escanear(self):
        ws = self.ws()
        s = num_unico()
        r = self.client.post("/api/pcb/escanear", json={"codigo": f"TQT-R3-V30-{s}", "operador": "ana"})
        self.assertEqual(r.json()["resultado"], "AGREGADA")
        msg = recibir_ws(ws, evento="PCB_RECIBIDA")
        self.assertEqual(msg["data"]["pcb"]["nombre"], f"TQT-R3-V30-{s}")
        self.assertEqual(msg["data"]["operador"], "ana")
        self.assertIn("R3", msg["data"]["conteos"])

    def test_04_una_duplicada_no_emite_pcb_recibida(self):
        s = num_unico()
        self.client.post("/api/pcb/escanear", json={"codigo": f"TQT-R1-V30-{s}"})
        ws = self.ws()
        self.client.post("/api/pcb/escanear", json={"codigo": f"TQT-R1-V30-{s}"})       # DUPLICADA: sin evento
        self.client.post("/api/pcb/escanear", json={"codigo": f"TQT-R2-V30-{s}"})       # AGREGADA: la primera que llega
        msg = recibir_ws(ws)
        self.assertEqual((msg["evento"], msg["data"]["pcb"]["tipo"]), ("PCB_RECIBIDA", "R2"))

    def test_05_recepcion_confirmada(self):
        s = num_unico()
        pid = self.client.post("/api/pcb/escanear", json={"codigo": f"TQT-R1-V30-{s}"}).json()["pcb"]["id"]
        ws = self.ws()
        self.client.post("/api/recepcion/confirmar", json={"ids": [pid]})
        msg = recibir_ws(ws, evento="RECEPCION_CONFIRMADA")
        self.assertEqual(msg["data"]["confirmadas"], 1)
        self.assertIn("disponibles", msg["data"])

    def test_06_edicion_mac_y_eliminacion(self):
        s = num_unico()
        pid = self.client.post("/api/pcb/escanear", json={"codigo": f"TQT-R1-V30-{s}"}).json()["pcb"]["id"]
        ws = self.ws()
        self.client.patch(f"/api/pcb/{pid}", json={"version": "31"})
        self.assertEqual(recibir_ws(ws, evento="PCB_ACTUALIZADA")["data"]["pcb"]["version"], "31")
        self.client.put(f"/api/pcb/{pid}/mac", json={"mac": mac_unica()})
        self.assertIsNotNone(recibir_ws(ws, evento="PCB_ACTUALIZADA")["data"]["pcb"]["mac"])
        self.client.delete(f"/api/pcb/{pid}")
        self.assertEqual(recibir_ws(ws, evento="PCB_ELIMINADA")["data"]["id"], pid)

    def test_07_emparejado_reemplazo_y_disolucion(self):
        s = num_unico()
        ids = {t: self.client.post("/api/pcb/escanear", json={"codigo": f"TQT-{t}-V30-{s}"}).json()["pcb"]["id"] for t in ("R1", "R2")}
        self.client.post("/api/recepcion/confirmar", json={"ids": list(ids.values())})
        ws = self.ws()
        r = self.client.post("/api/emparejar/auto", json={"lote_id": self.lote_id, "series": [s]})
        msg = recibir_ws(ws, evento="TARJETA_EMPAREJADA")
        self.assertEqual(msg["data"]["tarjeta"]["id_tarjeta_num"], s)
        self.assertIn("stats", msg["data"])
        tid = r.json()["creadas"][0]["id"]
        self.client.put(f"/api/tarjetas/{tid}/asignar", json={"ranura": "R2", "pcb_id": None})
        act = recibir_ws(ws, evento="TARJETA_ACTUALIZADA")
        self.assertFalse(act["data"]["tarjeta"]["completa"])
        self.client.delete(f"/api/tarjetas/{tid}")
        self.assertTrue(recibir_ws(ws, evento="TARJETA_ACTUALIZADA")["data"]["eliminada"])

    def test_09_lote_cambiado(self):
        ws = self.ws()
        self.client.post(f"/api/lotes/{self.lote_id}/activar")
        self.assertEqual(recibir_ws(ws, evento="LOTE_CAMBIADO")["data"]["lote_activo"]["id"], self.lote_id)

    def test_10_un_evento_que_no_llega_falla_rapido_en_vez_de_colgar(self):
        ws = self.ws()
        import time
        t0 = time.monotonic()
        with self.assertRaises(AssertionError):
            recibir_ws(ws, timeout=0.5, evento="NO_EXISTE")
        self.assertLess(time.monotonic() - t0, 3)


class TestSQLiteDirecto(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        verificar_aislamiento()
        db.init_db()

    def test_11_crud_directo(self):
        lote = nuevo_lote()["id"]
        t = crear_par(lote, num="0555")
        self.assertEqual(db.get_tarjeta_by_id(t["id"])["id_tarjeta_num"], "0555")
        self.assertEqual((t["estado_general"], t["completa"]), ("PENDIENTE", True))
        stats = db.get_stats(lote)
        self.assertEqual((stats["total_tarjetas"], stats["pendientes"], stats["funcionales"]), (1, 1, 0))  # recién armada: NO aprobada

    def test_12_lote_inexistente_es_error_controlado(self):
        client = TestClient(app)
        self.assertEqual(client.post("/api/emparejar/auto", json={"lote_id": 987654}).status_code, 404)
        self.assertEqual(client.get("/api/emparejar/sugerencias?lote_id=987654").status_code, 404)
        self.assertEqual(client.post("/api/tarjetas", json={"lote_id": 987654, "r1_id": 1}).status_code, 404)

    def test_13_bitacora_registra_altas(self):
        s = num_unico()
        inv.escanear_pcb(f"TQT-R1-V30-{s}", operador="marta")
        with db.get_db() as conn:
            fila = conn.execute("SELECT * FROM escaneos WHERE evento='PCB_ALTA' AND valor=?", (f"TQT-R1-V30-{s}",)).fetchone()
        self.assertEqual((fila["operador"], fila["detalle"]), ("marta", "QR"))


if __name__ == "__main__":
    unittest.main()
