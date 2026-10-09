/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main.h
  * @brief          : Header for main.c file.
  *                   This file contains the common defines of the application.
  ******************************************************************************
  * @attention
  *
  * Copyright (c) 2025 STMicroelectronics.
  * All rights reserved.
  *
  * This software is licensed under terms that can be found in the LICENSE file
  * in the root directory of this software component.
  * If no LICENSE file comes with this software, it is provided AS-IS.
  *
  ******************************************************************************
  */
/* USER CODE END Header */

/* Define to prevent recursive inclusion -------------------------------------*/
#ifndef __MAIN_H
#define __MAIN_H

#ifdef __cplusplus
extern "C" {
#endif

/* Includes ------------------------------------------------------------------*/
#include "stm32f1xx_hal.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */

/* USER CODE END Includes */

/* Exported types ------------------------------------------------------------*/
/* USER CODE BEGIN ET */

/* USER CODE END ET */

/* Exported constants --------------------------------------------------------*/
/* USER CODE BEGIN EC */

/* USER CODE END EC */

/* Exported macro ------------------------------------------------------------*/
/* USER CODE BEGIN EM */

/* USER CODE END EM */

/* Exported functions prototypes ---------------------------------------------*/
void Error_Handler(void);

/* USER CODE BEGIN EFP */

/* USER CODE END EFP */

/* Private defines -----------------------------------------------------------*/
#define LED_Pin GPIO_PIN_13
#define LED_GPIO_Port GPIOC
#define BOCINA_Pin GPIO_PIN_0
#define BOCINA_GPIO_Port GPIOC
#define LED_R_Pin GPIO_PIN_1
#define LED_R_GPIO_Port GPIOC
#define LED_G_Pin GPIO_PIN_2
#define LED_G_GPIO_Port GPIOC
#define LED_B_Pin GPIO_PIN_3
#define LED_B_GPIO_Port GPIOC
#define ADC_TRANSLOCK_Pin GPIO_PIN_0
#define ADC_TRANSLOCK_GPIO_Port GPIOA
#define MOTOR_1_Pin GPIO_PIN_1
#define MOTOR_1_GPIO_Port GPIOA
#define MOTOR_2_Pin GPIO_PIN_2
#define MOTOR_2_GPIO_Port GPIOA
#define R_1_Pin GPIO_PIN_4
#define R_1_GPIO_Port GPIOA
#define R_2_Pin GPIO_PIN_5
#define R_2_GPIO_Port GPIOA
#define OUT_2_Pin GPIO_PIN_6
#define OUT_2_GPIO_Port GPIOA
#define OUT_1_Pin GPIO_PIN_7
#define OUT_1_GPIO_Port GPIOA
#define M_INT_1_Pin GPIO_PIN_4
#define M_INT_1_GPIO_Port GPIOC
#define M_INT_2_Pin GPIO_PIN_5
#define M_INT_2_GPIO_Port GPIOC
#define INT_1_Pin GPIO_PIN_0
#define INT_1_GPIO_Port GPIOB
#define INT_2_Pin GPIO_PIN_1
#define INT_2_GPIO_Port GPIOB
#define INT_3_Pin GPIO_PIN_2
#define INT_3_GPIO_Port GPIOB
#define INDICADOR_BLOQUEO_Pin GPIO_PIN_12
#define INDICADOR_BLOQUEO_GPIO_Port GPIOB
#define RE_DE_Pin GPIO_PIN_7
#define RE_DE_GPIO_Port GPIOC
#define ESP_ENABLE_Pin GPIO_PIN_8
#define ESP_ENABLE_GPIO_Port GPIOA
#define BLE_TX_Pin GPIO_PIN_9
#define BLE_TX_GPIO_Port GPIOA
#define BLE_RX_Pin GPIO_PIN_10
#define BLE_RX_GPIO_Port GPIOA
#define DEBUG_TX_Pin GPIO_PIN_10
#define DEBUG_TX_GPIO_Port GPIOC
#define DEBUG_RX_Pin GPIO_PIN_11
#define DEBUG_RX_GPIO_Port GPIOC
#define RS485_TX_Pin GPIO_PIN_12
#define RS485_TX_GPIO_Port GPIOC
#define RS485_RX_Pin GPIO_PIN_2
#define RS485_RX_GPIO_Port GPIOD
#define BLQ_EEPROM_Pin GPIO_PIN_5
#define BLQ_EEPROM_GPIO_Port GPIOB
#define SCL_EEPROM_Pin GPIO_PIN_6
#define SCL_EEPROM_GPIO_Port GPIOB
#define SDA_EEPROM_Pin GPIO_PIN_7
#define SDA_EEPROM_GPIO_Port GPIOB

/* USER CODE BEGIN Private defines */

/* USER CODE END Private defines */

#ifdef __cplusplus
}
#endif

#endif /* __MAIN_H */
