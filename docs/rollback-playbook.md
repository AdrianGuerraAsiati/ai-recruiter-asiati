# Playbook de Rollback — Talent Intelligence

La estrategia actual de despliegue usa imágenes ECR inmutables por SHA y conserva las
imágenes recientes en la instancia para rollback rápido.

## Rollback automático

Los scripts:

- `scripts/deploy-api.sh`
- `scripts/deploy-worker.sh`
- `scripts/deploy-frontend.sh`

capturan la imagen anterior antes de reemplazar el contenedor. Si la nueva versión no
supera su verificación, restauran automáticamente la imagen anterior.

## Identificar versión actual

```bash
sudo docker inspect ai-recruiter-api --format '{{.Config.Image}}'
sudo docker inspect ai-recruiter-worker --format '{{.Config.Image}}'
sudo docker inspect ai-recruiter-web --format '{{.Config.Image}}'
```

## Ver imágenes disponibles

```bash
sudo docker image ls --digests
```

El despliegue conserva varias imágenes recientes para permitir recuperación sin
reconstrucción.

## Regla para rollback manual

1. Confirmar que el problema comenzó con un despliegue concreto.
2. Confirmar que PostgreSQL está sano.
3. Identificar el SHA estable anterior.
4. Reutilizar los scripts de deploy con ese SHA en lugar de crear contenedores ad hoc.
5. Verificar `/api/live`, `/api/ready` y frontend.
6. No promover `latest` hasta terminar la validación.

## Base de datos

Un rollback de aplicación **no revierte automáticamente una migración de esquema**.

Antes de cualquier restauración de DB:

- validar el backup;
- validar checksum;
- confirmar explícitamente el destino;
- usar `scripts/restore-postgres.sh`.

No ejecutar restore si un rollback de imagen es suficiente.
