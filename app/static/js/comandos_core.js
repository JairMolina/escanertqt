/* Pure catalog and payload logic. No network or hardware actions. */
(function(root){
'use strict';
const GROUPS = [
  {id:'all',label:'Todos los comandos',icon:'grid'},
  {id:'status',label:'Estado y diagnóstico',icon:'pulse'},
  {id:'movement',label:'Movimiento',icon:'move'},
  {id:'protection',label:'Protección del motor',icon:'shield'},
  {id:'io',label:'Entradas y salidas',icon:'sliders'},
  {id:'mapping',label:'Mapeo de señales',icon:'route'},
  {id:'system',label:'Sistema y mensajes',icon:'terminal'},
  {id:'reset',label:'Reinicios',icon:'reset'},
  {id:'protocol',label:'Protocolo',icon:'link'}
];
const KIND_LABELS={query:'Consulta',config:'Configuración',mixed:'Consulta / ajuste',action:'Acción',destructive:'Restablecimiento',protocol:'Protocolo'};
const normalize=s=>String(s??'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
function enrich(data){
 const ids = new Set();
 return data.commands.map(c=>{
  if(!Number.isInteger(c.id)||ids.has(c.id))throw new Error('ID de comando duplicado o inválido');
  ids.add(c.id);
  return {...c,input:c.input||'none',first:c.supported_versions[0]};
 });
}
function supported(c,hw,fw){return hw==='3.0'&&c.supported_versions.includes(fw);}
function filterCommands(commands,state,favorites=[]){
 const terms=normalize(state.q).trim().split(/\s+/).filter(Boolean);
 return commands.filter(c=>{
  if(state.hw!=='3.0')return false;
  if(state.compatible&&!supported(c,state.hw,state.fw))return false;
  if(state.channel!=='all'&&c.channel!==state.channel)return false;
  if(state.group!=='all'&&c.group!==state.group)return false;
  if(state.kind!=='all'&&c.kind!==state.kind)return false;
  if(state.favoriteOnly&&!favorites.includes(c.id))return false;
  if(state.newOnly&&(state.fw==='4.1'||c.first!==state.fw))return false;
  const haystack=normalize([c.command,c.title,c.description,c.values,c.example,GROUPS.find(g=>g.id===c.group)?.label,c.channel].join(' '));
  return terms.every(t=>haystack.includes(t));
 });
}
function initialValue(c){
 if(c.input==='none')return '';
 if(c.input==='separator')return c.id===20?'|':':';
 return c.example.slice(c.example.lastIndexOf(c.command.includes(';')?';':':')+1);
}
function operationKind(c,value){
 if(c.input==='input')return String(value)==='3'?'query':'config';
 if(c.input==='protection')return value==='?'?'query':'config';
 return c.kind;
}
function validateValue(c,value,otherSeparator,format='serial'){
 const s=String(value);
 if(c.input==='none')return '';
 const choices={sensors:['0','1'],binary:['0','1'],protection:['0','1','?'],mapping:['0','1'],input:['0','1','2','3'],output:['0','1'],blocking:['0','1','2','3','4']};
 if(choices[c.input]&&!choices[c.input].includes(s))return 'Elige uno de los valores documentados.';
 if(c.input==='time'&&(!/^\d+$/.test(s)||Number(s)<0||Number(s)>10))return 'Usa un número entero de 0 a 10.';
 if(c.input==='name'){
  if(!s.length)return 'Escribe un nombre. La documentación no confirma el uso de un nombre vacío.';
  if([...s].length>22)return 'El nombre admite hasta 22 caracteres.';
  if(/[\r\n]/.test(s))return 'El nombre no puede incluir saltos de línea en este constructor.';
  if(format==='platform'&&s.includes('"'))return 'El formato Plataforma encierra el comando entre comillas dobles. Usa un nombre sin comillas dobles.';
 }
 if(c.input==='separator'){
  if([...s].length!==1||/["'\r\n]/.test(s))return 'Usa un carácter, sin comillas ni saltos de línea.';
  if([...String(otherSeparator)].length!==1||/["'\r\n]/.test(String(otherSeparator)))return 'Indica el otro separador actual: un carácter válido.';
  if(s===otherSeparator)return 'Los dos separadores deben ser distintos.';
 }
 return '';
}
function supportsPlatform(c){return c.channel==='Serial/GPS'&&c.command.startsWith('$SMSG=');}
function outputFormatFor(c,requestedFormat){
 if(c.channel==='Bluetooth')return 'bluetooth';
 return supportsPlatform(c)&&requestedFormat==='platform'?'platform':'serial';
}
function buildPayload(c,value,includeCRLF=false,format='serial'){
 let command=c.example;
 if(c.input!=='none'){
  command=c.command.replace(/(:n|;n|:texto|;c)$/,match=>match[0]+String(value));
 }
 const outputFormat=outputFormatFor(c,format);
 if(outputFormat==='platform')return `AT$SMSG=1,0,"${command.slice('$SMSG='.length)}"`;
 return command+(outputFormat==='serial'&&includeCRLF?'\r\n':'');
}
function compareCommands(commands,from,to){
 return commands.map(c=>({...c,inFrom:c.supported_versions.includes(from),inTo:c.supported_versions.includes(to)}));
}
function related(c,value){
 const fixed={0:[27],1:[28],2:[3,4],3:[2],4:[24],7:[8,9,String(value)==='0'?35:34],8:[36,7],9:value==='?'?[8]:[7,8],10:[11,12],11:[10,12],12:[10,11],25:[29],27:[0],28:[1],29:[25],30:[13],31:[13],32:[14],33:[14],34:[7,8],35:[7,8],36:[8]};
 if(c.id===13)return value==='0'?[31]:value==='2'?[30]:[];
 if(c.id===14)return value==='0'?[33]:value==='2'?[32]:[];
 if(c.id===5)return [6];
 if(c.id===6)return [5];
 return fixed[c.id]||[];
}
function technicalNotes(c){
 const notes=[];
 if(c.group==='protection')notes.push('En FW4.1–4.3 el paro por sobrecorriente está fijo en la lógica. FW4.4 incorpora el ajuste configurable, que inicia en 0 (desactivado).','PARO_C se informa en una línea separada: PARO_C:0 o PARO_C:1. No añade un campo a la trama S29.');
 if([7,9,34,35].includes(c.id))notes.push('El ajuste se conserva tras reinicio cuando el guardado se confirma.');
 if(c.id===36)notes.unshift('La consulta se envía por Bluetooth, pero la respuesta se genera por Serial/GPS. El puente actual no implementa una notificación BLE para esta respuesta.');
 if(c.id===9)notes.unshift('PROT_C es un alias de PARO_C. Admite 0 para desactivar, 1 para activar y ? para consultar.');
 if(c.id===6)notes.push('El límite nominal es 4 + n segundos tanto para abrir como para cerrar. No representa la duración exacta de todo el proceso.','Con Sensores:0, alcanzar el sensor puede terminar antes. Con Sensores:1, se trabaja con el límite de tiempo. La pausa posterior de 3 s es independiente.');
 if([6,7,9,11,12].includes(c.id))notes.push('Si aparece «ajuste no confirmado» o «EEPROM ERROR», no asumas que el ajuste quedó persistido: revisa la unidad.');
 if([11,12].includes(c.id))notes.unshift('El cambio de mapeo solo se permite con el motor detenido.');
 if([13,14,15].includes(c.id))notes.push('Los valores 1 y 2 habilitan seguimiento; las fuentes no especifican aquí una diferencia funcional entre ambos. El valor 3 hace una lectura puntual sin cambiar la configuración.');
 if([16,17].includes(c.id))notes.push('0 y 1 son niveles lógicos; no representan una tensión ni describen el cableado. OUT_3 aparece como estado, pero no tiene comando de edición documentado.');
 if(c.id===19)notes.push('El nombre de ejemplo no es una identidad universal. Revisa el inventario antes de cambiarlo. La identidad fija continúa en Flash.');
 if([20,21].includes(c.id))notes.push('SPAS separa campos y SPAV separa el nombre de su valor. Deben ser distintos. Introduce el valor actual del otro separador; el nuevo valor comienza con un ejemplo y el otro separador comienza con su valor de fábrica.');
 if(c.id===22)notes.push('Este ajuste controla mensajes de eventos TQT; no es MODO_DEBUG ni la selección de compilación Debug/Release.');
 if(c.id===23)notes.push('Reset reinicia la tarjeta y no es un restablecimiento de fábrica.');
 if(c.id===24)notes.push('Reset_BLE reinicia la alimentación del módulo Bluetooth.');
 if([25,29].includes(c.id))notes.push('Restablece valores predeterminados y reinicia. Se pierde la configuración personalizada de EEPROM. El comando Reset_44 está documentado en FW4.1, 4.2, 4.3 y 4.4.');
 if(c.id===26)notes.push('Es una confirmación del protocolo GPS, no una orden de operador. $OK y OK son las formas documentadas.');
 if(c.id===2)notes.push('El estado general incluye VER, HW, TIEMPO y SEN_MOT, entre otros campos. Usa la versión interna del firmware, no el nombre del archivo HEX.','MOTOR es un campo histórico del estado. No existe un comando $SMSG=MOTOR:... en los parsers revisados.');
 if(c.id===3)notes.push('Los valores iniciales S_ON y S_OFF no garantizan por sí solos una posición física del perno.');
 return notes;
}
function careNote(c,value){
 if(c.kind==='destructive')return 'Restablece la configuración personalizada de EEPROM y reinicia la tarjeta.';
 if([0,1,27,28].includes(c.id))return 'Este comando mueve el perno. Comprueba el estado físico del equipo antes de utilizarlo.';
 if([11,12].includes(c.id))return 'Cambia las parejas de señales. El motor debe estar detenido.';
 if([16,17,18].includes(c.id))return 'Modifica una salida. Comprueba las señales y el estado físico del equipo.';
 if([23,24].includes(c.id))return 'Reinicia el equipo o su módulo. Comprueba el estado físico antes de utilizarlo.';
 if(c.id===19)return 'Revisa la identidad de la unidad en el inventario antes de cambiar su nombre.';
 if(c.group==='protection'&&operationKind(c,value)!=='query')return 'Modifica el paro por sobrecorriente. En FW4.4, el valor de fábrica es 0: desactivado.';
 if(c.requires_care&&operationKind(c,value)!=='query')return 'Cambia la configuración del equipo. Revisa el valor elegido antes de utilizarlo.';
 return '';
}



const api={GROUPS,KIND_LABELS,normalize,enrich,supported,filterCommands,initialValue,operationKind,validateValue,supportsPlatform,outputFormatFor,buildPayload,compareCommands,related,technicalNotes,careNote};
if(typeof module==='object'&&module.exports)module.exports=api;else root.TQTCommands=api;
})(globalThis);
