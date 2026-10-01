# AI Handoff — Talent Intelligence / aiRecruiterAsiati

> Punto de recuperación operativo. GitHub y AWS son la fuente de verdad; este documento resume el estado validado para continuar desde una sesión nueva.

## Estado del repositorio

- **Repositorio:** `AdrianGuerraAsiati/ai-recruiter-asiati`
- **Rama principal:** `main`
- **Checkpoint manual actual:** `c97338d2370dd894dee03a44b363f61f706acf86`
- **Fecha:** 2026-10-01
- **Último hito:** PR #121 — kiosco Android de Talent ID mergeado en el mismo monorepo de Talent Intelligence.
- **Arquitectura de producto:** Talent ID ya no es un proyecto separado; vive dentro de Talent Intelligence / aiRecruiter y comparte backend, base de datos, usuarios, RBAC e infraestructura AWS.

<!-- AI_HANDOFF_AUTO_START -->
## Checkpoint automático

- **Última actualización automática registrada:** 2026-09-29
- **Merge commit registrado:** `dbc8aba0984d5396396a4531309d56508bfdbea1`
- **PR registrado:** #102 — servir onboarding desde videos privados en S3

> Este bloque es administrado por `.github/workflows/ai-handoff.yml`. El checkpoint manual de arriba es más reciente y debe prevalecer mientras el workflow no regenere este bloque.
<!-- AI_HANDOFF_AUTO_END -->

## Objetivo actual

Cerrar un primer piloto operativo de **Talent ID en recepción** sobre Talent Intelligence:

1. enrolar biometría facial de empleados desde una interfaz administrativa;
2. instalar el APK Android del kiosco en un dispositivo real;
3. ejecutar una prueba E2E controlada de enrolamiento → reconocimiento → check-in/check-out;
4. validar reintentos/idempotencia y rostro no reconocido;
5. después agregar fallback PIN/QR, Face Liveness y modo kiosco administrado;
6. finalmente conectar asistencia con el sistema de puntos/reconocimientos del empleado.

En paralelo, mantener estable reclutamiento, onboarding y la integración Odoo ya existente.

## Estado funcional validado

### Reclutamiento

- Vacantes, candidatos y postulaciones son datos globales para administradores autorizados.
- `owner_sub` se conserva como procedencia/auditoría, no como frontera de acceso.
- Ranking oculta vacantes sin candidatos.
- Existe búsqueda/directorio de candidatos.
- Etapas de selección están alineadas con el proceso trabajado para Odoo.
- Existe Agenda de selección interna para llamadas y entrevistas presenciales.
- La agenda sigue siendo operativa dentro de Talent Intelligence; no debe depender de Odoo.

### Onboarding / Capacitación

- `Onboarding ASIATI` se provisiona automáticamente y no requiere que un administrador cree la estructura desde cero.
- La ruta estándar contiene **7 módulos**.
- Nuevos perfiles activos reciben onboarding automáticamente cuando aplica.
- ADMIN puede editar el contenido existente del curso/módulos/lecciones y reemplazar material, pero el flujo normal no debe exigir crear la ruta corporativa.
- Los videos corporativos se sirven desde infraestructura privada en AWS/S3.
- El progreso y resultados son visibles para administración.
- Equipo ASIATI permite editar cargo/área, rol y requisito de onboarding según permisos.

### Odoo

