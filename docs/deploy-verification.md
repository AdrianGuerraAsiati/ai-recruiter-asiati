# Verificación de Despliegue — Talent Intelligence

Arquitectura productiva actual:

- Región: `us-east-2`
- Instancia: `ai-recruiter-micro-prod`
- Frontend: `ai-recruiter-web`
- API: `ai-recruiter-api`
- Worker: `ai-recruiter-worker`

## Verificar estado de Lightsail

```bash
aws lightsail get-instance-state \
  --instance-name ai-recruiter-micro-prod \
  --region us-east-2
```

El estado esperado es `running`.

## Verificar contenedores

En el host:

```bash
sudo docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}'
```

Los tres contenedores de aplicación deben estar activos.

## Verificar API

```bash
curl -fsS http://127.0.0.1/api/live
curl -fsS http://127.0.0.1/api/ready
```

Esperado:

```json
{"status":"ok"}
```

y:

```json
{"status":"ok","db":true}
```

## Verificar imagen desplegada

```bash
sudo docker inspect ai-recruiter-api --format '{{.Config.Image}}'
sudo docker inspect ai-recruiter-worker --format '{{.Config.Image}}'
sudo docker inspect ai-recruiter-web --format '{{.Config.Image}}'
```

API y worker deben usar el mismo SHA de backend. El frontend debe usar el SHA de la
misma ejecución de despliegue.

## Verificar logs

```bash
sudo docker logs --since 10m --tail 200 ai-recruiter-api
sudo docker logs --since 10m --tail 200 ai-recruiter-worker
```

No debe existir un patrón sostenido de excepciones, reinicios o errores de conexión a DB.

## Seguridad del despliegue

Los contenedores se ejecutan con:

- límite de PIDs;
- rotación local de logs;
- `no-new-privileges`;
- imágenes ECR inmutables por SHA;
- rollback automático al contenedor anterior cuando falla la verificación.

Swagger, ReDoc y el endpoint HTTP de OpenAPI se deshabilitan en producción mediante
`API_DOCS_ENABLED=false`.
