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

## Inspección de ambos PDF originales y distribución correcta

Los archivos de prueba ya están disponibles y se inspeccionaron con PyMuPDF:

- Ambos son A4 de una página (aprox. 595.276 × 841.89 pt), **pero sus zonas de firma no son iguales**.
- El documento original de la plantilla 129 contiene dos recuadros punteados separados, ubicados aproximadamente en `[47,595,290,707]` y `[306,595,548,707]` puntos.
- Las coordenadas de 128 superponen texto o invaden ambos recuadros de la 129. **No reutilizarlas**.
- El detector de staging calcula dos campos **dentro de cada rectángulo**, debajo del texto descriptivo y antes del pie del firmante:

| Rol | Página | posX | posY | width | height | Obligatorio |
|---|---:|---:|---:|---:|---:|---|
| Empleado | 1 | 0.09911 | 0.75888 | 0.36729 | 0.04276 | Sí |
| Representante legal | 1 | 0.53360 | 0.75888 | 0.36729 | 0.04276 | Sí |

Estas cifras están normalizadas; la implementación las **deriva del PDF**, no las codifica como constantes, y verifica colisiones con el texto.

## Operación en ADN360

1. El administrador sube/aprueba el PDF ficticio, ya realizado.
2. ADN360 crea su plantilla Odoo Sign, ya realizado para 129.
3. Clic **Detectar dos campos de firma** consulta el PDF del expediente, valida los recuadros, tipo Firma y roles de Odoo, sin escrituras.
4. Clic **Colocar ambas firmas en Odoo** ejecuta un único write de dos campos obligatorios a la plantilla, verificando luego la posición/rol/tipo. Es idempotente si la plantilla ya contiene exactamente esos campos.
5. Envío de solicitudes permanece desactivado por defecto. Solo cuando terminemos el E2E habrá una confirmación de envío único a los dos contactos ficticios.

Limitaciones:
- La detección está restringida **al PDF ficticio de nombre exacto**, con marcador `SOLO PRUEBA - SIN VALIDEZ CONTRACTUAL`, una página y dos recuadros reconocibles.
- No es un algoritmo general para todo contrato real. Para producción diseñar editor de posiciones en ADN360 o plantillas laborales estandarizadas.
- Las escrituras XML-RPC reales de `sign.template.sign_item_ids` aún deben probarse en staging con usuario técnico; ningún PDF/productivo se ha firmado.
