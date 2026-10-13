"""Informes de fabricación TQT: HTML imprimible, historial CSV y cotejo opcional.

Sin servicios externos ni acceso a bases de datos. Los archivos se generan localmente.
"""
from __future__ import annotations
import csv
import html
import io
import json
import re
from datetime import datetime
from pathlib import Path
from .protocol import normalize_mac

INVENTORY_COLUMNS = ('id', 'mac_r1', 'mac_r2', 'nombre', 'observaciones')
ALIASES = {
    'id': ('id', 'id_r1', 'numero_de_tarjeta', 'numero_tarjeta', 'tarjeta', 'numero', 'serial', 'numero_serie'),
    'mac_r1': ('mac_r1', 'mac_ble_r1', 'macr1', 'mac'),
    'mac_r2': ('mac_r2', 'mac_ble_r2', 'macr2', 'macr'),
    'nombre': ('nombre', 'name', 'modelo'),
    'observaciones': ('observaciones', 'notas', 'comentarios'),
}


def _key(value: str) -> str:
    import unicodedata
    s = unicodedata.normalize('NFKD', str(value)).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+', '_', s).strip('_')


def _id(value: str) -> str:
    s = str(value or '').strip()
    if re.fullmatch(r'\d+', s):
        return str(int(s))
    return s.upper()


def _mac_valid(value: str) -> bool:
    return bool(re.fullmatch(r'[0-9A-F]{12}', normalize_mac(value)))


def load_inventory(path: str | Path) -> dict[str, dict]:
    """CSV UTF-8 BOM or normal; exige IDs únicos y MAC bien formada si existe."""
    result = {}
    with Path(path).open('r', encoding='utf-8-sig', newline='') as f:
        sample = f.read(4096)
        f.seek(0)
        # Se detecta el separador sin alterar la configuración global de csv.
        first_line = sample.splitlines()[0] if sample.splitlines() else ''
        if first_line.count(';') > first_line.count(','):
            reader = csv.DictReader(f, delimiter=';')
        else:
            reader = csv.DictReader(f, delimiter=',')
        headers = {_key(h): h for h in (reader.fieldnames or []) if h}
        mapping = {standard: next((headers[a] for a in names if a in headers), None)
                   for standard, names in ALIASES.items()}
        if not mapping['id']:
            raise ValueError('El CSV del inventario necesita columna ID, tarjeta o numero_tarjeta')
        if not mapping['mac_r1'] and not mapping['mac_r2']:
            raise ValueError('El CSV necesita una columna MAC / mac_r1 o MACR / mac_r2')
        for rowno, row in enumerate(reader, 2):
            key = _id(row.get(mapping['id']) or '')
            if not key: continue
            if key in result: raise ValueError(f'ID duplicado en inventario (fila {rowno}): {key}')
            record = {k: str(row.get(header) or '').strip() if header else '' for k, header in mapping.items()}
            for field in ('mac_r1', 'mac_r2'):
                if record[field] and not _mac_valid(record[field]):
                    raise ValueError(f'MAC inválida en fila {rowno}, {field}: {record[field]}')
            result[key] = record
    if not result: raise ValueError('CSV de inventario sin tarjetas')
    return result


def _hardware_id_from_name(value: str) -> str | None:
    """Infiere el numero fisico solamente de nombres TQT con sufijo inequívoco.

    TQT_R1_V3_0_0036 y TQT-R1-V30-0036 => 36. Un ID secuencial
    de la hoja no se debe confundir con el numero impreso en la tarjeta.
    """
    name = str(value or '').strip()
    if not re.search(r'(?i)TQT[-_]R1[-_]', name):
        return None
    hit = re.search(r'[-_](\d{4,8})$', name)
    return _id(hit.group(1)) if hit else None


