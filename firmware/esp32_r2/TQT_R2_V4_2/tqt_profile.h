#pragma once
#include <stdint.h>
struct __attribute__((packed)) TqtProfile {
    char magic[16]; uint32_t schema;
    char hw[8]; char fw[16]; char nombre[24]; char module[24];
    uint32_t capabilities; uint8_t otaKey[32];
};
static_assert(sizeof(TqtProfile) == 128, "Perfil OTA TQT incompatible");
extern const volatile TqtProfile tqtProfileStorage;
extern const TqtProfile tqtProfile;
