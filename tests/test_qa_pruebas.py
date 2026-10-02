"""QA de Pruebas/Monitor: estados, derivación, masivo, búsqueda con comodines, lotes, WebSocket."""
import _aislamiento  # noqa: F401  (debe ser lo primero)
import asyncio
import itertools
import threading
import time
import unittest

from fastapi.testclient import TestClient

from app.database import db
from app.database.models import derivar_estado_general, normalizar_estado_prueba, normalizar_etapa
from app.main import app

from _aislamiento import crear_par, nuevo_lote, recibir_ws, verificar_aislamiento

ETAPAS = ["soldadura", "programacion", "prueba_pcb", "integracion", "prueba_final"]
ESTADOS = ["PENDIENTE", "OK", "FALLA", "RETRABAJO", "NO APLICA"]


class TestDerivacion(unittest.TestCase):
    def test_todas_las_combinaciones(self):
        for combo in itertools.product(ESTADOS, repeat=5):
            g = derivar_estado_general(combo)
            if "FALLA" in combo:
                esperado = "DETENIDO"
            elif "RETRABAJO" in combo:
                esperado = "RETRABAJO"
            elif all(e in ("OK", "NO APLICA") for e in combo):
                esperado = "LIBERADO"
            elif all(e == "PENDIENTE" for e in combo):
                esperado = "PENDIENTE"
            else:
                esperado = "EN PROCESO"
            self.assertEqual(g, esperado, combo)

    def test_alias_y_variantes(self):
        for v in ("NO APLICA", "no aplica", "No_Aplica", "no-aplica", "  no   aplica ", "N/A"):
            self.assertEqual(normalizar_estado_prueba(v), "NO APLICA", v)
        self.assertEqual(normalizar_etapa("Prueba PCB"), "prueba_pcb")
        self.assertEqual(normalizar_etapa("prueba-pcb"), "prueba_pcb")
        self.assertEqual(normalizar_etapa("Programación"), "programacion")
        for malo in ("XX", "OKK"):
            with self.assertRaises(ValueError):
                normalizar_estado_prueba(malo)
        with self.assertRaises(ValueError):
            normalizar_etapa("pintura")


class TestApiQA(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        verificar_aislamiento()
        db.init_db()
        cls.client = TestClient(app)
        cls.lote_id = nuevo_lote()["id"]

    def _put(self, tid, etapa, estado):
        return self.client.put(f"/api/tarjetas/{tid}/pruebas", json={"etapa": etapa, "estado": estado})

    def test_busqueda_comodines_literales(self):
        lote = nuevo_lote(activar=False)["id"]
        t = crear_par(lote)
        for q in ("%", "_", "'", "\\", "!", "%%", "a' OR '1'='1", "x_y"):
            r = self.client.get("/api/tarjetas", params={"lote_id": lote, "search": q})
            self.assertEqual(r.status_code, 200, q)
            self.assertEqual(r.json()["total"], 0, f"'{q}' se comportó como comodín")
        self.assertEqual(self.client.get("/api/tarjetas", params={"lote_id": lote, "search": t["id_tarjeta_num"]}).json()["total"], 1)
        self.assertEqual(self.client.get("/api/tarjetas", params={"lote_id": lote, "search": t["mac_r1"].lower()}).json()["total"], 1)
        self.assertEqual(self.client.get("/api/tarjetas", params={"lote_id": lote, "search": t["nombre_r2"].lower()}).json()["total"], 1)

    def test_by_mac(self):
        t = crear_par(self.lote_id)
        mac = t["mac_r1"]
        for forma in (mac, mac.lower(), mac.replace(":", "-"), mac.replace(":", "")):
            self.assertEqual(self.client.get(f"/api/tarjetas/by-mac/{forma}").json()["id"], t["id"], forma)
        self.assertEqual(self.client.get("/api/tarjetas/by-mac/ZZ").status_code, 404)

    def test_lotes(self):
        for mal in ({"codigo_lote": "L", "mes": 0, "anio": 2026}, {"codigo_lote": "L", "mes": 13, "anio": 2026},
                    {"codigo_lote": "L", "mes": 5, "anio": 1999}, {"codigo_lote": "", "mes": 5, "anio": 2026}):
            self.assertEqual(self.client.post("/api/lotes", json={**mal, "crear_excel": False}).status_code, 422, mal)
        cod = f"QA-{time.time_ns()}"
        r = self.client.post("/api/lotes", json={"codigo_lote": cod, "mes": 5, "anio": 2031, "crear_excel": False, "activo": False})
        self.assertEqual(r.status_code, 201, r.text)
        lid = r.json()["id"]
        self.assertEqual(self.client.post("/api/lotes", json={"codigo_lote": cod, "mes": 5, "anio": 2031, "crear_excel": False}).status_code, 409)
        self.assertEqual(self.client.post("/api/lotes/999999/activar").status_code, 404)
        self.assertNotEqual(self.client.get("/api/status").json()["active_lote"]["id"], lid)
        self.assertEqual(self.client.post(f"/api/lotes/{lid}/activar").status_code, 200)
        self.assertEqual(self.client.get("/api/status").json()["active_lote"]["id"], lid)
        self.assertEqual(sum(1 for x in self.client.get("/api/lotes").json() if x["activo"]), 1)
        self.assertEqual(self.client.get("/api/tarjetas").json()["total"], 0)  # tarjetas de otros lotes no se ven
        self.client.post(f"/api/lotes/{self.lote_id}/activar")


class TestWebSocketQA(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        verificar_aislamiento()
        db.init_db()
        cls.client = TestClient(app)
        cls.lote_id = nuevo_lote()["id"]

    def test_ping_pong_y_mensajes_hostiles(self):
        with self.client.websocket_connect("/ws") as ws:
            self.assertEqual(recibir_ws(ws)["evento"], "CONEXION_ESTABLECIDA")
            ws.send_text('{"action":"ping"}')
            self.assertEqual(recibir_ws(ws)["evento"], "PONG")
            for raro in ("[1,2]", "123", "null", '{"action":null}', '"x"', "basura{"):
                ws.send_text(raro)
            ws.send_text("PING")
            eventos = [recibir_ws(ws)["evento"] for _ in range(6)]  # sigue viva tras entradas raras
            self.assertEqual(eventos[-1], "PONG")
            ws.send_text('{"action":"BROADCAST_SCAN","data":{"x":1}}')
            self.assertEqual(recibir_ws(ws)["evento"], "ACK")

    def test_cliente_lento_no_bloquea(self):
        from app.routers import ws as wsmod

        class Lento:
            async def send_text(self, _):
                await asyncio.sleep(30)

        class Rapido:
            def __init__(self):
                self.recibidos = []

            async def send_text(self, m):
                self.recibidos.append(m)

        m = wsmod.ConnectionManager()
        rapido = Rapido()
        m.active_connections = [Lento(), rapido]
        viejo = wsmod.SEND_TIMEOUT
        wsmod.SEND_TIMEOUT = 0.3
        try:
            t0 = time.monotonic()
            asyncio.run(m.broadcast("X", {"a": 1}))
            self.assertLess(time.monotonic() - t0, 2)
        finally:
            wsmod.SEND_TIMEOUT = viejo
        self.assertEqual(len(rapido.recibidos), 1)
        self.assertEqual(m.count(), 1)  # el lento se descarta


if __name__ == "__main__":
    unittest.main()
