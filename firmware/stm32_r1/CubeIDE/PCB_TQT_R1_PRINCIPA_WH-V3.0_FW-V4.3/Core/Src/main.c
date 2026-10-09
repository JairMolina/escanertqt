/* USER CODE BEGIN Header */
/// Titulo del programa   : TQT_XXX
/// Descripción           : Programa principal PCB TQT R1
/// Autor                 : Leonardo Miguel Rivera García
/// Fecha                 : 25/06/2025
/// versión del programa  : 1.0
/// notes                 : FINAL ya cuenta con la salida de pin para el equipo,
///                         tambien con el auto reset y reset por plataforma
/* USER CODE END Header */
/* Includes ------------------------------------------------------------------*/
#include "main.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */
#include <string.h>				// Libreria para manejo de cadena de datos
#include <stdio.h>				// Libreria para manejar mensanjes
#include <stdbool.h>			// Libreria para manejar boolianos
#include <stdlib.h>

#include "tqt_identity.h"
#include "tqt_identity_fault.h"
#define Nombre_Tarjeta_Fijo (TQT_IdentityGet()->name)
#define ID_R (TQT_IdentityGet()->id_r)
#define MAC_R (TQT_IdentityGet()->mac_r)
#define VER (TQT_IdentityGet()->fw)
#define HW (TQT_IdentityGet()->hw)
#define MODO_DEBUG 0
// --- DEFINICIÓN DE ESTADOS ---
#define UMBRAL_SENSOR 2480
// INT_1/INT_2: histeresis independiente de los limitadores (VDDA nominal 3.3 V).
#define ADC_ENTRADA_BAJO 2233U   // <= 1.8 V: nivel electrico 0
#define ADC_ENTRADA_ALTO 2482U   // >= 2.0 V: nivel electrico 1
#define ADC_LECTURAS 5U         // PA0, PA1, PA2, PB0, PB1
#define Rango_Viva		1
#define Rango_Bloqueo   4
#define Rango_Motor     4
#define Rango_Int01     3
#define Rango_Int02     3
#define Rango_Int03     3
#define Rango_Out01     3
#define Rango_Out02     3
#define Rango_Out03     3
#define Rango_Tiempo    10
#define Default_Int1    0
#define Default_Int2    0
#define Default_Int3    0
#define Default_Out1    0
#define Default_Out2    0
#define Default_Out3    0
#define Default_Bloqueo 0
#define Default_Motor   0
#define Default_Viva	0
#define Default_Reset   0
#define Default_S_ON    0
#define Default_S_OFF   0
#define Default_Error   0
#define Default_Sensores 0
#define Default_SPAS    '|'
#define Default_SPAV    ';'
#define Default_DBG     0
#define Default_Tiempo  0
#define Default_MapM1   0
#define Default_MapM2   0
#define ESTADO_ESPERA	0
#define ESTADO_ABRIENDO 1
#define ESTADO_ABIERTO  2
#define ESTADO_CERRANDO 3
#define ESTADO_CERRADO  4
#define ESTADO_ERROR    5
#define Tiempo_Espera	5000
#define Tiempo_es_mem	3000
#define Tiempo_Motor_Base 4000UL
// =========================================================
#define IDX_SENSOR_APERTURA  ((Config.MapM2 == 1) ? 4U : 2U)
#define IDX_SENSOR_CIERRE    ((Config.MapM1 == 1) ? 3U : 1U)
#define IDX_ENTRADA_1        ((Config.MapM1 == 1) ? 1U : 3U)
#define IDX_ENTRADA_2        ((Config.MapM2 == 1) ? 2U : 4U)
#define MOTOR_ACCION_ABRIR()   { RELAY_1_ON; RELAY_2_OFF;}
#define MOTOR_ACCION_CERRAR()  { RELAY_2_ON; RELAY_1_OFF; }
#define MOTOR_APAGAR_TODO()    { RELAY_1_OFF; RELAY_2_OFF; }
#define ADC_OFFSET      3300   // ajusta a tu valor real (≈2.5V)
// =========================================================
// =========== ADC DEFAULTS limite de corriente ============
#define ADC_5A_DELTA    380
#define ADC_8A_DELTA    620
#define ADC_10A_DELTA   780
// =========================================================
#define RS_485_Leer HAL_GPIO_WritePin(GPIOC, RE_DE_Pin, GPIO_PIN_RESET)
#define RS_485_Escribir HAL_GPIO_WritePin(GPIOC, RE_DE_Pin, GPIO_PIN_SET)
/// ------------------------------------------------------------------------------------- Atrack
#define ENCABEZADO		"AT$POST=1,0,\""
//#define BLUE			"Bluetooth"
//#define PLAT			"Plataforma"
#define PLAT			1
#define BLUE			2
#define OPEN 			" - desbloqueado por "
#define CLOSED	 		" - bloqueado por "
#define OPEN_1 			" - solicitud de desbloqueo por "
#define CLOSED_1 		" - solicitud de bloqueo por "
#define ERROR_O			" - error al abrir por "
#define ERROR_C			" - error al cerrar por "
#define ERROR_1			" - error comando por medio de "
#define FIN_ENCBEZADO	"\"\r\n"
/// ------------------------------------------------------------------------------------- FIN Atrack
/// ------------------------------------------------------------------------------------- Relay's
#define RELAY_1_ON	HAL_GPIO_WritePin(GPIOA,R_1_Pin, GPIO_PIN_SET )
#define RELAY_1_OFF	HAL_GPIO_WritePin(GPIOA,R_1_Pin, GPIO_PIN_RESET )
#define RELAY_2_ON	HAL_GPIO_WritePin(GPIOA,R_2_Pin, GPIO_PIN_SET )
#define RELAY_2_OFF	HAL_GPIO_WritePin(GPIOA,R_2_Pin, GPIO_PIN_RESET )
/// ------------------------------------------------------------------------------------- Relay's Fin
/// ------------------------------------------------------------------------------------- Led's RGB
#define LED_R_ON	HAL_GPIO_WritePin(GPIOC,LED_R_Pin, GPIO_PIN_SET )
#define LED_R_OFF	HAL_GPIO_WritePin(GPIOC,LED_R_Pin, GPIO_PIN_RESET )
#define LED_G_ON	HAL_GPIO_WritePin(GPIOC,LED_G_Pin, GPIO_PIN_SET )
#define LED_G_OFF	HAL_GPIO_WritePin(GPIOC,LED_G_Pin, GPIO_PIN_RESET )
#define LED_B_ON	HAL_GPIO_WritePin(GPIOC,LED_B_Pin, GPIO_PIN_SET )
#define LED_B_OFF	HAL_GPIO_WritePin(GPIOC,LED_B_Pin, GPIO_PIN_RESET )
/// ------------------------------------------------------------------------------------- Led's RGB FIN
/// ------------------------------------------------------------------------------------- BLE
#define BLE_01_ON	HAL_GPIO_WritePin(GPIOA,ESP_ENABLE_Pin, GPIO_PIN_SET )
#define BLE_01_OFF	HAL_GPIO_WritePin(GPIOA,ESP_ENABLE_Pin, GPIO_PIN_RESET )
#define EEPROM_I2C_ADDR 		0xA0		// Direccion de la eeprom
#define EEPROM_CONFIG_ADDR		0x0000
#define VERSION_ACTUAL      	6
#define VERSION_SIN_MAP         5
#define VERSION_ANTERIOR    	4
#define VERSION_COMPATIBLE_ANTERIOR 3
#define VERSION_COMPATIBLE_ANTERIOR_2 2
#define MAX_NOMBRE_LEN      	22
#define TQT_XXX             	Nombre_Tarjeta_Fijo
#define DEBOUNCE_TIME 2  // ms, suficiente si hay filtro RC físico
#define INDIC_ON	HAL_GPIO_WritePin(GPIOB,INDICADOR_BLOQUEO_Pin, GPIO_PIN_SET )
#define INDIC_OFF	HAL_GPIO_WritePin(GPIOB,INDICADOR_BLOQUEO_Pin, GPIO_PIN_RESET )
/// ------------------------------------------------------------------------------------- Indicador de bloqueo y desbloque Fin
#define RX_BUFFER_SIZE 256
#define TX_BUFFER_SIZE 320
#define GPS_MSG_QUEUE_SIZE 40
#define GPS_MSG_MAX_LEN 320
#define GPS_ACK_TIMEOUT 1500
#define GPS_MAX_REINTENTOS 4
/// ------------------------------------------------------------------------------------- BLE FIN
/* USER CODE END Includes */
/* Private typedef -----------------------------------------------------------*/
/* USER CODE BEGIN PTD */
// =================== CONFIGURACION =======================
#pragma pack(push,1)
typedef struct
{
	uint16_t Version;					// VERSION
	char Nombre[MAX_NOMBRE_LEN + 1];	//
	uint8_t  Int1;						// ENTRADA 1
	uint8_t  Int2;						// ENTRADA 2
	uint8_t  Int3;						// ENTRADA 3
	uint8_t  Out1;						// SALIDA  1
	uint8_t  Out2;						// SALIDA  2
	uint8_t  Out3;						// SALIDA  3
	uint8_t  Bloqueo;					//
	uint8_t  Motor;						// Se lleva el valor para saber cual sera el limite de corriente de proteccion 5A, 8A, 10A o nulo
	uint8_t  Viva;						//
	uint8_t  S_ON;						//
	uint8_t  S_OFF;						//
	uint8_t  Error;						//
	uint16_t  Reset;					// Se lleva la cuenta de cada vez que se reinicia o arranca la tarjeta para saber cuantas veces se usaron
	uint32_t MovMotor;					// Cuenta las veces que el motor se activa para abrir o cerrar
	uint8_t  Sensores;					// 0 usa sensores de motor, 1 ignora sensores de motor y trabaja por tiempo
	char SeparadorSensores;				// Separador entre sensores en la trama S#
	char SeparadorValor;				// Separador entre sensor y valor
	uint8_t DebugTqt;					// 0 envia sensores TQT, 1 envia mensajes de debug TQT
	uint8_t Tiempo;						// Segundos extra para esperar sensores de apertura/cierre
    uint8_t MapM1;                         // 0: motor PA1 / INT_1 PB0; 1: intercambiados
    uint8_t MapM2;                         // 0: motor PA2 / INT_2 PB1; 1: intercambiados
} CONFIG_TQT;
#pragma pack(pop)

typedef struct
{
	char texto[GPS_MSG_MAX_LEN];
	uint32_t numero;
	uint8_t actualiza_mensaje;
} GPS_MSG_T;
// =========================================================
// ================= VARIABLE GLOBAL =======================
// =========================================================
CONFIG_TQT Config;
char buffer[TX_BUFFER_SIZE];
GPS_MSG_T gpsCola[GPS_MSG_QUEUE_SIZE];
char gpsMensajeActual[GPS_MSG_MAX_LEN];
char gpsMensajeSalida[GPS_MSG_MAX_LEN];
uint32_t gpsConsecutivoMensaje = 0;
uint32_t gpsNumeroActual = 0;
uint8_t gpsColaLectura = 0;
uint8_t gpsColaEscritura = 0;
uint8_t gpsColaCantidad = 0;
uint8_t gpsMensajeActivo = 0;
uint8_t gpsActualizaMensaje = 0;
uint8_t gpsReintentos = 0;
uint8_t gpsAckRecibido = 0;
uint16_t gpsMensajesDescartados = 0;
uint32_t gpsTiempoEnvio = 0;
/// ------------------------------------------------------------------------------------- Pines
GPIO_PinState INT_01; 		// Estado actual de entrada del pin 1
GPIO_PinState INT_02; 		// Estado actual de entrada del pin 2
GPIO_PinState INT_03; 		// Estado actual de entrada del pin 3
GPIO_PinState INT_01_ANT = GPIO_PIN_SET; // Estado inicial del pin1
GPIO_PinState INT_02_ANT = GPIO_PIN_SET; // Estado inicial del pin2
GPIO_PinState INT_03_ANT = GPIO_PIN_SET; // Estado inicial del pin3
//GPIO_PinState O_C;			// Valor para saber si es apertura o cierre (roberto)
GPIO_PinState Out_01;		// Para saber el estado del bloqueo o desbloqueo de la salida 1
GPIO_PinState Out_02;		// Para saber el estado del bloqueo o desbloqueo de la salida 2
GPIO_PinState Int_02;		// Para si activaron la entrada
GPIO_PinState INT_S2; 		// Estado actual de entrada del pin 2
GPIO_PinState INT_S2_ANT = GPIO_PIN_SET;; 		// Estado actual de entrada del pin 2
uint32_t timeoutINTS = 0;		// Para llevar la cuenta del mensaje
GPIO_PinState Int_01;		// Para si activaron la entrada
GPIO_PinState INT_S1; 		// Estado actual de entrada del pin 1
GPIO_PinState INT_S1_ANT = GPIO_PIN_SET;; 		// Estado actual de entrada del pin 1
uint8_t stableCount1 = 0;
uint8_t stableCount2 = 0;
GPIO_PinState nivel_entrada_1 = GPIO_PIN_SET;
GPIO_PinState nivel_entrada_2 = GPIO_PIN_SET;
uint8_t stableCount3 = 0;
GPIO_PinState INT_S3; 		// Estado actual de entrada del pin 1
GPIO_PinState INT_S3_ANT = GPIO_PIN_SET;; 		// Estado actual de entrada del pin 1
/// ------------------------------------------------------------------------------------- Pines Fin
/// ------------------------------------------------------------------------------------- Led's RGB Fin
/// ------------------------------------------------------------------------------------- Indicador de bloqueo y desbloque
uint8_t rxBuffer1[RX_BUFFER_SIZE];
volatile uint16_t rxWriteIndex1 = 0;
volatile uint16_t rxReadIndex1 = 0;

uint8_t rxBuffer4[RX_BUFFER_SIZE];
volatile uint16_t rxWriteIndex4 = 0;
volatile uint16_t rxReadIndex4 = 0;

uint8_t rxBuffer5[RX_BUFFER_SIZE];
volatile uint16_t rxWriteIndex5 = 0;
volatile uint16_t rxReadIndex5 = 0;
/// -------------------------------------------------------------------------------------Fin serial
/// -------------------------------------------------------------------------------------Atrack
char SKY_COMD[100];      	// Se guarda el dato de la plataforma
char SKY_COMD_Debug[100];      	// Se guarda el dato de la plataforma
uint16_t  CS = 0;			// Se lleva contador para ingrementar donde se guarda el mensaje
uint16_t  CS_DBG = 0;       // Contador para los datos del UART Debug
uint32_t timeoutSKY = 0;	// Se lleva la cuenta
uint32_t timeoutDBG = 0;	// Se lleva la cuenta
bool esperandoSKY = false;	// Bandera para saber si aun esperamos o no
bool esperandoDBG = false;	// Bandera para saber si aun esperamos o no
/// -------------------------------------------------------------------------------------Fin Atrack
/// -------------------------------------------------------------------------------------Bluetooth
char BLE_COMD[100];		// Se guarda el dato de la plataforma
uint16_t  CB = 0;		// Se lleva contador para ingrementar donde se guarda el mensaje
int8_t  LL = 0;  // Variable para llevar la cuenta del BLE
uint32_t timeoutBLE = 0;		// Para llevar la cuenta del mensaje
bool esperandoBLE = false;		// Bandera para saber si aun esperamos o no

