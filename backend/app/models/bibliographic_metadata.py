import uuid
from datetime import datetime

from sqlalchemy import DateTime, JSON, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class BibliographicMetadataCache(Base):
    __tablename__ = "bibliographic_metadata_cache"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "identifier_type",
            "normalized_identifier",
            name="uq_bibliographic_metadata_cache_lookup",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    provider: Mapped[str] = mapped_column(String(32), index=True)
    identifier_type: Mapped[str] = mapped_column(String(16))
    normalized_identifier: Mapped[str] = mapped_column(String(255))
    record_json: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
    result_status: Mapped[str] = mapped_column(String(16))
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
