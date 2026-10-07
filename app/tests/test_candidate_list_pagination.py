"""Pagination contract for the organization-wide candidates list."""

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.db import Base
from app.domains.candidates import router as candidates_router
from app.models import Candidate, Job, JobCandidate


def _db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine, Session(engine)


def test_candidates_endpoint_returns_fixed_page_of_20_with_metadata():
    engine, db = _db()
    try:
        db.add_all(
            [
                Candidate(name=f"Candidate {index:02d}", owner_sub="owner-1", metadata_={})
                for index in range(1, 26)
            ]
            + [
                Candidate(name=f"Other {index:02d}", owner_sub="owner-2", metadata_={})
                for index in range(1, 4)
            ]
        )
        db.commit()

        payload = candidates_router.list_candidates(
            page=2,
            page_size=20,
            db=db,
            country_code="",
            _user={"sub": "owner-1"},
        )

        assert payload["total"] == 28
        assert payload["page"] == 2
        assert payload["page_size"] == 20
        assert payload["pages"] == 2
        assert len(payload["items"]) == 8
    finally:
        db.close()
        engine.dispose()


def test_candidates_endpoint_supports_alphabetical_name_sort():
    engine, db = _db()
    try:
        db.add_all(
            [
                Candidate(name="Zoe", owner_sub="owner-1", metadata_={}),
                Candidate(name="Ana", owner_sub="owner-1", metadata_={}),
                Candidate(name="Carlos", owner_sub="owner-2", metadata_={}),
            ]
        )
        db.commit()

        ascending = candidates_router.list_candidates(
            page=1,
            page_size=20,
            sort="name_asc",
            country_code="",
            db=db,
            _user={"sub": "owner-1"},
        )
        assert [item["name"] for item in ascending["items"]] == [
            "Ana",
            "Carlos",
            "Zoe",
        ]

        descending = candidates_router.list_candidates(
            page=1,
            page_size=20,
            sort="name_desc",
            country_code="",
            db=db,
            _user={"sub": "owner-1"},
        )
        assert [item["name"] for item in descending["items"]] == [
            "Zoe",
            "Carlos",
            "Ana",
        ]
    finally:
        db.close()
        engine.dispose()


def test_candidates_endpoint_filters_by_assigned_job_country_without_duplicates():
    engine, db = _db()
    try:
        colombia = Job(
            title="Colombia Role",
            description="CO",
            country_code="CO",
            owner_sub="owner-1",
        )
        colombia_two = Job(
            title="Second Colombia Role",
            description="CO2",
            country_code="CO",
            owner_sub="owner-1",
        )
        chile = Job(
            title="Chile Role",
            description="CL",
            country_code="CL",
            owner_sub="owner-1",
        )
        ana = Candidate(name="Ana Colombia", owner_sub="owner-1", metadata_={})
        betty = Candidate(name="Betty Chile", owner_sub="owner-1", metadata_={})
        unassigned = Candidate(name="Sin asignar", owner_sub="owner-1", metadata_={})
        db.add_all([colombia, colombia_two, chile, ana, betty, unassigned])
        db.flush()
        db.add_all(
            [
                JobCandidate(job_id=colombia.id, candidate_id=ana.id),
                JobCandidate(job_id=colombia_two.id, candidate_id=ana.id),
                JobCandidate(job_id=chile.id, candidate_id=betty.id),
            ]
        )
        db.commit()

        payload = candidates_router.list_candidates(
            page=1,
            page_size=20,
            sort="name_asc",
            country_code="co",
            db=db,
            _user={"sub": "owner-1"},
        )

        assert payload["total"] == 1
        assert [item["name"] for item in payload["items"]] == ["Ana Colombia"]
    finally:
        db.close()
        engine.dispose()
