package com.asiati.talentid.kiosk

import android.Manifest
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.blur
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Rect
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.clipPath
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.IntSize
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.asiati.talentid.camera.CameraPreview
import com.asiati.talentid.camera.FaceObservation
import com.asiati.talentid.camera.captureKioskPhoto
import com.asiati.talentid.camera.rememberKioskCameraController
import com.asiati.talentid.camera.rememberQrScannerController
import com.asiati.talentid.core.network.AttendanceEventType
import com.asiati.talentid.core.network.AttendanceResult
import com.asiati.talentid.core.network.KioskContext
import com.asiati.talentid.ui.TalentBlue
import com.asiati.talentid.ui.TalentCanvas
import com.asiati.talentid.ui.TalentCyan
import com.asiati.talentid.ui.TalentDanger
import com.asiati.talentid.ui.TalentDangerSoft
import com.asiati.talentid.ui.TalentIdTheme
import com.asiati.talentid.ui.TalentInk
import com.asiati.talentid.ui.TalentInkSoft
import com.asiati.talentid.ui.TalentNavy
import com.asiati.talentid.ui.TalentSuccess
import com.asiati.talentid.ui.TalentSuccessSoft
import com.asiati.talentid.ui.TalentSurfaceSoft
import com.asiati.talentid.ui.TalentWarning
import com.asiati.talentid.ui.TalentWarningSoft
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlin.math.roundToInt

@Composable
fun TalentIdApp(viewModel: KioskViewModel) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val kioskContext = state.context

    TalentIdTheme {
        Surface(
            modifier = Modifier.fillMaxSize(),
            color = TalentCanvas,
        ) {
            when {
                !state.credentialsConfigured -> ProvisioningScreen(
                    error = state.error,
                    onProvision = viewModel::provision,
                )

                kioskContext == null -> ConnectionScreen(
                    loading = state.loadingContext,
                    error = state.error,
                    onRetry = viewModel::refreshContext,
                    onReset = viewModel::clearProvisioning,
                )

                else -> KioskScreen(
                    context = kioskContext,
                    state = state,
                    onSubmit = viewModel::submitAttendance,
                    onSubmitQr = viewModel::submitQrAttendance,
                    onRetryPending = viewModel::retryPending,
                    onDismissResult = viewModel::dismissResult,
                )
            }
        }
    }
}

@Composable
private fun ProvisioningScreen(
    error: String?,
    onProvision: (String, String) -> Unit,
) {
    var deviceId by remember { mutableStateOf("") }
    var secret by remember { mutableStateOf("") }

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(TalentCanvas)
            .padding(24.dp),
        contentAlignment = Alignment.Center,
    ) {
        Surface(
            modifier = Modifier
                .fillMaxWidth()
                .widthIn(max = 560.dp),
            shape = RoundedCornerShape(28.dp),
            color = Color.White,
            tonalElevation = 2.dp,
            shadowElevation = 8.dp,
        ) {
            Column(
                modifier = Modifier.padding(28.dp),
                verticalArrangement = Arrangement.spacedBy(18.dp),
            ) {
                BrandLockup(
                    eyebrow = "CONFIGURACIÓN INICIAL",
                    title = "Talent ID",
                    subtitle = "Vincula este dispositivo de recepción una sola vez.",
                )

                Surface(
                    shape = RoundedCornerShape(16.dp),
                    color = TalentSurfaceSoft,
                ) {
                    Text(
                        modifier = Modifier.padding(16.dp),
                        text = "Usa el Device ID y Device Secret generados desde Talent Intelligence. " +
                            "El secreto se cifra en Android Keystore y no se mostrará después.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = TalentInkSoft,
                    )
                }

                OutlinedTextField(
                    modifier = Modifier.fillMaxWidth(),
                    value = deviceId,
                    onValueChange = { deviceId = it.trim() },
                    label = { Text("Device ID") },
                    supportingText = { Text("Identificador UUID del kiosco") },
                    singleLine = true,
                )

                OutlinedTextField(
                    modifier = Modifier.fillMaxWidth(),
                    value = secret,
                    onValueChange = { secret = it },
                    label = { Text("Device Secret") },
                    supportingText = { Text("Secreto mostrado una sola vez en Talent") },
                    visualTransformation = PasswordVisualTransformation(),
                    singleLine = true,
                )

                error?.let { ErrorBanner(it) }

                Button(
                    modifier = Modifier
                        .fillMaxWidth()
                        .heightIn(min = 54.dp),
                    enabled = deviceId.isNotBlank() && secret.isNotBlank(),
                    onClick = { onProvision(deviceId, secret) },
                ) {
                    Text(
                        text = "Vincular dispositivo",
                        fontWeight = FontWeight.SemiBold,
                    )
                }

                Text(
                    modifier = Modifier.fillMaxWidth(),
                    text = "ASIATI · Control de asistencia",
                    textAlign = TextAlign.Center,
                    style = MaterialTheme.typography.labelMedium,
                    color = TalentInkSoft,
                )
            }
        }
    }
}

