"""Cursor-based auto-pagination iterators.

Stainless / OpenAI / Anthropic pattern: a list call returns an iterable that
walks every item across all pages, fetching the next page on demand. The user
can also iterate page-by-page via ``.pages``.

API contract (subject to api-calc rollout): list endpoints return an envelope::

    {
        "ok": true,
        "data": {
            "items": [...],
            "next_cursor": "..."   // null/missing => last page
        }
    }

A response without ``items`` is a single page with the whole payload as the
sole item — so endpoints that aren't paginated yet still work through the
iterator and just yield once.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from typing import TYPE_CHECKING, Any, Generic, TypeVar

if TYPE_CHECKING:
    from ._client import Astroway, AsyncAstroway

T = TypeVar("T")

CURSOR_PARAM = "cursor"
ITEMS_KEY = "items"
NEXT_CURSOR_KEYS = ("next_cursor", "nextCursor")


def _extract(payload: Any) -> tuple[list[Any], str | None]:
    """Pull ``(items, next_cursor)`` out of a list-endpoint payload.

    Tolerant of endpoints that don't speak the list contract yet — those return
    a dict without ``items``, which we treat as a single-item page.
    """
    if isinstance(payload, dict):
        items_raw = payload.get(ITEMS_KEY)
        if isinstance(items_raw, list):
            for key in NEXT_CURSOR_KEYS:
                cursor = payload.get(key)
                if cursor:
                    return items_raw, str(cursor)
            return items_raw, None
        return [payload], None
    if isinstance(payload, list):
        return payload, None
    return [payload], None


class SyncPage(Generic[T]):
    """One page of items + optional next cursor.

    Iterate the page directly to walk its items::

        for item in page:
            ...

    Or use :attr:`items` / :attr:`next_cursor` directly.
    """

    __slots__ = ("items", "next_cursor", "raw")

    def __init__(self, items: list[T], next_cursor: str | None, raw: Any) -> None:
        self.items = items
        self.next_cursor = next_cursor
        self.raw = raw

    @property
    def has_next(self) -> bool:
        return self.next_cursor is not None

    def __iter__(self) -> Iterator[T]:
        return iter(self.items)

    def __len__(self) -> int:
        return len(self.items)


class AsyncPage(Generic[T]):
    """Async sibling of :class:`SyncPage`. Same fields; iteration over items is
    sync (the page is already in memory)."""

    __slots__ = ("items", "next_cursor", "raw")

    def __init__(self, items: list[T], next_cursor: str | None, raw: Any) -> None:
        self.items = items
        self.next_cursor = next_cursor
        self.raw = raw

    @property
    def has_next(self) -> bool:
        return self.next_cursor is not None

    def __iter__(self) -> Iterator[T]:
        return iter(self.items)

    def __len__(self) -> int:
        return len(self.items)


class SyncPaginator(Generic[T]):
    """Sync auto-paginator. Walks every item across pages.

    Usage::

        for transit in aw.transits.calendar(start="2026-01", end="2026-12"):
            ...

    Page-by-page::

        for page in aw.transits.calendar(start="...", end="...").pages():
            for transit in page:
                ...
    """

    def __init__(
        self,
        client: Astroway,
        method: str,
        path: str,
        *,
        body: Any | None = None,
        params: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> None:
        self._client = client
        self._method = method
        self._path = path
        self._body = body
        self._params = dict(params) if params else {}
        self._idempotency_key = idempotency_key

    def __iter__(self) -> Iterator[T]:
        for page in self.pages():
            yield from page

    def pages(self) -> Iterator[SyncPage[T]]:
        cursor: str | None = None
        while True:
            params = dict(self._params)
            if cursor is not None:
                params[CURSOR_PARAM] = cursor
            payload = self._client.request(
                self._method,
                self._path,
                body=self._body,
                params=params or None,
                idempotency_key=self._idempotency_key,
            )
            items, next_cursor = _extract(payload)
            yield SyncPage(items, next_cursor, payload)
            if next_cursor is None:
                return
            cursor = next_cursor

    def first_page(self) -> SyncPage[T]:
        return next(iter(self.pages()))


class AsyncPaginator(Generic[T]):
    """Async auto-paginator. ``async for`` over items, or ``async for page in .pages()``.

    Usage::

        async for transit in aw.transits.calendar(start=..., end=...):
            ...
    """

    def __init__(
        self,
        client: AsyncAstroway,
        method: str,
        path: str,
        *,
        body: Any | None = None,
        params: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> None:
        self._client = client
        self._method = method
        self._path = path
        self._body = body
        self._params = dict(params) if params else {}
        self._idempotency_key = idempotency_key

    async def __aiter__(self) -> AsyncIterator[T]:
        async for page in self.pages():
            for item in page:
                yield item

    async def pages(self) -> AsyncIterator[AsyncPage[T]]:
        cursor: str | None = None
        while True:
            params = dict(self._params)
            if cursor is not None:
                params[CURSOR_PARAM] = cursor
            payload = await self._client.request(
                self._method,
                self._path,
                body=self._body,
                params=params or None,
                idempotency_key=self._idempotency_key,
            )
            items, next_cursor = _extract(payload)
            yield AsyncPage(items, next_cursor, payload)
            if next_cursor is None:
                return
            cursor = next_cursor

    async def first_page(self) -> AsyncPage[T]:
        async for page in self.pages():
            return page
        raise RuntimeError("AsyncPaginator yielded no pages — endpoint returned empty payload")
