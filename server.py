import os
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

import ynab
from fastmcp import FastMCP

from models import (
    Account,
    AccountsResponse,
    Budget,
    CurrencyFormat,
    PaginationInfo,
    Payee,
    PayeesResponse,
    Subtransaction,
    Transaction,
    TransactionsResponse,
)

mcp: FastMCP[None] = FastMCP(
    name="YNAB",
    instructions="""
    Gives you access to a user's YNAB account, including budgets, accounts, and
    transactions.  If a user is ever asking about budgeting, their personal finances,
    banking, saving, or investing, their YNAB budget is very relevant to them.  When
    they don't specify a budget, you can skip looking up or passing a budget ID because
    they are probably talking about their default/only budget.  When the user asks about
    budget categories and "how much is left", they are talking about the current month.
    """,
)


def get_ynab_client() -> ynab.ApiClient:
    """Get authenticated YNAB client"""
    access_token = os.getenv("YNAB_ACCESS_TOKEN")
    if not access_token:
        raise ValueError("YNAB_ACCESS_TOKEN environment variable is required")

    configuration = ynab.Configuration(access_token=access_token)
    return ynab.ApiClient(configuration)


def milliunits_to_currency(milliunits: int, decimal_digits: int = 2) -> Decimal:
    """Convert YNAB milliunits to currency amount using Decimal for precision

    YNAB uses milliunits where 1000 milliunits = 1 currency unit
    """
    return Decimal(milliunits) / Decimal("1000")


def get_default_budget_id() -> str:
    """Get default budget ID from environment variable or raise error"""
    budget_id = os.getenv("YNAB_DEFAULT_BUDGET")
    if not budget_id:
        raise ValueError(
            "budget_id is required or set YNAB_DEFAULT_BUDGET environment variable"
        )
    return budget_id


def budget_id_or_default(budget_id: str | None) -> str:
    """Return the provided budget_id or get the default budget ID if None"""
    if budget_id is None:
        return get_default_budget_id()
    return budget_id


def convert_transaction_to_model(txn: Any) -> Transaction:
    """Convert YNAB transaction object to our Transaction model.

    Handles both TransactionDetail and HybridTransaction types that come from
    different endpoints.
    """
    # Convert amount from milliunits
    amount = milliunits_to_currency(txn.amount)

    # Handle subtransactions if present and available
    subtransactions = None
    if hasattr(txn, "subtransactions") and txn.subtransactions:
        subtransactions = []
        for sub in txn.subtransactions:
            if not sub.deleted:
                subtransactions.append(
                    Subtransaction(
                        id=sub.id,
                        transaction_id=sub.transaction_id,
                        amount=milliunits_to_currency(sub.amount),
                        memo=sub.memo,
                        payee_id=sub.payee_id,
                        payee_name=sub.payee_name,
                        category_id=sub.category_id,
                        category_name=sub.category_name,
                        transfer_account_id=sub.transfer_account_id,
                        transfer_transaction_id=sub.transfer_transaction_id,
                        deleted=sub.deleted,
                        amount_milliunits=sub.amount,
                    )
                )

    return Transaction(
        id=txn.id,
        date=txn.var_date,
        amount=amount,
        memo=txn.memo,
        cleared=txn.cleared,
        approved=txn.approved,
        flag_color=txn.flag_color,
        account_id=txn.account_id,
        account_name=getattr(txn, "account_name", None),
        payee_id=txn.payee_id,
        payee_name=getattr(txn, "payee_name", None),
        category_id=txn.category_id,
        category_name=getattr(txn, "category_name", None),
        transfer_account_id=txn.transfer_account_id,
        transfer_transaction_id=txn.transfer_transaction_id,
        matched_transaction_id=txn.matched_transaction_id,
        import_id=txn.import_id,
        import_payee_name=txn.import_payee_name,
        import_payee_name_original=txn.import_payee_name_original,
        debt_transaction_type=txn.debt_transaction_type,
        deleted=txn.deleted,
        amount_milliunits=txn.amount,
        subtransactions=subtransactions,
    )


