"""add project instructions, project plans and activities

Revision ID: u2v3w4x5y6z7
Revises: t1u2v3w4x5y6
Create Date: 2026-08-03 10:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "u2v3w4x5y6z7"
down_revision: Union[str, None] = "t1u2v3w4x5y6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    project_columns = {column["name"] for column in inspector.get_columns("projects")}
    if "instructions" not in project_columns:
        with op.batch_alter_table("projects") as batch_op:
            batch_op.add_column(sa.Column("instructions", sa.Text(), nullable=True))

    if "project_plans" not in tables:
        op.create_table(
            "project_plans",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column(
                "project_id",
                sa.String(length=36),
                sa.ForeignKey("projects.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("title", sa.String(length=200), nullable=False),
            sa.Column("content", sa.Text(), nullable=True),
            sa.Column("start_date", sa.Date(), nullable=True),
            sa.Column("due_date", sa.Date(), nullable=True),
            sa.Column("priority", sa.String(length=20), nullable=False, server_default="medium"),
            sa.Column("tags", sa.JSON(), nullable=False, server_default="[]"),
            sa.Column(
                "assignee_id",
                sa.String(length=36),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="todo"),
            sa.Column(
                "created_by",
                sa.String(length=36),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index("ix_project_plans_project_id", "project_plans", ["project_id"])
        op.create_index("ix_project_plans_assignee_id", "project_plans", ["assignee_id"])

    if "project_activities" not in tables:
        op.create_table(
            "project_activities",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column(
                "project_id",
                sa.String(length=36),
                sa.ForeignKey("projects.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "actor_id",
                sa.String(length=36),
                sa.ForeignKey("users.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("action", sa.String(length=50), nullable=False),
            sa.Column("target_type", sa.String(length=50), nullable=True),
            sa.Column("target_id", sa.String(length=100), nullable=True),
            sa.Column("target_title", sa.String(length=500), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )
        op.create_index(
            "ix_project_activities_project_id", "project_activities", ["project_id"]
        )


def downgrade() -> None:
    op.drop_index("ix_project_activities_project_id", table_name="project_activities")
    op.drop_table("project_activities")
    op.drop_index("ix_project_plans_assignee_id", table_name="project_plans")
    op.drop_index("ix_project_plans_project_id", table_name="project_plans")
    op.drop_table("project_plans")
    with op.batch_alter_table("projects") as batch_op:
        batch_op.drop_column("instructions")
