import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.governance import (
    AssetCategory,
    AssetClassification,
    AssetLifecycleStatus,
    CatalogStatus,
    GovernanceReviewStatus,
)


class ResearchAsset(Base):
    __tablename__ = "research_assets"
    __table_args__ = (
        UniqueConstraint("source_id", name="uq_research_assets_source_id"),
        UniqueConstraint(
            "research_object_id", name="uq_research_assets_research_object_id"
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    asset_type: Mapped[str] = mapped_column(String(40), index=True)
    asset_category: Mapped[str] = mapped_column(
        String(32),
        default=AssetCategory.UPLOADED_MATERIAL,
        server_default=AssetCategory.UPLOADED_MATERIAL,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(500))
    title_source: Mapped[str] = mapped_column(
        String(32), default="filename", server_default="filename"
    )
    title_locked: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("sources.id", ondelete="CASCADE"), nullable=True, index=True
    )
    research_object_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("research_objects.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    owner_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    owning_group_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("research_groups.id", ondelete="RESTRICT"),
        index=True,
    )
    steward_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    classification: Mapped[str] = mapped_column(
        String(32),
        default=AssetClassification.CONFIDENTIAL,
        server_default=AssetClassification.CONFIDENTIAL,
        index=True,
    )
    catalog_status: Mapped[str] = mapped_column(
        String(32),
        default=CatalogStatus.PUBLISHED,
        server_default=CatalogStatus.PUBLISHED,
        index=True,
    )
    lifecycle_status: Mapped[str] = mapped_column(
        String(32),
        default=AssetLifecycleStatus.ACTIVE,
        server_default=AssetLifecycleStatus.ACTIVE,
        index=True,
    )
    governance_review_status: Mapped[str] = mapped_column(
        String(32),
        default=GovernanceReviewStatus.PENDING,
        server_default=GovernanceReviewStatus.PENDING,
        index=True,
    )
    catalog_metadata_json: Mapped[dict] = mapped_column(
        JSON, default=dict, server_default="{}"
    )
    protected_metadata_json: Mapped[dict] = mapped_column(
        JSON, default=dict, server_default="{}"
    )
    current_revision_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey(
            "asset_revisions.id",
            ondelete="RESTRICT",
            use_alter=True,
            name="fk_research_asset_current_revision",
        ),
        index=True,
    )
    catalog_published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    catalog_withdrawn_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    origin_project_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    origin_session_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    visibility_scope: Mapped[str] = mapped_column(
        String(32), default="project", server_default="project", index=True
    )
    publication_status: Mapped[str] = mapped_column(
        String(32), default="active", server_default="active", index=True
    )
    published_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    withdrawn_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    withdrawal_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    deleted_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    delete_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    project_links: Mapped[list["ProjectAssetLink"]] = relationship(
        back_populates="asset", cascade="all, delete-orphan", passive_deletes=True
    )


class ProjectAssetLink(Base):
    __tablename__ = "project_asset_links"
    __table_args__ = (
        UniqueConstraint("project_id", "asset_id", name="uq_project_asset_link"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    asset_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("research_assets.id", ondelete="CASCADE"), index=True
    )
    link_type: Mapped[str] = mapped_column(
        String(32), default="reference", server_default="reference", index=True
    )
    created_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    asset: Mapped["ResearchAsset"] = relationship(back_populates="project_links")