def compare_inventory(records: dict | None, card_id: str, reported_r1: str, seen_r1: str,
                      reported_r2: str, seen_r2: str) -> dict:
    """No se da por cotejada una MAC si el campo en CSV está vacío."""
    if records is None:
        return {'state': 'no_configurado', 'detail': 'No se cargó inventario local', 'record': None,
                'r1': 'no_verificado', 'r2': 'no_verificado'}
    key = _id(card_id)
    # En inventarios existentes, ID puede ser el consecutivo de la hoja (p.ej. 2),
    # mientras el numero fisico 0036 está al final de Nombre.
    matches = [(k, r) for k, r in records.items()
               if _hardware_id_from_name(r.get('nombre', '')) == key]
    direct = records.get(key)
    if len(matches) > 1 or (matches and direct is not None and direct is not matches[0][1]):
        return {'state': 'ambiguo', 'detail': f'ID hardware {card_id} tiene filas en conflicto',
                'record': None, 'r1': 'no_verificado', 'r2': 'no_verificado'}
    if matches:
        csv_key, record = matches[0]
        matched_by = 'nombre' if csv_key != key else 'id_y_nombre'
    else:
        record, matched_by, csv_key = direct, 'id', key
        if record and _hardware_id_from_name(record.get('nombre', '')) not in (None, key):
            return {'state': 'ambiguo', 'detail': f'ID CSV {card_id} contradice el numero fisico de Nombre',
                    'record': None, 'r1': 'no_verificado', 'r2': 'no_verificado'}
    if record is None:
        return {'state': 'sin_registro', 'detail': f'ID hardware {card_id} no aparece en inventario por ID ni Nombre',
                'record': None, 'r1': 'no_verificado', 'r2': 'no_verificado'}
    outcome = {}
    for short, expected, reported, observed in (
        ('r1', record['mac_r1'], reported_r1, seen_r1),
        ('r2', record['mac_r2'], reported_r2, seen_r2)):
        if not expected:
            outcome[short] = 'no_verificado'
        elif (normalize_mac(expected) == normalize_mac(reported) == normalize_mac(observed)
              and _mac_valid(expected)):
            outcome[short] = 'coincide'
        else:
            outcome[short] = 'no_coincide'
    if 'no_coincide' in outcome.values(): state = 'no_coincide'
    elif all(v == 'coincide' for v in outcome.values()): state = 'coincide'
    else: state = 'incompleto'
    method = f' (localizada por Nombre; ID de fila CSV={csv_key})' if matched_by == 'nombre' else ''
    return {'state': state, 'detail': f'Inventario: R1 {outcome["r1"]}, R2 {outcome["r2"]}{method}',
            'record': record, 'matched_by': matched_by, 'csv_id':csv_key, **outcome}


def communicate(health: dict) -> dict:
    total = int(health.get('frames', 0) or 0)
    bad = int(health.get('corrupt_frames', 0) or 0)
    partial = int(health.get('partial_warnings', 0) or 0)
    retries = int(health.get('retries', 0) or 0)
    ack_errors = int(health.get('ack_errors', 0) or 0)
    # No llamamos a una cabecera dañada "S29 dañado": puede ser otra clase de reporte.
    if partial or retries or ack_errors: state = 'no_verificable'
    elif bad: state = 'advertencias'
    else: state = 'limpia'
    return {'state': state, 'received_lines': total, 'corrupt_lines': bad,
            'partial_warnings': partial, 'retries': retries, 'ack_errors': ack_errors,
            'corrupt_percent': round(100*bad/total, 1) if total else 0.0,
            'note': 'Las líneas dañadas no se usan como evidencia funcional. No se ha demostrado su causa física.'}


def build_warnings(health: dict, prior: list[str]) -> list[str]:
    notes = list(dict.fromkeys(prior))
    bad = int(health.get('corrupt_frames', 0) or 0)
    total = int(health.get('frames', 0) or 0)
    if bad:
        notes.append(f'Comunicación: {bad} líneas RX con cabecera/bytes ilegibles de {total} '
                     f'({round(100*bad/total, 1) if total else 0}%). Excluidas como evidencia; revisar canal UART y trazas HEX.')
    if health.get('retries', 0): notes.append(f'Comunicación: {health["retries"]} reintentos de ACK observados.')
    if health.get('partial_warnings', 0): notes.append(f'Comunicación: {health["partial_warnings"]} tramas/fragments incompletos.')
    if health.get('ack_errors', 0): notes.append(f'Comunicación: {health["ack_errors"]} errores de escritura de ACK.')
    return notes


