# Vinculación contractual desde Postulaciones — diseño

## Objetivo
Completar la interfaz de ADN360 para asociar un PDF aprobado y una empresa Odoo a una postulación concreta antes de preparar Odoo Sign. Evitar que una firma se inicie sin vínculo inmutable y que el expediente quede imposible de vincular después.

## Flujo de usuario
1. En **Postulaciones**, preparar el expediente APPLICANT sin crear una cuenta de empleado.
2. En **Documentos**, cargar y aprobar el PDF contractual.
3. Volver a la postulación seleccionada y abrir **Vincular contrato**. Elegir una empresa Odoo activa y confirmar el vínculo con esa postulación.
4. Tras confirmar el vínculo, abrir el expediente en Documentos y preparar la plantilla de Odoo Sign.
5. Continuar el proceso de dos firmas y archivo existente; solo el gate de contratación habilita la creación formal.

## Diseño elegido y alternativas
- **Elegido: modal desde cada fila de Postulaciones.** El contexto incluye explícitamente vacante y candidato; la selección de empresa se realiza una vez, el estado de vínculo puede consultarse y el usuario recibe una acción para continuar al expediente.
- Alternativa descartada: vincular desde Documentos. Esa vista se organiza por empleado y una persona puede tener más de una postulación, por lo que el contexto contractual puede ser ambiguo.
- Alternativa descartada: selector de empresa embebido en cada fila. Carga demasiado la tabla y dificulta mostrar errores, vínculo existente e inmutabilidad.

## Contratos y controles
- Añadir lectura de estado `GET /api/jobs/{job_id}/candidates/{candidate_id}/contract/binding`; conservar el `POST .../contract/bind` ya existente.
- Extender `GET /api/jobs/hiring/signature-flow` con `binding_enabled`, sin cambiar el significado de `enabled` (gate de contratación).
- Cuando `application_contracts.binding_enabled()` sea verdadero, la preparación y readiness de Odoo Sign deben rechazar contratos sin vínculo que coincida con empleado, documento y `source_storage_key`.
- Permisos: reutilizar `employees.create` para lectura/vinculación y `employee_documents.review` para preparación de firma.
- Flags cerrados por defecto. No activar variables ni desplegar desde esta tarea.

## Alcance
Frontend: `Applications.jsx`, nuevo `ApplicationContractBindingModal.jsx`, tests del modal y del flujo de Postulaciones.
Backend: `application_contracts.py`, `hiring/router.py`, `employee_documents/signing.py`, tests de vínculo y preparación de firma.
Documentación: pasos manuales de staging y condiciones de seguridad.

## No objetivos / limitaciones
No automatizar la contratación después de la firma, no cambiar el envío de correo de Odoo Sign, no migrar contratos históricos ni resolver el límite de un contrato por empleado/tipo. No desplegar ni activar flags en producción.

## Criterios de aceptación
- Un contrato aprobado y no preparado puede vincularse a una sola postulación y empresa.
- La UI informa si falta aprobar el PDF, si ya está vinculado o si el vínculo es inválido.
- La preparación de Odoo Sign falla antes de cualquier escritura cuando el flag está activo y falta el vínculo correcto.
- Con los flags desactivados se conserva el comportamiento anterior.
- Backend tests, frontend tests, lint y build pasan; la prueba real con Odoo Sign queda documentada para staging aislado.
