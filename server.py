import os
from datetime import date, datetime
from decimal import Decimal
from typing import Literal, cast

import ynab
from fastmcp import FastMCP

from models import (
    Account,
    AccountsResponse,
    BudgetMonth,
    CategoriesResponse,
    Category,
    CategoryGroup,
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
    Gives you access to a user's YNAB budget, including accounts, categories, and
    transactions. If a user is ever asking about budgeting, their personal finances,
    banking, saving, or investing, their YNAB budget is very relevant to them.
    When the user asks about budget categories and "how much is left", they are
    talking about the current month.

    Budget categories are grouped into category groups, which are important groupings
    to the user and should be displayed in a hierarchical manner. Categories will have
    the category_group_name and category_group_id available.

    The server operates on a single budget configured via the YNAB_BUDGET environment
    variable. All tools work with this budget automatically.
    """,
)


def get_ynab_client() -> ynab.ApiClient:
    """Get authenticated YNAB API client."""
    access_token = os.getenv("YNAB_ACCESS_TOKEN")
    if not access_token:
        raise ValueError("YNAB_ACCESS_TOKEN environment variable is required")

    configuration = ynab.Configuration(access_token=access_token)
    return ynab.ApiClient(configuration)


# Load budget ID at module import - fail fast if not configured
BUDGET_ID = os.environ["YNAB_BUDGET"]


def _paginate_items[T](
    items: list[T], limit: int, offset: int
) -> tuple[list[T], PaginationInfo]:
    """Apply pagination to a list of items and return the page with pagination info."""
    total_count = len(items)
    start_index = offset
    end_index = min(offset + limit, total_count)
    items_page = items[start_index:end_index]

    has_more = end_index < total_count

    pagination = PaginationInfo(
        total_count=total_count,
        limit=limit,
        offset=offset,
        has_more=has_more,
    )

    return items_page, pagination


def _filter_active_items[T](
    items: list[T],
    *,
    exclude_deleted: bool = True,
    exclude_hidden: bool = False,
    exclude_closed: bool = False,
) -> list[T]:
    """Filter items to exclude deleted/hidden/closed based on flags."""
    filtered = []
    for item in items:
        if exclude_deleted and getattr(item, "deleted", False):
            continue
        if exclude_hidden and getattr(item, "hidden", False):
            continue
        if exclude_closed and getattr(item, "closed", False):
            continue
        filtered.append(item)
    return filtered


def _build_category_group_map(
    category_groups: list[ynab.CategoryGroupWithCategories],
) -> dict[str, str]:
    """Build a mapping of category_id to category_group_name."""
    mapping = {}
    for category_group in category_groups:
        for category in category_group.categories:
            mapping[category.id] = category_group.name
    return mapping


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

    today = datetime.now().date()
    year, month_num = today.year, today.month

    match month:
        case "current":
            return date(year, month_num, 1)
        case "last":
            return (
                date(year - 1, 12, 1)
                if month_num == 1
                else date(year, month_num - 1, 1)
            )
        case "next":
            return (
                date(year + 1, 1, 1)
                if month_num == 12
                else date(year, month_num + 1, 1)
            )
        case _:
            raise ValueError(f"Invalid month value: {month}")


@mcp.tool()
def list_accounts(
    limit: int = 100,
    offset: int = 0,
) -> AccountsResponse:
    """List accounts with pagination.

    Only returns open/active accounts. Closed accounts are excluded automatically.

    Args:
        limit: Maximum number of accounts to return per page (default: 100)
        offset: Number of accounts to skip for pagination (default: 0)

    Returns:
        AccountsResponse with accounts list and pagination information
    """
    with get_ynab_client() as api_client:
        accounts_api = ynab.AccountsApi(api_client)
        accounts_response = accounts_api.get_accounts(BUDGET_ID)

        active_accounts = _filter_active_items(
            accounts_response.data.accounts, exclude_closed=True
        )
        all_accounts = [Account.from_ynab(account) for account in active_accounts]

        accounts_page, pagination = _paginate_items(all_accounts, limit, offset)

        return AccountsResponse(accounts=accounts_page, pagination=pagination)


@mcp.tool()
def list_categories(
    limit: int = 50,
    offset: int = 0,
) -> CategoriesResponse:
    """List categories with pagination.

    Only returns active/visible categories. Hidden and deleted categories are excluded
    automatically.

    Args:
        limit: Maximum number of categories to return per page (default: 50)
        offset: Number of categories to skip for pagination (default: 0)

    Returns:
        CategoriesResponse with categories list and pagination information
    """
    with get_ynab_client() as api_client:
        categories_api = ynab.CategoriesApi(api_client)
        categories_response = categories_api.get_categories(BUDGET_ID)

        all_categories = []
        for category_group in categories_response.data.category_groups:
            active_categories = _filter_active_items(
                category_group.categories, exclude_hidden=True
            )
            for category in active_categories:
                all_categories.append(
                    Category.from_ynab(category, category_group.name).model_dump()
                )

        categories_page, pagination = _paginate_items(all_categories, limit, offset)

        # Convert dict categories back to Category objects
        category_objects = [Category(**cat_dict) for cat_dict in categories_page]

        return CategoriesResponse(categories=category_objects, pagination=pagination)


@mcp.tool()
def list_category_groups() -> list[CategoryGroup]:
    """List category groups (lighter weight than full categories).

    Returns:
        List of category groups
    """
    with get_ynab_client() as api_client:
        categories_api = ynab.CategoriesApi(api_client)
        categories_response = categories_api.get_categories(BUDGET_ID)

        active_groups = _filter_active_items(categories_response.data.category_groups)
        groups = [
            CategoryGroup.from_ynab(category_group) for category_group in active_groups
        ]

        return groups


@mcp.tool()
def get_budget_month(
    month: date | Literal["current", "last", "next"] = "current",
    limit: int = 50,
    offset: int = 0,
) -> BudgetMonth:
    """Get budget data for a specific month including category budgets, activity, and
    balances with pagination.

    Only returns active/visible categories. Hidden and deleted categories are excluded
    automatically.

    Args:
        month: Specifies which budget month to retrieve:
              • "current": Current calendar month
              • "last": Previous calendar month
              • "next": Next calendar month
              • date object: Specific month (uses first day of month)
              Examples: "current", date(2024, 3, 1) for March 2024 (default: "current")
        limit: Maximum number of categories to return per page (default: 50)
        offset: Number of categories to skip for pagination (default: 0)

    Returns:
        BudgetMonth with month info, categories, and pagination
    """
    with get_ynab_client() as api_client:
        months_api = ynab.MonthsApi(api_client)
        converted_month = convert_month_to_date(month)
        month_response = months_api.get_budget_month(BUDGET_ID, converted_month)

        # Fetch category groups for names
        categories_api = ynab.CategoriesApi(api_client)
        categories_response = categories_api.get_categories(BUDGET_ID)

        # Map category IDs to group names
        category_group_map = _build_category_group_map(
            categories_response.data.category_groups
        )

        month_data = month_response.data.month
        all_categories = []

        active_categories = _filter_active_items(
            month_data.categories, exclude_hidden=True
        )
        for category in active_categories:
            group_name = category_group_map.get(category.id)
            all_categories.append(Category.from_ynab(category, group_name))

        categories_page, pagination = _paginate_items(all_categories, limit, offset)

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
) -> Category:
    """Get a specific category's data for a specific month.

    Args:
        category_id: Unique identifier for the category (required)
        month: Specifies which budget month to retrieve:
              • "current": Current calendar month
              • "last": Previous calendar month
              • "next": Next calendar month
              • date object: Specific month (uses first day of month)
              Examples: "current", date(2024, 3, 1) for March 2024 (default: "current")

    Returns:
        Category with budget data for the specified month
    """
    with get_ynab_client() as api_client:
        categories_api = ynab.CategoriesApi(api_client)
        converted_month = convert_month_to_date(month)
        category_response = categories_api.get_month_category_by_id(
            BUDGET_ID, converted_month, category_id
        )

        category = category_response.data.category

        # Fetch category groups to get group name
        categories_response = categories_api.get_categories(BUDGET_ID)
        category_group_map = _build_category_group_map(
            categories_response.data.category_groups
        )
        group_name = category_group_map.get(category_id)

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
) -> TransactionsResponse:
    """List transactions with powerful filtering options for financial analysis.

    This tool supports various filters that can be combined:
    - Filter by account to see transactions for a specific account
    - Filter by category to analyze spending in a category (e.g., "Dining Out")
    - Filter by payee to see all transactions with a specific merchant (e.g., "Amazon")
    - Filter by date range using since_date
    - Filter by amount range using min_amount and/or max_amount

    Example queries this tool can answer:
    - "Show me all transactions over $50 in Dining Out this year"
      → Use: category_id="cat_dining_out_id", min_amount=50.00,
             since_date=date(2024, 1, 1)
    - "How much have I spent at Amazon this month"
      → Use: payee_id="payee_amazon_id", since_date=date(2024, 12, 1)
    - "List recent transactions in my checking account"
      → Use: account_id="acc_checking_id"

    Args:
        account_id: Filter by specific account (optional)
        category_id: Filter by specific category (optional)
        payee_id: Filter by specific payee (optional)
        since_date: Only show transactions on or after this date. Accepts date objects
                   in YYYY-MM-DD format (e.g., date(2024, 1, 1)) (optional)
        min_amount: Only show transactions with amount >= this value in currency units.
                   Use negative values for outflows/expenses
                   (e.g., -50.00 for $50+ expenses) (optional)
        max_amount: Only show transactions with amount <= this value in currency units.
                   Use negative values for outflows/expenses
                   (e.g., -10.00 for under $10 expenses) (optional)
        limit: Maximum number of transactions to return per page (default: 25)
        offset: Number of transactions to skip for pagination (default: 0)

    Returns:
        TransactionsResponse with filtered transactions and pagination info
    """
    with get_ynab_client() as api_client:
        transactions_api = ynab.TransactionsApi(api_client)

        # Determine which API method to use based on filters
        response: ynab.TransactionsResponse | ynab.HybridTransactionsResponse
        if account_id:
            # Use account-specific endpoint if account filter is provided
            response = transactions_api.get_transactions_by_account(
                BUDGET_ID,
                account_id,
                since_date=since_date,
                type=None,  # Include all transaction types
            )
        elif category_id:
            # Use category-specific endpoint if category filter is provided
            response = transactions_api.get_transactions_by_category(
                BUDGET_ID, category_id, since_date=since_date, type=None
            )
        elif payee_id:
            # Use payee-specific endpoint if payee filter is provided
            response = transactions_api.get_transactions_by_payee(
                BUDGET_ID, payee_id, since_date=since_date, type=None
            )
        else:
            # Use general transactions endpoint
            response = transactions_api.get_transactions(
                BUDGET_ID, since_date=since_date, type=None
            )

        transactions_data: list[ynab.TransactionDetail | ynab.HybridTransaction] = cast(
            list[ynab.TransactionDetail | ynab.HybridTransaction],
            response.data.transactions,
        )
        active_transactions = _filter_active_items(transactions_data)
        all_transactions = []
        for txn in active_transactions:
            # Apply amount filters (check milliunits directly for efficiency)
            if (
                min_amount is not None
                and txn.amount is not None
                and txn.amount < (min_amount * 1000)
            ):
                continue
            if (
                max_amount is not None
                and txn.amount is not None
                and txn.amount > (max_amount * 1000)
            ):
                continue

            all_transactions.append(Transaction.from_ynab(txn))

        # Sort by date descending (most recent first)
        all_transactions.sort(key=lambda t: t.date, reverse=True)

        transactions_page, pagination = _paginate_items(all_transactions, limit, offset)

        return TransactionsResponse(
            transactions=transactions_page, pagination=pagination
        )


@mcp.tool()
def list_payees(
    limit: int = 50,
    offset: int = 0,
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
        limit: Maximum number of payees to return per page (default: 50)
        offset: Number of payees to skip for pagination (default: 0)

    Returns:
        PayeesResponse with payees list and pagination information
    """
    with get_ynab_client() as api_client:
        payees_api = ynab.PayeesApi(api_client)
        payees_response = payees_api.get_payees(BUDGET_ID)

        active_payees = _filter_active_items(payees_response.data.payees)
        all_payees = [Payee.from_ynab(payee) for payee in active_payees]

        # Sort by name for easier browsing
        all_payees.sort(key=lambda p: p.name.lower())

        payees_page, pagination = _paginate_items(all_payees, limit, offset)

        return PayeesResponse(payees=payees_page, pagination=pagination)


@mcp.tool()
def find_payee(
    name_search: str,
    limit: int = 10,
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
                     substring match). Examples: "amazon", "starbucks", "grocery"
        limit: Maximum number of matching payees to return (default: 10)

    Returns:
        PayeesResponse with matching payees and pagination information
    """
    with get_ynab_client() as api_client:
        payees_api = ynab.PayeesApi(api_client)
        payees_response = payees_api.get_payees(BUDGET_ID)

        active_payees = _filter_active_items(payees_response.data.payees)
        search_term = name_search.lower().strip()
        matching_payees = [
            Payee.from_ynab(payee)
            for payee in active_payees
            if search_term in payee.name.lower()
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
        frequency: Filter by recurrence frequency. Valid values:
                  • never, daily, weekly
                  • everyOtherWeek, twiceAMonth, every4Weeks
                  • monthly, everyOtherMonth, every3Months, every4Months
                  • twiceAYear, yearly, everyOtherYear
                  (optional)
        upcoming_days: Only show scheduled transactions with next occurrence
                       within this many days (optional)
        min_amount: Only show scheduled transactions with amount >= this value
                   in currency units. Use negative values for outflows/expenses
                   (optional)
        max_amount: Only show scheduled transactions with amount <= this value
                   in currency units. Use negative values for outflows/expenses
                   (optional)
        limit: Maximum number of scheduled transactions to return per page (default: 25)
        offset: Number of scheduled transactions to skip for pagination (default: 0)

    Returns:
        ScheduledTransactionsResponse with filtered scheduled transactions and
        pagination info
    """
    with get_ynab_client() as api_client:
        scheduled_transactions_api = ynab.ScheduledTransactionsApi(api_client)
        response = scheduled_transactions_api.get_scheduled_transactions(BUDGET_ID)

        active_scheduled_transactions = _filter_active_items(
            response.data.scheduled_transactions
        )
        all_scheduled_transactions = []
        for st in active_scheduled_transactions:
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

            all_scheduled_transactions.append(ScheduledTransaction.from_ynab(st))

        # Sort by next date ascending (earliest scheduled first)
        all_scheduled_transactions.sort(key=lambda st: st.date_next)

        scheduled_transactions_page, pagination = _paginate_items(
            all_scheduled_transactions, limit, offset
        )

        return ScheduledTransactionsResponse(
            scheduled_transactions=scheduled_transactions_page, pagination=pagination
        )


@mcp.tool()
def update_category_budget(
    category_id: str,
    budgeted: Decimal,
    month: date | Literal["current", "last", "next"] = "current",
) -> Category:
    """Update the budgeted amount for a category in a specific month.

    This tool allows you to assign money to budget categories, which is essential
    for monthly budget maintenance and reallocation.

    IMPORTANT: For categories with NEED goals (refill up to X monthly), budget the
    full goal_target amount regardless of current balance. These goals expect the
    full target to be budgeted each month.

    Args:
        category_id: Unique identifier for the category to update (required)
        budgeted: Amount to budget for this category in currency units (required)
        month: Budget month to update:
              • "current": Current calendar month
              • "last": Previous calendar month
              • "next": Next calendar month
              • date object: Specific month (uses first day of month)
              (default: "current")

    Returns:
        Category with updated budget information
    """
    with get_ynab_client() as api_client:
        categories_api = ynab.CategoriesApi(api_client)
        converted_month = convert_month_to_date(month)

        # Convert currency units to milliunits and create patch
        budgeted_milliunits = int(budgeted * 1000)
        save_month_category = ynab.SaveMonthCategory(budgeted=budgeted_milliunits)
        patch_wrapper = ynab.PatchMonthCategoryWrapper(category=save_month_category)

        response = categories_api.update_month_category(
            BUDGET_ID, converted_month, category_id, patch_wrapper
        )

        # Get category group name for the response
        categories_response = categories_api.get_categories(BUDGET_ID)
        category_group_map = _build_category_group_map(
            categories_response.data.category_groups
        )
        group_name = category_group_map.get(category_id)

        return Category.from_ynab(response.data.category, group_name)


@mcp.tool()
def update_transaction(
    transaction_id: str,
    category_id: str | None = None,
    payee_id: str | None = None,
    memo: str | None = None,
) -> Transaction:
    """Update an existing transaction's details.

    This tool allows you to modify transaction properties, most commonly
    to assign the correct category to imported or uncategorized transactions.

    Args:
        transaction_id: Unique identifier for the transaction to update (required)
        category_id: Category ID to assign (optional)
        payee_id: Payee ID to assign (optional)
        memo: Transaction memo (optional)

    Returns:
        Transaction with updated information
    """
    with get_ynab_client() as api_client:
        transactions_api = ynab.TransactionsApi(api_client)

        # First, get the existing transaction to preserve its current values
        existing_response = transactions_api.get_transaction_by_id(
            BUDGET_ID, transaction_id
        )
        existing_txn = existing_response.data.transaction

        # Build the update data starting with existing transaction values
        update_data = {
            "account_id": existing_txn.account_id,
            "date": existing_txn.var_date,  # ExistingTransaction uses 'date'
            "amount": existing_txn.amount,
            "payee_id": existing_txn.payee_id,
            "payee_name": existing_txn.payee_name,
            "category_id": existing_txn.category_id,
            "memo": existing_txn.memo,
            "cleared": existing_txn.cleared,
            "approved": existing_txn.approved,
            "flag_color": existing_txn.flag_color,
            "subtransactions": existing_txn.subtransactions,
        }

        # Apply only the fields we want to change
        if category_id is not None:
            update_data["category_id"] = category_id
        if payee_id is not None:
            update_data["payee_id"] = payee_id
        if memo is not None:
            update_data["memo"] = memo

        existing_transaction = ynab.ExistingTransaction(
            account_id=update_data["account_id"],  # type: ignore[arg-type]
            date=update_data["date"],  # type: ignore[arg-type]
            amount=update_data["amount"],  # type: ignore[arg-type]
            payee_id=update_data["payee_id"],  # type: ignore[arg-type]
            payee_name=update_data["payee_name"],  # type: ignore[arg-type]
            category_id=update_data["category_id"],  # type: ignore[arg-type]
            memo=update_data["memo"],  # type: ignore[arg-type]
            cleared=update_data["cleared"],  # type: ignore[arg-type]
            approved=update_data["approved"],  # type: ignore[arg-type]
            flag_color=update_data["flag_color"],  # type: ignore[arg-type]
            subtransactions=update_data["subtransactions"],  # type: ignore[arg-type]
        )
        put_wrapper = ynab.PutTransactionWrapper(transaction=existing_transaction)

        response = transactions_api.update_transaction(
            BUDGET_ID, transaction_id, put_wrapper
        )

        return Transaction.from_ynab(response.data.transaction)
