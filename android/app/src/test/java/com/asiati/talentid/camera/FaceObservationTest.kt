package com.asiati.talentid.camera

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class FaceObservationTest {
    private val bounds = FaceBounds(
        left = 100f,
        top = 120f,
        right = 300f,
        bottom = 420f,
        imageWidth = 640,
        imageHeight = 480,
    )

    @Test
    fun readyRequiresExactlyOneCenteredLargeFace() {
        assertTrue(
            FaceObservation(
                faceCount = 1,
                bounds = bounds,
                centered = true,
                largeEnough = true,
                tooLarge = false,
                fullyVisible = true,
            ).ready,
        )
    }

    @Test
    fun multipleOrMisalignedFacesAreNotReady() {
        assertFalse(
            FaceObservation(
                faceCount = 2,
                bounds = bounds,
                centered = true,
                largeEnough = true,
                tooLarge = false,
                fullyVisible = true,
            ).ready,
        )
        assertFalse(
            FaceObservation(
                faceCount = 1,
                bounds = bounds,
                centered = false,
                largeEnough = true,
                tooLarge = false,
                fullyVisible = true,
            ).ready,
        )
        assertFalse(
            FaceObservation(
                faceCount = 1,
                bounds = bounds,
                centered = true,
                largeEnough = false,
                tooLarge = false,
                fullyVisible = true,
            ).ready,
        )
        assertFalse(
            FaceObservation(
                faceCount = 1,
                bounds = bounds,
                centered = true,
                largeEnough = true,
                tooLarge = true,
                fullyVisible = true,
            ).ready,
        )
        assertFalse(
            FaceObservation(
                faceCount = 1,
                bounds = bounds,
                centered = true,
                largeEnough = true,
                tooLarge = false,
                fullyVisible = false,
            ).ready,
        )
    }
}
