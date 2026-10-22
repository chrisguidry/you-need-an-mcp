"""
Test the tools that list, get, create, update, and delete scheduled transactions.
"""

from datetime import date, timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest
import ynab
from assertions import assert_pagination_info, extract_response_data
from conftest import (
    create_ynab_account,
    scheduled_part,
    scheduled_response,
    scheduled_transaction,
)
from fastmcp.client import Client, FastMCPTransport
from fastmcp.exceptions import ToolError
from ids import uid


def scheduled_list(
    *details: ynab.ScheduledTransactionDetail,
) -> ynab.ScheduledTransactionsResponse:
    return ynab.ScheduledTransactionsResponse(
        data=ynab.ScheduledTransactionsResponseData(
            scheduled_transactions=list(details), server_knowledge=1
        )
    )


@pytest.fixture
def bills(scheduled_transactions_api: MagicMock) -> None:
    """Three schedules, out of order, with the rent overdue, and a deleted one."""
    today = date.today()
    scheduled_transactions_api.get_scheduled_transactions.return_value = scheduled_list(
        scheduled_transaction(
            id=uid("st-coffee"),
            date_next=today + timedelta(days=10),
            frequency="weekly",
            amount=-5_000,
            account_id=uid("acc-credit"),
            payee_id=uid("payee-cafe"),
            category_id=uid("cat-dining"),
        ),
        scheduled_transaction(
            id=uid("st-gone"),
            date_next=today + timedelta(days=1),
            deleted=True,
        ),
        scheduled_transaction(
            id=uid("st-paycheck"),
            date_next=today + timedelta(days=20),
            frequency="everyOtherWeek",
            amount=2_000_000,
            payee_id=uid("payee-employer"),
            category_id=uid("cat-income"),
        ),
        scheduled_transaction(
            id=uid("st-rent"),
            date_next=today - timedelta(days=2),
        ),
    )


async def test_list_scheduled_transactions_soonest_first_without_deleted(
    bills: None,
    mcp_client: Client[FastMCPTransport],
) -> None:
    result = await mcp_client.call_tool("list_scheduled_transactions", {})

    response = extract_response_data(result)
    ids = [st["id"] for st in response["scheduled_transactions"]]
    assert ids == [str(uid("st-rent")), str(uid("st-coffee")), str(uid("st-paycheck"))]
    assert_pagination_info(response["pagination"], total_count=3, limit=25)


@pytest.mark.parametrize(
    ("filters", "expected"),
    [
        ({"account_id": str(uid("acc-checking"))}, ["st-rent", "st-paycheck"]),
        ({"category_id": str(uid("cat-dining"))}, ["st-coffee"]),
        ({"payee_id": str(uid("payee-employer"))}, ["st-paycheck"]),
        ({"frequency": "weekly"}, ["st-coffee"]),
        ({"upcoming_days": 7}, ["st-rent"]),
        ({"upcoming_days": 10}, ["st-rent", "st-coffee"]),
        ({"min_amount": "0"}, ["st-paycheck"]),
        ({"max_amount": "-10"}, ["st-rent"]),
        ({"min_amount": "-100", "max_amount": "0"}, ["st-coffee"]),
        ({"min_amount": "-5", "max_amount": "-5"}, ["st-coffee"]),
        ({"account_id": str(uid("acc-checking")), "max_amount": "0"}, ["st-rent"]),
        ({"account_id": str(uid("acc-checking")), "upcoming_days": 7}, ["st-rent"]),
        ({"frequency": "weekly", "payee_id": str(uid("payee-landlord"))}, []),
    ],
)
async def test_list_scheduled_transactions_filters(
    bills: None,
    mcp_client: Client[FastMCPTransport],
    filters: dict[str, Any],
    expected: list[str],
) -> None:
    result = await mcp_client.call_tool("list_scheduled_transactions", filters)

    listed = extract_response_data(result)["scheduled_transactions"]
    assert [st["id"] for st in listed] == [str(uid(name)) for name in expected]


