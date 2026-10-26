# Checklist E2E de vinculación contractual — staging

## Antes de empezar
- [ ] El backend de staging contiene la migración Alembic `059` y el código de la rama revisada.
- [ ] La base y Odoo son de staging; el candidato, PDF y correos de firmantes son ficticios.
- [ ] `ADN360_APPLICATION_CONTRACT_BINDING_ENABLED=true`.
- [ ] `ADN360_REQUIRE_SIGNED_CONTRACT_FOR_HIRE=true`.
- [ ] `ODOO_SIGN_STAGING_PREPARE_ENABLED=true` y el perfil de prueba está en `ODOO_SIGN_TEST_EMPLOYEE_IDS`.
- [ ] El envío/tracking de firmas solo está habilitado si se usan los controles existentes de staging y una allowlist de correos ficticios. No usar correos reales ni contratos reales.

## Recorrido funcional
1. [ ] Consultar `GET /api/jobs/hiring/signature-flow`: `enabled=true` y `binding_enabled=true`.
2. [ ] Crear/seleccionar una postulación en estado `SELECTED` o `OFFER` sin perfil. En Postulaciones, usar **Preparar contrato**. Confirmar que solo se crea el perfil `APPLICANT`, sin empleado Odoo ni alta de empleado.
3. [ ] Desde **Documentos**, cargar un PDF ficticio para `EMPLOYMENT_CONTRACT` y aprobarlo como Talento Humano.
4. [ ] Antes de vincular, consultar `GET /api/jobs/{job_id}/candidates/{candidate_id}/contract/binding`: debe indicar `CONTRACT_READY_TO_BIND` y `can_bind=true`.
5. [ ] En Postulaciones, abrir **Vincular contrato**, seleccionar la empresa activa devuelta por el catálogo Odoo y confirmar.
6. [ ] Volver a consultar el endpoint: debe indicar `APPLICATION_CONTRACT_BOUND`, `valid=true` y el ID de empresa esperado. Reabrir el modal: la empresa queda bloqueada para edición.
7. [ ] Antes de vincular, intentar `POST /api/employee-documents/employees/{employee_id}/contract/sign/prepare` en el perfil de otra fixture no vinculada. Debe responder `409` sin crear adjuntos ni plantillas Odoo.
8. [ ] En Documentos, abrir el expediente vinculado y preparar Odoo Sign. Debe crearse una plantilla de staging, pero **no** una solicitud de firma ni correos automáticamente.
9. [ ] Usar únicamente el flujo existente de staging para configurar y enviar a los dos firmantes ficticios. Verificar estados individuales de ambos; una sola firma no es suficiente.
10. [ ] Reconciliar la solicitud y archivar el PDF final firmado y el certificado de finalización por separado. Verificar que ambos artefactos tengan SHA-256 y fechas registradas.
11. [ ] Consultar readiness de contratación: debe responder `SIGNED_CONTRACT_ARCHIVED`. Intentar contratar debe validar la misma empresa Odoo del vínculo.
12. [ ] Ejecutar controles negativos: una sola firma, PDF no archivado, archivo reemplazado, empresa distinta y otra postulación deben bloquearse antes de crear usuario Cognito, empleado Odoo o onboarding.
13. [ ] Repetir la consulta/vinculación y la reconciliación: deben ser idempotentes, sin duplicar vínculo, plantilla, solicitud o artefactos.
14. [ ] Con ambos flags desactivados, confirmar que el flujo legado sigue funcionando en el entorno de prueba.

## Evidencias a guardar
- SHA de imagen backend y frontend desplegados en staging.
- Versión de Alembic.
- IDs de fixture (no PII), postulación, empresa Odoo y solicitud Sign.
- Respuestas/status codes de los pasos 1, 4, 6, 7, 11 y 12.
- Estado y hashes del PDF firmado y certificado.
- Resultado de CI del commit desplegado.

## Bloqueos de liberación
No fusionar ni activar flags en producción si algún control negativo falla, si hay escritura de Odoo antes del vínculo, si se crea un empleado antes de ambas firmas y archivo, o si el PDF/certificado no pueden verificarse. Esta lista es un procedimiento manual; no afirma que la prueba real de staging ya se haya ejecutado.
