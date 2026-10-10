"""Non-destructive Computrabajo agent integration and security contracts.

These tests avoid live provider login, real candidates, and network calls.
"""
import pytest

from tools.indeed_resume_agent.computrabajo_browser import (
    ComputrabajoBrowserUse,
    safe_computrabajo_url,
)
from tools.indeed_resume_agent.platform_selector import select_platform
from tools.indeed_resume_agent.platforms import get_platform


@pytest.mark.parametrize("url", [
    "http://co.computrabajo.com/",
    "https://computrabajo.com.evil.example/",
    "https://notcomputrabajo.com/",
    "https://example.com/?redirect=computrabajo.com",
    "file:///etc/passwd",
    "javascript:alert(1)",
    "https://computrabajo.com@evil.example/",
    "https://evil.example/path/computrabajo.com",
])
def test_computrabajo_rejects_untrusted_navigation_targets(url):
    with pytest.raises(ValueError, match="COMPUTRABAJO_UNSAFE_URL"):
        safe_computrabajo_url(url)


@pytest.mark.parametrize("url", [
    "https://co.computrabajo.com/",
    "https://empresa.computrabajo.com.co/",
    "https://computrabajo.com/",
])
def test_computrabajo_allows_only_its_own_https_domains(url):
    assert safe_computrabajo_url(url) == url


def test_computrabajo_selector_is_independent_of_indeed():
    assert select_platform(environ={"ASIATI_RESUME_AGENT_PLATFORM": "computrabajo"}) == "computrabajo"
    assert get_platform("computrabajo").production_ready is False
    assert get_platform("indeed").production_ready is True


@pytest.mark.parametrize("url", [
    "https://co.computrabajo.com/empresa/candidatos?token=private#section",
    "https://example.com/?token=private",
])
def test_diagnostics_never_preserve_query_tokens(url):
    value = ComputrabajoBrowserUse._safe_diagnostic_url(url)
    assert "token=" not in value
    assert "#" not in value
    assert "?" not in value
