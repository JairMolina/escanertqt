"""Synthetic 0065 in two lots for Playwright; only the dedicated Docker QA DB."""
import json
import os
from app.config import settings
from app.database import db, inventario as inv

assert os.environ.get('TQT_QA_LOTES') == '1' and str(settings.DB_PATH) == '/data/qa.db', 'Solo el volumen QA aislado con TQT_QA_LOTES=1'
db.init_db()
result = []
for code, month, ver in [('QA-2026-09', 9, '30'), ('QA-2026-10', 10, '20')]:
    lote = db.get_lote_by_codigo(code) or db.create_lote(code, month, 2026)
    card = db.get_tarjeta_por_numero(lote['id'], '0065')
    if not card:
        ids = {}
        with db.transaction() as c:
            for role in ['R1', 'R2', 'R3']:
                p = inv.registrar_manual(role, ver, '0065', conn=c)['pcbs'][0]
                ids[role] = p['id']
                c.execute('UPDATE pcb_inventario SET lote_id=? WHERE id=?', (lote['id'], p['id']))
            inv.confirmar_recepcion(list(ids.values()), conn=c)
            card = inv.crear_tarjeta(lote['id'], '0065', ids['R1'], ids['R2'], ids['R3'], conn=c)
            for n, role in enumerate(['R1', 'R2']):
                inv.guardar_programacion(ids[role], f'02:00:00:00:{month:02X}:{n+1:02X}', '4.4' if role == 'R1' else '4.2', conn=c)
            inv.set_firmware(ids['R3'], '1.1', conn=c)
    with db.transaction() as c:
        for role, num in [('R2', '0066'), ('R3', '0066')]:
            row = c.execute('SELECT id FROM pcb_inventario WHERE tipo=? AND version=? AND serie=?', (role, ver, num)).fetchone()
            p = {'id': row[0]} if row else inv.registrar_manual(role, ver, num, conn=c)['pcbs'][0]
            c.execute('UPDATE pcb_inventario SET lote_id=? WHERE id=?', (lote['id'], p['id']))
        c.execute("UPDATE tarjetas_produccion SET fecha_finalizado='2026-10-29',fecha_real='2026-10-29' WHERE id=?", (card['id'],))
    result.append({'lote': lote, 'tarjeta_id': card['id']})
db.set_active_lote(result[0]['lote']['id'])
with db.transaction() as c:
    c.execute("UPDATE lotes_mensuales SET codigo_lote='QA-INICIAL',mes=1,anio=2025,fecha_inicio='2025-01-01' "
              "WHERE id=1 AND NOT EXISTS(SELECT 1 FROM tarjetas_produccion WHERE lote_id=1)")
extra = db.get_tarjeta_por_numero(result[1]['lote']['id'], '0064')
if not extra:
    with db.transaction() as c:
        ids = {r: inv.registrar_manual(r, '20', '0064', conn=c)['pcbs'][0]['id'] for r in ['R1','R2','R3']}
        for pid in ids.values(): c.execute('UPDATE pcb_inventario SET lote_id=? WHERE id=?', (result[1]['lote']['id'], pid))
        inv.confirmar_recepcion(list(ids.values()), conn=c)
        extra = inv.crear_tarjeta(result[1]['lote']['id'], '0064', ids['R1'], ids['R2'], ids['R3'], conn=c)
print(json.dumps(result))
