"""HTTP endpoints for explicit Odoo synchronization actions."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.deps import get_db, require_permission
from app.domains.odoo_sync import (
    applicant_import,
    company_catalog,
    contract_delivery,
    employee_delivery,
    employee_import,
    integration,
    job_delivery,
    staging,
)
from app.integrations.odoo.client import OdooClientError


router = APIRouter(prefix="/api/odoo", tags=["odoo"])


@router.get("/companies")
def list_odoo_companies(
    _principal: dict = Depends(require_permission("employees.create")),
):
    """Active companies visible in the configured Odoo environment; no logos or credentials."""
    try:
        return {"items": company_catalog.list_companies()}
    except (integration.OdooDisabled, integration.OdooNotConfigured, OdooClientError) as exc:
        raise HTTPException(
            status_code=503,
            detail="No se pudo consultar el catálogo de empresas de Odoo.",
        ) from exc




@router.get("/diagnostics")
def odoo_readonly_diagnostics(
    _principal: dict = Depends(require_permission("employees.update")),
):
    """Authenticate and inspect relevant Odoo models without writing data."""
    status = integration.connection_status()
    try:
        client = integration.build_odoo_client()
        health = client.healthcheck()
    except (integration.OdooDisabled, integration.OdooNotConfigured, OdooClientError) as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    models = {}
    for model in (
        "hr.employee",
        "hr.job",
        "hr.applicant",
        "hr.contract",
        "ir.attachment",
        "sign.request",
        "sign.template",
    ):
        try:
            fields = client.fields_get(model)
            models[model] = {
                "available": True,
                "field_count": len(fields),
                "fields": sorted(fields.keys()),
            }
        except OdooClientError:
            models[model] = {"available": False}

    return {"connection": status, "health": health, "models": models, "read_only": True}



@router.get("/staging/sign/diagnostics")
def staging_sign_schema_diagnostics(
    _principal: dict = Depends(require_permission("integrations.manage")),
):
    """Read-only metadata, no signatory data, no credentials, no Odoo writes."""
    try:
        target = staging.build_staging_client()
        health = target.healthcheck()
    except (integration.OdooNotConfigured, OdooClientError) as exc:
        raise HTTPException(status_code=503, detail="Odoo staging no está disponible.") from exc
    models = {}
    for model in ("sign.template", "sign.request", "sign.request.item",
                  "sign.send.request", "sign.item.role", "ir.attachment"):
        try:
            fields = target.fields_get(model, attributes=("type", "relation", "required", "readonly"))
            models[model] = {
                "available": True,
                "fields": {
                    name: {k: field.get(k) for k in ("type", "relation", "required", "readonly")}
                    for name, field in fields.items()
                    if name in {
                        "id", "template_id", "attachment_id", "request_item_ids",
                        "role_id", "signer_email", "partner_id", "state", "signed",
                        "signing_date", "signed_on", "completed_document",
                        "completed_document_attachment_ids", "signed_document",
                        "signed_document_attachment_id", "datas", "res_model",
                        "res_id", "reference", "filename", "name", "subject",
                        "signers_count", "signer_ids", "signers", "sign_item_ids",
                        "request_id", "mail_sent_order", "expire_date",
                    }
                },
            }
        except OdooClientError:
            models[model] = {"available": False}
    return {
        "environment": "staging", "read_only": True,
        "odoo_version": health.get("server_serie"),
        "models": models,
        "note": "El diagnóstico no contiene contactos ni solicitudes de firma.",
    }


@router.post("/jobs/sync")
def sync_jobs_to_odoo(
    db: Session = Depends(get_db),
    _principal: dict = Depends(require_permission("jobs.manage")),
):
    """Reconcile all Talent vacancies with Odoo using ACTIVE/PAUSED semantics."""
    try:
        return job_delivery.sync_all_jobs_now(db)
    except (integration.OdooDisabled, integration.OdooNotConfigured) as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except (job_delivery.OdooJobDeliveryError, OdooClientError) as exc:
        raise HTTPException(
            status_code=502,
            detail=f"No fue posible actualizar las vacantes en Odoo: {exc}",
        )


@router.get("/applicants/diagnostics")
def diagnose_odoo_applicants(
    sample_limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _principal: dict = Depends(require_permission("candidates.manage")),
):
    """Inspect raw Odoo applicants versus Talent job mappings without writes."""
    try:
        return applicant_import.diagnose_applicant_sources(
            db,
            sample_limit=sample_limit,
        )
    except (integration.OdooDisabled, integration.OdooNotConfigured) as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except applicant_import.OdooApplicantImportError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"No fue posible diagnosticar los postulantes de Odoo: {exc}",
        )


@router.post("/applicants/import")
def import_applicants_from_odoo(
    dry_run: bool = Query(default=False),
    job_id: str | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1, le=500),
    db: Session = Depends(get_db),
    _principal: dict = Depends(require_permission("candidates.manage")),
):
    """Preview or incrementally import Odoo Recruitment applicants and resumes."""
    try:
        if dry_run:
            return applicant_import.preview_applicants_from_odoo(
                db,
                job_id=job_id,
                limit=limit or 5,
            )
        return applicant_import.sync_applicants_from_odoo(
            db,
            job_id=job_id,
            limit=limit,
        )
    except (integration.OdooDisabled, integration.OdooNotConfigured) as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except applicant_import.OdooApplicantImportError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"No fue posible importar los candidatos desde Odoo: {exc}",
        )


@router.post("/employees/import")
def import_employees_from_odoo(
    db: Session = Depends(get_db),
    principal: dict = Depends(require_permission("employees.create")),
):
    """Import every Odoo hr.employee record without creating Cognito access."""
    try:
        return employee_import.sync_employees_from_odoo(
            db,
            actor_sub=principal.get("sub"),
        )
    except (integration.OdooDisabled, integration.OdooNotConfigured) as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except employee_import.OdooEmployeeImportError:
        raise HTTPException(
            status_code=502,
            detail="No fue posible importar los empleados desde Odoo.",
        )


@router.post("/employees/{employee_id}/sync")
def sync_employee_to_odoo(
    employee_id: str,
    db: Session = Depends(get_db),
    _principal: dict = Depends(require_permission("employees.update")),
):
    try:
        return employee_delivery.sync_employee_now(
            db,
            employee_id=employee_id,
        )
    except employee_delivery.OdooEmployeeSyncNotFound:
        raise HTTPException(
            status_code=404,
            detail="El empleado no tiene una sincronizacion Odoo preparada.",
        )
    except (integration.OdooDisabled, integration.OdooNotConfigured) as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except employee_delivery.OdooEmployeeDeliveryError:
        raise HTTPException(
            status_code=502,
            detail="No fue posible sincronizar el empleado con Odoo.",
        )



@router.post("/employees/{employee_id}/contract/sync")
def sync_employee_contract_to_odoo(
    employee_id: str,
    db: Session = Depends(get_db),
    _principal: dict = Depends(require_permission("employees.update")),
):
    try:
        return contract_delivery.sync_contract_now(
            db,
            employee_id=employee_id,
        )
    except contract_delivery.OdooContractSyncNotFound:
        raise HTTPException(
            status_code=404,
            detail="El empleado no tiene un contrato Odoo preparado.",
        )
    except contract_delivery.OdooContractDependencyError:
        raise HTTPException(
            status_code=409,
            detail="Sincroniza primero el empleado con Odoo.",
        )
    except (integration.OdooDisabled, integration.OdooNotConfigured) as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except contract_delivery.OdooContractDeliveryError:
        raise HTTPException(
            status_code=502,
            detail="No fue posible sincronizar el contrato con Odoo.",
        )


@router.get("/staging/diagnostics")
def staging_readonly_diagnostics(
    _principal: dict = Depends(require_permission("employees.update")),
):
    """Authenticate against the isolated staging API without modifying records."""
    try:
        client = staging.build_staging_client()
        health = client.healthcheck()
        fields = client.fields_get(
            "hr.contract",
            attributes=("type", "readonly", "selection"),
        )
        employee_fields = client.fields_get("hr.employee", attributes=("type",))
    except (integration.OdooNotConfigured, integration.OdooDisabled, OdooClientError) as exc:
        raise HTTPException(status_code=503, detail="Odoo staging is not available.") from exc
    return {
        "environment": "staging",
        "read_only": True,
        "health": health,
        "contract": {
            "has_state": "state" in fields,
            "has_date_end": "date_end" in fields,
            "state_selections": [
                str(item[0])
                for item in (fields.get("state", {}).get("selection") or [])
                if isinstance(item, (tuple, list)) and item
            ],
        },
        "employee": {"has_active": "active" in employee_fields},
    }
