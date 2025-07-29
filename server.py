import os
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

import ynab
from fastmcp import FastMCP

from models import (
    Account,
    AccountsResponse,
    Budget,
    BudgetMonth,
    CategoriesResponse,
    Category,
    CategoryGroup,
    CategoryGroupsResponse,
    PaginationInfo,
    Payee,
    PayeesResponse,
    ScheduledTransaction,
    ScheduledTransactionsResponse,
    Transaction,
    TransactionsResponse,
    milliunits_to_currency,
)

mcp = FastMCP[None](
    name="YNAB",
    instructions="""
    Gives you access to a user's YNAB account, including budgets, accounts, and
    transactions.  If a user is ever asking about budgeting, their personal finances,
    banking, saving, or investing, their YNAB budget is very relevant to them.  When
    they don't specify a budget, you can skip looking up or passing a budget ID because
    they are probably talking about their default/only budget.  When the user asks about
    budget categories and "how much is left", they are talking about the current month.

    Budget categories are grouped into category groups, which are important groupings
    to the user and should be displayed in a hierarchical manner.  Categories will have
    the category_group_name and category_group_id available.

    IMPORTANT: For any tool that accepts a budget_id parameter, if the user is asking
    about their data in general (not a specific budget), you can omit the budget_id
    parameter entirely. Do NOT call list_budgets first - just call the tool without
    budget_id and it will use their default budget automatically.
    """,
)


def get_ynab_client() -> ynab.ApiClient:
    """Get authenticated YNAB client"""
    access_token = os.getenv("YNAB_ACCESS_TOKEN")
    if not access_token:
        raise ValueError("YNAB_ACCESS_TOKEN environment variable is required")

    configuration = ynab.Configuration(access_token=access_token)
    return ynab.ApiClient(configuration)


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

        return [Budget.from_ynab(budget) for budget in budgets_response.data.budgets]


@mcp.tool()
def list_accounts(
    limit: int = 100,
    offset: int = 0,
    budget_id: str | None = None,
) -> AccountsResponse:
    """List accounts for a specific budget with pagination.

    Only returns open/active accounts. Closed accounts are excluded automatically.

    Args:
        limit: Maximum number of accounts to return (default 100)
        offset: Number of accounts to skip (default 0)
        budget_id: Budget ID (optional - omit to use default budget automatically)

    Returns:
        AccountsResponse with accounts list and pagination information
    """
    budget_id = budget_id_or_default(budget_id)

    with get_ynab_client() as api_client:
        accounts_api = ynab.AccountsApi(api_client)
        accounts_response = accounts_api.get_accounts(budget_id)

        # Filter accounts - exclude closed accounts
        all_accounts = [
            Account.from_ynab(account)
            for account in accounts_response.data.accounts
            if not account.closed
        ]

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
) -> CategoriesResponse:
    """List categories for a specific budget with pagination.

    Only returns active/visible categories. Hidden and deleted categories are excluded
    automatically.

    Args:
        limit: Maximum number of categories to return (default 50)
        offset: Number of categories to skip (default 0)
        budget_id: Budget ID (optional - omit to use default budget automatically)

    Returns:
        CategoriesResponse with categories list and pagination information
    """
    budget_id = budget_id_or_default(budget_id)

    with get_ynab_client() as api_client:
        categories_api = ynab.CategoriesApi(api_client)
        categories_response = categories_api.get_categories(budget_id)

        # First, collect all eligible categories - exclude hidden and deleted
        all_categories = []
        for category_group in categories_response.data.category_groups:
            for category in category_group.categories:
                # Skip hidden and deleted categories
                if category.hidden or category.deleted:
                    continue

                all_categories.append(
                    Category.from_ynab(category, category_group.name).model_dump()
                )

        # Apply pagination
        total_count = len(all_categories)
        start_index = offset
        end_index = min(offset + limit, total_count)
        categories_page = all_categories[start_index:end_index]

        has_more = end_index < total_count
        next_offset = end_index if has_more else None

        has_more = end_index < total_count
        next_offset = end_index if has_more else None

        pagination = PaginationInfo(
            total_count=total_count,
            limit=limit,
            offset=offset,
            has_more=has_more,
            next_offset=next_offset,
            returned_count=len(categories_page),
        )

        # Convert dict categories back to Category objects
        category_objects = [Category(**cat_dict) for cat_dict in categories_page]

        return CategoriesResponse(categories=category_objects, pagination=pagination)


@mcp.tool()
def list_category_groups(budget_id: str | None = None) -> CategoryGroupsResponse:
    """List category groups for a specific budget (lighter weight than full categories).

    Args:
        budget_id: Budget ID (optional - omit to use default budget automatically)

    Returns:
        CategoryGroupsResponse with category groups list
    """
    budget_id = budget_id_or_default(budget_id)

    with get_ynab_client() as api_client:
        categories_api = ynab.CategoriesApi(api_client)
        categories_response = categories_api.get_categories(budget_id)

        groups = [
            CategoryGroup.from_ynab(category_group)
            for category_group in categories_response.data.category_groups
            if not category_group.deleted
        ]

        return CategoryGroupsResponse(category_groups=groups)


