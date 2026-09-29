"""Managed private S3 media mapping for the system ASIATI onboarding route."""

from __future__ import annotations

import os
import re

from sqlalchemy.orm import Session

from app.models import TrainingCourse


_DRIVE_FILE_RE = re.compile(r"/file/d/([^/?]+)")

MANAGED_ONBOARDING_VIDEO_DEFAULTS = {
    ("Módulo 1 · Bienvenida a ASIATI", "Bienvenida a ASIATI"): {
        "drive_id": "1NuUYwD0ZEy3DDtptjlhz4NqfuGzD2wXN",
        "storage_key": "training/onboarding/module-1/bienvenida-a-asiati.mp4",
        "size_bytes": 59343746,
    },
    ("Módulo 2 · Entiende el negocio", "Quiénes somos y qué hacemos"): {
        "drive_id": "1zPS0k293LFvAQK4yrXVtOLoP5X-g9i7t",
        "storage_key": "training/onboarding/module-2/quienes-somos-y-que-hacemos.mp4",
        "size_bytes": 32214845,
    },
    ("Módulo 3 · Conoce al equipo", "Jersson"): {
        "drive_id": "1BQ38kuCqmh_XSXfATXlzhz0vSAqLsX6j",
        "storage_key": "training/onboarding/module-3/team/jersson.mp4",
        "size_bytes": 42279211,
    },
    ("Módulo 3 · Conoce al equipo", "Valentina"): {
        "drive_id": "166XnHlEoAV3rpQKAwhHj0wHUYxts0DOk",
        "storage_key": "training/onboarding/module-3/team/valentina.mp4",
        "size_bytes": 25845915,
    },
    ("Módulo 3 · Conoce al equipo", "Johana"): {
        "drive_id": "1Po6IxFG0QYpGwSlSiMJc87qH38h8gBuu",
        "storage_key": "training/onboarding/module-3/team/johana.mp4",
        "size_bytes": 48275968,
    },
    ("Módulo 3 · Conoce al equipo", "Laura"): {
        "drive_id": "1CY1OYFsSEVtyC6R9QJ4SRoWUfU4EXdFy",
        "storage_key": "training/onboarding/module-3/team/laura.mp4",
        "size_bytes": 43081182,
    },
    ("Módulo 3 · Conoce al equipo", "Katherine"): {
        "drive_id": "1iL3x98_7iksX21D7mjRsI4gyh0U7vSk_",
        "storage_key": "training/onboarding/module-3/team/katherine.mp4",
        "size_bytes": 45564227,
    },
    ("Módulo 3 · Conoce al equipo", "Claudia"): {
        "drive_id": "1ArY_1YfEz2nekwxHnVkqgPgVMscLorXP",
        "storage_key": "training/onboarding/module-3/team/claudia.mp4",
        "size_bytes": 98443405,
    },
    ("Módulo 3 · Conoce al equipo", "Erika"): {
        "drive_id": "1fOZ9atajsXmK_NU4IK96EcaEn52LakW8",
        "storage_key": "training/onboarding/module-3/team/erika.mp4",
        "size_bytes": 41289634,
    },
    ("Módulo 3 · Conoce al equipo", "Daniela"): {
        "drive_id": "12rabzH1xD-jaUGsPcqy9ws8pYOtJhh4Z",
        "storage_key": "training/onboarding/module-3/team/daniela.mp4",
        "size_bytes": 61650341,
    },
    ("Módulo 3 · Conoce al equipo", "Oscar"): {
        "drive_id": "1SV7tDQPsddVrALYHsfj8YasF6whToUsL",
        "storage_key": "training/onboarding/module-3/team/oscar.mp4",
        "size_bytes": 49797601,
    },
    ("Módulo 3 · Conoce al equipo", "Josue"): {
        "drive_id": "1YGHb4IaZv-irQhjWZiETjOh9uQNxYEHD",
        "storage_key": "training/onboarding/module-3/team/josue.mp4",
        "size_bytes": 45562482,
    },
    ("Módulo 3 · Conoce al equipo", "Sebastián"): {
        "drive_id": "1FwJJW6MoTkq_gNj5Trcx0b-NSKyedZnh",
        "storage_key": "training/onboarding/module-3/team/sebastian.mp4",
        "size_bytes": 64453723,
    },
    ("Módulo 3 · Conoce al equipo", "Jessica Pullas"): {
        "drive_id": "1409EGo8LzFH7gk0XOmoWmSYWTv9vHR-l",
        "storage_key": "training/onboarding/module-3/team/jessica-pullas.mp4",
        "size_bytes": 25327221,
    },
    ("Módulo 4 · Cómo trabajamos · permisos y vacaciones", "Permisos y vacaciones"): {
        "drive_id": "13wZ5Dmv7x19DuRJt_5K55OpQ3nMb6K4x",
        "storage_key": "training/onboarding/module-4/permisos-y-vacaciones.mp4",
        "size_bytes": 47486447,
    },
    ("Módulo 5 · Contenido corporativo", "Módulo 5"): {
        "drive_id": "1xITvIp8VAg4bkwIt0BFQX4UH2rYZ-CBu",
        "storage_key": "training/onboarding/module-5/modulo-5.mp4",
        "size_bytes": 335299281,
    },
    ("Módulo 6 · Cultura interna", "Cultura interna"): {
        "drive_id": "1HuAXb7anjLZWPik9RjuJiUmqLTqQQybj",
        "storage_key": "training/onboarding/module-6/cultura-interna.mp4",
        "size_bytes": 23703726,
    },
    ("Módulo 7 · Tu rol y tus primeros días", "Lo que esperamos de ti"): {
        "drive_id": "1y4FII6hl25cIADCUWMRr_gS-0AKY3uJW",
        "storage_key": "training/onboarding/module-7/lo-que-esperamos-de-ti.mp4",
        "size_bytes": 53399752,
    },
}


