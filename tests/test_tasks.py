from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


@pytest.mark.asyncio
async def test_create_task_success(
    client: AsyncClient,
    test_user: User,
    test_user_2: User,
    auth_headers: dict[str, str],
) -> None:
    """Test creating a task within an owned project with an assignee and due date."""
    # Create project
    proj_resp = await client.post(
        "/api/v1/projects",
        json={"name": "Backend Development"},
        headers=auth_headers,
    )
    project_id = proj_resp.json()["id"]

    due_date = (datetime.now(UTC) + timedelta(days=7)).isoformat()
    task_payload = {
        "title": "Implement Redis Caching",
        "description": "Cache GET /tasks endpoint with invalidation strategy.",
        "status": "todo",
        "due_date": due_date,
        "assignee_id": test_user_2.id,
    }
    response = await client.post(
        f"/api/v1/projects/{project_id}/tasks",
        json=task_payload,
        headers=auth_headers,
    )
    assert response.status_code == 201

    data = response.json()
    assert data["title"] == "Implement Redis Caching"
    assert data["status"] == "todo"
    assert data["assignee_id"] == test_user_2.id
    assert data["project_id"] == project_id
    assert "id" in data


@pytest.mark.asyncio
async def test_create_task_in_foreign_project_forbidden(
    client: AsyncClient,
    auth_headers: dict[str, str],
    auth_headers_2: dict[str, str],
) -> None:
    """Test that User B cannot create a task inside User A's project."""
    # Alice creates project
    proj_resp = await client.post(
        "/api/v1/projects",
        json={"name": "Alice Private Project"},
        headers=auth_headers,
    )
    project_id = proj_resp.json()["id"]

    # Bob attempts to add a task to Alice's project -> 403 Forbidden
    task_resp = await client.post(
        f"/api/v1/projects/{project_id}/tasks",
        json={"title": "Unauthorized Task", "status": "todo"},
        headers=auth_headers_2,
    )
    assert task_resp.status_code == 403


