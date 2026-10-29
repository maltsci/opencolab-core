"""add training modules and units

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
"""

from alembic import op
import sqlalchemy as sa


revision = "f5a6b7c8d9e0"
down_revision = "e4f5a6b7c8d9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "training_modules",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("course_version_id", sa.String(36), sa.ForeignKey("training_course_versions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="draft"),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("course_version_id", "position", name="uq_training_module_position"),
    )
    op.create_index("ix_training_modules_course_version_id", "training_modules", ["course_version_id"])
    op.create_index("ix_training_modules_status", "training_modules", ["status"])
    op.create_index("ix_training_modules_created_by", "training_modules", ["created_by"])
    op.create_table(
        "training_units",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("module_id", sa.String(36), sa.ForeignKey("training_modules.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="draft"),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("module_id", "position", name="uq_training_unit_position"),
    )
    op.create_index("ix_training_units_module_id", "training_units", ["module_id"])
    op.create_index("ix_training_units_status", "training_units", ["status"])
    op.create_index("ix_training_units_created_by", "training_units", ["created_by"])
    op.create_table(
        "training_unit_assets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("unit_id", sa.String(36), sa.ForeignKey("training_units.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("course_asset_id", sa.String(36), sa.ForeignKey("training_course_assets.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.UniqueConstraint("unit_id", "course_asset_id", name="uq_training_unit_asset"),
    )
    op.create_index("ix_training_unit_assets_unit_id", "training_unit_assets", ["unit_id"])
    op.create_index("ix_training_unit_assets_course_asset_id", "training_unit_assets", ["course_asset_id"])
    op.create_index("ix_training_unit_assets_created_by", "training_unit_assets", ["created_by"])
    op.create_table(
        "training_unit_lessons",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("unit_id", sa.String(36), sa.ForeignKey("training_units.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("outline_json", sa.JSON(), nullable=False),
        sa.Column("lesson_markdown", sa.Text(), nullable=False),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("unit_id", name="uq_training_unit_lesson"),
    )
    op.create_index("ix_training_unit_lessons_unit_id", "training_unit_lessons", ["unit_id"])
    op.create_index("ix_training_unit_lessons_status", "training_unit_lessons", ["status"])
    op.create_index("ix_training_unit_lessons_created_by", "training_unit_lessons", ["created_by"])
    op.create_table(
        "training_module_assignments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("module_id", sa.String(36), sa.ForeignKey("training_modules.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("trainee_id", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("assigned_by", sa.String(36), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="not_started"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("module_id", "trainee_id", name="uq_training_module_assignment"),
    )
    op.create_index("ix_training_module_assignments_module_id", "training_module_assignments", ["module_id"])
    op.create_index("ix_training_module_assignments_trainee_id", "training_module_assignments", ["trainee_id"])
    op.create_index("ix_training_module_assignments_assigned_by", "training_module_assignments", ["assigned_by"])
    op.create_index("ix_training_module_assignments_status", "training_module_assignments", ["status"])
    op.create_table(
        "training_unit_messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("module_assignment_id", sa.String(36), sa.ForeignKey("training_module_assignments.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("unit_id", sa.String(36), sa.ForeignKey("training_units.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("evidence_json", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_training_unit_messages_module_assignment_id", "training_unit_messages", ["module_assignment_id"])
    op.create_index("ix_training_unit_messages_unit_id", "training_unit_messages", ["unit_id"])
    op.create_table(
        "training_unit_assessment_attempts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("module_assignment_id", sa.String(36), sa.ForeignKey("training_module_assignments.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("unit_id", sa.String(36), sa.ForeignKey("training_units.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("questions_json", sa.JSON(), nullable=False),
        sa.Column("answers_json", sa.JSON()),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("score", sa.Integer()),
        sa.Column("passed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("feedback_text", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("answered_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("module_assignment_id", "unit_id", "attempt_number", name="uq_training_unit_assessment_attempt"),
    )
    op.create_index("ix_training_unit_assessment_attempts_module_assignment_id", "training_unit_assessment_attempts", ["module_assignment_id"])
    op.create_index("ix_training_unit_assessment_attempts_unit_id", "training_unit_assessment_attempts", ["unit_id"])
    op.create_index("ix_training_unit_assessment_attempts_status", "training_unit_assessment_attempts", ["status"])


def downgrade() -> None:
    op.drop_table("training_unit_assessment_attempts")
    op.drop_table("training_unit_messages")
    op.drop_table("training_module_assignments")
    op.drop_table("training_unit_lessons")
    op.drop_table("training_unit_assets")
    op.drop_table("training_units")
    op.drop_table("training_modules")