async def test_list_scheduled_transactions_pages(
    scheduled_transactions_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    scheduled_transactions_api.get_scheduled_transactions.return_value = scheduled_list(
        *(
            scheduled_transaction(id=uid(f"st-{day}"), date_next=date(2024, 3, day))
            for day in range(1, 6)
        )
    )

    result = await mcp_client.call_tool(
        "list_scheduled_transactions", {"limit": 2, "offset": 2}
    )

    response = extract_response_data(result)
    ids = [st["id"] for st in response["scheduled_transactions"]]
    assert ids == [str(uid("st-3")), str(uid("st-4"))]
    assert_pagination_info(
        response["pagination"], total_count=5, limit=2, offset=2, has_more=True
    )


async def test_get_scheduled_transaction(
    scheduled_transactions_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    scheduled_transactions_api.get_scheduled_transaction_by_id.return_value = (
        scheduled_response(
            scheduled_transaction(
                flag_color=ynab.TransactionFlagColor.RED, flag_name="Bills"
            )
        )
    )

    result = await mcp_client.call_tool(
        "get_scheduled_transaction", {"scheduled_transaction_id": str(uid("st-rent"))}
    )

    assert extract_response_data(result) == {
        "id": str(uid("st-rent")),
        "date_first": "2024-01-01",
        "date_next": "2024-02-01",
        "frequency": "monthly",
        "amount": "-1500",
        "memo": "Rent",
        "flag": "Bills (Red)",
        "account_id": str(uid("acc-checking")),
        "account_name": "Checking",
        "payee_id": str(uid("payee-landlord")),
        "payee_name": "Landlord",
        "category_id": str(uid("cat-rent")),
        "category_name": "Rent",
        "transfer_account_id": None,
        "subtransactions": None,
    }
    scheduled_transactions_api.get_scheduled_transaction_by_id.assert_called_once_with(
        "test_plan_id", str(uid("st-rent"))
    )


async def test_get_scheduled_transaction_shows_live_parts_of_a_split(
    scheduled_transactions_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    scheduled_transactions_api.get_scheduled_transaction_by_id.return_value = (
        scheduled_response(
            scheduled_transaction(
                category_id=None,
                subtransactions=[
                    scheduled_part("water", -40_000),
                    scheduled_part("trash", -25_000, deleted=True),
                    scheduled_part("sewer", -35_500),
                ],
            )
        )
    )

    result = await mcp_client.call_tool(
        "get_scheduled_transaction", {"scheduled_transaction_id": str(uid("st-rent"))}
    )

    parts = extract_response_data(result)["subtransactions"]
    assert [part["id"] for part in parts] == [str(uid("water")), str(uid("sewer"))]
    assert parts[1] == {
        "id": str(uid("sewer")),
        "amount": "-35.5",
        "memo": "sewer",
        "payee_id": None,
        "payee_name": None,
        "category_id": str(uid("cat-sewer")),
        "category_name": "Sewer",
    }


async def test_get_scheduled_transaction_shows_the_other_account_of_a_transfer(
    scheduled_transactions_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    scheduled_transactions_api.get_scheduled_transaction_by_id.return_value = (
        scheduled_response(
            scheduled_transaction(transfer_account_id=uid("acc-savings"))
        )
    )

    result = await mcp_client.call_tool(
        "get_scheduled_transaction", {"scheduled_transaction_id": str(uid("st-rent"))}
    )

    assert extract_response_data(result)["transfer_account_id"] == str(
        uid("acc-savings")
    )


@pytest.fixture
def savings(mock_repository: MagicMock) -> None:
    """A savings account, so that a schedule can transfer money into it."""
    mock_repository.get_accounts.return_value = [
        create_ynab_account(id=uid("acc-checking"), name="Checking"),
        create_ynab_account(
            id=uid("acc-savings"),
            name="Savings",
            transfer_payee_id=uid("payee-to-savings"),
        ),
    ]


async def test_create_scheduled_transaction(
    scheduled_transactions_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    scheduled_transactions_api.create_scheduled_transaction.return_value = (
        scheduled_response(scheduled_transaction(date_next=date(2024, 3, 1)))
    )

    result = await mcp_client.call_tool(
        "create_scheduled_transaction",
        {
            "account_id": str(uid("acc-checking")),
            "date": "2024-03-01",
            "amount": "-1500.00",
            "frequency": "monthly",
            "payee_name": "Landlord",
            "category_id": str(uid("cat-rent")),
            "memo": "Rent",
            "flag_color": "red",
        },
    )

    assert extract_response_data(result)["id"] == str(uid("st-rent"))
    plan_id, wrapper = (
        scheduled_transactions_api.create_scheduled_transaction.call_args.args
    )
    assert plan_id == "test_plan_id"
    assert (
        wrapper.scheduled_transaction
        == ynab.SaveScheduledTransaction.model_validate(
            {
                "account_id": uid("acc-checking"),
                "date": date(2024, 3, 1),
                "amount": -1_500_000,
                "frequency": "monthly",
                "payee_name": "Landlord",
                "category_id": uid("cat-rent"),
                "memo": "Rent",
                "flag_color": "red",
            }
        )
    )


async def test_create_scheduled_transfer_pays_the_other_accounts_transfer_payee(
    savings: None,
    scheduled_transactions_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    scheduled_transactions_api.create_scheduled_transaction.return_value = (
        scheduled_response(
            scheduled_transaction(transfer_account_id=uid("acc-savings"))
        )
    )

    await mcp_client.call_tool(
        "create_scheduled_transaction",
        {
            "account_id": str(uid("acc-checking")),
            "date": "2024-03-01",
            "amount": "-200",
            "frequency": "monthly",
            "transfer_account_id": str(uid("acc-savings")),
        },
    )

    wrapper = scheduled_transactions_api.create_scheduled_transaction.call_args.args[1]
    assert wrapper.scheduled_transaction.payee_id == uid("payee-to-savings")


@pytest.fixture
def rent(scheduled_transactions_api: MagicMock) -> None:
    """The flagged rent schedule in YNAB, and what YNAB returns when it changes."""
    rent = scheduled_transaction(flag_color=ynab.TransactionFlagColor.RED)
    api = scheduled_transactions_api
    api.get_scheduled_transaction_by_id.return_value = scheduled_response(rent)
    api.update_scheduled_transaction.return_value = scheduled_response(rent)


def saved_rent(**changes: object) -> ynab.SaveScheduledTransaction:
    """The rent schedule as an update sends it, with some fields changed."""
    fields: dict[str, object] = {
        "account_id": uid("acc-checking"),
        "date": date(2024, 2, 1),
        "amount": -1_500_000,
        "frequency": "monthly",
        "payee_id": uid("payee-landlord"),
        "category_id": uid("cat-rent"),
        "memo": "Rent",
        "flag_color": "red",
    }
    return ynab.SaveScheduledTransaction.model_validate(fields | changes)


@pytest.mark.parametrize(
    ("arguments", "changes"),
    [
        ({}, {}),
        ({"account_id": str(uid("acc-savings"))}, {"account_id": uid("acc-savings")}),
        ({"date": "2024-02-05"}, {"date": date(2024, 2, 5)}),
        ({"amount": "-1600.50"}, {"amount": -1_600_500}),
        ({"amount": "0"}, {"amount": 0}),
        ({"frequency": "yearly"}, {"frequency": "yearly"}),
        ({"category_id": str(uid("cat-home"))}, {"category_id": uid("cat-home")}),
        ({"memo": "Rent and parking"}, {"memo": "Rent and parking"}),
        ({"memo": ""}, {"memo": ""}),
        ({"flag_color": "blue"}, {"flag_color": "blue"}),
        ({"payee_id": str(uid("payee-new"))}, {"payee_id": uid("payee-new")}),
        (
            {"payee_name": "New Landlord"},
            {"payee_id": None, "payee_name": "New Landlord"},
        ),
        (
            {"transfer_account_id": str(uid("acc-savings"))},
            {"payee_id": uid("payee-to-savings")},
        ),
    ],
)
async def test_update_scheduled_transaction_changes_only_the_fields_given(
    rent: None,
    savings: None,
    scheduled_transactions_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
    arguments: dict[str, Any],
    changes: dict[str, object],
) -> None:
    result = await mcp_client.call_tool(
        "update_scheduled_transaction",
        {"scheduled_transaction_id": str(uid("st-rent")), **arguments},
    )

    assert extract_response_data(result)["id"] == str(uid("st-rent"))
    plan_id, scheduled_id, wrapper = (
        scheduled_transactions_api.update_scheduled_transaction.call_args.args
    )
    assert (plan_id, scheduled_id) == ("test_plan_id", str(uid("st-rent")))
    assert wrapper.scheduled_transaction == saved_rent(**changes)


async def test_update_scheduled_transaction_refuses_a_split(
    scheduled_transactions_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    scheduled_transactions_api.get_scheduled_transaction_by_id.return_value = (
        scheduled_response(
            scheduled_transaction(subtransactions=[scheduled_part("water", -40_000)])
        )
    )

    with pytest.raises(ToolError, match="split"):
        await mcp_client.call_tool(
            "update_scheduled_transaction",
            {"scheduled_transaction_id": str(uid("st-rent")), "amount": "-50"},
        )

    scheduled_transactions_api.update_scheduled_transaction.assert_not_called()


async def test_update_scheduled_transaction_ignores_deleted_parts(
    scheduled_transactions_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    rent = scheduled_transaction(
        subtransactions=[scheduled_part("water", -40_000, deleted=True)]
    )
    api = scheduled_transactions_api
    api.get_scheduled_transaction_by_id.return_value = scheduled_response(rent)
    api.update_scheduled_transaction.return_value = scheduled_response(rent)

    await mcp_client.call_tool(
        "update_scheduled_transaction",
        {"scheduled_transaction_id": str(uid("st-rent")), "amount": "-50"},
    )

    wrapper = api.update_scheduled_transaction.call_args.args[2]
    assert wrapper.scheduled_transaction.amount == -50_000


async def test_delete_scheduled_transaction(
    scheduled_transactions_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    scheduled_transactions_api.delete_scheduled_transaction.return_value = (
        scheduled_response(scheduled_transaction(deleted=True))
    )

    result = await mcp_client.call_tool(
        "delete_scheduled_transaction",
        {"scheduled_transaction_id": str(uid("st-rent"))},
    )

    assert extract_response_data(result)["id"] == str(uid("st-rent"))
    scheduled_transactions_api.delete_scheduled_transaction.assert_called_once_with(
        "test_plan_id", str(uid("st-rent"))
    )
