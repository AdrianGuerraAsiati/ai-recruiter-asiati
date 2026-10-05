package com.asiati.talentid.kiosk

import android.Manifest
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Canvas
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
import androidx.compose.foundation.layout.weight
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
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.asiati.talentid.camera.CameraPreview
import com.asiati.talentid.camera.captureKioskPhoto
import com.asiati.talentid.camera.rememberKioskCameraController
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

@Composable
private fun KioskScreen(
    context: KioskContext,
    state: KioskUiState,
    onSubmit: (java.io.File, AttendanceEventType) -> Unit,
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

    BoxWithConstraints(
        modifier = Modifier
            .fillMaxSize()
            .background(TalentCanvas),
    ) {
        val wideLayout = maxWidth >= 820.dp

        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(if (wideLayout) 28.dp else 18.dp),
            verticalArrangement = Arrangement.spacedBy(18.dp),
        ) {
            KioskHeader(context)

            if (!cameraGranted) {
                PermissionPanel(
                    modifier = Modifier
                        .fillMaxWidth()
                        .weight(1f),
                    onRequestPermission = {
                        permissionLauncher.launch(Manifest.permission.CAMERA)
                    },
                )
            } else {
                val controller = rememberKioskCameraController(
                    context = androidContext,
                    lifecycleOwner = lifecycleOwner,
                )

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
                        )
                        ActionPanel(
                            modifier = Modifier.weight(0.85f),
                            state = state.copy(submitting = state.submitting || capturing),
                            captureError = captureError,
                            onRetryPending = onRetryPending,
                            onEvent = { eventType ->
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
                            },
                        )
                    }
                } else {
                    CameraStage(
                        modifier = Modifier
                            .fillMaxWidth()
                            .weight(1f),
                        controller = controller,
                        submitting = state.submitting || capturing,
                    )
                    ActionPanel(
                        modifier = Modifier.fillMaxWidth(),
                        state = state.copy(submitting = state.submitting || capturing),
                        captureError = captureError,
                        onRetryPending = onRetryPending,
                        horizontalActions = true,
                        onEvent = { eventType ->
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
                                }.onFailure {
                                    captureError = "No fue posible tomar la fotografía. Intenta de nuevo."
                                }
                            }
                        },
                    )
                }
            }

            FooterNote()
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
            Column(
                modifier = Modifier.fillMaxWidth(),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(12.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    BrandBadge()
                    Column(modifier = Modifier.weight(1f)) {
                        Text(
                            text = "Talent ID",
                            style = MaterialTheme.typography.titleLarge,
                            fontWeight = FontWeight.Bold,
                            color = TalentNavy,
                        )
                        Text(
                            text = context.siteName,
                            style = MaterialTheme.typography.bodySmall,
                            color = TalentInkSoft,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                        )
                    }
                    StatusPill(
                        label = "Conectado",
                        color = TalentSuccess,
                        background = TalentSuccessSoft,
                    )
                }
                Text(
                    text = context.deviceName,
                    style = MaterialTheme.typography.labelSmall,
                    color = TalentInkSoft,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }
    }
}

@Composable
private fun BrandBadge() {
    Surface(
        modifier = Modifier.size(46.dp),
        shape = RoundedCornerShape(14.dp),
        color = TalentNavy,
    ) {
        Box(contentAlignment = Alignment.Center) {
            Text(
                text = "TI",
                color = Color.White,
                fontWeight = FontWeight.Bold,
                style = MaterialTheme.typography.titleMedium,
            )
        }
    }
}

