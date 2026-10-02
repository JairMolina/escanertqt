/**********************************************
*                LIBRERÍAS                   *
***********************************************/
#include <BLEDevice.h>      // Gestión básica de dispositivos BLE
#include <BLEUtils.h>       // Utilidades y helpers para BLE
#include <BLEServer.h>      // Funcionalidad de servidor BLE
#include <EEPROM.h>         // Manejo de memoria no volátil
#include <esp_task_wdt.h>   // Watchdog Timer (reinicio automático)
/***
///https://lastminuteengineers.com/esp32-arduino-ide-tutorial/
///https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json 
///ESP32 by Espressif Systems.
///DOIT ESP32 DEVKIT V1
***///
/**********************************************
*         DEFINICIONES Y CONSTANTES          *
***********************************************/
#define SERVICE_UUID        "4fafc201-1fb5-459e-8fcc-c5c9c331914b" // UUID único para el servicio BLE
#define CHARACTERISTIC_UUID "beb5483e-36e1-4688-b7f5-ea07361b26a8" // UUID único para la característica BLE
// Configuración EEPROM
#define EEPROM_SIZE 64      // Tamaño reservado para la EEPROM
#define NAME_ADDR 0         // Dirección de memoria para guardar el nombre BLE
#define DATA_ADDR 32        // Dirección de memoria para datos adicionales
// Watchdog Timer
#define WDT_TIMEOUT 5       // Tiempo máximo de bloqueo permitido (segundos)
#define WDT_TIMEOUT_MS 5000  // 5 segundos en milisegundos
// Configuración de Hardware

#define RX2_PIN 16          // Pin RX para UART2 - ORIGINAL
#define TX2_PIN 17          // Pin TX para UART2 - ORIGINAL

/*
#define RX2_PIN 17          // Pin RX para UART2
#define TX2_PIN 16          // Pin TX para UART2
//*/
#define SERIAL2_BAUD_RATE 115200 // Velocidad comunicación serial
/**********************************************
*          VARIABLES GLOBALES                *
***********************************************/
// BLE
BLEServer *pServer = nullptr;               // Instancia del servidor BLE
BLECharacteristic *pCharacteristic = nullptr; // Característica BLE
bool deviceConnected = false;               // Estado de conexión BLE
bool isCurrentlyAdvertising = false;        // Estado de publicidad BLE
// LEDs
const int ledPinIO2 = 2;     // Pin para LED de estado general
const int ledPinIO32 = 32;   // Pin para LED de estado BLE
// Temporizadores
unsigned long previousMillisIO2 = 0;  // Último tiempo de cambio LED IO2
const long intervalIO2 = 500;         // Intervalo parpadeo LED IO2 (ms)
int ledStateIO2 = LOW;                // Estado actual LED IO2
unsigned long previousMillisIO32 = 0; // Último tiempo de cambio LED IO32
const long intervalIO32 = 500;        // Intervalo parpadeo LED IO32 (ms)
int ledStateIO32 = LOW;               // Estado actual LED IO32
/**********************************************
*      CALLBACKS (EVENTOS) DEL SERVIDOR BLE   *
***********************************************/
class MyServerCallbacks : public BLEServerCallbacks {
    void onConnect(BLEServer* pServerInstance) {
        deviceConnected = true;          // Actualiza estado de conexión
        isCurrentlyAdvertising = false;  // Detiene la publicidad
        Serial.println("Dispositivo conectado");
        digitalWrite(ledPinIO32, HIGH);  // Enciende LED BLE
        ledStateIO32 = HIGH;             // Actualiza estado LED
    }

