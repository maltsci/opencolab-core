import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MemberRepresentativeAsset(Base):
    __tablename__ = "member_representative_assets"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "research_asset_id",
            name="uq_member_representative_asset",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    research_asset_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("research_assets.id", ondelete="CASCADE"),
        index=True,
    )
    display_order: Mapped[int] = mapped_column(Integer)
    created_by: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="RESTRICT"),
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
