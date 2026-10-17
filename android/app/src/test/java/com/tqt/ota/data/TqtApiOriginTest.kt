package com.tqt.ota.data

import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test

class TqtApiOriginTest {
    @Test fun onlyExplicitHttpsOriginsAreAccepted() {
        assertEquals("https://fixture.invalid:8443", TqtApi.validatedOrigin(" https://fixture.invalid:8443/ "))
        for (value in listOf("http://fixture.invalid", "https://user:password@fixture.invalid", "https://fixture.invalid/api", "https://fixture.invalid?x=1", "https://fixture.invalid#token", "file:///private")) {
            assertThrows(IllegalArgumentException::class.java) { TqtApi.validatedOrigin(value) }
        }
    }
}
