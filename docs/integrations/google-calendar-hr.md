# Google Calendar corporativo — entrevistas Talent

## Cuenta y alcance
- Cuenta de Google para la agenda **configurable**, inicialmente `talentohumano@asiati.com.co`. No se usa `sistemas@asiati.com.co` por defecto.
- Un administrador con `integrations.manage` puede cambiarla, conectar, sincronizar y desconectar desde la propia Agenda.
- Por defecto solo se aceptan `@asiati.com.co` y `@asiaticorp.com`. Operaciones puede ampliar dominios con `TALENT_GOOGLE_ALLOWED_DOMAINS` (lista CSV) tras revisar privacidad.
- Sincronización Fase 1: **Talent → Google** para llamadas telefónicas y entrevistas presenciales.
- La cuenta Google conectada al chat no autoriza al backend de Talent. Se solicita **un OAuth independiente** con el correo de Talento Humano.
- OAuth scope mínimo: `https://www.googleapis.com/auth/calendar.events` y `https://www.googleapis.com/auth/userinfo.email`.
- No se envían invitaciones a candidatos ni se generan enlaces Meet en esta fase. Ningún evento ajeno a Talent se modifica.

## Arquitectura
1. Se aprovecha el secreto AWS Secrets Manager **existente** de Gmail (`GMAIL_OAUTH_SECRET_ID`, predeterminado `/ai-recruiter/prod/gmail-oauth`) como contenedor. **No se reutiliza su token de Gmail**. El grant Google Calendar vive bajo la clave JSON `talent_calendar` con `refresh_token` y `connected_email` independientes; se preservan todas las demás claves.
2. Se reutiliza el cliente OAuth de Google presente en el secreto: `client_id`, `client_secret` y `state_secret`. Solo se autoriza la cuenta configurada; callback comprueba su email por la API userinfo **y** acceso real al calendario antes de guardar el token.
3. Registrar esta URI exacta en el cliente OAuth de Google Cloud:
   `https://talent.asiaticorp.com/api/recruitment-calendar/google/callback`.
   Si producción utiliza otra dirección, configurarla con `TALENT_GOOGLE_CALENDAR_REDIRECT_URI`.
4. Habilitar **Google Calendar API** para el proyecto de Google Cloud que contiene ese cliente OAuth y verificar configuración/consentimiento de scopes.
5. El administrador entra a `https://talent.asiaticorp.com/calendar` → **Conectar cuenta** → Google → autoriza la cuenta seleccionada (inicialmente `talentohumano@asiati.com.co`). La autorización no requiere introducir contraseñas en Talent ni ChatGPT.
6. Tras autorizar, pulsar **Sincronizar citas**. El backend consulta hasta 100 reuniones recientes/futuras, hace upsert idempotente por identificador derivado del UUID de Talent y devuelve conteo sincronizado/fallido. Si Google no responde, los datos originales siguen en Talent.
7. Solo después de validar la sincronización manual, habilitar en el runtime existente `TALENT_GOOGLE_CALENDAR_AUTOSYNC=true` para reflejar los cambios al crear, editar, completar o cancelar citas, sin recursos AWS nuevos.
8. **Desconectar** elimina únicamente el grant local de Calendar, no la conexión de ingesta Gmail ni los eventos ya creados.
9. **Guardar cuenta** permite sustituir la dirección de la cuenta corporativa. Cuando cambia, el token anterior y cualquier autorización OAuth pendiente se invalidan; hay que pulsar **Conectar cuenta** para autorizar la nueva identidad, seguido de **Sincronizar citas** para copiar los eventos actuales. Los eventos del calendario anterior permanecen allí y deben revisarse administrativamente antes de deshabilitar aquella cuenta.
10. Esta integración solo usa el producto **Google Calendar**. No lee el buzón Gmail de la cuenta conectada; el conector de ingesta Gmail permanece independiente.

## Contratos
- `GET /api/recruitment-calendar/google/status`: `candidates.read` (sin secretos).
- `PUT /api/recruitment-calendar/google/account` con JSON `{ "email": "cuenta@asiati.com.co" }`: `integrations.manage`; respuesta estado sin tokens.
- `GET /api/recruitment-calendar/google/oauth/start`: `integrations.manage`.
- `GET /api/recruitment-calendar/google/callback`: redirect público protegido por estado firmado HMAC SHA-256, temporal y de un solo uso.
- `POST /api/recruitment-calendar/google/sync`: `integrations.manage`.
- `DELETE /api/recruitment-calendar/google`: `integrations.manage`.
- `POST/PUT /api/recruitment-calendar/events`: mismos contratos, añaden propiedad informativa `google_sync` cuando la cita se guarda.

## Privacidad y recuperación
- Calendar contiene títulos con nombres de candidatos y descripción de vacante. Restringir acceso al calendario de RR. HH.; no incluir CV ni documentos.
- Ningún token se devuelve al frontend ni se escribe en logs.
- Estado de cancelación se refleja en Google como título «[Cancelada]» y evento transparente, conservando el mismo ID para reactivaciones.
- Sin esquema/migración, nuevos servicios AWS, Bedrock, ni infraestructura con coste.
- Fase 2 (posterior): Google → Talent mediante eventos y cursor incremental, con resolución de conflictos. **No está incluida** en este PR.

## Verificación
- `app/tests/test_google_calendar_hr.py` prueba separación de cuentas, callback y permisos, token no persistido en error, idempotencia y revocación local, cambio de cuenta, dominios permitidos y estado OAuth caducado.
- CI debe aprobar: pytest, frontend lint/build/tests, E2E, Postgres smoke, CodeQL.
