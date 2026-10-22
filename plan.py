"""
The plan itself: its name, the months it covers, and how it formats money.

This server works on one plan, the one YNAB_PLAN names.
"""

from __future__ import annotations

import datetime
from collections.abc import Callable

import ynab
from fastmcp.dependencies import Shared
from fastmcp.tools import tool
from pydantic import BaseModel, Field

from effects import READ, READS
from repository import YNABRepository, plan_repository


class CurrencyFormat(BaseModel):
    """How the plan writes amounts of money."""

    iso_code: str = Field(..., description="ISO 4217 currency code, such as USD")
    example_format: str = Field(..., description="An example amount, as shown")
    decimal_digits: int = Field(..., description="Digits after the decimal point")
    currency_symbol: str = Field(..., description="Currency symbol, such as $")
    symbol_first: bool = Field(..., description="Whether the symbol comes first")


class Plan(BaseModel):
    """The plan this server works on."""

    id: str = Field(..., description="The plan's ID, as configured")
    name: str | None = Field(None, description="The plan's name")
    first_month: datetime.date | None = Field(None, description="Earliest month")
    last_month: datetime.date | None = Field(None, description="Latest month")
    last_modified_on: datetime.datetime | None = Field(
        None, description="When anything in the plan last changed"
    )
    currency_format: CurrencyFormat = Field(
        ..., description="How the plan writes amounts of money"
    )
    date_format: str = Field(..., description="How the plan writes dates")


@tool(title="Get plan", tags={"plan", READ}, annotations=READS)
def get_plan(repository: YNABRepository = Shared(plan_repository)) -> Plan:
    """Get the plan's name, the months it covers, and its currency and date
    formats.  Use the currency format to write amounts the way the user sees
    them in YNAB.

    Returns:
        Plan with its name, months, and formats
    """
    with repository.api() as api_client:
        plans_api = ynab.PlansApi(api_client)
        settings = plans_api.get_plan_settings_by_id(repository.plan_id).data.settings
        summaries = plans_api.get_plans().data.plans

    summary = next((s for s in summaries if str(s.id) == repository.plan_id), None)
    currency = settings.currency_format
    return Plan(
        id=repository.plan_id,
        name=summary.name if summary else None,
        first_month=summary.first_month if summary else None,
        last_month=summary.last_month if summary else None,
        last_modified_on=summary.last_modified_on if summary else None,
        currency_format=CurrencyFormat(
            iso_code=currency.iso_code,
            example_format=currency.example_format,
            decimal_digits=currency.decimal_digits,
            currency_symbol=currency.currency_symbol,
            symbol_first=currency.symbol_first,
        ),
        date_format=settings.date_format.format,
    )


TOOLS: list[Callable[..., object]] = [get_plan]
