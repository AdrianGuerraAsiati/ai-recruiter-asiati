# Talent ID Android Kiosk

Native Android reception kiosk for Talent ID.

## Current scope

- Kotlin + Jetpack Compose.
- CameraX front-camera preview and JPEG capture.
- One-time kiosk provisioning with `deviceId + deviceSecret`.
- Device secret encrypted with Android Keystore (AES-GCM).
- Validation against `GET /v1/kiosk/context`.
- Facial attendance through `POST /v1/kiosk/recognize`.
- Check-in and check-out.
- Network-safe retry with the same idempotency key.
- Temporary captured images are removed after success or a final error.
- No AWS IAM credentials and no administrative API key inside the APK.

PIN/QR fallback, Face Liveness and managed-device lock task mode are subsequent slices.

## Requirements

- JDK 17.
- Gradle 9.6.
- Android SDK 36 (stable).
- Android 7.0 / API 24 or newer for the device.

## Backend URL

The app reads the backend address from a Gradle property:

```text
TALENT_ID_API_BASE_URL=https://your-talent-id-api.example.com
```

For a local command:

```powershell
cd android
gradle :app:assembleDebug -PTALENT_ID_API_BASE_URL=https://your-api.example.com
```

The default URL is intentionally invalid so an APK cannot accidentally point at an unknown environment.

## Provisioning

An administrator first creates the kiosk through the Talent ID backend. The backend returns:

- `device_id`
- `device_secret` (shown once)

Those two values are entered on the tablet's initial setup screen.

The app stores the device ID locally and encrypts the secret using an AES key held by Android Keystore. It then validates the credentials against the assigned site's kiosk context.

## Attendance request

For every capture the app generates a new idempotency key and sends:

- `X-Device-Id`
- `X-Device-Secret`
- `Idempotency-Key`
- `event_type=check_in|check_out`
- temporary JPEG image

If the network fails after submission, retry uses the same image and idempotency key so the backend can return the original attendance event without duplicating the mark or repeating face recognition.
