"""Typed namespaces — sync + async."""

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
            content=json.dumps({"ok": True, "data": {"echo": request.url.path}}).encode("utf-8"),
            headers={"content-type": "application/json"},
        )


class _RecordingAsyncTransport(httpx.AsyncBaseTransport):
    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(
            status_code=200,
            content=json.dumps({"ok": True, "data": {"echo": request.url.path}}).encode("utf-8"),
            headers={"content-type": "application/json"},
        )


def test_well_known_namespaces_attached() -> None:
    aw = Astroway(api_key="aw_test_x")
    assert callable(aw.synastry.aspect_grid)  # type: ignore[attr-defined]
    assert callable(aw.transits.compute)  # type: ignore[attr-defined]
    assert callable(aw.bazi.day_master)  # type: ignore[attr-defined]
    assert callable(aw.vedic.dashas_vimshottari_maha)  # type: ignore[attr-defined]
    assert callable(aw.human_design.compute)  # type: ignore[attr-defined]


def test_sync_namespace_posts_to_correct_path() -> None:
    transport = _RecordingTransport()
    aw = Astroway(api_key="aw_test_x", transport=transport)
    result = aw.synastry.aspect_grid({"foo": "bar"})  # type: ignore[attr-defined]
    assert transport.requests[0].method == "POST"
    assert transport.requests[0].url.path == "/v1/synastry/aspect-grid"
    body = json.loads(transport.requests[0].content.decode("utf-8"))
    assert body == {"foo": "bar"}
    # Envelope unwrapped — caller sees `data`, not the full {ok,data,error} dict.
    assert result == {"echo": "/v1/synastry/aspect-grid"}


def test_sync_compute_method_for_single_segment_endpoints() -> None:
    transport = _RecordingTransport()
    aw = Astroway(api_key="aw_test_x", transport=transport)
    aw.transits.compute({})  # type: ignore[attr-defined]
    assert transport.requests[0].url.path == "/v1/transits"


def test_sync_namespace_passes_headers() -> None:
    transport = _RecordingTransport()
    aw = Astroway(api_key="aw_test_x", transport=transport)
    aw.bazi.day_master({}, headers={"X-Trace-Id": "trace_abc"})  # type: ignore[attr-defined]
    assert transport.requests[0].headers["x-trace-id"] == "trace_abc"


@pytest.mark.asyncio
async def test_async_namespace_posts_to_correct_path() -> None:
    transport = _RecordingAsyncTransport()
    async with AsyncAstroway(api_key="aw_test_x", transport=transport) as aw:
        result = await aw.synastry.aspect_grid({"foo": "bar"})  # type: ignore[attr-defined]
    assert transport.requests[0].method == "POST"
    assert transport.requests[0].url.path == "/v1/synastry/aspect-grid"
    assert result == {"echo": "/v1/synastry/aspect-grid"}


def test_escape_hatch_still_works() -> None:
    transport = _RecordingTransport()
    aw = Astroway(api_key="aw_test_x", transport=transport)
    # Raw `request()` API still available.
    aw.request("POST", "/chart", body={"date": "1990-07-14"})
    assert transport.requests[0].url.path == "/v1/chart"
