# Runbook de Incidentes — Talent Intelligence

Este runbook describe la arquitectura productiva actual: una instancia Amazon Lightsail
`ai-recruiter-micro-prod` en `us-east-2`, con frontend, API y worker ejecutados en
Docker y PostgreSQL en el mismo host.

## Principios

1. No crear infraestructura adicional durante un incidente salvo aprobación explícita.
2. Preservar datos antes de reiniciar o migrar.
3. Preferir rollback de imagen antes que cambios manuales sobre producción.
4. Registrar hora, síntoma, acción y resultado.

## Severidad

| Señal | Severidad | Acción inicial |
| --- | --- | --- |
| Sitio o API totalmente caídos | P0 | Verificar instancia, contenedores y DB |
| `/api/ready` responde 503 | P0 | Revisar PostgreSQL antes de redeploy |
| API 5xx sostenido | P1 | Revisar logs y rollback si coincide con deploy |
| Worker detenido | P1 | Reiniciar únicamente worker si API está sana |
| Disco > 85% | P1 | Limpiar imágenes/logs de forma controlada |
| CPU o memoria sostenidas > 85% | P2 | Identificar proceso/contenedor antes de reiniciar |
| Integración externa caída | P2 | Aislar Gmail/Odoo/Indeed del core |

## Diagnóstico inicial

En la instancia:

```bash
sudo docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}'
sudo docker system df
df -h /
free -h
```

Contenedores esperados:

- `ai-recruiter-web`
- `ai-recruiter-api`
- `ai-recruiter-worker`

Health local:

```bash
curl -fsS http://127.0.0.1/api/live
curl -fsS http://127.0.0.1/api/ready
```

## Logs

```bash
sudo docker logs --since 15m --tail 300 ai-recruiter-api
sudo docker logs --since 15m --tail 300 ai-recruiter-worker
sudo docker logs --since 15m --tail 200 ai-recruiter-web
```

Buscar por `correlation_id` cuando el frontend o un usuario reporte un error concreto.

## Base de datos

No ejecutar restore como primera reacción.

Primero:

```bash
pg_isready -h 127.0.0.1
df -h /
```

Antes de una operación destructiva, crear backup con `scripts/backup-postgres.sh`.

El restore requiere checksum válido y `CONFIRM_RESTORE=yes`.

## Fallo posterior a deploy

Los scripts de deploy conservan la imagen anterior y hacen rollback automático si la
verificación del contenedor falla.

Confirmar imagen actual:

```bash
sudo docker inspect ai-recruiter-api --format '{{.Config.Image}}'
sudo docker inspect ai-recruiter-worker --format '{{.Config.Image}}'
sudo docker inspect ai-recruiter-web --format '{{.Config.Image}}'
```

Si el incidente empezó inmediatamente después de un despliegue, detener cambios
adicionales y usar la última imagen SHA conocida como estable.

## Disco lleno

Orden recomendado:

```bash
sudo docker system df
sudo docker container prune -f
sudo docker image prune -f
sudo docker builder prune -a -f
df -h /
```

No borrar backups recientes ni volúmenes de PostgreSQL durante una limpieza de emergencia.

## Cierre del incidente

Antes de cerrar:

- `/api/live` responde 200.
- `/api/ready` responde 200.
- API, worker y frontend están `running`.
- PostgreSQL acepta conexiones.
- No hay crecimiento anormal de disco.
- Se registra causa raíz y acción preventiva.
