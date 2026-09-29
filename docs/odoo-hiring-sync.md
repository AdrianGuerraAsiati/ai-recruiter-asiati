# Selección y contratación → Odoo

## Objetivo

Odoo recibe únicamente los procesos que ya avanzaron lo suficiente para ser operativos:

- al pasar una postulación a `SELECTED`, aiRecruiter prepara el alta/actualización de la vacante y del postulante en Odoo;
- al confirmar `HIRED`, aiRecruiter actualiza ese proceso y prepara el alta/actualización del empleado.

Las vacantes y candidatos que continúan en etapas tempranas permanecen solo en aiRecruiter.

## Arquitectura: outbox local

La integración se divide en estado durable y transporte.

La selección y la contratación terminan localmente aunque Odoo esté indisponible. El empleado contratado queda primero en el outbox y puede enviarse explícitamente con:

`POST /api/odoo/employees/{employee_id}/sync`

El endpoint consume `odoo_employee_syncs` y hace un upsert idempotente sobre `hr.employee`. El transporte externo sigue desacoplado del commit de contratación, por lo que un fallo de Odoo no revierte `HIRED`, Cognito ni onboarding.

### Postulante seleccionado

La tabla `odoo_applicant_syncs` mantiene un único estado por postulación (`job_candidate_id`).

Clave de idempotencia:

`application:{job_candidate_id}`

Estados:

- `PENDING`: el postulante/vacante están listos para crear o actualizar en Odoo;
- `SYNCED`: Odoo confirmó el upsert;
- `FAILED`: el último intento falló y conserva contexto para reintento.

`odoo_job_id` y `odoo_applicant_id` conservan los IDs externos para actualizaciones posteriores. El transporte explícito usa `POST /api/odoo/applications/{application_id}/sync` y ejecuta vacante → postulante → CV canónico.

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

## Conexión ASIATI validada

Validación realizada contra Odoo 18 Enterprise:

- base URL XML-RPC: `https://www.asiaticorp.com`;
- base de datos: `snva-proyectos-master-asiati-main-24854823`;
- usuario técnico: `sistemas@asiati.com.co`;
- secreto: `/ai-recruiter/prod/odoo` en AWS Secrets Manager;
- autenticación XML-RPC validada con UID 99;
- compañía objetivo: `ASIATI` (ID observado 1);
- permisos READ/CREATE/WRITE confirmados para `hr.employee`, `hr.applicant`, `hr.job` e `ir.attachment`;
- no existen campos personalizados `x_*` en esos modelos.

Etapas de reclutamiento observadas: `New`, `Initial Qualification`, `First Interview`, `Second Interview`, `Contract Proposal`, `Contract Signed`. Un `SELECTED` de aiRecruiter se envía inicialmente a `Initial Qualification` cuando esa etapa existe; la agenda de entrevistas sigue siendo interna y no mueve etapas Odoo automáticamente.

El transporte de postulante resuelve/reutiliza la vacante por nombre exacto dentro de ASIATI, crea/actualiza `hr.applicant` usando `partner_name`, `email_from`, `partner_phone`, `job_id`, `company_id` y `stage_id`, y adjunta el CV canónico mediante `ir.attachment.datas`. El transporte de empleado fija también `company_id` a ASIATI cuando el campo está disponible.

## Pendiente antes de activar producción

`ODOO_ENABLED` debe permanecer en `false` hasta desplegar y completar una prueba controlada.

Pendiente:

- cargar los valores no secretos en `/ai-recruiter/prod/runtime-config`;
- verificar que el runtime tenga IAM mínimo de lectura sobre `/ai-recruiter/prod/odoo`;
- desplegar el transporte de postulante;
- ejecutar un POST manual controlado sobre una postulación `SELECTED`;
- comprobar en Odoo vacante, postulante y CV;
- ejecutar después una contratación controlada para validar `hr.employee`;
- decidir si se incorporan más datos privados/contractuales;
- automatizar el consumo de outboxes únicamente después de validar ambos POST manuales.

## Regla de disponibilidad

Una indisponibilidad de Odoo no debe impedir que aiRecruiter:

1. cambie la postulación a `SELECTED`;
2. opere la agenda de llamadas/entrevistas;
3. confirme `HIRED`;
4. cree/reutilice el acceso del empleado;
5. asigne el Onboarding ASIATI.

El transporte se reintentará posteriormente a partir del outbox.
