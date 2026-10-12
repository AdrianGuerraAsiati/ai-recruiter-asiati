# Bienvenida y cierre de expedientes documentales

## Comportamiento

- **Al confirmar "Crear empleado" en Postulaciones**, tras la contratación y su commit en la base de datos, Talent registra una notificación única por empleado y envía un mensaje por AWS SES v2.
- Asunto: **¡Felicitaciones por tu contratación en ASIATI! | Documentación de ingreso**. El cuerpo felicita al empleado, muestra únicamente los requisitos que no estén aprobados y enlaza `https://talent.asiaticorp.com/documents` y el acceso al portal.
- No se transmite contraseña temporal por email ni se adjuntan cédulas, certificados ni otros archivos; cada persona sube documentos al repositorio privado de Talent.
- El usuario ya existente como **Postulante** conserva su identidad y expediente; al contratarlo pasa a rol **Empleado** y recibe onboarding, aun si los documentos siguen pendientes.
- **No se bloquea la contratación por documentos faltantes**: la solicitud se genera *después* de confirmar la contratación, como pidió el área. El expediente solo se considera completamente aprobado cuando sus 13 requisitos tienen visto bueno.
- El registro `employee_document_emails` garantiza que el mismo empleado no reciba varias felicitaciones cuando se reintenta contratar o se relaciona con otra vacante. Su estado es `PENDING`, `SENDING`, `SENT` o `FAILED`.
- Si SES falla, **el empleado queda contratado**, con estado del envío registrable y reintento desde la vista **Documentos**. No se declara enviado si SES respondió con error. Solo un usuario con `employee_documents.review` puede reintentar.
- Un intento que se quede en estado `SENDING` durante una interrupción debe revisarse manualmente para evitar duplicados potenciales tras un error de red justo después del envío.

## Bandeja de revisión

- `GET /api/employee-documents/review-queue`, protegida con `employee_documents.read_all`, lista hasta 100 expedientes recientes con documentos en estado `PENDING_REVIEW` o `CHANGES_REQUESTED`. Incluye nombre y cantidad por revisar o corregir, sin contenido sensible.
- En **Documentos**, los administradores pueden filtrar la bandeja, abrir cada expediente y revisar individualmente soportes (aprobar o solicitar correcciones con comentario). Los postulantes con cero archivos aún aparecen en **Postulaciones**.
- `GET /api/employee-documents/employees/{employee_id}/welcome` permite al administrador consultar el estado del aviso.
- `POST /api/employee-documents/employees/{employee_id}/welcome/retry` reintenta solo avisos para empleados realmente marcados como contratados.
- Permisos del postulante permanecen limitados a `employee_documents.read_own` y `employee_documents.upload_own`. Archivos almacenados en S3 privado, con URL de descarga temporal.

## Configuración sin infraestructura nueva

1. La implementación reutiliza el cliente **AWS SES v2** ya presente en Talent. Selecciona un remitente verificado configurado por la instalación en `TALENT_ID_FROM_EMAIL` o `TALENT_ID_CONSENT_FROM_EMAIL`. El código no crea nuevos recursos AWS.
2. Verifica que SES de `us-east-2` tenga permisos `ses:SendEmail` para la identidad remitente, y que la cuenta pueda enviar al dominio/destinatario esperado (si sigue en sandbox, requiere destinatarios verificados).
3. La migración Alembic **053** crea el registro de entregas. El pipeline existente ejecuta migraciones antes de activar la nueva versión.
4. Ejecuta un test controlado con un correo interno o autorizado: contratar un usuario de prueba → comprobar recepción de felicitación y lista de documentos → iniciar sesión → subir PDF → revisión y corrección → volver a subir → aprobar.
5. Verifica que el botón de reintento cambie estado a `SENT` solamente después de respuesta exitosa de SES. Nunca utilices direcciones de candidatos reales para pruebas automatizadas.

## Limitaciones conscientes

- El SMTP de Gmail no es necesario; el envío por SES es independiente del nuevo acceso a Google Calendar.
- Si SES no está configurado o el remitente carece de permiso, el correo queda en `FAILED` y se reintenta manualmente sin afectar la contratación.
- No se envían correos por cada comentario documental en este bloque; el usuario puede consultar sus observaciones al abrir Talent.
- La bandeja usa un límite de 100 expedientes con novedades más recientes; más adelante se puede paginar si el volumen de colaboradores lo requiere.
- La verificación real de entrega a una cuenta corporativa y subida efectiva a S3 debe hacerse después del despliegue; las pruebas de código no equivalen a esa comprobación.
