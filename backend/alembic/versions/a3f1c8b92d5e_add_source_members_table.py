"""add source_members table

Revision ID: a3f1c8b92d5e
Revises: 8e856d40e7c4
Create Date: 2026-03-24 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3f1c8b92d5e'
down_revision: Union[str, None] = '8e856d40e7c4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('source_members',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('parent_id', sa.String(length=36), nullable=False),
        sa.Column('child_id', sa.String(length=36), nullable=False),
        sa.Column('added_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['parent_id'], ['sources.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['child_id'], ['sources.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('parent_id', 'child_id', name='uq_source_member'),
        sa.CheckConstraint('parent_id != child_id', name='ck_no_self_reference'),
    )
    op.create_index('ix_source_members_parent_id', 'source_members', ['parent_id'])
    op.create_index('ix_source_members_child_id', 'source_members', ['child_id'])


def downgrade() -> None:
    op.drop_index('ix_source_members_child_id', table_name='source_members')
    op.drop_index('ix_source_members_parent_id', table_name='source_members')
    op.drop_table('source_members')
