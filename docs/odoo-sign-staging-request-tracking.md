# ADN360 → Odoo Sign: fase 2 de seguimiento en staging

## Alcance implementado

- **No se envían invitaciones desde ADN360**; Odoo gestiona la página del firmante, su correo y autenticación.
- Conservamos la fase 1 (PR #293, migración 054) y añadimos la migración **055** para asociar **una** solicitud de firma al contrato del expediente.
- Desde Documentos (solo Talento Humano), la fase 2 permite introducir el **ID numérico de una solicitud creada manualmente en Odoo staging** y consultar el avance de cada uno de los dos firmantes.
- Una consulta remota solo puede vincularse cuando coincide con la **misma plantilla preparada**, los roles exactos `Empleado` y `Representante legal`, y **dos correos ficticios autorizados**, distintos, con dominio `.invalid`.
- Estados normalizados: `PENDING_SIGNATURE`, `PARTIALLY_SIGNED`, `SIGNED`, `CANCELLED`, `EXPIRED`. Solo se marca `SIGNED` cuando la **solicitud y ambos firmantes** constan firmados en la lectura de Odoo. No significa que el archivo esté archivado ni que exista conformidad jurídica.
- El vínculo es único e idempotente y no permite cambiar la solicitud a otra.
- No se leen ni presentan tokens individuales del portal de firmas.

## Configuración por defecto: cerrada

```dotenv
ODOO_SIGN_STAGING_PREPARE_ENABLED=false
ODOO_SIGN_TEST_EMPLOYEE_IDS=
ODOO_SIGN_STAGING_TRACK_ENABLED=false
ODOO_SIGN_TEST_SIGNER_EMAILS=
```

En un backend de pruebas con Odoo staging aislado, configurar explícitamente el ID del **perfil ADN360 ficticio** en `ODOO_SIGN_TEST_EMPLOYEE_IDS`, y dos emails de prueba con dominio `.invalid`, separados por coma. Los dos flags deben habilitarse de manera separada para preparar y seguir una solicitud. Ninguna ruta de esta fase genera correos o escribe registros en Odoo. La recuperación de los estados usa XML-RPC de lectura únicamente.

Se necesitan las credenciales independientes existentes `ODOO_STAGING_*`, **no** las de producción.

### Endpoints

- `GET /api/employee-documents/employees/{employee_id}/contract/sign/request`: lectura del estado ya registrado, permiso `employee_documents.read_all`.
- `POST /api/employee-documents/employees/{employee_id}/contract/sign/request/link`: body `{"request_id":139,"confirm":true}`, permiso `employee_documents.review`. **El número 139 es solo ejemplo tomado de una prueba manual: NO vincularlo a empleados reales.** Debe pertenecer exactamente a la plantilla y firmantes del expediente ficticio.
- `POST /api/employee-documents/employees/{employee_id}/contract/sign/request/refresh`: refrescar estados validados, permiso `employee_documents.review`.
- `GET /api/odoo/staging/sign/diagnostics`: solo metadatos estructurales de modelos, con `integrations.manage`, sin leer contactos ni documentos.

## Pruebas pendientes en la instancia

1. Desplegar las migraciones en un entorno de pruebas compatible con el backend.
2. Consultar el diagnóstico de staging para validar que Odoo 18 Enterprise expone `sign.request.template_id`, `request_item_ids`, y en `sign.request.item`: `role_id`, `state`, `signer_email`.
3. Preparar con ADN360 un PDF ficticio y agregar sus dos campos de firma en Odoo; no se pueden reutilizar plantillas manuales cuyo ID no coincida con el expediente.
4. Crear solicitud manual de prueba en Odoo, con roles y correos `.invalid` autorizados.
5. Desde Documentos, vincular el ID de esa solicitud, refrescar, firmar con cuentas ficticias mediante una vía controlada y comprobar que los estados cambien de pendiente → parcial → firmado.
6. Confirmar que no se crearon firmantes, PDFs ni solicitudes en Odoo producción y que el backend no intentó enviarlos.
7. Auditar la obtención del **PDF firmado y certificado de finalización** en Odoo, confirmar el modelo/campo real y diseñar su archivado S3 con control de integridad, permisos de empleado y conservación. **No implementado aún**.
8. Verificar el asistente `sign.send.request` y sus firmas de método en esta base específica antes de incorporar envío automático; **no implementado aún**.

La experiencia de firma permanece dentro de Odoo Sign; ADN360 actuará como orquestador cuando se valide su contrato de API. Esta fase no almacena URLs individuales ni copia firmantes reales a staging.
