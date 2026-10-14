#include "tqt_ota.h"
#include "tqt_profile.h"
#include <Arduino.h>
#include <BLEDevice.h>
#include <esp_ota_ops.h>
#include <esp_partition.h>
#include <esp_system.h>
#include <esp_bt.h>
#include <mbedtls/md.h>
#include <mbedtls/aes.h>
#include <mbedtls/sha256.h>
#include <freertos/queue.h>

// Independent service: original PPON/POFF service and UUIDs stay unchanged.
static const char *OTA_SERVICE_UUID="d45a0001-6a76-4e41-9f38-a7043f0ec069";
static const char *OTA_INFO_UUID="d45a0002-6a76-4e41-9f38-a7043f0ec069";
static const char *OTA_CONTROL_UUID="d45a0003-6a76-4e41-9f38-a7043f0ec069";
static const char *OTA_DATA_UUID="d45a0004-6a76-4e41-9f38-a7043f0ec069";
static const char *OTA_STATUS_UUID="d45a0005-6a76-4e41-9f38-a7043f0ec069";
enum State : uint8_t { IDLE, MANIFEST, RECEIVING, READY, RESTARTING, ERROR_STATE };
static const char *STATE_NAMES[]={"idle","manifest","receiving","ready","restarting","error"};
struct Packet { uint16_t length; uint8_t data[184]; };
static BLEServer *serverRef=nullptr;
static QueueHandle_t packets=nullptr;
static portMUX_TYPE guard=portMUX_INITIALIZER_UNLOCKED;
static volatile State state=IDLE;
static volatile bool disconnected=false, overflow=false;
static volatile uint8_t control=0;
static uint32_t offset=0, total=0, lastPacket=0, restartAt=0, bootAt=0;
static char errorCode[40]={0};
static uint8_t nonce[16]={0}, appHash[32]={0}, manifest[138]={0};
static size_t manifestBytes=0, counterOffset=0;
static uint8_t counter[16]={0}, streamBlock[16]={0};
static bool bootValid=false, bootHealthy=false, hashReady=false, nonceAvailable=true, otaOpen=false;
static const esp_partition_t *target=nullptr;
static esp_ota_handle_t handle=0;
static mbedtls_aes_context aes;
static mbedtls_sha256_context digest;

// Arduino 3.3.12 otherwise confirms the OTA image before setup(). Defer to diagnostics.
extern "C" bool verifyRollbackLater() { return true; }

static bool hasKey() {
    uint8_t result=0; for (uint8_t b:tqtProfile.otaKey) result|=b;
    return tqtProfile.schema==2 && tqtProfile.capabilities==1 && result!=0;
}
static String hex(const uint8_t *bytes,size_t count) {
    static const char *digits="0123456789abcdef";
    String value; value.reserve(count*2);
    for (size_t i=0;i<count;++i) { value+=digits[bytes[i]>>4];value+=digits[bytes[i]&15]; }
    return value;
}
static bool constantEqual(const uint8_t *a,const uint8_t *b,size_t n) {
    uint8_t diff=0;for(size_t i=0;i<n;++i) diff|=a[i]^b[i];return diff==0;
}
static uint32_t u32(const uint8_t *p) { return uint32_t(p[0])|(uint32_t(p[1])<<8)|(uint32_t(p[2])<<16)|(uint32_t(p[3])<<24); }
static bool hmac(const uint8_t *data,size_t size,uint8_t *out) {
    return mbedtls_md_hmac(mbedtls_md_info_from_type(MBEDTLS_MD_SHA256),tqtProfile.otaKey,32,data,size,out)==0;
}
String tqtOtaKeyId() {
    uint8_t hash[32];if(!hasKey()) return "";
    if(mbedtls_sha256(tqtProfile.otaKey,32,hash,0)!=0) return "";
    return hex(hash,8);
}
static void freshNonce() {
    uint8_t value[16];esp_fill_random(value,sizeof(value));
    portENTER_CRITICAL(&guard);memcpy(nonce,value,16);nonceAvailable=true;portEXIT_CRITICAL(&guard);
}
static void setState(State next,const char *error="") {
    portENTER_CRITICAL(&guard);state=next;snprintf(errorCode,sizeof(errorCode),"%s",error);portEXIT_CRITICAL(&guard);
}
static void setOffset(uint32_t value) {
    portENTER_CRITICAL(&guard);offset=value;portEXIT_CRITICAL(&guard);
}
static void abortUpdate(const char *error) {
    if(otaOpen) { esp_ota_abort(handle);otaOpen=false; }
    if(packets) xQueueReset(packets);
    mbedtls_aes_free(&aes);mbedtls_aes_init(&aes);
    mbedtls_sha256_free(&digest);mbedtls_sha256_init(&digest);
    manifestBytes=0;counterOffset=0;setOffset(0);total=0;freshNonce();
    setState(error&&*error?ERROR_STATE:IDLE,error?error:"");
}
bool tqtOtaBusy() { return state==MANIFEST||state==RECEIVING||state==READY||state==RESTARTING; }
void tqtOtaConnected() { freshNonce(); }
void tqtOtaDisconnected() { disconnected=true; }
void tqtOtaBootReady(bool healthy) { bootHealthy=healthy && hashReady; }

