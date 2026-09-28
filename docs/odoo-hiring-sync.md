# Selección y contratación → Odoo

## Objetivo

Odoo recibe únicamente los procesos que ya avanzaron lo suficiente para ser operativos:

- al pasar una postulación a `SELECTED`, aiRecruiter prepara el alta/actualización de la vacante y del postulante en Odoo;
- al confirmar `HIRED`, aiRecruiter actualiza ese proceso y prepara el alta/actualización del empleado.

Las vacantes y candidatos que continúan en etapas tempranas permanecen solo en aiRecruiter.

## Arquitectura: outbox local

La integración se divide en estado durable y transporte.

Este corte **no hace llamadas de red a Odoo**. La selección y la contratación terminan localmente aunque Odoo esté indisponible; un transporte posterior consumirá los registros pendientes.

### Postulante seleccionado

La tabla `odoo_applicant_syncs` mantiene un único estado por postulación (`job_candidate_id`).

Clave de idempotencia:

`application:{job_candidate_id}`

Estados:

- `PENDING`: el postulante/vacante están listos para crear o actualizar en Odoo;
- `SYNCED`: Odoo confirmó el upsert;
- `FAILED`: el último intento falló y conserva contexto para reintento.

Cuando exista transporte real, `odoo_job_id` y `odoo_applicant_id` conservarán los IDs externos para actualizaciones posteriores.

### Empleado contratado

La tabla `odoo_employee_syncs` mantiene un único estado por empleado.

Clave de idempotencia:

`employee:{employee_id}`

La contratación garantiza también que exista el outbox del postulante. Así, un candidato contratado directamente sin haber pasado manualmente por `SELECTED` sigue teniendo los dos pasos durables y ordenables: postulante y empleado.

## Contrato de vacante / proceso de selección

Cada vacante conserva explícitamente:

- `response_time_business_days`: 2 por defecto;
- `phone_call_count`: 1 por defecto;
- `onsite_interview_count`: 1 por defecto;
- `offer_wait_days`: 4 por defecto;
- `offer_wait_reference`: `AFTER_INTERVIEW`.

Estos valores son editables en aiRecruiter y forman parte del payload `UPSERT_APPLICANT`.

## Contrato `UPSERT_APPLICANT` v1

Incluye:

- IDs internos de candidato, vacante y postulación;
- estado y fecha de cambio de la postulación;
- nombre, correo y teléfono cuando exista en metadata;
- referencia al CV canónico del candidato, sin persistir URLs firmadas temporales;
- título, país, ciudad y tipo de empleo;
- tiempos y pasos del proceso de selección.

El CV se identifica como `CANONICAL_CANDIDATE_DOCUMENT`; el transporte resolverá el documento canónico vigente al momento de enviarlo.

## Contrato `UPSERT_EMPLOYEE` v1

Incluye:

- IDs internos de empleado, candidato, vacante y postulación;
- fecha de contratación;
- nombre y apellido;
- correo;
- cargo;
- área/departamento;
- fecha de ingreso;
- contexto básico de la vacante.

## Pendiente antes del transporte real

No activar llamadas a Odoo hasta definir explícitamente:

- modelo(s) destino y nombres técnicos de campos en Odoo;
- endpoint/base URL y mecanismo de autenticación;
- fuente canónica de teléfono cuando no venga en metadata;
- transferencia del CV canónico como adjunto;
- campos contractuales o de nómina requeridos por Talento Humano;
- política de reintentos y transición `FAILED → PENDING`;
- orden de consumo postulante → empleado;
- captura y reutilización de `odoo_job_id`, `odoo_applicant_id` y `odoo_record_id`.

## Regla de disponibilidad

Una indisponibilidad de Odoo no debe impedir que aiRecruiter:

1. cambie la postulación a `SELECTED`;
2. opere la agenda de llamadas/entrevistas;
3. confirme `HIRED`;
4. cree/reutilice el acceso del empleado;
5. asigne el Onboarding ASIATI.

El transporte se reintentará posteriormente a partir del outbox.
