# Pruebas psicotécnicas en Talent Intelligence

## Fuente funcional

La sección se construyó a partir del paquete interno **4. PRUEBAS PSICOTECNICAS** suministrado para ASIATI. El catálogo digital conserva la estructura funcional de cuatro instrumentos:

- **Sentido común organizacional** — GTH-F-016, versión 00, fecha 2025-06-05.
- **Temperamento laboral** — GTH-F-017, versión 00, fecha 2025-06-05.
- **VALANTI** — cuestionario y hoja de resultados entregados para ASIATI.
- **Atención al detalle** — versión 00, fecha de emisión 2025-05-27.

Los resultados permanecen separados de Ranking IA y no descartan, seleccionan ni recomiendan candidatos automáticamente.

## Sentido común — GTH-F-016

Se digitalizaron las 10 situaciones y la clave de respuestas del documento de análisis.

Interpretación registrada en el archivo fuente:

- 9–10 respuestas correctas: excelente criterio organizacional y responsabilidad.
- 7–8: buen criterio; acompañamiento estratégico ocasional.
- 5–6: criterio básico; supervisión frecuente.
- 0–4: resultado bajo en criterio organizacional.

Talent muestra la banda como información descriptiva para Talento Humano.

## Temperamento — GTH-F-017

Se digitalizaron las 30 preguntas y el sistema de conteo A/B/C/D:

- A: Colérico — liderazgo, decisión, competitividad.
- B: Flemático — adaptabilidad, cooperación, estabilidad.
- C: Melancólico — análisis, precisión, planificación.
- D: Sanguíneo — expresividad, carisma, empatía.

La plataforma muestra distribución y perfil predominante. No utiliza estas categorías para inferir automáticamente idoneidad para un cargo.

## VALANTI

Se digitalizaron los 30 pares de frases y las cuatro distribuciones permitidas:

- 3-0
- 0-3
- 2-1
- 1-2

Cada par suma tres puntos.

La calificación reproduce las fórmulas de la hoja **RESULTADO - PRUEBA VALANTI.xlsx** para las cinco dimensiones:

- Verdad
- Rectitud
- Paz
- Amor
- No violencia

Se conservan las medias, desviaciones estándar, bandas de interpretación y la referencia institucional incluida en el archivo de resultados. La referencia se presenta como contexto, no como puntaje de contratación.

## Atención al detalle

Se conserva la lógica de tres tareas del formato original:

1. Alfanumérico.
2. Letras.
3. Figuras.

La calificación digital usa la misma estructura de la hoja de resultados:

- eficiencia = ítems respondidos / total;
- eficacia = ítems correctos / total;
- resultado por tarea = promedio entre eficiencia y eficacia;
- calificación final = promedio de las tres tareas.

Bandas del archivo fuente:

- 85% o más: nivel alto.
- 75% a 84,99%: nivel medio.
- menos de 75%: nivel bajo.

La parte de figuras se adaptó a estímulos legibles en pantalla. Por esa razón el sistema la identifica explícitamente como **versión digital** y no asume equivalencia histórica con resultados de la hoja impresa sin validación interna.

## Flujo de Talento Humano

1. Abrir **Reclutamiento → Pruebas psicotécnicas**.
2. Elegir uno de los cuatro instrumentos.
3. Seleccionar candidato.
4. Asociar opcionalmente una vacante.
5. Definir vigencia del enlace.
6. Generar y compartir el enlace.
7. Consultar estado: pendiente, en curso, completada, expirada o cancelada.
8. Revisar el resultado propio de cada instrumento.

Un candidato puede tener pruebas distintas activas al mismo tiempo, pero no dos instancias activas del mismo instrumento.

## Flujo candidato

El candidato abre un enlace público con token aleatorio y no necesita una cuenta Talent.

Antes de comenzar se informa que la evaluación es complementaria y que no determina por sí sola una contratación.

En Atención al Detalle se muestra un temporizador. Al llegar a 00:00 las respuestas quedan bloqueadas y la eficiencia refleja cuántos ítems alcanzó a responder.

## Seguridad

- Se almacena únicamente SHA-256(token), nunca el token público en claro.
- Los enlaces expiran.
- Una prueba completada no puede volver a enviarse.
- Un candidato vetado no puede recibir nuevas pruebas.
- **Nuevo enlace** rota el token e invalida inmediatamente el anterior.
- Las claves correctas no se envían al navegador.
- El payload público no expone correo ni resultados internos.
- Los resultados requieren permiso `psychotechnical.read`.
- La creación y administración requiere `psychotechnical.manage`.

## Versionado

Cada asignación conserva `test_key` y `test_version`, permitiendo cambiar un instrumento en el futuro sin reescribir resultados históricos.
