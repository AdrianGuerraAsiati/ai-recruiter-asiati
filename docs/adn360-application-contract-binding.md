# Vinculación de contratos por postulación — ADN360

Este cambio incorpora `application_contracts` como relación 1:1 entre la postulación (`job_candidates.id`) y el documento del contrato (`employee_documents.id`), con empresa Odoo y versión original (clave S3) fijadas antes de iniciar la firma.

## Conservación de contratos históricos
- La revisión 059 es aditiva y **no modifica ni elimina** `employee_documents`, PDFs, solicitudes 140 u otros documentos existentes.
- Los contratos históricos **no se asignan automáticamente** a una vacante: no hay prueba de la relación contractual para deducirla a partir de `employee_id`.
- El backend rechaza el uso de un documento sin vinculación explícita para nuevas contrataciones cuando el bloqueo está habilitado.
- La tabla protege la relación: un documento no se puede vincular a dos postulaciones y una postulación no puede referenciar dos documentos simultáneamente. Borrar registros referenciados está restringido a nivel de FK.
- **Limitación actual:** `EmployeeDocument` aún conserva la restricción única por empleado/tipo. Un candidato con dos postulaciones simultáneas necesitará una evolución posterior del almacenamiento de contratos por postulación. El control actual falla cerrado para impedir reutilización.

## Flujo backend (sin interfaz aún)
1. Preparar el perfil APPLICANT, subir un PDF y aprobarlo.
2. Con `ADN360_APPLICATION_CONTRACT_BINDING_ENABLED=true` habilitado solo en el entorno de ensayo, ejecutar `POST /api/jobs/{job_id}/candidates/{candidate_id}/contract/bind` con `{"odoo_company_id": <id>}`.
3. El endpoint verifica empresa con Odoo, que el documento está aprobado, que aún no se ha preparado/enviado a firma y que nadie lo ha vinculado a otra postulación. Repetir idéntica vinculación es idempotente.
4. Preparar el contrato en Odoo Sign, firmar ambas partes y archivarlo.
5. Con `ADN360_REQUIRE_SIGNED_CONTRACT_FOR_HIRE=true` en un entorno de ensayo, readiness y contratación requieren la relación exacta, versión del contrato y empresa coincidente.

No activar estas variables en producción antes de CI, migración sobre copia de PostgreSQL, recorrido E2E con Odoo staging y actualización de UI.

## Riesgos abiertos
- El registro histórico de la solicitud 140 se preserva sin modificación, pero no habilita ninguna nueva postulación.
- Los endpoints actuales de firma siguen utilizando `employee_id`: para permitir varios contratos simultáneos de una persona hará falta ampliar rutas y almacenamiento; la tabla impide confundir las firmas existentes.
- `HIRED` continúa usando la exención histórica de idempotencia; debe validarse con pruebas separadas antes de endurecer ese comportamiento.
