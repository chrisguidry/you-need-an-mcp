# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with
code in this repository.

## Project Overview

This is a Python project that implements an MCP (Model Context Protocol) server
for YNAB (You Need A Budget) using FastMCP. The server provides tools to query
YNAB data including budgets, accounts, categories, payees, and transactions.

## Development Commands

### Package Management

- **Install dependencies**: `uv sync`
- **Install with dev dependencies**: `uv sync --group dev`
- **Add new dependency**: `uv add <package>`
- **Add dev dependency**: `uv add --group dev <package>`
- **Run MCP server**: `uv run fastmcp run server.py:mcp`

### Testing

The project includes a comprehensive test suite with **100% code coverage** that
mocks all YNAB API calls.

**Basic Commands:**

- **Run all tests**: `uv run pytest`
- **Run with coverage report**: `uv run pytest --cov=server --cov=models --cov-report=term-missing`
- **Run tests in parallel**: `uv run pytest -n auto`
- **Run verbose output**: `uv run pytest -v`

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
- `list_accounts(budget_id: str = None, limit: int = 100, offset: int = 0)` - Returns active accounts with pagination. Closed accounts are automatically excluded.
- `list_categories(budget_id: str = None, limit: int = 50, offset: int = 0)` - Returns active/visible category structure only with pagination. Hidden and deleted categories are automatically excluded. No budget amounts included.
- `list_category_groups(budget_id: str = None)` - Returns active category groups with totals (lighter weight alternative to full categories). Deleted groups are automatically excluded.
- `get_budget_month(budget_id: str = None, month: str = "current", limit: int = 50, offset: int = 0)` - Returns monthly budget data including budgeted amounts, activity, and balances for active categories with pagination. Hidden and deleted categories are automatically excluded.
- `get_month_category_by_id(budget_id: str, category_id: str, month: str = "current")` - Returns specific category's monthly budget data
- `list_transactions(account_id: str = None, category_id: str = None, payee_id: str = None, since_date: date = None, min_amount: Decimal = None, max_amount: Decimal = None, limit: int = 25, offset: int = 0, budget_id: str = None)` - Returns transactions with powerful filtering options for financial analysis. Supports filtering by account, category, payee, date range, and amount range. Returns full transaction details including splits/subtransactions. Default limit reduced to 25 to avoid token limits.
- `list_payees(limit: int = 50, offset: int = 0, budget_id: str = None)` - Returns active payees (merchants, people, companies) with pagination. Deleted payees are automatically excluded. Useful for finding payee IDs for transaction filtering or analyzing spending patterns.
- `find_payee(name_search: str, limit: int = 10, budget_id: str = None)` - Find active payees by searching for name substrings (case-insensitive). Deleted payees are automatically excluded. Much more efficient than paginating through all payees when you know part of the payee name. Perfect for queries like "Find Amazon payee ID" or "Show me all Starbucks locations".

## Design Principles

### Pagination

**IMPORTANT**: All listing endpoints should implement pagination to handle large datasets efficiently. When adding new listing tools, always include pagination parameters (`limit`, `offset`).

The `list_accounts`, `list_categories`, `get_budget_month`, `list_transactions`, and `list_payees` tools return paginated results with this structure:

```json
{
  "accounts": [...],  // or "categories": [...] or "transactions": [...] or "payees": [...]
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

### Data Filtering

**IMPORTANT**: All MCP tools automatically exclude deleted, hidden, and closed data from YNAB. This provides a clean, user-friendly interface that only shows active/relevant data. Users who need to access deleted data should use the YNAB web application directly, as this is considered an advanced administrative use case not suitable for general MCP interactions.

## Styleguide

- 100% code coverage - complete coverage of all modules, including the test modules is required
- Always add good docstring context on any tool parameters, as they influence how LLM agents know which parameters to pass and how.
- All new features MUST have 100% test coverage.
- When designing tests for tools and how they use the YNAB API, ALWAYS use the real YNAB models and only mock the API calls.
- Use the FastMCP testing pattern with direct client-server testing
