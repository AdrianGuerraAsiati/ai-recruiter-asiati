"""HTTP coverage for employee-owned Talent ID biometric consent."""

from starlette.requests import Request
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app.db import Base
from app.domains.talent_id import consent, router
from app.domains.talent_id.schemas import (
    RecordBiometricConsentRequest,
    RequestBiometricConsentOtp,
    SignBiometricConsentRequest,
)
from app.models import UserProfile


def _db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return engine, Session()


def _employee(db):
    employee = UserProfile(
        cognito_sub="sub-route-consent",
        email="firma@asiati.com.co",
        login_username="firma",
        first_name="Firma",
        last_name="Prueba",
        status="ACTIVE",
    )
    db.add(employee)
    db.commit()
    db.refresh(employee)
    return employee


def _principal(employee):
    return {
        "sub": employee.cognito_sub,
        "profile": {
            "id": employee.id,
            "status": "ACTIVE",
        },
        "roles": ["EMPLOYEE"],
        "permissions": ["profile.read_own"],
    }


def _request():
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/talent-id/consent/sign",
            "headers": [(b"user-agent", b"pytest-consent")],
            "client": ("127.0.0.1", 43123),
            "scheme": "https",
            "server": ("talent.asiaticorp.com", 443),
            "query_string": b"",
        }
    )


def test_employee_can_sign_and_download_own_biometric_decision(monkeypatch):
    engine, db = _db()
    try:
        employee = _employee(db)
        principal = _principal(employee)
        delivered = {}

        monkeypatch.setenv("TALENT_ID_CONSENT_OTP_SECRET", "route-test-secret")
        monkeypatch.setenv("TALENT_ID_CONSENT_OTP_COOLDOWN_SECONDS", "0")

        def fake_send(email, code, ttl):
            delivered.update(email=email, code=code, ttl=ttl)

        monkeypatch.setattr(router, "send_consent_otp", fake_send)

        initial = router.get_my_biometric_consent(
            db=db,
            principal=principal,
        )
        assert initial["status"] == "PENDING"
        assert initial["document"]["version"] == consent.BIOMETRIC_CONSENT_VERSION

        challenge = router.request_my_biometric_consent_otp(
            body=RequestBiometricConsentOtp(
                decision="AUTHORIZED",
                document_version=consent.BIOMETRIC_CONSENT_VERSION,
            ),
            db=db,
            principal=principal,
        )
        assert challenge["delivery"] == "EMAIL"
        assert delivered["email"] == employee.email

        signed = router.sign_my_biometric_consent(
            body=SignBiometricConsentRequest(
                decision="AUTHORIZED",
                otp=delivered["code"],
                document_version=consent.BIOMETRIC_CONSENT_VERSION,
            ),
            request=_request(),
            db=db,
            principal=principal,
        )
        assert signed["status"] == "AUTHORIZED"
        assert signed["has_signed_document"] is True

        response = router.download_my_biometric_consent(
            db=db,
            principal=principal,
        )
        assert response.media_type == "application/pdf"
        assert bytes(response.body).startswith(b"%PDF")
    finally:
        db.close()
        engine.dispose()


def test_employee_can_explicitly_decline_biometrics(monkeypatch):
    engine, db = _db()
    try:
        employee = _employee(db)
        principal = _principal(employee)
        delivered = {}

        monkeypatch.setenv("TALENT_ID_CONSENT_OTP_SECRET", "route-test-secret")
        monkeypatch.setenv("TALENT_ID_CONSENT_OTP_COOLDOWN_SECONDS", "0")
        monkeypatch.setattr(
            router,
            "send_consent_otp",
            lambda email, code, ttl: delivered.update(code=code),
        )

        router.request_my_biometric_consent_otp(
            body=RequestBiometricConsentOtp(
                decision="DENIED",
                document_version=consent.BIOMETRIC_CONSENT_VERSION,
            ),
            db=db,
            principal=principal,
        )
        signed = router.sign_my_biometric_consent(
            body=SignBiometricConsentRequest(
                decision="DENIED",
                otp=delivered["code"],
                document_version=consent.BIOMETRIC_CONSENT_VERSION,
            ),
            request=_request(),
            db=db,
            principal=principal,
        )

        assert signed["status"] == "DENIED"
    finally:
        db.close()
        engine.dispose()


def test_employee_can_accept_biometrics_with_authenticated_checkbox():
    engine, db = _db()
    try:
        employee = _employee(db)
        principal = _principal(employee)

        initial = router.get_my_biometric_consent(
            db=db,
            principal=principal,
        )
        assert initial["status"] == "PENDING"

        accepted = router.accept_my_biometric_consent(
            body=RecordBiometricConsentRequest(
                document_version=consent.BIOMETRIC_CONSENT_VERSION,
                confirmed=True,
            ),
            request=_request(),
            db=db,
            principal=principal,
        )

        assert accepted["status"] == "AUTHORIZED"
        assert accepted["has_signed_document"] is True

        response = router.download_my_biometric_consent(
            db=db,
            principal=principal,
        )
        assert response.media_type == "application/pdf"
        assert bytes(response.body).startswith(b"%PDF")
    finally:
        db.close()
        engine.dispose()


def test_employee_can_revoke_authenticated_checkbox_consent(monkeypatch):
    engine, db = _db()
    try:
        employee = _employee(db)
        principal = _principal(employee)

        router.accept_my_biometric_consent(
            body=RecordBiometricConsentRequest(
                document_version=consent.BIOMETRIC_CONSENT_VERSION,
                confirmed=True,
            ),
            request=_request(),
            db=db,
            principal=principal,
        )

        monkeypatch.setattr(router, "_disable_biometrics_after_opt_out", lambda *_args: None)

        revoked = router.revoke_my_biometric_consent(
            body=RecordBiometricConsentRequest(
                document_version=consent.BIOMETRIC_CONSENT_VERSION,
                confirmed=True,
            ),
            request=_request(),
            db=db,
            principal=principal,
        )
        assert revoked["status"] == "REVOKED"
    finally:
        db.close()
        engine.dispose()
