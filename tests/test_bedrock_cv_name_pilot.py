from tools.bedrock_cv_name_pilot import verify


def test_accepts_explicit_name_as_review_only():
    name, status, evidence = verify({
        "full_name": "María Fernanda Ruiz",
        "exact_visible_evidence": "Nombre completo: María Fernanda Ruiz",
        "page": 1,
    })
    assert name == "María Fernanda Ruiz"
    assert status == "PENDING_VISUAL_REVIEW"
    assert "María Fernanda Ruiz" in evidence


def test_refuses_job_title():
    name, status, _ = verify({
        "full_name": "Oferta Director financiero - Latam",
        "exact_visible_evidence": "Oferta Director financiero - Latam",
        "page": 1,
    })
    assert name == ""
    assert status == "INVALID_NAME"


def test_refuses_unsubstantiated_name():
    name, status, _ = verify({
        "full_name": "María Fernanda Ruiz",
        "exact_visible_evidence": "Experiencia: 5 años",
        "page": 1,
    })
    assert name == ""
    assert status == "EVIDENCE_MISMATCH"


def test_refuses_unknown_identity():
    name, status, _ = verify({
        "full_name": None,
        "exact_visible_evidence": None,
        "page": 1,
    })
    assert name == ""
    assert status == "NOT_VISIBLE"
