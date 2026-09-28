from tools.indeed_resume_agent.browser_diagnostics import (
    safe_diagnostic_text,
    safe_diagnostic_url,
)


def test_safe_diagnostic_url_removes_query_and_fragment():
    assert (
        safe_diagnostic_url(
            "https://employers.indeed.com/resume/abc?token=secret#section"
        )
        == "https://employers.indeed.com/resume/abc"
    )


def test_safe_diagnostic_url_rejects_non_http_schemes():
    assert safe_diagnostic_url("javascript:alert(1)") == ""
    assert safe_diagnostic_url("") == ""


def test_safe_diagnostic_text_redacts_url_secrets_and_assignments():
    value = (
        "request https://employers.indeed.com/resume/abc?token=secret&sig=hidden "
        "authorization=topsecret api_key=anothersecret"
    )

    safe = safe_diagnostic_text(value)

    assert "secret" not in safe
    assert "hidden" not in safe
    assert "topsecret" not in safe
    assert "anothersecret" not in safe
    assert "https://employers.indeed.com/resume/abc" in safe
    assert "authorization=[REDACTED]" in safe
    assert "api_key=[REDACTED]" in safe


def test_safe_diagnostic_text_enforces_non_negative_limit():
    assert safe_diagnostic_text("abcdef", limit=3) == "abc"
    assert safe_diagnostic_text("abcdef", limit=-1) == ""
