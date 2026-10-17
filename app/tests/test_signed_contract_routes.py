"""Endpoint contracts for signature-first hiring; no AWS or Odoo network calls."""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.domains.employee_documents import router as documents
from app.domains.employee_documents import signed_artifacts, sign_requests, signing, service as doc_service
from app.domains.hiring import router as hiring
from app.domains.hiring import service as hiring_service


def test_signed_contract_status_is_scoped_to_exact_employee(monkeypatch):
    calls = []
    monkeypatch.setattr(signed_artifacts, "status", lambda db, employee_id: (
        calls.append(employee_id) or {"archived": True, "sha256": "a" * 64}
    ))
    assert documents.signed_contract_status("one", db=object(), _principal={})["archived"]
    assert documents.own_signed_contract_status(
        db=object(), principal={"profile": {"id": "self"}}
    )["archived"]
    assert calls == ["one", "self"]


def test_archive_endpoint_enforces_domain_failures(monkeypatch):
    monkeypatch.setattr(signed_artifacts, "archive", lambda db, employee_id: {"archived": True})
    assert documents.archive_signed_contract("employee-1", db=object(), _principal={}) == {
        "archived": True
    }

    def not_ready(db, employee_id):
        raise signed_artifacts.ArchiveNotReady("Aún no firmado")
    monkeypatch.setattr(signed_artifacts, "archive", not_ready)
    with pytest.raises(HTTPException) as exc:
        documents.archive_signed_contract("employee-1", db=object(), _principal={})
    assert exc.value.status_code == 409

    def unavailable(db, employee_id):
        raise signed_artifacts.ArchiveUnavailable("Odoo staging inactivo")
    monkeypatch.setattr(signed_artifacts, "archive", unavailable)
    with pytest.raises(HTTPException) as exc:
        documents.archive_signed_contract("employee-1", db=object(), _principal={})
    assert exc.value.status_code == 503


def test_download_endpoints_do_not_mix_users(monkeypatch):
    observed = []
    monkeypatch.setattr(signed_artifacts, "download", lambda db, employee_id: (
        observed.append(employee_id) or {"url": "https://private.example.invalid/signed"}
    ))
    documents.download_signed_contract_as_hr("employee-1", db=object(), _principal={})
    documents.download_own_signed_contract(
        db=object(), principal={"profile": {"id": "employee-2"}}
    )
    assert observed == ["employee-1", "employee-2"]
    def missing(db, employee_id):
        raise signed_artifacts.ArchiveNotReady("Sin contrato firmado")
    monkeypatch.setattr(signed_artifacts, "download", missing)
    with pytest.raises(HTTPException) as exc:
        documents.download_signed_contract_as_hr("one", db=object(), _principal={})
    assert exc.value.status_code == 404
    with pytest.raises(HTTPException) as exc:
        documents.download_own_signed_contract(
            db=object(), principal={"profile": {"id": "two"}}
        )
    assert exc.value.status_code == 404


def test_missing_person_or_document_is_translated(monkeypatch):
    def not_found(db, employee_id):
        raise doc_service.EmployeeNotFound()
    monkeypatch.setattr(signed_artifacts, "status", not_found)
    with pytest.raises(HTTPException) as exc:
        documents.signed_contract_status("missing", db=object(), _principal={})
    assert exc.value.status_code == 404


def test_link_and_refresh_errors_are_sanitized(monkeypatch):
    monkeypatch.setattr(sign_requests, "local_status", lambda db, employee_id: {
        "linked": True, "request_id": 42,
    })
    assert documents.get_staging_sign_request("x", db=object(), _principal={})["linked"]
    monkeypatch.setattr(sign_requests, "track", lambda db, employee_id, request_id=None: {
        "status": "SIGNED", "request_id": request_id or 42,
    })
    body = SimpleNamespace(request_id=42, confirm=True)
    assert documents.link_staging_sign_request(
        "x", body, db=object(), _principal={},
    )["request_id"] == 42
    assert documents.refresh_staging_sign_request("x", db=object(), _principal={})["request_id"] == 42

    def conflict(db, employee_id, request_id=None):
        raise sign_requests.SignTrackingConflict("Solicitud incorrecta")
    monkeypatch.setattr(sign_requests, "track", conflict)
    with pytest.raises(HTTPException) as exc:
        documents.link_staging_sign_request("x", body, db=object(), _principal={})
    assert exc.value.status_code == 409
    with pytest.raises(HTTPException) as exc:
        documents.refresh_staging_sign_request("x", db=object(), _principal={})
    assert exc.value.status_code == 409

    def unavailable(db, employee_id, request_id=None):
        raise sign_requests.SignTrackingUnavailable("Sin permisos")
    monkeypatch.setattr(sign_requests, "track", unavailable)
    with pytest.raises(HTTPException) as exc:
        documents.link_staging_sign_request("x", body, db=object(), _principal={})
    assert exc.value.status_code == 503
    with pytest.raises(HTTPException) as exc:
        documents.refresh_staging_sign_request("x", db=object(), _principal={})
    assert exc.value.status_code == 503


