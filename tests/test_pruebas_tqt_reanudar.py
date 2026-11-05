import _aislamiento as iso
"""v1.4.93: Pruebas TQT al volver de otro módulo. El seguimiento de una prueba (eventos, cancelar, log) responde 400 con
el motivo y no 500; una prueba del navegador sin latido se libera sola a los 45 s."""
import time
import unittest

from app.database import db, inventario as inv
from app.main import app
from app.services import test_station as s, usuarios

from _aislamiento import cliente_sin_sesion, verificar_aislamiento

OP = "operador@test.mx"


class TestPruebasTqtReanudar(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        verificar_aislamiento()
        db.init_db()
        usuarios.sembrar(iteraciones=1000)
        usuarios.limitador.reiniciar()
        cls.c = cliente_sin_sesion(app)
        r = cls.c.post("/api/auth/login", json={"email": "developer@skyguardian.mx", "password": usuarios.CLAVE_INICIAL})
        assert r.status_code == 200, r.text

    def test_seguimiento_de_prueba_inexistente_es_400_no_500(self):
        base = "/api/validacion/tqt/runs/" + "0" * 32
        for metodo, ruta in (("get", "/events?after=0"), ("get", ""), ("post", "/cancel"), ("get", "/log")):
            r = getattr(self.c, metodo)(base + ruta)
            self.assertLess(r.status_code, 500, (ruta, r.status_code, r.text))
            self.assertIn(r.status_code, (400, 404), (ruta, r.status_code))

    def test_prueba_web_sin_latido_se_libera_sola(self):
        t = iso.crear_par(iso.nuevo_lote()["id"], version="31")
        inv.set_mac(t["r1"]["id"], iso.mac_unica())
        inv.set_mac(t["r2"]["id"], iso.mac_unica())
        run = s.web_create(t["id"], OP)
        with self.assertRaisesRegex(ValueError, "prueba activa"):
            s.web_create(t["id"], OP)   # con latido reciente: sigue bloqueada
        with db.get_db() as c:
            c.execute("UPDATE tqt_test_runs SET updated=? WHERE id=?", (time.time() - s.WEB_SIN_LATIDO_S - 5, run["id"]))
        again = s.web_create(t["id"], OP)   # sin latido: la anterior queda interrumpida y se puede reintentar
        self.assertNotEqual(again["id"], run["id"])
        self.assertEqual(s.read(run["id"])["state"], "interrupted")


if __name__ == "__main__":
    unittest.main()
