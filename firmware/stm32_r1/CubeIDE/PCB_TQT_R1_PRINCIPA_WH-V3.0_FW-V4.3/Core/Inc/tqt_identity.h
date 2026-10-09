#ifndef TQT_IDENTITY_H
#define TQT_IDENTITY_H
#include <stddef.h>
#include <stdint.h>
/* Perfil tecnico aprobado: no son datos de una unidad. */
#define TQT_HW_COMPATIBLE "3.0"
#define TQT_MCU_NAME "STM32F103RET6"
#define TQT_IDENTITY_ADDRESS 0x0807F800UL
#define TQT_IDENTITY_MAGIC 0x31545154UL
#define TQT_IDENTITY_SCHEMA 2U
#define TQT_IDENTITY_SIZE 76U
typedef struct __attribute__((packed)) {
    uint32_t magic;
    uint16_t schema;
    uint16_t length;
    char name[23];
    char id_r[5]; /* Numero de la R2 asociada, independiente del numero R1. */
    char mac_r[18];
    char hw[8];
    char fw[8];
    uint16_t reserved;
    uint32_t crc32;
} TQT_Identity;
_Static_assert(sizeof(TQT_Identity) == TQT_IDENTITY_SIZE, "identity size");
_Static_assert(offsetof(TQT_Identity, crc32) == 72, "CRC offset");
typedef enum {
    TQT_ID_OK=0, TQT_ID_FORMAT=1, TQT_ID_CRC=2,
    TQT_ID_FIELDS=3, TQT_ID_HW=4, TQT_ID_FW=5
} TQT_IdentityResult;
uint32_t TQT_IdentityCRC32(const uint8_t *bytes, size_t length);
TQT_IdentityResult TQT_IdentityValidate(const TQT_Identity *identity);
TQT_IdentityResult TQT_IdentityLoad(void);
const TQT_Identity *TQT_IdentityGet(void);
#endif
