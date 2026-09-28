# AI Handoff — aiRecruiterAsiati

> Punto de recuperación operativo para continuar el proyecto desde un chat, agente o sesión nueva sin depender del historial de conversación.
>
> **Regla:** este archivo debe actualizarse después de un merge importante, un cambio de arquitectura o al cerrar una sesión larga de trabajo.

## Estado del repositorio

- **Repositorio:** `AdrianGuerraAsiati/ai-recruiter-asiati`
- **Rama principal:** `main`
- **Último checkpoint conocido:** `f0dafce976bc437c24bff08473602d2fbccb7d43`
- **Fecha del checkpoint:** 2026-09-27
- **Commit:** `refactor: extraer evaluación de empleado de Training (#48)`

Antes de continuar trabajo nuevo, comprobar que `main` sigue apuntando a este commit o a uno posterior.

<!-- AI_HANDOFF_AUTO_START -->
## Checkpoint automático

- **Última actualización automática:** 2026-09-27
- **Merge commit:** `dca0ccdd56a38d53460a9bcb1de347c099c8c3ce`
- **PR:** [#43 — chore(deps-dev): bump vitest from 3.2.7 to 5.0.1 in /frontend-react](https://github.com/AdrianGuerraAsiati/ai-recruiter-asiati/pull/43)
- **Origen:** merge a `main` con etiqueta `handoff:update`

> Este bloque es administrado por `.github/workflows/ai-handoff.yml`. No editarlo manualmente.
<!-- AI_HANDOFF_AUTO_END -->

## Objetivo actual

Mantener aiRecruiterAsiati como una plataforma de reclutamiento estable, modular y operable, con foco inmediato en:

1. cerrar deuda técnica P2;
2. mantener UI/UX consistente y accesible;
3. fortalecer pruebas y observabilidad;
4. evitar regresiones en Resume Agent, ingestión de candidatos, vacantes y onboarding;
5. mantener infraestructura y operaciones verificables antes de habilitar cambios sensibles.

## Trabajo reciente completado

### Arquitectura y calidad

- Modularización de Training y Resume Agent.
- Separación de modelos y responsabilidades.
- Validaciones locales relacionadas con Cognito.
- Hardening general de código e infraestructura.
- Mejoras de RBAC, readiness, rollback, backups, CI y seguridad web.
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

### Onboarding

- Seguimiento detallado del progreso de onboarding para ADMIN.
- Filtro de empleados por estado de onboarding.

### Operación e infraestructura

- Request correlation y logging estructurado.
- Alarmas de cola/DLQ versionadas.
- Alarmas operativas mantenidas como **opt-in** hasta verificar IAM.
- Diagnóstico automático de fallos del stack `candidate-import`.
- Backup/restore host-side corregido para Lightsail.
- Disaster recovery off-host opcional.

## Estado funcional que no debe romperse

### Candidatos y vacantes

- Un mismo candidato puede existir en vacantes distintas.
- Si el mismo candidato aparece varias veces para **la misma vacante**, debe prevalecer la postulación más reciente.
- Esa deduplicación no debe bloquear al candidato ni eliminar sus postulaciones a otras vacantes.

### Descripciones de vacantes

Deben coexistir dos fuentes independientes:

- descripción proveniente de Indeed;
- descripción generada/mejorada por IA.

La ingestión no debe sobrescribir automáticamente una descripción generada por IA. La UI debe permitir seleccionar cuál descripción utilizar.

### Resume Agent

El Resume Agent debe poder revisar vacantes y candidatos existentes y sincronizar el estado sin crear duplicados incorrectos ni dejar jobs permanentemente bloqueados.

## Riesgos / puntos a verificar

- IAM de las alarmas operativas todavía debe verificarse antes de habilitarlas por defecto.
- Cualquier cambio en Resume Agent debe probar idempotencia y recuperación ante fallos.
- Ingestiones deben probar deduplicación por combinación candidato + vacante.
- Cambios de UI deben conservar accesibilidad, responsive y feedback accionable.
- No asumir que un deploy exitoso implica funcionamiento correcto: revisar health/readiness y journey crítico.

## Prioridad de trabajo

### TODO actual

#### P2 · Gobernanza y mantenimiento
- [ ] Proteger `main` y exigir checks de CI/CodeQL antes de merge. Actualmente la rama no está protegida.
- [x] Separar upgrades mayores de Dependabot: minor/patch agrupados, majors individuales.
- [x] Desacoplar el contrato de CI de una versión fija de `actions/upload-artifact`.
- [x] Reducir ejecuciones innecesarias del workflow de AI handoff.
- [x] Evitar deploys de producción para cambios solo documentales, handoff, Dependabot o tests.
- [x] Omitir CodeQL en cambios puramente documentales/configuración de handoff.
- [x] PR #41 frontend minor/patch validado con CI + CodeQL y mergeado.
- [ ] Revisar PR #42: jsdom 26 → 30 como major independiente (Dependabot ya lo rebasó sobre el nuevo `main`).
- [ ] Revisar PR #43: Vitest 3 → 5 como major independiente; revalidar después del rebase sobre `main`.
- [ ] Revisar PR #44 Python minor/patch y los majors separados #45 (`websockets`) y #46 (`rpds-py`).
- [ ] Revisar el PR de GitHub Actions cuando Dependabot lo regenere con la nueva política.
- [ ] Confirmar CI verde en `main` después de los cambios actuales.

#### P2 · Modularización residual
- [~] Reducir responsabilidades de `frontend-react/src/pages/Training.jsx`: 1904 → ~1686 líneas; modales y quiz de empleado ya extraídos. Pendiente editor/admin + journey del empleado.
- [ ] Reducir responsabilidades de `tools/indeed_resume_agent/browser.py` (~74 KB).
- [ ] Modularizar `frontend-react/src/pages/Jobs.jsx` (~58 KB).
- [ ] Dividir `app/domains/training/asiati_preset.py` (~58 KB) en datos/configuración y builder.
- [ ] Reducir `frontend-react/src/pages/RankingView.jsx` (~51 KB).
- [ ] Revisar si `tools/indeed_resume_agent/ui.py` y `ui_v2.py` son legacy sin referencias; eliminarlos solo después de verificar imports, packaging y tests.

#### P2 · Regresiones críticas
- [ ] Mantener pruebas explícitas de deduplicación por candidato + vacante conservando la postulación más reciente.
- [ ] Mantener pruebas de idempotencia y recuperación del Resume Agent.
- [ ] Mantener pruebas de descripción Indeed vs descripción IA sin sobrescritura.
- [ ] Ejecutar journey E2E, accesibilidad y responsive en refactors de frontend.

#### Pendientes operativos externos
- [ ] Verificar IAM antes de activar las alarmas operativas por defecto.
- [ ] Ejecutar el corte controlado del Resume Agent con una aplicación real, luego lote de 5–10 y finalmente backlog.

### P2 — continuar

La fase activa es continuar cerrando P2 restantes detectados durante la auditoría senior.

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

- **Fecha:** 2026-09-27
- **Rama:** `main`
- **Commit:** `e27b4e2c50c3ebc4ef9934d947a7bd4fa4344b9d`
- **Último hito:** saneamiento del flujo de mantenimiento/CI y merge validado de dependencias frontend minor/patch.

### Completado

- Auditoría y refactor UI/UX.
- Motion y errores accionables.
- Seguimiento de onboarding para ADMIN.
- Hardening de código e infraestructura.
- Observabilidad y DR.
- Modularización inicial de Training y Resume Agent.
- Training: modales de preview/crear curso extraídos (#47).
- Training: evaluación final del empleado extraída (#48).
- E2E Chromium + smoke de accesibilidad y responsive.
- `docs/AI_HANDOFF.md` persistente y workflow automático de checkpoint.
- Dependabot configurado para agrupar solo minor/patch y separar majors.
- Test contractual del Resume Agent desacoplado de `upload-artifact@v4`.
- Workflow del handoff reducido a eventos realmente necesarios.
- Deploy de producción filtrado para no ejecutarse por documentación/configuración/test-only.
- CodeQL filtrado para no ejecutarse por cambios puramente documentales.

### En progreso

- Validación del nuevo conjunto de PRs de Dependabot; #41 ya está mergeado.
- Confirmación de CI de `main`.
- Continuación de modularización de Training; siguiente candidato: editor/admin o journey del empleado.

### Pendiente inmediato

1. Confirmar la validación post-merge de `main` para #41.
2. Revisar #42 y #43 por separado.
3. Revisar #44, #45 y #46 con sus checks.
4. Extraer primero los modales de `Training.jsx` como refactor de bajo riesgo.
5. Proteger `main` con checks obligatorios cuando haya acceso a la configuración administrativa correspondiente.

### Bloqueos / dependencias externas

- Verificación IAM de alarmas operativas.
- Prueba real controlada del Resume Agent requiere workstation/sesión Indeed autorizada.
- La protección de rama requiere acceso de administración de configuración de GitHub; no debe simularse solo con documentación.

### Riesgos

- Los majors de frontend deben tratarse de forma independiente para aislar regresiones.
- Los upgrades Python con cambios mayores (por ejemplo ORM/runtime) no deben agruparse con parches rutinarios.
- Los archivos grandes restantes concentran demasiado estado y lógica y elevan el riesgo de regresión.
- No eliminar UIs legacy del Resume Agent hasta demostrar ausencia de referencias en runtime, build y tests.

### Próximo paso recomendado

1. Cerrar la ronda de dependencias con CI verde.
2. Continuar Training con un tercer corte pequeño: editor/admin o journey.
3. Ejecutar tests unitarios + E2E en cada extracción.
4. Mantener PRs pequeños con `handoff:update`.
