"""No-secret contract tests for the production-safe Odoo.sh staging probe."""
from types import SimpleNamespace

import pytest

from app.scripts.verify_odoo_sign_live_staging import (
    EXPECTED_DATABASE, EXPECTED_HOST, ProbeError, probe,
)


class FakeVersion:
    def __init__(self, series="18.0"):
        self.series = series
        self.calls = 0

    def version(self):
        self.calls += 1
        return {"server_serie": self.series}


@pytest.mark.parametrize("url,db", [
    ("https://asiati.odoo.com", EXPECTED_DATABASE),
    ("http://" + EXPECTED_HOST, EXPECTED_DATABASE),
    ("https://" + EXPECTED_HOST + ".attacker.example", EXPECTED_DATABASE),
    ("https://user:pass@" + EXPECTED_HOST, EXPECTED_DATABASE),
    ("https://" + EXPECTED_HOST + "/somewhere", EXPECTED_DATABASE),
    ("https://" + EXPECTED_HOST + "?redirect=https://example.com", EXPECTED_DATABASE),
    ("https://" + EXPECTED_HOST, "asiati-production"),
])
def test_refuses_unexpected_hosts_and_databases_without_request(url, db):
    calls = []
    with pytest.raises(ProbeError, match="allowlist"):
        probe(url, db, proxy_factory=lambda endpoint: calls.append(endpoint))
    assert calls == []


def test_live_probe_calls_only_unauthenticated_version():
    fake = FakeVersion()
    urls = []
    def client(url):
        urls.append(url)
        return fake

    result = probe(
        "https://" + EXPECTED_HOST, EXPECTED_DATABASE, proxy_factory=client,
    )
    assert urls == ["https://" + EXPECTED_HOST + "/xmlrpc/2/common"]
    assert fake.calls == 1
    assert result["https_xmlrpc_reachable"] is True
    assert result["signature_request_created"] is False
    assert result["authenticated_sign_schema_checked"] is False
    assert result["staging_neutralization_checked"] is False


def test_live_probe_rejects_unexpected_odoo_series():
    with pytest.raises(ProbeError, match="Unexpected Odoo server series"):
        probe("https://" + EXPECTED_HOST, EXPECTED_DATABASE,
              proxy_factory=lambda url: FakeVersion("19.0"))