char MAC_BLE[18];
uint32_t timeoutVIVA = 0;		// Para llevar la cuenta del mensaje
uint32_t timeoutError = 0;		// Para limpiar el error despues de un tiempo
uint32_t timeoutBleV = 0;		// Para llevar la cuenta del mensaje
int8_t    Res_Gps_Ble = 0;		// Se lleva contador para ingrementar donde se guarda el mensaje

volatile uint8_t flag_sobrecorriente = 0;
uint32_t tiempo_bajo_corriente = 0;
static uint16_t filtro_adc = 0;
//bool esperandoVIVA = false;		// Bandera para saber si aun esperamos o no
/// -------------------------------------------------------------------------------------Fin Bluetooth
/* USER CODE END PTD */

/* Private define ------------------------------------------------------------*/
/* USER CODE BEGIN PD */

/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */
volatile uint8_t Estado_Sensor_01;
volatile uint16_t mis_lecturas_adc[ADC_LECTURAS];
volatile uint8_t etapa_apertura = 0; // <--- ESTA ES LA QUE USAREMOS AHORA
volatile uint8_t etapa_cierre = 0;

// --- VARIABLES GLOBALES ---
volatile uint8_t estado_actual_motor = ESTADO_ESPERA;
volatile uint8_t bandera_limite_alcanzado = 0;
uint8_t memoria_sensor_1 = 0;
uint8_t memoria_sensor_2 = 0;
uint8_t P_B = 0;
volatile uint32_t errores_pendientes = 0;

uint16_t ADC_DELTA = ADC_5A_DELTA;
// =========================================================
/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/
ADC_HandleTypeDef hadc1;
DMA_HandleTypeDef hdma_adc1;

CRC_HandleTypeDef hcrc;

I2C_HandleTypeDef hi2c1;
I2C_HandleTypeDef hi2c2;

IWDG_HandleTypeDef hiwdg;

TIM_HandleTypeDef htim2;
TIM_HandleTypeDef htim3;
TIM_HandleTypeDef htim4;

UART_HandleTypeDef huart4;
UART_HandleTypeDef huart5;
UART_HandleTypeDef huart1;

volatile uint16_t adc_debug[3];
volatile uint8_t flag_adc_debug = 0;
uint32_t tiempo_sobrecorriente_inicio = 0;
uint8_t sobrecorriente_confirmada = 0;
/* USER CODE BEGIN PV */

/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
void SystemClock_Config(void);
static void MX_GPIO_Init(void);
static void MX_DMA_Init(void);
static void MX_UART5_Init(void);
static void MX_I2C1_Init(void);
static void MX_USART1_UART_Init(void);
static void MX_TIM2_Init(void);
static void MX_UART4_Init(void);
static void MX_CRC_Init(void);
static void MX_IWDG_Init(void);
static void MX_I2C2_Init(void);
static void MX_ADC1_Init(void);
static void MX_TIM3_Init(void);
static void MX_TIM4_Init(void);
/* USER CODE BEGIN PFP */

/* USER CODE END PFP */

/* Private user code ---------------------------------------------------------*/
/* USER CODE BEGIN 0 */
void TIM2_Start(void);					// Timer 2 se activa
void TIM3_Start(void);					// Timer 3 se activa
void Serial_BLE(const char *string);	// Se manda mensaje al Bluetooth
void Serial_GPS(const char *string);	// Se manda mensaje al GPS
void Serial_GPS_Directo(const char *string);
void GPS_EncolarMensaje(const char *string);
uint8_t GPS_DesencolarMensaje(char *destino, uint32_t *numero, uint8_t *actualiza_mensaje);
void GPS_ActualizarCampoMensaje(const char *origen, char *destino, uint32_t numero, uint8_t intento);
void GPS_EnviarMensajeActual(void);
void GPS_ProcesarCola(void);
void GPS_MensajeConfirmado(void);
void Debug(const char *string);	// Se manda mensaje al Bluetooth
void ProcessSerialData1(void);			// Se lee el serial 1
int  UART_ReadByte1(void);
void StartUARTReceiveIT1(void);			// aqui se inicia la interrupcion del serial 1
void StartUARTReceiveIT4(void);			// aqui se inicia la interrupcion del serial 4
void StartUARTReceiveIT5(void);			// aqui se inicia la interrupcion del serial 5
void BT_DELAY(void);
void HAL_UART_RxCpltCallback(UART_HandleTypeDef *huart);
void HAL_UART_ErrorCallback(UART_HandleTypeDef *huart);
void buzzer_off(void);
void buzzer_on(void);
void CargarDatosDesdeEEPROM(void); // Funcion para leer los datos almacenados de la Epromm
void Mensaje_Atrack(char *comando); 	// Valida el mensaje de plataforma
void MENSAJE_BLUETOOTH(char *comando);	// Valida mensaje de Bluetooth
void BLE_MAC (void);					// Se obtiene la mac del bluetooth
int  BLE_OK(void);						// Se sabe si llego un dato correcto al BLE
void RELAY_INICIO (void);				// Inicio de relevadores
void APERTURA(uint8_t LLEGO);		// Abre el perno
void CIERRE(uint8_t LLEGO);
void MENSAJE_GPS (const char *MENJ,const char *LLEGO);	// manda mensaje de respuesta al GPS
void Mensaje_ADC (uint32_t ADC_01, uint32_t ADC_02, uint32_t ADC_03); // Aqui se manda un comando fijo de ADC
int BLE_Check_Viva(void);
void Reset_gps(int8_t LX);						// Reset de GPS
void TQT_Bloqueo (char *comando);				// Para guardar el tipo de bloqueo
void TQT_Reset_General (void);					// Reset de fabrica
void TQT_Reset_Ble (void);						// Reset de Bluetooth
void TQT_Nombre (char *comando);				// Nombre para guardar el BLE
GPIO_PinState NivelEntradaADC(uint16_t lectura, GPIO_PinState anterior);
GPIO_PinState LeerEntradaADC(uint8_t entrada);
void ReiniciarEntradasMap(uint8_t pares);
uint8_t FinMapaValido(const char *fin);
void EnviarMapaConfig(void);
void TQT_Map(char *comando);
void TQT_Sensores (char *comando);				// Activa o desactiva sensores de motor
void TQT_Tiempo (char *comando);				// Tiempo extra para esperar sensores de motor
void TQT_SPAS (char *comando);					// Separador entre sensores
void TQT_SPAV (char *comando);					// Separador entre sensor y valor
void TQT_DBG_TQT (char *comando);				// Modo de mensajes TQT
void TQT_OFF_GPS (void);						// Desbloqua
void TQT_ON_GPS (void);							// Bloquea
void TQT_Out_1 (char *comando);					// Bloqueo out_1
void TQT_Out_2 (char *comando);					// Bloqueo out_2
void TQT_Int_1 (char *comando);					// Activacion de mensaje de entrada
void TQT_Int_2 (char *comando);					// Activacion de mensaje de entrada
void TQT_Int_3 (char *comando);					// Activacion de mensaje de entrada
void TQTR_Status_Motor (void);
void TQTR_Indicador_Motor (void);
// ================= FUNCIONES EEPROM ======================
// =========================================================
void CargarDefaults(void);						// Carga los datos por defecto
void DATOS(void);
void GuardarConfig(void);
void LeerConfig(void);
void EnviarEstadoConfig(void); 					// Ejemplo de salida AT$POST=1,0,"S2-J:1-OUT:1"
void EnviarSeparadoresConfig(void);
void LimpiarMac(const char *origen, char *destino, size_t destino_len);
char SeparadorSensoresConfig(void);
char SeparadorValorConfig(void);
uint8_t FinComandoValido(char c);
uint8_t SeparadorConfigValido(char c);
const char *BuscarCampoMensaje(const char *origen);
const char *NombreOrigenMensaje(uint8_t origen);
void AgregarVariable(char *destino, const char *nombre, int valor, uint8_t ultimo);
void AgregarVariableTexto(char *destino, const char *nombre, const char *valor, uint8_t ultimo);
void AgregarVariableUint32(char *destino, const char *nombre, uint32_t valor, uint8_t ultimo);
void EnviarEstadoConfig(void);
void CambiarEstadoMotor(uint8_t nuevo_estado);
void RegistrarMovimientoMotor(void);
void ActualizarError(uint8_t nuevo_error);
uint32_t TiempoMotorEsperaMs(void);
/* USER CODE END 0 */

/**
  * @brief  The application entry point.
  * @retval int
  */
int main(void)
{

  /* USER CODE BEGIN 1 */

  /* USER CODE END 1 */

  /* MCU Configuration--------------------------------------------------------*/

  /* Reset of all peripherals, Initializes the Flash interface and the Systick. */
  HAL_Init();

  /* USER CODE BEGIN Init */
  /* Initialize the original GPIO off-levels BEFORE validating Flash.
   * UART4 is diagnostic only. No timers/ADC/IWDG/EEPROM started on failure. */
  MX_GPIO_Init();
  TQT_IdentityResult identity_result = TQT_IdentityLoad();
  if (identity_result != TQT_ID_OK) {
      SystemClock_Config();
      MX_UART4_Init();
      TQT_IdentityFault(identity_result);
  }

  /* USER CODE END Init */

  /* Configure the system clock */
  SystemClock_Config();

  /* USER CODE BEGIN SysInit */

  /* USER CODE END SysInit */

  /* Initialize all configured peripherals */
  MX_GPIO_Init();
  MX_DMA_Init();
  MX_UART5_Init();
  MX_I2C1_Init();
  MX_USART1_UART_Init();
  MX_TIM2_Init();
  MX_UART4_Init();
  MX_CRC_Init();
  MX_IWDG_Init();
  MX_I2C2_Init();
  MX_ADC1_Init();
  MX_TIM3_Init();
  MX_TIM4_Init();
  /* USER CODE BEGIN 2 */
  TIM2_Start();
  StartUARTReceiveIT1();
  StartUARTReceiveIT4();
  StartUARTReceiveIT5();
  HAL_ADC_Start_DMA(&hadc1, (uint32_t*)mis_lecturas_adc, ADC_LECTURAS);
  /* USER CODE END 2 */

  /* Infinite loop */
  /* USER CODE BEGIN WHILE */
  BLE_01_OFF;				// Se Apaga el BLE
  HAL_Delay(1000);			// Se deja pasar un segundo para simular que se reinicia
  BLE_01_ON;				// Se prende el BLE para que tenga alimentacion
  Debug("Inicio");
  RELAY_INICIO();
  HAL_Delay(1000);
  BT_DELAY();
  BT_DELAY();
  BLE_MAC();
  BT_DELAY();
  CargarDatosDesdeEEPROM();
  if (Config.Error != 0) { timeoutError = HAL_GetTick(); }
  Config.Viva = !Config.Viva;
  Config.Reset++;
  GuardarConfig();
  HAL_GPIO_WritePin(GPIOB,INDICADOR_BLOQUEO_Pin, Out_02);
  memoria_sensor_1 = (mis_lecturas_adc[IDX_SENSOR_APERTURA] < UMBRAL_SENSOR) ? 1 : 0;
  memoria_sensor_2 = (mis_lecturas_adc[IDX_SENSOR_CIERRE]   < UMBRAL_SENSOR) ? 1 : 0;
  ReiniciarEntradasMap(3); // Config de EEPROM ya cargada; TIM3 aun detenido.
  filtro_adc = mis_lecturas_adc[0];
  TIM3_Start();
  DATOS();
  sprintf(buffer, "%s%s - Lista para usarse %s", ENCABEZADO, Config.Nombre, FIN_ENCBEZADO );
  Serial_GPS(buffer);
  // INT_1/INT_2 ya inicializadas desde ADC y mapa antes de arrancar TIM3.
  INT_S3 = HAL_GPIO_ReadPin(GPIOB, INT_3_Pin);
  EnviarEstadoConfig();
///-----------------------------------------------------------------------------------------------------------------------------------
  while (1)
  {
    /* USER CODE END WHILE */

    /* USER CODE BEGIN 3 */
		HAL_IWDG_Refresh(&hiwdg);
		GPS_ProcesarCola();
//------------------------------------------------------------------------------------------------------------------
// Debug
	  	if (rxReadIndex4 != rxWriteIndex4) //Se procesan los datos que llegan del GPS
	  	{
	  		if (CS_DBG >= sizeof(SKY_COMD_Debug) - 1) { CS_DBG = 0; esperandoDBG = false; }
	  		SKY_COMD_Debug[CS_DBG++] = rxBuffer4[rxReadIndex4];
	  		rxReadIndex4 = (rxReadIndex4 + 1) % RX_BUFFER_SIZE;
	  		// Arranca el temporizador al primer carácter
	  		if (!esperandoDBG) { esperandoDBG = true; timeoutDBG = HAL_GetTick(); }
	  		// Si llega el fin de línea, procesamos
	  		if (SKY_COMD_Debug[CS_DBG - 1] == '\n')
	  		{
	  			SKY_COMD_Debug[CS_DBG] = '\0';
	  			Mensaje_Atrack(SKY_COMD_Debug);
	  			CS_DBG = 0;
	  			esperandoDBG = false; // reinicia el estado
	  		}
	  	}
//------------------------------------------------------------------------------------------------------------------
// GPS
		if (rxReadIndex5 != rxWriteIndex5) //Se procesan los datos que llegan del GPS
		{
			if (CS >= sizeof(SKY_COMD) - 1) { CS = 0; esperandoSKY = false; }
			SKY_COMD[CS++] = rxBuffer5[rxReadIndex5];
			rxReadIndex5 = (rxReadIndex5 + 1) % RX_BUFFER_SIZE;
			// Arranca el temporizador al primer carácter
			if (!esperandoSKY) { esperandoSKY = true; timeoutSKY = HAL_GetTick(); }
			// Si llega el fin de línea, procesamos
			if (SKY_COMD[CS - 1] == '\n')
			{
				SKY_COMD[CS] = '\0';
				Mensaje_Atrack(SKY_COMD);
				CS = 0;
				esperandoSKY = false; // reinicia el estado
			}
		}
//------------------------------------------------------------------------------------------------------------------
// BLE
		if (rxReadIndex1 != rxWriteIndex1) // Se procesan los datos que llegan del BLE
		{
			if (CB >= sizeof(BLE_COMD) - 1) { CB = 0; esperandoBLE = false; }
			BLE_COMD[CB++] = rxBuffer1[rxReadIndex1];
			rxReadIndex1 = (rxReadIndex1 + 1) % RX_BUFFER_SIZE;
			// Inicia el contador al primer carácter
			if (!esperandoBLE) { esperandoBLE = true; timeoutBLE = HAL_GetTick(); }
			// Si llega el fin de línea, procesamos
			if (BLE_COMD[CB - 1] == '\n') {
				LED_B_ON;
				BLE_COMD[CB] = '\0';
				MENSAJE_BLUETOOTH(BLE_COMD);
				CB = 0;
				esperandoBLE = false; // reiniciar estado de espera
				LED_B_OFF;
			}
		}
//------------------------------------------------------------------------------------------------------------------
		// ⏱️ Si se está esperando y pasaron más de 1000ms desde el último dato que llega del BLE
		if (esperandoBLE && (HAL_GetTick() - timeoutBLE > 1000)) { CB = 0; esperandoBLE = false; ActualizarError(16); GuardarConfig(); EnviarEstadoConfig(); Debug("BLE TIMEOUT: Se borro mensaje incompleto\r\n"); }
//------------------------------------------------------------------------------------------------------------------
		// ⏱️ Si se está esperando y pasaron más de 1000ms desde el último dato que llega de Atrack
		if (esperandoSKY && (HAL_GetTick() - timeoutSKY > 1000)) { CS = 0; esperandoSKY = false; ActualizarError(17); GuardarConfig(); EnviarEstadoConfig(); Debug("SKY TIMEOUT: Se borro mensaje incompleto"); }
		if (esperandoDBG && (HAL_GetTick() - timeoutDBG > 1000)) { CS_DBG = 0; esperandoDBG = false; ActualizarError(18); GuardarConfig(); EnviarEstadoConfig(); Debug("DBG TIMEOUT: Se borro mensaje incompleto"); }
//------------------------------------------------------------------------------------------------------------------
		// ⏱️ Si se está esperando y pasaron más de 1 Min desde el último inicio
		if (HAL_GetTick() - timeoutBleV >= 60000) { timeoutBleV = HAL_GetTick(); BLE_Check_Viva(); }
//------------------------------------------------------------------------------------------------------------------
		// LIMPIAR ERROR 2 MINUTOS DESPUES DEL ULTIMO CAMBIO DE ERROR
		if (Config.Error != 0 && (HAL_GetTick() - timeoutError >= 120000)) { ActualizarError(0); GuardarConfig(); EnviarEstadoConfig(); }
//------------------------------------------------------------------------------------------------------------------
		// MENSAJE VIVO CADA 10 MIN
		if (HAL_GetTick() - timeoutVIVA >= 600000) { timeoutVIVA = HAL_GetTick(); Config.Viva = !Config.Viva; GuardarConfig(); EnviarEstadoConfig(); }
//------------------------------------------------------------------------------------------------------------------
		// ERRORES DETECTADOS DESDE TIM3
		if (errores_pendientes != 0)
		{
		    uint8_t error_a_reportar = 0;
		    __disable_irq();
		    if (errores_pendientes & (1UL << 13)) { errores_pendientes &= ~(1UL << 13); error_a_reportar = 13; }
		    else if (errores_pendientes & (1UL << 14)) { errores_pendientes &= ~(1UL << 14); error_a_reportar = 14; }
		    else if (errores_pendientes & (1UL << 15)) { errores_pendientes &= ~(1UL << 15); error_a_reportar = 15; }
		    __enable_irq();
		    if (error_a_reportar != 0) { ActualizarError(error_a_reportar); GuardarConfig(); EnviarEstadoConfig(); }
		}
//------------------------------------------------------------------------------------------------------------------
		// VALIDAR ENTRADAS
		if (HAL_GetTick() - timeoutINTS >= 100)
		{
		    timeoutINTS = HAL_GetTick();
		    uint8_t cambio_inputs = 0;
		    if (Config.Int1 >= 1)	// ENTRADA 1
		    {
		        GPIO_PinState lectura = LeerEntradaADC(1);
		        if (lectura == INT_S1_ANT) { if (stableCount1 < 10) { stableCount1++; } }
		        else { stableCount1 = 0; INT_S1_ANT = lectura; }

		        if (stableCount1 >= 10 && INT_S1 != INT_S1_ANT) { INT_S1 = INT_S1_ANT; cambio_inputs = 1; }
		    }
		    if (Config.Int2 >= 1)	// ENTRADA 2
		    {
		        GPIO_PinState lectura = LeerEntradaADC(2);
		        if (lectura == INT_S2_ANT) { if (stableCount2 < 10) { stableCount2++; } }
		        else { stableCount2 = 0; INT_S2_ANT = lectura; }

		        if (stableCount2 >= 10 && INT_S2 != INT_S2_ANT) { INT_S2 = INT_S2_ANT; cambio_inputs = 1; }
		    }
		    if (Config.Int3 >= 1)	// ENTRADA 3
		    {
		        GPIO_PinState lectura = HAL_GPIO_ReadPin(GPIOB, INT_3_Pin);
		        if (lectura == INT_S3_ANT) { if (stableCount3 < 10) { stableCount3++; } }
		        else { stableCount3 = 0; INT_S3_ANT = lectura; }

		        if (stableCount3 >= 10 && INT_S3 != INT_S3_ANT) { INT_S3 = INT_S3_ANT; cambio_inputs = 1; }
		    }
		    if (cambio_inputs) { EnviarEstadoConfig(); }
		}
  }
  /* USER CODE END 3 */
}

