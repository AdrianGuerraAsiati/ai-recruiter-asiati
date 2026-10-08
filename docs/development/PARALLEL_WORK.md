# Protocolo de desarrollo paralelo en chats

**Objetivo:** cuatro chats de implementación + uno coordinador de integración. Los chats son independientes y no comparten memoria ni bloqueos automáticamente.

## Inicio de cada chat
1. Consultar `main`, PR abiertos y `AGENTS.md` de raíz y dominio.
2. Publicar en PR el objetivo, responsable (chat funcional), ramas, rutas previstas, endpoints/tablas afectados y dependencias.
3. Crear rama independiente actualizada de `main` (un PR por cambio).
4. Consultar la comprobación `PR Coordination` para solapamientos con PR abiertos.

## Reglas al trabajar
- El responsable del dominio modifica sus archivos; cambios compartidos deben anunciarse en ambos PR.
- No reutilizar ramas de otro chat; no usar force push sin necesidad y consentimiento explícito.
- Separar migraciones de código de negocio cuando faciliten revisiones, pero mantener dependencias explícitas.
- Los contratos entre frontend y backend deben ser compatibles de forma transitoria.
- Evitar merges paralelos; después de un merge validar de nuevo los PR afectados.

## Coordinador
- Vigila PR abiertos, conflictos, cambios de esquema, CI y dependencias.
- Define orden de integración; fusiona individualmente solo PR revisados y verdes.
- Si hay solapamiento: comentar en PR, decidir secuencia y rebasar el segundo.
- Revisa despliegue con señales de salud, evitando modificar AWS sin aprobación.

## Formato obligatorio de PR
- Dominio y objetivo
- Archivos/rutas previstas o modificadas
- Contratos compartidos, migraciones, RBAC y compatibilidad
- PR dependientes / con solapamiento
- Pruebas realizadas y riesgos
- Impacto en infraestructura o costo (siempre declarar)

## Prioridad ante choques
1. Integridad de datos y seguridad.
2. Contratos API y migraciones.
3. Funcionalidad productiva y CI.
4. Presentación y estilos.

El aviso automatizado de solapamientos se basa en rutas: es un **indicador de riesgo, no prueba de conflicto de merge**. Revisar manualmente dependencias semánticas.
