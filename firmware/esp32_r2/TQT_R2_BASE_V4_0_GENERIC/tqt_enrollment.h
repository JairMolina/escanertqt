#pragma once
#include <Arduino.h>
void tqtLoadEnrollment();
bool tqtIsGeneric();
void tqtEnrollmentReset();
String tqtEnrollmentInfo();
bool tqtAcceptEnrollment(const uint8_t *ticket,size_t size,const uint8_t *nonce);
