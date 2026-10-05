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


def _request(db, employee, sender, *, decision="AUTHORIZED"):
    return consent.request_otp(
        db,
        employee_id=employee.id,
        decision=decision,
        expected_document_version=consent.BIOMETRIC_CONSENT_VERSION,
        otp_secret="test-secret",
        ttl_seconds=600,
        cooldown_seconds=0,
        max_attempts=5,
        send_otp=sender,
    )


def test_otp_is_hashed_and_authorization_generates_immutable_pdf(db):
    employee = _employee(db)
    delivered = {}

    def sender(email, code, ttl):
        delivered.update(email=email, code=code, ttl=ttl)

    response = _request(db, employee, sender)

    assert response["destination"].endswith("@asiati.com.co")
    assert response["decision"] == "AUTHORIZED"
    assert response["document_version"] == consent.BIOMETRIC_CONSENT_VERSION
    assert re.fullmatch(r"\d{6}", delivered["code"])

    challenge = db.query(talent_models.TalentBiometricConsentOtp).one()
    assert challenge.otp_hash != delivered["code"]
    assert challenge.decision == "AUTHORIZED"

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


def test_otp_cannot_be_used_for_a_different_decision(db):
    employee = _employee(db)
    codes = []

    def sender(_email, code, _ttl):
        codes.append(code)

    _request(db, employee, sender, decision="AUTHORIZED")

    with pytest.raises(consent.ConsentStateError):
        consent.sign_decision(
            db,
            employee_id=employee.id,
            decision="DENIED",
            otp=codes[-1],
            expected_document_version=consent.BIOMETRIC_CONSENT_VERSION,
            otp_secret="test-secret",
        )

    assert db.query(talent_models.TalentBiometricConsentEvent).count() == 0


def test_revocation_requires_prior_authorization_and_creates_new_event(db):
    employee = _employee(db)
    codes = []

    def sender(_email, code, _ttl):
        codes.append(code)

    with pytest.raises(consent.ConsentStateError):
        _request(db, employee, sender, decision="REVOKED")

    _request(db, employee, sender, decision="AUTHORIZED")
    consent.sign_decision(
        db,
        employee_id=employee.id,
        decision="AUTHORIZED",
        otp=codes[-1],
        expected_document_version=consent.BIOMETRIC_CONSENT_VERSION,
        otp_secret="test-secret",
    )

    _request(db, employee, sender, decision="REVOKED")
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


def test_wrong_otp_increments_attempts_and_never_stores_plaintext(db):
    employee = _employee(db)

    def sender(_email, _code, _ttl):
        return None

    _request(db, employee, sender)

    with pytest.raises(consent.ConsentOtpInvalid):
        consent.sign_decision(
            db,
            employee_id=employee.id,
            decision="AUTHORIZED",
            otp="000000",
            expected_document_version=consent.BIOMETRIC_CONSENT_VERSION,
            otp_secret="test-secret",
        )

    challenge = db.query(talent_models.TalentBiometricConsentOtp).one()
    assert challenge.attempts == 1
    assert challenge.otp_hash != "000000"



def test_consent_otp_requires_employee_email(db):
    employee = UserProfile(
        cognito_sub="sub-no-email",
        email="",
        login_username="sin-correo",
        first_name="Sin",
        last_name="Correo",
        status="ACTIVE",
    )
    db.add(employee)
    db.commit()
    db.refresh(employee)

    with pytest.raises(consent.ConsentOtpUnavailable, match="correo"):
        consent.request_otp(
            db,
            employee_id=employee.id,
            decision="AUTHORIZED",
            expected_document_version=consent.BIOMETRIC_CONSENT_VERSION,
            otp_secret="test-secret",
            ttl_seconds=600,
            cooldown_seconds=0,
            max_attempts=5,
            send_otp=lambda *_args: None,
        )
