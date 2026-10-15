# Estado de Codex: TQT-Web

Actualizado: 2026-10-15 15:33 UTC
Commit de referencia: `53650a75d2b2` (puede no incluir cambios pendientes)

## Avance reportado
Prueba BLE aislada autorizada por usuario, sin cambios ni despliegue web. Medicion real R20069/FW4.1:MTU247,bloques180,24muestras escritura81.21ms/lectura90.01ms,2.16KiBs. Copia temporalFW4.1.1 conWRITE_NR/notificaciones10B/MTU517/cola8 compilada y personalizada, aun NO grabada.

## Siguiente paso
Solicitar LISTO cuando R20069 se conecte USB-TTL COM3 enBOOT+RESET; hoy no aparece adaptadorCOM. Scripts outputs/r2_ble_probe/flash_probe.ps1 verificaMACsilicioD6A4 yhash antes degrabar. Avisarfin para soltarBOOT/reiniciar;leerINFO41.1;retirarcontactos. Ejecutar run_fast_ota_probe.py conPythonvenv estacionDownloads,medirOTA41.1 yrestaurar4.1 con--restore. No modificarweb/catalogo/firmwareoriginal; prod1.3.78 sigueigual. Imagenprivada enAppData TQT/programming/R2_0069_FW41.

## Evidencia
BaselineHMACidentidad/MAC8C:8C:29:C3:D6:A6 validos;limpioCANCELerrorSesionAnterior;datosdescartadosenIDLE,sinBEGIN/COMMIT,Flash/particionintactos ysinreles. Arduino3.3.12 build1135459bytes86%,RAM42220 12%. ProbeBINprivado1201136SHAe1d451cfbd51320e22e335cdc00f0033ce1aff234a4e3a1d98deb3425db4a771;esptoolchecksum/SHAvalidos;Dockerofflineperfil/HMAC138/AESCTRfragmentado reconstruyeappexacta;sintaxisPythoncorrecta. Candidato sinpruebafisicafasttodavia. ReferenciaFreki sololectura, sinconfigprivada. ECC HWFW/CPP/verificacion yCMcheckpoint/memoria.
