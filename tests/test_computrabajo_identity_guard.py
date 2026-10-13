from tools.indeed_resume_agent.computrabajo_browser import valid_computrabajo_candidate_name


def test_accepts_plausible_personal_name():
    assert valid_computrabajo_candidate_name("María Fernanda Pérez")
    assert valid_computrabajo_candidate_name("José Luis Rodríguez García")


def test_rejects_vacancy_and_form_labels():
    for invalid in (
        "Oferta Director financiero - Latam",
        "Computrabajo CV",
        "Carnet de conducir",
        "No tengo empleo",
        "Disponibilidad para viajar",
        "", "a", "personal@example.com",
    ):
        assert not valid_computrabajo_candidate_name(invalid)
