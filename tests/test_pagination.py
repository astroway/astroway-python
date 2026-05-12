"""Auto-pagination iterators (sync + async)."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from astroway import Astroway, AsyncAstroway, AsyncPage, SyncPage


class _ScriptedTransport(httpx.BaseTransport):
    """Plays back a list of httpx.Response objects in order."""

    def __init__(self, responses: list[httpx.Response]) -> None:
        self._responses = list(responses)
        self.requests: list[httpx.Request] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if not self._responses:
            raise AssertionError(f"transport ran out of scripted responses; got {request.url}")
        return self._responses.pop(0)


class _AsyncScriptedTransport(httpx.AsyncBaseTransport):
    def __init__(self, responses: list[httpx.Response]) -> None:
        self._responses = list(responses)
        self.requests: list[httpx.Request] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if not self._responses:
            raise AssertionError(f"transport ran out of scripted responses; got {request.url}")
        return self._responses.pop(0)


def _ok(payload: Any) -> httpx.Response:
    return httpx.Response(
        status_code=200,
        content=json.dumps({"ok": True, "data": payload}).encode("utf-8"),
        headers={"content-type": "application/json"},
    )


# ─── Sync ────────────────────────────────────────────────────────


def test_sync_paginator_walks_every_item_across_pages() -> None:
    transport = _ScriptedTransport(
        [
            _ok({"items": [{"id": 1}, {"id": 2}], "next_cursor": "page2"}),
            _ok({"items": [{"id": 3}, {"id": 4}], "next_cursor": "page3"}),
            _ok({"items": [{"id": 5}], "next_cursor": None}),
        ],
    )
    aw = Astroway(api_key="aw_test_x", transport=transport)
    try:
        ids = [item["id"] for item in aw.paginate("GET", "/transits/calendar")]
    finally:
        aw.close()
    assert ids == [1, 2, 3, 4, 5]
    assert len(transport.requests) == 3


def test_sync_paginator_passes_cursor_param_on_subsequent_pages() -> None:
    transport = _ScriptedTransport(
        [
            _ok({"items": [{"id": 1}], "next_cursor": "abc"}),
            _ok({"items": [{"id": 2}], "next_cursor": None}),
        ],
    )
    aw = Astroway(api_key="aw_test_x", transport=transport)
    try:
        list(aw.paginate("GET", "/transits/calendar", params={"start": "2026-01"}))
    finally:
        aw.close()
    first = transport.requests[0]
    second = transport.requests[1]
    assert "cursor=" not in first.url.query.decode()
    assert "start=2026-01" in first.url.query.decode()
    assert "cursor=abc" in second.url.query.decode()
    assert "start=2026-01" in second.url.query.decode()


def test_sync_paginator_pages_yields_page_objects_with_metadata() -> None:
    transport = _ScriptedTransport(
        [
            _ok({"items": [{"id": 1}], "next_cursor": "abc"}),
            _ok({"items": [{"id": 2}], "next_cursor": None}),
        ],
    )
    aw = Astroway(api_key="aw_test_x", transport=transport)
    try:
        pages = list(aw.paginate("GET", "/anything").pages())
    finally:
        aw.close()
    assert len(pages) == 2
    assert isinstance(pages[0], SyncPage)
    assert pages[0].next_cursor == "abc"
    assert pages[0].has_next is True
    assert pages[1].next_cursor is None
    assert pages[1].has_next is False


def test_sync_paginator_treats_non_list_payload_as_single_page() -> None:
    """Endpoints that don't speak the list contract still work — they yield once."""
    transport = _ScriptedTransport([_ok({"angles": {"asc": "Aries"}})])
    aw = Astroway(api_key="aw_test_x", transport=transport)
    try:
        items = list(aw.paginate("POST", "/chart"))
    finally:
        aw.close()
    assert len(items) == 1
    assert items[0] == {"angles": {"asc": "Aries"}}


def test_sync_paginator_accepts_camelcase_cursor() -> None:
    transport = _ScriptedTransport(
        [
            _ok({"items": [{"id": 1}], "nextCursor": "abc"}),
            _ok({"items": [{"id": 2}], "nextCursor": None}),
        ],
    )
    aw = Astroway(api_key="aw_test_x", transport=transport)
    try:
        ids = [item["id"] for item in aw.paginate("GET", "/anything")]
    finally:
        aw.close()
    assert ids == [1, 2]


def test_sync_paginator_first_page_returns_immediately() -> None:
    transport = _ScriptedTransport([_ok({"items": [1, 2, 3], "next_cursor": "more"})])
    aw = Astroway(api_key="aw_test_x", transport=transport)
    try:
        page = aw.paginate("GET", "/anything").first_page()
    finally:
        aw.close()
    assert list(page) == [1, 2, 3]
    assert page.has_next is True
    assert len(transport.requests) == 1


# ─── Async ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_async_paginator_walks_pages() -> None:
    transport = _AsyncScriptedTransport(
        [
            _ok({"items": [{"id": 1}], "next_cursor": "p2"}),
            _ok({"items": [{"id": 2}], "next_cursor": None}),
        ],
    )
    aw = AsyncAstroway(api_key="aw_test_x", transport=transport)
    try:
        ids: list[int] = []
        async for item in aw.paginate("GET", "/transits/calendar"):
            ids.append(item["id"])
    finally:
        await aw.aclose()
    assert ids == [1, 2]


@pytest.mark.asyncio
async def test_async_paginator_pages_yields_async_page_objects() -> None:
    transport = _AsyncScriptedTransport(
        [
            _ok({"items": [{"id": 1}], "next_cursor": "p2"}),
            _ok({"items": [{"id": 2}], "next_cursor": None}),
        ],
    )
    aw = AsyncAstroway(api_key="aw_test_x", transport=transport)
    try:
        pages: list[AsyncPage[Any]] = []
        async for page in aw.paginate("GET", "/anything").pages():
            pages.append(page)
    finally:
        await aw.aclose()
    assert len(pages) == 2
    assert pages[0].has_next is True
    assert pages[1].has_next is False


@pytest.mark.asyncio
async def test_async_paginator_first_page_short_circuits() -> None:
    transport = _AsyncScriptedTransport([_ok({"items": [1, 2], "next_cursor": "next"})])
    aw = AsyncAstroway(api_key="aw_test_x", transport=transport)
    try:
        page = await aw.paginate("GET", "/anything").first_page()
    finally:
        await aw.aclose()
    assert list(page) == [1, 2]
    assert len(transport.requests) == 1
