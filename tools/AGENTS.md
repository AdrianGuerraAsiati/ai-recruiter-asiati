# Instrucciones agentes locales e integraciones

- Los agentes de Indeed y Computrabajo son integraciones de candidatos, no agentes autónomos de programación.
- Mantener adaptadores por proveedor, evitando modificar el núcleo común sin coordinación.
- Nunca guardar credenciales de proveedores en código, logs o documentación.
- Validar pruebas de `tools/indeed_resume_agent/tests` cuando se modifican archivos de ese agente.
- No introducir scraping agresivo ni automatizaciones que evadan controles de acceso.
