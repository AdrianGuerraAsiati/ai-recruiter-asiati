import pytest

from tools.indeed_resume_agent.browser_responses import (
    is_resume_download_response,
    response_document,
    response_filename,
    response_filename_raw,
    response_pdf,
)
from tools.indeed_resume_agent.documents import (
    PDF_CONTENT_TYPE,
    InvalidResumeDocument,
)


class FakeResponse:
    def __init__(
        self,
        *,
        status=200,
        content_type="text/html",
        body=b"",
        disposition=None,
        url="",
    ):
        self.status = status
        self.headers = {"content-type": content_type}
        if disposition is not None:
            self.headers["content-disposition"] = disposition
        self.url = url
        self._body = body
        self.body_calls = 0

    def body(self):
        self.body_calls += 1
        return self._body


def test_response_filename_raw_decodes_rfc5987_filename():
    response = FakeResponse(
        disposition="attachment; filename*=UTF-8''CV%20Jos%C3%A9.pdf"
    )

    assert response_filename_raw(response) == "CV José.pdf"
    assert response_filename(response) == "CV José.pdf"


def test_response_filename_uses_default_when_header_is_missing():
    response = FakeResponse()

    assert response_filename_raw(response) == "indeed-resume"
    assert response_filename(response) == "indeed-resume.pdf"


def test_response_document_skips_unlikely_body_when_probe_is_disabled():
    response = FakeResponse(
        content_type="text/html",
        body=b"<html>not a resume</html>",
        url="https://employers.indeed.com/candidates/view?id=abc",
    )

    assert response_document(response, probe_body=False) is None
    assert response.body_calls == 0


def test_response_document_parses_pdf_and_normalizes_filename():
    response = FakeResponse(
        content_type=PDF_CONTENT_TYPE,
        body=b"%PDF-network-response",
        disposition='attachment; filename="candidate.pdf"',
        url="https://employers.indeed.com/api/catws/resume/v2/download",
    )

    document = response_document(response)

    assert document == (
        b"%PDF-network-response",
        PDF_CONTENT_TYPE,
        "candidate.pdf",
    )
    assert response_pdf(response) == b"%PDF-network-response"


def test_response_document_raises_for_declared_invalid_pdf():
    response = FakeResponse(
        content_type=PDF_CONTENT_TYPE,
        body=b"not-a-pdf",
        disposition='attachment; filename="candidate.pdf"',
    )

    with pytest.raises(InvalidResumeDocument):
        response_document(response)


def test_resume_download_response_requires_exact_indeed_endpoint_and_status():
    response = FakeResponse(
        status=200,
        url="https://employers.indeed.com/api/catws/resume/v2/download?candidate=abc",
    )

    assert is_resume_download_response(response) is True

    response.url = "https://evil.example/api/catws/resume/v2/download"
    assert is_resume_download_response(response) is False

    response.url = "https://employers.indeed.com/api/catws/resume/v2/download"
    response.status = 302
    assert is_resume_download_response(response) is False
