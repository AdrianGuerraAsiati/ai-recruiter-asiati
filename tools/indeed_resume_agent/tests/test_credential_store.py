import pytest

from tools.indeed_resume_agent import credential_store


def test_write_read_and_delete_use_fixed_windows_credential_contract(monkeypatch):
    calls = []
    token = "t" * 40

    class FakeKeyring:
        @staticmethod
        def set_password(service, username, password):
            calls.append(("set", service, username, password))
        @staticmethod
        def get_password(service, username):
            calls.append(("get", service, username))
            return token
        @staticmethod
        def delete_password(service, username):
            calls.append(("delete", service, username))

    monkeypatch.setattr(credential_store, "_load_keyring", lambda: FakeKeyring)
    credential_store.write_agent_token(token)
    assert credential_store.read_agent_token() == token
    credential_store.delete_agent_token()
    assert calls == [
        ("set", "ASIATI Resume Agent", "agent-token", token),
        ("get", "ASIATI Resume Agent", "agent-token"),
        ("delete", "ASIATI Resume Agent", "agent-token"),
    ]


def test_read_rejects_missing_or_blank_token(monkeypatch):
    class FakeKeyring:
        @staticmethod
        def get_password(service, username):
            return "   "

    monkeypatch.setattr(credential_store, "_load_keyring", lambda: FakeKeyring)
    with pytest.raises(credential_store.AgentCredentialMissing):
        credential_store.read_agent_token()


def test_write_rejects_short_token():
    with pytest.raises(ValueError, match="32"):
        credential_store.write_agent_token("short")


def test_computrabajo_credentials_use_separate_windows_credential_entries(monkeypatch):
    calls = []
    values = {
        ("ASIATI Candidate Agent - Computrabajo", "username"): "recruiter@example.com",
        ("ASIATI Candidate Agent - Computrabajo", "password"): "secret-value",
    }

    class FakeKeyring:
        @staticmethod
        def set_password(service, username, password):
            calls.append(("set", service, username, password))
            values[(service, username)] = password

        @staticmethod
        def get_password(service, username):
            calls.append(("get", service, username))
            return values.get((service, username))

        @staticmethod
        def delete_password(service, username):
            calls.append(("delete", service, username))
            values.pop((service, username), None)

    monkeypatch.setattr(credential_store, "_load_keyring", lambda: FakeKeyring)

    credential_store.write_computrabajo_credentials(
        "recruiter@example.com",
        "new-secret",
    )
    assert credential_store.read_computrabajo_credentials() == (
        "recruiter@example.com",
        "new-secret",
    )
    credential_store.delete_computrabajo_credentials()

    assert ("set", "ASIATI Candidate Agent - Computrabajo", "username", "recruiter@example.com") in calls
    assert ("set", "ASIATI Candidate Agent - Computrabajo", "password", "new-secret") in calls


def test_computrabajo_credentials_reject_missing_values(monkeypatch):
    class FakeKeyring:
        @staticmethod
        def get_password(service, username):
            return None

    monkeypatch.setattr(credential_store, "_load_keyring", lambda: FakeKeyring)

    with pytest.raises(credential_store.ProviderCredentialMissing):
        credential_store.read_computrabajo_credentials()
