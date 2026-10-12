"""Durable, idempotent SES welcome email and document checklist delivery."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.domains.employee_documents.models import EmployeeDocumentEmail
from app.domains.employee_documents.requirements import EMPLOYEE_DOCUMENT_REQUIREMENTS
from app.domains.employee_documents.service import portfolio_payload
from app.infrastructure.bedrock.session import get_cached_session
from app.config import get_aws_region
from app.models import UserProfile

logger = logging.getLogger(__name__)

KIND = "WELCOME_DOCUMENTS"
DOCUMENTS_LINK = "https://talent.asiaticorp.com/documents"
LOGIN_LINK = "https://talent.asiaticorp.com"


def sender_address() -> str:
    """Use the existing SES verified Talent sender; no new infrastructure."""
    return (
        os.getenv("TALENT_ID_FROM_EMAIL", "").strip()
        or os.getenv("TALENT_ID_CONSENT_FROM_EMAIL", "").strip()
    )


def queue_welcome(db: Session, employee_id: str) -> EmployeeDocumentEmail:
    existing = (
        db.query(EmployeeDocumentEmail)
        .filter(
            EmployeeDocumentEmail.employee_id == employee_id,
            EmployeeDocumentEmail.kind == KIND,
        )
        .one_or_none()
    )
    if existing is not None:
        return existing
    row = EmployeeDocumentEmail(employee_id=employee_id, kind=KIND, status="PENDING")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def delivery_payload(row: EmployeeDocumentEmail | None) -> dict:
    if row is None:
        return {"status": "NOT_REQUESTED", "attempt_count": 0, "sent_at": None}
    return {
        "status": row.status,
        "attempt_count": row.attempt_count,
        "sent_at": row.sent_at.isoformat() if row.sent_at else None,
        "reason": row.last_error,
    }


def status_for_employee(db: Session, employee_id: str) -> dict:
    row = (
        db.query(EmployeeDocumentEmail)
        .filter(
            EmployeeDocumentEmail.employee_id == employee_id,
            EmployeeDocumentEmail.kind == KIND,
        )
        .one_or_none()
    )
    return delivery_payload(row)


def welcome_message(db: Session, employee: UserProfile) -> tuple[str, str]:
    portfolio = portfolio_payload(db, employee.id)
    missing = [
        item["label"]
        for item in portfolio["items"]
        if item["review_status"] != "APPROVED"
    ]
    first_name = (employee.first_name or "equipo").strip()
    title = "¡Felicitaciones por tu contratación en ASIATI! | Documentación de ingreso"
    lines = [
        f"Hola, {first_name}:",
        "",
        "¡Felicitaciones! Nos alegra darte la bienvenida a ASIATI.",
        "Tu proceso de contratación ha sido confirmado y estamos felices",
        "de que formes parte de nuestro equipo.",
        "",
    ]
    if missing:
        lines += [
            "Para completar tu expediente de ingreso, necesitamos que",
            "cargues o actualices los siguientes documentos y datos:",
            "",
            *[f"- {label}" for label in missing],
            "",
            "Si ya enviaste alguno, no necesitas repetirlo mientras esté",
            "aprobado. Talento Humano revisará cada requisito y te dejará",
            "comentarios en Talent si se requiere una corrección.",
        ]
    else:
        lines += [
            "Tus requisitos documentales ya figuran como aprobados en Talent.",
            "Puedes consultar tu expediente cuando lo necesites.",
        ]
    lines += [
        "",
        "Ingresa a Talent: " + LOGIN_LINK,
        "Carga tus documentos aquí, iniciando sesión: " + DOCUMENTS_LINK,
        "Usuario: " + (employee.login_username or employee.email or ""),
        "",
        "Si aún no estableciste tu contraseña, sigue las instrucciones",
        "de acceso entregadas por Talento Humano.",
        "Por seguridad nunca compartas tu contraseña ni envíes",
        "documentos personales respondiendo este mensaje.",
        "",
        "¡Bienvenido a ASIATI!",
        "Equipo de Talento Humano",
    ]
    return title, "\n".join(lines)


def send_welcome(db: Session, employee_id: str, *, ses_client=None) -> dict:
    """Best-effort delivery of a persisted intent, safely retryable.

    The intent is created on formal hire. The database is committed before
    contacting SES; failures are recorded and never undo employment.
    """
    row = queue_welcome(db, employee_id)
    if row.status in ("SENT", "SENDING"):
        return delivery_payload(row)

    employee = db.query(UserProfile).filter(UserProfile.id == employee_id).one_or_none()
    if employee is None or not employee.email:
        row.status = "FAILED"
        row.last_error = "EMPLOYEE_EMAIL_MISSING"
        db.commit()
        return delivery_payload(row)

    sender = sender_address()
    if not sender:
        row.status = "FAILED"
        row.last_error = "SES_SENDER_NOT_CONFIGURED"
        db.commit()
        return delivery_payload(row)

    # A concurrent retry cannot claim the same row when it is already SENDING.
    now = datetime.now(timezone.utc)
    claimed = (
        db.query(EmployeeDocumentEmail)
        .filter(
            EmployeeDocumentEmail.id == row.id,
            EmployeeDocumentEmail.status.in_(("PENDING", "FAILED")),
        )
        .update(
            {
                EmployeeDocumentEmail.status: "SENDING",
                EmployeeDocumentEmail.attempt_count: EmployeeDocumentEmail.attempt_count + 1,
                EmployeeDocumentEmail.attempt_at: now,
                EmployeeDocumentEmail.last_error: None,
            },
            synchronize_session=False,
        )
    )
    db.commit()
    db.refresh(row)
    if not claimed:
        return delivery_payload(row)

    try:
        subject, body = welcome_message(db, employee)
        client = ses_client or get_cached_session().client("sesv2", region_name=get_aws_region())
        client.send_email(
            FromEmailAddress=sender,
            Destination={"ToAddresses": [employee.email]},
            Content={
                "Simple": {
                    "Subject": {"Data": subject, "Charset": "UTF-8"},
                    "Body": {"Text": {"Data": body, "Charset": "UTF-8"}},
                }
            },
        )
    except Exception:
        logger.warning("Employee welcome document email delivery failed", exc_info=False)
        row.status = "FAILED"
        row.last_error = "SES_DELIVERY_FAILED"
        db.commit()
        db.refresh(row)
        return delivery_payload(row)

    row.status = "SENT"
    row.last_error = None
    row.sent_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return delivery_payload(row)
