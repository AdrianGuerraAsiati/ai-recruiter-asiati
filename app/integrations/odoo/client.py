"""Minimal Odoo 18 external API client.

The client implements only the documented XML-RPC boundary. Business mapping lives
outside this module so the transport can be tested and replaced independently.
"""

from __future__ import annotations

import xmlrpc.client
from collections.abc import Callable, Mapping, Sequence
from typing import Any
from urllib.parse import urlparse


class OdooClientError(RuntimeError):
    """Base error for sanitized Odoo transport failures."""


class OdooUnsafeUrl(OdooClientError):
    pass


class OdooAuthenticationError(OdooClientError):
    pass


class OdooRpcError(OdooClientError):
    pass


def _validated_base_url(value: str) -> str:
    raw = str(value or "").strip().rstrip("/")
    parsed = urlparse(raw)
    if not raw or not parsed.hostname:
        raise OdooUnsafeUrl("ODOO_BASE_URL is required.")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise OdooUnsafeUrl("ODOO_BASE_URL must not contain credentials, query or fragment.")
    local_hosts = {"localhost", "127.0.0.1", "::1"}
    if parsed.scheme != "https" and not (
        parsed.scheme == "http" and parsed.hostname in local_hosts
    ):
        raise OdooUnsafeUrl("Odoo external API requires HTTPS outside localhost.")
    return raw


ProxyFactory = Callable[..., Any]


class OdooXmlRpcClient:
    """Small authenticated client over Odoo's documented /xmlrpc/2 endpoints."""

    def __init__(
        self,
        *,
        base_url: str,
        database: str,
        username: str,
        api_key: str,
        proxy_factory: ProxyFactory | None = None,
    ) -> None:
        self.base_url = _validated_base_url(base_url)
        self.database = str(database or "").strip()
        self.username = str(username or "").strip()
        self._api_key = str(api_key or "").strip()
        if not self.database or not self.username or not self._api_key:
            raise OdooAuthenticationError("Odoo database, username and API key are required.")
        self._proxy_factory = proxy_factory or xmlrpc.client.ServerProxy
        self._common = self._proxy(
            f"{self.base_url}/xmlrpc/2/common"
        )
        self._models = self._proxy(
            f"{self.base_url}/xmlrpc/2/object"
        )
        self._uid: int | None = None

    def _proxy(self, url: str):
        try:
            return self._proxy_factory(url, allow_none=True)
        except TypeError:
            # Simple test doubles may intentionally expose only one positional arg.
            return self._proxy_factory(url)

    def server_version(self) -> dict:
        try:
            payload = self._common.version()
        except (xmlrpc.client.Error, OSError, ValueError) as exc:
            raise OdooRpcError("Odoo version request failed.") from exc
        return dict(payload or {})

    def authenticate(self) -> int:
        if self._uid is not None:
            return self._uid
        try:
            uid = self._common.authenticate(
                self.database,
                self.username,
                self._api_key,
                {},
            )
        except (xmlrpc.client.Error, OSError, ValueError) as exc:
            raise OdooRpcError("Odoo authentication request failed.") from exc
        if not uid:
            raise OdooAuthenticationError("Odoo rejected the configured credentials.")
        self._uid = int(uid)
        return self._uid

    def execute_kw(
        self,
        model: str,
        method: str,
        args: Sequence[Any] | None = None,
        kwargs: Mapping[str, Any] | None = None,
    ) -> Any:
        uid = self.authenticate()
        model_name = str(model or "").strip()
        method_name = str(method or "").strip()
        if not model_name or not method_name:
            raise ValueError("model and method are required")
        try:
            return self._models.execute_kw(
                self.database,
                uid,
                self._api_key,
                model_name,
                method_name,
                list(args or []),
                dict(kwargs or {}),
            )
        except (xmlrpc.client.Error, OSError, ValueError) as exc:
            raise OdooRpcError(
                f"Odoo RPC failed for {model_name}.{method_name}."
            ) from exc

    def fields_get(
        self,
        model: str,
        *,
        attributes: Sequence[str] = (
            "string",
            "type",
            "required",
            "readonly",
            "relation",
        ),
    ) -> dict:
        result = self.execute_kw(
            model,
            "fields_get",
            [],
            {"attributes": list(attributes)},
        )
        return dict(result or {})

    def search_read(
        self,
        model: str,
        domain: Sequence[Any],
        *,
        fields: Sequence[str] | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        kwargs: dict[str, Any] = {}
        if fields is not None:
            kwargs["fields"] = list(fields)
        if limit is not None:
            kwargs["limit"] = int(limit)
        result = self.execute_kw(model, "search_read", [list(domain)], kwargs)
        return list(result or [])

    def create(self, model: str, values: Mapping[str, Any]) -> int:
        return int(self.execute_kw(model, "create", [dict(values)]))

    def write(self, model: str, ids: Sequence[int], values: Mapping[str, Any]) -> bool:
        return bool(self.execute_kw(model, "write", [list(ids), dict(values)]))

    def healthcheck(self) -> dict:
        version = self.server_version()
        uid = self.authenticate()
        return {
            "connected": True,
            "uid": uid,
            "server_version": version.get("server_version"),
            "server_serie": version.get("server_serie"),
            "protocol_version": version.get("protocol_version"),
        }
