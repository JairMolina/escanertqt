#include "tqt_offline.h"
#include "tqt_profile.h"
#include "enrollment_trust.h"
#include <esp_system.h>
#include <esp_random.h>
#include <nvs.h>
#include <mbedtls/ecp.h>
#include <mbedtls/ecdsa.h>
#include <mbedtls/md.h>
#include <mbedtls/sha256.h>
#include <mbedtls/platform_util.h>
#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>

using namespace TqtOfflineWire;
// Referenced by the crypto self-test, retaining the marker in the linked app.
static const char OFFLINE_MARKER[]="TQT_OFFLINE_V1_P256";
struct __attribute__((packed)) Persistent {
    uint8_t magic[8];
    uint8_t privateKey[32];
    uint8_t counter[4];
    uint8_t lastGrant[16];
    uint8_t checksum[32];
};
static_assert(sizeof(Persistent)==92,"Offline NVS schema mismatch");
static Persistent persistent={};
static uint8_t publicKey[65]={0},anchorId[8]={0};
static uint8_t cachedInfoHash[32]={0},cachedInfo[INFO_BYTES]={0};
static bool cachedInfoValid=false;
static bool available=false;
static nvs_handle_t store=0;
static SemaphoreHandle_t mutex=nullptr;
static const uint8_t NVS_MAGIC[8]={'T','Q','T','O','F','F',1,0};

