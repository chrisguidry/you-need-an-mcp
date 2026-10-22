"""
Test the category and category group tools.
"""

from datetime import date
from typing import Any
from unittest.mock import MagicMock
from uuid import UUID

import pytest
import ynab
from assertions import assert_pagination_info, extract_response_data
from conftest import create_ynab_category, create_ynab_category_group, saved_category
from fastmcp.client import Client, FastMCPTransport
from ids import uid


async def test_list_categories_excludes_hidden_and_deleted_categories(
    mock_repository: MagicMock, mcp_client: Client[FastMCPTransport]
) -> None:
    mock_repository.get_category_groups.return_value = [
        create_ynab_category_group(
            categories=[
                create_ynab_category(id=uid("cat-groceries"), name="Groceries"),
                create_ynab_category(id=uid("cat-hidden"), name="Hidden", hidden=True),
                create_ynab_category(id=uid("cat-gone"), name="Gone", deleted=True),
            ]
        )
    ]

    result = await mcp_client.call_tool("list_categories", {})

    categories = extract_response_data(result)["categories"]
    assert [category["name"] for category in categories] == ["Groceries"]


async def test_list_categories_excludes_deleted_groups(
    mock_repository: MagicMock, mcp_client: Client[FastMCPTransport]
) -> None:
    mock_repository.get_category_groups.return_value = [
        create_ynab_category_group(
            id=uid("group-bills"),
            categories=[create_ynab_category(name="Rent")],
        ),
        create_ynab_category_group(
            id=uid("group-gone"),
            deleted=True,
            categories=[create_ynab_category(name="Old Hobby")],
        ),
    ]

    result = await mcp_client.call_tool("list_categories", {})

    categories = extract_response_data(result)["categories"]
    assert [category["name"] for category in categories] == ["Rent"]


async def test_list_categories_names_each_category_group(
    mock_repository: MagicMock, mcp_client: Client[FastMCPTransport]
) -> None:
    mock_repository.get_category_groups.return_value = [
        create_ynab_category_group(
            name="Monthly Bills", categories=[create_ynab_category(name="Rent")]
        ),
        create_ynab_category_group(
            name="Everyday", categories=[create_ynab_category(name="Groceries")]
        ),
    ]

    result = await mcp_client.call_tool("list_categories", {})

    categories = extract_response_data(result)["categories"]
    assert [
        (category["category_group_name"], category["name"]) for category in categories
    ] == [("Monthly Bills", "Rent"), ("Everyday", "Groceries")]


async def test_list_categories_reports_amounts_and_target_in_currency(
    mock_repository: MagicMock, mcp_client: Client[FastMCPTransport]
) -> None:
    vacation = create_ynab_category(
        id=uid("cat-vacation"),
        name="Vacation",
        category_group_id=uid("group-savings"),
        note="Beach trip",
        budgeted=150_000,
        activity=-12_500,
        balance=437_500,
        goal_type="TBD",
        goal_target=1_200_000,
        goal_percentage_complete=36,
        goal_under_funded=100_000,
        goal_overall_left=762_500,
    ).model_copy(update={"goal_target_date": date(2025, 6, 1)})
    mock_repository.get_category_groups.return_value = [
        create_ynab_category_group(
            id=uid("group-savings"), name="Savings", categories=[vacation]
        )
    ]

    result = await mcp_client.call_tool("list_categories", {})

    assert extract_response_data(result)["categories"] == [
        {
            "id": str(uid("cat-vacation")),
            "name": "Vacation",
            "category_group_id": str(uid("group-savings")),
            "category_group_name": "Savings",
            "internal": False,
            "note": "Beach trip",
            "assigned": "150",
            "activity": "-12.5",
            "available": "437.5",
            "target_type": "TBD",
            "target_amount": "1200",
            "target_date": "2025-06-01",
            "target_percentage_complete": 36,
            "target_underfunded": "100",
            "target_overall_left": "762.5",
        }
    ]


async def test_list_categories_marks_internal_categories(
    mock_repository: MagicMock, mcp_client: Client[FastMCPTransport]
) -> None:
    mock_repository.get_category_groups.return_value = [
        create_ynab_category_group(
            name="Internal Master Category",
            categories=[
                create_ynab_category(name="Inflow: Ready to Assign", internal=True),
                create_ynab_category(name="Groceries"),
            ],
        )
    ]

    result = await mcp_client.call_tool("list_categories", {})

    categories = extract_response_data(result)["categories"]
    assert [(category["name"], category["internal"]) for category in categories] == [
        ("Inflow: Ready to Assign", True),
        ("Groceries", False),
    ]


