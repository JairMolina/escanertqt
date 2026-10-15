/* GATT receiver model: finite queue, byte offsets, reconnect and cancellation. No hardware. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { performance } = require('node:perf_hooks');
const source = fs.readFileSync(path.join(__dirname, '../app/static/js/esp32_ota.js'), 'utf8');
async function trial(chunk, cancel = false, loseResult = false, fast = false, generic = false, staleConnected = false, migrate = false, disconnectDiscovery = false) {
    const image = Uint8Array.from({length: 8197}, (_, i) => (i * 17 + 3) & 255);
    const manifest = new Uint8Array(138);
    new DataView(manifest.buffer).setUint32(48, image.length, true);
    const state = {state:'idle', offset:0, total:0, error:''};
    const records = {writes:0, reads:0, queued:0, commits:0, cancels:0, apiCancel:0, received:[], manifest:[], discoveryDrops:0,prepareCalls:0};
    let rebooted = false, resultLost = false, assigned = false, bridgeVerified = false;
    const storage = new Map(); const signal = new AbortController();
    const json = value => new DataView(new TextEncoder().encode(JSON.stringify(value)).buffer);
    const info = () => ({nombre:generic&&!assigned?'TQT_R2_V30_XXXX':migrate&&records.commits>=2?'TQT-R2-V30-0069':'TQT_R2_V30_0069', ota_protocol:1, boot_valid:true, chunk,
                         enrollment:generic&&!assigned?1:0,
                         partition:rebooted ? 0x150000 : 0x10000});
    const chars = {
        '0002': {readValue:async()=>json(info())},
        '0005': {readValue:async()=>{records.reads++; records.queued=0; return json(state);}},
        '0003': {writeValueWithResponse:async bytes=>{
            if (bytes[0]===1) {records.received=[];records.manifest=[];Object.assign(state,{state:'manifest',offset:0,total:138});}
            if (bytes[0]===4) Object.assign(state,{state:'enrollment',offset:0,total:286});
            if (bytes[0]===3) records.cancels++;
            if (bytes[0]===2) {records.commits++;rebooted=true;if(!staleConnected)device.gatt.disconnect();}
        }},
        '0004': {writeValueWithResponse:async bytes=>{
            assert.ok(++records.queued<=8, 'Firmware queue capacity exceeded');
            assert.ok(bytes.length<=chunk+4, 'Peer MTU payload exceeded');
            const offset=new DataView(bytes.buffer,bytes.byteOffset,bytes.byteLength).getUint32(0,true);
            assert.equal(offset,state.offset, 'Receiver cannot accept skipped/duplicate offset');
            records.writes++;state.offset+=bytes.length-4;
            if(state.state==='enrollment') {
                if(state.offset===286){assigned=true;state.state='idle';}
            } else if(state.state==='manifest') {
                records.manifest.push(...bytes.slice(4));
                if(state.offset===138) Object.assign(state,{state:'receiving',offset:0,total:image.length});
            } else {
                records.received.push(...bytes.slice(4));
                if(state.offset===image.length) state.state='ready';
            }
        }}
    };
    if (fast) {
        let listener;
        chars['0004'].properties = {writeWithoutResponse:true};
        chars['0005'].properties = {notify:true};
        chars['0005'].addEventListener = (_, fn) => {listener=fn;};
        chars['0005'].removeEventListener = (_, fn) => {if(listener===fn) listener=null;};
        const notify = () => {
            const v = new DataView(new ArrayBuffer(10));
            v.setUint8(0,['idle','manifest','receiving','ready','restarting','error','enrollment'].indexOf(state.state));
            v.setUint32(1,state.offset,true);v.setUint32(5,state.total,true);
            records.queued=0;listener?.({target:{value:v}});
        };
        chars['0005'].startNotifications=async()=>{};
        const control=chars['0003'].writeValueWithResponse;
        chars['0003'].writeValueWithResponse=async bytes=>{await control(bytes);notify();};
        const write=chars['0004'].writeValueWithResponse;
        chars['0004'].writeValueWithoutResponse=async bytes=>{
            const before=state.state; await write(bytes);
            if(records.queued===8 || state.state!==before) notify();
        };
        chars['0004'].writeValueWithResponse=async()=>{throw Error('Fast path must use write without response');};
    }
    const device={gatt:{connected:false,
        connect:async function(){this.connected=true;return {getPrimaryService:async()=>{
            if(disconnectDiscovery&&bridgeVerified&&records.commits===1&&records.discoveryDrops===0){
                this.connected=false;records.discoveryDrops++;
                throw Error('GATT Server is disconnected. Cannot retrieve services.');
            }
            return {getCharacteristic:async uuid=>chars[uuid.slice(4,8)]};
        }};},
        disconnect(){this.connected=false;records.queued=0;}
    }};
    const context=vm.createContext({window:{isSecureContext:true},navigator:{bluetooth:{requestDevice:async()=>device}},
        sessionStorage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},
        TextDecoder,Uint8Array,DataView,atob:s=>Buffer.from(s,'base64').toString('binary'),
        setTimeout,clearTimeout,performance,console});
    vm.runInContext(source,context);
    const api=async (url)=>{
        if(url.includes('/enroll/prepare/'))return {ok:true,data:{id:'enrollment',ticket:Buffer.alloc(286).toString('base64')}};
        if(url.includes('/enroll/result/')){assert.ok(assigned);return {ok:true,data:{assigned:true}};}
        if(url.includes('/prepare/')) {records.prepareCalls++;return {ok:true,data:{job_id:'simulation',manifest:Buffer.from(manifest).toString('base64'),encrypted_image:Buffer.from(image).toString('base64')}};}
        if(url.includes('/cancel/')) {records.apiCancel++;return {ok:true};}
        if(loseResult&&!resultLost) {resultLost=true;return {ok:false,error:'Simulated network failure after restart'};}
        if(migrate&&records.commits===1){bridgeVerified=true;return {ok:true,data:{verified:false,migration_required:true}};}
        return {ok:true,data:{verified:true,fw:'4.1',pcb:{id:66}}};
    };
    const options={pcb:{id:66,nombre:'TQT-R2-V30-0069'},firmwareId:'base-R2-v41',api,signal:signal.signal,
        stage:()=>{},committing:()=>{},progress:(done,total,timing)=>{
            assert.ok(done<=total && timing.elapsed>=0);
            if(cancel&&done>0) signal.abort();
        }};
    if(cancel) {
        await assert.rejects(context.window.TQTR2OTA.execute(options),/cancelada/);
        assert.equal(records.commits,0);assert.equal(records.apiCancel,1);
        assert.equal(context.window.TQTR2OTA.pending(),null);
    } else {
        if(loseResult) {
            await assert.rejects(context.window.TQTR2OTA.execute(options),/pendiente/);
            assert.ok(context.window.TQTR2OTA.pending());
            assert.equal(records.apiCancel,0);
            const writes=records.writes;
            await context.window.TQTR2OTA.execute(options,true);
            assert.equal(records.writes,writes,'Recovery must never send firmware again');
        } else assert.equal((await context.window.TQTR2OTA.execute(options)).verified,true);
        assert.equal(records.commits,migrate?2:1);
        assert.equal(records.prepareCalls,migrate?2:1,'Connection retries must not create extra firmware jobs');
        if(disconnectDiscovery)assert.equal(records.discoveryDrops,1);
        assert.equal(context.window.TQTR2OTA.pending(),null);
        assert.deepEqual(Uint8Array.from(records.manifest),manifest);
        assert.deepEqual(Uint8Array.from(records.received),image);
        const batches=Math.ceil(Math.ceil(138/chunk)/8)+Math.ceil(Math.ceil(image.length/chunk)/8);
        assert.equal(records.reads,fast?0:batches+2,'Status read budget must match transport');
    }
    return {chunk,cancel,loseResult,writes:records.writes,statusReads:records.reads};
}
(async()=>{
    for(const args of [[16,false,false],[180,false,false],[16,true,false],[180,false,true],
        [500,false,false,true],[500,true,false,true],[500,false,true,true],
        [500,false,false,true,true],[16,false,false,true,true],
        [500,false,false,true,true,true],
        [500,false,false,true,false,false,true],
        [500,false,false,true,false,false,true,true]]) console.log(await trial(...args));
    console.log('12 transport scenarios passed; no hardware accessed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
