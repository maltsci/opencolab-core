import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DataAsset(Base):
    __tablename__ = "data_assets"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    research_asset_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("research_assets.id", ondelete="CASCADE"),
        unique=True,
        index=True,
    )
    research_object_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("research_objects.id", ondelete="CASCADE"),
        unique=True,
        index=True,
    )
    data_type: Mapped[str] = mapped_column(String(64), index=True)
    data_modality: Mapped[str | None] = mapped_column(String(64), index=True)
    scientific_metadata_json: Mapped[dict] = mapped_column(
        JSON, default=dict, server_default="{}"
    )
    created_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
