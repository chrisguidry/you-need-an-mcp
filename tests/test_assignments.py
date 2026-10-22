"""
Test the tools that assign money to categories and move it between them.
"""

import json
from datetime import UTC, date, datetime
from typing import Any
from unittest.mock import MagicMock
from uuid import UUID

import pytest
import ynab
from assertions import assert_pagination_info, extract_response_data
from conftest import create_ynab_category, saved_category
from fastmcp.client import Client, FastMCPTransport
from fastmcp.exceptions import ToolError
from ids import uid


@pytest.fixture
def month_categories(categories_api: MagicMock) -> dict[str, ynab.Category]:
    """Answer category lookups and changes the way YNAB does for one month.

    A test puts categories in the returned dict by ID.  A lookup returns the
    category, and a change returns it with the new assigned amount and its
    available amount moved by the same difference.
    """
    categories: dict[str, ynab.Category] = {}

    def look_up(plan_id: str, month: date, category_id: str) -> ynab.CategoryResponse:
        return ynab.CategoryResponse(
            data=ynab.CategoryResponseData(category=categories[category_id])
        )

    def change(
        plan_id: str,
        month: date,
        category_id: str,
        wrapper: ynab.PatchMonthCategoryWrapper,
    ) -> ynab.SaveCategoryResponse:
        category = categories[category_id]
        assigned = wrapper.category.budgeted
        available = category.balance + assigned - category.budgeted
        return saved_category(
            category.model_copy(update={"budgeted": assigned, "balance": available})
        )

    categories_api.get_month_category_by_id.side_effect = look_up
    categories_api.update_month_category.side_effect = change
    return categories


def sent_assignments(categories_api: MagicMock) -> list[tuple[str, int]]:
    """The category ID and assigned milliunits of each change sent to YNAB."""
    return [
        (call.args[2], call.args[3].category.budgeted)
        for call in categories_api.update_month_category.call_args_list
    ]


@pytest.mark.parametrize(
    ("amount", "assigned_after", "available_after", "sent"),
    [
        ("100", "350", "160", 350_000),
        ("-75.50", "174.5", "-15.5", 174_500),
    ],
)
async def test_assign_money_adds_to_the_assigned_amount(
    mock_repository: MagicMock,
    categories_api: MagicMock,
    month_categories: dict[str, ynab.Category],
    mcp_client: Client[FastMCPTransport],
    amount: str,
    assigned_after: str,
    available_after: str,
    sent: int,
) -> None:
    month_categories[str(uid("cat-groceries"))] = create_ynab_category(
        id=uid("cat-groceries"), name="Groceries", budgeted=250_000, balance=60_000
    )

    result = await mcp_client.call_tool(
        "assign_money",
        {
            "category_id": str(uid("cat-groceries")),
            "amount": amount,
            "month": "2024-03-10",
        },
    )

    assert extract_response_data(result) == {
        "changes": [
            {
                "category_id": str(uid("cat-groceries")),
                "category_name": "Groceries",
                "month": "2024-03-01",
                "assigned_before": "250",
                "assigned_after": assigned_after,
                "available_after": available_after,
            }
        ]
    }
    assert categories_api.update_month_category.call_args.args == (
        "test_plan_id",
        date(2024, 3, 1),
        str(uid("cat-groceries")),
        ynab.PatchMonthCategoryWrapper(category=ynab.SaveMonthCategory(budgeted=sent)),
    )
    mock_repository.mark_stale.assert_called_once_with("category_groups")


async def test_set_assigned_replaces_the_assigned_amount(
    categories_api: MagicMock,
    month_categories: dict[str, ynab.Category],
    mcp_client: Client[FastMCPTransport],
) -> None:
    month_categories[str(uid("cat-groceries"))] = create_ynab_category(
        id=uid("cat-groceries"), name="Groceries", budgeted=250_000, balance=60_000
    )

    result = await mcp_client.call_tool(
        "set_assigned",
        {
            "category_id": str(uid("cat-groceries")),
            "amount": "80",
            "month": "2024-03-01",
        },
    )

    change = extract_response_data(result)["changes"][0]
    assert (change["assigned_before"], change["assigned_after"]) == ("250", "80")
    assert change["available_after"] == "-110"
    assert sent_assignments(categories_api) == [(str(uid("cat-groceries")), 80_000)]