- Odoo se mantiene como sistema downstream/registro; Talent Intelligence sigue siendo el acceso principal de Talento Humano y empleados.
- Existe diagnóstico read-only de Odoo (#116).
- Existe panel administrativo de integración Odoo (#117).
- Al contratar, Talent Intelligence puede crear o actualizar el empleado en Odoo (#118) con entrega best-effort: una caída de Odoo no debe perder el estado local de contratación.
- Persisten contratos/outboxes para sincronización.
- La sincronización completa de postulante/vacante/CV todavía debe considerarse trabajo separado del alta de empleado y requiere validación contra los campos reales de Odoo.

## Talent ID — estado actual

### Backend base — completado (#119)

Talent ID está integrado dentro del backend existente y reutiliza:

- `user_profiles` / identidad de empleados;
- RBAC de Talent Intelligence;
- base de datos principal;
- runtime AWS existente;
- despliegue actual en Lightsail.

Incluye dominio de asistencia, sitios, dispositivos/kioscos, configuración de elegibilidad y eventos de marcación.

### Biometría facial — completado y desplegado (#120)

PR #120 fue mergeado como `921bc076f5fbd44d3ba5c880efa5c5919b32ab67` y su pipeline de producción terminó correctamente.

Backend disponible:

- `POST /api/talent-id/employees/{employee_id}/biometrics/enroll`
- `POST /v1/kiosk/recognize`

Reglas actuales:

- JPEG/PNG;
- máximo 5 MB;
- umbral de reconocimiento configurable, default 98%;
- asociación configurable, default 90%;
- múltiples rostros por empleado;
- kiosco autenticado con `X-Device-Id` + `X-Device-Secret`;
- `Idempotency-Key` evita duplicar marcaciones y evita repetir reconocimiento al reintentar;
- las imágenes recibidas se procesan en memoria y no se guardan como archivos por Talent Intelligence.

### AWS Rekognition — preparado

Cuenta y región usadas por este proyecto:

- **AWS Account:** `890876258895`
- **Región:** `us-east-2`
- **Colección:** `talent-intelligence-employees`
- **ARN:** `arn:aws:rekognition:us-east-2:890876258895:collection/talent-intelligence-employees`
- **Face model observado al crear la colección:** `7.0`
- **Runtime role:** `AiRecruiterBedrockRuntimeRole`
- **Runtime:** Lightsail + IAM Roles Anywhere.

La colección fue creada el 2026-10-01. Inició con 0 usuarios / 0 rostros.

Permisos mínimos validados mediante IAM simulation sobre el runtime:

- `rekognition:CreateUser`
- `rekognition:IndexFaces`
- `rekognition:AssociateFaces`
- `rekognition:DeleteFaces`
- `rekognition:SearchUsersByImage`

Todos resultaron `allowed` para la colección específica.

**Deuda de infraestructura:** el permiso se aplicó al inline policy del runtime para habilitar el piloto. El archivo `infra/talent-id-rekognition-runtime-policy.json` está versionado, pero el deploy todavía no gestiona automáticamente ese statement. Convertirlo en IaC reproducible antes de considerar la fase cerrada.

### Android kiosk — completado en código (#121)

PR #121 fue mergeado como `c97338d2370dd894dee03a44b363f61f706acf86`.

Stack:

- Kotlin;
- Jetpack Compose;
- CameraX;
- Android Keystore;
- OkHttp;
- Android 7.0 / API 24+ como mínimo documentado.

Flujo:

1. ADMIN provisiona un kiosco desde backend.
2. Backend entrega `device_id` + `device_secret` una sola vez.
3. El tablet guarda el secreto cifrado con Android Keystore / AES-GCM.
4. Valida contexto contra `GET /v1/kiosk/context`.
5. Captura JPEG temporal con cámara frontal.
6. Envía `POST /v1/kiosk/recognize`.
7. Registra `CHECK_IN` o `CHECK_OUT`.
8. Reintentos de red reutilizan la misma `Idempotency-Key`.
9. La imagen temporal se elimina después de éxito o error final.

No se incluyen credenciales IAM/AWS dentro del APK.

### Android CI / APK

Workflow: `.github/workflows/android-ci.yml`

Valida:

- unit tests;
- ensamblado debug APK;
- publicación del APK como GitHub Actions artifact.

El build usa:

- `vars.PUBLIC_BASE_URL` cuando está definido;
- fallback de producción: `https://talent.asiati.com.co`.

Artifact:

- nombre `talent-id-kiosk-debug-<commit-sha>`;
- archivo `android/app/build/outputs/apk/debug/app-debug.apk`;
- retención: 14 días.

El PR #121 pasó:

- Android unit tests;
- Assemble debug APK;
- Upload debug APK;
- CI general;
- E2E Chromium;
- PostgreSQL smoke;
- CodeQL.

## Producción

### Backend / frontend

- Instancia: `ai-recruiter-micro-prod`
- Despliegue: GitHub Actions → ECR → Lightsail vía SSH.
- API y worker consumen AWS mediante IAM Roles Anywhere.
- El pipeline de #120 terminó `success` y verificó el deploy después del merge de biometría.

### Regla importante

Un merge o build verde no sustituye la prueba funcional real. Para Talent ID falta todavía validar con un dispositivo y una persona enrolada.

## Próximo bloque de trabajo recomendado

### P0 — Piloto Talent ID

1. **Construir UI administrativa de enrolamiento biométrico**
   - ubicarla dentro de Equipo ASIATI / perfil de empleado;
   - mostrar estado: no enrolado / enrolado / cantidad de rostros / activo;
   - permitir captura o upload de fotografía;
   - permitir agregar fotografías adicionales;
   - definir desactivación/eliminación de biometría.

2. **Prueba controlada con un empleado**
   - habilitar asistencia;
   - enrolar 2–3 fotografías con consentimiento;
   - reconocer desde Android;
   - CHECK_IN;
   - retry con misma key;
   - CHECK_OUT;
   - probar rostro desconocido.

3. **Instalar APK en tablet/teléfono de recepción**
   - descargar artifact de GitHub Actions;
   - provisionar dispositivo;
   - validar cámara, permisos, red, orientación y experiencia de recepción.

4. **Hardening del kiosco**
   - PIN/QR fallback;
   - Face Liveness;
   - lock-task / managed-device mode;
   - observabilidad y mensajes de error offline.

5. **Puntos**
   - definir reglas de puntos por puntualidad/asistencia;
   - no acoplar el cálculo de puntos al reconocimiento biométrico;
   - generar puntos a partir del evento de asistencia confirmado.

### P1 — Biometría / privacidad

Antes de ampliar el piloto:

- definir consentimiento y finalidad del tratamiento biométrico;
- definir proceso de baja/desvinculación y borrado de rostros del proveedor;
- definir quién puede enrolar/desactivar biometría;
- auditar acciones administrativas;
- documentar qué se guarda localmente y qué se guarda en Rekognition;
- no persistir fotografías originales salvo decisión explícita y justificada.

### P2 — Infraestructura / mantenimiento

- convertir permisos Rekognition del runtime en IaC aplicado automáticamente;
- evitar deploy de API/frontend cuando el cambio sea únicamente `android/**`;
- proteger `main` y exigir checks si todavía no está protegido;
- continuar modularización residual de frontend/Resume Agent;
- mantener regresiones de deduplicación candidato+vacante;
- validar IAM de alarmas operativas antes de activarlas por defecto.

## Bloqueos / dependencias externas

Para completar la prueba E2E biométrica hace falta:

- un empleado de prueba activo;
- consentimiento para enrolamiento;
- fotografías/capturas reales;
- un dispositivo Android con cámara frontal para la prueba de recepción.

No inventar ni reutilizar imágenes personales sin autorización.

## Riesgos técnicos

- Una caída de Rekognition no debe generar una marcación falsa.
- No bajar el threshold de reconocimiento para “hacer pasar” pruebas.
- La idempotencia del evento debe mantenerse independiente de reintentos de red.
- Un usuario deshabilitado/no elegible no debe poder marcar asistencia aunque conserve rostros en Rekognition.
- La baja de un empleado debe contemplar limpieza/desasociación biométrica.
- No exponer `device_secret`, credenciales AWS ni secretos de runtime en frontend, logs o APK.
- No depender de URLs temporales o archivos de fotos persistentes para reconocer.

## Protocolo para una sesión nueva

1. Leer este archivo.
2. Verificar `main`, commits posteriores y PRs abiertos.
3. Revisar Actions del último merge.
4. Si la tarea toca AWS, comprobar estado real antes de crear recursos.
5. Trabajar por PR pequeño y verificable.
6. No mergear con checks rojos.
7. Actualizar este handoff al cerrar un hito importante.

## Fuente de verdad

Cuando haya contradicción:

1. código actual en `main`;
2. tests/workflows;
3. AWS real;
4. PRs/commits;
5. este handoff;
6. historial de chat.
