# Odoo Sign 18: un solo envío y reconciliación segura en staging

## Evidencia de Odoo Shell (17 oct 2026)

En staging `asiati-test160526-39554181` el usuario verificó el código de:

- `sign.send.request.send_request()` invoca `create_request()`, escribe una nota de actividad y, sin actividad previa, retorna `request.go_to_document()`.
- `create_request()` crea **un** `sign.request` con dos `request_item_ids`, plantilla, correo por rol, asunto y adjuntos. Copia `self.subject` a `sign.request.subject`.
- `go_to_document()` retorna una acción `sign.Document` cuya `context.id` es el **ID numérico de sign.request** (no divulgar `context.token`).
- `sign.request.get_completed_document()` retorna una URL con token. Para archivado backend se utiliza `completed_document_attachment_ids` sin transferir URLs públicas ni tokens al usuario.

## Implementación en ADN360

**Solo para empleados ficticios allowlisted en Odoo staging y con confirmación expresa de RRHH.**

1. Se valida la plantilla, el PDF aprobado, los roles Empleado y Representante legal y los correos de los dos contactos ficticios.
2. Antes de la escritura remota se consulta `sign.request` por `template_id` y un asunto único `ADN360-STAGING-{employee_document.id}`. Si hay un registro, no se envía.
3. En Postgres, bajo bloqueo por fila, se guarda `DISPATCHING`, asunto y fecha; la transacción se confirma **antes** del RPC.
4. Se crea el asistente transient `sign.send.request` con `signer_ids`, se registra el ID del asistente y se invoca **una sola vez** `send_request`. Nunca llamar a `create_request` y `send_request` por separado.
5. Del resultado se extrae únicamente `context.id`, si está presente. Si Odoo devolviera una acción de cierre, se consulta el asunto único y se requiere exactamente una coincidencia.
6. El ID remoto se comprueba mediante el seguimiento existente: plantilla, dos roles, correos ficticios autorizados, estados. Solo si se valida se marca `SENT`.
7. Ante timeout/error, se guarda `UNKNOWN`. **No reintentar nunca el envío directamente**: reconciliar el asunto con Odoo. Si no hay coincidencia, permanece UNKNOWN y requiere revisión manual. Si hay varias, nunca se elige una automáticamente.

### Endpoints

- `GET /api/employee-documents/employees/{employee_id}/contract/sign/request/send-status`: estado local, permiso `employee_documents.read_all`.
- `POST /api/employee-documents/employees/{employee_id}/contract/sign/request/preview`: lectura para validar plantilla y dos contactos, permiso `employee_documents.review`.
- `POST /api/employee-documents/employees/{employee_id}/contract/sign/request/send`: body `{"employee_partner_id":301,"representative_partner_id":302,"confirm":true}`; permiso `employee_documents.review`. IDs ilustrativos solamente.
- `POST /api/employee-documents/employees/{employee_id}/contract/sign/request/reconcile`: consulta remota de un intento incierto; nunca invoca envío. Permiso `employee_documents.review`.

### Flags de seguridad (todos deshabilitados por defecto)

```dotenv
ODOO_SIGN_STAGING_PREPARE_ENABLED=false
ODOO_SIGN_STAGING_TRACK_ENABLED=false
ODOO_SIGN_STAGING_SEND_ENABLED=false
ODOO_SIGN_TEST_EMPLOYEE_IDS=
ODOO_SIGN_TEST_SIGNER_EMAILS=
```

`ODOO_SIGN_STAGING_SEND_ENABLED` debe activarse **solo con una base Odoo staging neutralizada** y con los dos correos ficticios `example.invalid` que existan como contactos allí. Se sigue requiriendo configuración aislada `ODOO_STAGING_*`, distinta de producción.

Esta implementación **no garantiza entrega de correos**; Odoo.sh staging neutralizado no envía correo externo. No se activa el guard de contratación automática ni se provisionan empleados desde este endpoint.

## Pruebas pendientes con usuario técnico

- Confirmar permisos XML-RPC de lectura sobre `sign.request.subject` y de escritura/invocación en `sign.send.request`.
- En entorno staging neutralizado, enviar una solicitud de prueba y verificar `context.id`, la creación exacta de dos `sign.request.item`, que el intento queda en estado SENT en ADN360 y que no se envían correos externos.
- Forzar un timeout simulado en tests; confirmar que segundo clic no puede enviar y que reconciliación enlaza la solicitud por asunto único.
- Archivar PDF firmado y certificado, comprobar S3 SHA256 y permisos; solo después considerar el alta automatizada del empleado.
