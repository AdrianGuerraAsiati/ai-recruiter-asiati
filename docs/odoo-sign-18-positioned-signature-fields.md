# Odoo Sign staging: posición de campos y normalización de roles

## Evidencia leída desde Odoo Shell (19/oct/2026)

Plantilla de demostración **128** contiene exactamente dos `sign.item`:

| Rol | Role ID | Tipo | Página | posX | posY | width | height | Required |
|---|---:|---|---:|---:|---:|---:|---:|---|
| Employee | 3 | Signature (type 1) | 1 | 0.111 | 0.593 | 0.654 | 0.050 | true |
| Representante legal | 5 | Signature (type 1) | 1 | 0.107 | 0.748 | 0.669 | 0.048 | true |

Plantilla **129** creada por ADN360 para el expediente de prueba:
**0 campos**. La transferencia del PDF ya funciona, pero la plantilla no puede enviarse sin configurar los bloques de firma.

Estas coordenadas están normalizadas respecto de la página en Odoo Sign.
La plantilla 128 y la 129 pueden corresponder a PDFs de distinto diseño;
**no copiar ciegamente posiciones de la 128 a la 129**. Se requiere verificar
visualmente la zona de firmas en la página 1 del PDF 129 y, si coincide,
autorizar su aplicación exclusivamente a la plantilla de prueba.

## Corrección de este PR

En esta instancia Odoo devuelve la etiqueta de rol `Employee`, pero
el código ADN360 exigía literalmente `Empleado`. Ahora `canonical_role()`
acepta ambas etiquetas para el rol employee, además de
`Representante legal` / `Legal representative`, sin aceptar terceros.
Se utiliza en la validación de dos roles previa al envío y en el
seguimiento de firmas, incluidas las completadas.

Este PR **no modifica plantillas ni envía solicitudes**.

## Siguiente implementación tras confirmar el diseño

1. Resolver el campo many2one `sign.item.template_id` y requisitos de
   creación mediante `fields_get` en Odoo staging (solo lectura).
2. Obtener y comparar tamaños/páginas del PDF 128 y 129 o ubicar
   posiciones mediante los propios marcadores de firma del PDF 129.
3. Incorporar servicio de colocación de dos bloques de firma en ADN360,
   transaccional, idempotente y con verificación de ambos roles.
4. Solo entonces habilitar confirmación de envío desde ADN360, sin
   exponer contactos, IDs o enlaces Odoo en el frontend.

Mientras no se complete ese flujo, `ODOO_SIGN_STAGING_SEND_ENABLED=false`.
