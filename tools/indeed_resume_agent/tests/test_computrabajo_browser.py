from tools.indeed_resume_agent.computrabajo_browser import _external_candidate_id


def test_external_id_distinguishes_same_candidate_across_vacancies():
    first = _external_candidate_id(
        "https://empresa.computrabajo.com.co/Company/CvDetail/Detail?oi=offer-a&ids=candidate-1"
    )
    second = _external_candidate_id(
        "https://empresa.computrabajo.com.co/Company/CvDetail/Detail?oi=offer-b&ids=candidate-1"
    )

    assert first == "application:offer-a:ids:candidate-1"
    assert second == "application:offer-b:ids:candidate-1"
    assert first != second


def test_external_id_is_stable_when_only_candidate_identity_exists():
    value = _external_candidate_id(
        "https://empresa.computrabajo.com.co/Company/CvDetail/Detail?ids=candidate-1"
    )

    assert value == "ids:candidate-1"
