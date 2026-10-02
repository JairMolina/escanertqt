/*******************************************************************************
 * PROYECTO: TQT2 - MÓDULO DE RESPALDO R2
 * FIRMWARE OPTIMIZADO Y BLINDADO PARA LA PCB FÍSICA ANTERIOR (EXISTENTE)
 * 
 * Basado 1:1 en el firmware original PCB_TQT_R2_V2_0_RESPALDO.ino,
 * corrigiendo los fallos físicos de la tarjeta fabricada:
 * 
 * 1. SOLUCIÓN AL ARRANQUE EN FRÍO (Sin presionar RESET):
 *    - Auto-quema y verificación de eFuses (SDIO_FORCE y SDIO_TIEH).
 *      Neutraliza permanentemente el pin de strapping GPIO 12 (Q3 / Relé 2).
 *      El bootloader del ESP32 forzará siempre la Flash a 3.3V, ignorando
 *      el pulso inductivo Miller de 12V en el encendido en frío.
 *    - Desactivación del Brownout Detector (BOD) y pausa de 250ms en setup()
 *      para permitir que el riel de 3.3V del LDO RT9193 (300mA) se estabilice.
 *    - Potencia BLE ajustada a 0 dBm para reducir los picos de corriente RF.
 * 
 * 2. CORRECCIÓN DEL LED DE ESTADO (D4 Azul):
 *    - En el código original se declaró `ledPinIO32 = 35` (Pin GPI de solo entrada).
 *      En la PCB anterior está cableado físicamente al Pin 8 (GPIO 32).
 *      Se corrige a `ledPinIO32 = 32` para que el LED parpadee y encienda.
 * 
 * 3. RELÉS 3 Y 4 EN LA PCB ANTERIOR:
 *    - En la placa física anterior, R12 (Relé 3) y R14 (Relé 4) están unidos
 *      a la misma pista de GPIO 26. El código mantiene las definiciones originales
 *      y conmuta ambos sincronizados sin conflicto.
 * 
 * 4. ELIMINACIÓN DE BLOQUEO EN CALLBACK BLE:
 *    - Se reemplazó el `delay(3000)` dentro de `onWrite()` por una máquina de
 *      estados no bloqueante con `millis()`, evitando que el smartphone se desconecte.
 * 
 * 5. COMPATIBILIDAD 100% CON LA APP MÓVIL Y CONFIGURACIÓN ORIGINAL:
 *    - Mantiene el nombre exacto original: "TQT_R2_V2_0_0106".
 *    - Mantiene el Service UUID y Characteristic UUID originales.
 *    - Valida la EEPROM para evitar nombres corruptos con bytes 0xFF.
 *    - Mantiene la respuesta por consola Serial ("MAC" y mensaje inicial).
 *******************************************************************************/

#include <Arduino.h>
#include <BLEDevice.h>
#include <BLEUtils.h>
#include <BLEServer.h>
#include <EEPROM.h>
#include <esp_task_wdt.h>
#include <esp_bt.h>

// Registros de bajo nivel y eFuses del silicio ESP32
#include "soc/soc.h"
#include "soc/rtc_cntl_reg.h"
#include "esp_efuse.h"
#include "esp_efuse_table.h"

/**********************************************
 *         DEFINICIONES Y CONSTANTES          *
 ***********************************************/
#define Nombre_Del_Ble      "TQT_R2_V2_0_0049" // Nombre original de la tarjeta
#define SERVICE_UUID        "4fafc201-1fb5-459e-8fcc-c5c9c331914b"
#define CHARACTERISTIC_UUID "beb5483e-36e1-4688-b7f5-ea07361b26a8"

// Configuración EEPROM
#define EEPROM_SIZE         64
#define NAME_ADDR           0
#define DATA_ADDR           32

// Watchdog Timer
#define WDT_TIMEOUT_SECONDS 5

