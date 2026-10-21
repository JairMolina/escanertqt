/* Native console section, adapted from Explorador_R1.html. */
(function(){
'use strict';
const {GROUPS,KIND_LABELS,normalize,enrich,supported,filterCommands,initialValue,operationKind,validateValue,supportsPlatform,outputFormatFor,buildPayload,compareCommands,related,technicalNotes,careNote}=window.TQTCommands;
let catalogCache;
function loadCatalog(signal){
 if(catalogCache)return Promise.resolve(catalogCache);
 return fetch('/static/catalogos/comandos_r1.json',{signal,cache:'no-cache'}).then(r=>{if(!r.ok)throw new Error('Catálogo no disponible');return r.json();}).then(d=>{catalogCache=d;return d;});
}
window.TQTEscritorio.registrar({id:'comandos',titulo:'Comandos',icono:'list',grupo:'gestion',orden:110,
montar(host,ctx){
 let active=true;
 const controller=new AbortController();
 const catalogPromise=loadCatalog(controller.signal);
 let VERSIONS=['4.1','4.2','4.3','4.4'];
 const app=document.createElement('div');app.className='tqt-comandos';app.innerHTML='<p role="status">Cargando catálogo de comandos…</p>';
 const dialog=document.createElement('dialog');dialog.className='tqt-comandos commands-guide';dialog.id='commands-guide-dialog';dialog.setAttribute('aria-labelledby','guide-title');
 host.append(app,dialog);
const PATHS={
 terminal:'m4 6 5 6-5 6m9 0h7', grid:'M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z',
 pulse:'M2 12h5l3-8 4 16 3-8h5',move:'M7 3v18m-4-4 4 4 4-4M17 21V3m-4 4 4-4 4 4',
 shield:'m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6l8-3Zm-4 9 3 3 5-6',
 sliders:'M4 4v6m0 4v6M12 4v10m0 4v2M20 4v2m0 4v10M1 10h6m2 8h6m2-12h6',
 route:'M4 3v4c0 5 16 5 16 10v4M20 3v4c0 5-16 5-16 10v4M1 18l3 3 3-3m10 0 3 3 3-3',
 reset:'M3 10a9 9 0 1 1 1 7M3 4v6h6',link:'m9 15 6-6m-6-2 2-2a5 5 0 0 1 7 7l-2 2m-1 3-2 2a5 5 0 0 1-7-7l2-2',
 compare:'M8 3v18m8-18v18M4 7l4-4 4 4m0 10 4 4 4-4',book:'M12 5v16M3 3h5a4 4 0 0 1 4 3 4 4 0 0 1 4-3h5v16h-5a4 4 0 0 0-4 2 4 4 0 0 0-4-2H3V3Z',
 search:'M21 21l-5-5M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0Z',chevron:'m9 5 7 7-7 7',down:'m6 9 6 6 6-6',
 arrow:'M4 12h16m-6-6 6 6-6 6',star:'m12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2-5.6-3-5.6 3 1.1-6.2L3 9.6l6.2-.9L12 3Z',
 copy:'M9 9h12v12H9zM15 9V3H3v12h6',check:'m5 12 4 4L19 6',clock:'M12 8v5l3 2m6-3a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z',
 chip:'M6 6h12v12H6zM9 9h6v6H9zM9 2v4m6-4v4M9 18v4m6-4v4M2 9h4m-4 6h4m12-6h4m-4 6h4',
 bluetooth:'m7 7 10 10-5 4V3l5 4L7 17',cable:'M8 3v5m8-5v5M6 8h12v3a6 6 0 0 1-12 0V8Zm6 9v5',
 info:'M12 11v6m0-10v.1m9 4.9a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z',
 warning:'m12 3 10 18H2L12 3Zm0 6v5m0 3v.1',close:'m6 6 12 12M6 18 18 6',
 filter:'M3 5h18l-7 8v6l-4 2v-8L3 5Z',spark:'m12 3 2.7 6.3L21 12l-6.3 2.7L12 21l-2.7-6.3L3 12l6.3-2.7L12 3Z',
 download:'M12 3v12m-5-5 5 5 5-5M4 17v4h16v-4',external:'M14 3h7v7m0-7L10 14M10 3H3v18h18v-7',menu:'M3 6h18M3 12h18M3 18h18',
 minus:'M5 12h14',plus:'M5 12h14m-7-7v14',eye:'M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Zm13 0a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z'
};
const icon=(name,cls='')=>`<svg class="icon ${cls}" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${PATHS[name]||PATHS.terminal}"/></svg>`;
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const el=id=>id==='app'?app:id==='guide-dialog'?dialog:app.querySelector('#'+CSS.escape(id));
const readFavorites=()=>{try{const v=JSON.parse(localStorage.getItem('tqt.comandos.r1.favorites.v1')||'[]');return Array.isArray(v)?v.filter(x=>Number.isInteger(x)&&x>=0):[];}catch{return [];}};
let data,commands,commandById={},favorites=readFavorites(),lastSelection=null,toastTimer;
const values={},otherSeparators={20:';',21:'|'};
const qs=ctx.params();
const state={hw:qs.get('hw')==='other'?'other':'3.0',fw:VERSIONS.includes(qs.get('fw'))?qs.get('fw'):'4.4',view:['explore','compare','defaults'].includes(qs.get('view'))?qs.get('view'):'explore',channel:'all',group:'all',kind:'all',q:'',compatible:true,favoriteOnly:false,newOnly:false,selected:qs.has('cmd')?Number(qs.get('cmd')):6,outputFormat:'platform',includeCRLF:false,compareFrom:'4.3',compareTo:'4.4',changesOnly:true,defaultsQ:'',defaultType:'all',menuOpen:false};

function available(fw=state.fw){return commands.filter(c=>supported(c,state.hw,fw));}
function valueFor(c){return values[c.id]??initialValue(c);}
function deliveryFor(c,value=valueFor(c)){
 const format=outputFormatFor(c,state.outputFormat),includeCRLF=format==='serial'&&state.includeCRLF;
 const helper=format==='platform'?'Listo para pegar en la plataforma. Se copia sin CRLF.':format==='bluetooth'?'Se copian los 4 caracteres exactos. El puente ESP32 agrega el fin de línea al reenviarlos.':includeCRLF?'Se añade un CRLF real al copiar; el indicador \\r\\n lo representa en pantalla.':'Se copia sin CRLF. Para el envío serial, añade el terminador aquí o en tu aplicación.';
 return {format,includeCRLF,error:validateValue(c,value,otherSeparators[c.id],format),text:buildPayload(c,value,includeCRLF,format),preview:buildPayload(c,value,false,format),label:format==='platform'?'PLATAFORMA':format==='bluetooth'?'BLUETOOTH · 4 CARACTERES':'SERIAL / GPS',helper,copied:format==='platform'?'Comando de plataforma copiado, sin CRLF.':format==='bluetooth'?'Copiado: 4 caracteres, sin CRLF.':includeCRLF?'Comando serial copiado con CRLF real.':'Comando serial copiado, sin CRLF.'};
}
function deliveryControl(c,format){
 if(!supportsPlatform(c))return '';
 return `<div class="delivery-control"><span id="delivery-heading">Formato de envío</span><div class="segmented delivery-switch" role="group" aria-labelledby="delivery-heading"><button type="button" data-output-format="platform" class="${format==='platform'?'active':''}" aria-pressed="${format==='platform'}">${icon('route')}Plataforma</button><button type="button" data-output-format="serial" class="${format==='serial'?'active':''}" aria-pressed="${format==='serial'}">${icon('cable')}Serial / GPS</button></div></div>`;
}
function countFor(group){return available().filter(c=>group==='all'||c.group===group).length;}
function badge(kind){return `<span class="badge kind-${kind}">${esc(KIND_LABELS[kind])}</span>`;}
function groupIcon(c){return GROUPS.find(g=>g.id===c.group)?.icon||'terminal';}
function isNew(c){return state.fw!=='4.1'&&c.first===state.fw;}
function formatValue(v,unit){return v===null?'No disponible':`${v}${unit?' '+unit:''}`;}
const urlKeys=['hw','fw','view','cmd','channel','group','kind','q','compatible','favorites','new','format','crlf','value','other','from','to','changes','dq','dtype'];
function applyParams(q){
 state.hw=q.get('hw')==='other'?'other':'3.0';
 state.fw=VERSIONS.includes(q.get('fw'))?q.get('fw'):'4.4';
 state.view=['explore','compare','defaults'].includes(q.get('view'))?q.get('view'):'explore';
 const id=Number(q.get('cmd')??6);state.selected=commandById[id]?id:6;
 state.channel=['all','Serial/GPS','Bluetooth'].includes(q.get('channel'))?q.get('channel'):'all';
 state.group=GROUPS.some(g=>g.id===q.get('group'))?q.get('group'):'all';
 state.kind=['all',...Object.keys(KIND_LABELS)].includes(q.get('kind'))?q.get('kind'):'all';
 state.q=q.get('q')||'';state.compatible=q.get('compatible')!=='0';
 state.favoriteOnly=q.get('favorites')==='1';state.newOnly=q.get('new')==='1';
 state.outputFormat=q.get('format')==='serial'?'serial':'platform';
 state.includeCRLF=q.get('crlf')==='1'&&state.outputFormat==='serial';
 state.compareFrom=VERSIONS.includes(q.get('from'))?q.get('from'):'4.3';
 state.compareTo=VERSIONS.includes(q.get('to'))?q.get('to'):state.fw;
 state.changesOnly=q.get('changes')!=='0';state.defaultsQ=q.get('dq')||'';
 state.defaultType=['all','settings','states'].includes(q.get('dtype'))?q.get('dtype'):'all';
 if(q.has('value'))values[state.selected]=q.get('value');
 if(q.has('other'))otherSeparators[state.selected]=q.get('other');
}
function updateURL(){
 if(!active)return;
 const u=new URL(location.href),p=new URLSearchParams(u.hash.split('?')[1]||'');
 urlKeys.forEach(k=>p.delete(k));
 const entries={hw:state.hw,fw:state.fw,view:state.view,cmd:state.selected,channel:state.channel,group:state.group,kind:state.kind,q:state.q,compatible:state.compatible?'1':'0',favorites:state.favoriteOnly?'1':'0',new:state.newOnly?'1':'0',format:state.outputFormat,crlf:state.includeCRLF?'1':'0',from:state.compareFrom,to:state.compareTo,changes:state.changesOnly?'1':'0',dq:state.defaultsQ,dtype:state.defaultType};
 if(values[state.selected]!==undefined)entries.value=values[state.selected];
 if(otherSeparators[state.selected]!==undefined)entries.other=otherSeparators[state.selected];
 Object.entries(entries).forEach(([k,v])=>{if(v!==''&&v!==undefined)p.set(k,v);});
 u.hash='/comandos?'+p.toString();history.replaceState(history.state,'',u);
}
function sidebar(){return `<nav class="commands-tabs" aria-label="Vistas de comandos">${[['explore','terminal','Explorar comandos'],['compare','compare','Comparar firmware'],['defaults','sliders','Valores de fábrica']].map(([view,i,label])=>`<button class="button ${state.view===view?'primary':''}" data-view="${view}" aria-pressed="${state.view===view}">${icon(i)}${label}</button>`).join('')}</nav>${state.view==='explore'?`<nav class="commands-categories" aria-label="Categorías de comandos">${GROUPS.map(g=>`<button class="category ${state.group===g.id?'active':''}" data-group="${g.id}" aria-pressed="${state.group===g.id}">${icon(g.icon)}${g.label}<span>${countFor(g.id)}</span></button>`).join('')}</nav>`:''}`;}
function context(){return `<div class="context-bar"><div class="context-intro">${icon('chip')}<div><strong>Tu equipo</strong><span>Define el contexto</span></div></div>
 <label class="context-field" for="hardware"><span>Hardware <abbr title="Versión física de la tarjeta">HW</abbr></span><select id="hardware"><option value="3.0" ${state.hw==='3.0'?'selected':''}>R1 · HW 3.0</option><option value="other" ${state.hw==='other'?'selected':''}>Otro hardware · sin datos</option></select></label>
 <label class="context-field" for="firmware"><span>Firmware <abbr title="Versión del programa interno de la tarjeta">FW</abbr></span><select id="firmware">${VERSIONS.slice().reverse().map(v=>`<option value="${v}" ${state.fw===v?'selected':''}>FW ${v}${v==='4.4'?' · Referencia':''}</option>`).join('')}</select></label>
 <div class="context-summary"><span class="documented-dot"></span><strong>${available().length} comandos disponibles</strong><span>Según las fuentes de esta versión</span></div>
 </div>`;}
function header(){const titles={explore:['ENCUENTRA · ENTIENDE · PREPARA','Cada comando, en su contexto.','La referencia de tu R1, lista para trabajar.'],compare:['ENTIENDE QUÉ CAMBIA','Compara antes de cambiar.','Disponibilidad y valores de fábrica, versión por versión.'],defaults:['CONOCE EL PUNTO DE PARTIDA','Así comienza tu R1.','Valores de fábrica y estados iniciales documentados.']};const t=titles[state.view];return `<div class="page-heading"><div><div class="eyebrow">${t[0]}</div><h1>${t[1]}</h1><p>${t[2]}</p></div><div class="heading-mark" aria-hidden="true"><span>R1</span><i>COMMAND<br>EXPLORER</i></div></div>${context()}`;}
function filters(){return `<section class="explore-tools" aria-label="Filtros de comandos">
 <div class="search-row"><label class="search-field" for="search">${icon('search')}<input id="search" data-buscar type="search" aria-label="Buscar comandos por nombre, función o sintaxis" autocomplete="off" placeholder="Busca «abrir», «tiempo» o un comando…" value="${esc(state.q)}"><kbd>/</kbd></label><button class="button favorite-filter ${state.favoriteOnly?'selected':''}" data-action="favorites" aria-pressed="${state.favoriteOnly}" title="Mostrar tus comandos guardados">${icon('star')}<span>Guardados</span><small>${favorites.length}</small></button></div>
 <div class="filter-row"><div class="segmented" role="group" aria-label="Canal de comunicación">${[['all','Todos los canales',null],['Serial/GPS','Serial / GPS','cable'],['Bluetooth','Bluetooth','bluetooth']].map(([channel,label,i])=>`<button data-channel="${channel}" aria-pressed="${state.channel===channel}" class="${state.channel===channel?'active':''}">${i?icon(i):''}${label}${channel!=='all'?`<span>${available().filter(c=>c.channel===channel).length}</span>`:''}</button>`).join('')}</div><div class="filter-options"><label class="check-label"><input id="compatible" type="checkbox" ${state.compatible?'checked':''}><span>Solo disponibles</span></label><label class="check-label"><input id="new-only" type="checkbox" ${state.newOnly?'checked':''}><span>${state.fw==='4.1'?'Novedades documentadas':`Nuevos en ${state.fw}`}</span></label></div></div>
 <div class="intent-row"><span>Quiero…</span><button data-intent="status">${icon('eye')}Ver el estado</button><button data-intent="time">${icon('clock')}Ajustar el tiempo</button><button data-intent="protection">${icon('shield')}Revisar la protección</button><button data-intent="new">${icon('spark')}Ver qué cambió</button></div>
 </section>`;}
function emptyState(){if(state.group==='protection'&&state.fw!=='4.4'&&state.hw==='3.0'&&state.compatible)return `<div class="empty">${icon('shield')}<h3>Esta versión usa protección fija en la lógica.</h3><p>FW${state.fw} no dispone del ajuste configurable PARO_C. Los comandos para consultarlo o configurarlo aparecen en FW4.4.</p><button class="button" data-action="protection-changes">Ver el cambio en FW4.4 ${icon('arrow')}</button><button class="text-button" style="margin-top:15px" data-action="reset-filters">Ver todos los comandos</button></div>`;if(state.hw==='other')return `<div class="empty hardware-empty">${icon('chip')}<h2>Este hardware aún no tiene documentación.</h2><p>Los archivos proporcionados corresponden únicamente a R1 HW3.0. La disponibilidad de comandos para otros modelos está pendiente de documentar.</p><button class="button primary" data-action="known-hw">Explorar HW 3.0 ${icon('arrow')}</button></div>`;return `<div class="empty">${icon(state.favoriteOnly?'star':'search')}<h3>${state.favoriteOnly?'No hay guardados con estos filtros.':'No encontramos comandos con estos filtros.'}</h3><p>${state.newOnly&&state.fw==='4.1'?'FW4.1 es la primera versión documentada: no hay una versión anterior revisada para identificar novedades.':'Prueba otra palabra, categoría o versión de firmware.'}</p><button class="button" data-action="reset-filters">Restablecer filtros</button></div>`;}
function commandList(list){return `<section class="command-catalog" aria-labelledby="catalog-title"><div class="catalog-heading"><div><h2 id="catalog-title">${state.favoriteOnly?'Tus guardados':state.group==='all'?'Comandos':GROUPS.find(g=>g.id===state.group).label}</h2><span class="result-count">${list.length}</span></div><label class="sr-only" for="kind-filter">Tipo de operación</label><select id="kind-filter" class="kind-filter">${Object.entries({all:'Todos los tipos',...KIND_LABELS}).map(([k,l])=>`<option value="${k}" ${state.kind===k?'selected':''}>${l}</option>`).join('')}</select></div>
 <div class="command-list" aria-label="Resultados de comandos">${list.length?list.map(c=>`<div class="command-row ${state.selected===c.id?'selected':''} ${!supported(c,state.hw,state.fw)?'unavailable':''}"><button class="command-select" data-select="${c.id}" aria-pressed="${state.selected===c.id}"><span class="row-icon group-${c.group}">${icon(groupIcon(c))}</span><span class="row-body"><span class="row-title">${esc(c.title)}</span><code>${esc(c.command)}</code><span class="row-meta">${badge(c.kind)}<span class="channel-text">${icon(c.channel==='Bluetooth'?'bluetooth':'cable')}${c.channel==='Bluetooth'?'Bluetooth':'Serial / GPS'}</span>${!supported(c,state.hw,state.fw)?'<span class="unavailable-label">No disponible</span>':isNew(c)?`<span class="new-label">Nuevo ${state.fw}</span>`:''}</span></span></button><button class="star-button ${favorites.includes(c.id)?'saved':''}" data-favorite="${c.id}" aria-label="${favorites.includes(c.id)?'Quitar de guardados':'Guardar'} ${esc(c.command)}" aria-pressed="${favorites.includes(c.id)}">${icon('star')}</button></div>`).join(''):emptyState()}</div>
 <div class="catalog-footer">${icon('info')}La disponibilidad se basa en código revisado.</div></section>`;}
function parameterControl(c,value){
 const layoutValue=Number.isFinite(Number(value))?Math.max(0,Math.min(10,Number(value))):0;
 if(c.input==='none')return `<div class="no-parameter">${icon('check')}Este comando no necesita parámetros.</div>`;
 if(c.input==='time')return `<div class="parameter-heading"><label for="param-number">Segundos adicionales</label><div class="number-field"><input id="param-number" inputmode="numeric" type="number" min="0" max="10" step="1" value="${esc(value)}"><span>s</span></div></div><input aria-label="Segundos adicionales, de 0 a 10" id="param-range" type="range" min="0" max="10" step="1" value="${esc(value)}"><div class="range-labels"><span>0 s</span><span>Máximo 10 s</span></div><div class="time-insight"><div class="time-total"><span>Límite nominal del movimiento</span><strong id="nominal-value">${4+Number(value)}<small> s</small></strong></div><div class="time-track"><span class="track-base" style="flex:4">Base</span><span id="track-extra" class="track-extra" style="flex:${layoutValue};display:${layoutValue?'flex':'none'}">Extra</span></div><div class="time-equation"><span>4 s base</span><span>+ <b id="extra-equation">${esc(value)}</b> s extra</span><span>Apertura y cierre</span></div><p>${icon('info')}Los sensores pueden detenerlo antes. La pausa posterior de 3 s es independiente.</p></div>`;
 const options={sensors:[['0','0 · Terminar por sensores'],['1','1 · Trabajar por tiempo']],binary:[['0','0 · Desactivar'],['1','1 · Activar']],protection:[['?','? · Consultar ajuste'],['0','0 · Desactivar'],['1','1 · Activar']],mapping:[['0','0 · Mapeo normal'],['1','1 · Intercambiar señales']],input:[['3','3 · Lectura puntual, sin cambios'],['0','0 · Deshabilitar seguimiento'],['1','1 · Habilitar seguimiento'],['2','2 · Habilitar seguimiento']],output:[['0','0 · Nivel lógico bajo'],['1','1 · Nivel lógico alto']],blocking:[['0','0 · Ninguna salida'],...['1','2','3','4'].map(x=>[x,`${x} · Salida GPS ${x}`])]};
 if(options[c.input])return `<label class="field-label" for="param-value">${c.input==='input'||c.input==='protection'?'¿Qué quieres hacer?':'Elige el valor'}</label><select id="param-value" class="parameter-select">${options[c.input].map(([v,l])=>`<option value="${v}" ${String(value)===v?'selected':''}>${l}</option>`).join('')}</select><p class="input-helper">${esc(c.values)}</p>`;
 if(c.input==='name')return `<label class="field-label" for="param-value">Nombre de configuración / Bluetooth</label><input id="param-value" class="text-input mono" type="text" autocomplete="off" value="${esc(value)}" aria-describedby="name-note"><p class="input-helper" id="name-note">Hasta 22 caracteres. El texto inicial es un ejemplo: usa la identidad de tu unidad.</p>`;
 return `<div class="separator-fields"><label class="field-label" for="param-value">Nuevo ${c.id===20?'SPAS':'SPAV'}<input class="text-input mono" id="param-value" value="${esc(value)}" autocomplete="off"></label><label class="field-label" for="other-separator">${c.id===20?'SPAV':'SPAS'} actual<input class="text-input mono" id="other-separator" value="${esc(otherSeparators[c.id])}" autocomplete="off"></label></div><p class="input-helper">Confirma el otro separador que usa tu unidad. El formulario comienza con el valor de fábrica.</p>`;
}
function relatedHTML(c,value){return related(c,value).map(id=>`<button data-related="${id}"><code>${esc(commandById[id].command)}</code>${icon('arrow')}</button>`).join('');}
function detail(c){
 if(!c)return `<section class="detail-panel detail-empty"><span class="detail-empty-icon">${icon('terminal')}</span><h2>Un comando, toda la explicación.</h2><p>Selecciona un resultado para consultar sus valores, su compatibilidad y cómo utilizarlo.</p></section>`;
 const value=valueFor(c),delivery=deliveryFor(c,value),kind=operationKind(c,value),ok=supported(c,state.hw,state.fw),error=delivery.error,care=careNote(c,value),d=data.factory_defaults.find(x=>x.key===c.default_setting_key),notes=technicalNotes(c);
 return `<section class="detail-panel" aria-labelledby="detail-title"><div class="detail-topline"><span>${icon('book')}FICHA DE COMANDO</span></div><div class="detail-scroll">
 <div class="detail-title-row"><h2 id="detail-title">${esc(c.title)}</h2></div><div class="detail-tags"><span class="badge channel-badge">${icon(c.channel==='Bluetooth'?'bluetooth':'cable')}${c.channel==='Bluetooth'?'Bluetooth':'Serial / GPS'}</span><span id="operation-badge">${badge(kind)}</span>${ok?`<span class="availability">${icon('check')}Disponible en ${state.fw}</span>`:'<span class="unavailable-label">No disponible en esta versión</span>'}</div>
 <p class="command-description">${esc(c.description)}</p><div class="syntax-line"><span>${c.channel==='Bluetooth'?'Sintaxis Bluetooth':'Sintaxis serial'}</span><code>${esc(c.command)}</code></div>
 ${!ok?`<div class="notice danger">${icon('info')}<div><strong>No disponible en FW${state.fw}.</strong><p>Este comando está documentado en ${c.supported_versions.map(v=>'FW'+v).join(', ')}. Cambia el firmware para prepararlo.</p></div></div>`:''}
 <div class="builder"><div class="section-heading"><span class="step">1</span><h3>${c.input==='none'?'Revisa el comando':'Configura el parámetro'}</h3><span class="small-label">VISTA PREVIA</span></div>${parameterControl(c,value)}<p class="validation-error" id="validation-error" role="alert" ${error?'':'hidden'}>${esc(error)}</p></div>
 <div id="care-note">${care?`<div class="notice ${kind==='destructive'?'danger':'caution'}">${icon('warning')}<p>${esc(care)}</p></div>`:''}</div>
 <div class="copy-section"><div class="section-heading"><span class="step">2</span><h3>Tu comando preparado</h3></div>${deliveryControl(c,delivery.format)}<div class="terminal-box"><div class="terminal-meta"><span class="terminal-dot"></span><span id="delivery-label">${delivery.label}</span><span id="terminator-label">${delivery.includeCRLF?'CON CRLF':'SIN CRLF'}</span></div><div class="terminal-command"><code id="payload-content">${esc(delivery.preview)}</code><span class="terminator-symbol" id="terminator-symbol">${delivery.includeCRLF?'\\r\\n':''}</span></div><button id="copy-command" class="copy-button" data-action="copy" ${!ok||error?'disabled':''}>${icon('copy')}Copiar comando</button></div>
 ${delivery.format==='serial'?`<label class="check-label crlf-option"><input id="include-crlf" type="checkbox" ${state.includeCRLF?'checked':''}><span>Incluir fin de línea CRLF <code>\\r\\n</code></span></label>`:''}<p class="copy-helper" id="copy-helper">${esc(delivery.helper)}</p>${!supportsPlatform(c)&&c.channel==='Serial/GPS'?'<p class="copy-helper">Este acuse de recibo conserva su formato serial.</p>':''}</div>
 ${c.id===36?`<div class="notice info">${icon('route')}<p>La respuesta a <code>PC_?</code> se genera por <strong>Serial/GPS</strong>, no como notificación Bluetooth.</p></div>`:''}
 ${d?`<div class="default-preview"><span class="default-icon">${icon('reset')}</span><div><span>De fábrica · FW ${state.fw}</span><strong>${esc(formatValue(d.values_by_version[state.fw],d.unit))}</strong><p>${esc(d.meaning)}</p></div></div>`:''}
 <details class="technical-details"><summary>Detalles técnicos y compatibilidad ${icon('plus')}</summary><div class="technical-inner"><h4>Valores / respuesta documentada</h4><p>${esc(c.values)}</p>${notes.map(n=>`<p class="technical-note">${esc(n)}</p>`).join('')}<h4>Disponibilidad por firmware</h4><div class="compatibility-chips">${VERSIONS.map(v=>`<span class="${c.supported_versions.includes(v)?'yes':'no'}">${icon(c.supported_versions.includes(v)?'check':'minus')}FW ${v}</span>`).join('')}</div><p class="micro-copy">Para HW3.0. Presencia documentada en fuentes de código; no certifica pruebas físicas de todos los comandos.</p></div></details>
 <div class="related-section"><h4>También te puede servir</h4><div id="related-commands" class="related-commands">${relatedHTML(c,value)||'<span class="micro-copy">Explora más comandos en las categorías.</span>'}</div></div>
 <div class="source-label">${icon('book')}Fuente: catálogo R1 + notas técnicas adjuntas</div>
 </div><div class="detail-footer">${icon('eye')}Prepara y copia. La web no envía órdenes al equipo.</div></section>`;
}
function explore(){const list=filterCommands(commands,state,favorites);if(!list.some(c=>c.id===state.selected))state.selected=list[0]?.id??-1;return `${filters()}<div class="workspace-grid">${commandList(list)}${detail(commandById[state.selected])}</div>`;}
function comparison(){
 const rows=compareCommands(commands,state.compareFrom,state.compareTo),added=rows.filter(c=>!c.inFrom&&c.inTo),removed=rows.filter(c=>c.inFrom&&!c.inTo),same=rows.filter(c=>c.inFrom&&c.inTo),shown=state.changesOnly?rows.filter(c=>c.inFrom!==c.inTo):rows.filter(c=>c.inFrom||c.inTo),defaultChanges=data.factory_defaults.filter(d=>d.values_by_version[state.compareFrom]!==d.values_by_version[state.compareTo]);
 return `<section class="comparison-view"><div class="compare-controls"><label for="compare-from"><span>Versión de origen</span><select id="compare-from">${VERSIONS.map(v=>`<option ${v===state.compareFrom?'selected':''}>${v}</option>`).join('')}</select></label><button class="icon-button compare-swap" data-action="swap-versions" aria-label="Intercambiar versiones">${icon('compare')}</button><label for="compare-to"><span>Versión de destino</span><select id="compare-to">${VERSIONS.map(v=>`<option ${v===state.compareTo?'selected':''}>${v}</option>`).join('')}</select></label><div class="comparison-scope">${icon('chip')}HW 3.0<span>Elige cualquier par de versiones documentadas.</span></div></div>
 <div class="compare-metrics"><div><span class="metric-icon positive">${icon('plus')}</span><strong>${added.length}</strong><span>Comandos incorporados</span></div><div><span class="metric-icon neutral">${icon('check')}</span><strong>${same.length}</strong><span>Presentes en ambas</span></div><div><span class="metric-icon muted">${icon('minus')}</span><strong>${removed.length}</strong><span>Dejan de estar disponibles</span></div></div>
 <div class="comparison-callout">${icon('spark')}<div><strong>${state.compareFrom===state.compareTo?'Estás comparando la misma versión.':added.length||removed.length?'Las diferencias que sí necesitas ver.':'Sin cambios en el catálogo de comandos.'}</strong><p>${state.compareTo==='4.4'&&state.compareFrom!=='4.4'?'FW4.4 incorpora el ajuste de paro por sobrecorriente, desactivado de fábrica. Las 6 filas de protección incluyen alias y variantes de canal; no son 6 funciones independientes. Si comparas desde FW4.1, también se añaden los 3 comandos de mapeo incorporados en FW4.2.':!added.length&&!removed.length?'Esta comparación cubre disponibilidad y predeterminados documentados. No demuestra que el firmware completo sea idéntico.':'Los resultados describen presencia en el código de cada versión. Revisa también los cambios de valores de fábrica.'}</p></div></div>
 <div class="table-card"><div class="table-heading"><h2>Disponibilidad de comandos <span>${shown.length}</span></h2><label class="check-label"><input id="changes-only" type="checkbox" ${state.changesOnly?'checked':''}>Solo diferencias</label></div><div class="table-scroll"><table><thead><tr><th>Comando / función</th><th>Canal</th><th>FW ${state.compareFrom}</th><th>FW ${state.compareTo}</th><th>Cambio</th></tr></thead><tbody>${shown.length?shown.map(c=>`<tr><td><button class="table-command" data-jump="${c.id}"><code>${esc(c.command)}</code><span>${esc(c.title)}</span></button></td><td><span class="table-channel">${icon(c.channel==='Bluetooth'?'bluetooth':'cable')}${c.channel}</span></td><td><span class="status-cell ${c.inFrom?'yes':'no'}">${icon(c.inFrom?'check':'minus')}${c.inFrom?'Disponible':'No disponible'}</span></td><td><span class="status-cell ${c.inTo?'yes':'no'}">${icon(c.inTo?'check':'minus')}${c.inTo?'Disponible':'No disponible'}</span></td><td><span class="badge ${c.inTo&&!c.inFrom?'new':!c.inTo&&c.inFrom?'removed':'unchanged'}">${c.inTo&&!c.inFrom?'Se incorpora':!c.inTo&&c.inFrom?'Sin disponibilidad':'Sin cambio'}</span></td></tr>`).join(''):'<tr><td colspan="5" class="empty-table">No hay diferencias de disponibilidad entre estas versiones. Desmarca «Solo diferencias» para ver el catálogo.</td></tr>'}</tbody></table></div></div>
 <div class="table-card default-changes"><div class="table-heading"><h2>Cambios de valores de fábrica <span>${defaultChanges.length}</span></h2></div>${defaultChanges.length?`<div class="table-scroll"><table><thead><tr><th>Ajuste / dato</th><th>FW ${state.compareFrom}</th><th>FW ${state.compareTo}</th></tr></thead><tbody>${defaultChanges.map(d=>`<tr><td><strong>${esc(d.label)}</strong><p class="cell-note">${esc(d.meaning)}</p></td><td class="value-cell">${esc(formatValue(d.values_by_version[state.compareFrom],d.unit))}</td><td class="value-cell">${esc(formatValue(d.values_by_version[state.compareTo],d.unit))}</td></tr>`).join('')}</tbody></table></div>`:'<p class="empty-table">Los valores de fábrica documentados son iguales para este par de versiones.</p>'}</div><p class="scope-note">${icon('info')}Actualizar conserva los ajustes válidos existentes. Los valores de fábrica no son una lectura del equipo.</p></section>`;
}
function defaults(){
 const configurable=new Set(commands.map(c=>c.default_setting_key).filter(Boolean));
 const defs=data.factory_defaults.filter(d=>(state.defaultType==='all'||(state.defaultType==='settings'?configurable.has(d.key):!configurable.has(d.key)))&&normalize(d.label+' '+d.meaning+' '+d.key).includes(normalize(state.defaultsQ)));
 return `<section class="defaults-view"><div class="notice info defaults-notice">${icon('info')}<div><strong>Valores de fábrica, no valores actuales.</strong><p>Una actualización conserva la configuración válida existente. Sensores, contadores y señales cambian durante el arranque y la operación.</p></div></div><div class="defaults-controls"><label class="search-field" for="defaults-search">${icon('search')}<input type="search" id="defaults-search" data-buscar aria-label="Buscar valores de fábrica" placeholder="Buscar un ajuste o estado…" value="${esc(state.defaultsQ)}"></label><div class="segmented" role="group" aria-label="Tipo de valor">${[['all','Todos'],['settings','Ajustes'],['states','Estados y constantes']].map(([id,label])=>`<button data-default-type="${id}" class="${state.defaultType===id?'active':''}" aria-pressed="${state.defaultType===id}">${label}</button>`).join('')}</div></div><div class="defaults-heading"><h2>${defs.length} valores documentados</h2><span>R1 HW3.0 · FW${state.fw}</span></div><div class="default-grid">${defs.length?defs.map(d=>{const c=commands.find(c=>c.default_setting_key===d.key&&c.kind!=='query'),v=d.values_by_version[state.fw];return `<article class="default-card"><div class="default-card-head"><span class="default-card-category">${configurable.has(d.key)?'AJUSTE':'ESTADO / CONSTANTE'}</span>${v===null?'<span class="badge unavailable-label">Sin ajuste en esta versión</span>':''}</div><h3>${esc(d.label)}</h3><div class="factory-value ${v===null?'not-available':''}">${v===null?'—':esc(v)}${v!==null&&d.unit?`<small>${d.unit}</small>`:''}</div><p>${esc(d.meaning)}</p>${c&&v!==null?`<button class="text-button" data-jump="${c.id}">Ver comando ${icon('arrow')}</button>`:`<span class="default-card-foot">${v===null?'No está disponible como ajuste en esta versión.':'Dato de referencia · sin comando de edición propio.'}</span>`}</article>`;}).join(''):'<div class="empty"><h3>No hay coincidencias.</h3><p>Prueba con otro término o tipo de valor.</p><button class="button" data-action="reset-defaults">Limpiar filtros</button></div>'}</div></section>`;
}
function render(){
 const focusId=document.activeElement?.id,start=document.activeElement?.selectionStart,end=document.activeElement?.selectionEnd,listScroll=app.querySelector('.command-list')?.scrollTop||0,detailScroll=app.querySelector('.detail-scroll')?.scrollTop||0;
 const navNames={explore:'Comandos',compare:'Comparar firmware',defaults:'Valores de fábrica'};
 el('app').innerHTML=`<div class="commands-heading"><div><span class="eyebrow">R1 · CATÁLOGO DE REFERENCIA</span><h2>${navNames[state.view]}</h2></div><button class="button small" data-action="guide">${icon('book')}Guía rápida</button></div>${sidebar()}${header()}${state.hw==='other'?emptyState():state.view==='explore'?explore():state.view==='compare'?comparison():defaults()}`;
 const listNode=app.querySelector('.command-list');if(listNode)listNode.scrollTop=listScroll;
 const detailNode=app.querySelector('.detail-scroll');if(detailNode&&lastSelection===state.selected)detailNode.scrollTop=detailScroll;
 lastSelection=state.selected;
 if(state.view==='explore'&&state.hw==='3.0'&&commandById[state.selected])refreshBuilder();
 if(focusId&&el(focusId)){el(focusId).focus({preventScroll:true});if(start!==null&&start!==undefined)try{el(focusId).setSelectionRange(start,end);}catch{}}
 updateURL();
}
function refreshBuilder(){
 const c=commandById[state.selected];if(!c)return;const value=valueFor(c),delivery=deliveryFor(c,value),error=delivery.error,kind=operationKind(c,value),care=careNote(c,value);
 el('validation-error').textContent=error;el('validation-error').hidden=!error;
 el('copy-command').disabled=!!error||!supported(c,state.hw,state.fw);
 el('payload-content').textContent=delivery.preview;
 el('operation-badge').innerHTML=badge(kind);
 el('care-note').innerHTML=care?`<div class="notice ${kind==='destructive'?'danger':'caution'}">${icon('warning')}<p>${esc(care)}</p></div>`:'';
 el('related-commands').innerHTML=relatedHTML(c,value)||'<span class="micro-copy">Explora más comandos en las categorías.</span>';
 el('delivery-label').textContent=delivery.label;
 el('terminator-label').textContent=delivery.includeCRLF?'CON CRLF':'SIN CRLF';
 el('terminator-symbol').textContent=delivery.includeCRLF?'\\r\\n':'';
 el('copy-helper').textContent=delivery.helper;
 if(c.input==='time'){
  el('nominal-value').innerHTML=error?'—':`${4+Number(value)}<small> s</small>`;
  el('extra-equation').textContent=error?'—':value;
  el('track-extra').style.flex=error?'0':String(Number(value));el('track-extra').style.display=error||!Number(value)?'none':'flex';
 }
}
function toast(message){if(active)ctx.toast(message);}
async function copyText(text,message){
 try{await navigator.clipboard.writeText(text);toast(message);return true;}catch{
  if(text.includes('\r\n')){toast('Este navegador no pudo copiar con CRLF. Desmarca esa opción y añade el terminador en tu aplicación de envío.');return false;}
  const t=document.createElement('textarea');t.value=text;t.style.position='fixed';t.style.opacity='0';document.body.append(t);t.select();let ok=false;try{ok=document.execCommand('copy');}catch{}t.remove();toast(ok?message:'No se pudo copiar. Selecciona el texto del comando y cópialo manualmente.');return ok;
 }
}
function resetFilters(){Object.assign(state,{q:'',group:'all',kind:'all',channel:'all',compatible:true,newOnly:false,favoriteOnly:false});}
function jump(id,fromRelated=false){
 const previous=state.selected;
 if(fromRelated){if((previous===7&&id===9)||(previous===9&&id===7))values[id]=valueFor(commandById[previous]);const map={30:['13','2'],31:['13','0'],32:['14','2'],33:['14','0'],34:['7','1'],35:['7','0']};if(map[previous]&&Number(map[previous][0])===id)values[id]=map[previous][1];}
 resetFilters();state.view='explore';state.selected=id;state.compatible=supported(commandById[id],state.hw,state.fw);state.menuOpen=false;render();
 requestAnimationFrame(()=>{app.querySelector('.command-row.selected')?.scrollIntoView({block:'nearest',behavior:'smooth'});if(matchMedia('(max-width: 760px)').matches)app.querySelector('.detail-panel')?.scrollIntoView({block:'start',behavior:'smooth'});});
}
function showGuide(){
 const dialog=el('guide-dialog');dialog.innerHTML=`<div class="guide-header"><div><div class="eyebrow">R1 · GUÍA RÁPIDA</div><h2 id="guide-title">Encuentra. Entiende. Prepara.</h2></div><button class="icon-button" data-close-dialog aria-label="Cerrar guía">${icon('close')}</button></div><div class="guide-content"><p class="guide-intro">Un catálogo interactivo para consultar la documentación de tu equipo y preparar comandos con sus parámetros.</p><div class="guide-steps"><div><span class="step">1</span><div><h3>Identifica tu tarjeta y su firmware</h3><p><strong>HW</strong> es la versión del hardware; <strong>FW</strong>, la del programa interno. Consulta VER y HW en el estado del equipo. El nombre de un archivo HEX no sustituye la versión interna.</p></div></div><div><span class="step">2</span><div><h3>Busca lo que quieres hacer</h3><p>Escribe «abrir», «tiempo» o parte del comando. Filtra por canal, función y tipo de operación. La estrella guarda una referencia en este navegador.</p></div></div><div><span class="step">3</span><div><h3>Lee y prepara el valor</h3><p>La ficha explica el efecto, los valores admitidos y el predeterminado de la versión. El constructor muestra un ejemplo editable, no el valor actual de una unidad. Elige el formato de envío junto al botón de copia: Plataforma es la opción inicial.</p></div></div></div><h3 class="guide-subtitle">Elige cómo preparar el comando</h3><div class="transport-cards"><div class="platform-card">${icon('route')}<strong>Plataforma · opción predeterminada</strong><code>AT$SMSG=1,0,"ON"</code><p>Los comandos $SMSG= se preparan con el formato de plataforma indicado para esta sección. El valor elegido se actualiza dentro de las comillas. Se copian sin CRLF.</p></div><div>${icon('cable')}<strong>Serial / GPS</strong><code>$SMSG=ON</code><p>Respeta mayúsculas y minúsculas. CRLF está desactivado inicialmente; puedes activarlo para copiar un terminador real o añadirlo desde tu aplicación de envío. El acuse $OK conserva este formato.</p></div><div>${icon('bluetooth')}<strong>Bluetooth</strong><code>PC_?</code><p>Cuatro caracteres exactos, sin CRLF. El ESP32 añade el terminador al reenviar. Los comandos largos $SMSG no pasan por este puente.</p></div></div><div class="notice info">${icon('info')}<p><strong>Esta sección prepara comandos; no se conecta al hardware.</strong> Las respuestas descritas son documentación, no lecturas de un equipo.</p></div><h3 class="guide-subtitle">Qué está documentado</h3><p>Los archivos cubren <strong>R1 HW3.0</strong>, <strong>FW4.1 a FW4.4</strong>, ${commands.length} filas de comandos y ${data.factory_defaults.length} valores o estados de fábrica. La matriz documenta presencia en código y no certifica pruebas físicas de todos los comandos. No hay información de otros HW ni de FW4.0 o anteriores.</p><p>Los valores de fábrica no se aplican de nuevo por actualizar. Una actualización conserva la configuración válida existente. El esquema EEPROM es una versión de datos distinta del firmware.</p><div class="source-downloads"><a href="#" data-download="catalog">${icon('download')}Catálogo JSON original</a><a href="#" data-download="reference">${icon('download')}Notas técnicas originales</a></div><p class="micro-copy">Fuente de las fichas y comparaciones: comandos_r1_por_version.json y COMANDOS_R1.md proporcionados para esta sección. El formato AT$SMSG de plataforma fue proporcionado para esta revisión.</p></div><div class="guide-bottom"><button class="button primary" data-close-dialog>Entendido, explorar ${icon('arrow')}</button></div>`;
 dialog.showModal();dialog.querySelector('[data-close-dialog]').focus();
}
el('guide-dialog').addEventListener('click',async e=>{if(e.target.closest('[data-close-dialog]'))el('guide-dialog').close();const d=e.target.closest('[data-download]');if(d){e.preventDefault();const key=d.dataset.download;const raw=key==='catalog'?JSON.stringify(data,null,2):await fetch('/static/catalogos/COMANDOS_R1.md',{signal:controller.signal}).then(r=>{if(!r.ok)throw new Error('Referencia no disponible');return r.text();});const url=URL.createObjectURL(new Blob([raw],{type:key==='catalog'?'application/json':'text/markdown'}));const a=document.createElement('a');a.href=url;a.download=key==='catalog'?'comandos_r1_por_version.json':'COMANDOS_R1.md';a.click();setTimeout(()=>URL.revokeObjectURL(url),2000);}});
el('app').addEventListener('click',async e=>{
 if(e.target.closest('.brand')){e.preventDefault();resetFilters();state.view='explore';state.selected=6;render();return;}const b=e.target.closest('button');if(!b||b.disabled)return;
 if(b.dataset.view){state.view=b.dataset.view;if(state.view==='compare'){state.compareTo=state.fw;state.compareFrom=VERSIONS[Math.max(0,VERSIONS.indexOf(state.fw)-1)];}state.menuOpen=false;render();return;}
 if(b.dataset.group){state.view='explore';state.group=b.dataset.group;state.menuOpen=false;state.q='';render();return;}
 if(b.dataset.channel){state.channel=b.dataset.channel;render();return;}
 if(b.dataset.outputFormat){state.outputFormat=b.dataset.outputFormat;if(state.outputFormat!=='serial')state.includeCRLF=false;render();return;}
 if(b.dataset.select!==undefined){state.selected=Number(b.dataset.select);render();if(matchMedia('(max-width: 760px)').matches)app.querySelector('.detail-panel')?.scrollIntoView({behavior:'smooth',block:'start'});return;}
 if(b.dataset.favorite!==undefined){const id=Number(b.dataset.favorite);favorites=favorites.includes(id)?favorites.filter(x=>x!==id):[...favorites,id];let persisted=true;try{localStorage.setItem('tqt.comandos.r1.favorites.v1',JSON.stringify(favorites));}catch{persisted=false;}render();toast(persisted?(favorites.includes(id)?'Comando guardado en este navegador.':'Comando retirado de guardados.'):'Guardado durante esta sesión. El navegador no permite conservarlo.');return;}
 if(b.dataset.related!==undefined){jump(Number(b.dataset.related),true);return;}
 if(b.dataset.jump!==undefined){if(state.view==='compare')state.fw=state.compareTo;jump(Number(b.dataset.jump));return;}
 if(b.dataset.defaultType){state.defaultType=b.dataset.defaultType;render();return;}
 if(b.dataset.intent){resetFilters();if(b.dataset.intent==='status'){state.group='status';state.selected=2;}if(b.dataset.intent==='time'){state.group='movement';state.selected=6;}if(b.dataset.intent==='protection'){state.group='protection';state.selected=8;}if(b.dataset.intent==='new'){state.view='compare';state.compareTo=state.fw;state.compareFrom=VERSIONS[Math.max(0,VERSIONS.indexOf(state.fw)-1)];}render();return;}
 const action=b.dataset.action;
 if(action==='reload')location.reload();
 if(action==='menu'){state.menuOpen=!state.menuOpen;render();}
 if(action==='guide')showGuide();
 if(action==='favorites'){state.favoriteOnly=!state.favoriteOnly;render();}
 if(action==='reset-filters'){resetFilters();render();}
 if(action==='protection-changes'){state.view='compare';state.compareFrom=state.fw;state.compareTo='4.4';state.fw='4.4';render();}
 if(action==='reset-defaults'){state.defaultsQ='';state.defaultType='all';render();}
 if(action==='known-hw'){state.hw='3.0';render();}
 if(action==='swap-versions'){[state.compareFrom,state.compareTo]=[state.compareTo,state.compareFrom];state.fw=state.compareTo;render();}
 if(action==='share'){updateURL();await copyText(location.href,'Enlace a esta ficha copiado.');}
 if(action==='copy'){
  const c=commandById[state.selected],delivery=deliveryFor(c);if(delivery.error||!supported(c,state.hw,state.fw))return;
  const ok=await copyText(delivery.text,delivery.copied);
  if(ok){b.innerHTML=icon('check')+'Copiado';setTimeout(()=>{if(b.isConnected)b.innerHTML=icon('copy')+'Copiar comando';},1800);}
 }
});
el('app').addEventListener('input',e=>{
 const target=e.target;
 if(target.id==='search'){state.q=target.value;render();}
 if(target.id==='defaults-search'){state.defaultsQ=target.value;render();}
 if(['param-value','param-number','param-range'].includes(target.id)){
  values[state.selected]=target.value;
  if(target.id==='param-range')el('param-number').value=target.value;
  if(target.id==='param-number')el('param-range').value=target.value;
  refreshBuilder();updateURL();
 }
 if(target.id==='other-separator'){otherSeparators[state.selected]=target.value;refreshBuilder();updateURL();}
});
el('app').addEventListener('change',e=>{
 const t=e.target,mapping={'hardware':'hw','firmware':'fw','kind-filter':'kind','compare-from':'compareFrom','compare-to':'compareTo'};
 if(mapping[t.id]){state[mapping[t.id]]=t.value;if(t.id==='firmware'&&state.view==='compare')state.compareTo=t.value;if(t.id==='compare-to')state.fw=t.value;render();}
 if(t.id==='compatible'){state.compatible=t.checked;render();}
 if(t.id==='new-only'){state.newOnly=t.checked;render();}
 if(t.id==='changes-only'){state.changesOnly=t.checked;render();}
 if(t.id==='include-crlf'){state.includeCRLF=t.checked;refreshBuilder();updateURL();}
});
app.addEventListener('keydown',e=>{
 if(!e.defaultPrevented&&e.key==='/'&&!['INPUT','TEXTAREA','SELECT'].includes(document.activeElement.tagName)&&!el('guide-dialog').open){e.preventDefault();(el('search')||el('defaults-search'))?.focus();}
 if(e.key==='Escape'&&state.menuOpen){state.menuOpen=false;render();}
});
(async()=>{try{
 data=await catalogPromise; if(!active)return;VERSIONS=data.firmware_versions; commands=enrich(data);commandById=Object.fromEntries(commands.map(c=>[c.id,c]));applyParams(ctx.params());
 if(!Number.isInteger(state.selected)||!commandById[state.selected])state.selected=6;
 if(!supported(commandById[state.selected],state.hw,state.fw))state.compatible=false;
 render();
 const initialList=app.querySelector('.command-list'),initialRow=app.querySelector('.command-row.selected');
 if(initialList&&initialRow)initialList.scrollTop=Math.max(0,initialRow.getBoundingClientRect().top-initialList.getBoundingClientRect().top-180);
}catch(error){if(!active)return;el('app').innerHTML=`<div class="load-error"><h1>No pudimos cargar el catálogo.</h1><p>Vuelve a abrir la página para cargar los datos de referencia.</p><button class="button primary" data-action="reload">Reintentar</button></div>`;console.error(error);}


})();
return {parametros(q){if(commands){applyParams(q);render();}},desmontar(){active=false;controller.abort();dialog.close();dialog.remove();clearTimeout(toastTimer);}};

}
});
})();
