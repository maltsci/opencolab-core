import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ResearchObject(Base):
    __tablename__ = "research_objects"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    type: Mapped[str] = mapped_column(String(32), index=True)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_json: Mapped[dict] = mapped_column(
        JSON, default=dict, server_default="{}"
    )
    created_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    outgoing_relations: Mapped[list["ResearchObjectRelation"]] = relationship(
        foreign_keys="ResearchObjectRelation.source_object_id",
        back_populates="source_object",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    incoming_relations: Mapped[list["ResearchObjectRelation"]] = relationship(
        foreign_keys="ResearchObjectRelation.target_object_id",
        back_populates="target_object",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class ResearchObjectRelation(Base):
    __tablename__ = "research_object_relations"
    __table_args__ = (
        UniqueConstraint(
            "source_object_id",
            "target_object_id",
            "relation_type",
            name="uq_research_object_relation",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    source_object_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("research_objects.id", ondelete="CASCADE"), index=True
    )
    target_object_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("research_objects.id", ondelete="CASCADE"), index=True
    )
    relation_type: Mapped[str] = mapped_column(String(32), index=True)
    metadata_json: Mapped[dict] = mapped_column(
        JSON, default=dict, server_default="{}"
    )
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    created_by_type: Mapped[str] = mapped_column(
        String(32), default="human", server_default="human"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    source_object: Mapped["ResearchObject"] = relationship(
        foreign_keys=[source_object_id], back_populates="outgoing_relations"
    )
    target_object: Mapped["ResearchObject"] = relationship(
        foreign_keys=[target_object_id], back_populates="incoming_relations"
    )
