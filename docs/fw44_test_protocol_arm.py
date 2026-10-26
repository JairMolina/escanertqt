from pathlib import Path
import sys,re,subprocess,struct,json,argparse
args=argparse.ArgumentParser()
args.add_argument('--out',type=Path,required=True)
args.add_argument('--deps',type=Path)
args.add_argument('--project',type=Path,default=Path(__file__).resolve().parents[1])
opts=args.parse_args();out=opts.out.resolve();out.mkdir(parents=True,exist_ok=True)
project=opts.project.resolve()
if opts.deps:sys.path.insert(0,str(opts.deps.resolve()))
sys.path.insert(0,str(project/'tools'))
from test_config_arm import function
from unicorn import Uc,UC_ARCH_ARM,UC_MODE_THUMB,UC_MODE_MCLASS
from unicorn.arm_const import UC_ARM_REG_SP,UC_ARM_REG_LR
src=(project/'Core/Src/main.c').read_text(encoding='utf-8')
parser=function(src,'Mensaje_Atrack');ble=function(src,'BLE_Check_Viva')
clean=re.sub(r'//[^\n]*','',parser)
calls=set(re.findall(r'\b([A-Za-z_]\w*)\s*\(',clean))-{'Mensaje_Atrack','if','strncmp'}
real={'TQT_ON_GPS','TQT_OFF_GPS','Reset_gps','Debug','ComandoExacto'}
stubs='\n'.join('void '+n+'() {}' for n in sorted(calls-real))
c=r'''
#include <stdint.h>
#include <string.h>
volatile uint32_t observed[8];
static unsigned opens,closes,resets;
static int good;
uint8_t rxBuffer1[256]; uint16_t rxReadIndex1,rxWriteIndex1;
#define RX_BUFFER_SIZE 256
void TQT_ON_GPS(void) {++opens;}
void TQT_OFF_GPS(void) {++closes;}
void Reset_gps(int x) {(void)x;++resets;}
void Debug(const char*s) {(void)s;}
void HAL_Delay(uint32_t x) {(void)x;}
void Serial_BLE(const char*s) {(void)s;const char*r=good?"SIMON\r\n":"BAD\r\n";strcpy((char*)rxBuffer1,r);rxReadIndex1=0;rxWriteIndex1=strlen(r);}
'''+stubs+'\n'+function(src,'ComandoExacto')+'\n'+parser+'\n'+ble+r'''
void run_tests(void) {
 Mensaje_Atrack("$SMSG=ONINVALIDO\r\n"); observed[0]=opens;
 Mensaje_Atrack("$SMSG=OFFINVALIDO\r\n"); observed[1]=closes;
 for(int i=0;i<5;i++) {good=0;BLE_Check_Viva();good=1;BLE_Check_Viva();}
 observed[2]=resets;
 Mensaje_Atrack("$SMSG=ON\r\n"); observed[3]=opens;
 Mensaje_Atrack("$SMSG=OFF\n"); observed[4]=closes;
 observed[5]=ComandoExacto("PPONINVALIDO\r\n","PPON");
 observed[6]=ComandoExacto("$SMSG=ON\rBASURA\n","$SMSG=ON");
 observed[7]=ComandoExacto("PPON\r\n","PPON");
}
'''
(out/'extra.c').write_text(c,encoding='utf-8')
(out/'test.ld').write_text('ENTRY(run_tests)\nMEMORY { FLASH (rx) : ORIGIN = 0x08000000, LENGTH = 256K\n RAM (rwx) : ORIGIN = 0x20000000, LENGTH = 64K }\nSECTIONS { .text : { *(.text*) *(.rodata*) } > FLASH\n .data : { *(.data*) } > RAM AT> FLASH\n .bss : { *(.bss*) *(COMMON) . = ALIGN(8); end = .; } > RAM }')
cc=next(Path(r'C:/ST/STM32CubeIDE_2.1.0/STM32CubeIDE/plugins').glob('*gnu-tools-for-stm32*/tools/bin'))
elf=out/'extra.elf'
subprocess.run([str(cc/'arm-none-eabi-gcc.exe'),str(out/'extra.c'),'-mcpu=cortex-m3','-mthumb','-O0','-Wall','-Wextra','-ffunction-sections','-fdata-sections','--specs=nano.specs','--specs=nosys.specs','-nostartfiles','-Wl,--gc-sections','-T'+str(out/'test.ld'),'-o',str(elf)],check=True,capture_output=True)
symbols={}
for line in subprocess.check_output([str(cc/'arm-none-eabi-nm.exe'),str(elf)],text=True).splitlines():
 bits=line.split()
 if len(bits)==3:symbols[bits[2]]=int(bits[0],16)
data=elf.read_bytes();mu=Uc(UC_ARCH_ARM,UC_MODE_THUMB|UC_MODE_MCLASS)
mu.mem_map(0x08000000,0x80000);mu.mem_map(0x20000000,0x10000)
phoff=struct.unpack_from('<I',data,28)[0];phsize,phnum=struct.unpack_from('<HH',data,42)
for n in range(phnum):
 typ,offset,va,pa,filesz,memsz,flags,align=struct.unpack_from('<8I',data,phoff+n*phsize)
 if typ==1 and filesz:mu.mem_write(va,data[offset:offset+filesz])
mu.reg_write(UC_ARM_REG_SP,0x2000FFF0);mu.reg_write(UC_ARM_REG_LR,0x0807F001)
mu.emu_start(symbols['run_tests']|1,0x0807F000,timeout=10_000_000,count=5_000_000)
vals=struct.unpack('<8I',mu.mem_read(symbols['observed'],32))
r={'invalid_ON_dispatches':vals[0],'invalid_OFF_dispatches':vals[1],'ble_resets_with_5_failures_interleaved_with_5_successes':vals[2],'valid_ON_dispatches':vals[3],'valid_OFF_dispatches':vals[4],'invalid_BLE_match':vals[5],'invalid_CR_suffix_match':vals[6],'valid_BLE_match':vals[7],'physical_hardware':False}
(out/'extra_results.json').write_text(json.dumps(r,indent=2),encoding='utf-8');print(json.dumps(r,indent=2))

assert vals == (0,0,0,1,1,0,0,1), vals
