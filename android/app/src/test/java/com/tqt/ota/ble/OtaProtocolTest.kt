package com.tqt.ota.ble

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test

class OtaProtocolTest {
    @Test fun payloadFitsMinimumAndMaximumNegotiatedMtu() {
        assertEquals(16, OtaProtocol.payloadSize(23, 500))
        assertEquals(500, OtaProtocol.payloadSize(517, 500))
        assertEquals(180, OtaProtocol.payloadSize(517, 180))
        assertEquals(93, OtaProtocol.payloadSize(100, 500))
        assertThrows(IllegalArgumentException::class.java) { OtaProtocol.payloadSize(22, 16) }
        assertThrows(IllegalArgumentException::class.java) { OtaProtocol.payloadSize(517, 501) }
    }

    @Test fun packetUsesLittleEndianOffsetAndExactPayload() {
        val image = ByteArray(0x10210) { (it and 255).toByte() }
        val packet = OtaProtocol.packet(image, 0x10203, 8)
        assertArrayEquals(byteArrayOf(3, 2, 1, 0), packet.copyOfRange(0, 4))
        assertArrayEquals(image.copyOfRange(0x10203, 0x1020b), packet.copyOfRange(4, 12))
        assertEquals(504, OtaProtocol.packet(ByteArray(500), 0, 500).size)
        assertThrows(IllegalArgumentException::class.java) { OtaProtocol.packet(image, 0, 501) }
        assertThrows(IllegalArgumentException::class.java) { OtaProtocol.packet(image, image.size, 1) }
    }

    @Test fun notificationDecodesUnsignedU32AndAllStates() {
        val result = OtaProtocol.decodeNotification(frame(2, 0x80000000L, 0xffffffffL))
        assertEquals(OtaProtocol.State.RECEIVING, result.state)
        assertEquals(0x80000000L, result.offset)
        assertEquals(0xffffffffL, result.total)
        OtaProtocol.State.entries.forEach { state ->
            assertEquals(state, OtaProtocol.decodeNotification(frame(state.wire, 0, 0)).state)
        }
    }

    @Test fun minimumAndMaximumMtuProduceSequentialBoundedWindows() {
        val image = ByteArray(65536) { (it and 255).toByte() }
        for (mtu in listOf(23, 517)) {
            val chunk = OtaProtocol.payloadSize(mtu, 500)
            val acks = OtaProtocol.Acknowledgements(OtaProtocol.Phase.IMAGE, image.size.toLong())
            var offset = 0
            while (offset < image.size) {
                val previous = acks.confirmed
                repeat(OtaProtocol.WINDOW) {
                    if (offset < image.size) {
                        val length = minOf(chunk, image.size - offset)
                        val packet = OtaProtocol.packet(image, offset, length)
                        assertTrue(packet.size <= mtu - 3)
                        assertEquals(offset.toLong(), OtaProtocol.u32(packet, 0))
                        assertArrayEquals(image.copyOfRange(offset, offset + length), packet.copyOfRange(4, packet.size))
                        offset += length
                        acks.sentThrough(offset.toLong())
                        assertEquals(previous, acks.confirmed)
                    }
                }
                val state = if (offset == image.size) OtaProtocol.State.READY else OtaProtocol.State.RECEIVING
                acks.accept(OtaProtocol.decodeNotification(frame(state.wire, offset.toLong(), image.size.toLong())))
                assertEquals(offset.toLong(), acks.confirmed)
            }
            assertTrue(acks.complete)
        }
    }

    @Test fun malformedNotificationsNeverBecomeAcknowledgements() {
        listOf(byteArrayOf(), ByteArray(9), ByteArray(11), frame(8, 0, 0),
            frame(2, 11, 10), frame(2, 0, 10, 1), frame(5, 0, 0, 2)).forEach { bad ->
            assertThrows(OtaProtocol.ProtocolException::class.java) { OtaProtocol.decodeNotification(bad) }
        }
    }