@pytest.fixture
def groceries_and_dining(month_categories: dict[str, ynab.Category]) -> None:
    month_categories[str(uid("cat-groceries"))] = create_ynab_category(
        id=uid("cat-groceries"), name="Groceries", budgeted=300_000, balance=100_000
    )
    month_categories[str(uid("cat-dining"))] = create_ynab_category(
        id=uid("cat-dining"), name="Dining Out", budgeted=50_000, balance=-25_000
    )


def a_move(amount: str, **overrides: Any) -> dict[str, Any]:
    """Arguments to move an amount from groceries to dining out in March."""
    return {
        "from_category_id": str(uid("cat-groceries")),
        "to_category_id": str(uid("cat-dining")),
        "amount": amount,
        "month": "2024-03-01",
        **overrides,
    }


@pytest.mark.usefixtures("groceries_and_dining")
async def test_move_money_takes_from_one_category_and_gives_to_the_other(
    categories_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    result = await mcp_client.call_tool("move_money", a_move("25"))

    changes = extract_response_data(result)["changes"]
    assert [
        (
            change["category_name"],
            change["assigned_before"],
            change["assigned_after"],
            change["available_after"],
        )
        for change in changes
    ] == [
        ("Groceries", "300", "275", "75"),
        ("Dining Out", "50", "75", "0"),
    ]
    assert sent_assignments(categories_api) == [
        (str(uid("cat-groceries")), 275_000),
        (str(uid("cat-dining")), 75_000),
    ]


@pytest.mark.parametrize("amount", ["0", "-5"])
@pytest.mark.usefixtures("groceries_and_dining")
async def test_move_money_rejects_an_amount_that_is_not_positive(
    categories_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
    amount: str,
) -> None:
    with pytest.raises(ToolError, match="amount must be greater than zero"):
        await mcp_client.call_tool("move_money", a_move(amount))

    assert sent_assignments(categories_api) == []


@pytest.mark.usefixtures("groceries_and_dining")
async def test_move_money_rejects_moving_to_the_same_category(
    categories_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    with pytest.raises(ToolError, match="must differ"):
        await mcp_client.call_tool(
            "move_money", a_move("25", to_category_id=str(uid("cat-groceries")))
        )

    assert sent_assignments(categories_api) == []


def a_rejection(detail: str) -> ynab.ApiException:
    """A YNAB API error with the detail YNAB writes for the caller."""
    return ynab.ApiException(
        status=400,
        reason="Bad Request",
        body=json.dumps(
            {"error": {"id": "400", "name": "bad_request", "detail": detail}}
        ),
    )


@pytest.mark.usefixtures("groceries_and_dining")
async def test_move_money_puts_the_first_category_back_when_the_second_fails(
    categories_api: MagicMock,
    month_categories: dict[str, ynab.Category],
    mcp_client: Client[FastMCPTransport],
) -> None:
    groceries = month_categories[str(uid("cat-groceries"))]
    categories_api.update_month_category.side_effect = [
        saved_category(groceries.model_copy(update={"budgeted": 275_000})),
        a_rejection("category is locked"),
        saved_category(groceries),
    ]

    with pytest.raises(ToolError, match="YNAB returned 400: category is locked"):
        await mcp_client.call_tool("move_money", a_move("25"))

    assert sent_assignments(categories_api) == [
        (str(uid("cat-groceries")), 275_000),
        (str(uid("cat-dining")), 75_000),
        (str(uid("cat-groceries")), 300_000),
    ]


def create_ynab_money_movement(
    *,
    name: str,
    amount: int = 10_000,
    moved_at: datetime | None = None,
    from_category_id: UUID | None = None,
    to_category_id: UUID | None = None,
    note: str | None = None,
) -> ynab.MoneyMovement:
    """Create a YNAB money movement for testing with sensible defaults."""
    return ynab.MoneyMovement(
        id=uid(f"movement-{name}"),
        month=date(2024, 3, 1),
        moved_at=moved_at,
        note=note,
        from_category_id=from_category_id,
        to_category_id=to_category_id,
        amount=amount,
    )


def money_movements(*movements: ynab.MoneyMovement) -> ynab.MoneyMovementsResponse:
    """Wrap money movements the way YNAB answers a list of them."""
    return ynab.MoneyMovementsResponse(
        data=ynab.MoneyMovementsResponseData(
            money_movements=list(movements), server_knowledge=1
        )
    )


@pytest.fixture
def plan_categories(mock_repository: MagicMock) -> None:
    mock_repository.get_category_groups.return_value = [
        ynab.CategoryGroupWithCategories(
            id=uid("group-everyday"),
            name="Everyday",
            hidden=False,
            internal=False,
            deleted=False,
            categories=[
                create_ynab_category(id=uid("cat-groceries"), name="Groceries"),
                create_ynab_category(id=uid("cat-dining"), name="Dining Out"),
            ],
        )
    ]


@pytest.mark.usefixtures("plan_categories")
async def test_list_money_movements_for_one_month(
    money_movements_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    money_movements_api.get_money_movements_by_month.return_value = money_movements(
        create_ynab_money_movement(
            name="cover-dining",
            amount=25_500,
            moved_at=datetime(2024, 3, 12, 18, 30, tzinfo=UTC),
            from_category_id=uid("cat-groceries"),
            to_category_id=uid("cat-dining"),
            note="Birthday dinner",
        )
    )

    result = await mcp_client.call_tool("list_money_movements", {"month": "2024-03-20"})

    assert extract_response_data(result)["money_movements"] == [
        {
            "moved_at": "2024-03-12T18:30:00Z",
            "month": "2024-03-01",
            "amount": "25.5",
            "from_category_id": str(uid("cat-groceries")),
            "from_category_name": "Groceries",
            "to_category_id": str(uid("cat-dining")),
            "to_category_name": "Dining Out",
            "note": "Birthday dinner",
        }
    ]
    assert money_movements_api.get_money_movements_by_month.call_args.args == (
        "test_plan_id",
        date(2024, 3, 1),
    )
    money_movements_api.get_money_movements.assert_not_called()


@pytest.mark.usefixtures("plan_categories")
async def test_list_money_movements_for_every_month(
    money_movements_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    money_movements_api.get_money_movements.return_value = money_movements(
        create_ynab_money_movement(name="assign", to_category_id=uid("cat-groceries"))
    )

    result = await mcp_client.call_tool("list_money_movements", {"month": None})

    movements = extract_response_data(result)["money_movements"]
    assert [movement["to_category_name"] for movement in movements] == ["Groceries"]
    assert money_movements_api.get_money_movements.call_args.args == ("test_plan_id",)
    money_movements_api.get_money_movements_by_month.assert_not_called()


@pytest.mark.usefixtures("plan_categories")
async def test_list_money_movements_names_ready_to_assign_and_unknown_categories(
    money_movements_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    money_movements_api.get_money_movements_by_month.return_value = money_movements(
        create_ynab_money_movement(
            name="assign", from_category_id=None, to_category_id=uid("cat-groceries")
        ),
        create_ynab_money_movement(
            name="unassign", from_category_id=uid("cat-gone"), to_category_id=None
        ),
    )

    result = await mcp_client.call_tool("list_money_movements", {})

    movements = extract_response_data(result)["money_movements"]
    assert [
        (movement["from_category_name"], movement["to_category_name"])
        for movement in movements
    ] == [
        ("Ready to Assign", "Groceries"),
        ("Unknown category", "Ready to Assign"),
    ]


@pytest.mark.usefixtures("plan_categories")
async def test_list_money_movements_lists_the_most_recent_first(
    money_movements_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    money_movements_api.get_money_movements.return_value = money_movements(
        create_ynab_money_movement(
            name="first", moved_at=datetime(2024, 3, 1, tzinfo=UTC)
        ),
        create_ynab_money_movement(name="undated"),
        create_ynab_money_movement(
            name="latest", moved_at=datetime(2024, 3, 20, tzinfo=UTC)
        ),
        create_ynab_money_movement(
            name="middle", moved_at=datetime(2024, 3, 10, tzinfo=UTC)
        ),
    )

    result = await mcp_client.call_tool("list_money_movements", {"month": None})

    movements = extract_response_data(result)["money_movements"]
    assert [movement["moved_at"] for movement in movements] == [
        "2024-03-20T00:00:00Z",
        "2024-03-10T00:00:00Z",
        "2024-03-01T00:00:00Z",
        None,
    ]


@pytest.mark.usefixtures("plan_categories")
async def test_list_money_movements_pages_through_movements(
    money_movements_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    money_movements_api.get_money_movements.return_value = money_movements(
        *(
            create_ynab_money_movement(
                name=f"day-{day}",
                amount=day * 1_000,
                moved_at=datetime(2024, 3, day, tzinfo=UTC),
            )
            for day in range(1, 6)
        )
    )

    result = await mcp_client.call_tool(
        "list_money_movements", {"month": None, "limit": 2, "offset": 1}
    )

    response = extract_response_data(result)
    amounts = [movement["amount"] for movement in response["money_movements"]]
    assert amounts == ["4", "3"]
    assert_pagination_info(
        response["pagination"], total_count=5, limit=2, offset=1, has_more=True
    )
