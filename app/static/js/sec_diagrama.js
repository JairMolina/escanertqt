/* Native console reference section. The supplied standalone shell is not embedded. */
(function(){
'use strict';
let cached;
const KEY='tqt.diagrama.review.v1';
const VIEWS=[['explore','Conexiones'],['overview','Vista general'],['compare','Comparar HW'],['checklist','Revisión local']];
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
window.TQTEscritorio.registrar({id:'diagrama',titulo:'Diagrama',icono:'link',grupo:'gestion',orden:120,
montar(host,ctx){
 const {matches,comparisonRows,cleanReviews,reviewExport}=window.TQTDiagram;
 const app=ctx.h('div',{class:'tqt-diagrama diag-root'},ctx.h('p',{role:'status'},'Cargando diagrama TQT…'));
 const dialog=ctx.h('dialog',{class:'tqt-diagrama diag-dialog','aria-labelledby':'diag-dialog-title'});
 host.append(app,dialog);
 const abort=new AbortController();
 let alive=true,data,reviews={'20':[],'30':[]},storageOK=true,sourcePage=null,sourceZoom=1,opener=null;
 const urls=new Set(),state={hw:'30',view:'explore',group:'power',wire:'power-12',q:'',zoom:1,labels:true,changesOnly:true,reviewFilter:'all'};
 const rows=()=>data.wires[state.hw];
 const group=()=>data.groups.find(g=>g.id===state.group);
 const filtered=()=>rows().filter(w=>matches(w,state.q,data.groups));
 const current=()=>rows().find(w=>w.id===state.wire);
 const done=id=>reviews[state.hw].includes(id);
 const color=w=>`<span class="diag-swatch" style="--wire:${esc(/^#[0-9a-f]{3,8}$/i.test(w.colorHex)?w.colorHex:'#7f8a9e')}" aria-hidden="true"></span><span>${esc(w.colorName)}</span>`;
 const sourceButton=(page,caption='Ver lámina original')=>`<button type="button" class="btn btn-sm" data-source="${Number(page)}">${caption}</button>`;
 function focusKey(node){return node?{node,id:node.id||null,wire:node.dataset?.wire||null}:null;}
 function restoreFocus(key){
  if(!key)return;
  if(key.node?.isConnected){key.node.focus({preventScroll:true});return;}
  if(!key.id&&!key.wire)return;
  const node=key.id?app.querySelector('#'+CSS.escape(key.id)):app.querySelector('.diag-canvas [data-wire="'+CSS.escape(key.wire)+'"]');
  node?.focus({preventScroll:true});
 }
 function applyParams(q){
  state.hw=q.get('hw')==='20'?'20':'30';state.view=VIEWS.some(v=>v[0]===q.get('vista'))?q.get('vista'):'explore';
  state.group=data.groups.some(g=>g.id===q.get('grupo'))?q.get('grupo'):'power';
  const wire=rows().find(w=>w.id===q.get('cable'));state.wire=wire?.id||rows().find(w=>w.groupId===state.group)?.id;
  if(wire)state.group=wire.groupId;state.q=q.get('q')||'';state.zoom=1;
 }
 function sync(){
  const q=new URLSearchParams({hw:state.hw,vista:state.view,grupo:state.group,cable:state.wire||''});
  if(state.q)q.set('q',state.q);history.replaceState(history.state,'','#/diagrama?'+q);
 }
 function persist(){
  try{localStorage.setItem(KEY,JSON.stringify(reviews));storageOK=true;}catch{storageOK=false;}
 }
 function ensureSelection(){
  const found=filtered();if(!found.length)return;
  if(!found.some(w=>w.groupId===state.group))state.group=found[0].groupId;
  if(!found.some(w=>w.id===state.wire&&w.groupId===state.group))state.wire=found.find(w=>w.groupId===state.group).id;
 }
 function toggleReview(id){
  if(!rows().some(w=>w.id===id))return;
  reviews[state.hw]=done(id)?reviews[state.hw].filter(x=>x!==id):[...reviews[state.hw],id];persist();render();
 }
 function toolbar(){
  return `<div class="diag-heading"><div><p class="label">CABLEADO TQT</p><h2>Conexiones por hardware</h2><p class="hint">Consulta grupos, colores y destinos de R1, R2 y R3.</p></div><button class="btn" type="button" data-action="guide">Cómo leer el diagrama</button></div>
   <div class="diag-toolbar"><div class="diag-hw" role="group" aria-label="Hardware del diagrama">${['20','30'].map(hw=>`<button id="diag-hw-${hw}" class="btn ${state.hw===hw?'btn-primary':''}" type="button" data-hw="${hw}" aria-pressed="${state.hw===hw}">HW ${hw}</button>`).join('')}</div>
   <label class="diag-search" for="diag-search"><span class="sr-only">Buscar color, señal o destino</span><input class="input" id="diag-search" type="search" value="${esc(state.q)}" placeholder="Buscar color, señal o destino" autocomplete="off" data-buscar></label>
   <span class="diag-count mono" role="status">${reviews[state.hw].length} / ${rows().length} referencias revisadas</span></div>
   <nav class="diag-tabs" aria-label="Vistas del diagrama">${VIEWS.map(([id,label])=>`<button id="diag-view-${id}" class="btn ${state.view===id?'diag-active':''}" type="button" data-view="${id}" aria-pressed="${state.view===id}">${label}</button>`).join('')}</nav>
   ${storageOK?'':'<p class="diag-notice" role="status">No se pudo guardar en este navegador. Las marcas solo durarán esta sesión; puedes exportarlas.</p>'}`;
 }
 function groups(){
  const found=filtered();
  return `<nav class="diag-groups" aria-label="Grupos de conexiones">${data.groups.map(g=>{
   const n=found.filter(w=>w.groupId===g.id).length;
   return `<button type="button" class="diag-group" id="diag-group-${esc(g.id)}" data-group="${esc(g.id)}" aria-pressed="${state.group===g.id}" ${n?'':'disabled'}><span>${esc(g.shortTitle)}</span><b class="mono">${n}</b></button>`;
  }).join('')}</nav>`;
 }
 function wireList(items){
  return `<div class="diag-wire-list" aria-label="Conexiones de ${esc(group()?.shortTitle)}">${items.map(w=>`<button type="button" id="diag-wire-${esc(w.id)}" class="diag-wire" data-select="${esc(w.id)}" aria-pressed="${state.wire===w.id}"><span class="diag-color">${color(w)}</span><strong>${esc(w.shortLabel)}</strong><span>${esc(w.destination)}</span><small>${done(w.id)?'Revisada':'Pendiente'}${w.optional?' · Opcional':''}</small></button>`).join('')}</div>`;
 }
 function inspector(w){
  return `<aside class="diag-card diag-inspector" aria-label="Detalle de la conexión" aria-live="polite"><p class="label">CONEXIÓN SELECCIONADA</p><h3>${esc(w.shortLabel)}</h3><p class="diag-color">${color(w)}</p><dl class="diag-dl"><dt>Grupo</dt><dd>${esc(group().shortTitle)}</dd><dt>Señal</dt><dd>${esc(w.signal)}</dd><dt>Destino</dt><dd>${esc(w.destination)}</dd><dt>Referencia</dt><dd>HW ${state.hw} · lámina ${Number(w.sourcePage)}</dd></dl>
   ${w.optional?'<span class="diag-tag">Conexión opcional</span>':''}${w.changed?'<span class="diag-tag">Diferencia entre HW</span>':''}
   <p>${esc(w.description)}</p><div class="diag-check"><strong>Al revisar</strong><p>${esc(w.check)}</p></div>
   ${w.sourceNote?`<p class="hint">${esc(w.sourceNote)}</p>`:''}<details class="diag-quote"><summary>Texto de la fuente</summary><blockquote>${esc(w.sourceText)}</blockquote></details>
   <div class="diag-actions">${sourceButton(w.sourcePage)}<button type="button" class="btn btn-sm" data-action="copy">Copiar conexión</button></div>
   <label class="diag-review"><input id="diag-review-selected" type="checkbox" data-review="${esc(w.id)}" ${done(w.id)?'checked':''}> Marcar referencia como revisada</label><p class="hint">Solo en este navegador. No registra una prueba de producción.</p></aside>`;
 }
 function explore(){
  const found=filtered(),items=found.filter(w=>w.groupId===state.group);
  if(!found.length)return `${groups()}<div class="diag-card diag-empty"><h3>Sin coincidencias</h3><p>Prueba con otro color, grupo, señal o destino.</p><button type="button" class="btn" data-action="clear-search">Limpiar búsqueda</button></div>`;
  const w=current();
  return `${groups()}<div class="diag-explorer"><div class="diag-card"><div class="diag-panel-heading"><div><h3>${esc(group().title)}</h3><p class="hint">${esc(group().subtitle)}</p></div><div class="diag-actions"><button class="btn btn-sm" type="button" data-action="zoom-out" aria-label="Reducir esquema" ${state.zoom<=.75?'disabled':''}>−</button><button class="btn btn-sm" type="button" data-action="zoom-fit">${Math.round(state.zoom*100)} %</button><button class="btn btn-sm" type="button" data-action="zoom-in" aria-label="Ampliar esquema" ${state.zoom>=2?'disabled':''}>+</button></div></div>
   <p class="hint">${esc(group().description)}</p><div class="diag-canvas" tabindex="0" aria-label="Esquema de conexiones, desplazable horizontalmente"><div class="diag-drawing" style="width:${Math.round(state.zoom*100)}%">${window.TQTDiagramSVG({group:group(),wires:rows().filter(x=>x.groupId===state.group),selectedId:w.id,checkedIds:reviews[state.hw],hw:'HW '+state.hw,showLabels:state.labels,filterIds:items.map(x=>x.id)})}</div></div>
   <p class="hint diag-pan-hint">Desplaza el esquema horizontalmente para ver todos los destinos.</p><div class="diag-panel-heading"><label><input id="diag-labels" type="checkbox" ${state.labels?'checked':''}> Mostrar rótulos</label><span class="hint" role="status">${found.length} coincidencias · ${items.length} en este grupo</span></div>
   ${wireList(items)}<p class="hint">Esquema de lectura; la posición de las líneas no representa números de pin.</p></div>${inspector(w)}</div>`;
 }
 function pinTable(){
  return `<details class="diag-card diag-pins"><summary>Conector AK7V · referencia de pines y colores</summary><p class="hint">La tabla documenta pin y color. No asigna funciones eléctricas a esos pines.</p><div class="diag-pin-grid">${data.ak7v.map(p=>`<div><b class="mono">${p.pin}</b><span class="diag-color">${color({colorHex:p.hex,colorName:p.spanish})}</span><span class="hint">${esc(p.label)}</span></div>`).join('')}</div></details>`;
 }
 function overview(){
  const hw=data.meta.hardware[state.hw];
  return `<div class="diag-card"><div class="diag-panel-heading"><div><h3>Vista general · HW ${state.hw}</h3><p class="hint">${esc(hw.block)} · ${esc(data.meta.sourceName)}</p></div>${sourceButton(hw.overviewPage,'Abrir lámina completa')}</div><button type="button" class="diag-overview" data-source="${Number(hw.overviewPage)}" aria-label="Ampliar diagrama general HW ${state.hw}"><img src="${esc(data.assets.overview[state.hw])}" alt="Diagrama general de conexiones TQT HW ${state.hw}" loading="lazy"></button><p class="hint">Las fotografías de las tarjetas son referencias del documento; sus rótulos no sustituyen la selección de HW.</p></div>${pinTable()}`;
 }
 function compare(){
  let items=comparisonRows(data).filter(r=>[r.hw20,r.hw30].some(w=>w&&matches(w,state.q,data.groups)));
  if(state.changesOnly)items=items.filter(r=>r.status!=='same');
  const cell=(w,hw)=>w?`<div class="diag-color">${color(w)}</div><p>${esc(w.sourceText)}</p>${sourceButton(w.sourcePage,'Lámina HW '+hw)}`:'<span class="hint">No aparece en este bloque de la fuente.</span>';
  return `<div class="diag-card"><div class="diag-panel-heading"><div><h3>Comparación HW20 / HW30</h3><p class="hint">Se comparan los rótulos y colores documentados; no se deducen conexiones nuevas.</p></div><label><input id="diag-changes" type="checkbox" ${state.changesOnly?'checked':''}> Solo diferencias</label></div><div class="diag-table-wrap" tabindex="0" aria-label="Comparación de hardware, desplazable"><table class="diag-table"><caption class="sr-only">Conexiones por hardware</caption><thead><tr><th scope="col">Referencia</th><th scope="col">HW20</th><th scope="col">HW30</th></tr></thead><tbody>${items.map(r=>`<tr><th scope="row">${esc((r.hw20||r.hw30).shortLabel)}<small>${({same:'Sin cambio',changed:'Cambio de rótulo o color',only20:'Solo en HW20',only30:'Solo en HW30'})[r.status]}</small></th><td>${cell(r.hw20,'20')}</td><td>${cell(r.hw30,'30')}</td></tr>`).join('')}</tbody></table>${items.length?'':'<p class="diag-empty">Sin coincidencias en esta comparación.</p>'}</div></div>`;
 }
 function checklist(){
  const found=filtered().filter(w=>state.reviewFilter==='all'||(state.reviewFilter==='done'?done(w.id):!done(w.id)));
  return `<div class="diag-card"><div class="diag-panel-heading"><div><h3>Revisión local · HW ${state.hw}</h3><p class="hint">${reviews[state.hw].length} de ${rows().length} referencias. Las marcas son personales de este navegador y no aprueban tarjetas.</p></div><div class="diag-actions"><button class="btn btn-sm" type="button" data-action="export">Exportar revisión</button><button class="btn btn-sm" type="button" data-action="reset">Reiniciar HW ${state.hw}</button></div></div><label for="diag-review-filter">Mostrar <select class="input" id="diag-review-filter">${[['all','Todas'],['pending','Pendientes'],['done','Revisadas']].map(([v,l])=>`<option value="${v}" ${state.reviewFilter===v?'selected':''}>${l}</option>`).join('')}</select></label><div class="diag-checklist">${found.map(w=>`<div class="diag-check-row"><label><input id="diag-review-${esc(w.id)}" type="checkbox" data-review="${esc(w.id)}" ${done(w.id)?'checked':''}><span class="diag-color">${color(w)}</span><span><strong>${esc(w.shortLabel)}</strong><small>${esc(w.destination)}</small></span></label><button class="btn btn-sm" type="button" data-select="${esc(w.id)}">Ver conexión</button></div>`).join('')}</div>${found.length?'':'<p class="diag-empty">No hay referencias en este filtro.</p>'}</div>`;
 }
 function render(){
  if(!alive||!data)return;
  const focused=document.activeElement,key=focusKey(focused),selection=focused?.id==='diag-search'?[focused.selectionStart,focused.selectionEnd]:null;
  ensureSelection();app.innerHTML=toolbar()+({explore,overview,compare,checklist})[state.view]()+`<p class="diag-footnote">Fuente: ${esc(data.meta.sourceName)} · Selección por hardware, independiente del firmware y del lote. Los conteos de revisión se refieren a puntos de la leyenda, no a cables físicos únicos.</p>`;
  restoreFocus(key);if(selection&&document.activeElement?.id==='diag-search')document.activeElement.setSelectionRange(...selection);sync();
 }
 function closeDialog(){dialog.close();restoreFocus(opener);sourcePage=null;}
 function sourceBody(){
  const image=dialog.querySelector('img');if(image)image.style.width=Math.round(sourceZoom*100)+'%';
  const pct=dialog.querySelector('[data-source-zoom]');if(pct)pct.textContent=Math.round(sourceZoom*100)+' %';
 }
 function openSource(page,trigger){
  const path=data.assets.pages[String(page)];if(!path)return;opener=focusKey(trigger);sourcePage=page;sourceZoom=1;
  dialog.innerHTML=`<div class="diag-dialog-head"><h2 id="diag-dialog-title">Lámina ${Number(page)} · fuente original</h2><button class="btn" type="button" data-dialog-close autofocus>Cerrar</button></div><p class="hint">${esc(data.meta.sourceName)} · imagen incorporada al archivo de referencia.</p><div class="diag-actions"><button class="btn btn-sm" type="button" data-source-scale="-1" aria-label="Reducir lámina">−</button><span class="mono" data-source-zoom>100 %</span><button class="btn btn-sm" type="button" data-source-scale="1" aria-label="Ampliar lámina">+</button></div><div class="diag-source-scroll" tabindex="0" aria-label="Lámina original desplazable"><img src="${esc(path)}" alt="Lámina ${Number(page)} de ${esc(data.meta.sourceName)}"></div>`;
  dialog.showModal();
 }
 function guide(trigger){
  opener=focusKey(trigger);dialog.innerHTML=`<div class="diag-dialog-head"><h2 id="diag-dialog-title">Cómo leer el diagrama</h2><button class="btn" type="button" data-dialog-close autofocus>Cerrar</button></div><p>${esc(data.meta.scope)}</p><ol class="diag-guide"><li>Elige HW20 o HW30 y el grupo de conexiones.</li><li>Selecciona un cable por color o destino y contrasta su ficha con la lámina original.</li><li>Usa Comparar HW para ver diferencias y Revisión local para guardar tus marcas en este navegador.</li></ol><h3>Alcance de la referencia</h3><ul class="diag-guide">${data.limits.map(x=>`<li>${esc(x)}</li>`).join('')}</ul><p class="hint">Esta consulta no envía comandos ni registra resultados en Pruebas TQT.</p>`;dialog.showModal();
 }
 async function copyConnection(){
  const w=current();if(!w)return;
  const text=`TQT HW ${state.hw} · ${group().title}\n${w.colorName}: ${w.destination}\n${w.signal} · ${w.sourceText}\nFuente: ${data.meta.sourceName}, lámina ${w.sourcePage}`;
  try{await navigator.clipboard.writeText(text);if(alive)ctx.toast('Conexión copiada');}catch{if(alive)ctx.toast('No se pudo copiar. Puedes seleccionar el texto de la ficha.',{kind:'warn'});}
 }
 function exportReview(){
  const url=URL.createObjectURL(new Blob([JSON.stringify(reviewExport(data,reviews,state.hw),null,2)],{type:'application/json'}));urls.add(url);
  const a=document.createElement('a');a.href=url;a.download='TQT_Diagrama_HW'+state.hw+'_revision.json';a.click();
  setTimeout(()=>{URL.revokeObjectURL(url);urls.delete(url);},1000);
 }
 app.addEventListener('click',e=>{
  const el=e.target.closest('button,[data-wire]');if(!el||!data)return;
  if(el.dataset.hw){state.hw=el.dataset.hw;state.zoom=1;render();return;}
  if(el.dataset.view){state.view=el.dataset.view;state.q='';render();return;}
  if(el.dataset.group){state.group=el.dataset.group;state.wire=filtered().find(w=>w.groupId===state.group)?.id;state.zoom=1;render();return;}
  const id=el.dataset.select||el.dataset.wire;
  if(id&&rows().some(w=>w.id===id)){state.wire=id;state.group=rows().find(w=>w.id===id).groupId;state.view='explore';render();return;}
  if(el.dataset.source){openSource(Number(el.dataset.source),el);return;}
  const action=el.dataset.action;
  if(action==='guide'){guide(el);return;}if(action==='copy'){copyConnection();return;}if(action==='export'){exportReview();return;}
  if(action==='reset'){
   const hw=state.hw;ctx.sheet({title:'Reiniciar revisión local de HW '+hw,body:ctx.h('p',null,'Se quitarán las marcas de este hardware en este navegador. Las del otro hardware se conservarán.'),actions:[{label:'Reiniciar marcas',kind:'primary',onClick:()=>{if(alive){reviews[hw]=[];persist();render();}return true;}},{label:'Conservar',kind:'ghost',onClick:()=>true}]});return;
  }
  if(action==='clear-search')state.q='';
  if(action==='zoom-in')state.zoom=Math.min(2,state.zoom+.25);if(action==='zoom-out')state.zoom=Math.max(.75,state.zoom-.25);if(action==='zoom-fit')state.zoom=1;render();
 });
 app.addEventListener('input',e=>{if(e.target.id==='diag-search'){state.q=e.target.value;render();}});
 app.addEventListener('change',e=>{
  if(e.target.dataset.review){toggleReview(e.target.dataset.review);return;}
  if(e.target.id==='diag-labels')state.labels=e.target.checked;
  if(e.target.id==='diag-changes')state.changesOnly=e.target.checked;
  if(e.target.id==='diag-review-filter')state.reviewFilter=e.target.value;render();
 });
 app.addEventListener('keydown',e=>{if(e.target.closest('[data-wire]')&&['Enter',' '].includes(e.key)){e.preventDefault();e.target.closest('[data-wire]').dispatchEvent(new MouseEvent('click',{bubbles:true}));}});
 dialog.addEventListener('cancel',e=>{e.preventDefault();closeDialog();});
 dialog.addEventListener('click',e=>{
  if(e.target.closest('[data-dialog-close]')){closeDialog();return;}
  const scale=e.target.closest('[data-source-scale]');if(scale&&sourcePage){sourceZoom=Math.max(1,Math.min(3,sourceZoom+Number(scale.dataset.sourceScale)*.25));sourceBody();}
 });
 (async()=>{try{
  data=cached||await fetch('/static/catalogos/diagrama_tqt.json',{signal:abort.signal,cache:'no-cache'}).then(r=>{if(!r.ok)throw Error('Catálogo no disponible');return r.json();});
  if(!alive)return;cached=data;
  try{reviews=cleanReviews(JSON.parse(localStorage.getItem(KEY)||'{}'),data);}catch{storageOK=false;}
  applyParams(ctx.params());render();
 }catch(error){if(!alive)return;app.replaceChildren(ctx.T.banner('bad','alert','No se pudo cargar el diagrama. Vuelve a abrir esta sección para reintentar.'));}})();
 return {parametros(q){if(data){applyParams(q);render();}},actualizar(){if(data)render();},desmontar(){alive=false;abort.abort();dialog.close();dialog.remove();urls.forEach(url=>URL.revokeObjectURL(url));urls.clear();}};
}
});
})();