static String infoJson() {
    uint8_t n[16];portENTER_CRITICAL(&guard);memcpy(n,nonce,16);portEXIT_CRITICAL(&guard);
    uint16_t mtu=serverRef?serverRef->getPeerMTU(serverRef->getConnId()):23;
    uint16_t chunk=mtu>7?min(uint16_t(180),uint16_t(mtu-7)):16;
    // Signature binds fresh nonce, current app image, identity and actual boot confirmation.
    uint8_t proofData[15+16+32+24+8+16+6+1+4]={0};
    size_t p=0;memcpy(proofData+p,"TQT-OTA-INFO-v1",15);p+=15;
    memcpy(proofData+p,n,16);p+=16;memcpy(proofData+p,appHash,32);p+=32;
    memcpy(proofData+p,tqtProfile.nombre,24);p+=24;memcpy(proofData+p,tqtProfile.hw,8);p+=8;
    memcpy(proofData+p,tqtProfile.fw,16);p+=16;
    memcpy(proofData+p,BLEDevice::getAddress().getNative(),6);p+=6;proofData[p++]=bootValid?1:0;
    uint32_t partition=esp_ota_get_running_partition()->address;
    for(unsigned i=0;i<4;++i) proofData[p+i]=uint8_t(partition>>(8*i));
    uint8_t signature[32]={0};if(hasKey()) hmac(proofData,sizeof(proofData),signature);
    return String("{\"nombre\":\"")+tqtProfile.nombre+"\",\"hw\":\""+tqtProfile.hw+"\",\"fw\":\""+tqtProfile.fw+
        "\",\"mac\":\""+BLEDevice::getAddress().toString()+"\",\"ota_protocol\":"+(hasKey()?"1":"0")+
        ",\"key_id\":\""+tqtOtaKeyId()+"\",\"nonce\":\""+hex(n,16)+"\",\"app_sha256\":\""+hex(appHash,32)+
        "\",\"proof\":\""+hex(signature,32)+"\",\"boot_valid\":"+(bootValid?"true":"false")+",\"partition\":"+String(partition)+",\"chunk\":"+String(chunk)+"}";
}
class InfoCallbacks:public BLECharacteristicCallbacks {
    void onRead(BLECharacteristic *c) override { c->setValue(infoJson()); }
};
class StatusCallbacks:public BLECharacteristicCallbacks {
    void onRead(BLECharacteristic *c) override {
        State s;uint32_t o,t;char e[40];
        portENTER_CRITICAL(&guard);s=state;o=offset;t=total;memcpy(e,errorCode,40);portEXIT_CRITICAL(&guard);
        c->setValue(String("{\"state\":\"")+STATE_NAMES[s]+"\",\"offset\":"+String(o)+",\"total\":"+String(t)+",\"error\":\""+e+"\"}");
    }
};
class ControlCallbacks:public BLECharacteristicCallbacks {
    void onWrite(BLECharacteristic *c) override {
        String data=c->getValue();if(data.length()!=1) return;
        uint8_t op=uint8_t(data[0]);if(op>=1&&op<=3) control=op;
    }
};
class DataCallbacks:public BLECharacteristicCallbacks {
    void onWrite(BLECharacteristic *c) override {
        String data=c->getValue();
        if((state!=MANIFEST&&state!=RECEIVING)||data.length()<5||data.length()>184) { overflow=true;return; }
        Packet packet;packet.length=data.length();memcpy(packet.data,data.c_str(),packet.length);
        if(!packets||xQueueSend(packets,&packet,0)!=pdTRUE) overflow=true;
    }
};
void tqtOtaInit(BLEServer *server) {
    serverRef=server;packets=xQueueCreate(8,sizeof(Packet));bootAt=millis();freshNonce();
    mbedtls_aes_init(&aes);mbedtls_sha256_init(&digest);
    const esp_partition_t *running=esp_ota_get_running_partition();
    esp_ota_img_states_t imageState;
    bootValid=esp_ota_get_state_partition(running,&imageState)!=ESP_OK||imageState!=ESP_OTA_IMG_PENDING_VERIFY;
    hashReady=esp_partition_get_sha256(running,appHash)==ESP_OK;
    if(!hashReady) { memset(appHash,0,32);bootHealthy=false; }
    BLEService *service=server->createService(OTA_SERVICE_UUID);
    service->createCharacteristic(OTA_INFO_UUID,BLECharacteristic::PROPERTY_READ)->setCallbacks(new InfoCallbacks());
    service->createCharacteristic(OTA_STATUS_UUID,BLECharacteristic::PROPERTY_READ)->setCallbacks(new StatusCallbacks());
    service->createCharacteristic(OTA_CONTROL_UUID,BLECharacteristic::PROPERTY_WRITE)->setCallbacks(new ControlCallbacks());
    service->createCharacteristic(OTA_DATA_UUID,BLECharacteristic::PROPERTY_WRITE)->setCallbacks(new DataCallbacks());
    service->start();
    // Advertising packet stays within 31 bytes: OTA service is discovered after selecting by name.
}
static bool canonical(const uint8_t *field,size_t length) {
    bool ended=false;
    for(size_t i=0;i<length;++i) {
        if(!field[i]) ended=true;
        else if(ended||field[i]<32||field[i]>126) return false;
    }
    return ended&&field[0]!=0;
}
static bool validateIncomingProfile() {
    uint8_t header[24],segment[8];
    if(esp_partition_read(target,0,header,24)!=ESP_OK||header[0]!=0xE9||header[1]>16) return false;
    uint32_t pos=24;unsigned found=0;
    // Scan only image data segments, keeping the overlap needed for the 128-byte profile.
    uint8_t block[512+127];
    for(unsigned s=0;s<header[1];++s) {
        if(pos+8>total||esp_partition_read(target,pos,segment,8)!=ESP_OK) return false;
        uint32_t length=u32(segment+4);pos+=8;if(length>total||pos+length>total) return false;
        for(uint32_t start=0;start<length;start+=512) {
            size_t size=min(uint32_t(sizeof(block)),length-start);
            if(esp_partition_read(target,pos+start,block,size)!=ESP_OK) return false;
            size_t checks=min(size_t(512),size);
            for(size_t i=0;i<checks&&i+128<=size;++i) {
                if(memcmp(block+i,tqtProfile.magic,16)!=0) continue;
                ++found;const uint8_t *p=block+i;
                if(u32(p+16)!=2||memcmp(p+20,tqtProfile.hw,8)||memcmp(p+28,manifest+84,16)||
                   memcmp(p+44,tqtProfile.nombre,24)||memcmp(p+68,tqtProfile.module,24)||u32(p+92)!=1||
                   !constantEqual(p+96,tqtProfile.otaKey,32)) return false;
            }
        }
        pos+=length;
    }
    return found==1;
}
static bool authorizeManifest() {
    uint8_t signature[32];
    if(!hasKey()||!bootValid||!nonceAvailable||!hmac(manifest,106,signature)||!constantEqual(signature,manifest+106,32)) return false;
    if(!constantEqual(nonce,manifest,16)||memcmp(manifest+52,tqtProfile.nombre,24)||memcmp(manifest+76,tqtProfile.hw,8)||
       memcmp(manifest+100,BLEDevice::getAddress().getNative(),6)||!canonical(manifest+84,16)) return false;
    target=esp_ota_get_next_update_partition(nullptr);uint32_t size=u32(manifest+48);
    if(!target||target==esp_ota_get_running_partition()||size<65536||size>target->size) return false;
    uint8_t keyData[15+16];memcpy(keyData,"TQT-OTA-DATA-v1",15);memcpy(keyData+15,nonce,16);
    uint8_t sessionKey[32];if(!hmac(keyData,sizeof(keyData),sessionKey)) return false;
    if(mbedtls_aes_setkey_enc(&aes,sessionKey,256)!=0) return false;
    memset(sessionKey,0,32);memcpy(counter,nonce,16);memset(streamBlock,0,16);counterOffset=0;
    if(mbedtls_sha256_starts(&digest,0)!=0||esp_ota_begin(target,size,&handle)!=ESP_OK) return false;
    otaOpen=true;nonceAvailable=false;total=size;setOffset(0);setState(RECEIVING);return true;
}
void tqtOtaTick(bool relaysIdle) {
    uint32_t now=millis();
    if(!bootValid&&uint32_t(now-bootAt)>=3000) {
        if(bootHealthy&&packets&&serverRef&&esp_bt_controller_get_status()==ESP_BT_CONTROLLER_STATUS_ENABLED) {
            bootValid=esp_ota_mark_app_valid_cancel_rollback()==ESP_OK;
        } else { esp_ota_mark_app_invalid_rollback_and_reboot(); }
    }
    if(state==RESTARTING) { if(uint32_t(now-restartAt)>500) ESP.restart();return; }
    if(disconnected) { disconnected=false;if(tqtOtaBusy()) abortUpdate("disconnected"); }
    if(overflow) { overflow=false;if(tqtOtaBusy()) abortUpdate("queue_or_packet"); }
    uint8_t command=control;control=0;
    if(command==3) { abortUpdate("");return; }
    if(command==1) {
        if(tqtOtaBusy()) return;
        if(!relaysIdle||!hasKey()||!bootValid||!hashReady||!packets) { setState(ERROR_STATE,"busy_or_not_provisioned");return; }
        xQueueReset(packets);manifestBytes=0;total=138;setOffset(0);lastPacket=now;setState(MANIFEST);
    }
    if(command==2) {
        if(state!=READY||esp_ota_set_boot_partition(target)!=ESP_OK) { abortUpdate("commit_failed");return; }
        restartAt=now;setState(RESTARTING);return;
    }
    if(tqtOtaBusy()&&uint32_t(now-lastPacket)>30000) { abortUpdate("timeout");return; }
    Packet packet;
    if(!packets||xQueueReceive(packets,&packet,0)!=pdTRUE) return;
    uint32_t at=u32(packet.data),size=packet.length-4;
    if(at<offset) return; // Duplicate acknowledged packet; never decrypt/write it twice.
    if(at!=offset||size>total-offset) { abortUpdate("offset_or_size");return; }
    lastPacket=now;
    if(state==MANIFEST) {
        memcpy(manifest+manifestBytes,packet.data+4,size);manifestBytes+=size;setOffset(manifestBytes);
        if(manifestBytes==138&&!authorizeManifest()) abortUpdate("authorization_failed");
        return;
    }
    if(state!=RECEIVING) return;
    uint8_t clear[180];
    if(mbedtls_aes_crypt_ctr(&aes,size,&counterOffset,counter,streamBlock,packet.data+4,clear)!=0||
       mbedtls_sha256_update(&digest,clear,size)!=0||esp_ota_write(handle,clear,size)!=ESP_OK) { abortUpdate("write_failed");return; }
    setOffset(offset+size);
    if(offset==total) {
        uint8_t computed[32];
        if(mbedtls_sha256_finish(&digest,computed)!=0||!constantEqual(computed,manifest+16,32)||!validateIncomingProfile()) { abortUpdate("hash_or_profile_failed");return; }
        esp_err_t end=esp_ota_end(handle);otaOpen=false;
        if(end!=ESP_OK) { abortUpdate("image_invalid");return; }
        setState(READY);
    }
}
