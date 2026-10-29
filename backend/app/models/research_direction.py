import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class ResearchDirection(Base):
    __tablename__ = "research_directions"
    __table_args__ = (
        Index(
            "uq_research_directions_active_normalized_name",
            "normalized_name",
            unique=True,
            postgresql_where=text("status = 'active'"),
            sqlite_where=text("status = 'active'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255))
    normalized_name: Mapped[str] = mapped_column(String(255), index=True)
    summary: Mapped[str | None] = mapped_column(Text)
    background: Mapped[str | None] = mapped_column(Text)
    scope: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(20), default="active", server_default="active", index=True
    )
    owner_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    merged_into_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("research_directions.id", ondelete="RESTRICT"),
        index=True,
    )
    last_confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )
    review_due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )
    created_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ResearchDirectionRelation(Base):
    __tablename__ = "research_direction_relations"
    __table_args__ = (
        CheckConstraint(
            "direction_a_id < direction_b_id", name="ck_direction_relation_order"
        ),
        CheckConstraint(
            "relation_type = 'related'", name="ck_direction_relation_type"
        ),
        UniqueConstraint(
            "direction_a_id", "direction_b_id", name="uq_direction_relation_pair"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    direction_a_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("research_directions.id", ondelete="CASCADE"),
        index=True,
    )
    direction_b_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("research_directions.id", ondelete="CASCADE"),
        index=True,
    )
    relation_type: Mapped[str] = mapped_column(
        String(32), default="related", server_default="related"
    )
    reason: Mapped[str] = mapped_column(Text)
    evidence_json: Mapped[dict] = mapped_column(
        JSON, default=dict, server_default="{}"
    )
    created_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
