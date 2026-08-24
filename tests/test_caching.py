import fakeredis.aioredis as fakeredis
import pytest
from httpx import AsyncClient

from app.services.cache_service import CacheService


@pytest.mark.asyncio
async def test_cache_key_generation_deterministic() -> None:
    """Test that query parameter ordering produces identical deterministic cache keys."""
    user_id = 42
    params_1 = {"status": "todo", "page": 1, "page_size": 20, "assignee_id": 5}
    params_2 = {"assignee_id": 5, "page_size": 20, "page": 1, "status": "todo"}

    key1 = CacheService.generate_task_cache_key(user_id, params_1)
    key2 = CacheService.generate_task_cache_key(user_id, params_2)

    assert key1 == key2
    assert key1.startswith("taskflow:cache:user:42:tasks:")


@pytest.mark.asyncio
async def test_tasks_caching_and_cache_hit(
    client: AsyncClient,
    fake_redis: fakeredis.FakeRedis,
    auth_headers: dict[str, str],
) -> None:
    """Test that GET /tasks populates Redis cache and subsequent call hits cache."""
    # Create project and a task
    proj_resp = await client.post(
        "/api/v1/projects",
        json={"name": "Cache Test Project"},
        headers=auth_headers,
    )
    project_id = proj_resp.json()["id"]

    await client.post(
        f"/api/v1/projects/{project_id}/tasks",
        json={"title": "Test Caching", "status": "todo"},
        headers=auth_headers,
    )

    # First request: Cache Miss -> DB Query -> Populates Cache
    resp1 = await client.get("/api/v1/tasks", headers=auth_headers)
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["total"] == 1

    # Verify key exists in Redis
    keys = []
    async for key in fake_redis.scan_iter(match="taskflow:cache:user:*:tasks:*"):
        keys.append(key)
    assert len(keys) >= 1

    # Second request: Cache Hit
    resp2 = await client.get("/api/v1/tasks", headers=auth_headers)
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["total"] == data1["total"]
    assert data2["items"][0]["id"] == data1["items"][0]["id"]


@pytest.mark.asyncio
async def test_no_stale_reads_on_status_update(
    client: AsyncClient,
    fake_redis: fakeredis.FakeRedis,
    auth_headers: dict[str, str],
) -> None:
    """
    Critical requirement:
    Test that updating a task status immediately flushes user cache,
    preventing any stale reads.
    """
    proj_resp = await client.post(
        "/api/v1/projects",
        json={"name": "Stale Read Prevention Project"},
        headers=auth_headers,
    )
    project_id = proj_resp.json()["id"]

    task_resp = await client.post(
        f"/api/v1/projects/{project_id}/tasks",
        json={"title": "Critical Bug Fix", "status": "todo"},
        headers=auth_headers,
    )
    task_id = task_resp.json()["id"]

    # Initial query caches status='todo'
    initial_get = await client.get("/api/v1/tasks", headers=auth_headers)
    assert initial_get.json()["items"][0]["status"] == "todo"

    # Status update to 'in_progress'
    patch_resp = await client.patch(
        f"/api/v1/tasks/{task_id}",
        json={"status": "in_progress"},
        headers=auth_headers,
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["status"] == "in_progress"

    # Immediate read MUST reflect 'in_progress' (no stale 'todo')
    fresh_get = await client.get("/api/v1/tasks", headers=auth_headers)
    assert fresh_get.status_code == 200
    assert fresh_get.json()["items"][0]["status"] == "in_progress"

    # Further status update to 'done'
    patch_done = await client.patch(
        f"/api/v1/tasks/{task_id}",
        json={"status": "done"},
        headers=auth_headers,
    )
    assert patch_done.status_code == 200

    # Filtered query for status=done MUST return the item
    done_get = await client.get("/api/v1/tasks?status=done", headers=auth_headers)
    assert done_get.status_code == 200
    assert done_get.json()["total"] == 1
    assert done_get.json()["items"][0]["status"] == "done"


@pytest.mark.asyncio
async def test_cache_invalidation_on_task_deletion(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    """Test that deleting a task invalidates the cache immediately."""
    proj_resp = await client.post(
        "/api/v1/projects",
        json={"name": "Deletion Cache Test"},
        headers=auth_headers,
    )
    project_id = proj_resp.json()["id"]

    task_resp = await client.post(
        f"/api/v1/projects/{project_id}/tasks",
        json={"title": "Temporary Task", "status": "todo"},
        headers=auth_headers,
    )
    task_id = task_resp.json()["id"]

    # Cache list
    r1 = await client.get("/api/v1/tasks", headers=auth_headers)
    assert r1.json()["total"] == 1

    # Delete task
    del_resp = await client.delete(f"/api/v1/tasks/{task_id}", headers=auth_headers)
    assert del_resp.status_code == 204

    # Subsequent list read reflects 0 tasks
    r2 = await client.get("/api/v1/tasks", headers=auth_headers)
    assert r2.json()["total"] == 0
    assert len(r2.json()["items"]) == 0
