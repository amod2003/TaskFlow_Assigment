import math
from datetime import datetime

from fastapi import APIRouter, Depends, Query, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user
from app.core.config import settings
from app.core.database import get_db
from app.core.redis import get_redis
from app.models.task import TaskStatus
from app.models.user import User
from app.schemas.common import PaginatedResponse
from app.schemas.task import TaskCreate, TaskResponse, TaskUpdate
from app.services.cache_service import CacheService
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
    redis: Redis = Depends(get_redis),
) -> TaskResponse:
    """Create a task within a project and invalidate task cache."""
    task = await TaskService.create_task(
        db=db,
        project_id=project_id,
        task_in=task_in,
        user_id=current_user.id,
    )

    # Invalidate cached task queries for this user
    await CacheService.invalidate_user_tasks_cache(redis, current_user.id)
    if task.assignee_id and task.assignee_id != current_user.id:
        await CacheService.invalidate_user_tasks_cache(redis, task.assignee_id)

    return TaskResponse.model_validate(task)


@router.get(
    "/tasks",
    response_model=PaginatedResponse[TaskResponse],
    status_code=status.HTTP_200_OK,
    summary="Search and filter tasks (Cache-backed)",
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
    redis: Redis = Depends(get_redis),
) -> PaginatedResponse[TaskResponse]:
    """
    Retrieve filtered and paginated tasks.
    Uses Redis cache-aside strategy with automatic cache invalidation on task changes.
    """
    # Build filter dictionary for deterministic cache key generation
    filter_params = {
        "project_id": project_id,
        "status": task_status.value if task_status else None,
        "assignee_id": assignee_id,
        "due_date_from": due_date_from.isoformat() if due_date_from else None,
        "due_date_to": due_date_to.isoformat() if due_date_to else None,
        "page": page,
        "page_size": page_size,
    }
    cache_key = CacheService.generate_task_cache_key(current_user.id, filter_params)

    # 1. Attempt Cache Read
    cached_data = await CacheService.get_cached_tasks(redis, cache_key)
    if cached_data:
        return PaginatedResponse[TaskResponse](**cached_data)

    # 2. Cache Miss: Query Database
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

    response_payload = PaginatedResponse[TaskResponse](
        items=[TaskResponse.model_validate(t) for t in tasks],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        has_next=page < total_pages,
        has_prev=page > 1,
    )

    # 3. Populate Cache
    await CacheService.set_cached_tasks(
        redis_client=redis,
        cache_key=cache_key,
        data=response_payload.model_dump(mode="json"),
        ttl_seconds=settings.CACHE_TTL_SECONDS,
    )

    return response_payload


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
    redis: Redis = Depends(get_redis),
) -> TaskResponse:
    """
    Update task attributes, status, or assignee.
    Immediately flushes user cache to guarantee zero stale reads on status changes.
    """
    task, old_assignee, new_assignee, status_changed = await TaskService.update_task(
        db=db,
        task_id=task_id,
        task_in=task_in,
        user_id=current_user.id,
    )

    # Invalidate owner cache
    await CacheService.invalidate_user_tasks_cache(redis, current_user.id)

    # If assignee was modified, invalidate affected user caches
    if old_assignee and old_assignee != current_user.id:
        await CacheService.invalidate_user_tasks_cache(redis, old_assignee)
    if new_assignee and new_assignee != current_user.id:
        await CacheService.invalidate_user_tasks_cache(redis, new_assignee)

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
    redis: Redis = Depends(get_redis),
) -> None:
    """Delete a task and invalidate cache."""
    await TaskService.delete_task(db, task_id, current_user.id)
    await CacheService.invalidate_user_tasks_cache(redis, current_user.id)
