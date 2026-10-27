/* Pure SVG reading layout adapted from the supplied Diagrama_TQT.html. */
(function(){'use strict';
function renderHarnessSVG({
  group = {}, wires = [], selectedId = null, checkedIds = [],
  hw = '', showLabels = true, filterIds = null
} = {}) {
  const esc = value => String(value == null ? '' : value).replace(/[&<>"']/g, c => ({
    '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'
  }[c]));
  const safe = value => String(value || 'group').replace(/[^a-zA-Z0-9_-]/g, '-');
  const prefix = 'tqt-harness-' + safe(group.id) + '-' + safe(hw);
  const checked = new Set(checkedIds || []);
  const matches = filterIds == null ? null : new Set(filterIds);
  const rows = Array.isArray(wires) ? wires : [];
  const wrap = (value, max, count = 2) => {
    const words = String(value == null ? '' : value).trim().split(/\s+/);
    const lines = [];
    let line = '';
    for (const word of words) {
      if (line && (line + ' ' + word).length > max) {
        lines.push(line);
        line = word;
      } else line += (line ? ' ' : '') + word;
    }
    if (line) lines.push(line);
    if (lines.length > count) {
      lines[count - 1] = lines.slice(count - 1).join(' ');
      if (lines[count - 1].length > max + 8) lines[count - 1] = lines[count - 1].slice(0, max + 5).trimEnd() + '…';
      return lines.slice(0, count);
    }
    return lines;
  };
  const textLines = (lines, x, y, gap, attrs = '') => '<text x="' + x + '" y="' + y + '" ' + attrs + '>' +
    lines.map((line, i) => '<tspan x="' + x + '" dy="' + (i ? gap : 0) + '">' + esc(line) + '</tspan>').join('') + '</text>';
  const identity = group.terminalLabel || group.title || 'CONEXIONES';
  const iconKey = String(group.icon || group.id || '').toLowerCase();
  let componentIcon;
  if (/motor/.test(iconKey)) {
    componentIcon = '<rect x="102" y="202" width="66" height="49" rx="12"/><path d="M168 216h15v21h-15M101 214H91m10 24H91M115 202v49m39-49v49"/><path d="M123 218c9-11 20 10 29-1m-29 16c9-11 20 10 29-1"/>';
  } else if (/sensor/.test(iconKey)) {
    componentIcon = '<rect x="115" y="202" width="40" height="51" rx="10"/><path d="M135 253v14m-20-24h40M104 206c-11 12-11 29 0 41m63-41c11 12 11 29 0 41M95 197c-17 18-17 42 0 60m81-60c17 18 17 42 0 60"/>';
  } else if (/power|alim|supply/.test(iconKey)) {
    componentIcon = '<rect x="106" y="202" width="65" height="51" rx="10"/><path d="M116 225h14m-7-7v14m23-7h14M127 253v11m23-11v11"/>';
  } else if (/signal|gps|radio|link/.test(iconKey)) {
    componentIcon = '<rect x="108" y="207" width="65" height="48" rx="10"/><path d="M121 220h39m-39 10h25m-25 10h14m19-33v-13m-8 4a10 10 0 0 1 16 0m-22-7a19 19 0 0 1 28 0"/>';
  } else {
    componentIcon = '<rect x="110" y="203" width="57" height="57" rx="11"/><rect x="123" y="216" width="31" height="31" rx="6"/><path d="M122 195v8m16-8v8m16-8v8m-32 57v8m16-8v8m16-8v8m-52-53h8m-8 16h8m-8 16h8m57-32h8m-8 16h8m-8 16h8"/>';
  }
  const terminalLines = wrap(identity, 18, 2);
  const terminalY = terminalLines.length > 1 ? 300 : 311;
  const groupSubtitle = wrap(group.subtitle || 'Selecciona un cable', 23, 2);
  const count = rows.length;
  const top = count >= 5 ? 126 : count === 4 ? 144 : count === 3 ? 166 : 208;
  const bottom = count >= 5 ? 394 : count === 4 ? 384 : count === 3 ? 374 : 326;
  const ys = rows.map((_, i) => count === 1 ? 266 : top + i * (bottom - top) / Math.max(1, count - 1));
  const header = '<svg xmlns="http://www.w3.org/2000/svg" id="' + prefix + '" class="harness-diagram" viewBox="0 0 900 510" width="900" height="510" role="group" aria-labelledby="' + prefix + '-title ' + prefix + '-desc" style="display:block;width:100%;height:auto;overflow:visible;font-family:var(--font-ui,Arial,sans-serif)">' +
    '<title id="' + prefix + '-title">' + esc(group.title || identity) + ' · ' + esc(hw) + '</title>' +
    '<desc id="' + prefix + '-desc">Esquema interactivo de ' + count + ' conexiones. Selecciona un cable para consultar su ficha. La distribución no representa posiciones ni números de pin.</desc>' +
    '<defs><pattern id="' + prefix + '-grid" width="24" height="24" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r=".8" fill="#293348" opacity=".53"/></pattern>' +
    '<linearGradient id="' + prefix + '-panel" x1="0" x2="1" y1="0" y2="1"><stop stop-color="#182238"/><stop offset="1" stop-color="#101827"/></linearGradient>' +
    '<filter id="' + prefix + '-glow" x="-30%" y="-120%" width="160%" height="340%"><feGaussianBlur stdDeviation="3"/></filter></defs>' +
    '<style>#' + prefix + ' [data-wire]{cursor:pointer;outline:none}#' + prefix + ' [data-wire] .target-card{transition:stroke .16s,fill .16s}#' + prefix + ' [data-wire]:hover .target-card,#' + prefix + ' [data-wire]:focus-visible .target-card{stroke:#efbc58;fill:#20283a}#' + prefix + ' [data-wire]:focus-visible .focus-ring{opacity:1}#' + prefix + ' [data-wire]:hover .wire-name{fill:#fff}</style>' +
    '<rect x="1" y="1" width="898" height="508" rx="16" fill="#0d1423"/>' +
    '<rect x="1" y="1" width="898" height="508" rx="16" fill="url(#' + prefix + '-grid)"/>' +
    '<path d="M29 49h842" stroke="#253048"/>' +
    '<g fill="none" stroke="#d5a646" stroke-width="1.5"><path d="M31 24h8v8h-8zM43 24h8v8h-8zM31 36h8m4 0h8"/></g>' +
    '<text x="63" y="32" fill="#a3b0c6" font-size="10" font-weight="600" letter-spacing="1.6">ESQUEMA DE CONEXIONES</text>' +
    '<rect x="776" y="16" width="95" height="24" rx="6" fill="#dda637" fill-opacity=".09" stroke="#d5a646" stroke-opacity=".35"/>' +
    '<text x="823.5" y="32" text-anchor="middle" fill="#e4b04b" font-size="11" font-weight="700">' + esc(String(hw).replace(/^HW\s*/i, 'HW ')) + '</text>';
  const connector = '<g aria-hidden="true">' +
    '<rect x="51" y="94" width="214" height="341" rx="16" fill="url(#' + prefix + '-panel)" stroke="#314159" stroke-width="1.3"/>' +
    '<path d="M73 115h160M73 413h160" stroke="#334257" opacity=".65"/>' +
    '<circle cx="73" cy="115" r="3" fill="#334157"/><circle cx="245" cy="115" r="3" fill="#334157"/>' +
    '<circle cx="73" cy="414" r="3" fill="#334157"/><circle cx="245" cy="414" r="3" fill="#334157"/>' +
    '<text x="76" y="147" fill="#71839e" font-size="9" font-weight="600" letter-spacing="1.5">GRUPO DE CABLEADO</text>' +
    '<g fill="none" stroke="#c5a25c" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" transform="translate(6 -18)">' + componentIcon + '</g>' +
    textLines(terminalLines, 158, terminalY, 24, 'text-anchor="middle" fill="#eef2f8" font-size="23" font-weight="700"') +
    textLines(groupSubtitle, 158, terminalY + terminalLines.length * 24 + 8, 15, 'text-anchor="middle" fill="#8c9bb0" font-size="10"') +
    '<text x="158" y="398" text-anchor="middle" fill="#62738e" font-size="10">' + count + ' ' + (count === 1 ? 'conexión representada' : 'conexiones representadas') + '</text></g>';
  const cables = rows.map((wire, i) => {
    const y = Math.round(ys[i]);
    const selected = String(selectedId) === String(wire.id);
    const done = checked.has(wire.id) || checked.has(String(wire.id));
    const dim = matches && !matches.has(wire.id) && !matches.has(String(wire.id));
    const rawColor = String(wire.colorHex || '#d5a646');
    const color = /^#[0-9a-f]{3,8}$/i.test(rawColor) ? rawColor : '#d5a646';
    const label = wire.destination || wire.shortLabel || 'Consultar conexión';
    const destination = wrap(label, 33, 2);
    const colorLines = wrap(wire.colorName || 'Color según fuente', 34, 2);
    const chip = wire.optional ? 'Opcional' : wire.changed ? 'Cambio HW' : '';
    const chipWidth = wire.optional ? 61 : 76;
    const aria = [wire.colorName, wire.destination || label, wire.signal, wire.optional ? 'Conexión opcional' : '', wire.changed ? 'Diferencia entre versiones' : '', done ? 'Marcada como revisada' : 'Pendiente de revisión'].filter(Boolean).join('. ');
    return '<g data-wire="' + esc(wire.id) + '" role="button" tabindex="0" aria-pressed="' + selected + '" aria-label="' + esc(aria) + '" opacity="' + (dim ? '.28' : '1') + '">' +
      '<title>' + esc(wire.colorName) + ' → ' + esc(wire.destination || label) + '</title>' +
      '<rect class="focus-ring" x="272" y="' + (y - 35) + '" width="591" height="70" rx="10" fill="none" stroke="#f2bd58" stroke-width="2" stroke-dasharray="4 4" opacity="0"/>' +
      (selected ? '<path d="M264 ' + y + 'H569" stroke="#edb64f" stroke-width="13" opacity=".22" filter="url(#' + prefix + '-glow)"/>' : '') +
      '<path d="M264 ' + y + 'H569" fill="none" stroke="' + (selected ? '#92733c' : '#45536a') + '" stroke-width="7" stroke-linecap="round"/>' +
      '<path d="M264 ' + y + 'H569" fill="none" stroke="' + color + '" stroke-width="4.2" stroke-linecap="round"/>' +
      '<path d="M264 ' + y + 'H569" fill="none" stroke="transparent" stroke-width="34"/>' +
      '<circle cx="264" cy="' + y + '" r="' + (selected ? '7' : '5.5') + '" fill="#111b2c" stroke="' + (selected ? '#e7b24b' : '#61718a') + '" stroke-width="1.8"/>' +
      '<circle cx="264" cy="' + y + '" r="3" fill="' + color + '"/>' +
      (showLabels ? textLines(colorLines, 294, y - (colorLines.length > 1 ? 29 : 13), 14, 'class="wire-name" fill="' + (selected ? '#eadbc0' : '#9caac0') + '" font-size="11.5"') : '') +
      (showLabels && wire.signal ? '<text x="294" y="' + (y + 21) + '" fill="#62738e" font-size="9.5">' + esc(wrap(wire.signal, 42, 1)[0] || '') + '</text>' : '') +
      '<rect class="target-card" x="569" y="' + (y - 31) + '" width="286" height="62" rx="9" fill="' + (selected ? '#232739' : '#131e30') + '" stroke="' + (selected ? '#b99142' : '#2a3a53') + '" stroke-width="' + (selected ? '1.4' : '1') + '"/>' +
      '<circle cx="569" cy="' + y + '" r="4" fill="' + color + '" stroke="#8490a1" stroke-width=".8"/>' +
      '<text x="586" y="' + (y - 14) + '" fill="' + (selected ? '#c5a361' : '#647791') + '" font-size="8" font-weight="600" letter-spacing="1.3">DESTINO</text>' +
      (chip ? '<rect x="' + (841 - chipWidth) + '" y="' + (y - 24) + '" width="' + chipWidth + '" height="15" rx="4" fill="' + (wire.optional ? '#25334e' : '#3a3020') + '"/><text x="' + (841 - chipWidth / 2) + '" y="' + (y - 13) + '" text-anchor="middle" fill="' + (wire.optional ? '#9bb4df' : '#e4b458') + '" font-size="8.5" font-weight="600">' + chip + '</text>' : '') +
      textLines(destination, 586, y + (destination.length > 1 ? 5 : 11), 15, 'fill="' + (selected ? '#f2eadb' : '#c7d1e1') + '" font-size="12.5" font-weight="' + (selected ? '600' : '500') + '"') +
      (done ? '<g aria-hidden="true"><circle cx="548" cy="' + (y - 17) + '" r="8" fill="#103d35" stroke="#3c9b7b" stroke-width=".8"/><path d="m544 ' + (y - 17) + ' 2.5 2.5 5-5.5" fill="none" stroke="#85d4b2" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></g>' : '') +
      '</g>';
  }).join('');
  const footer = '<path d="M29 459h842" stroke="#253048"/>' +
    '<g aria-hidden="true" fill="none" stroke="#667a96" stroke-width="1.1"><circle cx="38" cy="483" r="6"/><path d="M38 482v5m0-8v1"/></g>' +
    '<text x="53" y="487" fill="#72849e" font-size="10">Distribución para lectura · sin numeración de pines</text>' +
    '<text x="867" y="487" text-anchor="end" fill="#72849e" font-size="10">Fuente · lámina ' + esc(group.sourcePage || (rows[0] && rows[0].sourcePage) || '—') + '</text>' +
    (count ? '' : '<text x="550" y="264" text-anchor="middle" fill="#8fa0b8" font-size="14">No hay conexiones para esta selección.</text>') +
    '</svg>';
  return header + connector + cables + footer;
}
window.TQTDiagramSVG=renderHarnessSVG;
})();
