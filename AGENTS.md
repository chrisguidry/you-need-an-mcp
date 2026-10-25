# CLAUDE.md

## Project Overview

MCP (Model Context Protocol) server for YNAB (You Need A Budget) using FastMCP. Provides structured access to YNAB financial data.

## Essential Commands

```bash
# Development
uv sync --group dev        # Install all dependencies
uv run pytest               # Run tests with coverage (100% required)
fastmcp run server.py:mcp  # Run MCP server

# Authentication (required)
export YNAB_ACCESS_TOKEN=your_token_here
export YNAB_PLAN=your_plan_id_here  # Required
export YNAB_READ_ONLY=1  # Optional: serve only the read tools
```

## Critical Design Principles

1. **100% test coverage is mandatory** - No exceptions. All new code must have complete coverage.
2. **All listing tools must implement pagination** - Use `limit` and `offset` parameters.
3. **Automatically filter out deleted/hidden/closed data** - Only show active, relevant data.
4. **Use real YNAB SDK models in tests** - Mock only the API calls, not the data structures.
5. **Handle milliunits properly** - 1000 milliunits = 1 currency unit.
6. **Try to avoid using abbreviations in names**

## Product Philosophy

- **Household finance assistant** - Help heads of household be more effective with YNAB
- **Insights and notifications** - Surface important financial patterns and alerts
- **Safe changes** - Every write tool says what it does through MCP annotations, reports what it changed, and can be switched off with `YNAB_READ_ONLY`
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
- Prefer not to use test classes, just simple test functions. Test organization should come through new files

## Architecture

Modules are organized by domain.  Each domain module holds its Pydantic
models, its tools, and the YNAB calls they make, and exports its tools as
`TOOLS`.

- `server.py` - The FastMCP server: instructions, middleware, the tools of every domain, and read-only mode
- `plan.py`, `months.py`, `accounts.py`, `categories.py`, `assignments.py`, `payees.py`, `transactions.py`, `transaction_entry.py`, `scheduled_transactions.py`, `scheduled_entry.py` - The domains
- `repository.py` - The in-memory mirror of accounts, payees, categories, and transactions, kept current with delta sync.  Tools receive it as `Shared(plan_repository)`; a write calls `mark_stale()` so the next read syncs first
- `effects.py` - The tags and MCP annotations that say what each tool does to the plan
- `ynab_errors.py` - Middleware that passes YNAB's error detail to the client
- `currency.py`, `pagination.py`, `recurrence.py` - Milliunit conversion, paging, and scheduled dates
- `DESIGN.md` - Detailed use cases and design philosophy

Every tool declares `title`, `tags` (its domain plus `read` or `write`), and `annotations` from `effects.py`.

Tests mock the repository with the `mock_repository` fixture and the YNAB API classes with fixtures like `transactions_api`, and return real SDK models.
