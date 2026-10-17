# TQT R2 FW4.3 — offline OTA P256 v1

Fuente nueva basada en FW4.2 para HW3.0 / ESP32-WROOM-32E-N4. Conserva pines,
relés, PPON/POFF, esquema2/capabilities1 y clave OTA por unidad; la escritura de
eFuses sigue desactivada. La plantilla `0000` tiene clave cero y no debe grabarse.
No se modificó la base genérica4.0 ni FW4.2. El único trust anchor incluido es
el encabezado **público** existente de la base genérica.

El contrato normativo es `protocols/offline-v1.json`. OTA online1 permanece
compatible para que FW4.2 instale FW4.3. CONTROL5 recibe en DATA la autorización
de sesión de472B con offsetLE32, estado7 `offline_manifest`, y los mismos ACK
binarios/JSON de FW4.2. El grant contiene firma del servidor y clave pública del
teléfono; la firma del teléfono vincula además el nonce INFO actual. Se verifican
dispositivo, identidad, contador y hash de origen, versión canónica mínima4.3,
tamaño/slot, perfil y ambos hashes de destino. La imagen usa AES256CTR con clave
HMAC por grant; la clave OTA de unidad nunca se entrega al teléfono.

## INFO y compatibilidad BLE

INFO legacy conserva sus campos y HMAC, dentro del límite GATT de512B. Tras
leer INFO, se lee la característica READ `d45a0006-6a76-4e41-9f38-a7043f0ec069`.
Devuelve el mismo snapshot firmado en190B:

| Bytes | Campo lógico reconstruido por Android |
| --- | --- |
| 0 | `offline_protocol` |
| 1..65 | `offline_public_key` (punto P256 sin comprimir) |
| 66..69 | `offline_counter` (LE32) |
| 70..77 | `offline_anchor_id` |
| 78..109 | `offline_identity_proof` (HMAC unidad) |
| 110..173 | `offline_signature` (ECDSA SHA256, r32/s32 big endian) |
| 174..189 | `offline_last_grant` (UUID binario16) |

La firma/JSON se mantienen coherentes con nonce, hash, partición, boot válido y
perfil del mismo snapshot. La firma se reutiliza mientras su transcript no
cambia. Sin lectura INFO previa o cuando offline está deshabilitado, el frame
contiene190 ceros (`offline_protocol=0`). Los UUID y el servicio legacy no cambian.

## Persistencia y cortes de alimentación

NVS genera una clave privada P256 exclusiva del dispositivo. Un único blob
versionado `tqt_offline/state_v1` guarda private32, counterLE32, último UUID16 y
checksumSHA256; después de commit se vuelve a leer y verificar. Un blob corrupto
nunca se sustituye automáticamente por una identidad nueva. NVS o crypto
fallidos deshabilitan offline. Si el nuevo boot está pendiente, estos fallos
impiden confirmarlo y se solicita rollback al cumplir los3s de diagnóstico.

**Cualquier COMMIT, online u offline, consume el contador de forma durable antes
de seleccionar la partición de arranque.** Online guarda un último UUID de ceros.
Si falla NVS no se activa la imagen. Si se corta la alimentación después del
consumo y antes de activar la partición, arranca la aplicación anterior y el
grant queda consumido: se necesita conexión online para otra autorización. La
confirmación se hace mediante INFO autenticado (contador+1, UUID y hash destino,
boot válido); nunca se retransmite una imagen únicamente para comprobar éxito.
Las interrupciones anteriores al COMMIT permiten reiniciar desde cero con el
mismo grant y una firma nueva del teléfono. No hay reanudación parcial.

No existe reloj UTC fiable en el equipo. El firmware exige ámbito, contador y
uso único; Android/servidor aplican vigencia y política de cuenta. No se promete
revocación instantánea sin conexión. No borrar NVS ni cambiar la identidad como
procedimiento de recuperación; requiere un proceso de servicio autorizado.

## Verificación sin hardware

`compilar_verificacion.ps1` usa el Arduino CLI instalado con coreESP32 **3.3.11**,
FQBN `esp32:esp32:esp32doit-devkit-v1`, tres jobs, salidas/cache privadas en
`privado/fw43-build`. No instala ni modifica el core global. La documentación
histórica menciona3.3.12; esa versión no se validó en este trabajo. No hay comando
de carga/flash y los binarios de plantilla no son una entrega programable.

Pruebas nativas reproducibles del módulo real:

```powershell
docker build -t tqt-fw43-native-test -f firmware/esp32_r2/TQT_R2_V4_3/tests/native/Dockerfile firmware/esp32_r2/TQT_R2_V4_3
docker run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges tqt-fw43-native-test
```

La imagen usa g++ con `-Wall -Wextra -Werror` y mbedTLS real. Copia sin cambios el
módulo productivo y sustituye únicamente el encabezado público del trust anchor
por un fixture explícito y público (escalar1). Simula NVS y mutex; RNG usa
`getrandom`. Cubre wire/versiones, INFO/HMAC/firmas, grants correctos y alterados,
teléfono/dispositivo/nonce/ámbito/origen, consumo online/offline, recibos tras
reinicio, fallos/corrupciónNVS y agotamiento de contador. No simula BLE, Flash,
bootloader, alimentación ni relés y no certifica su funcionamiento físico.

Se usó `ecc-cm-hw-fw` para trazabilidad y revisión del contrato; la evidencia es
la compilación y pruebas ejecutables, separadas de cualquier validación física.
