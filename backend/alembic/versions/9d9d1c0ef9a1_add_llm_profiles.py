"""add llm_profiles

Revision ID: 9d9d1c0ef9a1
Revises: 4b9d2e7f6c1a
Create Date: 2026-07-05 18:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9d9d1c0ef9a1"
down_revision: Union[str, None] = "4b9d2e7f6c1a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "llm_profiles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("api_base", sa.String(length=500), nullable=True),
        sa.Column("encrypted_key", sa.String(length=500), nullable=False),
        sa.Column("model", sa.String(length=200), nullable=False),
        sa.Column(
            "status",
            sa.String(length=50),
            nullable=False,
            server_default=sa.text("'unknown'"),
        ),
        sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_test_result", sa.Text(), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
    )

    connection = op.get_bind()
    # Legacy llm_keys records do not store a per-key model selection.
    # The only durable model setting before this migration is the global
    # system_configs.llm_model value, so every migrated profile must inherit
    # that single runtime model.
    runtime_model = (
        connection.execute(
            sa.text(
                """
                SELECT value
                FROM system_configs
                WHERE key = 'llm_model'
                ORDER BY updated_at DESC, key ASC
                LIMIT 1
                """
            )
        ).scalar()
        or "gpt-4o-mini"
    )
    legacy_keys = connection.execute(
        sa.text(
            """
            SELECT id, name, provider, api_base, encrypted_key, created_at
            FROM llm_keys
            """
        )
    ).mappings()

    for row in legacy_keys:
        connection.execute(
            sa.text(
                """
                INSERT INTO llm_profiles (
                    id,
                    name,
                    provider,
                    api_base,
                    encrypted_key,
                    model,
                    status,
                    created_at,
                    updated_at
                )
                VALUES (
                    :id,
                    :name,
                    :provider,
                    :api_base,
                    :encrypted_key,
                    :model,
                    'unknown',
                    :created_at,
                    CURRENT_TIMESTAMP
                )
                """
            ),
            {
                "id": row["id"],
                "name": row["name"],
                "provider": row["provider"],
                "api_base": row["api_base"],
                "encrypted_key": row["encrypted_key"],
                "model": runtime_model,
                "created_at": row["created_at"],
            },
        )


def downgrade() -> None:
    op.drop_table("llm_profiles")
