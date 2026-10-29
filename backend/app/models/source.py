import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    type: Mapped[str] = mapped_column(String(20))  # file, url, note, group, data_package
    name: Mapped[str] = mapped_column(String(500))
    owner_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    content_hash: Mapped[str | None] = mapped_column(
        String(64), unique=True, index=True
    )  # SHA-256
    content_path: Mapped[str | None] = mapped_column(String(1000))
    note_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("notes.id", ondelete="SET NULL"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    processing_state: Mapped[str] = mapped_column(
        String(20), default="ready", server_default="ready", index=True
    )
    progress: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    error_message: Mapped[str | None] = mapped_column(Text, default=None)
    meta_info: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)

    owner: Mapped["User | None"] = relationship(
        "User", foreign_keys=[owner_id]
    )
    share: Mapped["SourceShare | None"] = relationship(
        back_populates="source", uselist=False, cascade="all, delete-orphan", passive_deletes=True
    )

    chunks: Mapped[list["Chunk"]] = relationship(
        back_populates="source", cascade="all, delete-orphan", passive_deletes=True
    )
    # Group membership: children of this source (only meaningful when type=group)
    child_memberships: Mapped[list["SourceMember"]] = relationship(
        foreign_keys="SourceMember.parent_id",
        back_populates="parent",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    # Group membership: groups this source belongs to
    parent_memberships: Mapped[list["SourceMember"]] = relationship(
        foreign_keys="SourceMember.child_id",
        back_populates="child",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    extraction: Mapped["SourceExtraction | None"] = relationship(
        back_populates="source",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class WorkspaceSource(Base):
    __tablename__ = "workspace_sources"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    source_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sources.id", ondelete="CASCADE"), index=True
    )

    workspace: Mapped["Workspace"] = relationship(back_populates="workspace_sources")
    source: Mapped["Source"] = relationship()


class SessionSource(Base):
    __tablename__ = "session_sources"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    source_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sources.id", ondelete="CASCADE"), index=True
    )
    display_name: Mapped[str | None] = mapped_column(String(500), nullable=True)

    session: Mapped["Session"] = relationship(back_populates="session_sources")
    source: Mapped["Source"] = relationship()


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    source_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sources.id", ondelete="CASCADE"), index=True
    )
    text: Mapped[str] = mapped_column(Text)
    chunk_index: Mapped[int] = mapped_column(default=0)

    source: Mapped["Source"] = relationship(back_populates="chunks")


class SourceMember(Base):
    """Membership relation for source groups.

    parent_id must reference a Source with type='group'.
    child_id can reference any Source (including another group for nesting).
    """

    __tablename__ = "source_members"
    __table_args__ = (
        UniqueConstraint("parent_id", "child_id", name="uq_source_member"),
        CheckConstraint("parent_id != child_id", name="ck_no_self_reference"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    parent_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sources.id", ondelete="CASCADE"), index=True
    )
    child_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sources.id", ondelete="CASCADE"), index=True
    )
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    parent: Mapped["Source"] = relationship(
        foreign_keys=[parent_id], back_populates="child_memberships"
    )
    child: Mapped["Source"] = relationship(
        foreign_keys=[child_id], back_populates="parent_memberships"
    )


class SourceShare(Base):
    """Sharing metadata for a source.

    Each source can have at most one share record. scope determines the audience:
    - "all": visible to all users
    - "project": visible to members of the specified project
    permission determines what non-owners can do:
    - "read": view only
    - "readwrite": can modify (add/remove members for groups, edit notes)
    """

    __tablename__ = "source_shares"
    __table_args__ = (
        UniqueConstraint("source_id", name="uq_source_share"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    source_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sources.id", ondelete="CASCADE"), index=True
    )
    shared_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    scope: Mapped[str] = mapped_column(String(20))  # "all" or "project"
    project_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True
    )
    permission: Mapped[str] = mapped_column(
        String(20), default="read", server_default="read"
    )  # "read" or "readwrite"
    shared_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    source: Mapped["Source"] = relationship(back_populates="share")
    sharer: Mapped["User | None"] = relationship(
        "User", foreign_keys=[shared_by]
    )


class HiddenSource(Base):
    """Per-user soft-delete for shared sources.

    When a user 'deletes' a shared file, the file is hidden for that user
    only, so other users who reference it are unaffected.
    """

    __tablename__ = "hidden_sources"
    __table_args__ = (
        UniqueConstraint("user_id", "source_id", name="uq_hidden_source"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    source_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sources.id", ondelete="CASCADE"), index=True
    )
