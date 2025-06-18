# you-need-an-mcp

An MCP server providing LLMs access to a YNAB budget.

## Setup

### 1. Install Dependencies

```bash
uv sync
```

### 2. Get YNAB Access Token

To use this MCP server, you need a YNAB Personal Access Token:

1. Log into your YNAB account at https://app.youneedabudget.com
2. Go to **Account Settings** (click your email in the top right corner)
3. Click on **Developer Settings** in the left sidebar
4. Click **New Token**
5. Enter a token name (e.g., "MCP Server")
6. Click **Generate**
7. Copy the generated token (you won't be able to see it again)

### 3. Set Environment Variables

```bash
export YNAB_ACCESS_TOKEN=your_token_here
```

Optionally, set a default budget ID to avoid having to specify it in every call:

```bash
export YNAB_DEFAULT_BUDGET=your_budget_id_here
```

### 4. Run the Server

```bash
uv run python server.py
```

## Available Tools

- `list_budgets()` - Returns all your YNAB budgets
- `list_accounts(budget_id=None, limit=100, offset=0, include_closed=False)` - Returns accounts with pagination and filtering
- `list_categories(budget_id=None, limit=50, offset=0, include_hidden=False)` - Returns categories with pagination and filtering
- `list_category_groups(budget_id=None)` - Returns category groups with totals (lighter weight overview)

### Pagination

The `list_accounts` and `list_categories` tools support pagination. Use the `offset` parameter to get subsequent pages:
- First page: `list_categories(limit=50, offset=0)`
- Second page: `list_categories(limit=50, offset=50)`
- Check `pagination.has_more` to see if there are more results

## Security Note

Keep your YNAB access token secure and never commit it to version control. The token provides read access to all your budget data.
