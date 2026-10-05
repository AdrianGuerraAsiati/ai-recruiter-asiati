package com.asiati.talentid.ui

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

val TalentNavy = Color(0xFF071426)
val TalentNavySoft = Color(0xFF0D2039)
val TalentBlue = Color(0xFF185ADB)
val TalentBlueBright = Color(0xFF3478F6)
val TalentCyan = Color(0xFF16C7C2)
val TalentViolet = Color(0xFF7357E8)
val TalentCanvas = Color(0xFFF3F6FB)
val TalentSurfaceSoft = Color(0xFFF8FAFF)
val TalentBorder = Color(0xFFDFE6F0)
val TalentInk = Color(0xFF101B2D)
val TalentInkSoft = Color(0xFF526078)
val TalentSuccess = Color(0xFF128565)
val TalentSuccessSoft = Color(0xFFE8F8F2)
val TalentDanger = Color(0xFFC03F58)
val TalentDangerSoft = Color(0xFFFFF0F2)
val TalentWarning = Color(0xFF9A6610)
val TalentWarningSoft = Color(0xFFFFF7DF)

private val TalentIdColors = lightColorScheme(
    primary = TalentBlue,
    onPrimary = Color.White,
    primaryContainer = Color(0xFFEAF1FF),
    onPrimaryContainer = TalentNavy,
    secondary = TalentCyan,
    onSecondary = TalentNavy,
    tertiary = TalentViolet,
    background = TalentCanvas,
    onBackground = TalentInk,
    surface = Color.White,
    onSurface = TalentInk,
    surfaceVariant = TalentSurfaceSoft,
    onSurfaceVariant = TalentInkSoft,
    outline = TalentBorder,
    error = TalentDanger,
    errorContainer = TalentDangerSoft,
    onErrorContainer = TalentDanger,
)

@Composable
fun TalentIdTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = TalentIdColors,
        typography = Typography(),
        content = content,
    )
}
