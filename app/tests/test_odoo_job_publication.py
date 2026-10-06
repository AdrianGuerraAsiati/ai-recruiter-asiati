"""Vacancy publication from Talent into Odoo hr.job."""

import importlib

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.domains.jobs import service as jobs_service
from app.domains.odoo_sync import models as odoo_models
from app.models import Job


class FakeOdooClient:
    def __init__(
        self,
        *,
        existing=None,
        publication_field="website_published",
        include_location_fields=False,
    ):
        self.existing = existing
        self.publication_field = publication_field
        self.include_location_fields = include_location_fields
        self.created = []
        self.written = []
        self.deleted = []
        self.searches = []

    def fields_get(self, model, **_kwargs):
        assert model == "hr.job"
        fields = {
            "name": {"readonly": False, "type": "char"},
            "description": {"readonly": False, "type": "html"},
            "active": {"readonly": False, "type": "boolean"},
            "no_of_recruitment": {"readonly": False, "type": "integer"},
        }
        if self.publication_field:
            fields[self.publication_field] = {
                "readonly": False,
                "type": "boolean",
            }
        if self.include_location_fields:
            fields["address_id"] = {
                "readonly": False,
                "type": "many2one",
                "relation": "res.partner",
            }
            fields["contract_type_id"] = {
                "readonly": False,
                "type": "many2one",
                "relation": "hr.contract.type",
            }
        return fields

    def search_read(self, model, domain, *, fields=None, limit=None):
        self.searches.append((model, domain, fields, limit))
        if model == "res.partner":
            return [{"id": 33, "city": "Bogotá"}]
        if model == "hr.contract.type":
            return [{"id": 44, "name": "Full-Time"}]
        assert model == "hr.job"
        if domain and domain[0][0] == "id":
            record_id = int(domain[0][2])
            if self.existing and int(self.existing["id"]) == record_id:
                return [{"id": record_id}]
            return []
        if self.existing:
            return [dict(self.existing)]
        return []

    def create(self, model, values):
        assert model == "hr.job"
        self.created.append(dict(values))
        return 501

    def write(self, model, ids, values):
        assert model == "hr.job"
        self.written.append((list(ids), dict(values)))
        return True

    def unlink(self, model, ids):
        assert model == "hr.job"
        self.deleted.append(list(ids))
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


