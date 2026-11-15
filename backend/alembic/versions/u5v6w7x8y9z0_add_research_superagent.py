"""Add research superagent policies, tickets, and triggers.

Revision ID: u5v6w7x8y9z0
Revises: t4u5v6w7x8y9
"""

import sqlalchemy as sa
from alembic import op

revision = "u5v6w7x8y9z0"
down_revision = "t4u5v6w7x8y9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_policies",
        sa.Column(
            "project_id",
            sa.String(36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "accept_mode",
            sa.String(20),
            nullable=False,
            server_default="auto",
        ),
        sa.Column(
            "version",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
        sa.Column(
            "rules_json",
            sa.JSON(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "enabled_plugins_json",
            sa.JSON(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "updated_by",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_project_policies_updated_by",
        "project_policies",
        ["updated_by"],
    )

    op.create_table(
        "research_tickets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("short_key", sa.String(32), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column(
            "stage_category",
            sa.String(40),
            nullable=False,
            server_default="baseline_reproduction",
        ),
        sa.Column("iteration_round", sa.Integer(), nullable=True),
        sa.Column(
            "parent_ticket_id",
            sa.String(36),
            sa.ForeignKey("research_tickets.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="open",
        ),
        sa.Column(
            "report_state",
            sa.String(20),
            nullable=False,
            server_default="queued",
        ),
        sa.Column("ended_outcome", sa.String(32), nullable=True),
        sa.Column(
            "mandate_json",
            sa.JSON(),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("attention_json", sa.JSON(), nullable=True),
        sa.Column("deliverable_json", sa.JSON(), nullable=True),
        sa.Column(
            "thread_messages_json",
            sa.JSON(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "execution_log_json",
            sa.JSON(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("plugin_id", sa.String(100), nullable=True),
        sa.Column(
            "created_by",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "assignee_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
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
    )
    op.create_index("ix_research_tickets_project_id", "research_tickets", ["project_id"])
    op.create_index("ix_research_tickets_short_key", "research_tickets", ["short_key"])
    op.create_index("ix_research_tickets_stage_category", "research_tickets", ["stage_category"])
    op.create_index("ix_research_tickets_parent_ticket_id", "research_tickets", ["parent_ticket_id"])
    op.create_index("ix_research_tickets_status", "research_tickets", ["status"])
    op.create_index("ix_research_tickets_report_state", "research_tickets", ["report_state"])
    op.create_index("ix_research_tickets_plugin_id", "research_tickets", ["plugin_id"])
    op.create_index("ix_research_tickets_created_by", "research_tickets", ["created_by"])
    op.create_index("ix_research_tickets_assignee_id", "research_tickets", ["assignee_id"])

    op.create_table(
        "project_triggers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_kind", sa.String(40), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column(
            "actor_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column(
            "payload_json",
            sa.JSON(),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "disposition",
            sa.String(32),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("matched_rule_id", sa.String(100), nullable=True),
        sa.Column(
            "ticket_id",
            sa.String(36),
            sa.ForeignKey("research_tickets.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_project_triggers_project_id", "project_triggers", ["project_id"])
    op.create_index("ix_project_triggers_source_kind", "project_triggers", ["source_kind"])
    op.create_index("ix_project_triggers_event_type", "project_triggers", ["event_type"])
    op.create_index("ix_project_triggers_actor_id", "project_triggers", ["actor_id"])
    op.create_index("ix_project_triggers_disposition", "project_triggers", ["disposition"])
    op.create_index("ix_project_triggers_ticket_id", "project_triggers", ["ticket_id"])


def downgrade() -> None:
    op.drop_table("project_triggers")
    op.drop_table("research_tickets")
    op.drop_table("project_policies")
