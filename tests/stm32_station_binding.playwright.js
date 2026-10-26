// Pruebas Playwright contra QA aislada; todos los agentes y trabajos estan simulados.
async (page) => {
  const BASE='http://127.0.0.1:18089';
  const A='111111111111111111111111',B='222222222222222222222222';
  const one={id:A,name:'J-Link prueba A',online:true,local:true};
  const two={id:B,name:'J-Link prueba B',online:true,local:true};
  const assert=(ok,msg)=>{if(!ok)throw Error(msg);};
  const results=[],errors=[];
  async function setup(saved=A) {
    const c=await page.context().browser().newContext({viewport:{width:1440,height:1000}});
    const p=await c.newPage();p.on('pageerror',e=>errors.push(e.message));
    const state={agents:[one,two],hold:false,pending:null,post:null,cancel:null,reads:0};
    await c.addInitScript(({saved})=>{
      if(!sessionStorage.getItem('qa-station-initialized')) {
        if(saved){localStorage.setItem('tqt.station.stm32',saved);localStorage.setItem('tqt.station.stm32.name','J-Link prueba A');}
        else{localStorage.removeItem('tqt.station.stm32');localStorage.removeItem('tqt.station.stm32.name');}
        sessionStorage.setItem('qa-station-initialized','1');
      }
    },{saved});
    const job=()=>({id:'qa-job',station:state.post.station_id,state:'queued',payload:{kind:'R1',firmware_id:state.post.firmware_id,identity:{nombre:'TQT_R1_V30_0054',hw:'3.0',fw:'4.4'}}});
    await p.route('**/api/stm32/stations',r=>{
      state.reads++;
      if(state.hold){state.hold=false;state.pending=r;return;}
      return r.fulfill({json:state.agents});
    });
    await p.route(/\/api\/stm32\/stations\/[^/]+\/jobs$/,r=>r.fulfill({json:[]}));
    await p.route(/\/api\/stm32\/stations\/[^/]+\/cancel$/,r=>{state.cancel=r.request().url();return r.fulfill({json:{jobs:[]}});});
    await p.route('**/api/stm32/jobs',r=>{assert(r.request().method()==='POST','Solo POST simulado');state.post=r.request().postDataJSON();return r.fulfill({json:job()});});
    await p.route('**/api/stm32/jobs/qa-job',r=>r.fulfill({json:job()}));
    await p.goto(BASE+'/login');await p.locator('#email').fill('developer4@skyguardian.mx');await p.locator('#pass').fill('prueba-beta-local');
    await p.getByRole('button',{name:'Entrar',exact:true}).click();await p.waitForURL(u=>!u.pathname.endsWith('/login'));
    await p.goto(BASE+'/monitor#/programacion');await p.waitForTimeout(600);await p.getByRole('button',{name:'TQT R1',exact:true}).click();
    const select=p.locator('#stm-r1-est');await select.locator('option[value="'+A+'"]').waitFor({state:'attached'});
    const refresh=async()=>{await select.locator('..').getByRole('button',{name:'Actualizar',exact:true}).click();await p.waitForTimeout(180);};
    return {c,p,state,select,refresh};
  }
  let x=await setup();
  try {
    assert(await x.select.inputValue()===A,'Elegir guardada A');
    const readsBefore=x.state.reads; x.state.agents=[two,{...one,online:false}];await x.p.waitForTimeout(5200);
    assert(x.state.reads>readsBefore,'Sondeo automatico real ejecutado');
    assert(await x.select.inputValue()===A,'Offline A nunca cambia a B');
    assert(await x.p.locator('.prog-sesion-txt').first().textContent().then(t=>t.includes('desconectado')),'Mostrar desconectada');
    x.state.agents=[two];await x.refresh();
    assert(await x.select.inputValue()===A,'A desaparecida permanece seleccionada');
    assert(await x.p.evaluate(()=>localStorage.getItem('tqt.station.stm32'))===A,'No borrar preferencia ausente');
    results.push('offline y ausente conservan agente');
    await x.select.selectOption(B);await x.p.waitForTimeout(200);
    assert(await x.p.evaluate(()=>localStorage.getItem('tqt.station.stm32'))===B,'Eleccion manual persistida');
    assert(await x.p.locator('#stm-r3-est').inputValue()===B,'R1 y R3 sincronizadas por eleccion explicita');
    x.state.agents=[{...two,online:false},one];await x.refresh();
    assert(await x.select.inputValue()===B,'No sustituir manual B por A online');
    await x.p.reload();await x.p.waitForTimeout(600);await x.p.getByRole('button',{name:'TQT R1',exact:true}).click();
    assert(await x.select.inputValue()===B,'Recarga conserva B');
    results.push('seleccion manual, R3 y recarga');
    await x.p.setViewportSize({width:390,height:844});await x.p.waitForTimeout(350);
    assert(await x.p.evaluate(()=>document.documentElement.scrollWidth)<=390,'Sin desborde movil');
    results.push('selector responsive390');
  } finally {await x.c.close();}
  x=await setup('');
  try {assert(await x.select.inputValue()==='','Sin vinculacion no elegir por IP');results.push('misma IP no implica misma laptop');}
  finally {await x.c.close();}
  x=await setup();
  try {
    x.state.hold=true;await x.refresh();assert(x.state.pending,'Respuesta vieja retenida');
    await x.select.selectOption(B);await x.p.waitForTimeout(120);
    await x.state.pending.fulfill({json:[one]});x.state.pending=null;await x.p.waitForTimeout(180);
    assert(await x.select.inputValue()===B,'Respuesta vieja no sustituye B');
    results.push('respuesta obsoleta ignorada');
  }finally{await x.c.close();}
  x=await setup();
  try {
    await x.p.getByRole('button').filter({hasText:'TQT-R1-V30-0054'}).click();
    const program=x.p.getByRole('button',{name:'Programar R1 0054 con J-Link',exact:true});await program.waitFor();
    x.state.agents=[two,{...one,online:false}];await x.refresh();
    assert(await program.isDisabled(),'No programar agente fijado offline');
    x.state.agents=[one,two];await x.refresh();assert(await program.isEnabled(),'A conectada permite programar');
    x.state.hold=true;await x.refresh();assert(x.state.pending,'Retener refresh anterior al trabajo');
    await program.click();await x.p.waitForTimeout(150);assert(x.state.post.station_id===A,'POST siempre apunta a A elegida');
    await x.state.pending.fulfill({json:[two]});x.state.pending=null;await x.p.waitForTimeout(150);
    assert(await x.select.inputValue()===A,'Respuesta durante trabajo no cambia agente');assert(await x.select.isDisabled(),'Selector bloqueado en trabajo');
    await x.p.getByRole('button',{name:'Detener y cancelar programacion',exact:true}).click({timeout:1000}).catch(async()=>{
      await x.p.getByRole('button',{name:'Detener y cancelar programación',exact:true}).click();
    });
    assert(x.state.cancel?.includes('/stations/'+A+'/cancel'),'Cancelacion apunta a agente activo A');
    results.push('programacion y cancelacion simuladas fijadas a A');
  }finally{await x.c.close();}
  assert(errors.length===0,'Errores JS: '+errors.join('; '));
  return {passed:results,errors,physicalHardware:false};
}
