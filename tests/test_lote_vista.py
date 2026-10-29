"""Selected-lot scope is request-local, covers PCB/card identities and never falls back to another lot."""
import _aislamiento  # noqa: F401
import unittest
from concurrent.futures import ThreadPoolExecutor

from _aislamiento import cliente_sin_sesion, crear_par, nuevo_lote, num_unico, verificar_aislamiento
from app.config import settings
from app.database import db, inventario as inv
from app.main import app
from app.services import usuarios


class TestLoteVista(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        verificar_aislamiento()
        db.init_db()
        usuarios.sembrar(iteraciones=1000)
        cls.a, cls.b = nuevo_lote(activar=False), nuevo_lote(activar=False)
        cls.numero = num_unico()
        cls.ta = crear_par(cls.a['id'], num=cls.numero, version='30', r3=True)
        cls.tb = crear_par(cls.b['id'], num=cls.numero, version='20', r3=True)
        cls.only_b = crear_par(cls.b['id'])
        cls.loose = inv.registrar_manual('R2', '30', num_unico())['pcbs'][0]
        with db.transaction() as c:
            c.execute('UPDATE pcb_inventario SET lote_id=? WHERE id IN (?,?,?)',
                      (cls.a['id'], cls.ta['pcb_r1_id'], cls.ta['pcb_r2_id'], cls.ta['pcb_r3_id']))
            # Deliberately different receiving lot: assignment determines scope.
            c.execute('UPDATE pcb_inventario SET lote_id=? WHERE id=?', (cls.a['id'], cls.tb['pcb_r1_id']))
            c.execute('UPDATE pcb_inventario SET lote_id=? WHERE id=?', (cls.a['id'], cls.loose['id']))
            c.execute('UPDATE tarjetas_produccion SET fecha_finalizado=? WHERE id IN (?,?)',
                      ('2026-10-29', cls.ta['id'], cls.tb['id']))
        cls.client = cliente_sin_sesion(app)
        usuarios.limitador.reiniciar()
        r = cls.client.post('/api/auth/login', json={'email': 'developer4@skyguardian.mx', 'password': usuarios.CLAVE_INICIAL})
        assert r.status_code == 200, r.text

    def h(self, lot):
        return {'X-TQT-Lote': str(lot['id']) if isinstance(lot, dict) else str(lot)}

    def get(self, path, lot):
        r = self.client.get(path, headers=self.h(lot))
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def test_pcb_y_tarjetas_solo_del_lote_elegido(self):
        for lote, tarjeta in [(self.a, self.ta), (self.b, self.tb)]:
            cards = self.get('/api/tarjetas?search='+self.numero, lote)
            self.assertEqual([x['id'] for x in cards['items']], [tarjeta['id']])
            boards = self.get('/api/pcb?q='+self.numero, lote)
            self.assertEqual({p['id'] for p in boards['items']}, {tarjeta['pcb_r1_id'], tarjeta['pcb_r2_id'], tarjeta['pcb_r3_id']})
            self.assertTrue(all(p['lote_id'] == lote['id'] for p in boards['items']))

    def test_programacion_r1_r2_r3_por_tipo(self):
        for role in ['R1', 'R2', 'R3']:
            boards = self.get('/api/pcb?tipo='+role+'&q='+self.numero, self.a)
            self.assertEqual([p['id'] for p in boards['items']], [self.ta['pcb_'+role.lower()+'_id']])

    def test_todos_es_explicito_y_etiqueta_el_origen(self):
        cards = self.get('/api/tarjetas?search='+self.numero, 'all')
        self.assertEqual({p['id'] for p in cards['items']}, {self.ta['id'], self.tb['id']})
        self.assertTrue(all(p['lote_codigo'] for p in cards['items']))
        self.assertEqual(len(self.get('/api/pcb?q='+self.numero, 'all')['items']), 6)

    def test_numero_en_todos_no_elige_una_tarjeta_arbitraria(self):
        r = self.get('/api/consulta?codigo='+self.numero, 'all')
        self.assertIsNone(r['tarjeta'])
        self.assertEqual({t['id'] for t in r['coincidencias']}, {self.ta['id'], self.tb['id']})

    def test_consulta_numero_y_qr_y_mac_sin_mezcla(self):
        d = self.get('/api/consulta?codigo='+self.numero, self.a)
        self.assertEqual(d['tarjeta']['id'], self.ta['id'])
        for code in [self.tb['r1']['nombre'], self.tb['r1']['mac'], self.only_b['id_tarjeta_num']]:
            r = self.client.get('/api/consulta', params={'codigo': code}, headers=self.h(self.a))
            self.assertEqual(r.status_code, 404, r.text)

    def test_detalles_no_abren_tarjeta_de_otro_lote(self):
        r = self.client.get('/api/tarjetas/'+str(self.tb['id']), headers=self.h(self.a))
        self.assertEqual(r.status_code, 404)
        r = self.client.get('/api/pcb/'+str(self.tb['pcb_r1_id']), headers=self.h(self.a))
        self.assertEqual(r.status_code, 404)

    def test_edicion_cruzada_no_modifica_la_pcb(self):
        pid = self.tb['pcb_r1_id']
        before = inv.get_pcb(pid)
        r = self.client.put('/api/pcb/'+str(pid)+'/firmware', json={'firmware': '99.9'}, headers=self.h(self.a))
        self.assertEqual(r.status_code, 404, r.text)
        self.assertEqual(inv.get_pcb(pid), before)

    def test_preparacion_de_imagenes_no_acepta_otra_tarjeta(self):
        for path in ['/api/stm32/preview/', '/api/esp32/preview/', '/api/stm32/estado/']:
            r = self.client.get(path+str(self.tb['pcb_r1_id']), headers=self.h(self.a))
            self.assertIn(r.status_code, (400, 404), (path, r.text))

    def test_inventario_de_pruebas_rechaza_otro_lote(self):
        r = self.client.get('/api/validacion/tqt/inventory/'+str(self.tb['id']), headers=self.h(self.a))
        self.assertEqual(r.status_code, 400, r.text)

    def test_stats_y_reporte_solo_del_lote_y_sumados_en_todos(self):
        for lot in [self.a, self.b]:
            cards = self.get('/api/tarjetas', lot)['total']
            stats = self.get('/api/stats', lot)
            self.assertEqual(stats['total_tarjetas'], cards)
            self.assertEqual(stats['lote_id'], lot['id'])
            report = self.get('/api/reporte-dia?fecha=2026-10-29', lot)
            expected = self.ta['id'] if lot == self.a else self.tb['id']
            self.assertEqual([r['id'] for r in report['items']], [expected])
        stats = self.get('/api/stats', 'all')
        self.assertIsNone(stats['lote_id'])
        self.assertEqual(stats['total_tarjetas'], self.get('/api/tarjetas', 'all')['total'])

    def test_placas_sueltas_corresponden_a_su_recepcion(self):
        pa = self.get('/api/pcb?sin_tarjeta=true', self.a)['items']
        pb = self.get('/api/pcb?sin_tarjeta=true', self.b)['items']
        self.assertIn(self.loose['id'], [p['id'] for p in pa])
        self.assertNotIn(self.loose['id'], [p['id'] for p in pb])

    def test_header_invalido_o_lote_borrado_no_cae_al_activo(self):
        for header, status in [('0', 400), ('-1', 400), ('basura', 400), ('9999999999', 404)]:
            r = self.client.get('/api/pcb', headers=self.h(header))
            self.assertEqual(r.status_code, status)

    def test_parametro_no_puede_contradecir_la_seleccion(self):
        r = self.client.get('/api/tarjetas?lote_id='+str(self.b['id']), headers=self.h(self.a))
        self.assertEqual(r.status_code, 400)

    def test_vista_no_cambia_el_lote_activo_del_usuario(self):
        active = self.client.get('/api/status').json()['active_lote']
        self.get('/api/pcb', self.a)
        self.get('/api/pcb', self.b)
        self.get('/api/pcb', 'all')
        self.assertEqual(self.client.get('/api/status').json()['active_lote'], active)

    def test_peticiones_paralelas_no_contaminan_el_contexto(self):
        def query(n):
            lot, card = (self.a, self.ta) if n % 2 else (self.b, self.tb)
            result = self.get('/api/tarjetas?search='+self.numero, lot)
            return [t['id'] for t in result['items']] == [card['id']]
        with ThreadPoolExecutor(max_workers=4) as pool:
            self.assertTrue(all(pool.map(query, range(12))))

    def test_mover_de_lote_sigue_siendo_una_accion_explicita(self):
        p = inv.registrar_manual('R3', '30', num_unico())['pcbs'][0]
        with db.transaction() as c:
            c.execute('UPDATE pcb_inventario SET lote_id=? WHERE id=?', (self.a['id'], p['id']))
        r = self.client.post('/api/pcb/mover-lote', json={'ids': [p['id']], 'lote_id': self.b['id']}, headers=self.h(self.a))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()['pcbs'][0]['lote_id'], self.b['id'])
        self.assertNotIn(p['id'], [p['id'] for p in self.get('/api/pcb', self.a)['items']])

    def test_base_generica_no_recibe_en_lote_ajeno_y_todos_no_inventa_destino(self):
        num = num_unico()
        r = self.client.post('/api/pcb/manual', json={'tipo': 'R3', 'version': '30', 'serie': num}, headers=self.h(self.b))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()['pcbs'][0]['recibida_lote_id'], self.b['id'])
        num = num_unico()
        r = self.client.post('/api/pcb/manual', json={'tipo': 'R3', 'version': '30', 'serie': num}, headers=self.h('all'))
        self.assertEqual(r.status_code, 400, r.text)
        self.assertIn('lote concreto', r.json()['detail'])

    def test_excel_mensual_en_todos_no_exporta_el_activo_por_accidente(self):
        for path in ['/api/export/excel', '/api/admin/export/excel']:
            r = self.client.get(path, headers=self.h('all'))
            self.assertEqual(r.status_code, 400, r.text)

    def test_historial_y_contadores_de_validacion_son_del_lote(self):
        from app.routers import validacion
        validacion.init()
        with db.transaction() as c:
            for t in [self.ta, self.tb]:
                c.execute("INSERT INTO validaciones_ble(pcb_id,tarjeta_id,dispositivo,comando,resultado) VALUES(?,?,?,'PPON','ok')",
                          (t['pcb_r1_id'], t['id'], t['r1']['nombre']))
        for lot, t in [(self.a, self.ta), (self.b, self.tb)]:
            rows = self.get('/api/validacion/registros', lot)['items']
            self.assertTrue(rows)
            self.assertTrue(all(r['tarjeta']['id'] == t['id'] for r in rows))
            summary = self.get('/api/validacion/resumen', lot)
            self.assertEqual(summary['ultima']['tarjeta']['id'], t['id'])

    def test_descarga_de_reporte_conserva_scope_sin_cabecera_fetch(self):
        import io
        from openpyxl import load_workbook
        r = self.client.get('/api/reporte-dia/excel', params={'fecha': '2026-10-29', 'vista_lote': self.a['id']})
        self.assertEqual(r.status_code, 200, r.text[:100] if 'json' in r.headers.get('content-type', '') else r.status_code)
        wb = load_workbook(io.BytesIO(r.content), data_only=False)
        text = '\n'.join(str(c.value) for ws in wb for row in ws for c in row if c.value is not None)
        self.assertIn(self.ta['r1']['nombre'], text)
        self.assertNotIn(self.tb['r1']['nombre'], text)

    def test_scope_active_se_resuelve_por_cuenta_sin_modificar_el_global(self):
        original = self.client.get('/api/status').json()['active_lote']
        try:
            self.client.post('/api/lotes/'+str(self.b['id'])+'/activar')
            result = self.get('/api/tarjetas?search='+self.numero, 'active')
            self.assertEqual([t['id'] for t in result['items']], [self.tb['id']])
        finally:
            self.client.post('/api/lotes/'+str(original['id'])+'/activar')

    def test_todos_no_mezcla_placas_sueltas_de_distintos_lotes(self):
        num = num_unico()
        for version, lot in [('30', self.a), ('20', self.b)]:
            p = inv.registrar_manual('R2', version, num)['pcbs'][0]
            with db.transaction() as c:
                c.execute('UPDATE pcb_inventario SET lote_id=? WHERE id=?', (lot['id'], p['id']))
        r = self.get('/api/consulta?codigo='+num, 'all')
        self.assertIsNone(r.get('serie'))
        self.assertEqual({t['lote_id'] for t in r['coincidencias']}, {self.a['id'], self.b['id']})

    def test_modulo_no_autorizado_se_rechaza_antes_de_validar_lotes(self):
        from unittest.mock import patch
        with patch('app.main.modulos_cat.puede', return_value=False):
            for scope in [str(self.a['id']), '9999999999', 'invalido', 'all']:
                r = self.client.get('/api/pcb', headers=self.h(scope))
                self.assertEqual(r.status_code, 403)

    def test_campanas_tarjetas_historial_y_acciones_respetan_lote(self):
        import secrets
        from app.services import pruebas_auto as pa, stm32_programming as stm
        pa.init()
        station = stm.station_create('QA lotes', 'developer4@skyguardian.mx')
        campaigns = []
        with db.transaction() as c:
            for card in [self.ta, self.tb]:
                cid = secrets.token_hex(12)
                campaigns.append(cid)
                c.execute('INSERT INTO tqt_resistencia VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                          (cid, 'QA sin ejecución', '4.4', station['id'], card['id'], 1, 0, 1,
                           'terminada', None, 'developer4@skyguardian.mx', 0, 0))
        try:
            for lot, card, cid in [(self.a, self.ta, campaigns[0]), (self.b, self.tb, campaigns[1])]:
                self.assertEqual([t['id'] for t in self.get('/api/pruebas-auto/tarjetas?q='+self.numero, lot)], [card['id']])
                listing = self.get('/api/pruebas-auto/campanas', lot)
                self.assertIn(cid, [x['id'] for x in listing])
                self.assertEqual({x['tarjeta']['lote_id'] for x in listing}, {lot['id']})
            self.assertEqual(len(self.get('/api/pruebas-auto/tarjetas?q='+self.numero, 'all')), 2)
            self.assertGreaterEqual(len(self.get('/api/pruebas-auto/campanas', 'all')), 2)
            outside = '/api/pruebas-auto/campanas/'+campaigns[1]
            for suffix in ['', '/vivo', '/log.txt']:
                self.assertEqual(self.client.get(outside+suffix, headers=self.h(self.a)).status_code, 400)
            self.assertEqual(self.client.delete(outside, headers=self.h(self.a)).status_code, 400)
            self.assertEqual(self.client.post(outside+'/accion', json={'accion':'detener'}, headers=self.h(self.a)).status_code, 400)
            self.get(outside, self.b)  # rejected operations left it intact
        finally:
            with db.transaction() as c:
                c.executemany('DELETE FROM tqt_resistencia WHERE id=?', [(cid,) for cid in campaigns])

    def test_admin_resumen_y_selecciones_no_cruzan_lotes(self):
        from app.database import admin_ops
        token = db.LOTE_VISTA.set(self.a['id'])
        try:
            r = admin_ops.resumen()
            self.assertEqual([l['id'] for l in r['lotes']], [self.a['id']])
            self.assertEqual(r['totales']['tarjetas'], 1)
            self.assertEqual(admin_ops.verificar_tarjetas([self.ta['id'], self.tb['id']]), [self.ta['id']])
            self.assertEqual(admin_ops.verificar_pcb([self.ta['pcb_r1_id'], self.tb['pcb_r1_id']]), [self.ta['pcb_r1_id']])
        finally:
            db.LOTE_VISTA.reset(token)


if __name__ == '__main__':
    unittest.main()
