package com.asiati.talentid.camera

import android.content.Context
import android.net.Uri
import androidx.camera.core.CameraSelector
import androidx.camera.core.ExperimentalGetImage
import androidx.camera.core.ImageAnalysis
import androidx.camera.view.CameraController
import androidx.camera.view.LifecycleCameraController
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.core.content.ContextCompat
import androidx.lifecycle.LifecycleOwner
import com.google.mlkit.vision.barcode.Barcode
import com.google.mlkit.vision.barcode.BarcodeScannerOptions
import com.google.mlkit.vision.barcode.BarcodeScanning
import com.google.mlkit.vision.common.InputImage

private const val TALENT_QR_SCHEME = "talentid"
private const val TALENT_QR_HOST = "attendance"

fun extractTalentQrToken(rawValue: String): String? {
    val uri = runCatching { Uri.parse(rawValue.trim()) }.getOrNull() ?: return null
    if (uri.scheme != TALENT_QR_SCHEME || uri.host != TALENT_QR_HOST) {
        return null
    }
    val token = uri.getQueryParameter("token")?.trim().orEmpty()
    return token.takeIf { it.length >= 16 }
}

@OptIn(ExperimentalGetImage::class)
@Composable
fun rememberQrScannerController(
    context: Context,
    lifecycleOwner: LifecycleOwner,
    onQrCode: (String) -> Unit,
): LifecycleCameraController {
    val currentCallback = rememberUpdatedState(onQrCode)
    val scanner = remember {
        BarcodeScanning.getClient(
            BarcodeScannerOptions.Builder()
                .setBarcodeFormats(Barcode.FORMAT_QR_CODE)
                .build(),
        )
    }
    val controller = remember(context) {
        LifecycleCameraController(context).apply {
            cameraSelector = CameraSelector.DEFAULT_FRONT_CAMERA
            setEnabledUseCases(CameraController.IMAGE_ANALYSIS)
        }
    }

    DisposableEffect(lifecycleOwner, controller, scanner) {
        controller.setImageAnalysisAnalyzer(
            ContextCompat.getMainExecutor(context),
            ImageAnalysis.Analyzer { imageProxy ->
                val mediaImage = imageProxy.image
                if (mediaImage == null) {
                    imageProxy.close()
                    return@Analyzer
                }

                val input = InputImage.fromMediaImage(
                    mediaImage,
                    imageProxy.imageInfo.rotationDegrees,
                )
                scanner.process(input)
                    .addOnSuccessListener { barcodes ->
                        barcodes.asSequence()
                            .mapNotNull { barcode -> barcode.rawValue }
                            .mapNotNull(::extractTalentQrToken)
                            .firstOrNull()
                            ?.let(currentCallback.value)
                    }
                    .addOnCompleteListener {
                        imageProxy.close()
                    }
            },
        )
        controller.bindToLifecycle(lifecycleOwner)

        onDispose {
            controller.clearImageAnalysisAnalyzer()
            controller.unbind()
            scanner.close()
        }
    }

    return controller
}