def test_prepare_signature_route_checks_confirmation_and_unavailable(monkeypatch):
    body = SimpleNamespace(confirm=True)
    monkeypatch.setattr(signing, "prepare", lambda db, employee_id: {"status": "PREPARED"})
    assert documents.prepare_employee_contract_in_odoo_sign(
        "x", body, db=object(), _principal={},
    )["status"] == "PREPARED"
    with pytest.raises(HTTPException) as exc:
        documents.prepare_employee_contract_in_odoo_sign(
            "x", SimpleNamespace(confirm=False), db=object(), _principal={},
        )
    assert exc.value.status_code == 422

    def no_pdf(db, employee_id):
        raise signing.SignNotReady("Sin PDF")
    monkeypatch.setattr(signing, "prepare", no_pdf)
    with pytest.raises(HTTPException) as exc:
        documents.prepare_employee_contract_in_odoo_sign(
            "x", body, db=object(), _principal={},
        )
    assert exc.value.status_code == 409

    def disabled(db, employee_id):
        raise signing.SignUnavailable("No configurado")
    monkeypatch.setattr(signing, "prepare", disabled)
    with pytest.raises(HTTPException) as exc:
        documents.prepare_employee_contract_in_odoo_sign(
            "x", body, db=object(), _principal={},
        )
    assert exc.value.status_code == 503


def test_hiring_capabilities_and_precontract_route(monkeypatch):
    monkeypatch.setattr(hiring_service, "signed_contract_hiring_gate_enabled", lambda: True)
    assert hiring.signature_hiring_flow_capabilities(_principal={})["enabled"] is True
    called = []
    def prepare(db, **kwargs):
        called.append(kwargs)
        return {"profile_id": "draft", "access_provisioned": False}
    monkeypatch.setattr(hiring_service, "prepare_candidate_contract_profile", prepare)
    result = hiring.prepare_contract_dossier(
        "job-1", "cand-1", db=object(), principal={"sub": "admin-1"},
    )
    assert result["access_provisioned"] is False
    assert called[0]["owner_sub"] == "admin-1"
    assert called[0]["candidate_id"] == "cand-1"

    def reject(db, **kwargs):
        raise hiring_service.HiringConflictError("Postulación cerrada")
    monkeypatch.setattr(hiring_service, "prepare_candidate_contract_profile", reject)
    with pytest.raises(HTTPException) as exc:
        hiring.prepare_contract_dossier(
            "job-1", "cand-1", db=object(), principal={"sub": "admin-1"},
        )
    assert exc.value.status_code == 409


def test_hiring_readiness_checks_ownership_and_link(monkeypatch):
    from app.domains.candidates import service as candidates
    from app.domains.candidates import repository as candidates_repo
    monkeypatch.setattr(candidates, "require_job", lambda db, job_id, owner_sub: object())
    monkeypatch.setattr(candidates, "require_candidate", lambda db, candidate_id, owner_sub: object())
    monkeypatch.setattr(candidates_repo, "get_job_candidate",
                        lambda db, job_id, candidate_id, owner_sub: SimpleNamespace(employee_id="profile"))
    monkeypatch.setattr(hiring_service, "hiring_signature_readiness", lambda db, link: {
        "enabled": True, "ready": False,
    })
    assert hiring.hire_candidate_readiness(
        "job-1", "candidate-1", db=object(), principal={"sub": "admin"}
    )["ready"] is False

    monkeypatch.setattr(candidates_repo, "get_job_candidate",
                        lambda db, job_id, candidate_id, owner_sub: None)
    with pytest.raises(HTTPException) as exc:
        hiring.hire_candidate_readiness(
            "job-1", "candidate-1", db=object(), principal={"sub": "admin"},
        )
    assert exc.value.status_code == 404


