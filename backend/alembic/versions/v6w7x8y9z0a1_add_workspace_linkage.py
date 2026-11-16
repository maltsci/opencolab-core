"""Add stage_category and ticket_id linkage to project_plans and sessions."""

from alembic import op
import sqlalchemy as sa

revision = "v6w7x8y9z0a1"
down_revision = "u5v6w7x8y9z0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "project_plans",
        sa.Column("stage_category", sa.String(length=40), nullable=True),
    )
    op.add_column(
        "project_plans",
        sa.Column(
            "ticket_id",
            sa.String(length=36),
            sa.ForeignKey("research_tickets.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_project_plans_stage_category", "project_plans", ["stage_category"]
    )
    op.create_index("ix_project_plans_ticket_id", "project_plans", ["ticket_id"])

    op.add_column(
        "sessions",
        sa.Column(
            "ticket_id",
            sa.String(length=36),
            sa.ForeignKey("research_tickets.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "sessions",
        sa.Column("stage_category", sa.String(length=40), nullable=True),
    )
    op.create_index("ix_sessions_ticket_id", "sessions", ["ticket_id"])
    op.create_index("ix_sessions_stage_category", "sessions", ["stage_category"])


def downgrade() -> None:
    op.drop_index("ix_sessions_stage_category", table_name="sessions")
    op.drop_index("ix_sessions_ticket_id", table_name="sessions")
    op.drop_column("sessions", "stage_category")
    op.drop_column("sessions", "ticket_id")

    op.drop_index("ix_project_plans_ticket_id", table_name="project_plans")
    op.drop_index("ix_project_plans_stage_category", table_name="project_plans")
    op.drop_column("project_plans", "ticket_id")
    op.drop_column("project_plans", "stage_category")
