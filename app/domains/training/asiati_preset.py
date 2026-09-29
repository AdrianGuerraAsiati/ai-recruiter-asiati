"""ASIATI onboarding preset builder.

This module owns the large, organization-specific preset so the generic training
service can stay focused on catalog, assignment, progress and quiz operations.
"""

from __future__ import annotations

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.domains.training.asiati_media import migrate_default_onboarding_videos_to_s3
from app.domains.training.errors import TrainingNotFound, TrainingStateError
from app.models import (
    TrainingCourse,
    TrainingLesson,
    TrainingModule,
    TrainingQuiz,
    TrainingQuizQuestion,
)


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


def require_quiz(db: Session, quiz_id: str) -> TrainingQuiz:
    quiz = db.query(TrainingQuiz).filter(TrainingQuiz.id == quiz_id).one_or_none()
    if quiz is None:
        raise TrainingNotFound()
    return quiz


def create_course(
    db: Session,
    *,
    title: str,
    description: str | None,
    created_by_sub: str,
    is_onboarding: bool = False,
    managed_by_system: bool = False,
) -> TrainingCourse:
    course = TrainingCourse(
        title=title.strip(),
        description=(description or "").strip() or None,
        is_onboarding=is_onboarding,
        managed_by_system=managed_by_system,
        status="DRAFT",
        created_by_sub=created_by_sub,
    )
    db.add(course)
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


def _course_counts(course: TrainingCourse) -> tuple[int, int]:
    return len(course.modules), sum(len(module.lessons) for module in course.modules)


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


