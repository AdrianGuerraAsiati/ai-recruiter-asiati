"""Domain policies for protected training resources."""

from app.domains.training.errors import TrainingStateError
from app.domains.training.models import TrainingCourse


def is_system_managed_course(course: TrainingCourse) -> bool:
    return bool(getattr(course, "managed_by_system", False)) or (
        bool(course.is_onboarding)
        and str(course.title or "").strip() == "Onboarding ASIATI"
    )


def validate_system_managed_course_update(
    course: TrainingCourse,
    *,
    is_onboarding: bool | None,
    status: str | None,
) -> None:
    if not is_system_managed_course(course):
        return
    if is_onboarding is not None and bool(is_onboarding) != bool(course.is_onboarding):
        raise TrainingStateError(
            "The corporate onboarding classification is managed by the system."
        )
    if status is not None and status.upper() != course.status:
        raise TrainingStateError(
            "The corporate onboarding publication status is managed by the system."
        )
