"""Contract coverage for RBAC protection on recruiter-facing routes."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


ROUTE_PERMISSIONS = {
    "app/domains/jobs/router.py": "jobs.read",
    "app/domains/candidates/router.py": "candidates.read",
    "app/domains/ranking/router.py": "ranking.read",
    "app/domains/evaluations/router.py": "candidates.evaluate",
    "app/domains/candidate_imports/router.py": "candidates.read",
    "app/domains/indeed/router.py": "integrations.manage",
    "app/domains/psychotechnical/router.py": "psychotechnical.read",
}


def test_recruitment_routes_require_internal_permissions():
    for relative_path, permission in ROUTE_PERMISSIONS.items():
        text = (ROOT / relative_path).read_text(encoding="utf-8")
        assert "require_permission" in text, relative_path
        assert f'Depends(require_permission("{permission}"))' in text, relative_path
        assert "Depends(get_current_user)" not in text, relative_path


WRITE_ROUTE_PERMISSIONS = {
    "app/domains/jobs/router.py": {
        "enrich_job": "jobs.manage",
        "create_job": "jobs.manage",
        "update_job": "jobs.manage",
        "delete_job": "jobs.manage",
    },
    "app/domains/candidates/router.py": {
        "assign_candidates_to_job": "candidates.manage",
        "update_application_status": "candidates.manage",
        "upload_candidates_bulk": "candidates.manage",
    },
    "app/domains/ranking/router.py": {
        "recalculate_ranking_endpoint": "ranking.recalculate",
    },
    "app/domains/candidate_imports/router.py": {
        "create_import_batch": "candidates.manage",
        "complete_import_batch": "candidates.manage",
    },
    "app/domains/odoo_sync/router.py": {
        "sync_employee_to_odoo": "employees.update",
    },
    "app/domains/psychotechnical/router.py": {
        "create_assignment": "psychotechnical.manage",
        "cancel_assignment": "psychotechnical.manage",
    },
}


def _function_block(text: str, function_name: str) -> str:
    marker = f"def {function_name}("
    start = text.index(marker)
    next_route = text.find("\n\n@", start)
    return text[start:] if next_route == -1 else text[start:next_route]


def test_recruitment_mutations_require_write_permissions():
    for relative_path, functions in WRITE_ROUTE_PERMISSIONS.items():
        text = (ROOT / relative_path).read_text(encoding="utf-8")
        for function_name, permission in functions.items():
            block = _function_block(text, function_name)
            assert (
                f'Depends(require_permission("{permission}"))' in block
            ), f"{relative_path}:{function_name}"
