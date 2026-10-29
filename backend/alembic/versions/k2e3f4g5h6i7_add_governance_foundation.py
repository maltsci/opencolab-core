"""add governance foundation

Revision ID: k2e3f4g5h6i7
Revises: j1d2e3f4g5h6
Create Date: 2026-07-20 12:00:00.000000

"""

import hashlib
import json
import mimetypes
import re
import uuid
from datetime import UTC, datetime
from pathlib import PurePath
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "k2e3f4g5h6i7"
down_revision: Union[str, None] = "j1d2e3f4g5h6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_BACKFILL_NAMESPACE = uuid.UUID("766abce0-cc37-4cfa-9950-e865c21a2815")
_CONTENT_CAPABILITIES = [
    "metadata:view",
    "content:preview",
    "content:download",
    "content:use_in_agent",
]
_CLASSIFICATION_BY_VISIBILITY = {
    "lab_public": "internal",
    "lab_private": "confidential",
    "project": "confidential",
    "private": "restricted",
}
_CATEGORY_BY_TYPE = {
    "uploaded_file": "uploaded_material",
    "external_reference": "external_reference",
    "generated_doc": "generated_document",
    "report": "generated_document",
    "research_memory": "research_memory",
    "protocol": "experimental_material",
    "dataset": "scientific_data",
}


def _deterministic_id(*parts: str) -> str:
    return str(uuid.uuid5(_BACKFILL_NAMESPACE, ":".join(parts)))


def _safe_member_path(name: str) -> str:
    path = PurePath(name).name.strip()
    if not path or path in {".", ".."}:
        return "content"
    return path.replace("\\", "_")


def _member_format(name: str, source_type: str) -> str:
    suffix = PurePath(name).suffix.lower().lstrip(".")
    return (suffix or source_type or "binary")[:32]


