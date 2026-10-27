/* Pure SVG reading layout adapted from the supplied Diagrama_TQT.html.
   Theme-aware: every surface/text colour reads a --dg-* token (defined in sec_diagrama.css)
   with a dark fallback, so the drawing follows the console light/dark theme. Wire colours
   are catalogue data and are never themed. */
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
      if (lines[count - 1].length > max + 2) lines[count - 1] = lines[count - 1].slice(0, max).trimEnd() + '…';
      return lines.slice(0, count);
    }
    return lines;
  };
  const textLines = (lines, x, y, gap, attrs = '') => '<text x="' + x + '" y="' + y + '" ' + attrs + '>' +
    lines.map((line, i) => '<tspan x="' + x + '" dy="' + (i ? gap : 0) + '">' + esc(line) + '</tspan>').join('') + '</text>';
  const identity = group.terminalLabel || group.title || 'Conexiones';
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
  const terminalLines = wrap(identity, 13, 2);
  const terminalY = terminalLines.length > 1 ? 286 : 300;
  const groupSubtitle = wrap(group.subtitle || 'Selecciona un cable', 24, 2);
  const count = rows.length;
  const top = count >= 5 ? 122 : count === 4 ? 140 : count === 3 ? 170 : 210;
  const bottom = count >= 5 ? 404 : count === 4 ? 392 : count === 3 ? 362 : 322;
  const ys = rows.map((_, i) => count === 1 ? 262 : top + i * (bottom - top) / Math.max(1, count - 1));
  const P = '#' + prefix;
  const css =
    P + '{font-family:var(--font-ui,Arial,sans-serif)}' +
    P + ' .dg-bg{fill:var(--dg-bg,#0d1423)}' +
    P + ' .dg-dot{fill:var(--dg-line,#26335a)}' +
    P + ' .dg-rule{stroke:var(--dg-line,#26335a)}' +
    P + ' .dg-panel{fill:var(--dg-panel,#121b33);stroke:var(--dg-line,#26335a)}' +
    P + ' .dg-icon{stroke:var(--dg-accent,#d9a441)}' +
    P + ' .dg-title{fill:var(--dg-text,#e9eef5)}' +
    P + ' .dg-muted{fill:var(--dg-muted,#93a1bd)}' +
    P + ' .dg-badge{fill:var(--dg-sel,#2a2a2a);stroke:var(--dg-accent,#d9a441)}' +
    P + ' .dg-badge-t{fill:var(--dg-accent-text,#e6b458)}' +
    P + ' .dg-casing{stroke:var(--dg-casing,#5f72a6)}' +
    P + ' .dg-halo{stroke:var(--dg-accent,#d9a441)}' +
    P + ' .dg-node{fill:var(--dg-panel,#121b33);stroke:var(--dg-casing,#5f72a6)}' +
    P + ' .dg-card{fill:var(--dg-card,#121b33);stroke:var(--dg-line,#26335a);transition:fill .16s,stroke .16s}' +
    P + ' .dg-bar{fill:var(--dg-accent,#d9a441)}' +
    P + ' .dg-dest{fill:var(--dg-text,#e9eef5)}' +
    P + ' .dg-cname{fill:var(--dg-text,#e9eef5)}' +
    P + ' .dg-chip-opt{fill:var(--dg-info-bg,#16294a);stroke:var(--dg-info,#5aa9ff)}' +
    P + ' .dg-chip-opt-t{fill:var(--dg-info,#5aa9ff)}' +
    P + ' .dg-chip-chg{fill:var(--dg-warn-bg,#33280f);stroke:var(--dg-warn,#f2b33d)}' +
    P + ' .dg-chip-chg-t{fill:var(--dg-warn,#f2b33d)}' +
    P + ' .dg-done{fill:var(--dg-ok-bg,#0f3327);stroke:var(--dg-ok,#3fd08a)}' +
    P + ' .dg-done-t{stroke:var(--dg-ok,#3fd08a)}' +
    P + ' .dg-ring{stroke:var(--dg-accent-text,#e6b458)}' +
    P + ' [data-wire]{cursor:pointer;outline:none}' +
    P + ' [data-wire]:hover .dg-card{fill:var(--dg-hover,#1a2646);stroke:var(--dg-casing,#5f72a6)}' +
    P + ' [data-wire][aria-pressed="true"] .dg-card{fill:var(--dg-sel,#2a2a2a);stroke:var(--dg-accent,#d9a441);stroke-width:2}' +
    P + ' [data-wire][aria-pressed="true"] .dg-node{stroke:var(--dg-accent,#d9a441)}' +
    P + ' [data-wire] .focus-ring{opacity:0}' +
    P + ' [data-wire]:focus-visible .focus-ring{opacity:1}' +
    '@media (prefers-reduced-motion:reduce){' + P + ' .dg-card{transition:none}}';
  const header = '<svg xmlns="http://www.w3.org/2000/svg" id="' + prefix + '" class="harness-diagram" viewBox="0 0 900 510" width="900" height="510" role="group" aria-labelledby="' + prefix + '-title ' + prefix + '-desc" style="display:block;width:100%;height:auto;overflow:visible">' +
    '<title id="' + prefix + '-title">' + esc(group.title || identity) + ' · ' + esc(hw) + '</title>' +
    '<desc id="' + prefix + '-desc">Esquema interactivo de ' + count + ' conexiones. Selecciona un cable para consultar su ficha. La distribución no representa posiciones ni números de pin.</desc>' +
    '<defs><pattern id="' + prefix + '-grid" width="24" height="24" patternUnits="userSpaceOnUse"><circle class="dg-dot" cx="1" cy="1" r="1"/></pattern></defs>' +
    '<style>' + css + '</style>' +
    '<rect class="dg-bg" x="0" y="0" width="900" height="510" rx="8"/>' +
    '<rect x="0" y="0" width="900" height="510" rx="8" fill="url(#' + prefix + '-grid)" opacity=".7"/>' +
    '<path class="dg-rule" d="M24 56h852"/>' +
    '<g class="dg-icon" fill="none" stroke-width="1.6" aria-hidden="true"><path d="M28 24h9v9h-9zM41 24h9v9h-9zM28 38h9m4 0h9"/></g>' +
    '<text class="dg-muted" x="62" y="36" font-size="15" font-weight="600">Esquema de conexiones</text>' +
    '<rect class="dg-badge" x="784" y="18" width="92" height="26" rx="4" stroke-width="1"/>' +
    '<text class="dg-badge-t" x="830" y="36" text-anchor="middle" font-size="14" font-weight="600">' + esc(String(hw).replace(/^HW\s*/i, 'HW ')) + '</text>';
  const connector = '<g aria-hidden="true">' +
    '<rect class="dg-panel" x="40" y="84" width="216" height="352" rx="10" stroke-width="1.2"/>' +
    '<g class="dg-icon" fill="none" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" transform="translate(13 -36)">' + componentIcon + '</g>' +
    textLines(terminalLines, 148, terminalY, 28, 'class="dg-title" text-anchor="middle" font-size="26" font-weight="600"') +
    textLines(groupSubtitle, 148, terminalY + terminalLines.length * 28 + 4, 17, 'class="dg-muted" text-anchor="middle" font-size="13"') +
    '<path class="dg-rule" d="M60 392h176"/>' +
    '<text class="dg-muted" x="148" y="418" text-anchor="middle" font-size="12">' + count + ' ' + (count === 1 ? 'conexión representada' : 'conexiones representadas') + '</text></g>';
  const cables = rows.map((wire, i) => {
    const y = Math.round(ys[i]);
    const selected = String(selectedId) === String(wire.id);
    const done = checked.has(wire.id) || checked.has(String(wire.id));
    const dim = matches && !matches.has(wire.id) && !matches.has(String(wire.id));
    const rawColor = String(wire.colorHex || '#d5a646');
    const color = /^#[0-9a-f]{3,8}$/i.test(rawColor) ? rawColor : '#d5a646';
    const label = wire.destination || wire.shortLabel || 'Consultar conexión';
    const chip = wire.optional ? 'Opcional' : wire.changed ? 'Cambio HW' : '';
    const chipWidth = wire.optional ? 70 : 82;
    const destination = wrap(label, chip ? 24 : 32, 2);
    const colorLines = wrap(wire.colorName || 'Color según fuente', 32, 2);
    const aria = [wire.colorName, wire.destination || label, wire.signal, wire.optional ? 'Conexión opcional' : '', wire.changed ? 'Diferencia entre versiones' : '', done ? 'Marcada como revisada' : 'Pendiente de revisión'].filter(Boolean).join('. ');
    const run = 'M256 ' + y + 'H560';
    return '<g data-wire="' + esc(wire.id) + '" role="button" tabindex="0" aria-pressed="' + selected + '" aria-label="' + esc(aria) + '" opacity="' + (dim ? '.28' : '1') + '">' +
      '<title>' + esc(wire.colorName) + ' → ' + esc(wire.destination || label) + '</title>' +
      '<rect class="focus-ring dg-ring" x="266" y="' + (y - 35) + '" width="612" height="70" rx="8" fill="none" stroke-width="2.5" stroke-dasharray="6 4"/>' +
      (selected ? '<path class="dg-halo" d="' + run + '" stroke-width="16" stroke-linecap="round" opacity=".25" fill="none"/>' : '') +
      '<path class="dg-casing" d="' + run + '" fill="none" stroke-width="' + (selected ? 10 : 8) + '" stroke-linecap="round"/>' +
      '<path d="' + run + '" fill="none" stroke="' + color + '" stroke-width="' + (selected ? 6 : 4.5) + '" stroke-linecap="round"/>' +
      '<path d="' + run + '" fill="none" stroke="transparent" stroke-width="34"/>' +
      '<circle class="dg-node" cx="256" cy="' + y + '" r="' + (selected ? 8 : 6.5) + '" stroke-width="2"/>' +
      '<circle cx="256" cy="' + y + '" r="3.5" fill="' + color + '"/>' +
      (showLabels ? textLines(colorLines, 280, y - (colorLines.length > 1 ? 30 : 13), 16, 'class="dg-cname" font-size="15" font-weight="' + (selected ? '600' : '500') + '"') : '') +
      (showLabels && wire.signal ? '<text class="dg-muted" x="280" y="' + (y + 26) + '" font-size="13">' + esc(wrap(wire.signal, 40, 1)[0] || '') + '</text>' : '') +
      '<rect class="dg-card" x="560" y="' + (y - 29) + '" width="316" height="58" rx="6" stroke-width="1"/>' +
      (selected ? '<rect class="dg-bar" x="560" y="' + (y - 29) + '" width="4" height="58" rx="2"/>' : '') +
      '<circle cx="560" cy="' + y + '" r="4.5" fill="' + color + '" class="dg-casing" stroke-width="1"/>' +
      (chip ? '<rect class="' + (wire.optional ? 'dg-chip-opt' : 'dg-chip-chg') + '" x="' + (864 - chipWidth) + '" y="' + (y - 11) + '" width="' + chipWidth + '" height="22" rx="4" stroke-width="1"/><text class="' + (wire.optional ? 'dg-chip-opt-t' : 'dg-chip-chg-t') + '" x="' + (864 - chipWidth / 2) + '" y="' + (y + 4) + '" text-anchor="middle" font-size="12" font-weight="600">' + chip + '</text>' : '') +
      textLines(destination, 580, y + (destination.length > 1 ? -4 : 5), 18, 'class="dg-dest" font-size="16" font-weight="' + (selected ? '600' : '500') + '"') +
      (done ? '<g aria-hidden="true"><circle class="dg-done" cx="536" cy="' + (y - 18) + '" r="9" stroke-width="1"/><path class="dg-done-t" d="m532 ' + (y - 18) + ' 2.8 2.8 5.2-5.6" fill="none" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></g>' : '') +
      '</g>';
  }).join('');
  const footer = '<path class="dg-rule" d="M24 456h852"/>' +
    '<g aria-hidden="true" class="dg-icon" fill="none" stroke-width="1.2"><circle cx="34" cy="482" r="7"/><path d="M34 481v5m0-9v1"/></g>' +
    '<text class="dg-muted" x="50" y="487" font-size="13">Distribución para lectura · sin numeración de pines</text>' +
    '<text class="dg-muted" x="876" y="487" text-anchor="end" font-size="13">Fuente · lámina ' + esc(group.sourcePage || (rows[0] && rows[0].sourcePage) || '—') + '</text>' +
    (count ? '' : '<text class="dg-muted" x="566" y="264" text-anchor="middle" font-size="15">No hay conexiones para esta selección.</text>') +
    '</svg>';
  return header + connector + cables + footer;
}
window.TQTDiagramSVG=renderHarnessSVG;
})();
