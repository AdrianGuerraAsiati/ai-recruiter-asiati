# ADN360 · Pruebas del módulo de firmas (26 oct 2026)

## Qué se valida automáticamente

En **GitHub Actions → Signature module — synthetic E2E** se corre una batería sin credenciales, red Odoo ni AWS:

1. Vinculación inmutable de PDF aprobado, perfil y postulación, con empresa Odoo ficticia.
2. Preparación de plantilla, una sola vez; no se envía ninguna solicitud en este paso.
3. Seguimiento de estados pendiente, una sola firma y ambas firmas con estado global confirmado.
4. Bloqueo del alta de empleado hasta contar con ambas firmas y archivo final.
5. Archivo separado del PDF y certificado, hash SHA-256 y conservación del original; idempotencia.
6. Rechazo de PDF sustituido, adjuntos incompletos, roles no autorizados, correos no ficticios, errores de esquema, envíos repetidos y respuestas ambiguas.
7. Controles de permisos y endpoints, validaciones del flujo de contratación, UI de vinculación y envío único.

Se usa SQLite temporal, cliente de Odoo en memoria y almacenamiento S3 simulado. **Aprobar esta batería NO equivale a comprobar XML-RPC, entrega de correos, firmas legales ni integración real en Odoo staging.** La prueba E2E sintética añadida no ejecuta Cognito, envío remoto ni firma de personas reales. El pipeline CI general sigue verificando esquema en PostgreSQL 16.

## Prueba real en staging — pendiente de ejecución separada

**Prerrequisitos obligatorios:** autorización de RRHH, entorno de Talent de *staging* independiente, Odoo Enterprise 18 en base de staging **neutralizada**, migración 059, dos contactos sintéticos con correos `example.invalid`, PDF sintético sin PII, empleado de prueba allowlisted y credenciales **exclusivas** de staging. No usar el pool de Cognito real ni sus datos para esta prueba.

### Fase A — solo lectura

- Comprobar la configuración y segregación `ODOO_STAGING_*` con `GET /api/odoo/staging/sign/diagnostics` desde la cuenta administrativa autorizada.
- Verificar el esquema efectivo de `sign.template`, `sign.send.request`, `sign.request`, `sign.request.item` y `ir.attachment`. Confirmar `completed_document_attachment_ids` como relación a `ir.attachment`.
- Consultar `GET /api/jobs/hiring/signature-flow` y confirmar **qué flags están habilitados**. No modificarlos ni asumir que están activos.

### Fase B — escritura, solo con aprobación y datos ficticios

- Crear postulación ficticia y expediente APPLICANT; corroborar ausencia de alta EMPLOYEE/Odoo.
- Subir/aprobar PDF sintético, vincular con empresa Odoo de staging, preparar plantilla y validar exactamente dos campos de firma.
- Usar el envío de staging explícito, con correos ficticios allowlisted. Confirmar una única solicitud, que el campo `subject` permite conciliación y que no se envían correos externos.
- Firmar mediante **mecanismo controlado de staging**, por ambos roles, verificando primero estado parcial y luego firmado. Archivar PDF final y certificado por separado.
- Validar integridad/hash, descarga por titular/RRHH, bloqueo de acceso a terceros y ausencia de modificación del original.
- Verificar condiciones negativas: un firmante, plantilla ajena, asunto duplicado, cambio de PDF, otra postulación, empresa incorrecta y fallo de Odoo.
- Solo en entorno aislado, activar `ADN360_REQUIRE_SIGNED_CONTRACT_FOR_HIRE` y probar bloqueo/habilitación del alta; confirmar idempotencia de rol Cognito y sincronización Odoo.
- Conservar evidencia de respuestas sanitizadas, IDs de prueba, hashes y capturas. Desactivar flags al finalizar y validar que no haya escritos en producción.

**No habilitar flags de firma en producción ni enviar contratos reales a partir de un resultado verde del workflow sintético.**

### Evidencia previa

`docs/odoo-sign-signature-first-hiring.md` documenta una solicitud ficticia con dos firmas y certificado el **19-oct-2026**. Es evidencia histórica, **no una ejecución E2E nueva** del flujo completo posterior a los PR #319 y #320.
