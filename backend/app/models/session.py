import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="SET NULL"), index=True
    )
    title: Mapped[str | None] = mapped_column(String(500))
    task_id: Mapped[str | None] = mapped_column(String(100), index=True)
    conversation_summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    workspace: Mapped["Workspace"] = relationship(back_populates="sessions")
    project: Mapped["Project | None"] = relationship()
    session_tags: Mapped[list["SessionTag"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", passive_deletes=True
    )
    messages: Mapped[list["Message"]] = relationship(
        back_populates="session", order_by="Message.created_at",
        cascade="all, delete-orphan", passive_deletes=True
    )
    session_sources: Mapped[list["SessionSource"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", passive_deletes=True
    )
