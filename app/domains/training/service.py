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


class TrainingNotFound(Exception):
    pass


class TrainingStateError(Exception):
    pass


class TrainingAssignmentError(Exception):
    pass


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


ASIATI_ONBOARDING_SOURCE_VIDEO_1_3 = (
    "https://drive.google.com/file/d/"
    "1_2XSmYKr66TR0zQm-fZjQgG2tHvwi7yP/view?usp=drivesdk"
)

ASIATI_ONBOARDING_MODULE_1_TITLE = "Módulo 1 · Bienvenida a ASIATI"
ASIATI_ONBOARDING_MODULE_1_LESSON_TITLE = "Bienvenida a ASIATI"
ASIATI_ONBOARDING_MODULE_1_VIDEO_URL = (
    "https://drive.google.com/file/d/"
    "1NuUYwD0ZEy3DDtptjlhz4NqfuGzD2wXN/view?usp=drivesdk"
)
ASIATI_ONBOARDING_MODULE_1_DURATION_SECONDS = 58
ASIATI_ONBOARDING_MODULE_1_DESCRIPTION = (
    "Empieza aquí. Un mensaje breve para darte la bienvenida, presentarte "
    "el espíritu de ASIATI y abrir tu ruta de inducción."
)
ASIATI_ONBOARDING_MODULE_1_LESSON_DESCRIPTION = (
    "Mensaje de bienvenida corporativa. Conoce el tono de esta nueva etapa "
    "y cómo queremos que vivas tu llegada a ASIATI."
)


def _ensure_asiati_module_1(
    db: Session,
    *,
    course: TrainingCourse,
) -> TrainingCourse:
    module = next(
        (
            item
            for item in course.modules
            if item.title in {"Bienvenida", ASIATI_ONBOARDING_MODULE_1_TITLE}
        ),
        None,
    )
    if module is None:
        module = add_module(
            db,
            course_id=course.id,
            title=ASIATI_ONBOARDING_MODULE_1_TITLE,
            description=ASIATI_ONBOARDING_MODULE_1_DESCRIPTION,
        )
        course = require_course(db, course.id)

    changed = False
    if module.title != ASIATI_ONBOARDING_MODULE_1_TITLE:
        module.title = ASIATI_ONBOARDING_MODULE_1_TITLE
        changed = True
    if module.description != ASIATI_ONBOARDING_MODULE_1_DESCRIPTION:
        module.description = ASIATI_ONBOARDING_MODULE_1_DESCRIPTION
        changed = True

    lesson = next(
        (
            item
            for item in module.lessons
            if item.title in {"Tu ruta de inducción", ASIATI_ONBOARDING_MODULE_1_LESSON_TITLE}
        ),
        None,
    )
    if lesson is None:
        add_lesson(
            db,
            module_id=module.id,
            title=ASIATI_ONBOARDING_MODULE_1_LESSON_TITLE,
            description=ASIATI_ONBOARDING_MODULE_1_LESSON_DESCRIPTION,
            video_url=ASIATI_ONBOARDING_MODULE_1_VIDEO_URL,
            duration_seconds=ASIATI_ONBOARDING_MODULE_1_DURATION_SECONDS,
            content_type="VIDEO",
            estimated_minutes=1,
            is_optional=False,
        )
    else:
        desired_values = {
            "title": ASIATI_ONBOARDING_MODULE_1_LESSON_TITLE,
            "description": ASIATI_ONBOARDING_MODULE_1_LESSON_DESCRIPTION,
            "duration_seconds": ASIATI_ONBOARDING_MODULE_1_DURATION_SECONDS,
            "content_type": "VIDEO",
            "external_url": None,
            "estimated_minutes": 1,
            "checklist_items": [],
            "is_optional": False,
        }
        if not lesson.video_storage_key:
            desired_values["video_url"] = ASIATI_ONBOARDING_MODULE_1_VIDEO_URL
        for field, value in desired_values.items():
            if getattr(lesson, field) != value:
                setattr(lesson, field, value)
                changed = True

    # Remove the old empty placeholder so the administrator does not see the
    # same learning activity twice. Preserve it if it already has real media
    # or employee progress.
    for other_module in course.modules:
        for other_lesson in list(other_module.lessons):
            if (
                other_lesson.title == "Módulo 1 · ASIATI"
                and not other_lesson.video_storage_key
                and not other_lesson.video_url
                and not other_lesson.progress_entries
            ):
                db.delete(other_lesson)
                changed = True

    if changed:
        db.commit()
    return require_course(db, course.id)


ASIATI_ONBOARDING_MODULE_2_TITLE = "Módulo 2 · Conoce ASIATI"
ASIATI_ONBOARDING_MODULE_2_LESSON_TITLE = "Quiénes somos y qué hacemos"
ASIATI_ONBOARDING_MODULE_2_VIDEO_URL = (
    "https://drive.google.com/file/d/"
    "1zPS0k293LFvAQK4yrXVtOLoP5X-g9i7t/view?usp=drivesdk"
)
ASIATI_ONBOARDING_MODULE_2_DURATION_SECONDS = 38
ASIATI_ONBOARDING_MODULE_2_DESCRIPTION = (
    "Conoce el alcance de ASIATI, cómo conectamos operación, logística y "
    "tecnología, y la presencia que construimos como compañía."
)
ASIATI_ONBOARDING_MODULE_2_LESSON_DESCRIPTION = (
    "Un recorrido breve por ASIATI: nuestra operación, alcance y las marcas "
    "que hacen parte del ecosistema."
)


