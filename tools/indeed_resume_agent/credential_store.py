from __future__ import annotations

SERVICE_NAME = "ASIATI Resume Agent"
USERNAME = "agent-token"

COMPUTRABAJO_SERVICE_NAME = "ASIATI Candidate Agent - Computrabajo"
COMPUTRABAJO_USERNAME_KEY = "username"
COMPUTRABAJO_PASSWORD_KEY = "password"


class AgentCredentialMissing(RuntimeError):
    pass


class ProviderCredentialMissing(RuntimeError):
    pass


def _load_keyring():
    import keyring
    return keyring


def read_agent_token() -> str:
    token = str(_load_keyring().get_password(SERVICE_NAME, USERNAME) or "").strip()
    if not token:
        raise AgentCredentialMissing(
            "No hay credencial del ASIATI Resume Agent en Windows Credential Manager."
        )
    return token


def write_agent_token(token: str) -> None:
    value = str(token or "").strip()
    if len(value) < 32:
        raise ValueError("Agent token must contain at least 32 characters")
    _load_keyring().set_password(SERVICE_NAME, USERNAME, value)


def delete_agent_token() -> None:
    _load_keyring().delete_password(SERVICE_NAME, USERNAME)


def read_computrabajo_credentials() -> tuple[str, str]:
    """Read recruiter credentials from Windows Credential Manager only."""
    keyring = _load_keyring()
    username = str(
        keyring.get_password(COMPUTRABAJO_SERVICE_NAME, COMPUTRABAJO_USERNAME_KEY)
        or ""
    ).strip()
    password = str(
        keyring.get_password(COMPUTRABAJO_SERVICE_NAME, COMPUTRABAJO_PASSWORD_KEY)
        or ""
    )
    if not username or not password:
        raise ProviderCredentialMissing(
            "No hay credenciales de Computrabajo en Windows Credential Manager."
        )
    return username, password


def write_computrabajo_credentials(username: str, password: str) -> None:
    """Persist recruiter credentials without writing them to files or environment."""
    normalized_username = str(username or "").strip()
    normalized_password = str(password or "")
    if not normalized_username or "@" not in normalized_username:
        raise ValueError("Computrabajo username must be a valid email address")
    if not normalized_password:
        raise ValueError("Computrabajo password must not be empty")

    keyring = _load_keyring()
    keyring.set_password(
        COMPUTRABAJO_SERVICE_NAME,
        COMPUTRABAJO_USERNAME_KEY,
        normalized_username,
    )
    keyring.set_password(
        COMPUTRABAJO_SERVICE_NAME,
        COMPUTRABAJO_PASSWORD_KEY,
        normalized_password,
    )


def delete_computrabajo_credentials() -> None:
    keyring = _load_keyring()
    for key in (COMPUTRABAJO_USERNAME_KEY, COMPUTRABAJO_PASSWORD_KEY):
        try:
            keyring.delete_password(COMPUTRABAJO_SERVICE_NAME, key)
        except Exception:
            pass
