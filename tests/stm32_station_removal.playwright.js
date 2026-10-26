// Only isolated QA, mocked agents and jobs; no physical hardware.
async (page) => {
  const A='111111111111111111111111', B='222222222222222222222222';
  const c=await page.context().browser().newContext({viewport:{width:1440,height:1000}});
  const p=await c.newPage(), errors=[], results=[];
  const assert=(ok,msg)=>{if(!ok)throw Error(msg);};
  p.on('pageerror',e=>errors.push(e.message));
  let agents=[{id:A,name:'Agente A',owner:'owner@test.mx',can_delete:true,online:true},
              {id:B,name:'Agente B',owner:'other@test.mx',can_delete:false,online:true}];
  let fail=true, deleted=0;
  await c.addInitScript(()=>{
    localStorage.setItem('tqt.station.stm32','111111111111111111111111');
    localStorage.setItem('tqt.station.stm32.name','Agente A');
  });
  await p.route('**/api/stm32/stations',r=>r.fulfill({json:agents}));
  await p.route(/\/api\/stm32\/stations\/[^/]+\/jobs$/,r=>r.fulfill({json:[]}));
  await p.route('**/api/stm32/stations/'+A,r=>{
    assert(r.request().method()==='DELETE','DELETE only');deleted++;
    if(fail)return r.fulfill({status:409,json:{detail:'El agente tiene una prueba en curso.'}});
    agents=agents.filter(x=>x.id!==A);return r.fulfill({json:{removed:[A],history_preserved:true}});
  });
  try {
    await p.goto('http://127.0.0.1:18089/login');
    await p.locator('#email').fill('developer4@skyguardian.mx');await p.locator('#pass').fill('prueba-beta-local');
    await p.getByRole('button',{name:'Entrar',exact:true}).click();await p.waitForURL(u=>!u.pathname.endsWith('/login'));
    await p.goto('http://127.0.0.1:18089/monitor#/programacion');await p.waitForTimeout(600);
    await p.getByRole('button',{name:'TQT R1',exact:true}).click();
    const select=p.locator('#stm-r1-est');await select.locator('option[value="'+A+'"]').waitFor({state:'attached'});
    assert((await select.locator('option:checked').textContent()).includes('owner@test.mx'),'Usuario que registró agente visible');
    await select.selectOption(B);
    const del=p.getByRole('button',{name:'Borrar agente',exact:true});
    assert(await del.isDisabled(),'No ofrecer borrar agente ajeno');
    await select.selectOption(A);await p.waitForTimeout(200);
    await del.click();
    const dialog=p.getByRole('dialog');await dialog.waitFor();
    assert((await dialog.textContent()).includes('historiales'),'Advertir conservación de historia');
    await dialog.getByRole('button',{name:'Conservar agente',exact:true}).click();
    assert(deleted===0,'Cancelar no llama DELETE');results.push('cancelación y permisos visibles');
    await del.click();await dialog.getByRole('button',{name:'Borrar agente',exact:true}).click();
    await dialog.getByRole('alert').filter({hasText:'prueba en curso'}).first().waitFor();
    assert(await select.inputValue()===A,'409 conserva selección');
    assert(await p.evaluate(()=>localStorage.getItem('tqt.station.stm32'))===A,'409 conserva preferencia');
    results.push('trabajo activo rechaza sin cambiar selección');
    fail=false;await dialog.getByRole('button',{name:'Borrar agente',exact:true}).click();
    await dialog.waitFor({state:'hidden'});await p.waitForTimeout(250);
    assert(await select.inputValue()==='','Borrado limpia selección');
    assert(await p.evaluate(()=>localStorage.getItem('tqt.station.stm32'))===null,'Borrado limpia preferencia');
    assert(!await select.locator('option[value="'+A+'"]').count(),'Borrado no reaparece en selector');
    results.push('borrado elimina credencial del selector y no elige otro agente');
    await p.getByRole('button',{name:'TQT R3',exact:true}).click();await p.waitForTimeout(250);
    assert(await p.locator('#stm-r3-est').inputValue()==='','R3 comparte limpieza');
    await p.setViewportSize({width:390,height:844});await p.waitForTimeout(200);
    assert(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Móvil sin desborde');
    assert(!errors.length,errors.join('\n'));results.push('R3, móvil 390 y sin errores JS');
    return {results,deleted,errors};
  } finally { await c.close(); }
}
