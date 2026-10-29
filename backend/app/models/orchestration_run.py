import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class OrchestrationRun(Base):
    __tablename__ = "orchestration_runs"
    __table_args__ = (
        UniqueConstraint("session_id", "turn_index", name="uq_orchestration_runs_session_turn"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    task_id: Mapped[str] = mapped_column(String(100), index=True)
    turn_index: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), index=True)
    goal_message_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )
    plan_snapshot: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
    capability_snapshot: Mapped[dict] = mapped_column(
        JSON, default=dict, server_default="{}"
    )
    context_manifest: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
    output_contract_snapshot: Mapped[dict] = mapped_column(
        JSON, default=dict, server_default="{}"
    )
    budget_usage: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
    sandbox_session_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    resume_token: Mapped[str | None] = mapped_column(String(255), nullable=True)
    final_message_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_by_type: Mapped[str] = mapped_column(
        String(32), default="human", server_default="human"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    session: Mapped["Session"] = relationship()
