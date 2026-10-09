/*******************************************************************************
 * PROYECTO: TQT2 - MÓDULO DE RESPALDO R2
 * FIRMWARE: V3.1.1 CORREGIDO
 *
 * Base funcional: PCB_TQT_R2_V3_0_RESPALDO.ino
 * Mejoras tomadas de: TQT2_RESPALDO_V2_1_CORREGIDO.ino
 * Hardware revisado: ESP32-WROOM-32E-N4 + etapa de relés mostrada en esquema.
 *
 * CAMBIOS PRINCIPALES
 *  - Conserva nombre BLE, UUID y lógica PPON / POFF del firmware original.
 *  - Solución definitiva para GPIO12/MTDI mediante eFuse VDD_SDIO=3.3 V.
 *  - Verifica LOS TRES eFuses y comprueba errores de escritura.
 *  - NO deshabilita el Brownout Detector.
 *  - Inicializa todas las salidas de relé en LOW lo antes posible.
 *  - Elimina delay(3000) del callback BLE; usa máquina de estados con millis().
 *  - Evita energizar simultáneamente R_01 y R_02.
 *  - GPIO26 (R_C) gobierna los dos relés comunes del esquema.
 *  - GPIO27 (R_S) se conserva por compatibilidad, pero se mantiene LOW porque
 *    no aparece conectado a las bobinas en el diagrama de relés suministrado.
 *  - Reinicio de advertising BLE fuera del callback.
 *  - Potencia BLE a 0 dBm para reducir picos de corriente.
 *  - EEPROM validada.
 *  - Conserva UART2 en GPIO16/17 y añade consola no bloqueante.
 *  - Watchdog con inicialización/reconfiguración segura.
 *  - V3.1.1: evita tipos personalizados en firmas de funciones para compatibilidad
 *    con el autogenerador de prototipos del Arduino IDE.
 *  - V3.1.2: el nombre compilado en Nombre_Del_Ble tiene prioridad y reemplaza
 *    automaticamente cualquier nombre anterior guardado en EEPROM.
 *
 * IMPORTANTE SOBRE eFUSE:
 *  Esta compilación está preparada EXCLUSIVAMENTE para el módulo indicado en
 *  el esquema: ESP32-WROOM-32E-N4. La programación VDD_SDIO=3.3 V es irreversible.
 *  Si en el futuro se monta un ESP32/módulo diferente, poner
 *  ENABLE_VDD_SDIO_3V3_EFUSE_FIX en 0 hasta verificar el tipo de Flash.
 *******************************************************************************/

#include <Arduino.h>
#include <BLEDevice.h>
#include <BLEUtils.h>
#include <BLEServer.h>
#include <EEPROM.h>
#include <esp_task_wdt.h>
#include <esp_bt.h>
#include <esp_system.h>
#include <esp_err.h>
#include "esp_efuse.h"
#include "esp_efuse_table.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"

/*******************************************************************************
 * CONFIGURACIÓN GENERAL
 *******************************************************************************/
#define Nombre_Del_Ble      "TQT_R2_V30_0024"
#define SERVICE_UUID        "4fafc201-1fb5-459e-8fcc-c5c9c331914b"
#define CHARACTERISTIC_UUID "beb5483e-36e1-4688-b7f5-ea07361b26a8"

#define EEPROM_SIZE 64
#define NAME_ADDR   0
#define DATA_ADDR   32

#define RX2_PIN 16
#define TX2_PIN 17
#define SERIAL2_BAUD_RATE 115200

#define WDT_TIMEOUT_MS 5000

// 1 = programa una sola vez los eFuses para fijar VDD_SDIO a 3.3 V.
// USAR SOLO con el ESP32-WROOM-32E-N4 indicado en el esquema.
#define ENABLE_VDD_SDIO_3V3_EFUSE_FIX 1

// Tiempo de estabilización antes de iniciar BLE.
#define POWER_STABILIZATION_MS 300

// Duración del pulso de los relés.
#define RELAY_PULSE_DURATION_MS 3000UL

// Espera antes de reiniciar advertising tras una desconexión.
#define BLE_ADV_RESTART_DELAY_MS 250UL

/*******************************************************************************
 * HARDWARE SEGÚN ESQUEMA
 *******************************************************************************/
