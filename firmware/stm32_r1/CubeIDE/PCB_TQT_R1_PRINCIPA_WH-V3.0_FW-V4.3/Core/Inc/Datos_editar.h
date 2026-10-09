#ifndef DATOS_EDITAR_H
#define DATOS_EDITAR_H
/* DATOS PARA EDITAR DESDE STM32CUBEIDE.
 * Nombre/numero de R1, ID de R2, MAC de R2, HW de R1 y FW de R1.
 * R1 y R2 pueden tener numeros diferentes; ID y MAC deben pertenecer a la misma R2.
 * Cambiar FW al liberar una nueva version del codigo y recompilar.
 * El build calcula CRC y usa esta misma version en el perfil del firmware.
 * Datos de ejemplo: comprobar inventario antes de programar. */
#define TQT_LOCAL_NAME "TQT_R1_V30_0001"
#define TQT_LOCAL_ID "0002"
#define TQT_LOCAL_MAC_R "02:00:00:00:00:02"
#define TQT_LOCAL_HW "3.0"
#define TQT_FW_VERSION "4.3"
#endif
