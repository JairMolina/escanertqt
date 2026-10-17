#pragma once
#include <stdint.h>
#include "tqt_offline_wire.h"

bool tqtOfflineInit();
bool tqtOfflineAvailable();
bool tqtOfflineInfoFrame(const uint8_t nonce[16],const uint8_t appDigest[32],
    const uint8_t legacyProof[32],uint32_t partition,bool bootValid,const uint8_t mac[6],
    uint8_t frame[TqtOfflineWire::INFO_BYTES]);
bool tqtOfflineAuthorize(const uint8_t manifest[TqtOfflineWire::SESSION_BYTES],
    const uint8_t nonce[16],const uint8_t appDigest[32],const uint8_t mac[6],
    uint32_t slotSize,uint8_t imageKey[32]);
// Call before esp_ota_set_boot_partition for EVERY OTA, including online.
bool tqtOfflineConsume(const uint8_t *grantUuid);
