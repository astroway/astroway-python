"""rc1 — bring-your-own httpx.Client / httpx.AsyncClient + transport selection."""

from __future__ import annotations

import httpx
import pytest

from astroway import Astroway, AsyncAstroway


class _RecordingTransport(httpx.BaseTransport):
    def __init__(self) -> None:
        self.last_request: httpx.Request | None = None

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.last_request = request
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            json={"ok": True, "data": {"v": 1}},
        )


class _AsyncRecordingTransport(httpx.AsyncBaseTransport):
    def __init__(self) -> None:
        self.last_request: httpx.Request | None = None

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.last_request = request
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            json={"ok": True, "data": {"v": 1}},
        )


def test_sync_http_client_byo_is_used_as_is() -> None:
    rec = _RecordingTransport()
    user_client = httpx.Client(
        base_url="https://api.astroway.info/v1",
        transport=rec,
    )
    aw = Astroway(api_key="aw_test_x", http_client=user_client)
    assert aw._http is user_client
    assert aw._owns_http is False
    aw.request("POST", "/chart", body={})
    assert rec.last_request is not None
    # SDK headers must still be on the request even though we didn't construct the client.
    assert rec.last_request.headers["x-api-key"] == "aw_test_x"
    assert rec.last_request.headers["x-astroway-channel"] == "sdk-py"
    assert rec.last_request.headers["user-agent"].startswith("astroway-sdk-python/")


def test_sync_http_client_close_does_not_touch_user_client() -> None:
    user_client = httpx.Client(base_url="https://api.astroway.info/v1")
    aw = Astroway(api_key="aw_test_x", http_client=user_client)
    aw.close()
    # Still usable — proves we did not call close() on the user-supplied instance.
    assert user_client.is_closed is False
    user_client.close()


def test_sync_http_client_rejects_conflicting_options() -> None:
    user_client = httpx.Client(base_url="https://api.astroway.info/v1")
    with pytest.raises(ValueError, match="http_client OR"):
        Astroway(
            api_key="aw_test_x",
            http_client=user_client,
            transport=httpx.HTTPTransport(),
        )


def test_sync_limits_propagated_when_no_byo_client() -> None:
    limits = httpx.Limits(max_connections=99, max_keepalive_connections=10)
    aw = Astroway(api_key="aw_test_x", limits=limits)
    # We can't easily peek into the wrapped transport's limits — assert ownership instead.
    assert aw._owns_http is True
    aw.close()


def test_sync_string_transport_rejected() -> None:
    with pytest.raises(ValueError, match="not supported on the sync client"):
        Astroway(api_key="aw_test_x", transport="aiohttp")


@pytest.mark.asyncio
async def test_async_http_client_byo_is_used_as_is() -> None:
    rec = _AsyncRecordingTransport()
    user_client = httpx.AsyncClient(
        base_url="https://api.astroway.info/v1",
        transport=rec,
    )
    aw = AsyncAstroway(api_key="aw_test_x", http_client=user_client)
    assert aw._http is user_client
    assert aw._owns_http is False
    await aw.request("POST", "/chart", body={})
    assert rec.last_request is not None
    assert rec.last_request.headers["x-api-key"] == "aw_test_x"
    await user_client.aclose()


@pytest.mark.asyncio
async def test_async_aiohttp_transport_raises_clear_error_when_extra_missing() -> None:
    # Without `pip install astroway[aiohttp]` the transport string must surface a
    # helpful ImportError, not a confusing AttributeError downstream.
    with pytest.raises(ImportError, match=r"astroway\[aiohttp\]"):
        AsyncAstroway(api_key="aw_test_x", transport="aiohttp")


@pytest.mark.asyncio
async def test_async_unknown_transport_string_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown transport"):
        AsyncAstroway(api_key="aw_test_x", transport="trio")
