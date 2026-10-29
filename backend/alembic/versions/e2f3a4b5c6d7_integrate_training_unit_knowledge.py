"""integrate training unit knowledge

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
"""

from alembic import op
import sqlalchemy as sa


revision = "e2f3a4b5c6d7"
down_revision = "d1e2f3a4b5c6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "training_knowledge_points",
        sa.Column(
            "unit_id",
            sa.String(36),
            sa.ForeignKey("training_units.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    op.add_column(
        "training_knowledge_points",
        sa.Column("assessment_json", sa.JSON(), nullable=True),
    )
    op.add_column(
        "training_knowledge_points",
        sa.Column("position", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_training_knowledge_points_unit_id",
        "training_knowledge_points",
        ["unit_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_training_knowledge_points_unit_id",
        table_name="training_knowledge_points",
    )
    op.drop_column("training_knowledge_points", "assessment_json")
    op.drop_column("training_knowledge_points", "position")
    op.drop_column("training_knowledge_points", "unit_id")
