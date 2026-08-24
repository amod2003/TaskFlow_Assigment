"""Pydantic schemas package."""

from app.schemas.auth import LoginRequest, TokenPayload, TokenResponse
from app.schemas.common import MessageResponse, PaginatedResponse
from app.schemas.notification import NotificationResponse
from app.schemas.project import ProjectCreate, ProjectResponse, ProjectUpdate
from app.schemas.task import TaskCreate, TaskResponse, TaskUpdate
from app.schemas.user import UserCreate, UserResponse, UserUpdate

__all__ = [
    "LoginRequest",
    "TokenPayload",
    "TokenResponse",
    "MessageResponse",
    "PaginatedResponse",
    "NotificationResponse",
    "UserCreate",
    "UserResponse",
    "UserUpdate",
    "ProjectCreate",
    "ProjectResponse",
    "ProjectUpdate",
    "TaskCreate",
    "TaskResponse",
    "TaskUpdate",
]
