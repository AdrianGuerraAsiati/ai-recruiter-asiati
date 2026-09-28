from tools.indeed_resume_agent.browser_diagnostics import (
    diagnostic_controls,
    diagnostic_request_event,
    diagnostic_response_event,
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


class FakeRequest:
    method = "GET"
    resource_type = "fetch"
    url = "https://employers.indeed.com/candidates?token=secret"


class FakeResponse:
    status = 200
    url = "https://employers.indeed.com/candidates/resume?token=secret"
    request = FakeRequest()
    headers = {
        "content-type": "application/octet-stream",
        "content-disposition": 'attachment; filename="Candidate.pdf"; token=secret',
        "content-length": "9",
        "set-cookie": "must-not-be-recorded",
    }

    def body(self):
        return b"%PDF-test"


def test_diagnostic_request_event_sanitizes_url():
    event = diagnostic_request_event(FakeRequest())

    assert event == {
        "kind": "request",
        "method": "GET",
        "resource_type": "fetch",
        "url": "https://employers.indeed.com/candidates",
    }


def test_diagnostic_response_event_keeps_only_safe_metadata_and_pdf_probe():
    event = diagnostic_response_event(FakeResponse())

    serialized = str(event)
    assert event["url"] == "https://employers.indeed.com/candidates/resume"
    assert event["starts_with_pdf"] is True
    assert event["body_size"] == 9
    assert "secret" not in serialized
    assert "must-not-be-recorded" not in serialized


class FakeControlNode:
    def evaluate(self, script):
        return "a"

    def is_visible(self):
        return True

    def get_attribute(self, name):
        values = {
            "href": "https://employers.indeed.com/resume/abc?token=secret",
            "role": "button",
            "aria-label": "Open authorization=secret",
            "data-testid": "resume-link",
        }
        return values.get(name)

    def inner_text(self, timeout=None):
        return "Download token=secret"


class FakeControls:
    def count(self):
        return 1

    def nth(self, index):
        assert index == 0
        return FakeControlNode()


class FakePage:
    def locator(self, selector):
        return FakeControls()


def test_diagnostic_controls_redacts_text_and_targets():
    controls = diagnostic_controls(FakePage())

    assert len(controls) == 1
    control = controls[0]
    assert control["target"] == "https://employers.indeed.com/resume/abc"
    assert control["text"] == "Download token=[REDACTED]"
    assert control["aria_label"] == "Open authorization=[REDACTED]"
    assert "secret" not in str(control)
