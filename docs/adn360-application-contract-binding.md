# Vinculación de contratos por postulación — ADN360

Este cambio incorpora `application_contracts` como relación 1:1 entre la postulación (`job_candidates.id`) y el documento del contrato (`employee_documents.id`), con empresa Odoo y versión original (clave S3) fijadas antes de iniciar la firma.

## Conservación de contratos históricos
- La revisión 059 es aditiva y **no modifica ni elimina** `employee_documents`, PDFs, solicitudes 140 u otros documentos existentes.
- Los contratos históricos **no se asignan automáticamente** a una vacante: no hay prueba de la relación contractual para deducirla a partir de `employee_id`.
- El backend rechaza el uso de un documento sin vinculación explícita para nuevas contrataciones cuando el bloqueo está habilitado.
- La tabla protege la relación: un documento no se puede vincular a dos postulaciones y una postulación no puede referenciar dos documentos simultáneamente. Borrar registros referenciados está restringido a nivel de FK.
- **Limitación actual:** `EmployeeDocument` aún conserva la restricción única por empleado/tipo. Un candidato con dos postulaciones simultáneas necesitará una evolución posterior del almacenamiento de contratos por postulación. El control actual falla cerrado para impedir reutilización.

## Flujo integrado en la interfaz
1. En **Postulaciones**, preparar el perfil APPLICANT sin crear un empleado Odoo.
2. En **Documentos**, cargar el contrato PDF y aprobarlo como Talento Humano.
3. Volver a la postulación exacta y abrir **Vincular contrato**. Seleccionar una empresa activa del catálogo Odoo y confirmar.
4. El modal consulta `GET /api/jobs/{job_id}/candidates/{candidate_id}/contract/binding` para mostrar el estado y la empresa vinculada. El vínculo es inmutable; una versión de PDF distinta se rechaza.
5. Continuar a Documentos y preparar Odoo Sign. Si la vinculación está habilitada y falta el vínculo correcto, readiness y `POST .../contract/sign/prepare` bloquean la preparación antes de cualquier escritura en Odoo.
6. La firma de ambas partes, reconciliación y archivo separado del PDF firmado y el certificado siguen el flujo existente.
7. Con `ADN360_REQUIRE_SIGNED_CONTRACT_FOR_HIRE=true` en un entorno de ensayo, readiness y contratación requieren la postulación, versión del contrato y empresa coincidentes.

La interfaz y el guard de preparación están implementados en la rama de trabajo, pero la prueba real contra Odoo Sign staging sigue pendiente. Usa [el checklist E2E de staging](adn360-contract-binding-staging-checklist.md). No activar estas variables en producción.

## Riesgos abiertos
- El registro histórico de la solicitud 140 se preserva sin modificación, pero no habilita ninguna nueva postulación.
- Los endpoints actuales de firma siguen utilizando `employee_id`: para permitir varios contratos simultáneos de una persona hará falta ampliar rutas y almacenamiento; la tabla impide confundir las firmas existentes.
- `HIRED` continúa usando la exención histórica de idempotencia; debe validarse con pruebas separadas antes de endurecer ese comportamiento.
