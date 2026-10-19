# Estado de Codex: TQT-Web

Actualizado: 2026-10-19 06:49 UTC
Commit de referencia: `9fdbb1748bc4` (puede no incluir cambios pendientes)

## Avance reportado
Android 0.2.0 instalada y verificada en telefono Android13. Corregida consulta con API web vigente: 11 a 0011, QR local/camara, filtros Todas/R1/R2/R3, paginacion y ficha firmware/evidencia. Causa 404 confirmada en API Android no desplegada; nuevas programaciones bloqueadas con explicacion. Commit de codigo guardado; rama codex/android-inventario-qr-20261019. Sin cambios ni despliegue en produccion. Guia docs/ANDROID_INVENTARIO_020.md.

## Siguiente paso
Con R2 fisica: BLE/OTA/cortes/recuperacion. Backend Android pendiente de despliegue autorizado y respaldo; firma y publicacion definitiva del APK pendientes. Conservar base4.0 fija y contratos criptograficos. APK de ensayo entregado e instalado, sesion conservada.

## Evidencia
40JVM PASS;10casos instrumentados distintos Android13(9iniciales+4inventario finales con3repetidos); build y lint PASS(0errores/15avisos). 300PCB sin duplicados; 11/QR sintetico/ficha/catalogo concuerdan con web; busqueda vacia recuperable. Camara real y UI ADB; SDK firma y version0.2.0/code2 validos. Reinstalaciones Success sin intervencion. ECC Android/backend/verificacion y ui-ux-pro-max;0agentes/0Gemini.
