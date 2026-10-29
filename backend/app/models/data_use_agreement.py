import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DataUseAgreement(Base):
    __tablename__ = "data_use_agreements"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(255))
    owning_group_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("research_groups.id", ondelete="RESTRICT"),
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(24), default="draft", server_default="draft", index=True
    )
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )
    allowed_project_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="RESTRICT"), index=True
    )
    allowed_research_group_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("research_groups.id", ondelete="RESTRICT"),
        index=True,
    )
    allowed_capabilities_json: Mapped[list[str]] = mapped_column(
        JSON, default=list, server_default="[]"
    )
    reference: Mapped[str] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