const uint8_t LED_BLE_PIN      = 32;  // LED_BLE -> R29 -> Q9 -> LED
const uint8_t RELAY_ON_PIN     = 14;  // R_01 -> MOSFET -> relé inferior izquierdo
const uint8_t RELAY_OFF_PIN    = 12;  // R_02 / MTDI -> MOSFET -> relé inferior derecho
const uint8_t RELAY_COMMON_PIN = 26;  // R_C -> dos MOSFET -> dos relés superiores
const uint8_t RELAY_RS_PIN     = 27;  // R_S; no aparece conectado en el diagrama de relés mostrado

/*******************************************************************************
 * BLE
 *******************************************************************************/
BLEServer *pServer = nullptr;
BLECharacteristic *pCharacteristic = nullptr;

volatile bool deviceConnected = false;
volatile bool isCurrentlyAdvertising = false;
volatile bool advertisingRestartPending = false;
volatile uint32_t disconnectMillis = 0;

String activeDeviceName = Nombre_Del_Ble;

/*******************************************************************************
 * LED
 *******************************************************************************/
uint32_t previousLedMillis = 0;
const uint32_t LED_BLINK_INTERVAL_MS = 500;
bool ledState = LOW;

/*******************************************************************************
 * RELÉS
 *******************************************************************************/
enum RelayCommand : uint8_t {
    RELAY_CMD_NONE = 0,
    RELAY_CMD_PPON,
    RELAY_CMD_POFF
};

enum RelayState : uint8_t {
    RELAY_IDLE = 0,
    RELAY_PPON_ACTIVE,
    RELAY_POFF_ACTIVE
};

RelayState currentRelayState = RELAY_IDLE;
uint32_t relayPulseStartMillis = 0;
QueueHandle_t relayCommandQueue = nullptr;

/*******************************************************************************
 * CONSOLA SERIAL NO BLOQUEANTE
 *******************************************************************************/
String serial0Buffer;
String serial2Buffer;
bool watchdogSubscribed = false;

/*******************************************************************************
 * FUNCIONES DE HARDWARE SEGURO
 *******************************************************************************/
void configureOutputsSafe() {
    pinMode(LED_BLE_PIN, OUTPUT);
    pinMode(RELAY_ON_PIN, OUTPUT);
    pinMode(RELAY_OFF_PIN, OUTPUT);
    pinMode(RELAY_COMMON_PIN, OUTPUT);
    pinMode(RELAY_RS_PIN, OUTPUT);

    // Estado seguro inmediato.
    digitalWrite(LED_BLE_PIN, LOW);
    digitalWrite(RELAY_COMMON_PIN, LOW);
    digitalWrite(RELAY_RS_PIN, LOW);
    digitalWrite(RELAY_ON_PIN, LOW);
    digitalWrite(RELAY_OFF_PIN, LOW);

    ledState = LOW;
}

void setAllRelaysLow() {
    // Primero se libera la etapa común y después los relés de selección.
    digitalWrite(RELAY_COMMON_PIN, LOW);
    digitalWrite(RELAY_RS_PIN, LOW);
    digitalWrite(RELAY_ON_PIN, LOW);
    digitalWrite(RELAY_OFF_PIN, LOW);
}

/*******************************************************************************
 * eFUSE: GPIO12 / MTDI / VDD_SDIO
 *
 * NOTA Arduino IDE:
 * Se usa una mascara uint8_t en lugar de un struct personalizado. El
 * preprocesador de Arduino genera prototipos automaticamente y, dependiendo de
 * la version del IDE/core, puede colocarlos antes de la declaracion de un tipo
 * personalizado y provocar: "does not name a type".
 *******************************************************************************/
const uint8_t EFUSE_STATE_FORCE = 0x01;
const uint8_t EFUSE_STATE_REG   = 0x02;
const uint8_t EFUSE_STATE_TIEH  = 0x04;
const uint8_t EFUSE_STATE_3V3_MASK = EFUSE_STATE_FORCE | EFUSE_STATE_REG | EFUSE_STATE_TIEH;

uint8_t readFlashEfuseState() {
    uint8_t state = 0;

    if (esp_efuse_read_field_bit(ESP_EFUSE_XPD_SDIO_FORCE)) {
        state |= EFUSE_STATE_FORCE;
    }
    if (esp_efuse_read_field_bit(ESP_EFUSE_XPD_SDIO_REG)) {
        state |= EFUSE_STATE_REG;
    }
    if (esp_efuse_read_field_bit(ESP_EFUSE_XPD_SDIO_TIEH)) {
        state |= EFUSE_STATE_TIEH;
    }

    return state;
}

