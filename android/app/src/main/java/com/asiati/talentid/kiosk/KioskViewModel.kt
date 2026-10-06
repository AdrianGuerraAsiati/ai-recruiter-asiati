package com.asiati.talentid.kiosk

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.asiati.talentid.core.network.AttendanceEventType
import com.asiati.talentid.core.network.AttendanceResult
import com.asiati.talentid.core.network.KioskContext
import com.asiati.talentid.core.network.TalentIdApi
import com.asiati.talentid.core.network.TalentIdApiException
import com.asiati.talentid.core.security.DeviceCredentialStore
import com.asiati.talentid.core.security.DeviceCredentials
import java.io.File
import java.io.IOException
import java.util.UUID
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class KioskUiState(
    val credentialsConfigured: Boolean = false,
    val loadingContext: Boolean = false,
    val context: KioskContext? = null,
    val submitting: Boolean = false,
    val lastResult: AttendanceResult? = null,
    val error: String? = null,
    val retryAvailable: Boolean = false,
)

private data class PendingAttendance(
    val image: File,
    val eventType: AttendanceEventType,
    val idempotencyKey: String,
)

private data class PendingQrAttendance(
    val token: String,
    val eventType: AttendanceEventType,
)

class KioskViewModel(
    private val credentialStore: DeviceCredentialStore,
    private val api: TalentIdApi,
) : ViewModel() {
    private var credentials: DeviceCredentials? = credentialStore.load()
    private var pendingAttendance: PendingAttendance? = null
    private var pendingQrAttendance: PendingQrAttendance? = null

    private val _state = MutableStateFlow(
        KioskUiState(credentialsConfigured = credentials != null),
    )
    val state: StateFlow<KioskUiState> = _state.asStateFlow()

    init {
        if (credentials != null) {
            refreshContext()
        }
    }

    fun provision(deviceId: String, secret: String) {
        val normalizedId = deviceId.trim()
        val normalizedSecret = secret.trim()

        if (runCatching { UUID.fromString(normalizedId) }.isFailure) {
            setError("El ID del dispositivo no es válido.")
            return
        }
        if (normalizedSecret.length < 16) {
            setError("El secreto del dispositivo no es válido.")
            return
        }

        credentials = DeviceCredentials(
            deviceId = normalizedId,
            secret = normalizedSecret,
        ).also(credentialStore::save)

        _state.update {
            it.copy(
                credentialsConfigured = true,
                context = null,
                error = null,
            )
        }
        refreshContext()
    }

    fun clearProvisioning() {
        pendingAttendance?.image?.delete()
        pendingAttendance = null
        pendingQrAttendance = null
        credentials = null
        credentialStore.clear()
        _state.value = KioskUiState()
    }

    fun refreshContext() {
        val currentCredentials = credentials ?: return
        viewModelScope.launch {
            _state.update { it.copy(loadingContext = true, error = null) }
            runCatching { api.getKioskContext(currentCredentials) }
                .onSuccess { context ->
                    _state.update {
                        it.copy(
                            loadingContext = false,
                            context = context,
                            error = null,
                        )
                    }
                }
                .onFailure { error ->
                    _state.update {
                        it.copy(
                            loadingContext = false,
                            context = null,
                            error = userMessage(error),
                        )
                    }
                }
        }
    }

    fun submitAttendance(
        image: File,
        eventType: AttendanceEventType,
    ) {
        pendingAttendance?.image?.delete()
        pendingAttendance = PendingAttendance(
            image = image,
            eventType = eventType,
            idempotencyKey = UUID.randomUUID().toString(),
        )
        submitPending()
    }

    fun retryPending() {
        when {
            pendingAttendance != null -> submitPending()
            pendingQrAttendance != null -> submitPendingQr()
        }
    }

    fun submitQrAttendance(
        token: String,
        eventType: AttendanceEventType,
    ) {
        pendingAttendance?.image?.delete()
        pendingAttendance = null
        pendingQrAttendance = PendingQrAttendance(
            token = token,
            eventType = eventType,
        )
        submitPendingQr()
    }

    fun dismissResult() {
        _state.update { it.copy(lastResult = null, error = null) }
    }

    private fun submitPending() {
        val currentCredentials = credentials ?: return
        val pending = pendingAttendance ?: return

        viewModelScope.launch {
            _state.update {
                it.copy(
                    submitting = true,
                    error = null,
                    retryAvailable = false,
                )
            }

            try {
                val result = api.recognize(
                    credentials = currentCredentials,
                    image = pending.image,
                    eventType = pending.eventType,
                    idempotencyKey = pending.idempotencyKey,
                )
                pending.image.delete()
                pendingAttendance = null
                _state.update {
                    it.copy(
                        submitting = false,
                        lastResult = result,
                        error = null,
                        retryAvailable = false,
                    )
                }
            } catch (error: Throwable) {
                val canRetry = error is IOException && error !is TalentIdApiException
                if (!canRetry) {
                    pending.image.delete()
                    pendingAttendance = null
                }
                _state.update {
                    it.copy(
                        submitting = false,
                        error = userMessage(error),
                        retryAvailable = canRetry,
                    )
                }
            }
        }
    }


    private fun submitPendingQr() {
        val currentCredentials = credentials ?: return
        val pending = pendingQrAttendance ?: return

        viewModelScope.launch {
            _state.update {
                it.copy(
                    submitting = true,
                    error = null,
                    retryAvailable = false,
                )
            }

            try {
                val result = api.submitQr(
                    credentials = currentCredentials,
                    token = pending.token,
                    eventType = pending.eventType,
                )
                pendingQrAttendance = null
                _state.update {
                    it.copy(
                        submitting = false,
                        lastResult = result,
                        error = null,
                        retryAvailable = false,
                    )
                }
            } catch (error: Throwable) {
                val canRetry = error is IOException && error !is TalentIdApiException
                if (!canRetry) {
                    pendingQrAttendance = null
                }
                _state.update {
                    it.copy(
                        submitting = false,
                        error = userMessage(error),
                        retryAvailable = canRetry,
                    )
                }
            }
        }
    }

    private fun setError(message: String) {
        _state.update { it.copy(error = message) }
    }

    private fun userMessage(error: Throwable): String = when (error) {
        is TalentIdApiException -> when (error.statusCode) {
            401 -> "Este dispositivo no está autorizado."
            404 -> "No pudimos validar la marcación."
            409 -> "Este código ya fue utilizado para otra operación."
            410 -> "El código QR expiró. Genera uno nuevo en tu celular."
            412 -> error.message
                ?: "Tu rostro fue identificado, pero debes aceptar la autorización biométrica en Talent > Mi perfil antes de marcar con reconocimiento facial."
            422 -> error.message ?: "El código QR o la solicitud no son válidos."
            else -> error.message ?: "Talent ID rechazó la solicitud."
        }
        is IOException -> "No hay conexión con Talent ID."
        else -> "Ocurrió un error al procesar la marcación."
    }

    class Factory(
        private val credentialStore: DeviceCredentialStore,
        private val api: TalentIdApi,
    ) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T {
            require(modelClass.isAssignableFrom(KioskViewModel::class.java))
            return KioskViewModel(credentialStore, api) as T
        }
    }
}
