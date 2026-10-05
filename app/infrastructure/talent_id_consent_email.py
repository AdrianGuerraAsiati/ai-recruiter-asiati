"""AWS SES delivery for Talent ID verification codes."""

from __future__ import annotations

from app.config import (
    get_aws_region,
    get_talent_id_consent_settings,
    get_talent_id_qr_settings,
)
from app.infrastructure.bedrock.session import get_cached_session


class ConsentEmailDeliveryError(RuntimeError):
    pass


class MobileLinkEmailDeliveryError(RuntimeError):
    pass


def _send_email(*, from_email: str, to_email: str, subject: str, body: str) -> None:
    if not from_email:
        raise ValueError("Talent ID email sender is not configured.")

    client = get_cached_session().client(
        "sesv2",
        region_name=get_aws_region(),
    )
    client.send_email(
        FromEmailAddress=from_email,
        Destination={"ToAddresses": [to_email]},
        Content={
            "Simple": {
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {"Text": {"Data": body, "Charset": "UTF-8"}},
            }
        },
    )


def send_consent_otp(to_email: str, code: str, ttl_seconds: int) -> None:
    settings = get_talent_id_consent_settings()
    minutes = max(1, round(ttl_seconds / 60))
    subject = "Código de firma electrónica - Talent ID"
    body = (
        "Tu código para firmar la decisión de tratamiento de datos biométricos "
        f"en Talent ID es: {code}\n\n"
        f"El código vence en aproximadamente {minutes} minutos.\n"
        "Si no solicitaste este código, no lo compartas y comunícate con Talento Humano."
    )

    try:
        _send_email(
            from_email=settings.from_email,
            to_email=to_email,
            subject=subject,
            body=body,
        )
    except Exception as exc:
        raise ConsentEmailDeliveryError(
            "No fue posible enviar el código de firma."
        ) from exc


def send_mobile_link_otp(to_email: str, code: str, ttl_seconds: int) -> None:
    settings = get_talent_id_qr_settings()
    minutes = max(1, round(ttl_seconds / 60))
    subject = "Verifica tu celular para Talent ID"
    body = (
        "Se solicitó vincular un celular como credencial no biométrica de Talent ID.\n\n"
        f"Tu código de verificación es: {code}\n\n"
        f"El código vence en aproximadamente {minutes} minutos.\n"
        "No compartas este código. Si no solicitaste la vinculación, cambia tu contraseña "
        "de Talent y comunícate con Talento Humano."
    )

    try:
        _send_email(
            from_email=settings.from_email,
            to_email=to_email,
            subject=subject,
            body=body,
        )
    except Exception as exc:
        raise MobileLinkEmailDeliveryError(
            "No fue posible enviar el código para vincular el celular."
        ) from exc
