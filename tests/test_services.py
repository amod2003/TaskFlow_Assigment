from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.models.task import TaskStatus
from app.models.user import User
from app.schemas.auth import LoginRequest
from app.schemas.project import ProjectCreate, ProjectUpdate
from app.schemas.task import TaskCreate, TaskUpdate
from app.schemas.user import UserCreate
from app.services.auth_service import AuthService
from app.services.cache_service import CacheService
from app.services.project_service import ProjectService
from app.services.task_service import TaskService


@pytest.mark.asyncio
async def test_auth_service_unit(db_session: AsyncSession) -> None:
    """Unit tests for AuthService edge cases."""
    # Register user
    user_in = UserCreate(
        email="service_test@example.com",
        password="ValidPassword123!",
        full_name="Service Tester",
    )
    user = await AuthService.register_user(db_session, user_in)
    assert user.email == "service_test@example.com"

    # Duplicate registration raises 400
    with pytest.raises(HTTPException) as exc_info:
        await AuthService.register_user(db_session, user_in)
    assert exc_info.value.status_code == 400

    # Inactive user login raises 403
    user.is_active = False
    await db_session.flush()

    login_req = LoginRequest(
        email="service_test@example.com",
        password="ValidPassword123!",
    )
    with pytest.raises(HTTPException) as exc_info:
        await AuthService.authenticate_user(db_session, login_req)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_project_service_unit(
    db_session: AsyncSession, test_user: User, test_user_2: User
) -> None:
    """Unit tests for ProjectService edge cases."""
    # Create project
    proj = await ProjectService.create_project(
        db_session,
        ProjectCreate(name="Unit Test Project", description="Desc"),
        test_user.id,
    )
    assert proj.id is not None

    # Get non-existent project raises 404
    with pytest.raises(HTTPException) as exc_info:
        await ProjectService.get_project_by_id(db_session, 99999, test_user.id)
    assert exc_info.value.status_code == 404

    # Get project by non-owner raises 403
    with pytest.raises(HTTPException) as exc_info:
        await ProjectService.get_project_by_id(db_session, proj.id, test_user_2.id)
    assert exc_info.value.status_code == 403

    # Update project
    updated = await ProjectService.update_project(
        db_session,
        proj.id,
        ProjectUpdate(name="Renamed Project"),
        test_user.id,
    )
    assert updated.name == "Renamed Project"

    # Delete project
    await ProjectService.delete_project(db_session, proj.id, test_user.id)


@pytest.mark.asyncio
async def test_task_service_unit(
    db_session: AsyncSession, test_user: User, test_user_2: User
) -> None:
    """Unit tests for TaskService edge cases."""
    proj = await ProjectService.create_project(
        db_session,
        ProjectCreate(name="Task Unit Project"),
        test_user.id,
    )

    # Creating task with non-existent assignee raises 400
    with pytest.raises(HTTPException) as exc_info:
        await TaskService.create_task(
            db_session,
            proj.id,
            TaskCreate(title="Invalid Assignee Task", assignee_id=99999),
            test_user.id,
        )
    assert exc_info.value.status_code == 400

    # Create valid task
    now = datetime.now(UTC)
    task = await TaskService.create_task(
        db_session,
        proj.id,
        TaskCreate(
            title="Service Task 1",
            status=TaskStatus.TODO,
            due_date=now + timedelta(days=3),
            assignee_id=test_user.id,
        ),
        test_user.id,
    )
    assert task.id is not None

    # Non-existent task raises 404
    with pytest.raises(HTTPException) as exc_info:
        await TaskService.get_task_by_id(db_session, 88888, test_user.id)
    assert exc_info.value.status_code == 404

    # Unauthorized access to task raises 403
    with pytest.raises(HTTPException) as exc_info:
        await TaskService.get_task_by_id(db_session, task.id, test_user_2.id)
    assert exc_info.value.status_code == 403

    # Update task with non-existent assignee raises 400
    with pytest.raises(HTTPException) as exc_info:
        await TaskService.update_task(
            db_session,
            task.id,
            TaskUpdate(assignee_id=99999),
            test_user.id,
        )
    assert exc_info.value.status_code == 400

    # List tasks with project_id and status filters
    tasks, total = await TaskService.list_tasks(
        db_session,
        user_id=test_user.id,
        project_id=proj.id,
        task_status=TaskStatus.TODO,
        assignee_id=test_user.id,
    )
    assert total == 1
    assert len(tasks) == 1

    # Delete task
    await TaskService.delete_task(db_session, task.id, test_user.id)


@pytest.mark.asyncio
async def test_cache_service_error_handling() -> None:
    """Test that CacheService handles Redis connection failures gracefully."""
    mock_redis = AsyncMock()
    mock_redis.get.side_effect = Exception("Redis connection lost")
    mock_redis.set.side_effect = Exception("Redis write failed")
    mock_redis.scan_iter.side_effect = Exception("Redis scan failed")

    # get_cached_tasks returns None on error
    result = await CacheService.get_cached_tasks(mock_redis, "dummy_key")
    assert result is None

    # set_cached_tasks returns False on error
    success = await CacheService.set_cached_tasks(mock_redis, "dummy_key", {"data": 123})
    assert success is False

    # invalidate_user_tasks_cache returns 0 on error
    count = await CacheService.invalidate_user_tasks_cache(mock_redis, 1)
    assert count == 0


@pytest.mark.asyncio
async def test_auth_deps_edge_cases(db_session: AsyncSession) -> None:
    """Test get_current_user dependency edge cases."""
    # Test non-integer subject in token payload
    from app.core.security import create_access_token

    token = create_access_token(subject="not-an-int")
    credentials = MagicMock()
    credentials.credentials = token

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(credentials=credentials, db=db_session)
    assert exc_info.value.status_code == 401
