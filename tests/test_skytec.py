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
            alta.return_value = [{"slot": "R1", "nombre": "TQT_R1_X", "mac": "AA", "estado": "creado"}, {"slot": "R2", "nombre": "TQT_R2_X", "mac": "BB", "estado": "creado"}]
            r = c.post(url)
            self.assertEqual(r.status_code, 200, r.text)
            self.assertTrue(r.json()["ok"])
            alta.side_effect = skytec.SkytecError("Sin conexión con Skytec (x).")
            r = c.post(url)
            self.assertEqual(r.status_code, 503)
            self.assertIn("Skytec", r.text)


    def test_tarjeta_queda_marcada_skytec_y_boton_de_tarjetas(self):
        """v1.4.60: el alta se guarda por tarjeta; la tarjeta trae skytec=True solo con R1 y R2 registradas con su MAC vigente."""
        import _aislamiento as iso
        t = iso.crear_par(iso.nuevo_lote()["id"])
        self.assertFalse(db.get_tarjeta_by_id(t["id"])["skytec"])
        c = cliente_sin_sesion(app)
        c.cookies.set(usuarios.COOKIE, usuarios.emitir_sesion("developer@skyguardian.mx"))
        post, llamadas = falso_skytec()
        with mock.patch.dict(os.environ, ENV), mock.patch.object(skytec, "_post", side_effect=post):
            r = c.post("/api/tarjetas/%d/skytec" % t["id"])   # sin prueba aprobada: el botón de Tarjetas sí procede
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual([i["estado"] for i in r.json()["items"]], ["creado", "creado"])
        self.assertTrue(db.get_tarjeta_by_id(t["id"])["skytec"])
        items, _ = db.list_tarjetas(lote_id=db.get_tarjeta_by_id(t["id"])["lote_id"])
        self.assertTrue(next(x for x in items if x["id"] == t["id"])["skytec"])
        with db.get_db() as cx:   # otra MAC en la R2 (placa cambiada): deja de contar
            cx.execute("UPDATE skytec_candados SET mac='00:00:00:00:00:00' WHERE tarjeta_id=? AND slot='R2'", (t["id"],))
        self.assertFalse(db.get_tarjeta_by_id(t["id"])["skytec"])
        with mock.patch.dict(os.environ, {"TQT_SKYTEC_USER": "", "TQT_SKYTEC_PASSWORD": ""}):
            self.assertEqual(c.post("/api/tarjetas/%d/skytec" % t["id"]).status_code, 503)
        self.assertEqual(c.post("/api/tarjetas/999999/skytec").status_code, 404)


    def test_respuesta_fallida_pero_creado_se_confirma_en_la_lista(self):
        """v1.4.62: si upd_candado no responde 'success' pero el candado aparece en la lista de Skytec, cuenta como creado."""
        creados = []

        def post(ruta, cuerpo):
            if ruta == "/login_web":
                return {"token": "tk"}
            if ruta == "/get_candados":
                return {"datos": [{"identificador": n, "mac_address": "", "nombre": n} for n in creados]}
            creados.append(cuerpo["formDataJSON"]["identificador"])
            raise skytec.SkytecError("Sin conexión con Skytec (timed out).")
        with mock.patch.dict(os.environ, ENV), mock.patch.object(skytec, "_post", side_effect=post):
            items = skytec.alta_armado(TARJETA)
        self.assertEqual([i["estado"] for i in items], ["creado", "creado"])

    def test_sincronizar_marca_y_desmarca(self):
        import _aislamiento as iso
        t = iso.crear_par(iso.nuevo_lote()["id"])
        tj = db.get_tarjeta_by_id(t["id"])
        r1, r2 = skytec.nombre_completo(tj["r1"]), tj["r2"]["mac"].upper()
        lista = [{"identificador": r1, "mac_address": "", "nombre": r1}, {"identificador": "OTRO", "mac_address": r2, "nombre": "OTRO"}]
        c = cliente_sin_sesion(app)
        c.cookies.set(usuarios.COOKIE, usuarios.emitir_sesion("developer@skyguardian.mx"))
        post, llamadas = falso_skytec(existentes=lista)
        with mock.patch.dict(os.environ, ENV), mock.patch.object(skytec, "_post", side_effect=post):
            r = c.post("/api/tarjetas/skytec/sincronizar")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertGreaterEqual(r.json()["con_candados"], 1)
        self.assertNotIn("/upd_candado", [x for x, _ in llamadas])   # sincronizar nunca crea
        self.assertTrue(db.get_tarjeta_by_id(t["id"])["skytec"])
        post, _ = falso_skytec(existentes=lista[:1])               # la R2 ya no está en Skytec
        with mock.patch.dict(os.environ, ENV), mock.patch.object(skytec, "_post", side_effect=post):
            self.assertEqual(c.post("/api/tarjetas/skytec/sincronizar").status_code, 200)
        self.assertFalse(db.get_tarjeta_by_id(t["id"])["skytec"])
        with mock.patch.dict(os.environ, {"TQT_SKYTEC_USER": "", "TQT_SKYTEC_PASSWORD": ""}):
            self.assertEqual(c.post("/api/tarjetas/skytec/sincronizar").status_code, 503)


if __name__ == "__main__":
    unittest.main()
