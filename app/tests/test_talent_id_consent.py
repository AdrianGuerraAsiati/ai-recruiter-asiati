"""Talent ID biometric consent signature coverage."""

import re

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app.db import Base
from app.domains.talent_id import consent
from app.domains.talent_id import models as talent_models  # noqa: F401
from app.models import UserProfile


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


def _employee(db):
    employee = UserProfile(
        cognito_sub="sub-consent",
        email="ana@asiati.com.co",
        login_username="aperez",
        first_name="Ana",
        last_name="Pérez",
        status="ACTIVE",
    )
    db.add(employee)
    db.commit()
    db.refresh(employee)
    return employee


def test_otp_is_hashed_and_authorization_generates_immutable_pdf(db):
    employee = _employee(db)
    delivered = {}

    def sender(email, code, ttl):
        delivered.update(email=email, code=code, ttl=ttl)

    response = consent.request_otp(
        db,
        employee_id=employee.id,
        otp_secret="test-secret",
        ttl_seconds=600,
        cooldown_seconds=0,
        max_attempts=5,
        send_otp=sender,
    )

    assert response["destination"].endswith("@asiati.com.co")
    assert re.fullmatch(r"\d{6}", delivered["code"])

    challenge = db.query(talent_models.TalentBiometricConsentOtp).one()
    assert challenge.otp_hash != delivered["code"]

    event = consent.sign_decision(
        db,
        employee_id=employee.id,
        decision="AUTHORIZED",
        otp=delivered["code"],
        expected_document_version=consent.BIOMETRIC_CONSENT_VERSION,
        otp_secret="test-secret",
        evidence={"auth_sub": "sub-consent"},
    )

    assert event.decision == "AUTHORIZED"
    assert event.signed_pdf.startswith(b"%PDF")
    assert len(event.pdf_sha256) == 64
    assert consent.current_status(db, employee.id) == "AUTHORIZED"
    assert db.query(talent_models.TalentBiometricConsentEvent).count() == 1


def test_revocation_requires_prior_authorization_and_creates_new_event(db):
    employee = _employee(db)
    codes = []

    def sender(_email, code, _ttl):
        codes.append(code)

    consent.request_otp(
        db,
        employee_id=employee.id,
        otp_secret="test-secret",
        ttl_seconds=600,
        cooldown_seconds=0,
        max_attempts=5,
        send_otp=sender,
    )
    with pytest.raises(consent.ConsentStateError):
        consent.sign_decision(
            db,
            employee_id=employee.id,
            decision="REVOKED",
            otp=codes[-1],
            expected_document_version=consent.BIOMETRIC_CONSENT_VERSION,
            otp_secret="test-secret",
        )

    consent.request_otp(
        db,
        employee_id=employee.id,
        otp_secret="test-secret",
        ttl_seconds=600,
        cooldown_seconds=0,
        max_attempts=5,
        send_otp=sender,
    )
    consent.sign_decision(
        db,
        employee_id=employee.id,
        decision="AUTHORIZED",
        otp=codes[-1],
        expected_document_version=consent.BIOMETRIC_CONSENT_VERSION,
        otp_secret="test-secret",
    )

    consent.request_otp(
        db,
        employee_id=employee.id,
        otp_secret="test-secret",
        ttl_seconds=600,
        cooldown_seconds=0,
        max_attempts=5,
        send_otp=sender,
    )
    consent.sign_decision(
        db,
        employee_id=employee.id,
        decision="REVOKED",
        otp=codes[-1],
        expected_document_version=consent.BIOMETRIC_CONSENT_VERSION,
        otp_secret="test-secret",
    )

    assert consent.current_status(db, employee.id) == "REVOKED"
    assert db.query(talent_models.TalentBiometricConsentEvent).count() == 2