def convert_month_to_date(
    month: date | Literal["current", "last", "next"],
) -> date:
    """Convert month parameter to appropriate date object for YNAB API.

    Args:
        month: Month in ISO format (date object), or "current", "last", "next" literals

    Returns:
        date object representing the first day of the specified month:
        - "current": first day of current month
        - "last": first day of previous month
        - "next": first day of next month
        - date object unchanged if already a date
    """
    if isinstance(month, date):
        return month

    # Get current date for calculations
    today = datetime.now().date()
    current_year = today.year
    current_month = today.month

    if month == "current":
        return date(current_year, current_month, 1)

    elif month == "last":
        # Previous month
        if current_month == 1:
            # January -> December of previous year
            return date(current_year - 1, 12, 1)
        else:
            return date(current_year, current_month - 1, 1)

    elif month == "next":
        # Next month
        if current_month == 12:
            # December -> January of next year
            return date(current_year + 1, 1, 1)
        else:
            return date(current_year, current_month + 1, 1)

    # This shouldn't happen with proper typing, but just in case
    raise ValueError(f"Invalid month value: {month}")


@mcp.tool()
def list_budgets() -> list[Budget]:
    """List all budgets from YNAB with metadata and currency formatting information."""
    with get_ynab_client() as api_client:
        budgets_api = ynab.BudgetsApi(api_client)
        budgets_response = budgets_api.get_budgets()

        budgets = []
        for budget in budgets_response.data.budgets:
            currency_format = None
            if budget.currency_format:
                currency_format = CurrencyFormat(
                    iso_code=budget.currency_format.iso_code,
                    example_format=budget.currency_format.example_format,
                    decimal_digits=budget.currency_format.decimal_digits,
                    decimal_separator=budget.currency_format.decimal_separator,
                    symbol_first=budget.currency_format.symbol_first,
                    group_separator=budget.currency_format.group_separator,
                    currency_symbol=budget.currency_format.currency_symbol,
                    display_symbol=budget.currency_format.display_symbol,
                )

            budgets.append(
                Budget(
                    id=budget.id,
                    name=budget.name,
                    last_modified_on=budget.last_modified_on,
                    first_month=budget.first_month,
                    last_month=budget.last_month,
                    currency_format=currency_format,
                )
            )

        return budgets


@mcp.tool()
def list_accounts(
    limit: int = 100,
    offset: int = 0,
    budget_id: str | None = None,
) -> AccountsResponse:
    """List accounts for a specific budget with pagination.

    IMPORTANT: If the user is asking about their accounts in general (not a
    specific budget), you can omit the budget_id parameter entirely. Do NOT call
    list_budgets first - just call this tool without budget_id and it will use their
    default budget automatically.

    Only returns open/active accounts. Closed accounts are excluded automatically.

    Args:
        limit: Maximum number of accounts to return (default 100)
        offset: Number of accounts to skip (default 0)
        budget_id: Budget ID (optional - omit to use default budget
        automatically)

    Returns:
        AccountsResponse with accounts list and pagination information
    """
    budget_id = budget_id_or_default(budget_id)

    with get_ynab_client() as api_client:
        accounts_api = ynab.AccountsApi(api_client)
        accounts_response = accounts_api.get_accounts(budget_id)

        # Filter accounts - exclude closed accounts
        all_accounts = []
        for account in accounts_response.data.accounts:
            # Skip closed accounts
            if account.closed:
                continue

            all_accounts.append(
                Account(
                    id=account.id,
                    name=account.name,
                    type=account.type,
                    on_budget=account.on_budget,
                    closed=account.closed,
                    note=account.note,
                    balance=milliunits_to_currency(account.balance),
                    cleared_balance=milliunits_to_currency(account.cleared_balance),
                    uncleared_balance=milliunits_to_currency(account.uncleared_balance),
                    transfer_payee_id=account.transfer_payee_id,
                    direct_import_linked=account.direct_import_linked,
                    direct_import_in_error=account.direct_import_in_error,
                    last_reconciled_at=account.last_reconciled_at,
                    debt_original_balance=milliunits_to_currency(
                        account.debt_original_balance
                    )
                    if account.debt_original_balance is not None
                    else None,
                )
            )

        # Apply pagination
        total_count = len(all_accounts)
        start_index = offset
        end_index = min(offset + limit, total_count)
        accounts_page = all_accounts[start_index:end_index]

        has_more = end_index < total_count
        next_offset = end_index if has_more else None

        pagination = PaginationInfo(
            total_count=total_count,
            limit=limit,
            offset=offset,
            has_more=has_more,
            next_offset=next_offset,
            returned_count=len(accounts_page),
        )

        return AccountsResponse(accounts=accounts_page, pagination=pagination)


