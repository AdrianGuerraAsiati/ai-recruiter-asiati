"""Country inference coverage for candidate CVs."""

from types import SimpleNamespace

from langchain_core.runnables import RunnableLambda

from app.domains.candidates import country


class _Db:
    def __init__(self):
        self.flushed = 0

    def flush(self):
        self.flushed += 1


def _parsed(*, header="", text=None, phone=None):
    return SimpleNamespace(
        header_text=header,
        text=text if text is not None else header,
        phone=phone,
    )


def test_explicit_country_in_contact_header_wins():
    result = country.infer_country_deterministic(
        _parsed(header="Ana Test\nBogotá, Colombia\nana@example.com")
    )
    assert result.country_code == "CO"
    assert result.source == "CV_EXPLICIT"
    assert result.confidence == "HIGH"


def test_common_surname_is_not_treated_as_colombian_city():
    result = country.infer_country_deterministic(
        _parsed(header="María Pereira\\nIngeniera industrial")
    )
    assert result.country_code is None


def test_phone_prefix_is_medium_confidence_fallback():
    result = country.infer_country_deterministic(
        _parsed(header="Ana Test\nIngeniera", phone="+56 9 1234 5678")
    )
    assert result.country_code == "CL"
    assert result.source == "CV_PHONE"
    assert result.confidence == "MEDIUM"


def test_conflicting_city_and_phone_stays_unresolved():
    result = country.infer_country_deterministic(
        _parsed(header="Ana Test\nQuito", phone="+57 300 1234567")
    )
    assert result.country_code is None
    assert result.source == "CV_CONFLICT"


def test_ai_fallback_accepts_high_confidence_alpha2(monkeypatch):
    monkeypatch.setattr(country, "get_llm", lambda: RunnableLambda(lambda value: value))
    monkeypatch.setattr(
        country,
        "invoke_json_prompt",
        lambda *_args, **_kwargs: {
            "country_code": "CA",
            "confidence": "HIGH",
            "evidence": "Toronto, Canada",
        },
    )

    result = country.infer_country_with_ai(
        _parsed(
            header="Ana Test",
            text="Ana Test\nActualmente resido en Toronto, Canada.",
        )
    )

    assert result.country_code == "CA"
    assert result.source == "CV_AI"
    assert result.confidence == "HIGH"


def test_ai_low_confidence_does_not_assign_country(monkeypatch):
    monkeypatch.setattr(country, "get_llm", lambda: RunnableLambda(lambda value: value))
    monkeypatch.setattr(
        country,
        "invoke_json_prompt",
        lambda *_args, **_kwargs: {
            "country_code": "CO",
            "confidence": "LOW",
            "evidence": "Colombia",
        },
    )

    result = country.infer_country_with_ai(_parsed(header="Ana Test", text="Ana Test"))

    assert result.country_code is None
    assert result.source == "CV_UNRESOLVED"


def test_ai_failure_is_non_fatal(monkeypatch):
    monkeypatch.setattr(country, "get_llm", lambda: RunnableLambda(lambda value: value))

    def _raise(*_args, **_kwargs):
        raise RuntimeError("bedrock unavailable")

    monkeypatch.setattr(country, "invoke_json_prompt", _raise)
    result = country.infer_country_with_ai(_parsed(header="Ana Test", text="Ana Test"))
    assert result.country_code is None
    assert result.source == "CV_AI_FAILED"


def test_manual_country_is_never_overwritten(monkeypatch):
    db = _Db()
    candidate = SimpleNamespace(
        country_code="CL",
        metadata_={
            "country_source": "MANUAL",
            "country_confidence": "HIGH",
        },
    )
    monkeypatch.setattr(
        country,
        "infer_country_with_ai",
        lambda _parsed: country.CountryInference("CO", "CV_EXPLICIT", "HIGH"),
    )

    result = country.apply_country_inference(
        db,
        candidate=candidate,
        parsed_document=_parsed(header="Bogotá, Colombia"),
        use_ai=True,
    )

    assert result.country_code == "CL"
    assert candidate.country_code == "CL"
    assert candidate.metadata_["country_source"] == "MANUAL"
    assert candidate.metadata_["country_review_status"] == "MANUAL_PRESERVED"
    assert db.flushed == 1


def test_cv_country_replaces_non_manual_fallback(monkeypatch):
    db = _Db()
    candidate = SimpleNamespace(
        country_code="CL",
        metadata_={
            "country_source": "JOB_FALLBACK",
            "country_confidence": "LOW",
        },
    )
    monkeypatch.setattr(
        country,
        "infer_country_with_ai",
        lambda _parsed: country.CountryInference(
            "CO", "CV_EXPLICIT", "HIGH", "EXPLICIT_COUNTRY"
        ),
    )

    country.apply_country_inference(
        db,
        candidate=candidate,
        parsed_document=_parsed(header="Bogotá, Colombia"),
        use_ai=True,
    )

    assert candidate.country_code == "CO"
    assert candidate.metadata_["country_previous_code"] == "CL"
    assert candidate.metadata_["country_source"] == "CV_EXPLICIT"
    assert candidate.metadata_["country_review_status"] == "RESOLVED"


def test_unresolved_cv_preserves_existing_country(monkeypatch):
    db = _Db()
    candidate = SimpleNamespace(country_code="CO", metadata_={})
    monkeypatch.setattr(
        country,
        "infer_country_deterministic",
        lambda _parsed: country.CountryInference(
            None, "CV_UNRESOLVED", "LOW", None
        ),
    )

    result = country.apply_country_inference(
        db,
        candidate=candidate,
        parsed_document=_parsed(header="Ana Test"),
        use_ai=False,
    )

    assert result.country_code is None
    assert candidate.country_code == "CO"
    assert candidate.metadata_["country_source"] == "LEGACY_FALLBACK"
    assert candidate.metadata_["country_review_status"] == "CV_UNRESOLVED_FALLBACK"
