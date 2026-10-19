"""v1.4.6: «Cable R3» automático en la DYMO compartida al asignar una R3 a una TQT."""
import _aislamiento as iso  # noqa: F401  (debe ser lo primero)
import json
import unittest

from app.database import db
from app.main import app
from app.services import cable_r3_auto as auto, dymo_remoto as svc, usuarios

from _aislamiento import cliente_sin_sesion, verificar_aislamiento


class TestCableR3Auto(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        verificar_aislamiento()
        db.init_db()
        usuarios.sembrar(iteraciones=1000)
        svc.init()

    def setUp(self):
        with db.get_db() as c:
            c.execute("DELETE FROM dymo_trabajos"); c.execute("DELETE FROM dymo_agentes")
        auto.set_activo(False)
        self.ag = svc.agente_crear("Raspberry prueba")
        self.lote = iso.nuevo_lote()["id"]

    def latido(self, ok=True):
        svc.latido(self.ag["id"], {"version": "1", "cola": "TQT_DYMO", "impresora_ok": ok, "detalle": ""})

    def trabajos(self):
        with db.get_db() as c:
            return [dict(r) for r in c.execute("SELECT tipo, params, operador FROM dymo_trabajos")]

    def test_apagado_no_imprime(self):
        self.latido()
        t = iso.crear_par(self.lote, r3=True)
        self.assertIsNone(auto.al_notificar(t))
        self.assertEqual(self.trabajos(), [])

    def test_solo_asignaciones_nuevas_y_una_vez(self):
        self.latido()
        vieja = iso.crear_par(self.lote, r3=True)
        res = auto.set_activo(True)
        self.assertTrue(res["activo"]); self.assertGreaterEqual(res["marcadas"], 1)
        self.assertIsNone(auto.al_notificar(vieja))   # ya tenía R3 al encender: no se imprime
        nueva = db.get_tarjeta_by_id(iso.crear_par(self.lote, r3=True)["id"])
        r = auto.al_notificar(nueva)
        self.assertTrue(r and r["ok"], r)
        (j,) = self.trabajos()
        self.assertEqual(j["tipo"], "cable")
        self.assertEqual(json.loads(j["params"]), {"numero": auto.numero_tarjeta(nueva), "r3": auto.numero_r3(nueva)})
        self.assertIsNone(auto.al_notificar(nueva))   # misma pareja: no se repite
        self.assertEqual(len(self.trabajos()), 1)
        sin_r3 = iso.crear_par(self.lote)
        self.assertIsNone(auto.al_notificar(sin_r3))

    def test_sin_dymo_queda_pendiente(self):
        auto.set_activo(True)
        t = db.get_tarjeta_by_id(iso.crear_par(self.lote, r3=True)["id"])
        r = auto.al_notificar(t)   # sin latido: la Raspberry no está en línea
        self.assertFalse(r["ok"]); self.assertEqual(self.trabajos(), [])
        self.latido()
        self.assertTrue(auto.al_notificar(t)["ok"])   # se reintenta en el siguiente aviso
        self.assertEqual(len(self.trabajos()), 1)

    def test_endpoint_exige_admin(self):
        c = cliente_sin_sesion(app)
        c.cookies.set(usuarios.COOKIE, usuarios.emitir_sesion("developer@skyguardian.mx"))
        self.assertIn(c.put("/api/admin/dymo/cable-r3-auto", json={"activo": True}).status_code, (401, 403, 503))   # 503 = administración deshabilitada
        self.assertFalse(auto.activo())


if __name__ == "__main__":
    unittest.main()