def _ensure_asiati_module_2(
    db: Session,
    *,
    course: TrainingCourse,
) -> TrainingCourse:
    module = next(
        (
            item
            for item in course.modules
            if item.title in {"Conoce ASIATI", ASIATI_ONBOARDING_MODULE_2_TITLE}
        ),
        None,
    )
    if module is None:
        module = add_module(
            db,
            course_id=course.id,
            title=ASIATI_ONBOARDING_MODULE_2_TITLE,
            description=ASIATI_ONBOARDING_MODULE_2_DESCRIPTION,
        )
        course = require_course(db, course.id)

    changed = False
    if module.title != ASIATI_ONBOARDING_MODULE_2_TITLE:
        module.title = ASIATI_ONBOARDING_MODULE_2_TITLE
        changed = True
    if module.description != ASIATI_ONBOARDING_MODULE_2_DESCRIPTION:
        module.description = ASIATI_ONBOARDING_MODULE_2_DESCRIPTION
        changed = True

    lesson = next(
        (
            item
            for item in module.lessons
            if item.title in {"Módulo 2 · ASIATI", ASIATI_ONBOARDING_MODULE_2_LESSON_TITLE}
        ),
        None,
    )
    if lesson is None:
        add_lesson(
            db,
            module_id=module.id,
            title=ASIATI_ONBOARDING_MODULE_2_LESSON_TITLE,
            description=ASIATI_ONBOARDING_MODULE_2_LESSON_DESCRIPTION,
            video_url=ASIATI_ONBOARDING_MODULE_2_VIDEO_URL,
            duration_seconds=ASIATI_ONBOARDING_MODULE_2_DURATION_SECONDS,
            content_type="VIDEO",
            estimated_minutes=1,
            is_optional=False,
        )
        course = require_course(db, course.id)
        module = next(
            item
            for item in course.modules
            if item.id == module.id
        )
    else:
        desired_values = {
            "title": ASIATI_ONBOARDING_MODULE_2_LESSON_TITLE,
            "description": ASIATI_ONBOARDING_MODULE_2_LESSON_DESCRIPTION,
            "duration_seconds": ASIATI_ONBOARDING_MODULE_2_DURATION_SECONDS,
            "content_type": "VIDEO",
            "external_url": None,
            "estimated_minutes": 1,
            "checklist_items": [],
            "is_optional": False,
        }
        if not lesson.video_storage_key:
            desired_values["video_url"] = ASIATI_ONBOARDING_MODULE_2_VIDEO_URL
        for field, value in desired_values.items():
            if getattr(lesson, field) != value:
                setattr(lesson, field, value)
                changed = True

    # Las presentaciones y el sitio corporativo enriquecen el módulo, pero no
    # deben bloquear el progreso. El video es la actividad obligatoria.
    for resource in module.lessons:
        if resource.title in {
            "Presentación ASIATI I",
            "Presentación ASIATI II",
            "Página oficial de ASIATI Corp",
        } and not resource.is_optional:
            resource.is_optional = True
            changed = True

    if changed:
        db.commit()
    return require_course(db, course.id)


ASIATI_ONBOARDING_MODULE_3_TITLE = "Módulo 3 · Conoce al equipo"
ASIATI_ONBOARDING_MODULE_3_DESCRIPTION = (
    "Ponle cara al equipo de ASIATI. Cada persona te cuenta brevemente qué "
    "hace y cómo se conecta su trabajo con el resto de la compañía."
)
ASIATI_ONBOARDING_MODULE_3_TEAM = [
    (
        "Jersson",
        "https://drive.google.com/file/d/1BQ38kuCqmh_XSXfATXlzhz0vSAqLsX6j/view?usp=drivesdk",
        37,
    ),
    (
        "Valentina",
        "https://drive.google.com/file/d/166XnHlEoAV3rpQKAwhHj0wHUYxts0DOk/view?usp=drivesdk",
        37,
    ),
    (
        "Johana",
        "https://drive.google.com/file/d/1Po6IxFG0QYpGwSlSiMJc87qH38h8gBuu/view?usp=drivesdk",
        50,
    ),
    (
        "Laura",
        "https://drive.google.com/file/d/1CY1OYFsSEVtyC6R9QJ4SRoWUfU4EXdFy/view?usp=drivesdk",
        46,
    ),
    (
        "Katherine",
        "https://drive.google.com/file/d/1iL3x98_7iksX21D7mjRsI4gyh0U7vSk_/view?usp=drivesdk",
        49,
    ),
    (
        "Claudia",
        "https://drive.google.com/file/d/1ArY_1YfEz2nekwxHnVkqgPgVMscLorXP/view?usp=drivesdk",
        101,
    ),
    (
        "Erika",
        "https://drive.google.com/file/d/1fOZ9atajsXmK_NU4IK96EcaEn52LakW8/view?usp=drivesdk",
        45,
    ),
    (
        "Daniela",
        "https://drive.google.com/file/d/12rabzH1xD-jaUGsPcqy9ws8pYOtJhh4Z/view?usp=drivesdk",
        64,
    ),
    (
        "Oscar",
        "https://drive.google.com/file/d/1SV7tDQPsddVrALYHsfj8YasF6whToUsL/view?usp=drivesdk",
        69,
    ),
    (
        "Josue",
        "https://drive.google.com/file/d/1YGHb4IaZv-irQhjWZiETjOh9uQNxYEHD/view?usp=drivesdk",
        51,
    ),
    (
        "Sebastián",
        "https://drive.google.com/file/d/1FwJJW6MoTkq_gNj5Trcx0b-NSKyedZnh/view?usp=drivesdk",
        67,
    ),
    (
        "Jessica Pullas",
        "https://drive.google.com/file/d/1409EGo8LzFH7gk0XOmoWmSYWTv9vHR-l/view?usp=drivesdk",
        28,
    ),
]

ASIATI_ECOSYSTEM_CONTENT_TITLES = {
    "Mapa del ecosistema ASIATI",
    "ASIATI Corp",
    "ASIATI Commerce",
    "Wiilog",
    "Origen Vital",
    "Chin Chin",
    "El Retrovisor",
}