    @Test fun offlineManifestRequiresAll472BytesAndAuthenticatedTransition() {
        val acks = OtaProtocol.Acknowledgements(OtaProtocol.Phase.OFFLINE_MANIFEST, 472, 65536)
        acks.sentThrough(128)
        acks.accept(status(OtaProtocol.State.OFFLINE_MANIFEST, 128, 472))
        assertThrows(OtaProtocol.ProtocolException::class.java) { acks.accept(status(OtaProtocol.State.RECEIVING, 0, 65536)) }
        acks.sentThrough(472)
        acks.accept(status(OtaProtocol.State.OFFLINE_MANIFEST, 472, 472))
        assertFalse(acks.complete)
        acks.accept(status(OtaProtocol.State.RECEIVING, 0, 65536))
        assertTrue(acks.complete)
        val manifest = ByteArray(472)
        put32(manifest, 278, 65536)
        OtaProtocol.validateOfflineUpdate(manifest, ByteArray(65536))
        assertThrows(IllegalArgumentException::class.java) { OtaProtocol.validateOfflineUpdate(manifest, ByteArray(65537)) }
    }

    @Test fun offlineInfoUsesBounded190ByteFrameWithExactOffsets() {
        val frame = ByteArray(190) { it.toByte() }
        frame[0] = 1
        put32(frame, 66, 0x80000001L)
        val info = OtaProtocol.decodeOfflineInfo(frame)
        assertArrayEquals(frame.copyOfRange(1, 66), info.devicePublicKey)
        assertEquals(0x80000001L, info.counter)
        assertArrayEquals(frame.copyOfRange(70, 78), info.anchorId)
        assertArrayEquals(frame.copyOfRange(78, 110), info.identityProof)
        assertArrayEquals(frame.copyOfRange(110, 174), info.signature)
        assertArrayEquals(frame.copyOfRange(174, 190), info.lastGrant)
        assertThrows(OtaProtocol.ProtocolException::class.java) { OtaProtocol.decodeOfflineInfo(frame.copyOf(191)) }
        assertThrows(OtaProtocol.ProtocolException::class.java) { OtaProtocol.decodeOfflineInfo(ByteArray(190)) }
    }

    @Test fun manifestRequiresAuthenticatedTransitionWithResetOffset() {
        val acks = OtaProtocol.Acknowledgements(OtaProtocol.Phase.MANIFEST, 138, 65536)
        acks.sentThrough(16)
        assertEquals(16, acks.accept(status(OtaProtocol.State.MANIFEST, 16, 138)))
        acks.sentThrough(138)
        assertEquals(138, acks.accept(status(OtaProtocol.State.MANIFEST, 138, 138)))
        assertFalse(acks.complete)
        assertEquals(138, acks.accept(status(OtaProtocol.State.RECEIVING, 0, 65536)))
        assertTrue(acks.complete)
    }

    @Test fun prematureOrIncorrectManifestTransitionIsRejected() {
        val acks = OtaProtocol.Acknowledgements(OtaProtocol.Phase.MANIFEST, 138, 65536)
        acks.sentThrough(16)
        assertThrows(OtaProtocol.ProtocolException::class.java) { acks.accept(status(OtaProtocol.State.RECEIVING, 0, 65536)) }
        acks.sentThrough(138)
        assertThrows(OtaProtocol.ProtocolException::class.java) { acks.accept(status(OtaProtocol.State.RECEIVING, 0, 65537)) }
        assertThrows(OtaProtocol.ProtocolException::class.java) { acks.accept(status(OtaProtocol.State.RECEIVING, 138, 65536)) }
    }

    @Test fun imageProgressOnlyAdvancesWithConfirmedDeviceBytes() {
        val acks = OtaProtocol.Acknowledgements(OtaProtocol.Phase.IMAGE, 1000)
        acks.sentThrough(500)
        assertEquals(0, acks.confirmed)
        acks.accept(status(OtaProtocol.State.RECEIVING, 200, 1000))
        assertEquals(200, acks.confirmed)
        // Duplicate ACKs are allowed, but never counted twice.
        acks.accept(status(OtaProtocol.State.RECEIVING, 200, 1000))
        assertEquals(200, acks.confirmed)
        acks.sentThrough(1000)
        acks.accept(status(OtaProtocol.State.RECEIVING, 1000, 1000))
        assertFalse(acks.complete)
        acks.accept(status(OtaProtocol.State.READY, 1000, 1000))
        assertTrue(acks.complete)
    }

