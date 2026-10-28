"""v1.4.51 · Pruebas automáticas: el servidor encadena ciclos de Pruebas TQT y cierra la campaña con reglas seguras."""
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
        self.st = pa.registrar_banco("operador@test.mx", nuevo=True)   # la Raspberry: único banco (aislado por test)
        with db.get_db() as c:
            self.d = s.snapshot(self.t["id"], c)

    def tearDown(self):
        with db.get_db() as c:   # BD de pruebas compartida: no dejar campañas activas que bloqueen reinstalar el banco
            c.execute("UPDATE tqt_resistencia SET estado='detenida' WHERE estado IN ('activa','pausada')")
            c.execute("UPDATE tqt_resistencia_banco SET ocupado_por=NULL,ocupado_desde=NULL,ocupado_visto=NULL")

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

    # ---- v1.4.52: sesiones separadas y Raspberry ocupada ----
    def tomar(self, email, admin=False):
        with db.transaction() as c:
            pa.tomar(c, email, admin)

    def test_otra_cuenta_ve_la_raspberry_ocupada(self):
        c = self.campana(ciclos=3)
        with self.assertRaises(pa.Ocupado) as e:
            self.tomar("otra@test.mx")
        self.assertEqual(e.exception.info["por"], "operador@test.mx")
        self.assertEqual(e.exception.info["campana"]["id"], c["id"])
        b = pa.banco("otra@test.mx")["ocupacion"]
        self.assertFalse(b["mio"])
        self.assertTrue(pa.banco("operador@test.mx")["ocupacion"]["mio"])
        with self.assertRaises(pa.Ocupado):   # tampoco crea campañas ni lee el log del agente
            pa.crear("x", "fw", self.t["id"], 1, 0, True, "otra@test.mx", True)
        with self.assertRaises(pa.Ocupado):
            pa.log_agente("otra@test.mx")

    def test_cada_cuenta_ve_solo_sus_campanas(self):
        c = self.campana(ciclos=1)
        self.assertEqual([x["id"] for x in pa.lista("operador@test.mx")][:1], [c["id"]])
        self.assertNotIn(c["id"], [x["id"] for x in pa.lista("otra@test.mx")])
        with self.assertRaises(ValueError):
            pa.leer(c["id"], "otra@test.mx")
        with self.assertRaises(ValueError):
            pa.cambiar(c["id"], "detener", "otra@test.mx")
        self.assertEqual(pa.leer(c["id"], "jefe@test.mx", True)["id"], c["id"])   # el administrador sí

    def test_sesion_sin_campana_se_libera_al_salir(self):
        self.tomar("operador@test.mx")
        with self.assertRaises(pa.Ocupado):
            self.tomar("otra@test.mx")
        with db.get_db() as c:   # dejó la página hace más de LIBERAR_S
            c.execute("UPDATE tqt_resistencia_banco SET ocupado_visto=?", (0,))
        self.tomar("otra@test.mx")
        self.assertTrue(pa.banco("otra@test.mx")["ocupacion"]["mio"])

    def test_liberar_dueno_y_admin(self):
        c = self.campana(ciclos=3)
        with self.assertRaises(ValueError):   # el dueño primero detiene su campaña
            pa.liberar("operador@test.mx")
        with self.assertRaises(pa.Ocupado):
            pa.liberar("otra@test.mx")
        pa.liberar("jefe@test.mx", True)   # el administrador fuerza: detiene la campaña y libera
        self.assertEqual(pa.leer(c["id"])["estado"], "detenida")
        self.assertIsNone(pa.banco("otra@test.mx")["ocupacion"])

    def test_pruebas_tqt_no_usa_la_raspberry(self):
        """v1.4.54: la Raspberry se anuncia como puente BLE; Pruebas TQT no la lista ni la usa (ni BLE ni pruebas)."""
        from app.services import native_ble
        s.claim(self.st["id"], {"ble_bridge": 1, "serial_connected": True})
        self.assertNotIn(self.st["id"], [x["id"] for x in native_ble.stations("operador@test.mx")])
        with self.assertRaisesRegex(ValueError, "Raspberry"):
            native_ble.prepare("operador@test.mx", {"station_id": self.st["id"], "operation": "scan", "role": "R1", "request_id": "x"})
        with self.assertRaisesRegex(ValueError, "Raspberry"):
            s.create(self.st["id"], self.t["id"], "operador@test.mx", True)
        win = stm.station_create("Banco TQT Windows", "operador@test.mx")
        s.claim(win["id"], {"ble_bridge": 1})
        self.assertIn(win["id"], [x["id"] for x in native_ble.stations("operador@test.mx")])


    def test_cada_cuenta_ve_y_usa_solo_sus_agentes(self):
        """v1.4.55/56: /stations (modo agente de Pruebas TQT) solo lista agentes de la cuenta, sin la Raspberry ni puentes
        «solo BLE»; crear pruebas o mandar comandos a un agente ajeno se rechaza."""
        from starlette.testclient import TestClient
        from app.main import app
        from app.services import usuarios
        yo = usuarios.CUENTAS_INICIALES[0]
        yo = yo["email"] if isinstance(yo, dict) else yo
        s.claim(self.st["id"], {"ble_bridge": 1})
        puente = stm.station_create("Bluetooth TQT Windows (solo BLE)", yo)
        s.claim(puente["id"], {"ble_bridge": 1, "ble_only": True})
        mio = stm.station_create("Banco TQT Windows", yo)
        s.claim(mio["id"], {"ble_bridge": 1, "ble_only": False})
        ajeno = stm.station_create("Banco TQT Windows", "otra@test.mx")
        s.claim(ajeno["id"], {"ble_bridge": 1, "ble_only": False, "serial_connected": True})
        cli = TestClient(app)
        ids = [x["id"] for x in cli.get("/api/validacion/tqt/stations").json()]
        self.assertIn(mio["id"], ids)
        for otro in (puente["id"], ajeno["id"], self.st["id"]):
            self.assertNotIn(otro, ids)
        with self.assertRaisesRegex(ValueError, "otra cuenta"):
            s.create(ajeno["id"], self.t["id"], yo, True)
        r = cli.post("/api/validacion/tqt/commands", json={"station_id": ajeno["id"], "action": "scan_ble"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("otra cuenta", r.text)

    def test_aviso_de_agente_viejo(self):
        """v1.4.57: Pruebas TQT avisa de agentes/puentes viejos de la cuenta; no de otras cuentas ni de la Raspberry;
        un viejo apagado deja de contar cuando la cuenta ya tiene uno actualizado."""
        actual = s.agente_actual()
        self.assertRegex(actual, r"^1\.4\.")
        yo = "aviso-%s@test.mx" % self.t["id"]
        self.assertEqual((s.desactualizados(yo)["estaciones"], s.desactualizados(yo)["sin_agente"]), ([], True))   # v1.4.64: sin ninguno también avisa
        s.claim(self.st["id"], {"ble_bridge": 1, "agent_version": "viejo"})
        ajeno = stm.station_create("Bluetooth TQT Windows (solo BLE)", "otra-" + yo)
        s.claim(ajeno["id"], {"ble_bridge": 1, "ble_only": True})
        viejo = stm.station_create("Bluetooth TQT Windows (solo BLE)", yo)
        s.claim(viejo["id"], {"ble_bridge": 1, "ble_only": True})
        d = s.desactualizados(yo)
        self.assertEqual([(x["nombre"], x["version"], x["solo_ble"]) for x in d["estaciones"]],
                         [(viejo["name"], "anterior a 1.4.51", True)])
        nuevo = stm.station_create("Bluetooth TQT Windows (solo BLE)", yo)
        s.claim(nuevo["id"], {"ble_bridge": 1, "ble_only": True, "agent_version": actual})
        self.assertEqual(s.desactualizados(yo)["estaciones"], [])   # v1.4.60: con uno actualizado ya no se avisa
        self.assertFalse(s.desactualizados(yo)["sin_agente"])
        with db.get_db() as c:
            c.execute("UPDATE tqt_test_presence SET seen=seen-60 WHERE station=?", (viejo["id"],))
        self.assertEqual(s.desactualizados(yo)["estaciones"], [])

    # ---- v1.4.64: instalador de la Raspberry por comando ----
    def test_reinstalar_reutiliza_la_estacion_del_banco(self):
        otra = pa.registrar_banco("operador@test.mx")
        self.assertEqual(otra["id"], self.st["id"])
        self.assertNotEqual(otra["token"], self.st["token"])
        self.assertEqual(stm.station_auth(self.st["token"])["id"], self.st["id"])   # el token previo sigue valiendo
        self.assertEqual(pa.banco()["station"], self.st["id"])
        self.assertEqual(pa.registrar_banco("jefe@test.mx", True)["id"], self.st["id"])   # el admin también reutiliza
        with db.get_db() as c:
            c.execute("UPDATE tqt_resistencia_banco SET ocupado_por=NULL")
        ajena = pa.registrar_banco("otra@test.mx")   # banco de otra cuenta: se crea una estación nueva
        self.assertNotEqual(ajena["id"], self.st["id"])

    def test_comando_de_un_solo_uso_y_caduca(self):
        import io, json, time, zipfile
        from starlette.testclient import TestClient
        from app.main import app
        from app.routers import test_station as rts
        from app.services import instalador_linux, usuarios
        yo = usuarios.CUENTAS_INICIALES[0]
        yo = yo["email"] if isinstance(yo, dict) else yo
        mio = pa.registrar_banco(yo, nuevo=True)
        cli = TestClient(app)   # sesión automática de la primera cuenta (ver _aislamiento)
        z0 = cli.post("/api/pruebas-auto/agente", json={})   # compatibilidad: ZIP por defecto, misma estación
        self.assertEqual((z0.status_code, z0.headers["content-type"], z0.headers["x-tqt-station"]),
                         (200, "application/zip", mio["id"]))
        sh = cli.post("/api/pruebas-auto/agente", json={"formato": "sh", "puerto_serie": "/dev/ttyUSB0"})
        self.assertEqual(sh.status_code, 200, sh.text)
        self.assertEqual(sh.headers["x-tqt-station"], mio["id"])
        self.assertIn("text/x-shellscript", sh.headers["content-type"])
        self.assertIn("instalar_tqt_pruebas.sh", sh.headers["content-disposition"])
        self.assertNotIn(b"\r", sh.content)
        z = zipfile.ZipFile(io.BytesIO(instalador_linux.extraer_zip(sh.content)))
        cfg = json.loads(z.read("config.json"))
        self.assertEqual((cfg["id"], cfg["serial_port"], cfg["ble_only"]), (mio["id"], "/dev/ttyUSB0", False))
        self.assertNotIn(cfg["token"].encode(), sh.content)   # el token solo viaja dentro del ZIP
        self.assertIn("agent.py", z.namelist())
        self.assertIn("--fondo", instalador_linux.script_fondo(sh.content))
        r = cli.post("/api/pruebas-auto/agente", json={"formato": "comando"})
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertEqual(set(d), {"comando", "expira", "station"})
        self.assertEqual(d["station"], mio["id"])
        self.assertAlmostEqual(d["expira"], time.time() + 900, delta=30)
        self.assertRegex(d["comando"], r"^curl -fsSL 'http://testserver/api/stm32/agent/tests/instalar/[A-Za-z0-9_-]{32}\.sh' \| sh$")
        ruta = d["comando"].split("'")[1].replace("http://testserver", "")
        self.assertEqual(cli.get("/api/pruebas-auto/agente/instalacion").json()["etapa"], "")
        anon = iso.cliente_sin_sesion(app, https=False)   # sin sesión ni Bearer
        primero = anon.get(ruta)
        self.assertEqual(primero.status_code, 200)
        self.assertTrue(primero.content.startswith(b"#!/bin/sh"))
        self.assertEqual(json.loads(zipfile.ZipFile(io.BytesIO(instalador_linux.extraer_zip(primero.content)))
                                    .read("config.json"))["id"], mio["id"])
        self.assertEqual(anon.get(ruta).status_code, 404)   # un solo uso
        self.assertEqual(anon.get("/api/stm32/agent/tests/package").status_code, 401)   # sin Bearer no hay otra ruta
        self.assertEqual(anon.get("/api/pruebas-auto/agente/instalacion").status_code, 401)
        codigo, _ = rts.guardar_instalador_sh(b"x", ahora=1.0)   # caducó hace mucho
        self.assertEqual(anon.get(f"/api/stm32/agent/tests/instalar/{codigo}.sh").status_code, 404)

    def test_instalacion_devuelve_etapa_y_listo(self):
        from app.routers import test_station as rts
        rts.INSTALACION.pop(self.st["id"], None)
        d = pa.instalacion(rts.INSTALACION, "1.4.64", "operador@test.mx")
        self.assertEqual((d["etapa"], d["en_linea"], d["listo"]), ("", False, False))
        rts.install_progress(rts.InstallProgress(etapa="dependencias", mensaje="pip"), st={"id": self.st["id"]})
        s.claim(self.st["id"], {"agent_version": "1.4.63"})
        d = pa.instalacion(rts.INSTALACION, "1.4.64", "operador@test.mx")
        self.assertEqual((d["etapa"], d["mensaje"], d["en_linea"], d["listo"]), ("dependencias", "pip", True, False))
        self.assertEqual(set(d), {"etapa", "mensaje", "ts", "en_linea", "agent_version", "servidor_version", "listo"})
        s.claim(self.st["id"], {"agent_version": "1.4.64"})
        self.assertTrue(pa.instalacion(rts.INSTALACION, "1.4.64", "operador@test.mx")["listo"])
        self.campana()   # otra cuenta con la Raspberry ocupada: 409 como el log
        with self.assertRaises(pa.Ocupado):
            pa.instalacion(rts.INSTALACION, "1.4.64", "otra@test.mx")


if __name__ == "__main__":
    unittest.main()
