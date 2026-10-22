"""
Test how the next date of a scheduled transaction is worked out.
"""

from datetime import date

import pytest

from recurrence import UnknownRecurrence, add_months, next_occurrence


@pytest.mark.parametrize(
    ("frequency", "first", "after", "expected"),
    [
        ("daily", date(2024, 1, 1), date(2024, 1, 1), date(2024, 1, 2)),
        ("daily", date(2024, 1, 1), date(2024, 1, 5), date(2024, 1, 6)),
        ("weekly", date(2024, 1, 1), date(2024, 1, 1), date(2024, 1, 8)),
        ("weekly", date(2024, 1, 1), date(2024, 1, 10), date(2024, 1, 15)),
        ("everyOtherWeek", date(2024, 1, 1), date(2024, 1, 1), date(2024, 1, 15)),
        ("every4Weeks", date(2024, 1, 1), date(2024, 1, 1), date(2024, 1, 29)),
        ("monthly", date(2024, 1, 15), date(2024, 1, 15), date(2024, 2, 15)),
        ("everyOtherMonth", date(2024, 1, 15), date(2024, 1, 15), date(2024, 3, 15)),
        ("every3Months", date(2024, 1, 15), date(2024, 1, 15), date(2024, 4, 15)),
        ("every4Months", date(2024, 1, 15), date(2024, 1, 15), date(2024, 5, 15)),
        ("twiceAYear", date(2024, 1, 15), date(2024, 1, 15), date(2024, 7, 15)),
        ("yearly", date(2024, 1, 15), date(2024, 1, 15), date(2025, 1, 15)),
        ("everyOtherYear", date(2024, 1, 15), date(2024, 1, 15), date(2026, 1, 15)),
    ],
)
def test_next_occurrence_steps_by_frequency(
    frequency: str, first: date, after: date, expected: date
) -> None:
    assert next_occurrence(frequency, first, after) == expected


def test_next_occurrence_of_a_one_time_schedule_is_none() -> None:
    assert next_occurrence("never", date(2024, 1, 15), date(2024, 1, 15)) is None


@pytest.mark.parametrize(
    ("first", "after", "expected"),
    [
        (date(2023, 1, 31), date(2023, 1, 31), date(2023, 2, 28)),
        (date(2024, 1, 31), date(2024, 1, 31), date(2024, 2, 29)),
        (date(2024, 1, 31), date(2024, 2, 29), date(2024, 3, 31)),
        (date(2024, 1, 31), date(2024, 4, 30), date(2024, 5, 31)),
        (date(2024, 12, 31), date(2024, 12, 31), date(2025, 1, 31)),
    ],
)
def test_monthly_keeps_the_day_of_the_first_date_at_month_end(
    first: date, after: date, expected: date
) -> None:
    assert next_occurrence("monthly", first, after) == expected


@pytest.mark.parametrize(
    ("after", "expected"),
    [
        (date(2024, 2, 29), date(2025, 2, 28)),
        (date(2027, 2, 28), date(2028, 2, 29)),
    ],
)
def test_yearly_from_a_leap_day_returns_to_the_leap_day(
    after: date, expected: date
) -> None:
    assert next_occurrence("yearly", date(2024, 2, 29), after) == expected


@pytest.mark.parametrize(
    "frequency",
    ["daily", "weekly", "every4Weeks", "monthly", "yearly"],
)
def test_next_occurrence_before_the_first_date_is_the_first_date(
    frequency: str,
) -> None:
    assert next_occurrence(frequency, date(2024, 5, 10), date(2024, 4, 1)) == date(
        2024, 5, 10
    )


@pytest.mark.parametrize("frequency", ["twiceAMonth", "fortnightly"])
def test_next_occurrence_refuses_a_frequency_it_cannot_work_out(
    frequency: str,
) -> None:
    with pytest.raises(UnknownRecurrence, match=f"a {frequency} schedule"):
        next_occurrence(frequency, date(2024, 1, 15), date(2024, 1, 15))


@pytest.mark.parametrize(
    ("day", "months", "expected"),
    [
        (date(2024, 1, 15), 1, date(2024, 2, 15)),
        (date(2024, 1, 31), 1, date(2024, 2, 29)),
        (date(2024, 3, 31), 1, date(2024, 4, 30)),
        (date(2024, 11, 30), 2, date(2025, 1, 30)),
        (date(2024, 12, 15), 1, date(2025, 1, 15)),
        (date(2024, 6, 15), 30, date(2026, 12, 15)),
    ],
)
def test_add_months_rolls_over_years_and_clamps_to_month_end(
    day: date, months: int, expected: date
) -> None:
    assert add_months(day, months) == expected
