from __future__ import annotations

import pytest

from tools.indeed_resume_agent.computrabajo_browser import (
    ComputrabajoBrowserUse,
    safe_computrabajo_url,
)
from tools.indeed_resume_agent.platforms import (
    get_platform,
    normalize_platform,
    platform_labels,
)
from tools.indeed_resume_agent.platform_selector import select_platform


def test_platform_registry_exposes_indeed_and_computrabajo():
    assert platform_labels() == ("Indeed", "Computrabajo")
    assert get_platform("indeed").production_ready is True
    assert get_platform("Computrabajo").key == "computrabajo"
    assert get_platform("computrabajo").production_ready is False


def test_platform_normalization_rejects_unknown_values():
    assert normalize_platform("INDEED") == "indeed"
    assert normalize_platform("Computrabajo") == "computrabajo"
    with pytest.raises(ValueError):
        normalize_platform("linkedin")


def test_selector_can_be_pinned_without_tkinter():
    assert (
        select_platform(
            environ={"ASIATI_RESUME_AGENT_PLATFORM": "computrabajo"}
        )
        == "computrabajo"
    )


def test_computrabajo_url_is_https_and_allowlisted():
    assert safe_computrabajo_url() == "https://co.computrabajo.com/"
    assert (
        safe_computrabajo_url("https://www.computrabajo.com.co/")
        == "https://www.computrabajo.com.co/"
    )
    with pytest.raises(ValueError):
        safe_computrabajo_url("http://co.computrabajo.com/")
    with pytest.raises(ValueError):
        safe_computrabajo_url("https://example.com/")


def test_computrabajo_diagnostics_strip_query_strings_and_fragments():
    sanitized = ComputrabajoBrowserUse._safe_diagnostic_url(
        "https://co.computrabajo.com/empresa/candidatos?id=secret#profile"
    )
    assert sanitized == "https://co.computrabajo.com/empresa/candidatos"
    assert (
        ComputrabajoBrowserUse._safe_diagnostic_url(
            "https://example.com/candidate?id=secret"
        )
        == ""
    )
