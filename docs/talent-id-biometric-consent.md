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

## Aceptación electrónica

1. El empleado inicia sesión en Talent.
2. En **Mi perfil > Talent ID** ve una casilla de autorización biométrica cuando no existe una autorización vigente.
3. Puede abrir la versión completa de la autorización antes de decidir.
4. Marca expresamente la casilla que indica que autoriza el tratamiento biométrico y selecciona **Aceptar y continuar**.
5. Talent registra un evento inmutable y genera un comprobante PDF con:
   - decisión `AUTHORIZED`;
   - versión exacta del documento;
   - SHA-256 del documento base;
   - SHA-256 del comprobante PDF;
   - fecha/hora del servidor;
   - cuenta Talent autenticada;
   - origen de la aceptación;
   - hashes de IP y User-Agent cuando el secreto de auditoría está configurado.

La casilla desaparece después de aceptar y queda únicamente el estado de autorización, fecha,
versión, acceso al comprobante y opción de revocación. La interfaz no permite a Talento Humano
autorizar en nombre del empleado.

La revocación se confirma desde la misma sesión autenticada. Al revocar, Talent ID bloquea
el reconocimiento facial de inmediato e inicia la limpieza de los datos biométricos del proveedor.

## Enrolamiento y revocación

El endpoint administrativo de enrolamiento valida en backend que el estado sea
`AUTHORIZED`. La casilla de autorización solo existe en la experiencia autenticada del
propio empleado; la interfaz administrativa no permite que Talento Humano declare
consentimiento en su nombre.

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



## Eliminación biométrica pendiente

Al negar o revocar una autorización vigente, Talent bloquea inmediatamente el reconocimiento
facial y marca el enrolamiento como inactivo. La eliminación en el proveedor biométrico se
intenta en ese mismo flujo.

Si el proveedor no responde, Talent conserva el estado
`provider_cleanup_pending=true`, el último error y la fecha del intento. El administrador
puede reintentar la eliminación desde el panel del empleado mediante:

- `POST /api/talent-id/employees/{employee_id}/biometrics/purge-provider`

La revocación sigue siendo efectiva aunque el proveedor externo esté temporalmente
indisponible; el pendiente existe únicamente para garantizar la eliminación posterior de los
datos biométricos externos.


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
- Las migraciones Alembic deben aplicarse hasta `043` antes de habilitar la interfaz.

## Endpoints

Empleado autenticado:

- `GET /api/talent-id/consent`
- `POST /api/talent-id/consent/accept`
- `POST /api/talent-id/consent/revoke`
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

Los endpoints OTP anteriores se mantienen temporalmente en backend por compatibilidad con
clientes antiguos, pero ya no forman parte del flujo visible de Talent ID.