bool flashEfuseIsFixed3V3(uint8_t state) {
    return (state & EFUSE_STATE_3V3_MASK) == EFUSE_STATE_3V3_MASK;
}

void printFlashEfuseStatus(Print &out) {
    uint8_t state = readFlashEfuseState();

    out.print(F("[eFUSE] XPD_SDIO_FORCE="));
    out.print((state & EFUSE_STATE_FORCE) ? 1 : 0);
    out.print(F("  XPD_SDIO_REG="));
    out.print((state & EFUSE_STATE_REG) ? 1 : 0);
    out.print(F("  XPD_SDIO_TIEH="));
    out.println((state & EFUSE_STATE_TIEH) ? 1 : 0);

    if (flashEfuseIsFixed3V3(state)) {
        out.println(F("[eFUSE] VDD_SDIO fijado permanentemente a 3.3 V; GPIO12 ya no selecciona el voltaje al arrancar."));
    } else {
        out.println(F("[eFUSE] VDD_SDIO aun depende total o parcialmente de la configuracion de arranque."));
    }
}

bool programFlashEfuse3V3() {
#if ENABLE_VDD_SDIO_3V3_EFUSE_FIX
    uint8_t before = readFlashEfuseState();

    if (flashEfuseIsFixed3V3(before)) {
        Serial.println(F("[eFUSE] Configuracion 3.3 V ya aplicada. No se escribe nada."));
        return true;
    }

    Serial.println(F("[eFUSE] ATENCION: se programaran eFuses irreversibles para fijar VDD_SDIO=3.3 V."));
    Serial.println(F("[eFUSE] Hardware objetivo confirmado por esquema: ESP32-WROOM-32E-N4."));
    printFlashEfuseStatus(Serial);

    // Se usa escritura por lote para que los tres bits se preparen y quemen juntos.
    esp_err_t err = esp_efuse_batch_write_begin();
    if (err != ESP_OK) {
        Serial.print(F("[eFUSE][ERROR] batch_write_begin: "));
        Serial.println(esp_err_to_name(err));
        return false;
    }

    err = esp_efuse_write_field_bit(ESP_EFUSE_XPD_SDIO_REG);
    if (err != ESP_OK) {
        Serial.print(F("[eFUSE][ERROR] XPD_SDIO_REG: "));
        Serial.println(esp_err_to_name(err));
        esp_efuse_batch_write_cancel();
        return false;
    }

    err = esp_efuse_write_field_bit(ESP_EFUSE_XPD_SDIO_TIEH);
    if (err != ESP_OK) {
        Serial.print(F("[eFUSE][ERROR] XPD_SDIO_TIEH: "));
        Serial.println(esp_err_to_name(err));
        esp_efuse_batch_write_cancel();
        return false;
    }

    err = esp_efuse_write_field_bit(ESP_EFUSE_XPD_SDIO_FORCE);
    if (err != ESP_OK) {
        Serial.print(F("[eFUSE][ERROR] XPD_SDIO_FORCE: "));
        Serial.println(esp_err_to_name(err));
        esp_efuse_batch_write_cancel();
        return false;
    }

    err = esp_efuse_batch_write_commit();
    if (err != ESP_OK) {
        Serial.print(F("[eFUSE][ERROR] batch_write_commit: "));
        Serial.println(esp_err_to_name(err));
        return false;
    }

    delay(20);
    uint8_t after = readFlashEfuseState();
    printFlashEfuseStatus(Serial);

    if (!flashEfuseIsFixed3V3(after)) {
        Serial.println(F("[eFUSE][ERROR] La verificacion posterior fallo. NO se reporta reparacion como exitosa."));
        return false;
    }

    Serial.println(F("[eFUSE] Programacion y verificacion correctas."));
    Serial.println(F("[eFUSE] Reiniciando para que el siguiente arranque use VDD_SDIO fijo a 3.3 V..."));
    Serial.flush();
    delay(100);
    ESP.restart();

    return true; // No se alcanza normalmente porque ESP.restart() reinicia el MCU.
#else
    Serial.println(F("[eFUSE] Auto-fix deshabilitado por compilacion."));
    printFlashEfuseStatus(Serial);
    return flashEfuseIsFixed3V3(readFlashEfuseState());
#endif
}

