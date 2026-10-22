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

Set the budget ID used by all tools (required):

```bash
export YNAB_BUDGET=your_budget_id_here
```

### 4. Run the Server

```bash
uv run python server.py
```

### Windows / Managed Machines

If `uvx` or `you-need-an-mcp.exe` fails with `Access is denied (os error 5)`,
endpoint security may be blocking the generated console-script executable.
Launch the server through the environment's `python.exe` instead.

For a source checkout, after installing dependencies with `uv sync --locked`,
run these PowerShell commands from the repository directory:

```powershell
$env:YNAB_ACCESS_TOKEN = "<your-token>"
$env:YNAB_BUDGET = "<your-budget-id>"
& .\.venv\Scripts\python.exe -m server
```

For a persistent tool installation of a version with module-launch support
(`uv tool install git+https://github.com/chrisguidry/you-need-an-mcp.git`),
locate the interpreter using `uv tool dir` rather than assuming a fixed
installation path:

```powershell
$toolDirectory = uv tool dir
$python = Join-Path $toolDirectory "you-need-an-mcp\Scripts\python.exe"
& $python -I -m server
```

To register that installed environment with Claude Code, replace the placeholders
with your configuration:

```powershell
claude mcp add ynab --scope user `
  -e "YNAB_ACCESS_TOKEN=<your-token>" -e "YNAB_BUDGET=<your-budget-id>" `
  -- $python -I -m server
```

The module launch runs the same MCP server as the console-script entry point.
For installed tools, `-I` prevents an unrelated `server.py` in the current
directory from shadowing the installed module.
It requires an installed environment and permission to execute its interpreter.
If endpoint security also prevents installation or interpreter execution, use
your organization's approved setup process.

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
