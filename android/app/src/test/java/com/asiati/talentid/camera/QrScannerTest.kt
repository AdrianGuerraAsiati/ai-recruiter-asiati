package com.asiati.talentid.camera

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class QrScannerTest {
    @Test
    fun extractsTalentQrTokenFromExpectedUri() {
        val token = "abcdefghijklmnopqrstuv1234567890"

        assertEquals(
            token,
            extractTalentQrToken("talentid://attendance?token=$token"),
        )
    }

    @Test
    fun rejectsForeignOrShortQrPayloads() {
        assertNull(
            extractTalentQrToken(
                "https://example.com/?token=abcdefghijklmnopqrstuv1234567890",
            ),
        )
        assertNull(
            extractTalentQrToken("talentid://attendance?token=short"),
        )
    }
}
