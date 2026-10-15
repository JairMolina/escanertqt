# Estado de Codex: TQT-Web

Actualizado: 2026-10-15 21:26 UTC
Commit de referencia: `8580b278d2a4` (puede no incluir cambios pendientes)

## Avance reportado
Cierre fisico local1.3.86: R2 0067 completada desde base generica4.0 y OTA4.2, transicion final por web exitosa. Nombre ESP32 exactamente igual al inventario TQT-R2-V30-0067; FW4.2 HW3.0 MAC8C:8C:29:C3:D7:EA. Lectura BLE fresca autentica y hash coinciden con imagen personalizada y trabajo final. Un solo registro y ninguna OTA pendiente. eFuses desactivados. ECC HWFW/seguridad/verificacion y CM aplicados.

## Siguiente paso
Prueba0067 cerrada. Produccion sigue sin desplegar; hacerlo solo por peticion expresa y conservando clave privada del emisor y credenciales de unidades fuera de Git. Proxima unidad nueva puede validar ruta directa de ultima base generica con nombre con guiones; esa revision se compilo y probo por protocolo, la0067 recorrio base inicial y transicion.

## Evidencia
Usuario: OTA verificada FW4.2 en web1.3.86. Trabajo9a5e54b583bff4ea0a427c64 verified. Lectura BLE independiente exactname TQT-R2-V30-0067,boot_validtrue,name_format2,particion0x150000,appSHA78d28604f878255f8f5ff7e937d302becda538748bdd65ae02f6e7921966554a. validate_final67 comprueba HMAC fresco,hash personalizado,MAC,FW/HW,estado ble_ota,unicidad y cero pendientes.58 pruebas servidor/agente y12 transporte previamenteOK; sin cambios de codigo en este cierre.
