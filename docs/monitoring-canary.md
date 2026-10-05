# Monitorización operativa — Talent Intelligence

> El antiguo diseño de canary ECS/ALB ya no representa producción.

La arquitectura vigente usa una única instancia Lightsail con Docker. Mientras se
mantenga la restricción de no aumentar gasto fijo AWS, la observabilidad se apoya en
health checks, logs estructurados y controles locales.

## Señales mínimas

| Señal | Fuente | Umbral operativo |
| --- | --- | --- |
| API liveness | `/api/live` | debe responder 200 |
| DB readiness | `/api/ready` | debe responder 200 |
| Disco | `df -h /` | investigar desde 80%, crítico desde 90% |
| Memoria | `free -h` | investigar uso sostenido > 85% |
| Contenedores | `docker ps` | web/api/worker deben estar running |
| Worker | logs Docker | no debe entrar en restart loop |
| Errores API | logs JSON | investigar patrón 5xx sostenido |

## Logs

La aplicación emite logs estructurados JSON con `correlation_id`, ruta, status y
latencia. Docker limita el crecimiento de cada log mediante `max-size` y `max-file`.

```bash
sudo docker logs --since 15m ai-recruiter-api
sudo docker logs --since 15m ai-recruiter-worker
```

## Verificación rápida

```bash
curl -fsS http://127.0.0.1/api/live
curl -fsS http://127.0.0.1/api/ready
sudo docker ps
sudo docker system df
df -h /
free -h
```

## Evolución futura

CloudWatch dashboards, alarmas adicionales o infraestructura HA se evaluarán solamente
cuando su beneficio operativo justifique el costo adicional.
