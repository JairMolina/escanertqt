# Estado de Codex: TQT-Web

Actualizado: 2026-10-14 21:32 UTC
Commit de referencia: `15cafb8acee4` (puede no incluir cambios pendientes)

## Avance reportado
R2 0069 instalada y verificada fisicamente por COM3 con FW4.1. Esptool verifica hash Flash; INFO tras reinicio confirma nombre/HW/FW/credencialOTA y MAC8C:8C:29:C3:D6:A6. API registra PCB66 y capability eligible=true. Usuario puede retirar contactos. Web1.3.77 desplegada y saludable.

## Siguiente paso
Prueba OTA real en Chrome/Edge: R20069 alimentada normalmente, R1 apagada o sin conexion Bluetooth. Usuario debe elegir TQT_R2_V30_0069 y Actualizar por Bluetooth con FW4.1 para probar otra particion. Esperar resultado y contrastar job/attestation en servidor. No afirmar OTA fisica verificada todavia; COM3 cerrado y sin comandos de reles.

## Evidencia
Usuario autorizo y confirmo LISTO/banco libre; ESP32-D0WD-V3 rev3.1,1196624bytes escritos460800baud,hash deFlash verificado. Usuario confirmo BOOTlibre y reinicio; INFO real nombre0069 HW3.0 FW4.1 OTA1 y key_id coincide. PUT HTTPS programacion PCB66 correcto; GET capability eligibletrue/requires_serialfalse. GitHub rama codex/esp32-r2-ble-ota; produccion codigo927b965. Backups pre/post1377 existentes,78tests yPlaywright previos correctos. CM checkpoint/memoria/Git, ECC HWFW/CPP/security/verification.