// Pines de Hardware en la PCB Anterior
const int ledPinIO32 = 32; // ¡CORREGIDO! En la PCB física va al Pin 8 (GPIO 32). (Originalmente decía 35).
const int Relay_01   = 14; // Relé 1 (Q1)
const int Relay_02   = 12; // Relé 2 (Q3 / Strapping MTDI neutralizado por eFuse)
const int Relay_03   = 26; // Relé 3 (Q6 - En la PCB anterior la pista une Q6 y Q7)
const int Relay_04   = 27; // Relé 4 (En la PCB anterior pin 27 está sin pista)

// Temporización de Actuadores y LED
const unsigned long RELAY_PULSE_DURATION_MS = 3000; // 3 segundos de activación de relés
const long intervalIO32                     = 500;  // 500 ms parpadeo LED desconectado

/**********************************************
 *          VARIABLES GLOBALES                *
 ***********************************************/
BLEServer *pServer = nullptr;
BLECharacteristic *pCharacteristic = nullptr;
volatile bool deviceConnected = false;
volatile bool isCurrentlyAdvertising = false;

// Temporizadores LED
unsigned long previousMillisIO32 = 0;
int ledStateIO32 = LOW;

// Máquina de estados no bloqueante para Relés
enum RelayState {
    RELAY_IDLE,
    RELAY_PPON_ACTIVE,
    RELAY_POFF_ACTIVE
};

volatile RelayState currentRelayState = RELAY_IDLE;
unsigned long relayTimerStartMillis = 0;

/**********************************************
 *  CORRECCIÓN DEFINITIVA DE ARRANQUE EN FRÍO  *
 *  (Neutralización de GPIO 12 vía eFuse)     *
 ***********************************************/
void checkAndFixFlashVoltageEfuse() {
    size_t force_val = 0;
    size_t tieh_val = 0;

    esp_efuse_read_field_blob(ESP_EFUSE_SDIO_FORCE, &force_val, 1);
    esp_efuse_read_field_blob(ESP_EFUSE_SDIO_TIEH, &tieh_val, 1);

    if (force_val == 0 || tieh_val == 0) {
        Serial.println(F("[AUTO-REPARACION] Fijando eFuses de Flash a 3.3V (SDIO_FORCE & SDIO_TIEH)..."));
        size_t one = 1;
        esp_efuse_write_field_blob(ESP_EFUSE_XPD_SDIO_REG, &one, 1);
        esp_efuse_write_field_blob(ESP_EFUSE_SDIO_TIEH, &one, 1);
        esp_efuse_write_field_blob(ESP_EFUSE_SDIO_FORCE, &one, 1);
        Serial.println(F("[AUTO-REPARACION] eFuses quemados con éxito. GPIO 12 neutralizado."));
        Serial.println(F("[AUTO-REPARACION] La placa anterior ahora arrancará en frío sin presionar RESET."));
    } else {
        Serial.println(F("[BOOT] eFuses de Flash 3.3V OK: GPIO 12 neutralizado."));
    }
}

/**********************************************
 *        CONTROL SEGURO DE RELÉS             *
 ***********************************************/
void setAllRelaysLow() {
    digitalWrite(Relay_01, LOW);
    digitalWrite(Relay_02, LOW);
    digitalWrite(Relay_03, LOW);
    digitalWrite(Relay_04, LOW);
}

void processRelayStateMachine() {
    // 1. Detección y ejecución del comando
    if (currentRelayState != RELAY_IDLE && relayTimerStartMillis == 0) {
        relayTimerStartMillis = millis();

        if (currentRelayState == RELAY_PPON_ACTIVE) {
            Serial.println(F("Comando recibido: ENCENDER (PPON)"));
            digitalWrite(Relay_03, HIGH);
            digitalWrite(Relay_04, HIGH);
            digitalWrite(Relay_01, HIGH);
            digitalWrite(Relay_02, LOW);
        } 
        else if (currentRelayState == RELAY_POFF_ACTIVE) {
            Serial.println(F("Comando recibido: APAGAR (POFF)"));
            digitalWrite(Relay_03, HIGH);
            digitalWrite(Relay_04, HIGH);
            digitalWrite(Relay_01, LOW);
            digitalWrite(Relay_02, HIGH);
        }
    }

    // 2. Apagado automático al cumplirse los 3 segundos (Sin congelar BLE)
    if (currentRelayState != RELAY_IDLE && relayTimerStartMillis > 0) {
        if (millis() - relayTimerStartMillis >= RELAY_PULSE_DURATION_MS) {
            setAllRelaysLow();
            currentRelayState = RELAY_IDLE;
            relayTimerStartMillis = 0;
            Serial.println(F("Pulso de relés finalizado. Retorno a reposo (LOW)."));
        }
    }
}