async def test_list_categories_pages_through_categories(
    mock_repository: MagicMock, mcp_client: Client[FastMCPTransport]
) -> None:
    mock_repository.get_category_groups.return_value = [
        create_ynab_category_group(
            categories=[
                create_ynab_category(id=uid(f"cat-{index}"), name=f"Category {index}")
                for index in range(5)
            ]
        )
    ]

    result = await mcp_client.call_tool("list_categories", {"limit": 2, "offset": 2})

    response = extract_response_data(result)
    names = [category["name"] for category in response["categories"]]
    assert names == ["Category 2", "Category 3"]
    assert_pagination_info(
        response["pagination"], total_count=5, limit=2, offset=2, has_more=True
    )


async def test_list_category_groups_totals_visible_categories(
    mock_repository: MagicMock, mcp_client: Client[FastMCPTransport]
) -> None:
    mock_repository.get_category_groups.return_value = [
        create_ynab_category_group(
            id=uid("group-everyday"),
            name="Everyday",
            categories=[
                create_ynab_category(budgeted=300_000, activity=-120_000, balance=0),
                create_ynab_category(budgeted=50_500, activity=-20_000, balance=30_500),
                create_ynab_category(budgeted=99_000, balance=99_000, hidden=True),
                create_ynab_category(budgeted=88_000, balance=88_000, deleted=True),
            ],
        )
    ]

    result = await mcp_client.call_tool("list_category_groups", {})

    assert result.structured_content == {
        "result": [
            {
                "id": str(uid("group-everyday")),
                "name": "Everyday",
                "hidden": False,
                "internal": False,
                "category_count": 2,
                "total_assigned": "350.5",
                "total_activity": "-140",
                "total_available": "30.5",
            }
        ]
    }


async def test_list_category_groups_excludes_deleted_groups(
    mock_repository: MagicMock, mcp_client: Client[FastMCPTransport]
) -> None:
    mock_repository.get_category_groups.return_value = [
        create_ynab_category_group(name="Everyday"),
        create_ynab_category_group(name="Gone", deleted=True),
    ]

    result = await mcp_client.call_tool("list_category_groups", {})

    assert result.structured_content is not None
    groups = result.structured_content["result"]
    assert [group["name"] for group in groups] == ["Everyday"]