def _ensure_asiati_module_3(
    db: Session,
    *,
    course: TrainingCourse,
) -> TrainingCourse:
    module_two = next(
        (
            module
            for module in course.modules
            if module.title in {"Conoce ASIATI", ASIATI_ONBOARDING_MODULE_2_TITLE}
        ),
        None,
    )
    module_three = next(
        (
            module
            for module in course.modules
            if module.title in {"Nuestro ecosistema", ASIATI_ONBOARDING_MODULE_3_TITLE}
        ),
        None,
    )

    if module_three is None:
        module_three = add_module(
            db,
            course_id=course.id,
            title=ASIATI_ONBOARDING_MODULE_3_TITLE,
            description=ASIATI_ONBOARDING_MODULE_3_DESCRIPTION,
        )
        course = require_course(db, course.id)
        module_three = next(
            module
            for module in course.modules
            if module.title == ASIATI_ONBOARDING_MODULE_3_TITLE
        )

    changed = False

    # The old preset had a standalone "Nuestro ecosistema" module. Keep those
    # resources, but move them under module 2 as optional enrichment so module
    # 3 can correspond exactly to the approved "Conoce al equipo" source.
    if module_two is not None:
        next_position = max(
            [lesson.position for lesson in module_two.lessons] or [0],
        ) + 1
        for lesson in list(module_three.lessons):
            if lesson.title in ASIATI_ECOSYSTEM_CONTENT_TITLES:
                lesson.module_id = module_two.id
                lesson.module = module_two
                lesson.position = next_position
                lesson.is_optional = True
                next_position += 1
                changed = True

    if module_three.title != ASIATI_ONBOARDING_MODULE_3_TITLE:
        module_three.title = ASIATI_ONBOARDING_MODULE_3_TITLE
        changed = True
    if module_three.description != ASIATI_ONBOARDING_MODULE_3_DESCRIPTION:
        module_three.description = ASIATI_ONBOARDING_MODULE_3_DESCRIPTION
        changed = True

    existing_by_title = {
        lesson.title: lesson
        for lesson in module_three.lessons
        if lesson.title not in ASIATI_ECOSYSTEM_CONTENT_TITLES
    }
    for position, (name, url, duration_seconds) in enumerate(
        ASIATI_ONBOARDING_MODULE_3_TEAM,
        start=1,
    ):
        lesson = existing_by_title.get(name)
        if lesson is None:
            add_lesson(
                db,
                module_id=module_three.id,
                title=name,
                description=(
                    f"Conoce a {name} y su participación dentro del equipo ASIATI."
                ),
                video_url=url,
                duration_seconds=duration_seconds,
                content_type="VIDEO",
                estimated_minutes=max(1, (duration_seconds + 59) // 60),
                is_optional=False,
            )
            continue

        desired_values = {
            "description": f"Conoce a {name} y su participación dentro del equipo ASIATI.",
            "duration_seconds": duration_seconds,
            "content_type": "VIDEO",
            "external_url": None,
            "estimated_minutes": max(1, (duration_seconds + 59) // 60),
            "checklist_items": [],
            "is_optional": False,
            "position": position,
        }
        if not lesson.video_storage_key:
            desired_values["video_url"] = url
        for field, value in desired_values.items():
            if getattr(lesson, field) != value:
                setattr(lesson, field, value)
                changed = True

    # Remove the now-obsolete empty module-3 placeholder from module 2.
    for module in course.modules:
        for lesson in list(module.lessons):
            if (
                lesson.title == "Módulo 3 · ASIATI"
                and not lesson.video_storage_key
                and not lesson.video_url
                and not lesson.progress_entries
            ):
                db.delete(lesson)
                changed = True

    if changed:
        db.commit()
    return require_course(db, course.id)


ASIATI_ONBOARDING_MODULE_4_TITLE = "Módulo 4 · Permisos y vacaciones"
ASIATI_ONBOARDING_MODULE_4_VIDEO_TITLE = "Permisos y vacaciones"
ASIATI_ONBOARDING_MODULE_4_VIDEO_URL = (
    "https://drive.google.com/file/d/"
    "13wZ5Dmv7x19DuRJt_5K55OpQ3nMb6K4x/view?usp=drivesdk"
)
ASIATI_ONBOARDING_MODULE_4_DURATION_SECONDS = 105
ASIATI_ONBOARDING_MODULE_4_DESCRIPTION = (
    "Aprende el flujo interno para tramitar permisos y vacaciones: formato, "
    "aprobaciones y puntos de control antes de enviar tu solicitud."
)
ASIATI_ONBOARDING_MODULE_4_VIDEO_DESCRIPTION = (
    "Revisa el procedimiento corporativo de permisos y vacaciones y los "
    "formatos que debes usar para cada solicitud."
)
ASIATI_ONBOARDING_MODULE_4_CHECKLIST_TITLE = "Antes de enviar tu solicitud"
ASIATI_ONBOARDING_MODULE_4_CHECKLIST_ITEMS = [
    "Identifiqué el formato que corresponde a mi solicitud.",
    "Sé que debo diligenciar la información solicitada antes de enviarla.",
    "Confirmaré la aprobación de mi líder de acuerdo con el procedimiento.",
    "Para vacaciones, revisaré el checklist correspondiente antes de cerrar la solicitud.",
]


def _ensure_asiati_module_4(
    db: Session,
    *,
    course: TrainingCourse,
) -> TrainingCourse:
    module_four = next(
        (
            module
            for module in course.modules
            if module.title == ASIATI_ONBOARDING_MODULE_4_TITLE
        ),
        None,
    )
    created_module = module_four is None
    if module_four is None:
        module_four = add_module(
            db,
            course_id=course.id,
            title=ASIATI_ONBOARDING_MODULE_4_TITLE,
            description=ASIATI_ONBOARDING_MODULE_4_DESCRIPTION,
        )
        course = require_course(db, course.id)
        module_four = next(
            module
            for module in course.modules
            if module.id == module_four.id
        )

        # Insert module 4 directly after the team module. Existing modules keep
        # their relative order and move one slot down.
        for module in course.modules:
            if module.id != module_four.id and module.position >= 4:
                module.position += 1
        module_four.position = 4
        db.commit()
        course = require_course(db, course.id)
        module_four = next(
            module
            for module in course.modules
            if module.id == module_four.id
        )

    changed = False
    if module_four.description != ASIATI_ONBOARDING_MODULE_4_DESCRIPTION:
        module_four.description = ASIATI_ONBOARDING_MODULE_4_DESCRIPTION
        changed = True

    video = next(
        (
            lesson
            for lesson in module_four.lessons
            if lesson.title in {
                "Módulo 4 · Permisos y vacaciones",
                ASIATI_ONBOARDING_MODULE_4_VIDEO_TITLE,
            }
        ),
        None,
    )
    if video is None:
        # Reuse the old video that lived inside "Así trabajamos" when repairing
        # an existing draft, so lesson progress IDs are preserved.
        for module in course.modules:
            if module.id == module_four.id:
                continue
            video = next(
                (
                    lesson
                    for lesson in module.lessons
                    if lesson.title == "Módulo 4 · Permisos y vacaciones"
                ),
                None,
            )
            if video is not None:
                video.module_id = module_four.id
                video.module = module_four
                changed = True
                break

    if video is None:
        add_lesson(
            db,
            module_id=module_four.id,
            title=ASIATI_ONBOARDING_MODULE_4_VIDEO_TITLE,
            description=ASIATI_ONBOARDING_MODULE_4_VIDEO_DESCRIPTION,
            video_url=ASIATI_ONBOARDING_MODULE_4_VIDEO_URL,
            duration_seconds=ASIATI_ONBOARDING_MODULE_4_DURATION_SECONDS,
            content_type="VIDEO",
            estimated_minutes=2,
            is_optional=False,
        )
        course = require_course(db, course.id)
        module_four = next(
            module
            for module in course.modules
            if module.id == module_four.id
        )
        video = next(
            lesson
            for lesson in module_four.lessons
            if lesson.title == ASIATI_ONBOARDING_MODULE_4_VIDEO_TITLE
        )
    else:
        desired_values = {
            "title": ASIATI_ONBOARDING_MODULE_4_VIDEO_TITLE,
            "description": ASIATI_ONBOARDING_MODULE_4_VIDEO_DESCRIPTION,
            "duration_seconds": ASIATI_ONBOARDING_MODULE_4_DURATION_SECONDS,
            "content_type": "VIDEO",
            "external_url": None,
            "estimated_minutes": 2,
            "checklist_items": [],
            "is_optional": False,
            "position": 1,
        }
        if not video.video_storage_key:
            desired_values["video_url"] = ASIATI_ONBOARDING_MODULE_4_VIDEO_URL
        for field, value in desired_values.items():
            if getattr(video, field) != value:
                setattr(video, field, value)
                changed = True

    checklist = next(
        (
            lesson
            for lesson in module_four.lessons
            if lesson.title == ASIATI_ONBOARDING_MODULE_4_CHECKLIST_TITLE
        ),
        None,
    )
    if checklist is None:
        add_lesson(
            db,
            module_id=module_four.id,
            title=ASIATI_ONBOARDING_MODULE_4_CHECKLIST_TITLE,
            description=(
                "Confirma estos puntos antes de considerar terminado el módulo."
            ),
            video_url=None,
            duration_seconds=None,
            content_type="CHECKLIST",
            estimated_minutes=1,
            checklist_items=ASIATI_ONBOARDING_MODULE_4_CHECKLIST_ITEMS,
            is_optional=False,
        )
    else:
        desired_values = {
            "description": "Confirma estos puntos antes de considerar terminado el módulo.",
            "video_url": None,
            "duration_seconds": None,
            "content_type": "CHECKLIST",
            "external_url": None,
            "estimated_minutes": 1,
            "checklist_items": list(ASIATI_ONBOARDING_MODULE_4_CHECKLIST_ITEMS),
            "is_optional": False,
            "position": 2,
        }
        for field, value in desired_values.items():
            if getattr(checklist, field) != value:
                setattr(checklist, field, value)
                changed = True

    if changed:
        db.commit()
    elif created_module:
        db.commit()
    return require_course(db, course.id)


ASIATI_ONBOARDING_MODULE_5_TITLE = "Módulo 5 · Contenido corporativo"
ASIATI_ONBOARDING_MODULE_5_VIDEO_TITLE = "Módulo 5"
ASIATI_ONBOARDING_MODULE_5_VIDEO_URL = (
    "https://drive.google.com/file/d/"
    "1xITvIp8VAg4bkwIt0BFQX4UH2rYZ-CBu/view?usp=drivesdk"
)
ASIATI_ONBOARDING_MODULE_5_DESCRIPTION = (
    "Continúa tu ruta con el quinto contenido corporativo de ASIATI. "
    "La temática se mantiene neutra hasta validar el material fuente completo."
)
ASIATI_ONBOARDING_MODULE_5_VIDEO_DESCRIPTION = (
    "Contenido corporativo correspondiente al Módulo 5 de la inducción ASIATI."
)


def _ensure_asiati_module_5(
    db: Session,
    *,
    course: TrainingCourse,
) -> TrainingCourse:
    module_five = next(
        (
            module
            for module in course.modules
            if module.title == ASIATI_ONBOARDING_MODULE_5_TITLE
        ),
        None,
    )
    if module_five is None:
        module_five = add_module(
            db,
            course_id=course.id,
            title=ASIATI_ONBOARDING_MODULE_5_TITLE,
            description=ASIATI_ONBOARDING_MODULE_5_DESCRIPTION,
        )
        course = require_course(db, course.id)
        module_five = next(
            module
            for module in course.modules
            if module.id == module_five.id
        )

        # Insert module 5 directly after module 4.
        for module in course.modules:
            if module.id != module_five.id and module.position >= 5:
                module.position += 1
        module_five.position = 5
        db.commit()
        course = require_course(db, course.id)
        module_five = next(
            module
            for module in course.modules
            if module.id == module_five.id
        )

    changed = False
    if module_five.description != ASIATI_ONBOARDING_MODULE_5_DESCRIPTION:
        module_five.description = ASIATI_ONBOARDING_MODULE_5_DESCRIPTION
        changed = True

    video = next(
        (
            lesson
            for lesson in module_five.lessons
            if lesson.title in {
                ASIATI_ONBOARDING_MODULE_5_VIDEO_TITLE,
                "Módulo 5 · Recorrido de sede",
            }
        ),
        None,
    )
    if video is None:
        # Reuse the previous placeholder when repairing an existing draft so
        # employee progress stays attached to the same lesson record.
        for module in course.modules:
            if module.id == module_five.id:
                continue
            video = next(
                (
                    lesson
                    for lesson in module.lessons
                    if lesson.title == "Módulo 5 · Recorrido de sede"
                ),
                None,
            )
            if video is not None:
                video.module_id = module_five.id
                video.module = module_five
                changed = True
                break

    if video is None:
        add_lesson(
            db,
            module_id=module_five.id,
            title=ASIATI_ONBOARDING_MODULE_5_VIDEO_TITLE,
            description=ASIATI_ONBOARDING_MODULE_5_VIDEO_DESCRIPTION,
            video_url=ASIATI_ONBOARDING_MODULE_5_VIDEO_URL,
            duration_seconds=None,
            content_type="VIDEO",
            estimated_minutes=None,
            is_optional=False,
        )
    else:
        desired_values = {
            "title": ASIATI_ONBOARDING_MODULE_5_VIDEO_TITLE,
            "description": ASIATI_ONBOARDING_MODULE_5_VIDEO_DESCRIPTION,
            "duration_seconds": None,
            "content_type": "VIDEO",
            "external_url": None,
            "estimated_minutes": None,
            "checklist_items": [],
            "is_optional": False,
            "position": 1,
        }
        if not video.video_storage_key:
            desired_values["video_url"] = ASIATI_ONBOARDING_MODULE_5_VIDEO_URL
        for field, value in desired_values.items():
            if getattr(video, field) != value:
                setattr(video, field, value)
                changed = True

    if changed:
        db.commit()
    return require_course(db, course.id)


ASIATI_ONBOARDING_MODULE_6_TITLE = "Módulo 6 · Cultura interna"
ASIATI_ONBOARDING_MODULE_6_VIDEO_TITLE = "Cultura interna"
ASIATI_ONBOARDING_MODULE_6_VIDEO_URL = (
    "https://drive.google.com/file/d/"
    "1HuAXb7anjLZWPik9RjuJiUmqLTqQQybj/view?usp=drivesdk"
)
ASIATI_ONBOARDING_MODULE_6_DURATION_SECONDS = 29
ASIATI_ONBOARDING_MODULE_6_DESCRIPTION = (
    "Conoce una pieza breve sobre comportamientos y hábitos cotidianos que "
    "forman parte de la cultura interna de ASIATI."
)
ASIATI_ONBOARDING_MODULE_6_VIDEO_DESCRIPTION = (
    "Un vistazo breve a la forma de vivir la cultura de ASIATI en el día a día."
)


def _ensure_asiati_module_6(
    db: Session,
    *,
    course: TrainingCourse,
) -> TrainingCourse:
    module_six = next(
        (
            module
            for module in course.modules
            if module.title == ASIATI_ONBOARDING_MODULE_6_TITLE
        ),
        None,
    )
    if module_six is None:
        module_six = add_module(
            db,
            course_id=course.id,
            title=ASIATI_ONBOARDING_MODULE_6_TITLE,
            description=ASIATI_ONBOARDING_MODULE_6_DESCRIPTION,
        )
        course = require_course(db, course.id)
        module_six = next(
            module
            for module in course.modules
            if module.id == module_six.id
        )

        # Insert module 6 directly after module 5.
        for module in course.modules:
            if module.id != module_six.id and module.position >= 6:
                module.position += 1
        module_six.position = 6
        db.commit()
        course = require_course(db, course.id)
        module_six = next(
            module
            for module in course.modules
            if module.id == module_six.id
        )

    changed = False
    if module_six.description != ASIATI_ONBOARDING_MODULE_6_DESCRIPTION:
        module_six.description = ASIATI_ONBOARDING_MODULE_6_DESCRIPTION
        changed = True

    video = next(
        (
            lesson
            for lesson in module_six.lessons
            if lesson.title in {
                ASIATI_ONBOARDING_MODULE_6_VIDEO_TITLE,
                "Módulo 6 · Cultura interna",
            }
        ),
        None,
    )
    if video is None:
        # Reuse the old lesson from the temporary "Así trabajamos" module so
        # existing employee progress remains attached to the same record.
        for module in course.modules:
            if module.id == module_six.id:
                continue
            video = next(
                (
                    lesson
                    for lesson in module.lessons
                    if lesson.title == "Módulo 6 · Cultura interna"
                ),
                None,
            )
            if video is not None:
                video.module_id = module_six.id
                video.module = module_six
                changed = True
                break

    if video is None:
        add_lesson(
            db,
            module_id=module_six.id,
            title=ASIATI_ONBOARDING_MODULE_6_VIDEO_TITLE,
            description=ASIATI_ONBOARDING_MODULE_6_VIDEO_DESCRIPTION,
            video_url=ASIATI_ONBOARDING_MODULE_6_VIDEO_URL,
            duration_seconds=ASIATI_ONBOARDING_MODULE_6_DURATION_SECONDS,
            content_type="VIDEO",
            estimated_minutes=1,
            is_optional=False,
        )
    else:
        desired_values = {
            "title": ASIATI_ONBOARDING_MODULE_6_VIDEO_TITLE,
            "description": ASIATI_ONBOARDING_MODULE_6_VIDEO_DESCRIPTION,
            "duration_seconds": ASIATI_ONBOARDING_MODULE_6_DURATION_SECONDS,
            "content_type": "VIDEO",
            "external_url": None,
            "estimated_minutes": 1,
            "checklist_items": [],
            "is_optional": False,
            "position": 1,
        }
        if not video.video_storage_key:
            desired_values["video_url"] = ASIATI_ONBOARDING_MODULE_6_VIDEO_URL
        for field, value in desired_values.items():
            if getattr(video, field) != value:
                setattr(video, field, value)
                changed = True

    if changed:
        db.commit()
    return require_course(db, course.id)


ASIATI_ONBOARDING_MODULE_7_TITLE = "Módulo 7 · Lo que esperamos de ti"
ASIATI_ONBOARDING_MODULE_7_VIDEO_TITLE = "Lo que esperamos de ti"
ASIATI_ONBOARDING_MODULE_7_VIDEO_URL = (
    "https://drive.google.com/file/d/"
    "1y4FII6hl25cIADCUWMRr_gS-0AKY3uJW/view?usp=drivesdk"
)
ASIATI_ONBOARDING_MODULE_7_DURATION_SECONDS = 55
ASIATI_ONBOARDING_MODULE_7_DESCRIPTION = (
    "Cierra la inducción corporativa con las expectativas que ASIATI presenta "
    "para esta nueva etapa dentro del equipo."
)
ASIATI_ONBOARDING_MODULE_7_VIDEO_DESCRIPTION = (
    "Mensaje de cierre sobre las expectativas para tu incorporación a ASIATI."
)
ASIATI_ONBOARDING_MODULE_7_ACK_TITLE = "Confirmación de comprensión"
ASIATI_ONBOARDING_MODULE_7_ACK_ITEMS = [
    "He visto el módulo y entiendo las expectativas presentadas para mi incorporación a ASIATI.",
]


def _ensure_asiati_module_7(
    db: Session,
    *,
    course: TrainingCourse,
) -> TrainingCourse:
    module_seven = next(
        (
            module
            for module in course.modules
            if module.title == ASIATI_ONBOARDING_MODULE_7_TITLE
        ),
        None,
    )
    if module_seven is None:
        module_seven = add_module(
            db,
            course_id=course.id,
            title=ASIATI_ONBOARDING_MODULE_7_TITLE,
            description=ASIATI_ONBOARDING_MODULE_7_DESCRIPTION,
        )
        course = require_course(db, course.id)
        module_seven = next(
            module
            for module in course.modules
            if module.id == module_seven.id
        )

        # Insert module 7 directly after module 6.
        for module in course.modules:
            if module.id != module_seven.id and module.position >= 7:
                module.position += 1
        module_seven.position = 7
        db.commit()
        course = require_course(db, course.id)
        module_seven = next(
            module
            for module in course.modules
            if module.id == module_seven.id
        )

    changed = False
    if module_seven.description != ASIATI_ONBOARDING_MODULE_7_DESCRIPTION:
        module_seven.description = ASIATI_ONBOARDING_MODULE_7_DESCRIPTION
        changed = True

    video = next(
        (
            lesson
            for lesson in module_seven.lessons
            if lesson.title in {
                ASIATI_ONBOARDING_MODULE_7_VIDEO_TITLE,
                "Módulo 7 · Lo que esperamos de ti",
            }
        ),
        None,
    )
    if video is None:
        for module in course.modules:
            if module.id == module_seven.id:
                continue
            video = next(
                (
                    lesson
                    for lesson in module.lessons
                    if lesson.title == "Módulo 7 · Lo que esperamos de ti"
                ),
                None,
            )
            if video is not None:
                video.module_id = module_seven.id
                video.module = module_seven
                changed = True
                break

    if video is None:
        add_lesson(
            db,
            module_id=module_seven.id,
            title=ASIATI_ONBOARDING_MODULE_7_VIDEO_TITLE,
            description=ASIATI_ONBOARDING_MODULE_7_VIDEO_DESCRIPTION,
            video_url=ASIATI_ONBOARDING_MODULE_7_VIDEO_URL,
            duration_seconds=ASIATI_ONBOARDING_MODULE_7_DURATION_SECONDS,
            content_type="VIDEO",
            estimated_minutes=1,
            is_optional=False,
        )
    else:
        desired_values = {
            "title": ASIATI_ONBOARDING_MODULE_7_VIDEO_TITLE,
            "description": ASIATI_ONBOARDING_MODULE_7_VIDEO_DESCRIPTION,
            "duration_seconds": ASIATI_ONBOARDING_MODULE_7_DURATION_SECONDS,
            "content_type": "VIDEO",
            "external_url": None,
            "estimated_minutes": 1,
            "checklist_items": [],
            "is_optional": False,
            "position": 1,
        }
        if not video.video_storage_key:
            desired_values["video_url"] = ASIATI_ONBOARDING_MODULE_7_VIDEO_URL
        for field, value in desired_values.items():
            if getattr(video, field) != value:
                setattr(video, field, value)
                changed = True

    acknowledgement = next(
        (
            lesson
            for lesson in module_seven.lessons
            if lesson.title == ASIATI_ONBOARDING_MODULE_7_ACK_TITLE
        ),
        None,
    )
    if acknowledgement is None:
        add_lesson(
            db,
            module_id=module_seven.id,
            title=ASIATI_ONBOARDING_MODULE_7_ACK_TITLE,
            description="Confirma que completaste y comprendiste el mensaje de cierre.",
            video_url=None,
            duration_seconds=None,
            content_type="CHECKLIST",
            estimated_minutes=1,
            checklist_items=ASIATI_ONBOARDING_MODULE_7_ACK_ITEMS,
            is_optional=False,
        )
    else:
        desired_values = {
            "description": "Confirma que completaste y comprendiste el mensaje de cierre.",
            "video_url": None,
            "duration_seconds": None,
            "content_type": "CHECKLIST",
            "external_url": None,
            "estimated_minutes": 1,
            "checklist_items": list(ASIATI_ONBOARDING_MODULE_7_ACK_ITEMS),
            "is_optional": False,
            "position": 2,
        }
        for field, value in desired_values.items():
            if getattr(acknowledgement, field) != value:
                setattr(acknowledgement, field, value)
                changed = True

    if changed:
        db.commit()

    # "Así trabajamos" was only a temporary container for modules 4–7.
    # Remove it once empty, but preserve it if an administrator added content.
    course = require_course(db, course.id)
    temporary_module = next(
        (
            module
            for module in course.modules
            if module.title == "Así trabajamos"
        ),
        None,
    )
    if temporary_module is not None and not temporary_module.lessons:
        db.delete(temporary_module)
        db.commit()

    return require_course(db, course.id)


ASIATI_ROLE_CHECKLIST_ITEMS = [
    "Conozco el alcance principal de mi cargo.",
    "Sé cuáles son mis responsabilidades prioritarias.",
    "Tengo identificadas las herramientas y accesos que necesito.",
    "Sé quién es mi líder o punto de apoyo.",
    "Entiendo los objetivos de mi primera semana.",
]


def _ensure_asiati_role_checklist(
    db: Session,
    *,
    course: TrainingCourse,
) -> None:
    changed = False
    for module in course.modules:
        for lesson in module.lessons:
            if (
                lesson.title == "Tu rol y tus primeros días"
                and str(lesson.content_type or "").upper() == "CHECKLIST"
                and not list(lesson.checklist_items or [])
            ):
                lesson.checklist_items = list(ASIATI_ROLE_CHECKLIST_ITEMS)
                changed = True
    if changed:
        db.commit()


ASIATI_ONBOARDING_BASE_QUIZ = [
    (
        "¿Cuál es el sitio web corporativo oficial incluido en la inducción?",
        [
            "asiaticorp.com",
            "El Retrovisor",
            "Wiilog",
            "Origen Vital",
        ],
        0,
    ),
    (
        "¿Cuál de estas iniciativas aparece dentro del ecosistema ASIATI presentado en la ruta?",
        [
            "Wiilog",
            "Coursera",
            "LinkedIn Learning",
            "Udemy",
        ],
        0,
    ),
    (
        "¿En qué plataforma se presenta El Retrovisor dentro de los recursos del onboarding?",
        [
            "YouTube",
            "Canva",
            "Portal de vacaciones",
            "Google Calendar",
        ],
        0,
    ),
    (
        "¿Qué debes revisar en la etapa 'Tu cargo en ASIATI'?",
        [
            "Alcance, responsabilidades, herramientas y objetivos de tus primeros días",
            "Únicamente el organigrama",
            "Solo las redes sociales corporativas",
            "Únicamente permisos y vacaciones",
        ],
        0,
    ),
    (
        "Si necesitas detener la inducción antes de terminar, ¿qué puedes hacer?",
        [
            "Retomarla después desde tu avance guardado",
            "Empezar obligatoriamente desde cero",
            "Solicitar que eliminen el curso",
            "Perder el acceso a la ruta",
        ],
        0,
    ),
]


def _ensure_asiati_onboarding_quiz_questions(
    db: Session,
    *,
    quiz: TrainingQuiz,
) -> None:
    if quiz.questions:
        return

    for prompt, options, correct_option in ASIATI_ONBOARDING_BASE_QUIZ:
        add_quiz_question(
            db,
            quiz_id=quiz.id,
            prompt=prompt,
            options=options,
            correct_option=correct_option,
        )


def create_asiati_onboarding_template(
    db: Session,
    *,
    created_by_sub: str,
) -> TrainingCourse:
    existing = (
        db.query(TrainingCourse)
        .filter(
            TrainingCourse.title == "Onboarding ASIATI",
            TrainingCourse.is_onboarding.is_(True),
            TrainingCourse.status == "DRAFT",
        )
        .order_by(TrainingCourse.created_at.desc())
        .first()
    )
    if existing is not None:
        changed = False
        empty_final_modules = [
            module
            for module in existing.modules
            if module.title == "Evaluación final" and not module.lessons
        ]
        for module in empty_final_modules:
            db.delete(module)
            changed = True
        quiz = existing.quiz
        if quiz is None:
            quiz = create_quiz(
                db,
                course_id=existing.id,
                title="Evaluación final",
                passing_score=70,
                created_by_sub=created_by_sub,
            )
        _ensure_asiati_onboarding_quiz_questions(db, quiz=quiz)
        if changed:
            db.commit()
        refreshed = _ensure_asiati_module_1(
            db,
            course=require_course(db, existing.id),
        )
        refreshed = _ensure_asiati_module_2(
            db,
            course=refreshed,
        )
        refreshed = _ensure_asiati_module_3(
            db,
            course=refreshed,
        )
        refreshed = _ensure_asiati_module_4(
            db,
            course=refreshed,
        )
        refreshed = _ensure_asiati_module_5(
            db,
            course=refreshed,
        )
        refreshed = _ensure_asiati_module_6(
            db,
            course=refreshed,
        )
        refreshed = _ensure_asiati_module_7(
            db,
            course=refreshed,
        )
        _ensure_asiati_role_checklist(
            db,
            course=require_course(db, existing.id),
        )
        return require_course(db, existing.id)

    course = create_course(
        db,
        title="Onboarding ASIATI",
        description=(
            "Ruta de inducción corporativa en bloques cortos: ASIATI, ecosistema, "
            "forma de trabajo, rol y evaluación final."
        ),
        created_by_sub=created_by_sub,
        is_onboarding=True,
    )

    welcome = add_module(
        db,
        course_id=course.id,
        title=ASIATI_ONBOARDING_MODULE_1_TITLE,
        description=ASIATI_ONBOARDING_MODULE_1_DESCRIPTION,
    )
    add_lesson(
        db,
        module_id=welcome.id,
        title=ASIATI_ONBOARDING_MODULE_1_LESSON_TITLE,
        description=ASIATI_ONBOARDING_MODULE_1_LESSON_DESCRIPTION,
        video_url=ASIATI_ONBOARDING_MODULE_1_VIDEO_URL,
        duration_seconds=ASIATI_ONBOARDING_MODULE_1_DURATION_SECONDS,
        content_type="VIDEO",
        estimated_minutes=1,
        is_optional=False,
    )

    asiati = add_module(
        db,
        course_id=course.id,
        title=ASIATI_ONBOARDING_MODULE_2_TITLE,
        description=ASIATI_ONBOARDING_MODULE_2_DESCRIPTION,
    )
    add_lesson(
        db,
        module_id=asiati.id,
        title=ASIATI_ONBOARDING_MODULE_2_LESSON_TITLE,
        description=ASIATI_ONBOARDING_MODULE_2_LESSON_DESCRIPTION,
        video_url=ASIATI_ONBOARDING_MODULE_2_VIDEO_URL,
        duration_seconds=ASIATI_ONBOARDING_MODULE_2_DURATION_SECONDS,
        content_type="VIDEO",
        estimated_minutes=1,
        is_optional=False,
    )
    for title, url, minutes, optional in [
        ("Presentación ASIATI I", "https://canva.link/ub9ggivhfxawuoh", 5, True),
        ("Presentación ASIATI II", "https://canva.link/kma1whh1rya59td", 5, True),
        ("Página oficial de ASIATI Corp", "https://www.asiaticorp.com/", 3, True),
    ]:
        add_lesson(
            db,
            module_id=asiati.id,
            title=title,
            description="Recurso corporativo oficial.",
            video_url=None,
            duration_seconds=None,
            content_type="RESOURCE",
            external_url=url,
            estimated_minutes=minutes,
            is_optional=optional,
        )

    add_lesson(
        db,
        module_id=asiati.id,
        title="Mapa del ecosistema ASIATI",
        description=(
            "ASIATI Corp integra iniciativas de comercio, logística, marcas de "
            "consumo y contenido. Revísalo como material complementario."
        ),
        video_url=None,
        duration_seconds=None,
        content_type="ARTICLE",
        estimated_minutes=3,
        is_optional=True,
    )
    for title, url in [
        ("ASIATI Corp", "https://www.instagram.com/asiati_corp/?hl=es"),
        ("ASIATI Commerce", "https://www.instagram.com/asiati_ecommerce/?hl=es"),
        ("Wiilog", "https://www.instagram.com/wiilog_logistica/?hl=es"),
        ("Origen Vital", "https://www.instagram.com/origen_vital_col/"),
        ("Chin Chin", "https://www.instagram.com/chin_chin_bodega/?hl=es-la"),
        ("El Retrovisor", "https://www.youtube.com/@Elretrovisor.podcast"),
    ]:
        add_lesson(
            db,
            module_id=asiati.id,
            title=title,
            description="Material complementario para conocer esta marca.",
            video_url=None,
            duration_seconds=None,
            content_type="RESOURCE",
            external_url=url,
            estimated_minutes=2,
            is_optional=True,
        )

    team_module = add_module(
        db,
        course_id=course.id,
        title=ASIATI_ONBOARDING_MODULE_3_TITLE,
        description=ASIATI_ONBOARDING_MODULE_3_DESCRIPTION,
    )
    for name, url, duration_seconds in ASIATI_ONBOARDING_MODULE_3_TEAM:
        add_lesson(
            db,
            module_id=team_module.id,
            title=name,
            description=f"Conoce a {name} y su participación dentro del equipo ASIATI.",
            video_url=url,
            duration_seconds=duration_seconds,
            content_type="VIDEO",
            estimated_minutes=max(1, (duration_seconds + 59) // 60),
            is_optional=False,
        )

    module_four = add_module(
        db,
        course_id=course.id,
        title=ASIATI_ONBOARDING_MODULE_4_TITLE,
        description=ASIATI_ONBOARDING_MODULE_4_DESCRIPTION,
    )
    add_lesson(
        db,
        module_id=module_four.id,
        title=ASIATI_ONBOARDING_MODULE_4_VIDEO_TITLE,
        description=ASIATI_ONBOARDING_MODULE_4_VIDEO_DESCRIPTION,
        video_url=ASIATI_ONBOARDING_MODULE_4_VIDEO_URL,
        duration_seconds=ASIATI_ONBOARDING_MODULE_4_DURATION_SECONDS,
        content_type="VIDEO",
        estimated_minutes=2,
        is_optional=False,
    )
    add_lesson(
        db,
        module_id=module_four.id,
        title=ASIATI_ONBOARDING_MODULE_4_CHECKLIST_TITLE,
        description="Confirma estos puntos antes de considerar terminado el módulo.",
        video_url=None,
        duration_seconds=None,
        content_type="CHECKLIST",
        estimated_minutes=1,
        checklist_items=ASIATI_ONBOARDING_MODULE_4_CHECKLIST_ITEMS,
        is_optional=False,
    )

    module_five = add_module(
        db,
        course_id=course.id,
        title=ASIATI_ONBOARDING_MODULE_5_TITLE,
        description=ASIATI_ONBOARDING_MODULE_5_DESCRIPTION,
    )
    add_lesson(
        db,
        module_id=module_five.id,
        title=ASIATI_ONBOARDING_MODULE_5_VIDEO_TITLE,
        description=ASIATI_ONBOARDING_MODULE_5_VIDEO_DESCRIPTION,
        video_url=ASIATI_ONBOARDING_MODULE_5_VIDEO_URL,
        duration_seconds=None,
        content_type="VIDEO",
        estimated_minutes=None,
        is_optional=False,
    )

    module_six = add_module(
        db,
        course_id=course.id,
        title=ASIATI_ONBOARDING_MODULE_6_TITLE,
        description=ASIATI_ONBOARDING_MODULE_6_DESCRIPTION,
    )
    add_lesson(
        db,
        module_id=module_six.id,
        title=ASIATI_ONBOARDING_MODULE_6_VIDEO_TITLE,
        description=ASIATI_ONBOARDING_MODULE_6_VIDEO_DESCRIPTION,
        video_url=ASIATI_ONBOARDING_MODULE_6_VIDEO_URL,
        duration_seconds=ASIATI_ONBOARDING_MODULE_6_DURATION_SECONDS,
        content_type="VIDEO",
        estimated_minutes=1,
        is_optional=False,
    )

    module_seven = add_module(
        db,
        course_id=course.id,
        title=ASIATI_ONBOARDING_MODULE_7_TITLE,
        description=ASIATI_ONBOARDING_MODULE_7_DESCRIPTION,
    )
    add_lesson(
        db,
        module_id=module_seven.id,
        title=ASIATI_ONBOARDING_MODULE_7_VIDEO_TITLE,
        description=ASIATI_ONBOARDING_MODULE_7_VIDEO_DESCRIPTION,
        video_url=ASIATI_ONBOARDING_MODULE_7_VIDEO_URL,
        duration_seconds=ASIATI_ONBOARDING_MODULE_7_DURATION_SECONDS,
        content_type="VIDEO",
        estimated_minutes=1,
        is_optional=False,
    )
    add_lesson(
        db,
        module_id=module_seven.id,
        title=ASIATI_ONBOARDING_MODULE_7_ACK_TITLE,
        description="Confirma que completaste y comprendiste el mensaje de cierre.",
        video_url=None,
        duration_seconds=None,
        content_type="CHECKLIST",
        estimated_minutes=1,
        checklist_items=ASIATI_ONBOARDING_MODULE_7_ACK_ITEMS,
        is_optional=False,
    )

    role_module = add_module(
        db,
        course_id=course.id,
        title="Tu cargo en ASIATI",
        description=(
            "Conoce el alcance de tu rol, responsabilidades, herramientas y "
            "objetivos de tus primeros días."
        ),
    )
    add_lesson(
        db,
        module_id=role_module.id,
        title="Tu rol y tus primeros días",
        description=(
            "Revisa con tu líder el alcance de tu cargo, responsabilidades, "
            "herramientas y objetivos de la primera semana."
        ),
        video_url=None,
        duration_seconds=None,
        content_type="CHECKLIST",
        estimated_minutes=5,
        checklist_items=ASIATI_ROLE_CHECKLIST_ITEMS,
    )
    quiz = create_quiz(
        db,
        course_id=course.id,
        title="Evaluación final",
        passing_score=70,
        created_by_sub=created_by_sub,
    )
    _ensure_asiati_onboarding_quiz_questions(db, quiz=quiz)
    normalized_course = _ensure_asiati_module_1(
        db,
        course=require_course(db, course.id),
    )
    normalized_course = _ensure_asiati_module_2(
        db,
        course=normalized_course,
    )
    normalized_course = _ensure_asiati_module_3(
        db,
        course=normalized_course,
    )
    normalized_course = _ensure_asiati_module_4(
        db,
        course=normalized_course,
    )
    normalized_course = _ensure_asiati_module_5(
        db,
        course=normalized_course,
    )
    normalized_course = _ensure_asiati_module_6(
        db,
        course=normalized_course,
    )
    normalized_course = _ensure_asiati_module_7(
        db,
        course=normalized_course,
    )
    _ensure_asiati_role_checklist(
        db,
        course=require_course(db, course.id),
    )

    return require_course(db, course.id)


ASIATI_ONBOARDING_REQUIRED_MODULE_TITLES = {
    "Módulo 1 · Bienvenida a ASIATI",
    "Módulo 2 · Conoce ASIATI",
    "Módulo 3 · Conoce al equipo",
    "Módulo 4 · Permisos y vacaciones",
    "Módulo 5 · Contenido corporativo",
    "Módulo 6 · Cultura interna",
    "Módulo 7 · Lo que esperamos de ti",
}


def _is_current_asiati_onboarding(course: TrainingCourse) -> bool:
    module_titles = {module.title for module in course.modules}
    return (
        course.title == "Onboarding ASIATI"
        and bool(course.is_onboarding)
        and ASIATI_ONBOARDING_REQUIRED_MODULE_TITLES.issubset(module_titles)
        and course.quiz is not None
        and len(course.quiz.questions) >= 5
    )


def ensure_published_asiati_onboarding(
    db: Session,
    *,
    created_by_sub: str,
) -> TrainingCourse:
    """Return the current published ASIATI onboarding, publishing the preset when needed."""

    published = (
        db.query(TrainingCourse)
        .filter(
            TrainingCourse.title == "Onboarding ASIATI",
            TrainingCourse.is_onboarding.is_(True),
            TrainingCourse.status == "PUBLISHED",
        )
        .order_by(TrainingCourse.created_at.desc())
        .all()
    )
    current = next(
        (course for course in published if _is_current_asiati_onboarding(course)),
        None,
    )
    if current is not None:
        return current

    course = create_asiati_onboarding_template(
        db,
        created_by_sub=created_by_sub,
    )
    if course.status == "DRAFT":
        course = update_course(
            db,
            course.id,
            status="PUBLISHED",
        )
    return course


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