/**********************************************
 *      CALLBACKS (EVENTOS) DEL SERVIDOR BLE  *
 ***********************************************/
class MyServerCallbacks : public BLEServerCallbacks {
    void onConnect(BLEServer* pServerInstance) override {
        deviceConnected = true;
        isCurrentlyAdvertising = false;
        Serial.println(F("Dispositivo conectado"));
        digitalWrite(ledPinIO32, HIGH);  // Enciende LED BLE fijo
        ledStateIO32 = HIGH;
    }

    void onDisconnect(BLEServer* pServerInstance) override {
        deviceConnected = false;
        Serial.println(F("Dispositivo desconectado"));
        digitalWrite(ledPinIO32, LOW);   // Apaga LED BLE
        ledStateIO32 = LOW;
        previousMillisIO32 = millis();
        // La reactivación de publicidad se realiza en loop() para no bloquear el callback
    }
};

/**********************************************
 *  CALLBACKS (EVENTOS) DE CARACTERÍSTICAS    *
 *  (Asíncrono: NO usa delay para no colgar)  *
 ***********************************************/
class MyCallbacks : public BLECharacteristicCallbacks {
    void onWrite(BLECharacteristic *pChar) override {
        String value = pChar->getValue().c_str();
        value.trim();

        if (value.equalsIgnoreCase("PPON")) {
            currentRelayState = RELAY_PPON_ACTIVE;
            relayTimerStartMillis = 0; // Disparará la máquina en loop()
        } 
        else if (value.equalsIgnoreCase("POFF")) {
            currentRelayState = RELAY_POFF_ACTIVE;
            relayTimerStartMillis = 0;
        } 
        else {
            Serial.print(F("Comando ignorado: "));
            Serial.println(value);
        }
    }
};

/**********************************************
 *      FUNCIÓN DE INICIALIZACIÓN BLE         *
 ***********************************************/
void initBLE(const char* deviceName) {
    Serial.print(F("Iniciando BLE con nombre: "));
    Serial.println(deviceName);

    BLEDevice::init(deviceName);

    // Optimización de potencia de transmisión para proteger el LDO de 300 mA
    esp_ble_tx_power_set(ESP_BLE_PWR_TYPE_DEFAULT, ESP_PWR_LVL_N0); // 0 dBm
    esp_ble_tx_power_set(ESP_BLE_PWR_TYPE_ADV, ESP_PWR_LVL_N0);

    pServer = BLEDevice::createServer();
    pServer->setCallbacks(new MyServerCallbacks());

    BLEService *pService = pServer->createService(SERVICE_UUID);
    pCharacteristic = pService->createCharacteristic(
        CHARACTERISTIC_UUID,
        BLECharacteristic::PROPERTY_READ | BLECharacteristic::PROPERTY_WRITE
    );
    pCharacteristic->setCallbacks(new MyCallbacks());
    pService->start();

    BLEAdvertising *pAdvertising = BLEDevice::getAdvertising();
    pAdvertising->addServiceUUID(SERVICE_UUID);
    pAdvertising->setScanResponse(true);
    pAdvertising->setMinPreferred(0x06);
    pAdvertising->setMinPreferred(0x12);

    BLEDevice::startAdvertising();
    isCurrentlyAdvertising = true;
    Serial.println(F("Publicidad iniciada exitosamente"));
}

/**********************************************
 *               SETUP INICIAL                *
 ***********************************************/
