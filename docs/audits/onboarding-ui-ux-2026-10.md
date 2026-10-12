# Auditoría UX de onboarding — Talent Intelligence

Fecha: 2026-10-12
Alcance: interfaz del empleado en `/training`, sin cambios a API, cursos, roles ni reglas de seguimiento.

## Hallazgos

| Hallazgo | Impacto | Acción implementada |
| --- | --- | --- |
| Encabezado del curso, tarjeta de progreso y sesión recomendada repetían título/avance | El video aparece demasiado abajo | Hero compacto con progreso, actividades y tiempo en el mismo bloque |
| Siete módulos forzados en una cuadrícula de siete columnas | Títulos truncados, objetivos táctiles pequeños | Rail horizontal con tarjetas legibles, botones anterior/siguiente y snap |
| Lista de lecciones ocupa demasiado ancho del reproductor | Los videos horizontales se ven pequeños | Layout 27% / 73%, modo «Ampliar contenido» y reproductor fluido |
| Lecciones en módulos con muchos videos requieren exceso de scroll | Pierde continuidad la inducción | Panel por módulo con acceso directo, scroll al contenido seleccionado y controles previos |
| Variaciones móvil/escritorio (pestañas, videos verticales y checklist) | El ancho y los controles se apilan de forma irregular | Breakpoints 1100/820/620/420, sin columnas forzadas en móvil |
| Falta de feedback visible sobre progreso global | Difícil saber cuánto queda | Resumen «n de n actividades», porcentaje y siguiente paso destacado |
| Foco teclado en navegación poco distinguible | Menor accesibilidad | Foco visible para pestañas, botones de rail y modo concentración |

## Criterios de aceptación
1. Empleado con una sola ruta: vista aprovecha ancho y prioriza video/lección.
2. Módulos largos: el rail se desplaza y permite seleccionar cualquier módulo.
3. Módulo 3 «Conoce al equipo»: seleccionar persona cambia el video sin acción adicional.
4. Módulos 4/6: el video vertical conserva proporción y no desborda contenedor.
5. «Ampliar contenido» oculta solo la lista lateral, **sin** borrar estado ni bloquear los controles de reproducción.
6. Seguir permitiendo marcar artículos y checklist según reglas actuales; video directo completa automáticamente al 80% observado.
7. La evaluación final conserva sus restricciones (todas las lecciones obligatorias completas).
8. Desktop y móvil: sin scroll horizontal del documento; el desplazamiento horizontal queda dentro del rail.

## Validación
- `TrainingEmployeeJourney.test.jsx`: modo amplio y controles de módulo.
- `Training.test.jsx`: sesiones recomendadas, video retrato, equipo, checklist y avance.
- CI: lint, build, Vitest, E2E Chromium, pruebas backend, PostgreSQL y CodeQL.
- Prueba visual autenticada en producción pendiente de validación manual: 1440 × 900, 1024 × 768, 390 × 844 y 360 × 800; probar estados en curso y completado.

## Riesgos / pendientes fuera de alcance
- Videos externos incrustados desde Google Drive no suministran a Talent telemetría confiable de reproducción; deben migrarse a almacenamiento/video directo compatible si deben completar automáticamente al 80%.
- El editor administrativo de cursos no se rediseñó en este PR para no ampliar riesgos de regresión.
- No se añaden librerías ni costos AWS.
