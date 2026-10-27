"""v1.4.58: alta de candados en Skytec al imprimir etiquetas (sin red: _post simulado)."""
import _aislamiento  # noqa: F401  (debe ser lo primero)
import os
import time
import unittest
from unittest import mock

from app.database import db
from app.main import app
from app.services import skytec, usuarios

from _aislamiento import cliente_sin_sesion, verificar_aislamiento

TARJETA = {"r1": {"nombre": "TQT-R1-V30-0029", "mac": "8c:8c:29:c3:e1:30"},
           "r2": {"nombre": "TQT-R2-V30-0029", "mac": "8C:8C:29:C3:E1:3A"}}
ENV = {"TQT_SKYTEC_USER": "u@test.mx", "TQT_SKYTEC_PASSWORD": "x"}


def falso_skytec(existentes=(), respuesta="success"):
    llamadas = []

    def post(ruta, cuerpo):
        llamadas.append((ruta, cuerpo))
        if ruta == "/login_web":
            return {"token": "tk", "nombre": "Dev", "apellido_p": "Seis"}
        if ruta == "/get_candados":
            return {"datos": list(existentes)}
        if ruta == "/upd_candado":
            return {"respuesta": respuesta}
        raise AssertionError(ruta)
    return post, llamadas


class TestSkytec(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        verificar_aislamiento()
        db.init_db()
        usuarios.sembrar(iteraciones=1000)

    def test_sin_credenciales_no_llama(self):
        with mock.patch.dict(os.environ, {"TQT_SKYTEC_USER": "", "TQT_SKYTEC_PASSWORD": ""}), \
                mock.patch.object(skytec, "_post") as p:
            with self.assertRaises(skytec.SkytecNoConfigurado):
                skytec.alta_armado(TARJETA)
            p.assert_not_called()

    def test_crea_r1_y_r2_con_nombre_completo_mac_y_marca_tqt(self):
        post, llamadas = falso_skytec()
        with mock.patch.dict(os.environ, ENV), mock.patch.object(skytec, "_post", side_effect=post):
            items = skytec.alta_armado(TARJETA)
        self.assertEqual([i["estado"] for i in items], ["creado", "creado"])
        altas = [c for r, c in llamadas if r == "/upd_candado"]
        self.assertEqual(len(altas), 2)
        f = altas[0]["formDataJSON"]
        self.assertEqual((f["nombre"], f["identificador"], f["mac"], f["marca"], f["id_candado"]),
                         ("TQT_R1_V30_0029", "TQT_R1_V30_0029", "8C:8C:29:C3:E1:30", "8", "0"))
        self.assertEqual(altas[1]["formDataJSON"]["nombre"], "TQT_R2_V30_0029")
        self.assertEqual((altas[0]["upd"], altas[0]["headers"]["Authorization"], altas[0]["creado"]), (0, "tk", "Dev Seis"))

    def test_reimprimir_no_duplica(self):
        post, llamadas = falso_skytec(existentes=[{"nombre": "TQT_R1_V30_0029", "identificador": "TQT_R1_V30_0029",
                                                    "mac_address": "8C:8C:29:C3:E1:30"}])
        with mock.patch.dict(os.environ, ENV), mock.patch.object(skytec, "_post", side_effect=post):
            items = skytec.alta_armado(TARJETA)
        self.assertEqual([i["estado"] for i in items], ["ya_existia", "creado"])
        self.assertEqual(len([1 for r, _ in llamadas if r == "/upd_candado"]), 1)

    def test_error_de_skytec_se_informa(self):
        post, _ = falso_skytec(respuesta="error")
        with mock.patch.dict(os.environ, ENV), mock.patch.object(skytec, "_post", side_effect=post):
            items = skytec.alta_armado(TARJETA)
        self.assertEqual({i["estado"] for i in items}, {"error"})
        self.assertIn("error", items[0]["detalle"])

    def test_sin_mac_no_da_de_alta(self):
        with mock.patch.dict(os.environ, ENV), mock.patch.object(skytec, "_post") as p:
            with self.assertRaises(skytec.SkytecError):
                skytec.alta_armado({"r1": TARJETA["r1"], "r2": {"nombre": "TQT-R2-V30-0029", "mac": ""}})
            p.assert_not_called()

    def test_endpoint_exige_prueba_aprobada(self):
        import _aislamiento as iso
        from app.services import test_station
        t = iso.crear_par(iso.nuevo_lote()["id"])
        c = cliente_sin_sesion(app)
        c.cookies.set(usuarios.COOKIE, usuarios.emitir_sesion("developer@skyguardian.mx"))
        url = "/api/validacion/tqt/tarjetas/%d/skytec" % t["id"]
        with mock.patch.object(skytec, "alta_armado", return_value=[]) as alta:
            self.assertEqual(c.post(url).status_code, 403)
            alta.assert_not_called()
            test_station.init()
            with db.get_db() as cx:
                sid = test_station.web_station(cx, "op@test.mx")
                cx.execute("INSERT INTO tqt_test_runs(id,station,requested_card,tarjeta_id,operator,state,created,updated,inventory,result,origin)"
                           " VALUES(?,?,?,?,?,'finished',?,?,'{}','aprobado','web')",
                           ("sky-%d" % t["id"], sid, t["id"], t["id"], "op@test.mx", time.time(), time.time()))
            alta.return_value = [{"slot": "R1", "estado": "creado"}, {"slot": "R2", "estado": "creado"}]
            r = c.post(url)
            self.assertEqual(r.status_code, 200, r.text)
            self.assertTrue(r.json()["ok"])
            alta.side_effect = skytec.SkytecError("Sin conexión con Skytec (x).")
            r = c.post(url)
            self.assertEqual(r.status_code, 503)
            self.assertIn("Skytec", r.text)


if __name__ == "__main__":
    unittest.main()
