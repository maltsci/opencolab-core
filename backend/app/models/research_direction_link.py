import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class MemberResearchDirection(Base):
    __tablename__ = "member_research_directions"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "direction_id", "valid_from", name="uq_member_direction_period"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    direction_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("research_directions.id", ondelete="CASCADE"),
        index=True,
    )
    role: Mapped[str] = mapped_column(
        String(32), default="contributor", server_default="contributor"
    )
    valid_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    valid_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )
    source_type: Mapped[str] = mapped_column(
        String(32), default="human", server_default="human"
    )
    source_id: Mapped[str | None] = mapped_column(String(36), index=True)
    created_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ProjectResearchDirection(Base):
    __tablename__ = "project_research_directions"
    __table_args__ = (
        UniqueConstraint("project_id", "direction_id", name="uq_project_direction"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    direction_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("research_directions.id", ondelete="CASCADE"),
        index=True,
    )
    reason: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ResearchAssetDirection(Base):
    __tablename__ = "research_asset_directions"
    __table_args__ = (
        UniqueConstraint(
            "research_asset_id", "direction_id", name="uq_asset_direction"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    research_asset_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("research_assets.id", ondelete="CASCADE"),
        index=True,
    )
    direction_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("research_directions.id", ondelete="CASCADE"),
        index=True,
    )
    purpose: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column(
        JSON, default=dict, server_default="{}"
    )
    created_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ResearchObjectDirection(Base):
    __tablename__ = "research_object_directions"
    __table_args__ = (
        UniqueConstraint(
            "research_object_id",
            "direction_id",
            "relation_type",
            name="uq_object_direction",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    research_object_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("research_objects.id", ondelete="CASCADE"),
        index=True,
    )
    direction_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("research_directions.id", ondelete="CASCADE"),
        index=True,
    )
    relation_type: Mapped[str] = mapped_column(
        String(32), default="belongs_to", server_default="belongs_to"
    )
    reason: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