@mcp.tool()
def list_categories(
    limit: int = 50,
    offset: int = 0,
    budget_id: str | None = None,
) -> dict[str, Any]:
    """List categories for a specific budget with pagination.

    IMPORTANT: If the user is asking about their categories in general (not a specific
    budget), you can omit the budget_id parameter entirely. Do NOT call list_budgets
    first - just call this tool without budget_id and it will use their default budget
    automatically.

    Only returns active/visible categories. Hidden and deleted categories are excluded
    automatically.

    Args:
        limit: Maximum number of categories to return (default 50)
        offset: Number of categories to skip (default 0)
        budget_id: Budget ID (optional - omit to use default budget
        automatically)

    Returns:
        Dict with 'categories', 'total_count', 'has_more', 'next_offset' fields
    """
    budget_id = budget_id_or_default(budget_id)

    with get_ynab_client() as api_client:
        categories_api = ynab.CategoriesApi(api_client)
        categories_response = categories_api.get_categories(budget_id)

        # First, collect all eligible categories - exclude hidden and deleted
        all_categories = []
        for category_group in categories_response.data.category_groups:
            for category in category_group.categories:
                # Skip hidden categories
                if category.hidden:
                    continue

                # Skip deleted categories
                if category.deleted:
                    continue

                all_categories.append(
                    {
                        "id": category.id,
                        "name": category.name,
                        "category_group_id": category.category_group_id,
                        "category_group_name": category_group.name,
                        "hidden": category.hidden,
                        "note": category.note,
                        "budgeted": milliunits_to_currency(category.budgeted),
                        "activity": milliunits_to_currency(category.activity),
                        "balance": milliunits_to_currency(category.balance),
                        "goal_type": category.goal_type,
                        "goal_target": milliunits_to_currency(category.goal_target)
                        if category.goal_target is not None
                        else None,
                        "goal_percentage_complete": category.goal_percentage_complete,
                        "goal_under_funded": milliunits_to_currency(
                            category.goal_under_funded
                        )
                        if category.goal_under_funded is not None
                        else None,
                    }
                )

        # Apply pagination
        total_count = len(all_categories)
        start_index = offset
        end_index = min(offset + limit, total_count)
        categories_page = all_categories[start_index:end_index]

        has_more = end_index < total_count
        next_offset = end_index if has_more else None

        return {
            "categories": categories_page,
            "pagination": {
                "total_count": total_count,
                "limit": limit,
                "offset": offset,
                "has_more": has_more,
                "next_offset": next_offset,
                "returned_count": len(categories_page),
            },
        }


@mcp.tool()
def list_category_groups(budget_id: str | None = None) -> list[dict[str, Any]]:
    """List category groups for a specific budget (lighter weight than full categories).

    IMPORTANT: If the user is asking about their category groups in general (not a
    specific budget), you can omit the budget_id parameter entirely. Do NOT call
    list_budgets first - just call this tool without budget_id and it will use their
    default budget automatically.

    Args:
        budget_id: Budget ID (optional - omit to use default budget
        automatically)
    """
    budget_id = budget_id_or_default(budget_id)

    with get_ynab_client() as api_client:
        categories_api = ynab.CategoriesApi(api_client)
        categories_response = categories_api.get_categories(budget_id)

        groups = []
        for category_group in categories_response.data.category_groups:
            if category_group.deleted:
                continue

            # Calculate totals for the group (exclude deleted and hidden categories)
            total_budgeted = sum(
                cat.budgeted or 0
                for cat in category_group.categories
                if not cat.deleted and not cat.hidden
            )
            total_activity = sum(
                cat.activity or 0
                for cat in category_group.categories
                if not cat.deleted and not cat.hidden
            )
            total_balance = sum(
                cat.balance or 0
                for cat in category_group.categories
                if not cat.deleted and not cat.hidden
            )

            groups.append(
                {
                    "id": category_group.id,
                    "name": category_group.name,
                    "hidden": category_group.hidden,
                    "category_count": len(
                        [
                            cat
                            for cat in category_group.categories
                            if not cat.deleted and not cat.hidden
                        ]
                    ),
                    "total_budgeted": milliunits_to_currency(total_budgeted),
                    "total_activity": milliunits_to_currency(total_activity),
                    "total_balance": milliunits_to_currency(total_balance),
                }
            )

        return groups


