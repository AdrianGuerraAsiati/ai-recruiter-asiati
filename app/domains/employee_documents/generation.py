"""Generate controlled contract DOCX and reference PDF artifacts."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import uuid

from sqlalchemy.orm import Session

from app.domains.employee_documents import service
from app.domains.employee_documents.converter import convert_docx_to_pdf
from app.domains.employee_documents.models import (
    EmployeeDocumentArtifact,
)
from app.domains.employee_documents.storage import (
    EmployeeDocumentStorage,
    generated_artifact_key,
)
from app.domains.employee_documents.template import (
    MissingTemplateVariables,
    TemplateManifest,
    TemplateValidationError,
    render_docx,
)
from app.models import OdooContractSync, UserProfile


class DocumentGenerationError(RuntimeError):
    pass


def _load_template_bundle(
    storage: EmployeeDocumentStorage,
) -> tuple[bytes, TemplateManifest]:
    try:
        template_bytes = storage.get_bytes(storage.config.contract_template_key)
        manifest_bytes = storage.get_bytes(
            storage.config.contract_template_manifest_key
        )
    except Exception as exc:
        raise DocumentGenerationError(
            "La plantilla corporativa de contrato no está disponible."
        ) from exc
    manifest = TemplateManifest.from_json_bytes(manifest_bytes)
    return template_bytes, manifest


def _employee_values(employee: UserProfile) -> dict[str, str | None]:
    full_name = " ".join(
        part
        for part in (employee.first_name, employee.last_name)
        if str(part or "").strip()
    ).strip()
    return {
        "employee.full_name": full_name or None,
        "employee.job_title": employee.job_title,
        "employee.department": employee.department,
        "employee.email": employee.email,
    }


def _contract_values(sync: OdooContractSync) -> dict[str, str | None]:
    contract = (sync.payload or {}).get("contract") or {}
    return {
        "contract.contract_type": contract.get("contract_type"),
        "contract.start_date": contract.get("start_date"),
        "contract.end_date": contract.get("end_date"),
        "contract.monthly_wage": contract.get("monthly_wage"),
    }


def _document_context(
    db: Session,
    *,
    employee_id: str,
    document_id: str,
):
    document = service._require_document(
        db,
        employee_id=employee_id,
        document_id=document_id,
    )
    if document.document_type != "CONTRACT":
        raise DocumentGenerationError(
            "La generación automática v1 solo está disponible para contratos."
        )
    if document.status in {"SIGNED", "VOID"}:
        raise DocumentGenerationError(
            "El documento ya no admite regeneración."
        )
    employee = (
        db.query(UserProfile)
        .filter(UserProfile.id == employee_id)
        .one()
    )
    if not document.contract_sync_id:
        raise DocumentGenerationError(
            "El contrato no tiene datos estructurados asociados."
        )
    sync = (
        db.query(OdooContractSync)
        .filter(OdooContractSync.id == document.contract_sync_id)
        .one_or_none()
    )
    if sync is None:
        raise DocumentGenerationError(
            "No se encontraron los datos estructurados del contrato."
        )
    return document, employee, sync


def resolve_contract_generation_context(
    db: Session,
    *,
    employee_id: str,
    document_id: str,
    storage: EmployeeDocumentStorage,
) -> dict:
    _template_bytes, manifest = _load_template_bundle(storage)
    _document, employee, sync = _document_context(
        db,
        employee_id=employee_id,
        document_id=document_id,
    )
    source_values = {
        **_employee_values(employee),
        **_contract_values(sync),
    }
    resolved: dict[str, str | None] = {}
    manual_fields: list[dict] = []
    missing: list[str] = []

    for field in manifest.fields:
        if field.source == "manual":
            manual_fields.append(
                {
                    "name": field.name,
                    "label": field.label,
                    "required": field.required,
                    "value": None,
                }
            )
            continue
        value = source_values.get(field.source)
        resolved[field.name] = None if value is None else str(value)
        if field.required and not str(value or "").strip():
            missing.append(field.name)

    return {
        "template_version": manifest.template_version,
        "document_type": manifest.document_type,
        "resolved_values": resolved,
        "manual_fields": manual_fields,
        "missing_required_fields": sorted(missing),
    }


def _variables_for_generation(
    *,
    manifest: TemplateManifest,
    employee: UserProfile,
    sync: OdooContractSync,
    manual_values: dict[str, str],
) -> dict[str, str]:
    source_values = {
        **_employee_values(employee),
        **_contract_values(sync),
    }
    values: dict[str, str] = {}
    missing: list[str] = []

    for field in manifest.fields:
        if field.source == "manual":
            raw = manual_values.get(field.name)
        else:
            raw = source_values.get(field.source)
        value = "" if raw is None else str(raw).strip()
        values[field.name] = value
        if field.required and not value:
            missing.append(field.name)
    if missing:
        raise MissingTemplateVariables(missing)
    return values


def generate_contract_artifacts(
    db: Session,
    *,
    employee_id: str,
    document_id: str,
    manual_values: dict[str, str],
    actor_sub: str,
    storage: EmployeeDocumentStorage,
) -> tuple[EmployeeDocumentArtifact, EmployeeDocumentArtifact]:
    template_bytes, manifest = _load_template_bundle(storage)
    document, employee, sync = _document_context(
        db,
        employee_id=employee_id,
        document_id=document_id,
    )
    values = _variables_for_generation(
        manifest=manifest,
        employee=employee,
        sync=sync,
        manual_values=manual_values,
    )
    try:
        docx_bytes = render_docx(
            template_bytes,
            variables=values,
            manifest=manifest,
        )
        pdf_bytes = convert_docx_to_pdf(docx_bytes, timeout_seconds=30)
    except (TemplateValidationError, MissingTemplateVariables):
        raise
    except Exception as exc:
        raise DocumentGenerationError(
            "No fue posible generar los documentos del contrato."
        ) from exc

    docx_id = str(uuid.uuid4())
    pdf_id = str(uuid.uuid4())
    docx_key = generated_artifact_key(
        employee_id, document.id, docx_id, "docx"
    )
    pdf_key = generated_artifact_key(
        employee_id, document.id, pdf_id, "pdf"
    )
    uploaded: list[str] = []
    try:
        storage.put_bytes(
            docx_key,
            docx_bytes,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        uploaded.append(docx_key)
        storage.put_bytes(pdf_key, pdf_bytes, "application/pdf")
        uploaded.append(pdf_key)
    except Exception as exc:
        for key in uploaded:
            try:
                storage.delete_object(key)
            except Exception:
                pass
        raise DocumentGenerationError(
            "No fue posible almacenar los documentos generados."
        ) from exc

    previous = (
        db.query(EmployeeDocumentArtifact)
        .filter(EmployeeDocumentArtifact.document_id == document.id)
        .all()
    )
    now = datetime.now(timezone.utc)
    docx = EmployeeDocumentArtifact(
        id=docx_id,
        document_id=document.id,
        artifact_kind="GENERATED_DOCX",
        storage_key=docx_key,
        mime_type=(
            "application/vnd.openxmlformats-officedocument."
            "wordprocessingml.document"
        ),
        file_size=len(docx_bytes),
        sha256=hashlib.sha256(docx_bytes).hexdigest(),
        template_version=manifest.template_version,
        created_by_sub=actor_sub,
        created_at=now,
    )
    pdf = EmployeeDocumentArtifact(
        id=pdf_id,
        document_id=document.id,
        artifact_kind="REFERENCE_PDF",
        storage_key=pdf_key,
        mime_type="application/pdf",
        file_size=len(pdf_bytes),
        sha256=hashlib.sha256(pdf_bytes).hexdigest(),
        template_version=manifest.template_version,
        created_by_sub=actor_sub,
        created_at=now,
    )
    try:
        for artifact in previous:
            db.delete(artifact)
        db.add_all([docx, pdf])
        document.status = "PENDING_SIGNATURE"
        db.commit()
        db.refresh(docx)
        db.refresh(pdf)
        db.refresh(document)
    except Exception as exc:
        db.rollback()
        for key in uploaded:
            try:
                storage.delete_object(key)
            except Exception:
                pass
        raise DocumentGenerationError(
            "No fue posible registrar los documentos generados."
        ) from exc

    for artifact in previous:
        try:
            storage.delete_object(artifact.storage_key)
        except Exception:
            pass
    return docx, pdf
