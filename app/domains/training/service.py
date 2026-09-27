"""Training catalog, assignment and progress services."""

from __future__ import annotations

from datetime import datetime, timezone
import logging

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.infrastructure.storage import training_media
from app.models import (
    TrainingAssignment,
    TrainingCourse,
    TrainingLesson,
    TrainingLessonProgress,
    TrainingModule,
    TrainingQuiz,
    TrainingQuizAttempt,
    TrainingQuizQuestion,
    UserProfile,
)


from app.domains.training.errors import (
    TrainingAssignmentError,
    TrainingNotFound,
    TrainingStateError,
)


logger = logging.getLogger(__name__)


def require_course(db: Session, course_id: str) -> TrainingCourse:
    course = db.query(TrainingCourse).filter(TrainingCourse.id == course_id).one_or_none()
    if course is None:
        raise TrainingNotFound()
    return course


def require_module(db: Session, module_id: str) -> TrainingModule:
    module = db.query(TrainingModule).filter(TrainingModule.id == module_id).one_or_none()
    if module is None:
        raise TrainingNotFound()
    return module


def require_lesson(db: Session, lesson_id: str) -> TrainingLesson:
    lesson = db.query(TrainingLesson).filter(TrainingLesson.id == lesson_id).one_or_none()
    if lesson is None:
        raise TrainingNotFound()
    return lesson


def require_quiz(db: Session, quiz_id: str) -> TrainingQuiz:
    quiz = db.query(TrainingQuiz).filter(TrainingQuiz.id == quiz_id).one_or_none()
    if quiz is None:
        raise TrainingNotFound()
    return quiz


def require_employee(db: Session, employee_id: str) -> UserProfile:
    employee = db.query(UserProfile).filter(UserProfile.id == employee_id).one_or_none()
    if employee is None:
        raise TrainingNotFound()
    return employee


def _normalize_scope(value: str | None) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def _module_applies(
    module: TrainingModule,
    employee: UserProfile | None,
) -> bool:
    if employee is None:
        return True

    job_target = _normalize_scope(module.audience_job_title)
    department_target = _normalize_scope(module.audience_department)
    if job_target and job_target != _normalize_scope(employee.job_title):
        return False
    if department_target and department_target != _normalize_scope(employee.department):
        return False
    return True


ASIATI_PENDING_CORPORATE_VIDEO_TITLES = {
    "Módulo 1 · ASIATI",
    "Módulo 2 · ASIATI",
    "Módulo 3 · ASIATI",
}


def _lesson_visible_to_employee(lesson: TrainingLesson) -> bool:
    if (
        lesson.title in ASIATI_PENDING_CORPORATE_VIDEO_TITLES
        and not lesson.video_storage_key
        and not lesson.video_url
    ):
        return False
    return True


def _module_lessons(
    module: TrainingModule,
    employee: UserProfile | None = None,
) -> list[TrainingLesson]:
    lessons = sorted(module.lessons, key=lambda lesson: lesson.position)
    if employee is None:
        return lessons
    return [
        lesson
        for lesson in lessons
        if _lesson_visible_to_employee(lesson)
    ]


def _applicable_modules(
    course: TrainingCourse,
    employee: UserProfile | None = None,
) -> list[TrainingModule]:
    modules = [
        module
        for module in sorted(course.modules, key=lambda item: item.position)
        if _module_applies(module, employee)
    ]
    if employee is not None:
        modules = [
            module
            for module in modules
            if _module_lessons(module, employee)
        ]
    return modules


