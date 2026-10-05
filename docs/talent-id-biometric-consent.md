# Talent ID — consentimiento biométrico y firma electrónica

## Objetivo

Talent ID no puede enrolar ni reconocer biometría facial de un empleado sin una decisión
biométrica vigente firmada por el propio titular. La autorización de uso de imagen corporativa
es independiente y no habilita reconocimiento facial.

## Estados

- `PENDING`: el empleado aún no ha firmado una decisión.
- `AUTHORIZED`: reconocimiento facial permitido.
- `DENIED`: el empleado decidió no autorizar biometría.
- `REVOKED`: existía una autorización previa y el empleado la revocó.

Los administradores pueden consultar el estado y descargar la evidencia firmada, pero no
pueden cambiar el estado de consentimiento.

## Firma electrónica

1. El empleado inicia sesión en Talent.
2. En **Mi perfil** revisa la versión vigente de la autorización.
3. Selecciona Autorizar, No autorizar o, cuando corresponda, Revocar.
4. Talent genera un OTP de seis dígitos vinculado a:
   - empleado,
   - decisión,
   - versión exacta del documento.
5. El OTP se envía al correo registrado del empleado.
6. El empleado confirma el OTP.
7. Talent genera un PDF de evidencia y conserva:
   - decisión,
   - versión del documento,
   - SHA-256 del documento base,
   - SHA-256 del PDF firmado,
   - fecha/hora del servidor,
   - correo verificado mediante OTP,
   - identificador de la cuenta autenticada,
   - hashes de IP y User-Agent para trazabilidad.

El OTP se almacena únicamente como HMAC-SHA256 y expira. Solicitar un nuevo OTP invalida
los desafíos anteriores para impedir reutilización.

## Enrolamiento y revocación

El endpoint administrativo de enrolamiento valida en backend que el estado sea
`AUTHORIZED`. La interfaz administrativa no contiene un checkbox para que Talento Humano
declare consentimiento en nombre del empleado.

Si el empleado firma `DENIED` o `REVOKED`, el reconocimiento queda bloqueado por estado.
Cuando existe un enrolamiento activo, Talent lo desactiva localmente e intenta eliminar del
proveedor biométrico el usuario y los vectores faciales asociados. Un fallo temporal del
proveedor no vuelve a habilitar el reconocimiento.

## Alternativa no biométrica

La decisión biométrica no controla la elegibilidad laboral ni la posibilidad de registrar
asistencia. Para `DENIED` y `REVOKED` se mantiene un mecanismo alternativo no biométrico.

La alternativa implementada es **QR dinámico + dispositivo móvil previamente vinculado**.
Para vincular o reemplazar el celular, Talent envía primero un OTP al correo registrado del
empleado. Esto evita que compartir únicamente el usuario y la contraseña sea suficiente para
apropiarse del mecanismo de asistencia.

Después de verificar el OTP, el navegador del celular genera una llave ECDSA P-256 y conserva
la llave privada como no exportable en IndexedDB. El servidor conserva únicamente la llave
pública. Para emitir cada QR, el celular debe firmar un reto efímero. El QR expira en
aproximadamente 30 segundos, se invalida al rotar y solo puede consumirse una vez en un kiosco
autorizado y en la sede asignada al empleado.

La marcación manual auditada queda como contingencia administrativa. El consentimiento
biométrico no se usa como requisito para acceder a esta alternativa.


## Contingencia manual auditada

Cuando un empleado no pueda marcar mediante reconocimiento facial ni QR móvil, un usuario con
permiso `talent_id.manage` puede registrar una entrada o salida manual desde la vista de
Asistencia. La operación exige:

- empleado activo y habilitado para asistencia;
- sede y horario configurados;
- tipo de evento (entrada/salida);
- fecha y hora de la contingencia;
- motivo obligatorio;
- identidad del administrador autenticado.

Las marcaciones manuales se almacenan con método `MANUAL`, `manual_reason` y
`created_by_sub`. No se permite editar destructivamente una marcación existente para
ocultar la trazabilidad. La fecha de contingencia no puede estar en el futuro y se limita a
31 días hacia atrás.


## Configuración

Variables de entorno:

```text
TALENT_ID_CONSENT_FROM_EMAIL=
TALENT_ID_CONSENT_OTP_SECRET=
TALENT_ID_CONSENT_OTP_TTL_SECONDS=600
TALENT_ID_CONSENT_OTP_COOLDOWN_SECONDS=60
TALENT_ID_CONSENT_OTP_MAX_ATTEMPTS=5

TALENT_ID_QR_CHALLENGE_TTL_SECONDS=60
TALENT_ID_QR_TOKEN_TTL_SECONDS=30
TALENT_ID_QR_MAX_SIGNATURE_ATTEMPTS=5

TALENT_ID_FROM_EMAIL=
TALENT_ID_MOBILE_LINK_OTP_SECRET=
TALENT_ID_MOBILE_LINK_OTP_TTL_SECONDS=600
TALENT_ID_MOBILE_LINK_OTP_COOLDOWN_SECONDS=60
TALENT_ID_MOBILE_LINK_OTP_MAX_ATTEMPTS=5
```

En producción:

- `TALENT_ID_CONSENT_OTP_SECRET` debe ser un secreto aleatorio de alta entropía y no debe
  almacenarse en el repositorio.
- `TALENT_ID_CONSENT_FROM_EMAIL` debe corresponder a una identidad habilitada para envío.
- El runtime necesita permiso mínimo para enviar el correo OTP.
- Las migraciones Alembic deben aplicarse hasta `042` antes de habilitar la interfaz.

## Endpoints

Empleado autenticado:

- `GET /api/talent-id/consent`
- `POST /api/talent-id/consent/otp`
- `POST /api/talent-id/consent/sign`
- `GET /api/talent-id/consent/document`

Marcación QR del empleado:

- `GET /api/talent-id/mobile-devices`
- `POST /api/talent-id/mobile-devices/link-otp`
- `POST /api/talent-id/mobile-devices`
- `DELETE /api/talent-id/mobile-devices/{device_id}`
- `POST /api/talent-id/mobile-devices/{device_id}/challenge`
- `POST /api/talent-id/mobile-qr`
- `POST /v1/kiosk/qr`

Administración:

- `POST /api/talent-id/attendance/manual`
- `GET /api/talent-id/employees/{employee_id}/consent`
- `GET /api/talent-id/employees/{employee_id}/consent/document`

El enrolamiento existente en
`POST /api/talent-id/employees/{employee_id}/biometrics/enroll` rechaza solicitudes sin
consentimiento `AUTHORIZED`.
