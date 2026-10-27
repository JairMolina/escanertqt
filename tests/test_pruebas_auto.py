"""v1.4.xx · Pruebas automáticas: el servidor encadena ciclos de Pruebas TQT y cierra la campaña con reglas seguras."""
import _aislamiento as iso
import unittest
from app.database import db, inventario as inv
from app.services import test_station as s, stm32_programming as stm, pruebas_auto as pa

LIBRE = {"serial_connected": True}


class PruebasAuto(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init_db()

    def setUp(self):
        self.t = iso.crear_par(iso.nuevo_lote()["id"], version="30")
        inv.set_mac(self.t["r1"]["id"], iso.mac_unica())
        inv.set_mac(self.t["r2"]["id"], iso.mac_unica())
        self.st = pa.registrar_banco("operador@test.mx")   # la Raspberry: único banco del submódulo
        with db.get_db() as c:
            self.d = s.snapshot(self.t["id"], c)

    def tearDown(self):
        with db.get_db() as c:   # BD de pruebas compartida: no dejar campañas activas que bloqueen reinstalar el banco
            c.execute("UPDATE tqt_resistencia SET estado='detenida' WHERE estado IN ('activa','pausada')")

    def report(self, ok=True):
        return dict(
            result="aprobado" if ok else "fallido",
            card=self.d["nombre"].replace("-", "_"), card_id=self.d["r1_serie"],
            reported_mac=self.d["mac_r1"], r1_ble_address=self.d["mac_r1"],
            reported_mac_r2=self.d["mac_r2"], r2_ble_address=self.d["mac_r2"],
            steps=[{"name": str(i), "state": "aprobado" if ok or i < 13 else "fallido"} for i in range(14)],
            communication_quality={"state": "limpia"},
            serial_health={"frames": 50, "retries": 0, "partial_warnings": 0, "ack_errors": 0},
            warnings=[], status_final={"IDR": self.d["r2_serie"]},
        )

    def campana(self, ciclos=2, detener=True, pausa=0):
        return pa.crear("Resistencia", "FW 4.4 beta", self.t["id"], ciclos, pausa, detener, "operador@test.mx", True)

    def ciclo(self, ok=True):
        job = s.claim(self.st["id"], LIBRE)
        self.assertIn("run", job)
        s.finish(self.st["id"], job["run"]["id"], self.report(ok))
        return job["run"]["id"]

    def test_completa_todos_los_ciclos_y_termina(self):
        c = self.campana(ciclos=2)
        self.ciclo(); self.ciclo()
        self.assertEqual(s.claim(self.st["id"], LIBRE), {})
        d = pa.leer(c["id"])
        self.assertEqual(d["estado"], "terminada")
        self.assertEqual(d["conteo"]["aprobados"], 2)
        self.assertEqual([x["n"] for x in d["ciclos_detalle"]], [2, 1])

    def test_falla_detiene_si_se_pide(self):
        c = self.campana(ciclos=5, detener=True)
        self.ciclo(ok=False)
        s.claim(self.st["id"], LIBRE)
        self.assertEqual(pa.leer(c["id"])["estado"], "fallida")

    def test_falla_sigue_si_no_se_pide(self):
        c = self.campana(ciclos=2, detener=False)
        self.ciclo(ok=False); self.ciclo()
        s.claim(self.st["id"], LIBRE)
        d = pa.leer(c["id"])
        self.assertEqual((d["estado"], d["conteo"]["fallidos"], d["conteo"]["aprobados"]), ("fallida", 1, 1))

    def test_interrumpido_detiene_y_no_repite(self):
        c = self.campana(ciclos=3)
        job = s.claim(self.st["id"], LIBRE)
        s.claim(self.st["id"], {"serial_connected": True, "run_id": None})   # el agente se reinició: ejecución interrumpida
        self.assertEqual(s.claim(self.st["id"], LIBRE), {})
        d = pa.leer(c["id"])
        self.assertEqual(d["estado"], "detenida")
        self.assertEqual(len(d["ciclos_detalle"]), 1)
        self.assertEqual(s.read(job["run"]["id"])["result"], "no_verificado")

    def test_sin_puerto_serie_no_encola_y_pausa_respeta(self):
        c = self.campana(ciclos=3, pausa=3600)
        self.assertEqual(s.claim(self.st["id"], {"serial_connected": False}), {})
        self.ciclo()
        self.assertEqual(s.claim(self.st["id"], LIBRE), {})   # pausa de 1 h sin cumplir
        self.assertEqual(len(pa.leer(c["id"])["ciclos_detalle"]), 1)

    def test_pausar_y_una_sola_campana_por_estacion(self):
        c = self.campana(ciclos=3)
        pa.cambiar(c["id"], "pausar", "operador@test.mx")
        self.assertEqual(s.claim(self.st["id"], LIBRE), {})
        with self.assertRaises(ValueError):
            self.campana()
        pa.cambiar(c["id"], "detener", "operador@test.mx")
        self.assertEqual(pa.leer(c["id"])["estado"], "detenida")

    def test_exige_confirmacion_fisica(self):
        with self.assertRaises(ValueError):
            pa.crear("x", "fw", self.t["id"], 1, 0, True, "op", False)

    def test_banco_unico_y_reinstalar(self):
        b = pa.banco()
        self.assertTrue(b["registrado"]); self.assertEqual(b["station"], self.st["id"])
        self.campana()
        with self.assertRaises(ValueError):   # con campaña activa no se cambia de agente
            pa.registrar_banco("operador@test.mx")

    def test_log_del_agente_pedido_y_subido(self):
        self.assertFalse(pa.pide_log(self.st["id"]))
        pa.pedir_log()
        self.assertTrue(pa.pide_log(self.st["id"]))
        pa.guardar_log(self.st["id"], "linea 1\nlinea 2")
        self.assertFalse(pa.pide_log(self.st["id"]))
        self.assertEqual(pa.log_agente()[0], "linea 1\nlinea 2")
        otra = stm.station_create("Otra laptop", "operador@test.mx")
        with self.assertRaises(ValueError):
            pa.guardar_log(otra["id"], "x")

    def test_log_de_campana_txt(self):
        c = self.campana(ciclos=1)
        self.ciclo()
        _, texto = pa.log_campana(c["id"], lambda jid: "LOG " + jid + "\n")
        self.assertIn("===== Ciclo 1 · aprobado", texto)
        self.assertIn("Firmware: FW 4.4 beta", texto)


if __name__ == "__main__":
    unittest.main()
