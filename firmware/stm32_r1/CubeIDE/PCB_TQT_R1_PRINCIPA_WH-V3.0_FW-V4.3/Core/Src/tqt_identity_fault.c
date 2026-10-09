#include "main.h"
#include "tqt_identity.h"
#include "tqt_identity_fault.h"
#include <stdio.h>
volatile TQT_IdentityResult tqt_identity_fault = TQT_ID_OK;
void TQT_IdentityFault(TQT_IdentityResult result) {
    tqt_identity_fault=result; /* Also visible from the CubeIDE debugger. */
    __HAL_RCC_GPIOA_CLK_ENABLE();
    __HAL_RCC_GPIOB_CLK_ENABLE();
    __HAL_RCC_GPIOC_CLK_ENABLE();
    GPIO_InitTypeDef gpio={0};
    gpio.Mode=GPIO_MODE_OUTPUT_PP; gpio.Speed=GPIO_SPEED_FREQ_LOW;
    gpio.Pull=GPIO_NOPULL;
    HAL_GPIO_WritePin(GPIOA,R_1_Pin|R_2_Pin|OUT_1_Pin|OUT_2_Pin|ESP_ENABLE_Pin,GPIO_PIN_RESET);
    gpio.Pin=R_1_Pin|R_2_Pin|OUT_1_Pin|OUT_2_Pin|ESP_ENABLE_Pin;
    HAL_GPIO_Init(GPIOA,&gpio);
    HAL_GPIO_WritePin(GPIOB,INDICADOR_BLOQUEO_Pin|BLQ_EEPROM_Pin,GPIO_PIN_RESET);
    gpio.Pin=INDICADOR_BLOQUEO_Pin|BLQ_EEPROM_Pin; HAL_GPIO_Init(GPIOB,&gpio);
    HAL_GPIO_WritePin(GPIOC,BOCINA_Pin|RE_DE_Pin|LED_Pin,GPIO_PIN_RESET);
    gpio.Pin=BOCINA_Pin|RE_DE_Pin|LED_Pin; HAL_GPIO_Init(GPIOC,&gpio);
    /* UART4 already configured by the caller: diagnostic only, no command loop. */
    extern UART_HandleTypeDef huart4;
    char text[72];
    int n=snprintf(text,sizeof text,"TQT IDENTITY ERROR %u - REPROGRAM HEX COMPLETO\r\n",(unsigned)result);
    HAL_UART_Transmit(&huart4,(uint8_t *)text,(uint16_t)n,200);
    for (;;) {
        HAL_GPIO_TogglePin(GPIOC,LED_Pin);
        /* Do not call the project's HAL_Delay: its override refreshes IWDG. */
        uint32_t start=HAL_GetTick();
        while ((uint32_t)(HAL_GetTick()-start)<250U) { }
    }
}
