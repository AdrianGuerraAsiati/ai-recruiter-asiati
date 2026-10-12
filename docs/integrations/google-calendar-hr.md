# Google Calendar corporativo — entrevistas Talent

## Cuenta y alcance
- Calendario único de destino: `talentohumano@asiati.com.co`. **Jamás se utiliza `sistemas@asiati.com.co` como reemplazo.**
- Sincronización Fase 1: **Talent → Google** para llamadas telefónicas y entrevistas presenciales.
- La cuenta Google conectada al chat no autoriza al backend de Talent. Se solicita **un OAuth independiente** con el correo de Talento Humano.
- OAuth scope mínimo: `https://www.googleapis.com/auth/calendar.events` y `https://www.googleapis.com/auth/userinfo.email`.
- No se envían invitaciones a candidatos ni se generan enlaces Meet en esta fase. Ningún evento ajeno a Talent se modifica.

## Arquitectura
1. Se aprovecha el secreto AWS Secrets Manager **existente** de Gmail (`GMAIL_OAUTH_SECRET_ID`, predeterminado `/ai-recruiter/prod/gmail-oauth`) como contenedor. **No se reutiliza su token de Gmail**. El grant Google Calendar vive bajo la clave JSON `talent_calendar` con `refresh_token` y `connected_email` independientes; se preservan todas las demás claves.
2. Se reutiliza el cliente OAuth de Google presente en el secreto: `client_id`, `client_secret` y `state_secret`. Solo se autoriza la cuenta objetivo; callback comprueba su email por la API userinfo **y** acceso real al calendario antes de guardar el token.
3. Registrar esta URI exacta en el cliente OAuth de Google Cloud:
   `https://talent.asiaticorp.com/api/recruitment-calendar/google/callback`.
   Si producción utiliza otra dirección, configurarla con `TALENT_GOOGLE_CALENDAR_REDIRECT_URI`.
4. Habilitar **Google Calendar API** para el proyecto de Google Cloud que contiene ese cliente OAuth y verificar configuración/consentimiento de scopes.
5. El administrador entra a `https://talent.asiaticorp.com/calendar` → **Conectar cuenta** → Google → autoriza `talentohumano@asiati.com.co`. La autorización no requiere introducir contraseñas en Talent ni ChatGPT.
6. Tras autorizar, pulsar **Sincronizar citas**. El backend consulta hasta 100 reuniones recientes/futuras, hace upsert idempotente por identificador derivado del UUID de Talent y devuelve conteo sincronizado/fallido. Si Google no responde, los datos originales siguen en Talent.
7. Solo después de validar la sincronización manual, habilitar en el runtime existente `TALENT_GOOGLE_CALENDAR_AUTOSYNC=true` para reflejar los cambios al crear, editar, completar o cancelar citas, sin recursos AWS nuevos.
8. Opcional: **Desconectar** elimina solo el grant local del Calendar corporativo, no la conexión Gmail ni los eventos ya creados.

## Contratos
- `GET /api/recruitment-calendar/google/status`: `candidates.read` (sin secretos).
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
- `app/tests/test_google_calendar_hr.py` prueba separación de cuentas, callback y permisos, token no persistido en error, idempotencia y revocación local.
- CI debe aprobar: pytest, frontend lint/build/tests, E2E, Postgres smoke, CodeQL.