def report_html(report: dict) -> str:
    def e(v): return html.escape(str('—' if v is None or v == '' else v), quote=True)
    def tr(label, value): return '<tr><th>'+e(label)+'</th><td>'+e(value)+'</td></tr>'
    steps = report.get('steps', [])
    rows = ''.join('<tr><td>'+str(i+1)+'</td><td>'+e(x.get('name'))+'</td><td><span class="state '+e(x.get('state'))+'">'+e(x.get('state'))+'</span></td><td>'+e(x.get('detail'))+'</td><td>'+e(x.get('duration_s'))+'</td></tr>' for i,x in enumerate(steps))
    checks = report.get('inventory_check', {})
    inv_note = ('Cotejo CSV realizado contra las MAC de firmware y BLE; el campo Localizada por indica la procedencia del identificador.'
                if checks.get('state') not in ('no_configurado', 'sin_registro', None) else
                'Sin registro coincidente de inventario: las MAC BLE pueden coincidir entre sí, pero no quedan cotejadas contra CSV.')
    health = report.get('serial_health', {})
    quality = report.get('communication_quality', {})
    timing = report.get('serial_timing', {})
    warnings = ''.join('<li>'+e(w)+'</li>' for w in report.get('warnings', [])) or '<li>No se registraron advertencias.</li>'
    root = checks.get('record') or {}
    output = f'''<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>TQT · {e(report.get('card'))}</title><style>
:root{{color-scheme:light}}*{{box-sizing:border-box}}body{{margin:0;background:#eef2f7;font:14px/1.55 system-ui,Segoe UI,Arial,sans-serif;color:#172235}}main{{max-width:1060px;margin:32px auto;background:white;padding:38px;box-shadow:0 8px 40px #22314715;border-radius:16px}}h1{{font-size:26px;margin:0}}h2{{margin:24px 0 8px;font-size:17px;border-bottom:1px solid #dce4eb;padding-bottom:7px}}.eyebrow{{color:#64748b;font-weight:700;letter-spacing:.08em;font-size:11px}}.summary{{display:flex;gap:12px;align-items:center;justify-content:space-between;border-bottom:3px solid #18334c;padding-bottom:16px}}.chip{{font-weight:700;padding:9px 13px;border-radius:50px;background:#e8f5eb;color:#166534}}.chip.bad{{background:#fee2e2;color:#991b1b}}.chip.warn{{background:#fef3c7;color:#92400e}}table{{border-collapse:collapse;width:100%;font-size:12px;margin:10px 0}}th,td{{text-align:left;border-bottom:1px solid #e1e9ef;padding:9px 10px;vertical-align:top;word-break:break-word}}th{{width:185px;background:#f8fafc}}.steps th{{width:auto;background:#f1f5f9}}.state{{text-transform:uppercase;font-size:10px;letter-spacing:.03em;font-weight:700}}.state.aprobado{{color:#15803d}}.state.fallido{{color:#be123c}}.state.no_verificado{{color:#a16207}}.cols{{display:grid;grid-template-columns:1fr 1fr;gap:20px}}.sub{{color:#64748b;font-size:12px}}ul{{padding-left:20px}}li{{margin:6px 0}}footer{{margin-top:28px;padding-top:12px;border-top:1px solid #dce4eb;color:#64748b;font-size:11px}}@media(max-width:700px){{main{{margin:0;padding:18px;border-radius:0}}.cols{{grid-template-columns:1fr}}.summary{{align-items:flex-start;flex-direction:column}}}}@media print{{body{{background:#fff}}main{{margin:0;padding:0;max-width:none;box-shadow:none}}@page{{size:A4;margin:15mm}}tr{{break-inside:avoid}}}}
</style></head><body><main><header class="summary"><div><div class="eyebrow">CONTROL DE FABRICACIÓN · TQT TEST STATION v0.6.3</div><h1>{e(report.get('card'))}</h1><div class="sub">{e(report.get('date'))} · {e(report.get('serial_port'))} · Documento local, sin firma de certificación externa</div></div><div class="chip {'bad' if report.get('result')=='fallido' else 'warn' if report.get('warnings') or report.get('result')!='aprobado' else ''}">{e(report.get('result')).upper()}{' · CON AVISOS' if report.get('warnings') and report.get('result')=='aprobado' else ''}</div></header>
<div class="cols"><section><h2>Identidad</h2><table>{tr('R1 reportada (MAC)',report.get('reported_mac'))}{tr('R1 vista por BLE',report.get('r1_ble_address'))}{tr('R2 reportada (MACR)',report.get('reported_mac_r2'))}{tr('R2 vista por BLE',report.get('r2_ble_address'))}{tr('FW / HW',str(report.get('firmware') or '—')+' / '+str(report.get('hardware') or '—'))}{tr('Posición final',report.get('ending_position'))}</table></section><section><h2>Trazabilidad de inventario</h2><table>{tr('Estado de cotejo',checks.get('state', 'no_configurado'))}{tr('Localizada por',checks.get('matched_by','—'))}{tr('ID de fila CSV',checks.get('csv_id','—'))}{tr('MAC R1 vs inventario',checks.get('r1','no_verificado'))}{tr('MAC R2 vs inventario',checks.get('r2','no_verificado'))}{tr('MAC R1 en CSV',root.get('mac_r1'))}{tr('MAC R2 en CSV',root.get('mac_r2'))}{tr('Nombre en CSV',root.get('nombre'))}</table><p class="sub">{e(inv_note)}</p></section></div>
<section><h2>Estado de comunicación</h2><table>{tr('Calidad',quality.get('state'))}{tr('Tramas recibidas',health.get('frames',0))}{tr('Cabeceras o bytes RX dañados',health.get('corrupt_frames',0))}{tr('Proporción de líneas dañadas',str(quality.get('corrupt_percent',0))+' %')}{tr('Reintentos de ACK',health.get('retries',0))}{tr('Parciales / fragmentos',health.get('partial_warnings',0))}{tr('Errores de escritura ACK',health.get('ack_errors',0))}{tr('Espera ACK configurada',str(timing.get('ack_delay_ms','—'))+' ms')}{tr('Espera adicional Status',str(timing.get('status_quiet_ms',0))+' ms')}{tr('Guardia de canal',str(timing.get('command_quiet_ms','—'))+' ms')}</table><p class="sub">La causa de RX dañado no se puede establecer solamente con este informe. Consultar HEX del registro para diagnóstico.</p></section>
<section><h2>Secuencia verificada ({sum(x.get('state')=='aprobado' for x in steps)}/{len(steps)})</h2><table class="steps"><thead><tr><th>#</th><th>Prueba</th><th>Resultado</th><th>Detalle de evidencia</th><th>Duración (s)</th></tr></thead><tbody>{rows}</tbody></table></section>
<section><h2>Advertencias y observaciones</h2><ul>{warnings}</ul>{'<p><strong>Motivo:</strong> '+e(report.get('issue'))+'</p>' if report.get('issue') else ''}</section>
<footer>Registro generado automáticamente. El archivo JSON contiene los datos estructurados y el LOG conserva mensajes RX/TX. Los ensayos se basan en el estado informado por R1; no sustituyen mediciones eléctricas externas. Puede imprimirse mediante Ctrl+P.</footer></main></body></html>'''
    return output


