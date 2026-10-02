# Selección y contratación → Odoo

## Objetivo

Odoo recibe únicamente los procesos que ya avanzaron lo suficiente para ser operativos:

- al pasar una postulación a `SELECTED`, aiRecruiter prepara el alta/actualización de la vacante y del postulante en Odoo;
- al confirmar `HIRED`, aiRecruiter actualiza ese proceso, prepara el alta/actualización del empleado y, cuando se suministran datos contractuales, prepara también su contrato inicial.

Las vacantes y candidatos que continúan en etapas tempranas permanecen solo en aiRecruiter.

## Arquitectura: outbox local

La integración se divide en estado durable y transporte.

La selección y la contratación terminan localmente aunque Odoo esté indisponible. El empleado contratado queda primero en el outbox y puede enviarse explícitamente con:

`POST /api/odoo/employees/{employee_id}/sync`

El endpoint consume `odoo_employee_syncs` y hace un upsert idempotente sobre `hr.employee`. El transporte externo sigue desacoplado del commit de contratación, por lo que un fallo de Odoo no revierte `HIRED`, Cognito ni onboarding.

Cuando la contratación incluye contrato, `odoo_contract_syncs` conserva el payload y el estado de entrega de `hr.contract`. El contrato solo se intenta después de que el empleado tenga un `odoo_record_id`; si Odoo falla, queda reintentable sin revertir la contratación.

Retry explícito del contrato:

`POST /api/odoo/employees/{employee_id}/contract/sync`

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
- teléfono del candidato cuando exista en metadata;
- contexto básico de la vacante.

### Mapeo inicial a `hr.employee`

El transporte consulta primero `fields_get` y solo escribe campos disponibles y editables en la instancia real.

Mapeo v1:

- `name` ← nombre completo;
- `work_email` ← correo del empleado en aiRecruiter;
- `job_title` ← cargo;
- `private_phone` ← teléfono del candidato;
- `employee_type = employee` solo si Odoo expone esa selección;
- `department_id` solo si existe exactamente un departamento con el mismo nombre;
- `job_id` solo si existe exactamente un puesto con el mismo nombre.

No se crean automáticamente departamentos, puestos ni empresas. Si una relación no puede resolverse de forma inequívoca, se omite y el empleado puede sincronizarse con los campos restantes.

La búsqueda idempotente usa primero `odoo_record_id` persistido y, si no existe, `work_email`. Dos empleados Odoo con el mismo correo detienen el intento para evitar actualizar el registro equivocado.


## Contrato `UPSERT_CONTRACT` v1

El modal normal de contratación captura:

- tipo de contrato;
- fecha de inicio;
- fecha de finalización opcional;
- salario mensual.

El payload también conserva IDs internos de empleado, vacante y postulación, además del nombre, cargo y área del empleado.

### Mapeo inicial a `hr.contract`

El transporte consulta `fields_get` antes de escribir y solo usa campos disponibles y editables:

- `name` ← nombre generado del contrato;
- `employee_id` ← ID de `hr.employee` ya sincronizado;
- `date_start` ← inicio del contrato;
- `date_end` ← finalización cuando exista;
- `wage` ← salario mensual;
- `contract_type_id` ← coincidencia exacta por nombre, solo cuando Odoo expone ese campo y existe exactamente un tipo coincidente.

La búsqueda idempotente usa primero el `odoo_record_id` del contrato y luego la pareja empleado + fecha de inicio. Esta primera versión cubre el **contrato inicial generado al contratar**; renovaciones, otrosíes y terminaciones se modelarán como historial contractual separado para no sobrescribir evidencia histórica.

## Pendiente antes de activar producción

El transporte de empleado ya existe, pero `ODOO_ENABLED` debe permanecer en `false` hasta configurar y validar la conexión ASIATI.

Pendiente:

- cargar base URL, base de datos, usuario y secret ID en runtime;
- guardar la API key únicamente en AWS Secrets Manager;
- verificar IAM mínimo de lectura del secreto;
- hacer `healthcheck` y prueba controlada sobre la instancia real;
- completar transporte de postulante/vacante;
- transferir el CV canónico como adjunto;
- decidir qué datos contractuales adicionales deben gestionarse después del contrato inicial (renovaciones, otrosíes, terminación y documentos firmados);
- automatizar el consumo de outboxes después de validar el POST manual.

## Regla de disponibilidad

Una indisponibilidad de Odoo no debe impedir que aiRecruiter:

1. cambie la postulación a `SELECTED`;
2. opere la agenda de llamadas/entrevistas;
3. confirme `HIRED`;
4. cree/reutilice el acceso del empleado;
5. asigne el Onboarding ASIATI.

El transporte se reintentará posteriormente a partir del outbox.
