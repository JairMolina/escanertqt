#include "tqt_identity.h"
#include "Datos_editar.h"
#include <string.h>
#include "tqt_identity_generated.h"

/* Kept in the firmware region. Personalizers must obey this immutable profile. */
typedef struct __attribute__((packed)) {
    char marker[8]; char mcu[16]; char fw[8]; char hw[8];
    uint16_t schema; uint16_t identity_size; uint32_t identity_address;
} TQT_FirmwareProfile;
_Static_assert(sizeof(TQT_FirmwareProfile) == 48, "profile size");
__attribute__((used, aligned(4), section(".tqt_fwmeta")))
const TQT_FirmwareProfile tqt_firmware_profile = {
    "TQTFWM2", TQT_MCU_NAME, TQT_FW_VERSION, TQT_HW_COMPATIBLE,
    TQT_IDENTITY_SCHEMA, TQT_IDENTITY_SIZE, TQT_IDENTITY_ADDRESS
};
static TQT_Identity active;
uint32_t TQT_IdentityCRC32(const uint8_t *bytes, size_t length) {
    uint32_t crc=0xFFFFFFFFUL;
    for (size_t i=0; i<length; ++i) {
        crc ^= bytes[i];
        for (unsigned b=0; b<8; ++b)
            crc=(crc>>1) ^ ((0U-(crc&1U)) & 0xEDB88320UL);
    }
    return crc ^ 0xFFFFFFFFUL;
}
static int canonical(const char *s, size_t n) {
    size_t end=0;
    while (end<n && s[end]) ++end;
    if (end==0 || end==n) return 0;
    for (size_t i=end; i<n; ++i) if (s[i]!=0) return 0;
    return 1;
}
static int hex_upper(char c) {
    return (c>='0' && c<='9') || (c>='A' && c<='F');
}
TQT_IdentityResult TQT_IdentityValidate(const TQT_Identity *d) {
    if (d->magic!=TQT_IDENTITY_MAGIC || d->schema!=TQT_IDENTITY_SCHEMA ||
        d->length!=sizeof(*d) || d->reserved!=0) return TQT_ID_FORMAT;
    if (TQT_IdentityCRC32((const uint8_t *)d, offsetof(TQT_Identity, crc32))!=d->crc32)
        return TQT_ID_CRC;
    if (!canonical(d->name,sizeof d->name) || !canonical(d->id_r,sizeof d->id_r) ||
        !canonical(d->mac_r,sizeof d->mac_r) || !canonical(d->hw,sizeof d->hw) ||
        !canonical(d->fw,sizeof d->fw)) return TQT_ID_FIELDS;
    if (strlen(d->id_r)!=4 || strlen(d->mac_r)!=17) return TQT_ID_FIELDS;
    for (unsigned i=0;i<4;++i)
        if (d->id_r[i]<'0' || d->id_r[i]>'9') return TQT_ID_FIELDS;
    for (unsigned i=0;i<17;++i)
        if (i%3==2 ? d->mac_r[i]!=':' : !hex_upper(d->mac_r[i])) return TQT_ID_FIELDS;
    if (strcmp(d->mac_r,"00:00:00:00:00:00")==0 ||
        strcmp(d->mac_r,"FF:FF:FF:FF:FF:FF")==0) return TQT_ID_FIELDS;
    if (strcmp(d->hw,TQT_HW_COMPATIBLE)!=0) return TQT_ID_HW;
    if (strcmp(d->fw,TQT_FW_VERSION)!=0) return TQT_ID_FW;
    /* Name encodes R1/HW and its OWN serial; id_r belongs to the associated R2. */
    char expected[23]="TQT_R1_V";
    size_t pos=8;
    for (size_t i=0;d->hw[i];++i) {
        if (d->hw[i]=='.') continue;
        if (d->hw[i]<'0' || d->hw[i]>'9' || pos>=17) return TQT_ID_FIELDS;
        expected[pos++]=d->hw[i];
    }
    expected[pos++]='_';
    if (strlen(d->name)!=pos+4 || strncmp(d->name,expected,pos)!=0)
        return TQT_ID_FIELDS;
    for (size_t i=pos;i<pos+4;++i)
        if (d->name[i]<'0' || d->name[i]>'9') return TQT_ID_FIELDS;
    return TQT_ID_OK;
}
TQT_IdentityResult TQT_IdentityLoad(void) {
    /* volatile physical reads prevent using compiler-folded template strings. */
    const volatile uint8_t *flash=(const volatile uint8_t *)TQT_IDENTITY_ADDRESS;
    uint8_t *ram=(uint8_t *)&active;
    for (size_t i=0;i<sizeof(active);++i) ram[i]=flash[i];
    TQT_IdentityResult result=TQT_IdentityValidate(&active);
    if (result!=TQT_ID_OK) memset(&active,0,sizeof active);
    return result;
}
const TQT_Identity *TQT_IdentityGet(void) { return &active; }
