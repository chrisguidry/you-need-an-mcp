"""
Test the tools that read transactions.
"""

from datetime import date
from typing import Any
from unittest.mock import MagicMock
from uuid import UUID

import pytest
import ynab
from assertions import assert_pagination_info, extract_response_data
from conftest import create_ynab_transaction, transaction_response
from fastmcp.client import Client, FastMCPTransport
from ids import uid

from transactions import Transaction


async def list_transaction_ids(
    mcp_client: Client[FastMCPTransport], arguments: dict[str, Any]
) -> list[str]:
    result = await mcp_client.call_tool("list_transactions", arguments)
    return [txn["id"] for txn in extract_response_data(result)["transactions"]]


async def test_list_transactions_without_filters_reads_the_cache(
    mock_repository: MagicMock,
    transactions_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    mock_repository.get_transactions.return_value = [
        create_ynab_transaction(
            id="txn-1",
            amount=-43_170,
            memo="Weekly shop",
            account_name="Checking",
            payee_id=uid("payee-kroger"),
            payee_name="Kroger",
            category_id=uid("cat-groceries"),
            category_name="Groceries",
        )
    ]

    result = await mcp_client.call_tool("list_transactions", {})

    response = extract_response_data(result)
    assert response["transactions"] == [
        {
            "id": "txn-1",
            "date": "2024-01-15",
            "amount": "-43.17",
            "memo": "Weekly shop",
            "cleared": "cleared",
            "approved": True,
            "flag": None,
            "account_id": str(uid("acc-1")),
            "account_name": "Checking",
            "payee_id": str(uid("payee-kroger")),
            "payee_name": "Kroger",
            "category_id": str(uid("cat-groceries")),
            "category_name": "Groceries",
            "transfer_account_id": None,
            "import_payee_name_original": None,
            "parent_transaction_id": None,
            "subtransactions": None,
        }
    ]
    transactions_api.get_transactions.assert_not_called()


async def test_list_transactions_excludes_deleted_and_puts_newest_first(
    mock_repository: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    mock_repository.get_transactions.return_value = [
        create_ynab_transaction(id="txn-jan", transaction_date=date(2024, 1, 15)),
        create_ynab_transaction(id="txn-mar", transaction_date=date(2024, 3, 1)),
        create_ynab_transaction(
            id="txn-gone", transaction_date=date(2024, 4, 1), deleted=True
        ),
        create_ynab_transaction(id="txn-feb", transaction_date=date(2024, 2, 10)),
    ]

    ids = await list_transaction_ids(mcp_client, {})

    assert ids == ["txn-mar", "txn-feb", "txn-jan"]


async def test_list_transactions_pages_the_results(
    mock_repository: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    mock_repository.get_transactions.return_value = [
        create_ynab_transaction(id=f"txn-{day}", transaction_date=date(2024, 1, day))
        for day in range(1, 6)
    ]

    result = await mcp_client.call_tool("list_transactions", {"limit": 2, "offset": 2})

    response = extract_response_data(result)
    assert [txn["id"] for txn in response["transactions"]] == ["txn-3", "txn-2"]
    assert_pagination_info(
        response["pagination"], total_count=5, limit=2, offset=2, has_more=True
    )


def transactions_response(*rows: ynab.TransactionDetail) -> ynab.TransactionsResponse:
    return ynab.TransactionsResponse(
        data=ynab.TransactionsResponseData(transactions=list(rows), server_knowledge=1)
    )


async def test_list_transactions_passes_dates_and_status_to_ynab(
    transactions_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    transactions_api.get_transactions.return_value = transactions_response(
        create_ynab_transaction(id="txn-1", approved=False)
    )

    ids = await list_transaction_ids(
        mcp_client,
        {
            "since_date": "2024-03-01",
            "until_date": "2024-03-31",
            "status": "unapproved",
        },
    )

    assert ids == ["txn-1"]
    transactions_api.get_transactions.assert_called_once_with(
        "test_plan_id",
        since_date=date(2024, 3, 1),
        until_date=date(2024, 3, 31),
        type="unapproved",
    )


def create_ynab_hybrid_transaction(
    *,
    id: str = "txn-1",
    type: str = "transaction",
    parent_transaction_id: str | None = None,
    transaction_date: date = date(2024, 1, 15),
    amount: int = -50_000,
    account_id: UUID = uid("acc-1"),
    payee_id: UUID | None = None,
    payee_name: str | None = None,
    category_id: UUID | None = None,
    category_name: str | None = None,
    deleted: bool = False,
) -> ynab.HybridTransaction:
    """Create a HybridTransaction, a row from the lists by category or payee."""
    return ynab.HybridTransaction(
        id=id,
        date=transaction_date,
        amount=amount,
        cleared=ynab.TransactionClearedStatus.CLEARED,
        approved=True,
        account_id=account_id,
        account_name="Checking",
        payee_id=payee_id,
        payee_name=payee_name,
        category_id=category_id,
        category_name=category_name,
        deleted=deleted,
        type=type,
        parent_transaction_id=parent_transaction_id,
    )


def hybrid_transactions_response(
    *rows: ynab.HybridTransaction,
) -> ynab.HybridTransactionsResponse:
    return ynab.HybridTransactionsResponse(
        data=ynab.HybridTransactionsResponseData(transactions=list(rows))
    )


@pytest.mark.parametrize(
    ("argument", "endpoint", "response"),
    [
        (
            "account_id",
            "get_transactions_by_account",
            transactions_response(create_ynab_transaction(account_id=uid("filter"))),
        ),
        (
            "category_id",
            "get_transactions_by_category",
            hybrid_transactions_response(
                create_ynab_hybrid_transaction(category_id=uid("filter"))
            ),
        ),
        (
            "payee_id",
            "get_transactions_by_payee",
            hybrid_transactions_response(
                create_ynab_hybrid_transaction(payee_id=uid("filter"))
            ),
        ),
    ],
)
async def test_list_transactions_asks_ynab_for_one_filter(
    transactions_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
    argument: str,
    endpoint: str,
    response: ynab.TransactionsResponse | ynab.HybridTransactionsResponse,
) -> None:
    getattr(transactions_api, endpoint).return_value = response

    ids = await list_transaction_ids(
        mcp_client,
        {
            argument: str(uid("filter")),
            "since_date": "2024-01-01",
            "status": "uncategorized",
        },
    )

    assert ids == ["txn-1"]
    getattr(transactions_api, endpoint).assert_called_once_with(
        "test_plan_id",
        str(uid("filter")),
        since_date=date(2024, 1, 1),
        until_date=None,
        type="uncategorized",
    )


async def test_list_transactions_by_category_also_applies_account_and_payee(
    transactions_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    transactions_api.get_transactions_by_category.return_value = (
        hybrid_transactions_response(
            create_ynab_hybrid_transaction(
                id="txn-match",
                account_id=uid("acc-checking"),
                category_id=uid("cat-dining"),
                payee_id=uid("payee-diner"),
            ),
            create_ynab_hybrid_transaction(
                id="txn-other-account",
                account_id=uid("acc-credit"),
                category_id=uid("cat-dining"),
                payee_id=uid("payee-diner"),
            ),
            create_ynab_hybrid_transaction(
                id="txn-other-payee",
                account_id=uid("acc-checking"),
                category_id=uid("cat-dining"),
                payee_id=uid("payee-cafe"),
            ),
        )
    )

    ids = await list_transaction_ids(
        mcp_client,
        {
            "account_id": str(uid("acc-checking")),
            "category_id": str(uid("cat-dining")),
            "payee_id": str(uid("payee-diner")),
        },
    )

    assert ids == ["txn-match"]
    transactions_api.get_transactions_by_account.assert_not_called()
    transactions_api.get_transactions_by_payee.assert_not_called()


async def test_list_transactions_by_payee_also_applies_account(
    transactions_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    transactions_api.get_transactions_by_payee.return_value = (
        hybrid_transactions_response(
            create_ynab_hybrid_transaction(
                id="txn-match",
                account_id=uid("acc-checking"),
                payee_id=uid("payee-diner"),
            ),
            create_ynab_hybrid_transaction(
                id="txn-other-account",
                account_id=uid("acc-credit"),
                payee_id=uid("payee-diner"),
            ),
        )
    )

    ids = await list_transaction_ids(
        mcp_client,
        {"account_id": str(uid("acc-checking")), "payee_id": str(uid("payee-diner"))},
    )

    assert ids == ["txn-match"]
    transactions_api.get_transactions_by_account.assert_not_called()


async def test_list_transactions_by_account_and_category_keeps_a_split_part(
    transactions_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    transactions_api.get_transactions_by_category.return_value = (
        hybrid_transactions_response(
            create_ynab_hybrid_transaction(
                id="sub-groceries",
                type="subtransaction",
                parent_transaction_id="txn-target",
                account_id=uid("acc-checking"),
                category_id=uid("cat-groceries"),
                payee_id=uid("payee-target"),
            )
        )
    )

    ids = await list_transaction_ids(
        mcp_client,
        {
            "account_id": str(uid("acc-checking")),
            "category_id": str(uid("cat-groceries")),
        },
    )

    assert ids == ["sub-groceries"]


async def test_list_transactions_gives_a_split_part_its_parents_payee(
    transactions_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    transactions_api.get_transactions_by_category.return_value = (
        hybrid_transactions_response(
            create_ynab_hybrid_transaction(
                id="sub-1",
                type="subtransaction",
                parent_transaction_id="txn-parent",
                category_id=uid("cat-groceries"),
            )
        )
    )
    transactions_api.get_transaction_by_id.return_value = transaction_response(
        create_ynab_transaction(
            id="txn-parent", payee_id=uid("payee-target"), payee_name="Target"
        )
    )

    result = await mcp_client.call_tool(
        "list_transactions", {"category_id": str(uid("cat-groceries"))}
    )

    part = extract_response_data(result)["transactions"][0]
    assert part["payee_id"] == str(uid("payee-target"))
    assert part["payee_name"] == "Target"
    assert part["parent_transaction_id"] == "txn-parent"
    transactions_api.get_transaction_by_id.assert_called_once_with(
        "test_plan_id", "txn-parent"
    )


async def test_list_transactions_filters_a_split_part_by_its_parents_payee(
    transactions_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    transactions_api.get_transactions_by_category.return_value = (
        hybrid_transactions_response(
            create_ynab_hybrid_transaction(
                id="sub-groceries",
                type="subtransaction",
                parent_transaction_id="txn-target",
                category_id=uid("cat-groceries"),
            )
        )
    )
    transactions_api.get_transaction_by_id.return_value = transaction_response(
        create_ynab_transaction(
            id="txn-target", payee_id=uid("payee-target"), payee_name="Target"
        )
    )

    ids = await list_transaction_ids(
        mcp_client,
        {
            "category_id": str(uid("cat-groceries")),
            "payee_id": str(uid("payee-target")),
        },
    )

    assert ids == ["sub-groceries"]


@pytest.mark.parametrize(
    "row",
    [
        create_ynab_hybrid_transaction(type="transaction"),
        create_ynab_hybrid_transaction(
            type="subtransaction",
            parent_transaction_id="txn-parent",
            payee_id=uid("payee-own"),
        ),
        create_ynab_hybrid_transaction(
            type="subtransaction",
            parent_transaction_id="txn-parent",
            payee_name="Own Payee",
        ),
        create_ynab_hybrid_transaction(type="subtransaction"),
    ],
    ids=["whole-transaction", "own-payee-id", "own-payee-name", "no-parent"],
)
def test_hybrid_rows_that_need_no_parent_keep_their_own_payee(
    mock_repository: MagicMock,
    transactions_api: MagicMock,
    row: ynab.HybridTransaction,
) -> None:
    transaction = Transaction.from_ynab(row, mock_repository)

    assert transaction.payee_id == row.payee_id
    assert transaction.payee_name == row.payee_name
    transactions_api.get_transaction_by_id.assert_not_called()


def test_hybrid_split_part_keeps_no_payee_without_a_repository(
    transactions_api: MagicMock,
) -> None:
    row = create_ynab_hybrid_transaction(
        type="subtransaction", parent_transaction_id="txn-parent"
    )

    transaction = Transaction.from_ynab(row)

    assert transaction.payee_id is None
    assert transaction.payee_name is None
    transactions_api.get_transaction_by_id.assert_not_called()


async def test_get_transaction(
    transactions_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    transactions_api.get_transaction_by_id.return_value = transaction_response(
        create_ynab_transaction(
            id="txn-1",
            amount=-80_000,
            payee_name="Target",
            category_name="Split",
            subtransactions=[
                ynab.SubTransaction(
                    id="sub-1",
                    transaction_id="txn-1",
                    amount=-80_000,
                    category_id=uid("cat-groceries"),
                    category_name="Groceries",
                    deleted=False,
                )
            ],
        )
    )

    result = await mcp_client.call_tool("get_transaction", {"transaction_id": "txn-1"})

    transaction = extract_response_data(result)
    assert transaction["id"] == "txn-1"
    assert transaction["amount"] == "-80"
    assert transaction["subtransactions"][0]["category_name"] == "Groceries"
    transactions_api.get_transaction_by_id.assert_called_once_with(
        "test_plan_id", "txn-1"
    )