/**
  * @brief System Clock Configuration
  * @retval None
  */
void SystemClock_Config(void)
{
  RCC_OscInitTypeDef RCC_OscInitStruct = {0};
  RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};
  RCC_PeriphCLKInitTypeDef PeriphClkInit = {0};

  /** Initializes the RCC Oscillators according to the specified parameters
  * in the RCC_OscInitTypeDef structure.
  */
  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_LSI|RCC_OSCILLATORTYPE_HSE;
  RCC_OscInitStruct.HSEState = RCC_HSE_ON;
  RCC_OscInitStruct.HSEPredivValue = RCC_HSE_PREDIV_DIV1;
  RCC_OscInitStruct.HSIState = RCC_HSI_ON;
  RCC_OscInitStruct.LSIState = RCC_LSI_ON;
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
  RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSE;
  RCC_OscInitStruct.PLL.PLLMUL = RCC_PLL_MUL9;
  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK)
  {
    Error_Handler();
  }

  /** Initializes the CPU, AHB and APB buses clocks
  */
  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK|RCC_CLOCKTYPE_SYSCLK
                              |RCC_CLOCKTYPE_PCLK1|RCC_CLOCKTYPE_PCLK2;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV2;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV1;

  if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_2) != HAL_OK)
  {
    Error_Handler();
  }
  PeriphClkInit.PeriphClockSelection = RCC_PERIPHCLK_ADC;
  PeriphClkInit.AdcClockSelection = RCC_ADCPCLK2_DIV6;
  if (HAL_RCCEx_PeriphCLKConfig(&PeriphClkInit) != HAL_OK)
  {
    Error_Handler();
  }
}

/**
  * @brief ADC1 Initialization Function
  * @param None
  * @retval None
  */
