from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge_governance import KnowledgeChangeEvent
from app.models.research_asset import ResearchAsset


pytestmark = pytest.mark.asyncio


async def _create_direction(
    client: AsyncClient,
    headers: dict[str, str],
    name: str,
) -> dict:
    response = await client.post(
        "/api/v1/research-directions",
        json={"name": name},
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


async def _create_public_asset(
    db: AsyncSession,
    *,
    owner_id: str,
    title: str = "Shared Dataset",
) -> ResearchAsset:
    asset = ResearchAsset(
        asset_type="dataset",
        title=title,
        owner_id=owner_id,
        steward_user_id=owner_id,
        visibility_scope="lab_public",
        catalog_metadata_json={
            "resource_profile": {
                "purpose": "Initial benchmark data",
                "access_instructions": "Request access from the steward.",
            }
        },
    )
    db.add(asset)
    await db.commit()
    await db.refresh(asset)
    return asset


async def test_discoverable_resource_profile_exposes_public_metadata_only(
    client: AsyncClient,
    researcher_headers: dict[str, str],
    admin_user,
    db: AsyncSession,
) -> None:
    asset = await _create_public_asset(db, owner_id=admin_user.id)

    response = await client.get(
        f"/api/v1/research-assets/{asset.id}/resource-profile",
        headers=researcher_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["asset_id"] == asset.id
    assert payload["purpose"] == "Initial benchmark data"
    assert payload["access_instructions"] == "Request access from the steward."
    assert payload["protected_access_location"] is None
    assert payload["directions"] == []


async def test_only_asset_manager_can_update_resource_profile(
    client: AsyncClient,
    auth_headers: dict[str, str],
    researcher_headers: dict[str, str],
    admin_user,
    db: AsyncSession,
) -> None:
    asset = await _create_public_asset(db, owner_id=admin_user.id)
    review_due_at = (datetime.now(UTC) + timedelta(days=30)).isoformat()

    denied = await client.patch(
        f"/api/v1/research-assets/{asset.id}/resource-profile",
        json={"purpose": "Attempted overwrite"},
        headers=researcher_headers,
    )
    updated = await client.patch(
        f"/api/v1/research-assets/{asset.id}/resource-profile",
        json={
            "purpose": "Validated benchmark data",
            "suitable_for": "Model evaluation",
            "limitations": "Not suitable for clinical decisions.",
            "access_instructions": "Submit a project access request.",
            "request_url": "https://lab.example/access",
            "last_confirmed_at": datetime.now(UTC).isoformat(),
            "review_due_at": review_due_at,
        },
        headers=auth_headers,
    )

    assert denied.status_code == 403
    assert updated.status_code == 200
    payload = updated.json()
    assert payload["purpose"] == "Validated benchmark data"
    assert payload["suitable_for"] == "Model evaluation"
    assert payload["limitations"] == "Not suitable for clinical decisions."
    assert payload["request_url"] == "https://lab.example/access"
    assert payload["is_stale"] is False


async def test_resource_profile_rejects_credential_values(
    client: AsyncClient,
    auth_headers: dict[str, str],
    admin_user,
    db: AsyncSession,
) -> None:
    asset = await _create_public_asset(db, owner_id=admin_user.id)

    response = await client.patch(
        f"/api/v1/research-assets/{asset.id}/resource-profile",
        json={"access_instructions": "Password: correct-horse-battery-staple"},
        headers=auth_headers,
    )

    assert response.status_code == 422
    assert "credentials" in response.text.lower()


async def test_resource_profile_rejects_unsafe_request_url(
    client: AsyncClient,
    auth_headers: dict[str, str],
    admin_user,
    db: AsyncSession,
) -> None:
    asset = await _create_public_asset(db, owner_id=admin_user.id)

    response = await client.patch(
        f"/api/v1/research-assets/{asset.id}/resource-profile",
        json={"request_url": "javascript:alert('unsafe')"},
        headers=auth_headers,
    )

    assert response.status_code == 422
    assert "http" in response.text.lower()


async def test_resource_maintenance_worklist_only_returns_current_steward_items(
    client: AsyncClient,
    researcher_headers: dict[str, str],
    researcher_user,
    admin_user,
    db: AsyncSession,
) -> None:
    overdue_asset = ResearchAsset(
        asset_type="dataset",
        title="Overdue maintained dataset",
        owner_id=researcher_user.id,
        steward_user_id=researcher_user.id,
        visibility_scope="lab_public",
        catalog_metadata_json={
            "resource_profile": {
                "review_due_at": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
            }
        },
    )
    missing_review_asset = ResearchAsset(
        asset_type="gpu",
        title="GPU without a review date",
        owner_id=researcher_user.id,
        steward_user_id=researcher_user.id,
        visibility_scope="lab_public",
    )
    current_asset = ResearchAsset(
        asset_type="dataset",
        title="Current maintained dataset",
        owner_id=researcher_user.id,
        steward_user_id=researcher_user.id,
        visibility_scope="lab_public",
        catalog_metadata_json={
            "resource_profile": {
                "review_due_at": (datetime.now(UTC) + timedelta(days=7)).isoformat(),
            }
        },
    )
    other_steward_asset = ResearchAsset(
        asset_type="dataset",
        title="Another steward's overdue dataset",
        owner_id=admin_user.id,
        steward_user_id=admin_user.id,
        visibility_scope="lab_public",
        catalog_metadata_json={
            "resource_profile": {
                "review_due_at": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
            }
        },
    )
    db.add_all([overdue_asset, missing_review_asset, current_asset, other_steward_asset])
    await db.commit()

    response = await client.get(
        "/api/v1/research-assets/maintenance",
        headers=researcher_headers,
    )

    assert response.status_code == 200
    items = response.json()
    assert {item["asset_id"] for item in items} == {
        overdue_asset.id,
        missing_review_asset.id,
    }
    issues_by_asset_id = {item["asset_id"]: item["issue"] for item in items}
    assert issues_by_asset_id[overdue_asset.id] == "review_overdue"
    assert issues_by_asset_id[missing_review_asset.id] == "review_missing"


async def test_gpu_resource_profile_keeps_manual_operating_details(
    client: AsyncClient,
    auth_headers: dict[str, str],
    admin_user,
    db: AsyncSession,
) -> None:
    asset = await _create_public_asset(db, owner_id=admin_user.id, title="GPU cluster")
    asset.asset_type = "gpu"
    await db.commit()

    response = await client.patch(
        f"/api/v1/research-assets/{asset.id}/resource-profile",
        json={
            "gpu_configuration": "4 x A100 80GB",
            "gpu_login_instructions": "Request an account from the steward.",
            "gpu_maintenance_note": "Maintenance window is updated manually.",
        },
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["gpu_configuration"] == "4 x A100 80GB"


async def test_model_weight_resource_profile_keeps_reuse_details(
    client: AsyncClient,
    auth_headers: dict[str, str],
    admin_user,
    db: AsyncSession,
) -> None:
    asset = await _create_public_asset(db, owner_id=admin_user.id, title="Cell annotation model")
    asset.asset_type = "model_weight"
    await db.commit()

    response = await client.patch(
        f"/api/v1/research-assets/{asset.id}/resource-profile",
        json={
            "model_weight_source": "https://models.example/cell-annotation",
            "model_weight_version": "v2.1",
            "model_weight_framework": "PyTorch 2.3 with CUDA 12",
            "model_weight_license": "Apache-2.0",
            "model_weight_usage_instructions": "Load with the lab inference script.",
        },
        headers=auth_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["model_weight_source"] == "https://models.example/cell-annotation"
    assert payload["model_weight_version"] == "v2.1"
    assert payload["model_weight_framework"] == "PyTorch 2.3 with CUDA 12"
    assert payload["model_weight_license"] == "Apache-2.0"
    assert payload["model_weight_usage_instructions"] == "Load with the lab inference script."


async def test_dataset_resource_profile_keeps_reuse_details(
    client: AsyncClient,
    auth_headers: dict[str, str],
    admin_user,
    db: AsyncSession,
) -> None:
    asset = await _create_public_asset(db, owner_id=admin_user.id, title="Single-cell reference data")

    response = await client.patch(
        f"/api/v1/research-assets/{asset.id}/resource-profile",
        json={
            "dataset_source": "Lab-curated public studies",
            "dataset_version": "2026.08",
            "dataset_format": "AnnData (.h5ad)",
            "dataset_update_frequency": "Reviewed quarterly",
        },
        headers=auth_headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["dataset_source"] == "Lab-curated public studies"
    assert payload["dataset_version"] == "2026.08"
    assert payload["dataset_format"] == "AnnData (.h5ad)"
    assert payload["dataset_update_frequency"] == "Reviewed quarterly"


async def test_resource_direction_links_are_governed_and_human_readable(
    client: AsyncClient,
    auth_headers: dict[str, str],
    researcher_headers: dict[str, str],
    admin_user,
    db: AsyncSession,
) -> None:
    asset = await _create_public_asset(db, owner_id=admin_user.id)
    direction = await _create_direction(client, auth_headers, "Resource Direction")

    denied = await client.post(
        f"/api/v1/research-assets/{asset.id}/directions",
        json={"direction_id": direction["id"], "purpose": "Evaluate baselines"},
        headers=researcher_headers,
    )
    created = await client.post(
        f"/api/v1/research-assets/{asset.id}/directions",
        json={"direction_id": direction["id"], "purpose": "Evaluate baselines"},
        headers=auth_headers,
    )
    duplicate = await client.post(
        f"/api/v1/research-assets/{asset.id}/directions",
        json={"direction_id": direction["id"], "purpose": "Evaluate baselines"},
        headers=auth_headers,
    )

    assert denied.status_code == 403
    assert created.status_code == 201
    assert created.json()["direction_name"] == "Resource Direction"
    assert duplicate.status_code == 409

    profile = await client.get(
        f"/api/v1/research-assets/{asset.id}/resource-profile",
        headers=researcher_headers,
    )
    assert profile.status_code == 200
    assert profile.json()["directions"] == [
        {
            "id": created.json()["id"],
            "direction_id": direction["id"],
            "direction_name": "Resource Direction",
            "direction_status": "active",
            "purpose": "Evaluate baselines",
            "created_at": created.json()["created_at"],
        }
    ]

    deleted = await client.delete(
        f"/api/v1/research-assets/{asset.id}/directions/{created.json()['id']}",
        headers=auth_headers,
    )
    assert deleted.status_code == 204
    event = await db.scalar(
        select(KnowledgeChangeEvent).where(
            KnowledgeChangeEvent.entity_id == created.json()["id"],
            KnowledgeChangeEvent.action == "unlink",
        )
    )
    assert event is not None
    assert event.before_json["direction_id"] == direction["id"]
