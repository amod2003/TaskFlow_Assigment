import math

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_active_user
from app.core.config import settings
from app.core.database import get_db
from app.models.user import User
from app.schemas.common import PaginatedResponse
from app.schemas.project import ProjectCreate, ProjectResponse, ProjectUpdate
from app.services.project_service import ProjectService

router = APIRouter(prefix="/projects", tags=["Projects"])


@router.post(
    "",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new project",
)
async def create_project(
    project_in: ProjectCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectResponse:
    """Create a new project owned by the authenticated user."""
    project = await ProjectService.create_project(db, project_in, current_user.id)
    return ProjectResponse.model_validate(project)


@router.get(
    "",
    response_model=PaginatedResponse[ProjectResponse],
    status_code=status.HTTP_200_OK,
    summary="List all projects for current user",
)
async def list_projects(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(
        default=settings.DEFAULT_PAGE_SIZE,
        ge=1,
        le=settings.MAX_PAGE_SIZE,
        description="Items per page",
    ),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse[ProjectResponse]:
    """Retrieve all projects owned by the authenticated user with pagination."""
    projects, total = await ProjectService.get_user_projects(
        db=db,
        owner_id=current_user.id,
        page=page,
        page_size=page_size,
    )
    total_pages = math.ceil(total / page_size) if total > 0 else 0

    return PaginatedResponse[ProjectResponse](
        items=[ProjectResponse.model_validate(p) for p in projects],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        has_next=page < total_pages,
        has_prev=page > 1,
    )


@router.get(
    "/{project_id}",
    response_model=ProjectResponse,
    status_code=status.HTTP_200_OK,
    summary="Get project details by ID",
)
async def get_project(
    project_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectResponse:
    """Retrieve project details. Access is restricted to the project owner."""
    project = await ProjectService.get_project_by_id(db, project_id, current_user.id)
    return ProjectResponse.model_validate(project)


@router.patch(
    "/{project_id}",
    response_model=ProjectResponse,
    status_code=status.HTTP_200_OK,
    summary="Update project details",
)
async def update_project(
    project_id: int,
    project_in: ProjectUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> ProjectResponse:
    """Update project details. Access is restricted to the project owner."""
    project = await ProjectService.update_project(
        db=db,
        project_id=project_id,
        project_in=project_in,
        user_id=current_user.id,
    )
    return ProjectResponse.model_validate(project)


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a project",
)
async def delete_project(
    project_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a project and its associated tasks. Access is restricted to the project owner."""
    await ProjectService.delete_project(db, project_id, current_user.id)
