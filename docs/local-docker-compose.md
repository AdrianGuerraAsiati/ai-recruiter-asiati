# Docker Compose local (solo desarrollo)

Este entorno es independiente del despliegue de producción de Lightsail. **No ejecutar `docker compose up` en la instancia productiva**: la producción usa `scripts/deploy-*.sh`, su PostgreSQL existente, AWS Secrets Manager y sus propios contenedores.

## Requisitos

- Docker Engine / Docker Desktop con el plugin `docker compose`.
- Puertos locales `8080` (o `WEB_PORT`) libres.
- Para probar reclutamiento/IA real se requieren credenciales de desarrollo y configuración explícita; esta pila **no** usa credenciales AWS/Odoo reales ni arranca un worker de importaciones.

## Levantar (desde la raíz del repositorio)

```bash
docker compose config --quiet
docker compose up --build -d
docker compose ps
curl -i http://127.0.0.1:8080/api/live
curl -i http://127.0.0.1:8080/api/ready
```

Frontend: `http://127.0.0.1:8080`. Si el 8080 está ocupado: `WEB_PORT=8081 docker compose up --build -d`.

El servicio `db` crea un PostgreSQL 16 local con credenciales de desarrollo definidas en Compose; **nunca reutilizarlas en producción**. `migrate` ejecuta Alembic `upgrade head` una vez que Postgres está saludable. Solo después arranca la API, cuyo healthcheck valida `/api/ready` en el puerto **80**. Nginx alcanza la API por el nombre interno `ai-recruiter-api:80`.

Esta configuración intencionalmente no publica puertos de la API ni PostgreSQL, no abre 443 (no se suministra certificado TLS) y limita el acceso web al loopback `127.0.0.1`. Se dejan deshabilitadas Gmail, Indeed, Odoo y el registro público. No modificar esa configuración para compartir la pila en Internet.

## Diagnóstico

```bash
docker compose ps
docker compose logs --tail=100 db migrate ai-recruiter-api web
docker compose exec ai-recruiter-api python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:80/api/ready').read().decode())"
```

Para detener conservando la base local:

```bash
docker compose down
```

**Borrado destructivo SOLO local** (elimina los datos de PostgreSQL dentro del volumen de Compose):

```bash
docker compose down -v
```

## Validación de regresión

```bash
python -m pytest app/tests/test_local_compose_contract.py -v
docker compose config --quiet
```

GitHub Actions ejecuta `.github/workflows/docker-compose-smoke.yml` en runners Ubuntu cuando cambia Compose o su infraestructura relacionada (y manualmente con `workflow_dispatch`). Hace `docker compose up --build --detach`, valida migración Alembic, contenedores, endpoints `/api/live` y `/api/ready` a través de Nginx, HTML del frontend y limpia los volúmenes locales al terminar. No usa secretos de GitHub ni recursos AWS. Revisa el job **Docker Compose — Local integration** del PR para ver el resultado de ejecución real.

## Alcance

Archivos afectados: `docker-compose.yml`, `app/tests/test_local_compose_contract.py`, `.github/workflows/docker-compose-smoke.yml` y esta guía. Sin cambios en rutas de aplicación, esquema, RBAC, scripts productivos, IAM ni recursos AWS; costo AWS adicional: **ninguno**.
