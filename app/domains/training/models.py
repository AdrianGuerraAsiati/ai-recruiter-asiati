"""SQLAlchemy models for the training domain."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy import JSON
from sqlalchemy.orm import relationship

from app.db import Base


class TrainingCourse(Base):
    """Internal learning course."""

    __tablename__ = "training_courses"
    __table_args__ = (
        Index("idx_training_courses_status", "status"),
    )

    id = Column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    is_onboarding = Column(Boolean, nullable=False, default=False)
    status = Column(Text, nullable=False, default="DRAFT")
    created_by_sub = Column(Text, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    modules = relationship(
        "TrainingModule",
        back_populates="course",
        cascade="all, delete-orphan",
        order_by="TrainingModule.position",
    )
    assignments = relationship(
        "TrainingAssignment",
        back_populates="course",
        cascade="all, delete-orphan",
    )
    quiz = relationship(
        "TrainingQuiz",
        back_populates="course",
        cascade="all, delete-orphan",
        uselist=False,
    )


class TrainingModule(Base):
    __tablename__ = "training_modules"
    __table_args__ = (
        UniqueConstraint(
            "course_id",
            "position",
            name="uq_training_modules_course_position",
        ),
    )

    id = Column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    course_id = Column(
        Text,
        ForeignKey("training_courses.id", ondelete="CASCADE"),
        nullable=False,
    )
    title = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    audience_job_title = Column(Text, nullable=True)
    audience_department = Column(Text, nullable=True)
    position = Column(Integer, nullable=False, default=1)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    course = relationship("TrainingCourse", back_populates="modules")
    lessons = relationship(
        "TrainingLesson",
        back_populates="module",
        cascade="all, delete-orphan",
        order_by="TrainingLesson.position",
    )


class TrainingLesson(Base):
    __tablename__ = "training_lessons"
    __table_args__ = (
        UniqueConstraint(
            "module_id",
            "position",
            name="uq_training_lessons_module_position",
        ),
    )

    id = Column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    module_id = Column(
        Text,
        ForeignKey("training_modules.id", ondelete="CASCADE"),
        nullable=False,
    )
    title = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    video_url = Column(Text, nullable=True)
    video_storage_key = Column(Text, nullable=True)
    video_content_type = Column(Text, nullable=True)
    video_size_bytes = Column(Integer, nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    content_type = Column(Text, nullable=False, default="VIDEO")
    external_url = Column(Text, nullable=True)
    estimated_minutes = Column(Integer, nullable=True)
    checklist_items = Column(JSON, nullable=True, default=list)
    is_optional = Column(Boolean, nullable=False, default=False)
    position = Column(Integer, nullable=False, default=1)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    module = relationship("TrainingModule", back_populates="lessons")
    progress_entries = relationship(
        "TrainingLessonProgress",
        back_populates="lesson",
        cascade="all, delete-orphan",
    )


class TrainingAssignment(Base):
    __tablename__ = "training_assignments"
    __table_args__ = (
        UniqueConstraint(
            "course_id",
            "employee_id",
            name="uq_training_assignments_course_employee",
        ),
        Index(
            "idx_training_assignments_employee_status",
            "employee_id",
            "status",
        ),
    )

    id = Column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    course_id = Column(
        Text,
        ForeignKey("training_courses.id", ondelete="CASCADE"),
        nullable=False,
    )
    employee_id = Column(
        Text,
        ForeignKey("user_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )
    status = Column(Text, nullable=False, default="ASSIGNED")
    assigned_by_sub = Column(Text, nullable=False)
    assigned_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    completed_at = Column(DateTime(timezone=True), nullable=True)

    course = relationship("TrainingCourse", back_populates="assignments")
    employee = relationship("UserProfile")
    lesson_progress = relationship(
        "TrainingLessonProgress",
        back_populates="assignment",
        cascade="all, delete-orphan",
    )
    quiz_attempts = relationship(
        "TrainingQuizAttempt",
        back_populates="assignment",
        cascade="all, delete-orphan",
    )


class TrainingLessonProgress(Base):
    __tablename__ = "training_lesson_progress"
    __table_args__ = (
        UniqueConstraint(
            "assignment_id",
            "lesson_id",
            name="uq_training_lesson_progress_assignment_lesson",
        ),
        Index(
            "idx_training_lesson_progress_assignment_status",
            "assignment_id",
            "status",
        ),
    )

    id = Column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    assignment_id = Column(
        Text,
        ForeignKey("training_assignments.id", ondelete="CASCADE"),
        nullable=False,
    )
    lesson_id = Column(
        Text,
        ForeignKey("training_lessons.id", ondelete="CASCADE"),
        nullable=False,
    )
    status = Column(Text, nullable=False, default="COMPLETED")
    details = Column(JSON, nullable=True, default=dict)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    assignment = relationship(
        "TrainingAssignment",
        back_populates="lesson_progress",
    )
    lesson = relationship(
        "TrainingLesson",
        back_populates="progress_entries",
    )


class TrainingQuiz(Base):
    __tablename__ = "training_quizzes"
    __table_args__ = (
        UniqueConstraint("course_id", name="uq_training_quizzes_course"),
    )

    id = Column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    course_id = Column(
        Text,
        ForeignKey("training_courses.id", ondelete="CASCADE"),
        nullable=False,
    )
    title = Column(Text, nullable=False)
    passing_score = Column(Integer, nullable=False, default=70)
    created_by_sub = Column(Text, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    course = relationship("TrainingCourse", back_populates="quiz")
    questions = relationship(
        "TrainingQuizQuestion",
        back_populates="quiz",
        cascade="all, delete-orphan",
        order_by="TrainingQuizQuestion.position",
    )
    attempts = relationship(
        "TrainingQuizAttempt",
        back_populates="quiz",
        cascade="all, delete-orphan",
    )


class TrainingQuizQuestion(Base):
    __tablename__ = "training_quiz_questions"
    __table_args__ = (
        UniqueConstraint(
            "quiz_id",
            "position",
            name="uq_training_quiz_questions_quiz_position",
        ),
    )

    id = Column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    quiz_id = Column(
        Text,
        ForeignKey("training_quizzes.id", ondelete="CASCADE"),
        nullable=False,
    )
    prompt = Column(Text, nullable=False)
    options = Column(JSON, nullable=False, default=list)
    correct_option = Column(Integer, nullable=False)
    position = Column(Integer, nullable=False, default=1)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    quiz = relationship("TrainingQuiz", back_populates="questions")


class TrainingQuizAttempt(Base):
    __tablename__ = "training_quiz_attempts"
    __table_args__ = (
        UniqueConstraint(
            "assignment_id",
            "attempt_number",
            name="uq_training_quiz_attempts_assignment_number",
        ),
        Index(
            "idx_training_quiz_attempts_assignment_submitted",
            "assignment_id",
            "submitted_at",
        ),
    )

    id = Column(Text, primary_key=True, default=lambda: str(uuid.uuid4()))
    assignment_id = Column(
        Text,
        ForeignKey("training_assignments.id", ondelete="CASCADE"),
        nullable=False,
    )
    quiz_id = Column(
        Text,
        ForeignKey("training_quizzes.id", ondelete="CASCADE"),
        nullable=False,
    )
    answers = Column(JSON, nullable=False, default=dict)
    score_percent = Column(Integer, nullable=False)
    passed = Column(Boolean, nullable=False, default=False)
    attempt_number = Column(Integer, nullable=False)
    submitted_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    assignment = relationship(
        "TrainingAssignment",
        back_populates="quiz_attempts",
    )
    quiz = relationship("TrainingQuiz", back_populates="attempts")
