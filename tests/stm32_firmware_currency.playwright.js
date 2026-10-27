// Isolated QA with synthetic catalog/inventory. No hardware or production writes.
async (page) => {
 const c=await page.context().browser().newContext({viewport:{width:1440,height:1000}}),p=await c.newPage();
 const errors=[],passed=[];let writes=0,kind='R1',fw='4.3',unconfirmed=false,failCatalog=false;
 const meta=(id,version,hw='3.0',status='aprobado')=>({id,fw:version,hw,release_status:status,sha256:'a'.repeat(64)});
 let catalog=[meta('old','4.3'),meta('current','4.4'),meta('beta','4.5','3.0','beta'),meta('incompatible','9.0','4.0')];
 const card=()=>({id:kind==='R1'?9055:9039,tipo:kind,version:'30',serie:kind==='R1'?'0055':'0039',nombre:kind==='R1'?'TQT-R1-V30-0055':'TQT-R3-V30-0039',firmware:fw});
 const assert=(v,m)=>{if(!v)throw Error(m);};
 p.on('pageerror',e=>errors.push(e.message));
 await p.route('**/api/stm32/firmwares?*',r=>{
   if(failCatalog)return r.fulfill({status:503,json:{detail:'Catálogo no disponible en ensayo'}});
   return r.fulfill({json:{items:catalog,default_id:kind==='R1'?'current':'r3-current'}});
 });
 await p.route('**/api/pcb?*',r=>{
   const url=new URL(r.request().url());
   if(url.searchParams.get('tipo')===kind)return r.fulfill({json:{items:[card()],total:1}});
   return r.continue();
 });
 await p.route('**/api/stm32/stations',r=>r.fulfill({json:[]}));
 await p.route('**/api/stm32/estado/*',r=>r.fulfill({json:{pcb_id:card().id,source:fw?'verified_programming':'none',firmware:fw,hardware:'3.0',nombre:card().nombre,uid:'1234567890ABCDEF12345678',verified_at:1793023200,current_unconfirmed:unconfirmed,note:'Historia sintética de ensayo; sin acceso físico.'}}));
 await p.route('**/api/stm32/preview/*',r=>{
   const id=new URL(r.request().url()).searchParams.get('firmware_id')||(kind==='R1'?'current':'r3-current');
   const image=catalog.find(x=>x.id===id)||catalog[0];
   return r.fulfill({json:{pcb_id:card().id,kind,identity:{nombre:card().nombre,fw:image.fw,hw:'3.0',id_r:'0055',mac_r:'02:00:00:00:00:55'},firmware_id:image.id,hex_sha256:'a'.repeat(64),bytes:100,crc32:'12345678'}});
 });
 await p.route('**/api/stm32/jobs',r=>{writes++;return r.fulfill({status:500,json:{detail:'Hardware writes prohibited in this test'}});});
 try {
  await p.goto('http://127.0.0.1:18089/login');await p.locator('#email').fill('developer4@skyguardian.mx');await p.locator('#pass').fill('prueba-beta-local');
  await p.getByRole('button',{name:'Entrar',exact:true}).click();await p.waitForURL(u=>!u.pathname.endsWith('/login'));
  await p.goto('http://127.0.0.1:18089/monitor#/programacion');await p.waitForTimeout(500);
  await p.getByRole('button',{name:'TQT R1',exact:true}).click();
  const select=()=>p.locator('#stm-'+kind.toLowerCase()+'-fw'),right=()=>p.locator('.prog-estado').filter({has:p.locator('.prog-luz-txt')});
  const choose=async()=>{await p.getByRole('button').filter({hasText:card().nombre}).click();await p.waitForTimeout(200);};
  const badge=()=>p.locator('.prog-item').filter({hasText:card().nombre}).locator('.prog-r2-state');
  const reload=async()=>{await p.reload();await p.waitForTimeout(350);await p.getByRole('button',{name:'TQT '+kind,exact:true}).click();await choose();};
  await choose();
  assert(await badge().getAttribute('data-s')==='outdated','Lista:4.3 desactualizada frente4.4');
  assert(await right().getAttribute('data-s')==='warn','Panel:4.3 verificada es naranja frente4.4');
  const orange=await right().locator('.prog-luz').evaluate(el=>getComputedStyle(el).backgroundColor);
  const rgb=orange.match(/\d+/g).map(Number);
  assert(rgb[0]>rgb[1]&&rgb[1]>rgb[2],'El color CSS renderizado es naranja');
  assert((await right().innerText()).includes('Desactualizada'),'Texto acompaña al color');
  assert((await right().innerText()).includes('4.3 / 4.4'),'Versiones instalada/vigente explícitas');
  const before=await right().innerText();await select().selectOption('old');await p.waitForTimeout(200);
  assert(await right().innerText()===before,'Elegir4.3 no quita aviso de actualización pendiente');
  await select().selectOption('beta');await p.waitForTimeout(200);
  assert(await right().innerText()===before,'Seleccionar beta tampoco cambia el firmware histórico');
  passed.push('lista/panel naranja y selección independiente');
  fw='4.4';await reload();
  assert(await badge().getAttribute('data-s')==='updated','Lista:4.4 actualizada');
  assert(await right().getAttribute('data-s')==='ok','Panel:4.4 verificada verde');
  const green=await right().locator('.prog-luz').evaluate(el=>getComputedStyle(el).backgroundColor);
  const greenRgb=green.match(/\d+/g).map(Number);
  assert(green!==orange&&greenRgb[1]>greenRgb[0]&&greenRgb[1]>greenRgb[2],'El color CSS renderizado al día es verde');
  passed.push('firmware vigente verificado verde');
  assert((await right().innerText()).includes('4.4 / 4.4'),'No comparar beta4.5 ni HWincompatible9.0');
  passed.push('beta y otro hardware no exigen actualización');
  unconfirmed=true;await reload();
  assert(await right().getAttribute('data-s')==='warn','Resultado físico incierto no se pinta verde');
  assert((await right().innerText()).includes('Sin verificación actual'),'Mantener advertencia de intento fallido');
  passed.push('resultado incierto conserva advertencia');
  unconfirmed=false;failCatalog=true;await reload();
  assert(await badge().getAttribute('data-s')==='unknown','Sin catálogo no asegurar actualizada en lista');
  assert(await right().getAttribute('data-s')==='warn','Sin catálogo no asegurar actualizada en panel');
  passed.push('catálogo no disponible no da falso verde');
  failCatalog=false;fw=null;await reload();
  assert(await badge().getAttribute('data-s')==='unprogrammed','Sin firmware rojo en lista');
  assert(await right().getAttribute('data-s')==='bad','Sin firmware rojo en panel');
  passed.push('sin firmware conserva estado rojo');
  fw='4.3';catalog=[meta('old','4.3'),meta('current','4.4','3.0','beta')];await reload();
  assert(await right().getAttribute('data-s')==='ok','4.3 sigue vigente mientras4.4 esbeta');
  assert(await badge().getAttribute('data-s')==='updated','Lista también excluye beta');
  passed.push('solo las versiones aprobadas determinan vigencia');
  kind='R3';fw='1.0';catalog=[meta('r3-old','1.0'),meta('r3-current','1.1')];await reload();
  assert(await right().getAttribute('data-s')==='warn','R3 también avisa firmware anterior');
  assert(await badge().getAttribute('data-s')==='outdated','R3 coherente con lista');
  passed.push('misma regla en R3');
  await p.setViewportSize({width:390,height:844});await p.waitForTimeout(200);
  assert(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Móvil sin desborde');
  assert(!errors.length,errors.join('\n'));assert(writes===0,'Ninguna programación');
  return {passed,errors,writes,mobile:390};
 } finally {await c.close();}
}
