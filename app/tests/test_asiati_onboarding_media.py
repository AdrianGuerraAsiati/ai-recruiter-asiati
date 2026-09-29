"""Contracts for ASIATI onboarding managed video migration."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.domains.training import service
from app.domains.training.asiati_media import (
    MANAGED_ONBOARDING_VIDEO_DEFAULTS,
    migrate_default_onboarding_videos_to_s3,
)


def test_default_onboarding_video_moves_to_managed_storage(monkeypatch):
    monkeypatch.setenv("TRAINING_CONTENT_BUCKET", "training-bucket")
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    try:
        course = service.create_course(
            db,
            title="Ruta de prueba",
            description="Ruta",
            created_by_sub="system",
            is_onboarding=False,
        )
        module = service.add_module(
            db,
            course_id=course.id,
            title="Módulo 1 · Bienvenida a ASIATI",
            description="Bienvenida",
        )
        lesson = service.add_lesson(
            db,
            module_id=module.id,
            title="Bienvenida a ASIATI",
            description="Video",
            video_url=(
                "https://drive.google.com/file/d/"
                "1NuUYwD0ZEy3DDtptjlhz4NqfuGzD2wXN/view"
            ),
            duration_seconds=58,
        )

        migrate_default_onboarding_videos_to_s3(db, course=course)
        db.refresh(lesson)

        spec = MANAGED_ONBOARDING_VIDEO_DEFAULTS[
            ("Módulo 1 · Bienvenida a ASIATI", "Bienvenida a ASIATI")
        ]
        assert lesson.video_url is None
        assert lesson.video_storage_key == spec["storage_key"]
        assert lesson.video_content_type == "video/mp4"
        assert lesson.video_size_bytes == spec["size_bytes"]
    finally:
        db.close()
        engine.dispose()
