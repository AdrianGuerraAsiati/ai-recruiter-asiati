package com.asiati.talentid.core.network

import org.junit.Assert.assertEquals
import org.junit.Test

class AttendanceEventTypeTest {
    @Test
    fun eventTypesMatchBackendContract() {
        assertEquals("check_in", AttendanceEventType.CHECK_IN.apiValue)
        assertEquals("check_out", AttendanceEventType.CHECK_OUT.apiValue)
    }
}
