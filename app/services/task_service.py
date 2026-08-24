from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.models.task import Task, TaskStatus
from app.models.user import User
from app.schemas.task import TaskCreate, TaskUpdate
from app.services.project_service import ProjectService


class TaskService:
    """Service handling task lifecycle, multi-attribute filtering, and status workflows."""

    @staticmethod
    async def create_task(
        db: AsyncSession,
        project_id: int,
        task_in: TaskCreate,
        user_id: int,
    ) -> Task:
        """Create a new task within a project after verifying project ownership."""
        # Ensure project exists and belongs to requesting user
        await ProjectService.get_project_by_id(db, project_id, user_id)

        # If assignee_id provided, verify assignee exists
        if task_in.assignee_id is not None:
            assignee_stmt = select(User).where(User.id == task_in.assignee_id)
            assignee_res = await db.execute(assignee_stmt)
            if not assignee_res.scalars().first():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Assignee user with id {task_in.assignee_id} does not exist.",
                )

        task = Task(
            title=task_in.title,
            description=task_in.description,
            status=task_in.status,
            due_date=task_in.due_date,
            project_id=project_id,
            assignee_id=task_in.assignee_id,
        )
        db.add(task)
        await db.flush()
        await db.refresh(task)
        return task

    @staticmethod
    async def get_task_by_id(
        db: AsyncSession,
        task_id: int,
        user_id: int,
    ) -> Task:
        """Retrieve task by ID ensuring user owns the associated project."""
        stmt = select(Task).join(Project, Task.project_id == Project.id).where(Task.id == task_id)
        result = await db.execute(stmt)
        task = result.scalars().first()

        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Task with id {task_id} not found.",
            )

        # Check authorization via project ownership
        project_stmt = select(Project).where(Project.id == task.project_id)
        project_res = await db.execute(project_stmt)
        project = project_res.scalars().first()

        if not project or project.owner_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access tasks in this project.",
            )

        return task

    @staticmethod
    async def list_tasks(
        db: AsyncSession,
        user_id: int,
        project_id: int | None = None,
        task_status: TaskStatus | None = None,
        assignee_id: int | None = None,
        due_date_from: datetime | None = None,
        due_date_to: datetime | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Task], int]:
        """Search and filter tasks across user projects with pagination."""
        offset = (page - 1) * page_size

        # Base query joined with projects owned by the user
        conditions = [Project.owner_id == user_id]

        if project_id is not None:
            conditions.append(Task.project_id == project_id)
        if task_status is not None:
            conditions.append(Task.status == task_status)
        if assignee_id is not None:
            conditions.append(Task.assignee_id == assignee_id)
        if due_date_from is not None:
            conditions.append(Task.due_date >= due_date_from)
        if due_date_to is not None:
            conditions.append(Task.due_date <= due_date_to)

        # Count total matching rows
        count_stmt = (
            select(func.count(Task.id))
            .join(Project, Task.project_id == Project.id)
            .where(*conditions)
        )
        total_res = await db.execute(count_stmt)
        total = total_res.scalar_one()

        # Query filtered paginated items
        stmt = (
            select(Task)
            .join(Project, Task.project_id == Project.id)
            .where(*conditions)
            .order_by(Task.due_date.asc().nulls_last(), Task.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        result = await db.execute(stmt)
        tasks = list(result.scalars().all())

        return tasks, total

    @classmethod
    async def update_task(
        cls,
        db: AsyncSession,
        task_id: int,
        task_in: TaskUpdate,
        user_id: int,
    ) -> tuple[Task, int | None, int | None, bool]:
        """
        Update task attributes.
        Returns (task, old_assignee_id, new_assignee_id, status_changed).
        """
        task = await cls.get_task_by_id(db, task_id, user_id)

        old_assignee_id = task.assignee_id
        old_status = task.status
        update_data = task_in.model_dump(exclude_unset=True)

        if "assignee_id" in update_data and update_data["assignee_id"] is not None:
            assignee_stmt = select(User).where(User.id == update_data["assignee_id"])
            assignee_res = await db.execute(assignee_stmt)
            if not assignee_res.scalars().first():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Assignee user with id {update_data['assignee_id']} does not exist.",
                )

        for field, value in update_data.items():
            setattr(task, field, value)

        await db.flush()
        await db.refresh(task)

        new_assignee_id = task.assignee_id
        status_changed = old_status != task.status
        reassigned = old_assignee_id != new_assignee_id and new_assignee_id is not None

        return (
            task,
            old_assignee_id if reassigned else None,
            new_assignee_id if reassigned else None,
            status_changed,
        )

    @classmethod
    async def delete_task(
        cls,
        db: AsyncSession,
        task_id: int,
        user_id: int,
    ) -> None:
        """Delete task after verifying ownership."""
        task = await cls.get_task_by_id(db, task_id, user_id)
        await db.delete(task)
        await db.flush()
