#pragma once
#include <BLEServer.h>
void tqtOtaInit(BLEServer *server);
void tqtOtaConnected();
void tqtOtaDisconnected();
void tqtOtaTick(bool relaysIdle);
bool tqtOtaBusy();
String tqtOtaKeyId();
void tqtOtaBootReady(bool healthy);