    @Test fun regressiveAndUnsentOffsetsAreRejected() {
        val acks = OtaProtocol.Acknowledgements(OtaProtocol.Phase.IMAGE, 1000)
        acks.sentThrough(500)
        acks.accept(status(OtaProtocol.State.RECEIVING, 200, 1000))
        assertThrows(OtaProtocol.ProtocolException::class.java) { acks.accept(status(OtaProtocol.State.RECEIVING, 199, 1000)) }
        assertThrows(OtaProtocol.ProtocolException::class.java) { acks.accept(status(OtaProtocol.State.RECEIVING, 501, 1000)) }
        assertThrows(OtaProtocol.ProtocolException::class.java) { acks.accept(status(OtaProtocol.State.RECEIVING, 200, 999)) }
        assertEquals(200, acks.confirmed)
    }

    @Test fun readyMustAcknowledgeTheCompleteImage() {
        val acks = OtaProtocol.Acknowledgements(OtaProtocol.Phase.IMAGE, 1000)
        acks.sentThrough(500)
        assertThrows(OtaProtocol.ProtocolException::class.java) { acks.accept(status(OtaProtocol.State.READY, 500, 1000)) }
        assertThrows(OtaProtocol.ProtocolException::class.java) { acks.accept(status(OtaProtocol.State.READY, 1000, 1000)) }
        assertFalse(acks.complete)
    }

    @Test fun enrollmentCompletesOnlyAfterIdleAndFullTicketOffset() {
        val acks = OtaProtocol.Acknowledgements(OtaProtocol.Phase.ENROLLMENT, 286)
        acks.sentThrough(286)
        acks.accept(status(OtaProtocol.State.ENROLLMENT, 286, 286))
        assertFalse(acks.complete)
        assertThrows(OtaProtocol.ProtocolException::class.java) { acks.accept(status(OtaProtocol.State.IDLE, 0, 0)) }
        acks.accept(status(OtaProtocol.State.IDLE, 286, 286))
        assertTrue(acks.complete)
    }

    @Test fun errorsAndDisconnectsNeverImplyCompletionOrResume() {
        val interrupted = OtaProtocol.Acknowledgements(OtaProtocol.Phase.IMAGE, 1000)
        interrupted.sentThrough(500)
        interrupted.accept(status(OtaProtocol.State.RECEIVING, 200, 1000))
        assertThrows(OtaProtocol.ProtocolException::class.java) {
            interrupted.accept(OtaProtocol.status("error", 0, 0, "disconnected"))
        }
        assertFalse(interrupted.complete)
        assertEquals(200, interrupted.confirmed)
        // A fresh session has no resume command: previous offsets cannot be claimed as received.
        val fresh = OtaProtocol.Acknowledgements(OtaProtocol.Phase.IMAGE, 1000)
        assertThrows(OtaProtocol.ProtocolException::class.java) { fresh.accept(status(OtaProtocol.State.RECEIVING, 200, 1000)) }
        assertEquals(0, fresh.confirmed)
    }

    @Test fun activationIsNotAnImageAckOrBootVerification() {
        val acks = OtaProtocol.Acknowledgements(OtaProtocol.Phase.IMAGE, 1000)
        acks.sentThrough(1000)
        assertThrows(OtaProtocol.ProtocolException::class.java) { acks.accept(status(OtaProtocol.State.RESTARTING, 1000, 1000)) }
        assertFalse(acks.complete)
    }

    @Test fun manifestLengthMustMatchEncryptedImageExactly() {
        val manifest = ByteArray(138)
        put32(manifest, 48, 65536)
        OtaProtocol.validateUpdate(manifest, ByteArray(65536))
        assertThrows(IllegalArgumentException::class.java) { OtaProtocol.validateUpdate(manifest, ByteArray(65537)) }
        assertThrows(IllegalArgumentException::class.java) { OtaProtocol.validateUpdate(ByteArray(137), ByteArray(65536)) }
    }

    private fun status(state: OtaProtocol.State, offset: Long, total: Long) = OtaProtocol.status(state.json, offset, total)
    private fun frame(state: Int, offset: Long, total: Long, error: Int = 0) = ByteArray(10).also {
        it[0] = state.toByte()
        put32(it, 1, offset)
        put32(it, 5, total)
        it[9] = error.toByte()
    }
    private fun put32(bytes: ByteArray, at: Int, value: Long) {
        for (i in 0..3) bytes[at + i] = (value ushr (8 * i)).toByte()
    }
}