/*******************************************************************************
 * WATCHDOG
 *******************************************************************************/
void initWatchdog() {
    esp_task_wdt_config_t config = {};
    config.timeout_ms = WDT_TIMEOUT_MS;
    config.idle_core_mask = 0;
    config.trigger_panic = true;

    esp_err_t err = esp_task_wdt_init(&config);

    // En algunas versiones de Arduino-ESP32 el TWDT ya viene inicializado.
    if (err == ESP_ERR_INVALID_STATE) {
        err = esp_task_wdt_reconfigure(&config);
    }

    if (err != ESP_OK) {
        Serial.print(F("[WDT][WARN] No se pudo inicializar/reconfigurar TWDT: "));
        Serial.println(esp_err_to_name(err));
        return;
    }

    // Si la tarea ya estaba registrada, no intentamos registrarla dos veces.
    err = esp_task_wdt_status(NULL);
    if (err == ESP_OK) {
        watchdogSubscribed = true;
        Serial.println(F("[WDT] loopTask ya estaba registrado en el watchdog."));
        return;
    }

    err = esp_task_wdt_add(NULL);
    if (err == ESP_OK) {
        watchdogSubscribed = true;
        Serial.println(F("[WDT] loopTask agregado al watchdog."));
    } else {
        watchdogSubscribed = false;
        Serial.print(F("[WDT][WARN] esp_task_wdt_add: "));
        Serial.println(esp_err_to_name(err));
    }
}

/*******************************************************************************
 * EEPROM
 *******************************************************************************/
bool isValidDeviceName(const String &name) {
    if (name.length() == 0 || name.length() > 24) {
        return false;
    }

    if ((uint8_t)name[0] == 0xFF) {
        return false;
    }

    for (size_t i = 0; i < name.length(); ++i) {
        uint8_t c = (uint8_t)name[i];
        if (c < 32 || c > 126) {
            return false;
        }
    }

    return true;
}

void loadDeviceName() {
    // El nombre definido en el firmware SIEMPRE tiene prioridad sobre el
    // que haya quedado guardado de una programacion anterior.
    // Solo se escribe EEPROM si el nombre realmente cambio, para evitar
    // escrituras innecesarias en cada arranque.
    activeDeviceName = Nombre_Del_Ble;

    if (!EEPROM.begin(EEPROM_SIZE)) {
        Serial.println(F("[EEPROM][ERROR] EEPROM.begin fallo. Se usara el nombre definido en el firmware."));
        return;
    }

    String storedName = EEPROM.readString(NAME_ADDR);

    if (!isValidDeviceName(storedName) || storedName != activeDeviceName) {
        Serial.print(F("[EEPROM] Actualizando nombre BLE: '"));
        Serial.print(storedName);
        Serial.print(F("' -> '"));
        Serial.print(activeDeviceName);
        Serial.println(F("'"));

        EEPROM.writeString(NAME_ADDR, activeDeviceName);
        if (EEPROM.commit()) {
            Serial.println(F("[EEPROM] Nombre BLE actualizado correctamente."));
        } else {
            Serial.println(F("[EEPROM][WARN] No fue posible confirmar EEPROM.commit(). Se usara el nombre nuevo en RAM."));
        }
    } else {
        Serial.print(F("[EEPROM] Nombre BLE ya coincide con el firmware: "));
        Serial.println(activeDeviceName);
    }
}

/*******************************************************************************
 * RELÉS: LÓGICA NO BLOQUEANTE
 *******************************************************************************/
void startRelayPulse(uint8_t command) {
    // Siempre partimos de un estado conocido y sin solapamiento.
    setAllRelaysLow();

    if (command == RELAY_CMD_PPON) {
        // Primero se selecciona R_01 y al final se energiza la etapa común R_C.
        digitalWrite(RELAY_ON_PIN, HIGH);
        digitalWrite(RELAY_OFF_PIN, LOW);
        digitalWrite(RELAY_COMMON_PIN, HIGH);

        currentRelayState = RELAY_PPON_ACTIVE;
        relayPulseStartMillis = millis();
        Serial.println(F("[RELAY] PPON iniciado: R_C=1, R_01=1, R_02=0, R_S=0"));
    }
    else if (command == RELAY_CMD_POFF) {
        // Primero se selecciona R_02 y al final se energiza la etapa común R_C.
        digitalWrite(RELAY_ON_PIN, LOW);
        digitalWrite(RELAY_OFF_PIN, HIGH);
        digitalWrite(RELAY_COMMON_PIN, HIGH);

        currentRelayState = RELAY_POFF_ACTIVE;
        relayPulseStartMillis = millis();
        Serial.println(F("[RELAY] POFF iniciado: R_C=1, R_01=0, R_02=1, R_S=0"));
    }
}

