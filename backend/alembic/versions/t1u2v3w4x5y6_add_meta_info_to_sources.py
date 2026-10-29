"""add meta_info to sources

Revision ID: t1u2v3w4x5y6
Revises: s0t1u2v3w4x5
Create Date: 2026-07-25 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "t1u2v3w4x5y6"
down_revision: Union[str, None] = "s0t1u2v3w4x5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("sources")}
    if "meta_info" not in columns:
        with op.batch_alter_table("sources") as batch_op:
            batch_op.add_column(sa.Column("meta_info", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("sources") as batch_op:
        batch_op.drop_column("meta_info")
