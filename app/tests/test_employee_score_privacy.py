"""Permission contract for employee score administration."""

from app.access_control import ADMIN, ROLE_PERMISSION_MATRIX


def test_private_score_permissions_belong_to_admin():
    score_permissions = {
        "employee_scores.read",
        "employee_scores.create",
        "employee_scores.correct",
        "employee_scores.export",
    }

    assert score_permissions.issubset(ROLE_PERMISSION_MATRIX[ADMIN])
