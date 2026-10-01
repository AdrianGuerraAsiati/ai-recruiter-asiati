"""Credential helpers for Talent ID kiosk devices."""

import hashlib
import hmac


def hash_device_secret(secret: str) -> str:
    normalized = str(secret or "").strip()
    if not normalized:
        raise ValueError("device secret is required")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def verify_device_secret(secret: str, expected_hash: str) -> bool:
    try:
        candidate = hash_device_secret(secret)
    except ValueError:
        return False
    return hmac.compare_digest(candidate, expected_hash)
