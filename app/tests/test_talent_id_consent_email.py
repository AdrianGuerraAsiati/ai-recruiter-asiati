"""AWS SES delivery coverage for Talent ID consent OTP."""

from types import SimpleNamespace

from app.infrastructure import talent_id_consent_email as email_service


class _Client:
    def __init__(self):
        self.calls = []

    def send_email(self, **kwargs):
        self.calls.append(kwargs)
        return {"MessageId": "message-1"}


class _Session:
    def __init__(self, client):
        self._client = client

    def client(self, service_name, region_name=None):
        assert service_name == "sesv2"
        assert region_name == "us-east-2"
        return self._client


def test_send_consent_otp_uses_registered_destination(monkeypatch):
    client = _Client()
    monkeypatch.setattr(
        email_service,
        "get_talent_id_consent_settings",
        lambda: SimpleNamespace(from_email="talent@asiaticorp.com"),
    )
    monkeypatch.setattr(
        email_service,
        "get_cached_session",
        lambda: _Session(client),
    )
    monkeypatch.setattr(email_service, "get_aws_region", lambda: "us-east-2")

    email_service.send_consent_otp(
        "empleado@asiati.com.co",
        "123456",
        600,
    )

    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["FromEmailAddress"] == "talent@asiaticorp.com"
    assert call["Destination"]["ToAddresses"] == ["empleado@asiati.com.co"]
    assert "123456" in call["Content"]["Simple"]["Body"]["Text"]["Data"]



def test_send_mobile_link_otp_uses_talent_sender(monkeypatch):
    client = _Client()
    monkeypatch.setattr(
        email_service,
        "get_talent_id_qr_settings",
        lambda: SimpleNamespace(from_email="talent@asiaticorp.com"),
    )
    monkeypatch.setattr(
        email_service,
        "get_cached_session",
        lambda: _Session(client),
    )
    monkeypatch.setattr(email_service, "get_aws_region", lambda: "us-east-2")

    email_service.send_mobile_link_otp(
        "empleado@asiati.com.co",
        "654321",
        600,
    )

    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["FromEmailAddress"] == "talent@asiaticorp.com"
    assert call["Destination"]["ToAddresses"] == ["empleado@asiati.com.co"]
    assert "654321" in call["Content"]["Simple"]["Body"]["Text"]["Data"]
    assert "vincular" in call["Content"]["Simple"]["Body"]["Text"]["Data"].lower()
