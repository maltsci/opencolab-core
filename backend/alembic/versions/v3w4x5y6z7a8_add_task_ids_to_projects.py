"""add task_ids to projects

Revision ID: v3w4x5y6z7a8
Revises: u2v3w4x5y6z7
Create Date: 2026-08-04 10:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "v3w4x5y6z7a8"
down_revision: Union[str, None] = "u2v3w4x5y6z7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("projects")}
    if "task_ids" not in columns:
        with op.batch_alter_table("projects") as batch_op:
            batch_op.add_column(
                sa.Column("task_ids", sa.JSON(), nullable=False, server_default="[]")
            )


def downgrade() -> None:
    with op.batch_alter_table("projects") as batch_op:
        batch_op.drop_column("task_ids")