@Composable
private fun CameraStage(
    modifier: Modifier,
    controller: androidx.camera.view.LifecycleCameraController,
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
                        color = TalentNavy.copy(alpha = 0.76f),
                        shape = RoundedCornerShape(18.dp),
                    )
                    .padding(horizontal = 16.dp, vertical = 9.dp),
            ) {
                Text(
                    text = "Mira a la cámara y centra tu rostro",
                    color = Color.White,
                    style = MaterialTheme.typography.labelLarge,
                    fontWeight = FontWeight.SemiBold,
                )
            }

            FaceGuide(
                modifier = Modifier
                    .align(Alignment.Center)
                    .size(width = 205.dp, height = 270.dp),
            )

            Box(
                modifier = Modifier
                    .align(Alignment.BottomCenter)
                    .padding(18.dp)
                    .background(
                        color = TalentNavy.copy(alpha = 0.76f),
                        shape = RoundedCornerShape(16.dp),
                    )
                    .padding(horizontal = 14.dp, vertical = 8.dp),
            ) {
                Text(
                    text = "Una persona · rostro visible · buena iluminación",
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
private fun FaceGuide(modifier: Modifier = Modifier) {
    Canvas(modifier = modifier) {
        drawOval(
            color = Color.White.copy(alpha = 0.94f),
            style = Stroke(width = 3.dp.toPx()),
        )
        drawOval(
            color = TalentCyan.copy(alpha = 0.55f),
            style = Stroke(width = 1.dp.toPx()),
        )
    }
}

@Composable
private fun ActionPanel(
    modifier: Modifier,
    state: KioskUiState,
    captureError: String?,
    onRetryPending: () -> Unit,
    onEvent: (AttendanceEventType) -> Unit,
    horizontalActions: Boolean = false,
) {
    Surface(
        modifier = modifier,
        shape = RoundedCornerShape(26.dp),
        color = Color.White,
        shadowElevation = 3.dp,
    ) {
        Column(
            modifier = Modifier.padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(
                    text = "¿Qué deseas registrar?",
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.Bold,
                    color = TalentInk,
                )
                Text(
                    text = "Selecciona una opción. La foto se toma automáticamente.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = TalentInkSoft,
                )
            }

            captureError?.let { ErrorBanner(it) }
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
                    horizontalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    AttendanceAction(
                        modifier = Modifier.weight(1f),
                        title = "Entrada",
                        subtitle = "Inicio de jornada",
                        primary = true,
                        enabled = !state.submitting,
                        onClick = { onEvent(AttendanceEventType.CHECK_IN) },
                    )
                    AttendanceAction(
                        modifier = Modifier.weight(1f),
                        title = "Salida",
                        subtitle = "Fin de jornada",
                        primary = false,
                        enabled = !state.submitting,
                        onClick = { onEvent(AttendanceEventType.CHECK_OUT) },
                    )
                }
            } else {
                AttendanceAction(
                    modifier = Modifier.fillMaxWidth(),
                    title = "Registrar entrada",
                    subtitle = "Marca el inicio de tu jornada",
                    primary = true,
                    enabled = !state.submitting,
                    onClick = { onEvent(AttendanceEventType.CHECK_IN) },
                )
                AttendanceAction(
                    modifier = Modifier.fillMaxWidth(),
                    title = "Registrar salida",
                    subtitle = "Marca el cierre de tu jornada",
                    primary = false,
                    enabled = !state.submitting,
                    onClick = { onEvent(AttendanceEventType.CHECK_OUT) },
                )
            }

            Surface(
                shape = RoundedCornerShape(14.dp),
                color = TalentSurfaceSoft,
            ) {
                Text(
                    modifier = Modifier.padding(14.dp),
                    text = "No necesitas tocar la pantalla después de elegir. " +
                        "Talent ID captura una imagen temporal, verifica tu identidad y registra la marcación.",
                    style = MaterialTheme.typography.bodySmall,
                    color = TalentInkSoft,
                )
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
            modifier = modifier.heightIn(min = 76.dp),
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
            modifier = modifier.heightIn(min = 76.dp),
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
                    text = "Identidad verificada · " +
                        String.format("%.1f", result.similarity) + "%",
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
        text = "Talent ID · ASIATI  •  Reconocimiento facial para control de asistencia",
        style = MaterialTheme.typography.labelSmall,
        color = TalentInkSoft,
        textAlign = TextAlign.Center,
    )
}