static bool equal(const uint8_t *a,const uint8_t *b,size_t size) {
    uint8_t diff=0;for(size_t i=0;i<size;++i) diff|=a[i]^b[i];return diff==0;
}
static int randomBytes(void *,unsigned char *out,size_t size) { esp_fill_random(out,size);return 0; }
static bool sha(const uint8_t *p,size_t size,uint8_t out[32]) { return mbedtls_sha256(p,size,out,0)==0; }
static bool unitHmac(const uint8_t *p,size_t size,uint8_t out[32]) {
    return mbedtls_md_hmac(mbedtls_md_info_from_type(MBEDTLS_MD_SHA256),tqtProfile.otaKey,32,p,size,out)==0;
}
static bool checksum(Persistent &value) {
    return sha(reinterpret_cast<const uint8_t *>(&value),offsetof(Persistent,checksum),value.checksum);
}
static bool valid(const Persistent &value) {
    uint8_t hash[32];return equal(value.magic,NVS_MAGIC,8)&&
        sha(reinterpret_cast<const uint8_t *>(&value),offsetof(Persistent,checksum),hash)&&equal(hash,value.checksum,32);
}
static bool persist(Persistent &next) {
    if(!checksum(next)||nvs_set_blob(store,"state_v1",&next,sizeof(next))!=ESP_OK||nvs_commit(store)!=ESP_OK) return false;
    Persistent readback={};size_t size=sizeof(readback);
    bool ok=nvs_get_blob(store,"state_v1",&readback,&size)==ESP_OK&&size==sizeof(readback)&&
        valid(readback)&&equal(reinterpret_cast<uint8_t *>(&next),reinterpret_cast<uint8_t *>(&readback),sizeof(next));
    mbedtls_platform_zeroize(&readback,sizeof(readback));return ok;
}
static bool publicFromPrivate(const uint8_t key[32],uint8_t out[65]) {
    mbedtls_ecp_keypair pair;mbedtls_ecp_keypair_init(&pair);size_t written=0;
    bool ok=mbedtls_ecp_read_key(MBEDTLS_ECP_DP_SECP256R1,&pair,key,32)==0&&
        mbedtls_ecp_mul(&pair.MBEDTLS_PRIVATE(grp),&pair.MBEDTLS_PRIVATE(Q),&pair.MBEDTLS_PRIVATE(d),
            &pair.MBEDTLS_PRIVATE(grp).G,randomBytes,nullptr)==0&&
        mbedtls_ecp_point_write_binary(&pair.MBEDTLS_PRIVATE(grp),&pair.MBEDTLS_PRIVATE(Q),
            MBEDTLS_ECP_PF_UNCOMPRESSED,&written,out,65)==0&&written==65;
    mbedtls_ecp_keypair_free(&pair);return ok;
}
static bool verify(const uint8_t key[65],const uint8_t *data,size_t size,const uint8_t signature[64]) {
    uint8_t hash[32];if(key[0]!=4||!sha(data,size,hash)) return false;
    mbedtls_ecp_group group;mbedtls_ecp_point q;mbedtls_mpi r,s;
    mbedtls_ecp_group_init(&group);mbedtls_ecp_point_init(&q);mbedtls_mpi_init(&r);mbedtls_mpi_init(&s);
    bool ok=mbedtls_ecp_group_load(&group,MBEDTLS_ECP_DP_SECP256R1)==0&&
        mbedtls_ecp_point_read_binary(&group,&q,key,65)==0&&mbedtls_ecp_check_pubkey(&group,&q)==0&&
        mbedtls_mpi_read_binary(&r,signature,32)==0&&mbedtls_mpi_read_binary(&s,signature+32,32)==0&&
        mbedtls_ecdsa_verify(&group,hash,32,&q,&r,&s)==0;
    mbedtls_mpi_free(&r);mbedtls_mpi_free(&s);mbedtls_ecp_point_free(&q);mbedtls_ecp_group_free(&group);return ok;
}
static bool sign(const uint8_t *data,size_t size,uint8_t signature[64]) {
    uint8_t hash[32];if(!sha(data,size,hash)) return false;
    mbedtls_ecp_keypair pair;mbedtls_mpi r,s;
    mbedtls_ecp_keypair_init(&pair);mbedtls_mpi_init(&r);mbedtls_mpi_init(&s);
    bool ok=mbedtls_ecp_read_key(MBEDTLS_ECP_DP_SECP256R1,&pair,persistent.privateKey,32)==0&&
        mbedtls_ecdsa_sign(&pair.MBEDTLS_PRIVATE(grp),&r,&s,&pair.MBEDTLS_PRIVATE(d),hash,32,randomBytes,nullptr)==0&&
        mbedtls_mpi_write_binary(&r,signature,32)==0&&mbedtls_mpi_write_binary(&s,signature+32,32)==0;
    mbedtls_mpi_free(&r);mbedtls_mpi_free(&s);mbedtls_ecp_keypair_free(&pair);return ok;
}
bool tqtOfflineInit() {
    available=false;cachedInfoValid=false;
    mutex=xSemaphoreCreateMutex();if(!mutex) return false;
    uint8_t nonzero=0;for(uint8_t b:tqtProfile.otaKey) nonzero|=b;
    if(!nonzero||tqtProfile.schema!=2||tqtProfile.capabilities!=1) return false;
    if(strlen(ENROLL_KEY_ID)!=16||ENROLL_PUBLIC_KEY[0]!=4) return false;
    for(unsigned i=0;i<8;++i) {
        unsigned value=0;
        for(unsigned j=0;j<2;++j) {
            char c=ENROLL_KEY_ID[i*2+j];if(c<'0'||(c>'9'&&c<'a')||c>'f') return false;
            value=(value<<4)|unsigned(c<='9'?c-'0':c-'a'+10);
        }
        anchorId[i]=uint8_t(value);
    }
    if(nvs_open("tqt_offline",NVS_READWRITE,&store)!=ESP_OK) return false;
    size_t size=sizeof(persistent);esp_err_t result=nvs_get_blob(store,"state_v1",&persistent,&size);
    if(result==ESP_ERR_NVS_NOT_FOUND) {
        memcpy(persistent.magic,NVS_MAGIC,8);
        mbedtls_ecp_keypair pair;mbedtls_ecp_keypair_init(&pair);
        bool generated=mbedtls_ecp_gen_key(MBEDTLS_ECP_DP_SECP256R1,&pair,randomBytes,nullptr)==0&&
            mbedtls_mpi_write_binary(&pair.MBEDTLS_PRIVATE(d),persistent.privateKey,32)==0;
        mbedtls_ecp_keypair_free(&pair);
        if(!generated||!persist(persistent)) return false;
    } else if(result!=ESP_OK||size!=sizeof(persistent)||!valid(persistent)) return false;
    if(!publicFromPrivate(persistent.privateKey,publicKey)) return false;
    // Check signing and the copied public trust anchor before confirming a new boot.
    uint8_t signature[64];
    mbedtls_ecp_group group;mbedtls_ecp_point q;mbedtls_ecp_group_init(&group);mbedtls_ecp_point_init(&q);
    bool anchorOk=mbedtls_ecp_group_load(&group,MBEDTLS_ECP_DP_SECP256R1)==0&&
        mbedtls_ecp_point_read_binary(&group,&q,ENROLL_PUBLIC_KEY,65)==0&&mbedtls_ecp_check_pubkey(&group,&q)==0;
    mbedtls_ecp_point_free(&q);mbedtls_ecp_group_free(&group);
    uint8_t hmacTest[32];
    available=anchorOk&&unitHmac(reinterpret_cast<const uint8_t *>(OFFLINE_MARKER),sizeof(OFFLINE_MARKER)-1,hmacTest)&&
        sign(reinterpret_cast<const uint8_t *>(OFFLINE_MARKER),sizeof(OFFLINE_MARKER)-1,signature)&&
        verify(publicKey,reinterpret_cast<const uint8_t *>(OFFLINE_MARKER),sizeof(OFFLINE_MARKER)-1,signature);
    return available;
}
bool tqtOfflineAvailable() {
    if(!mutex) return false;
    xSemaphoreTake(mutex,portMAX_DELAY);bool result=available;xSemaphoreGive(mutex);return result;
}
bool tqtOfflineInfoFrame(const uint8_t nonce[16],const uint8_t appDigest[32],
    const uint8_t legacyProof[32],uint32_t partition,bool bootValid,const uint8_t mac[6],uint8_t frame[INFO_BYTES]) {
    memset(frame,0,INFO_BYTES);if(!mutex) return false;
    xSemaphoreTake(mutex,portMAX_DELAY);
    if(!available) {xSemaphoreGive(mutex);return false;}
    uint8_t identity[sizeof(IDENTITY_LABEL)-1+32+65+4+8],proof[32];size_t p=0;
    memcpy(identity+p,IDENTITY_LABEL,sizeof(IDENTITY_LABEL)-1);p+=sizeof(IDENTITY_LABEL)-1;
    memcpy(identity+p,legacyProof,32);p+=32;memcpy(identity+p,publicKey,65);p+=65;
    memcpy(identity+p,persistent.counter,4);p+=4;memcpy(identity+p,anchorId,8);
    uint8_t info[sizeof(INFO_LABEL)-1+16+32+4+4+1+24+8+16+6+16],signature[64];p=0;
    memcpy(info+p,INFO_LABEL,sizeof(INFO_LABEL)-1);p+=sizeof(INFO_LABEL)-1;
    memcpy(info+p,nonce,16);p+=16;memcpy(info+p,appDigest,32);p+=32;
    memcpy(info+p,persistent.counter,4);p+=4;write32(info+p,partition);p+=4;info[p++]=bootValid?1:0;
    memcpy(info+p,tqtProfile.nombre,24);p+=24;memcpy(info+p,tqtProfile.hw,8);p+=8;
    memcpy(info+p,tqtProfile.fw,16);p+=16;memcpy(info+p,mac,6);p+=6;memcpy(info+p,persistent.lastGrant,16);
    uint8_t infoHash[32];
    if(!sha(info,sizeof(info),infoHash)) {available=false;xSemaphoreGive(mutex);return false;}
    if(cachedInfoValid&&equal(cachedInfoHash,infoHash,32)) {
        memcpy(frame,cachedInfo,INFO_BYTES);xSemaphoreGive(mutex);return true;
    }
    if(!unitHmac(identity,sizeof(identity),proof)||!sign(info,sizeof(info),signature)) {
        available=false;xSemaphoreGive(mutex);return false;
    }
    frame[0]=1;memcpy(frame+1,publicKey,65);memcpy(frame+66,persistent.counter,4);
    memcpy(frame+70,anchorId,8);memcpy(frame+78,proof,32);memcpy(frame+110,signature,64);
    memcpy(frame+174,persistent.lastGrant,16);
    memcpy(cachedInfoHash,infoHash,32);memcpy(cachedInfo,frame,INFO_BYTES);cachedInfoValid=true;
    xSemaphoreGive(mutex);return true;
}
bool tqtOfflineAuthorize(const uint8_t m[SESSION_BYTES],const uint8_t nonce[16],
    const uint8_t appDigest[32],const uint8_t mac[6],uint32_t slotSize,uint8_t imageKey[32]) {
    memset(imageKey,0,32);if(!mutex) return false;
    xSemaphoreTake(mutex,portMAX_DELAY);
    bool ok=available&&read32(persistent.counter)!=UINT32_MAX&&equal(m,reinterpret_cast<const uint8_t *>(MAGIC),16)&&
        equal(m+DEVICE_KEY,publicKey,65)&&equal(m+COUNTER,persistent.counter,4)&&
        equal(m+SOURCE_DIGEST,appDigest,32)&&equal(m+MAC,mac,6)&&equal(m+ANCHOR,anchorId,8)&&
        equal(m+HARDWARE,reinterpret_cast<const uint8_t *>(tqtProfile.hw),8)&&
        canonicalAscii(m+NAME,24)&&canonicalAscii(m+HARDWARE,8)&&supportedVersion(m+FIRMWARE)&&
        read32(m+IMAGE_BYTES)>=65536&&read32(m+IMAGE_BYTES)<=slotSize;
    uint8_t uuidNonzero=0;for(unsigned i=0;i<16;++i) uuidNonzero|=m[UUID+i];ok=ok&&uuidNonzero;
    for(unsigned i=0;i<24&&ok;++i) {
        uint8_t a=m[NAME+i]=='_'?'-':m[NAME+i],b=tqtProfile.nombre[i]=='_'?'-':tqtProfile.nombre[i];
        if(a!=b) ok=false;
    }
    if(ok) ok=verify(ENROLL_PUBLIC_KEY,m,BODY_BYTES,m+SERVER_SIG);
    uint8_t session[sizeof(SESSION_LABEL)-1+16+16+32];size_t p=0;
    memcpy(session+p,SESSION_LABEL,sizeof(SESSION_LABEL)-1);p+=sizeof(SESSION_LABEL)-1;
    memcpy(session+p,m+UUID,16);p+=16;memcpy(session+p,nonce,16);p+=16;
    if(ok) ok=sha(m,GRANT_BYTES,session+p)&&verify(m+PHONE_KEY,session,sizeof(session),m+PHONE_SIG);
    uint8_t keyData[sizeof(IMAGE_KEY_LABEL)-1+16];
    memcpy(keyData,IMAGE_KEY_LABEL,sizeof(IMAGE_KEY_LABEL)-1);memcpy(keyData+sizeof(IMAGE_KEY_LABEL)-1,m+UUID,16);
    if(ok) ok=unitHmac(keyData,sizeof(keyData),imageKey);
    xSemaphoreGive(mutex);return ok;
}
bool tqtOfflineConsume(const uint8_t *grantUuid) {
    if(!mutex) return false;
    xSemaphoreTake(mutex,portMAX_DELAY);
    uint32_t value=read32(persistent.counter);bool ok=available&&value!=UINT32_MAX;
    if(ok) {
        Persistent next=persistent;write32(next.counter,value+1);
        if(grantUuid) memcpy(next.lastGrant,grantUuid,16);else memset(next.lastGrant,0,16);
        ok=persist(next);if(ok) persistent=next;
        // Never retry from stale RAM if NVS may already have consumed the grant.
        if(!ok) available=false;
        mbedtls_platform_zeroize(&next,sizeof(next));
    }
    xSemaphoreGive(mutex);return ok;
}
