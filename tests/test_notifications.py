from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification, NotificationType
from app.models.project import Project
from app.models.task import Task, TaskStatus
from app.models.user import User
from app.workers.tasks import check_overdue_tasks, notify_task_reassigned


@pytest.mark.asyncio
async def test_reassign_task_triggers_background_worker(
    client: AsyncClient,
    test_user_2: User,
    auth_headers: dict[str, str],
) -> None:
    """Test that creating a task with assignee triggers the Celery delay method."""
    proj_resp = await client.post(
        "/api/v1/projects",
        json={"name": "Worker Trigger Project"},
        headers=auth_headers,
    )
    project_id = proj_resp.json()["id"]

    with patch("app.api.v1.tasks.notify_task_reassigned.delay") as mock_delay:
        # Create task assigned to test_user_2 (Bob)
        task_resp = await client.post(
            f"/api/v1/projects/{project_id}/tasks",
            json={
                "title": "Celery Worker Task",
                "status": "todo",
                "assignee_id": test_user_2.id,
            },
            headers=auth_headers,
        )
        assert task_resp.status_code == 201
        assert mock_delay.called
        assert mock_delay.call_args.kwargs["new_assignee_id"] == test_user_2.id


@pytest.mark.asyncio
async def test_notify_task_reassigned_worker_execution(
    db_session: AsyncSession,
    test_user: User,
    test_user_2: User,
) -> None:
    """Test running the worker function creates a Notification record."""
    # Create project and task directly
    project = Project(name="Project X", owner_id=test_user.id)
    db_session.add(project)
    await db_session.flush()

    task = Task(title="Design Review", project_id=project.id, assignee_id=test_user_2.id)
    db_session.add(task)
    await db_session.flush()

    # We patch SyncSessionLocal in workers.tasks to use our test session factory
    with patch("app.workers.tasks.SyncSessionLocal") as mock_session_factory:
        # Create a mock session context manager that interacts with db
        class SessionContext:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_val, exc_tb):
                pass

            def add(self, obj):
                db_session.add(obj)

            def commit(self):
                pass

            def refresh(self, obj):
                obj.id = 999

        mock_session_factory.return_value = SessionContext()

        result = notify_task_reassigned(
            task_id=task.id,
            new_assignee_id=test_user_2.id,
            task_title=task.title,
            project_id=project.id,
            old_assignee_id=None,
        )
        assert result["status"] == "success"
        assert result["user_id"] == test_user_2.id


@pytest.mark.asyncio
async def test_check_overdue_tasks_worker_execution(
    db_session: AsyncSession,
    test_user: User,
) -> None:
    """Test overdue tasks scanner creates notifications for overdue tasks."""
    project = Project(name="Overdue Project", owner_id=test_user.id)
    db_session.add(project)
    await db_session.flush()

    past_date = datetime.now(UTC) - timedelta(days=2)
    overdue_task = Task(
        title="Late Report",
        project_id=project.id,
        status=TaskStatus.TODO,
        due_date=past_date,
        assignee_id=test_user.id,
    )
    db_session.add(overdue_task)
    await db_session.flush()

    created_notifications = []

    with patch("app.workers.tasks.SyncSessionLocal") as mock_session_factory:

        class SessionContext:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_val, exc_tb):
                pass

            def scalars(self, stmt):
                class Result:
                    def all(self):
                        return [overdue_task]

                    def first(self):
                        return None

                return Result()

            def get(self, model, pk):
                return project

            def add(self, obj):
                created_notifications.append(obj)

            def commit(self):
                pass

        mock_session_factory.return_value = SessionContext()

        result = check_overdue_tasks()
        assert result["status"] == "success"
        assert result["overdue_tasks_count"] == 1
        assert result["notifications_created"] == 1
        assert len(created_notifications) == 1
        assert created_notifications[0].type == NotificationType.TASK_OVERDUE


@pytest.mark.asyncio
async def test_notifications_api_endpoints(
    client: AsyncClient,
    db_session: AsyncSession,
    test_user: User,
    auth_headers: dict[str, str],
) -> None:
    """Test listing notifications and marking as read."""
    # Seed 2 notifications for test_user
    n1 = Notification(
        user_id=test_user.id,
        type=NotificationType.TASK_REASSIGNED,
        title="Task Reassigned",
        message="You were assigned a new task.",
        is_read=False,
    )
    n2 = Notification(
        user_id=test_user.id,
        type=NotificationType.TASK_OVERDUE,
        title="Task Overdue",
        message="Your task is past due date.",
        is_read=False,
    )
    db_session.add_all([n1, n2])
    await db_session.flush()

    # List notifications
    list_resp = await client.get("/api/v1/notifications", headers=auth_headers)
    assert list_resp.status_code == 200
    data = list_resp.json()
    assert data["total"] == 2

    # Mark n1 as read
    patch_resp = await client.patch(f"/api/v1/notifications/{n1.id}/read", headers=auth_headers)
    assert patch_resp.status_code == 200
    assert patch_resp.json()["is_read"] is True

    # Mark all read
    read_all_resp = await client.post("/api/v1/notifications/read-all", headers=auth_headers)
    assert read_all_resp.status_code == 200
    assert "Marked 1 notifications as read" in read_all_resp.json()["message"]
