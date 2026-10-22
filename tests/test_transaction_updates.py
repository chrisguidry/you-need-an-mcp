"""
Test the tool that changes existing transactions.
"""

from datetime import date
from typing import Any
from unittest.mock import MagicMock

import pytest
import ynab
from conftest import create_ynab_account, create_ynab_transaction
from fastmcp.client import Client, FastMCPTransport
from fastmcp.exceptions import ToolError
from ids import uid

from transaction_entry import CHANGED_BY_TRANSACTIONS


@pytest.fixture
def updated(mock_repository: MagicMock, transactions_api: MagicMock) -> None:
    mock_repository.get_accounts.return_value = [
        create_ynab_account(
            id=uid("acc-savings"), transfer_payee_id=uid("payee-to-savings")
        )
    ]
    transactions_api.update_transactions.return_value = ynab.SaveTransactionsResponse(
        data=ynab.SaveTransactionsResponseData(
            transaction_ids=["txn-1"],
            transactions=[create_ynab_transaction(id="txn-1", approved=True)],
            server_knowledge=1,
        )
    )


async def update(
    mcp_client: Client[FastMCPTransport],
    transactions_api: MagicMock,
    *changes: dict[str, Any],
) -> list[dict[str, Any]]:
    """Send the changes, and return each update as YNAB receives it."""
    await mcp_client.call_tool("update_transactions", {"changes": list(changes)})
    sent = transactions_api.update_transactions.call_args.args[1].transactions
    return [saved.to_dict() for saved in sent]


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ({"approved": True}, {"approved": True}),
        ({"approved": False}, {"approved": False}),
        (
            {"account_id": str(uid("acc-savings"))},
            {"account_id": uid("acc-savings")},
        ),
        ({"date": "2024-03-02"}, {"date": date(2024, 3, 2)}),
        ({"amount": "-12.34"}, {"amount": -12_340}),
        ({"payee_id": str(uid("payee-costco"))}, {"payee_id": uid("payee-costco")}),
        ({"payee_name": "Costco"}, {"payee_name": "Costco"}),
        (
            {"transfer_account_id": str(uid("acc-savings"))},
            {"payee_id": uid("payee-to-savings")},
        ),
        (
            {"category_id": str(uid("cat-dining"))},
            {"category_id": uid("cat-dining")},
        ),
        ({"memo": "Team lunch"}, {"memo": "Team lunch"}),
        ({"memo": ""}, {"memo": ""}),
        (
            {"cleared": "reconciled"},
            {"cleared": ynab.TransactionClearedStatus.RECONCILED},
        ),
        ({"flag_color": "green"}, {"flag_color": ynab.TransactionFlagColor.GREEN}),
        ({"clear_flag": True}, {"flag_color": None}),
        (
            {"splits": [{"amount": "-30", "category_id": str(uid("cat-gifts"))}]},
            {
                "subtransactions": [
                    {
                        "amount": -30_000,
                        "category_id": uid("cat-gifts"),
                        "payee_id": None,
                        "payee_name": None,
                        "memo": None,
                    }
                ]
            },
        ),
    ],
)
@pytest.mark.usefixtures("updated")
async def test_update_transactions_sends_only_the_fields_named(
    transactions_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
    change: dict[str, Any],
    expected: dict[str, Any],
) -> None:
    sent = await update(mcp_client, transactions_api, {"id": "txn-1", **change})

    assert sent == [{"id": "txn-1", **expected}]


@pytest.mark.usefixtures("updated")
async def test_update_transactions_sends_every_change_in_one_request(
    transactions_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    sent = await update(
        mcp_client,
        transactions_api,
        {"id": "txn-1", "approved": True, "category_id": str(uid("cat-dining"))},
        {"id": "txn-2", "payee_name": "Costco"},
    )

    assert sent == [
        {"id": "txn-1", "approved": True, "category_id": uid("cat-dining")},
        {"id": "txn-2", "payee_name": "Costco"},
    ]
    assert transactions_api.update_transactions.call_count == 1
    assert transactions_api.update_transactions.call_args.args[0] == "test_plan_id"


@pytest.mark.usefixtures("updated")
async def test_update_transactions_returns_what_ynab_saved(
    mock_repository: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    result = await mcp_client.call_tool(
        "update_transactions", {"changes": [{"id": "txn-1", "approved": True}]}
    )

    saved = result.structured_content
    assert saved is not None
    assert [(txn["id"], txn["approved"]) for txn in saved["result"]] == [
        ("txn-1", True)
    ]
    mock_repository.mark_stale.assert_called_once_with(*CHANGED_BY_TRANSACTIONS)


@pytest.mark.usefixtures("updated")
async def test_update_transactions_refuses_a_transfer_to_an_unknown_account(
    transactions_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    change = {"id": "txn-1", "transfer_account_id": str(uid("acc-missing"))}

    with pytest.raises(ToolError, match="No account"):
        await mcp_client.call_tool("update_transactions", {"changes": [change]})

    transactions_api.update_transactions.assert_not_called()


async def test_update_transactions_refuses_an_empty_list(
    transactions_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    with pytest.raises(ToolError, match="at least one change"):
        await mcp_client.call_tool("update_transactions", {"changes": []})

    transactions_api.update_transactions.assert_not_called()
