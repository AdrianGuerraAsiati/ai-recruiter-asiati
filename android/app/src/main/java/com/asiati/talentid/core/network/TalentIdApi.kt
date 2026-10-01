package com.asiati.talentid.core.network

import com.asiati.talentid.core.security.DeviceCredentials
import java.io.File
import java.io.IOException
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.asRequestBody
import org.json.JSONObject

enum class AttendanceEventType(val apiValue: String) {
    CHECK_IN("check_in"),
    CHECK_OUT("check_out"),
}

data class KioskContext(
    val deviceId: String,
    val deviceName: String,
    val siteName: String,
    val siteTimezone: String,
)

data class AttendanceResult(
    val employeeId: String,
    val displayName: String,
    val similarity: Double,
    val eventType: AttendanceEventType,
    val occurredAt: String,
    val created: Boolean,
)

class TalentIdApiException(
    val statusCode: Int,
    override val message: String,
) : IOException(message)

class TalentIdApi(
    private val baseUrl: String,
    private val client: OkHttpClient = defaultClient(),
) {
    suspend fun getKioskContext(credentials: DeviceCredentials): KioskContext =
        withContext(Dispatchers.IO) {
            val request = Request.Builder()
                .url(url("/v1/kiosk/context"))
                .header("X-Device-Id", credentials.deviceId)
                .header("X-Device-Secret", credentials.secret)
                .get()
                .build()

            client.newCall(request).execute().use { response ->
                val body = response.body.string()
                ensureSuccess(response.code, body)

                val json = JSONObject(body)
                val device = json.getJSONObject("device")
                KioskContext(
                    deviceId = device.getString("id"),
                    deviceName = device.getString("name"),
                    siteName = json.getString("site_name"),
                    siteTimezone = json.getString("site_timezone"),
                )
            }
        }

    suspend fun recognize(
        credentials: DeviceCredentials,
        image: File,
        eventType: AttendanceEventType,
        idempotencyKey: String,
    ): AttendanceResult = withContext(Dispatchers.IO) {
        val multipart = MultipartBody.Builder()
            .setType(MultipartBody.FORM)
            .addFormDataPart("event_type", eventType.apiValue)
            .addFormDataPart(
                "image",
                image.name,
                image.asRequestBody("image/jpeg".toMediaType()),
            )
            .build()

        val request = Request.Builder()
            .url(url("/v1/kiosk/recognize"))
            .header("X-Device-Id", credentials.deviceId)
            .header("X-Device-Secret", credentials.secret)
            .header("Idempotency-Key", idempotencyKey)
            .post(multipart)
            .build()

        client.newCall(request).execute().use { response ->
            val body = response.body.string()
            ensureSuccess(response.code, body)

            val json = JSONObject(body)
            val attendance = json.getJSONObject("attendance")
            AttendanceResult(
                employeeId = json.getString("employee_id"),
                displayName = json.getString("display_name"),
                similarity = json.getDouble("similarity"),
                eventType = AttendanceEventType.entries.first {
                    it.apiValue == attendance.getString("event_type")
                },
                occurredAt = attendance.getString("occurred_at"),
                created = attendance.getBoolean("created"),
            )
        }
    }

    private fun url(path: String): String = baseUrl.trimEnd('/') + path

    private fun ensureSuccess(statusCode: Int, body: String) {
        if (statusCode in 200..299) {
            return
        }

        val detail = runCatching {
            JSONObject(body).optString("detail")
        }.getOrNull().orEmpty()

        throw TalentIdApiException(
            statusCode = statusCode,
            message = detail.ifBlank { "Talent ID request failed ($statusCode)" },
        )
    }

    private companion object {
        fun defaultClient(): OkHttpClient = OkHttpClient.Builder()
            .connectTimeout(10, TimeUnit.SECONDS)
            .readTimeout(20, TimeUnit.SECONDS)
            .writeTimeout(20, TimeUnit.SECONDS)
            .build()
    }
}
