import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class ResearchGroupSteward(Base):
    __tablename__ = "research_group_stewards"
    __table_args__ = (
        UniqueConstraint("group_id", "user_id", name="uq_group_steward"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    group_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("research_groups.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    created_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )


class ResearchDirectionSteward(Base):
    __tablename__ = "research_direction_stewards"
    __table_args__ = (
        UniqueConstraint("direction_id", "user_id", name="uq_direction_steward"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    direction_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("research_directions.id", ondelete="CASCADE"),
        index=True,
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    created_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )


class KnowledgeSuggestion(Base):
    __tablename__ = "knowledge_suggestions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    target_type: Mapped[str] = mapped_column(String(64), index=True)
    target_id: Mapped[str | None] = mapped_column(String(36), index=True)
    action: Mapped[str] = mapped_column(String(32), index=True)
    payload_json: Mapped[dict] = mapped_column(
        JSON, default=dict, server_default="{}"
    )
    evidence_json: Mapped[dict] = mapped_column(
        JSON, default=dict, server_default="{}"
    )
    status: Mapped[str] = mapped_column(
        String(20), default="pending", server_default="pending", index=True
    )
    submitted_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    submitted_by_type: Mapped[str] = mapped_column(
        String(20), default="human", server_default="human"
    )
    reviewer_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    decision_reason: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )
    decision_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class KnowledgeChangeEvent(Base):
    __tablename__ = "knowledge_change_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    entity_type: Mapped[str] = mapped_column(String(64), index=True)
    entity_id: Mapped[str] = mapped_column(String(36), index=True)
    action: Mapped[str] = mapped_column(String(32), index=True)
    actor_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    suggestion_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("knowledge_suggestions.id", ondelete="SET NULL"),
        index=True,
    )
    before_json: Mapped[dict] = mapped_column(
        JSON, default=dict, server_default="{}"
    )
    after_json: Mapped[dict] = mapped_column(
        JSON, default=dict, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
