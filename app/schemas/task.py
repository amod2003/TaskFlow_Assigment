from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.task import TaskStatus


class TaskBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=255, description="Task title")
    description: str | None = Field(default=None, description="Task description")
    status: TaskStatus = Field(default=TaskStatus.TODO, description="Task status")
    due_date: datetime | None = Field(default=None, description="Due date in UTC")
    assignee_id: int | None = Field(default=None, description="Assignee user ID")


class TaskCreate(TaskBase):
    pass


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None)
    status: TaskStatus | None = Field(default=None)
    due_date: datetime | None = Field(default=None)
    assignee_id: int | None = Field(default=None)


class TaskResponse(TaskBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    created_at: datetime
    updated_at: datetime
