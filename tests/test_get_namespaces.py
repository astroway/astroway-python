"""GET lookup namespace methods.

Before this the generator filtered on ``post``, so the spec's GET-only paths
(the zodiac, tarot and esoteric dictionaries, ``/acg/categories``,
``/muhurta/types``) were reachable only through the raw client.
"""

from __future__ import annotations

import json

import httpx
import pytest

from astroway import Astroway, AsyncAstroway


class _RecordingTransport(httpx.BaseTransport):
    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(
            status_code=200,
            content=json.dumps({"ok": True, "data": {"count": 19}}).encode("utf-8"),
            headers={"content-type": "application/json"},
        )


class _AsyncRecordingTransport(httpx.AsyncBaseTransport):
    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(
            status_code=200,
            content=json.dumps({"ok": True, "data": {"count": 19}}).encode("utf-8"),
            headers={"content-type": "application/json"},
        )


def test_get_lookup_issues_get_with_no_body() -> None:
    transport = _RecordingTransport()
    aw = Astroway(api_key="aw_test_x", transport=transport)
    result = aw.acg.categories_get()

    req = transport.requests[0]
    assert req.method == "GET"
    assert req.url.path.endswith("/acg/categories")
    # A GET carrying a body is the regression this guards: it would mean the
    # generator fell back to the POST call path.
    assert req.content == b""
    assert result == {"count": 19}


def test_get_lookup_forwards_headers() -> None:
    transport = _RecordingTransport()
    aw = Astroway(api_key="aw_test_x", transport=transport)
    aw.esoteric.crystals_get(headers={"x-custom": "yes"})
    assert transport.requests[0].headers["x-custom"] == "yes"


@pytest.mark.asyncio
async def test_async_get_lookup() -> None:
    transport = _AsyncRecordingTransport()
    aw = AsyncAstroway(api_key="aw_test_x", transport=transport)
    result = await aw.muhurta.types_get()
    assert transport.requests[0].method == "GET"
    assert result == {"count": 19}


def test_representative_lookups_exist() -> None:
    aw = Astroway(api_key="aw_test_x")
    for ns, method in [
        ("acg", "categories_get"),
        ("muhurta", "types_get"),
        ("esoteric", "crystals_get"),
        ("reference", "signs_get"),
    ]:
        assert callable(getattr(getattr(aw, ns), method))


def test_html_widgets_and_keyless_mirrors_are_not_generated() -> None:
    """The widgets answer text/html and /public/* duplicates keyed endpoints."""
    aw = Astroway(api_key="aw_test_x")
    assert not hasattr(aw, "embed")
    assert not hasattr(aw, "public")
