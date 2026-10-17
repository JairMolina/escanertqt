#include "tqt_offline.h"
#include "tqt_profile.h"
#include "enrollment_trust.h"
#include "nvs.h"
#include <mbedtls/ecp.h>
#include <mbedtls/ecdsa.h>
#include <mbedtls/sha256.h>
#include <mbedtls/md.h>
#include <sys/random.h>
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <vector>
#include <array>
#include <stdexcept>

using namespace TqtOfflineWire;
const TqtProfile tqtProfile={"TQT_R2_CFG_V1",2,"3.0","4.3","TQT-R2-V30-0067","ESP32-WROOM-32E-N4",1,
    {1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,32}};
static std::vector<uint8_t> durable,staged;
static bool openFail=false,writeFail=false,commitFail=false;
void esp_fill_random(void *out,size_t size) {
    auto *p=static_cast<uint8_t *>(out);
    while(size) {ssize_t n=getrandom(p,size,0);if(n<=0) throw std::runtime_error("RNG");p+=n;size-=n;}
}
int nvs_open(const char *,int,nvs_handle_t *handle) {*handle=1;return openFail?ESP_FAIL:ESP_OK;}
int nvs_get_blob(nvs_handle_t,const char *,void *out,size_t *size) {
    if(durable.empty()) return ESP_ERR_NVS_NOT_FOUND;
    if(*size<durable.size()) return ESP_FAIL;
    memcpy(out,durable.data(),durable.size());*size=durable.size();return ESP_OK;
}
int nvs_set_blob(nvs_handle_t,const char *,const void *in,size_t size) {
    if(writeFail) return ESP_FAIL;
    auto *p=static_cast<const uint8_t *>(in);staged.assign(p,p+size);return ESP_OK;
}
int nvs_commit(nvs_handle_t) {if(commitFail) return ESP_FAIL;durable=staged;return ESP_OK;}
static int rng(void *,unsigned char *p,size_t n) {esp_fill_random(p,n);return 0;}
static void digest(const uint8_t *data,size_t size,uint8_t out[32]) {assert(mbedtls_sha256_ret(data,size,out,0)==0);}
static void signBytes(unsigned scalar,const uint8_t *data,size_t size,uint8_t out[64]) {
    uint8_t key[32]={0},hash[32];key[31]=uint8_t(scalar);digest(data,size,hash);
    mbedtls_ecp_keypair pair;mbedtls_ecp_keypair_init(&pair);mbedtls_mpi r,s;mbedtls_mpi_init(&r);mbedtls_mpi_init(&s);
    assert(mbedtls_ecp_read_key(MBEDTLS_ECP_DP_SECP256R1,&pair,key,32)==0);
    assert(mbedtls_ecdsa_sign(&pair.grp,&r,&s,&pair.d,hash,32,rng,nullptr)==0);
    assert(mbedtls_mpi_write_binary(&r,out,32)==0&&mbedtls_mpi_write_binary(&s,out+32,32)==0);
    mbedtls_ecp_keypair_free(&pair);mbedtls_mpi_free(&r);mbedtls_mpi_free(&s);
}
static void pub(unsigned scalar,uint8_t out[65]) {
    uint8_t key[32]={0};key[31]=uint8_t(scalar);size_t size=0;
    mbedtls_ecp_keypair pair;mbedtls_ecp_keypair_init(&pair);
    assert(mbedtls_ecp_read_key(MBEDTLS_ECP_DP_SECP256R1,&pair,key,32)==0);
    assert(mbedtls_ecp_mul(&pair.grp,&pair.Q,&pair.d,&pair.grp.G,rng,nullptr)==0);
    assert(mbedtls_ecp_point_write_binary(&pair.grp,&pair.Q,MBEDTLS_ECP_PF_UNCOMPRESSED,&size,out,65)==0&&size==65);
    mbedtls_ecp_keypair_free(&pair);
}
static void verifyBytes(const uint8_t key[65],const uint8_t *data,size_t size,const uint8_t signature[64]) {
    uint8_t hash[32];digest(data,size,hash);
    mbedtls_ecp_group group;mbedtls_ecp_point q;mbedtls_mpi r,s;
    mbedtls_ecp_group_init(&group);mbedtls_ecp_point_init(&q);mbedtls_mpi_init(&r);mbedtls_mpi_init(&s);
    assert(mbedtls_ecp_group_load(&group,MBEDTLS_ECP_DP_SECP256R1)==0);
    assert(mbedtls_ecp_point_read_binary(&group,&q,key,65)==0);
    assert(mbedtls_mpi_read_binary(&r,signature,32)==0&&mbedtls_mpi_read_binary(&s,signature+32,32)==0);
    assert(mbedtls_ecdsa_verify(&group,hash,32,&q,&r,&s)==0);
    mbedtls_ecp_group_free(&group);mbedtls_ecp_point_free(&q);mbedtls_mpi_free(&r);mbedtls_mpi_free(&s);
}
static uint8_t nonce[16]={1},app[32]={2},legacy[32]={3},mac[6]={4,5,6,7,8,9};
using Manifest=std::array<uint8_t,SESSION_BYTES>;
static void signatures(Manifest &m,unsigned root=1,unsigned phone=2) {
    signBytes(root,m.data(),BODY_BYTES,m.data()+SERVER_SIG);
    uint8_t session[sizeof(SESSION_LABEL)-1+16+16+32];size_t p=0;
    memcpy(session,SESSION_LABEL,sizeof(SESSION_LABEL)-1);p+=sizeof(SESSION_LABEL)-1;
    memcpy(session+p,m.data()+UUID,16);p+=16;memcpy(session+p,nonce,16);p+=16;digest(m.data(),GRANT_BYTES,session+p);
    signBytes(phone,session,sizeof(session),m.data()+PHONE_SIG);
}
static Manifest grant(const uint8_t info[INFO_BYTES]) {
    Manifest m={};memcpy(m.data(),MAGIC,16);m[UUID]=9;memcpy(m.data()+DEVICE_KEY,info+1,65);
    pub(2,m.data()+PHONE_KEY);m[IV]=7;memcpy(m.data()+COUNTER,info+66,4);memcpy(m.data()+SOURCE_DIGEST,app,32);
    m[TRANSFER_DIGEST]=5;m[TARGET_DIGEST]=6;write32(m.data()+IMAGE_BYTES,65536);
    memcpy(m.data()+NAME,tqtProfile.nombre,24);memcpy(m.data()+HARDWARE,tqtProfile.hw,8);
    memcpy(m.data()+FIRMWARE,tqtProfile.fw,16);memcpy(m.data()+MAC,mac,6);memcpy(m.data()+ANCHOR,info+70,8);
    signatures(m);return m;
}
static bool authorize(const Manifest &m,uint8_t key[32]) {return tqtOfflineAuthorize(m.data(),nonce,app,mac,1310720,key);}
static void wireTests() {
    for(const char *s:{"4.3","4.3.0","4.3.0.1","4.10","5.0","99999999999.3"}) {
        uint8_t f[16]={0};memcpy(f,s,strlen(s));assert(supportedVersion(f));
    }
    for(const char *s:{"4.2","04.3","4.03","4","4.3.","4..3","4.3.0.0.1","4.3x"}) {
        uint8_t f[16]={0};memcpy(f,s,strlen(s));assert(!supportedVersion(f));
    }
    uint8_t f[16];memset(f,'9',16);assert(!supportedVersion(f));
    memset(f,0,16);memcpy(f,"4.3",3);f[10]='x';assert(!supportedVersion(f));
    uint8_t word[4];write32(word,0xfedcba98);assert(read32(word)==0xfedcba98&&word[0]==0x98);
}
int main() {
    wireTests();assert(tqtOfflineInit()&&tqtOfflineAvailable());assert(durable.size()==92);
    uint8_t info[INFO_BYTES],again[INFO_BYTES];
    assert(tqtOfflineInfoFrame(nonce,app,legacy,65536,true,mac,info));
    assert(info[0]==1&&info[1]==4&&read32(info+66)==0);
    assert(tqtOfflineInfoFrame(nonce,app,legacy,65536,true,mac,again)&&memcmp(info,again,INFO_BYTES)==0);
    uint8_t transcript[sizeof(INFO_LABEL)-1+16+32+4+4+1+24+8+16+6+16];size_t p=0;
    memcpy(transcript+p,INFO_LABEL,sizeof(INFO_LABEL)-1);p+=sizeof(INFO_LABEL)-1;
    memcpy(transcript+p,nonce,16);p+=16;memcpy(transcript+p,app,32);p+=32;memcpy(transcript+p,info+66,4);p+=4;
    write32(transcript+p,65536);p+=4;transcript[p++]=1;memcpy(transcript+p,tqtProfile.nombre,24);p+=24;
    memcpy(transcript+p,tqtProfile.hw,8);p+=8;memcpy(transcript+p,tqtProfile.fw,16);p+=16;
    memcpy(transcript+p,mac,6);p+=6;memcpy(transcript+p,info+174,16);verifyBytes(info+1,transcript,sizeof(transcript),info+110);
    uint8_t identity[sizeof(IDENTITY_LABEL)-1+32+65+4+8],proof[32];p=0;
    memcpy(identity+p,IDENTITY_LABEL,sizeof(IDENTITY_LABEL)-1);p+=sizeof(IDENTITY_LABEL)-1;
    memcpy(identity+p,legacy,32);p+=32;memcpy(identity+p,info+1,65);p+=65;
    memcpy(identity+p,info+66,4);p+=4;memcpy(identity+p,info+70,8);
    assert(mbedtls_md_hmac(mbedtls_md_info_from_type(MBEDTLS_MD_SHA256),tqtProfile.otaKey,32,identity,sizeof(identity),proof)==0);
    assert(memcmp(proof,info+78,32)==0);
    Manifest good=grant(info);uint8_t key[32],expected[32],keyData[sizeof(IMAGE_KEY_LABEL)-1+16];
    assert(authorize(good,key));memcpy(keyData,IMAGE_KEY_LABEL,sizeof(IMAGE_KEY_LABEL)-1);
    memcpy(keyData+sizeof(IMAGE_KEY_LABEL)-1,good.data()+UUID,16);
    assert(mbedtls_md_hmac(mbedtls_md_info_from_type(MBEDTLS_MD_SHA256),tqtProfile.otaKey,32,keyData,sizeof(keyData),expected)==0);
    assert(memcmp(key,expected,32)==0);
    // Even a valid server/phone signature cannot override device/source/scope.
    for(size_t at:{size_t(0),UUID,DEVICE_KEY,COUNTER,SOURCE_DIGEST,NAME,HARDWARE,MAC,ANCHOR}) {
        auto bad=good;bad[at]^=1;if(at==UUID) memset(bad.data()+UUID,0,16);signatures(bad);assert(!authorize(bad,key));
    }
    for(const char *fw:{"4.2","04.3","4.3.","4.3.0.0.1"}) {
        auto bad=good;memset(bad.data()+FIRMWARE,0,16);memcpy(bad.data()+FIRMWARE,fw,strlen(fw));signatures(bad);assert(!authorize(bad,key));
    }
    for(uint32_t size:{65535U,1310721U}) {auto bad=good;write32(bad.data()+IMAGE_BYTES,size);signatures(bad);assert(!authorize(bad,key));}
    {auto bad=good;bad[SERVER_SIG]^=1;assert(!authorize(bad,key));}
    {auto bad=good;bad[PHONE_SIG]^=1;assert(!authorize(bad,key));}
    {auto bad=good;signatures(bad,3);assert(!authorize(bad,key));}
    {auto bad=good;pub(3,bad.data()+PHONE_KEY);signatures(bad);assert(!authorize(bad,key));}
    nonce[0]^=1;assert(!authorize(good,key));nonce[0]^=1;
    // Reboot before COMMIT preserves key/counter and the same grant works.
    assert(tqtOfflineInit()&&authorize(good,key));
    assert(tqtOfflineConsume(good.data()+UUID));assert(!authorize(good,key));
    assert(tqtOfflineInit());assert(tqtOfflineInfoFrame(nonce,app,legacy,65536,true,mac,again));
    assert(read32(again+66)==1&&memcmp(again+174,good.data()+UUID,16)==0&&memcmp(again+1,info+1,65)==0);
    // A lost activation has already consumed the authorization, with old digest.
    assert(memcmp(app,transcript+sizeof(INFO_LABEL)-1+16,32)==0);
    assert(tqtOfflineConsume(nullptr));assert(tqtOfflineInit());
    assert(tqtOfflineInfoFrame(nonce,app,legacy,65536,true,mac,again)&&read32(again+66)==2);
    uint8_t zero[16]={0};assert(memcmp(again+174,zero,16)==0);
    auto saved=durable;writeFail=true;assert(!tqtOfflineConsume(nullptr)&&!tqtOfflineAvailable());
    assert(durable==saved);writeFail=false;assert(tqtOfflineInit());
    commitFail=true;assert(!tqtOfflineConsume(nullptr)&&!tqtOfflineAvailable());commitFail=false;assert(tqtOfflineInit());
    durable[8]^=1;assert(!tqtOfflineInit()&&!tqtOfflineAvailable());durable=saved;assert(tqtOfflineInit());
    openFail=true;assert(!tqtOfflineInit()&&!tqtOfflineAvailable());openFail=false;assert(tqtOfflineInit());
    write32(durable.data()+40,UINT32_MAX);digest(durable.data(),60,durable.data()+60);
    assert(tqtOfflineInit()&&!tqtOfflineConsume(nullptr));
    puts("FW4.3 native: wire, real P256/HMAC, grant scope, fresh nonce, durable receipt, online consumption, NVS failure/corruption and exhaustion PASS");
}
