# ADN360 → Odoo Sign (fase 1: preparar plantilla en staging)

**Estado:** integración de preparación para pruebas; **no hay envío de solicitudes ni firma automática**.
No habilitar con contratos reales hasta completar validación legal, funcional y de seguridad.

## Flujo disponible
1. Talento Humano carga un contrato **PDF** en `/documents` y lo **aprueba**.
2. En el expediente administrativo, debajo de **Contrato laboral**, se ve **Odoo Sign**.
3. ADN360 consulta los modelos `sign.template` y `ir.attachment` de **Odoo staging** mediante XML-RPC.
4. Si el usuario/contrato está autorizado como fixture de prueba, el botón **Preparar en Odoo Sign** copia el PDF del bucket privado a un adjunto en staging y crea una plantilla.
5. El ID de la plantilla, el adjunto, el objeto de origen y el estado quedan persistidos en `employee_documents`.
6. Talento Humano abre la plantilla en staging, **ubica los campos de firma, selecciona firmantes y envía la solicitud manualmente en Odoo**.

**Importante:** preparado ≠ enviado ≠ firmado. No interpretar `PREPARED` como evidencia de firma. Esta fase no descarga documentos firmados ni habilita acceso del empleado al original.

## Configuración cerrada por defecto

Configurar en el **backend de pruebas** (no en el frontend):

```bash
ODOO_SIGN_STAGING_PREPARE_ENABLED=false
ODOO_SIGN_TEST_EMPLOYEE_IDS=
```

Para pruebas controladas: usar `true` y los ID de perfiles **sintéticos y expresamente autorizados**, separados por comas. Sin ambas condiciones **ningún PDF** se transfiere a staging.

Requiere el conjunto existente de variables y credenciales separadas `ODOO_STAGING_BASE_URL`, `ODOO_STAGING_DATABASE`, `ODOO_STAGING_USERNAME`, `ODOO_STAGING_SECRET_ID`. `staging.py` rechaza host, base y secreto compartidos con producción. **Nunca usar credenciales de producción.**

Los endpoints internos autorizan:
- `GET /api/employee-documents/employees/{employee_id}/contract/sign`: permiso `employee_documents.read_all`.
- `POST /api/employee-documents/employees/{employee_id}/contract/sign/prepare` con `{"confirm":true}`: permiso `employee_documents.review`.

La creación se bloquea si el contrato no está aprobado, no es PDF, ya está preparando, el usuario no está permitido o los modelos de staging no están disponibles. Tras preparar, ADN360 impide sustituir el documento original para que no difiera del PDF ya copiado.

## Checklist E2E en staging

- [ ] Ejecutar migración Alembic 054 y testear ida/vuelta con una copia de base aislada.
- [ ] Confirmar Odoo Enterprise Sign instalado y acceso del usuario técnico a `sign.template` e `ir.attachment`.
- [ ] Crear **un empleado ficticio** con PDF de prueba sin PII real y configurar solamente su ID en la allowlist.
- [ ] Probar lectura de estado (sin escrituras), aprobar PDF y pulsar **Preparar en Odoo Sign**.
- [ ] Validar que el PDF coincida en staging y que se pueda colocar un campo de firma por cada rol.
- [ ] Verificar que refrescar o volver a pulsar no cree una segunda plantilla.
- [ ] Confirmar manualmente el envío, firma de empleados ficticios y evidencia de auditoría de Odoo Sign.
- [ ] Confirmar que la prueba no haya emitido correos reales ni escrito en Odoo producción.
- [ ] Pasar revisión jurídica colombiana de firma, autenticación y conservación.

## Pendiente antes de producción

Implementar en un PR posterior, con el esquema de Sign observado en la instancia y E2E aprobado: solicitud con dos firmantes (empleado y representante legal); permisos de lectura de copia firmada; seguimiento de estados; sincronización segura del PDF firmado y certificado de evidencia al expediente; idempotencia y reintentos; gestión de rechazos y vencimientos; política de conservación y garantías legales. No activar emails reales con este PR.
