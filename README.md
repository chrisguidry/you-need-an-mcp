# you-need-an-mcp

An MCP server that lets an LLM read and manage a YNAB plan.  It can answer
questions about accounts, categories, spending, and scheduled transactions, and
it can enter and edit transactions, assign and move money, and manage scheduled
transactions.  YNAB now calls budgets "plans", and so does this server.

## Setup

### 1. Install Dependencies

```bash
uv sync
```

### 2. Get YNAB Access Token

To use this MCP server, you need a YNAB Personal Access Token:

1. Log into your YNAB account at https://app.ynab.com
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

Set the plan ID used by all tools (required).  It is the ID in the address of
your plan in YNAB's web app: `https://app.ynab.com/<plan-id>/...`.

```bash
export YNAB_PLAN=your_plan_id_here
```

To serve only the tools that read the plan, set `YNAB_READ_ONLY` to any
non-empty value.  The tools that change the plan are then not offered at all.

```bash
export YNAB_READ_ONLY=1
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
$env:YNAB_PLAN = "<your-plan-id>"
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
  -e "YNAB_ACCESS_TOKEN=<your-token>" -e "YNAB_PLAN=<your-plan-id>" `
  -- $python -I -m server
```

The module launch runs the same MCP server as the console-script entry point.
For installed tools, `-I` prevents an unrelated `server.py` in the current
directory from shadowing the installed module.
It requires an installed environment and permission to execute its interpreter.
If endpoint security also prevents installation or interpreter execution, use
your organization's approved setup process.

## Available Tools

Every tool is tagged `read` or `write`, and carries MCP annotations that tell a
client whether it only reads, adds, changes, or deletes, so the client can ask
you before a change.  All amounts are in your plan's currency, not milliunits.

### Plan and months

- `get_plan` - The plan's name, the months it covers, and its currency format
- `get_plan_month` - One month's income, assigned, activity, Ready to Assign,
  age of money, and categories
- `list_plan_months` - Every month's totals, newest first
- `get_month_category` - One category's amounts and target for a month

### Accounts

- `list_accounts` - Accounts with balances, optionally including closed ones
- `create_account` - Add an account that you track by hand

### Categories and assigning money

- `list_categories` / `list_category_groups` - Categories by group, with this
  month's assigned, activity, available, and target
- `create_category`, `update_category` - Add or change a category and its target
- `create_category_group`, `rename_category_group` - Manage category groups
- `assign_money` - Assign more to a category from Ready to Assign, or take some back
- `set_assigned` - Set exactly what a category has assigned
- `move_money` - Move assigned money from one category to another
- `list_money_movements` - The history of money assigned and moved

### Payees

- `list_payees`, `find_payee` - Browse or search payees
- `create_payee`, `rename_payee` - Manage payees

### Transactions

- `list_transactions` - Filter by account, category, payee, dates, amounts,
  unapproved or uncategorized status, and text
- `get_transaction` - One transaction, with its splits
- `create_transactions` - Enter spending, income, transfers, and splits
- `update_transactions` - Approve, categorize, and fix transactions in bulk
- `delete_transaction` - Delete a transaction
- `import_transactions` - Import new transactions from linked banks now

### Scheduled transactions

- `list_scheduled_transactions`, `get_scheduled_transaction` - Upcoming bills
  and income
- `create_scheduled_transaction`, `update_scheduled_transaction`,
  `delete_scheduled_transaction` - Manage schedules
- `enter_scheduled_transaction` - Enter a scheduled transaction now, before its
  date, and move the schedule to its next date

YNAB's API cannot create or change split scheduled transactions, and it cannot
attach receipts to transactions.

### Pagination

Every listing tool takes `limit` and `offset`.  Check `pagination.has_more`, and
raise `offset` by `limit` to get the next page.

## Security Note

Keep your YNAB access token secure and never commit it to version control.  The
token can read and change everything in your YNAB account.  Use
`YNAB_READ_ONLY` when you want the server to only read.
