import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(String(2000))
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Task ids chosen at project creation; informational association shown in
    # the project settings panel.
    task_ids: Mapped[list] = mapped_column(JSON, default=list, server_default="[]")
    research_group_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("research_groups.id", ondelete="RESTRICT"),
        index=True,
    )
    archived: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    members: Mapped[list["ResearcherProject"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )
    project_tags: Mapped[list["ProjectTag"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )
    research_group: Mapped["ResearchGroup | None"] = relationship()


class ResearcherProject(Base):
    __tablename__ = "researcher_projects"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    researcher_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(20), default="member")  # owner, member

    project: Mapped["Project"] = relationship(back_populates="members")
    researcher: Mapped["User"] = relationship(foreign_keys=[researcher_id])
