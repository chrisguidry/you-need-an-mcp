"""
Test the tools that create, delete, and import transactions.
"""

from datetime import date
from typing import Any
from unittest.mock import MagicMock

import pytest
import ynab
from assertions import extract_response_data
from conftest import create_ynab_account, create_ynab_transaction, transaction_response
from fastmcp.client import Client, FastMCPTransport
from fastmcp.exceptions import ToolError
from ids import uid

from transaction_entry import CHANGED_BY_TRANSACTIONS


@pytest.fixture
def accounts(mock_repository: MagicMock) -> None:
    mock_repository.get_accounts.return_value = [
        create_ynab_account(
            id=uid("acc-checking"), transfer_payee_id=uid("payee-to-checking")
        ),
        create_ynab_account(
            id=uid("acc-savings"), transfer_payee_id=uid("payee-to-savings")
        ),
        create_ynab_account(
            id=uid("acc-closed"),
            transfer_payee_id=uid("payee-to-closed"),
            deleted=True,
        ),
    ]


def saved_transactions_response(
    *txns: ynab.TransactionDetail,
) -> ynab.SaveTransactionsResponse:
    return ynab.SaveTransactionsResponse(
        data=ynab.SaveTransactionsResponseData(
            transaction_ids=[txn.id for txn in txns],
            transactions=list(txns),
            server_knowledge=1,
        )
    )


@pytest.fixture
def created(transactions_api: MagicMock, accounts: None) -> None:
    transactions_api.create_transaction.return_value = saved_transactions_response(
        create_ynab_transaction(id="txn-new")
    )


async def create(
    mcp_client: Client[FastMCPTransport],
    transactions_api: MagicMock,
    *entries: dict[str, Any],
) -> list[ynab.NewTransaction]:
    """Create the entries, and return the transactions sent to YNAB."""
    await mcp_client.call_tool("create_transactions", {"transactions": list(entries)})
    sent: list[ynab.NewTransaction] = (
        transactions_api.create_transaction.call_args.args[1].transactions
    )
    return sent


