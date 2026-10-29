import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AccessPolicy(Base):
    __tablename__ = "access_policies"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    research_asset_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("research_assets.id", ondelete="CASCADE"),
        index=True,
    )
    asset_revision_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("asset_revisions.id", ondelete="CASCADE"),
        index=True,
    )
    applies_to_future_revisions: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    subject_type: Mapped[str] = mapped_column(String(32), index=True)
    subject_id: Mapped[str | None] = mapped_column(String(36), index=True)
    group_role: Mapped[str | None] = mapped_column(String(32), index=True)
    required_project_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    required_agreement_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("data_use_agreements.id", ondelete="RESTRICT"),
        index=True,
    )
    capabilities_json: Mapped[list[str]] = mapped_column(
        JSON, default=list, server_default="[]"
    )
    effect: Mapped[str] = mapped_column(
        String(16), default="allow", server_default="allow"
    )
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )
    priority: Mapped[int] = mapped_column(Integer, default=0, server_default="0", index=True)
    enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", index=True
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
