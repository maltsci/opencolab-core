"""add direction activity presentations

Revision ID: z7a8b9c0d1e2
Revises: y6z7a8b9c0d1
Create Date: 2026-08-10 12:10:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "z7a8b9c0d1e2"
down_revision: Union[str, None] = "y6z7a8b9c0d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "research_direction_activity_presentations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("direction_id", sa.String(length=36), nullable=False),
        sa.Column("project_activity_id", sa.String(length=36), nullable=False),
        sa.Column("presentation", sa.String(length=16), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["direction_id"], ["research_directions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["project_activity_id"], ["project_activities.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "direction_id",
            "project_activity_id",
            name="uq_direction_activity_presentation",
        ),
    )
    op.create_index(
        "ix_research_direction_activity_presentations_direction_id",
        "research_direction_activity_presentations",
        ["direction_id"],
        unique=False,
    )
    op.create_index(
        "ix_rdap_project_activity",
        "research_direction_activity_presentations",
        ["project_activity_id"],
        unique=False,
    )
    op.create_index(
        "ix_research_direction_activity_presentations_updated_by",
        "research_direction_activity_presentations",
        ["updated_by"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_research_direction_activity_presentations_updated_by",
        table_name="research_direction_activity_presentations",
    )
    op.drop_index(
        "ix_rdap_project_activity",
        table_name="research_direction_activity_presentations",
    )
    op.drop_index(
        "ix_research_direction_activity_presentations_direction_id",
        table_name="research_direction_activity_presentations",
    )
    op.drop_table("research_direction_activity_presentations")
