package com.asiati.talentid.camera

import android.content.Context
import android.os.SystemClock
import androidx.camera.core.CameraSelector
import androidx.camera.core.ExperimentalGetImage
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageCapture
import androidx.camera.core.ImageCaptureException
import androidx.camera.view.CameraController
import androidx.camera.view.LifecycleCameraController
import androidx.camera.view.PreviewView
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import androidx.lifecycle.LifecycleOwner
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.face.FaceDetection
import com.google.mlkit.vision.face.FaceDetectorOptions
import java.io.File
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import kotlinx.coroutines.delay
import kotlinx.coroutines.suspendCancellableCoroutine

data class FaceBounds(
    val left: Float,
    val top: Float,
    val right: Float,
    val bottom: Float,
    val imageWidth: Int,
    val imageHeight: Int,
)

data class FaceObservation(
    val faceCount: Int = 0,
    val bounds: FaceBounds? = null,
    val centered: Boolean = false,
    val largeEnough: Boolean = false,
) {
    val ready: Boolean
        get() = faceCount == 1 && bounds != null && centered && largeEnough
}

private const val FACE_UI_UPDATE_INTERVAL_MS = 90L

@OptIn(ExperimentalGetImage::class)
@Composable
fun rememberKioskCameraController(
    context: Context,
    lifecycleOwner: LifecycleOwner,
    onFaceObservation: (FaceObservation) -> Unit = {},
): LifecycleCameraController {
    val currentCallback = rememberUpdatedState(onFaceObservation)
    val detector = remember {
        FaceDetection.getClient(
            FaceDetectorOptions.Builder()
                .setPerformanceMode(FaceDetectorOptions.PERFORMANCE_MODE_FAST)
                .setMinFaceSize(0.12f)
                .build(),
        )
    }
    val controller = remember(context) {
        LifecycleCameraController(context).apply {
            cameraSelector = CameraSelector.DEFAULT_FRONT_CAMERA
            setEnabledUseCases(
                CameraController.IMAGE_CAPTURE or CameraController.IMAGE_ANALYSIS,
            )
        }
    }

    DisposableEffect(lifecycleOwner, controller, detector) {
        var lastUiUpdate = 0L

        controller.setImageAnalysisAnalyzer(
            ContextCompat.getMainExecutor(context),
            ImageAnalysis.Analyzer { imageProxy ->
                val mediaImage = imageProxy.image
                if (mediaImage == null) {
                    imageProxy.close()
                    return@Analyzer
                }

                val rotation = imageProxy.imageInfo.rotationDegrees
                val imageWidth = if (rotation == 90 || rotation == 270) {
                    imageProxy.height
                } else {
                    imageProxy.width
                }
                val imageHeight = if (rotation == 90 || rotation == 270) {
                    imageProxy.width
                } else {
                    imageProxy.height
                }

                val input = InputImage.fromMediaImage(mediaImage, rotation)
                detector.process(input)
                    .addOnSuccessListener { faces ->
                        val now = SystemClock.elapsedRealtime()
                        if (now - lastUiUpdate < FACE_UI_UPDATE_INTERVAL_MS) {
                            return@addOnSuccessListener
                        }
                        lastUiUpdate = now

                        val primary = faces.maxByOrNull { face ->
                            face.boundingBox.width() * face.boundingBox.height()
                        }
                        val bounds = primary?.boundingBox?.let { rect ->
                            // PreviewView mirrors the front camera, so mirror the X coordinates
                            // to keep the UX oval visually attached to the person's face.
                            FaceBounds(
                                left = (imageWidth - rect.right).toFloat(),
                                top = rect.top.toFloat(),
                                right = (imageWidth - rect.left).toFloat(),
                                bottom = rect.bottom.toFloat(),
                                imageWidth = imageWidth,
                                imageHeight = imageHeight,
                            )
                        }

                        val centered = bounds?.let {
                            val centerX = ((it.left + it.right) / 2f) / it.imageWidth
                            val centerY = ((it.top + it.bottom) / 2f) / it.imageHeight
                            centerX in 0.22f..0.78f && centerY in 0.18f..0.78f
                        } ?: false

                        val largeEnough = bounds?.let {
                            val widthRatio = (it.right - it.left) / it.imageWidth
                            val heightRatio = (it.bottom - it.top) / it.imageHeight
                            widthRatio >= 0.18f && heightRatio >= 0.24f
                        } ?: false

                        currentCallback.value(
                            FaceObservation(
                                faceCount = faces.size,
                                bounds = bounds,
                                centered = centered,
                                largeEnough = largeEnough,
                            ),
                        )
                    }
                    .addOnFailureListener {
                        currentCallback.value(FaceObservation())
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
            detector.close()
        }
    }

    return controller
}

@Composable
fun CameraPreview(
    controller: LifecycleCameraController,
    modifier: Modifier = Modifier,
    onPreviewBitmap: ((android.graphics.Bitmap) -> Unit)? = null,
) {
    val context = LocalContext.current
    val currentBitmapCallback = rememberUpdatedState(onPreviewBitmap)
    val previewView = remember(context, controller) {
        PreviewView(context).apply {
            scaleType = PreviewView.ScaleType.FILL_CENTER
            implementationMode = PreviewView.ImplementationMode.COMPATIBLE
            this.controller = controller
        }
    }

    AndroidView(
        modifier = modifier,
        factory = { previewView },
        update = { preview ->
            preview.controller = controller
        },
    )

    LaunchedEffect(previewView, onPreviewBitmap != null) {
        if (onPreviewBitmap == null) return@LaunchedEffect

        while (true) {
            previewView.bitmap?.let { bitmap ->
                currentBitmapCallback.value?.invoke(bitmap)
            }
            delay(120)
        }
    }
}

suspend fun captureKioskPhoto(
    context: Context,
    controller: LifecycleCameraController,
): File = suspendCancellableCoroutine { continuation ->
    val file = File.createTempFile("talent-id-", ".jpg", context.cacheDir)
    val outputOptions = ImageCapture.OutputFileOptions.Builder(file).build()

    controller.takePicture(
        outputOptions,
        ContextCompat.getMainExecutor(context),
        object : ImageCapture.OnImageSavedCallback {
            override fun onImageSaved(outputFileResults: ImageCapture.OutputFileResults) {
                if (continuation.isActive) {
                    continuation.resume(file)
                }
            }

            override fun onError(exception: ImageCaptureException) {
                file.delete()
                if (continuation.isActive) {
                    continuation.resumeWithException(exception)
                }
            }
        },
    )

    continuation.invokeOnCancellation {
        file.delete()
    }
}
