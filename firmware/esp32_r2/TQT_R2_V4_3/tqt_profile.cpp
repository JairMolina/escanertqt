#include "tqt_profile.h"
const volatile TqtProfile tqtProfileStorage __attribute__((used)) = {
    "TQT_R2_CFG_V1", 2, "3.0", "4.3", "TQT-R2-V30-0000", "ESP32-WROOM-32E-N4", 1, {0}
};
static TqtProfile loadProfile() {
    TqtProfile value;
    const volatile uint8_t *src = reinterpret_cast<const volatile uint8_t *>(&tqtProfileStorage);
    uint8_t *dst = reinterpret_cast<uint8_t *>(&value);
    for (unsigned i=0;i<sizeof(value);++i) dst[i]=src[i];
    return value;
}
const TqtProfile tqtProfile=loadProfile();
