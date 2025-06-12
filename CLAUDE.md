# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Python project that implements a read-only MCP (Model Context Protocol) server for YNAB (You Need A Budget) using FastMCP. The server provides tools to query YNAB data including budgets and accounts.

## Development Commands

### Package Management

- **Install dependencies**: `uv sync`
- **Install with dev dependencies**: `uv sync --group dev`
- **Add new dependency**: `uv add <package>`
- **Add dev dependency**: `uv add --group dev <package>`
- **Run MCP server**: `uv run fastmcp run server.py:mcp`

### Testing

The project includes a comprehensive test suite with **100% code coverage** that mocks all YNAB API calls.

**Basic Commands:**
- **Run all tests**: `uv run pytest`
- **Run with coverage report**: `uv run pytest --cov=server --cov=models --cov-report=term-missing`
- **Run tests in parallel**: `uv run pytest -n auto`
- **Run verbose output**: `uv run pytest -v`

**Test Categories:**
- **Utility Functions** (8 tests) - Currency conversion, environment handling, client setup
- **MCP Tools** (13 tests) - All 6 MCP tools with pagination, filtering, edge cases

**Key Features:**
- ✅ **No YNAB API dependency** - All tests use realistic mocked data
- ✅ **FastMCP testing patterns** - Direct client-server testing
- ✅ **Comprehensive edge cases** - Hidden/deleted entities, null values, pagination
- ✅ **100% code coverage** - Complete coverage of all modules
- ✅ **Proper isolation** - Each test is independent with mocked environment

### Authentication Setup

Before running the server, you must set up YNAB authentication:

1. Get your YNAB Personal Access Token from Account Settings in YNAB web app
2. Set environment variable: `export YNAB_ACCESS_TOKEN=your_token_here`
3. Optionally set default budget: `export YNAB_DEFAULT_BUDGET=your_budget_id_here`

### Project Structure

- `server.py` - Main MCP server implementation with YNAB integration
- `models.py` - Pydantic models for YNAB entities
- `pyproject.toml` - Project configuration using modern Python packaging standards
- `uv.lock` - Dependency lock file (managed by uv)

## Key Dependencies

- **FastMCP** - MCP server framework - https://gofastmcp.com/
- **ynab** - Official YNAB API Python SDK - https://github.com/ynab/ynab-sdk-python
- **Python** >=3.12 required

## MCP Tools Available

- `list_budgets()` - Returns all YNAB budgets with metadata and currency formatting
- `list_accounts(budget_id: str = None, limit: int = 100, offset: int = 0, include_closed: bool = False)` - Returns accounts with pagination (excludes closed by default)
- `list_categories(budget_id: str = None, limit: int = 50, offset: int = 0, include_hidden: bool = False)` - Returns category structure only with pagination (excludes hidden/deleted by default, no budget amounts)
- `list_category_groups(budget_id: str = None)` - Returns category groups with totals (lighter weight alternative to full categories)
- `get_budget_month(budget_id: str = None, month: str = "current", limit: int = 50, offset: int = 0, include_hidden: bool = False)` - Returns monthly budget data including budgeted amounts, activity, and balances for categories with pagination
- `get_month_category_by_id(budget_id: str, category_id: str, month: str = "current")` - Returns specific category's monthly budget data

## Design Principles

### Pagination

**IMPORTANT**: All listing endpoints should implement pagination to handle large datasets efficiently. When adding new listing tools, always include pagination parameters (`limit`, `offset`, `include_*` flags).

The `list_accounts`, `list_categories`, and `get_budget_month` tools return paginated results with this structure:

```json
{
  "accounts": [...],  // or "categories": [...]
  "pagination": {
    "total_count": 150,
    "limit": 50,
    "offset": 0,
    "has_more": true,
    "next_offset": 50,
    "returned_count": 50
  }
}
```

## Architecture Notes

- Uses FastMCP's `@mcp.tool()` decorator to expose YNAB API functions
- Implements proper error handling for missing authentication tokens
- Returns structured JSON data from YNAB API with comprehensive account and budget information
- Uses context managers for proper YNAB client lifecycle management
- Handles YNAB's milliunit format (1000 milliunits = 1 currency unit) by providing both raw milliunits and converted currency amounts

## Memories

- Always add good docstring context on any tool parameters, as they influence how LLM agents know which parameters to pass and how.