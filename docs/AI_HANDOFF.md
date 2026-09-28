# AI Handoff — aiRecruiterAsiati

> Punto de recuperación operativo para continuar el proyecto desde un chat, agente o sesión nueva sin depender del historial de conversación.
>
> **Regla:** este archivo debe actualizarse después de un merge importante, un cambio de arquitectura o al cerrar una sesión larga de trabajo.

## Estado del repositorio

- **Repositorio:** `AdrianGuerraAsiati/ai-recruiter-asiati`
- **Rama principal:** `main`
- **Último checkpoint conocido:** `7866838171c435eb218ddf6b98cda69b1471fb9c`
- **Fecha del checkpoint:** 2026-09-28
- **Commit:** `feat: enviar empleados contratados a Odoo (#92)`

Antes de continuar trabajo nuevo, comprobar que `main` sigue apuntando a este commit o a uno posterior.

<!-- AI_HANDOFF_AUTO_START -->
## Checkpoint automático

- **Última actualización automática:** 2026-09-28
- **Merge commit:** `cd5897f33ca73d6893f07d5e00b7e5fb8858529a`
- **PR:** [#94 — feat: editar equipo ASIATI desde administración](https://github.com/AdrianGuerraAsiati/ai-recruiter-asiati/pull/94)
- **Origen:** merge a `main` con etiqueta `handoff:update`

> Este bloque es administrado por `.github/workflows/ai-handoff.yml`. No editarlo manualmente.
<!-- AI_HANDOFF_AUTO_END -->

## Objetivo actual

Mantener aiRecruiterAsiati como una plataforma de reclutamiento estable, modular y operable, con foco inmediato en:

1. completar el consumidor real de `odoo_applicant_syncs`; el envío explícito de `odoo_employee_syncs` ya existe vía POST;
2. validar el mapeo real de empleado contra Odoo ASIATI y completar postulante/vacante + adjunto de CV;
3. mantener la agenda de selección como herramienta operativa interna de Talento Humano para llamadas telefónicas y entrevistas presenciales;
4. cerrar deuda técnica P2 sin romper reclutamiento, Resume Agent, onboarding ni los flujos críticos ya estabilizados;
5. fortalecer pruebas, observabilidad, UI/UX e infraestructura antes de habilitar sincronización externa en producción.

## Trabajo reciente completado

### Arquitectura y calidad

- Modularización de Training y Resume Agent.
- Training reducido de ~1904 a 928 líneas mediante extracción progresiva de modales, quizzes, journey de empleado, editor de contenido y asignaciones/resultados.
- Resume Agent: runtime extraído a `browser_runtime.py` (#61); sanitización y construcción de eventos/controles a `browser_diagnostics.py` (#63/#69); parsing de respuestas a `browser_responses.py` (#67); estado/challenges de página a `browser_page_state.py` (#68).
- Jobs: utilidades puras, paginación, card, toolbar y modales de eliminación/contratación extraídos (#71–#74, #76–#77), reduciendo `Jobs.jsx` de 1244 a 1021 líneas.
- Separación de modelos y responsabilidades.
- Validaciones locales relacionadas con Cognito.
- Hardening general de código e infraestructura.
- Mejoras de RBAC, readiness, rollback, backups, CI y seguridad web.
- PR #79 eliminó `owner_sub` como frontera de autorización para datos de reclutamiento: vacantes, candidatos, postulaciones, evaluaciones, rankings, importaciones ligadas a vacantes, contratación y acceso al CV canónico son compartidos entre administradores autorizados. `owner_sub` se conserva como procedencia/auditoría e identidad técnica de integraciones.
- Dependabot agrupado por ecosistema.

### Testing

- E2E con Chromium.
- Smoke tests de accesibilidad.
- Smoke tests responsive.
- Journey integrado de autenticación y navegación.

### UI/UX

- Auditoría integral del sistema visual.
- Consolidación de navegación y primitives de UI.
- Mejoras de accesibilidad y responsive.
- Estados de carga más claros.
- Feedback no bloqueante.
- Animaciones accesibles para cargas, calificaciones y rankings.
- Sustitución de errores genéricos por mensajes contextualizados y accionables.

### Selección, agenda y contratación

- PR #85 agregó una **Agenda de selección** interna dentro del reclutador para que Talento Humano programe directamente llamadas telefónicas y entrevistas presenciales.
- Se agregó la etapa de postulación `SELECTED`; para Indeed se traduce a `POSITIVELY_SCREENED`.
- La agenda persiste citas por vacante + candidato y soporta tipos `PHONE_CALL` y `ONSITE_INTERVIEW`.
- Las citas soportan estados `SCHEDULED`, `COMPLETED` y `CANCELED`, edición, cancelación, marcado como realizada, vista mensual y panel de próximas citas.
- Solo postulaciones en `SELECTED`, `INTERVIEW`, `OFFER` o `HIRED` son elegibles para agenda.
- Se agregó el dominio backend `app/domains/recruitment_calendar`, la ruta de frontend de Agenda y la migración Alembic `027`.
- El PR #85 pasó `CI — Tests & Build` y `Security — CodeQL` antes del merge.
- La agenda es actualmente **fuente operativa interna de aiRecruiter**. La sincronización con Odoo todavía no está implementada.
- Regla de producto para la integración futura: evitar poblar Odoo con todo el pipeline de reclutamiento; el envío debe ocurrir únicamente cuando el candidato haya avanzado a la etapa de negocio definida para selección/contratación.

### Onboarding

- Seguimiento detallado del progreso de onboarding para ADMIN.
- Filtro de empleados por estado de onboarding.
- PR #81 convirtió `Onboarding ASIATI` en contenido administrado por el sistema: se provisiona/publica automáticamente y no depende de que un ADMIN cree el curso, módulos, lecciones, videos o quiz.
- La ruta corporativa mantiene 7 módulos versionados: bienvenida, conoce ASIATI, conoce al equipo, permisos y vacaciones, contenido corporativo, cultura interna y lo que esperamos de ti; usa los videos disponibles en la carpeta `Final` de Drive.
- PR #83 eliminó la asignación manual del onboarding: todos los perfiles `ACTIVE` que requieren onboarding reciben automáticamente la misma ruta `Onboarding ASIATI`; perfiles `NOT_REQUIRED` y `DISABLED` quedan excluidos.
- ADMIN/SUPER_ADMIN no asignan la ruta. Su flujo administrativo es vista previa, seguimiento de progreso y resultados.
- La vista **Empleados > Equipo ASIATI** permite editar cargo/área, rol y si el Onboarding ASIATI es requerido para cada integrante administrable.
- ADMIN puede gestionar roles `EMPLOYEE` y `ADMIN`; `SUPER_ADMIN` permanece reservado para Dirección. Un ADMIN no puede administrar perfiles `SUPER_ADMIN`.
- El requisito de onboarding puede cambiarse entre requerido/no requerido, pero el progreso `PENDING` / `IN_PROGRESS` / `COMPLETED` sigue derivándose de actividades reales y no se marca manualmente.
- Al marcar `NOT_REQUIRED`, la asignación histórica no se destruye, pero el onboarding deja de exponerse al empleado; al volver a requerirlo, se reutiliza y resincroniza la asignación existente.
- `managed_by_system=true` identifica la ruta protegida y el backend rechaza mutaciones manuales sobre su contenido.

### Operación e infraestructura

- Request correlation y logging estructurado.
- Alarmas de cola/DLQ versionadas.
- Alarmas operativas mantenidas como **opt-in** hasta verificar IAM.
- Diagnóstico automático de fallos del stack `candidate-import`.
- Backup/restore host-side corregido para Lightsail.
- Disaster recovery off-host opcional.

## Estado funcional que no debe romperse

### Candidatos y vacantes

- Vacantes, candidatos y postulaciones son datos globales de reclutamiento de la organización para usuarios con permisos administrativos correspondientes; no deben ocultarse por el `owner_sub` del creador.
- `owner_sub` es procedencia/auditoría y no una frontera de acceso para estos datos. EMPLOYEE sigue restringido por RBAC.
- Un mismo candidato puede existir en vacantes distintas.
- Si el mismo candidato aparece varias veces para **la misma vacante**, debe prevalecer la postulación más reciente.
- Esa deduplicación no debe bloquear al candidato ni eliminar sus postulaciones a otras vacantes.

### Descripciones de vacantes

Deben coexistir dos fuentes independientes:

- descripción proveniente de Indeed;
- descripción generada/mejorada por IA.

La ingestión no debe sobrescribir automáticamente una descripción generada por IA. La UI debe permitir seleccionar cuál descripción utilizar.

### Onboarding ASIATI

- Los módulos corporativos los mantiene el sistema, no los administradores.
- Al abrir el catálogo administrativo de capacitación, el backend debe garantizar una única ruta `Onboarding ASIATI` publicada e idempotente.
- Un ADMIN no debe necesitar botones de “Crear ruta ASIATI” ni “Crear curso” para que exista el onboarding corporativo.
- La ruta administrada por sistema debe ser de solo lectura en autoría y distribución; los administradores conservan seguimiento, resultados y vista previa.
- La asignación del `Onboarding ASIATI` es automática e idempotente para perfiles activos que requieren onboarding. Altas, reactivaciones, contratación y acceso a Capacitación deben poder recuperar una asignación faltante sin intervención administrativa.
- La infraestructura genérica de asignaciones puede mantenerse para futuras capacitaciones opcionales o segmentadas, pero no debe exponerse como parte del flujo actual del onboarding corporativo.
- No inventar contenido corporativo no respaldado por los materiales disponibles. Si un recurso fuente es genérico (por ejemplo, el video de Módulo 5), mantener una denominación neutral hasta contar con información corporativa adicional.

### Agenda de selección

- Talento Humano agenda manualmente llamadas y entrevistas presenciales desde aiRecruiter.
- No se debe exigir que un administrador asigne una agenda o ruta de selección a otro usuario.
- Una cita debe estar ligada a una postulación real `job_id + candidate_id`.
- Candidatos en etapas tempranas no deben aparecer como elegibles para crear citas.
- La agenda no debe crear por sí sola registros en Odoo mientras no exista el contrato de sincronización aprobado e implementado.
- Las fechas persistidas deben conservar semántica de zona horaria y el backend debe seguir validando que `ends_at > starts_at`.

### Integración Odoo

- Odoo será un sistema posterior dentro del flujo, no el repositorio primario de todas las vacantes/candidatos del reclutador.
- No enviar a Odoo candidatos que todavía están únicamente en etapas tempranas del pipeline.
- Antes de implementar la sincronización deben definirse explícitamente: evento disparador, payload, mapeo de campos, idempotencia, reintentos, trazabilidad y comportamiento ante errores.
- La agenda interna puede servir como contexto operativo, pero en esta fase no sincroniza llamadas ni entrevistas con Odoo.
- La contratación/onboarding debe seguir funcionando aunque Odoo esté temporalmente no disponible; la futura integración no debe convertir una caída de Odoo en pérdida del estado local.

### Resume Agent

El Resume Agent debe poder revisar vacantes y candidatos existentes y sincronizar el estado sin crear duplicados incorrectos ni dejar jobs permanentemente bloqueados.

## Riesgos / puntos a verificar

- IAM de las alarmas operativas todavía debe verificarse antes de habilitarlas por defecto.
- Cualquier cambio en Resume Agent debe probar idempotencia y recuperación ante fallos.
- Ingestiones deben probar deduplicación por combinación candidato + vacante.
- Cambios de UI deben conservar accesibilidad, responsive y feedback accionable.
- No asumir que un deploy exitoso implica funcionamiento correcto: revisar health/readiness y journey crítico.
- La integración con Odoo todavía es diseño pendiente: no asumir que existe sincronización de candidatos, agenda o contratación.
- La futura sincronización con Odoo debe ser idempotente para evitar empleados/contactos duplicados ante reintentos.
- Cambios en Agenda deben conservar elegibilidad por estado, zona horaria, permisos y relación vacante+candidato.

## Prioridad de trabajo

### TODO actual

#### Flujo selección → contratación → Odoo
- [x] Compartir vacantes/candidatos/postulaciones entre administradores autorizados (#79).
- [x] Incorporar etapa `SELECTED` y agenda interna para llamadas/entrevistas (#85).
- [x] Mantener el Onboarding ASIATI administrado y asignado automáticamente por el sistema (#81/#83).
- [x] Permitir edición administrativa del Equipo ASIATI para cargo/área, rol EMPLOYEE↔ADMIN y requisito de onboarding (#94).
- [ ] Definir contrato de datos aiRecruiter → Odoo para candidatos que alcancen la etapa de negocio acordada.
- [ ] Mapear los campos requeridos por Odoo y separar datos obligatorios, opcionales y derivados.
- [ ] Definir el disparador exacto de alta/sincronización en Odoo y cómo se relaciona con `SELECTED`, `OFFER` y `HIRED`.
- [ ] Implementar idempotencia y trazabilidad de sincronización con Odoo para evitar duplicados.
- [ ] Diseñar reintentos/estado de error sin bloquear contratación ni onboarding local.
- [ ] Decidir posteriormente si las citas internas también deben sincronizarse con calendario/Odoo; por ahora permanecen solo en aiRecruiter.

#### P2 · Gobernanza y mantenimiento
- [ ] Proteger `main` y exigir checks de CI/CodeQL antes de merge. Actualmente la rama no está protegida.
- [x] Separar upgrades mayores de Dependabot: minor/patch agrupados, majors individuales.
- [x] Desacoplar el contrato de CI de una versión fija de `actions/upload-artifact`.
- [x] Reducir ejecuciones innecesarias del workflow de AI handoff.
- [x] Evitar deploys de producción para cambios solo documentales, handoff, Dependabot o tests.
- [x] Omitir CodeQL en cambios puramente documentales/configuración de handoff.
- [x] PR #41 frontend minor/patch validado con CI + CodeQL y mergeado.
- [x] PR #42: jsdom 26 → 30 validado y mergeado.
- [x] PR #43: Vitest 3 → 5 validado y mergeado.
- [x] Lote Python minor/patch revalidado con cobertura del Resume Agent (#51) y mergeado vía #52.
- [x] Major `websockets` revalidado sobre `main` actual y mergeado vía #55; #45 quedó reemplazado/cerrado.
- [x] Major `rpds-py` revalidado sobre `main` actual y mergeado vía #56; #46 quedó reemplazado/cerrado.
- [x] #53, #55 y #56 pasaron CI/CodeQL; los cambios de dependencias raíz también pasaron Resume Agent Linux + Windows y self-test empaquetado.
- [ ] Revisar el PR de GitHub Actions cuando Dependabot lo regenere con la nueva política.

#### P2 · Modularización residual
- [x] Reducir responsabilidades de `frontend-react/src/pages/Training.jsx`: 1904 → 928 líneas; modales, quiz de empleado, quiz administrativo, journey del empleado, editor de módulos/lecciones y asignaciones/resultados extraídos.
- [~] Reducir responsabilidades de `tools/indeed_resume_agent/browser.py`: 2028 → 1692 líneas; runtime, sanitización/eventos de diagnóstico, parsing de respuestas y estado de página extraídos. Pendiente separar lifecycle/persistencia de diagnóstico y, en una fase dedicada de mayor riesgo, navegación/búsqueda y captura de CV.
- [~] Modularizar `frontend-react/src/pages/Jobs.jsx`: 1244 → 1021 líneas; utilidades puras, paginación, card, toolbar y modales de eliminación/contratación extraídos (#71–#74, #76–#77). Pendiente separar detalle/formulario en cortes pequeños.
- [ ] Dividir `app/domains/training/asiati_preset.py` (~58 KB) en datos/configuración y builder.
- [ ] Reducir `frontend-react/src/pages/RankingView.jsx` (~51 KB).
- [ ] Revisar si `tools/indeed_resume_agent/ui.py` y `ui_v2.py` son legacy sin referencias; eliminarlos solo después de verificar imports, packaging y tests.

#### P2 · Regresiones críticas
- [ ] Mantener pruebas explícitas de deduplicación por candidato + vacante conservando la postulación más reciente.
- [x] Mantener cobertura de visibilidad/operación global entre administradores para vacantes, candidatos, ranking, importaciones, contratación y CV canónico (#79).
- [ ] Mantener pruebas de idempotencia y recuperación del Resume Agent.
- [ ] Mantener pruebas de descripción Indeed vs descripción IA sin sobrescritura.
- [ ] Ejecutar journey E2E, accesibilidad y responsive en refactors de frontend.
- [x] Mantener regresiones de autoprovisionamiento/idempotencia y bloqueo de autoría manual del Onboarding ASIATI (#81).

#### Pendientes operativos externos
- [ ] Verificar IAM antes de activar las alarmas operativas por defecto.
- [ ] Ejecutar el corte controlado del Resume Agent con una aplicación real, luego lote de 5–10 y finalmente backlog.

### Fase activa

La fase funcional activa es consolidar el flujo **selección → agenda → contratación → integración Odoo**. La deuda P2 sigue vigente y debe cerrarse en paralelo mediante PRs pequeños, pero no sustituye el objetivo funcional inmediato.

Antes de construir la integración con Odoo debe verificarse el modelo actual de contratación y definirse un contrato explícito de sincronización. No implementar envíos generales de vacantes/candidatos a Odoo.

### P2 — continuar

La fase técnica paralela continúa cerrando P2 restantes detectados durante la auditoría senior.

Al comenzar una nueva sesión:

1. revisar los commits posteriores al checkpoint;
2. revisar CI y tests;
3. identificar P2 todavía abiertos en código/documentación;
4. trabajar por bloques pequeños y verificables;
5. ejecutar pruebas relevantes;
6. hacer commit/merge;
7. actualizar este archivo si cambió el estado del proyecto.

## Protocolo para una sesión nueva de IA

Una sesión nueva debería comenzar con una instrucción similar a:

> Continúa aiRecruiterAsiati. Usa `docs/AI_HANDOFF.md` como checkpoint inicial, pero verifica el estado actual de `main`, los commits posteriores, CI y el código antes de asumir que el documento sigue vigente. GitHub es la fuente de verdad.

### Orden recomendado de lectura

1. `docs/AI_HANDOFF.md`
2. últimos commits de `main`
3. README y documentación técnica relacionada con la tarea
4. archivos modificados recientemente
5. tests asociados
6. CI / workflows relevantes

## Jerarquía de fuentes de verdad

Cuando exista una contradicción, usar este orden:

1. **Código actual en `main`**
2. **Tests y configuración versionada**
3. **Commits / PRs recientes**
4. **Este archivo**
5. **Historial de chats**

Nunca asumir que una afirmación de un chat sigue siendo cierta sin contrastarla con el repositorio.

## Cuándo actualizar este archivo

El bloque **Checkpoint automático** se actualiza solo cuando un PR con la etiqueta `handoff:update` se fusiona a `main`. El resto del documento sigue siendo deliberadamente manual para que riesgos, decisiones, bloqueos y próximos pasos reflejen el estado real del proyecto.

Actualizar manualmente el contenido semántico cuando ocurra cualquiera de estos eventos:

- merge importante;
- cierre de una fase P0/P1/P2;
- cambio de arquitectura;
- cambio relevante de infraestructura;
- modificación de reglas de negocio;
- aparición de un bloqueo conocido;
- cambio del próximo objetivo;
- antes de abandonar un chat de trabajo muy largo.

No hace falta registrar cada commit menor.

## Plantilla de checkpoint

Al actualizar este documento, mantener como mínimo:

```md
## Checkpoint

- Fecha:
- Rama:
- Commit:
- Último hito:

### Completado
- ...

### En progreso
- ...

### Pendiente
- ...

### Bloqueos
- ...

### Riesgos
- ...

### Próximo paso recomendado
1. ...
2. ...
3. ...
```

---

## Checkpoint

- **Fecha:** 2026-09-28
- **Rama:** `main`
- **Commit funcional de referencia:** `7866838171c435eb218ddf6b98cda69b1471fb9c`
- **Último hito:** PR #92 mergeado — POST explícito de empleado contratado hacia Odoo con upsert idempotente, introspección de campos y configuración runtime opcional.

### Completado

- Reclutamiento global entre administradores autorizados (#79).
- Onboarding ASIATI precargado y asignado automáticamente por el sistema (#81/#83), pero editable por administradores sobre módulos/lecciones existentes (#89).
- Agenda de selección interna para llamadas y entrevistas presenciales (#85).
- Ranking solo muestra vacantes con `Number(candidate_count) > 0`; `0`, `null` o campo ausente quedan ocultos. Si todas quedan fuera, no selecciona ninguna ni consulta `/ranking` (#90/#91).
- Etapa `SELECTED` y mapeo Indeed `POSITIVELY_SCREENED` (#85).
- Outbox de empleado Odoo `odoo_employee_syncs` al contratar, idempotente por empleado (#86, Alembic 028).
- Outbox de postulante Odoo `odoo_applicant_syncs` al pasar a `SELECTED`, idempotente por postulación (#87, Alembic 029).
- Vacantes conservan proceso de selección editable y `UPSERT_APPLICANT` v1 incluye candidato, vacante, proceso y referencia al CV canónico (#87).
- POST `/api/odoo/employees/{employee_id}/sync` agregado (#92): consume el outbox de empleado, hace upsert sobre `hr.employee` y persiste estado/ID externo.
- El mapper de empleado usa `fields_get` para escribir solo campos soportados/editables.
- Mapeo inicial: nombre, correo de trabajo, cargo, teléfono privado, tipo Employee cuando esté disponible y relaciones existentes de departamento/puesto.
- Idempotencia: primero `odoo_record_id`; en ausencia, `work_email`. Correos Odoo duplicados detienen el intento.
- No se crean automáticamente departamentos, puestos ni empresas desde aiRecruiter.
- Configuración Odoo opcional ya se propaga a API/worker en deploy; `ODOO_ENABLED` permanece `false` por defecto.
- Cliente `OdooXmlRpcClient` agregado (#88) sobre:
  - `/xmlrpc/2/common` para versión/autenticación;
  - `/xmlrpc/2/object` para operaciones de modelos.
- Configuración no secreta: `ODOO_ENABLED`, `ODOO_BASE_URL`, `ODOO_DATABASE`, `ODOO_USERNAME`, `ODOO_SECRET_ID`, `ODOO_REQUEST_TIMEOUT_SECONDS`.
- API key de Odoo fuera del repositorio, leída desde AWS Secrets Manager.
- HTTPS obligatorio fuera de localhost.
- Timeout Odoo configurable, 15 segundos por defecto.
- Helpers genéricos disponibles: `fields_get`, `search_read`, `create`, `write`, `healthcheck`.
- Errores de transporte sanitizados para no propagar detalles remotos/secretos.
- Tests específicos para cliente XML-RPC, composición de integración, configuración y Secrets Manager.
- PR #88 pasó backend pytest, PostgreSQL smoke, frontend, E2E Chromium y CodeQL.
- No hay PRs abiertos después del merge.

### En progreso

- Mapeo técnico real entre los contratos `UPSERT_APPLICANT` / `UPSERT_EMPLOYEE` y los modelos/campos de Odoo ASIATI.
- Diseño/implementación del consumidor de outbox de postulante; empleado ya tiene POST explícito e idempotente (#92).
- Resolución del CV canónico como adjunto al consumir el outbox.
- Definición de una fuente canónica para teléfono cuando no venga en metadata.
- Cierre paralelo de P2 residuales.
- Prueba funcional del onboarding precargado desde dos perspectivas: admin editor y empleado asignado automáticamente.
- Validación funcional de la edición del Equipo ASIATI: cargo/área, rol y requisito de onboarding desde la vista administrativa (#94).

### Pendiente inmediato

1. Ejecutar prueba funcional del Onboarding ASIATI con un admin: abrir la ruta precargada, editar módulo/lección y reemplazar un video sin crear estructura nueva.
2. Ejecutar prueba como empleado activo: confirmar asignación automática, avance, checklist y evaluación final.
3. Configurar conexión Odoo ASIATI y ejecutar `healthcheck` + prueba controlada del POST de empleado.
4. Validar en la instancia real los campos `name`, `work_email`, `job_title`, `private_phone`, `employee_type`, `department_id` y `job_id`.
5. Implementar consumidor de `odoo_applicant_syncs` con orden: upsert vacante → upsert postulante → adjuntar CV → guardar `odoo_job_id` / `odoo_applicant_id`.
6. Automatizar reintentos/consumo de outboxes después de validar el POST manual.
7. Agregar permisos IAM mínimos para leer `ODOO_SECRET_ID` cuando se habilite la integración en runtime.
8. Mantener `ODOO_ENABLED=false` hasta validar conexión y mapeo contra un entorno seguro.
9. Mantener etapas previas a `SELECTED` exclusivamente en aiRecruiter y Agenda sin sincronización de citas hasta decisión posterior.

### Bloqueos / dependencias externas

- Falta configurar la conexión runtime Odoo ASIATI (base URL, database, username y API key en Secrets Manager) para inspeccionar modelos reales.
- Falta confirmar el modelo/campo destino del CV en Odoo antes de habilitar escrituras.
- La instancia conocida es Odoo 18 Enterprise con Reclutamiento instalado; no asumir nombres/campos custom sin inspección.
- Verificación IAM de alarmas operativas.
- Prueba real controlada del Resume Agent requiere workstation/sesión Indeed autorizada.

### Riesgos

- No activar escrituras Odoo con un mapeo supuesto: primero usar `fields_get`/lecturas contra la instancia real.
- Una API key no debe aparecer en Git, logs, responses ni variables de frontend.
- El worker Odoo debe tener timeout y reintentos; una caída externa no puede bloquear estados locales.
- Persistir los IDs externos solo después de confirmación del upsert para mantener idempotencia.
- Las URLs firmadas de CV expiran; resolver el documento canónico al ejecutar, no guardar URL temporal.
- El teléfono aún no tiene una fuente canónica garantizada para todos los candidatos.

### Próximo paso recomendado

1. Configurar de forma segura la conexión Odoo runtime sin habilitar escrituras automáticas.
2. Ejecutar un diagnóstico de solo lectura: `healthcheck` + `fields_get` de los modelos de Reclutamiento/RRHH presentes.
3. Documentar el mapeo real fuente → destino.
4. Implementar el consumidor de outboxes con reintentos e idempotencia.
5. Probar primero en entorno seguro antes de activar `ODOO_ENABLED` en producción.
