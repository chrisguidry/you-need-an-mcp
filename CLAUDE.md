# CLAUDE.md

## Project Overview

MCP (Model Context Protocol) server for YNAB (You Need A Budget) using FastMCP. Provides structured access to YNAB financial data.

## Essential Commands

```bash
# Development
uv sync --group dev              # Install all dependencies
uv run pytest --cov=server --cov=models --cov-report=term-missing  # Run tests with coverage
uv run fastmcp run server.py:mcp # Run MCP server

# Authentication (required)
export YNAB_ACCESS_TOKEN=your_token_here
export YNAB_DEFAULT_BUDGET=your_budget_id_here  # Optional
```

## Critical Design Principles

1. **100% test coverage is mandatory** - No exceptions. All new code must have complete coverage.
2. **All listing tools must implement pagination** - Use `limit` and `offset` parameters.
3. **Automatically filter out deleted/hidden/closed data** - Only show active, relevant data.
4. **Use real YNAB SDK models in tests** - Mock only the API calls, not the data structures.
5. **Handle milliunits properly** - 1000 milliunits = 1 currency unit.

## Product Philosophy

- **Household finance assistant** - Help heads of household be more effective with YNAB
- **Insights and notifications** - Surface important financial patterns and alerts
- **Safe evolution** - Currently read-only, will add careful mutations (transactions, imports)
- **Natural language friendly** - Enable text-based transaction entry and import assistance
- **User-friendly defaults** - Sensible limits, current month defaults, active data only
- **Performance conscious** - Pagination prevents token overflow, efficient payee search

## Security & Privacy

- **Never log financial amounts or account numbers** - Use debug logs carefully
- **Sanitize error messages** - Don't expose internal IDs or sensitive details
- **Token safety** - Never commit or expose YNAB access tokens
- **Fail securely** - Return generic errors for auth failures

## Tool Documentation

**Critical**: Tool docstrings directly influence how LLMs use the MCP server. Every parameter must have clear descriptions explaining valid values and defaults. Bad docs = bad AI behavior.

## Testing Guidelines

- Always run the full test suite after changes: `uv run pytest`
- Use FastMCP's testing pattern with direct client-server testing
- Mock YNAB API calls, but use real YNAB model instances
- Verify pagination works correctly for all listing endpoints

## Architecture

- `server.py` - MCP server implementation using `@mcp.tool()` decorators
- `models.py` - Pydantic models matching YNAB's data structures
- Uses context managers for YNAB client lifecycle
- Returns structured JSON with consistent pagination format
- Handle YNAB API errors gracefully with user-friendly messages