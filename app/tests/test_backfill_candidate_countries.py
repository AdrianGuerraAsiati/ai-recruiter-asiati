"""Tests for historical candidate-country backfill."""

from types import SimpleNamespace

from app.domains.candidates.country import CountryInference
from app.scripts import backfill_candidate_countries as script


class _Query:
    def __init__(self, candidates):
        self.candidates = candidates

    def order_by(self, *_args):
        return self

    def limit(self, value):
        self.candidates = self.candidates[:value]
        return self

    def all(self):
        return list(self.candidates)


class _Db:
    def __init__(self, candidates):
        self.candidates = candidates
        self.commits = 0
        self.rollbacks = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def query(self, _model):
        return _Query(self.candidates)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def refresh(self, _candidate):
        return None


def _candidate(candidate_id, *, country=None, metadata=None):
    return SimpleNamespace(
        id=candidate_id,
        country_code=country,
        metadata_=metadata or {},
        created_at=None,
    )


def test_backfill_scans_unchecked_cvs_and_skips_manual_or_checked(monkeypatch):
    manual = _candidate(
        "manual",
        country="CL",
        metadata={"country_source": "MANUAL"},
    )
    checked = _candidate(
        "checked",
        country="EC",
        metadata={
            "country_source": "CV_EXPLICIT",
            "country_checked_at": "2026-10-07T00:00:00+00:00",
        },
    )
    missing = _candidate("missing")
    resolved = _candidate("resolved", country="CL")

    db = _Db([manual, checked, missing, resolved])
    monkeypatch.setattr(script, "SessionLocal", lambda: db)

    def _read(candidate_id):
        if candidate_id == "missing":
            return None
        if candidate_id == "resolved":
            return b"pdf-bytes", "cv-resolved.pdf"
        raise AssertionError(candidate_id)

    monkeypatch.setattr(
        script.storage,
        "read_existing_canonical_document_with_filename",
        _read,
    )
    parsed = SimpleNamespace(header_text="Bogotá, Colombia", text="x", phone=None)
    monkeypatch.setattr(script.documents, "extract_document", lambda *_args: parsed)

    def _apply(_db, *, candidate, parsed_document, use_ai):
        assert use_ai is True
        assert parsed_document is parsed
        candidate.country_code = "CO"
        candidate.metadata_ = {
            **candidate.metadata_,
            "country_source": "CV_EXPLICIT",
            "country_checked_at": "now",
        }
        return CountryInference("CO", "CV_EXPLICIT", "HIGH")

    monkeypatch.setattr(script.candidate_country, "apply_country_inference", _apply)

    result = script.run()

    assert result["total_candidates"] == 4
    assert result["manual_preserved"] == 1
    assert result["already_checked"] == 1
    assert result["scanned"] == 2
    assert result["no_document"] == 1
    assert result["resolved_from_cv"] == 1
    assert result["resolved_deterministically"] == 1
    assert result["by_country"]["CO"] == 1
    assert result["by_country"]["CL"] == 1
    assert result["by_country"]["EC"] == 1
    assert result["by_country"]["UNRESOLVED"] == 1
    assert missing.metadata_["country_review_status"] == "NO_CANONICAL_CV"


def test_backfill_no_ai_and_limit_are_forwarded(monkeypatch):
    candidate = _candidate("one")
    extra = _candidate("two")
    db = _Db([candidate, extra])
    monkeypatch.setattr(script, "SessionLocal", lambda: db)
    monkeypatch.setattr(
        script.storage,
        "read_existing_canonical_document_with_filename",
        lambda _candidate_id: (b"doc", "cv-one.pdf"),
    )
    parsed = SimpleNamespace(header_text="Quito", text="Quito", phone=None)
    monkeypatch.setattr(script.documents, "extract_document", lambda *_args: parsed)

    observed = {}

    def _apply(_db, *, candidate, parsed_document, use_ai):
        observed["candidate_id"] = candidate.id
        observed["use_ai"] = use_ai
        candidate.country_code = "EC"
        candidate.metadata_ = {
            "country_source": "CV_CITY",
            "country_checked_at": "now",
        }
        return CountryInference("EC", "CV_CITY", "HIGH")

    monkeypatch.setattr(script.candidate_country, "apply_country_inference", _apply)

    result = script.run(use_ai=False, limit=1)

    assert result["total_candidates"] == 1
    assert observed == {"candidate_id": "one", "use_ai": False}



def test_backfill_rechecks_stale_unresolved_country_after_inference_upgrade(monkeypatch):
    candidate = _candidate(
        "stale-unresolved",
        metadata={
            "country_source": "CV_UNRESOLVED",
            "country_checked_at": "2026-10-07T00:00:00+00:00",
        },
    )
    db = _Db([candidate])
    monkeypatch.setattr(script, "SessionLocal", lambda: db)
    monkeypatch.setattr(
        script.storage,
        "read_existing_canonical_document_with_filename",
        lambda _candidate_id: (b"doc", "cv.pdf"),
    )
    parsed = SimpleNamespace(
        header_text="Ana Test",
        text="Lugar de residencia: Pereira, Risaralda",
        phone=None,
    )
    monkeypatch.setattr(script.documents, "extract_document", lambda *_args: parsed)

    def _apply(_db, *, candidate, parsed_document, use_ai):
        assert parsed_document is parsed
        assert use_ai is True
        candidate.country_code = "CO"
        candidate.metadata_ = {
            **candidate.metadata_,
            "country_source": "CV_LOCATION_LABEL",
            "country_checked_at": "now",
            "country_inference_version": script.candidate_country.COUNTRY_INFERENCE_VERSION,
        }
        return CountryInference("CO", "CV_LOCATION_LABEL", "HIGH")

    monkeypatch.setattr(script.candidate_country, "apply_country_inference", _apply)

    result = script.run()

    assert result["scanned"] == 1
    assert result["rechecked_for_inference_version"] == 1
    assert result["resolved_from_cv"] == 1
    assert result["by_country"]["CO"] == 1
