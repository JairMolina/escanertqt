async (page) => {
  // Only the synthetic Docker at 18091. No serial/BLE operations or production DB.
  const browser = page.context().browser();
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'reduce' });
  const p = await context.newPage(), errors = [], checks = [], writes = [];
  const base = 'http://127.0.0.1:18091';
  const assert = (value, msg) => { if (!value) throw Error(msg); };
  p.on('pageerror', e => errors.push(e.message));
  p.on('request', r => { if (r.method() !== 'GET' && r.url().includes('/api/')) writes.push(r.method()+' '+new URL(r.url()).pathname); });
  const header = () => p.getByRole('button', {name: /^Lote: /});
  const items = () => p.locator('#sec-programacion .prog-item:visible');
  const search = () => p.locator('#sec-programacion input[type=search]:visible');
  async function lot(name) {
    await header().click({timeout:5000});
    await p.getByRole('menuitemradio', {name: new RegExp('^'+name)}).click();
    await p.waitForFunction(name => document.querySelector('.esc-lote')?.getAttribute('aria-label')?.includes(name), name);
  }
  async function nav(id) { await p.locator('.esc-nav a[data-id="'+id+'"]').click(); await p.locator('#sec-'+id).waitFor(); }
  async function listCount(n) { await p.waitForFunction(n => [...document.querySelectorAll('#sec-programacion .prog-item')].filter(e=>e.getClientRects().length).length === n, n); }
  try {
    // Existing delivery and bridge notices are passive; dismiss without changing records.
    const notice = p.locator('.sheet').last().filter({has:p.getByRole('button',{name:/^(Más tarde|Ahora no)$/})});
    await p.addLocatorHandler(notice, async()=>{
      await p.locator('.sheet').last().getByRole('button',{name:/^(Más tarde|Ahora no)$/}).click({timeout:5000});
    }, {noWaitAfter:true});
    await p.addInitScript(() => {
      window.__hardwareCalls = 0;
      Object.defineProperty(navigator, 'serial', {value: {getPorts: async()=>[], addEventListener(){}, removeEventListener(){}, requestPort: async()=>{ window.__hardwareCalls++; throw Error('Serial prohibited in QA'); }}});
      Object.defineProperty(navigator, 'bluetooth', {value: {getAvailability:async()=>false,addEventListener(){},removeEventListener(){},requestDevice: async()=>{ window.__hardwareCalls++; throw Error('BLE prohibited in QA'); }}});
    });
    const login = await context.request.post(base+'/api/auth/login', {data:{email:'developer4@skyguardian.mx', password:'prueba-lotes-local'}});
    assert(login.ok(), 'Login QA');
    await p.goto(base+'/monitor?lote=2#/programacion'); await p.locator('#sec-programacion').waitFor();
    await search().fill('65'); await listCount(1);
    assert((await items().innerText()).includes('TQT-R2-V30-0065'), 'Septiembre solo R2 propia');
    await items().click();
    await p.locator('#sec-programacion').getByText('TQT-R2-V30-0065', {exact:true}).last().waitFor();
    checks.push('Programación: 0065 de septiembre sin mezclar octubre');

    await lot('Octubre 2026'); await listCount(3);
    assert(await search().inputValue()==='', 'Cambio limpia búsqueda');
    assert((await p.locator('#sec-programacion').innerText()).includes('Elige una R2'), 'Cambio limpia tarjeta anterior');
    await search().fill('65'); await listCount(1);
    assert((await items().innerText()).includes('TQT-R2-V20-0065'), 'Octubre solo su R2');
    assert(!new URL(p.url()).searchParams.has('lote'), 'Selección elimina parámetro viejo del enlace');
    await p.reload(); await p.locator('#sec-programacion').waitFor();
    assert((await header().getAttribute('aria-label')).includes('Octubre'), 'Persistencia tras recarga');
    checks.push('Cambio y recarga conservan lote, sin selección anterior');

    await nav('resumen'); await p.getByRole('button',{name:'Tarjetas: 2. Ver detalle',exact:true}).waitFor();
    await lot('Septiembre 2026'); await p.getByRole('button',{name:'Tarjetas: 1. Ver detalle',exact:true}).waitFor();
    await lot('Todos los lotes'); await p.getByRole('button',{name:'Tarjetas: 3. Ver detalle',exact:true}).waitFor();
    checks.push('Dashboard: 2 octubre / 1 septiembre / 3 todos');

    await nav('programacion'); await search().fill('65'); await listCount(2);
    const both = await items().allTextContents();
    assert(both.some(t=>t.includes('QA-2026-09')) && both.some(t=>t.includes('QA-2026-10')), 'Todos identifica lote');
    for (const role of ['TQT R1','TQT R3']) {
      await p.getByRole('button',{name:role,exact:true}).click(); await search().fill('65'); await listCount(2);
    }
    await lot('Septiembre 2026'); await p.getByRole('button',{name:'TQT R3',exact:true}).click(); await search().fill('65'); await listCount(1);
    assert((await items().innerText()).includes('V30-0065'), 'R3 también acotada');
    checks.push('R1/R2/R3 y origen visible en Todos');

    await nav('inventario'); await p.waitForFunction(()=>document.querySelectorAll('#sec-inventario tbody tr').length===5);
    assert(!(await p.locator('#sec-inventario tbody').innerText()).includes('V20'), 'Inventario sin lote ajeno');
    await lot('Octubre 2026'); await p.waitForFunction(()=>document.querySelectorAll('#sec-inventario tbody tr').length===8);
    await lot('Todos los lotes'); await p.waitForFunction(()=>document.querySelectorAll('#sec-inventario tbody tr').length===13);
    checks.push('Inventario: 5 / 8 / 13 PCB, incluye sueltas propias');

    await nav('tarjetas'); await p.waitForFunction(()=>document.querySelectorAll('#sec-tarjetas tbody tr').length===3);
    assert((await p.locator('#sec-tarjetas tbody').innerText()).includes('QA-2026-09'), 'Tarjetas etiqueta el lote');
    await lot('Septiembre 2026'); await p.waitForFunction(()=>document.querySelectorAll('#sec-tarjetas tbody tr').length===1);
    checks.push('Tarjetas filtra por lote y muestra origen en Todos');

    await lot('Todos los lotes'); await nav('consultar');
    await p.locator('#consQ').fill('65'); await p.locator('#consQ').press('Enter');
    await p.getByRole('heading',{name:'Elige el lote de la tarjeta'}).waitFor();
    await p.getByRole('button',{name:'#0065 · Lote QA-2026-09',exact:true}).click();
    await p.locator('#sec-consultar .esc-ficha').getByText('TQT-R1-V30-0065',{exact:true}).waitFor();
    assert((await header().getAttribute('aria-label')).includes('Septiembre'), 'Consulta ambigua elige lote exacto');
    checks.push('Consulta de 65 en Todos requiere elegir lote');

    await nav('validacion');
    if (await p.getByRole('button',{name:'Cambiar tarjeta',exact:true}).isVisible()) await p.getByRole('button',{name:'Cambiar tarjeta',exact:true}).click();
    await p.getByRole('button',{name:'Ver tarjetas del lote',exact:true}).click();
    let picker = p.getByRole('dialog',{name:'Elige la tarjeta en prueba'});
    await picker.waitFor();
    await p.waitForFunction(()=>document.querySelectorAll('.tqt-picker-sheet .tqt-cardbtn').length===1);
    assert(await picker.locator('.tqt-cardbtn').count()===1, 'Pruebas: una tarjeta del lote seleccionado');
    assert((await picker.locator('.tqt-cardbtn').innerText()).includes('V30-0065'), 'Pruebas solo septiembre');
    await picker.getByRole('button',{name:'Cerrar',exact:true}).click();
    await lot('Todos los lotes');
    if (await p.getByRole('button',{name:'Cambiar tarjeta',exact:true}).isVisible()) await p.getByRole('button',{name:'Cambiar tarjeta',exact:true}).click();
    await p.getByRole('button',{name:'Ver tarjetas del lote',exact:true}).click();
    picker = p.getByRole('dialog',{name:'Elige la tarjeta en prueba'}); await picker.waitFor();
    await p.waitForFunction(()=>document.querySelectorAll('.tqt-picker-sheet .tqt-cardbtn').length===3);
    await picker.getByRole('button',{name:'Cerrar',exact:true}).click();
    checks.push('Selector de Pruebas TQT: un lote o todas las tarjetas, sin ejecutar pruebas físicas');
    await lot('Septiembre 2026');

    await nav('excel'); await p.getByRole('button',{name:'Descargar copia (.xlsx)',exact:true}).waitFor();
    assert(await p.getByRole('button',{name:'Descargar copia (.xlsx)',exact:true}).isEnabled(), 'Excel del lote disponible');
    await lot('Todos los lotes'); assert(await p.getByRole('button',{name:'Descargar copia (.xlsx)',exact:true}).isDisabled(), 'Todos no descarga Excel de otro lote');
    checks.push('Excel mensual exige lote concreto');

    await lot('Septiembre 2026'); await nav('resumen');
    await p.evaluate(()=>{
      const d=window.TQTEscritorio.secciones.get('programacion'), original=d.montar;
      d.montar=(host,ctx)=>{ const i=original(host,ctx); return {...i, ocupada:()=>window.__testBusy || i.ocupada()}; };
    });
    await nav('programacion'); await listCount(2);
    await p.evaluate(()=>window.__testBusy=true); await header().click(); await p.getByRole('menuitemradio',{name:/^Octubre 2026/}).click();
    assert((await header().getAttribute('aria-label')).includes('Septiembre'), 'No cambia de lote durante operación');
    await p.evaluate(()=>window.__testBusy=false); await lot('Octubre 2026'); await listCount(3);
    checks.push('Cambio bloqueado mientras está ocupada, habilitado al terminar');

    // Delay an old request across a lot switch: it must not populate the new view.
    let releaseOld, reachedOld;
    const gate = new Promise(resolve=>{ releaseOld=resolve; });
    const seen = new Promise(resolve=>{ reachedOld=resolve; });
    let hold = true;
    await p.route('**/api/pcb?tipo=R2&limit=500', async route => {
      if (hold && route.request().headers()['x-tqt-lote']==='3') {
        hold=false; const r=await route.fetch(); reachedOld(); await gate; await route.fulfill({response:r});
      } else await route.continue();
    });
    await nav('resumen'); await nav('programacion');
    await Promise.race([seen,new Promise((_,reject)=>setTimeout(()=>reject(Error('No llegó la petición a demorar')),5000))]);
    await lot('Septiembre 2026'); releaseOld(); await listCount(2);
    assert((await items().allTextContents()).every(t=>!t.includes('V20')), 'Respuesta tardía no mezcla el lote anterior');
    await p.unroute('**/api/pcb?tipo=R2&limit=500');
    checks.push('Respuesta antigua demorada descartada después de cambiar de lote');

    await p.reload(); await p.locator('#sec-programacion').waitFor();
    assert((await header().getAttribute('aria-label')).includes('Septiembre'), 'Recarga respeta última elección');
    for (const width of [1440,390]) {
      await p.setViewportSize({width,height:1000}); await search().fill('65'); await listCount(1);
      await p.waitForFunction(()=>document.documentElement.scrollWidth<=innerWidth);
      assert(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth), 'Sin desborde '+width);
      await p.screenshot({path:'C:/Users/usuario/Mi unidad/Inventario TQT/outputs/lotes_20261029/programacion_'+width+'.png',fullPage:true});
    }
    await lot('Todos los lotes'); await search().fill('65'); await listCount(2);
    await p.reload(); await p.locator('#sec-programacion').waitFor();
    assert((await header().getAttribute('aria-label')).includes('Todos los lotes'), 'Todos persiste también en móvil');
    await search().fill('65'); await listCount(2);
    checks.push('Selector de lotes usable en móvil y Todos persiste tras recarga');
    assert(await p.evaluate(()=>window.__hardwareCalls)===0, 'Ningún acceso físico');
    assert(errors.length===0, 'Errores JS: '+errors.join('; '));
    assert(writes.length===0, 'No programar ni crear trabajos: '+writes.join('; '));
    checks.push('1440/390 sin desborde; cero errores JS, escrituras API o accesos físicos');
    return {checks,errors,writes};
  } catch (e) {
    throw Error(e.message + '\nChecks: ' + checks.join(' | ') + '\nURL: ' + p.url() + '\nJS: ' + errors.join(' | ') + '\nDialog: ' + (await p.locator('.sheet').allTextContents()).join(' | '));
  } finally { await context.close(); }
}
