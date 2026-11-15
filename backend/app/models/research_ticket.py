import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


STAGE_CATEGORIES = (
    "problem_framing",
    "baseline_reproduction",
    "innovation_feasibility",
    "experiment_iteration",
    "manuscript_writing",
)

ACCEPT_MODES = ("auto", "observe", "off")

TICKET_REPORT_STATES = (
    "queued",
    "progress",
    "waiting",
    "ready",
    "blocked",
    "failed",
    "dropped",
)


def compute_ticket_stage(
    *,
    status: str,
    report_state: str,
    attention_json: dict | None,
) -> str:
    """Compute the mutually exclusive dsh-superagent stage for a ticket.

    Evaluated top-to-bottom; the first matching rule wins:
    1. ended -> 'ended'
    2. active wetlab attention -> 'person / wetlab'
    3. active decision attention -> 'person / answer'
    4. ready deliverable awaiting review -> 'person / review'
    5. blocked or failed -> 'person / blocked'
    6. queued -> 'working / queued'
    7. waiting -> 'idle'
    8. everything else -> 'working'
    """
    if status == "ended":
        return "ended"
    if attention_json and isinstance(attention_json, dict) and attention_json.get("question"):
        if attention_json.get("kind") == "wetlab_upload":
            return "person / wetlab"
        return "person / answer"
    if report_state == "ready":
        return "person / review"
    if report_state in {"blocked", "failed"}:
        return "person / blocked"
    if report_state == "queued":
        return "working / queued"
    if report_state == "waiting":
        return "idle"
    return "working"


class ProjectPolicy(Base):
    __tablename__ = "project_policies"

    project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
        primary_key=True,
    )
    accept_mode: Mapped[str] = mapped_column(
        String(20), default="auto", server_default="auto"
    )
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    rules_json: Mapped[list] = mapped_column(JSON, default=list, server_default="[]")
    enabled_plugins_json: Mapped[list] = mapped_column(
        JSON, default=list, server_default="[]"
    )
    updated_by: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        onupdate=lambda: datetime.now(UTC),
    )


class ResearchTicket(Base):
    __tablename__ = "research_tickets"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
    )
    short_key: Mapped[str] = mapped_column(String(32), index=True)
    title: Mapped[str] = mapped_column(String(500))
    stage_category: Mapped[str] = mapped_column(
        String(40), default="baseline_reproduction", index=True
    )
    iteration_round: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parent_ticket_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("research_tickets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(20), default="open", server_default="open", index=True
    )
    report_state: Mapped[str] = mapped_column(
        String(20), default="queued", server_default="queued", index=True
    )
    ended_outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)
    mandate_json: Mapped[dict] = mapped_column(
        JSON, default=dict, server_default="{}"
    )
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    attention_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    deliverable_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    thread_messages_json: Mapped[list] = mapped_column(
        JSON, default=list, server_default="[]"
    )
    execution_log_json: Mapped[list] = mapped_column(
        JSON, default=list, server_default="[]"
    )
    plugin_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, index=True
    )
    created_by: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    assignee_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        onupdate=lambda: datetime.now(UTC),
    )

    assignee: Mapped["User | None"] = relationship(foreign_keys=[assignee_id])
    creator: Mapped["User | None"] = relationship(foreign_keys=[created_by])

    @property
    def stage(self) -> str:
        return compute_ticket_stage(
            status=self.status,
            report_state=self.report_state,
            attention_json=self.attention_json,
        )

    @property
    def needs_person(self) -> bool:
        return self.stage.startswith("person /")


class ProjectTrigger(Base):
    __tablename__ = "project_triggers"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
        index=True,
    )
    source_kind: Mapped[str] = mapped_column(String(40), index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    actor_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(500))
    payload_json: Mapped[dict] = mapped_column(
        JSON, default=dict, server_default="{}"
    )
    disposition: Mapped[str] = mapped_column(
        String(32), default="pending", server_default="pending", index=True
    )
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    matched_rule_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ticket_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("research_tickets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
    )
