"""Both stage vocabularies (legacy and Odoo) must behave the same everywhere."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.domains.candidates import stages
from app.domains.candidates.service import APPLICATION_STATUSES
from app.domains.employee_documents import service as documents_service
from app.domains.employee_documents.models import EmployeeDocument
from app.domains.indeed import dispositions
from app.domains.recruitment_calendar import service as calendar_service
from app.models import UserProfile


@pytest.mark.parametrize("status", sorted(APPLICATION_STATUSES))
def test_every_application_status_maps_to_indeed_without_error(status):
    # Previously the Odoo stages raised IndeedValidationError -> HTTP 500.
    dispositions.map_local_status(status)


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("INITIAL_QUALIFICATION", "POSITIVELY_SCREENED"),
        ("FIRST_INTERVIEW", "INTERVIEW"),
        ("SECOND_INTERVIEW", "INTERVIEW"),
        ("CONTRACT_PROPOSAL", "OFFER_MADE"),
        ("CONTRACT_SIGNED", None),
    ],
)
def test_odoo_stages_map_to_equivalent_indeed_dispositions(status, expected):
    assert dispositions.map_local_status(status) == expected


@pytest.mark.parametrize("status", ["FIRST_INTERVIEW", "SECOND_INTERVIEW", "CONTRACT_PROPOSAL"])
def test_calendar_accepts_odoo_interview_stages(status):
    assert status in calendar_service.ELIGIBLE_APPLICATION_STATUSES


@pytest.mark.parametrize(
    "status",
    ["APPLIED", "SCREENING", "INITIAL_QUALIFICATION", "REJECTED", "WITHDRAWN", "ON_HOLD"],
)
def test_calendar_still_rejects_inactive_or_unscreened_applications(status):
    assert status not in calendar_service.ELIGIBLE_APPLICATION_STATUSES


@pytest.mark.parametrize("status", ["SELECTED", "OFFER", "CONTRACT_PROPOSAL"])
def test_contract_ready_covers_both_vocabularies(status):
    assert stages.is_contract_ready(status)


@pytest.mark.parametrize("status", ["APPLIED", "FIRST_INTERVIEW", "SECOND_INTERVIEW", "REJECTED"])
def test_contract_not_ready_before_proposal(status):
    assert not stages.is_contract_ready(status)


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("APPLIED", False),
        ("FIRST_INTERVIEW", False),
        ("SELECTED", True),
        ("CONTRACT_PROPOSAL", True),
        ("CONTRACT_SIGNED", True),
        ("REJECTED", False),
        ("ON_HOLD", False),
    ],
)
def test_creating_access_never_moves_later_stages_back(status, expected):
    assert stages.is_at_or_beyond(status, "SELECTED") is expected


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _contract(db, **fields) -> EmployeeDocument:
    employee = UserProfile(email="contrato@asiati.com.co", status="ACTIVE")
    db.add(employee)
    db.flush()
    document = EmployeeDocument(
        employee_id=employee.id,
        document_type="EMPLOYMENT_CONTRACT",
        original_filename="contrato.pdf",
        storage_key=f"documents/{employee.id}/contrato.pdf",
        **fields,
    )
    db.add(document)
    db.commit()
    return document


def test_changes_cannot_be_requested_on_a_contract_in_odoo_sign(db):
    document = _contract(db, odoo_sign_request_id=77)

    with pytest.raises(ValueError, match="no se pueden solicitar cambios"):
        documents_service.review_document(
            db,
            document_id=document.id,
            status="CHANGES_REQUESTED",
            comment="Corregir salario",
            reviewed_by_sub="admin",
        )


def test_locked_contract_can_still_be_approved(db):
    document = _contract(db, odoo_sign_status="PREPARED")

    reviewed = documents_service.review_document(
        db,
        document_id=document.id,
        status="APPROVED",
        comment=None,
        reviewed_by_sub="admin",
    )

    assert reviewed.review_status == "APPROVED"


def test_unlocked_contract_accepts_change_requests(db):
    document = _contract(db)

    reviewed = documents_service.review_document(
        db,
        document_id=document.id,
        status="CHANGES_REQUESTED",
        comment="Falta la firma del empleado",
        reviewed_by_sub="admin",
    )

    assert reviewed.review_status == "CHANGES_REQUESTED"