def append_history(folder: Path, report: dict, json_filename: str, html_filename: str) -> None:
    path = folder / 'historial_pruebas.csv'
    columns = ['fecha','tarjeta','resultado','pasos_aprobados','pasos_totales','calidad_comunicacion',
               'rx_corruptas','reintentos_ack','advertencias','inventario','mac_r1','mac_r2',
               'posicion_final','motivo','json','html']
    health = report.get('serial_health', {})
    row = {'fecha':report.get('date'),'tarjeta':report.get('card'),'resultado':report.get('result'),
           'pasos_aprobados':sum(s.get('state')=='aprobado' for s in report.get('steps',[])),
           'pasos_totales':len(report.get('steps',[])),
           'calidad_comunicacion':report.get('communication_quality',{}).get('state'),
           'rx_corruptas':health.get('corrupt_frames',0),'reintentos_ack':health.get('retries',0),
           'advertencias':len(report.get('warnings',[])),
           'inventario':report.get('inventory_check',{}).get('state'),
           'mac_r1':report.get('reported_mac'),'mac_r2':report.get('reported_mac_r2'),
           'posicion_final':report.get('ending_position'),'motivo':report.get('issue'),
           'json':json_filename,'html':html_filename}
    # Evitar evaluación de fórmulas al abrir el historial en Excel.
    row = {k: ("'" + v if isinstance(v, str) and v.lstrip().startswith(('=', '+', '-', '@'))
               else v) for k,v in row.items()}
    with path.open('a', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        if f.tell() == 0: writer.writeheader()
        writer.writerow(row)
