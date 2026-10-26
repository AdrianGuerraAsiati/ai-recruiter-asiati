# Plan: UI de vinculación contractual ADN360

## Interfaces previstas
- `application_contracts.binding_status(db, *, owner_sub, job_id, candidate_id) -> dict`: estado `enabled`, `bound`, `valid`, `can_bind`, `status`, `message` y `odoo_company_id` opcional.
- `GET /api/jobs/{job_id}/candidates/{candidate_id}/contract/binding`: expone el estado anterior tras validar vacante/candidato y permiso `employees.create`.
- `GET /api/jobs/hiring/signature-flow`: conserva `enabled` y añade `binding_enabled`.
- Modal React: recibe `application`, `onClose`, `onContinue(profileId)`; consulta estado y catálogo de empresas, vincula con el endpoint existente y ofrece continuar a Documentos.

## Tarea 1 — Pruebas de backend primero
- Añadir pruebas para estado sin perfil, contrato no aprobado, contrato aprobable/vinculable, vínculo existente válido e inválido.
- Añadir pruebas de `signing.readiness` y `signing.prepare`: con el flag de vinculación activo, el contrato sin vínculo falla antes de llamar al cliente Odoo; con un vínculo consistente, readiness puede continuar.
- Ejecutar `pytest app/tests/test_application_contract_binding_routes.py app/tests/test_employee_contract_sign_requests.py -q` y confirmar que las nuevas pruebas fallan por funcionalidad ausente.

## Tarea 2 — Estado de vinculación y capacidades
- Implementar `binding_status` en `app/domains/hiring/application_contracts.py`.
- Añadir ruta GET y devolver `binding_enabled` en `/jobs/hiring/signature-flow`.
- Ejecutar las pruebas de Tarea 1 hasta que pasen.

## Tarea 3 — Fail-closed antes de Odoo Sign
- En `app/domains/employee_documents/signing.py`, comprobar documento, empleado, postulación asociada y `source_storage_key` en readiness y antes de la rama idempotente de preparación.
- No consultar ni escribir en Odoo si el vínculo falta o no coincide.
- Ejecutar pruebas de firma y regresiones de documentos.

## Tarea 4 — Modal frontend con pruebas
- Crear `frontend-react/src/components/ApplicationContractBindingModal.jsx`.
- Crear pruebas para: cargar empresas/estado, bloquear si el PDF no está aprobado, vincular una vez, mostrar empresa ya vinculada, errores de API y continuar a Documentos.
- Ejecutar `npm test -- ApplicationContractBindingModal.test.jsx` en `frontend-react/` y verificar que falle antes de implementar el modal.

## Tarea 5 — Integración en Postulaciones
- En `Applications.jsx`, usar las capacidades `enabled` y `binding_enabled`; ofrecer preparación de expediente cuando cualquiera de los flags de flujo aplica.
- Mostrar **Vincular contrato** solo a usuarios con permiso, perfil existente, estado `SELECTED` o `OFFER`, y vinculación habilitada.
- Al terminar, ofrecer navegación a `/documents?employee_id=...`; conservar la vía actual de revisión documental y contratación.
- Añadir pruebas de visibilidad por permisos/estado, apertura del modal y navegación.
- Ejecutar la suite completa de frontend.

## Tarea 6 — Verificación y staging
- Ejecutar `pytest app/tests -q` en el entorno aislado de CI, `npm test`, `npm run lint` y `npm run build` desde `frontend-react/`.
- Revisar diff y CI completo.
- Documentar un recorrido manual con candidato ficticio: perfil sin login, PDF aprobado, vínculo a empresa Odoo, preparación sin envío automático, dos firmas, PDF + certificado archivados, gate de contratación y ausencia de duplicados.
- No desplegar ni modificar flags desde esta rama. La validación real requiere que el backend de staging contenga la migración 059 y ambos flags estén habilitados solo en ese entorno de pruebas.

## Revisión de cobertura
- Estados de entrada: sin perfil, documento ausente, pendiente de revisión, aprobado, ya preparado, vínculo existente, vínculo inválido.
- Fallos externos: catálogo Odoo no disponible, empresas vacías, error 409/422 de vinculación.
- Seguridad: permisos de lectura/escritura, no mutar si el vínculo falta, no reutilizar PDF en otra postulación.
- Compatibilidad: ambos flags desactivados conservan el flujo legado.
