#pragma once
#include <mbedtls/sha256.h>
// Debian bookworm mbedTLS 2.28 exposes the same API without private-field macro.
#ifndef MBEDTLS_PRIVATE
#define MBEDTLS_PRIVATE(member) member
#endif
#define mbedtls_sha256 mbedtls_sha256_ret
