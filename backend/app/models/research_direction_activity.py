import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ResearchDirectionActivityPresentation(Base):
    __tablename__ = "research_direction_activity_presentations"
    __table_args__ = (
        UniqueConstraint(
            "direction_id",
            "project_activity_id",
            name="uq_direction_activity_presentation",
        ),
        Index("ix_rdap_project_activity", "project_activity_id"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    direction_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("research_directions.id", ondelete="CASCADE"),
        index=True,
    )
    project_activity_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("project_activities.id", ondelete="CASCADE"),
    )
    presentation: Mapped[str] = mapped_column(String(16))
    updated_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
