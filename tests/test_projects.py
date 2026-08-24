import pytest
from httpx import AsyncClient

from app.models.user import User


@pytest.mark.asyncio
async def test_create_project_success(
    client: AsyncClient, test_user: User, auth_headers: dict[str, str]
) -> None:
    """Test project creation by authenticated user."""
    payload = {
        "name": "Frontend Redesign",
        "description": "Revamp the user interface with modern components.",
    }
    response = await client.post("/api/v1/projects", json=payload, headers=auth_headers)
    assert response.status_code == 201

    data = response.json()
    assert data["name"] == "Frontend Redesign"
    assert data["description"] == payload["description"]
    assert data["owner_id"] == test_user.id
    assert "id" in data


@pytest.mark.asyncio
async def test_list_projects_pagination_and_isolation(
    client: AsyncClient,
    test_user: User,
    test_user_2: User,
    auth_headers: dict[str, str],
    auth_headers_2: dict[str, str],
) -> None:
    """Test projects listing is paginated and isolated per user."""
    # Create 3 projects for User 1 (Alice)
    for i in range(3):
        await client.post(
            "/api/v1/projects",
            json={"name": f"Alice Project {i + 1}"},
            headers=auth_headers,
        )

    # Create 2 projects for User 2 (Bob)
    for i in range(2):
        await client.post(
            "/api/v1/projects",
            json={"name": f"Bob Project {i + 1}"},
            headers=auth_headers_2,
        )

    # Fetch Alice's projects
    resp_alice = await client.get("/api/v1/projects?page=1&page_size=10", headers=auth_headers)
    assert resp_alice.status_code == 200
    data_alice = resp_alice.json()
    assert data_alice["total"] == 3
    assert len(data_alice["items"]) == 3
    assert all(p["owner_id"] == test_user.id for p in data_alice["items"])

    # Fetch Bob's projects
    resp_bob = await client.get("/api/v1/projects", headers=auth_headers_2)
    assert resp_bob.status_code == 200
    data_bob = resp_bob.json()
    assert data_bob["total"] == 2
    assert len(data_bob["items"]) == 2
    assert all(p["owner_id"] == test_user_2.id for p in data_bob["items"])


@pytest.mark.asyncio
async def test_get_project_authorization_boundary(
    client: AsyncClient,
    test_user: User,
    test_user_2: User,
    auth_headers: dict[str, str],
    auth_headers_2: dict[str, str],
) -> None:
    """Test that a user cannot access another user's project (403 Forbidden)."""
    # Create project by Alice
    create_resp = await client.post(
        "/api/v1/projects",
        json={"name": "Alice Confidential Project"},
        headers=auth_headers,
    )
    assert create_resp.status_code == 201
    project_id = create_resp.json()["id"]

    # Alice can view her own project
    resp_alice = await client.get(f"/api/v1/projects/{project_id}", headers=auth_headers)
    assert resp_alice.status_code == 200
    assert resp_alice.json()["id"] == project_id

    # Bob attempts to view Alice's project -> 403 Forbidden
    resp_bob = await client.get(f"/api/v1/projects/{project_id}", headers=auth_headers_2)
    assert resp_bob.status_code == 403
    assert "permission" in resp_bob.json()["detail"].lower()


@pytest.mark.asyncio
async def test_update_project_authorization_boundary(
    client: AsyncClient,
    auth_headers: dict[str, str],
    auth_headers_2: dict[str, str],
) -> None:
    """Test that a user cannot edit another user's project."""
    # Alice creates project
    create_resp = await client.post(
        "/api/v1/projects",
        json={"name": "Original Name", "description": "Original Desc"},
        headers=auth_headers,
    )
    project_id = create_resp.json()["id"]

    # Bob attempts to update Alice's project -> 403 Forbidden
    update_attempt = await client.patch(
        f"/api/v1/projects/{project_id}",
        json={"name": "Hacked Name"},
        headers=auth_headers_2,
    )
    assert update_attempt.status_code == 403

    # Alice successfully updates her project
    update_success = await client.patch(
        f"/api/v1/projects/{project_id}",
        json={"name": "Updated Name By Alice"},
        headers=auth_headers,
    )
    assert update_success.status_code == 200
    assert update_success.json()["name"] == "Updated Name By Alice"


@pytest.mark.asyncio
async def test_delete_project_authorization_boundary(
    client: AsyncClient,
    auth_headers: dict[str, str],
    auth_headers_2: dict[str, str],
) -> None:
    """Test that a user cannot delete another user's project."""
    # Alice creates project
    create_resp = await client.post(
        "/api/v1/projects",
        json={"name": "Project to Delete"},
        headers=auth_headers,
    )
    project_id = create_resp.json()["id"]

    # Bob attempts to delete Alice's project -> 403 Forbidden
    delete_attempt = await client.delete(
        f"/api/v1/projects/{project_id}",
        headers=auth_headers_2,
    )
    assert delete_attempt.status_code == 403

    # Alice deletes her project -> 204 No Content
    delete_success = await client.delete(
        f"/api/v1/projects/{project_id}",
        headers=auth_headers,
    )
    assert delete_success.status_code == 204

    # Project is gone
    get_resp = await client.get(f"/api/v1/projects/{project_id}", headers=auth_headers)
    assert get_resp.status_code == 404
