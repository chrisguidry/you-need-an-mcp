"""
Test paging through a list.
"""

import pytest

from pagination import paginate


@pytest.mark.parametrize(
    ("limit", "offset", "page", "has_more"),
    [
        (2, 0, ["a", "b"], True),
        (2, 2, ["c", "d"], True),
        (2, 4, ["e"], False),
        (10, 0, ["a", "b", "c", "d", "e"], False),
        (2, 9, [], False),
    ],
)
def test_paginate(limit: int, offset: int, page: list[str], has_more: bool) -> None:
    items, pagination = paginate(["a", "b", "c", "d", "e"], limit, offset)

    assert items == page
    assert pagination.total_count == 5
    assert (pagination.limit, pagination.offset) == (limit, offset)
    assert pagination.has_more is has_more