async def test_create_category(
    mock_repository: MagicMock,
    categories_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    pets = create_ynab_category(
        id=uid("cat-pets"),
        name="Pets",
        category_group_id=uid("group-everyday"),
        budgeted=0,
        activity=0,
        balance=0,
    )
    categories_api.create_category.return_value = saved_category(pets)
    mock_repository.get_category_groups.return_value = [
        create_ynab_category_group(
            id=uid("group-everyday"), name="Everyday", categories=[pets]
        )
    ]

    result = await mcp_client.call_tool(
        "create_category",
        {"name": "Pets", "category_group_id": str(uid("group-everyday"))},
    )

    category = extract_response_data(result)
    assert category["id"] == str(uid("cat-pets"))
    assert category["category_group_name"] == "Everyday"
    plan_id, wrapper = categories_api.create_category.call_args.args
    assert plan_id == "test_plan_id"
    assert wrapper.category.to_dict() == {
        "name": "Pets",
        "category_group_id": uid("group-everyday"),
    }
    mock_repository.mark_stale.assert_called_once_with("category_groups")


async def test_create_category_with_target_sends_it_in_milliunits(
    mock_repository: MagicMock,
    categories_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    categories_api.create_category.return_value = saved_category(
        create_ynab_category(goal_type="NEED", goal_target=125_500)
    )
    mock_repository.get_category_groups.return_value = []

    result = await mcp_client.call_tool(
        "create_category",
        {
            "name": "Pet Food",
            "category_group_id": str(uid("group-everyday")),
            "note": "Kibble and treats",
            "target_amount": "125.50",
            "target_needs_whole_amount": True,
            "target_frequency": "monthly",
        },
    )

    category = extract_response_data(result)
    assert (category["target_type"], category["target_amount"]) == ("NEED", "125.5")
    sent = categories_api.create_category.call_args.args[1].category
    assert sent.to_dict() == {
        "name": "Pet Food",
        "category_group_id": uid("group-everyday"),
        "note": "Kibble and treats",
        "goal_target": 125_500,
        "goal_needs_whole_amount": True,
        "goal_frequency": "monthly",
    }


@pytest.mark.parametrize(
    ("arguments", "sent"),
    [
        ({"name": "Food"}, {"name": "Food"}),
        ({"note": "Weekly shop"}, {"note": "Weekly shop"}),
        (
            {"category_group_id": str(uid("group-bills"))},
            {"category_group_id": uid("group-bills")},
        ),
        ({"target_amount": "200"}, {"goal_target": 200_000}),
        ({"target_amount": "0"}, {"goal_target": 0}),
        ({"target_date": "2025-06-01"}, {"goal_target_date": date(2025, 6, 1)}),
        ({"target_needs_whole_amount": False}, {"goal_needs_whole_amount": False}),
        ({"target_frequency": "weekly"}, {"goal_frequency": "weekly"}),
    ],
)
async def test_update_category_sends_only_the_fields_given(
    mock_repository: MagicMock,
    categories_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
    arguments: dict[str, Any],
    sent: dict[str, Any],
) -> None:
    categories_api.update_category.return_value = saved_category(
        create_ynab_category(id=uid("cat-groceries"))
    )
    mock_repository.get_category_groups.return_value = []

    await mcp_client.call_tool(
        "update_category", {"category_id": str(uid("cat-groceries")), **arguments}
    )

    plan_id, category_id, wrapper = categories_api.update_category.call_args.args
    assert (plan_id, category_id) == ("test_plan_id", str(uid("cat-groceries")))
    assert wrapper.category.to_dict() == sent


async def test_update_category_returns_the_category_with_its_group_name(
    mock_repository: MagicMock,
    categories_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    food = create_ynab_category(
        id=uid("cat-groceries"), name="Food", category_group_id=uid("group-everyday")
    )
    categories_api.update_category.return_value = saved_category(food)
    mock_repository.get_category_groups.return_value = [
        create_ynab_category_group(
            id=uid("group-everyday"), name="Everyday", categories=[food]
        )
    ]

    result = await mcp_client.call_tool(
        "update_category", {"category_id": str(uid("cat-groceries")), "name": "Food"}
    )

    category = extract_response_data(result)
    assert (category["name"], category["category_group_name"]) == ("Food", "Everyday")
    mock_repository.mark_stale.assert_called_once_with("category_groups")


def saved_category_group(id: UUID, name: str) -> ynab.SaveCategoryGroupResponse:
    """Wrap a category group the way YNAB answers a create or rename."""
    return ynab.SaveCategoryGroupResponse(
        data=ynab.SaveCategoryGroupResponseData(
            category_group=ynab.CategoryGroup(
                id=id, name=name, hidden=False, internal=False, deleted=False
            ),
            server_knowledge=1,
        )
    )


async def test_create_category_group(
    mock_repository: MagicMock,
    categories_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    categories_api.create_category_group.return_value = saved_category_group(
        uid("group-kids"), "Kids"
    )

    result = await mcp_client.call_tool("create_category_group", {"name": "Kids"})

    assert extract_response_data(result) == {
        "id": str(uid("group-kids")),
        "name": "Kids",
    }
    assert categories_api.create_category_group.call_args.args == (
        "test_plan_id",
        ynab.PostCategoryGroupWrapper(
            category_group=ynab.SaveCategoryGroup(name="Kids")
        ),
    )
    mock_repository.mark_stale.assert_called_once_with("category_groups")


async def test_rename_category_group(
    mock_repository: MagicMock,
    categories_api: MagicMock,
    mcp_client: Client[FastMCPTransport],
) -> None:
    categories_api.update_category_group.return_value = saved_category_group(
        uid("group-kids"), "Children"
    )

    result = await mcp_client.call_tool(
        "rename_category_group",
        {"category_group_id": str(uid("group-kids")), "name": "Children"},
    )

    assert extract_response_data(result) == {
        "id": str(uid("group-kids")),
        "name": "Children",
    }
    assert categories_api.update_category_group.call_args.args == (
        "test_plan_id",
        str(uid("group-kids")),
        ynab.PatchCategoryGroupWrapper(
            category_group=ynab.SaveCategoryGroup(name="Children")
        ),
    )
    mock_repository.mark_stale.assert_called_once_with("category_groups")
