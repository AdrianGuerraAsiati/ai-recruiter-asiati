"""Selected applicant delivery into the real Odoo recruitment models."""

from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.domains.odoo_sync import applicant_delivery
from app.models import Candidate, Job, JobCandidate, OdooApplicantSync


class FakeOdooClient:
    def __init__(self, *, existing_job=None, existing_applicant=None):
        self.existing_job = existing_job
        self.existing_applicant = existing_applicant
        self.created = []
        self.written = []

    def fields_get(self, model, **_kwargs):
        if model == "hr.job":
            return {
                "name": {"readonly": False},
                "company_id": {"readonly": False},
                "description": {"readonly": False},
            }
        if model == "hr.applicant":
            return {
                "partner_name": {"readonly": False},
                "email_from": {"readonly": False},
                "partner_phone": {"readonly": False},
                "job_id": {"readonly": False},
                "stage_id": {"readonly": False},
                "company_id": {"readonly": False},
            }
        if model == "ir.attachment":
            return {
                "name": {"readonly": False},
                "datas": {"readonly": False},
                "res_model": {"readonly": False},
                "res_id": {"readonly": False},
                "description": {"readonly": False},
                "company_id": {"readonly": False},
                "mimetype": {"readonly": True},
            }
        raise AssertionError(model)

    def search_read(self, model, domain, *, fields=None, limit=None):
        if model == "res.company":
            return [{"id": 1, "name": "ASIATI"}]
        if model == "hr.recruitment.stage":
            return [{"id": 2, "name": "Initial Qualification"}]
        if model == "hr.job":
            if domain and domain[0][0] == "id":
                return [{"id": int(domain[0][2])}] if self.existing_job else []
            return [dict(self.existing_job)] if self.existing_job else []
        if model == "hr.applicant":
            if domain and domain[0][0] == "id":
                return [{"id": int(domain[0][2])}] if self.existing_applicant else []
            return [dict(self.existing_applicant)] if self.existing_applicant else []
        if model == "ir.attachment":
            return []
        return []

    def create(self, model, values):
        ids = {"hr.job": 34, "hr.applicant": 55, "ir.attachment": 77}
        self.created.append((model, dict(values)))
        return ids[model]

    def write(self, model, ids, values):
        self.written.append((model, list(ids), dict(values)))
        return True


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _sync(db):
    job = Job(
        title="Backend Developer",
        description="<p>Python y AWS</p>",
        owner_sub="admin-sub",
    )
    candidate = Candidate(
        name="Ana Perez",
        email="ana@example.com",
        owner_sub="admin-sub",
    )
    db.add_all([job, candidate])
    db.flush()
    application = JobCandidate(
        job_id=job.id,
        candidate_id=candidate.id,
        application_status="SELECTED",
    )
    db.add(application)
    db.flush()
    sync = OdooApplicantSync(
        job_candidate_id=application.id,
        idempotency_key=f"application:{application.id}",
        payload={
            "schema_version": 1,
            "operation": "UPSERT_APPLICANT",
            "candidate": {
                "external_id": candidate.id,
                "name": candidate.name,
                "email": candidate.email,
                "phone": "+573001112233",
            },
            "job": {
                "external_id": job.id,
                "title": job.title,
                "description": job.description,
            },
        },
        status="PENDING",
    )
    db.add(sync)
    db.commit()
    return sync


def _document(_candidate_id):
    return SimpleNamespace(
        filename="cv-candidate.pdf",
        content_type="application/pdf",
        data=b"%PDF-test",
    )


def test_sync_selected_application_creates_job_applicant_and_cv(db):
    sync = _sync(db)
    client = FakeOdooClient()

    result = applicant_delivery.sync_applicant_now(
        db,
        application_id=sync.job_candidate_id,
        client=client,
        document_loader=_document,
    )

    assert result["status"] == "SYNCED"
    assert result["company_id"] == 1
    assert result["odoo_job_id"] == "34"
    assert result["odoo_applicant_id"] == "55"
    assert [item[0] for item in client.created] == [
        "hr.job",
        "hr.applicant",
        "ir.attachment",
    ]

    job_values = client.created[0][1]
    assert job_values["name"] == "Backend Developer"
    assert job_values["company_id"] == 1
    assert job_values["description"] == "<p>Python y AWS</p>"

    applicant_values = client.created[1][1]
    assert applicant_values == {
        "partner_name": "Ana Perez",
        "job_id": 34,
        "company_id": 1,
        "email_from": "ana@example.com",
        "partner_phone": "+573001112233",
        "stage_id": 2,
    }

    attachment_values = client.created[2][1]
    assert attachment_values["res_model"] == "hr.applicant"
    assert attachment_values["res_id"] == 55
    assert attachment_values["company_id"] == 1
    assert "mimetype" not in attachment_values
    assert attachment_values["datas"]


def test_sync_reuses_existing_job_and_updates_existing_applicant(db):
    sync = _sync(db)
    client = FakeOdooClient(
        existing_job={"id": 34, "name": "Backend Developer"},
        existing_applicant={"id": 55},
    )

    result = applicant_delivery.sync_applicant_now(
        db,
        application_id=sync.job_candidate_id,
        client=client,
        document_loader=_document,
    )

    assert result["job"]["action"] == "REUSED"
    assert result["applicant"]["action"] == "UPDATED"
    assert [item[0] for item in client.created] == ["ir.attachment"]
    assert any(item[0] == "hr.applicant" and item[1] == [55] for item in client.written)


def test_missing_canonical_cv_marks_sync_failed(db):
    sync = _sync(db)

    with pytest.raises(
        applicant_delivery.OdooApplicantDeliveryError,
        match="Canonical candidate CV was not found",
    ):
        applicant_delivery.sync_applicant_now(
            db,
            application_id=sync.job_candidate_id,
            client=FakeOdooClient(),
            document_loader=lambda _candidate_id: None,
        )

    db.refresh(sync)
    assert sync.status == "FAILED"
    assert sync.odoo_job_id == "34"
    assert sync.odoo_applicant_id == "55"
    assert sync.synced_at is None
