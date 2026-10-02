"""Endpoints REST v2 (BD temporal aislada): recepción por QR, inventario, MAC, emparejado, reemplazos, lotes y páginas."""
import _aislamiento  # noqa: F401  (debe ser lo primero)
import unittest

from fastapi.testclient import TestClient

from app.database import db
from app.main import app

from _aislamiento import crear_par, mac_unica, nuevo_lote, num_unico, verificar_aislamiento


class TestAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        verificar_aislamiento()
        db.init_db()
        cls.client = TestClient(app)
        cls.lote = nuevo_lote()
        cls.lote_id = cls.lote["id"]

    # ------------------------------------------------------------------ helpers
    def escanear(self, codigo, **extra):
        r = self.client.post("/api/pcb/escanear", json={"codigo": codigo, **extra})
        self.assertEqual(r.status_code, 200, r.text)  # el escaneo continuo NUNCA devuelve errores HTTP
        return r.json()

    def serie(self):
        return num_unico()

    def disponibles(self, serie, tipos=("R1", "R2", "R3")):
        ids = {}
        for t in tipos:
            ids[t] = self.escanear(f"TQT-{t}-V30-{serie}")["pcb"]["id"]
        self.assertEqual(self.client.post("/api/recepcion/confirmar", json={"ids": list(ids.values())}).status_code, 200)
        return ids

    # ------------------------------------------------------------------ sistema y lotes
    def test_01_status_y_config(self):
        d = self.client.get("/api/status").json()
        self.assertEqual((d["status"], d["app_name"]), ("online", "Escaner TQT"))
        self.assertTrue(d["https_url"].startswith("https://"))
        for campo in ("ws_url", "active_lote", "migration_warnings"):
            self.assertIn(campo, d)
        self.assertIn("url", self.client.get("/api/config").json())

    def test_02_lotes_crud_y_excel_mensual(self):
        body = {"codigo_lote": "2027-01-API", "mes": 1, "anio": 2027, "activo": True}
        res = self.client.post("/api/lotes", json=body)
        self.assertEqual(res.status_code, 201)
        creado = res.json()
        self.assertTrue(creado["ruta_excel"].endswith("Control_Produccion_TQT_Enero_2027.xlsx"))
        self.assertEqual(self.client.post("/api/lotes", json=body).status_code, 409)
        sin = self.client.post("/api/lotes", json={"codigo_lote": "2027-02-API", "mes": 2, "anio": 2027, "crear_excel": False})
        self.assertIsNone(sin.json()["ruta_excel"])
        act = self.client.post(f"/api/lotes/{creado['id']}/activar")
        self.assertEqual(act.json()["lote"]["activo"], 1)
        self.assertEqual(self.client.post("/api/lotes/999999/activar").status_code, 404)
        self.client.post(f"/api/lotes/{self.lote_id}/activar")

    # ------------------------------------------------------------------ recepción
    def test_03_escanear_agregada_duplicada_invalida(self):
        s = self.serie()
        a = self.escanear(f"TQT-R3-V30-{s}", operador="ana")
        self.assertEqual(a["resultado"], "AGREGADA")
        self.assertEqual((a["pcb"]["tipo"], a["pcb"]["estado_ciclo"], a["pcb"]["operador"]), ("R3", "RECIBIDA", "ana"))
        self.assertIn("R3", a["conteos"])
        d = self.escanear(f"tqt r3 v30 {s}")
        self.assertEqual((d["resultado"], d["pcb"]["id"]), ("DUPLICADA", a["pcb"]["id"]))
        i = self.escanear("esto no es un QR de PCB")
        self.assertEqual((i["resultado"], i["pcb"]), ("INVALIDA", None))
        # solo número con tipo forzado
        f = self.escanear(str(int(s) + 5000)[-4:], tipo_forzado="R1", version="V31")
        self.assertEqual((f["resultado"], f["pcb"]["version"]), ("AGREGADA", "31"))
        # validación de entrada: 422 (y no 500)
        self.assertEqual(self.client.post("/api/pcb/escanear", json={"codigo": "x" * 500}).status_code, 422)
        self.assertEqual(self.client.post("/api/pcb/escanear", json={}).status_code, 422)

    def test_04_recepcion_y_confirmacion(self):
        s = self.serie()
        ids = [self.escanear(f"TQT-{t}-V30-{s}")["pcb"]["id"] for t in ("R1", "R2")]
        rec = self.client.get("/api/recepcion").json()
        self.assertTrue({p["id"] for p in rec["items"]} >= set(ids))
        for campo in ("conteos", "huecos", "avisos"):
            self.assertIn(campo, rec)
        r = self.client.post("/api/recepcion/confirmar", json={"ids": ids, "nota": "lote de prueba", "operador": "ana"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual((r.json()["confirmadas"], r.json()["omitidas"]), (2, []))
        self.assertNotIn(ids[0], {p["id"] for p in self.client.get("/api/recepcion").json()["items"]})
        self.assertEqual(self.client.get(f"/api/pcb/{ids[0]}").json()["estado_ciclo"], "DISPONIBLE")

    def test_05_alta_manual(self):
        r = self.client.post("/api/pcb/manual", json={"tipo": "R2", "cantidad": 2, "version": "V32"})
        self.assertEqual(r.status_code, 200, r.text)
        pcbs = r.json()["pcbs"]
        self.assertEqual(len(pcbs), 2)
        self.assertTrue(all(p["version"] == "32" and p["origen"] == "MANUAL" for p in pcbs))
        self.assertEqual(int(pcbs[1]["serie"]), int(pcbs[0]["serie"]) + 1)
        self.assertEqual(self.client.post("/api/pcb/manual", json={"tipo": "R9"}).status_code, 400)
        dup = self.client.post("/api/pcb/manual", json={"tipo": "R2", "serie": pcbs[0]["serie"], "version": "32"})
        self.assertEqual(dup.status_code, 409)

    def test_06_ajustes_version_por_defecto(self):
        self.assertEqual(self.client.get("/api/ajustes").json()["version_defecto"], "30")
        self.assertEqual(self.client.put("/api/ajustes", json={"version_defecto": "V31"}).json()["version_defecto"], "31")
        s = self.serie()
        self.assertEqual(self.escanear(s, tipo_forzado="R1")["pcb"]["version"], "31")
        self.assertEqual(self.client.put("/api/ajustes", json={"version_defecto": "abc"}).status_code, 400)
        self.client.put("/api/ajustes", json={"version_defecto": "30"})

    # ------------------------------------------------------------------ edición del inventario
    def test_07_listar_editar_y_eliminar_pcb(self):
        s = self.serie()
        pid = self.escanear(f"TQT-R1-V30-{s}")["pcb"]["id"]
        lista = self.client.get("/api/pcb", params={"q": s, "tipo": "R1"}).json()
        self.assertEqual((lista["total"], lista["items"][0]["id"]), (1, pid))
        self.assertEqual(self.client.get("/api/pcb", params={"tipo": "R9"}).status_code, 400)

        e = self.client.patch(f"/api/pcb/{pid}", json={"version": "V31"})
        self.assertEqual((e.status_code, e.json()["nombre"]), (200, f"TQT-R1-V31-{s}"))
        otra = self.escanear(f"TQT-R1-V30-{s}")["pcb"]["id"]
        self.assertEqual(self.client.patch(f"/api/pcb/{otra}", json={"version": "31"}).status_code, 409)  # choca con la editada
        self.assertEqual(self.client.patch(f"/api/pcb/{otra}", json={"serie": "abc"}).status_code, 400)
        self.assertEqual(self.client.patch("/api/pcb/999999", json={"version": "30"}).status_code, 404)

        choque = self.client.post("/api/pcb/version", json={"ids": [pid, otra], "version": "33"})  # misma serie -> mismo nombre
        self.assertEqual(choque.status_code, 409)
        self.assertEqual(self.client.get(f"/api/pcb/{pid}").json()["version"], "31")               # todo o nada
        s2 = self.serie()
        otra2 = self.escanear(f"TQT-R1-V30-{s2}")["pcb"]["id"]
        m = self.client.post("/api/pcb/version", json={"ids": [pid, otra2], "version": "33"})
        self.assertEqual((m.status_code, m.json()["actualizadas"]), (200, 2))

        self.assertEqual(self.client.delete(f"/api/pcb/{pid}").status_code, 204)
        self.assertEqual(self.client.get(f"/api/pcb/{pid}").status_code, 404)
        self.assertEqual(self.client.delete("/api/pcb/999999").status_code, 404)

    def test_08_no_se_elimina_una_pcb_montada(self):
        t = crear_par(self.lote_id)
        r = self.client.delete(f"/api/pcb/{t['pcb_r1_id']}")
        self.assertEqual(r.status_code, 409)
        self.assertIn("tarjeta", r.json()["detail"])

    # ------------------------------------------------------------------ MAC
    def test_09_mac(self):
        t = crear_par(self.lote_id, r3=True, macs=False)
        r = self.client.put(f"/api/pcb/{t['pcb_r1_id']}/mac", json={"mac": "70-4b-ca-5b-9f-6e", "operador": "luis"})
        self.assertEqual((r.status_code, r.json()["mac"]), (200, "70:4B:CA:5B:9F:6E"))
        self.assertEqual(self.client.put(f"/api/pcb/{t['pcb_r2_id']}/mac", json={"mac": "704bca5b9f6e"}).status_code, 409)
        self.assertEqual(self.client.put(f"/api/pcb/{t['pcb_r2_id']}/mac", json={"mac": "no-es-mac"}).status_code, 400)
        self.assertEqual(self.client.put(f"/api/pcb/{t['pcb_r3_id']}/mac", json={"mac": mac_unica()}).status_code, 400)  # R3 sin MAC
        self.assertEqual(self.client.put("/api/pcb/999999/mac", json={"mac": mac_unica()}).status_code, 404)
        self.assertEqual(self.client.put(f"/api/pcb/{t['pcb_r1_id']}/mac", json={"mac": None}).json()["mac"], None)
        self.assertEqual(self.client.get("/api/pcb", params={"sin_mac": True, "limit": 1000}).json()["total"] >= 2, True)
        c = self.client.get("/api/pcb/por-codigo", params={"codigo": f"TQT-R2-V30-{t['id_tarjeta_num']}"}).json()
        self.assertEqual((c["ranura"], c["tarjeta"]["id"]), ("R2", t["id"]))
        self.assertEqual(self.client.get("/api/pcb/por-codigo", params={"codigo": "TQT-R1-V30-9999"}).status_code, 404)

    # ------------------------------------------------------------------ emparejar
    def test_10_sugerencias_y_emparejado_automatico(self):
        s = self.serie()
        self.disponibles(s)
        sug = self.client.get("/api/emparejar/sugerencias", params={"lote_id": self.lote_id}).json()
        self.assertIn(s, [x["serie"] for x in sug["completas"]])
        r = self.client.post("/api/emparejar/auto", json={"lote_id": self.lote_id, "series": [s, "7777"], "r3": "auto"})
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertEqual([t["id_tarjeta_num"] for t in d["creadas"]], [s])
        self.assertEqual(d["omitidas"][0]["serie"], "7777")
        t = d["creadas"][0]
        self.assertTrue(t["completa"] and t["r3"] and t["estado_general"] == "PENDIENTE")

    def test_11_tarjeta_impar_reemplazo_y_disolver(self):
        s1, s2, s3 = self.serie(), self.serie(), self.serie()
        a, b, c = self.disponibles(s1, ("R1",)), self.disponibles(s2, ("R2",)), self.disponibles(s3, ("R2",))
        r = self.client.post("/api/tarjetas", json={"lote_id": self.lote_id, "r1_id": a["R1"], "r2_id": b["R2"]})
        self.assertEqual(r.status_code, 201, r.text)
        t = r.json()
        self.assertEqual((t["id_tarjeta_num"], t["nombre_r1"], t["nombre_r2"]), (s1, f"TQT-R1-V30-{s1}", f"TQT-R2-V30-{s2}"))  # impar
        self.assertEqual(self.client.post("/api/tarjetas", json={"lote_id": self.lote_id, "r1_id": a["R1"]}).status_code, 409)

        f = self.client.post(f"/api/pcb/{b['R2']}/falla", json={"motivo": "no arranca", "reemplazo_id": c["R2"]})
        self.assertEqual(f.status_code, 200, f.text)
        self.assertEqual(f.json()["pcb"]["estado_ciclo"], "FALLA")
        self.assertEqual(f.json()["tarjeta"]["nombre_r2"], f"TQT-R2-V30-{s3}")

        lib = self.client.put(f"/api/tarjetas/{t['id']}/asignar", json={"ranura": "R2", "pcb_id": None})
        self.assertEqual((lib.status_code, lib.json()["completa"]), (200, False))
        self.assertEqual(self.client.put(f"/api/tarjetas/{t['id']}/asignar", json={"ranura": "R1", "pcb_id": c["R2"]}).status_code, 400)
        self.assertEqual(self.client.put("/api/tarjetas/999999/asignar", json={"ranura": "R1", "pcb_id": None}).status_code, 404)

        d = self.client.delete(f"/api/tarjetas/{t['id']}")
        self.assertEqual((d.status_code, len(d.json()["liberadas"])), (200, 1))
        self.assertEqual(self.client.get(f"/api/tarjetas/{t['id']}").status_code, 404)
        self.assertEqual(self.client.delete(f"/api/tarjetas/{t['id']}").status_code, 404)

    def test_12_datos_de_captura_de_la_tarjeta(self):
        t = crear_par(self.lote_id)
        r = self.client.patch(f"/api/tarjetas/{t['id']}", json={"firmware_r1": "3.2", "semana_produccion": 38, "fecha_real": "2026-09-20"})
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertEqual((d["firmware_r1"], d["semana_produccion"], d["fecha_real"]), ("3.2", 38, "2026-09-20"))
        self.assertEqual(self.client.patch(f"/api/tarjetas/{t['id']}", json={"fecha_real": "20/09/2026"}).status_code, 400)
        self.assertEqual(self.client.patch(f"/api/tarjetas/{t['id']}", json={"semana_produccion": 99}).status_code, 422)
        self.assertIsNone(self.client.patch(f"/api/tarjetas/{t['id']}", json={"fecha_real": ""}).json()["fecha_real"])  # vacía = borra
        self.assertEqual(self.client.patch("/api/tarjetas/999999", json={"firmware_r1": "1"}).status_code, 404)

    # ------------------------------------------------------------------ consulta de tarjetas y estadísticas
    def test_13_tarjetas_listado_busqueda_y_filtros(self):
        lote = nuevo_lote()["id"]
        t = crear_par(lote, r3=True)
        self.assertEqual(self.client.get(f"/api/tarjetas/{t['id']}").json()["id_tarjeta_num"], t["id_tarjeta_num"])
        self.assertEqual(self.client.get(f"/api/tarjetas/by-mac/{t['mac_r1']}").json()["id"], t["id"])
        self.assertEqual(self.client.get("/api/tarjetas/99999999").status_code, 404)
        self.assertEqual(self.client.get("/api/tarjetas/by-mac/FF:FF:FF:00:00:00").status_code, 404)

        lista = self.client.get(f"/api/tarjetas?lote_id={lote}&search={t['id_tarjeta_num']}").json()
        self.assertEqual(lista["total"], 1)
        item = lista["items"][0]
        for campo in ("soldadura", "programacion", "prueba_pcb", "integracion", "prueba_final", "estado_general", "r1", "r2", "r3",
                      "completa", "sin_mac", "estado_pcb_r1", "estado_pcb_r2", "nombre_r3"):
            self.assertIn(campo, item)
        self.assertEqual((item["r3"]["tipo"], item["completa"], item["sin_mac"]), ("R3", True, []))
        # búsqueda por MAC (con y sin separadores) y por nombre de la R3
        self.assertEqual(self.client.get(f"/api/tarjetas?lote_id={lote}&search={t['mac_r2']}").json()["total"], 1)
        self.assertEqual(self.client.get(f"/api/tarjetas?lote_id={lote}&search={t['nombre_r3']}").json()["total"], 1)
        self.assertEqual(self.client.get(f"/api/tarjetas?lote_id={lote}&estado_general=PENDIENTE").json()["total"], 1)
        self.assertEqual(self.client.get(f"/api/tarjetas?lote_id={lote}&estado_general=LIBERADO").json()["total"], 0)

    def test_14_stats_incluye_inventario_e_incompletas(self):
        s = self.client.get(f"/api/stats?lote_id={self.lote_id}").json()
        for campo in ("total_tarjetas", "funcionales", "defectuosas", "en_revision", "pendientes", "en_proceso", "porcentaje_aprobacion",
                      "total_r1_escaneados", "total_r2_escaneados", "total_r3_escaneados", "incompletas", "inventario"):
            self.assertIn(campo, s)
        self.assertTrue(0.0 <= s["porcentaje_aprobacion"] <= 100.0)
        self.assertEqual(set(s["inventario"]), {"R1", "R2", "R3"})

    # ------------------------------------------------------------------ páginas, caché y seguridad
    def test_15_paginas_html(self):
        for ruta in ("/", "/emparejar", "/programar", "/consultar", "/monitor", "/dymo"):
            res = self.client.get(ruta)
            self.assertEqual(res.status_code, 200, ruta)
            self.assertIn("text/html", res.headers.get("content-type", ""), ruta)
            self.assertEqual(res.headers.get("cache-control"), "no-store" if ruta == "/monitor" else "no-cache", ruta)

    def test_16_estaticos_sin_cache(self):
        res = self.client.get("/static/js/common.js")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers.get("cache-control"), "no-cache")
        self.assertEqual(self.client.get("/static/js/no-existe.js").status_code, 404)

    def test_17_certificado_publico_para_instalar_en_el_celular(self):
        res = self.client.get("/cert")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers["content-type"], "application/x-x509-ca-cert")
        self.assertIn('filename="escaner-tqt-ca.crt"', res.headers["content-disposition"])   # la AUTORIDAD local, no el certificado del servidor
        self.assertTrue(res.content.startswith(b"-----BEGIN CERTIFICATE-----"))
        self.assertEqual(res.content.count(b"BEGIN CERTIFICATE"), 1)
        self.assertNotIn(b"PRIVATE KEY", res.content)          # jamás la llave
        self.assertEqual(self.client.get("/ca").content, res.content)

    def test_18_wizard_v1_eliminado(self):
        for ruta in ("/api/scan/validate", "/api/scan/pair"):
            self.assertEqual(self.client.post(ruta, json={"codigo": "x"}).status_code, 404, ruta)

    def test_19_sin_cors_abierto(self):
        res = self.client.get("/api/status", headers={"Origin": "https://sitio-externo.example"})
        self.assertNotIn("access-control-allow-origin", res.headers)

    def test_20_sin_lote_activo_valido_da_errores_claros(self):
        self.assertEqual(self.client.get("/api/emparejar/sugerencias", params={"lote_id": 999999}).status_code, 404)
        self.assertEqual(self.client.post("/api/emparejar/auto", json={"lote_id": 999999}).status_code, 404)


if __name__ == "__main__":
    unittest.main()
