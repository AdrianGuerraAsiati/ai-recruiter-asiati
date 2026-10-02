"""Playback accounting for training videos."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.domains.training.errors import TrainingStateError
from app.models import TrainingLessonProgress


VIDEO_COMPLETION_THRESHOLD = 0.80


def video_progress_payload(progress_details: dict | None) -> dict:
    details = progress_details or {}
    return {
        "watched_percent": float(details.get("watched_percent") or 0),
        "watched_seconds": float(details.get("watched_seconds") or 0),
        "last_position_seconds": float(details.get("last_position_seconds") or 0),
        "completion_threshold_percent": round(VIDEO_COMPLETION_THRESHOLD * 100),
    }


def reject_manual_video_completion(lesson) -> None:
    if str(lesson.content_type or "").upper() == "VIDEO":
        raise TrainingStateError(
            "Los videos se completan automaticamente al reproducir al menos el 80%."
        )


def _merge_watched_ranges(
    ranges: list[list[float]],
    new_range: tuple[float, float],
    *,
    duration_seconds: float,
) -> list[list[float]]:
    normalized: list[tuple[float, float]] = []
    for raw in [*ranges, list(new_range)]:
        if not isinstance(raw, (list, tuple)) or len(raw) != 2:
            continue
        start = max(0.0, min(float(raw[0]), duration_seconds))
        end = max(0.0, min(float(raw[1]), duration_seconds))
        if end <= start:
            continue
        normalized.append((start, end))
    normalized.sort(key=lambda item: item[0])

    merged: list[list[float]] = []
    for start, end in normalized:
        if not merged or start > merged[-1][1] + 0.5:
            merged.append([round(start, 3), round(end, 3)])
            continue
        merged[-1][1] = round(max(merged[-1][1], end), 3)
    return merged


def update_video_progress(
    db: Session,
    *,
    employee_id: str,
    lesson_id: str,
    duration_seconds: float,
    played_from_seconds: float,
    played_to_seconds: float,
    position_seconds: float,
) -> dict:
    # Local import avoids an import cycle while keeping catalog/progress rules
    # centralized in the existing training service.
    from app.domains.training import service

    lesson = service.require_lesson(db, lesson_id)
    course = lesson.module.course
    assignment = service.require_my_assignment(
        db,
        employee_id=employee_id,
        course_id=course.id,
    )
    if course.status != "PUBLISHED":
        raise TrainingStateError("This course is not available.")
    if not service._module_applies(lesson.module, assignment.employee):
        raise TrainingStateError("This lesson is not assigned to your profile.")
    if not service._lesson_visible_to_employee(lesson):
        raise TrainingStateError("This lesson is not available yet.")
    if str(lesson.content_type or "").upper() != "VIDEO":
        raise TrainingStateError("This lesson is not a video.")

    canonical_duration = float(lesson.duration_seconds or duration_seconds)
    if canonical_duration <= 0:
        raise TrainingStateError("Video duration is not available.")
    start = max(0.0, min(float(played_from_seconds), canonical_duration))
    end = max(0.0, min(float(played_to_seconds), canonical_duration))
    if end <= start or end - start > 30:
        raise TrainingStateError("Invalid video progress segment.")

    entry = (
        db.query(TrainingLessonProgress)
        .filter(
            TrainingLessonProgress.assignment_id == assignment.id,
            TrainingLessonProgress.lesson_id == lesson_id,
        )
        .one_or_none()
    )
    details = dict(entry.details or {}) if entry is not None else {}
    ranges = _merge_watched_ranges(
        list(details.get("watched_ranges") or []),
        (start, end),
        duration_seconds=canonical_duration,
    )
    watched_seconds = min(
        canonical_duration,
        sum(max(0.0, item[1] - item[0]) for item in ranges),
    )
    watched_percent = min(100.0, (watched_seconds / canonical_duration) * 100.0)
    completed = watched_percent + 1e-9 >= VIDEO_COMPLETION_THRESHOLD * 100

    details.update({
        "watched_ranges": ranges,
        "watched_seconds": round(watched_seconds, 3),
        "watched_percent": round(watched_percent, 1),
        "last_position_seconds": round(
            max(0.0, min(float(position_seconds), canonical_duration)),
            3,
        ),
        "duration_seconds": round(canonical_duration, 3),
        "completion_threshold_percent": round(VIDEO_COMPLETION_THRESHOLD * 100),
    })

    if entry is None:
        entry = TrainingLessonProgress(
            assignment_id=assignment.id,
            lesson_id=lesson_id,
            status="COMPLETED" if completed else "IN_PROGRESS",
            details=details,
            completed_at=datetime.now(timezone.utc) if completed else None,
        )
        db.add(entry)
    else:
        entry.details = details
        if completed:
            entry.status = "COMPLETED"
            if entry.completed_at is None:
                entry.completed_at = datetime.now(timezone.utc)
        elif entry.status != "COMPLETED":
            entry.status = "IN_PROGRESS"
            entry.completed_at = None

    db.flush()
    service._refresh_assignment_completion(db, assignment)
    db.commit()
    return service.get_my_course(db, employee_id=employee_id, course_id=course.id)