static void MX_ADC1_Init(void)
{

  /* USER CODE BEGIN ADC1_Init 0 */

  /* USER CODE END ADC1_Init 0 */

  ADC_ChannelConfTypeDef sConfig = {0};

  /* USER CODE BEGIN ADC1_Init 1 */

  /* USER CODE END ADC1_Init 1 */

  /** Common config
  */
  hadc1.Instance = ADC1;
  hadc1.Init.ScanConvMode = ADC_SCAN_ENABLE;
  hadc1.Init.ContinuousConvMode = ENABLE;
  hadc1.Init.DiscontinuousConvMode = DISABLE;
  hadc1.Init.ExternalTrigConv = ADC_SOFTWARE_START;
  hadc1.Init.DataAlign = ADC_DATAALIGN_RIGHT;
  hadc1.Init.NbrOfConversion = 5;
  if (HAL_ADC_Init(&hadc1) != HAL_OK)
  {
    Error_Handler();
  }

  /** Configure Regular Channel
  */
  sConfig.Channel = ADC_CHANNEL_0;
  sConfig.Rank = ADC_REGULAR_RANK_1;
  sConfig.SamplingTime = ADC_SAMPLETIME_55CYCLES_5;
  if (HAL_ADC_ConfigChannel(&hadc1, &sConfig) != HAL_OK)
  {
    Error_Handler();
  }

  /** Configure Regular Channel
  */
  sConfig.Channel = ADC_CHANNEL_1;
  sConfig.Rank = ADC_REGULAR_RANK_2;
  if (HAL_ADC_ConfigChannel(&hadc1, &sConfig) != HAL_OK)
  {
    Error_Handler();
  }

  /** Configure Regular Channel
  */
  sConfig.Channel = ADC_CHANNEL_2;
  sConfig.Rank = ADC_REGULAR_RANK_3;
  if (HAL_ADC_ConfigChannel(&hadc1, &sConfig) != HAL_OK)
  {
    Error_Handler();
  }
  /** PB0 y PB1: entradas generales o limitadores segun MAP_M1/MAP_M2. */
  sConfig.Channel = ADC_CHANNEL_8;
  sConfig.Rank = ADC_REGULAR_RANK_4;
  if (HAL_ADC_ConfigChannel(&hadc1, &sConfig) != HAL_OK)
  {
    Error_Handler();
  }
  sConfig.Channel = ADC_CHANNEL_9;
  sConfig.Rank = ADC_REGULAR_RANK_5;
  if (HAL_ADC_ConfigChannel(&hadc1, &sConfig) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN ADC1_Init 2 */

  /* USER CODE END ADC1_Init 2 */

}

/**
  * @brief CRC Initialization Function
  * @param None
  * @retval None
  */
static void MX_CRC_Init(void)
{

  /* USER CODE BEGIN CRC_Init 0 */

  /* USER CODE END CRC_Init 0 */

  /* USER CODE BEGIN CRC_Init 1 */

  /* USER CODE END CRC_Init 1 */
  hcrc.Instance = CRC;
  if (HAL_CRC_Init(&hcrc) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN CRC_Init 2 */

  /* USER CODE END CRC_Init 2 */

}

/**
  * @brief I2C1 Initialization Function
  * @param None
  * @retval None
  */
static void MX_I2C1_Init(void)
{

  /* USER CODE BEGIN I2C1_Init 0 */

  /* USER CODE END I2C1_Init 0 */

  /* USER CODE BEGIN I2C1_Init 1 */

  /* USER CODE END I2C1_Init 1 */
  hi2c1.Instance = I2C1;
  hi2c1.Init.ClockSpeed = 100000;
  hi2c1.Init.DutyCycle = I2C_DUTYCYCLE_2;
  hi2c1.Init.OwnAddress1 = 0;
  hi2c1.Init.AddressingMode = I2C_ADDRESSINGMODE_7BIT;
  hi2c1.Init.DualAddressMode = I2C_DUALADDRESS_DISABLE;
  hi2c1.Init.OwnAddress2 = 0;
  hi2c1.Init.GeneralCallMode = I2C_GENERALCALL_DISABLE;
  hi2c1.Init.NoStretchMode = I2C_NOSTRETCH_DISABLE;
  if (HAL_I2C_Init(&hi2c1) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN I2C1_Init 2 */

  /* USER CODE END I2C1_Init 2 */

}

/**
  * @brief I2C2 Initialization Function
  * @param None
  * @retval None
  */
static void MX_I2C2_Init(void)
{

  /* USER CODE BEGIN I2C2_Init 0 */

  /* USER CODE END I2C2_Init 0 */

  /* USER CODE BEGIN I2C2_Init 1 */

  /* USER CODE END I2C2_Init 1 */
  hi2c2.Instance = I2C2;
  hi2c2.Init.ClockSpeed = 100000;
  hi2c2.Init.DutyCycle = I2C_DUTYCYCLE_2;
  hi2c2.Init.OwnAddress1 = 0;
  hi2c2.Init.AddressingMode = I2C_ADDRESSINGMODE_7BIT;
  hi2c2.Init.DualAddressMode = I2C_DUALADDRESS_DISABLE;
  hi2c2.Init.OwnAddress2 = 0;
  hi2c2.Init.GeneralCallMode = I2C_GENERALCALL_DISABLE;
  hi2c2.Init.NoStretchMode = I2C_NOSTRETCH_DISABLE;
  if (HAL_I2C_Init(&hi2c2) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN I2C2_Init 2 */

  /* USER CODE END I2C2_Init 2 */

}

/**
  * @brief IWDG Initialization Function
  * @param None
  * @retval None
  */
static void MX_IWDG_Init(void)
{

  /* USER CODE BEGIN IWDG_Init 0 */

  /* USER CODE END IWDG_Init 0 */

  /* USER CODE BEGIN IWDG_Init 1 */

  /* USER CODE END IWDG_Init 1 */
  hiwdg.Instance = IWDG;
  hiwdg.Init.Prescaler = IWDG_PRESCALER_32;
  hiwdg.Init.Reload = 4095;
  if (HAL_IWDG_Init(&hiwdg) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN IWDG_Init 2 */

  /* USER CODE END IWDG_Init 2 */

}

/**
  * @brief TIM2 Initialization Function
  * @param None
  * @retval None
  */
static void MX_TIM2_Init(void)
{

  /* USER CODE BEGIN TIM2_Init 0 */

  /* USER CODE END TIM2_Init 0 */

  TIM_ClockConfigTypeDef sClockSourceConfig = {0};
  TIM_MasterConfigTypeDef sMasterConfig = {0};

  /* USER CODE BEGIN TIM2_Init 1 */

  /* USER CODE END TIM2_Init 1 */
  htim2.Instance = TIM2;
  htim2.Init.Prescaler = 7199;
  htim2.Init.CounterMode = TIM_COUNTERMODE_UP;
  htim2.Init.Period = 5000;
  htim2.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;
  htim2.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;
  if (HAL_TIM_Base_Init(&htim2) != HAL_OK)
  {
    Error_Handler();
  }
  sClockSourceConfig.ClockSource = TIM_CLOCKSOURCE_INTERNAL;
  if (HAL_TIM_ConfigClockSource(&htim2, &sClockSourceConfig) != HAL_OK)
  {
    Error_Handler();
  }
  sMasterConfig.MasterOutputTrigger = TIM_TRGO_RESET;
  sMasterConfig.MasterSlaveMode = TIM_MASTERSLAVEMODE_DISABLE;
  if (HAL_TIMEx_MasterConfigSynchronization(&htim2, &sMasterConfig) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN TIM2_Init 2 */
  sClockSourceConfig.ClockSource = TIM_CLOCKSOURCE_INTERNAL;
  if (HAL_TIM_ConfigClockSource(&htim2, &sClockSourceConfig) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE END TIM2_Init 2 */

}

/**
  * @brief TIM3 Initialization Function
  * @param None
  * @retval None
  */
static void MX_TIM3_Init(void)
{

  /* USER CODE BEGIN TIM3_Init 0 */

  /* USER CODE END TIM3_Init 0 */

  TIM_ClockConfigTypeDef sClockSourceConfig = {0};
  TIM_MasterConfigTypeDef sMasterConfig = {0};

  /* USER CODE BEGIN TIM3_Init 1 */

  /* USER CODE END TIM3_Init 1 */
  htim3.Instance = TIM3;
  htim3.Init.Prescaler = 71;
  htim3.Init.CounterMode = TIM_COUNTERMODE_UP;
  htim3.Init.Period = 185;
  htim3.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;
  htim3.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;
  if (HAL_TIM_Base_Init(&htim3) != HAL_OK)
  {
    Error_Handler();
  }
  sClockSourceConfig.ClockSource = TIM_CLOCKSOURCE_INTERNAL;
  if (HAL_TIM_ConfigClockSource(&htim3, &sClockSourceConfig) != HAL_OK)
  {
    Error_Handler();
  }
  sMasterConfig.MasterOutputTrigger = TIM_TRGO_RESET;
  sMasterConfig.MasterSlaveMode = TIM_MASTERSLAVEMODE_DISABLE;
  if (HAL_TIMEx_MasterConfigSynchronization(&htim3, &sMasterConfig) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN TIM3_Init 2 */

  /* USER CODE END TIM3_Init 2 */

}

/**
  * @brief TIM4 Initialization Function
  * @param None
  * @retval None
  */
static void MX_TIM4_Init(void)
{

  /* USER CODE BEGIN TIM4_Init 0 */

  /* USER CODE END TIM4_Init 0 */

  TIM_ClockConfigTypeDef sClockSourceConfig = {0};
  TIM_MasterConfigTypeDef sMasterConfig = {0};

  /* USER CODE BEGIN TIM4_Init 1 */

  /* USER CODE END TIM4_Init 1 */
  htim4.Instance = TIM4;
  htim4.Init.Prescaler = 71;
  htim4.Init.CounterMode = TIM_COUNTERMODE_UP;
  htim4.Init.Period = 185;
  htim4.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;
  htim4.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_DISABLE;
  if (HAL_TIM_Base_Init(&htim4) != HAL_OK)
  {
    Error_Handler();
  }
  sClockSourceConfig.ClockSource = TIM_CLOCKSOURCE_INTERNAL;
  if (HAL_TIM_ConfigClockSource(&htim4, &sClockSourceConfig) != HAL_OK)
  {
    Error_Handler();
  }
  sMasterConfig.MasterOutputTrigger = TIM_TRGO_RESET;
  sMasterConfig.MasterSlaveMode = TIM_MASTERSLAVEMODE_DISABLE;
  if (HAL_TIMEx_MasterConfigSynchronization(&htim4, &sMasterConfig) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN TIM4_Init 2 */

  /* USER CODE END TIM4_Init 2 */

}

/**
  * @brief UART4 Initialization Function
  * @param None
  * @retval None
  */
static void MX_UART4_Init(void)
{

  /* USER CODE BEGIN UART4_Init 0 */

  /* USER CODE END UART4_Init 0 */

  /* USER CODE BEGIN UART4_Init 1 */

  /* USER CODE END UART4_Init 1 */
  huart4.Instance = UART4;
  huart4.Init.BaudRate = 57600;
  huart4.Init.WordLength = UART_WORDLENGTH_8B;
  huart4.Init.StopBits = UART_STOPBITS_1;
  huart4.Init.Parity = UART_PARITY_NONE;
  huart4.Init.Mode = UART_MODE_TX_RX;
  huart4.Init.HwFlowCtl = UART_HWCONTROL_NONE;
  huart4.Init.OverSampling = UART_OVERSAMPLING_16;
  if (HAL_UART_Init(&huart4) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN UART4_Init 2 */

  /* USER CODE END UART4_Init 2 */

}

/**
  * @brief UART5 Initialization Function
  * @param None
  * @retval None
  */
static void MX_UART5_Init(void)
{

  /* USER CODE BEGIN UART5_Init 0 */

  /* USER CODE END UART5_Init 0 */

  /* USER CODE BEGIN UART5_Init 1 */

  /* USER CODE END UART5_Init 1 */
  huart5.Instance = UART5;
  huart5.Init.BaudRate = 57600;
  huart5.Init.WordLength = UART_WORDLENGTH_8B;
  huart5.Init.StopBits = UART_STOPBITS_1;
  huart5.Init.Parity = UART_PARITY_NONE;
  huart5.Init.Mode = UART_MODE_TX_RX;
  huart5.Init.HwFlowCtl = UART_HWCONTROL_NONE;
  huart5.Init.OverSampling = UART_OVERSAMPLING_16;
  if (HAL_UART_Init(&huart5) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN UART5_Init 2 */

  /* USER CODE END UART5_Init 2 */

}

/**
  * @brief USART1 Initialization Function
  * @param None
  * @retval None
  */
static void MX_USART1_UART_Init(void)
{

  /* USER CODE BEGIN USART1_Init 0 */

  /* USER CODE END USART1_Init 0 */

  /* USER CODE BEGIN USART1_Init 1 */

  /* USER CODE END USART1_Init 1 */
  huart1.Instance = USART1;
  huart1.Init.BaudRate = 115200;
  huart1.Init.WordLength = UART_WORDLENGTH_8B;
  huart1.Init.StopBits = UART_STOPBITS_1;
  huart1.Init.Parity = UART_PARITY_NONE;
  huart1.Init.Mode = UART_MODE_TX_RX;
  huart1.Init.HwFlowCtl = UART_HWCONTROL_NONE;
  huart1.Init.OverSampling = UART_OVERSAMPLING_16;
  if (HAL_UART_Init(&huart1) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN USART1_Init 2 */

  /* USER CODE END USART1_Init 2 */

}

/**
  * Enable DMA controller clock
  */
static void MX_DMA_Init(void)
{

  /* DMA controller clock enable */
  __HAL_RCC_DMA1_CLK_ENABLE();

  /* DMA interrupt init */
  /* DMA1_Channel1_IRQn interrupt configuration */
  HAL_NVIC_SetPriority(DMA1_Channel1_IRQn, 0, 0);
  HAL_NVIC_EnableIRQ(DMA1_Channel1_IRQn);

}

/**
  * @brief GPIO Initialization Function
  * @param None
  * @retval None
  */
static void MX_GPIO_Init(void)
{
  GPIO_InitTypeDef GPIO_InitStruct = {0};
  /* USER CODE BEGIN MX_GPIO_Init_1 */

  /* USER CODE END MX_GPIO_Init_1 */

  /* GPIO Ports Clock Enable */
  __HAL_RCC_GPIOC_CLK_ENABLE();
  __HAL_RCC_GPIOD_CLK_ENABLE();
  __HAL_RCC_GPIOA_CLK_ENABLE();
  __HAL_RCC_GPIOB_CLK_ENABLE();

  /*Configure GPIO pin Output Level */
  HAL_GPIO_WritePin(GPIOC, LED_Pin|BOCINA_Pin|LED_R_Pin|LED_G_Pin
                          |LED_B_Pin|RE_DE_Pin, GPIO_PIN_RESET);

  /*Configure GPIO pin Output Level */
  HAL_GPIO_WritePin(GPIOA, R_1_Pin|R_2_Pin|OUT_2_Pin|OUT_1_Pin
                          |ESP_ENABLE_Pin, GPIO_PIN_RESET);

  /*Configure GPIO pin Output Level */
  HAL_GPIO_WritePin(GPIOB, INDICADOR_BLOQUEO_Pin|BLQ_EEPROM_Pin, GPIO_PIN_RESET);

  /*Configure GPIO pins : LED_Pin BOCINA_Pin LED_R_Pin LED_G_Pin
                           LED_B_Pin RE_DE_Pin */
  GPIO_InitStruct.Pin = LED_Pin|BOCINA_Pin|LED_R_Pin|LED_G_Pin
                          |LED_B_Pin|RE_DE_Pin;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(GPIOC, &GPIO_InitStruct);

  /*Configure GPIO pins : R_1_Pin R_2_Pin OUT_2_Pin OUT_1_Pin
                           ESP_ENABLE_Pin */
  GPIO_InitStruct.Pin = R_1_Pin|R_2_Pin|OUT_2_Pin|OUT_1_Pin
                          |ESP_ENABLE_Pin;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(GPIOA, &GPIO_InitStruct);

  /*Configure GPIO pin : INT_3_Pin (INT_1/INT_2 se configuran en ADC MSP) */
  GPIO_InitStruct.Pin = INT_3_Pin;
  GPIO_InitStruct.Mode = GPIO_MODE_INPUT;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  HAL_GPIO_Init(GPIOB, &GPIO_InitStruct);

  /*Configure GPIO pins : INDICADOR_BLOQUEO_Pin BLQ_EEPROM_Pin */
  GPIO_InitStruct.Pin = INDICADOR_BLOQUEO_Pin|BLQ_EEPROM_Pin;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(GPIOB, &GPIO_InitStruct);

  /* USER CODE BEGIN MX_GPIO_Init_2 */

  /* USER CODE END MX_GPIO_Init_2 */
}

/* USER CODE BEGIN 4 */
void HAL_Delay(uint32_t Delay)
{
  uint32_t tickstart = HAL_GetTick();
  uint32_t wait = Delay;

  /* Add a freq to guarantee minimum wait */
  if (wait < HAL_MAX_DELAY)
  {
    wait += (uint32_t)(uwTickFreq);
  }

  while((HAL_GetTick() - tickstart) < wait)
  {
      HAL_IWDG_Refresh(&hiwdg);
  }
}

void HAL_TIM_PeriodElapsedCallback(TIM_HandleTypeDef *htim)
{
    if (htim->Instance == TIM2) {
        HAL_GPIO_TogglePin(GPIOC, LED_Pin);
    }

    // --- LÓGICA DEL MOTOR (TIMER 4) ---
    if (htim->Instance == TIM4) { HAL_GPIO_TogglePin(GPIOC,BOCINA_Pin); }
    // --- LÓGICA DEL MOTOR (TIMER 3) ---
    if (htim->Instance == TIM3) {
    	//HAL_GPIO_TogglePin(GPIOC,BOCINA_Pin);
        // A. LECTURA DE SENSORES
        uint8_t sensor_apertura_activo = (mis_lecturas_adc[IDX_SENSOR_APERTURA] < UMBRAL_SENSOR) ? 1 : 0;
        uint8_t sensor_cierre_activo   = (mis_lecturas_adc[IDX_SENSOR_CIERRE]   < UMBRAL_SENSOR) ? 1 : 0;
        //uint8_t sensor_apertura_activo = 1;
        //uint8_t sensor_cierre_activo   = 0;
        adc_debug[0] = mis_lecturas_adc[0];
        adc_debug[1] = mis_lecturas_adc[1];
        adc_debug[2] = mis_lecturas_adc[2];

        flag_adc_debug = 1;
        // B. MOVIMIENTO
        if (estado_actual_motor != ESTADO_ESPERA) {

            // 1. ABRIENDO (AHORA TIENE LA LÓGICA DE 3 PASOS)
            if (estado_actual_motor == ESTADO_ABRIENDO) {

                // Paso 0: Detecta primer contacto (falso/obstáculo)
                if (Config.Sensores == 0 && etapa_apertura == 0) {
                    if (sensor_apertura_activo == 1) etapa_apertura = 1;
                }
                // Paso 1: Espera que se libere (el hueco)
                else if (Config.Sensores == 0 && etapa_apertura == 1) {
                    if (sensor_apertura_activo == 0) etapa_apertura = 2;
                }
                // Paso 2: Detecta el final REAL
                else if (Config.Sensores == 0 && etapa_apertura == 2) {
                    if (sensor_apertura_activo == 1) {
                        // ¡LLEGÓ!
                        //MOTOR_APAGAR_TODO(); aqui va a ir lo del tipo si es que se hace
                        memoria_sensor_1 = sensor_apertura_activo;
                        memoria_sensor_2 = sensor_cierre_activo;
                        estado_actual_motor = ESTADO_ESPERA;
                        bandera_limite_alcanzado = 1;
                        etapa_apertura = 0; // Reiniciar
                    }
                }
                TQTR_Indicador_Motor();
            }
            // 2. CERRANDO (AHORA TIENE LÓGICA SIMPLE: Detecta y para)
            else if (estado_actual_motor == ESTADO_CERRANDO) {

                if (Config.Sensores == 0 && sensor_cierre_activo == 1) {

                    // ¡LLEGÓ! (Paro inmediato)
                    //MOTOR_APAGAR_TODO();

                    memoria_sensor_1 = sensor_apertura_activo;
                    memoria_sensor_2 = sensor_cierre_activo;

                    estado_actual_motor = ESTADO_ESPERA;
                    bandera_limite_alcanzado = 1;
                }
                TQTR_Indicador_Motor();
            }
        }

        // C. MANIPULACIÓN
        else {
            if (sensor_apertura_activo != memoria_sensor_1) {
            	errores_pendientes |= (1UL << 13);
                memoria_sensor_1 = sensor_apertura_activo;
            }
            if (sensor_cierre_activo != memoria_sensor_2) {
            	errores_pendientes |= (1UL << 14);
                memoria_sensor_2 = sensor_cierre_activo;
            }
            TQTR_Indicador_Motor();
        }


  	  // Lectura cruda
  	  uint16_t adc_raw = mis_lecturas_adc[0];

  	  // ---- FILTRO (IIR suave) ----
  	  // 75% valor anterior + 25% nuevo
  	  filtro_adc = (filtro_adc * 3 + adc_raw) / 4;

  	  // Usa el valor filtrado
  	  uint16_t adc = filtro_adc;

  	  // Valor absoluto respecto al centro
  	  uint16_t delta = (adc > ADC_OFFSET) ? (adc - ADC_OFFSET) : (ADC_OFFSET - adc);

  	  // ---- DETECCIÓN ----
  	// ---- DETECCIÓN ----
  	if (delta > ADC_DELTA)
  	{
  	    // Si es la primera vez que detecta alto → inicia conteo
  	    if (sobrecorriente_confirmada == 0)
  	    {
  	        if (tiempo_sobrecorriente_inicio == 0)
  	        {
  	            tiempo_sobrecorriente_inicio = HAL_GetTick();
  	        }

  	        // Si ya pasó 250 ms → confirmar sobrecorriente
  	        if (HAL_GetTick() - tiempo_sobrecorriente_inicio >= 250)
  	        {
  	            sobrecorriente_confirmada = 1;

  	            if (flag_sobrecorriente == 0)
  	            {
  	                flag_sobrecorriente = 1;
  	            	errores_pendientes |= (1UL << 15);
  	            }
  	        }
  	    }

  	    // Mientras esté alto → reinicia timer de "bajo"
  	    tiempo_bajo_corriente = HAL_GetTick();
  	}
  	else
  	{
  	    // Si bajó → resetear proceso de confirmación
  	    tiempo_sobrecorriente_inicio = 0;
  	    sobrecorriente_confirmada = 0;

  	    // Lógica de rearme (tuya, está bien)
  	    if (flag_sobrecorriente == 1)
  	    {
  	        if (HAL_GetTick() - tiempo_bajo_corriente > 1000)
  	        {
  	            flag_sobrecorriente = 0;
  	        }
  	    }
  	}
    }
}

///------------------------------------------------------------------------------------------------- Fin Timers
void TIM2_Start(void) {
    HAL_TIM_Base_Start_IT(&htim2);
}
void TIM3_Start(void) {
    HAL_TIM_Base_Start_IT(&htim3);
}

///------------------------------------------------------------------------------------------------- Seriales

void StartUARTReceiveIT1(void) {
    HAL_UART_Receive_IT(&huart1, &rxBuffer1[rxWriteIndex1], 1);
}
void StartUARTReceiveIT4(void) {
    HAL_UART_Receive_IT(&huart4, &rxBuffer4[rxWriteIndex4], 1);
}
void StartUARTReceiveIT5(void) {
    HAL_UART_Receive_IT(&huart5, &rxBuffer5[rxWriteIndex5], 1);
}

void ProcessSerialData1(void) {
    int data;
    while ((data = UART_ReadByte1()) != -1) {
    	HAL_Delay(10);
        // Transmite de vuelta el dato recibido
        HAL_UART_Transmit(&huart5, (uint8_t *)&data, 1, HAL_MAX_DELAY);
        HAL_UART_Transmit(&huart4, (uint8_t *)&data, 1, HAL_MAX_DELAY);
    }
}

int UART_ReadByte1(void) {
    if (rxReadIndex1 == rxWriteIndex1) {
        return -1; // No hay datos disponibles
    } else {
        uint8_t data = rxBuffer1[rxReadIndex1];
        rxReadIndex1 = (rxReadIndex1 + 1) % RX_BUFFER_SIZE;
        return data;
    }
}

void HAL_UART_RxCpltCallback(UART_HandleTypeDef *huart) {
    if (huart->Instance == USART1) {
        uint16_t nextIndex = (rxWriteIndex1 + 1) % RX_BUFFER_SIZE;
        if (nextIndex != rxReadIndex1) { // Verifica el desbordamiento del buffer
            rxWriteIndex1 = nextIndex;
        }
        StartUARTReceiveIT1(); // Reinicia la recepción siempre
    }
    else if (huart->Instance == UART4) {
        uint16_t nextIndex = (rxWriteIndex4 + 1) % RX_BUFFER_SIZE;
        if (nextIndex != rxReadIndex4) { // Verifica el desbordamiento del buffer
            rxWriteIndex4 = nextIndex;
        }
        StartUARTReceiveIT4(); // Reinicia la recepción siempre
    }
    else if (huart->Instance == UART5) {
        uint16_t nextIndex = (rxWriteIndex5 + 1) % RX_BUFFER_SIZE;
        if (nextIndex != rxReadIndex5) { // Verifica el desbordamiento del buffer
            rxWriteIndex5 = nextIndex;
        }
        StartUARTReceiveIT5(); // Reinicia la recepción siempre
    }
}

void HAL_UART_ErrorCallback(UART_HandleTypeDef *huart) {
    if (huart->Instance == USART1) {
        // Reinicia la recepción en caso de error
        StartUARTReceiveIT1();
    }
    else if (huart->Instance == UART4) {
        // Reinicia la recepción en caso de error
        StartUARTReceiveIT4();
    }
    else if (huart->Instance == UART5) {
        // Reinicia la recepción en caso de error
        StartUARTReceiveIT5();
    }
}

void Serial_GPS_Directo(const char *string)
{
	RS_485_Escribir;
	//HAL_Delay(10);
    HAL_UART_Transmit(&huart5, (uint8_t *)string, strlen(string), HAL_MAX_DELAY);
    while(__HAL_UART_GET_FLAG(&huart5, UART_FLAG_TC) == RESET);
    HAL_UART_Transmit(&huart4, (uint8_t *)string, strlen(string), HAL_MAX_DELAY);
    while(__HAL_UART_GET_FLAG(&huart4, UART_FLAG_TC) == RESET);
    RS_485_Leer;
}

uint8_t FinComandoValido(char c)
{
    return (c == '\r' || c == '\n' || c == '\0');
}

uint8_t SeparadorConfigValido(char c)
{
    return (c != '\0' && c != '\r' && c != '\n' && c != '"');
}

char SeparadorSensoresConfig(void)
{
    if (!SeparadorConfigValido(Config.SeparadorSensores)) { return Default_SPAS; }
    return Config.SeparadorSensores;
}

char SeparadorValorConfig(void)
{
    if (!SeparadorConfigValido(Config.SeparadorValor)) { return Default_SPAV; }
    return Config.SeparadorValor;
}

const char *BuscarCampoMensaje(const char *origen)
{
    char patron[12];
    snprintf(patron, sizeof(patron), "Mensaje%c", SeparadorValorConfig());
    const char *inicio = strstr(origen, patron);
    if (inicio == NULL) { inicio = strstr(origen, "Mensaje:"); }
    return inicio;
}

const char *NombreOrigenMensaje(uint8_t origen)
{
    if (origen == PLAT) { return "Plataforma"; }
    if (origen == BLUE) { return "Bluetooth"; }
    return "Sistema";
}

void GPS_EncolarMensaje(const char *string)
{
    if (string == NULL) { return; }
    if (gpsColaCantidad >= GPS_MSG_QUEUE_SIZE)
    {
        gpsColaLectura = (gpsColaLectura + 1) % GPS_MSG_QUEUE_SIZE;
        gpsColaCantidad--;
        gpsMensajesDescartados++;
    }
    snprintf(gpsCola[gpsColaEscritura].texto, GPS_MSG_MAX_LEN, "%s", string);
    gpsCola[gpsColaEscritura].actualiza_mensaje = (BuscarCampoMensaje(string) != NULL) ? 1 : 0;
    if (gpsCola[gpsColaEscritura].actualiza_mensaje)
    {
        gpsConsecutivoMensaje++;
        gpsCola[gpsColaEscritura].numero = gpsConsecutivoMensaje;
    }
    else
    {
        gpsCola[gpsColaEscritura].numero = 0;
    }
    gpsColaEscritura = (gpsColaEscritura + 1) % GPS_MSG_QUEUE_SIZE;
    gpsColaCantidad++;
}

uint8_t GPS_DesencolarMensaje(char *destino, uint32_t *numero, uint8_t *actualiza_mensaje)
{
    if (gpsColaCantidad == 0) { return 0; }
    snprintf(destino, GPS_MSG_MAX_LEN, "%s", gpsCola[gpsColaLectura].texto);
    *numero = gpsCola[gpsColaLectura].numero;
    *actualiza_mensaje = gpsCola[gpsColaLectura].actualiza_mensaje;
    gpsColaLectura = (gpsColaLectura + 1) % GPS_MSG_QUEUE_SIZE;
    gpsColaCantidad--;
    return 1;
}

void GPS_ActualizarCampoMensaje(const char *origen, char *destino, uint32_t numero, uint8_t intento)
{
    const char *inicio = BuscarCampoMensaje(origen);
    if (inicio == NULL)
    {
        snprintf(destino, GPS_MSG_MAX_LEN, "%s", origen);
        return;
    }

    const char *fin = strchr(inicio, SeparadorSensoresConfig());
    if (fin == NULL) { fin = strchr(inicio, '-'); }
    if (fin == NULL) { snprintf(destino, GPS_MSG_MAX_LEN, "%s", origen); return; }

    size_t prefijo_len = (size_t)(inicio - origen);
    snprintf(destino, GPS_MSG_MAX_LEN, "%.*sMensaje%c%lu.%u%s", (int)prefijo_len, origen, SeparadorValorConfig(), (unsigned long)numero, intento, fin);
}

void GPS_EnviarMensajeActual(void)
{
    if (gpsActualizaMensaje)
    {
        GPS_ActualizarCampoMensaje(gpsMensajeActual, gpsMensajeSalida, gpsNumeroActual, gpsReintentos);
        Serial_GPS_Directo(gpsMensajeSalida);
    }
    else
    {
        Serial_GPS_Directo(gpsMensajeActual);
    }
    gpsTiempoEnvio = HAL_GetTick();
}

void GPS_ProcesarCola(void)
{
    if (gpsMensajeActivo)
    {
        if (gpsAckRecibido)
        {
            gpsMensajeActivo = 0;
            gpsAckRecibido = 0;
            gpsActualizaMensaje = 0;
            gpsNumeroActual = 0;
            gpsReintentos = 0;
            return;
        }
        if ((HAL_GetTick() - gpsTiempoEnvio) >= GPS_ACK_TIMEOUT)
        {
            if ((gpsReintentos + 1) < GPS_MAX_REINTENTOS)
            {
                gpsReintentos++;
                GPS_EnviarMensajeActual();
            }
            else
            {
                gpsMensajeActivo = 0;
                gpsAckRecibido = 0;
                gpsActualizaMensaje = 0;
                gpsNumeroActual = 0;
                gpsReintentos = 0;
            }
        }
        return;
    }

    if (GPS_DesencolarMensaje(gpsMensajeActual, &gpsNumeroActual, &gpsActualizaMensaje))
    {
        gpsMensajeActivo = 1;
        gpsAckRecibido = 0;
        gpsReintentos = 0;
        GPS_EnviarMensajeActual();
    }
}

void GPS_MensajeConfirmado(void)
{
    if (gpsMensajeActivo) { gpsAckRecibido = 1; }
}

void Serial_GPS(const char *string)
{
    GPS_EncolarMensaje(string);
}

void Serial_BLE(const char *string)
{
    HAL_UART_Transmit(&huart1, (uint8_t *)string, strlen(string), HAL_MAX_DELAY);
    Debug(string);
}

void Debug( const char *string )
{
#if MODO_DEBUG == 1
    // Enviamos un tag para identificar rápido en la terminal
    HAL_UART_Transmit(&huart4, (uint8_t *)"[DBG]< ", 7, HAL_MAX_DELAY);

    // Enviamos el mensaje
    HAL_UART_Transmit(&huart4, (uint8_t *)string, strlen(string), HAL_MAX_DELAY);

    HAL_UART_Transmit(&huart4, (uint8_t *)">[DBG]\r\n", 8, HAL_MAX_DELAY);
#endif
}

void MENSAJE_GPS (const char *MENJ,const char *LLEGO)
{
	sprintf(buffer, "%s%s%s%s%s", ENCABEZADO, Config.Nombre,MENJ, LLEGO, FIN_ENCBEZADO );
	Serial_GPS(buffer);
}
///------------------------------------------------------------------------------------------------- Fin Serial
///------------------------------------------------------------------------------------------------- EPROMM

void CargarDatosDesdeEEPROM(void)
{
    uint8_t guardar = 0;
    // =====================================================
    // LEER CONFIG COMPLETA
    // =====================================================
    if (HAL_I2C_Mem_Read(&hi2c1, EEPROM_I2C_ADDR, EEPROM_CONFIG_ADDR, I2C_MEMADD_SIZE_16BIT, (uint8_t*)&Config, sizeof(CONFIG_TQT), HAL_MAX_DELAY) != HAL_OK)
    { Debug("ERROR EEPROM -> DEFAULTS"); CargarDefaults(); GuardarConfig(); return; }
    // =====================================================
    // VALIDAR VERSION
    if (Config.Version == 0xFFFF)
    { Debug("VERSION INVALIDA -> DEFAULTS"); CargarDefaults(); GuardarConfig(); return; }
    if (Config.Version != VERSION_ACTUAL)
    {
        if (Config.Version == VERSION_SIN_MAP)
        {
            Config.Version = VERSION_ACTUAL;
            guardar = 1; // FW 4.1: conservar todos los campos anteriores.
        }
        else if (Config.Version == VERSION_ANTERIOR)
        {
            Config.Version = VERSION_ACTUAL;
            Config.Tiempo = Default_Tiempo;
            guardar = 1;
        }
        else if (Config.Version == VERSION_COMPATIBLE_ANTERIOR ||
                 Config.Version == VERSION_COMPATIBLE_ANTERIOR_2)
        {
            if (Config.Version == VERSION_COMPATIBLE_ANTERIOR_2) { Config.Sensores = Default_Sensores; }
            Config.Version = VERSION_ACTUAL;
            Config.SeparadorSensores = Default_SPAS;
            Config.SeparadorValor = Default_SPAV;
            Config.DebugTqt = Default_DBG;
            Config.Tiempo = Default_Tiempo;
            guardar = 1;
        }
        else
        { Debug("VERSION INVALIDA -> DEFAULTS"); CargarDefaults(); GuardarConfig(); return; }
        // Campos nuevos al final de CONFIG_TQT: no interpretar bytes viejos de EEPROM.
        Config.MapM1 = Default_MapM1;
        Config.MapM2 = Default_MapM2;
    }
    // =====================================================
    // VALIDAR MAPEO
    if (Config.MapM1 > 1) { Config.MapM1 = Default_MapM1; guardar = 1; }
    if (Config.MapM2 > 1) { Config.MapM2 = Default_MapM2; guardar = 1; }
    // VALIDAR NOMBRE
    if (Config.Nombre[0] == 0xFF || Config.Nombre[0] == 0x00)
    { snprintf(Config.Nombre, sizeof(Config.Nombre), "%s", TQT_XXX); guardar = 1; }
    // =====================================================
    // VALIDAR ENTRADAS
    if (Config.Int1 == 0xFF || Config.Int1 > Rango_Int01) { Config.Int1 = Default_Int1; guardar = 1; }
    if (Config.Int2 == 0xFF || Config.Int2 > Rango_Int02) { Config.Int2 = Default_Int2; guardar = 1; }
    if (Config.Int3 == 0xFF || Config.Int3 > Rango_Int03) { Config.Int3 = Default_Int3; guardar = 1; }
    // =====================================================
    // VALIDAR SALIDAS (0-5)
    if (Config.Out1 == 0xFF || Config.Out1 > Rango_Out01) { Config.Out1 = Default_Out1; guardar = 1; }
    if (Config.Out2 == 0xFF || Config.Out2 > Rango_Out02) { Config.Out2 = Default_Out2; guardar = 1; }
    if (Config.Out3 == 0xFF || Config.Out3 > Rango_Out03) { Config.Out3 = Default_Out3; guardar = 1; }
    // =====================================================
    // VALIDAR BLOQUEO
    if (Config.Bloqueo == 0xFF || Config.Bloqueo > Rango_Bloqueo) { Config.Bloqueo = Default_Bloqueo; guardar = 1; }
    // =====================================================
    // VALIDAR MOTOR
    if (Config.Motor == 0xFF || Config.Motor > Rango_Motor) { Config.Motor = Default_Motor; guardar = 1; }
    if (Config.Sensores == 0xFF || Config.Sensores > 1) { Config.Sensores = Default_Sensores; guardar = 1; }
    if (!SeparadorConfigValido(Config.SeparadorSensores)) { Config.SeparadorSensores = Default_SPAS; guardar = 1; }
    if (!SeparadorConfigValido(Config.SeparadorValor)) { Config.SeparadorValor = Default_SPAV; guardar = 1; }
    if (Config.SeparadorSensores == Config.SeparadorValor)
    {
        Config.SeparadorSensores = Default_SPAS;
        Config.SeparadorValor = Default_SPAV;
        guardar = 1;
    }
    if (Config.DebugTqt == 0xFF || Config.DebugTqt > 1) { Config.DebugTqt = Default_DBG; guardar = 1; }
    if (Config.Tiempo == 0xFF || Config.Tiempo > Rango_Tiempo) { Config.Tiempo = Default_Tiempo; guardar = 1; }
    // =====================================================
    // VALIDAR RESET
    if (Config.Reset == 0xFFFF) { Config.Reset = Default_Reset; guardar = 1; }
    if (Config.MovMotor == 0xFFFFFFFFUL) { Config.MovMotor = 0; guardar = 1; }
    // =====================================================
    // VALIDAR Viva
    if (Config.Viva == 0xFF || Config.Viva > Rango_Viva) { Config.Viva = Default_Viva; guardar = 1; }
    // =====================================================
    // GUARDAR SI HUBO CAMBIOS
    if (guardar) { Debug("CONFIG CORREGIDA"); GuardarConfig(); }
    // =====================================================
    // APLICAR GPIO
    HAL_GPIO_WritePin(GPIOA, OUT_1_Pin, Config.Out1);
    HAL_GPIO_WritePin(GPIOA, OUT_2_Pin, Config.Out2);
    HAL_GPIO_WritePin(GPIOB, INDICADOR_BLOQUEO_Pin, Config.Out3);
    // =====================================================
    // BLE
    sprintf(buffer, "NAME:%s\r\n", Config.Nombre);
    Serial_BLE(buffer);
    BLE_OK();
    // =====================================================
    // DEBUG
    // =====================================================
    sprintf(buffer, "\r\nCONFIG OK\r\n" "Nombre:%s\r\n" "Version:%d\r\n"  "Reset:%d\r\n", Config.Nombre, Config.Version, Config.Reset);
    Debug(buffer);
}

///------------------------------------------------------------------------------------------------- Fin de EPROMM
///------------------------------------------------------------------------------------------------- Atrack
void Mensaje_Atrack(char *comando) {
    // Verifica si el comando comienza con el prefijo correcto - $SMSG=Nombre:
	if (strncmp(comando, "$SMSG=Nombre:", 13) == 0) 		{ TQT_Nombre (comando);	}			// OK
/// --------------------------- Comando Para abrir el translock
    else if (strncmp(comando, "$SMSG=ON", 8) == 0) 			{ TQT_ON_GPS(); }					// OK
/// --------------------------- Comando Para cerrar el translock
    else if (strncmp(comando, "$SMSG=OFF", 9) == 0) 		{ TQT_OFF_GPS(); }					// OK
/// --------------------------- Comando para activar/desactivar sensores del motor
    else if (strncmp(comando, "$SMSG=MAP", 9) == 0) { TQT_Map(comando); }
    else if (strncmp(comando, "$SMSG=Sensores:", 15) == 0)	{ TQT_Sensores(comando); }			// OK
/// --------------------------- Comando para tiempo extra de espera del motor
    else if (strncmp(comando, "$SMSG=TIEMPO:", 13) == 0)	{ TQT_Tiempo(comando); }			// OK
/// --------------------------- Comando para separador entre sensores $SMSG=SPAS;|
    else if (strncmp(comando, "$SMSG=SPAS;", 11) == 0)		{ TQT_SPAS(comando); }				// OK
/// --------------------------- Comando para separador entre sensor y valor $SMSG=SPAV;;
    else if (strncmp(comando, "$SMSG=SPAV;", 11) == 0)		{ TQT_SPAV(comando); }				// OK
/// --------------------------- Comando para modo debug TQT
    else if (strncmp(comando, "$SMSG=DBG_TQT;", 14) == 0)	{ TQT_DBG_TQT(comando); }			// OK
/// --------------------------- Comando de bloqueo $SMSG=Bloqueo:
    else if (strncmp(comando, "$SMSG=Bloqueo:", 14) == 0)	{ TQT_Bloqueo (comando); }			// OK
/// --------------------------- Comando de Reset de fabrica
	else if (strncmp(comando, "$SMSG=Reset_44", 14) == 0) 	{ TQT_Reset_General(); }			// OK
/// --------------------------- Comando de Reset del ble
    else if (strncmp(comando, "$SMSG=Reset_BLE", 15) == 0)	{ TQT_Reset_Ble (); }				// OK
/// --------------------------- Comando de Reset de la tarjeta
	else if (strncmp(comando, "$SMSG=Reset", 11) == 0) 		{ Reset_gps(0); }					// OK
	/// --------------------------- Comando para Activar y desactivar salida 1
	else if (strncmp(comando, "$SMSG=OUT_1:", 12) == 0) 		{ TQT_Out_1(comando); }			// OK
/// --------------------------- Comando para Activar y desactivar salida 2
	else if (strncmp(comando, "$SMSG=OUT_2:", 12) == 0) 		{ TQT_Out_2(comando); }			// OK
/// --------------------------- Comando para Activar y desactivar Entrada 1
	else if (strncmp(comando, "$SMSG=INT_1:", 12) == 0) 		{ TQT_Int_1(comando); }			//
/// --------------------------- Comando para Activar y desactivar Entrada 2
	else if (strncmp(comando, "$SMSG=INT_2:", 12) == 0) 		{ TQT_Int_2(comando); }			//
/// --------------------------- Comando para Activar y desactivar Entrada 2
	else if (strncmp(comando, "$SMSG=INT_3:", 12) == 0) 		{ TQT_Int_3(comando); }			//
/// --------------------------- Comando de Status
	else if (strncmp(comando, "$SMSG=Status_Motor", 18) == 0)	{ TQTR_Status_Motor(); }		//
/// --------------------------- Comando Para solicitar el MAC del BLE
    else if (strncmp(comando, "$SMSG=MAC", 9) == 0) 											// OK
    {
        Debug("OK - $SMSG=MAC\r\n");
        BT_DELAY();
        BLE_MAC();
        BT_DELAY();
        EnviarEstadoConfig();
        EnviarSeparadoresConfig();
    }
/// --------------------------- Comando de Status
	else if (strncmp(comando, "$SMSG=Status", 12) == 0)											// OK
	{
		BT_DELAY();
		BLE_MAC();
		BT_DELAY();
		EnviarEstadoConfig();
		EnviarSeparadoresConfig();
	}
	else if (strncmp(comando, "$OK", 3) == 0 || strncmp(comando, "OK", 2) == 0) { GPS_MensajeConfirmado(); Debug("Comando OK");
	}
/// --------------------------- Error de comando
    else { ActualizarError(1); GuardarConfig(); EnviarEstadoConfig(); Debug("Comando no valido"); }
}
///------------------------------------------------------------------------------------------------- Fin Atrack
///------------------------------------------------------------------------------------------------- BLE
void BT_DELAY(void)          // Funcion para el borrado de datos del bluetooth
{
  HAL_Delay(40);                  // Retardo para la buena lectura
  LL = 40;                    // Se indican cuantas veces se leera el bluetooth
  while(LL) { ProcessSerialData1(); HAL_Delay(10); LL--; }
}

void BLE_MAC (void)
{
	Serial_BLE("MAC\r\n");
	HAL_Delay(20);
	MAC_BLE[17] = 0;
	int MB=0;
	int Ll = 400;                    // Se indican cuantas veces se leera el bluetooth
	while(Ll)
	{                  // Se entra a leer las valores del bluetooth
	  if (rxReadIndex1 != rxWriteIndex1)        // Se pregunta si hay datos en el bluetooth   //  AT$SMSG=1,0,"ON"
	  {
		 MAC_BLE[MB] = rxBuffer1[rxReadIndex1];    // Se lee el valor de entrada
		 rxReadIndex1 = (rxReadIndex1 + 1) % RX_BUFFER_SIZE;            // Se pregunta si hay datos en el bluetooth
		 MB++;
		 if (MB == 17)
		 {
			 char stringX[32];
			 sprintf(stringX, "MAC %s\r\n",MAC_BLE);
			 Debug(stringX);
			 Ll=1;
		}
	 }
	 HAL_Delay(10);                // Retardo antes de la siguiente lectura
	 Ll--;                     // Se resta un valor al contador.
	}
}

int BLE_OK(void)
{
    HAL_Delay(20);
    char MAC_BLE1[8] = {0};  // Aumentamos tamaño por seguridad
    int MB = 0;
    int Ll = 400;
    while (Ll)
    {
        if (rxReadIndex1 != rxWriteIndex1)
        {
            char c = rxBuffer1[rxReadIndex1];
            rxReadIndex1 = (rxReadIndex1 + 1) % RX_BUFFER_SIZE;
            if (MB < sizeof(MAC_BLE1) - 1) {
                MAC_BLE1[MB++] = c;
                MAC_BLE1[MB] = '\0';  // Asegura terminación
            }
            if (c == '\n') {
                // Limpia espacios, \r y \n
                for (int i = 0; i < MB; i++) {
                    if (MAC_BLE1[i] == '\r' || MAC_BLE1[i] == '\n')
                        MAC_BLE1[i] = '\0';
                }
                if (strcmp(MAC_BLE1, "OK") == 0) { Debug("OK"); return 1; }
                else { Debug("ERROR"); return 0; }
            }
        }

        HAL_Delay(10);
        Ll--;
    }
    return 0;  // Si se agota el tiempo, también es error
}

int BLE_Check_Viva(void)
{
    static uint8_t errorCount = 0;  // Contador de errores consecutivos
    Serial_BLE("VIVO\r\n");
    HAL_Delay(20);
    char respuesta[16] = {0};
    int idx = 0;
    int timeout = 200; // 200 * 10ms = 2s de espera máxima
    while (timeout--)
    {
        if (rxReadIndex1 != rxWriteIndex1)
        {
            char c = rxBuffer1[rxReadIndex1];
            rxReadIndex1 = (rxReadIndex1 + 1) % RX_BUFFER_SIZE;

            if (idx < sizeof(respuesta) - 1) { respuesta[idx++] = c; respuesta[idx] = '\0'; }

            if (c == '\n') // Fin de línea detectado
            {
                for (int i = 0; i < idx; i++) {  if (respuesta[i] == '\r' || respuesta[i] == '\n') respuesta[i] = '\0'; }
                // Comparar respuesta
                if (strcmp(respuesta, "SIMON") == 0) { Debug("BLE OK"); return 1; }
                else
                {
                	errorCount++;
                	Debug("BLE Respuesta incorrecta");
                	if (errorCount >= 5)
					{
						Debug("ERROR: 5 fallos consecutivos en BLE");
						Reset_gps(1);
						errorCount = 0; // Opcional: reset para volver a contar
					}
                    return 0;
                }
            }
        }
        HAL_Delay(10);
    }
    // Timeout
    errorCount++;
	Debug("BLE Timeout\r\n");

	if (errorCount >= 5)
	{
		Debug("ERROR: 5 fallos consecutivos en BLE");
		Reset_gps(1);
		errorCount = 0; // Opcional
	}
	return 0;
}

void MENSAJE_BLUETOOTH  ( char *comando )
{
	if (strncmp(comando, "PPON", 4) == 0)
	{
		if (Config.DebugTqt) { MENSAJE_GPS(OPEN_1, NombreOrigenMensaje(BLUE)); }
		APERTURA(BLUE);                           // Se llama a la funcion de apertura de translock
	}
	else if (strncmp(comando, "POFF", 4) == 0)
	{
		if (Config.DebugTqt) { MENSAJE_GPS(CLOSED_1, NombreOrigenMensaje(BLUE)); }
		CIERRE(BLUE);                             // Se manda a llamar la funcion de cierre
	}
	else if (strncmp(comando, "RST4", 4) == 0)
	{
		TQT_Reset_General();                             // Se manda a llamar la funcion de cierre
	}
	else if (strncmp(comando, "I1_1", 4) == 0)
	{
		TQT_Int_1("$SMSG=INT_1:2\r\n");                     // Se manda a llamar la funcion para activar la entrada 1
	}
	else if (strncmp(comando, "I1_0", 4) == 0)
	{
		TQT_Int_1("$SMSG=INT_1:0\r\n");                     // Se manda a llamar la funcion para activar la entrada 1
	}
	else if (strncmp(comando, "I2_1", 4) == 0)
	{
		TQT_Int_2("$SMSG=INT_2:2\r\n");                     // Se manda a llamar la funcion para activar la entrada 1
	}
	else if (strncmp(comando, "I2_0", 4) == 0)
	{
		TQT_Int_2("$SMSG=INT_2:0\r\n");                     // Se manda a llamar la funcion para activar la entrada 1
	}
	else
	{
		Debug(comando);
		ActualizarError(2); GuardarConfig(); EnviarEstadoConfig();
	}
}
///------------------------------------------------------------------------------------------------- BLE FIN
///------------------------------------------------------------------------------------------------- RElay's
void RELAY_INICIO (void)
{
	RELAY_1_ON;
	RELAY_2_ON;
	LED_R_ON;
	HAL_Delay(500);
	RELAY_1_OFF;
	RELAY_2_OFF;
	LED_R_OFF;
	LED_G_ON;
	buzzer_on();
	HAL_Delay(500);
	RELAY_1_ON;
	RELAY_2_ON;
	LED_G_OFF;
	LED_B_ON;
	buzzer_off();
	HAL_Delay(500);
	RELAY_1_OFF;
	RELAY_2_OFF;
	LED_B_OFF;
	HAL_Delay(500);
}

void buzzer_on(void) {
    HAL_TIM_Base_Start_IT(&htim4);
}

void buzzer_off(void)
{
    HAL_TIM_Base_Stop_IT(&htim4);  // Detiene el cambio de estado
    HAL_Delay(20);
    HAL_GPIO_WritePin(GPIOC,BOCINA_Pin, GPIO_PIN_RESET); // Asegura que quede en LOW
}

void APERTURA(uint8_t LLEGO)
{
	P_B = LLEGO;
    if (Config.Sensores == 0 && mis_lecturas_adc[IDX_SENSOR_APERTURA] < UMBRAL_SENSOR)
    {
        if (Config.DebugTqt) { MENSAJE_GPS(OPEN, NombreOrigenMensaje(LLEGO)); }
        CambiarEstadoMotor(ESTADO_ABIERTO);
        CambiarEstadoMotor(ESTADO_ESPERA);
        return;
    }
    bandera_limite_alcanzado = 0;
    etapa_apertura = 0;
    CambiarEstadoMotor(ESTADO_ABRIENDO);
    if (flag_sobrecorriente == 0) { MOTOR_ACCION_ABRIR(); }
    uint32_t tiempo_inicio = HAL_GetTick();
    uint32_t tiempo_espera_motor = TiempoMotorEsperaMs();
    uint8_t exito = 0;
    while ((HAL_GetTick() - tiempo_inicio) < tiempo_espera_motor)
    {
        if (flag_sobrecorriente == 1) { exito = 0; break; } // La falla tiene prioridad sobre el limite
        if (bandera_limite_alcanzado == 1) { exito = 1; break; }
        HAL_Delay(10);
    }
    if (Config.Sensores == 1 && flag_sobrecorriente == 0) { exito = 1; } // Éxito si es control por tiempo
    if (flag_sobrecorriente == 0) { HAL_Delay(100); }
    if (flag_sobrecorriente != 0) { exito = 0; }
    MOTOR_APAGAR_TODO();
    HAL_Delay(Tiempo_es_mem);
    memoria_sensor_1 = (mis_lecturas_adc[IDX_SENSOR_APERTURA] < UMBRAL_SENSOR) ? 1 : 0;
    memoria_sensor_2 = (mis_lecturas_adc[IDX_SENSOR_CIERRE] < UMBRAL_SENSOR) ? 1 : 0;
    if (exito == 1)
    {
        INDIC_ON;
        RegistrarMovimientoMotor();
        if (Config.DebugTqt) { MENSAJE_GPS(OPEN, NombreOrigenMensaje(LLEGO)); }
        CambiarEstadoMotor(ESTADO_ABIERTO);
        CambiarEstadoMotor(ESTADO_ESPERA);
    }
    else
    {
        ActualizarError(3);
        GuardarConfig();
        if (Config.DebugTqt) { MENSAJE_GPS(ERROR_O, NombreOrigenMensaje(LLEGO)); }
        CambiarEstadoMotor(ESTADO_ERROR);
        CambiarEstadoMotor(ESTADO_ESPERA);
    }
}

void CIERRE(uint8_t LLEGO)
{
	P_B = LLEGO;
    if (Config.Sensores == 0 && mis_lecturas_adc[IDX_SENSOR_CIERRE] < UMBRAL_SENSOR)
    {
        if (Config.DebugTqt) { MENSAJE_GPS(CLOSED, NombreOrigenMensaje(LLEGO)); }
        CambiarEstadoMotor(ESTADO_CERRADO);
        CambiarEstadoMotor(ESTADO_ESPERA);
        return;
    }
    bandera_limite_alcanzado = 0;
    CambiarEstadoMotor(ESTADO_CERRANDO);
    if (flag_sobrecorriente == 0) { MOTOR_ACCION_CERRAR(); }
    uint32_t tiempo_inicio = HAL_GetTick();
    uint32_t tiempo_espera_motor = TiempoMotorEsperaMs();
    uint8_t exito = 0;
    while ((HAL_GetTick() - tiempo_inicio) < tiempo_espera_motor)
    {
        if (flag_sobrecorriente == 1) { exito = 0; break; } // La falla tiene prioridad sobre el limite
        if (bandera_limite_alcanzado == 1) { exito = 1; break; }
        HAL_Delay(10);
    }
    if (Config.Sensores == 1 && flag_sobrecorriente == 0) { exito = 1; } // Éxito si es control por tiempo
    if (flag_sobrecorriente == 0) { HAL_Delay(200); }
    if (flag_sobrecorriente != 0) { exito = 0; }
    MOTOR_APAGAR_TODO();
    HAL_Delay(Tiempo_es_mem);
    memoria_sensor_1 = (mis_lecturas_adc[IDX_SENSOR_APERTURA] < UMBRAL_SENSOR) ? 1 : 0;
    memoria_sensor_2 = (mis_lecturas_adc[IDX_SENSOR_CIERRE] < UMBRAL_SENSOR) ? 1 : 0;
    if (exito == 1)
    {
        INDIC_OFF;
        RegistrarMovimientoMotor();
        if (Config.DebugTqt) { MENSAJE_GPS(CLOSED, NombreOrigenMensaje(LLEGO)); }
        CambiarEstadoMotor(ESTADO_CERRADO);
        CambiarEstadoMotor(ESTADO_ESPERA);
    }
    else
    {
        ActualizarError(4);
        GuardarConfig();
        if (Config.DebugTqt) { MENSAJE_GPS(ERROR_C, NombreOrigenMensaje(LLEGO)); }
        CambiarEstadoMotor(ESTADO_ERROR);
        CambiarEstadoMotor(ESTADO_ESPERA);
    }
}


///------------------------------------------------------------------------------------------------- FIN ADC
///------------------------------------------------------------------------------------------------- Otras
void Reset_gps(int8_t LX)
{
	Debug("OK - Reset  del GPS o BLE");
	if ( LX == 0)
	{
		sprintf(buffer, "%s%s - Se realizara reset%s", ENCABEZADO, Config.Nombre, FIN_ENCBEZADO );
		Serial_GPS_Directo(buffer);
		if ( Config.Bloqueo != 0 ) { sprintf(buffer, "AT$OUTC=%d,1,20\r\n",Config.Bloqueo ); Serial_GPS_Directo(buffer); HAL_Delay(5000); }
		sprintf(buffer, "%s%s - Reset realizado por software%s", ENCABEZADO, Config.Nombre, FIN_ENCBEZADO );
		Serial_GPS_Directo(buffer);
		NVIC_SystemReset();
	}
	else { ActualizarError(5); GuardarConfig(); EnviarEstadoConfig(); TQT_Reset_Ble(); Debug("error de comunicacion BLE, se reinicia"); }
}

void TQT_Bloqueo(char *comando)
{
    uint8_t valor = atoi(&comando[14]);
    if (valor <= Rango_Bloqueo)
    {
        Config.Bloqueo = valor; GuardarConfig(); EnviarEstadoConfig();
        sprintf(buffer, "%s%s - Bloqueo OUT%d guardado%s", ENCABEZADO, Config.Nombre, Config.Bloqueo, FIN_ENCBEZADO);
        Serial_GPS(buffer);
    }
    else
    {
    	ActualizarError(6); GuardarConfig(); EnviarEstadoConfig();
    	Debug("Valor invalido solo 0-4");
    }
}

void TQT_Reset_General(void)
{
    // GUARDAR BLOQUEO ACTUAL
    uint8_t bloqueo_anterior = Config.Bloqueo;
    // CARGAR DEFAULTS
    CargarDefaults();
    // GUARDAR CONFIG COMPLETA
    GuardarConfig();
    Debug("Reset realizado: Valores de fabrica");
    // DESACTIVAR SALIDA BLOQUEO SI EXISTIA
    if (bloqueo_anterior != 0)
    { sprintf(buffer, "AT$OUTC=%d,1,20\r\n", bloqueo_anterior); Serial_GPS_Directo(buffer); HAL_Delay(5000); }
    // REINICIO MCU
    NVIC_SystemReset();
}

void TQT_Reset_Ble (void)
{
    Debug("OK - $SMSG=Reset_BLE");
    BLE_01_OFF;
    ActualizarError(7); GuardarConfig(); EnviarEstadoConfig();
    Debug("Se realizara reset del bluetooth");
    HAL_Delay(2000);
    BLE_01_ON;
}

void TQT_Nombre (char *comando)
{
    char nombre_recibido[MAX_NOMBRE_LEN + 1] = {0}; // buffer temporal (espacio extra por si llega largo)
    strncpy(nombre_recibido, comando + 13, MAX_NOMBRE_LEN); // copiamos un poco más
    nombre_recibido[MAX_NOMBRE_LEN] = '\0';
    // Eliminar \r o \n al final si existen
    size_t len = strlen(nombre_recibido);
    while (len > 0 && (nombre_recibido[len - 1] == '\r' || nombre_recibido[len - 1] == '\n')) { nombre_recibido[--len] = '\0'; }
    // Eliminar espacios iniciales
    char *ptr = nombre_recibido;
    while (*ptr == ' ') ptr++;
    if (*ptr != '\0')
    {
        snprintf(Config.Nombre,sizeof(Config.Nombre),"%s",ptr);
        GuardarConfig();
        BT_DELAY();
        sprintf(buffer, "NAME:%s\r\n", Config.Nombre);
        Serial_BLE(buffer);
        if ( BLE_OK() ) { ActualizarError(9); GuardarConfig(); EnviarEstadoConfig(); Debug("Se guarda el nombre correctamente"); }
        else {	ActualizarError(8); GuardarConfig(); EnviarEstadoConfig(); Debug("Error al guardar el nombre"); }
    }
    else
    {
    	snprintf(Config.Nombre, sizeof(Config.Nombre), "%s", TQT_XXX);
    	GuardarConfig();
        BT_DELAY();
        sprintf(buffer,"NAME:%s\r\n",Config.Nombre);
        Serial_BLE(buffer);
        if ( BLE_OK() ) {
			sprintf(buffer, "%s%s - Nombre vacio, Se asigna por defecto: %s%s", ENCABEZADO, Config.Nombre, Config.Nombre, FIN_ENCBEZADO );
			Serial_GPS(buffer);
        }
        else { ActualizarError(10); GuardarConfig(); EnviarEstadoConfig(); Debug("Error Nombre no se pudo guardar"); }

    }
}

///------------------------------------------------------------------------------------------------- Mapeo de entradas FW 4.3
GPIO_PinState NivelEntradaADC(uint16_t lectura, GPIO_PinState anterior)
{
    if (lectura >= ADC_ENTRADA_ALTO) { return GPIO_PIN_SET; }
    if (lectura <= ADC_ENTRADA_BAJO) { return GPIO_PIN_RESET; }
    return anterior;
}

GPIO_PinState LeerEntradaADC(uint8_t entrada)
{
    if (entrada == 1)
    {
        nivel_entrada_1 = NivelEntradaADC(mis_lecturas_adc[IDX_ENTRADA_1], nivel_entrada_1);
        return nivel_entrada_1;
    }
    nivel_entrada_2 = NivelEntradaADC(mis_lecturas_adc[IDX_ENTRADA_2], nivel_entrada_2);
    return nivel_entrada_2;
}

void ReiniciarEntradasMap(uint8_t pares)
{
    // En arranque/cambio, una lectura en la banda intermedia parte de nivel alto (inactivo).
    // El llamador protege el cambio de mapa y estas memorias frente a TIM3.
    if (pares & 1U)
    {
        nivel_entrada_1 = GPIO_PIN_SET;
        INT_S1 = LeerEntradaADC(1);
        INT_S1_ANT = INT_S1;
        stableCount1 = 0;
        memoria_sensor_2 = (mis_lecturas_adc[IDX_SENSOR_CIERRE] < UMBRAL_SENSOR) ? 1 : 0;
    }
    if (pares & 2U)
    {
        nivel_entrada_2 = GPIO_PIN_SET;
        INT_S2 = LeerEntradaADC(2);
        INT_S2_ANT = INT_S2;
        stableCount2 = 0;
        memoria_sensor_1 = (mis_lecturas_adc[IDX_SENSOR_APERTURA] < UMBRAL_SENSOR) ? 1 : 0;
    }
}

uint8_t FinMapaValido(const char *fin)
{
    if (*fin == '\r') { fin++; }
    if (*fin == '\n') { fin++; }
    return (*fin == '\0');
}

void EnviarMapaConfig(void)
{
    snprintf(buffer, sizeof(buffer), "%sMAP M1:%u M2:%u%s", ENCABEZADO,
             (unsigned int)Config.MapM1, (unsigned int)Config.MapM2, FIN_ENCBEZADO);
    Serial_GPS(buffer);
}

void TQT_Map(char *comando)
{
    uint8_t par = 0;
    if (strncmp(comando, "$SMSG=MAP?", 10) == 0 && FinMapaValido(&comando[10]))
    {
        EnviarMapaConfig();
        return;
    }
    if (strncmp(comando, "$SMSG=MAP_M1:", 13) == 0) { par = 1; }
    else if (strncmp(comando, "$SMSG=MAP_M2:", 13) == 0) { par = 2; }
    if (par == 0 || (comando[13] != '0' && comando[13] != '1') || !FinMapaValido(&comando[14]))
    {
        snprintf(buffer, sizeof(buffer), "%sMAP ERROR: COMANDO INVALIDO%s", ENCABEZADO, FIN_ENCBEZADO);
        Serial_GPS(buffer);
        return;
    }

    uint8_t valor = (uint8_t)(comando[13] - '0');
    uint8_t anterior = (par == 1) ? Config.MapM1 : Config.MapM2;
    if (valor == anterior) { EnviarMapaConfig(); return; }
    // TIM3 puede marcar ESPERA antes de apagar los reles: comprobar tambien las salidas.
    if (estado_actual_motor != ESTADO_ESPERA ||
        HAL_GPIO_ReadPin(GPIOA, R_1_Pin) != GPIO_PIN_RESET ||
        HAL_GPIO_ReadPin(GPIOA, R_2_Pin) != GPIO_PIN_RESET)
    {
        snprintf(buffer, sizeof(buffer), "%sMAP ERROR: MOTOR ACTIVO%s", ENCABEZADO, FIN_ENCBEZADO);
        Serial_GPS(buffer);
        return;
    }

    CONFIG_TQT nueva = Config;
    if (par == 1) { nueva.MapM1 = valor; }
    else { nueva.MapM2 = valor; }
    // Guardar antes de aplicar: si falla EEPROM, conservar el mapa vigente.
    if (HAL_I2C_Mem_Write(&hi2c1, EEPROM_I2C_ADDR, EEPROM_CONFIG_ADDR, I2C_MEMADD_SIZE_16BIT,
                          (uint8_t*)&nueva, sizeof(nueva), HAL_MAX_DELAY) != HAL_OK)
    {
        snprintf(buffer, sizeof(buffer), "%sMAP ERROR: EEPROM%s", ENCABEZADO, FIN_ENCBEZADO);
        Serial_GPS(buffer);
        return;
    }
    HAL_Delay(5); // Completar el ciclo de escritura antes del siguiente comando.
    uint32_t primask = __get_PRIMASK();
    __disable_irq();
    if (par == 1) { Config.MapM1 = valor; }
    else { Config.MapM2 = valor; }
    ReiniciarEntradasMap(par);
    TQTR_Indicador_Motor();
    __set_PRIMASK(primask);
    EnviarMapaConfig();
}

void TQT_Sensores(char *comando)
{
    char valor = comando[15];
    char fin = comando[16];
    if ((valor == '0' || valor == '1') && (fin == '\r' || fin == '\n' || fin == '\0'))
    {
        Config.Sensores = (uint8_t)(valor - '0');
        GuardarConfig();
        EnviarEstadoConfig();
    }
    else
    {
        ActualizarError(19);
        GuardarConfig();
        EnviarEstadoConfig();
        Debug("Error Sensores solo 0 o 1");
    }
}

void TQT_Tiempo(char *comando)
{
    char *fin = NULL;
    unsigned long valor = strtoul(&comando[13], &fin, 10);

    if (fin != &comando[13] && valor <= Rango_Tiempo && FinComandoValido(*fin))
    {
        Config.Tiempo = (uint8_t)valor;
        GuardarConfig();
        EnviarEstadoConfig();
    }
    else
    {
        ActualizarError(23);
        GuardarConfig();
        EnviarEstadoConfig();
        Debug("Error TIEMPO solo acepta 0 a 10 segundos");
    }
}

void TQT_SPAS(char *comando)
{
    char valor = comando[11];
    char fin = comando[12];
    if (SeparadorConfigValido(valor) && valor != SeparadorValorConfig() && FinComandoValido(fin))
    {
        Config.SeparadorSensores = valor;
        GuardarConfig();
        EnviarEstadoConfig();
        EnviarSeparadoresConfig();
    }
    else
    {
        ActualizarError(20);
        GuardarConfig();
        EnviarEstadoConfig();
        Debug("Error SPAS separador invalido");
    }
}

void TQT_SPAV(char *comando)
{
    char valor = comando[11];
    char fin = comando[12];
    if (SeparadorConfigValido(valor) && valor != SeparadorSensoresConfig() && FinComandoValido(fin))
    {
        Config.SeparadorValor = valor;
        GuardarConfig();
        EnviarEstadoConfig();
        EnviarSeparadoresConfig();
    }
    else
    {
        ActualizarError(21);
        GuardarConfig();
        EnviarEstadoConfig();
        Debug("Error SPAV separador invalido");
    }
}

void TQT_DBG_TQT(char *comando)
{
    char valor = comando[14];
    char fin = comando[15];
    if ((valor == '0' || valor == '1') && FinComandoValido(fin))
    {
        Config.DebugTqt = (uint8_t)(valor - '0');
        GuardarConfig();
        EnviarEstadoConfig();
    }
    else
    {
        ActualizarError(22);
        GuardarConfig();
        EnviarEstadoConfig();
        Debug("Error DBG_TQT solo acepta 0 o 1");
    }
}

void TQT_ON_GPS (void)
{
	Debug("OK - $SMSG=ON");
	if (Config.DebugTqt) { MENSAJE_GPS(OPEN_1, NombreOrigenMensaje(PLAT)); }
	APERTURA(PLAT);
}

void TQT_OFF_GPS (void)
{
	Debug("OK - $SMSG=OFF");
	if (Config.DebugTqt) { MENSAJE_GPS(CLOSED_1, NombreOrigenMensaje(PLAT)); }
	CIERRE(PLAT);
}

void TQT_Out_1(char *comando)
{
    uint8_t valor = atoi(&comando[12]);
    if (valor <= 1 && comando[13] == '\r')
    {
        Config.Out1 = valor;
        HAL_GPIO_WritePin(GPIOA, OUT_2_Pin, Config.Out1);
        GuardarConfig();
        EnviarEstadoConfig();
    }
    else { ActualizarError(11); GuardarConfig(); EnviarEstadoConfig(); Debug("Error dato mayo de 1 o menos de 0"); }
}

void TQT_Out_2(char *comando)
{
    uint8_t valor = atoi(&comando[12]);
    // VALIDAR VALOR
    if (valor <= 1 && comando[13] == '\r')
    {
        Config.Out2 = valor;
        HAL_GPIO_WritePin(GPIOA, OUT_1_Pin, Config.Out2);
        GuardarConfig();
        EnviarEstadoConfig();
    }
    else { ActualizarError(11); GuardarConfig(); EnviarEstadoConfig(); Debug("Error dato mayo de 1 o menos de 0"); }
}

void TQT_Int_1(char *comando)
{   uint8_t valor = atoi(&comando[12]);
    if (valor <= 2 && comando[13] == '\r')
    {   Config.Int1 = valor;
        GuardarConfig();
        EnviarEstadoConfig();
    }
    else if (valor == 3 && comando[13] == '\r')
    {
        INT_S1 = LeerEntradaADC(1);
        EnviarEstadoConfig();
    }
    else { ActualizarError(12); GuardarConfig(); EnviarEstadoConfig(); Debug("Error dato mayo de 3 o menos de 0"); }
}

void TQT_Int_2(char *comando)
{   uint8_t valor = atoi(&comando[12]);
    if (valor <= 2 && comando[13] == '\r')
    {   Config.Int2 = valor;
        GuardarConfig();
        EnviarEstadoConfig();
    }
    else if (valor == 3 && comando[13] == '\r')
    {
        INT_S2 = LeerEntradaADC(2);
        EnviarEstadoConfig();
    }
    else { ActualizarError(12); GuardarConfig(); EnviarEstadoConfig(); Debug("Error dato mayo de 3 o menos de 0"); }
}

void TQT_Int_3(char *comando)
{   uint8_t valor = atoi(&comando[12]);
    if (valor <= 2 && comando[13] == '\r')
    {   Config.Int3 = valor;
        GuardarConfig();
        EnviarEstadoConfig();
    }
    else if (valor == 3 && comando[13] == '\r')
    {
        INT_S3 = HAL_GPIO_ReadPin(GPIOB, INT_3_Pin);
        EnviarEstadoConfig();
    }
    else { ActualizarError(12); GuardarConfig(); EnviarEstadoConfig(); Debug("Error dato mayo de 3 o menos de 0"); }
}

void TQTR_Status_Motor(void)
{   uint8_t sensor_apertura = (mis_lecturas_adc[IDX_SENSOR_APERTURA] < UMBRAL_SENSOR) ? 1 : 0;
    uint8_t sensor_cierre   = (mis_lecturas_adc[IDX_SENSOR_CIERRE] < UMBRAL_SENSOR) ? 1 : 0;
    // -----------------------------------------------------
    if (sensor_apertura == 1 && sensor_cierre   == 0)
    {
        sprintf(buffer, "%s%s - El perno esta Desbloqueado%s", ENCABEZADO, Config.Nombre, FIN_ENCBEZADO);
    }
    else if (sensor_apertura == 0 && sensor_cierre   == 1)
    {
        sprintf(buffer, "%s%s - El perno esta Bloqueado%s", ENCABEZADO, Config.Nombre, FIN_ENCBEZADO);
    }
    else if (sensor_apertura == 1 && sensor_cierre   == 1)
    {
        sprintf(buffer, "%s%s - ERROR: Ambos sensores activados%s", ENCABEZADO, Config.Nombre, FIN_ENCBEZADO);
    }
    else
    {
        sprintf(buffer, "%s%s - El perno esta en MOVIMIENTO%s", ENCABEZADO, Config.Nombre, FIN_ENCBEZADO);
    }
    Serial_GPS(buffer);
}

void TQTR_Indicador_Motor (void)
{
	// Usamos el índice mapeado
	    uint8_t sensor_apertura = (mis_lecturas_adc[IDX_SENSOR_APERTURA] < UMBRAL_SENSOR) ? 1 : 0;
	    uint8_t sensor_cierre   = (mis_lecturas_adc[IDX_SENSOR_CIERRE] < UMBRAL_SENSOR) ? 1 : 0;
	    Config.S_OFF = sensor_apertura;
	    Config.S_ON = sensor_cierre;
    // Lógica de estados
    if (sensor_apertura == 1 && sensor_cierre == 0)
    {
        // Está tocando el sensor de apertura -> Perno Adentro (Abierto)
    	INDIC_ON;
    }
    if (sensor_apertura == 0 && sensor_cierre == 1)
    {
        // Está tocando el sensor de cierre -> Perno Afuera (Cerrado)
    	INDIC_OFF;
    }
    Config.Out3 = HAL_GPIO_ReadPin(GPIOB,INDICADOR_BLOQUEO_Pin);
}
///------------------------------------------------------------------------------------------------- Fin Otros

void CargarDefaults(void)			// Carga la informacion por defecto
{
	Config.Version = VERSION_ACTUAL;	// VERSION
	Config.Int1		= Default_Int1;		// ENTRADA 1
	Config.Int2 	= Default_Int2;		// ENTRADA 2
	Config.Int3 	= Default_Int3;		// ENTRADA 3
	Config.Out1 	= Default_Out1;		// SALIDA  1
	Config.Out2 	= Default_Out2;		// SALIDA  2
	Config.Out3 	= Default_Out3;		// SALIDA  3
	Config.S_ON 	= Default_S_ON;		//
	Config.S_OFF 	= Default_S_OFF;	//
	Config.Bloqueo 	= Default_Bloqueo;	// Que salida se usara para el bloqueo de la unidad
	Config.Motor 	= Default_Motor;	// Se lleva el valor para saber cual sera el limite de corriente de proteccion 5A, 8A, 10A o nulo
	Config.Sensores = Default_Sensores;	// 0 usa sensores de motor, 1 trabaja por tiempo
	Config.SeparadorSensores = Default_SPAS;
	Config.SeparadorValor = Default_SPAV;
	Config.DebugTqt = Default_DBG;
	Config.Tiempo = Default_Tiempo;
    Config.MapM1 = Default_MapM1;
    Config.MapM2 = Default_MapM2;
	Config.Viva 	= Default_Viva;		// default del estado vivo
	Config.Error 	= Default_Error;	// default del estado de error
	Config.Reset 	= Default_Reset;	// Se lleva la cuenta de cada vez que se reinicia o arranca la tarjeta para saber cuantas veces se usaron
	Config.MovMotor = 0;				// Cuenta de movimientos reales del motor
    // ---------------- NOMBRE ----------------
    snprintf(Config.Nombre, sizeof(Config.Nombre), "%s", TQT_XXX);
    sprintf(buffer, "NAME:%s\r\n", Config.Nombre);
    Serial_BLE(buffer);
    BLE_OK();
}

void GuardarConfig(void)
{
    HAL_I2C_Mem_Write(&hi2c1, EEPROM_I2C_ADDR, EEPROM_CONFIG_ADDR, I2C_MEMADD_SIZE_16BIT, (uint8_t*)&Config, sizeof(CONFIG_TQT), HAL_MAX_DELAY);
//    HAL_Delay(5);
}

void LeerConfig(void)
{
    HAL_I2C_Mem_Read(&hi2c1, EEPROM_I2C_ADDR, EEPROM_CONFIG_ADDR, I2C_MEMADD_SIZE_16BIT, (uint8_t*)&Config, sizeof(CONFIG_TQT), HAL_MAX_DELAY);
}

void DATOS(void)
{
	  sprintf(buffer, "Nombre: %s\r\n"
			  "VER: %s\r\n"
			  "HW: %s\r\n"
			  "Bloqueo: %d\r\n"
	          "Mac: %s\r\n"
	          "Out_1:%d\r\n"
	          "Out_2:%d\r\n"
	          "Out_3:%d\r\n"
	          "Int_1:%d\r\n"
	          "Int_2:%d\r\n"
	          "Int_3:%d\r\n"
	          "Motor:%d\r\n"
			  "SEN_MOT:%d\r\n"
			  "TIEMPO:%d\r\n"
			  "SPAS:%c\r\n"
			  "SPAV:%c\r\n"
			  "DBG:%d\r\n"
	          "Viva:%d\r\n"
	          "Reset:%d\r\n"
			  "MovMotor:%lu\r\n",
	          Config.Nombre,
			  VER,
			  HW,
	          Config.Bloqueo,
	          MAC_BLE,
	          Config.Out1,
	          Config.Out2,
	          Config.Out3,
	          Config.Int1,
	          Config.Int2,
	          Config.Int3,
	          Config.Motor,
			  Config.Sensores,
			  Config.Tiempo,
			  SeparadorSensoresConfig(),
			  SeparadorValorConfig(),
			  Config.DebugTqt,
	          Config.Viva,
	          Config.Reset,
			  (unsigned long)Config.MovMotor);

	  Debug(buffer);
}


//
void LimpiarMac(const char *origen, char *destino, size_t destino_len)
{
    size_t j = 0;
    if (destino_len == 0) { return; }
    for (size_t i = 0; origen[i] != '\0' && j < (destino_len - 1); i++)
    {
        if (origen[i] != ':') { destino[j++] = origen[i]; }
    }
    destino[j] = '\0';
}

void AgregarVariable(char *destino, const char *nombre, int valor, uint8_t ultimo)
{
    char temp[64];
    if (ultimo) { sprintf(temp, "%s%c%d" , nombre, SeparadorValorConfig(), valor); }
    else 		{ sprintf(temp, "%s%c%d%c", nombre, SeparadorValorConfig(), valor, SeparadorSensoresConfig()); }
    strcat(destino, temp);
}

void AgregarVariableTexto(char *destino, const char *nombre, const char *valor, uint8_t ultimo)
{
    char temp[64];
    if (ultimo) { sprintf(temp, "%s%c%s" , nombre, SeparadorValorConfig(), valor); }
    else 		{ sprintf(temp, "%s%c%s%c", nombre, SeparadorValorConfig(), valor, SeparadorSensoresConfig()); }
    strcat(destino, temp);
}

void AgregarVariableUint32(char *destino, const char *nombre, uint32_t valor, uint8_t ultimo)
{
    char temp[64];
    if (ultimo) { sprintf(temp, "%s%c%lu" , nombre, SeparadorValorConfig(), (unsigned long)valor); }
    else 		{ sprintf(temp, "%s%c%lu%c", nombre, SeparadorValorConfig(), (unsigned long)valor, SeparadorSensoresConfig()); }
    strcat(destino, temp);
}

void ActualizarError(uint8_t nuevo_error)
{
    if (Config.Error != nuevo_error)
    {
        Config.Error = nuevo_error;
        if (nuevo_error != 0) { timeoutError = HAL_GetTick(); }
    }
}

uint32_t TiempoMotorEsperaMs(void)
{
    uint8_t tiempo_extra = Config.Tiempo;

    if (tiempo_extra > Rango_Tiempo) { tiempo_extra = Default_Tiempo; }
    return Tiempo_Motor_Base + ((uint32_t)tiempo_extra * 1000UL);
}

void RegistrarMovimientoMotor(void)
{
    if (Config.MovMotor < 0xFFFFFFFFUL) { Config.MovMotor++; }
    GuardarConfig();
}

void EnviarEstadoConfig(void)
{
    char id_tarjeta[8] = {0};
    char mac_limpia[13] = {0};
    char mac_r_limpia[13] = {0};
    char sep_sensores = SeparadorSensoresConfig();
    char sep_valor = SeparadorValorConfig();
    const char *mac_ble_envio = MAC_BLE;
    const char *mac_r_envio = MAC_R;
    char *ptr = strrchr(Nombre_Tarjeta_Fijo, '_');
    if (ptr != NULL) { snprintf(id_tarjeta, sizeof(id_tarjeta), "%s", ptr + 1); }
    else { strcpy(id_tarjeta, "0000"); }
    if (sep_valor == ':')
    {
        LimpiarMac(MAC_BLE, mac_limpia, sizeof(mac_limpia));
        LimpiarMac(MAC_R, mac_r_limpia, sizeof(mac_r_limpia));
        mac_ble_envio = mac_limpia;
        mac_r_envio = mac_r_limpia;
    }
    uint8_t total = 29;
    sprintf(buffer, "AT$POST=1,0,\"S%d%c", total, sep_sensores);
    AgregarVariable(buffer, "BLK",   Config.Bloqueo, 0);
    AgregarVariable(buffer, "OUT1",  Config.Out1, 0);
    AgregarVariable(buffer, "OUT2",  Config.Out2, 0);
    AgregarVariable(buffer, "OUT3",  Config.Out3, 0);
    AgregarVariable(buffer, "INT1",  Config.Int1, 0);
    AgregarVariable(buffer, "INT2",  Config.Int2, 0);
    AgregarVariable(buffer, "INT3",  Config.Int3, 0);
    AgregarVariable(buffer, "EST1", !INT_S1, 0);
    AgregarVariable(buffer, "EST2", !INT_S2, 0);
    AgregarVariable(buffer, "EST3", !INT_S3, 0);
    AgregarVariable(buffer, "MOTOR", Config.Motor, 0);
    AgregarVariable(buffer, "SEN_MOT", Config.Sensores, 0);
    AgregarVariable(buffer, "TIEMPO", Config.Tiempo, 0);
    AgregarVariable(buffer, "DBG", Config.DebugTqt, 0);
    AgregarVariable(buffer, "VIVA",  Config.Viva, 0);
    AgregarVariable(buffer, "TQT", estado_actual_motor, 0);
    AgregarVariable(buffer, "ON", Config.S_ON, 0);
    AgregarVariable(buffer, "OFF", Config.S_OFF, 0);
    AgregarVariable(buffer, "PB", P_B, 0);
    AgregarVariable(buffer, "err", Config.Error, 0);
    AgregarVariable(buffer, "RESET", Config.Reset, 0);
    AgregarVariableTexto(buffer, "VER", VER, 0);
    AgregarVariableTexto(buffer, "HW", HW, 0);
    AgregarVariableUint32(buffer, "MOV", Config.MovMotor, 0);
    AgregarVariableTexto(buffer, "Mensaje", "0.0", 0);
    AgregarVariableTexto(buffer, "IDR", ID_R, 0);
    AgregarVariableTexto(buffer, "MACR", mac_r_envio, 0);
    sprintf(buffer + strlen(buffer), "ID%c%s%cMAC%c%s\"", sep_valor, id_tarjeta, sep_sensores, sep_valor, mac_ble_envio);
    strcat(buffer, "\r\n");
    Serial_GPS(buffer);
}

void EnviarSeparadoresConfig(void)
{
    sprintf(buffer, "%s SPAS = %c  SPAV = %c%s", ENCABEZADO, SeparadorSensoresConfig(), SeparadorValorConfig(), FIN_ENCBEZADO);
    Serial_GPS(buffer);
}

void CambiarEstadoMotor(uint8_t nuevo_estado)
{
    if (estado_actual_motor != nuevo_estado)
    {
        estado_actual_motor = nuevo_estado;
        if (Config.DebugTqt == 0) { EnviarEstadoConfig(); }
    }
}

/* USER CODE END 4 */

/**
  * @brief  This function is executed in case of error occurrence.
  * @retval None
  */
void Error_Handler(void)
{
  /* USER CODE BEGIN Error_Handler_Debug */
  /* User can add his own implementation to report the HAL error return state */
  __disable_irq();
  while (1)
  {
  }
  /* USER CODE END Error_Handler_Debug */
}
#ifdef USE_FULL_ASSERT
/**
  * @brief  Reports the name of the source file and the source line number
  *         where the assert_param error has occurred.
  * @param  file: pointer to the source file name
  * @param  line: assert_param error line source number
  * @retval None
  */
void assert_failed(uint8_t *file, uint32_t line)
{
  /* USER CODE BEGIN 6 */
  /* User can add his own implementation to report the file name and line number,
     ex: printf("Wrong parameters value: file %s on line %d\r\n", file, line) */
  /* USER CODE END 6 */
}
#endif /* USE_FULL_ASSERT */
