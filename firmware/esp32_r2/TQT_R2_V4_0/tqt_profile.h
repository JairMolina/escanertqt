#pragma once
#include <stdint.h>
// Contrato binario V1: no cambiar el orden ni las longitudes de los campos.
struct __attribute__((packed)) TqtProfile {
    char magic[16];
    uint32_t schema;
    char hw[8];
    char fw[16];
    char nombre[24];
    char module[24];
};
static_assert(sizeof(TqtProfile) == 92, "Perfil TQT incompatible");
// Se conserva en la imagen y se lee desde Flash. La web solo cambia nombre.
const volatile TqtProfile tqtProfileStorage __attribute__((used)) = {
    "TQT_R2_CFG_V1", 1, "3.0", "4.0", "TQT_R2_V30_0000", "ESP32-WROOM-32E-N4"
};
// Copia con lecturas volátiles: el compilador no debe sustituir campos por literales.
inline TqtProfile loadTqtProfile() {
    TqtProfile profile;
    const volatile uint8_t *source = reinterpret_cast<const volatile uint8_t *>(&tqtProfileStorage);
    uint8_t *target = reinterpret_cast<uint8_t *>(&profile);
    for (unsigned i = 0; i < sizeof(profile); ++i) target[i] = source[i];
    return profile;
}
const TqtProfile tqtProfile = loadTqtProfile();