@Composable
private fun ConnectionScreen(
    loading: Boolean,
    error: String?,
    onRetry: () -> Unit,
    onReset: () -> Unit,
) {
    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(TalentCanvas)
            .padding(24.dp),
        contentAlignment = Alignment.Center,
    ) {
        Surface(
            modifier = Modifier
                .fillMaxWidth()
                .widthIn(max = 520.dp),
            shape = RoundedCornerShape(28.dp),
            color = Color.White,
            shadowElevation = 6.dp,
        ) {
            Column(
                modifier = Modifier.padding(32.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(18.dp),
            ) {
                BrandLockup(
                    eyebrow = "TALENT ID",
                    title = if (loading) "Conectando kiosco" else "No pudimos conectar",
                    subtitle = if (loading) {
                        "Estamos validando este dispositivo con Talent Intelligence."
                    } else {
                        "Revisa la conexión o vuelve a vincular el dispositivo."
                    },
                    centered = true,
                )

                if (loading) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(42.dp),
                        color = TalentBlue,
                        trackColor = MaterialTheme.colorScheme.primaryContainer,
                    )
                    Text(
                        text = "Validando credenciales y sede…",
                        style = MaterialTheme.typography.bodyMedium,
                        color = TalentInkSoft,
                    )
                } else {
                    error?.let { ErrorBanner(it) }
                    Button(
                        modifier = Modifier
                            .fillMaxWidth()
                            .heightIn(min = 52.dp),
                        onClick = onRetry,
                    ) {
                        Text("Reintentar conexión")
                    }
                    OutlinedButton(
                        modifier = Modifier.fillMaxWidth(),
                        onClick = onReset,
                    ) {
                        Text("Reconfigurar dispositivo")
                    }
                }
            }
        }
    }
}

private enum class KioskIdentityMode {
    FACE,
    QR,
}

@Composable
private fun KioskScreen(
    context: KioskContext,
    state: KioskUiState,
    onSubmit: (java.io.File, AttendanceEventType) -> Unit,
    onSubmitQr: (String, AttendanceEventType) -> Unit,
    onRetryPending: () -> Unit,
    onDismissResult: () -> Unit,
) {
    val androidContext = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    val scope = rememberCoroutineScope()

    var cameraGranted by remember {
        mutableStateOf(
            ContextCompat.checkSelfPermission(
                androidContext,
                Manifest.permission.CAMERA,
            ) == PackageManager.PERMISSION_GRANTED,
        )
    }
    var captureError by remember { mutableStateOf<String?>(null) }
    var capturing by remember { mutableStateOf(false) }
    var identityMode by remember { mutableStateOf(KioskIdentityMode.FACE) }
    var qrEventType by remember { mutableStateOf<AttendanceEventType?>(null) }
    var qrScanLocked by remember { mutableStateOf(false) }
    var faceObservation by remember { mutableStateOf(FaceObservation()) }
    var faceReadyStable by remember { mutableStateOf(false) }

    val permissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { granted ->
        cameraGranted = granted
    }

    LaunchedEffect(Unit) {
        if (!cameraGranted) {
            permissionLauncher.launch(Manifest.permission.CAMERA)
        }
    }

    LaunchedEffect(state.lastResult) {
        if (state.lastResult != null) {
            delay(4500)
            onDismissResult()
        }
    }

    LaunchedEffect(faceObservation.ready) {
        if (faceObservation.ready) {
            delay(300)
            if (faceObservation.ready) {
                faceReadyStable = true
            }
        } else {
            faceReadyStable = false
        }
    }

    BoxWithConstraints(
        modifier = Modifier
            .fillMaxSize()
            .background(TalentCanvas),
    ) {
        val wideLayout = maxWidth >= 820.dp

        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(if (wideLayout) 28.dp else 12.dp),
            verticalArrangement = Arrangement.spacedBy(if (wideLayout) 18.dp else 10.dp),
        ) {
            KioskHeader(context)

            IdentityMethodSelector(
                selected = identityMode,
                enabled = !state.submitting && !capturing,
                onSelect = { mode ->
                    identityMode = mode
                    captureError = null
                    qrEventType = null
                    qrScanLocked = false
                    faceObservation = FaceObservation()
                    faceReadyStable = false
                },
            )

            if (!cameraGranted) {
                PermissionPanel(
                    modifier = Modifier
                        .fillMaxWidth()
                        .weight(1f),
                    onRequestPermission = {
                        permissionLauncher.launch(Manifest.permission.CAMERA)
                    },
                )
            } else if (identityMode == KioskIdentityMode.FACE) {
                val controller = rememberKioskCameraController(
                    context = androidContext,
                    lifecycleOwner = lifecycleOwner,
                    onFaceObservation = { faceObservation = it },
                )
                val submitFaceEvent: (AttendanceEventType) -> Unit = { eventType ->
                    captureError = null
                    capturing = true
                    scope.launch {
                        runCatching {
                            captureKioskPhoto(
                                context = androidContext,
                                controller = controller,
                            )
                        }.onSuccess { photoFile ->
                            onSubmit(photoFile, eventType)
                            capturing = false
                        }.onFailure {
                            capturing = false
                            captureError = "No fue posible tomar la fotografía. Intenta de nuevo."
                        }
                    }
                }

                if (wideLayout) {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .weight(1f),
                        horizontalArrangement = Arrangement.spacedBy(22.dp),
                    ) {
                        CameraStage(
                            modifier = Modifier.weight(1.55f),
                            controller = controller,
                            submitting = state.submitting || capturing,
                            faceObservation = faceObservation,
                            faceReadyStable = faceReadyStable,
                        )
                        ActionPanel(
                            modifier = Modifier.weight(0.85f),
                            state = state.copy(submitting = state.submitting || capturing),
                            captureError = captureError,
                            faceObservation = faceObservation,
                            faceReady = faceReadyStable,
                            onRetryPending = onRetryPending,
                            onEvent = submitFaceEvent,
                        )
                    }
                } else {
                    CameraStage(
                        modifier = Modifier
                            .fillMaxWidth()
                            .weight(1f),
                        controller = controller,
                        submitting = state.submitting || capturing,
                        faceObservation = faceObservation,
                        faceReadyStable = faceReadyStable,
                    )
                    ActionPanel(
                        modifier = Modifier.fillMaxWidth(),
                        state = state.copy(submitting = state.submitting || capturing),
                        captureError = captureError,
                        faceObservation = faceObservation,
                        faceReady = faceReadyStable,
                        onRetryPending = onRetryPending,
                        horizontalActions = true,
                        onEvent = submitFaceEvent,
                    )
                }
            } else {
                val qrController = rememberQrScannerController(
                    context = androidContext,
                    lifecycleOwner = lifecycleOwner,
                    onQrCode = { token ->
                        val eventType = qrEventType
                        if (
                            eventType != null
                            && !qrScanLocked
                            && !state.submitting
                        ) {
                            qrScanLocked = true
                            qrEventType = null
                            onSubmitQr(token, eventType)
                        }
                    },
                )

                if (wideLayout) {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .weight(1f),
                        horizontalArrangement = Arrangement.spacedBy(22.dp),
                    ) {
                        QrCameraStage(
                            modifier = Modifier.weight(1.55f),
                            controller = qrController,
                            scannerActive = qrEventType != null,
                            submitting = state.submitting,
                        )
                        QrActionPanel(
                            modifier = Modifier.weight(0.85f),
                            state = state,
                            selectedEvent = qrEventType,
                            onRetryPending = onRetryPending,
                            onEvent = { eventType ->
                                qrScanLocked = false
                                qrEventType = eventType
                            },
                        )
                    }
                } else {
                    QrCameraStage(
                        modifier = Modifier
                            .fillMaxWidth()
                            .weight(1f),
                        controller = qrController,
                        scannerActive = qrEventType != null,
                        submitting = state.submitting,
                    )
                    QrActionPanel(
                        modifier = Modifier.fillMaxWidth(),
                        state = state,
                        selectedEvent = qrEventType,
                        onRetryPending = onRetryPending,
                        horizontalActions = true,
                        onEvent = { eventType ->
                            qrScanLocked = false
                            qrEventType = eventType
                        },
                    )
                }
            }

            if (wideLayout) {
                FooterNote()
            }
        }

        state.lastResult?.let { result ->
            SuccessOverlay(
                result = result,
                onDismiss = onDismissResult,
            )
        }
    }
}