def _lesson_minutes(lesson: TrainingLesson) -> int | None:
    if lesson.estimated_minutes:
        return int(lesson.estimated_minutes)
    if lesson.duration_seconds:
        return max(1, (int(lesson.duration_seconds) + 59) // 60)
    return None


def _required_lessons(
    course: TrainingCourse,
    employee: UserProfile | None = None,
) -> list[TrainingLesson]:
    return [
        lesson
        for module in _applicable_modules(course, employee)
        for lesson in _module_lessons(module, employee)
        if not lesson.is_optional
    ]


def lesson_payload(
    lesson: TrainingLesson,
    *,
    completed: bool = False,
    progress_details: dict | None = None,
) -> dict:
    video_url = lesson.video_url
    video_source = "external" if lesson.video_url else None
    if lesson.video_storage_key:
        video_url = training_media.create_video_playback_url(
            lesson.video_storage_key,
        )
        video_source = "managed"

    return {
        "id": lesson.id,
        "title": lesson.title,
        "description": lesson.description,
        "video_url": video_url,
        "video_source": video_source,
        "video_content_type": lesson.video_content_type,
        "video_size_bytes": lesson.video_size_bytes,
        "duration_seconds": lesson.duration_seconds,
        "content_type": lesson.content_type or "VIDEO",
        "external_url": lesson.external_url,
        "estimated_minutes": _lesson_minutes(lesson),
        "duration_known": _lesson_minutes(lesson) is not None,
        "is_optional": bool(lesson.is_optional),
        "checklist_items": list(lesson.checklist_items or []),
        "checklist_completed_items": list(
            (progress_details or {}).get("completed_items") or []
        ),
        "position": lesson.position,
        "completed": completed,
    }


def module_payload(
    module: TrainingModule,
    *,
    completed_lesson_ids: set[str] | None = None,
    progress_details_by_lesson: dict[str, dict] | None = None,
    employee: UserProfile | None = None,
) -> dict:
    completed_lesson_ids = completed_lesson_ids or set()
    progress_details_by_lesson = progress_details_by_lesson or {}
    lessons = _module_lessons(module, employee)
    required = [lesson for lesson in lessons if not lesson.is_optional]
    completed_required = [
        lesson for lesson in required if lesson.id in completed_lesson_ids
    ]
    required_minutes = [_lesson_minutes(lesson) for lesson in required]
    remaining_required = [
        lesson
        for lesson in required
        if lesson.id not in completed_lesson_ids
    ]
    remaining_values = [
        _lesson_minutes(lesson)
        for lesson in remaining_required
    ]
    estimated_minutes = sum(
        value for value in required_minutes if value is not None
    )
    remaining_minutes = sum(
        value for value in remaining_values if value is not None
    )
    has_unknown_duration = any(value is None for value in required_minutes)
    has_unknown_remaining_duration = any(
        value is None for value in remaining_values
    )
    lesson_count = len(required)
    completed_count = len(completed_required)
    return {
        "id": module.id,
        "title": module.title,
        "description": module.description,
        "audience_job_title": module.audience_job_title,
        "audience_department": module.audience_department,
        "position": module.position,
        "lesson_count": lesson_count,
        "content_item_count": len(lessons),
        "completed_lessons": completed_count,
        "progress_percent": (
            round((completed_count / lesson_count) * 100)
            if lesson_count
            else 100
        ),
        "is_complete": completed_count >= lesson_count if lesson_count else True,
        "estimated_minutes": estimated_minutes,
        "remaining_minutes": remaining_minutes,
        "has_unknown_duration": has_unknown_duration,
        "has_unknown_remaining_duration": has_unknown_remaining_duration,
        "lessons": [
            lesson_payload(
                lesson,
                completed=lesson.id in completed_lesson_ids,
                progress_details=progress_details_by_lesson.get(lesson.id),
            )
            for lesson in lessons
        ],
    }


def _course_counts(
    course: TrainingCourse,
    employee: UserProfile | None = None,
) -> tuple[int, int]:
    modules = _applicable_modules(course, employee)
    return len(modules), len(_required_lessons(course, employee))


def course_payload(
    course: TrainingCourse,
    *,
    completed_lesson_ids: set[str] | None = None,
    progress_details_by_lesson: dict[str, dict] | None = None,
    include_structure: bool = False,
    employee: UserProfile | None = None,
) -> dict:
    completed_lesson_ids = completed_lesson_ids or set()
    progress_details_by_lesson = progress_details_by_lesson or {}
    modules = _applicable_modules(course, employee)
    required_lessons = _required_lessons(course, employee)
    required_ids = {lesson.id for lesson in required_lessons}
    completed_required_ids = required_ids & completed_lesson_ids
    module_count = len(modules)
    lesson_count = len(required_lessons)
    completed_count = len(completed_required_ids)
    progress_percent = round((completed_count / lesson_count) * 100) if lesson_count else 0
    required_minutes = [
        _lesson_minutes(lesson)
        for lesson in required_lessons
    ]
    remaining_required = [
        lesson
        for lesson in required_lessons
        if lesson.id not in completed_required_ids
    ]
    remaining_values = [
        _lesson_minutes(lesson)
        for lesson in remaining_required
    ]
    estimated_minutes = sum(
        value for value in required_minutes if value is not None
    )
    remaining_minutes = sum(
        value for value in remaining_values if value is not None
    )
    has_unknown_duration = any(value is None for value in required_minutes)
    has_unknown_remaining_duration = any(
        value is None for value in remaining_values
    )
    next_lesson = next(
        (
            lesson
            for lesson in required_lessons
            if lesson.id not in completed_required_ids
        ),
        None,
    )

    payload = {
        "id": course.id,
        "title": course.title,
        "description": course.description,
        "status": course.status,
        "is_onboarding": bool(course.is_onboarding),
        "module_count": module_count,
        "lesson_count": lesson_count,
        "content_item_count": sum(
            len(_module_lessons(module, employee))
            for module in modules
        ),
        "completed_lessons": completed_count,
        "progress_percent": progress_percent,
        "estimated_minutes": estimated_minutes,
        "remaining_minutes": remaining_minutes,
        "has_unknown_duration": has_unknown_duration,
        "has_unknown_remaining_duration": has_unknown_remaining_duration,
        "next_lesson_id": next_lesson.id if next_lesson else None,
        "has_quiz": course.quiz is not None,
        "created_at": course.created_at.isoformat() if course.created_at else None,
        "updated_at": course.updated_at.isoformat() if course.updated_at else None,
    }
    if include_structure:
        payload["modules"] = [
            module_payload(
                module,
                completed_lesson_ids=completed_lesson_ids,
                progress_details_by_lesson=progress_details_by_lesson,
                employee=employee,
            )
            for module in modules
        ]
    return payload

def course_quality_report(
    course: TrainingCourse,
    *,
    employee: UserProfile | None = None,
) -> dict:
    modules = _applicable_modules(course, employee)
    lessons = [
        lesson
        for module in modules
        for lesson in _module_lessons(module, employee)
    ]
    required_lessons = [
        lesson
        for lesson in lessons
        if not lesson.is_optional
    ]
    issues: list[dict] = []

    for module in modules:
        visible_lessons = _module_lessons(module, employee)
        if not visible_lessons:
            issues.append(
                {
                    "severity": "info",
                    "code": "EMPTY_MODULE",
                    "message": f'El módulo "{module.title}" aún no tiene contenido visible.',
                    "module_id": module.id,
                    "lesson_id": None,
                }
            )

    for lesson in required_lessons:
        minutes = _lesson_minutes(lesson)
        if minutes is None:
            issues.append(
                {
                    "severity": "warning",
                    "code": "UNKNOWN_DURATION",
                    "message": f'Confirma la duración de "{lesson.title}".',
                    "module_id": lesson.module_id,
                    "lesson_id": lesson.id,
                }
            )
        elif minutes > 7:
            issues.append(
                {
                    "severity": "warning",
                    "code": "LONG_ACTIVITY",
                    "message": (
                        f'"{lesson.title}" dura ~{minutes} min. '
                        "Conviene dividirla en bloques de máximo ~7 min."
                    ),
                    "module_id": lesson.module_id,
                    "lesson_id": lesson.id,
                }
            )

        if (
            str(lesson.content_type or "").upper() == "VIDEO"
            and not lesson.video_storage_key
            and not lesson.video_url
        ):
            issues.append(
                {
                    "severity": "warning",
                    "code": "MISSING_VIDEO",
                    "message": f'Falta cargar el video de "{lesson.title}".',
                    "module_id": lesson.module_id,
                    "lesson_id": lesson.id,
                }
            )

    known_minutes = [
        _lesson_minutes(lesson)
        for lesson in required_lessons
        if _lesson_minutes(lesson) is not None
    ]
    total_known_minutes = sum(known_minutes)
    if total_known_minutes > 60:
        issues.append(
            {
                "severity": "warning",
                "code": "LONG_JOURNEY",
                "message": (
                    f"La ruta acumula ~{total_known_minutes} min conocidos. "
                    "Considera dividirla en varias sesiones o días."
                ),
                "module_id": None,
                "lesson_id": None,
            }
        )

    quiz_question_count = len(course.quiz.questions) if course.quiz else 0
    if course.is_onboarding:
        if course.quiz is None:
            issues.append(
                {
                    "severity": "warning",
                    "code": "MISSING_QUIZ",
                    "message": "La ruta de onboarding no tiene evaluación final.",
                    "module_id": None,
                    "lesson_id": None,
                }
            )
        elif quiz_question_count < 5:
            issues.append(
                {
                    "severity": "info",
                    "code": "QUIZ_TOO_SHORT",
                    "message": (
                        f"El quiz tiene {quiz_question_count} preguntas. "
                        "La recomendación para onboarding es 5–8."
                    ),
                    "module_id": None,
                    "lesson_id": None,
                }
            )
        elif quiz_question_count > 8:
            issues.append(
                {
                    "severity": "warning",
                    "code": "QUIZ_TOO_LONG",
                    "message": (
                        f"El quiz tiene {quiz_question_count} preguntas. "
                        "Para una inducción ligera recomendamos máximo 8."
                    ),
                    "module_id": None,
                    "lesson_id": None,
                }
            )

    return {
        "issue_count": len(issues),
        "warning_count": sum(
            1 for issue in issues if issue["severity"] == "warning"
        ),
        "info_count": sum(
            1 for issue in issues if issue["severity"] == "info"
        ),
        "known_minutes": total_known_minutes,
        "required_activity_count": len(required_lessons),
        "quiz_question_count": quiz_question_count,
        "issues": issues,
    }


def get_course_preview(
    db: Session,
    course_id: str,
    *,
    employee_id: str | None = None,
) -> dict:
    course = require_course(db, course_id)
    employee = require_employee(db, employee_id) if employee_id else None
    payload = course_payload(
        course,
        include_structure=True,
        employee=employee,
    )
    payload["quality"] = course_quality_report(
        course,
        employee=employee,
    )
    payload["preview_employee"] = (
        {
            "id": employee.id,
            "email": employee.email,
            "first_name": employee.first_name,
            "last_name": employee.last_name,
            "job_title": employee.job_title,
            "department": employee.department,
        }
        if employee is not None
        else None
    )
    return payload


def list_courses(db: Session) -> list[dict]:
    courses = db.query(TrainingCourse).order_by(TrainingCourse.created_at.desc()).all()
    return [course_payload(course) for course in courses]


def get_course(db: Session, course_id: str) -> dict:
    course = require_course(db, course_id)
    payload = course_payload(course, include_structure=True)
    payload["quiz"] = quiz_admin_payload(course.quiz) if course.quiz else None
    payload["quality"] = course_quality_report(course)
    return payload


def create_course(
    db: Session,
    *,
    title: str,
    description: str | None,
    created_by_sub: str,
    is_onboarding: bool = False,
) -> TrainingCourse:
    course = TrainingCourse(
        title=title.strip(),
        description=(description or "").strip() or None,
        is_onboarding=is_onboarding,
        status="DRAFT",
        created_by_sub=created_by_sub,
    )
    db.add(course)
    db.commit()
    db.refresh(course)
    return course


from app.domains.training.asiati_preset import (
    create_asiati_onboarding_template,
    ensure_published_asiati_onboarding,
)

def update_course(
    db: Session,
    course_id: str,
    *,
    title: str | None = None,
    description: str | None = None,
    is_onboarding: bool | None = None,
    status: str | None = None,
) -> TrainingCourse:
    course = require_course(db, course_id)
    if title is not None:
        course.title = title.strip()
    if description is not None:
        course.description = description.strip() or None
    if is_onboarding is not None:
        if course.status != "DRAFT":
            raise TrainingStateError("Only draft courses can change onboarding classification.")
        course.is_onboarding = is_onboarding
    if status is not None:
        normalized = status.upper()
        allowed_transitions = {
            "DRAFT": {"DRAFT", "PUBLISHED", "ARCHIVED"},
            "PUBLISHED": {"PUBLISHED", "ARCHIVED"},
            "ARCHIVED": {"ARCHIVED"},
        }
        if normalized not in allowed_transitions.get(course.status, {course.status}):
            raise TrainingStateError("Unsupported course status transition.")
        if normalized == "PUBLISHED":
            _, lesson_count = _course_counts(course)
            if lesson_count == 0:
                raise TrainingStateError("A course needs at least one lesson before publishing.")
            if course.quiz is not None and not course.quiz.questions:
                raise TrainingStateError("A course quiz needs at least one question before publishing.")
        course.status = normalized
    db.commit()
    db.refresh(course)
    return course


def add_module(
    db: Session,
    *,
    course_id: str,
    title: str,
    description: str | None,
    audience_job_title: str | None = None,
    audience_department: str | None = None,
) -> TrainingModule:
    course = require_course(db, course_id)
    if course.status != "DRAFT":
        raise TrainingStateError("Only draft courses can change their content.")
    position = (
        db.query(func.coalesce(func.max(TrainingModule.position), 0))
        .filter(TrainingModule.course_id == course_id)
        .scalar()
        or 0
    ) + 1
    module = TrainingModule(
        course_id=course_id,
        title=title.strip(),
        description=(description or "").strip() or None,
        audience_job_title=(audience_job_title or "").strip() or None,
        audience_department=(audience_department or "").strip() or None,
        position=position,
    )
    db.add(module)
    db.commit()
    db.refresh(module)
    return module


def add_lesson(
    db: Session,
    *,
    module_id: str,
    title: str,
    description: str | None,
    video_url: str | None,
    duration_seconds: int | None,
    content_type: str = "VIDEO",
    external_url: str | None = None,
    estimated_minutes: int | None = None,
    checklist_items: list[str] | None = None,
    is_optional: bool = False,
) -> TrainingLesson:
    module = require_module(db, module_id)
    if module.course.status != "DRAFT":
        raise TrainingStateError("Only draft courses can change their content.")
    position = (
        db.query(func.coalesce(func.max(TrainingLesson.position), 0))
        .filter(TrainingLesson.module_id == module_id)
        .scalar()
        or 0
    ) + 1
    lesson = TrainingLesson(
        module_id=module_id,
        title=title.strip(),
        description=(description or "").strip() or None,
        video_url=(video_url or "").strip() or None,
        duration_seconds=duration_seconds,
        content_type=(content_type or "VIDEO").strip().upper(),
        external_url=(external_url or "").strip() or None,
        estimated_minutes=estimated_minutes,
        checklist_items=list(checklist_items or []),
        is_optional=bool(is_optional),
        position=position,
    )
    db.add(lesson)
    db.commit()
    db.refresh(lesson)
    return lesson


def create_lesson_video_upload(
    db: Session,
    *,
    lesson_id: str,
    filename: str,
    content_type: str,
    size_bytes: int,
) -> dict:
    lesson = require_lesson(db, lesson_id)
    if lesson.module.course.status != "DRAFT":
        raise TrainingStateError("Only draft courses can change their videos.")
    return training_media.create_video_upload(
        lesson_id=lesson.id,
        filename=filename,
        content_type=content_type,
        size_bytes=size_bytes,
    )


def finalize_lesson_video_upload(
    db: Session,
    *,
    lesson_id: str,
    key: str,
    content_type: str,
    size_bytes: int,
) -> TrainingLesson:
    lesson = require_lesson(db, lesson_id)
    if lesson.module.course.status != "DRAFT":
        raise TrainingStateError("Only draft courses can change their videos.")

    verified = training_media.verify_video_object(
        lesson_id=lesson.id,
        key=key,
        expected_content_type=content_type,
        expected_size_bytes=size_bytes,
    )
    previous_key = lesson.video_storage_key

    lesson.video_storage_key = verified["key"]
    lesson.video_content_type = verified["content_type"]
    lesson.video_size_bytes = verified["size_bytes"]
    lesson.video_url = None
    db.commit()
    db.refresh(lesson)

    if previous_key and previous_key != lesson.video_storage_key:
        try:
            training_media.delete_video_object(previous_key)
        except Exception:
            logger.warning(
                "Could not delete superseded training media %s",
                previous_key,
                exc_info=True,
            )

    return lesson


def _sync_employee_onboarding(db: Session, employee_id: str) -> UserProfile:
    employee = require_employee(db, employee_id)
    assignments = (
        db.query(TrainingAssignment)
        .join(
            TrainingCourse,
            TrainingAssignment.course_id == TrainingCourse.id,
        )
        .filter(
            TrainingAssignment.employee_id == employee_id,
            TrainingCourse.is_onboarding.is_(True),
        )
        .all()
    )

    if not assignments:
        return employee

    if all(assignment.status == "COMPLETED" for assignment in assignments):
        employee.onboarding_status = "COMPLETED"
        if employee.onboarding_started_at is None:
            employee.onboarding_started_at = datetime.now(timezone.utc)
        if employee.onboarding_completed_at is None:
            employee.onboarding_completed_at = datetime.now(timezone.utc)
        return employee

    assignment_ids = [assignment.id for assignment in assignments]
    has_lesson_activity = (
        db.query(TrainingLessonProgress.id)
        .filter(TrainingLessonProgress.assignment_id.in_(assignment_ids))
        .first()
        is not None
    )
    has_quiz_activity = (
        db.query(TrainingQuizAttempt.id)
        .filter(TrainingQuizAttempt.assignment_id.in_(assignment_ids))
        .first()
        is not None
    )
    has_started = (
        employee.onboarding_started_at is not None
        or has_lesson_activity
        or has_quiz_activity
    )

    if has_started:
        employee.onboarding_status = "IN_PROGRESS"
        if employee.onboarding_started_at is None:
            employee.onboarding_started_at = datetime.now(timezone.utc)
    else:
        employee.onboarding_status = "PENDING"

    employee.onboarding_completed_at = None
    return employee


def assign_course(
    db: Session,
    *,
    course_id: str,
    employee_id: str,
    assigned_by_sub: str,
) -> TrainingAssignment:
    course = require_course(db, course_id)
    employee = require_employee(db, employee_id)
    if employee.status != "ACTIVE":
        raise TrainingAssignmentError("Disabled employees cannot receive new courses.")
    if course.status != "PUBLISHED":
        raise TrainingAssignmentError("Only published courses can be assigned.")

    existing = (
        db.query(TrainingAssignment)
        .filter(
            TrainingAssignment.course_id == course_id,
            TrainingAssignment.employee_id == employee_id,
        )
        .one_or_none()
    )
    if existing is not None:
        if course.is_onboarding:
            _sync_employee_onboarding(db, employee_id)
            db.commit()
            db.refresh(existing)
        return existing

    assignment = TrainingAssignment(
        course_id=course_id,
        employee_id=employee_id,
        status="ASSIGNED",
        assigned_by_sub=assigned_by_sub,
    )
    db.add(assignment)
    db.flush()
    if course.is_onboarding:
        _sync_employee_onboarding(db, employee_id)
    db.commit()
    db.refresh(assignment)
    return assignment


def _completed_ids(db: Session, assignment_id: str) -> set[str]:
    return {
        lesson_id
        for (lesson_id,) in (
            db.query(TrainingLessonProgress.lesson_id)
            .filter(
                TrainingLessonProgress.assignment_id == assignment_id,
                TrainingLessonProgress.status == "COMPLETED",
            )
            .all()
        )
    }


def _progress_details_by_lesson(
    db: Session,
    assignment_id: str,
) -> dict[str, dict]:
    entries = (
        db.query(TrainingLessonProgress)
        .filter(TrainingLessonProgress.assignment_id == assignment_id)
        .all()
    )
    return {
        entry.lesson_id: dict(entry.details or {})
        for entry in entries
    }


def _assignment_course_payload(
    db: Session,
    assignment: TrainingAssignment,
    *,
    include_structure: bool,
) -> dict:
    completed = _completed_ids(db, assignment.id)
    progress_details = _progress_details_by_lesson(db, assignment.id)
    course = course_payload(
        assignment.course,
        completed_lesson_ids=completed,
        progress_details_by_lesson=progress_details,
        include_structure=include_structure,
        employee=assignment.employee,
    )
    if assignment.course.quiz is not None:
        passed_quiz = any(attempt.passed for attempt in assignment.quiz_attempts)
        lesson_count = course["lesson_count"]
        total_units = lesson_count + 1
        completed_units = course["completed_lessons"] + (1 if passed_quiz else 0)
        course["progress_percent"] = round((completed_units / total_units) * 100)
        course["quiz_pending"] = (
            course["completed_lessons"] >= lesson_count and not passed_quiz
        )
    else:
        course["quiz_pending"] = False
    return course


def assignment_payload(db: Session, assignment: TrainingAssignment) -> dict:
    course = _assignment_course_payload(
        db,
        assignment,
        include_structure=False,
    )
    attempts = sorted(
        assignment.quiz_attempts,
        key=lambda attempt: attempt.attempt_number,
    )
    best_score = max((attempt.score_percent for attempt in attempts), default=None)
    latest_attempt = attempts[-1] if attempts else None

    return {
        "id": assignment.id,
        "status": assignment.status,
        "assigned_at": assignment.assigned_at.isoformat() if assignment.assigned_at else None,
        "completed_at": assignment.completed_at.isoformat() if assignment.completed_at else None,
        "quiz_result": {
            "attempt_count": len(attempts),
            "best_score": best_score,
            "latest_score": latest_attempt.score_percent if latest_attempt else None,
            "passed": any(attempt.passed for attempt in attempts),
        } if assignment.course.quiz else None,
        "employee": {
            "id": assignment.employee.id,
            "email": assignment.employee.email,
            "first_name": assignment.employee.first_name,
            "last_name": assignment.employee.last_name,
            "job_title": assignment.employee.job_title,
            "department": assignment.employee.department,
        },
        "course": course,
    }


def list_course_assignments(db: Session, course_id: str) -> list[dict]:
    require_course(db, course_id)
    assignments = (
        db.query(TrainingAssignment)
        .filter(TrainingAssignment.course_id == course_id)
        .order_by(TrainingAssignment.assigned_at.desc())
        .all()
    )
    return [assignment_payload(db, assignment) for assignment in assignments]


def list_my_training(db: Session, employee_id: str) -> list[dict]:
    assignments = (
        db.query(TrainingAssignment)
        .filter(TrainingAssignment.employee_id == employee_id)
        .order_by(TrainingAssignment.assigned_at.desc())
        .all()
    )
    return [assignment_payload(db, assignment) for assignment in assignments]


def require_my_assignment(
    db: Session,
    *,
    employee_id: str,
    course_id: str,
) -> TrainingAssignment:
    assignment = (
        db.query(TrainingAssignment)
        .filter(
            TrainingAssignment.employee_id == employee_id,
            TrainingAssignment.course_id == course_id,
        )
        .one_or_none()
    )
    if assignment is None:
        raise TrainingNotFound()
    return assignment


def get_my_course(db: Session, *, employee_id: str, course_id: str) -> dict:
    assignment = require_my_assignment(
        db,
        employee_id=employee_id,
        course_id=course_id,
    )
    return {
        "assignment_id": assignment.id,
        "assignment_status": assignment.status,
        "course": _assignment_course_payload(
            db,
            assignment,
            include_structure=True,
        ),
    }


def _refresh_assignment_completion(
    db: Session,
    assignment: TrainingAssignment,
) -> None:
    course = assignment.course
    required_lessons = _required_lessons(course, assignment.employee)
    required_ids = {item.id for item in required_lessons}
    completed_ids = _completed_ids(db, assignment.id)
    all_required_complete = bool(required_ids) and required_ids.issubset(completed_ids)

    if course.quiz is None:
        if all_required_complete:
            assignment.status = "COMPLETED"
            if assignment.completed_at is None:
                assignment.completed_at = datetime.now(timezone.utc)
        elif assignment.status == "COMPLETED":
            assignment.status = "ASSIGNED"
            assignment.completed_at = None

    if course.is_onboarding:
        _sync_employee_onboarding(db, assignment.employee_id)


def complete_lesson(
    db: Session,
    *,
    employee_id: str,
    lesson_id: str,
) -> dict:
    lesson = require_lesson(db, lesson_id)
    course = lesson.module.course
    assignment = require_my_assignment(
        db,
        employee_id=employee_id,
        course_id=course.id,
    )
    if course.status != "PUBLISHED":
        raise TrainingStateError("This course is not available.")
    if not _module_applies(lesson.module, assignment.employee):
        raise TrainingStateError("This lesson is not assigned to your profile.")
    if not _lesson_visible_to_employee(lesson):
        raise TrainingStateError("This lesson is not available yet.")
    if (
        str(lesson.content_type or "").upper() == "CHECKLIST"
        and list(lesson.checklist_items or [])
    ):
        raise TrainingStateError(
            "Complete the checklist items before finishing this lesson."
        )

    existing = (
        db.query(TrainingLessonProgress)
        .filter(
            TrainingLessonProgress.assignment_id == assignment.id,
            TrainingLessonProgress.lesson_id == lesson_id,
        )
        .one_or_none()
    )
    if existing is None:
        db.add(
            TrainingLessonProgress(
                assignment_id=assignment.id,
                lesson_id=lesson_id,
                status="COMPLETED",
                details={},
                completed_at=datetime.now(timezone.utc),
            )
        )
        db.flush()

    _refresh_assignment_completion(db, assignment)
    db.commit()
    return get_my_course(db, employee_id=employee_id, course_id=course.id)


def update_checklist_progress(
    db: Session,
    *,
    employee_id: str,
    lesson_id: str,
    completed_items: list[int],
) -> dict:
    lesson = require_lesson(db, lesson_id)
    course = lesson.module.course
    assignment = require_my_assignment(
        db,
        employee_id=employee_id,
        course_id=course.id,
    )
    if course.status != "PUBLISHED":
        raise TrainingStateError("This course is not available.")
    if not _module_applies(lesson.module, assignment.employee):
        raise TrainingStateError("This lesson is not assigned to your profile.")
    if not _lesson_visible_to_employee(lesson):
        raise TrainingStateError("This lesson is not available yet.")
    if str(lesson.content_type or "").upper() != "CHECKLIST":
        raise TrainingStateError("This lesson is not a checklist.")
    if assignment.status == "COMPLETED":
        return get_my_course(
            db,
            employee_id=employee_id,
            course_id=course.id,
        )

    items = list(lesson.checklist_items or [])
    if not items:
        raise TrainingStateError("This checklist has no configured items.")

    normalized = sorted(set(completed_items))
    if any(index < 0 or index >= len(items) for index in normalized):
        raise TrainingStateError("One or more checklist items are invalid.")

    is_complete = len(normalized) == len(items)
    entry = (
        db.query(TrainingLessonProgress)
        .filter(
            TrainingLessonProgress.assignment_id == assignment.id,
            TrainingLessonProgress.lesson_id == lesson.id,
        )
        .one_or_none()
    )
    now = datetime.now(timezone.utc)
    if entry is None:
        entry = TrainingLessonProgress(
            assignment_id=assignment.id,
            lesson_id=lesson.id,
            status="COMPLETED" if is_complete else "IN_PROGRESS",
            details={"completed_items": normalized},
            completed_at=now if is_complete else None,
        )
        db.add(entry)
    else:
        entry.status = "COMPLETED" if is_complete else "IN_PROGRESS"
        entry.details = {"completed_items": normalized}
        entry.completed_at = now if is_complete else None

    db.flush()
    _refresh_assignment_completion(db, assignment)
    db.commit()
    return get_my_course(db, employee_id=employee_id, course_id=course.id)


def quiz_admin_payload(quiz: TrainingQuiz) -> dict:
    return {
        "id": quiz.id,
        "course_id": quiz.course_id,
        "title": quiz.title,
        "passing_score": quiz.passing_score,
        "question_count": len(quiz.questions),
        "questions": [
            {
                "id": question.id,
                "prompt": question.prompt,
                "options": list(question.options or []),
                "correct_option": question.correct_option,
                "position": question.position,
            }
            for question in sorted(quiz.questions, key=lambda item: item.position)
        ],
    }


def quiz_employee_payload(quiz: TrainingQuiz, *, attempts: list[TrainingQuizAttempt]) -> dict:
    return {
        "id": quiz.id,
        "course_id": quiz.course_id,
        "title": quiz.title,
        "passing_score": quiz.passing_score,
        "question_count": len(quiz.questions),
        "questions": [
            {
                "id": question.id,
                "prompt": question.prompt,
                "options": list(question.options or []),
                "position": question.position,
            }
            for question in sorted(quiz.questions, key=lambda item: item.position)
        ],
        "attempts": [
            {
                "id": attempt.id,
                "attempt_number": attempt.attempt_number,
                "score_percent": attempt.score_percent,
                "passed": attempt.passed,
                "submitted_at": attempt.submitted_at.isoformat()
                if attempt.submitted_at else None,
            }
            for attempt in sorted(attempts, key=lambda item: item.attempt_number)
        ],
    }


def create_quiz(
    db: Session,
    *,
    course_id: str,
    title: str,
    passing_score: int,
    created_by_sub: str,
) -> TrainingQuiz:
    course = require_course(db, course_id)
    if course.status != "DRAFT":
        raise TrainingStateError("Only draft courses can change their evaluation.")
    if course.quiz is not None:
        raise TrainingStateError("This course already has an evaluation.")

    quiz = TrainingQuiz(
        course_id=course_id,
        title=title.strip(),
        passing_score=passing_score,
        created_by_sub=created_by_sub,
    )
    db.add(quiz)
    db.commit()
    db.refresh(quiz)
    return quiz


def add_quiz_question(
    db: Session,
    *,
    quiz_id: str,
    prompt: str,
    options: list[str],
    correct_option: int,
) -> TrainingQuizQuestion:
    quiz = require_quiz(db, quiz_id)
    if quiz.course.status != "DRAFT":
        raise TrainingStateError("Only draft courses can change their evaluation.")
    if correct_option < 0 or correct_option >= len(options):
        raise TrainingStateError("Correct option is outside the option range.")

    position = (
        db.query(func.coalesce(func.max(TrainingQuizQuestion.position), 0))
        .filter(TrainingQuizQuestion.quiz_id == quiz_id)
        .scalar()
        or 0
    ) + 1

    question = TrainingQuizQuestion(
        quiz_id=quiz_id,
        prompt=prompt.strip(),
        options=[option.strip() for option in options],
        correct_option=correct_option,
        position=position,
    )
    db.add(question)
    db.commit()
    db.refresh(question)
    return question


def _all_lessons_completed(db: Session, assignment: TrainingAssignment) -> bool:
    required_lessons = _required_lessons(
        assignment.course,
        assignment.employee,
    )
    if not required_lessons:
        return False
    required_ids = {lesson.id for lesson in required_lessons}
    completed_ids = _completed_ids(db, assignment.id)
    return required_ids.issubset(completed_ids)


def get_my_quiz(db: Session, *, employee_id: str, course_id: str) -> dict:
    assignment = require_my_assignment(
        db,
        employee_id=employee_id,
        course_id=course_id,
    )
    course = assignment.course
    if course.status != "PUBLISHED" or course.quiz is None:
        raise TrainingNotFound()
    if not _all_lessons_completed(db, assignment):
        raise TrainingStateError("Complete all course lessons before taking the evaluation.")

    attempts = (
        db.query(TrainingQuizAttempt)
        .filter(TrainingQuizAttempt.assignment_id == assignment.id)
        .order_by(TrainingQuizAttempt.attempt_number.asc())
        .all()
    )
    return quiz_employee_payload(course.quiz, attempts=attempts)


def submit_quiz_attempt(
    db: Session,
    *,
    employee_id: str,
    course_id: str,
    answers: dict[str, int],
) -> dict:
    assignment = require_my_assignment(
        db,
        employee_id=employee_id,
        course_id=course_id,
    )
    course = assignment.course
    quiz = course.quiz
    if course.status != "PUBLISHED" or quiz is None:
        raise TrainingNotFound()
    if not _all_lessons_completed(db, assignment):
        raise TrainingStateError("Complete all course lessons before taking the evaluation.")

    questions = sorted(quiz.questions, key=lambda item: item.position)
    if not questions:
        raise TrainingStateError("This evaluation has no questions.")

    expected_ids = {question.id for question in questions}
    if set(answers) != expected_ids:
        raise TrainingStateError("Answer every question before submitting.")

    correct = 0
    normalized_answers = {}
    for question in questions:
        selected = answers[question.id]
        if not isinstance(selected, int) or selected < 0 or selected >= len(question.options or []):
            raise TrainingStateError("One or more selected answers are invalid.")
        normalized_answers[question.id] = selected
        if selected == question.correct_option:
            correct += 1

    score_percent = round((correct / len(questions)) * 100)
    passed = score_percent >= quiz.passing_score
    latest_number = (
        db.query(func.coalesce(func.max(TrainingQuizAttempt.attempt_number), 0))
        .filter(TrainingQuizAttempt.assignment_id == assignment.id)
        .scalar()
        or 0
    )
    attempt = TrainingQuizAttempt(
        assignment_id=assignment.id,
        quiz_id=quiz.id,
        answers=normalized_answers,
        score_percent=score_percent,
        passed=passed,
        attempt_number=latest_number + 1,
    )
    db.add(attempt)

    if passed and assignment.status != "COMPLETED":
        assignment.status = "COMPLETED"
        assignment.completed_at = datetime.now(timezone.utc)

    if course.is_onboarding:
        _sync_employee_onboarding(db, employee_id)

    db.commit()
    db.refresh(attempt)
    return {
        "attempt": {
            "id": attempt.id,
            "attempt_number": attempt.attempt_number,
            "score_percent": attempt.score_percent,
            "passed": attempt.passed,
            "submitted_at": attempt.submitted_at.isoformat()
            if attempt.submitted_at else None,
        },
        "assignment_status": assignment.status,
        "passing_score": quiz.passing_score,
    }

