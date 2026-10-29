import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TrainingCourse(Base):
    __tablename__ = "training_courses"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    content_language: Mapped[str] = mapped_column(String(16), default="auto")
    scope_type: Mapped[str] = mapped_column(String(16), default="lab", index=True)
    project_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="RESTRICT"), index=True
    )
    lifecycle_status: Mapped[str] = mapped_column(
        String(16), default="active", index=True
    )
    created_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TrainingCourseVersion(Base):
    __tablename__ = "training_course_versions"
    __table_args__ = (
        UniqueConstraint("course_id", "version_number", name="uq_training_course_version"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    course_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("training_courses.id", ondelete="RESTRICT"), index=True
    )
    version_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24), default="draft", index=True)
    description_snapshot: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    published_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TrainingCourseAsset(Base):
    __tablename__ = "training_course_assets"
    __table_args__ = (
        UniqueConstraint(
            "course_version_id", "research_asset_id", name="uq_training_course_asset"
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    course_version_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("training_course_versions.id", ondelete="RESTRICT"),
        index=True,
    )
    research_asset_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("research_assets.id", ondelete="RESTRICT"), index=True
    )
    asset_revision_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("asset_revisions.id", ondelete="RESTRICT"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    added_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )


class TrainingModule(Base):
    __tablename__ = "training_modules"
    __table_args__ = (
        UniqueConstraint("course_version_id", "position", name="uq_training_module_position"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    course_version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("training_course_versions.id", ondelete="RESTRICT"), index=True
    )
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24), default="draft", index=True)
    revision_number: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TrainingUnit(Base):
    __tablename__ = "training_units"
    __table_args__ = (
        UniqueConstraint("module_id", "position", name="uq_training_unit_position"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    module_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("training_modules.id", ondelete="RESTRICT"), index=True
    )
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24), default="draft", index=True)
    pass_score: Mapped[int] = mapped_column(Integer, default=80)
    created_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TrainingUnitAsset(Base):
    __tablename__ = "training_unit_assets"
    __table_args__ = (
        UniqueConstraint("unit_id", "course_asset_id", name="uq_training_unit_asset"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    unit_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("training_units.id", ondelete="RESTRICT"), index=True
    )
    course_asset_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("training_course_assets.id", ondelete="RESTRICT"), index=True
    )
    created_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )


class TrainingUnitLesson(Base):
    __tablename__ = "training_unit_lessons"
    __table_args__ = (UniqueConstraint("unit_id", name="uq_training_unit_lesson"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    unit_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("training_units.id", ondelete="RESTRICT"), index=True
    )
    outline_json: Mapped[list] = mapped_column(JSON)
    lesson_markdown: Mapped[str] = mapped_column(Text)
    evidence_json: Mapped[list] = mapped_column(JSON)
    visuals_json: Mapped[list] = mapped_column(JSON, default=list)
    translations_json: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    created_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TrainingModuleAssignment(Base):
    __tablename__ = "training_module_assignments"
    __table_args__ = (
        UniqueConstraint("module_id", "trainee_id", name="uq_training_module_assignment"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    module_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("training_modules.id", ondelete="RESTRICT"), index=True
    )
    trainee_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    assigned_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    status: Mapped[str] = mapped_column(String(24), default="not_started", index=True)
    required_revision: Mapped[int] = mapped_column(Integer, default=1)
    requires_retraining: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TrainingUnitMessage(Base):
    __tablename__ = "training_unit_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    module_assignment_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("training_module_assignments.id", ondelete="RESTRICT"), index=True
    )
    unit_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("training_units.id", ondelete="RESTRICT"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    evidence_json: Mapped[list | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TrainingUnitAssessmentAttempt(Base):
    __tablename__ = "training_unit_assessment_attempts"
    __table_args__ = (
        UniqueConstraint(
            "module_assignment_id",
            "unit_id",
            "attempt_number",
            name="uq_training_unit_assessment_attempt",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    module_assignment_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("training_module_assignments.id", ondelete="RESTRICT"), index=True
    )
    unit_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("training_units.id", ondelete="RESTRICT"), index=True
    )
    module_revision: Mapped[int] = mapped_column(Integer, default=1)
    attempt_number: Mapped[int] = mapped_column(Integer)
    questions_json: Mapped[list] = mapped_column(JSON)
    answers_json: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    score: Mapped[int | None] = mapped_column(Integer)
    passed: Mapped[bool] = mapped_column(Boolean, default=False)
    feedback_text: Mapped[str | None] = mapped_column(Text)
    translations_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TrainingKnowledgePoint(Base):
    __tablename__ = "training_knowledge_points"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    course_version_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("training_course_versions.id", ondelete="RESTRICT"),
        index=True,
    )
    unit_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("training_units.id", ondelete="RESTRICT"), index=True
    )
    position: Mapped[int | None] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text)
    assessment_json: Mapped[dict | None] = mapped_column(JSON)
    review_status: Mapped[str] = mapped_column(String(16), default="approved", index=True)
    created_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class TrainingKnowledgeEvidence(Base):
    __tablename__ = "training_knowledge_evidence"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    knowledge_point_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("training_knowledge_points.id", ondelete="RESTRICT"),
        index=True,
    )
    course_asset_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("training_course_assets.id", ondelete="RESTRICT"),
        index=True,
    )
    excerpt_text: Mapped[str] = mapped_column(Text)
    origin_chunk_ref: Mapped[str | None] = mapped_column(String(36))
    created_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class TrainingAssignment(Base):
    __tablename__ = "training_assignments"
    __table_args__ = (
        UniqueConstraint(
            "course_version_id", "trainee_id", name="uq_training_assignment"
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    course_version_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("training_course_versions.id", ondelete="RESTRICT"),
        index=True,
    )
    trainee_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    assigned_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    status: Mapped[str] = mapped_column(String(24), default="not_started", index=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TrainingPracticeAttempt(Base):
    __tablename__ = "training_practice_attempts"
    __table_args__ = (
        UniqueConstraint(
            "assignment_id", "knowledge_point_id", "attempt_number",
            name="uq_training_practice_attempt",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    assignment_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("training_assignments.id", ondelete="RESTRICT"), index=True
    )
    knowledge_point_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("training_knowledge_points.id", ondelete="RESTRICT"), index=True
    )
    attempt_number: Mapped[int] = mapped_column(Integer, default=1)
    question_text: Mapped[str] = mapped_column(Text)
    answer_text: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    verdict: Mapped[str | None] = mapped_column(String(24))
    score: Mapped[int | None] = mapped_column(Integer)
    feedback_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TrainingFinalAssessment(Base):
    __tablename__ = "training_final_assessments"
    __table_args__ = (UniqueConstraint("assignment_id", name="uq_training_final_assessment"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    assignment_id: Mapped[str] = mapped_column(String(36), ForeignKey("training_assignments.id", ondelete="RESTRICT"), index=True)
    question_text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    answer_text: Mapped[str | None] = mapped_column(Text)
    score: Mapped[int | None] = mapped_column(Integer)
    feedback_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
