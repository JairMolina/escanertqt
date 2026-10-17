#pragma once
#include <stdint.h>
#include <stddef.h>
using esp_err_t=int;
using nvs_handle_t=uint32_t;
constexpr int ESP_OK=0,ESP_FAIL=-1,ESP_ERR_NVS_NOT_FOUND=4354,NVS_READWRITE=1;
int nvs_open(const char *,int,nvs_handle_t *);
int nvs_get_blob(nvs_handle_t,const char *,void *,size_t *);
int nvs_set_blob(nvs_handle_t,const char *,const void *,size_t);
int nvs_commit(nvs_handle_t);
