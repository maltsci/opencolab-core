import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class SourceExtraction(Base):
    __tablename__ = "source_extractions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    source_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sources.id", ondelete="CASCADE"), unique=True, index=True
    )
    status: Mapped[str] = mapped_column(
        String(20), default="pending", server_default="pending"
    )
    document_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    schema_version: Mapped[str] = mapped_column(
        String(20), default="v1", server_default="v1"
    )
    structured_json: Mapped[dict] = mapped_column(
        JSON, default=dict, server_default="{}"
    )
    rendered_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    metadata_status: Mapped[str] = mapped_column(
        String(32), default="not_applicable", server_default="not_applicable", index=True
    )
    metadata_attempts: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    metadata_next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    metadata_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    metadata_error: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    source: Mapped["Source"] = relationship(back_populates="extraction")


class ResearchTrace(Base):
    __tablename__ = "research_traces"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    message_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("messages.id", ondelete="SET NULL"), nullable=True, index=True
    )
    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    agent_run_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    workflow_run_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("workflow_runs.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    inputs_json: Mapped[dict] = mapped_column(
        JSON, default=dict, server_default="{}"
    )
    retrieval_json: Mapped[list] = mapped_column(
        JSON, default=list, server_default="[]"
    )
    citations_json: Mapped[list] = mapped_column(
        JSON, default=list, server_default="[]"
    )
    summary_steps_json: Mapped[list] = mapped_column(
        JSON, default=list, server_default="[]"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    session: Mapped["Session"] = relationship()
    message: Mapped["Message | None"] = relationship()
    user: Mapped["User | None"] = relationship()
    agent_run: Mapped["AgentRun | None"] = relationship(back_populates="traces")
    workflow_run: Mapped["WorkflowRun | None"] = relationship()
