import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_create_tag(client: AsyncClient, researcher_headers):
    response = await client.post(
        "/api/v1/tags",
        json={"name": "custom-tag", "type": "custom"},
        headers=researcher_headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "custom-tag"
    assert data["type"] == "custom"


async def test_list_tags(client: AsyncClient, researcher_headers):
    await client.post(
        "/api/v1/tags",
        json={"name": "list-tag"},
        headers=researcher_headers,
    )
    response = await client.get("/api/v1/tags", headers=researcher_headers)
    assert response.status_code == 200
    assert len(response.json()) >= 1


async def test_delete_custom_tag(client: AsyncClient, researcher_headers):
    create = await client.post(
        "/api/v1/tags",
        json={"name": "to-delete"},
        headers=researcher_headers,
    )
    tag_id = create.json()["id"]
    response = await client.delete(
        f"/api/v1/tags/{tag_id}", headers=researcher_headers
    )
    assert response.status_code == 204


async def test_cannot_delete_project_tag(client: AsyncClient, researcher_headers):
    # Create a project (auto-creates a project tag)
    create = await client.post(
        "/api/v1/projects",
        json={"name": "Tag Test Project"},
        headers=researcher_headers,
    )
    # List tags to find the project tag
    tags_response = await client.get("/api/v1/tags", headers=researcher_headers)
    project_tags = [
        t for t in tags_response.json() if t["type"] == "project"
    ]
    assert len(project_tags) >= 1

    # Attempt to delete a project tag
    response = await client.delete(
        f"/api/v1/tags/{project_tags[0]['id']}", headers=researcher_headers
    )
    assert response.status_code == 400
