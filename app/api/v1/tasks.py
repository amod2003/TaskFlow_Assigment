import math
from datetime import datetime

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user
from app.core.config import settings
from app.core.database import get_db
from app.models.task import TaskStatus
from app.models.user import User
from app.schemas.common import PaginatedResponse
from app.schemas.task import TaskCreate, TaskResponse, TaskUpdate
from app.services.task_service import TaskService

router = APIRouter(tags=["Tasks"])


@router.post(
    "/projects/{project_id}/tasks",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new task in a project",
)
async def create_task(
    project_id: int,
    task_in: TaskCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> TaskResponse:
    """Create a task within a project. Access restricted to project owner."""
    task = await TaskService.create_task(
        db=db,
        project_id=project_id,
        task_in=task_in,
        user_id=current_user.id,
    )
    return TaskResponse.model_validate(task)


@router.get(
    "/tasks",
    response_model=PaginatedResponse[TaskResponse],
    status_code=status.HTTP_200_OK,
    summary="Search and filter tasks",
)
async def list_tasks(
    project_id: int | None = Query(default=None, description="Filter by project ID"),
    task_status: TaskStatus | None = Query(
        default=None, alias="status", description="Filter by status (todo, in_progress, done)"
    ),
    assignee_id: int | None = Query(default=None, description="Filter by assignee user ID"),
    due_date_from: datetime | None = Query(
        default=None, description="Filter tasks due on or after this timestamp (ISO 8601 UTC)"
    ),
    due_date_to: datetime | None = Query(
        default=None, description="Filter tasks due on or before this timestamp (ISO 8601 UTC)"
    ),
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(
        default=settings.DEFAULT_PAGE_SIZE,
        ge=1,
        le=settings.MAX_PAGE_SIZE,
        description="Items per page",
    ),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[TaskResponse]:
    """Retrieve filtered and paginated tasks across projects owned by the user."""
    tasks, total = await TaskService.list_tasks(
        db=db,
        user_id=current_user.id,
        project_id=project_id,
        task_status=task_status,
        assignee_id=assignee_id,
        due_date_from=due_date_from,
        due_date_to=due_date_to,
        page=page,
        page_size=page_size,
    )
    total_pages = math.ceil(total / page_size) if total > 0 else 0

    return PaginatedResponse[TaskResponse](
        items=[TaskResponse.model_validate(t) for t in tasks],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        has_next=page < total_pages,
        has_prev=page > 1,
    )


@router.get(
    "/tasks/{task_id}",
    response_model=TaskResponse,
    status_code=status.HTTP_200_OK,
    summary="Get task details",
)
async def get_task(
    task_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> TaskResponse:
    """Retrieve details for a single task."""
    task = await TaskService.get_task_by_id(db, task_id, current_user.id)
    return TaskResponse.model_validate(task)


@router.patch(
    "/tasks/{task_id}",
    response_model=TaskResponse,
    status_code=status.HTTP_200_OK,
    summary="Update task details or status",
)
async def update_task(
    task_id: int,
    task_in: TaskUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> TaskResponse:
    """Update task attributes, status, or assignee."""
    task, old_assignee, new_assignee, status_changed = await TaskService.update_task(
        db=db,
        task_id=task_id,
        task_in=task_in,
        user_id=current_user.id,
    )
    return TaskResponse.model_validate(task)


@router.delete(
    "/tasks/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a task",
)
async def delete_task(
    task_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a task. Access restricted to project owner."""
    await TaskService.delete_task(db, task_id, current_user.id)
