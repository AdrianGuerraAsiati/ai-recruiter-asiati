# Contratación → Odoo

## Objetivo

La integración de Odoo comienza únicamente cuando una postulación se confirma como contratada (`HIRED`). Las vacantes y los candidatos que siguen en etapas de reclutamiento permanecen en aiRecruiter y no se replican de forma general al ERP.

## Primer corte: outbox local

El flujo de contratación prepara un registro durable en `odoo_employee_syncs` después de crear/reutilizar el empleado, asignar el onboarding y marcar la postulación como `HIRED`.

Este primer corte **no hace llamadas de red a Odoo**. El objetivo es desacoplar la contratación local de la disponibilidad del ERP y disponer de una cola idempotente antes de implementar el transporte.

### Estados

- `PENDING`: existe información lista para sincronizar.
- `SYNCED`: el upsert fue confirmado por Odoo.
- `FAILED`: el último intento falló y conserva contexto para reintento.

La clave de idempotencia inicial es `employee:{employee_id}`, por lo que reintentar la misma contratación no crea múltiples registros de sincronización para el mismo empleado.

## Contrato v1

El payload preparado tiene `schema_version = 1` y `operation = UPSERT_EMPLOYEE`.

Incluye actualmente:

- IDs internos de empleado, candidato, vacante y postulación;
- fecha de contratación;
- nombre y apellido;
- correo;
- cargo;
- área/departamento;
- fecha de ingreso;
- contexto básico de la vacante: título, país, ciudad y tipo de empleo.

## Campos todavía por cerrar antes del transporte real

El transporte a Odoo no debe activarse hasta definir explícitamente:

- modelo(s) destino y nombres técnicos de campos en Odoo;
- teléfono del contratado y su fuente canónica;
- adjunto/CV canónico y cómo se transferirá;
- cualquier dato contractual o de nómina requerido por Talento Humano;
- credenciales y endpoint de Odoo;
- política de reintentos y transición `FAILED → PENDING`;
- captura del identificador externo en `odoo_record_id`.

## Regla de disponibilidad

Una indisponibilidad de Odoo no debe impedir que aiRecruiter complete la contratación, cree el acceso del empleado ni asigne el onboarding. El transporte consumirá posteriormente el outbox pendiente.
