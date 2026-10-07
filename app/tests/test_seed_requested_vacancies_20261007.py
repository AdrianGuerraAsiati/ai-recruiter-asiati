"""Tests for the one-shot enriched vacancy seed."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Job, UserProfile
from app.scripts import seed_requested_vacancies_20261007 as seed


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            UserProfile.__table__,
            Job.__table__,
        ],
    )
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _fake_create_job(db, **kwargs):
    job = Job(
        title=kwargs["title"],
        description=kwargs["description"],
        indeed_description=kwargs["indeed_description"],
        ai_description=kwargs["ai_description"],
        active_description_source=kwargs["active_description_source"],
        evaluation_profile=kwargs["evaluation_profile"],
        owner_sub=kwargs["owner_sub"],
        status=kwargs["status"],
        country_code=kwargs["country_code"],
        company_name=kwargs["company_name"],
        city=kwargs["city"],
        employment_type=kwargs["employment_type"],
        response_time_business_days=kwargs["response_time_business_days"],
        phone_call_count=kwargs["phone_call_count"],
        onsite_interview_count=kwargs["onsite_interview_count"],
        offer_wait_days=kwargs["offer_wait_days"],
        offer_wait_reference=kwargs["offer_wait_reference"],
        public_slug=kwargs["public_slug"],
        published_at=kwargs["published_at"],
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def test_seed_creates_all_requested_jobs_once(db, monkeypatch):
    db.add(
        UserProfile(
            email="talentohumano@asiati.com.co",
            cognito_sub="talent-owner",
            first_name="Talento",
            status="ACTIVE",
        )
    )
    db.commit()
    monkeypatch.setattr(seed.service, "create_job", _fake_create_job)

    first = seed.seed_jobs(db)
    second = seed.seed_jobs(db)

    assert first["requested"] == 17
    assert first["created"] == 17
    assert first["skipped_existing"] == 0
    assert first["failed"] == 0

    assert second["created"] == 0
    assert second["skipped_existing"] == 17
    assert second["failed"] == 0
    assert db.query(Job).count() == 17

    titles = {job.title for job in db.query(Job).all()}
    assert "Head of Marketing Global" in titles
    assert "Head de Selección y Talento Humano" in titles
    assert "Community Manager (2)" in titles
    assert "SAC (2)" in titles


def test_seed_normalizes_source_typo_aliases(db, monkeypatch):
    db.add(
        UserProfile(
            email="talentohumano@asiati.com.co",
            cognito_sub="talent-owner",
            first_name="Talento",
            status="ACTIVE",
        )
    )
    db.add(
        Job(
            title="HEAT OF MARKETING GLOBAL",
            description="Existing",
            owner_sub="talent-owner",
            status="ACTIVE",
        )
    )
    db.commit()
    monkeypatch.setattr(seed.service, "create_job", _fake_create_job)

    result = seed.seed_jobs(db)

    assert result["created"] == 16
    assert result["skipped_existing"] == 1
    assert db.query(Job).count() == 17