@Composable
private fun IdentityMethodSelector(
    selected: KioskIdentityMode,
    enabled: Boolean,
    onSelect: (KioskIdentityMode) -> Unit,
) {
    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(16.dp),
        color = Color.White,
        shadowElevation = 1.dp,
    ) {
        BoxWithConstraints {
            val compact = maxWidth < 460.dp
            val faceLabel = if (compact) "Rostro" else "Reconocimiento facial"

            Row(
                modifier = Modifier.padding(4.dp),
                horizontalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                if (selected == KioskIdentityMode.FACE) {
                    Button(
                        modifier = Modifier
                            .weight(1f)
                            .heightIn(min = 44.dp),
                        enabled = enabled,
                        shape = RoundedCornerShape(12.dp),
                        onClick = { onSelect(KioskIdentityMode.FACE) },
                    ) {
                        Text(faceLabel, maxLines = 1)
                    }
                } else {
                    OutlinedButton(
                        modifier = Modifier
                            .weight(1f)
                            .heightIn(min = 44.dp),
                        enabled = enabled,
                        shape = RoundedCornerShape(12.dp),
                        onClick = { onSelect(KioskIdentityMode.FACE) },
                    ) {
                        Text(faceLabel, maxLines = 1)
                    }
                }

                if (selected == KioskIdentityMode.QR) {
                    Button(
                        modifier = Modifier
                            .weight(1f)
                            .heightIn(min = 44.dp),
                        enabled = enabled,
                        shape = RoundedCornerShape(12.dp),
                        onClick = { onSelect(KioskIdentityMode.QR) },
                    ) {
                        Text("QR móvil", maxLines = 1)
                    }
                } else {
                    OutlinedButton(
                        modifier = Modifier
                            .weight(1f)
                            .heightIn(min = 44.dp),
                        enabled = enabled,
                        shape = RoundedCornerShape(12.dp),
                        onClick = { onSelect(KioskIdentityMode.QR) },
                    ) {
                        Text("QR móvil", maxLines = 1)
                    }
                }
            }
        }
    }
}

