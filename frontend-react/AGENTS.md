# Instrucciones frontend React

- Trabajar en componentes y páginas del dominio asignado.
- Los contratos globales (`src/api/`, `src/context/`, routing, dependencias, estilos globales) son COMPARTIDOS: comunicar cambios a los otros PR.
- Mantener permisos, traducciones, estados de carga, errores y responsividad.
- Los parámetros URL deben preservar filtros y permitir enlaces profundos; utilizar `encodeURIComponent` cuando corresponda.
- Ejecutar `npm run lint`, `npm test` y `npm run build` desde `frontend-react/`.
- No modificar componentes globales para resolver un problema local si puede aislarse en el módulo.
