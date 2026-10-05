"""Email delivery for Talent ID electronic-signature OTP codes."""

from __future__ import annotations

from app.config import get_aws_region, get_talent_id_consent_settings
from app.infrastructure.bedrock.session import get_cached_session


class ConsentEmailDeliveryError(RuntimeError):
    pass


def send_consent_otp(to_email: str, code: str, ttl_seconds: int) -> None:
    settings = get_talent_id_consent_settings()
    if not settings.from_email:
        raise ConsentEmailDeliveryError(
            "TALENT_ID_CONSENT_FROM_EMAIL no está configurado."
        )

    minutes = max(1, round(ttl_seconds / 60))
    subject = "Código de firma electrónica - Talent ID"
    body = (
        "Tu código para firmar la decisión de tratamiento de datos biométricos "
        f"en Talent ID es: {code}\n\n"
        f"El código vence en aproximadamente {minutes} minutos.\n"
        "Si no solicitaste este código, no lo compartas y comunícate con Talento Humano."
    )

    client = get_cached_session().client(
        "sesv2",
        region_name=get_aws_region(),
    )
    try:
        client.send_email(
            FromEmailAddress=settings.from_email,
            Destination={"ToAddresses": [to_email]},
            Content={
                "Simple": {
                    "Subject": {"Data": subject, "Charset": "UTF-8"},
                    "Body": {"Text": {"Data": body, "Charset": "UTF-8"}},
                }
            },
        )
    except Exception as exc:
        raise ConsentEmailDeliveryError(
            "No fue posible enviar el código de firma."
        ) from exc
