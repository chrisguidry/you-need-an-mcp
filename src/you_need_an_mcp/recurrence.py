"""
When a scheduled transaction happens next.

YNAB stores a scheduled transaction's first date and its frequency.  Every
occurrence is counted from the first date, not from the one before it, so a
monthly schedule that starts on January 31 lands on the last day of February
and then on March 31, instead of drifting to the 28th or 29th.
"""

import calendar
import datetime

DAYS_BETWEEN = {
    "daily": 1,
    "weekly": 7,
    "everyOtherWeek": 14,
    "every4Weeks": 28,
}

MONTHS_BETWEEN = {
    "monthly": 1,
    "everyOtherMonth": 2,
    "every3Months": 3,
    "every4Months": 4,
    "twiceAYear": 6,
    "yearly": 12,
    "everyOtherYear": 24,
}


class UnknownRecurrence(ValueError):
    """A frequency whose dates this module cannot work out."""


def add_months(day: datetime.date, months: int) -> datetime.date:
    """Move a date by whole months, keeping its day where the month allows."""
    month_index = day.month - 1 + months
    year, month = day.year + month_index // 12, month_index % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    return day.replace(year=year, month=month, day=min(day.day, last_day))


def next_occurrence(
    frequency: str, first: datetime.date, after: datetime.date
) -> datetime.date | None:
    """The first occurrence of a schedule that falls after a date.

    Returns None for a schedule that happens only once.  Raises
    UnknownRecurrence for "twiceAMonth", because YNAB does not document which
    two days of the month it picks.
    """
    if frequency == "never":
        return None

    if frequency in DAYS_BETWEEN:
        step = DAYS_BETWEEN[frequency]
        if after < first:
            return first
        periods = (after - first).days // step + 1
        return first + datetime.timedelta(days=periods * step)

    if frequency in MONTHS_BETWEEN:
        step = MONTHS_BETWEEN[frequency]
        periods = 0
        occurrence = first
        while occurrence <= after:
            periods += 1
            occurrence = add_months(first, periods * step)
        return occurrence

    raise UnknownRecurrence(f"Cannot work out the dates of a {frequency} schedule")
