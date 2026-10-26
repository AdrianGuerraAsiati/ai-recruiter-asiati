"""Pre-sign binding of approved contract documents to one application.

Binding must happen before Odoo Sign preparation, never after signatures.
This deliberately does not migrate or reassign legacy signed documents.
"""
from __future__ import annotations

import os

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domains.candidates import repository as candidates_repository
from app.domains.candidates import service as candidates_service
from app.domains.employee_documents.models import ApplicationContract, EmployeeDocument
from app.domains.employees import service as employees_service
from app.domains.odoo_sync import company_catalog, integration as odoo_integration
from app.integrations.odoo.client import OdooClientError


class ContractBindingConflict(ValueError):
    pass


def binding_enabled() -> bool:
    return (
        os.getenv("ADN360_APPLICATION_CONTRACT_BINDING_ENABLED", "").strip().lower()
        in {"1", "true", "yes"}
        or os.getenv("ADN360_REQUIRE_SIGNED_CONTRACT_FOR_HIRE", "").strip().lower()
        in {"1", "true", "yes"}
    )


def bind(
    db: Session,
    *,
    owner_sub: str,
    job_id: str,
    candidate_id: str,
    odoo_company_id: int,
) -> dict:
    """Bind an APPROVED, unsigned PDF; never silently adopt an old signed PDF."""
    if not binding_enabled():
        raise ContractBindingConflict("La vinculación de contratos por postulación no está habilitada.")
    if type(odoo_company_id) is not int or odoo_company_id <= 0:
        raise ContractBindingConflict("Selecciona una empresa válida de Odoo.")

    candidates_service.require_job(db, job_id, owner_sub)
    candidates_service.require_candidate(db, candidate_id, owner_sub)
    link = candidates_repository.get_job_candidate(
        db, job_id=job_id, candidate_id=candidate_id, owner_sub=None,
    )
    if link is None:
        raise candidates_service.JobCandidateNotFound(candidate_id)
    if link.application_status not in {"SELECTED", "OFFER"}:
        raise ContractBindingConflict("Selecciona la postulación antes de vincular el contrato.")
    if not link.employee_id:
        raise ContractBindingConflict("Primero crea el expediente del postulante.")
    employees_service.require_employee(db, link.employee_id)

    document = db.query(EmployeeDocument).filter(
        EmployeeDocument.employee_id == link.employee_id,
        EmployeeDocument.document_type == "EMPLOYMENT_CONTRACT",
    ).with_for_update().one_or_none()
    if not document or not document.storage_key or document.review_status != "APPROVED":
        raise ContractBindingConflict("Primero carga y aprueba el contrato de esta postulación.")

    existing = db.query(ApplicationContract).filter(
        ApplicationContract.application_id == link.id
    ).one_or_none()
    if existing is not None:
        if (
            existing.employee_id != link.employee_id
            or existing.document_id != document.id
            or existing.source_storage_key != document.storage_key
            or existing.odoo_company_id != odoo_company_id
        ):
            raise ContractBindingConflict("El contrato ya tiene una vinculación diferente.")
        return {
            "application_id": str(link.id),
            "document_id": document.id,
            "odoo_company_id": existing.odoo_company_id,
            "bound": True,
            "already_bound": True,
        }

    if (
        document.odoo_sign_status != "NOT_PREPARED"
        or document.odoo_sign_request_id is not None
        or document.odoo_sign_request_status != "UNLINKED"
        or document.odoo_sign_signed_storage_key
        or document.odoo_sign_certificate_storage_key
    ):
        raise ContractBindingConflict(
            "Este documento ya fue preparado o firmado. No se permite vincularlo retrospectivamente."
        )
    if db.query(ApplicationContract).filter(
        ApplicationContract.document_id == document.id,
    ).first():
        raise ContractBindingConflict("El PDF ya pertenece a otra postulación.")

    # Verify actual Odoo company before persisting the irreversible binding.
    try:
        company_catalog.require_company(odoo_company_id)
    except company_catalog.OdooCompanyNotFound as exc:
        raise ContractBindingConflict(str(exc)) from exc
    except (odoo_integration.OdooDisabled, odoo_integration.OdooNotConfigured, OdooClientError) as exc:
        raise ContractBindingConflict("No está disponible el catálogo de empresas de Odoo.") from exc

    db.add(ApplicationContract(
        application_id=link.id,
        employee_id=link.employee_id,
        document_id=document.id,
        odoo_company_id=odoo_company_id,
        source_storage_key=document.storage_key,
    ))
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ContractBindingConflict("El contrato fue vinculado por otra operación. Actualiza el expediente.") from exc

    return {
        "application_id": str(link.id),
        "document_id": document.id,
        "odoo_company_id": odoo_company_id,
        "bound": True,
        "already_bound": False,
    }
