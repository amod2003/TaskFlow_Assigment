from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class MessageResponse(BaseModel):
    """Standard message response schema."""

    message: str
    detail: str | None = None


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic pagination response wrapper."""

    model_config = ConfigDict(from_attributes=True)

    items: list[T]
    total: int = Field(..., description="Total number of items matching filters")
    page: int = Field(..., ge=1, description="Current page number")
    page_size: int = Field(..., ge=1, description="Number of items per page")
    total_pages: int = Field(..., ge=0, description="Total number of available pages")
    has_next: bool = Field(..., description="Whether a next page exists")
    has_prev: bool = Field(..., description="Whether a previous page exists")
