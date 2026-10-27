/* Reference-only logic. No serial, Bluetooth, programming or production writes. */
(function(root){
'use strict';
const normalize=v=>String(v??'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/12\s*v(?:cd|dc)?/g,'12v').trim();
function matches(w,query,groups){
 const g=groups.find(x=>x.id===w.groupId)||{};
 const text=normalize([w.colorName,w.shortLabel,w.destination,w.signal,w.sourceText,w.sourceNote,g.title,g.subtitle,w.signal==='GND'?'tierra masa ground':'',w.colorName==='Café'?'marron brown':''].join(' '));
 return normalize(query).split(/\s+/).every(part=>text.includes(part));
}
function comparisonRows(data){
 const a=new Map(data.wires['20'].map(w=>[w.id,w])),b=new Map(data.wires['30'].map(w=>[w.id,w]));
 const fields=['colorName','colorHex','sourceText','signal','destination','optional'];
 return [...new Set([...a.keys(),...b.keys()])].map(id=>{
  const hw20=a.get(id),hw30=b.get(id);
  const changes=hw20&&hw30?fields.filter(k=>hw20[k]!==hw30[k]):[];
  return {id,hw20,hw30,changes,status:!hw20?'only30':!hw30?'only20':changes.length?'changed':'same'};
 });
}
function cleanReviews(value,data){
 const out={'20':[],'30':[]};
 for(const hw of ['20','30']){
  const allowed=new Set(data.wires[hw].map(w=>w.id));
  out[hw]=Array.isArray(value?.[hw])?[...new Set(value[hw].filter(id=>typeof id==='string'&&allowed.has(id)))]:[];
 }
 return out;
}
function reviewExport(data,reviews,hw,now=new Date()){
 const ids=new Set(cleanReviews(reviews,data)[hw]);
 return {format:'tqt-diagrama-review-v1',created_at:now.toISOString(),hardware:hw,source:data.meta.sourceName,source_sha256:data.provenance.html_sha256,
  scope:'Revisión local de referencia; no registra ni aprueba pruebas de producción.',
  total:data.wires[hw].length,reviewed:ids.size,
  connections:data.wires[hw].map(w=>({id:w.id,group:w.groupId,color:w.colorName,destination:w.destination,source_text:w.sourceText,source_page:w.sourcePage,reviewed:ids.has(w.id)}))};
}
const api={normalize,matches,comparisonRows,cleanReviews,reviewExport};
if(typeof module==='object'&&module.exports)module.exports=api;else root.TQTDiagram=api;
})(globalThis);
