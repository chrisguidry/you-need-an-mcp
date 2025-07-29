"""
Test assertion helpers for YNAB MCP Server tests.

This module provides helper functions for common test assertions and response
parsing to reduce boilerplate in test files.
"""

import json
from typing import Any

from mcp.types import TextContent


def extract_response_data(result: list[Any]) -> dict[str, Any]:
    """Extract JSON data from MCP client response."""
    assert len(result) == 1
    response_data = (
        json.loads(result[0].text) if isinstance(result[0], TextContent) else None
    )
    assert response_data is not None
    return response_data  # type: ignore[no-any-return]


def assert_pagination_info(
    pagination: dict[str, Any],
    *,
    total_count: int,
    limit: int,
    offset: int = 0,
    has_more: bool = False,
) -> None:
    """Assert pagination info matches expected values."""
    assert pagination["total_count"] == total_count
    assert pagination["limit"] == limit
    assert pagination["offset"] == offset
    assert pagination["has_more"] == has_more
