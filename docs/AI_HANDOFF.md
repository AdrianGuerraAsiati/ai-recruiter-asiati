# AI Handoff — aiRecruiterAsiati

> Punto de recuperación operativo para continuar el proyecto desde un chat, agente o sesión nueva sin depender del historial de conversación.
>
> **Regla:** este archivo debe actualizarse después de un merge importante, un cambio de arquitectura o al cerrar una sesión larga de trabajo.

## Estado del repositorio

- **Repositorio:** `AdrianGuerraAsiati/ai-recruiter-asiati`
- **Rama principal:** `main`
- **Último checkpoint conocido:** `2110be855bd44ec6235403d76ad1f99533314093`
- **Fecha del checkpoint:** 2026-09-28
- **Commit:** `feat: agregar agenda de selección (#85)`

Antes de continuar trabajo nuevo, comprobar que `main` sigue apuntando a este commit o a uno posterior.

<!-- AI_HANDOFF_AUTO_START -->
## Checkpoint automático

- **Última actualización automática:** 2026-09-28
- **Merge commit:** `178a2a111c73bbfbc9d1433ee8a5046309c45f7d`
- **PR:** [#87 — feat: preparar postulantes seleccionados para Odoo](https://github.com/AdrianGuerraAsiati/ai-recruiter-asiati/pull/87)
- **Origen:** merge a `main` con etiqueta `handoff:update`

> Este bloque es administrado por `.github/workflows/ai-handoff.yml`. No editarlo manualmente.
<!-- AI_HANDOFF_AUTO_END -->

## Objetivo actual

Mantener aiRecruiterAsiati como una plataforma de reclutamiento estable, modular y operable, con foco inmediato en:

1. consolidar el flujo de selección desde candidato/postulación hasta agenda, contratación y alta posterior en Odoo;
2. definir e implementar el contrato de integración con Odoo sin replicar indiscriminadamente vacantes ni candidatos que todavía están en etapas tempranas;
3. mantener la agenda de selección como herramienta operativa interna de Talento Humano para llamadas telefónicas y entrevistas presenciales;
4. cerrar deuda técnica P2 sin romper reclutamiento, Resume Agent, onboarding ni los flujos críticos ya estabilizados;
5. fortalecer pruebas, observabilidad, UI/UX e infraestructura antes de habilitar cambios sensibles en producción.

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
- **Commit funcional de referencia:** `2110be855bd44ec6235403d76ad1f99533314093`
- **Último hito:** PR #85 mergeado — Agenda de selección interna para llamadas telefónicas y entrevistas presenciales, con etapa `SELECTED`, persistencia, migración 027 y cobertura de CI/CodeQL.

### Completado

- Reclutamiento global entre administradores autorizados (#79): vacantes, candidatos, postulaciones, ranking, importaciones y contratación ya no están aislados por creador.
- `owner_sub` permanece como procedencia/auditoría, no como frontera de acceso para datos de reclutamiento.
- Onboarding ASIATI administrado por el sistema (#81), con contenido corporativo versionado y protegido de autoría manual.
- Asignación automática e idempotente de Onboarding ASIATI para perfiles activos que lo requieren (#83); ADMIN/SUPER_ADMIN supervisan progreso y resultados, no asignan rutas.
- Agenda de selección (#85) integrada al reclutador.
- Nueva etapa `SELECTED` de postulaciones y mapeo a Indeed `POSITIVELY_SCREENED`.
- Citas `PHONE_CALL` y `ONSITE_INTERVIEW` con estados `SCHEDULED`, `COMPLETED` y `CANCELED`.
- Vista mensual, próximas citas, creación, edición, cancelación y marcado como realizada.
- Elegibilidad de agenda limitada a postulaciones `SELECTED`, `INTERVIEW`, `OFFER` y `HIRED`.
- Dominio backend `recruitment_calendar`, rutas API, modelo persistente y migración Alembic `027`.
- PR #85 validado con `CI — Tests & Build` y `Security — CodeQL` en `success`.
- Modularización previa de Training, Resume Agent y Jobs se conserva como base técnica.
- E2E Chromium, smoke de accesibilidad/responsive, observabilidad, backups/DR y hardening de infraestructura continúan vigentes.

### En progreso

- Diseño del siguiente tramo funcional: **selección → contratación → alta/sincronización con Odoo**.
- Definición del contrato de integración para que Odoo reciba únicamente los candidatos que alcancen la etapa de negocio acordada, evitando duplicar todo el pipeline de reclutamiento.
- Mapeo de los datos de contratación requeridos por Odoo y definición del disparador exacto de sincronización.
- Cierre paralelo de P2 residuales en `Jobs.jsx`, `browser.py`, `asiati_preset.py` y `RankingView.jsx`.

### Pendiente inmediato

1. Revisar el flujo/modelo actual de contratación y los campos que ya captura aiRecruiter.
2. Formalizar el payload aiRecruiter → Odoo a partir de los datos de contratación requeridos por la empresa.
3. Definir cuándo se crea/sincroniza el registro en Odoo: no enviar candidatos de etapas tempranas.
4. Diseñar idempotencia, estado de sincronización, reintentos, auditoría y recuperación ante indisponibilidad de Odoo.
5. Mantener la Agenda como sistema interno de llamadas/entrevistas hasta decidir expresamente si esas citas también deben sincronizarse.
6. Continuar P2 técnico mediante cambios pequeños y verificables sin mezclarlo con la primera integración Odoo.

### Bloqueos / dependencias externas

- Falta cerrar el contrato funcional/técnico exacto de campos y disparador de alta en Odoo.
- Verificación IAM de alarmas operativas.
- Prueba real controlada del Resume Agent requiere workstation/sesión Indeed autorizada.
- La API de protección de `main` no es accesible actualmente desde la integración GitHub conectada; no asumir protección solo porque la cuenta tenga permisos administrativos generales.

### Riesgos

- Enviar candidatos demasiado pronto a Odoo llenaría el ERP con registros que todavía pertenecen únicamente al proceso de reclutamiento.
- Una sincronización sin clave idempotente puede duplicar empleados/contactos ante reintentos o fallos parciales.
- La futura integración con Odoo no debe bloquear ni revertir el estado local de contratación/onboarding por una caída externa.
- Los archivos grandes restantes concentran estado y lógica; mantener refactors separados de cambios funcionales de integración.
- No eliminar UIs legacy del Resume Agent hasta demostrar ausencia de referencias en runtime, build y tests.

### Próximo paso recomendado

1. Inspeccionar el modelo/endpoint actual de contratación y enumerar los campos ya disponibles al pasar una postulación a contratación.
2. Contrastar esos campos con los requeridos por Odoo y documentar el mapeo fuente → destino.
3. Implementar primero el contrato y la persistencia de estado de sincronización/idempotencia; después conectar la llamada real a Odoo.
4. Mantener llamadas e entrevistas en la Agenda interna en esta fase.
5. Continuar posteriormente con P2 residual (`Jobs.jsx`, `asiati_preset.py`, `RankingView.jsx` y Resume Agent) en PRs separados.
