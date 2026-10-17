# ADN360 · firma antes de contratación (fase 3)

## Regla de producto aprobada

1. El administrador elige una **postulación** y prepara su expediente contractual.
   - La API crea/reutiliza un `UserProfile` con rol **APPLICANT** para asociar el PDF.
   - Si todavía no existe acceso al portal, **no crea Cognito** ni un empleado en Odoo.
   - Si el candidato ya tiene acceso de postulante para pruebas psicotécnicas, se reutiliza; esto no es una contratación.
2. Talento Humano sube/aprueba el contrato PDF desde **Documentos**, vinculado al perfil de candidato.
3. ADN360 prepara el PDF como plantilla en Odoo Sign.
4. **Odoo envía los correos y aloja los enlaces de firma** (API de envío por validar con la instancia Enterprise v18). Firmantes: Empleado y Representante legal.
5. ADN360 verifica que **ambos** firmaron, recupera el PDF final y conserva una copia privada inmutable. El original jamás se reemplaza.
6. Solo entonces se permite **Crear empleado**: otorgar/elevar rol EMPLOYEE, crear acceso Cognito si no existía, ejecutar onboarding y sincronizar `hr.employee` y, con datos contractuales confirmados, `hr.contract` a Odoo.

El botón de contratación sigue requiriendo una confirmación administrativa. El alta *totalmente automática* al completarse la firma demanda registrar antes los campos del contrato y una operación de orquestación idempotente; **no está implementada** en esta fase.

## Lo que implementa este PR

- Perfil de expediente previo a contratación sin cuenta ni integración Odoo:
  `POST /api/jobs/{job_id}/candidates/{candidate_id}/contract/prepare-dossier`.
- Consulta antes de contratar:
  `GET /api/jobs/{job_id}/candidates/{candidate_id}/hire-readiness`.
- Capacidad protegida para mostrar el botón solo si el flujo está habilitado:
  `GET /api/jobs/hiring/signature-flow`.
- Regla de backend activable `ADN360_REQUIRE_SIGNED_CONTRACT_FOR_HIRE` que falla **antes de toda creación de usuario / rol / onboarding / entrega Odoo**, salvo postulaciones previamente HIRED. Requiere ambas firmas, estado general `SIGNED` y PDF firmado archivado con hash SHA-256.
- Si el expediente previo carece de Cognito, al contratar se provisiona sobre el **mismo perfil**, sin duplicarlo. Los ya provisionados pasan de APPLICANT a EMPLOYEE.
- Al confirmar, el admin completa tipo de contrato, fecha de inicio, fin (si aplica) y salario para `hr.contract`.
- Migración 056: metadatos separados del PDF firmado (ubicación, hash, adjunto Odoo, fecha de archivo).
- Descarga del PDF firmado por Talento Humano y por su propio titular; ninguna otra persona puede acceder por la ruta `/me`.
- Importación **solo en staging** desde un campo de adjunto firmado que antes debe confirmarse en Odoo Enterprise v18.
- Protección de 15 MB, comprobación de cabecera y fin del PDF, SHA-256, SSE-S3 y almacenamiento con nombre basado en contenido. El PDF original sigue intacto.

## Flags: cerrados por defecto

```dotenv
ODOO_SIGN_STAGING_PREPARE_ENABLED=false
ODOO_SIGN_STAGING_TRACK_ENABLED=false
ODOO_SIGN_STAGING_ARCHIVE_ENABLED=false
ODOO_SIGN_STAGING_SIGNED_ATTACHMENT_FIELD=
ODOO_SIGN_TEST_EMPLOYEE_IDS=
ODOO_SIGN_TEST_SIGNER_EMAILS=
ADN360_REQUIRE_SIGNED_CONTRACT_FOR_HIRE=false
```

No activar el último flag en producción mientras Odoo Sign no permita enviar y archivar documentos reales; bloquearía la contratación de postulantes pendientes. No mezclar credenciales de Odoo staging con producción.

## Validación de API Odoo v18, lectura solamente

Usar el endpoint administrativo ya implementado
`GET /api/odoo/staging/sign/diagnostics` y comprobar:
- Si `sign.send.request` está disponible y cuáles son sus campos.
- Cómo vincular los dos roles y contactos con `sign.request`.
- Qué relación/campo expone el **PDF final**, y dónde se encuentra su **certificado de finalización**.
- El método real del asistente que envía la solicitud en esta instancia.

**No adivinar** campos: la importación acepta exclusivamente
`completed_document_attachment_id(s)` o `signed_document_attachment_id(s)`
cuando la relación real sea `ir.attachment`. Si Odoo devuelve otro formato, falla sin descargar nada. No equivale a una prueba E2E en vivo.

## Pruebas E2E por completar

1. Preparar expediente de candidato ficticio desde Postulaciones y confirmar que NO se creó login ni `hr.employee`.
2. Subir/aprobar PDF ficticio y preparar plantilla con los dos campos de firma.
3. Verificar asistente real de envío Odoo Sign (en staging los correos están neutralizados).
4. Firmar con ambos roles, verificar estados progresivos y recuperar **PDF + certificado**.
5. Comprobar S3, hash, permisos de descarga y ausencia de efectos en producción.
6. Activar flag de contratación en entorno aislado, confirmar que bloquea antes de dos firmas y habilita el alta después de archivado.
7. Validar asignación del rol EMPLOYEE, Cognito, `hr.employee` y `hr.contract` sin duplicados ni envíos de bienvenida anticipados.
8. Diseñar activación automática idempotente al completar la firma (en vez de botón manual), con datos contractuales previamente validados y reintentos del worker.

**Importante:** este PR no contiene el envío automático de correos ni el proceso automático de alta; primero debe verificarse el contrato API y la evidencia jurídica en staging.
