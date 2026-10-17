# Odoo Sign 18 · contrato de envío confirmado en staging

## Confirmado mediante Odoo Shell del usuario (17-oct-2026)

Base: `asiati-test160526-39554181` — staging Odoo Enterprise 18.

- `sign.send.request`: `template_id` (many2one sign.template, requerido),
  `signer_ids` (one2many sign.send.request.signer), `set_sign_order` (boolean),
  `subject` (char requerido), `attachment_ids` (many2many ir.attachment),
  `message` (html), método `send_request()`.
- `sign.send.request.signer`: `partner_id` (many2one res.partner, requerido),
  `role_id` (many2one sign.item.role, requerido), `mail_sent_order` (integer).
- `sign.request.state`: `shared`, `sent`, `signed`, `canceled`, `expired`.
- `sign.request.item.state`: `sent`, `completed`, `canceled`.
- `sign.request.completed_document`: binary.
- `sign.request.completed_document_attachment_ids`: many2many ir.attachment.
- `sign.request.get_completed_document()` existe, no requiere argumentos adicionales.

Este esquema está confirmado **solo para la instancia staging inspeccionada**.
No se debe extrapolar el comportamiento de `send_request()` sin verificar su implementación.

## Implementado en el PR (sin efectos externos)

El servicio `app/domains/employee_documents/sign_dispatch.py` valida:

1. `employee_id` en lista autorizada y seguimiento staging habilitado.
2. Contrato PDF aprobado, misma versión subida a Odoo, plantilla lista y ninguna solicitud ya vinculada.
3. Esquema de wizard, campos de roles y contactos disponibles vía `fields_get`.
4. La plantilla tiene bloques asignados **únicamente** a `Empleado` y
   `Representante legal`; evita enviar una plantilla no configurada.
5. Ambos contactos son distintos y sus correos coinciden con las direcciones
   ficticias permitidas de `ODOO_SIGN_TEST_SIGNER_EMAILS`.

Construye el payload ORM para más adelante:

```python
{
  "template_id": prepared_template_id,
  "subject": "ADN360 - Firma de contrato laboral (PRUEBA)",
  "set_sign_order": True,
  "signer_ids": [
    [0, 0, {"partner_id": employee_partner_id, "role_id": employee_role_id, "mail_sent_order": 1}],
    [0, 0, {"partner_id": representative_partner_id, "role_id": representative_role_id, "mail_sent_order": 2}],
  ],
}
```

**No ejecuta `create`, `send_request`, `write` ni `unlink`.**
Tampoco retorna correos o URLs de firma en el JSON HTTP.

API RH (read-only):
`POST /api/employee-documents/employees/{employee_id}/contract/sign/request/preview`
body: `{"employee_partner_id": 301, "representative_partner_id": 302}`.
Los IDs son ejemplos; **deben utilizarse IDs de contactos de pruebas reales en staging**.
Requiere `employee_documents.review`; sin acceso directo para candidatos.

`ODOO_SIGN_STAGING_SEND_ENABLED=false` permanece apagado por defecto
y **no está conectado a ningún método de envío**.

## Validaciones restantes para implementar envío automático

En Odoo Shell de staging (sin llamar al método), inspeccionar:

```python
exec("""
import inspect
for name, method in (
    ("sign.send.request", "send_request"),
    ("sign.request", "get_completed_document"),
):
    fn = getattr(env[name], method)
    source = inspect.getsource(fn).splitlines()
    print("\\n", name, method, "total de líneas:", len(source))
    for index, line in enumerate(source, 1):
        if any(token in line for token in (
            "return", "create(", "request_id", "request_item",
            "sign.request", "completed_document", "attachment", "context",
        )):
            print(index, line.strip())
print("\\nCAMPOS DE SIGN.ITEM:")
for key, field in env["sign.item"]._fields.items():
    if getattr(field, "comodel_name", None) == "sign.item.role":
        print(key, field.type, "relación:", field.comodel_name)
""")
```

Esto **no genera solicitudes** y permite conocer cómo se referencia el request remoto.
Luego diseñar la acción de envío con control de idempotencia
(`SENDING`/resultado desconocido ante timeout, reconciliación por plantilla),
sin reintentos automáticos que dupliquen correos.

Antes de producción también verificar:
- permiso de usuario técnico para `sign.send.request` y roles/contactos;
- comportamiento de correo en staging neutralizado;
- PDF de salida + certificado de finalización;
- transición `sent` → `completed` por firmante y estado `signed` global;
- habilitar contratación automática solo después del archivado final.