    void onDisconnect(BLEServer* pServerInstance) {
        deviceConnected = false;         // Actualiza estado de conexión
        Serial.println("Dispositivo desconectado");
        digitalWrite(ledPinIO32, LOW);   // Apaga LED BLE
        ledStateIO32 = LOW;              // Actualiza estado LED
        previousMillisIO32 = millis();   // Reinicia temporizador
        BLEDevice::startAdvertising();   // Reactiva publicidad
        isCurrentlyAdvertising = true;   // Actualiza estado publicidad
        Serial.println("Publicidad reiniciada");
    }
};
/**********************************************
*  CALLBACKS (EVENTOS) DE CARACTERÍSTICAS BLE *
***********************************************/

class MyCallbacks : public BLECharacteristicCallbacks {
    void onWrite(BLECharacteristic *pCharacteristic) {
        esp_task_wdt_reset();
        String value = pCharacteristic->getValue();  // Lee datos recibidos
        if (value.length() == 4) {       // Verifica longitud correcta
            Serial2.println(value);      // Reenvía datos por UART2
            Serial.println(value);      // Reenvía datos por UART2
        } else {
            Serial.println("Error: se esperaban 4 caracteres");
        }
    }
};
/**********************************************
*      FUNCIÓN DE INICIALIZACIÓN BLE         *
***********************************************/
void initBLE(const char* deviceName) {
    BLEDevice::init(deviceName);         // Inicializa dispositivo BLE
    pServer = BLEDevice::createServer(); // Crea instancia de servidor
    pServer->setCallbacks(new MyServerCallbacks()); // Asigna callbacks
    BLEService *pService = pServer->createService(SERVICE_UUID); // Crea servicio++
    pCharacteristic = pService->createCharacteristic( // Crea característica
        CHARACTERISTIC_UUID,
        BLECharacteristic::PROPERTY_READ | // Configura permisos
        BLECharacteristic::PROPERTY_WRITE
    );
    pCharacteristic->setCallbacks(new MyCallbacks()); // Asigna callbacks
    pService->start(); // Inicia servicio
    BLEAdvertising *pAdvertising = BLEDevice::getAdvertising(); // Configura publicidad
    pAdvertising->addServiceUUID(SERVICE_UUID); // Añade UUID del servicio
    pAdvertising->setScanResponse(true);       // Habilita respuesta a escaneos
    pAdvertising->setMinPreferred(0x06);       // Parámetros de conexión
    pAdvertising->setMinPreferred(0x12);
    BLEDevice::startAdvertising();      // Inicia publicidad
    isCurrentlyAdvertising = true;      // Actualiza estado
}
/**********************************************
*               SETUP INICIAL                *
***********************************************/
void setup() {
    Serial.begin(115200); // Inicia comunicación serial con PC
    // Configuración Watchdog
    esp_task_wdt_config_t wdt_config = {
        .timeout_ms = 5000,    // 5 segundos en milisegundos
        .trigger_panic = true   // Reiniciar en lugar de solo notificar
    };
    esp_task_wdt_init(&wdt_config); // Inicializa con estructura de configuración
    esp_task_wdt_add(NULL);         // Añade tarea actual
    EEPROM.begin(EEPROM_SIZE); // Inicializa EEPROM
    // Carga nombre guardado o usa uno por defecto
    String deviceName = EEPROM.readString(NAME_ADDR);
    if (deviceName.isEmpty()) {
        deviceName = "TQT_V1.0_XXX";
        EEPROM.writeString(NAME_ADDR, deviceName);
        EEPROM.commit(); // Guarda en memoria no volátil
    }
    // Configuración de pines LED
    pinMode(ledPinIO2, OUTPUT);
    pinMode(ledPinIO32, OUTPUT);
    digitalWrite(ledPinIO2, LOW);  // Estado inicial LED IO2
    digitalWrite(ledPinIO32, LOW); // Estado inicial LED IO32
    Serial.println("Iniciando BLE...");
    initBLE(deviceName.c_str()); // Inicializa BLE con nombre
    delay(100);
    Serial2.begin(SERIAL2_BAUD_RATE, SERIAL_8N1, RX2_PIN, TX2_PIN); // Inicia UART2
    delay(100);
    String macAddress = BLEDevice::getAddress().toString().c_str();
    Serial.print("Dirección MAC: ");
    Serial.println(macAddress);
}
/**********************************************
*            LOOP PRINCIPAL                  *
***********************************************/
void loop() {
    unsigned long currentMillis = millis(); // Tiempo actual
    // 1. Reset del Watchdog - Mantiene vivo al sistema
    esp_task_wdt_reset();
    // Control LED IO2 (parpadeo constante)
    if (currentMillis - previousMillisIO2 >= intervalIO2) {
        previousMillisIO2 = currentMillis;
        ledStateIO2 = !ledStateIO2; // Cambia estado
        digitalWrite(ledPinIO2, ledStateIO2); // Actualiza LED
    }
    // Control LED IO32 (parpadeo solo si desconectado)
    if (!deviceConnected && (currentMillis - previousMillisIO32 >= intervalIO32)) {
        previousMillisIO32 = currentMillis;
        ledStateIO32 = !ledStateIO32;
        digitalWrite(ledPinIO32, ledStateIO32);
    }
    // 2. Reset del Watchdog - Antes de procesar serial
    esp_task_wdt_reset();
    // Manejo de comandos por UART2
    if (Serial2.available()) {
        String input = Serial2.readStringUntil('\n'); // Lee hasta salto de línea
        input.trim(); // Elimina espacios y caracteres especiales
        // Comando para cambiar nombre BLE
        if (input.startsWith("NAME:")) {
            //esp_task_wdt_reset();
            String newName = input.substring(5); // Extrae nuevo nombre
            if (newName.length() > 0) {
                EEPROM.writeString(NAME_ADDR, newName); // Escribe en EEPROM
                if (EEPROM.commit()) { // Confirma escritura
                    BLEDevice::deinit(); // Detiene BLE
                    Serial2.println("OK");
                    Serial.print("Nombre actualizado: ");
                    Serial.println(newName);
                    ESP.restart();
                }
                else Serial2.println("ERROR");
            }
        }
        // Comando para Saber si esta funcionando
        else if (input.equalsIgnoreCase("VIVO")) {
            Serial2.println("SIMON");
            Serial.println("SIMON");
        }
        // Comando para obtener la MAC del BLE
        else if (input.equalsIgnoreCase("MAC")) {
            String macAddress = BLEDevice::getAddress().toString().c_str();
            Serial2.println(macAddress);
            Serial.print("Dirección MAC: ");
            Serial.println(macAddress);
        }
        // Comando de reinicio manual
        else if (input.equalsIgnoreCase("RESET")) { 
            Serial2.println("OK");
            Serial.println("Iniciando reset por software...");
            delay(100);
            ESP.restart(); // Reinicio controlado
        }
        // Comando de prueba de Watchdog
        else if (input.equalsIgnoreCase("BLOQUEAR")) {
            Serial2.println("OK");
            Serial.println("Simulación de bloqueo...");
            while(true) { // Bloqueo infinito intencional
                // El Watchdog reiniciará el sistema después de WDT_TIMEOUT segundos
            }
        }
        // Cualquier otro dato recibido
        else { 
            Serial.print("Dato serial 2: "); 
            Serial.println(input);
            Serial2.println("ERROR");
            //esp_task_wdt_reset();
            // Podría añadirse lógica adicional aquí
        }
        // 3. Reset del Watchdog - Después de procesar
        esp_task_wdt_reset();
    }
    // 4. Reset del Watchdog - Antes de verificar publicidad
    //esp_task_wdt_reset();
    // Verificación de estado de publicidad BLE
    if (!deviceConnected && !isCurrentlyAdvertising) {
        BLEDevice::startAdvertising(); // Reactiva publicidad si es necesario
        isCurrentlyAdvertising = true;
    }
    // 5. Reset final del Watchdog - Fin del ciclo
    esp_task_wdt_reset();
}
