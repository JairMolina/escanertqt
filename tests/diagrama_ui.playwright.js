// Isolated QA only. The diagram is a reference; no physical devices are involved.
async(page)=>{
 const c=await page.context().browser().newContext({viewport:{width:1440,height:1000}}),p=await c.newPage();
 const errors=[],unexpectedWrites=[],httpErrors=[],passed=[],screens='C:/Users/usuario/Mi unidad/Inventario TQT/outputs/diagrama_tqt_20261027/';
 let signedIn=false,expectedCatalogFailure=false;
 const assert=(value,message)=>{if(!value)throw Error(message);};
 p.on('pageerror',e=>errors.push(e.message));
 p.on('request',r=>{if(!['GET','HEAD'].includes(r.method())&&!r.url().includes('/api/auth/login'))unexpectedWrites.push(r.method()+' '+r.url());});
 p.on('response',r=>{if(r.status()<400||(!signedIn&&r.status()===401&&r.url().endsWith('/api/auth/yo'))||(expectedCatalogFailure&&r.status()===503&&r.url().includes('diagrama_tqt.json')))return;httpErrors.push(r.status()+' '+r.url());});
 await c.addInitScript(()=>{const original=URL.createObjectURL;URL.createObjectURL=function(blob){window.__diagramBlob=blob;return original.call(this,blob);};});
 const app=()=>p.locator('#sec-diagrama'),count=()=>app().locator('.diag-count');
 const open=async()=>{await p.goto('http://127.0.0.1:18089/monitor#/diagrama');await p.getByRole('heading',{name:'Conexiones por hardware'}).waitFor();};
 try{
  await p.goto('http://127.0.0.1:18089/login');await p.locator('#email').fill('developer4@skyguardian.mx');await p.locator('#pass').fill('prueba-beta-local');await p.getByRole('button',{name:'Entrar',exact:true}).click();await p.waitForURL(u=>!u.pathname.endsWith('/login'));
  signedIn=true;
  await open();
  const menu=await p.locator('.esc-nav a[data-id]').evaluateAll(xs=>xs.map(x=>x.dataset.id));
  assert(menu.indexOf('diagrama')===menu.indexOf('comandos')+1,'Diagrama inmediatamente debajo de Comandos');
  assert(await p.locator('.esc-lat').count()===1,'No duplicar barra lateral');assert(await p.locator('#escTitulo').innerText()==='Diagrama','Cabecera nativa');
  assert((await count().innerText()).includes('/ 18'),'HW30 contiene18referencias');passed.push('registro nativo, orden y HW30');
  await p.getByRole('button',{name:'HW 20',exact:true}).click();assert((await count().innerText()).includes('/ 19'),'HW20 contiene19referencias');
  await p.locator('#diag-group-r3').click();assert(await app().locator('.diag-wire-list .diag-wire').count()===5,'R3HW20 tiene5referencias');
  await app().locator('.diag-canvas [data-wire="r3-extra-12"]').focus();await p.keyboard.press('Enter');
  assert(await app().locator('.diag-canvas [data-wire="r3-extra-12"]').getAttribute('aria-pressed')==='true','SVG mantiene selección');
  await app().locator('.diag-quote summary').click();
  assert((await app().locator('.diag-inspector').innerText()).includes('Conectar a +12 VCD'),'SelecciónSVG por teclado');
  await p.getByRole('button',{name:'HW 30',exact:true}).click();assert(await app().locator('.diag-wire-list .diag-wire').count()===4,'R3HW30 tiene4referencias');
  assert(!await app().locator('.diag-wire-list [data-select="r3-extra-12"]').count(),'No inventar cableextra enHW30');passed.push('cambioHW y selecciónSVG por teclado');
  await p.evaluate(()=>Object.defineProperty(navigator.clipboard,'writeText',{value:async text=>{window.__diagramCopy=text;},configurable:true}));
  await p.getByRole('button',{name:'Copiar conexión',exact:true}).click();assert((await p.evaluate(()=>window.__diagramCopy)).includes('TQT HW 30'),'Copia identifica hardware');assert((await p.evaluate(()=>window.__diagramCopy)).includes('lámina 6'),'Copia conserva trazabilidad');passed.push('copiar conexión con hardware y fuente');
  await p.locator('#diag-search').fill('rs485');assert(await app().locator('.diag-wire-list .diag-wire').count()===4,'Búsqueda global encuentra el grupo GPS/RS485');
  assert(await p.locator('#diag-search').inputValue()==='rs485','Búsqueda conserva valor/foco');
  await p.locator('#diag-search').fill('rs485 negro');assert(await app().locator('.diag-wire-list .diag-wire').count()===1,'Búsqueda combina color y grupo');
  await p.locator('#diag-search').fill('zzzznada');await p.getByRole('heading',{name:'Sin coincidencias',exact:true}).waitFor();
  await p.getByRole('button',{name:'Limpiar búsqueda',exact:true}).click();assert(await app().locator('.diag-canvas svg').count()===1,'Recuperar búsqueda');passed.push('filtros y sin coincidencias');
  await p.getByRole('button',{name:'Comparar HW',exact:true}).click();
  assert((await app().locator('.diag-table').innerText()).includes('Solo en HW20'),'Comparación identifica cableextra');
  const different=await app().locator('.diag-table tbody tr').count();await p.locator('#diag-changes').uncheck();
  assert(await app().locator('.diag-table tbody tr').count()===19,'Comparación completa19referencias');assert(different<19,'Solo diferencias reduce tabla');passed.push('comparaciónHW por datos de referencia');
  await p.getByRole('button',{name:'Vista general',exact:true}).click();await app().locator('.diag-overview img').waitFor();
  await p.locator('.diag-pins summary').click();assert(await p.locator('.diag-pin-grid>div').count()===12,'AK7V12pines sin funciones inventadas');
  const source=p.getByRole('button',{name:'Abrir lámina completa',exact:true});await source.click();
  const dialog=p.getByRole('dialog',{name:/Lámina/});await dialog.waitFor();
  assert(await dialog.locator('img').evaluate(img=>new Promise(resolve=>{if(img.complete)resolve(img.naturalWidth>0);else img.onload=()=>resolve(img.naturalWidth>0);})), 'Lámina original carga');
  await dialog.getByRole('button',{name:'Ampliar lámina',exact:true}).click();assert(await dialog.locator('[data-source-zoom]').innerText()==='125 %','Zoomfuente');
  await p.keyboard.press('Escape');await dialog.waitFor({state:'hidden'});assert(await source.evaluate(el=>document.activeElement===el),'Cerrar devuelve foco');passed.push('láminas, zoom, Escape y AK7V');
  await p.getByRole('button',{name:'Conexiones',exact:true}).click();await p.locator('#diag-group-r3').click();
  await app().locator('.diag-wire-list [data-select="r3-timer"]').click();await p.locator('#diag-review-selected').check();assert((await count().innerText()).startsWith('1 /'),'Marcar referenciaHW30');
  await p.reload();await p.getByRole('heading',{name:'Conexiones por hardware'}).waitFor();assert(await p.locator('#diag-review-selected').isChecked(),'Marca persiste trasrecarga');
  await p.getByRole('button',{name:'HW 20',exact:true}).click();assert(!await p.locator('#diag-review-selected').isChecked(),'Marca aislada porHW');await p.locator('#diag-review-selected').check();
  await p.getByRole('button',{name:'HW 30',exact:true}).click();await p.getByRole('button',{name:'Revisión local',exact:true}).click();
  await p.locator('#diag-review-filter').selectOption('done');assert(await app().locator('.diag-check-row').count()===1,'Filtrorevisadas');
  const downloadPromise=p.waitForEvent('download');await p.getByRole('button',{name:'Exportar revisión',exact:true}).click();const download=await downloadPromise;
  assert(download.suggestedFilename()==='TQT_Diagrama_HW30_revision.json','Nombreexport');const exported=await p.evaluate(async()=>JSON.parse(await window.__diagramBlob.text()));
  assert(exported.reviewed===1&&exported.total===18&&exported.hardware==='30','JSONexportadocorrecto');assert(exported.scope.includes('no registra ni aprueba'),'Sin falsa aprobación');passed.push('revisión persistente porHW, filtro y exportación real');
  await p.getByRole('button',{name:'Reiniciar HW 30',exact:true}).click();const reset=p.getByRole('dialog');await reset.getByRole('button',{name:'Reiniciar marcas',exact:true}).click();
  assert((await count().innerText()).startsWith('0 /'),'ResetHW30');await p.getByRole('button',{name:'HW 20',exact:true}).click();assert((await count().innerText()).startsWith('1 /'),'ResetpreservaHW20');passed.push('reinicio limitado al HW elegido');
  await p.getByRole('button',{name:'Conexiones',exact:true}).click();
  for(const theme of ['dark','light']){
   await p.evaluate(theme=>document.documentElement.dataset.theme=theme,theme);
   for(const width of [1440,1024,390]){
    await p.setViewportSize({width,height:900});await p.waitForTimeout(200);
    assert(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Sin desborde '+theme+width);
    await p.screenshot({path:screens+'native_'+theme+'_'+width+'.png',fullPage:true});
   }
  }
  passed.push('temas claro/oscuro y1440/1024/390 sin desborde');
  await p.setViewportSize({width:1440,height:1000});
  await p.goto('http://127.0.0.1:18089/monitor#/diagrama?hw=20&grupo=r3&cable=r3-extra-12&vista=explore');await p.locator('.diag-inspector h3').waitFor();
  assert(await app().locator('.diag-wire-list [data-select="r3-extra-12"]').getAttribute('aria-pressed')==='true','Enlaceprofundo cableHW20');
  await p.getByRole('button',{name:'Cómo leer el diagrama',exact:true}).click();await p.getByRole('dialog').getByRole('heading',{name:'Alcance de la referencia'}).waitFor();await p.keyboard.press('Escape');passed.push('enlaces profundos y guía de alcance');
  await p.route('**/api/auth/yo',r=>r.fulfill({json:{email:'developer4@skyguardian.mx',rol:'consultor',debe_cambiar:false,modulos:['escaner-tqt']}}));await p.reload();await p.getByRole('heading',{name:'Conexiones por hardware'}).waitFor();
  assert(await p.locator('.esc-nav a[data-id="diagrama"]').count()===1,'Consultor puede leerdiagrama');assert(!await p.locator('.esc-nav a[data-id="admin"]').count(),'Consultor mantiene restricciones');passed.push('consulta permitida sin ampliar administración');
  let failOnce=true;expectedCatalogFailure=true;
  await p.route('**/static/catalogos/diagrama_tqt.json',r=>failOnce?(failOnce=false,r.fulfill({status:503,json:{detail:'Ensayo de error de carga'}})):r.continue());
  await p.reload();await p.getByRole('alert').filter({hasText:'No se pudo cargar el diagrama'}).waitFor();expectedCatalogFailure=false;
  await p.locator('.esc-nav a[data-id="resumen"]').click();await p.locator('.esc-nav a[data-id="diagrama"]').click();await p.getByRole('heading',{name:'Conexiones por hardware'}).waitFor();passed.push('error de carga y recuperación al reabrir');
  const catalog=await (await p.request.get('http://127.0.0.1:18089/static/catalogos/diagrama_tqt.json')).json();
  let pending;await p.route('**/static/catalogos/diagrama_tqt.json',r=>{pending=r;});
  await p.reload();await p.getByRole('status').filter({hasText:'Cargando diagrama TQT…'}).waitFor();await p.locator('.esc-nav a[data-id="comandos"]').click();
  await p.waitForTimeout(200);assert(pending,'Carga interceptada');try{await pending.fulfill({json:catalog});}catch{/* request correctly aborted on unmount */}
  await p.waitForTimeout(200);assert(await p.locator('#sec-diagrama').count()===0,'Carga tardía no restaura diagrama');assert(await p.locator('#escTitulo').innerText()==='Comandos','Desmontar conserva navegación');passed.push('cancelación y desmontaje sin respuestas tardías');
  assert(!errors.length,errors.join('\n'));assert(!unexpectedWrites.length,unexpectedWrites.join('\n'));assert(!httpErrors.length,httpErrors.join('\n'));
  return {passed,errors,unexpectedWrites,httpErrors,exported:{reviewed:exported.reviewed,total:exported.total,hardware:exported.hardware}};
 }finally{await c.close();}
}
