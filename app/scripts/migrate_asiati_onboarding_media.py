"""Bind the published ASIATI onboarding to the managed S3 video copies."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.domains.training.asiati_media import (
    MANAGED_ONBOARDING_VIDEO_DEFAULTS,
    migrate_default_onboarding_videos_to_s3,
)
from app.models import TrainingCourse

logger = logging.getLogger(__name__)


def migrate_published_onboarding_media(db: Session) -> dict[str, int | str]:
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
        and str(lesson.video_storage_key or "").startswith("training/onboarding/")
    )
    return {
        "status": "MIGRATED",
        "managed_videos": managed,
        "course_id": course.id,
    }


def main() -> None:
    with SessionLocal() as db:
        result = migrate_published_onboarding_media(db)
    logger.warning("ASIATI onboarding media migration: %s", result)
    if result["status"] == "MIGRATED" and result["managed_videos"] != 18:
        raise RuntimeError(
            "Expected all 18 default onboarding videos to be managed after migration."
        )


if __name__ == "__main__":
    main()
