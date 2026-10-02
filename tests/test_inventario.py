"""Inventario global de PCB: recepción por QR, edición, versión, MAC, emparejado, tarjetas impares y reemplazo de falladas."""
import _aislamiento  # noqa: F401  (debe ser lo primero)
import tempfile
import unittest
from pathlib import Path

from app.database import db, inventario as inv
from app.database.db import ConflictoError, NoEncontradoError

from _aislamiento import crear_par, mac_unica, verificar_aislamiento


class TestInventario(unittest.TestCase):
    def setUp(self):
        verificar_aislamiento()
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "inv.db"
        db.init_db(self.path)
        self.lote = db.get_active_lote(db_path=self.path)["id"]

    def tearDown(self):
        self.tmp.cleanup()

    # ------------------------------------------------------------------ helpers
    def esc(self, codigo, **kw):
        return inv.escanear_pcb(codigo, db_path=self.path, **kw)

    def disponibles(self, *codigos):
        """Escanea y confirma; devuelve {nombre: id}."""
        ids = {}
        for c in codigos:
            r = self.esc(c)
            self.assertEqual(r["resultado"], "AGREGADA", r)
            ids[r["pcb"]["nombre"]] = r["pcb"]["id"]
        inv.confirmar_recepcion(list(ids.values()), db_path=self.path)
        return ids

    # ------------------------------------------------------------------ escaneo
    def test_01_qr_del_ejemplo_real(self):
        r = self.esc("TQT-R3-V30-0084", operador="ana")
        self.assertEqual(r["resultado"], "AGREGADA")
        p = r["pcb"]
        self.assertEqual((p["tipo"], p["version"], p["serie"], p["nombre"]), ("R3", "30", "0084", "TQT-R3-V30-0084"))
        self.assertEqual((p["estado_ciclo"], p["origen"], p["operador"], p["mac"]), ("RECIBIDA", "QR", "ana", None))
        self.assertEqual(r["conteos"], {"R1": 0, "R2": 0, "R3": 1, "total": 1})

    def test_02_parser_tolerante(self):
        for crudo, nombre in (("tqt r1 v30 0021", "TQT-R1-V30-0021"), ("TQT_R2_V31_0010", "TQT-R2-V31-0010"),
                              ("  TQT-R1-V30-22 \r\n", "TQT-R1-V30-0022"), ("TQT-R3-V30-0084", "TQT-R3-V30-0084")):
            r = self.esc(crudo)
            self.assertEqual((r["resultado"], r["pcb"]["nombre"]), ("AGREGADA", nombre), crudo)

    def test_03_duplicada_e_idempotente(self):
        primero = self.esc("TQT-R1-V30-0001")
        segundo = self.esc("tqt-r1-v30-0001")
        self.assertEqual((primero["resultado"], segundo["resultado"]), ("AGREGADA", "DUPLICADA"))
        self.assertEqual(segundo["pcb"]["id"], primero["pcb"]["id"])
        self.assertEqual(segundo["conteos"]["total"], 1)
        # también es DUPLICADA cuando ya está confirmada o asignada, y el mensaje dice dónde
        ids = self.disponibles("TQT-R1-V30-0002", "TQT-R2-V30-0002")
        inv.crear_tarjeta(self.lote, None, ids["TQT-R1-V30-0002"], ids["TQT-R2-V30-0002"], db_path=self.path)
        r = self.esc("TQT-R1-V30-0002")
        self.assertEqual(r["resultado"], "DUPLICADA")
        self.assertIn("tarjeta 0002", r["mensaje"])
        self.assertEqual(r["pcb"]["ranura"], "R1")

    def test_04_invalidas(self):
        for basura in ("hola", "", "TQT-R4-V30-0001", "TQT-R1-0001", "70:4b:ca:5b:9f:6e", "0084"):
            r = self.esc(basura)
            self.assertEqual(r["resultado"], "INVALIDA", basura)
            self.assertIsNone(r["pcb"])
        self.assertEqual(inv.listar_recepcion(db_path=self.path)["conteos"]["total"], 0)

    def test_05_solo_numero_requiere_tipo_forzado(self):
        r = self.esc("84", tipo_forzado="R3", version="V31")
        self.assertEqual((r["resultado"], r["pcb"]["nombre"]), ("AGREGADA", "TQT-R3-V31-0084"))
        inv.set_version_defecto("32", db_path=self.path)
        self.assertEqual(self.esc("85", tipo_forzado="R2")["pcb"]["nombre"], "TQT-R2-V32-0085")  # versión por defecto

    def test_06_misma_serie_otra_version_es_otra_pcb(self):
        a, b = self.esc("TQT-R1-V30-0005"), self.esc("TQT-R1-V31-0005")
        self.assertEqual((a["resultado"], b["resultado"]), ("AGREGADA", "AGREGADA"))
        self.assertNotEqual(a["pcb"]["id"], b["pcb"]["id"])

    # ------------------------------------------------------------------ recepción
    def test_07_recepcion_conteos_huecos_y_avisos(self):
        for c in ("TQT-R1-V30-0001", "TQT-R1-V30-0002", "TQT-R1-V30-0005", "TQT-R2-V30-0001"):
            self.esc(c)
        rec = inv.listar_recepcion(db_path=self.path)
        self.assertEqual(rec["conteos"], {"R1": 3, "R2": 1, "R3": 0, "total": 4})
        self.assertEqual(rec["huecos"]["R1"], ["0003", "0004"])
        self.assertEqual(rec["huecos"]["R2"], [])
        self.assertTrue(any("Desbalance" in a for a in rec["avisos"]))
        self.assertTrue(any("R1: faltan 2" in a for a in rec["avisos"]))
        self.assertEqual(rec["items"][0]["nombre"], "TQT-R2-V30-0001")  # las más nuevas primero

    def test_08_confirmar_todo_o_solo_algunas(self):
        a = self.esc("TQT-R1-V30-0001")["pcb"]["id"]
        b = self.esc("TQT-R2-V30-0001")["pcb"]["id"]
        self.esc("TQT-R3-V30-0001")
        r = inv.confirmar_recepcion([a, b, 9999], nota="lote 1", db_path=self.path)
        self.assertEqual((r["confirmadas"], r["omitidas"]), (2, [9999]))
        self.assertEqual(r["disponibles"], {"R1": 1, "R2": 1, "R3": 0, "total": 2})
        self.assertEqual(inv.get_pcb(a, db_path=self.path)["estado_ciclo"], "DISPONIBLE")
        rest = inv.confirmar_recepcion(db_path=self.path)
        self.assertEqual(rest["confirmadas"], 1)
        self.assertEqual(inv.confirmar_recepcion(db_path=self.path)["confirmadas"], 0)  # ya no queda borrador

    def test_09_alta_manual_serie_automatica_y_conflictos(self):
        r = inv.registrar_manual("R1", None, None, 3, db_path=self.path)
        self.assertEqual([p["serie"] for p in r["pcbs"]], ["0001", "0002", "0003"])
        self.assertTrue(all(p["origen"] == "MANUAL" and p["estado_ciclo"] == "RECIBIDA" for p in r["pcbs"]))
        self.assertEqual(inv.registrar_manual("R1", "31", None, 1, db_path=self.path)["pcbs"][0]["serie"], "0004")
        self.assertEqual(inv.registrar_manual("R2", None, "0100", 1, db_path=self.path)["pcbs"][0]["nombre"], "TQT-R2-V30-0100")
        with self.assertRaises(ConflictoError):  # todo o nada
            inv.registrar_manual("R1", "30", "0003", 3, db_path=self.path)
        self.assertEqual(inv.listar_recepcion(db_path=self.path)["conteos"]["R1"], 4)
        for malo in (dict(tipo="R9"), dict(tipo="R1", version="abc"), dict(tipo="R1", serie="12345"), dict(tipo="R1", cantidad=0)):
            with self.assertRaises(ValueError):
                inv.registrar_manual(malo.pop("tipo"), malo.get("version"), malo.get("serie"), malo.get("cantidad", 1), db_path=self.path)

    # ------------------------------------------------------------------ edición / versión / baja
    def test_10_editar_recalcula_nombre_y_detecta_choques(self):
        a = self.esc("TQT-R1-V30-0001")["pcb"]
        self.esc("TQT-R1-V30-0002")
        e = inv.editar_pcb(a["id"], version="V31", serie="7", db_path=self.path)
        self.assertEqual((e["version"], e["serie"], e["nombre"]), ("31", "0007", "TQT-R1-V31-0007"))
        with self.assertRaises(ConflictoError):
            inv.editar_pcb(a["id"], version="30", serie="2", db_path=self.path)
        self.assertEqual(inv.editar_pcb(a["id"], tipo="R2", db_path=self.path)["nombre"], "TQT-R2-V31-0007")  # corregir tipo mal leído
        with self.assertRaises(ValueError):
            inv.editar_pcb(a["id"], version="x", db_path=self.path)
        with self.assertRaises(NoEncontradoError):
            inv.editar_pcb(99999, version="30", db_path=self.path)

    def test_11_editar_pcb_asignada_se_refleja_en_la_tarjeta(self):
        t = crear_par(self.lote, path=self.path)
        inv.editar_pcb(t["pcb_r1_id"], version="31", db_path=self.path)
        nueva = db.get_tarjeta_by_id(t["id"], db_path=self.path)
        self.assertEqual(nueva["nombre_r1"], f"TQT-R1-V31-{t['id_tarjeta_num']}")
        self.assertEqual(nueva["nombre_r2"], f"TQT-R2-V30-{t['id_tarjeta_num']}")  # cada PCB conserva su versión
        with self.assertRaises(ConflictoError):  # cambiar el tipo de una PCB montada no se permite
            inv.editar_pcb(t["pcb_r1_id"], tipo="R2", db_path=self.path)

    def test_12_version_masiva_todo_o_nada(self):
        ids = [self.esc(f"TQT-R1-V30-000{i}")["pcb"]["id"] for i in (1, 2, 3)]
        r = inv.cambiar_version_masiva(ids, "V31", db_path=self.path)
        self.assertEqual((r["actualizadas"], r["version"]), (3, "31"))
        self.assertEqual({p["nombre"] for p in r["pcbs"]}, {"TQT-R1-V31-0001", "TQT-R1-V31-0002", "TQT-R1-V31-0003"})
        # choque: una V30-0001 nueva ya existe (la anterior se renombró), volver a V30 pisaría a la nueva
        inv.escanear_pcb("TQT-R1-V30-0002", db_path=self.path)
        with self.assertRaises(ConflictoError):
            inv.cambiar_version_masiva(ids, "30", db_path=self.path)
        self.assertEqual({inv.get_pcb(i, db_path=self.path)["version"] for i in ids}, {"31"})  # no se cambió ninguna
        with self.assertRaises(NoEncontradoError):
            inv.cambiar_version_masiva(ids + [9999], "32", db_path=self.path)

    def test_13_eliminar_segun_el_ciclo(self):
        a = self.esc("TQT-R1-V30-0001")["pcb"]["id"]
        self.assertEqual(inv.eliminar_pcb(a, db_path=self.path)["accion"], "ELIMINADA")
        self.assertIsNone(inv.get_pcb(a, db_path=self.path))
        self.assertEqual(self.esc("TQT-R1-V30-0001")["resultado"], "AGREGADA")  # se puede volver a escanear

        t = crear_par(self.lote, path=self.path)
        with self.assertRaises(ConflictoError) as ctx:
            inv.eliminar_pcb(t["pcb_r1_id"], db_path=self.path)
        self.assertIn("tarjeta", str(ctx.exception))

        inv.asignar_pcb(t["id"], "R1", None, marcar_falla=True, db_path=self.path)  # queda FALLA
        self.assertEqual(inv.eliminar_pcb(t["pcb_r1_id"], db_path=self.path)["accion"], "BAJA")
        self.assertEqual(inv.get_pcb(t["pcb_r1_id"], db_path=self.path)["estado_ciclo"], "BAJA")
        with self.assertRaises(NoEncontradoError):
            inv.eliminar_pcb(99999, db_path=self.path)

    # ------------------------------------------------------------------ MAC
    def test_14_mac_formatos_y_reglas(self):
        ids = self.disponibles("TQT-R1-V30-0001", "TQT-R2-V30-0001", "TQT-R3-V30-0001")
        r1, r2, r3 = ids["TQT-R1-V30-0001"], ids["TQT-R2-V30-0001"], ids["TQT-R3-V30-0001"]
        self.assertEqual(inv.set_mac(r1, "70-4b-ca-5b-9f-6e", db_path=self.path)["mac"], "70:4B:CA:5B:9F:6E")
        self.assertEqual(inv.set_mac(r1, "704bca5b9f6e", db_path=self.path)["mac"], "70:4B:CA:5B:9F:6E")  # misma MAC: idempotente
        with self.assertRaises(ConflictoError) as ctx:
            inv.set_mac(r2, "70:4b:ca:5b:9f:6e", db_path=self.path)
        self.assertIn("TQT-R1-V30-0001", str(ctx.exception))  # dice quién la tiene
        with self.assertRaises(ValueError):
            inv.set_mac(r3, "70:4b:ca:5b:9c:a2", db_path=self.path)  # R3 no tiene MAC
        for mala in ("xx:yy", "00:00:00:00:00:00", "70:4b:ca:5b:9f", "12345"):
            with self.assertRaises(ValueError, msg=mala):
                inv.set_mac(r2, mala, db_path=self.path)
        self.assertIsNone(inv.set_mac(r1, None, db_path=self.path)["mac"])       # borrar
        self.assertEqual(inv.set_mac(r2, "70:4b:ca:5b:9f:6e", db_path=self.path)["mac"], "70:4B:CA:5B:9F:6E")  # ya libre

    def test_15_sin_mac_y_busqueda(self):
        t = crear_par(self.lote, path=self.path, macs=False)
        self.assertEqual(t["sin_mac"], ["R1", "R2"])
        pend = inv.listar_pcb(sin_mac=True, db_path=self.path)
        self.assertEqual({p["tipo"] for p in pend["items"]}, {"R1", "R2"})
        inv.set_mac(t["pcb_r1_id"], "70:4b:ca:5b:9f:6e", db_path=self.path)
        self.assertEqual(inv.listar_pcb(sin_mac=True, db_path=self.path)["total"], 1)
        self.assertEqual(inv.listar_pcb(q="704bca5b9f6e", db_path=self.path)["items"][0]["id"], t["pcb_r1_id"])
        self.assertEqual(inv.pcb_por_codigo("70:4b:ca:5b:9f:6e", db_path=self.path)["tarjeta"]["id"], t["id"])
        self.assertEqual(inv.pcb_por_codigo(f"TQT-R2-V30-{t['id_tarjeta_num']}", db_path=self.path)["ranura"], "R2")
        with self.assertRaises(NoEncontradoError):
            inv.pcb_por_codigo("TQT-R1-V30-9999", db_path=self.path)

    # ------------------------------------------------------------------ emparejar
    def test_16_sugerencias_y_auto(self):
        self.disponibles("TQT-R1-V30-0001", "TQT-R2-V30-0001", "TQT-R3-V30-0001",
                         "TQT-R1-V30-0002", "TQT-R2-V30-0002",                       # sin R3: igual se empareja
                         "TQT-R1-V30-0003",                                          # sin R2: incompleta
                         "TQT-R2-V30-0004")                                          # sin R1: incompleta
        self.esc("TQT-R1-V30-0009")                                                  # borrador: no cuenta
        sug = inv.sugerencias(self.lote, db_path=self.path)
        self.assertEqual([x["serie"] for x in sug["completas"]], ["0001", "0002"])
        self.assertEqual({x["serie"]: x["faltan"] for x in sug["incompletas"]}, {"0003": ["R2"], "0004": ["R1"]})
        self.assertEqual(len(sug["sueltas"]["R1"]), 3)

        res = inv.emparejar_auto(self.lote, None, "ana", r3_auto=True, db_path=self.path)
        # primero las parejas (0001, 0002) y después la impar con lo que sobra (R1 0003 + R2 0004)
        self.assertEqual([t["id_tarjeta_num"] for t in res["creadas"]], ["0001", "0002", "0003"])
        self.assertEqual(res["creadas"][2]["nombre_r2"], "TQT-R2-V30-0004")
        t1 = res["creadas"][0]
        self.assertTrue(t1["completa"] and t1["r3"] is not None)
        self.assertEqual((t1["estado_general"], t1["r1"]["estado_ciclo"]), ("PENDIENTE", "ASIGNADA"))
        self.assertIsNone(res["creadas"][1]["r3"])
        self.assertEqual(inv.emparejar_auto(self.lote, db_path=self.path)["creadas"], [])  # ya no queda nada por emparejar

    def test_16b_impares_en_orden_numerico_y_con_r3(self):
        self.disponibles("TQT-R1-V30-0005", "TQT-R2-V30-0005",                       # pareja
                         "TQT-R1-V30-0021", "TQT-R1-V30-0018", "TQT-R1-V30-0030",   # R1 sobrantes (desordenadas)
                         "TQT-R2-V30-0040", "TQT-R2-V30-0010",                       # R2 sobrantes
                         "TQT-R3-V30-0018", "TQT-R3-V30-0050")
        res = inv.emparejar_auto(self.lote, r3_auto=True, db_path=self.path)
        vistas = [(t["nombre_r1"][-4:], t["nombre_r2"][-4:], (t["nombre_r3"] or "-")[-4:]) for t in res["creadas"]]
        # parejas primero; luego R1 y R2 sobrantes por orden: 0018+0010 (R3 del mismo número 0018), 0021+0040 (R3 sobrante 0050)
        self.assertEqual(vistas, [("0005", "0005", "-"), ("0018", "0010", "0018"), ("0021", "0040", "0050")])
        self.assertEqual(inv.listar_pcb(estado_ciclo="DISPONIBLE", db_path=self.path)["total"], 1)  # R1 0030 sin par

    def test_16d_r3_manual_por_defecto_no_asigna_r3(self):
        self.disponibles("TQT-R1-V30-0005", "TQT-R2-V30-0005", "TQT-R3-V30-0005", "TQT-R1-V30-0018", "TQT-R2-V30-0021", "TQT-R3-V30-0018")
        res = inv.emparejar_auto(self.lote, db_path=self.path)
        self.assertEqual([t["id_tarjeta_num"] for t in res["creadas"]], ["0005", "0018"])
        self.assertTrue(all(t["r3"] is None for t in res["creadas"]) and res["r3_asignadas"] == [])
        self.assertEqual(inv.listar_pcb(tipo="R3", estado_ciclo="DISPONIBLE", db_path=self.path)["total"], 2)

    def test_16c_r3_tardia_se_monta_en_su_tarjeta(self):
        self.disponibles("TQT-R1-V30-0007", "TQT-R2-V30-0007")
        inv.emparejar_auto(self.lote, db_path=self.path)
        self.disponibles("TQT-R3-V30-0007", "TQT-R3-V30-0099")                     # llegan después
        self.assertEqual(inv.sugerencias(self.lote, db_path=self.path)["r3_pendientes"], [])  # manual: nada automático
        self.assertEqual([x["id_tarjeta_num"] for x in inv.sugerencias(self.lote, r3_auto=True, db_path=self.path)["r3_pendientes"]], ["0007"])
        res = inv.emparejar_auto(self.lote, r3_auto=True, db_path=self.path)
        self.assertEqual(res["r3_asignadas"], [{"id_tarjeta_num": "0007", "r3": "TQT-R3-V30-0007"}])
        self.assertEqual(inv.listar_pcb(estado_ciclo="DISPONIBLE", db_path=self.path)["items"][0]["nombre"], "TQT-R3-V30-0099")

    def test_17_auto_con_series_reporta_omitidas(self):
        self.disponibles("TQT-R1-V30-0001", "TQT-R2-V30-0001", "TQT-R1-V30-0003")
        res = inv.emparejar_auto(self.lote, ["1", "0003", "0077"], db_path=self.path)
        self.assertEqual([t["id_tarjeta_num"] for t in res["creadas"]], ["0001"])
        self.assertEqual({o["serie"] for o in res["omitidas"]}, {"0003", "0077"})

    def test_18_tarjeta_impar_r1_0021_con_r2_0010(self):
        ids = self.disponibles("TQT-R1-V30-0021", "TQT-R2-V30-0010")
        t = inv.crear_tarjeta(self.lote, None, ids["TQT-R1-V30-0021"], ids["TQT-R2-V30-0010"], db_path=self.path)
        self.assertEqual((t["id_tarjeta_num"], t["nombre_r1"], t["nombre_r2"]), ("0021", "TQT-R1-V30-0021", "TQT-R2-V30-0010"))
        otra = self.disponibles("TQT-R1-V30-0099")["TQT-R1-V30-0099"]
        with self.assertRaises(ConflictoError):  # el número de tarjeta ya existe en el lote
            inv.crear_tarjeta(self.lote, "0021", otra, None, None, db_path=self.path)

    def test_19_reglas_de_asignacion(self):
        ids = self.disponibles("TQT-R1-V30-0001", "TQT-R2-V30-0001")
        t = inv.crear_tarjeta(self.lote, None, ids["TQT-R1-V30-0001"], None, db_path=self.path)
        with self.assertRaises(ValueError):   # R2 no cabe en la ranura R1
            inv.asignar_pcb(t["id"], "R1", ids["TQT-R2-V30-0001"], db_path=self.path)
        borrador = self.esc("TQT-R2-V30-0002")["pcb"]["id"]
        with self.assertRaises(ConflictoError) as ctx:  # sin confirmar la recepción no se puede usar
            inv.asignar_pcb(t["id"], "R2", borrador, db_path=self.path)
        self.assertIn("Confirma", str(ctx.exception))
        with self.assertRaises(ConflictoError):          # ya asignada a otra tarjeta
            inv.crear_tarjeta(self.lote, "0500", ids["TQT-R1-V30-0001"], None, db_path=self.path)
        with self.assertRaises(ValueError):
            inv.asignar_pcb(t["id"], "R9", None, db_path=self.path)
        with self.assertRaises(ValueError):
            inv.crear_tarjeta(self.lote, None, None, None, None, db_path=self.path)  # sin PCB

    # ------------------------------------------------------------------ fallas y reemplazos
    def test_20_reemplazo_de_pcb_fallada(self):
        t = crear_par(self.lote, num="0021", path=self.path)
        for etapa in ("soldadura", "programacion", "prueba_pcb"):
            db.set_prueba(t["id"], etapa, "OK", db_path=self.path)
        repuesto = self.disponibles("TQT-R2-V30-0010")["TQT-R2-V30-0010"]
        r = inv.marcar_falla(t["pcb_r2_id"], "no arranca", repuesto, operador="luis", db_path=self.path)

        self.assertEqual((r["pcb"]["estado_ciclo"], r["pcb"]["estado_pcb"], r["pcb"]["tarjeta_id"]), ("FALLA", "FALLA", None))
        nueva = r["tarjeta"]
        self.assertEqual((nueva["id_tarjeta_num"], nueva["nombre_r2"], nueva["r2"]["estado_ciclo"]), ("0021", "TQT-R2-V30-0010", "ASIGNADA"))
        self.assertIsNone(nueva["mac_r2"])                                   # la PCB nueva aún no se programa
        self.assertEqual(nueva["sin_mac"], ["R2"])
        # las pruebas se reinician: hay que volver a soldar/programar/probar
        self.assertEqual((nueva["soldadura"], nueva["estado_general"]), ("PENDIENTE", "PENDIENTE"))
        with db.get_db(self.path) as c:
            eventos = [f["evento"] for f in c.execute("SELECT evento FROM escaneos WHERE valor IN ('0021','TQT-R2-V30-0021') ORDER BY id")]
        self.assertIn("PCB_REEMPLAZO", eventos)
        self.assertIn("PCB_FALLA", eventos)

    def test_21_reemplazo_conservando_pruebas(self):
        t = crear_par(self.lote, path=self.path)
        db.set_prueba(t["id"], "soldadura", "OK", db_path=self.path)
        repuesto = self.disponibles("TQT-R1-V30-0900")["TQT-R1-V30-0900"]
        nueva = inv.asignar_pcb(t["id"], "R1", repuesto, marcar_falla=False, conservar_pruebas=True, db_path=self.path)
        self.assertEqual(nueva["soldadura"], "OK")
        self.assertEqual(inv.get_pcb(t["pcb_r1_id"], db_path=self.path)["estado_ciclo"], "DISPONIBLE")  # la anterior vuelve al inventario

    def test_22_falla_sin_tarjeta_y_liberar_ranura(self):
        suelta = self.disponibles("TQT-R1-V30-0001")["TQT-R1-V30-0001"]
        r = inv.marcar_falla(suelta, "golpeada", db_path=self.path)
        self.assertEqual((r["pcb"]["estado_ciclo"], r["tarjeta"]), ("FALLA", None))
        with self.assertRaises(ValueError):
            inv.marcar_falla(self.disponibles("TQT-R1-V30-0002")["TQT-R1-V30-0002"], "x", 9999, db_path=self.path)

        t = crear_par(self.lote, path=self.path)
        libre = inv.asignar_pcb(t["id"], "R2", None, db_path=self.path)   # sacar sin marcar falla
        self.assertFalse(libre["completa"])
        self.assertEqual(inv.get_pcb(t["pcb_r2_id"], db_path=self.path)["estado_ciclo"], "DISPONIBLE")

    def test_23_tarjeta_incompleta_no_puede_liberarse(self):
        ids = self.disponibles("TQT-R1-V30-0001")
        t = inv.crear_tarjeta(self.lote, None, ids["TQT-R1-V30-0001"], None, db_path=self.path)
        for etapa in ("soldadura", "programacion", "prueba_pcb", "integracion", "prueba_final"):
            t = db.set_prueba(t["id"], etapa, "OK", db_path=self.path)
        self.assertEqual(t["estado_general"], "EN PROCESO")   # las 5 OK pero sin R2: no LIBERADO
        self.assertEqual(db.get_stats(self.lote, db_path=self.path)["funcionales"], 0)

    def test_24_disolver_tarjeta(self):
        t = crear_par(self.lote, path=self.path, r3=True)
        db.set_prueba(t["id"], "soldadura", "OK", db_path=self.path)
        with self.assertRaises(ConflictoError):
            inv.disolver_tarjeta(t["id"], db_path=self.path)
        r = inv.disolver_tarjeta(t["id"], forzar=True, db_path=self.path)
        self.assertEqual(len(r["liberadas"]), 3)
        self.assertIsNone(db.get_tarjeta_by_id(t["id"], db_path=self.path))
        self.assertEqual(inv.get_pcb(t["pcb_r3_id"], db_path=self.path)["estado_ciclo"], "DISPONIBLE")
        with self.assertRaises(NoEncontradoError):
            inv.disolver_tarjeta(t["id"], db_path=self.path)

    def test_25_bitacora_de_todo(self):
        a = self.esc("TQT-R1-V30-0001", operador="ana")["pcb"]["id"]
        inv.editar_pcb(a, version="31", operador="ana", db_path=self.path)
        inv.confirmar_recepcion([a], operador="ana", db_path=self.path)
        inv.set_mac(a, mac_unica(), operador="ana", db_path=self.path)
        inv.eliminar_pcb(a, operador="ana", db_path=self.path)
        with db.get_db(self.path) as c:
            eventos = [f["evento"] for f in c.execute("SELECT evento FROM escaneos ORDER BY id")]
        for esperado in ("PCB_ALTA", "PCB_EDITADA", "RECEPCION_CONFIRMADA", "MAC_GUARDADA", "PCB_ELIMINADA"):
            self.assertIn(esperado, eventos)


if __name__ == "__main__":
    unittest.main()
