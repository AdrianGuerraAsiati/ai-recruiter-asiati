# ADN360 — Firma sin IDs de Odoo en Talento Humano

## Regla de producto

El administrador no necesita acceso a Odoo, identificadores `sign.request` ni IDs `res.partner`. Odoo es proveedor de firma; ADN360 es la interfaz de operaciones y fuente del expediente del candidato.

El formulario de Documentos ya no pide ningún ID de solicitud ni contacto. El backend resuelve los contactos y, cuando está explícitamente habilitado en **staging**, invoca la creación de la solicitud, comprueba el resultado y conserva su `request_id` en la base de datos. La actualización de estado utiliza el ID ya registrado.

## Implementación de este PR

- `POST /api/employee-documents/employees/{employee_id}/contract/sign/request/automatic-preview` sin body: valida que haya una plantilla preparada con ambos campos de firma y localiza por correo exacto los dos contactos ficticios en `res.partner`. No crea solicitudes ni revela IDs.
- `POST /api/employee-documents/employees/{employee_id}/contract/sign/request/automatic-send` con `{"confirm":true}`: obtiene contactos en backend e invoca la lógica existente de envío único, correlación por asunto e idempotencia. Solo si `ODOO_SIGN_STAGING_SEND_ENABLED=true`.
- Todos los endpoints requieren el permiso `employee_documents.review` y un empleado permitido en `ODOO_SIGN_TEST_EMPLOYEE_IDS`.
- La configuración staging exige exactamente dos direcciones distintas con dominio `@example.invalid`, con prefijos `empleado.` y `representante.`, en ese orden dentro de `ODOO_SIGN_TEST_SIGNER_EMAILS`.
- Se rechaza contacto inexistente o ambiguo en Odoo, roles faltantes, plantilla no configurada, y cualquier error de conexión. No se realizan envíos ante errores de validación.
- React: sin campo para pegar ID de solicitud ni IDs numéricos de contactos; validación y confirmación en un mismo flujo de Talento Humano. Las rutas manuales preexistentes se conservan temporalmente para diagnósticos internos y no se muestran al usuario.

## Lo que NO está resuelto

- Odoo Sign necesita **bloques de firma ubicados en la plantilla PDF**. Actualmente deben configurarse en Odoo; automatizar su posicionamiento desde ADN360 requiere un cambio separado. No se debe activar el envío de pruebas si todavía no existen ambos campos.
- En producción, los correos deben provenir del candidato y del representante legal configurado por organización, no de la allowlist de correos ficticios de staging. **Esta integración no es habilitación productiva**.
- `ODOO_SIGN_STAGING_SEND_ENABLED` permanece apagado por defecto. No se envían correos, no se activan cuentas de empleados ni se archivarán documentos finales hasta completar el E2E y la implementación posterior.

## Validación

- Tests del servicio resuelven contactos en orden Empleado → Representante legal, impiden duplicados, verifican flag OFF y la asociación automática del ID en el expediente.
- Tests de frontend verifican ausencia de campos de ID, confirmación antes de enviar y actualización de firmas con la referencia guardada.
- CI PostgreSQL/backend/frontend/E2E/CodeQL antes de integrar.
