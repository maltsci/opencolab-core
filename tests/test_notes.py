import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def _create_session(client: AsyncClient, headers: dict) -> str:
    response = await client.post(
        "/api/v1/sessions",
        json={"title": "Note Test Session"},
        headers=headers,
    )
    return response.json()["id"]


async def test_create_note(client: AsyncClient, researcher_headers):
    session_id = await _create_session(client, researcher_headers)
    response = await client.post(
        "/api/v1/notes",
        json={"session_id": session_id, "content": "Test note content"},
        headers=researcher_headers,
    )
    assert response.status_code == 201
    assert response.json()["content"] == "Test note content"


async def test_list_notes(client: AsyncClient, researcher_headers):
    session_id = await _create_session(client, researcher_headers)
    await client.post(
        "/api/v1/notes",
        json={"session_id": session_id, "content": "Listed note"},
        headers=researcher_headers,
    )
    response = await client.get("/api/v1/notes", headers=researcher_headers)
    assert response.status_code == 200
    assert len(response.json()) >= 1


async def test_update_note(client: AsyncClient, researcher_headers):
    session_id = await _create_session(client, researcher_headers)
    create = await client.post(
        "/api/v1/notes",
        json={"session_id": session_id, "content": "Old content"},
        headers=researcher_headers,
    )
    note_id = create.json()["id"]
    response = await client.put(
        f"/api/v1/notes/{note_id}",
        json={"content": "Updated content"},
        headers=researcher_headers,
    )
    assert response.status_code == 200
    assert response.json()["content"] == "Updated content"


async def test_delete_note(client: AsyncClient, researcher_headers):
    session_id = await _create_session(client, researcher_headers)
    create = await client.post(
        "/api/v1/notes",
        json={"session_id": session_id, "content": "To delete"},
        headers=researcher_headers,
    )
    note_id = create.json()["id"]
    response = await client.delete(
        f"/api/v1/notes/{note_id}", headers=researcher_headers
    )
    assert response.status_code == 204
