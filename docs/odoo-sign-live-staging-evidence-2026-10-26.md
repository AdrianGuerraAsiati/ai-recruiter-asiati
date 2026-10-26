# Odoo.sh staging real — evidencia y siguiente prueba de firmas (26-oct-2026)

## Evidencia efectivamente ejecutada

Workflow: [GitHub Actions run 40391838032](https://github.com/AdrianGuerraAsiati/ai-recruiter-asiati/actions/runs/40391838032).

- **Servicio real**: `asiati-test160526-39554181.dev.odoo.com`
- **Base objetivo autorizada**: `asiati-test160526-39554181` (el probe comprueba la allowlist, no entra a la base).
- **Método real**: HTTPS XML-RPC `/xmlrpc/2/common`, llamada anónima `version()`.
- **Resultado**: `https_xmlrpc_reachable=true`, `odoo_series=18.0`, 9/9 controles de seguridad de URL y base correctos.
- **No realizado**: autenticación, `fields_get` real de Odoo Sign, consulta de correo neutralizado, creación de plantilla/solicitud o firmas.
- **Sin efectos**: sin API keys, roles IAM, correo saliente, `create`, `write`, `unlink`, `send_request` ni cambios productivos.

La documentación oficial de Odoo.sh 18 confirma que **staging y development** neutralizan el correo saliente y lo capturan en *Mails*. Esta protección estándar no demuestra que la base concreta no se haya personalizado.

## Comprobación autenticada de Odoo.sh antes de enviar firma

Este paso necesita la pestaña **Odoo.sh → Staging (no Production) → Shell** y un usuario autorizado. Odoo.sh recomienda `odoo-bin shell`. **No ejecutar en Shell roja de producción.** Las instrucciones siguientes son solo de lectura y no necesitan compartir claves.

Abrir Shell, ejecutar `odoo-bin shell`, y dentro de la consola Python:

```python
assert env.cr.dbname == "asiati-test160526-39554181", "NO ES STAGING"
params = env["ir.config_parameter"].sudo()
neutralized = str(params.get_param("database.is_neutralized") or "").strip().lower()
print("BASE_STAGING_OK", True)
print("NEUTRALIZACION", neutralized in {"true", "1", "yes"})
print("SIGN_INSTALADO", env["ir.module.module"].sudo().search_count(
    [("name", "=", "sign"), ("state", "=", "installed")],
) > 0)

required = {
    "sign.template": {"attachment_id", "sign_item_ids"},
    "sign.send.request": {"template_id", "signer_ids", "subject"},
    "sign.send.request.signer": {"partner_id", "role_id"},
    "sign.request": {"template_id", "request_item_ids", "state",
                     "completed_document_attachment_ids"},
    "sign.request.item": {"role_id", "signer_email", "state"},
}
for model, fields in required.items():
    actual = set(env[model]._fields)
    print("SCHEMA_OK", model, fields.issubset(actual))

final_field = env["sign.request"]._fields.get("completed_document_attachment_ids")
print("PDF_Y_CERTIFICADO_RELACION", bool(
    final_field and final_field.type == "many2many"
    and final_field.comodel_name == "ir.attachment"
))
test_emails = [
    "empleado.adn360@example.invalid",
    "representante.adn360@example.invalid",
]
partners = env["res.partner"].sudo().search([("email", "in", test_emails)])
print("DOS_FIRMANTES_FICTICIOS", (
    len(partners) == 2 and set(partners.mapped("email")) == set(test_emails)
))
```

**No ejecutar `create`, `write`, `unlink`, `send_request` ni activar flags** hasta que salgan `True` la neutralización, todos los `SCHEMA_OK`, la relación de documentos finales y la validación de dos contactos `.invalid`.

## Fase de envío real controlado — aún pendiente

Después de verificar los puntos anteriores y preparar una fixture contractual sin PII en un entorno **Talent staging separado**:

1. Crear/aprobar/vincular un PDF ficticio, con una empresa Odoo de pruebas y un usuario ADN360 allowlisted.
2. Preparar una única plantilla con campos para **Empleado** y **Representante legal**.
3. Enviar **una sola vez** mediante el flujo staging de ADN360 a los correos `.invalid`; observar el mail catcher de Odoo.sh.
4. Simular las firmas en entorno controlado; demostrar que una sola no habilita contratación.
5. Tras las dos firmas, verificar un `sign.request` válido y los **dos adjuntos** (PDF y certificado), luego archivar y comprobar SHA-256 por separado.
6. Confirmar idempotencia, protección contra reenvío, coincidencia de empresa y bloqueo al cambiar el PDF; no habilitar producción.

Si las direcciones `.invalid` no existen o la base staging no está neutralizada, **no enviar solicitudes**. No pasar credenciales ni enlaces individuales de firma en GitHub ni en chats.
