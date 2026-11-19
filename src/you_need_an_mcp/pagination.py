"""
Pagination for listing tools.

Every listing tool pages its results, so that a large plan never overflows a
model's context in one response.
"""

from pydantic import BaseModel, Field


class PaginationInfo(BaseModel):
    """Pagination metadata for listing endpoints."""

    total_count: int = Field(..., description="Total number of items available")
    limit: int = Field(..., description="Maximum items per page")
    offset: int = Field(..., description="Number of items skipped")
    has_more: bool = Field(..., description="Whether more items are available")


def paginate[T](
    items: list[T], limit: int, offset: int
) -> tuple[list[T], PaginationInfo]:
    """Return one page of items and the pagination info that describes it."""
    total_count = len(items)
    end_index = min(offset + limit, total_count)
    pagination = PaginationInfo(
        total_count=total_count,
        limit=limit,
        offset=offset,
        has_more=end_index < total_count,
    )
    return items[offset:end_index], pagination
