# Pruebas psicotécnicas en Talent Intelligence

## Alcance del MVP

La sección **Pruebas psicotécnicas** permite a Talento Humano asignar una prueba laboral objetiva a un candidato mediante un enlace seguro y temporal.

La primera prueba incluida es **Razonamiento y atención**, con 12 preguntas distribuidas en:

- razonamiento lógico;
- razonamiento numérico;
- atención al detalle;
- comprensión verbal.

La prueba **no es clínica**, no diagnostica salud mental, no infiere personalidad y no consulta categorías sensibles. Su resultado se mantiene separado de **Ranking IA** y no descarta ni selecciona candidatos automáticamente.

## Flujo recruiter

1. Abrir **Reclutamiento → Pruebas psicotécnicas**.
2. Seleccionar **Asignar prueba**.
3. Buscar el candidato por nombre o correo.
4. Asociar opcionalmente una vacante.
5. Definir vigencia del enlace.
6. Generar y compartir el enlace.
7. Consultar estado: pendiente, en curso, completada, expirada o cancelada.
8. Revisar resultado general y desglose por dimensión.

Si el enlace se pierde o se considera comprometido, **Nuevo enlace** rota el token e invalida inmediatamente el anterior.

## Flujo candidato

El candidato abre un enlace público con token aleatorio. No necesita una cuenta Talent.

Antes de comenzar se informa explícitamente que:

- la prueba es laboral y objetiva;
- no es una evaluación clínica;
- no evalúa salud mental;
- el resultado es complementario y no determina por sí solo una contratación.

Las respuestas correctas nunca se envían al navegador. La calificación ocurre exclusivamente en backend.

## Seguridad

- En base de datos se almacena únicamente SHA-256(token), nunca el token público.
- Los enlaces expiran.
- Una prueba completada no puede volver a enviarse.
- Un candidato vetado no puede recibir nuevas pruebas.
- Regenerar el enlace invalida el enlace anterior.
- El payload público no expone correo ni resultados internos.
- Los resultados solo están disponibles para roles con psychotechnical.read.

## Evolución prevista

El modelo está versionado (test_key + test_version) para poder agregar posteriormente bancos de preguntas distintos por familia de cargo, manteniendo resultados auditables y sin reescribir pruebas históricas.
