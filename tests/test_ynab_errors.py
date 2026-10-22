"""
Test how YNAB API errors and unexpected errors reach the client.
"""

from unittest.mock import MagicMock

import pytest
from fastmcp.client import Client, FastMCPTransport
from fastmcp.exceptions import ToolError
from ynab.exceptions import ApiException

from ynab_errors import describe_api_error


@pytest.mark.parametrize(
    ("error", "description"),
    [
        (
            ApiException(status=401, reason="Unauthorized"),
            "YNAB did not accept the access token. Check YNAB_ACCESS_TOKEN.",
        ),
        (
            ApiException(status=429, reason="Too Many Requests"),
            "YNAB's rate limit is exhausted. Wait a few minutes and try again.",
        ),
        (
            ApiException(
                status=400,
                reason="Bad Request",
                body='{"error": {"id": "400", "name": "bad_request", '
                '"detail": "category_id does not exist"}}',
            ),
            "YNAB returned 400: category_id does not exist",
        ),
        (
            ApiException(status=500, reason="Internal Server Error", body="<html>"),
            "YNAB returned 500: Internal Server Error",
        ),
        (ApiException(status=503), "YNAB returned 503: no detail"),
    ],
)
def test_describe_api_error(error: ApiException, description: str) -> None:
    assert describe_api_error(error) == description


async def test_api_errors_reach_the_client_with_ynab_detail(
    months_api: MagicMock, mcp_client: Client[FastMCPTransport]
) -> None:
    months_api.get_plan_months.side_effect = ApiException(
        status=404,
        reason="Not Found",
        body='{"error": {"id": "404.2", "name": "resource_not_found", '
        '"detail": "Plan not found"}}',
    )

    with pytest.raises(ToolError, match="YNAB returned 404: Plan not found"):
        await mcp_client.call_tool("list_plan_months", {})


async def test_unexpected_errors_reach_the_client_without_detail(
    months_api: MagicMock, mcp_client: Client[FastMCPTransport]
) -> None:
    months_api.get_plan_months.side_effect = RuntimeError("internal secret")

    with pytest.raises(ToolError) as raised:
        await mcp_client.call_tool("list_plan_months", {})

    assert "internal secret" not in str(raised.value)
