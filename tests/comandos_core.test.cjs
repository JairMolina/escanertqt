/* Run with node --test tests/comandos_core.test.cjs (no npm dependencies). */
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const core=require('../app/static/js/comandos_core.js');
const catalog=JSON.parse(fs.readFileSync(path.join(__dirname,'../app/static/catalogos/comandos_r1.json'),'utf8'));
const commands=core.enrich(catalog);
const get=syntax=>commands.find(c=>c.command===syntax);
const state={hw:'3.0',fw:'4.4',q:'',compatible:true,channel:'all',group:'all',kind:'all',favoriteOnly:false,newOnly:false};

test('stable catalog IDs are unique and metadata survives array reorder',()=>{
 assert.equal(commands.length,37);
 assert.equal(catalog.factory_defaults.length,28);
 const reversed=core.enrich({...catalog,commands:[...catalog.commands].reverse()});
 assert.deepEqual(reversed.find(c=>c.id===6),commands.find(c=>c.id===6));
 assert.throws(()=>core.enrich({commands:[catalog.commands[0],catalog.commands[0]]}));
 for(const c of commands){assert.ok(c.title);assert.ok(core.GROUPS.some(g=>g.id===c.group));assert.ok(core.KIND_LABELS[c.kind]);}
});
test('platform conversion wraps SMSG only, with current parameter',()=>{
 assert.equal(core.buildPayload(get('$SMSG=ON'),'',false,'platform'),'AT$SMSG=1,0,"ON"');
 assert.equal(core.buildPayload(get('$SMSG=TIEMPO:n'),'0',false,'platform'),'AT$SMSG=1,0,"TIEMPO:0"');
 assert.equal(core.buildPayload(get('$SMSG=TIEMPO:n'),'8',false,'platform'),'AT$SMSG=1,0,"TIEMPO:8"');
 assert.equal(core.buildPayload(get('$SMSG=SPAS;c'),'|',false,'platform'),'AT$SMSG=1,0,"SPAS;|"');
 assert.equal(core.buildPayload(get('$SMSG=PROT_C:n'),'?',false,'platform'),'AT$SMSG=1,0,"PROT_C:?"');
});
test('CRLF is real, opt in, and only used for serial output',()=>{
 const on=get('$SMSG=ON');
 assert.equal(core.buildPayload(on,'',false,'serial'),'$SMSG=ON');
 assert.equal(core.buildPayload(on,'',true,'serial'),'$SMSG=ON\r\n');
 assert.equal(core.buildPayload(on,'',true,'platform'),'AT$SMSG=1,0,"ON"');
 for(const c of commands.filter(c=>c.channel==='Bluetooth')){
  for(const format of ['serial','platform']){
   const payload=core.buildPayload(c,'',true,format);
   assert.equal(payload.length,4);assert.equal(payload,c.example);
  }
 }
 const ack=get('$OK / OK');
 assert.equal(core.buildPayload(ack,'',false,'platform'),'$OK');
 assert.equal(core.buildPayload(ack,'',true,'platform'),'$OK\r\n');
});
test('all editable parameters validate and build current values',()=>{
 for(const c of commands.filter(c=>c.input!=='none')){
  const other=c.id===20?';':'|',value=core.initialValue(c);
  assert.equal(core.validateValue(c,value,other,'platform'),'',c.command);
  assert.ok(!/(:n|;n|:texto|;c)$/.test(core.buildPayload(c,value,false,'platform')));
 }
 for(const c of commands.filter(c=>['sensors','binary','mapping','output'].includes(c.input))){
  for(const v of ['0','1']){assert.equal(core.validateValue(c,v), '');assert.ok(core.buildPayload(c,v,false,'platform').includes(v));}
  assert.ok(core.validateValue(c,'2'));
 }
});
test('time bounds and malformed values',()=>{
 const time=get('$SMSG=TIEMPO:n');
 for(let n=0;n<=10;n++)assert.equal(core.validateValue(time,String(n)), '');
 for(const n of ['-1','11','1.2','','1x','1\n2'])assert.ok(core.validateValue(time,n));
});
test('name and separator validation prevents broken platform frames',()=>{
 const name=get('$SMSG=Nombre:texto'),sep=get('$SMSG=SPAS;c');
 assert.equal(core.validateValue(name,'A'.repeat(22),'','platform'),'');
 for(const value of ['','A'.repeat(23),'a\r\nb','a"b'])assert.ok(core.validateValue(name,value,'','platform'));
 for(const value of ['','ab','"',"'",'\n',';'])assert.ok(core.validateValue(sep,value,';'));
 assert.equal(core.validateValue(sep,'|',';'),'');
});
test('hardware, firmware, channel, group, type and text filters compose',()=>{
 assert.equal(core.filterCommands(commands,state).length,37);
 assert.equal(core.filterCommands(commands,{...state,hw:'other'}).length,0);
 assert.ok(!core.filterCommands(commands,{...state,fw:'4.1'}).some(c=>c.group==='mapping'||c.group==='protection'));
 assert.equal(core.filterCommands(commands,{...state,channel:'Bluetooth'}).length,10);
 assert.ok(core.filterCommands(commands,{...state,q:'proteccion',group:'protection',kind:'query'}).every(c=>c.group==='protection'&&c.kind==='query'));
 assert.equal(core.filterCommands(commands,{...state,q:'no-existe'}).length,0);
 assert.deepEqual(core.filterCommands(commands,{...state,favoriteOnly:true},[6]).map(c=>c.id),[6]);
 assert.ok(core.filterCommands(commands,{...state,newOnly:true}).every(c=>c.first==='4.4'));
});
test('comparison matches source-supported versions',()=>{
 const diff=core.compareCommands(commands,'4.3','4.4');
 assert.equal(diff.filter(c=>!c.inFrom&&c.inTo).length,6);
 assert.equal(diff.filter(c=>c.inFrom&&!c.inTo).length,0);
});
test('factory movement stays four seconds with no extra and protection off',()=>{
 const field=key=>catalog.factory_defaults.find(d=>d.key===key);
 for(const fw of catalog.firmware_versions){
  assert.equal(field('movement_base_ms').values_by_version[fw],4000);
  assert.equal(field('extra_seconds').values_by_version[fw],0);
 }
 assert.equal(field('overcurrent_stop').values_by_version['4.4'],0);
 assert.equal(field('overcurrent_stop').values_by_version['4.3'],null);
});