def test_document_dossier_routes_remain_scoped_and_reviewable(monkeypatch):
    uploads = []
    monkeypatch.setattr(doc_service, "portfolio_payload",
                        lambda db, employee_id, include_admin_only=False: {
                            "id": employee_id, "admin": include_admin_only,
                        })
    monkeypatch.setattr(doc_service, "require_employee",
                        lambda db, employee_id: SimpleNamespace(id=employee_id))
    monkeypatch.setattr(doc_service, "create_upload",
                        lambda db, **kw: uploads.append(("prepare", kw)) or {"key": "private"})
    monkeypatch.setattr(doc_service, "finalize_upload",
                        lambda db, **kw: uploads.append(("complete", kw)))
    monkeypatch.setattr(doc_service, "save_value",
                        lambda db, **kw: uploads.append(("value", kw)))
    monkeypatch.setattr(doc_service, "review_queue",
                        lambda db: {"items": []})
    me = {"profile": {"id": "self"}, "sub": "staff"}
    upload = SimpleNamespace(
        document_type="IDENTITY", filename="id.pdf", content_type="application/pdf",
        size_bytes=350, key="training/employee-documents/self/id.pdf",
    )
    assert documents.my_documents(db=object(), principal=me)["id"] == "self"
    assert documents.employee_documents("candidate", db=object(), _principal={})["admin"]
    assert documents.create_my_document_upload(upload, db=object(), principal=me)["key"]
    assert documents.complete_my_document_upload(upload, db=object(), principal=me)["id"] == "self"
    assert uploads[-1][1]["employee_id"] == "self"
    value = SimpleNamespace(document_type="RESIDENCE_ADDRESS", value="Bogotá")
    assert documents.save_my_document_value(value, db=object(), principal=me)["id"] == "self"
    assert documents.document_review_queue(db=object(), _principal={}) == {"items": []}

    contract = SimpleNamespace(
        document_type="EMPLOYMENT_CONTRACT", filename="contract.pdf",
        content_type="application/pdf", size_bytes=340,
        key="training/employee-documents/other/contract.pdf",
    )
    assert documents.create_employee_contract_upload(
        "other", contract, db=object(), _principal={}
    )["key"] == "private"
    assert uploads[-1][1]["admin_upload"] is True
    assert documents.complete_employee_contract_upload(
        "other", contract, db=object(), principal=me
    )["admin"]
    with pytest.raises(HTTPException) as exc:
        documents.create_employee_contract_upload("other", upload, db=object(), _principal={})
    assert exc.value.status_code == 422
    with pytest.raises(HTTPException) as exc:
        documents.complete_employee_contract_upload("other", upload, db=object(), principal=me)
    assert exc.value.status_code == 422


def test_document_download_rejects_unprivileged_contract_reader(monkeypatch):
    record = SimpleNamespace(
        id="contract", employee_id="owner",
        document_type="EMPLOYMENT_CONTRACT",
    )
    monkeypatch.setattr(doc_service, "require_document", lambda db, document_id: record)
    monkeypatch.setattr(doc_service, "download_payload",
                        lambda db, document_id: {"url": "https://private.example.invalid/pdf"})
    with pytest.raises(HTTPException) as exc:
        documents.download_document(
            "contract", db=object(),
            principal={"profile": {"id": "owner"}, "permissions": ["employee_documents.read_own"]},
        )
    assert exc.value.status_code == 403
    assert documents.download_document(
        "contract", db=object(),
        principal={"profile": {"id": "admin"}, "permissions": ["employee_documents.read_all"]},
    )["url"].startswith("https://")


def test_employee_document_review_preserves_admin_only_portfolio(monkeypatch):
    monkeypatch.setattr(doc_service, "review_document",
                        lambda db, **kw: SimpleNamespace(employee_id="owner"))
    monkeypatch.setattr(doc_service, "portfolio_payload",
                        lambda db, employee_id, include_admin_only=False: {
                            "employee_id": employee_id, "admin_only": include_admin_only
                        })
    outcome = documents.review_document(
        "doc-1", SimpleNamespace(status="APPROVED", comment=None),
        db=object(), principal={"sub": "hr-admin"},
    )
    assert outcome == {"employee_id": "owner", "admin_only": True}


def test_signature_preview_endpoint_uses_only_reviewer_and_no_send(monkeypatch):
    from app.domains.employee_documents import sign_dispatch
    received = []
    def fake_preview(db, employee_id, **kwargs):
        received.append((employee_id, kwargs))
        return {"validated": True, "request_created": False, "emails_sent": False}
    monkeypatch.setattr(sign_dispatch, "preview", fake_preview)
    body = SimpleNamespace(employee_partner_id=301, representative_partner_id=302)
    result = documents.preview_staging_sign_request(
        "test-employee", body, db=object(), _principal={},
    )
    assert result["validated"] is True
    assert result["emails_sent"] is False
    assert received == [("test-employee", {
        "employee_partner_id": 301, "representative_partner_id": 302,
    })]

    def not_ready(db, employee_id, **kwargs):
        raise sign_dispatch.DispatchNotReady("Plantilla no aprobada")
    monkeypatch.setattr(sign_dispatch, "preview", not_ready)
    with pytest.raises(HTTPException) as exc:
        documents.preview_staging_sign_request(
            "test-employee", body, db=object(), _principal={},
        )
    assert exc.value.status_code == 409

    def unavailable(db, employee_id, **kwargs):
        raise sign_dispatch.DispatchUnavailable("Staging no configurado")
    monkeypatch.setattr(sign_dispatch, "preview", unavailable)
    with pytest.raises(HTTPException) as exc:
        documents.preview_staging_sign_request(
            "test-employee", body, db=object(), _principal={},
        )
    assert exc.value.status_code == 503

    def unauthorized(db, employee_id, **kwargs):
        raise sign_requests.SignTrackingUnavailable("No autorizado")
    monkeypatch.setattr(sign_dispatch, "preview", unauthorized)
    with pytest.raises(HTTPException) as exc:
        documents.preview_staging_sign_request(
            "test-employee", body, db=object(), _principal={},
        )
    assert exc.value.status_code == 503
