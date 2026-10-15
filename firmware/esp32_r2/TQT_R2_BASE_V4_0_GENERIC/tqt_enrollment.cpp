#include "tqt_enrollment.h"
#include "tqt_profile.h"
#include "enrollment_trust.h"
#include <Preferences.h>
#include <BLEDevice.h>
#include <esp_system.h>
#include <mbedtls/ecp.h>
#include <mbedtls/ecdsa.h>
#include <mbedtls/gcm.h>
#include <mbedtls/sha256.h>

static const uint8_t LABEL[]="TQT-ENROLL-v1";
static mbedtls_ecp_group group;
static mbedtls_mpi privateKey;
static mbedtls_ecp_point publicKey;
static uint8_t publicBytes[65];
static bool initialized=false,ready=false;
static int rng(void *,unsigned char *out,size_t size){esp_fill_random(out,size);return 0;}
bool tqtIsGeneric(){return tqtProfile.schema==3 && tqtProfile.capabilities==3;}
static bool validAssigned(const TqtProfile &p){
    if(memcmp(p.magic,tqtProfile.magic,16)||p.schema!=2||p.capabilities!=1||memcmp(p.hw,tqtProfile.hw,8)||
       memcmp(p.fw,tqtProfile.fw,16)||memcmp(p.module,tqtProfile.module,24)||strnlen(p.nombre,24)>=24) return false;
    uint8_t key=0;for(uint8_t b:p.otaKey)key|=b;if(!key)return false;
    String hw=tqtProfile.hw;hw.replace(".","");String prefix=String("TQT-R2-V")+hw+"-";
    if(strncmp(p.nombre,prefix.c_str(),prefix.length())||strlen(p.nombre)!=prefix.length()+4)return false;
    for(size_t i=prefix.length();i<strlen(p.nombre);++i)if(p.nombre[i]<'0'||p.nombre[i]>'9')return false;
    return strcmp(p.nombre+prefix.length(),"0000")!=0;
}
void tqtLoadEnrollment(){
    if(!tqtIsGeneric())return;
    Preferences store;if(!store.begin("tqt-enroll",true))return;
    TqtProfile saved={};size_t n=store.getBytes("profile",&saved,sizeof(saved));store.end();
    if(n==sizeof(saved)&&validAssigned(saved))tqtProfile=saved;
    memset(&saved,0,sizeof(saved));
}
void tqtEnrollmentReset(){
    if(!initialized){mbedtls_ecp_group_init(&group);mbedtls_mpi_init(&privateKey);mbedtls_ecp_point_init(&publicKey);initialized=true;}
    ready=false;if(!tqtIsGeneric())return;
    size_t n=0;
    ready=mbedtls_ecp_group_load(&group,MBEDTLS_ECP_DP_SECP256R1)==0 &&
      mbedtls_ecp_gen_keypair(&group,&privateKey,&publicKey,rng,nullptr)==0 &&
      mbedtls_ecp_point_write_binary(&group,&publicKey,MBEDTLS_ECP_PF_UNCOMPRESSED,&n,publicBytes,sizeof(publicBytes))==0 && n==65;
}
String tqtEnrollmentInfo(){
    if(!tqtIsGeneric())return "";
    String pub;pub.reserve(130);const char *hex="0123456789abcdef";
    for(uint8_t b:publicBytes){pub+=hex[b>>4];pub+=hex[b&15];}
    return String(",\"enrollment\":1,\"enroll_key_id\":\"")+ENROLL_KEY_ID+"\",\"device_pub\":\""+pub+"\"";
}
bool tqtAcceptEnrollment(const uint8_t *ticket,size_t size,const uint8_t *nonce){
    if(!ready||!tqtIsGeneric()||size!=286||ticket[0]!=1)return false;
    uint8_t mac[6];memcpy(mac,BLEDevice::getAddress().getNative(),6);
    uint8_t message[13+65+16+6+222],digest[32];size_t at=0;
    memcpy(message+at,LABEL,13);at+=13;memcpy(message+at,publicBytes,65);at+=65;
    memcpy(message+at,nonce,16);at+=16;memcpy(message+at,mac,6);at+=6;memcpy(message+at,ticket,222);
    if(mbedtls_sha256(message,sizeof(message),digest,0)!=0)return false;
    mbedtls_ecp_point signer,peer,shared;mbedtls_ecp_point_init(&signer);mbedtls_ecp_point_init(&peer);mbedtls_ecp_point_init(&shared);
    mbedtls_mpi r,s;mbedtls_mpi_init(&r);mbedtls_mpi_init(&s);
    mbedtls_gcm_context gcm;mbedtls_gcm_init(&gcm);
    uint8_t derived[13+32+16+6]={0},key[32]={0},aad[13+16+6];TqtProfile assigned={};
    bool ok=mbedtls_ecp_point_read_binary(&group,&signer,ENROLL_PUBLIC_KEY,65)==0 &&
      mbedtls_mpi_read_binary(&r,ticket+222,32)==0 && mbedtls_mpi_read_binary(&s,ticket+254,32)==0 &&
      mbedtls_ecdsa_verify(&group,digest,32,&signer,&r,&s)==0 &&
      mbedtls_ecp_point_read_binary(&group,&peer,ticket+1,65)==0 && mbedtls_ecp_check_pubkey(&group,&peer)==0 &&
      mbedtls_ecp_mul(&group,&shared,&privateKey,&peer,rng,nullptr)==0;
    if(ok){
      memcpy(derived,LABEL,13);ok=mbedtls_mpi_write_binary(&shared.MBEDTLS_PRIVATE(X),derived+13,32)==0;
      memcpy(derived+45,nonce,16);memcpy(derived+61,mac,6);
      memcpy(aad,LABEL,13);memcpy(aad+13,nonce,16);memcpy(aad+29,mac,6);
      ok=ok && mbedtls_sha256(derived,sizeof(derived),key,0)==0 && mbedtls_gcm_setkey(&gcm,MBEDTLS_CIPHER_ID_AES,key,256)==0 &&
         mbedtls_gcm_auth_decrypt(&gcm,128,ticket+66,12,aad,sizeof(aad),ticket+206,16,ticket+78,reinterpret_cast<uint8_t *>(&assigned))==0 && validAssigned(assigned);
    }
    if(ok){Preferences store;ok=store.begin("tqt-enroll",false);if(ok){ok=store.putBytes("profile",&assigned,sizeof(assigned))==sizeof(assigned);store.end();}}
    if(ok){tqtProfile=assigned;ready=false;mbedtls_mpi_free(&privateKey);mbedtls_mpi_init(&privateKey);}
    memset(derived,0,sizeof(derived));memset(key,0,sizeof(key));memset(&assigned,0,sizeof(assigned));
    mbedtls_gcm_free(&gcm);mbedtls_mpi_free(&r);mbedtls_mpi_free(&s);
    mbedtls_ecp_point_free(&signer);mbedtls_ecp_point_free(&peer);mbedtls_ecp_point_free(&shared);
    return ok;
}