def _job(db, *, status="ACTIVE", title="Backend Developer"):
    job = Job(
        title=title,
        description="<p>Python y AWS</p>",
        owner_sub="admin-sub",
        status=status,
        country_code="CO",
        city="Bogotá",
        employment_type="FULL_TIME",
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def _publication_module():
    return importlib.import_module("app.domains.odoo_sync.job_delivery")


def _sync_model():
    model = getattr(odoo_models, "OdooJobSync", None)
    assert model is not None, "OdooJobSync durable state is required"
    return model


def test_active_talent_vacancy_creates_published_odoo_job(db):
    delivery = _publication_module()
    Sync = _sync_model()
    job = _job(db)
    sync = Sync(
        job_id=job.id,
        idempotency_key=f"job:{job.id}",
        payload={
            "schema_version": 1,
            "operation": "UPSERT_JOB",
            "job": {
                "external_id": job.id,
                "title": job.title,
                "description": job.description,
                "status": "ACTIVE",
                "country_code": "CO",
                "city": "Bogotá",
                "employment_type": "FULL_TIME",
            },
        },
        status="PENDING",
    )
    db.add(sync)
    db.commit()

    client = FakeOdooClient(publication_field="website_published")
    result = delivery.sync_job_now(db, job_id=job.id, client=client)

    assert result["status"] == "SYNCED"
    assert result["action"] == "CREATED"
    assert result["odoo_record_id"] == "501"
    assert client.created == [{
        "name": "Backend Developer",
        "description": "<p>Python y AWS</p>",
        "active": True,
        "no_of_recruitment": 1,
        "website_published": True,
    }]


def test_paused_talent_vacancy_deletes_existing_odoo_job(db):
    delivery = _publication_module()
    Sync = _sync_model()
    job = _job(db, status="PAUSED")
    sync = Sync(
        job_id=job.id,
        idempotency_key=f"job:{job.id}",
        payload={
            "schema_version": 1,
            "operation": "UPSERT_JOB",
            "job": {
                "external_id": job.id,
                "title": job.title,
                "description": job.description,
                "status": "PAUSED",
            },
        },
        status="PENDING",
        odoo_record_id="77",
    )
    db.add(sync)
    db.commit()

    client = FakeOdooClient(
        existing={"id": 77, "name": "Backend Developer"},
        publication_field="is_published",
    )
    result = delivery.sync_job_now(db, job_id=job.id, client=client)

    assert result["action"] == "DELETED"
    assert result["odoo_record_id"] is None
    assert client.created == []
    assert client.written == []
    assert client.deleted == [[77]]
    db.refresh(sync)
    assert sync.odoo_record_id is None


def test_publication_requires_an_odoo_website_publish_field(db):
    delivery = _publication_module()
    Sync = _sync_model()
    job = _job(db)
    sync = Sync(
        job_id=job.id,
        idempotency_key=f"job:{job.id}",
        payload={
            "schema_version": 1,
            "operation": "UPSERT_JOB",
            "job": {
                "external_id": job.id,
                "title": job.title,
                "description": job.description,
                "status": "ACTIVE",
            },
        },
        status="PENDING",
    )
    db.add(sync)
    db.commit()

    with pytest.raises(delivery.OdooJobDeliveryError, match="publication field"):
        delivery.sync_job_now(
            db,
            job_id=job.id,
            client=FakeOdooClient(publication_field=None),
        )


def test_creating_a_talent_job_prepares_and_delivers_odoo_publication(db, monkeypatch):
    delivery = _publication_module()
    Sync = _sync_model()
    delivered = []

    def fake_delivery(_db, *, job_id, client=None):
        delivered.append(job_id)
        return {"job_id": job_id, "status": "SYNCED", "action": "CREATED"}

    monkeypatch.setattr(delivery, "sync_job_now", fake_delivery)

    job = jobs_service.create_job(
        db,
        title="Country Manager Chile",
        description="Liderar la operación.",
        owner_sub="admin-sub",
        country_code="CL",
        city="Santiago",
        employment_type="FULL_TIME",
    )

    sync = db.query(Sync).filter(Sync.job_id == job.id).one()
    assert sync.payload["operation"] == "UPSERT_JOB"
    assert sync.payload["job"]["title"] == "Country Manager Chile"
    assert sync.payload["job"]["status"] == "ACTIVE"
    assert delivered == [job.id]


def test_odoo_outage_does_not_block_talent_job_creation(db, monkeypatch):
    delivery = _publication_module()
    Sync = _sync_model()

    def fail_delivery(_db, *, job_id, client=None):
        raise delivery.OdooJobDeliveryError("Odoo unavailable")

    monkeypatch.setattr(delivery, "sync_job_now", fail_delivery)

    job = jobs_service.create_job(
        db,
        title="Auxiliar administrativo Chile",
        description="Vacante operativa.",
        owner_sub="admin-sub",
        country_code="CL",
        city="Santiago",
        employment_type="FULL_TIME",
    )

    assert job.id
    assert db.query(Job).filter(Job.id == job.id).one().title == job.title
    sync = db.query(Sync).filter(Sync.job_id == job.id).one()
    assert sync.status in {"PENDING", "FAILED"}


def test_existing_single_named_odoo_job_is_adopted_instead_of_duplicated(db):
    delivery = _publication_module()
    Sync = _sync_model()
    job = _job(db)
    sync = Sync(
        job_id=job.id,
        idempotency_key=f"job:{job.id}",
        payload={
            "schema_version": 1,
            "operation": "UPSERT_JOB",
            "job": {
                "external_id": job.id,
                "title": job.title,
                "description": job.description,
                "status": "ACTIVE",
            },
        },
        status="PENDING",
    )
    db.add(sync)
    db.commit()

    client = FakeOdooClient(
        existing={"id": 88, "name": "Backend Developer"},
        publication_field="website_published",
    )
    result = delivery.sync_job_now(db, job_id=job.id, client=client)

    assert result["action"] == "UPDATED"
    assert result["odoo_record_id"] == "88"
    assert client.created == []
    db.refresh(sync)
    assert sync.odoo_record_id == "88"


def test_pausing_never_published_talent_job_does_not_send_it_to_odoo(db, monkeypatch):
    delivery = _publication_module()
    Sync = _sync_model()
    delivered = []

    def fake_delivery(_db, *, job_id, client=None):
        delivered.append(job_id)
        return {"job_id": job_id, "status": "SYNCED", "action": "UPDATED"}

    monkeypatch.setattr(delivery, "sync_job_now", fake_delivery)

    job = jobs_service.create_job(
        db,
        title="Coordinador de transporte",
        description="Coordinar operación.",
        owner_sub="admin-sub",
    )
    delivered.clear()

    updated = jobs_service.update_job(
        db,
        job_id=job.id,
        owner_sub="admin-sub",
        status="PAUSED",
    )

    sync = db.query(Sync).filter(Sync.job_id == job.id).one()
    assert updated.status == "PAUSED"
    assert sync.payload["job"]["status"] == "PAUSED"
    assert sync.status == "SYNCED"
    assert sync.odoo_record_id is None
    assert delivered == []


def test_pausing_previously_published_talent_job_withdraws_it_from_odoo(db, monkeypatch):
    delivery = _publication_module()
    Sync = _sync_model()
    delivered = []

    def fake_delivery(_db, *, job_id, client=None):
        delivered.append(job_id)
        return {"job_id": job_id, "status": "SYNCED", "action": "UPDATED"}

    monkeypatch.setattr(delivery, "sync_job_now", fake_delivery)

    job = jobs_service.create_job(
        db,
        title="Coordinador de operaciones",
        description="Coordinar operación.",
        owner_sub="admin-sub",
    )
    sync = db.query(Sync).filter(Sync.job_id == job.id).one()
    sync.odoo_record_id = "77"
    db.commit()
    delivered.clear()

    updated = jobs_service.update_job(
        db,
        job_id=job.id,
        owner_sub="admin-sub",
        status="PAUSED",
    )

    db.refresh(sync)
    assert updated.status == "PAUSED"
    assert sync.payload["job"]["status"] == "PAUSED"
    assert delivered == [job.id]


def test_sync_all_backfills_existing_talent_vacancies(db):
    delivery = _publication_module()
    Sync = _sync_model()
    active = _job(db, status="ACTIVE", title="Vacante Activa")
    paused = _job(db, status="PAUSED", title="Vacante Pausada")
    client = FakeOdooClient(publication_field="website_published")

    result = delivery.sync_all_jobs_now(db, client=client)

    assert result == {
        "total": 2,
        "active_total": 1,
        "paused_total": 1,
        "attempted": 2,
        "synced": 1,
        "failed": 0,
        "skipped": 1,
    }
    assert db.query(Sync).count() == 2
    assert {
        sync.job_id for sync in db.query(Sync).all()
    } == {active.id, paused.id}
    assert len(client.created) == 1
    assert client.created[0]["website_published"] is True
    assert client.created[0]["active"] is True



def test_job_publication_resolves_existing_location_and_employment_type(db):
    delivery = _publication_module()
    Sync = _sync_model()
    job = _job(db)
    sync = Sync(
        job_id=job.id,
        idempotency_key=f"job:{job.id}",
        payload={
            "schema_version": 1,
            "operation": "UPSERT_JOB",
            "job": {
                "external_id": job.id,
                "title": job.title,
                "description": job.description,
                "status": "ACTIVE",
                "country_code": "CO",
                "city": "Bogotá",
                "employment_type": "FULL_TIME",
            },
        },
        status="PENDING",
    )
    db.add(sync)
    db.commit()

    client = FakeOdooClient(
        publication_field="website_published",
        include_location_fields=True,
    )
    result = delivery.sync_job_now(db, job_id=job.id, client=client)

    assert result["status"] == "SYNCED"
    assert client.created[0]["address_id"] == 33
    assert client.created[0]["contract_type_id"] == 44


def test_paused_never_published_vacancy_is_not_created_in_odoo(db):
    delivery = _publication_module()
    Sync = _sync_model()
    job = _job(db, status="PAUSED", title="Vacante Interna Pausada")
    sync = Sync(
        job_id=job.id,
        idempotency_key=f"job:{job.id}",
        payload={
            "schema_version": 1,
            "operation": "UPSERT_JOB",
            "job": {
                "external_id": job.id,
                "title": job.title,
                "description": job.description,
                "status": "PAUSED",
            },
        },
        status="PENDING",
    )
    db.add(sync)
    db.commit()

    client = FakeOdooClient(publication_field="website_published")
    result = delivery.sync_job_now(db, job_id=job.id, client=client)

    assert result["status"] == "SYNCED"
    assert result["action"] == "SKIPPED"
    assert result["published"] is False
    assert result["odoo_record_id"] is None
    assert client.created == []
    assert client.written == []
    assert client.searches == []


def test_paused_vacancy_clears_stale_odoo_reference_when_record_is_already_absent(db):
    delivery = _publication_module()
    Sync = _sync_model()
    job = _job(db, status="PAUSED", title="Vacante ya eliminada")
    sync = Sync(
        job_id=job.id,
        idempotency_key=f"job:{job.id}",
        payload={
            "schema_version": 1,
            "operation": "UPSERT_JOB",
            "job": {
                "external_id": job.id,
                "title": job.title,
                "description": job.description,
                "status": "PAUSED",
            },
        },
        status="PENDING",
        odoo_record_id="91",
    )
    db.add(sync)
    db.commit()

    client = FakeOdooClient(existing=None)
    result = delivery.sync_job_now(db, job_id=job.id, client=client)

    assert result["action"] == "ALREADY_ABSENT"
    assert result["odoo_record_id"] is None
    assert client.deleted == []
    db.refresh(sync)
    assert sync.odoo_record_id is None


def test_sync_all_reconciles_active_job_even_when_local_sync_marker_is_synced(db):
    delivery = _publication_module()
    Sync = _sync_model()
    job = _job(db, status="ACTIVE", title="Data & Automation Developer")
    sync = Sync(
        job_id=job.id,
        idempotency_key=f"job:{job.id}",
        payload={
            "schema_version": 1,
            "operation": "UPSERT_JOB",
            "job": {
                "external_id": job.id,
                "title": job.title,
                "description": job.description,
                "status": "ACTIVE",
            },
        },
        status="SYNCED",
        odoo_record_id=None,
    )
    db.add(sync)
    db.commit()

    client = FakeOdooClient(publication_field="website_published")
    result = delivery.sync_all_jobs_now(db, client=client)

    assert result["active_total"] == 1
    assert result["attempted"] == 1
    assert result["synced"] == 1
    assert result["failed"] == 0
    assert len(client.created) == 1
    db.refresh(sync)
    assert sync.odoo_record_id == "501"