def _manifest_sha256(member: dict) -> str:
    manifest = [
        {
            "content_mode": member["content_mode"],
            "display_name": member["display_name"],
            "format": member["format"],
            "media_type": member["media_type"],
            "normalized_path": member["normalized_path"],
            "position": member["position"],
            "role": member["role"],
            "sha256": member["sha256"],
            "size_bytes": member["size_bytes"],
        }
    ]
    payload = json.dumps(
        manifest,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def _valid_sha256(value: str | None) -> str | None:
    if value is not None and re.fullmatch(r"[0-9a-f]{64}", value):
        return value
    return None


def _supported_values(table: sa.Table, values: dict) -> dict:
    return {key: value for key, value in values.items() if key in table.c}


def _create_group_tables() -> None:
    op.create_table(
        "research_groups",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    for column in ("name", "created_by", "archived_at"):
        op.create_index(
            op.f(f"ix_research_groups_{column}"),
            "research_groups",
            [column],
            unique=column == "name",
        )

    op.create_table(
        "research_group_members",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("group_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["group_id"], ["research_groups.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("group_id", "user_id", name="uq_group_member"),
    )
    for column in ("group_id", "user_id", "role", "created_by", "removed_at"):
        op.create_index(
            op.f(f"ix_research_group_members_{column}"),
            "research_group_members",
            [column],
            unique=False,
        )


def _add_governance_columns() -> None:
    with op.batch_alter_table("projects") as batch_op:
        batch_op.add_column(
            sa.Column("research_group_id", sa.String(length=36), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_projects_research_group",
            "research_groups",
            ["research_group_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_index(
            op.f("ix_projects_research_group_id"),
            ["research_group_id"],
            unique=False,
        )

    with op.batch_alter_table("research_assets") as batch_op:
        batch_op.add_column(
            sa.Column(
                "asset_category",
                sa.String(length=32),
                server_default="uploaded_material",
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column("owning_group_id", sa.String(length=36), nullable=True)
        )
        batch_op.add_column(
            sa.Column("steward_user_id", sa.String(length=36), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "classification",
                sa.String(length=32),
                server_default="confidential",
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column(
                "catalog_status",
                sa.String(length=32),
                server_default="published",
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column(
                "lifecycle_status",
                sa.String(length=32),
                server_default="active",
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column(
                "governance_review_status",
                sa.String(length=32),
                server_default="pending",
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column(
                "catalog_metadata_json",
                sa.JSON(),
                server_default=sa.text("'{}'"),
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column(
                "protected_metadata_json",
                sa.JSON(),
                server_default=sa.text("'{}'"),
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column("current_revision_id", sa.String(length=36), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "catalog_published_at",
                sa.DateTime(timezone=True),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "catalog_withdrawn_at",
                sa.DateTime(timezone=True),
                nullable=True,
            )
        )
        batch_op.create_foreign_key(
            "fk_research_assets_owning_group",
            "research_groups",
            ["owning_group_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_foreign_key(
            "fk_research_assets_steward",
            "users",
            ["steward_user_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        for column in (
            "asset_category",
            "owning_group_id",
            "steward_user_id",
            "classification",
            "catalog_status",
            "lifecycle_status",
            "governance_review_status",
            "current_revision_id",
        ):
            batch_op.create_index(
                op.f(f"ix_research_assets_{column}"),
                [column],
                unique=False,
            )


def _create_revision_tables() -> None:
    op.create_table(
        "asset_revisions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("research_asset_id", sa.String(length=36), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column(
            "processing_state",
            sa.String(length=24),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("manifest_sha256", sa.String(length=64), nullable=True),
        sa.Column("change_summary", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("sealed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["research_asset_id"],
            ["research_assets.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "research_asset_id",
            "revision_number",
            name="uq_asset_revision_number",
        ),
    )
    for column in ("research_asset_id", "processing_state", "created_by"):
        op.create_index(
            op.f(f"ix_asset_revisions_{column}"),
            "asset_revisions",
            [column],
            unique=False,
        )

    op.create_table(
        "asset_content_members",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("asset_revision_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(length=24), nullable=False),
        sa.Column("content_mode", sa.String(length=24), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("normalized_path", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("media_type", sa.String(length=128), nullable=True),
        sa.Column("format", sa.String(length=32), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("managed_source_id", sa.String(length=36), nullable=True),
        sa.Column("external_reference_ciphertext", sa.Text(), nullable=True),
        sa.Column(
            "external_metadata_json",
            sa.JSON(),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column(
            "external_handoff_json",
            sa.JSON(),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.CheckConstraint(
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
        sa.ForeignKeyConstraint(
            ["asset_revision_id"],
            ["asset_revisions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["managed_source_id"],
            ["sources.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "asset_revision_id",
            "normalized_path",
            name="uq_revision_member_path",
        ),
        sa.UniqueConstraint(
            "asset_revision_id",
            "position",
            name="uq_revision_member_position",
        ),
    )
    for column in (
        "asset_revision_id",
        "role",
        "content_mode",
        "format",
        "managed_source_id",
    ):
        op.create_index(
            op.f(f"ix_asset_content_members_{column}"),
            "asset_content_members",
            [column],
            unique=False,
        )


def _create_policy_tables() -> None:
    op.create_table(
        "data_use_agreements",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("owning_group_id", sa.String(length=36), nullable=False),
        sa.Column(
            "status",
            sa.String(length=24),
            server_default="draft",
            nullable=False,
        ),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("allowed_project_id", sa.String(length=36), nullable=True),
        sa.Column(
            "allowed_research_group_id",
            sa.String(length=36),
            nullable=True,
        ),
        sa.Column(
            "allowed_capabilities_json",
            sa.JSON(),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
        sa.Column("reference", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["owning_group_id"],
            ["research_groups.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["allowed_project_id"],
            ["projects.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["allowed_research_group_id"],
            ["research_groups.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in (
        "owning_group_id",
        "status",
        "valid_until",
        "allowed_project_id",
        "allowed_research_group_id",
        "created_by",
    ):
        op.create_index(
            op.f(f"ix_data_use_agreements_{column}"),
            "data_use_agreements",
            [column],
            unique=False,
        )

    op.create_table(
        "data_assets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("research_asset_id", sa.String(length=36), nullable=False),
        sa.Column("research_object_id", sa.String(length=36), nullable=False),
        sa.Column("data_type", sa.String(length=64), nullable=False),
        sa.Column("data_modality", sa.String(length=64), nullable=True),
        sa.Column(
            "scientific_metadata_json",
            sa.JSON(),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["research_asset_id"],
            ["research_assets.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["research_object_id"],
            ["research_objects.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("research_asset_id"),
        sa.UniqueConstraint("research_object_id"),
    )
    for column in (
        "research_asset_id",
        "research_object_id",
        "data_type",
        "data_modality",
        "created_by",
    ):
        op.create_index(
            op.f(f"ix_data_assets_{column}"),
            "data_assets",
            [column],
            unique=column in {"research_asset_id", "research_object_id"},
        )

    op.create_table(
        "access_policies",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("research_asset_id", sa.String(length=36), nullable=False),
        sa.Column("asset_revision_id", sa.String(length=36), nullable=True),
        sa.Column(
            "applies_to_future_revisions",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("subject_type", sa.String(length=32), nullable=False),
        sa.Column("subject_id", sa.String(length=36), nullable=True),
        sa.Column("group_role", sa.String(length=32), nullable=True),
        sa.Column("required_project_id", sa.String(length=36), nullable=True),
        sa.Column("required_agreement_id", sa.String(length=36), nullable=True),
        sa.Column(
            "capabilities_json",
            sa.JSON(),
            server_default=sa.text("'[]'"),
            nullable=False,
        ),
        sa.Column(
            "effect",
            sa.String(length=16),
            server_default="allow",
            nullable=False,
        ),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("priority", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "enabled",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["research_asset_id"],
            ["research_assets.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["asset_revision_id"],
            ["asset_revisions.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["required_project_id"],
            ["projects.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["required_agreement_id"],
            ["data_use_agreements.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in (
        "research_asset_id",
        "asset_revision_id",
        "subject_type",
        "subject_id",
        "group_role",
        "required_project_id",
        "required_agreement_id",
        "valid_until",
        "priority",
        "enabled",
        "created_by",
    ):
        op.create_index(
            op.f(f"ix_access_policies_{column}"),
            "access_policies",
            [column],
            unique=False,
        )


def _reflect_tables(bind) -> dict[str, sa.Table]:
    names = (
        "users",
        "projects",
        "research_assets",
        "project_asset_links",
        "researcher_projects",
        "sources",
        "chunks",
        "research_objects",
        "asset_revisions",
        "asset_content_members",
        "data_assets",
        "access_policies",
    )
    metadata = sa.MetaData()
    metadata.reflect(bind=bind, only=names)
    return {name: metadata.tables[name] for name in names}


def _backfill_existing_assets() -> None:
    bind = op.get_bind()
    tables = _reflect_tables(bind)
    users = list(
        bind.execute(
            sa.select(tables["users"].c.id, tables["users"].c.role).order_by(
                tables["users"].c.id
            )
        ).mappings()
    )
    fallback_actor = next(
        (row["id"] for row in users if row["role"] == "admin"),
        users[0]["id"] if users else None,
    )
    project_groups = dict(
        bind.execute(
            sa.select(
                tables["projects"].c.id,
                tables["projects"].c.research_group_id,
            )
        ).all()
    )
    sources = {
        row["id"]: row
        for row in bind.execute(sa.select(tables["sources"])).mappings()
    }
    research_objects = {
        row["id"]: row
        for row in bind.execute(sa.select(tables["research_objects"])).mappings()
    }
    project_members: dict[str, set[str]] = {}
    for project_id, researcher_id in bind.execute(
        sa.select(
            tables["researcher_projects"].c.project_id,
            tables["researcher_projects"].c.researcher_id,
        )
    ):
        project_members.setdefault(project_id, set()).add(researcher_id)
    linked_projects: dict[str, set[str]] = {}
    for asset_id, project_id in bind.execute(
        sa.select(
            tables["project_asset_links"].c.asset_id,
            tables["project_asset_links"].c.project_id,
        )
    ):
        linked_projects.setdefault(asset_id, set()).add(project_id)

    for asset in bind.execute(
        sa.select(tables["research_assets"]).order_by(
            tables["research_assets"].c.id
        )
    ).mappings():
        asset_id = asset["id"]
        category = _CATEGORY_BY_TYPE.get(
            asset["asset_type"],
            "uploaded_material",
        )
        is_collection = asset["asset_type"] == "collection"
        is_withdrawn = (
            is_collection
            or asset["publication_status"] == "withdrawn"
            or asset["deleted_at"] is not None
        )
        owning_group_id = project_groups.get(asset["origin_project_id"])
        catalog_metadata = {
            "title": asset["title"],
            "category": category,
            "subtype": asset["asset_type"],
            "governance_backfill_version": 1,
        }
        if asset["description"]:
            catalog_metadata["description"] = asset["description"]
        if asset["created_at"]:
            catalog_metadata["created_at"] = asset["created_at"].isoformat()
        update_values = {
            "asset_category": category,
            "owning_group_id": owning_group_id,
            "steward_user_id": asset["owner_id"],
            "classification": _CLASSIFICATION_BY_VISIBILITY.get(
                asset["visibility_scope"],
                "confidential",
            ),
            "catalog_status": "withdrawn" if is_withdrawn else "published",
            "lifecycle_status": "active",
            "governance_review_status": "pending",
            "catalog_metadata_json": catalog_metadata,
            "catalog_published_at": (
                None
                if is_withdrawn
                else asset["published_at"] or asset["created_at"]
            ),
        }
        actor_id = asset["owner_id"] or fallback_actor
        research_object_id = asset["research_object_id"]
        legacy_metadata = asset["metadata_json"] or {}
        if (
            asset["asset_type"] == "dataset"
            and actor_id is not None
            and research_object_id is None
        ):
            research_object_id = _deterministic_id(
                "data-asset-object",
                asset_id,
            )
            exists = bind.scalar(
                sa.select(tables["research_objects"].c.id).where(
                    tables["research_objects"].c.id == research_object_id
                )
            )
            if exists is None:
                bind.execute(
                    tables["research_objects"].insert().values(
                        id=research_object_id,
                        type="data_asset",
                        title=asset["title"],
                        content=None,
                        content_json={},
                        created_by=actor_id,
                    )
                )
            update_values["research_object_id"] = research_object_id
        bind.execute(
            tables["research_assets"]
            .update()
            .where(tables["research_assets"].c.id == asset_id)
            .values(**update_values)
        )

        if (
            asset["asset_type"] == "dataset"
            and actor_id is not None
            and research_object_id is not None
        ):
            data_asset_id = _deterministic_id("data-asset", asset_id)
            exists = bind.scalar(
                sa.select(tables["data_assets"].c.id).where(
                    tables["data_assets"].c.research_asset_id == asset_id
                )
            )
            if exists is None:
                bind.execute(
                    tables["data_assets"].insert().values(
                        id=data_asset_id,
                        research_asset_id=asset_id,
                        research_object_id=research_object_id,
                        data_type=legacy_metadata.get("data_type") or "unspecified",
                        data_modality=legacy_metadata.get("data_modality"),
                        scientific_metadata_json=(
                            legacy_metadata.get("scientific_metadata") or {}
                        ),
                        created_by=actor_id,
                    )
                )

        if is_collection or actor_id is None:
            continue
        source = sources.get(asset["source_id"])
        content_mode = "managed"
        snapshot_payload = None
        if source is None and research_object_id is not None:
            research_object = research_objects.get(research_object_id)
            if research_object is not None:
                payload = research_object["content"]
                if not payload and research_object["content_json"]:
                    payload = json.dumps(
                        research_object["content_json"],
                        ensure_ascii=True,
                        separators=(",", ":"),
                        sort_keys=True,
                    )
                if payload:
                    snapshot_payload = payload
                    snapshot_id = _deterministic_id(
                        "research-object-snapshot",
                        research_object_id,
                    )
                    snapshot_exists = bind.execute(
                        sa.select(tables["sources"]).where(
                            tables["sources"].c.id == snapshot_id
                        )
                    ).mappings().one_or_none()
                    if snapshot_exists is None:
                        snapshot_values = _supported_values(
                            tables["sources"],
                            {
                                "id": snapshot_id,
                                "type": "note",
                                "name": (
                                    f"{research_object['title'] or research_object['type']}.json"
                                ),
                                "owner_id": research_object["created_by"] or actor_id,
                                "content_hash": hashlib.sha256(
                                    f"{research_object_id}:{payload}".encode()
                                ).hexdigest(),
                                "content_path": None,
                                "note_id": None,
                                "processing_state": "ready",
                                "progress": 100,
                                "error_message": None,
                            },
                        )
                        bind.execute(
                            tables["sources"].insert().values(**snapshot_values)
                        )
                        source = snapshot_values
                    else:
                        source = snapshot_exists
                    content_mode = "generated"
        if source is None:
            continue
        if snapshot_payload is not None:
            chunk_id = _deterministic_id(
                "research-object-snapshot-chunk",
                source["id"],
            )
            chunk_exists = bind.scalar(
                sa.select(tables["chunks"].c.id).where(
                    tables["chunks"].c.id == chunk_id
                )
            )
            if chunk_exists is None:
                bind.execute(
                    tables["chunks"].insert().values(
                        **_supported_values(
                            tables["chunks"],
                            {
                                "id": chunk_id,
                                "source_id": source["id"],
                                "text": snapshot_payload,
                                "chunk_index": 0,
                            },
                        )
                    )
                )
        revision_id = _deterministic_id("asset-revision", asset_id, "1")
        revision_exists = bind.scalar(
            sa.select(tables["asset_revisions"].c.id).where(
                tables["asset_revisions"].c.research_asset_id == asset_id,
                tables["asset_revisions"].c.revision_number == 1,
            )
        )
        if revision_exists is None:
            path = _safe_member_path(source["name"])
            member = {
                "id": _deterministic_id("asset-member", revision_id, path),
                "asset_revision_id": revision_id,
                "role": "primary",
                "content_mode": content_mode,
                "position": 0,
                "normalized_path": path,
                "display_name": source["name"],
                "media_type": mimetypes.guess_type(source["name"])[0],
                "format": _member_format(source["name"], source["type"]),
                "size_bytes": None,
                "sha256": _valid_sha256(source["content_hash"]),
                "managed_source_id": source["id"],
                "external_reference_ciphertext": None,
                "external_metadata_json": {},
                "external_handoff_json": {},
            }
            now = datetime.now(UTC)
            bind.execute(
                tables["asset_revisions"].insert().values(
                    id=revision_id,
                    research_asset_id=asset_id,
                    revision_number=1,
                    processing_state="ready",
                    manifest_sha256=_manifest_sha256(member),
                    change_summary="Governance migration",
                    created_by=actor_id,
                    sealed_at=now,
                )
            )
            bind.execute(tables["asset_content_members"].insert().values(**member))
        else:
            revision_id = revision_exists
        bind.execute(
            tables["research_assets"]
            .update()
            .where(tables["research_assets"].c.id == asset_id)
            .values(current_revision_id=revision_id)
        )

        if is_withdrawn:
            continue
        linked_member_ids = {
            user_id
            for project_id in linked_projects.get(asset_id, set())
            for user_id in project_members.get(project_id, set())
        }
        if asset["visibility_scope"] == "lab_public":
            audience = {user["id"] for user in users}
        elif asset["visibility_scope"] == "lab_private":
            audience = {
                user["id"]
                for user in users
                if user["role"] in {"admin", "pi"}
            } | linked_member_ids
        elif asset["visibility_scope"] == "project":
            audience = linked_member_ids
        elif asset["visibility_scope"] == "private" and asset["owner_id"]:
            audience = {asset["owner_id"]}
        else:
            audience = set()
        for user_id in sorted(audience):
            policy_id = _deterministic_id(
                "compatibility-policy",
                asset_id,
                revision_id,
                user_id,
            )
            exists = bind.scalar(
                sa.select(tables["access_policies"].c.id).where(
                    tables["access_policies"].c.id == policy_id
                )
            )
            if exists is not None:
                continue
            bind.execute(
                tables["access_policies"].insert().values(
                    id=policy_id,
                    research_asset_id=asset_id,
                    asset_revision_id=revision_id,
                    applies_to_future_revisions=False,
                    subject_type="user",
                    subject_id=user_id,
                    group_role=None,
                    required_project_id=None,
                    required_agreement_id=None,
                    capabilities_json=_CONTENT_CAPABILITIES,
                    effect="allow",
                    valid_from=None,
                    valid_until=None,
                    priority=0,
                    enabled=True,
                    created_by=actor_id,
                )
            )


def upgrade() -> None:
    _create_group_tables()
    _add_governance_columns()
    _create_revision_tables()
    _create_policy_tables()
    if op.get_bind().dialect.name != "sqlite":
        op.create_foreign_key(
            "fk_research_asset_current_revision",
            "research_assets",
            "asset_revisions",
            ["current_revision_id"],
            ["id"],
            ondelete="RESTRICT",
        )
    _backfill_existing_assets()


def downgrade() -> None:
    bind = op.get_bind()
    tables = _reflect_tables(bind)
    asset_rows = list(
        bind.execute(
            sa.select(
                tables["research_assets"].c.id,
                tables["research_assets"].c.asset_type,
                tables["research_assets"].c.research_object_id,
            )
        ).mappings()
    )
    generated_research_object_ids = {
        row["research_object_id"]
        for row in asset_rows
        if row["asset_type"] == "dataset"
        and row["research_object_id"]
        == _deterministic_id("data-asset-object", row["id"])
    }
    research_object_by_asset_id = {
        row["id"]: row["research_object_id"] for row in asset_rows
    }
    generated_snapshot_source_ids = {
        row.managed_source_id
        for row in bind.execute(
            sa.select(
                tables["asset_revisions"].c.research_asset_id,
                tables["asset_content_members"].c.managed_source_id,
            ).join(
                tables["asset_content_members"],
                tables["asset_content_members"].c.asset_revision_id
                == tables["asset_revisions"].c.id,
            )
        )
        if research_object_by_asset_id.get(row.research_asset_id) is not None
        if row.managed_source_id
        == _deterministic_id(
            "research-object-snapshot",
            research_object_by_asset_id.get(row.research_asset_id),
        )
    }
    generated_snapshot_chunk_ids = {
        _deterministic_id(
            "research-object-snapshot-chunk",
            source_id,
        )
        for source_id in generated_snapshot_source_ids
    }

    if op.get_bind().dialect.name != "sqlite":
        op.drop_constraint(
            "fk_research_asset_current_revision",
            "research_assets",
            type_="foreignkey",
        )
    op.drop_table("access_policies")
    op.drop_table("data_assets")
    op.drop_table("data_use_agreements")
    op.drop_table("asset_content_members")
    op.drop_table("asset_revisions")

    if generated_research_object_ids:
        bind.execute(
            tables["research_assets"]
            .update()
            .where(
                tables["research_assets"].c.research_object_id.in_(
                    generated_research_object_ids
                )
            )
            .values(research_object_id=None)
        )
    if generated_snapshot_chunk_ids:
        bind.execute(
            tables["chunks"].delete().where(
                tables["chunks"].c.id.in_(generated_snapshot_chunk_ids)
            )
        )
    if generated_snapshot_source_ids:
        bind.execute(
            tables["sources"].delete().where(
                tables["sources"].c.id.in_(generated_snapshot_source_ids)
            )
        )
    if generated_research_object_ids:
        bind.execute(
            tables["research_objects"].delete().where(
                tables["research_objects"].c.id.in_(
                    generated_research_object_ids
                )
            )
        )

    with op.batch_alter_table("research_assets") as batch_op:
        for column in (
            "current_revision_id",
            "governance_review_status",
            "lifecycle_status",
            "catalog_status",
            "classification",
            "steward_user_id",
            "owning_group_id",
            "asset_category",
        ):
            batch_op.drop_index(op.f(f"ix_research_assets_{column}"))
        batch_op.drop_constraint(
            "fk_research_assets_steward",
            type_="foreignkey",
        )
        batch_op.drop_constraint(
            "fk_research_assets_owning_group",
            type_="foreignkey",
        )
        for column in (
            "catalog_withdrawn_at",
            "catalog_published_at",
            "current_revision_id",
            "protected_metadata_json",
            "catalog_metadata_json",
            "governance_review_status",
            "lifecycle_status",
            "catalog_status",
            "classification",
            "steward_user_id",
            "owning_group_id",
            "asset_category",
        ):
            batch_op.drop_column(column)

    with op.batch_alter_table("projects") as batch_op:
        batch_op.drop_index(op.f("ix_projects_research_group_id"))
        batch_op.drop_constraint(
            "fk_projects_research_group",
            type_="foreignkey",
        )
        batch_op.drop_column("research_group_id")

    op.drop_table("research_group_members")
    op.drop_table("research_groups")
