"""AWS Secrets Manager reader for the Odoo external API credential."""

from __future__ import annotations

import json
import os
from typing import Any

import boto3
from botocore.exceptions import ClientError

from app.config import get_aws_region, get_odoo_settings


class OdooSecretStore:
    """Read the Odoo API credential document without exposing it to responses/logs."""

    def __init__(self, secret_id: str | None = None, *, client: Any | None = None) -> None:
        self.secret_id = (secret_id or get_odoo_settings().secret_id).strip()
        if client is not None:
            self._client = client
            return

        profile_name = os.getenv("BEDROCK_AWS_PROFILE", "").strip() or None
        session = boto3.Session(profile_name=profile_name)
        self._client = session.client("secretsmanager", region_name=get_aws_region())

    def read(self) -> dict:
        if not self.secret_id:
            return {}
        try:
            response = self._client.get_secret_value(SecretId=self.secret_id)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") == "ResourceNotFoundException":
                return {}
            raise

        raw = response.get("SecretString") or "{}"
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError) as exc:
            raise RuntimeError("ODOO_SECRET_INVALID") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("ODOO_SECRET_INVALID")
        return payload