void processRelayStateMachine() {
    RelayCommand incomingCommand;

    if (currentRelayState == RELAY_IDLE) {
        if (relayCommandQueue != nullptr &&
            xQueueReceive(relayCommandQueue, &incomingCommand, 0) == pdTRUE) {
            startRelayPulse(incomingCommand);
        }
    } else {
        // Mientras existe un pulso activo se descartan comandos nuevos para impedir
        // cambios de sentido/seleccion a mitad de los 3 segundos.
        while (relayCommandQueue != nullptr &&
               xQueueReceive(relayCommandQueue, &incomingCommand, 0) == pdTRUE) {
            Serial.println(F("[RELAY][BUSY] Comando ignorado: hay un pulso de 3 s en curso."));
        }

        if ((uint32_t)(millis() - relayPulseStartMillis) >= RELAY_PULSE_DURATION_MS) {
            setAllRelaysLow();
            currentRelayState = RELAY_IDLE;
            relayPulseStartMillis = 0;
            Serial.println(F("[RELAY] Pulso finalizado. Todas las salidas en LOW."));
        }
    }
}

/*******************************************************************************
 * CALLBACKS BLE
 *******************************************************************************/
class MyServerCallbacks : public BLEServerCallbacks {
    void onConnect(BLEServer* pServerInstance) override {
        (void)pServerInstance;
        deviceConnected = true;
        isCurrentlyAdvertising = false;
        advertisingRestartPending = false;

        digitalWrite(LED_BLE_PIN, HIGH);
        ledState = HIGH;

        Serial.println(F("[BLE] Dispositivo conectado."));
    }

    void onDisconnect(BLEServer* pServerInstance) override {
        (void)pServerInstance;
        deviceConnected = false;
        isCurrentlyAdvertising = false;
        advertisingRestartPending = true;
        disconnectMillis = millis();

        digitalWrite(LED_BLE_PIN, LOW);
        ledState = LOW;
        previousLedMillis = millis();

        Serial.println(F("[BLE] Dispositivo desconectado. Advertising se reactivara desde loop()."));
    }
};

class MyCallbacks : public BLECharacteristicCallbacks {
    void onWrite(BLECharacteristic *pChar) override {
        String value = pChar->getValue().c_str();
        value.trim();

        RelayCommand command = RELAY_CMD_NONE;

        if (value.equalsIgnoreCase("PPON")) {
            command = RELAY_CMD_PPON;
        }
        else if (value.equalsIgnoreCase("POFF")) {
            command = RELAY_CMD_POFF;
        }
        else {
            Serial.print(F("[BLE] Comando ignorado: "));
            Serial.println(value);
            return;
        }

        if (relayCommandQueue == nullptr) {
            Serial.println(F("[RELAY][ERROR] Cola de comandos no disponible."));
            return;
        }

        if (xQueueSend(relayCommandQueue, &command, 0) != pdTRUE) {
            Serial.println(F("[RELAY][BUSY] Comando no aceptado: cola ocupada."));
        }
    }
};

/*******************************************************************************
 * BLE
 *******************************************************************************/
