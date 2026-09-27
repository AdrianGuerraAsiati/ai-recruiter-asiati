# Auditoría UI/UX — AI Recruiter ASIATI

## Objetivo

Consolidar una experiencia coherente para Dirección, Administración y Empleados, reducir deuda visual y establecer una base reutilizable para futuras pantallas.

## Hallazgos principales

Antes de esta refactorización la aplicación ya tenía una identidad visual sólida, pero la implementación estaba creciendo de forma fragmentada:

- `index.css` concentraba miles de líneas y múltiples excepciones.
- Existían más de cien usos de `!important` y numerosos colores hardcodeados en estilos heredados.
- Headers, loaders, empty states, métricas y barras de progreso se repetían entre pantallas.
- La navegación principal era plana y usaba símbolos Unicode como iconos.
- Algunas acciones operativas de Candidatos todavía dependían de `alert()`.
- Dirección utilizaba `window.prompt()` para anular movimientos de calificación.
- Abrir una ruta sin permisos redirigía silenciosamente a Inicio.
- Una URL inexistente podía terminar en Login aun con sesión válida.
- Había CSS muerto (`App.css` y `styles.css`) que ya no participaba en el bundle.
- Varias vistas dependían de estilos inline estáticos, dificultando modo oscuro, responsive y consistencia.

## Cambios estructurales

Se creó una capa de UI compartida:

- `components/ui/Icon.jsx`: iconografía SVG consistente sin dependencia externa.
- `components/ui/PageHeader.jsx`: encabezado estándar para páginas.
- `components/ui/StatePanel.jsx`: LoadingState, EmptyState, FeedbackMessage, ProgressBar y MetricCard.
- `context/NoticeContext.jsx`: feedback no bloqueante para acciones rutinarias.
- `ui-system.css`: tokens semánticos, layout, estados, responsive, tablas, modales, avisos y compatibilidad con estilos heredados.

La capa `ui-system.css` se carga al final del árbol de estilos para actuar como contrato transversal mientras el CSS heredado se migra progresivamente.

## Navegación

La barra lateral ahora agrupa funciones por intención:

1. General
2. Reclutamiento
3. Equipo
4. Desarrollo
5. Cuenta
6. Sistema

Los permisos RBAC continúan siendo la fuente de verdad para determinar qué opciones se muestran.

Los iconos Unicode fueron reemplazados por SVG consistentes.

El menú móvil bloquea el scroll de fondo mientras está abierto y mantiene cierre por Escape.

## Estados del sistema

Los estados de carga y ausencia de contenido se normalizaron para evitar cambios abruptos de altura y mensajes inconsistentes.

Los errores recuperables utilizan FeedbackMessage.

Las notificaciones de acciones rutinarias utilizan NoticeContext en lugar de diálogos nativos bloqueantes.

Las rutas protegidas ahora distinguen:

- usuario sin permiso → página “Acceso restringido”;
- ruta inexistente con sesión válida → página “Esta página no existe”;
- usuario sin sesión → Login.

## Pantallas migradas

La nueva capa ya se utiliza en:

- Dashboard;
- Vacantes;
- Postulaciones;
- Candidatos;
- detalle de candidato;
- Ranking IA;
- Empleados;
- Calificación de Dirección;
- Capacitación;
- Mi progreso;
- Mi perfil;
- Integraciones.

## Convenciones para nuevo desarrollo

### Componentes

No crear un header de página manual si `PageHeader` cubre el caso.

No crear loaders o empty states ad hoc. Usar los componentes de `StatePanel.jsx`.

No usar `alert()`, `confirm()` o `prompt()` para flujos normales de producto.

- información breve → NoticeContext;
- confirmación sensible → modal accesible;
- error persistente de página → FeedbackMessage.

### CSS

No agregar nuevas reglas generales a `index.css` salvo mantenimiento del legado.

Los nuevos primitives y overrides transversales viven en `ui-system.css`.

Los estilos propios de una feature deben vivir junto a esa feature o su página.

Evitar:

- `!important`;
- colores hex repetidos cuando exista token;
- estilos inline estáticos;
- tamaños absolutos sin responsive.

Los estilos inline se reservan para valores genuinamente dinámicos, por ejemplo:

- ancho calculado de una barra;
- delay escalonado de una animación.

### Accesibilidad

Toda nueva interacción debe contemplar:

- foco visible;
- labels accesibles;
- botones con `type="button"` cuando no envían formularios;
- `aria-modal` y título asociado en diálogos;
- mensajes críticos con `role="alert"`;
- estados no críticos con `role="status"`;
- `prefers-reduced-motion`.

## Deuda restante deliberada

No se intentó reescribir de una sola vez todo el CSS heredado. El objetivo de esta fase es crear una arquitectura de UI estable y migrar las superficies activas sin introducir una regresión visual masiva.

Las reglas heredadas con `!important` y colores hardcodeados pueden retirarse gradualmente a medida que cada feature sea migrada al sistema semántico.

La regla para trabajo futuro es que la deuda no crezca: toda pantalla o componente nuevo debe usar la capa compartida.