@mcp.tool()
def get_budget_month(
    month: date | Literal["current", "last", "next"] = "current",
    limit: int = 50,
    offset: int = 0,
    budget_id: str | None = None,
) -> BudgetMonth:
    """Get budget data for a specific month including category budgets, activity, and
    balances with pagination.

    Only returns active/visible categories. Hidden and deleted categories are excluded
    automatically.

    Args:
        month: Month specifier. Use "current" for current month, "last" for previous
               month, "next" for next month, or a specific date object for an exact
               month (default "current")
        limit: Maximum number of categories to return (default 50)
        offset: Number of categories to skip for pagination (default 0)
        budget_id: Budget ID (optional - omit to use default budget automatically)

    Returns:
        BudgetMonth with month info, categories, and pagination
    """
    budget_id = budget_id_or_default(budget_id)

    with get_ynab_client() as api_client:
        months_api = ynab.MonthsApi(api_client)
        converted_month = convert_month_to_date(month)
        month_response = months_api.get_budget_month(budget_id, converted_month)

        # Also fetch category groups to get group names
        categories_api = ynab.CategoriesApi(api_client)
        categories_response = categories_api.get_categories(budget_id)

        # Build a mapping of category_id to group_name
        category_group_map = {}
        for category_group in categories_response.data.category_groups:
            for category in category_group.categories:
                category_group_map[category.id] = category_group.name

        month_data = month_response.data.month
        all_categories = []

        for category in month_data.categories:
            # Skip hidden and deleted categories
            if category.deleted or category.hidden:
                continue

            # Get the group name from our mapping
            group_name = category_group_map.get(category.id)
            all_categories.append(Category.from_ynab(category, group_name))

        # Apply pagination
        total_count = len(all_categories)
        start_index = offset
        end_index = min(offset + limit, total_count)
        categories_page = all_categories[start_index:end_index]

        has_more = end_index < total_count
        next_offset = end_index if has_more else None

        pagination = PaginationInfo(
            total_count=total_count,
            limit=limit,
            offset=offset,
            has_more=has_more,
            next_offset=next_offset,
            returned_count=len(categories_page),
        )

        return BudgetMonth(
            month=month_data.month,
            note=month_data.note,
            income=milliunits_to_currency(month_data.income),
            budgeted=milliunits_to_currency(month_data.budgeted),
            activity=milliunits_to_currency(month_data.activity),
            to_be_budgeted=milliunits_to_currency(month_data.to_be_budgeted),
            age_of_money=month_data.age_of_money,
            categories=categories_page,
            pagination=pagination,
        )


@mcp.tool()
def get_month_category_by_id(
    category_id: str,
    month: date | Literal["current", "last", "next"] = "current",
    budget_id: str | None = None,
) -> Category:
    """Get a specific category's data for a specific month.

    Args:
        category_id: Category ID (required)
        month: Month specifier. Use "current" for current month, "last" for previous
               month, "next" for next month, or a specific date object for an exact
               month (default "current")
        budget_id: Budget ID (optional - omit to use default budget automatically)

    Returns:
        Category with budget data for the specified month
    """
    budget_id = budget_id_or_default(budget_id)

    with get_ynab_client() as api_client:
        categories_api = ynab.CategoriesApi(api_client)
        converted_month = convert_month_to_date(month)
        category_response = categories_api.get_month_category_by_id(
            budget_id, converted_month, category_id
        )

        category = category_response.data.category

        # Fetch category groups to get the group name for this category
        categories_response = categories_api.get_categories(budget_id)
        group_name = None
        for category_group in categories_response.data.category_groups:
            for cat in category_group.categories:
                if cat.id == category_id:
                    group_name = category_group.name
                    break
            if group_name:
                break

        return Category.from_ynab(category, group_name)


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
        budget_id: Budget ID (optional - omit to use default budget automatically)

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

            # Apply amount filters (check milliunits directly for efficiency)
            if min_amount is not None and txn.amount < (min_amount * 1000):
                continue
            if max_amount is not None and txn.amount > (max_amount * 1000):
                continue

            # Use class method to convert transaction
            all_transactions.append(Transaction.from_ynab(txn))

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
        budget_id: Budget ID (optional - omit to use default budget automatically)

    Returns:
        PayeesResponse with payees list and pagination information
    """
    budget_id = budget_id_or_default(budget_id)

    with get_ynab_client() as api_client:
        payees_api = ynab.PayeesApi(api_client)
        payees_response = payees_api.get_payees(budget_id)

        # Filter payees - exclude deleted payees
        all_payees = [
            Payee.from_ynab(payee)
            for payee in payees_response.data.payees
            if not payee.deleted
        ]

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
        budget_id: Budget ID (optional - omit to use default budget automatically)

    Returns:
        PayeesResponse with matching payees and pagination information
    """
    budget_id = budget_id_or_default(budget_id)

    with get_ynab_client() as api_client:
        payees_api = ynab.PayeesApi(api_client)
        payees_response = payees_api.get_payees(budget_id)

        # Filter payees by name search and deleted status
        search_term = name_search.lower().strip()
        matching_payees = [
            Payee.from_ynab(payee)
            for payee in payees_response.data.payees
            if not payee.deleted and search_term in payee.name.lower()
        ]

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


