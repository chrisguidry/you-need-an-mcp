"""
Turning YNAB API errors into messages a model can act on.

The server masks the details of unexpected errors, so that a stack trace never
leaks internal state to the client.  A YNAB API error is different: YNAB writes
its error detail for the caller ("category_id does not exist"), and the model
needs that detail to correct its next call.  This middleware passes the detail
through as a ToolError, which the server never masks.

FastMCP masks a tool's exception before middleware sees it, but it chains the
original exception as the masked error's cause, so that is where this looks.
"""

import json
import logging

import mcp.types as mt
from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.tools import ToolResult
from ynab.exceptions import ApiException

logger = logging.getLogger(__name__)


def describe_api_error(error: ApiException) -> str:
    """Describe a YNAB API error in one sentence, without the access token."""
    if error.status == 401:
        return "YNAB did not accept the access token. Check YNAB_ACCESS_TOKEN."
    if error.status == 429:
        return "YNAB's rate limit is exhausted. Wait a few minutes and try again."

    detail = None
    try:
        detail = json.loads(error.body or "")["error"]["detail"]
    except (ValueError, KeyError, TypeError):
        pass
    return f"YNAB returned {error.status}: {detail or error.reason or 'no detail'}"


class YNABErrorMiddleware(Middleware):
    """Report YNAB API errors from any tool as ToolErrors."""

    async def on_call_tool(
        self,
        context: MiddlewareContext[mt.CallToolRequestParams],
        call_next: CallNext[mt.CallToolRequestParams, ToolResult],
    ) -> ToolResult:
        try:
            return await call_next(context)
        except ToolError as error:
            cause = error.__cause__
            if not isinstance(cause, ApiException):
                raise
            logger.warning("YNAB API error %s in %s", cause.status, context.method)
            raise ToolError(describe_api_error(cause)) from cause
