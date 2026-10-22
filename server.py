"""
The YNAB MCP server: one FastMCP server with every domain's tools.

Set YNAB_READ_ONLY to any non-empty value to serve only the tools that read the
plan.  The write tools are then not listed and cannot be called.
"""

import logging
import os

from fastmcp import FastMCP
from fastmcp.server.transforms.visibility import Visibility

import accounts
import assignments
import categories
import months
import payees
import plan
import scheduled_entry
import scheduled_transactions
import transaction_entry
import transactions
from effects import WRITE
from ynab_errors import YNABErrorMiddleware

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

INSTRUCTIONS = """
Gives you access to the user's YNAB plan (YNAB used to call plans "budgets"):
accounts, categories, transactions, scheduled transactions, and the money
assigned to each category every month.  If the user asks about budgeting, their
personal finances, banking, saving, or investing, their YNAB plan is relevant.

When the user asks about categories and "how much is left", they mean the
current month's available amount.

Categories belong to category groups, which matter to the user.  Show them in
that hierarchy, using category_group_name.

All amounts are in the plan's currency units, not YNAB's milliunits.  Spending
is negative and income is positive.

The server works on one plan, set by the YNAB_PLAN environment variable.

Before you change the plan, say what you will change.  After a change, report
what changed, using the before and after amounts the tools return.
"""


def read_only() -> bool:
    """Whether this server should serve only the tools that read the plan."""
    return bool(os.environ.get("YNAB_READ_ONLY"))


mcp: FastMCP[None] = FastMCP(
    name="YNAB",
    instructions=INSTRUCTIONS,
    middleware=[YNABErrorMiddleware()],
    mask_error_details=True,
    tools=[
        *plan.TOOLS,
        *months.TOOLS,
        *accounts.TOOLS,
        *categories.TOOLS,
        *assignments.TOOLS,
        *payees.TOOLS,
        *transactions.TOOLS,
        *transaction_entry.TOOLS,
        *scheduled_transactions.TOOLS,
        *scheduled_entry.TOOLS,
    ],
    transforms=[Visibility(False, tags={WRITE})] if read_only() else [],
)


if __name__ == "__main__":
    mcp.run()
