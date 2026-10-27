const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto'),vm=require('node:vm');
const root=path.resolve(__dirname,'..'),data=JSON.parse(fs.readFileSync(path.join(root,'app/static/catalogos/diagrama_tqt.json'),'utf8'));
const core=require('../app/static/js/diagrama_core.js');
const stable=v=>Array.isArray(v)?'['+v.map(stable).join(',')+']':v&&typeof v==='object'?'{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+stable(v[k])).join(',')+'}':JSON.stringify(v);
const sha=value=>crypto.createHash('sha256').update(value).digest('hex');
test('reference content and all extracted illustrations retain their source hashes',()=>{
 const original={...data};delete original.assets;delete original.provenance;
 assert.equal(sha(stable(original)),data.provenance.data_sha256);
 assert.deepEqual(Object.fromEntries(Object.entries(data.wires).map(([hw,wires])=>[hw,wires.length])),{'20':19,'30':18});
 for(const [name,hash] of Object.entries(data.provenance.asset_sha256))assert.equal(sha(fs.readFileSync(path.join(root,'app/static/img/diagrama_tqt',name))),hash);
 assert.equal(Object.keys(data.provenance.asset_sha256).length,6);
});
test('groups, source pages and AK7V pins are complete and unambiguous',()=>{
 assert.equal(data.groups.length,6);const groups=new Set(data.groups.map(g=>g.id));
 for(const [hw,rows] of Object.entries(data.wires)){
  assert.equal(new Set(rows.map(w=>w.id)).size,rows.length);
  for(const w of rows){assert(groups.has(w.groupId));assert.equal(w.sourcePage,hw==='20'?3:6);assert(w.sourceText);}
 }
 assert.deepEqual(data.ak7v.map(p=>p.pin),Array.from({length:12},(_,i)=>i+1));
 assert.equal(data.ak7v.find(p=>p.pin===11).spanish,'Negro');
 assert(!data.ak7v.some(p=>'signal' in p||'destination' in p));
});
test('search tolerates accents, multiple terms, electrical aliases and voltage spacing',()=>{
 const rows=data.wires['30'];
 assert(core.matches(rows.find(w=>w.id==='power-gnd-green'),'tierra verde',data.groups));
 assert(core.matches(rows.find(w=>w.id==='motor-brown'),'marron motor',data.groups));
 assert(core.matches(rows.find(w=>w.id==='power-12'),'12 VCD',data.groups));
 assert(!core.matches(rows.find(w=>w.id==='gps-reset'),'verde GND',data.groups));
});
test('comparison preserves HW20-only lead and documented ambiguous colors',()=>{
 const rows=core.comparisonRows(data);
 assert.equal(rows.find(r=>r.id==='r3-extra-12').status,'only20');
 assert.equal(rows.find(r=>r.id==='power-gnd-change').status,'changed');
 assert.equal(rows.find(r=>r.id==='gps-reset').status,'same');
 const link=rows.find(r=>r.id==='r3-r2');assert.equal(link.status,'changed');
 assert.equal(link.hw20.colorName,'Claro (según dibujo)');assert.equal(link.hw30.colorName,'Gris oscuro');
 assert(link.hw20.sourceNote);assert(link.hw30.sourceNote);
});
test('review storage rejects unknown IDs, wrong hardware, duplicates and malformed values',()=>{
 const result=core.cleanReviews({'20':['power-12','power-12','unknown'],'30':['r3-extra-12','gps-reset',{},5]},data);
 assert.deepEqual(result,{'20':['power-12'],'30':['gps-reset']});
 for(const bad of [null,1,'x',false])assert.deepEqual(core.cleanReviews(bad,data),{'20':[],'30':[]});
});
test('export is a local reference review, not a production approval',()=>{
 const result=core.reviewExport(data,{'20':['r3-extra-12']},'20',new Date('2026-10-27T12:00:00Z'));
 assert.equal(result.hardware,'20');assert.equal(result.reviewed,1);assert.equal(result.total,19);
 assert.equal(result.created_at,'2026-10-27T12:00:00.000Z');assert.equal(result.source_sha256,data.provenance.html_sha256);
 assert(result.scope.includes('no registra ni aprueba'));assert.equal(result.connections.find(w=>w.id==='r3-extra-12').reviewed,true);
 assert.equal(result.connections.find(w=>w.id==='gps-reset').reviewed,false);
});
test('pure SVG renderer escapes labels/IDs and contains the exact group lead count',()=>{
 const context={window:{}};vm.createContext(context);vm.runInContext(fs.readFileSync(path.join(root,'app/static/js/diagrama_svg.js'),'utf8'),context);
 const group=data.groups.find(g=>g.id==='r3'),wires=data.wires['20'].filter(w=>w.groupId==='r3');
 const svg=context.window.TQTDiagramSVG({group,wires,hw:'HW20'});
 assert.equal((svg.match(/role="button"/g)||[]).length,5);assert(svg.includes('sin numeración de pines'));
 const dirty=context.window.TQTDiagramSVG({group:{id:'a',title:'<script>bad()</script>'},wires:[{id:'"<bad>',destination:'<img src=x>',colorHex:'url(evil)',colorName:'"unsafe'}],hw:'<bad>'});
 assert(!dirty.includes('<script>'));assert(!dirty.includes('<img'));assert(dirty.includes('&lt;script&gt;'));assert(!dirty.includes('stroke="url(evil)"'));
});
