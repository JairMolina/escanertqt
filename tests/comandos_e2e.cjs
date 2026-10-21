/* Local real-backend review. Requires Playwright and a fresh local QA account.
 * TQT_COMMANDS_QA_PASSWORD must match compose.commands-local.yaml.
 * Run: node tests/comandos_e2e.cjs
 */
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const base=process.env.TQT_COMMANDS_QA_URL||'http://localhost:18086';
assert.ok(/^http:\/\/(localhost|127\.0\.0\.1):\d+$/.test(base),'Only isolated loopback QA instances are allowed');
const reportDir=process.env.TQT_COMMANDS_QA_OUTPUT||path.join(__dirname,'../.qa-comandos');
fs.mkdirSync(reportDir,{recursive:true});
const results=[],errors=[],httpErrors=[];
let browser,page;
async function check(name,fn){await fn();results.push(name);console.log('PASS '+name);}
const count=()=>page.locator('.command-row').count();
const payload=()=>page.locator('#payload-content').innerText();
const pick=id=>page.locator(`[data-select="${id}"]`).click();
const clipboard=()=>page.evaluate(()=>navigator.clipboard.readText());
async function copy(){await page.locator('#copy-command').click();return clipboard();}
async function enter(hash='comandos'){
 await page.goto(base+'/monitor?qa_context=preserved#/'+hash);
 await page.locator('#sec-comandos .commands-tabs').waitFor();
}
(async()=>{
 try{
  browser=await chromium.launch({headless:true});
  const context=await browser.newContext({viewport:{width:1440,height:1050},permissions:['clipboard-read','clipboard-write']});
  page=await context.newPage();page.setDefaultTimeout(10000);
  page.on('pageerror',e=>errors.push(e.message));
  page.on('response',r=>{if(r.status()>=400)httpErrors.push({status:r.status(),url:r.url()});});
  const login=await context.request.post(base+'/api/auth/login',{data:{email:process.env.TQT_COMMANDS_QA_EMAIL||'developer@skyguardian.mx',password:process.env.TQT_COMMANDS_QA_PASSWORD}});
  assert.equal(login.status(),200);
  await enter();
  await check('native Gestión navigation and 37 commands',async()=>{
   assert.equal(await count(),37);
   assert.equal(await page.locator('a[data-id="comandos"][aria-current="page"]').count(),1);
   assert.equal(await page.locator('iframe').count(),0);
   assert.ok(await page.locator('a[data-id="comandos"]').evaluate(e=>e.closest('.esc-nav')?.innerText.includes('GESTIÓN')||e.closest('nav')?.innerText.includes('Gestión')));
  });
  await check('Plataforma initial ON preview and exact clipboard',async()=>{
   await pick(0);assert.equal(await payload(),'AT$SMSG=1,0,"ON"');
   assert.equal(await copy(),'AT$SMSG=1,0,"ON"');
   assert.equal(await page.locator('#include-crlf').count(),0);
  });
  await check('dynamic time input, slider, clipboard, base of four seconds',async()=>{
   await pick(6);await page.locator('#param-number').fill('8');
   assert.equal(await payload(),'AT$SMSG=1,0,"TIEMPO:8"');assert.equal(await copy(),await payload());
   assert.equal(await page.locator('#nominal-value').innerText(),'12 s');
   await page.locator('#param-range').fill('0');assert.equal(await page.locator('#param-number').inputValue(),'0');
   assert.equal(await payload(),'AT$SMSG=1,0,"TIEMPO:0"');assert.equal(await page.locator('#nominal-value').innerText(),'4 s');
  });
  await check('Serial CRLF opt-in and exact bytes; Plataforma resets terminator',async()=>{
   await page.locator('[data-output-format="serial"]').click();assert.equal(await page.locator('#include-crlf').isChecked(),false);
   assert.equal(await copy(),'$SMSG=TIEMPO:0');await page.locator('#include-crlf').check();assert.equal(await copy(),'$SMSG=TIEMPO:0\r\n');
   await page.locator('[data-output-format="platform"]').click();assert.equal(await copy(),'AT$SMSG=1,0,"TIEMPO:0"');
   await page.locator('[data-output-format="serial"]').click();assert.equal(await page.locator('#include-crlf').isChecked(),false);
  });
  await check('all dropdown parameters immediately update preview and clipboard',async()=>{
   await page.locator('[data-output-format="platform"]').click();
   for(const [id,value,expected] of [[5,'1','Sensores:1'],[7,'1','PARO_C:1'],[9,'?','PROT_C:?'],[11,'1','MAP_M1:1'],[12,'1','MAP_M2:1'],[13,'0','INT_1:0'],[14,'2','INT_2:2'],[15,'3','INT_3:3'],[16,'0','OUT_1:0'],[17,'1','OUT_2:1'],[18,'4','Bloqueo:4'],[22,'1','DBG_TQT;1']]){
    await pick(id);await page.locator('#param-value').selectOption(value);assert.equal(await payload(),`AT$SMSG=1,0,"${expected}"`);assert.equal(await copy(),await payload());
   }
  });
  await check('name, separators and invalid parameter guards',async()=>{
   await pick(19);await page.locator('#param-value').fill('TQT_R1_TEST');assert.equal(await copy(),'AT$SMSG=1,0,"Nombre:TQT_R1_TEST"');
   await page.locator('#param-value').fill('invalid"name');assert.equal(await page.locator('#copy-command').isDisabled(),true);
   await pick(20);await page.locator('#param-value').fill(':');assert.equal(await copy(),'AT$SMSG=1,0,"SPAS;:"');
   await page.locator('#param-value').fill(';');assert.equal(await page.locator('#copy-command').isDisabled(),true);
   await pick(6);await page.locator('#param-number').fill('11');assert.equal(await page.locator('#copy-command').isDisabled(),true);
   await page.locator('#param-number').fill('0');
  });
  await check('Bluetooth and GPS acknowledgement keep original formats',async()=>{
   for(const [id,value] of [[27,'PPON'],[28,'POFF'],[29,'RST4'],[30,'I1_1'],[31,'I1_0'],[32,'I2_1'],[33,'I2_0'],[34,'PC_1'],[35,'PC_0'],[36,'PC_?']]){
    await pick(id);assert.equal(await payload(),value);assert.equal(await copy(),value);assert.equal(await page.locator('#include-crlf').count(),0);
   }
   await pick(26);assert.equal(await payload(),'$OK');assert.equal(await page.locator('#include-crlf').isChecked(),false);assert.equal(await copy(),'$OK');
  });
  await check('hardware, firmware, channel, type, category and search filters',async()=>{
   await page.locator('#hardware').selectOption('other');assert.equal(await count(),0);assert.ok(await page.getByText('Este hardware aún no tiene documentación.').isVisible());
   await page.locator('#hardware').selectOption('3.0');await page.locator('#firmware').selectOption('4.1');assert.equal(await count(),28);
   await page.locator('#firmware').selectOption('4.4');await page.locator('[data-channel="Bluetooth"]').click();assert.equal(await count(),10);
   await page.locator('#kind-filter').selectOption('query');assert.equal(await count(),1);
   await page.locator('[data-channel="all"]').click();await page.locator('#kind-filter').selectOption('all');
   await page.locator('[data-group="protection"]').click();assert.equal(await count(),6);
   await page.locator('#search').fill('consultar');assert.equal(await count(),2);
   await page.locator('#search').fill('zzzz');assert.equal(await count(),0);await page.locator('[data-action="reset-filters"]').click();assert.equal(await count(),37);
  });
  await check('favorites persist through reload and filter correctly',async()=>{
   await page.locator('[data-favorite="6"]').click();await page.locator('[data-action="favorites"]').click();assert.equal(await count(),1);
   await page.reload();await page.locator('.command-row').waitFor();assert.equal(await count(),1);assert.equal(await page.locator('[data-favorite="6"]').getAttribute('aria-pressed'),'true');
   await page.locator('[data-action="favorites"]').click();
  });
  await check('firmware comparison and 28 factory defaults',async()=>{
   await page.locator('[data-view="compare"]').click();assert.equal(await page.locator('.comparison-view .table-card').first().locator('tbody tr').count(),6);
   await page.locator('#compare-from').selectOption('4.1');await page.locator('#compare-to').selectOption('4.2');assert.equal(await page.locator('.comparison-view .table-card').first().locator('tbody tr').count(),3);
   await page.locator('[data-view="defaults"]').click();assert.equal(await page.locator('.default-card').count(),28);
   await page.locator('#defaults-search').fill('tiempo base');assert.equal(await page.locator('.default-card').count(),1);assert.ok((await page.locator('.factory-value').innerText()).includes('4000'));
  });
  await check('shareable hash retains outer query, filters and current parameter',async()=>{
   await enter('comandos?cmd=6&fw=4.4&value=7&format=serial&crlf=1&channel=Serial%2FGPS&q=tiempo&extension=keep');
   assert.equal(await page.locator('#param-number').inputValue(),'7');assert.equal(await copy(),'$SMSG=TIEMPO:7\r\n');
   await page.locator('#param-number').fill('9');const url=new URL(page.url());assert.equal(url.searchParams.get('qa_context'),'preserved');
   const params=new URLSearchParams(url.hash.split('?')[1]);assert.equal(params.get('value'),'9');assert.equal(params.get('q'),'tiempo');assert.equal(params.get('extension'),'keep');
   await page.reload();await page.locator('#payload-content').waitFor();assert.equal(await copy(),'$SMSG=TIEMPO:9\r\n');
  });
  await check('malformed URL parameters cannot inject markup or enable copying',async()=>{
   const attack='\"><img src=x onerror="window.__commandsInjection=1">';
   await enter('comandos?cmd=6&value='+encodeURIComponent(attack));
   await page.locator('#copy-command').waitFor();
   assert.equal(await page.locator('#copy-command').isDisabled(),true);
   assert.equal(await page.evaluate(()=>window.__commandsInjection),undefined);
   assert.equal(await page.locator('#sec-comandos img').count(),0);
  });
  await check('routing within section, away and back cleans up dialogs and listeners',async()=>{
   await page.evaluate(()=>{location.hash='/comandos?cmd=0';});await page.waitForFunction(()=>document.querySelector('#payload-content')?.textContent==='AT$SMSG=1,0,"ON"');
   await page.locator('[data-action="guide"]').click();assert.equal(await page.locator('dialog[open]').count(),1);
   await page.keyboard.press('Escape');assert.equal(await page.locator('dialog[open]').count(),0);
   await page.locator('a[data-id="resumen"]').click();await page.locator('#sec-resumen').waitFor();assert.equal(await page.locator('#commands-guide-dialog').count(),0);
   await page.locator('a[data-id="comandos"]').click();await page.locator('#payload-content').waitFor();assert.equal(await page.locator('#commands-guide-dialog').count(),1);
  });
  await check('guide downloads catalog and notes',async()=>{
   await page.locator('[data-action="guide"]').click();
   const downloadPromise=page.waitForEvent('download');await page.locator('[data-download="catalog"]').click();const download=await downloadPromise;
   assert.equal(download.suggestedFilename(),'comandos_r1_por_version.json');
   const referencePromise=page.waitForEvent('download');await page.locator('[data-download="reference"]').click();assert.equal((await referencePromise).suggestedFilename(),'COMANDOS_R1.md');
   await page.keyboard.press('Escape');
  });
  await check('desktop and mobile dark/light themes do not overflow',async()=>{
   for(const width of [1440,1024,390]){
    await page.setViewportSize({width,height:1000});
    for(const theme of ['dark','light']){
     await page.evaluate(t=>document.documentElement.dataset.theme=t,theme);
     await page.evaluate(()=>window.scrollTo(0,0));
     const size=await page.evaluate(()=>({scroll:document.documentElement.scrollWidth,width:innerWidth}));assert.ok(size.scroll<=size.width+1,JSON.stringify({width,theme,...size}));
     await page.screenshot({path:path.join(reportDir,`comandos-${width}-${theme}.png`),fullPage:true});
    }
   }
  });
  await check('no JS exceptions or HTTP errors in the isolated review',async()=>{assert.deepEqual(errors,[]);assert.deepEqual(httpErrors,[]);});
 }finally{
  fs.writeFileSync(path.join(reportDir,'results.json'),JSON.stringify({base,passed:results.length,checks:results,errors,httpErrors},null,2));
  if(browser)await browser.close();
 }
})().catch(e=>{console.error(e);process.exitCode=1;});
