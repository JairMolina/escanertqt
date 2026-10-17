#pragma once
using SemaphoreHandle_t=void *;
inline SemaphoreHandle_t xSemaphoreCreateMutex() {return reinterpret_cast<void *>(1);}
inline int xSemaphoreTake(SemaphoreHandle_t,unsigned) {return 1;}
inline int xSemaphoreGive(SemaphoreHandle_t) {return 1;}
