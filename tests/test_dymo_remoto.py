"""v1.4.2: DYMO compartida (agente en Raspberry): cola, contrato del agente e impresión como máximo una vez."""
import _aislamiento as iso  # noqa: F401  (debe ser lo primero)
import time
import unittest
import xml.etree.ElementTree as ET

from app.database import db
from app.main import app
from app.services import dymo_remoto as svc, usuarios
from app.services.dymo_service import DymoService

from _aislamiento import cliente_sin_sesion, verificar_aislamiento

OP = "developer@skyguardian.mx"


class TestDymoRemoto(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        verificar_aislamiento()
        db.init_db()
        usuarios.sembrar(iteraciones=1000)
        svc.init()

    def setUp(self):
        with db.get_db() as c:
            c.execute("DELETE FROM dymo_trabajos"); c.execute("DELETE FROM dymo_agentes")
        self.ag = svc.agente_crear("Raspberry prueba")
        self.op = cliente_sin_sesion(app)
        self.op.cookies.set(usuarios.COOKIE, usuarios.emitir_sesion(OP))
        self.pi = cliente_sin_sesion(app)   # sin sesión: solo el token Bearer
        self.H = {"Authorization": "Bearer " + self.ag["token"]}

    def latido(self, ok=True):
        r = self.pi.post("/api/dymo/remoto/agente/latido", json={"version": "1", "cola": "TQT_DYMO", "impresora_ok": ok}, headers=self.H)
        self.assertEqual(r.status_code, 200)

    def test_agente_exige_token_y_no_sesion(self):
        self.assertEqual(self.pi.post("/api/dymo/remoto/agente/latido", json={}).status_code, 401)
        self.assertEqual(self.pi.get("/api/dymo/remoto/agente/siguiente?espera=0", headers={"Authorization": "Bearer x"}).status_code, 401)
        self.assertEqual(self.pi.get("/api/dymo/remoto/estado").status_code, 401)   # la web sí exige sesión

    def test_sin_latido_no_se_encola(self):
        r = self.op.post("/api/dymo/remoto/trabajos", json={"tipo": "cable", "numero": "0021"})
        self.assertEqual(r.status_code, 400)
        self.latido(ok=False)   # en línea pero sin impresora lista
        self.assertFalse(self.op.get("/api/dymo/remoto/estado").json()["disponible"])
        self.assertEqual(self.op.post("/api/dymo/remoto/trabajos", json={"tipo": "cable", "numero": "0021"}).status_code, 400)

    def test_flujo_completo_y_una_sola_vez(self):
        self.latido()
        t = iso.crear_par(iso.nuevo_lote()["id"])
        j = self.op.post("/api/dymo/remoto/trabajos", json={"tipo": "tarjeta", "tarjeta_id": t["id"], "copias": 2}).json()
        self.assertEqual(j["estado"], "pendiente")
        s = self.pi.get("/api/dymo/remoto/agente/siguiente?espera=0", headers=self.H).json()
        self.assertEqual((s["id"], s["copias"], s["ancho_mm"], s["alto_mm"]), (j["id"], 2, 57.0, 32.0))
        svg = self.pi.get(s["svg_url"], headers=self.H)
        self.assertEqual(svg.status_code, 200); ET.fromstring(svg.text.encode())
        self.assertNotIn('stroke-width="0.2"', svg.text)   # sin contorno de vista previa
        self.assertNotIn("guia", svg.text)
        # reinicio del agente: recibe el MISMO trabajo (no uno nuevo) para reportarlo sin reimprimir
        self.assertEqual(self.pi.get("/api/dymo/remoto/agente/siguiente?espera=0", headers=self.H).json()["id"], j["id"])
        r = self.pi.post(f"/api/dymo/remoto/agente/trabajos/{j['id']}/resultado", json={"estado": "impresa", "cups_id": "TQT_DYMO-7"}, headers=self.H)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.op.get(f"/api/dymo/remoto/trabajos/{j['id']}").json()["estado"], "impresa")
        self.assertEqual(self.pi.get("/api/dymo/remoto/agente/siguiente?espera=0", headers=self.H).status_code, 204)
        # resultado repetido: idempotente, no cambia el estado final
        self.pi.post(f"/api/dymo/remoto/agente/trabajos/{j['id']}/resultado", json={"estado": "error"}, headers=self.H)
        self.assertEqual(svc.trabajo(j["id"])["estado"], "impresa")

    def test_otro_agente_no_toca_trabajo_ajeno(self):
        self.latido()
        j = svc.encolar("cable", {"numero": "0021"}, 1, "Cable 0021", OP)
        self.pi.get("/api/dymo/remoto/agente/siguiente?espera=0", headers=self.H)
        otro = {"Authorization": "Bearer " + svc.agente_crear("Otra")["token"]}
        self.assertEqual(self.pi.get(f"/api/dymo/remoto/agente/trabajos/{j['id']}/svg", headers=otro).status_code, 400)
        self.assertEqual(self.pi.post(f"/api/dymo/remoto/agente/trabajos/{j['id']}/resultado", json={"estado": "impresa"}, headers=otro).status_code, 400)

    def test_vencimientos(self):
        self.latido()
        a = svc.encolar("cable", {"numero": "0001"}, 1, "Cable 0001", OP)
        b = svc.encolar("cable", {"numero": "0002"}, 1, "Cable 0002", OP)
        svc.tomar(self.ag["id"])   # toma a
        viejo = time.time() - svc.PENDIENTE_TTL - 5
        with db.get_db() as c:
            c.execute("UPDATE dymo_trabajos SET creado=?, actualizado=?", (viejo, viejo))
        self.assertEqual(svc.trabajo(a["id"])["estado"], "desconocido")   # tomado sin resultado: nunca se reimprime
        self.assertEqual(svc.trabajo(b["id"])["estado"], "cancelada")     # nadie lo tomó: no sale tarde
        self.assertIsNone(svc.tomar(self.ag["id"]))
        # un resultado real tardío sí corrige «desconocido»
        svc.resultado(self.ag["id"], a["id"], "impresa", "", "")
        self.assertEqual(svc.trabajo(a["id"])["estado"], "impresa")

    def test_cancelar_solo_pendiente(self):
        self.latido()
        j = svc.encolar("cable", {"numero": "0021"}, 1, "Cable 0021", OP)
        self.assertEqual(self.op.post(f"/api/dymo/remoto/trabajos/{j['id']}/cancelar").json()["estado"], "cancelada")
        self.assertEqual(self.op.post(f"/api/dymo/remoto/trabajos/{j['id']}/cancelar").status_code, 400)

    def test_validaciones_y_aprobada(self):
        self.latido()
        p = lambda b: self.op.post("/api/dymo/remoto/trabajos", json=b).status_code
        self.assertEqual(p({"tipo": "cable", "numero": "ab"}), 422)
        self.assertEqual(p({"tipo": "r3", "nombres": ["malo"]}), 422)
        self.assertEqual(p({"tipo": "tarjeta", "tarjeta_id": 999999}), 404)
        self.assertEqual(p({"tipo": "cable", "numero": "1", "copias": 21}), 422)
        t = iso.crear_par(iso.nuevo_lote()["id"])
        self.assertEqual(p({"tipo": "aprobada", "tarjeta_id": t["id"]}), 403)   # sin prueba TQT aprobada
        self.assertEqual(p({"tipo": "r3", "nombres": ["TQT-R3-V30-0084", "TQT-R3-V30-0085"]}), 200)

    def test_resultado_tolerante_no_atora_al_agente(self):
        """v1.4.9: un resultado con null, texto largo o estado raro ya no da 422 (el agente lo reintentaba para siempre)."""
        self.latido()
        for body in ({"estado": "error", "detalle": None, "cups_id": None}, {"estado": "fallo", "detalle": "x" * 900}):
            j = svc.encolar("cable", {"numero": "0031"}, 1, "Cable 0031", OP)
            self.assertEqual(svc.tomar(self.ag["id"])["id"], j["id"])
            r = self.pi.post(f"/api/dymo/remoto/agente/trabajos/{j['id']}/resultado", json=body, headers=self.H)
            self.assertEqual(r.status_code, 200, body)
            t = svc.trabajo(j["id"])
            self.assertEqual(t["estado"], "error")
            self.assertLessEqual(len(t["detalle"] or ""), 500)

    def test_aprobada_sale_aunque_empiece_otra_prueba(self):
        """v1.4.9: «Aprobada» se valida al encolar; una prueba nueva de la misma tarjeta (sin resultado) no bloquea el SVG."""
        from app.services import test_station
        self.latido()
        t = iso.crear_par(iso.nuevo_lote()["id"])
        test_station.init()
        ahora = time.time()
        with db.get_db() as c:
            sid = test_station.web_station(c, OP)
            c.execute("INSERT INTO tqt_test_runs(id,station,requested_card,tarjeta_id,operator,state,created,updated,inventory,result,origin)"
                      " VALUES(?,?,?,?,?,'finished',?,?,'{}','aprobado','web')", ("apr-r", sid, t["id"], t["id"], OP, ahora, ahora))
        j = self.op.post("/api/dymo/remoto/trabajos", json={"tipo": "aprobada", "tarjeta_id": t["id"]}).json()
        with db.get_db() as c:
            c.execute("INSERT INTO tqt_test_runs(id,station,requested_card,operator,state,created,updated,inventory,origin)"
                      " VALUES(?,?,?,?,'running',?,?,'{}','web')", ("run-r", sid, t["id"], OP, ahora + 1, ahora + 1))
        s = self.pi.get("/api/dymo/remoto/agente/siguiente?espera=0", headers=self.H).json()
        self.assertEqual(s["id"], j["id"])
        svg = self.pi.get(s["svg_url"], headers=self.H)
        self.assertEqual(svg.status_code, 200)
        self.assertIn("Aprobada", svg.text)

    def test_latido_vence_aunque_no_pida_trabajo(self):
        self.latido()
        a = svc.encolar("cable", {"numero": "0001"}, 1, "Cable 0001", OP)
        viejo = time.time() - svc.PENDIENTE_TTL - 5
        with db.get_db() as c:
            c.execute("UPDATE dymo_trabajos SET creado=?, actualizado=?", (viejo, viejo))
        self.latido()
        with db.get_db() as c:
            self.assertEqual(c.execute("SELECT estado FROM dymo_trabajos WHERE id=?", (a["id"],)).fetchone()[0], "cancelada")

    def test_svg_r3(self):
        svg = DymoService.generate_r3_svg(["TQT-R3-V30-0084", "TQT-R3-V30-0085"])
        ET.fromstring(svg.encode())
        self.assertIn("TQT-R3-V30-0084", svg); self.assertIn("Inconsolata", svg)


if __name__ == "__main__":
    unittest.main()