def _drive_file_id(url: str | None) -> str | None:
    match = _DRIVE_FILE_RE.search(str(url or ""))
    return match.group(1) if match else None


def migrate_default_onboarding_videos_to_s3(
    db: Session,
    *,
    course: TrainingCourse,
) -> None:
    """Replace untouched Drive defaults with their private S3 media keys."""

    if not os.getenv("TRAINING_CONTENT_BUCKET"):
        return

    changed = False
    for module in course.modules:
        for lesson in module.lessons:
            spec = MANAGED_ONBOARDING_VIDEO_DEFAULTS.get(
                (module.title, lesson.title)
            )
            if spec is None:
                continue

            current_storage_key = str(lesson.video_storage_key or "").strip()
            if current_storage_key and current_storage_key != spec["storage_key"]:
                # Preserve a video uploaded/replaced by an administrator.
                continue

            if not current_storage_key:
                if _drive_file_id(lesson.video_url) != spec["drive_id"]:
                    # Preserve an external replacement or an intentional removal.
                    continue

            desired = {
                "video_storage_key": spec["storage_key"],
                "video_content_type": "video/mp4",
                "video_size_bytes": spec["size_bytes"],
                "video_url": None,
            }
            for field, value in desired.items():
                if getattr(lesson, field) != value:
                    setattr(lesson, field, value)
                    changed = True

    if changed:
        db.commit()



def migrate_latest_published_onboarding_media(
    db: Session,
) -> dict[str, int | str]:
    """Bind the current published onboarding to managed S3 media."""

    course = (
        db.query(TrainingCourse)
        .filter(
            TrainingCourse.title == "Onboarding ASIATI",
            TrainingCourse.is_onboarding.is_(True),
            TrainingCourse.status == "PUBLISHED",
        )
        .order_by(TrainingCourse.created_at.desc())
        .first()
    )
    if course is None:
        return {"status": "SKIPPED", "managed_videos": 0}

    migrate_default_onboarding_videos_to_s3(db, course=course)
    db.refresh(course)
    managed = sum(
        1
        for module in course.modules
        for lesson in module.lessons
        if (module.title, lesson.title) in MANAGED_ONBOARDING_VIDEO_DEFAULTS
        and str(lesson.video_storage_key or "").startswith(
            "training/onboarding/"
        )
    )
    return {
        "status": "MIGRATED",
        "managed_videos": managed,
        "course_id": course.id,
    }
