async (page) => {
 const ctx=await page.context().browser().newContext(); const p=await ctx.newPage(); const errors=[];
 p.on('pageerror',e=>errors.push(e.message));
 await p.goto('http://127.0.0.1:18081/login?next=%2Fmonitor');
 await p.locator('#email').fill('developer4@skyguardian.mx');await p.locator('#pass').fill('prueba-aislada-r2-v4');
 await p.locator('button[type=submit]').first().click();await p.waitForURL('**/monitor**');
 const cards=await p.evaluate(async()=>await(await fetch('/api/pcb?tipo=R2&limit=500')).json());
 const pcb=cards.items.find(x=>x.serie==='0069');let verified=false,attempts=0;
 await p.addInitScript(()=>{
   window.testBauds=[];
   const port={getInfo:()=>({usbVendorId:0x1a86,usbProductId:0x7523}),open:async function(){
     this.readable=new ReadableStream({start(c){c.enqueue(new TextEncoder().encode('TQT_INFO '+JSON.stringify({nombre:'TQT_R2_V30_0069',hw:'3.0',fw:'4.0',mac:'02:00:00:00:00:69',ota_protocol:1,key_id:'0123456789abcdef'})+'\n'));}});
     this.writable=new WritableStream({write(){}});
   },close:async function(){this.readable=null;this.writable=null;}};
   Object.defineProperty(navigator,'serial',{value:{getPorts:async()=>[port],requestPort:async()=>port,addEventListener(){},removeEventListener(){}}});
 });
 await p.route('**/static/js/vendor/esptool-js/bundle.js',r=>r.fulfill({contentType:'application/javascript',body:`
 export class Transport{constructor(p){this.p=p;}async disconnect(){await this.p.close();}}
 export class ESPLoader{constructor(o){this.o=o;window.testBauds.push(o.baudrate);}async main(){return 'ESP32 simulado';}
 async writeFlash(o){if(this.o.baudrate>115200)throw Error('fallo simulado alta velocidad');o.reportProgress(0,100,100);}async after(){}}`}));
 await p.route('**/api/stm32/stations',r=>r.fulfill({json:[{id:'a'.repeat(24),name:'Agente simulado',local:true,online:true}]}));
 await p.route('**/api/esp32/r2/status',r=>r.fulfill({json:{items:[{pcb_id:pcb.id,state:verified?'outdated':'unprogrammed',verified,installed_fw:verified?'4.0':null,latest_fw:'4.1.1',evidence:verified?{method:'serial'}:null}]}}));
 await p.route('**/api/esp32/ota/capability/*',r=>r.fulfill({json:{eligible:false,current_fw:'',requires_serial:true}}));
 await p.route('**/api/esp32/bin/*',r=>r.fulfill({body:Buffer.from([1,2,3]),headers:{'Content-Type':'application/octet-stream','X-TQT-Nombre-Ble':'TQT_R2_V30_0069','X-TQT-Firmware':'4.0','X-TQT-Hardware':'3.0','X-TQT-Firmware-Id':'base-R2-v40-ota','X-TQT-OTA-Protocol':'1','X-TQT-Key-Id':'0123456789abcdef'}}));
 await p.route('**/api/esp32/r2/*/attempts',r=>{attempts++;return r.fulfill({json:{id:'mock-r2',state:'flashing'}});});
 await p.route('**/api/esp32/r2/attempts/mock-r2/ready',r=>r.fulfill({json:{state:'queued'}}));
 await p.route('**/api/esp32/r2/attempts/mock-r2',r=>{verified=true;return r.fulfill({json:{state:'verified',result:{verified:true,fw:'4.0',pcb:{...pcb,mac:'02:00:00:00:00:69',firmware:'4.0'}}}});});
 await p.goto('http://127.0.0.1:18081/monitor?serial-test=1#/programacion');
 await p.getByText(pcb.nombre,{exact:true}).click();
 await p.getByRole('button',{name:'Instalar base 4.0 OTA por USB',exact:true}).click();
 await p.getByRole('button',{name:'Ya está en BOOT',exact:true}).click();
 await p.getByRole('button',{name:'Ya reinicié',exact:true}).click();
 await p.getByText('Guardado ✓',{exact:false}).waitFor();
 const result={errors,attempts,bauds:await p.evaluate(()=>window.testBauds),automaticBleValidated:verified,
   maintenanceHidden:!(await p.locator('#prog-flash-baud').isVisible())};
 await ctx.close();return result;
}