@mcp.tool()
def get_budget_month(
    month: date | Literal["current", "last", "next"] = "current",
    limit: int = 50,
    offset: int = 0,
    budget_id: str | None = None,
) -> dict[str, Any]:
    """Get budget data for a specific month including category budgets, activity, and
    balances with pagination.

    IMPORTANT: If the user is asking about their budget in general (not a specific
    budget), you can omit the budget_id parameter entirely. Do NOT call list_budgets
    first - just call this tool without budget_id and it will use their default budget
    automatically.

    Only returns active/visible categories. Hidden and deleted categories are excluded
    automatically.

    Args:
        month: Month specifier. Use "current" for current month, "last" for previous
               month, "next" for next month, or a specific date object for an exact
               month (default "current")
        limit: Maximum number of categories to return (default 50)
        offset: Number of categories to skip for pagination (default 0)
        budget_id: Budget ID (optional - omit to use default budget
        automatically)

    Returns:
        Dict with month info, categories with budgeted/activity/balance data, and
        pagination info
    """
    budget_id = budget_id_or_default(budget_id)

    with get_ynab_client() as api_client:
        months_api = ynab.MonthsApi(api_client)
        converted_month = convert_month_to_date(month)
        month_response = months_api.get_budget_month(budget_id, converted_month)

        month_data = month_response.data.month
        all_categories = []

        for category in month_data.categories:
            if category.deleted:
                continue

            # Skip hidden categories
            if category.hidden:
                continue

            all_categories.append(
                {
                    "id": category.id,
                    "name": category.name,
                    "category_group_id": category.category_group_id,
                    "hidden": category.hidden,
                    "note": category.note,
                    "budgeted": milliunits_to_currency(category.budgeted),
                    "activity": milliunits_to_currency(category.activity),
                    "balance": milliunits_to_currency(category.balance),
                    "goal_type": category.goal_type,
                    "goal_target": milliunits_to_currency(category.goal_target)
                    if category.goal_target is not None
                    else None,
                    "goal_percentage_complete": category.goal_percentage_complete,
                    "goal_under_funded": milliunits_to_currency(
                        category.goal_under_funded
                    )
                    if category.goal_under_funded is not None
                    else None,
                    "budgeted_milliunits": category.budgeted,
                    "activity_milliunits": category.activity,
                    "balance_milliunits": category.balance,
                }
            )

        # Apply pagination
        total_count = len(all_categories)
        start_index = offset
        end_index = min(offset + limit, total_count)
        categories_page = all_categories[start_index:end_index]

        has_more = end_index < total_count
        next_offset = end_index if has_more else None

        return {
            "month": month_data.month,
            "note": month_data.note,
            "income": milliunits_to_currency(month_data.income),
            "budgeted": milliunits_to_currency(month_data.budgeted),
            "activity": milliunits_to_currency(month_data.activity),
            "to_be_budgeted": milliunits_to_currency(month_data.to_be_budgeted),
            "age_of_money": month_data.age_of_money,
            "categories": categories_page,
            "income_milliunits": month_data.income,
            "budgeted_milliunits": month_data.budgeted,
            "activity_milliunits": month_data.activity,
            "to_be_budgeted_milliunits": month_data.to_be_budgeted,
            "pagination": {
                "total_count": total_count,
                "limit": limit,
                "offset": offset,
                "has_more": has_more,
                "next_offset": next_offset,
                "returned_count": len(categories_page),
            },
        }


@mcp.tool()
def get_month_category_by_id(
    category_id: str,
    month: date | Literal["current", "last", "next"] = "current",
    budget_id: str | None = None,
) -> dict[str, Any]:
    """Get a specific category's data for a specific month.

    IMPORTANT: If the user is asking about a category in their general budget (not a
    specific budget), you can omit the budget_id parameter entirely. Do NOT call
    list_budgets first - just call this tool without budget_id and it will use their
    default budget automatically.

    Args:
        category_id: Category ID (required)
        month: Month specifier. Use "current" for current month, "last" for previous
               month, "next" for next month, or a specific date object for an exact
               month (default "current")
        budget_id: Budget ID (optional - omit to use default budget
        automatically)

    Returns:
        Dict with category budget data for the specified month
    """
    budget_id = budget_id_or_default(budget_id)

    with get_ynab_client() as api_client:
        categories_api = ynab.CategoriesApi(api_client)
        converted_month = convert_month_to_date(month)
        category_response = categories_api.get_month_category_by_id(
            budget_id, converted_month, category_id
        )

        category = category_response.data.category

        return {
            "id": category.id,
            "name": category.name,
            "category_group_id": category.category_group_id,
            "hidden": category.hidden,
            "note": category.note,
            "budgeted": milliunits_to_currency(category.budgeted),
            "activity": milliunits_to_currency(category.activity),
            "balance": milliunits_to_currency(category.balance),
            "goal_type": category.goal_type,
            "goal_target": milliunits_to_currency(category.goal_target)
            if category.goal_target is not None
            else None,
            "goal_percentage_complete": category.goal_percentage_complete,
            "goal_under_funded": milliunits_to_currency(category.goal_under_funded)
            if category.goal_under_funded is not None
            else None,
            "budgeted_milliunits": category.budgeted,
            "activity_milliunits": category.activity,
            "balance_milliunits": category.balance,
        }