@pytest.mark.asyncio
async def test_tasks_filtering_by_status(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    """Test filtering tasks by status (todo, in_progress, done)."""
    proj_resp = await client.post(
        "/api/v1/projects",
        json={"name": "Status Filtering Project"},
        headers=auth_headers,
    )
    project_id = proj_resp.json()["id"]

    # Create tasks in different statuses
    await client.post(
        f"/api/v1/projects/{project_id}/tasks",
        json={"title": "Task 1", "status": "todo"},
        headers=auth_headers,
    )
    await client.post(
        f"/api/v1/projects/{project_id}/tasks",
        json={"title": "Task 2", "status": "in_progress"},
        headers=auth_headers,
    )
    await client.post(
        f"/api/v1/projects/{project_id}/tasks",
        json={"title": "Task 3", "status": "done"},
        headers=auth_headers,
    )

    # Filter status=in_progress
    resp = await client.get("/api/v1/tasks?status=in_progress", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["title"] == "Task 2"
    assert data["items"][0]["status"] == "in_progress"

    # Filter status=done
    resp_done = await client.get("/api/v1/tasks?status=done", headers=auth_headers)
    assert resp_done.status_code == 200
    assert resp_done.json()["total"] == 1
    assert resp_done.json()["items"][0]["title"] == "Task 3"


@pytest.mark.asyncio
async def test_tasks_filtering_by_due_date_range(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    """Test filtering tasks by due date range."""
    proj_resp = await client.post(
        "/api/v1/projects",
        json={"name": "Date Range Project"},
        headers=auth_headers,
    )
    project_id = proj_resp.json()["id"]

    now = datetime.now(UTC)
    t1_date = (now + timedelta(days=2)).isoformat()
    t2_date = (now + timedelta(days=10)).isoformat()
    t3_date = (now + timedelta(days=20)).isoformat()

    await client.post(
        f"/api/v1/projects/{project_id}/tasks",
        json={"title": "Soon Task", "status": "todo", "due_date": t1_date},
        headers=auth_headers,
    )
    await client.post(
        f"/api/v1/projects/{project_id}/tasks",
        json={"title": "Mid Task", "status": "todo", "due_date": t2_date},
        headers=auth_headers,
    )
    await client.post(
        f"/api/v1/projects/{project_id}/tasks",
        json={"title": "Late Task", "status": "todo", "due_date": t3_date},
        headers=auth_headers,
    )

    # Filter range: days 5 to 15 (should only match Mid Task)
    from_date = (now + timedelta(days=5)).isoformat()
    to_date = (now + timedelta(days=15)).isoformat()

    resp = await client.get(
        "/api/v1/tasks",
        params={"due_date_from": from_date, "due_date_to": to_date},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["title"] == "Mid Task"


@pytest.mark.asyncio
async def test_update_task_status_and_reassignment(
    client: AsyncClient,
    test_user_2: User,
    auth_headers: dict[str, str],
) -> None:
    """Test updating task status and assignee."""
    proj_resp = await client.post(
        "/api/v1/projects",
        json={"name": "Task Update Project"},
        headers=auth_headers,
    )
    project_id = proj_resp.json()["id"]

    task_resp = await client.post(
        f"/api/v1/projects/{project_id}/tasks",
        json={"title": "Original Task", "status": "todo"},
        headers=auth_headers,
    )
    task_id = task_resp.json()["id"]

    # Update status to in_progress and assign to Bob
    update_resp = await client.patch(
        f"/api/v1/tasks/{task_id}",
        json={"status": "in_progress", "assignee_id": test_user_2.id},
        headers=auth_headers,
    )
    assert update_resp.status_code == 200
    updated_data = update_resp.json()
    assert updated_data["status"] == "in_progress"
    assert updated_data["assignee_id"] == test_user_2.id


@pytest.mark.asyncio
async def test_delete_task(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    """Test task deletion."""
    proj_resp = await client.post(
        "/api/v1/projects",
        json={"name": "Task Delete Project"},
        headers=auth_headers,
    )
    project_id = proj_resp.json()["id"]

    task_resp = await client.post(
        f"/api/v1/projects/{project_id}/tasks",
        json={"title": "Task to be Deleted", "status": "todo"},
        headers=auth_headers,
    )
    task_id = task_resp.json()["id"]

    # Delete task
    del_resp = await client.delete(f"/api/v1/tasks/{task_id}", headers=auth_headers)
    assert del_resp.status_code == 204

    # Verify task is gone
    get_resp = await client.get(f"/api/v1/tasks/{task_id}", headers=auth_headers)
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_create_task_unassigned_success(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    """Test creating a task without an assignee."""
    proj_resp = await client.post(
        "/api/v1/projects",
        json={"name": "Unassigned Task Project"},
        headers=auth_headers,
    )
    project_id = proj_resp.json()["id"]

    task_payload = {
        "title": "Unassigned Task",
        "description": "No assignee yet.",
        "status": "todo",
    }
    response = await client.post(
        f"/api/v1/projects/{project_id}/tasks",
        json=task_payload,
        headers=auth_headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Unassigned Task"
    assert data["assignee_id"] is None


@pytest.mark.asyncio
async def test_filter_tasks_by_assignee_id(
    client: AsyncClient,
    test_user: User,
    test_user_2: User,
    auth_headers: dict[str, str],
) -> None:
    """Test filtering tasks by assignee_id."""
    proj_resp = await client.post(
        "/api/v1/projects",
        json={"name": "Assignee Filter Project"},
        headers=auth_headers,
    )
    project_id = proj_resp.json()["id"]

    await client.post(
        f"/api/v1/projects/{project_id}/tasks",
        json={"title": "Alice Task", "assignee_id": test_user.id},
        headers=auth_headers,
    )
    await client.post(
        f"/api/v1/projects/{project_id}/tasks",
        json={"title": "Bob Task", "assignee_id": test_user_2.id},
        headers=auth_headers,
    )
    await client.post(
        f"/api/v1/projects/{project_id}/tasks",
        json={"title": "Unassigned Task"},
        headers=auth_headers,
    )

    resp_alice = await client.get(
        "/api/v1/tasks",
        params={"assignee_id": test_user.id},
        headers=auth_headers,
    )
    assert resp_alice.status_code == 200
    data = resp_alice.json()
    assert data["total"] == 1
    assert data["items"][0]["title"] == "Alice Task"

    resp_bob = await client.get(
        "/api/v1/tasks",
        params={"assignee_id": test_user_2.id},
        headers=auth_headers,
    )
    assert resp_bob.status_code == 200
    data = resp_bob.json()
    assert data["total"] == 1
    assert data["items"][0]["title"] == "Bob Task"


@pytest.mark.asyncio
async def test_assign_inactive_user_fails(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict[str, str],
) -> None:
    """Test that assigning a task to an inactive user returns 400."""
    proj_resp = await client.post(
        "/api/v1/projects",
        json={"name": "Inactive Assignee Project"},
        headers=auth_headers,
    )
    project_id = proj_resp.json()["id"]

    inactive_user = User(
        email="inactive@example.com",
        hashed_password="test",
        full_name="Inactive User",
        is_active=False,
    )
    db_session.add(inactive_user)
    await db_session.flush()
    await db_session.refresh(inactive_user)

    task_payload = {
        "title": "Task for Inactive User",
        "assignee_id": inactive_user.id,
    }
    response = await client.post(
        f"/api/v1/projects/{project_id}/tasks",
        json=task_payload,
        headers=auth_headers,
    )
    assert response.status_code == 400
    assert "not active" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_unassign_task_invalidates_old_assignee_cache(
    client: AsyncClient,
    test_user: User,
    test_user_2: User,
    auth_headers: dict[str, str],
    auth_headers_2: dict[str, str],
    fake_redis,
) -> None:
    """Test that unassigning a task invalidates the old assignee's cache."""
    proj_resp = await client.post(
        "/api/v1/projects",
        json={"name": "Cache Invalidation Project"},
        headers=auth_headers,
    )
    project_id = proj_resp.json()["id"]

    task_resp = await client.post(
        f"/api/v1/projects/{project_id}/tasks",
        json={"title": "Cache Test Task", "assignee_id": test_user_2.id},
        headers=auth_headers,
    )
    task_id = task_resp.json()["id"]

    await client.get("/api/v1/tasks", headers=auth_headers_2)
    cache_key_pattern = f"taskflow:cache:user:{test_user_2.id}:tasks:*"
    import fnmatch

    keys = []
    for key in await fake_redis.keys("*"):
        decoded = key.decode() if isinstance(key, bytes) else key
        if fnmatch.fnmatch(decoded, cache_key_pattern):
            keys.append(decoded)
    assert len(keys) > 0, "Expected cache keys to exist for old assignee"

    await client.patch(
        f"/api/v1/tasks/{task_id}",
        json={"assignee_id": None},
        headers=auth_headers,
    )

    keys_after = []
    for key in await fake_redis.keys("*"):
        decoded = key.decode() if isinstance(key, bytes) else key
        if fnmatch.fnmatch(decoded, cache_key_pattern):
            keys_after.append(decoded)
    assert len(keys_after) == 0, "Expected old assignee cache keys to be invalidated"
