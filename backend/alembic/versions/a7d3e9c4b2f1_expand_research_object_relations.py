"""expand research_object_relations

Revision ID: a7d3e9c4b2f1
Revises: c1d2e3f4a5b6, f1a2b3c4d5e6
Create Date: 2026-07-09 18:30:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a7d3e9c4b2f1"
down_revision: Union[str, tuple[str, str], None] = ("c1d2e3f4a5b6", "f1a2b3c4d5e6")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "research_object_relations",
        sa.Column("metadata_json", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
    )
    op.add_column(
        "research_object_relations",
        sa.Column("created_by", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "research_object_relations",
        sa.Column(
            "created_by_type",
            sa.String(length=32),
            server_default=sa.text("'human'"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_research_object_relations_created_by",
        "research_object_relations",
        ["created_by"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_research_object_relations_created_by",
        table_name="research_object_relations",
    )
    op.drop_column("research_object_relations", "created_by_type")
    op.drop_column("research_object_relations", "created_by")
    op.drop_column("research_object_relations", "metadata_json")
