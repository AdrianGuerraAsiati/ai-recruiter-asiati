"""Live, unauthenticated reachability probe for the EXACT Odoo.sh staging DB.

NO API key, write calls, user records, Odoo Sign requests or emails.
This proves that the endpoint responds, NOT that signing is ready.
"""
from __future__ import annotations

import argparse
import json
import xmlrpc.client
from urllib.parse import urlparse

EXPECTED_HOST = "asiati-test160526-39554181.dev.odoo.com"
EXPECTED_DATABASE = "asiati-test160526-39554181"


class ProbeError(RuntimeError):
    pass


class TimeoutTransport(xmlrpc.client.SafeTransport):
    def make_connection(self, host):
        connection = super().make_connection(host)
        connection.timeout = 10
        return connection


def probe(base_url: str, database: str, *, proxy_factory=None) -> dict:
    parsed = urlparse(base_url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != EXPECTED_HOST
        or parsed.port not in (None, 443)
        or parsed.path not in ("", "/")
        or parsed.params or parsed.query or parsed.fragment
        or parsed.username or parsed.password
        or database != EXPECTED_DATABASE
    ):
        raise ProbeError("The Odoo.sh target does not match the isolated staging allowlist.")

    endpoint = f"https://{EXPECTED_HOST}/xmlrpc/2/common"
    try:
        proxy = (
            proxy_factory(endpoint)
            if proxy_factory
            else xmlrpc.client.ServerProxy(
                endpoint, allow_none=True, transport=TimeoutTransport(),
            )
        )
        version = proxy.version()
        series = version.get("server_serie")
        if not isinstance(series, str) or series != "18.0":
            raise ProbeError("Unexpected Odoo server series; staging validation stopped.")
    except ProbeError:
        raise
    except (xmlrpc.client.Error, OSError, ValueError, TypeError) as exc:
        raise ProbeError("Staging XML-RPC endpoint is unreachable or returned invalid data.") from exc

    return {
        "target": "Odoo.sh isolated staging",
        "database_allowlisted": True,
        "https_xmlrpc_reachable": True,
        "odoo_series": series,
        "authenticated_sign_schema_checked": False,
        "staging_neutralization_checked": False,
        "signature_request_created": False,
        "emails_sent": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only Odoo.sh staging health probe")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--database", required=True)
    arguments = parser.parse_args()
    try:
        result = probe(arguments.base_url, arguments.database)
    except ProbeError as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}))
        raise SystemExit(2) from None
    print(json.dumps({"status": "OK", **result}, sort_keys=True))


if __name__ == "__main__":
    main()
