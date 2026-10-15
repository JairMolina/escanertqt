# Estado de Codex: TQT-Web

Actualizado: 2026-10-15 21:14 UTC
Commit de referencia: `81ff7f5ca2bc` (puede no incluir cambios pendientes)

## Avance reportado
Local 1.3.85: base4.0 generica XXXX y FW4.2 con eFuses desactivados; alta P256 ECDH/AES-GCM firmada. R2 0067 COM4 grabada y OTA4.2 real verificada por API tras fallo de desconexion; DB MAC 8C:8C:29:C3:D7:EA. Usuario exige nombre identico al inventario: nuevos binarios y transicion OTA automatica de guiones bajos a guiones, sin cambiar unidad/clave. Capacidades ECC HWFW, C++, seguridad y verificacion usadas para contratos y pruebas; CM para continuidad.

## Siguiente paso
Usuario debe probar transicion de nombre desde web local18082: cerrar OTA anterior pendiente si aparece, actualizar0067 a4.2; se esperan dos pasos OTA y nombre final TQT-R2-V30-0067. Verificar lectura fisica final y DB. Produccion sin cambios; antes de desplegar conservar clave privada del emisor fuera de Git y transferirla segura.

## Evidencia
Builds Arduino ESP32 3.3.12 base1178511B y4.2 1130907B;18 pruebasR2 y40ESP32 OK;11 escenariostransporteOK; Playwright local1.3.85/caches1385/catalogo exact_name=true sin erroresJS. Lectura fisica previa0067 FW4.2,HW3.0,particion0x150000,HMAC e imagen validados en endpoint result;alta yOTA verified. Transicion nueva aun pendiente fisica.
