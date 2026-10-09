#ifndef TQT_IDENTITY_FAULT_H
#define TQT_IDENTITY_FAULT_H
#include "tqt_identity.h"
extern volatile TQT_IdentityResult tqt_identity_fault;
__attribute__((noreturn)) void TQT_IdentityFault(TQT_IdentityResult result);
#endif
