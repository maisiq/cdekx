"""Asynchronous page traversal (page-based pagination in the CDEK API).

CDEK uses the ``page`` (0-based) and ``size`` (<= 1000) parameters. The API does
not guarantee a header with the total item count, so the paginator relies on the
actual size of the page it received: a page shorter than ``page_size`` is treated
as the last one.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from typing import Any, Generic, Protocol, TypeVar

from pydantic import BaseModel

__all__ = ["PageFetcher", "Paginator"]

ModelT = TypeVar("ModelT", bound=BaseModel)


class PageFetcher(Protocol):
    """Page fetcher protocol: ``params -> raw JSON``."""

    async def __call__(self, params: Mapping[str, Any]) -> Any:
        """Fetch a page by query parameters and return the raw JSON."""
        ...


class Paginator(Generic[ModelT]):
    """Lazy asynchronous iterator over the pages of a list.

    Example:
        >>> async for order in client.orders.paginate(page_size=500):  # doctest: +SKIP
        ...     print(order.uuid)  # doctest: +SKIP

    Args:
        fetch: coroutine function that accepts the page query parameters.
        model: pydantic model class for a list item.
        page_size: page size (1..1000).
        start_page: first page number (0 by default).
        params: base query parameters (filters).
        max_pages: cap on the number of pages to load (guards against infinity).

    """

    def __init__(
        self,
        *,
        fetch: PageFetcher,
        model: type[ModelT],
        page_size: int = 100,
        start_page: int = 0,
        params: Mapping[str, Any] | None = None,
        max_pages: int | None = None,
    ) -> None:
        """Validate the arguments and initialise the traversal state."""
        if not 1 <= page_size <= 1000:
            raise ValueError("page_size must be in 1..1000")
        if max_pages is not None and max_pages < 1:
            raise ValueError("max_pages must be >= 1")

        self._fetch = fetch
        self._model = model
        self._page_size = page_size
        self._page = start_page
        self._base_params: dict[str, Any] = dict(params or {})
        self._max_pages = max_pages

        self._buffer: list[ModelT] = []
        self._exhausted = False
        self._pages_loaded = 0
        self._items_seen = 0

    # -- introspection ------------------------------------------------------
    @property
    def page_size(self) -> int:
        """Size of the page being requested."""
        return self._page_size

    @property
    def pages_loaded(self) -> int:
        """Number of pages loaded so far."""
        return self._pages_loaded

    @property
    def items_seen(self) -> int:
        """Number of items yielded so far."""
        return self._items_seen

    @property
    def exhausted(self) -> bool:
        """Whether the end of the list has been reached."""
        return self._exhausted and not self._buffer

    # -- iteration ----------------------------------------------------------
    def __aiter__(self) -> AsyncIterator[ModelT]:
        """Return the paginator itself as the asynchronous iterator."""
        return self

    async def __anext__(self) -> ModelT:
        """Return the next item, loading more pages as needed."""
        while not self._buffer:
            if not await self._load_next_page():
                raise StopAsyncIteration
        self._items_seen += 1
        return self._buffer.pop(0)

    async def collect(self) -> list[ModelT]:
        """Collect every item into memory (mind large result sets)."""
        return [item async for item in self]

    # -- internals ----------------------------------------------------------
    async def _load_next_page(self) -> bool:
        """Load the next page. ``False`` means there are no pages left."""
        if self._exhausted:
            return False
        if self._max_pages is not None and self._pages_loaded >= self._max_pages:
            self._exhausted = True
            return False

        # Импорт внутри метода разрывает цикл endpoints -> pagination ->
        # endpoints.base: Paginator нужен самим эндпоинтам в рантайме.
        from .endpoints.base import unwrap_entities

        params = {**self._base_params, "page": self._page, "size": self._page_size}
        payload = await self._fetch(params)
        raw_items = unwrap_entities(payload)

        self._pages_loaded += 1
        self._page += 1
        self._buffer = [self._model.model_validate(item) for item in raw_items]

        if len(self._buffer) < self._page_size:
            self._exhausted = True
        return bool(self._buffer)
