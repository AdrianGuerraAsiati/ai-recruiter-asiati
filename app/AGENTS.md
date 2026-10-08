# Instrucciones backend FastAPI

- Responsable: contratos API, dominios `app/domains/`, persistencia, auth, evaluaciones.
- Mantener router/service/repository separados. Respetar permisos `require_permission` y aislamiento de datos.
- Los cambios de `app/models.py`, `app/crud.py`, `app/bootstrap.py`, `app/deps.py` y `alembic/` son COMPARTIDOS: declarar coordinación previa en PR.
- Evitar calls LLM en endpoints de métricas; preferir agregación persistida.
- Escribir pruebas en `app/tests/` para rutas nuevas o lógica de negocio.
- Ejecutar `python -m pytest app/tests/ -v` y validar esquema/migraciones cuando aplique.
- No cambiar `DATABASE_URL`, permisos AWS, Secrets Manager o capacidades facturables sin autorización.