void initBLE(const char* deviceName) {
    Serial.print(F("[BLE] Iniciando con nombre: "));
    Serial.println(deviceName);

    BLEDevice::init(deviceName);

    // Reduce picos RF sin modificar UUID ni protocolo de la app.
    esp_err_t errDefault = esp_ble_tx_power_set(ESP_BLE_PWR_TYPE_DEFAULT, ESP_PWR_LVL_N0);
    esp_err_t errAdv = esp_ble_tx_power_set(ESP_BLE_PWR_TYPE_ADV, ESP_PWR_LVL_N0);

    if (errDefault != ESP_OK || errAdv != ESP_OK) {
        Serial.print(F("[BLE][WARN] Ajuste de potencia: DEFAULT="));
        Serial.print(esp_err_to_name(errDefault));
        Serial.print(F(" ADV="));
        Serial.println(esp_err_to_name(errAdv));
    }

    pServer = BLEDevice::createServer();
    pServer->setCallbacks(new MyServerCallbacks());

    BLEService *pService = pServer->createService(SERVICE_UUID);
    pCharacteristic = pService->createCharacteristic(
        CHARACTERISTIC_UUID,
        BLECharacteristic::PROPERTY_READ |
        BLECharacteristic::PROPERTY_WRITE
    );

    pCharacteristic->setCallbacks(new MyCallbacks());
    pCharacteristic->setValue("READY");
    pService->start();

    BLEAdvertising *pAdvertising = BLEDevice::getAdvertising();
    pAdvertising->addServiceUUID(SERVICE_UUID);
    pAdvertising->setScanResponse(true);
    pAdvertising->setMinPreferred(0x06);
    pAdvertising->setMinPreferred(0x12);

    BLEDevice::startAdvertising();
    isCurrentlyAdvertising = true;
    advertisingRestartPending = false;

    Serial.println(F("[BLE] Advertising iniciado."));

    // Verificación adicional: el controlador BT debe quedar habilitado.
    if (esp_bt_controller_get_status() != ESP_BT_CONTROLLER_STATUS_ENABLED) {
        Serial.println(F("[BLE][ERROR] El controlador Bluetooth no quedo habilitado. Reinicio de recuperacion."));
        Serial.flush();
        delay(100);
        ESP.restart();
    }
}

void processBLEAdvertising() {
    if (deviceConnected) {
        return;
    }

    if (advertisingRestartPending &&
        (uint32_t)(millis() - disconnectMillis) >= BLE_ADV_RESTART_DELAY_MS) {
        BLEDevice::startAdvertising();
        isCurrentlyAdvertising = true;
        advertisingRestartPending = false;
        Serial.println(F("[BLE] Advertising reactivado."));
    }
}

/*******************************************************************************
 * LED BLE
 *******************************************************************************/
void processLed() {
    if (deviceConnected) {
        if (!ledState) {
            ledState = HIGH;
            digitalWrite(LED_BLE_PIN, HIGH);
        }
        return;
    }

    uint32_t now = millis();
    if ((uint32_t)(now - previousLedMillis) >= LED_BLINK_INTERVAL_MS) {
        previousLedMillis = now;
        ledState = !ledState;
        digitalWrite(LED_BLE_PIN, ledState ? HIGH : LOW);
    }
}

/*******************************************************************************
 * DIAGNÓSTICO / CONSOLA
 *******************************************************************************/
const char* resetReasonText(esp_reset_reason_t reason) {
    switch (reason) {
        case ESP_RST_UNKNOWN:   return "UNKNOWN";
        case ESP_RST_POWERON:   return "POWERON";
        case ESP_RST_EXT:       return "EXT";
        case ESP_RST_SW:        return "SOFTWARE";
        case ESP_RST_PANIC:     return "PANIC";
        case ESP_RST_INT_WDT:   return "INT_WDT";
        case ESP_RST_TASK_WDT:  return "TASK_WDT";
        case ESP_RST_WDT:       return "WDT";
        case ESP_RST_DEEPSLEEP: return "DEEPSLEEP";
        case ESP_RST_BROWNOUT:  return "BROWNOUT";
        case ESP_RST_SDIO:      return "SDIO";
        default:                return "OTRO";
    }
}

void printSystemStatus(Print &out) {
    out.println(F("---------------- STATUS ----------------"));
    out.print(F("Nombre BLE: "));
    out.println(activeDeviceName);
    out.print(F("Conectado BLE: "));
    out.println(deviceConnected ? F("SI") : F("NO"));
    out.print(F("Advertising marcado activo: "));
    out.println(isCurrentlyAdvertising ? F("SI") : F("NO"));
    out.print(F("Estado rele: "));

    switch (currentRelayState) {
        case RELAY_IDLE:        out.println(F("IDLE")); break;
        case RELAY_PPON_ACTIVE: out.println(F("PPON")); break;
        case RELAY_POFF_ACTIVE: out.println(F("POFF")); break;
        default:                out.println(F("DESCONOCIDO")); break;
    }

    esp_reset_reason_t reason = esp_reset_reason();
    out.print(F("Reset reason: "));
    out.print(resetReasonText(reason));
    out.print(F(" ("));
    out.print((int)reason);
    out.println(F(")"));
    printFlashEfuseStatus(out);
    out.println(F("----------------------------------------"));
}

