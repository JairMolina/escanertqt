// QA aislada: las programaciones estan interceptadas y nunca llegan a agentes reales.
async (page) => {
 const BASE='http://127.0.0.1:18089',SID='111111111111111111111111';
 const c=await page.context().browser().newContext({viewport:{width:1440,height:1050}});
 const p=await c.newPage(),errors=[],posts=[],results=[];
 p.on('pageerror',e=>errors.push(e.message));
 const assert=(v,m)=>{if(!v)throw Error(m);};
 let source={source:'inventory',firmware:'4.3',hardware:'3.0',nombre:'TQT-R1-V30-0054',recorded_at:'2026-10-26 10:00:00',verified_at:null,job_id:null,uid:null,id_r:null,mac_r:null,current_unconfirmed:false,note:'Inventario de ensayo; sin lectura del STM32.'};
 let jobState='queued',lastPost=null,jobN=0;
 const job=()=>({id:'qa-state-'+jobN,station:SID,state:jobState,payload:{kind:'R1',firmware_id:lastPost.firmware_id,identity:{nombre:'TQT_R1_V30_0054',fw:'4.4',hw:'3.0'}},result:jobState==='verified'?{uid:'1234567890ABCDEF12345678'}:{error:'Fallo simulado sin nueva verificacion'}});
 await c.addInitScript(sid=>localStorage.setItem('tqt.station.stm32',sid),SID);
 await p.route('**/api/stm32/stations',r=>r.fulfill({json:[{id:SID,name:'QA sin hardware',online:true,local:true}]}));
 await p.route(/\/api\/stm32\/stations\/[^/]+\/jobs$/,r=>r.fulfill({json:[]}));
 await p.route('**/api/stm32/estado/*',r=>r.fulfill({json:{...source,kind:'R1',pcb_id:Number(r.request().url().split('/').pop())}}));
 await p.route('**/api/stm32/jobs',r=>{
   assert(r.request().method()==='POST','POST esperado');lastPost=r.request().postDataJSON();posts.push(lastPost);jobN++;return r.fulfill({json:job()});
 });
 await p.route(/\/api\/stm32\/jobs\/qa-state-\d+$/,r=>r.fulfill({json:job()}));
 try {
  await p.goto(BASE+'/login');await p.locator('#email').fill('developer4@skyguardian.mx');await p.locator('#pass').fill('prueba-beta-local');
  await p.getByRole('button',{name:'Entrar',exact:true}).click();await p.waitForURL(u=>!u.pathname.endsWith('/login'));
  await p.goto(BASE+'/monitor#/programacion');await p.waitForTimeout(600);await p.getByRole('button',{name:'TQT R1',exact:true}).click();
  await p.getByRole('button').filter({hasText:'TQT-R1-V30-0054'}).click();
  const root=p.locator('#stm-r1-est').locator('..').locator('..'),select=p.locator('#stm-r1-fw'),right=root.locator('.prog-estado'),left=root.locator('.prog-datos');
  const options=await select.locator('option').evaluateAll(xs=>xs.map(x=>({id:x.value,text:x.textContent})));
  const old=options.find(x=>x.text.includes('FW 4.3 ')).id,newer=options.find(x=>x.text.includes('FW 4.4 ')).id;
  const selectFw=async value=>{await select.selectOption(value);await p.waitForTimeout(250);};
  await selectFw(old);const before=await right.innerText();
  await selectFw(newer);assert((await left.innerText()).includes('4.4'),'Izquierda toma4.4');assert(await right.innerText()===before,'Derecha inventario4.3 no cambia');
  await selectFw(old);assert(await right.innerText()===before,'Derecha tampoco cambia al volver4.3');assert(posts.length===0,'Cambiar seleccion no programa');
  results.push('inventario fijo al alternar4.3/4.4 sin grabar');
  source={...source,source:'none',firmware:null,recorded_at:null,note:'Sin datos confirmados.'};await selectFw(newer);
  assert((await right.locator('.prog-luz-txt').textContent())==='Sin verificar','Sin datos no anunciar programada');
  assert(!(await right.innerText()).includes('FW 4.4'),'No inferir firmware seleccionado');results.push('sin datos muestra sin verificar');
  source={...source,source:'verified_programming',firmware:'4.3',nombre:'TQT_R1_V30_0054',verified_at:1793023200,uid:'1234567890ABCDEF12345678',id_r:'0040',mac_r:'02:00:00:00:00:40',note:'Ultima imagen verificada; no lectura en vivo.'};
  await selectFw(old);const verifiedBefore=await right.innerText();await selectFw(newer);
  assert(await right.innerText()===verifiedBefore,'Lectura anterior4.3 no reemplazada por4.4 seleccionada');
  assert(verifiedBefore.includes('0040'),'Mostrar pareja archivada, no la prevista0054');results.push('identidad verificada archivada independiente');
  const program=p.getByRole('button',{name:'Programar R1 0054 con J-Link',exact:true});
  await program.click();await p.waitForTimeout(250);assert((await right.innerText()).includes('FW 4.3'),'En proceso aun no atribuir4.4');
  source={...source,current_unconfirmed:true,note:'Intento posterior sin verificar.'};jobState='failed';
  await p.waitForFunction(()=>document.querySelector('#stm-r1-est').closest('.prog-panel').querySelector('.prog-luz-txt').textContent==='Sin verificación actual');
  assert((await right.innerText()).includes('FW 4.3'),'Fallo mantiene ultimo FWverificado');assert(!(await right.innerText()).includes('FW 4.4'),'Fallo no actualiza4.4');
  results.push('fallo no acredita firmware nuevo');
  jobState='queued';await program.click();await p.waitForTimeout(200);
  source={...source,firmware:'4.4',id_r:'0054',mac_r:'02:00:00:00:00:54',verified_at:1793026800,current_unconfirmed:false,note:'Nueva imagen verificada en ensayo.'};jobState='verified';
  await p.waitForFunction(()=>{const e=document.querySelector('#stm-r1-est').closest('.prog-panel').querySelector('.prog-estado');return e.textContent.includes('FW 4.4')&&e.querySelector('.prog-luz-txt').textContent==='Última programación verificada';});
  assert((await right.innerText()).includes('0054'),'Nueva identidad tras verificacion');assert(posts.length===2,'Solo dos grabaciones simuladas explicitas');
  results.push('actualizacion solo tras resultado verificado');
  await p.setViewportSize({width:390,height:844});await p.waitForTimeout(350);
  assert(await p.evaluate(()=>document.documentElement.scrollWidth)<=390,'Sin desborde movil');
  await p.screenshot({path:'C:/Users/usuario/Mi unidad/Inventario TQT/outputs/revision_r1_fw44_20261026/estado_separado_qa.png',fullPage:true});
  assert(errors.length===0,'ErroresJS:'+errors.join(';'));
  return {passed:results,posts:posts.length,errors,mobile:390,physicalHardware:false};
 } finally {await c.close();}
}
