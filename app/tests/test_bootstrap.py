from app.bootstrap import create_app
from app.main import app


def _critical_paths(application):
    return set(application.openapi()["paths"])


def test_create_app_exposes_critical_routes():
    paths = _critical_paths(create_app())
    assert "/health" in paths
    assert "/api/jobs" in paths
    assert "/api/candidates" in paths
    assert "/api/jobs/{job_id}/ranking" in paths
    assert "/api/jobs/{job_id}/ranking/recalculate" in paths
    assert "/api/integrations/indeed/status" in paths
    assert "/api/integrations/indeed/candidates/sync" in paths
    assert "/api/integrations/indeed/dispositions/sync" in paths
    assert "/api/jobs/{job_id}/integrations/indeed/publish" in paths
    assert "/api/jobs/{job_id}/integrations/indeed/status" in paths
    assert "/api/jobs/{job_id}/integrations/indeed/expire" in paths
    assert "/api/jobs/{job_id}/candidates/{candidate_id}/status" in paths
    assert "/api/recruitment-calendar/events" in paths
    assert "/api/recruitment-calendar/applications" in paths
    assert "/api/recruitment-calendar/events/{event_id}" in paths
    assert "/api/jobs/{job_id}/candidates/{candidate_id}/integrations/indeed" in paths
    assert "/api/employees" in paths
    assert "/api/employees/summary" in paths
    assert "/api/employees/{employee_id}" in paths
    assert "/api/employees/{employee_id}/status" in paths
    assert "/api/employees/{employee_id}/role" in paths
    assert "/api/odoo/employees/{employee_id}/sync" in paths
    assert "/api/direction/employee-scores" in paths
    assert "/api/direction/employee-scores/{employee_id}" in paths
    assert "/api/direction/employee-scores/{employee_id}/events" in paths
    assert "/api/direction/employee-scores/events/{event_id}/void" in paths
    assert "/api/training/courses" in paths
    assert "/api/training/courses/{course_id}" in paths
    assert "/api/training/courses/{course_id}/modules" in paths
    assert "/api/training/modules/{module_id}/lessons" in paths
    assert "/api/training/courses/{course_id}/assignments/{employee_id}" in paths
    assert "/api/training/me" in paths
    assert "/api/training/me/courses/{course_id}" in paths
    assert "/api/training/me/lessons/{lesson_id}/complete" in paths
    assert "/api/training/me/lessons/{lesson_id}/checklist" in paths
    assert "/api/training/courses/{course_id}/quiz" in paths
    assert "/api/training/quizzes/{quiz_id}/questions" in paths
    assert "/api/training/me/courses/{course_id}/quiz" in paths
    assert "/api/training/me/courses/{course_id}/quiz/attempts" in paths
    assert "/api/training/lessons/{lesson_id}/video/upload" in paths
    assert "/api/training/lessons/{lesson_id}/video/complete" in paths


def test_main_app_uses_same_public_contract():
    assert _critical_paths(app) == _critical_paths(create_app())


def test_production_startup_provisions_published_onboarding(monkeypatch):
    import app.bootstrap as bootstrap

    calls = []
    fake_course = type("Course", (), {"modules": [object()] * 8})()

    class FakeDb:
        def commit(self):
            calls.append("commit")

        def close(self):
            calls.append("close")

    monkeypatch.setattr(bootstrap, "get_database_url", lambda: "postgresql://prod")
    monkeypatch.setattr(bootstrap, "SessionLocal", lambda: FakeDb())
    monkeypatch.setattr(
        bootstrap,
        "ensure_rbac_catalog",
        lambda db: calls.append("rbac"),
    )
    monkeypatch.setattr(
        bootstrap.training_service,
        "ensure_published_asiati_onboarding",
        lambda db, created_by_sub: (
            calls.append(("course", created_by_sub)) or fake_course
        ),
    )
    monkeypatch.setattr(
        bootstrap.training_service,
        "ensure_asiati_onboarding_for_active_employees",
        lambda db, course, created_by_sub: (
            calls.append(("assign", course, created_by_sub)) or 3
        ),
    )

    application = bootstrap.create_app()
    startup = application.router.on_startup[0]
    startup()

    assert "rbac" in calls
    assert ("course", bootstrap.training_service.SYSTEM_ONBOARDING_ACTOR) in calls
    assert (
        "assign",
        fake_course,
        bootstrap.training_service.SYSTEM_ONBOARDING_ACTOR,
    ) in calls
    assert "close" in calls
