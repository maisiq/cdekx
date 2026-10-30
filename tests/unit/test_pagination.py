"""Тесты пагинатора."""

from __future__ import annotations

from typing import Any

import pytest

from cdekx import Paginator
from cdekx.models.base import RootEntity


def make_fetcher(pages: list[list[dict[str, Any]]]) -> Any:
    """Создать фейковый загрузчик страниц, запоминающий запросы."""
    calls: list[dict[str, Any]] = []

    async def fetch(params: Any) -> list[dict[str, Any]]:
        calls.append(dict(params))
        return pages[params["page"]] if params["page"] < len(pages) else []

    fetch.calls = calls  # type: ignore[attr-defined]
    return fetch


async def test_iterates_all_pages() -> None:
    fetcher = make_fetcher(
        [
            [{"uuid": f"u{i}"} for i in range(3)],
            [{"uuid": f"u{i}"} for i in range(3, 5)],
        ]
    )
    paginator: Paginator[RootEntity] = Paginator(fetch=fetcher, model=RootEntity, page_size=3)

    uuids = [item.uuid async for item in paginator]

    assert uuids == ["u0", "u1", "u2", "u3", "u4"]
    assert paginator.pages_loaded == 2
    assert paginator.items_seen == 5
    assert paginator.exhausted


async def test_page_and_size_params_are_passed() -> None:
    fetcher = make_fetcher([[{"uuid": "u1"}]])
    paginator: Paginator[RootEntity] = Paginator(
        fetch=fetcher, model=RootEntity, page_size=50, start_page=2, params={"country_code": "RU"}
    )

    await paginator.collect()

    assert fetcher.calls == [{"country_code": "RU", "page": 2, "size": 50}]


async def test_empty_first_page_stops_immediately() -> None:
    fetcher = make_fetcher([[]])
    paginator: Paginator[RootEntity] = Paginator(fetch=fetcher, model=RootEntity, page_size=10)

    assert await paginator.collect() == []
    assert paginator.pages_loaded == 1


async def test_max_pages_limit_is_respected() -> None:
    full = [{"uuid": f"u{i}"} for i in range(10)]
    fetcher = make_fetcher([full, full, full])
    paginator: Paginator[RootEntity] = Paginator(
        fetch=fetcher, model=RootEntity, page_size=10, max_pages=2
    )

    items = await paginator.collect()

    assert len(items) == 20
    assert paginator.pages_loaded == 2


async def test_invalid_page_size_rejected() -> None:
    with pytest.raises(ValueError, match="page_size"):
        Paginator(fetch=make_fetcher([[]]), model=RootEntity, page_size=0)
    with pytest.raises(ValueError, match="page_size"):
        Paginator(fetch=make_fetcher([[]]), model=RootEntity, page_size=1001)


async def test_invalid_max_pages_rejected() -> None:
    with pytest.raises(ValueError, match="max_pages"):
        Paginator(fetch=make_fetcher([[]]), model=RootEntity, page_size=10, max_pages=0)


async def test_unwraps_entity_envelope() -> None:
    """СДЭК может отдать список как {'entities': [...]} — пагинатор это понимает."""

    async def fetch(params: Any) -> dict[str, Any]:
        if params["page"] == 0:
            return {"entities": [{"uuid": "u1"}]}
        return {"entities": []}

    paginator: Paginator[RootEntity] = Paginator(fetch=fetch, model=RootEntity, page_size=1)
    assert [item.uuid async for item in paginator] == ["u1"]


async def test_reusable_iteration_stops_after_exhaustion() -> None:
    fetcher = make_fetcher([[{"uuid": "u1"}]])
    paginator: Paginator[RootEntity] = Paginator(fetch=fetcher, model=RootEntity, page_size=1)

    first = await paginator.collect()
    second = await paginator.collect()

    assert len(first) == 1
    assert second == []
