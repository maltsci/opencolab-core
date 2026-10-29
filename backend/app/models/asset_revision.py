import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    event,
    func,
    select,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.governance import AssetRevisionState


class AssetRevisionImmutableError(ValueError):
    pass


class AssetRevision(Base):
    __tablename__ = "asset_revisions"
    __table_args__ = (
        UniqueConstraint(
            "research_asset_id",
            "revision_number",
            name="uq_asset_revision_number",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    research_asset_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("research_assets.id", ondelete="CASCADE"),
        index=True,
    )
    revision_number: Mapped[int] = mapped_column(Integer)
    processing_state: Mapped[str] = mapped_column(
        String(24),
        default=AssetRevisionState.PENDING,
        server_default=AssetRevisionState.PENDING,
        index=True,
    )
    manifest_sha256: Mapped[str | None] = mapped_column(String(64))
    change_summary: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    sealed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AssetContentMember(Base):
    __tablename__ = "asset_content_members"
    __table_args__ = (
        UniqueConstraint(
            "asset_revision_id",
            "normalized_path",
            name="uq_revision_member_path",
        ),
        UniqueConstraint(
            "asset_revision_id",
            "position",
            name="uq_revision_member_position",
        ),
        CheckConstraint(
            "("
            "content_mode IN ('managed', 'generated') "
            "AND managed_source_id IS NOT NULL "
            "AND external_reference_ciphertext IS NULL"
            ") OR ("
            "content_mode = 'external' "
            "AND managed_source_id IS NULL "
            "AND external_reference_ciphertext IS NOT NULL"
            ")",
            name="ck_asset_member_content_reference",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    asset_revision_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("asset_revisions.id", ondelete="CASCADE"),
        index=True,
    )
    role: Mapped[str] = mapped_column(String(24), index=True)
    content_mode: Mapped[str] = mapped_column(String(24), index=True)
    position: Mapped[int] = mapped_column(Integer)
    normalized_path: Mapped[str] = mapped_column(Text)
    display_name: Mapped[str] = mapped_column(Text)
    media_type: Mapped[str | None] = mapped_column(String(128))
    format: Mapped[str] = mapped_column(String(32), index=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    sha256: Mapped[str | None] = mapped_column(String(64))
    managed_source_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("sources.id", ondelete="RESTRICT"), index=True
    )
    external_reference_ciphertext: Mapped[str | None] = mapped_column(Text)
    external_metadata_json: Mapped[dict] = mapped_column(
        JSON, default=dict, server_default="{}"
    )
    external_handoff_json: Mapped[dict] = mapped_column(
        JSON, default=dict, server_default="{}"
    )


def _reject_sealed_member_mutation(
    _mapper,
    connection,
    target: AssetContentMember,
) -> None:
    sealed_at = connection.execute(
        select(AssetRevision.sealed_at).where(
            AssetRevision.id == target.asset_revision_id
        )
    ).scalar_one_or_none()
    if sealed_at is not None:
        raise AssetRevisionImmutableError("Sealed revision members are immutable")


event.listen(
    AssetContentMember,
    "before_insert",
    _reject_sealed_member_mutation,
)
event.listen(
    AssetContentMember,
    "before_update",
    _reject_sealed_member_mutation,
)
event.listen(
    AssetContentMember,
    "before_delete",
    _reject_sealed_member_mutation,
)


def _reject_sealed_revision_mutation(
    _mapper,
    connection,
    target: AssetRevision,
) -> None:
    sealed_at = connection.execute(
        select(AssetRevision.sealed_at).where(
            AssetRevision.id == target.id
        )
    ).scalar_one_or_none()
    if sealed_at is not None:
        raise AssetRevisionImmutableError("Sealed revisions are immutable")


event.listen(
    AssetRevision,
    "before_update",
    _reject_sealed_revision_mutation,
)
event.listen(
    AssetRevision,
    "before_delete",
    _reject_sealed_revision_mutation,
)