@mcp.tool()
def list_transactions(
    account_id: str | None = None,
    category_id: str | None = None,
    payee_id: str | None = None,
    since_date: date | None = None,
    min_amount: Decimal | None = None,
    max_amount: Decimal | None = None,
    limit: int = 25,
    offset: int = 0,
    budget_id: str | None = None,
) -> TransactionsResponse:
    """List transactions with powerful filtering options for financial analysis.

    IMPORTANT: If the user is asking about a category in their general budget (not a
    specific budget), you can omit the budget_id parameter entirely. Do NOT call
    list_budgets first - just call this tool without budget_id and it will use their
    default budget automatically.

    This tool supports various filters that can be combined:
    - Filter by account to see transactions for a specific account
    - Filter by category to analyze spending in a category (e.g., "Dining Out")
    - Filter by payee to see all transactions with a specific merchant (e.g., "Amazon")
    - Filter by date range using since_date
    - Filter by amount range using min_amount and/or max_amount

    Example queries this tool can answer:
    - "Show me all transactions over $50 in Dining Out this year" (use category_id,
      min_amount, since_date)
    - "How much have I spent at Amazon this month" (use payee_id, since_date)
    - "List recent transactions in my checking account" (use account_id)

    Args:
        account_id: Filter by specific account (optional)
        category_id: Filter by specific category (optional)
        payee_id: Filter by specific payee (optional)
        since_date: Only show transactions on or after this date (optional)
        min_amount: Only show transactions with amount >= this value (optional,
                    negative for outflows)
        max_amount: Only show transactions with amount <= this value (optional,
                    negative for outflows)
        limit: Maximum number of transactions to return (default 25)
        offset: Number of transactions to skip for pagination (default 0)
        budget_id: Budget ID (optional - omit to use default budget
        automatically)

    Returns:
        TransactionsResponse with filtered transactions and pagination info
    """
    budget_id = budget_id_or_default(budget_id)

    with get_ynab_client() as api_client:
        transactions_api = ynab.TransactionsApi(api_client)

        # Determine which API method to use based on filters
        response: ynab.TransactionsResponse | ynab.HybridTransactionsResponse
        if account_id:
            # Use account-specific endpoint if account filter is provided
            response = transactions_api.get_transactions_by_account(
                budget_id,
                account_id,
                since_date=since_date,
                type=None,  # Include all transaction types
            )
        elif category_id:
            # Use category-specific endpoint if category filter is provided
            response = transactions_api.get_transactions_by_category(
                budget_id, category_id, since_date=since_date, type=None
            )
        elif payee_id:
            # Use payee-specific endpoint if payee filter is provided
            response = transactions_api.get_transactions_by_payee(
                budget_id, payee_id, since_date=since_date, type=None
            )
        else:
            # Use general transactions endpoint
            response = transactions_api.get_transactions(
                budget_id, since_date=since_date, type=None
            )

        # Convert and filter transactions
        all_transactions = []
        for txn in response.data.transactions:
            # Skip deleted transactions
            if txn.deleted:
                continue

            # Convert amount from milliunits
            amount = milliunits_to_currency(txn.amount)

            # Apply amount filters if specified
            if min_amount is not None and amount < min_amount:
                continue
            if max_amount is not None and amount > max_amount:
                continue

            # Use helper function to convert transaction
            all_transactions.append(convert_transaction_to_model(txn))

        # Sort by date descending (most recent first)
        all_transactions.sort(key=lambda t: t.date, reverse=True)

        # Apply pagination
        total_count = len(all_transactions)
        start_index = offset
        end_index = min(offset + limit, total_count)
        transactions_page = all_transactions[start_index:end_index]

        has_more = end_index < total_count
        next_offset = end_index if has_more else None

        pagination = PaginationInfo(
            total_count=total_count,
            limit=limit,
            offset=offset,
            has_more=has_more,
            next_offset=next_offset,
            returned_count=len(transactions_page),
        )

        return TransactionsResponse(
            transactions=transactions_page, pagination=pagination
        )