@pytest.mark.usefixtures("created")
async def test_create_transactions_returns_what_ynab_saved(
    mock_repository: MagicMock,
    transactions_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    transactions_api.create_transaction.return_value = saved_transactions_response(
        create_ynab_transaction(id="txn-kroger", amount=-43_170),
        create_ynab_transaction(id="txn-payroll", amount=2_500_000),
    )

    result = await mcp_client.call_tool(
        "create_transactions",
        {
            "transactions": [
                {
                    "account_id": str(uid("acc-checking")),
                    "date": "2024-03-02",
                    "amount": "-43.17",
                    "payee_name": "Kroger",
                },
                {
                    "account_id": str(uid("acc-checking")),
                    "date": "2024-03-01",
                    "amount": "2500",
                    "payee_name": "Acme Payroll",
                },
            ]
        },
    )

    saved = result.structured_content
    assert saved is not None
    assert [(txn["id"], txn["amount"]) for txn in saved["result"]] == [
        ("txn-kroger", "-43.17"),
        ("txn-payroll", "2500"),
    ]
    assert transactions_api.create_transaction.call_count == 1
    assert transactions_api.create_transaction.call_args.args[0] == "test_plan_id"
    mock_repository.mark_stale.assert_called_once_with(*CHANGED_BY_TRANSACTIONS)


@pytest.mark.parametrize(
    ("entry", "expected"),
    [
        (
            {
                "account_id": str(uid("acc-checking")),
                "date": "2024-03-02",
                "amount": "-43.17",
                "payee_name": "Kroger",
                "category_id": str(uid("cat-groceries")),
            },
            ynab.NewTransaction(
                account_id=uid("acc-checking"),
                date=date(2024, 3, 2),
                amount=-43_170,
                payee_name="Kroger",
                category_id=uid("cat-groceries"),
                cleared=ynab.TransactionClearedStatus.UNCLEARED,
                approved=True,
            ),
        ),
        (
            {
                "account_id": str(uid("acc-checking")),
                "date": "2024-03-01",
                "amount": "2500",
                "payee_id": str(uid("payee-acme")),
                "category_id": str(uid("cat-ready-to-assign")),
            },
            ynab.NewTransaction(
                account_id=uid("acc-checking"),
                date=date(2024, 3, 1),
                amount=2_500_000,
                payee_id=uid("payee-acme"),
                category_id=uid("cat-ready-to-assign"),
                cleared=ynab.TransactionClearedStatus.UNCLEARED,
                approved=True,
            ),
        ),
        (
            {
                "account_id": str(uid("acc-checking")),
                "date": "2024-03-04",
                "amount": "-12",
                "payee_name": "Hardware Store",
                "memo": "Return this",
                "cleared": "cleared",
                "approved": False,
                "flag_color": "red",
            },
            ynab.NewTransaction(
                account_id=uid("acc-checking"),
                date=date(2024, 3, 4),
                amount=-12_000,
                payee_name="Hardware Store",
                memo="Return this",
                cleared=ynab.TransactionClearedStatus.CLEARED,
                approved=False,
                flag_color=ynab.TransactionFlagColor.RED,
            ),
        ),
    ],
    ids=["spending", "income", "flagged-and-cleared"],
)
@pytest.mark.usefixtures("created")
async def test_create_transactions_sends_the_entry(
    transactions_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
    entry: dict[str, Any],
    expected: ynab.NewTransaction,
) -> None:
    assert await create(mcp_client, transactions_api, entry) == [expected]


@pytest.mark.usefixtures("created")
async def test_create_transactions_pays_a_transfer_to_the_other_accounts_payee(
    transactions_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    sent = await create(
        mcp_client,
        transactions_api,
        {
            "account_id": str(uid("acc-checking")),
            "date": "2024-03-05",
            "amount": "-200",
            "transfer_account_id": str(uid("acc-savings")),
        },
    )

    assert [txn.payee_id for txn in sent] == [uid("payee-to-savings")]


@pytest.mark.parametrize("account", ["acc-missing", "acc-closed"])
@pytest.mark.usefixtures("created")
async def test_create_transactions_refuses_a_transfer_to_an_account_that_is_gone(
    transactions_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
    account: str,
) -> None:
    entry = {
        "account_id": str(uid("acc-checking")),
        "date": "2024-03-05",
        "amount": "-200",
        "transfer_account_id": str(uid(account)),
    }

    with pytest.raises(ToolError, match="No account"):
        await mcp_client.call_tool("create_transactions", {"transactions": [entry]})

    transactions_api.create_transaction.assert_not_called()


@pytest.mark.usefixtures("created")
async def test_create_transactions_sends_the_parts_of_a_split(
    transactions_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    sent = await create(
        mcp_client,
        transactions_api,
        {
            "account_id": str(uid("acc-checking")),
            "date": "2024-03-06",
            "amount": "-80",
            "payee_name": "Target",
            "splits": [
                {"amount": "-50", "category_id": str(uid("cat-groceries"))},
                {
                    "amount": "-30",
                    "category_id": str(uid("cat-gifts")),
                    "payee_name": "Toy Store",
                    "memo": "Birthday present",
                },
            ],
        },
    )

    assert [txn.subtransactions for txn in sent] == [
        [
            ynab.SaveSubTransaction(amount=-50_000, category_id=uid("cat-groceries")),
            ynab.SaveSubTransaction(
                amount=-30_000,
                category_id=uid("cat-gifts"),
                payee_name="Toy Store",
                memo="Birthday present",
            ),
        ]
    ]


@pytest.mark.usefixtures("created")
async def test_create_transactions_refuses_splits_that_do_not_add_up(
    transactions_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    entry = {
        "account_id": str(uid("acc-checking")),
        "date": "2024-03-06",
        "amount": "-80",
        "splits": [{"amount": "-50"}, {"amount": "-20"}],
    }

    with pytest.raises(ToolError, match="add up to -70"):
        await mcp_client.call_tool("create_transactions", {"transactions": [entry]})

    transactions_api.create_transaction.assert_not_called()


async def test_create_transactions_refuses_an_empty_list(
    transactions_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    with pytest.raises(ToolError, match="at least one transaction"):
        await mcp_client.call_tool("create_transactions", {"transactions": []})

    transactions_api.create_transaction.assert_not_called()


async def test_delete_transaction_returns_the_deleted_transaction(
    mock_repository: MagicMock,
    transactions_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    transactions_api.delete_transaction.return_value = transaction_response(
        create_ynab_transaction(id="txn-1", payee_name="Kroger", deleted=True)
    )

    result = await mcp_client.call_tool(
        "delete_transaction", {"transaction_id": "txn-1"}
    )

    transaction = extract_response_data(result)
    assert transaction["id"] == "txn-1"
    assert transaction["payee_name"] == "Kroger"
    transactions_api.delete_transaction.assert_called_once_with("test_plan_id", "txn-1")
    mock_repository.mark_stale.assert_called_once_with(*CHANGED_BY_TRANSACTIONS)


async def test_import_transactions_reports_what_came_in(
    mock_repository: MagicMock,
    transactions_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    transactions_api.import_transactions.return_value = ynab.TransactionsImportResponse(
        data=ynab.TransactionsImportResponseData(
            transaction_ids=["txn-bank-1", "txn-bank-2"]
        )
    )

    result = await mcp_client.call_tool("import_transactions", {})

    assert extract_response_data(result) == {
        "imported_count": 2,
        "transaction_ids": ["txn-bank-1", "txn-bank-2"],
    }
    transactions_api.import_transactions.assert_called_once_with("test_plan_id")
    mock_repository.mark_stale.assert_called_once_with(*CHANGED_BY_TRANSACTIONS)
