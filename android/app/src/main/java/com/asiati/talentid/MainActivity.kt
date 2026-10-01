package com.asiati.talentid

import android.os.Bundle
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.lifecycle.viewmodel.compose.viewModel
import com.asiati.talentid.core.network.TalentIdApi
import com.asiati.talentid.core.security.DeviceCredentialStore
import com.asiati.talentid.kiosk.KioskViewModel
import com.asiati.talentid.kiosk.TalentIdApp

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)

        val factory = KioskViewModel.Factory(
            credentialStore = DeviceCredentialStore(applicationContext),
            api = TalentIdApi(BuildConfig.TALENT_ID_API_BASE_URL),
        )

        setContent {
            val kioskViewModel: KioskViewModel = viewModel(factory = factory)
            TalentIdApp(kioskViewModel)
        }
    }
}
