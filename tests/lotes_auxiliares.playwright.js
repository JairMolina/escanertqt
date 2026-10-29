async (page) => {
  const c = await page.context().browser().newContext({viewport:{width:1440,height:1000}});
  const p = await c.newPage(), errors=[], writes=[], checks=[];
  const base='http://127.0.0.1:18091';
  const assert=(v,m)=>{if(!v)throw Error(m);};
  p.on('pageerror', e=>errors.push(e.message));
  p.on('request', r=>{if(r.method()!=='GET'&&r.url().includes('/api/')&&!r.url().endsWith('/api/admin/login'))writes.push(r.method()+' '+new URL(r.url()).pathname);});
  try {
    await p.addInitScript(()=>{if(!localStorage.getItem('tqt.lote.vista'))localStorage.setItem('tqt.lote.vista','2');window.__printCalls=0;});
    await p.route('**/*',r=>new URL(r.request().url()).host==='127.0.0.1:18091'?r.continue():r.abort());
    await p.route('**/static/js/vendor/dymo.connect.framework.js*',r=>r.fulfill({contentType:'application/javascript',body:'/* Hardware SDK intentionally absent in QA */'}));
    await p.route('**/static/js/dymo_connect.js*',r=>r.fulfill({contentType:'application/javascript',body:"window.TQTDymo={detect:async()=>({estado:'no_servicio',printers:[],preferred:null,detalle:'QA sin impresora'}),esXmlEtiqueta:()=>false,print:async()=>{window.__printCalls++;throw Error('No physical printing in QA')}};"}));
    await p.route('**/static/js/dymo_remoto.js*',r=>r.fulfill({contentType:'application/javascript',body:"window.TQTDymoRemoto={VALOR:'remota',estado:async()=>({disponible:false,agentes:[],en_cola:0}),imprimir:async()=>{window.__printCalls++;throw Error('No remote printing in QA')}};"}));
    let r=await c.request.post(base+'/api/auth/login',{data:{email:'developer@skyguardian.mx',password:'prueba-lotes-local'}}); assert(r.ok(),'QA admin user');
    await p.goto(base+'/admin?tab=tarjetas');
    assert((await p.content()).includes('1.4.76'),'QA serves candidate 1.4.76');
    await p.locator('#pass').fill('admin-lotes-local');
    await p.getByRole('button',{name:'Entrar',exact:true}).click();
    await p.getByRole('tab',{name:'Tarjetas',exact:true}).click();
    await p.waitForFunction(()=>document.querySelectorAll('#tTabla tbody tr').length===1);
    assert(await p.evaluate(()=>window.TQT.cabecerasLote('/api/sync/excel')['X-TQT-Lote'])==='2','Monthly Excel sync carries the selected lot');
    await p.waitForFunction(()=>document.querySelector('#resumenBox .kpi .v')?.textContent==='1');
    assert(await p.locator('#tLote').inputValue()==='2','Admin uses selected lot');
    await p.locator('#tLote').selectOption('3');
    await p.waitForFunction(()=>document.querySelectorAll('#tTabla tbody tr').length===2);
    await p.waitForFunction(()=>document.querySelector('#resumenBox .kpi .v')?.textContent==='2');
    assert(await p.locator('#mLote').inputValue()==='3','Movements selection follows');
    await p.locator('#tLote').selectOption('0');
    await p.waitForFunction(()=>document.querySelectorAll('#tTabla tbody tr').length===3);
    await p.waitForFunction(()=>document.querySelector('#resumenBox .kpi .v')?.textContent==='3');
    assert(await p.evaluate(()=>localStorage.getItem('tqt.lote.vista'))==='all','All string value stored correctly');
    checks.push('Administración: resumen y lista con 1/2/3 tarjetas, selección coherente con Movimientos');

    for (const [scope,n] of [[2,1],[3,1],[0,2]]) {
      const r=await p.evaluate(async scope=>{window.TQT.guardarLoteVista(scope);return window.TQT.api('/api/pruebas-auto/tarjetas?q=65');},scope);
      assert(r.ok&&r.data.length===n,'Campaign lookup uses browser lot '+scope);
      assert(r.data.every(t=>t.lote_codigo),'Campaign source lot visible in All');
    }
    checks.push('Pruebas automáticas: búsqueda 0065 en septiembre/octubre/Todos por la misma cabecera del navegador');

    await p.evaluate(()=>window.TQT.guardarLoteVista(2));
    await p.goto(base+'/dymo');
    await p.waitForFunction(()=>document.querySelector('#selTarjeta')?.options.length===1);
    assert((await p.locator('#selTarjeta').innerText()).includes('QA-2026-09'),'Label selection shows source lot');
    await p.getByRole('button',{name:'R3',exact:true}).click();
    await Promise.all([p.waitForEvent('load'),p.locator('#r3Lote').selectOption('3')]);
    await p.waitForFunction(()=>document.querySelector('#selTarjeta')?.options.length===2);
    assert((await p.locator('#selTarjeta').innerText()).includes('QA-2026-10'),'Dymo refresh clears old card set');
    await p.getByRole('button',{name:'R3',exact:true}).click();
    await Promise.all([p.waitForEvent('load'),p.locator('#r3Lote').selectOption('0')]);
    await p.waitForFunction(()=>document.querySelector('#selTarjeta')?.options.length===3);
    assert(await p.locator('#r3Lote').inputValue()==='0','All persists in labels');
    assert(await p.evaluate(()=>window.__printCalls)===0,'No print API invoked');
    checks.push('DYMO: selección del lote 1/2/3 tarjetas, origen visible y Todos conservado');
    assert(!writes.length,'No inventory or print writes: '+writes.join(';'));
    assert(!errors.length,'JS: '+errors.join(';'));
    return {checks,errors,writes,hardware:'DYMO SDK/remote transport mocked; no physical printing'};
  } catch(e) {throw Error(e.message+'\nChecks: '+checks.join('|')+'\nURL: '+p.url()+'\nJS:'+errors.join('|'));}
  finally {await c.close();}
}
