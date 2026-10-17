#pragma once
#include <stddef.h>
#include <stdint.h>
#include <string.h>

// Wire layout is normative in protocols/offline-v1.json. No packed casts.
namespace TqtOfflineWire {
constexpr size_t BODY_BYTES=344, GRANT_BYTES=408, SESSION_BYTES=472;
constexpr size_t INFO_BYTES=190;
constexpr size_t UUID=16, DEVICE_KEY=32, PHONE_KEY=97, IV=162, COUNTER=178,
    SOURCE_DIGEST=182, TRANSFER_DIGEST=214, TARGET_DIGEST=246, IMAGE_BYTES=278,
    NAME=282, HARDWARE=306, FIRMWARE=314, MAC=330, ANCHOR=336, SERVER_SIG=344,
    PHONE_SIG=408;
constexpr char MAGIC[16]="TQT-OFFLINE-v1";
constexpr char IDENTITY_LABEL[]="TQT-OFFLINE-IDENTITY-v1";
constexpr char INFO_LABEL[]="TQT-OFFLINE-INFO-v1";
constexpr char SESSION_LABEL[]="TQT-OFFLINE-SESSION-v1";
constexpr char IMAGE_KEY_LABEL[]="TQT-OFFLINE-DATA-v1";
inline uint32_t read32(const uint8_t *p) {
    return uint32_t(p[0])|(uint32_t(p[1])<<8)|(uint32_t(p[2])<<16)|(uint32_t(p[3])<<24);
}
inline void write32(uint8_t *p,uint32_t v) { for(unsigned i=0;i<4;++i) p[i]=uint8_t(v>>(8*i)); }
inline bool canonicalAscii(const uint8_t *p,size_t count) {
    bool ended=false;
    for(size_t i=0;i<count;++i) {
        if(!p[i]) ended=true;
        else if(ended||p[i]<32||p[i]>126) return false;
    }
    return ended&&p[0]!=0;
}
// Decimal versions contain 2..4 components, no leading zeroes, maximum 15 bytes.
// Compare as a four-component tuple, treating absent components as zero.
inline bool version(const uint8_t *p,uint64_t out[4]) {
    if(!canonicalAscii(p,16)) return false;
    for(unsigned i=0;i<4;++i) out[i]=0;
    unsigned component=0,digits=0;bool firstZero=false;
    for(size_t i=0;i<16;++i) {
        uint8_t c=p[i];
        if(c==0) return digits>0&&component>=1;
        if(c=='.') {
            if(!digits||component>=3) return false;
            ++component;digits=0;firstZero=false;continue;
        }
        if(c<'0'||c>'9'||(digits&&firstZero)) return false;
        if(!digits) firstZero=c=='0';
        if(out[component]>(UINT64_MAX-uint64_t(c-'0'))/10) return false;
        out[component]=out[component]*10+uint64_t(c-'0');++digits;
    }
    return false;
}
inline bool supportedVersion(const uint8_t *p) {
    uint64_t v[4];return version(p,v)&&(v[0]>4||(v[0]==4&&v[1]>=3));
}
}