@mcp.tool()
def list_scheduled_transactions(
    account_id: str | None = None,
    category_id: str | None = None,
    payee_id: str | None = None,
    frequency: str | None = None,
    upcoming_days: int | None = None,
    min_amount: Decimal | None = None,
    max_amount: Decimal | None = None,
    limit: int = 25,
    offset: int = 0,
    budget_id: str | None = None,
) -> ScheduledTransactionsResponse:
    """List scheduled transactions with powerful filtering options for analysis.

    This tool supports various filters that can be combined:
    - Filter by account to see scheduled transactions for a specific account
    - Filter by category to analyze recurring spending (e.g., "Monthly Bills")
    - Filter by payee to see scheduled transactions (e.g., "Netflix")
    - Filter by frequency to find daily, weekly, monthly, etc. recurring transactions
    - Filter by upcoming_days to see what's scheduled in the next N days
    - Filter by amount range using min_amount and/or max_amount

    Example queries this tool can answer:
    - "Show me all monthly recurring expenses" (use frequency="monthly")
    - "What bills are due in the next 7 days?" (use upcoming_days=7)
    - "List all Netflix subscriptions" (use payee search first, then filter by payee_id)
    - "Show scheduled transactions over $100" (use min_amount=100)

    Args:
        account_id: Filter by specific account (optional)
        category_id: Filter by specific category (optional)
        payee_id: Filter by specific payee (optional)
        frequency: Filter by frequency (never, daily, weekly, everyOtherWeek,
                   twiceAMonth, every4Weeks, monthly, everyOtherMonth, every3Months,
                   every4Months, twiceAYear, yearly, everyOtherYear) (optional)
        upcoming_days: Only show scheduled transactions with next occurrence
                       within this many days (optional)
        min_amount: Only show scheduled transactions with amount >= this value
                    (optional, negative for outflows)
        max_amount: Only show scheduled transactions with amount <= this value
                    (optional, negative for outflows)
        limit: Maximum number of scheduled transactions to return (default 25)
        offset: Number of scheduled transactions to skip for pagination (default 0)
        budget_id: Budget ID (optional - omit to use default budget automatically)

    Returns:
        ScheduledTransactionsResponse with filtered scheduled transactions and
        pagination info
    """
    budget_id = budget_id_or_default(budget_id)

    with get_ynab_client() as api_client:
        scheduled_transactions_api = ynab.ScheduledTransactionsApi(api_client)
        response = scheduled_transactions_api.get_scheduled_transactions(budget_id)

        # Convert and filter scheduled transactions
        all_scheduled_transactions = []
        for st in response.data.scheduled_transactions:
            # Skip deleted scheduled transactions
            if st.deleted:
                continue

            # Apply filters
            if account_id and st.account_id != account_id:
                continue
            if category_id and st.category_id != category_id:
                continue
            if payee_id and st.payee_id != payee_id:
                continue
            if frequency and st.frequency != frequency:
                continue

            # Apply upcoming_days filter
            if upcoming_days is not None:
                days_until_next = (st.date_next - datetime.now().date()).days
                if days_until_next > upcoming_days:
                    continue

            # Apply amount filters (check milliunits directly for efficiency)
            if min_amount is not None and st.amount < (min_amount * 1000):
                continue
            if max_amount is not None and st.amount > (max_amount * 1000):
                continue

            # Use class method to convert scheduled transaction
            all_scheduled_transactions.append(ScheduledTransaction.from_ynab(st))

        # Sort by next date ascending (earliest scheduled first)
        all_scheduled_transactions.sort(key=lambda st: st.date_next)

        # Apply pagination
        total_count = len(all_scheduled_transactions)
        start_index = offset
        end_index = min(offset + limit, total_count)
        scheduled_transactions_page = all_scheduled_transactions[start_index:end_index]

        has_more = end_index < total_count
        next_offset = end_index if has_more else None

        pagination = PaginationInfo(
            total_count=total_count,
            limit=limit,
            offset=offset,
            has_more=has_more,
            next_offset=next_offset,
            returned_count=len(scheduled_transactions_page),
        )

        return ScheduledTransactionsResponse(
            scheduled_transactions=scheduled_transactions_page, pagination=pagination
        )
