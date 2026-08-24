from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.schemas.project import ProjectCreate, ProjectUpdate


class ProjectService:
    """Service handling project management and strict multi-tenant authorization."""

    @staticmethod
    async def get_user_projects(
        db: AsyncSession,
        owner_id: int,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Project], int]:
        """Fetch all projects owned by the specified user with pagination."""
        offset = (page - 1) * page_size

        # Count total
        count_stmt = select(func.count(Project.id)).where(Project.owner_id == owner_id)
        total_result = await db.execute(count_stmt)
        total = total_result.scalar_one()

        # Query items
        stmt = (
            select(Project)
            .where(Project.owner_id == owner_id)
            .order_by(Project.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        result = await db.execute(stmt)
        projects = list(result.scalars().all())

        return projects, total

    @staticmethod
    async def get_project_by_id(
        db: AsyncSession,
        project_id: int,
        user_id: int,
    ) -> Project:
        """Fetch a specific project ensuring the requesting user is the owner."""
        stmt = select(Project).where(Project.id == project_id)
        result = await db.execute(stmt)
        project = result.scalars().first()

        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project with id {project_id} not found.",
            )

        # Authorization check: verify ownership
        if project.owner_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this project.",
            )

        return project

    @staticmethod
    async def create_project(
        db: AsyncSession,
        project_in: ProjectCreate,
        owner_id: int,
    ) -> Project:
        """Create a new project associated with the authenticated user."""
        project = Project(
            name=project_in.name,
            description=project_in.description,
            owner_id=owner_id,
        )
        db.add(project)
        await db.flush()
        await db.refresh(project)
        return project

    @classmethod
    async def update_project(
        cls,
        db: AsyncSession,
        project_id: int,
        project_in: ProjectUpdate,
        user_id: int,
    ) -> Project:
        """Update an existing project after validating ownership."""
        project = await cls.get_project_by_id(db, project_id, user_id)

        update_data = project_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(project, field, value)

        await db.flush()
        await db.refresh(project)
        return project

    @classmethod
    async def delete_project(
        cls,
        db: AsyncSession,
        project_id: int,
        user_id: int,
    ) -> None:
        """Delete a project after validating ownership."""
        project = await cls.get_project_by_id(db, project_id, user_id)
        await db.delete(project)
        await db.flush()