@Composable
private fun QrCameraStage(
    modifier: Modifier,
    controller: androidx.camera.view.LifecycleCameraController,
    scannerActive: Boolean,
    submitting: Boolean,
) {
    Surface(
        modifier = modifier,
        shape = RoundedCornerShape(30.dp),
        color = TalentNavy,
        shadowElevation = 4.dp,
    ) {
        Box(modifier = Modifier.fillMaxSize()) {
            CameraPreview(
                controller = controller,
                modifier = Modifier
                    .fillMaxSize()
                    .clip(RoundedCornerShape(30.dp)),
            )

            Box(
                modifier = Modifier
                    .align(Alignment.TopCenter)
                    .padding(top = 18.dp)
                    .background(
                        color = TalentNavy.copy(alpha = 0.82f),
                        shape = RoundedCornerShape(18.dp),
                    )
                    .padding(horizontal = 16.dp, vertical = 9.dp),
            ) {
                Text(
                    text = if (scannerActive) {
                        "Acerca el QR dinámico de tu celular"
                    } else {
                        "Selecciona Entrada o Salida para activar el lector"
                    },
                    color = Color.White,
                    style = MaterialTheme.typography.labelLarge,
                    fontWeight = FontWeight.SemiBold,
                    textAlign = TextAlign.Center,
                )
            }

            Canvas(
                modifier = Modifier
                    .align(Alignment.Center)
                    .size(230.dp),
            ) {
                drawRect(
                    color = if (scannerActive) TalentCyan else Color.White.copy(alpha = 0.72f),
                    style = Stroke(width = 4.dp.toPx()),
                )
            }

            Box(
                modifier = Modifier
                    .align(Alignment.BottomCenter)
                    .padding(18.dp)
                    .background(
                        color = TalentNavy.copy(alpha = 0.82f),
                        shape = RoundedCornerShape(16.dp),
                    )
                    .padding(horizontal = 14.dp, vertical = 8.dp),
            ) {
                Text(
                    text = "QR de un solo uso · celular vinculado · expiración corta",
                    color = Color.White.copy(alpha = 0.92f),
                    style = MaterialTheme.typography.labelMedium,
                    textAlign = TextAlign.Center,
                )
            }

            if (submitting) {
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .background(TalentNavy.copy(alpha = 0.78f)),
                    contentAlignment = Alignment.Center,
                ) {
                    Column(
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.spacedBy(14.dp),
                    ) {
                        CircularProgressIndicator(
                            modifier = Modifier.size(48.dp),
                            color = TalentCyan,
                            trackColor = Color.White.copy(alpha = 0.18f),
                        )
                        Text(
                            text = "Validando QR…",
                            color = Color.White,
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.SemiBold,
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun QrActionPanel(
    modifier: Modifier,
    state: KioskUiState,
    selectedEvent: AttendanceEventType?,
    onRetryPending: () -> Unit,
    onEvent: (AttendanceEventType) -> Unit,
    horizontalActions: Boolean = false,
) {
    val compact = horizontalActions

    Surface(
        modifier = modifier,
        shape = RoundedCornerShape(if (compact) 20.dp else 26.dp),
        color = Color.White,
        shadowElevation = if (compact) 1.dp else 3.dp,
    ) {
        Column(
            modifier = Modifier.padding(if (compact) 14.dp else 20.dp),
            verticalArrangement = Arrangement.spacedBy(if (compact) 10.dp else 14.dp),
        ) {
            if (compact) {
                Text(
                    modifier = Modifier.fillMaxWidth(),
                    text = if (selectedEvent == null) {
                        "Elige Entrada o Salida y luego muestra tu QR."
                    } else {
                        "Lector activo · muestra el QR dinámico de tu celular."
                    },
                    style = MaterialTheme.typography.bodySmall,
                    color = TalentInkSoft,
                    textAlign = TextAlign.Center,
                )
            } else {
                Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text(
                        text = "Marcación con QR móvil",
                        style = MaterialTheme.typography.titleLarge,
                        fontWeight = FontWeight.Bold,
                        color = TalentInk,
                    )
                    Text(
                        text = if (selectedEvent == null) {
                            "Primero indica si registrarás entrada o salida."
                        } else {
                            "Lector activo. Muestra el QR dinámico de Talent en tu celular."
                        },
                        style = MaterialTheme.typography.bodyMedium,
                        color = TalentInkSoft,
                    )
                }
            }

            state.error?.let { ErrorBanner(it) }

            if (state.retryAvailable) {
                RetryBanner(
                    enabled = !state.submitting,
                    onRetry = onRetryPending,
                )
            }

            if (horizontalActions) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    AttendanceAction(
                        modifier = Modifier.weight(1f),
                        title = "Entrada",
                        subtitle = "Activar QR",
                        primary = selectedEvent != AttendanceEventType.CHECK_OUT,
                        enabled = !state.submitting,
                        onClick = { onEvent(AttendanceEventType.CHECK_IN) },
                    )
                    AttendanceAction(
                        modifier = Modifier.weight(1f),
                        title = "Salida",
                        subtitle = "Activar QR",
                        primary = selectedEvent == AttendanceEventType.CHECK_OUT,
                        enabled = !state.submitting,
                        onClick = { onEvent(AttendanceEventType.CHECK_OUT) },
                    )
                }

                Text(
                    modifier = Modifier.fillMaxWidth(),
                    text = "Token efímero · sin contraseñas en el QR",
                    style = MaterialTheme.typography.labelSmall,
                    color = TalentInkSoft,
                    textAlign = TextAlign.Center,
                )
            } else {
                AttendanceAction(
                    modifier = Modifier.fillMaxWidth(),
                    title = "Registrar entrada",
                    subtitle = "Luego muestra tu QR al lector",
                    primary = selectedEvent != AttendanceEventType.CHECK_OUT,
                    enabled = !state.submitting,
                    onClick = { onEvent(AttendanceEventType.CHECK_IN) },
                )
                AttendanceAction(
                    modifier = Modifier.fillMaxWidth(),
                    title = "Registrar salida",
                    subtitle = "Luego muestra tu QR al lector",
                    primary = selectedEvent == AttendanceEventType.CHECK_OUT,
                    enabled = !state.submitting,
                    onClick = { onEvent(AttendanceEventType.CHECK_OUT) },
                )

                Surface(
                    shape = RoundedCornerShape(14.dp),
                    color = TalentSurfaceSoft,
                ) {
                    Text(
                        modifier = Modifier.padding(14.dp),
                        text = "El QR no contiene tu contraseña. Talent valida un token efímero emitido solo después de comprobar la llave privada de tu celular vinculado.",
                        style = MaterialTheme.typography.bodySmall,
                        color = TalentInkSoft,
                    )
                }
            }
        }
    }
}

@Composable
private fun KioskHeader(context: KioskContext) {
    BoxWithConstraints(modifier = Modifier.fillMaxWidth()) {
        if (maxWidth >= 620.dp) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(16.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                BrandBadge()
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = "Talent ID",
                        style = MaterialTheme.typography.headlineSmall,
                        fontWeight = FontWeight.Bold,
                        color = TalentNavy,
                    )
                    Text(
                        text = context.siteName,
                        style = MaterialTheme.typography.bodyMedium,
                        color = TalentInkSoft,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                }

                StatusPill(
                    label = "Kiosco conectado",
                    color = TalentSuccess,
                    background = TalentSuccessSoft,
                )

                Text(
                    modifier = Modifier.widthIn(max = 180.dp),
                    text = context.deviceName,
                    style = MaterialTheme.typography.labelMedium,
                    color = TalentInkSoft,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        } else {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(10.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                BrandBadge()
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = "Talent ID",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold,
                        color = TalentNavy,
                    )
                    Text(
                        text = context.siteName,
                        style = MaterialTheme.typography.labelMedium,
                        color = TalentInkSoft,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                }
                StatusPill(
                    label = "En línea",
                    color = TalentSuccess,
                    background = TalentSuccessSoft,
                )
            }
        }
    }
}

@Composable
private fun BrandBadge() {
    Surface(
        modifier = Modifier.size(40.dp),
        shape = RoundedCornerShape(12.dp),
        color = TalentNavy,
    ) {
        Box(contentAlignment = Alignment.Center) {
            Text(
                text = "TI",
                color = Color.White,
                fontWeight = FontWeight.Bold,
                style = MaterialTheme.typography.titleSmall,
            )
        }
    }
}

@Composable
private fun CameraStage(
    modifier: Modifier,
    controller: androidx.camera.view.LifecycleCameraController,
    submitting: Boolean,
    faceObservation: FaceObservation,
    faceReadyStable: Boolean,
) {
    var previewBitmap by remember { mutableStateOf<android.graphics.Bitmap?>(null) }

    val statusText = when {
        faceObservation.faceCount > 1 -> "Solo una persona"
        faceReadyStable -> "Rostro listo"
        faceObservation.faceCount == 1 && !faceObservation.largeEnough -> "Acércate un poco"
        faceObservation.faceCount == 1 && !faceObservation.centered -> "Céntrate en la cámara"
        faceObservation.faceCount == 1 -> "Mantén la posición"
        else -> "Mira a la cámara"
    }

    Surface(
        modifier = modifier,
        shape = RoundedCornerShape(24.dp),
        color = TalentNavy,
        shadowElevation = 2.dp,
    ) {
        Box(modifier = Modifier.fillMaxSize()) {
            CameraPreview(
                controller = controller,
                modifier = Modifier
                    .fillMaxSize()
                    .clip(RoundedCornerShape(24.dp)),
                onPreviewBitmap = { bitmap ->
                    previewBitmap = bitmap
                },
            )

            previewBitmap?.let { bitmap ->
                FocusedPrivacyPreview(
                    bitmap = bitmap,
                    observation = faceObservation,
                    modifier = Modifier.fillMaxSize(),
                )
            }

            FaceTrackingGuide(
                observation = faceObservation,
                ready = faceReadyStable,
                modifier = Modifier.fillMaxSize(),
            )

            Box(
                modifier = Modifier
                    .align(Alignment.TopCenter)
                    .padding(12.dp)
                    .background(
                        color = TalentNavy.copy(alpha = 0.72f),
                        shape = RoundedCornerShape(14.dp),
                    )
                    .padding(horizontal = 12.dp, vertical = 7.dp),
            ) {
                Text(
                    text = statusText,
                    color = Color.White,
                    style = MaterialTheme.typography.labelMedium,
                    fontWeight = FontWeight.SemiBold,
                    textAlign = TextAlign.Center,
                )
            }

            if (submitting) {
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .background(TalentNavy.copy(alpha = 0.78f)),
                    contentAlignment = Alignment.Center,
                ) {
                    Column(
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.spacedBy(14.dp),
                    ) {
                        CircularProgressIndicator(
                            modifier = Modifier.size(48.dp),
                            color = TalentCyan,
                            trackColor = Color.White.copy(alpha = 0.18f),
                        )
                        Text(
                            text = "Verificando identidad…",
                            color = Color.White,
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.SemiBold,
                        )
                        Text(
                            text = "Mantén el rostro frente a la cámara",
                            color = Color.White.copy(alpha = 0.75f),
                            style = MaterialTheme.typography.bodyMedium,
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun FocusedPrivacyPreview(
    bitmap: android.graphics.Bitmap,
    observation: FaceObservation,
    modifier: Modifier = Modifier,
) {
    val imageBitmap = remember(bitmap) { bitmap.asImageBitmap() }

    Box(modifier = modifier) {
        Image(
            bitmap = imageBitmap,
            contentDescription = null,
            modifier = Modifier
                .fillMaxSize()
                .blur(10.dp),
            contentScale = ContentScale.FillBounds,
        )

        Canvas(modifier = Modifier.fillMaxSize()) {
            val oval = faceOvalRect(size, observation)
            val ovalPath = Path().apply { addOval(oval) }

            clipPath(ovalPath) {
                drawImage(
                    image = imageBitmap,
                    srcOffset = IntOffset.Zero,
                    srcSize = IntSize(imageBitmap.width, imageBitmap.height),
                    dstOffset = IntOffset.Zero,
                    dstSize = IntSize(size.width.roundToInt(), size.height.roundToInt()),
                )
            }
        }
    }
}

private fun faceOvalRect(
    canvasSize: Size,
    observation: FaceObservation,
): Rect {
    val bounds = observation.bounds
    if (bounds == null) {
        val guideWidth = canvasSize.width * 0.48f
        val guideHeight = canvasSize.height * 0.62f
        val left = (canvasSize.width - guideWidth) / 2f
        val top = (canvasSize.height - guideHeight) / 2f
        return Rect(
            left = left,
            top = top,
            right = left + guideWidth,
            bottom = top + guideHeight,
        )
    }

    val scale = maxOf(
        canvasSize.width / bounds.imageWidth.toFloat(),
        canvasSize.height / bounds.imageHeight.toFloat(),
    )
    val renderedWidth = bounds.imageWidth * scale
    val renderedHeight = bounds.imageHeight * scale
    val offsetX = (canvasSize.width - renderedWidth) / 2f
    val offsetY = (canvasSize.height - renderedHeight) / 2f

    val rawLeft = offsetX + bounds.left * scale
    val rawTop = offsetY + bounds.top * scale
    val rawRight = offsetX + bounds.right * scale
    val rawBottom = offsetY + bounds.bottom * scale
    val faceWidth = rawRight - rawLeft
    val faceHeight = rawBottom - rawTop
    val horizontalPadding = faceWidth * 0.10f
    val verticalPadding = faceHeight * 0.10f

    return Rect(
        left = (rawLeft - horizontalPadding).coerceAtLeast(0f),
        top = (rawTop - verticalPadding).coerceAtLeast(0f),
        right = (rawRight + horizontalPadding).coerceAtMost(canvasSize.width),
        bottom = (rawBottom + verticalPadding).coerceAtMost(canvasSize.height),
    )
}

@Composable
private fun FaceTrackingGuide(
    observation: FaceObservation,
    ready: Boolean,
    modifier: Modifier = Modifier,
) {
    Canvas(modifier = modifier) {
        val oval = faceOvalRect(size, observation)
        val color = when {
            observation.faceCount > 1 -> TalentWarning
            ready -> TalentSuccess
            observation.bounds == null -> Color.White.copy(alpha = 0.52f)
            else -> TalentCyan
        }

        if (observation.bounds != null) {
            drawOval(
                color = color.copy(alpha = 0.08f),
                topLeft = Offset(oval.left, oval.top),
                size = Size(oval.width, oval.height),
            )
        }

        drawOval(
            color = color,
            topLeft = Offset(oval.left, oval.top),
            size = Size(oval.width, oval.height),
            style = Stroke(width = if (observation.bounds == null) 2.dp.toPx() else 3.dp.toPx()),
        )
    }
}

@Composable
private fun ActionPanel(
    modifier: Modifier,
    state: KioskUiState,
    captureError: String?,
    faceObservation: FaceObservation,
    faceReady: Boolean,
    onRetryPending: () -> Unit,
    onEvent: (AttendanceEventType) -> Unit,
    horizontalActions: Boolean = false,
) {
    val compact = horizontalActions
    val helperText = when {
        faceObservation.faceCount > 1 -> "Debe haber una sola persona frente a la cámara."
        faceReady -> "Rostro listo · elige Entrada o Salida."
        faceObservation.faceCount == 1 -> "Ajusta tu posición hasta que el óvalo se vea verde."
        else -> "Ubica tu rostro dentro del óvalo."
    }

    Surface(
        modifier = modifier,
        shape = RoundedCornerShape(if (compact) 20.dp else 26.dp),
        color = Color.White,
        shadowElevation = if (compact) 1.dp else 3.dp,
    ) {
        Column(
            modifier = Modifier.padding(if (compact) 14.dp else 20.dp),
            verticalArrangement = Arrangement.spacedBy(if (compact) 10.dp else 14.dp),
        ) {
            if (compact) {
                Text(
                    modifier = Modifier.fillMaxWidth(),
                    text = helperText,
                    style = MaterialTheme.typography.bodySmall,
                    color = TalentInkSoft,
                    textAlign = TextAlign.Center,
                )
            } else {
                Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text(
                        text = "¿Qué deseas registrar?",
                        style = MaterialTheme.typography.titleLarge,
                        fontWeight = FontWeight.Bold,
                        color = TalentInk,
                    )
                    Text(
                        text = helperText,
                        style = MaterialTheme.typography.bodyMedium,
                        color = TalentInkSoft,
                    )
                }
            }

            captureError?.let { ErrorBanner(it) }
            state.error?.let { ErrorBanner(it) }

            if (state.retryAvailable) {
                RetryBanner(
                    enabled = faceReady && !state.submitting,
                    onRetry = onRetryPending,
                )
            }

            if (horizontalActions) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    AttendanceAction(
                        modifier = Modifier.weight(1f),
                        title = "Entrada",
                        subtitle = "Inicio",
                        primary = true,
                        enabled = faceReady && !state.submitting,
                        onClick = { onEvent(AttendanceEventType.CHECK_IN) },
                    )
                    AttendanceAction(
                        modifier = Modifier.weight(1f),
                        title = "Salida",
                        subtitle = "Fin",
                        primary = false,
                        enabled = faceReady && !state.submitting,
                        onClick = { onEvent(AttendanceEventType.CHECK_OUT) },
                    )
                }

                Text(
                    modifier = Modifier.fillMaxWidth(),
                    text = "Imagen temporal · verificación segura",
                    style = MaterialTheme.typography.labelSmall,
                    color = TalentInkSoft,
                    textAlign = TextAlign.Center,
                )
            } else {
                AttendanceAction(
                    modifier = Modifier.fillMaxWidth(),
                    title = "Registrar entrada",
                    subtitle = "Marca el inicio de tu jornada",
                    primary = true,
                    enabled = faceReady && !state.submitting,
                    onClick = { onEvent(AttendanceEventType.CHECK_IN) },
                )
                AttendanceAction(
                    modifier = Modifier.fillMaxWidth(),
                    title = "Registrar salida",
                    subtitle = "Marca el cierre de tu jornada",
                    primary = false,
                    enabled = faceReady && !state.submitting,
                    onClick = { onEvent(AttendanceEventType.CHECK_OUT) },
                )

                Surface(
                    shape = RoundedCornerShape(14.dp),
                    color = TalentSurfaceSoft,
                ) {
                    Text(
                        modifier = Modifier.padding(14.dp),
                        text = "La detección del óvalo ocurre localmente en la tablet y no identifica quién eres. " +
                            "Cuando el rostro esté listo, Talent ID toma una imagen temporal para verificar tu identidad y registrar la marcación.",
                        style = MaterialTheme.typography.bodySmall,
                        color = TalentInkSoft,
                    )
                }
            }
        }
    }
}

@Composable
private fun AttendanceAction(
    modifier: Modifier,
    title: String,
    subtitle: String,
    primary: Boolean,
    enabled: Boolean,
    onClick: () -> Unit,
) {
    if (primary) {
        Button(
            modifier = modifier.heightIn(min = 64.dp),
            enabled = enabled,
            shape = RoundedCornerShape(18.dp),
            colors = ButtonDefaults.buttonColors(
                containerColor = TalentBlue,
                contentColor = Color.White,
            ),
            onClick = onClick,
        ) {
            Column(
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(2.dp),
            ) {
                Text(
                    text = title,
                    fontWeight = FontWeight.Bold,
                    style = MaterialTheme.typography.titleMedium,
                )
                Text(
                    text = subtitle,
                    style = MaterialTheme.typography.labelMedium,
                    color = Color.White.copy(alpha = 0.8f),
                )
            }
        }
    } else {
        FilledTonalButton(
            modifier = modifier.heightIn(min = 64.dp),
            enabled = enabled,
            shape = RoundedCornerShape(18.dp),
            colors = ButtonDefaults.filledTonalButtonColors(
                containerColor = MaterialTheme.colorScheme.primaryContainer,
                contentColor = TalentBlue,
            ),
            onClick = onClick,
        ) {
            Column(
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(2.dp),
            ) {
                Text(
                    text = title,
                    fontWeight = FontWeight.Bold,
                    style = MaterialTheme.typography.titleMedium,
                )
                Text(
                    text = subtitle,
                    style = MaterialTheme.typography.labelMedium,
                    color = TalentInkSoft,
                )
            }
        }
    }
}

@Composable
private fun PermissionPanel(
    modifier: Modifier,
    onRequestPermission: () -> Unit,
) {
    Surface(
        modifier = modifier,
        shape = RoundedCornerShape(28.dp),
        color = Color.White,
        shadowElevation = 3.dp,
    ) {
        Box(
            modifier = Modifier.padding(28.dp),
            contentAlignment = Alignment.Center,
        ) {
            Column(
                modifier = Modifier.widthIn(max = 480.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(14.dp),
            ) {
                Surface(
                    modifier = Modifier.size(72.dp),
                    shape = CircleShape,
                    color = MaterialTheme.colorScheme.primaryContainer,
                ) {
                    Box(contentAlignment = Alignment.Center) {
                        Text(
                            text = "ID",
                            color = TalentBlue,
                            style = MaterialTheme.typography.titleLarge,
                            fontWeight = FontWeight.Bold,
                        )
                    }
                }
                Text(
                    text = "Activa la cámara para continuar",
                    style = MaterialTheme.typography.headlineSmall,
                    fontWeight = FontWeight.Bold,
                    color = TalentInk,
                    textAlign = TextAlign.Center,
                )
                Text(
                    text = "La cámara frontal se usa únicamente durante la marcación. " +
                        "La fotografía temporal se elimina después de procesarse.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = TalentInkSoft,
                    textAlign = TextAlign.Center,
                )
                Button(
                    modifier = Modifier
                        .fillMaxWidth()
                        .heightIn(min = 52.dp),
                    onClick = onRequestPermission,
                ) {
                    Text("Permitir cámara")
                }
            }
        }
    }
}

@Composable
private fun RetryBanner(
    enabled: Boolean,
    onRetry: () -> Unit,
) {
    Surface(
        shape = RoundedCornerShape(16.dp),
        color = TalentWarningSoft,
    ) {
        Column(
            modifier = Modifier.padding(14.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Text(
                text = "La marcación quedó pendiente por conexión.",
                color = TalentWarning,
                fontWeight = FontWeight.SemiBold,
                style = MaterialTheme.typography.bodyMedium,
            )
            Text(
                text = "Puedes reintentar sin duplicar el registro.",
                color = TalentInkSoft,
                style = MaterialTheme.typography.bodySmall,
            )
            FilledTonalButton(
                enabled = enabled,
                onClick = onRetry,
            ) {
                Text("Reintentar marcación")
            }
        }
    }
}

@Composable
private fun SuccessOverlay(
    result: AttendanceResult,
    onDismiss: () -> Unit,
) {
    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(TalentNavy.copy(alpha = 0.68f))
            .padding(24.dp),
        contentAlignment = Alignment.Center,
    ) {
        Surface(
            modifier = Modifier
                .fillMaxWidth()
                .widthIn(max = 500.dp),
            shape = RoundedCornerShape(30.dp),
            color = Color.White,
            shadowElevation = 16.dp,
        ) {
            Column(
                modifier = Modifier.padding(30.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                Surface(
                    modifier = Modifier.size(76.dp),
                    shape = CircleShape,
                    color = TalentSuccessSoft,
                ) {
                    Box(contentAlignment = Alignment.Center) {
                        Text(
                            text = "✓",
                            color = TalentSuccess,
                            style = MaterialTheme.typography.headlineLarge,
                            fontWeight = FontWeight.Bold,
                        )
                    }
                }

                Text(
                    text = "Marcación registrada",
                    style = MaterialTheme.typography.headlineSmall,
                    fontWeight = FontWeight.Bold,
                    color = TalentInk,
                    textAlign = TextAlign.Center,
                )

                Text(
                    text = result.displayName,
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.SemiBold,
                    color = TalentNavy,
                    textAlign = TextAlign.Center,
                )

                StatusPill(
                    label = if (result.eventType == AttendanceEventType.CHECK_IN) {
                        "Entrada registrada"
                    } else {
                        "Salida registrada"
                    },
                    color = TalentSuccess,
                    background = TalentSuccessSoft,
                )

                Text(
                    text = if (result.verificationMethod == "qr") {
                        "Dispositivo móvil vinculado · QR de un solo uso"
                    } else {
                        "Identidad verificada · " +
                            String.format("%.1f", result.similarity ?: 0.0) + "%"
                    },
                    style = MaterialTheme.typography.bodyMedium,
                    color = TalentInkSoft,
                )

                Spacer(modifier = Modifier.height(4.dp))

                Button(
                    modifier = Modifier
                        .fillMaxWidth()
                        .heightIn(min = 52.dp),
                    onClick = onDismiss,
                ) {
                    Text("Listo")
                }

                Text(
                    text = "Esta confirmación se cerrará automáticamente.",
                    style = MaterialTheme.typography.labelMedium,
                    color = TalentInkSoft,
                )
            }
        }
    }
}

@Composable
private fun ErrorBanner(message: String) {
    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(14.dp),
        color = TalentDangerSoft,
    ) {
        Column(
            modifier = Modifier.padding(14.dp),
            verticalArrangement = Arrangement.spacedBy(3.dp),
        ) {
            Text(
                text = "No pudimos completar la acción",
                color = TalentDanger,
                style = MaterialTheme.typography.labelLarge,
                fontWeight = FontWeight.Bold,
            )
            Text(
                text = message,
                color = TalentInkSoft,
                style = MaterialTheme.typography.bodySmall,
            )
        }
    }
}

@Composable
private fun StatusPill(
    label: String,
    color: Color,
    background: Color,
) {
    Surface(
        shape = RoundedCornerShape(999.dp),
        color = background,
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 11.dp, vertical = 7.dp),
            horizontalArrangement = Arrangement.spacedBy(7.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Box(
                modifier = Modifier
                    .size(7.dp)
                    .background(color = color, shape = CircleShape),
            )
            Text(
                text = label,
                color = color,
                style = MaterialTheme.typography.labelMedium,
                fontWeight = FontWeight.SemiBold,
            )
        }
    }
}

@Composable
private fun BrandLockup(
    eyebrow: String,
    title: String,
    subtitle: String,
    centered: Boolean = false,
) {
    Column(
        modifier = Modifier.fillMaxWidth(),
        horizontalAlignment = if (centered) Alignment.CenterHorizontally else Alignment.Start,
        verticalArrangement = Arrangement.spacedBy(5.dp),
    ) {
        Text(
            text = eyebrow,
            style = MaterialTheme.typography.labelMedium,
            fontWeight = FontWeight.Bold,
            color = TalentBlue,
        )
        Text(
            text = title,
            style = MaterialTheme.typography.headlineMedium,
            fontWeight = FontWeight.Bold,
            color = TalentNavy,
            textAlign = if (centered) TextAlign.Center else TextAlign.Start,
        )
        Text(
            text = subtitle,
            style = MaterialTheme.typography.bodyMedium,
            color = TalentInkSoft,
            textAlign = if (centered) TextAlign.Center else TextAlign.Start,
        )
    }
}

@Composable
private fun FooterNote() {
    Text(
        modifier = Modifier.fillMaxWidth(),
        text = "Talent ID · ASIATI  •  Biometría o QR móvil vinculado para asistencia",
        style = MaterialTheme.typography.labelSmall,
        color = TalentInkSoft,
        textAlign = TextAlign.Center,
    )
}
