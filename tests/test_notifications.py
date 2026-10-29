import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import select

from app.models.access_request import AccessRequest
from app.models.notification import Notification
from app.models.project import Project, ResearcherProject
from app.models.source import Source
from app.services.research_asset_service import materialize_source_asset

pytestmark = pytest.mark.asyncio


async def _request_material(db, client, admin_user, researcher_user, pi_user, pi_headers):
    project = Project(name="Private source project")
    source = Source(type="file", name="Hidden document", owner_id=admin_user.id,
                    content_hash="a" * 64, processing_state="ready")
    db.add_all([project, source])
    await db.flush()
    db.add(ResearcherProject(project_id=project.id, researcher_id=researcher_user.id, role="owner"))
    asset = await materialize_source_asset(
        db=db, source=source, owner_id=admin_user.id, origin_project_id=project.id,
        origin_session_id=None, visibility_scope="project", link_type="source",
    )
    await db.commit()
    response = await client.post(f"/api/v1/sources/{source.id}/access-requests", headers=pi_headers,
                                 json={"content_hash": source.content_hash, "purpose": "Research", "duration_days": 7})
    assert response.status_code == 201
    return response.json()["id"], source, asset


@pytest.mark.parametrize("action", ["approve", "reject", "cancel"])
async def test_access_request_notifications_are_scoped_and_transactional(
    db, client, admin_user, auth_headers, researcher_user, researcher_headers, pi_user, pi_headers, action,
):
    request_id, source, asset = await _request_material(
        db, client, admin_user, researcher_user, pi_user, pi_headers,
    )
    for headers in (auth_headers, researcher_headers):
        inbox = (await client.get("/api/v1/notifications", headers=headers)).json()
        assert inbox["unread_count"] == 1
        assert inbox["items"][0]["kind"] == "access_request_pending"
        assert inbox["items"][0]["access_request_id"] == request_id
        assert "Hidden document" not in str(inbox)
    assert (await client.get("/api/v1/notifications", headers=pi_headers)).json()["items"] == []
    repeated = await client.post(f"/api/v1/sources/{source.id}/access-requests", headers=pi_headers,
                                 json={"content_hash": source.content_hash, "purpose": "Repeat"})
    assert repeated.status_code == 409
    assert (await client.get("/api/v1/notifications", headers=auth_headers)).json()["unread_count"] == 1
    denied = await client.post(f"/api/v1/research-assets/access-requests/{request_id}/approve",
                               json={}, headers=pi_headers)
    assert denied.status_code == 403
    result = await client.post(f"/api/v1/research-assets/access-requests/{request_id}/{action}",
                               json={}, headers=pi_headers if action == "cancel" else researcher_headers)
    assert result.status_code == 200
    for headers in (auth_headers, researcher_headers):
        assert (await client.get("/api/v1/notifications", headers=headers)).json()["unread_count"] == 0
    applicant = (await client.get("/api/v1/notifications", headers=pi_headers)).json()
    if action == "cancel":
        assert applicant["items"] == []
    else:
        assert applicant["unread_count"] == 1
        assert applicant["items"][0]["kind"] == f"access_request_{'approved' if action == 'approve' else 'rejected'}"
        repeated_decision = await client.post(f"/api/v1/research-assets/access-requests/{request_id}/{action}",
                                              json={}, headers=researcher_headers)
        assert repeated_decision.status_code == 409
        assert (await client.get("/api/v1/notifications", headers=pi_headers)).json()["unread_count"] == 1


async def test_notification_pagination_and_read_operations_are_user_isolated(
    db, client, admin_user, auth_headers, pi_user, pi_headers,
):
    db.add_all([Notification(user_id=admin_user.id, kind="access_request_approved") for _ in range(23)])
    other = Notification(user_id=pi_user.id, kind="access_request_rejected")
    db.add(other)
    await db.commit()
    first = (await client.get("/api/v1/notifications?limit=20", headers=auth_headers)).json()
    second = (await client.get(f"/api/v1/notifications?cursor={first['next_cursor']}", headers=auth_headers)).json()
    assert len(first["items"]) == 20
    assert len(second["items"]) == 3
    assert second["next_cursor"] is None
    assert len({row["id"] for row in first["items"] + second["items"]}) == 23
    assert first["unread_count"] == 23
    assert (await client.post(f"/api/v1/notifications/{other.id}/read", headers=auth_headers)).status_code == 404
    assert (await client.get(f"/api/v1/notifications?cursor={other.id}", headers=auth_headers)).status_code == 404
    selected = first["items"][0]["id"]
    for _ in range(2):
        assert (await client.post(f"/api/v1/notifications/{selected}/read", headers=auth_headers)).status_code == 204
    assert (await client.get("/api/v1/notifications", headers=auth_headers)).json()["unread_count"] == 22
    assert (await client.post("/api/v1/notifications/read-all", headers=auth_headers)).status_code == 204
    assert (await client.get("/api/v1/notifications", headers=auth_headers)).json()["unread_count"] == 0
    assert (await client.get("/api/v1/notifications", headers=pi_headers)).json()["unread_count"] == 1
    assert (await client.get("/api/v1/notifications")).status_code == 403


async def test_migration_backfills_existing_pending_requests(
    db, client, admin_user, auth_headers, researcher_user, researcher_headers, pi_user, pi_headers,
):
    request_id, _, _ = await _request_material(db, client, admin_user, researcher_user, pi_user, pi_headers)
    path = Path("backend/alembic/versions/t4u5v6w7x8y9_add_notifications.py")
    spec = importlib.util.spec_from_file_location("notification_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    connection = await db.connection()

    def migrate(sync_connection):
        Notification.__table__.drop(sync_connection)
        with Operations.context(MigrationContext.configure(sync_connection)):
            migration.upgrade()

    await connection.run_sync(migrate)
    await db.commit()
    rows = list((await db.scalars(select(Notification))).all())
    assert {row.user_id for row in rows} == {admin_user.id, researcher_user.id}
    assert all(row.access_request_id == request_id and row.read_at is None for row in rows)
    assert (await db.get(AccessRequest, request_id)).status == "pending"
