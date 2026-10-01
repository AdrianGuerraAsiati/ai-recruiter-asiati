package com.asiati.talentid.kiosk

import android.Manifest
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.asiati.talentid.camera.CameraPreview
import com.asiati.talentid.camera.captureKioskPhoto
import com.asiati.talentid.camera.rememberKioskCameraController
import com.asiati.talentid.core.network.AttendanceEventType
import com.asiati.talentid.core.network.AttendanceResult
import com.asiati.talentid.core.network.KioskContext
import kotlinx.coroutines.launch

@Composable
fun TalentIdApp(viewModel: KioskViewModel) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val kioskContext = state.context

    MaterialTheme {
        Surface(modifier = Modifier.fillMaxSize()) {
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
            .padding(32.dp),
        contentAlignment = Alignment.Center,
    ) {
        Column(
            modifier = Modifier.fillMaxWidth(),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Text(
                text = "Talent ID",
                style = MaterialTheme.typography.headlineLarge,
                fontWeight = FontWeight.Bold,
            )
            Text(
                text = "Configuración inicial del kiosco",
                style = MaterialTheme.typography.titleMedium,
            )
            Text(
                text = "Ingresa las credenciales entregadas al registrar esta tablet. " +
                    "El secreto se cifra con Android Keystore y no se vuelve a mostrar.",
                style = MaterialTheme.typography.bodyMedium,
            )

            OutlinedTextField(
                modifier = Modifier.fillMaxWidth(),
                value = deviceId,
                onValueChange = { deviceId = it },
                label = { Text("Device ID") },
                singleLine = true,
            )

            OutlinedTextField(
                modifier = Modifier.fillMaxWidth(),
                value = secret,
                onValueChange = { secret = it },
                label = { Text("Device Secret") },
                visualTransformation = PasswordVisualTransformation(),
                singleLine = true,
            )

            error?.let { ErrorMessage(it) }

            Button(
                modifier = Modifier.fillMaxWidth(),
                onClick = { onProvision(deviceId, secret) },
            ) {
                Text("Vincular dispositivo")
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
            .padding(32.dp),
        contentAlignment = Alignment.Center,
    ) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Text(
                text = "Talent ID",
                style = MaterialTheme.typography.headlineLarge,
                fontWeight = FontWeight.Bold,
            )

            if (loading) {
                CircularProgressIndicator()
                Text("Validando dispositivo…")
            } else {
                error?.let { ErrorMessage(it) }
                Button(onClick = onRetry) {
                    Text("Reintentar conexión")
                }
                OutlinedButton(onClick = onReset) {
                    Text("Reconfigurar dispositivo")
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

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Header(context)

        if (!cameraGranted) {
            Box(
                modifier = Modifier
                    .weight(1f)
                    .fillMaxWidth()
                    .background(
                        MaterialTheme.colorScheme.surfaceVariant,
                        RoundedCornerShape(24.dp),
                    ),
                contentAlignment = Alignment.Center,
            ) {
                Column(
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    Text("Talent ID necesita acceso a la cámara.")
                    Button(onClick = {
                        permissionLauncher.launch(Manifest.permission.CAMERA)
                    }) {
                        Text("Permitir cámara")
                    }
                }
            }
        } else {
            val controller = rememberKioskCameraController(
                context = androidContext,
                lifecycleOwner = lifecycleOwner,
            )

            CameraPreview(
                controller = controller,
                modifier = Modifier
                    .fillMaxWidth()
                    .weight(1f)
                    .background(
                        MaterialTheme.colorScheme.surfaceVariant,
                        RoundedCornerShape(24.dp),
                    ),
            )

            captureError?.let { ErrorMessage(it) }
            state.error?.let { ErrorMessage(it) }

            state.lastResult?.let {
                ResultCard(
                    result = it,
                    onDismiss = onDismissResult,
                )
            }

            if (state.retryAvailable) {
                FilledTonalButton(
                    modifier = Modifier.fillMaxWidth(),
                    enabled = !state.submitting,
                    onClick = onRetryPending,
                ) {
                    Text("Reintentar la misma marcación")
                }
            }

            AttendanceButtons(
                enabled = !state.submitting,
                onEvent = { eventType ->
                    captureError = null
                    scope.launch {
                        runCatching {
                            captureKioskPhoto(
                                context = androidContext,
                                controller = controller,
                            )
                        }.onSuccess { file ->
                            onSubmit(file, eventType)
                        }.onFailure {
                            captureError = "No fue posible tomar la fotografía."
                        }
                    }
                },
            )

            if (state.submitting) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.Center,
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    CircularProgressIndicator()
                    Text(
                        modifier = Modifier.padding(start = 12.dp),
                        text = "Verificando identidad…",
                    )
                }
            }
        }
    }
}

@Composable
private fun Header(context: KioskContext) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column {
            Text(
                text = "Talent ID",
                style = MaterialTheme.typography.headlineMedium,
                fontWeight = FontWeight.Bold,
            )
            Text(
                text = context.siteName,
                style = MaterialTheme.typography.bodyLarge,
            )
        }
        Text(
            text = context.deviceName,
            style = MaterialTheme.typography.bodyMedium,
        )
    }
}

@Composable
private fun AttendanceButtons(
    enabled: Boolean,
    onEvent: (AttendanceEventType) -> Unit,
) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Button(
            modifier = Modifier.weight(1f),
            enabled = enabled,
            onClick = { onEvent(AttendanceEventType.CHECK_IN) },
        ) {
            Text("Entrada")
        }
        FilledTonalButton(
            modifier = Modifier.weight(1f),
            enabled = enabled,
            onClick = { onEvent(AttendanceEventType.CHECK_OUT) },
        ) {
            Text("Salida")
        }
    }
}

@Composable
private fun ResultCard(
    result: AttendanceResult,
    onDismiss: () -> Unit,
) {
    Surface(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(20.dp),
        color = MaterialTheme.colorScheme.primaryContainer,
    ) {
        Column(
            modifier = Modifier.padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            Text(
                text = "Marcación registrada",
                style = MaterialTheme.typography.titleLarge,
                fontWeight = FontWeight.Bold,
            )
            Text(result.displayName)
            Text(
                if (result.eventType == AttendanceEventType.CHECK_IN) {
                    "Entrada"
                } else {
                    "Salida"
                },
            )
            Text(String.format("Coincidencia: %.1f%%", result.similarity))
            OutlinedButton(onClick = onDismiss) {
                Text("Cerrar")
            }
        }
    }
}

@Composable
private fun ErrorMessage(message: String) {
    Text(
        text = message,
        color = MaterialTheme.colorScheme.error,
        style = MaterialTheme.typography.bodyMedium,
    )
}