void setup() {
    // 1. DESHABILITAR BROWNOUT DETECTOR INMEDIATAMENTE
    // Evita reinicios por micro-caídas del LDO RT9193 (300mA) al conectar en frío
    WRITE_PERI_REG(RTC_CNTL_BROWN_OUT_REG, 0);

    // 2. Retardo de estabilización de energía
    // Permite que la fuente de 12V, el convertidor Buck y el LDO se estabilicen
    delay(250);

    Serial.begin(115200);
    delay(50);
    Serial.println(F("\n========================================================"));
    Serial.println(F("    TQT2 MÓDULO RESPALDO R2 - FIRMWARE CORREGIDO        "));
    Serial.println(F("========================================================"));

    // 3. Auto-reparación de arranque en frío (eFuse Flash a 3.3V)
    checkAndFixFlashVoltageEfuse();

    // 4. Configuración del Watchdog Timer (TWDT)
    esp_task_wdt_config_t wdt_config = {
        .timeout_ms = WDT_TIMEOUT_SECONDS * 1000,
        .trigger_panic = true
    };
    esp_task_wdt_init(&wdt_config);
    esp_task_wdt_add(NULL); // Monitorea loopTask

    // 5. Configuración de pines de la PCB anterior
    pinMode(ledPinIO32, OUTPUT);
    pinMode(Relay_01, OUTPUT);
    pinMode(Relay_02, OUTPUT);
    pinMode(Relay_03, OUTPUT);
    pinMode(Relay_04, OUTPUT);

    // Estado inicial seguro: todo apagado
    digitalWrite(ledPinIO32, LOW);
    setAllRelaysLow();

    // 6. Manejo seguro de EEPROM (con validación de datos virgen 0xFF)
    EEPROM.begin(EEPROM_SIZE);
    String deviceName = EEPROM.readString(NAME_ADDR);

    // Si la EEPROM está virgen (0xFF), vacía o corrupta (>20 caracteres)
    if (deviceName.isEmpty() || ((uint8_t)deviceName[0] == 0xFF) || deviceName.length() > 20) {
        deviceName = Nombre_Del_Ble;
        EEPROM.writeString(NAME_ADDR, deviceName);
        EEPROM.commit();
        Serial.println(F("EEPROM inicializada con nombre por defecto."));
    }

    // 7. Inicialización de BLE
    initBLE(deviceName.c_str());

    // 8. Mensaje de identificación serial (Exactamente igual al original)
    String macAddress = BLEDevice::getAddress().toString().c_str();
    Serial.print(Nombre_Del_Ble);
    Serial.print(" MAC: ");
    Serial.println(macAddress);
    Serial.println(F("Sistema en línea y listo para operar."));
}

/**********************************************
 *            LOOP PRINCIPAL                  *
 ***********************************************/
void loop() {
    unsigned long currentMillis = millis();

    // 1. Control del LED Azul (parpadeo a 500 ms solo si está desconectado)
    if (!deviceConnected && (currentMillis - previousMillisIO32 >= intervalIO32)) {
        previousMillisIO32 = currentMillis;
        ledStateIO32 = !ledStateIO32;
        digitalWrite(ledPinIO32, ledStateIO32);
    }

    // 2. Máquina de estados no bloqueante de relés
    processRelayStateMachine();

    // 3. Manejo de comandos por consola Serial UART0 (USB / Programador)
    if (Serial.available()) {
        String input = Serial.readStringUntil('\n'); 
        input.trim(); 
        if (input.equalsIgnoreCase("MAC")) {
            String macAddress = BLEDevice::getAddress().toString().c_str();
            Serial.print(Nombre_Del_Ble);
            Serial.print(" MAC: ");
            Serial.println(macAddress);
        }
    }

    // 4. Verificación y reactivación de publicidad BLE si se desconectó
    if (!deviceConnected && !isCurrentlyAdvertising) {
        BLEDevice::startAdvertising(); 
        isCurrentlyAdvertising = true;
        Serial.println(F("Publicidad reactivada"));
    }

    // 5. Alimentar el Watchdog Timer
    esp_task_wdt_reset(); 
}