void processConsoleCommand(Print &out, String command) {
    command.trim();

    if (command.equalsIgnoreCase("MAC")) {
        String macAddress = BLEDevice::getAddress().toString().c_str();
        out.print(activeDeviceName);
        out.print(F(" MAC: "));
        out.println(macAddress);
    }
    else if (command.equalsIgnoreCase("STATUS")) {
        printSystemStatus(out);
    }
    else if (command.equalsIgnoreCase("EFUSE")) {
        printFlashEfuseStatus(out);
    }
    else if (command.length() > 0) {
        out.print(F("Comando de consola ignorado: "));
        out.println(command);
    }
}

void processSerialPort(Stream &port, String &buffer) {
    while (port.available() > 0) {
        char c = (char)port.read();

        if (c == '\r') {
            continue;
        }

        if (c == '\n') {
            if (buffer.length() > 0) {
                processConsoleCommand(port, buffer);
                buffer = "";
            }
            continue;
        }

        if ((uint8_t)c >= 32 && (uint8_t)c <= 126) {
            if (buffer.length() < 32) {
                buffer += c;
            } else {
                buffer = "";
                port.println(F("[SERIAL][WARN] Linea descartada por longitud."));
            }
        }
    }
}

/*******************************************************************************
 * SETUP
 *******************************************************************************/
void setup() {
    // IMPORTANTE: no se deshabilita el Brownout Detector.

    // Salidas seguras apenas entra setup().
    configureOutputsSafe();

    Serial.begin(115200);
    delay(50);

    Serial.println();
    Serial.println(F("========================================================"));
    Serial.println(F(" TQT R2 V3.1.2 - BLE / RELAYS / COLD-BOOT FIX"));
    Serial.println(F(" Base: PCB_TQT_R2_V3_0_RESPALDO.ino"));
    Serial.println(F(" Hardware: ESP32-WROOM-32E-N4"));
    Serial.println(F("========================================================"));
    esp_reset_reason_t bootReason = esp_reset_reason();
    Serial.print(F("[BOOT] Reset reason: "));
    Serial.print(resetReasonText(bootReason));
    Serial.print(F(" ("));
    Serial.print((int)bootReason);
    Serial.println(F(")"));

    // Dejar estabilizar la alimentación antes de cualquier operación irreversible o RF.
    delay(POWER_STABILIZATION_MS);

    // Solución a GPIO12/MTDI. Si programa eFuse por primera vez, reinicia automáticamente.
    bool efuseOk = programFlashEfuse3V3();
    if (!efuseOk) {
        Serial.println(F("[eFUSE][WARN] No se pudo confirmar VDD_SDIO fijo a 3.3 V."));
        Serial.println(F("[eFUSE][WARN] El equipo continuara, pero el arranque en frio puede seguir siendo sensible a GPIO12."));
    }

    // Cola de comandos BLE para sacar el control de relés del callback.
    relayCommandQueue = xQueueCreate(1, sizeof(RelayCommand));
    if (relayCommandQueue == nullptr) {
        Serial.println(F("[RELAY][FATAL] No se pudo crear la cola de comandos."));
    }

    loadDeviceName();

    // Conserva UART2 del firmware original.
    Serial2.begin(SERIAL2_BAUD_RATE, SERIAL_8N1, RX2_PIN, TX2_PIN);

    initWatchdog();

    // Pequeño margen adicional antes del arranque del radio BLE.
    delay(100);
    initBLE(activeDeviceName.c_str());

    String macAddress = BLEDevice::getAddress().toString().c_str();
    Serial.print(activeDeviceName);
    Serial.print(F(" MAC: "));
    Serial.println(macAddress);
    Serial.println(F("[BOOT] Sistema listo."));
}

/*******************************************************************************
 * LOOP
 *******************************************************************************/
void loop() {
    processLed();
    processRelayStateMachine();
    processBLEAdvertising();

    // Consola USB/UART0 y UART2 sin readStringUntil() bloqueante.
    processSerialPort(Serial, serial0Buffer);
    processSerialPort(Serial2, serial2Buffer);

    if (watchdogSubscribed) {
        esp_task_wdt_reset();
    }

    // Cede CPU a tareas del stack BLE/RTOS sin introducir un bloqueo largo.
    delay(1);
}
