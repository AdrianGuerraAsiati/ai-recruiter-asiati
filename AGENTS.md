# Talent Intelligence — reglas de colaboración para agentes

Estas reglas son instrucciones para asistentes de desarrollo; **no ejecutan agentes por sí solas**.

## Antes de modificar
1. Consultar `docs/development/PARALLEL_WORK.md` y `docs/development/OWNERSHIP.md`.
2. Consultar PR abiertos y cambios recientes en `main`. Identificar conflictos de archivos y contratos antes de escribir.
3. Crear una rama propia desde `main` actualizado: `feat/<dominio>-<objetivo>` o `fix/<dominio>-<objetivo>`. Nunca trabajar directamente en `main`.
4. Definir alcance (rutas que tocarás), contratos afectados y validaciones en la descripción del PR.
5. Si otro PR toca las mismas rutas o contratos, coordinar en ambos PR antes de continuar. No hacer force push sobre trabajo ajeno.

## Durante la implementación
- Respetar instrucciones `AGENTS.md` de cada subdirectorio.
- Reducir cambios transversales; evitar refactors no relacionados.
- No incluir credenciales, tokens, CV reales, datos personales ni secretos en PR o logs.
- Usar cambios de esquema Alembic compatibles con despliegues escalonados. No reescribir migraciones publicadas.
- Nunca cambiar infraestructura AWS o introducir costo adicional sin aprobación expresa.
- No asumir que otros chats leen tu conversación: dejar decisiones en PR e issues.

## Integración
- Ejecutar tests relevantes y verificar CI + seguridad.
- Rebasar o actualizar rama después de cada merge relevante; repetir CI.
- Fusionar PR **de uno en uno**, en orden de dependencias, únicamente con checks verdes.
- Ningún agente debe desplegar a producción de forma independiente.
- Un PR que altera endpoints, tablas, RBAC o eventos debe describir impacto y compatibilidad.

El workflow de solapamiento es asesor: **no es un bloqueo transaccional de archivos**.
