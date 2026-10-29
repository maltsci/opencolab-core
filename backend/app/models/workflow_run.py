import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    workflow_id: Mapped[str] = mapped_column(String(100), index=True)
    workflow_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(
        String(32), default="pending", server_default="pending", index=True
    )
    input_payload: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
    output_payload: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
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
    steps: Mapped[list["StepRun"]] = relationship(
        back_populates="workflow_run",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="StepRun.created_at",
    )


class StepRun(Base):
    __tablename__ = "step_runs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    workflow_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workflow_runs.id", ondelete="CASCADE"), index=True
    )
    step_id: Mapped[str] = mapped_column(String(100), index=True)
    step_type: Mapped[str] = mapped_column(String(32))
    ref: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(
        String(32), default="pending", server_default="pending", index=True
    )
    input_payload: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
    output_payload: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    workflow_run: Mapped["WorkflowRun"] = relationship(back_populates="steps")