@mcp.tool()
def list_payees(
    limit: int = 50,
    offset: int = 0,
    budget_id: str | None = None,
) -> PayeesResponse:
    """List payees for a specific budget with pagination.

    IMPORTANT: If the user is asking about a category in their general budget (not a
    specific budget), you can omit the budget_id parameter entirely. Do NOT call
    list_budgets first - just call this tool without budget_id and it will use their
    default budget automatically.

    Payees are the entities you pay money to (merchants, people, companies, etc.).
    This tool helps you find payee IDs for filtering transactions or analyzing spending
    patterns. Only returns active payees. Deleted payees are excluded automatically.

    Example queries this tool can answer:
    - "List all my payees"
    - "Find the payee ID for Amazon"
    - "Show me all merchants I've paid"

    Args:
        limit: Maximum number of payees to return (default 50)
        offset: Number of payees to skip for pagination (default 0)
        budget_id: Budget ID (optional - omit to use default budget
        automatically)

    Returns:
        PayeesResponse with payees list and pagination information
    """
    budget_id = budget_id_or_default(budget_id)

    with get_ynab_client() as api_client:
        payees_api = ynab.PayeesApi(api_client)
        payees_response = payees_api.get_payees(budget_id)

        # Filter payees - exclude deleted payees
        all_payees = []
        for payee in payees_response.data.payees:
            # Skip deleted payees
            if payee.deleted:
                continue

            all_payees.append(
                Payee(
                    id=payee.id,
                    name=payee.name,
                    transfer_account_id=payee.transfer_account_id,
                    deleted=payee.deleted,
                )
            )

        # Sort by name for easier browsing
        all_payees.sort(key=lambda p: p.name.lower())

        # Apply pagination
        total_count = len(all_payees)
        start_index = offset
        end_index = min(offset + limit, total_count)
        payees_page = all_payees[start_index:end_index]

        has_more = end_index < total_count
        next_offset = end_index if has_more else None

        pagination = PaginationInfo(
            total_count=total_count,
            limit=limit,
            offset=offset,
            has_more=has_more,
            next_offset=next_offset,
            returned_count=len(payees_page),
        )

        return PayeesResponse(payees=payees_page, pagination=pagination)


@mcp.tool()
def find_payee(
    name_search: str,
    limit: int = 10,
    budget_id: str | None = None,
) -> PayeesResponse:
    """Find payees by searching for name substrings (case-insensitive).

    IMPORTANT: If the user is asking about a category in their general budget (not a
    specific budget), you can omit the budget_id parameter entirely. Do NOT call
    list_budgets first - just call this tool without budget_id and it will use their
    default budget automatically.

    This tool is perfect for finding specific payees when you know part of their name.
    Much more efficient than paginating through all payees with list_payees.
    Only returns active payees. Deleted payees are excluded automatically.

    Example queries this tool can answer:
    - "Find Amazon payee ID" (use name_search="amazon")
    - "Show me all Starbucks locations" (use name_search="starbucks")
    - "Find payees with 'grocery' in the name" (use name_search="grocery")

    Args:
        name_search: Search term to match against payee names (case-insensitive
                     substring match)
        limit: Maximum number of matching payees to return (default 10)
        budget_id: Budget ID (optional - omit to use default budget
        automatically)

    Returns:
        PayeesResponse with matching payees and pagination information
    """
    budget_id = budget_id_or_default(budget_id)

    with get_ynab_client() as api_client:
        payees_api = ynab.PayeesApi(api_client)
        payees_response = payees_api.get_payees(budget_id)

        # Filter payees by name search and deleted status
        search_term = name_search.lower().strip()
        matching_payees = []

        for payee in payees_response.data.payees:
            # Skip deleted payees
            if payee.deleted:
                continue

            # Check if search term is in payee name (case-insensitive)
            if search_term in payee.name.lower():
                matching_payees.append(
                    Payee(
                        id=payee.id,
                        name=payee.name,
                        transfer_account_id=payee.transfer_account_id,
                        deleted=payee.deleted,
                    )
                )

        # Sort by name for easier browsing
        matching_payees.sort(key=lambda p: p.name.lower())

        # Apply limit (no offset since this is a search, not pagination)
        limited_payees = matching_payees[:limit]

        # Create pagination info showing search results
        total_count = len(matching_payees)
        has_more = len(matching_payees) > limit

        pagination = PaginationInfo(
            total_count=total_count,
            limit=limit,
            offset=0,
            has_more=has_more,
            next_offset=None,  # Search doesn't support offset-based pagination
            returned_count=len(limited_payees),
        )

        return PayeesResponse(payees=limited_payees, pagination=pagination)