ASIATI_ONBOARDING_MODULE_2_TITLE = "Módulo 2 · Entiende el negocio"
ASIATI_ONBOARDING_MODULE_2_LESSON_TITLE = "Quiénes somos y qué hacemos"
ASIATI_ONBOARDING_MODULE_2_VIDEO_URL = (
    "https://drive.google.com/file/d/"
    "1zPS0k293LFvAQK4yrXVtOLoP5X-g9i7t/view?usp=drivesdk"
)
ASIATI_ONBOARDING_MODULE_2_DURATION_SECONDS = 38
ASIATI_ONBOARDING_MODULE_2_DESCRIPTION = (
    "Entiende qué hace ASIATI, cómo conectamos operación, logística y tecnología, "
    "qué iniciativas forman parte del ecosistema y cómo tu trabajo se conecta con "
    "el valor que entregamos como compañía."
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


ASIATI_ONBOARDING_MODULE_4_TITLE = "Módulo 4 · Cómo trabajamos · permisos y vacaciones"
ASIATI_ONBOARDING_MODULE_4_VIDEO_TITLE = "Permisos y vacaciones"
ASIATI_ONBOARDING_MODULE_4_VIDEO_URL = (
    "https://drive.google.com/file/d/"
    "13wZ5Dmv7x19DuRJt_5K55OpQ3nMb6K4x/view?usp=drivesdk"
)
ASIATI_ONBOARDING_MODULE_4_DURATION_SECONDS = 105
ASIATI_ONBOARDING_MODULE_4_DESCRIPTION = (
    "Aterriza cómo se trabaja en el día a día: comunicación oportuna, coordinación "
    "con tu líder y el flujo interno para tramitar permisos y vacaciones."
)
ASIATI_ONBOARDING_MODULE_4_VIDEO_DESCRIPTION = (
    "Revisa el procedimiento corporativo de permisos y vacaciones y los "
    "formatos que debes usar para cada solicitud."
)
ASIATI_ONBOARDING_MODULE_4_CHECKLIST_TITLE = "Antes de enviar tu solicitud"
ASIATI_ONBOARDING_MODULE_4_LEGACY_CHECKLIST_ITEMS = [
    "Identifiqué el formato que corresponde a mi solicitud.",
    "Sé que debo diligenciar la información solicitada antes de enviarla.",
    "Confirmaré la aprobación de mi líder de acuerdo con el procedimiento.",
    "Para vacaciones, revisaré el checklist correspondiente antes de cerrar la solicitud.",
]
ASIATI_ONBOARDING_MODULE_4_CHECKLIST_ITEMS = [
    "Identifiqué el formato que corresponde a mi solicitud.",
    "Sé que debo diligenciar la información solicitada antes de enviarla.",
    "Confirmaré la aprobación de mi líder de acuerdo con el procedimiento.",
    "Para vacaciones, revisaré el checklist correspondiente antes de cerrar la solicitud.",
    "Tengo claro con mi líder cómo comunicar a tiempo una ausencia, novedad o bloqueo que afecte mi trabajo.",
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
            if module.title in {
                "Módulo 4 · Permisos y vacaciones",
                ASIATI_ONBOARDING_MODULE_4_TITLE,
            }
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
    if module_four.title != ASIATI_ONBOARDING_MODULE_4_TITLE:
        module_four.title = ASIATI_ONBOARDING_MODULE_4_TITLE
        changed = True
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
ASIATI_ONBOARDING_MODULE_5_SECURITY_TITLE = "Recursos y seguridad · confirma con tu líder"
ASIATI_ONBOARDING_MODULE_5_SECURITY_ITEMS = [
    "Sé que mis credenciales son personales y no debo compartirlas.",
    "Confirmé cuáles son las herramientas y accesos autorizados que necesito para mi cargo.",
    "Sé a quién acudir si pierdo un acceso o detecto un posible incidente de seguridad.",
    "Entiendo que la información de clientes y de la empresa debe usarse únicamente para fines autorizados.",
]


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

    security_checklist = next(
        (
            lesson
            for lesson in module_five.lessons
            if lesson.title == ASIATI_ONBOARDING_MODULE_5_SECURITY_TITLE
        ),
        None,
    )
    if security_checklist is None:
        add_lesson(
            db,
            module_id=module_five.id,
            title=ASIATI_ONBOARDING_MODULE_5_SECURITY_TITLE,
            description=(
                "Antes de empezar a operar, confirma con tu líder los accesos, "
                "herramientas y reglas básicas para proteger la información."
            ),
            video_url=None,
            duration_seconds=None,
            content_type="CHECKLIST",
            estimated_minutes=2,
            checklist_items=ASIATI_ONBOARDING_MODULE_5_SECURITY_ITEMS,
            is_optional=False,
        )
    else:
        desired_values = {
            "description": (
                "Antes de empezar a operar, confirma con tu líder los accesos, "
                "herramientas y reglas básicas para proteger la información."
            ),
            "video_url": None,
            "duration_seconds": None,
            "content_type": "CHECKLIST",
            "external_url": None,
            "estimated_minutes": 2,
            "checklist_items": list(ASIATI_ONBOARDING_MODULE_5_SECURITY_ITEMS),
            "is_optional": False,
            "position": 2,
        }
        for field, value in desired_values.items():
            if getattr(security_checklist, field) != value:
                setattr(security_checklist, field, value)
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
ASIATI_ONBOARDING_MODULE_6_BEHAVIOR_TITLE = "Cómo actuar en el día a día"
ASIATI_ONBOARDING_MODULE_6_BEHAVIOR_ITEMS = [
    "Si una tarea se bloquea o está en riesgo, lo comunicaré a tiempo con contexto e impacto.",
    "Pediré ayuda cuando la necesite en lugar de dejar avanzar un bloqueo sin comunicarlo.",
    "Si cometo un error, lo informaré y participaré en la solución.",
    "Documentaré las decisiones relevantes para que el equipo pueda darles continuidad.",
    "Mantendré una comunicación respetuosa y orientada a resolver problemas.",
]


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

    behavior_checklist = next(
        (
            lesson
            for lesson in module_six.lessons
            if lesson.title == ASIATI_ONBOARDING_MODULE_6_BEHAVIOR_TITLE
        ),
        None,
    )
    if behavior_checklist is None:
        add_lesson(
            db,
            module_id=module_six.id,
            title=ASIATI_ONBOARDING_MODULE_6_BEHAVIOR_TITLE,
            description=(
                "Convierte la cultura en decisiones concretas frente a bloqueos, "
                "errores, colaboración y comunicación."
            ),
            video_url=None,
            duration_seconds=None,
            content_type="CHECKLIST",
            estimated_minutes=2,
            checklist_items=ASIATI_ONBOARDING_MODULE_6_BEHAVIOR_ITEMS,
            is_optional=False,
        )
    else:
        desired_values = {
            "description": (
                "Convierte la cultura en decisiones concretas frente a bloqueos, "
                "errores, colaboración y comunicación."
            ),
            "video_url": None,
            "duration_seconds": None,
            "content_type": "CHECKLIST",
            "external_url": None,
            "estimated_minutes": 2,
            "checklist_items": list(ASIATI_ONBOARDING_MODULE_6_BEHAVIOR_ITEMS),
            "is_optional": False,
            "position": 2,
        }
        for field, value in desired_values.items():
            if getattr(behavior_checklist, field) != value:
                setattr(behavior_checklist, field, value)
                changed = True

    if changed:
        db.commit()
    return require_course(db, course.id)


ASIATI_ONBOARDING_MODULE_7_TITLE = "Módulo 7 · Tu rol y tus primeros días"
ASIATI_ONBOARDING_MODULE_7_VIDEO_TITLE = "Lo que esperamos de ti"
ASIATI_ONBOARDING_MODULE_7_VIDEO_URL = (
    "https://drive.google.com/file/d/"
    "1y4FII6hl25cIADCUWMRr_gS-0AKY3uJW/view?usp=drivesdk"
)
ASIATI_ONBOARDING_MODULE_7_DURATION_SECONDS = 55
ASIATI_ONBOARDING_MODULE_7_DESCRIPTION = (
    "Cierra la inducción aterrizando tu cargo: alcance, responsabilidades, "
    "herramientas, apoyos, prioridades y objetivos de tus primeros días."
)
ASIATI_ONBOARDING_MODULE_7_VIDEO_DESCRIPTION = (
    "Mensaje de cierre sobre las expectativas para tu incorporación a ASIATI."
)
ASIATI_ONBOARDING_MODULE_7_ACK_TITLE = "Antes de comenzar"
ASIATI_ONBOARDING_MODULE_7_LEGACY_ACK_ITEMS = [
    "He visto el módulo y entiendo las expectativas presentadas para mi incorporación a ASIATI.",
]
ASIATI_ONBOARDING_MODULE_7_ACK_ITEMS = [
    "Puedo explicar, a nivel general, qué hace ASIATI y cómo mi trabajo aporta al equipo.",
    "Sé quién es mi líder o punto de apoyo y a quién acudir cuando necesito orientación.",
    "Tengo claros los canales que debo usar para comunicar avances, dudas, bloqueos o novedades.",
    "Conozco el procedimiento básico para permisos y vacaciones.",
    "Confirmé las herramientas y accesos que necesito para trabajar.",
    "Entiendo las reglas básicas de cuidado de credenciales e información.",
    "Tengo claros mis objetivos y prioridades de la primera semana.",
    "Sé que debo comunicar a tiempo un problema o riesgo en lugar de esperar a que escale.",
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
            if module.title in {
                "Módulo 7 · Lo que esperamos de ti",
                ASIATI_ONBOARDING_MODULE_7_TITLE,
            }
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
    if module_seven.title != ASIATI_ONBOARDING_MODULE_7_TITLE:
        module_seven.title = ASIATI_ONBOARDING_MODULE_7_TITLE
        changed = True
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
            if lesson.title in {
                "Confirmación de comprensión",
                ASIATI_ONBOARDING_MODULE_7_ACK_TITLE,
            }
        ),
        None,
    )
    if acknowledgement is None:
        add_lesson(
            db,
            module_id=module_seven.id,
            title=ASIATI_ONBOARDING_MODULE_7_ACK_TITLE,
            description=(
                "Comprueba que tienes la información mínima para empezar a trabajar "
                "con claridad y sabes qué debes confirmar con tu líder."
            ),
            video_url=None,
            duration_seconds=None,
            content_type="CHECKLIST",
            estimated_minutes=1,
            checklist_items=ASIATI_ONBOARDING_MODULE_7_ACK_ITEMS,
            is_optional=False,
        )
    else:
        desired_values = {
            "title": ASIATI_ONBOARDING_MODULE_7_ACK_TITLE,
            "description": (
                "Comprueba que tienes la información mínima para empezar a trabajar "
                "con claridad y sabes qué debes confirmar con tu líder."
            ),
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


ASIATI_ROLE_LEGACY_CHECKLIST_ITEMS = [
    "Conozco el alcance principal de mi cargo.",
    "Sé cuáles son mis responsabilidades prioritarias.",
    "Tengo identificadas las herramientas y accesos que necesito.",
    "Sé quién es mi líder o punto de apoyo.",
    "Entiendo los objetivos de mi primera semana.",
]
ASIATI_ROLE_CHECKLIST_ITEMS = [
    "Conozco el alcance principal de mi cargo.",
    "Sé cuáles son mis responsabilidades prioritarias y qué temas debo escalar.",
    "Tengo identificadas las herramientas y accesos que necesito.",
    "Sé quién es mi líder o punto de apoyo.",
    "Entiendo los objetivos de mi primera semana.",
    "Acordé cuáles son mis primeros entregables o resultados esperados.",
    "Sé cómo y con quién revisaré mi progreso durante las primeras semanas.",
]


def _ensure_asiati_role_checklist(
    db: Session,
    *,
    course: TrainingCourse,
) -> None:
    """Keep the role checklist inside module 7 so the default route has 7 modules."""

    module_seven = next(
        (
            module
            for module in course.modules
            if module.title == ASIATI_ONBOARDING_MODULE_7_TITLE
        ),
        None,
    )
    if module_seven is None:
        return

    changed = False
    role_lesson = next(
        (
            lesson
            for module in course.modules
            for lesson in module.lessons
            if lesson.title == "Tu rol y tus primeros días"
            and str(lesson.content_type or "").upper() == "CHECKLIST"
        ),
        None,
    )
    if role_lesson is None:
        db.add(
            TrainingLesson(
                module_id=module_seven.id,
                title="Tu rol y tus primeros días",
                description=(
                    "Revisa con tu líder el alcance de tu cargo, responsabilidades, "
                    "herramientas, primeros entregables y objetivos iniciales."
                ),
                content_type="CHECKLIST",
                estimated_minutes=5,
                checklist_items=list(ASIATI_ROLE_CHECKLIST_ITEMS),
                is_optional=False,
                position=3,
            )
        )
        changed = True
    else:
        if role_lesson.module_id != module_seven.id:
            role_lesson.module_id = module_seven.id
            role_lesson.module = module_seven
            changed = True
        current_items = list(role_lesson.checklist_items or [])
        if not current_items or current_items == ASIATI_ROLE_LEGACY_CHECKLIST_ITEMS:
            role_lesson.checklist_items = list(ASIATI_ROLE_CHECKLIST_ITEMS)
            changed = True
        if role_lesson.description in {
            None,
            "",
            "Revisa con tu líder el alcance de tu cargo, responsabilidades, herramientas y objetivos de la primera semana.",
        }:
            role_lesson.description = (
                "Revisa con tu líder el alcance de tu cargo, responsabilidades, "
                "herramientas, primeros entregables y objetivos iniciales."
            )
            changed = True
        if role_lesson.position != 3:
            role_lesson.position = 3
            changed = True

    role_module = next(
        (module for module in course.modules if module.title == "Tu cargo en ASIATI"),
        None,
    )
    if role_module is not None and not role_module.lessons:
        db.delete(role_module)
        changed = True

    if changed:
        db.commit()


ASIATI_ONBOARDING_LEGACY_QUIZ = [
    (
        "¿Cuál es el sitio web corporativo oficial incluido en la inducción?",
        ["asiaticorp.com", "El Retrovisor", "Wiilog", "Origen Vital"],
        0,
    ),
    (
        "¿Cuál de estas iniciativas aparece dentro del ecosistema ASIATI presentado en la ruta?",
        ["Wiilog", "Coursera", "LinkedIn Learning", "Udemy"],
        0,
    ),
    (
        "¿En qué plataforma se presenta El Retrovisor dentro de los recursos del onboarding?",
        ["YouTube", "Canva", "Portal de vacaciones", "Google Calendar"],
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

ASIATI_ONBOARDING_PREVIOUS_QUIZ = [
    (
        "Según la inducción, ¿qué describe mejor a ASIATI?",
        [
            "Una compañía que conecta operación, logística y tecnología",
            "Una plataforma dedicada únicamente a cursos virtuales",
            "Una agencia enfocada exclusivamente en redes sociales",
            "Un portal interno para solicitar vacaciones",
        ],
        0,
    ),
    (
        "¿Cuál de estas iniciativas del ecosistema ASIATI está relacionada con logística?",
        ["Wiilog", "Coursera", "LinkedIn Learning", "Google Calendar"],
        0,
    ),
    (
        "¿Cuál es el propósito principal del módulo 'Conoce al equipo'?",
        [
            "Identificar a las personas y entender cómo se conecta su trabajo con la compañía",
            "Memorizar únicamente los nombres del equipo",
            "Elegir quién aprobará las vacaciones",
            "Aprender a publicar vacantes",
        ],
        0,
    ),
    (
        "Antes de enviar una solicitud de permiso o vacaciones, ¿qué hace parte del procedimiento?",
        [
            "Usar el formato correspondiente, completar la información y confirmar la aprobación del líder",
            "Enviar únicamente un mensaje informal sin formato",
            "Registrar primero una vacante en el sistema",
            "Esperar a que Talento Humano complete toda la solicitud",
        ],
        0,
    ),
    (
        "Según el módulo de cultura interna, ¿cómo se vive la cultura de ASIATI?",
        [
            "A través de comportamientos y hábitos cotidianos en la forma de trabajar",
            "Únicamente asistiendo a reuniones mensuales",
            "Solo mediante publicaciones en redes sociales",
            "Exclusivamente leyendo documentos corporativos",
        ],
        0,
    ),
    (
        "En tus primeros días, ¿qué deberías revisar con tu líder o punto de apoyo?",
        [
            "El alcance del cargo, responsabilidades, herramientas y objetivos de la primera semana",
            "Solo el nombre exacto de tu cargo",
            "Únicamente las redes sociales de ASIATI",
            "Solo el calendario de vacaciones",
        ],
        0,
    ),
    (
        "Al finalizar el onboarding, ¿qué deberías tener claro?",
        [
            "Las expectativas para tu incorporación y cómo se conecta tu trabajo con ASIATI",
            "Que todos los cargos tienen exactamente las mismas responsabilidades",
            "Que el onboarding reemplaza el acompañamiento de tu líder",
            "Que los recursos opcionales son obligatorios para terminar la ruta",
        ],
        0,
    ),
]

ASIATI_ONBOARDING_BASE_QUIZ = [
    (
        "Tienes una tarea bloqueada y ves riesgo de no cumplir la fecha acordada. ¿Qué deberías hacer?",
        [
            "Comunicarlo a tiempo a tu líder o punto de apoyo, explicando el bloqueo y su impacto",
            "Esperar hasta la fecha de entrega para informar que no fue posible",
            "Ocultar el problema mientras intentas resolverlo sin avisar",
            "Cambiar la fecha por tu cuenta sin comunicarlo",
        ],
        0,
    ),
    (
        "Necesitas solicitar un permiso o vacaciones. ¿Cuál es la actuación correcta?",
        [
            "Seguir el procedimiento, completar la información requerida y confirmar la aprobación correspondiente",
            "Asumir que la solicitud está aprobada con solo comentarla informalmente",
            "Ausentarte y diligenciar el formato después",
            "Pedir a un compañero que haga la solicitud por ti",
        ],
        0,
    ),
    (
        "No sabes quién debe ayudarte con una decisión de tu trabajo. ¿Qué haces primero?",
        [
            "Identificas a tu líder o punto de apoyo y escalas la duda con el contexto necesario",
            "Tomas cualquier decisión sin consultar para no interrumpir a nadie",
            "Esperas indefinidamente a que alguien note el bloqueo",
            "Envías la duda a toda la empresa sin contexto",
        ],
        0,
    ),
    (
        "Recibes o manejas información de clientes o de la empresa. ¿Qué principio debes aplicar?",
        [
            "Usarla solo para fines autorizados, proteger los accesos y reportar cualquier incidente",
            "Compartir credenciales si eso acelera una tarea",
            "Copiar la información a cuentas personales para trabajar más rápido",
            "Ignorar un acceso sospechoso si el sistema sigue funcionando",
        ],
        0,
    ),
    (
        "Cometes un error que puede afectar una tarea o a otra persona del equipo. ¿Qué se espera de ti?",
        [
            "Informarlo oportunamente, asumir responsabilidad y participar en la solución",
            "Ocultarlo mientras exista la posibilidad de que nadie lo note",
            "Esperar a que otra persona lo descubra",
            "Eliminar cualquier evidencia antes de comunicarlo",
        ],
        0,
    ),
    (
        "Durante tu primera semana, ¿qué deberías validar con tu líder?",
        [
            "Alcance del cargo, prioridades, herramientas, primeros entregables y forma de seguimiento",
            "Únicamente el nombre formal de tu cargo",
            "Solo el calendario de vacaciones",
            "Únicamente las redes sociales de la empresa",
        ],
        0,
    ),
    (
        "¿Cuándo se considera que el onboarding te dejó listo para empezar con claridad?",
        [
            "Cuando entiendes el negocio, tu rol, a quién acudir, cómo trabajar, los procedimientos básicos y tus primeros objetivos",
            "Cuando memorizas nombres y enlaces aunque no sepas cómo actuar",
            "Cuando terminas los videos aunque no tengas claros tus accesos ni prioridades",
            "Cuando puedes trabajar sin volver a pedir ayuda a nadie",
        ],
        0,
    ),
]


def _ensure_asiati_onboarding_quiz_questions(
    db: Session,
    *,
    quiz: TrainingQuiz,
) -> None:
    questions = sorted(quiz.questions, key=lambda item: item.position)
    legacy_prompts = [prompt for prompt, _, _ in ASIATI_ONBOARDING_LEGACY_QUIZ]
    previous_prompts = [prompt for prompt, _, _ in ASIATI_ONBOARDING_PREVIOUS_QUIZ]
    current_prompts = tuple(question.prompt for question in questions)

    if questions and current_prompts not in {
        tuple(legacy_prompts),
        tuple(previous_prompts),
    }:
        return

    for position, (prompt, options, correct_option) in enumerate(
        ASIATI_ONBOARDING_BASE_QUIZ,
        start=1,
    ):
        if position <= len(questions):
            question = questions[position - 1]
            question.prompt = prompt
            question.options = list(options)
            question.correct_option = correct_option
            question.position = position
        else:
            db.add(
                TrainingQuizQuestion(
                    quiz_id=quiz.id,
                    prompt=prompt,
                    options=list(options),
                    correct_option=correct_option,
                    position=position,
                )
            )
    db.commit()


def create_asiati_onboarding_template(
    db: Session,
    *,
    created_by_sub: str,
) -> TrainingCourse:
    existing = (
        db.query(TrainingCourse)
        .filter(
            TrainingCourse.is_onboarding.is_(True),
            TrainingCourse.status == "DRAFT",
            or_(
                TrainingCourse.managed_by_system.is_(True),
                TrainingCourse.title == "Onboarding ASIATI",
            ),
        )
        .order_by(TrainingCourse.created_at.desc())
        .first()
    )
    if existing is not None:
        changed = False
        if not existing.managed_by_system:
            existing.managed_by_system = True
            changed = True
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
            "Ruta de inducción para empezar con claridad: entiende ASIATI, conoce "
            "al equipo, aprende cómo actuar en el día a día, confirma accesos y "
            "procedimientos, aterriza tu rol y valida lo aprendido."
        ),
        created_by_sub=created_by_sub,
        is_onboarding=True,
        managed_by_system=True,
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
    add_lesson(
        db,
        module_id=module_five.id,
        title=ASIATI_ONBOARDING_MODULE_5_SECURITY_TITLE,
        description=(
            "Antes de empezar a operar, confirma con tu líder los accesos, "
            "herramientas y reglas básicas para proteger la información."
        ),
        video_url=None,
        duration_seconds=None,
        content_type="CHECKLIST",
        estimated_minutes=2,
        checklist_items=ASIATI_ONBOARDING_MODULE_5_SECURITY_ITEMS,
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
    add_lesson(
        db,
        module_id=module_six.id,
        title=ASIATI_ONBOARDING_MODULE_6_BEHAVIOR_TITLE,
        description=(
            "Convierte la cultura en decisiones concretas frente a bloqueos, "
            "errores, colaboración y comunicación."
        ),
        video_url=None,
        duration_seconds=None,
        content_type="CHECKLIST",
        estimated_minutes=2,
        checklist_items=ASIATI_ONBOARDING_MODULE_6_BEHAVIOR_ITEMS,
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
        description=(
            "Comprueba que tienes la información mínima para empezar a trabajar "
            "con claridad y sabes qué debes confirmar con tu líder."
        ),
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
    ASIATI_ONBOARDING_MODULE_2_TITLE,
    "Módulo 3 · Conoce al equipo",
    ASIATI_ONBOARDING_MODULE_4_TITLE,
    "Módulo 5 · Contenido corporativo",
    "Módulo 6 · Cultura interna",
    ASIATI_ONBOARDING_MODULE_7_TITLE,
}


def _upgrade_published_asiati_recruiter_experience(
    db: Session,
    *,
    course: TrainingCourse,
) -> None:
    """Upgrade untouched system defaults without overwriting admin customizations."""

    changed = False

    legacy_course_description = (
        "Ruta de inducción corporativa en bloques cortos: ASIATI, ecosistema, "
        "forma de trabajo, rol y evaluación final."
    )
    desired_course_description = (
        "Ruta de inducción para empezar con claridad: entiende ASIATI, conoce "
        "al equipo, aprende cómo actuar en el día a día, confirma accesos y "
        "procedimientos, aterriza tu rol y valida lo aprendido."
    )
    if course.description == legacy_course_description:
        course.description = desired_course_description
        changed = True

    module_two = next(
        (
            module
            for module in course.modules
            if module.title in {
                "Módulo 2 · Conoce ASIATI",
                ASIATI_ONBOARDING_MODULE_2_TITLE,
            }
        ),
        None,
    )
    if module_two is not None:
        if module_two.title == "Módulo 2 · Conoce ASIATI":
            module_two.title = ASIATI_ONBOARDING_MODULE_2_TITLE
            changed = True
        legacy_description = (
            "Conoce el alcance de ASIATI, cómo conectamos operación, logística y "
            "tecnología, y la presencia que construimos como compañía."
        )
        if module_two.description == legacy_description:
            module_two.description = ASIATI_ONBOARDING_MODULE_2_DESCRIPTION
            changed = True

    module_four = next(
        (
            module
            for module in course.modules
            if module.title in {
                "Módulo 4 · Permisos y vacaciones",
                ASIATI_ONBOARDING_MODULE_4_TITLE,
            }
        ),
        None,
    )
    if module_four is not None:
        if module_four.title == "Módulo 4 · Permisos y vacaciones":
            module_four.title = ASIATI_ONBOARDING_MODULE_4_TITLE
            changed = True
        legacy_description = (
            "Aprende el flujo interno para tramitar permisos y vacaciones: formato, "
            "aprobaciones y puntos de control antes de enviar tu solicitud."
        )
        if module_four.description == legacy_description:
            module_four.description = ASIATI_ONBOARDING_MODULE_4_DESCRIPTION
            changed = True
        checklist = next(
            (
                lesson
                for lesson in module_four.lessons
                if lesson.title == ASIATI_ONBOARDING_MODULE_4_CHECKLIST_TITLE
            ),
            None,
        )
        if checklist is not None:
            items = list(checklist.checklist_items or [])
            if not items or items == ASIATI_ONBOARDING_MODULE_4_LEGACY_CHECKLIST_ITEMS:
                checklist.checklist_items = list(ASIATI_ONBOARDING_MODULE_4_CHECKLIST_ITEMS)
                changed = True

    module_five = next(
        (
            module
            for module in course.modules
            if module.title == ASIATI_ONBOARDING_MODULE_5_TITLE
        ),
        None,
    )
    if module_five is not None:
        security = next(
            (
                lesson
                for lesson in module_five.lessons
                if lesson.title == ASIATI_ONBOARDING_MODULE_5_SECURITY_TITLE
            ),
            None,
        )
        if security is None:
            db.add(
                TrainingLesson(
                    module_id=module_five.id,
                    title=ASIATI_ONBOARDING_MODULE_5_SECURITY_TITLE,
                    description=(
                        "Antes de empezar a operar, confirma con tu líder los accesos, "
                        "herramientas y reglas básicas para proteger la información."
                    ),
                    content_type="CHECKLIST",
                    estimated_minutes=2,
                    checklist_items=list(ASIATI_ONBOARDING_MODULE_5_SECURITY_ITEMS),
                    is_optional=False,
                    position=max(
                        [lesson.position for lesson in module_five.lessons] or [0]
                    ) + 1,
                )
            )
            changed = True

    module_six = next(
        (
            module
            for module in course.modules
            if module.title == ASIATI_ONBOARDING_MODULE_6_TITLE
        ),
        None,
    )
    if module_six is not None:
        behavior = next(
            (
                lesson
                for lesson in module_six.lessons
                if lesson.title == ASIATI_ONBOARDING_MODULE_6_BEHAVIOR_TITLE
            ),
            None,
        )
        if behavior is None:
            db.add(
                TrainingLesson(
                    module_id=module_six.id,
                    title=ASIATI_ONBOARDING_MODULE_6_BEHAVIOR_TITLE,
                    description=(
                        "Convierte la cultura en decisiones concretas frente a bloqueos, "
                        "errores, colaboración y comunicación."
                    ),
                    content_type="CHECKLIST",
                    estimated_minutes=2,
                    checklist_items=list(ASIATI_ONBOARDING_MODULE_6_BEHAVIOR_ITEMS),
                    is_optional=False,
                    position=max(
                        [lesson.position for lesson in module_six.lessons] or [0]
                    ) + 1,
                )
            )
            changed = True

    module_seven = next(
        (
            module
            for module in course.modules
            if module.title in {
                "Módulo 7 · Lo que esperamos de ti",
                ASIATI_ONBOARDING_MODULE_7_TITLE,
            }
        ),
        None,
    )
    if module_seven is not None:
        if module_seven.title == "Módulo 7 · Lo que esperamos de ti":
            module_seven.title = ASIATI_ONBOARDING_MODULE_7_TITLE
            changed = True
        legacy_description = (
            "Cierra la inducción corporativa con las expectativas que ASIATI presenta "
            "para esta nueva etapa dentro del equipo."
        )
        if module_seven.description == legacy_description:
            module_seven.description = ASIATI_ONBOARDING_MODULE_7_DESCRIPTION
            changed = True

        acknowledgement = next(
            (
                lesson
                for lesson in module_seven.lessons
                if lesson.title in {
                    "Confirmación de comprensión",
                    ASIATI_ONBOARDING_MODULE_7_ACK_TITLE,
                }
            ),
            None,
        )
        if acknowledgement is not None:
            items = list(acknowledgement.checklist_items or [])
            if acknowledgement.title == "Confirmación de comprensión":
                acknowledgement.title = ASIATI_ONBOARDING_MODULE_7_ACK_TITLE
                changed = True
            if not items or items == ASIATI_ONBOARDING_MODULE_7_LEGACY_ACK_ITEMS:
                acknowledgement.description = (
                    "Comprueba que tienes la información mínima para empezar a trabajar "
                    "con claridad y sabes qué debes confirmar con tu líder."
                )
                acknowledgement.checklist_items = list(
                    ASIATI_ONBOARDING_MODULE_7_ACK_ITEMS
                )
                changed = True

    if changed:
        db.commit()


def _is_current_asiati_onboarding(course: TrainingCourse) -> bool:
    """Identify the provisioned onboarding without depending on editable labels.

    Administrators may customize module/lesson titles after bootstrap. Once the
    published route has the expected structural minimum, do not rebuild or repair
    it on routine reads because that would overwrite intentional edits.
    """

    return (
        bool(course.is_onboarding)
        and (
            bool(getattr(course, "managed_by_system", False))
            or course.title == "Onboarding ASIATI"
        )
        and len(course.modules) >= 7
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
            TrainingCourse.is_onboarding.is_(True),
            TrainingCourse.status == "PUBLISHED",
            or_(
                TrainingCourse.managed_by_system.is_(True),
                TrainingCourse.title == "Onboarding ASIATI",
            ),
        )
        .order_by(TrainingCourse.created_at.desc())
        .all()
    )
    current = next(
        (course for course in published if _is_current_asiati_onboarding(course)),
        None,
    )
    if current is not None:
        if not current.managed_by_system:
            current.managed_by_system = True
            db.commit()
            db.refresh(current)
        _upgrade_published_asiati_recruiter_experience(db, course=current)
        current = require_course(db, current.id)
        migrate_default_onboarding_videos_to_s3(db, course=current)
        current = require_course(db, current.id)
        _ensure_asiati_role_checklist(db, course=current)
        _ensure_asiati_onboarding_quiz_questions(db, quiz=current.quiz)
        return require_course(db, current.id)

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
    migrate_default_onboarding_videos_to_s3(db, course=course)
    return require_course(db, course.id)
