"""Retry transport — sync + async, retryable codes only, jitter delay sanity."""

from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest

from astroway._retry import (
    AsyncRetryTransport,
    RetryConfig,
    SyncRetryTransport,
    _parse_retry_after,
)


class _SequenceTransport(httpx.BaseTransport):
    """Yields a scripted sequence of responses; tracks call count."""

    def __init__(self, responses: list[httpx.Response]) -> None:
        self._iter: Iterator[httpx.Response] = iter(responses)
        self.calls: int = 0

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        return next(self._iter)


class _SequenceAsyncTransport(httpx.AsyncBaseTransport):
    def __init__(self, responses: list[httpx.Response]) -> None:
        self._iter: Iterator[httpx.Response] = iter(responses)
        self.calls: int = 0

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        return next(self._iter)


def _resp(status: int, headers: dict[str, str] | None = None) -> httpx.Response:
    return httpx.Response(status_code=status, headers=headers or {}, content=b"{}")


# ─── Sync transport ──────────────────────────────────────────────


def test_sync_returns_immediately_on_2xx() -> None:
    inner = _SequenceTransport([_resp(200)])
    transport = SyncRetryTransport(inner, RetryConfig(base_delay_ms=1, max_delay_ms=5))
    with httpx.Client(transport=transport) as client:
        r = client.get("https://example.test/")
    assert r.status_code == 200
    assert inner.calls == 1


def test_sync_retries_429_then_succeeds() -> None:
    inner = _SequenceTransport([_resp(429, {"retry-after": "0"}), _resp(200)])
    transport = SyncRetryTransport(inner, RetryConfig(base_delay_ms=1, max_delay_ms=5))
    with httpx.Client(transport=transport) as client:
        r = client.get("https://example.test/")
    assert r.status_code == 200
    assert inner.calls == 2


def test_sync_retries_503_then_succeeds() -> None:
    inner = _SequenceTransport([_resp(503), _resp(200)])
    transport = SyncRetryTransport(inner, RetryConfig(base_delay_ms=1, max_delay_ms=5))
    with httpx.Client(transport=transport) as client:
        r = client.get("https://example.test/")
    assert r.status_code == 200
    assert inner.calls == 2


def test_sync_does_not_retry_400() -> None:
    inner = _SequenceTransport([_resp(400)])
    transport = SyncRetryTransport(inner, RetryConfig(base_delay_ms=1))
    with httpx.Client(transport=transport) as client:
        r = client.get("https://example.test/")
    assert r.status_code == 400
    assert inner.calls == 1


def test_sync_does_not_retry_401() -> None:
    inner = _SequenceTransport([_resp(401)])
    transport = SyncRetryTransport(inner, RetryConfig(base_delay_ms=1))
    with httpx.Client(transport=transport) as client:
        r = client.get("https://example.test/")
    assert r.status_code == 401
    assert inner.calls == 1


def test_sync_returns_last_response_after_max_retries() -> None:
    inner = _SequenceTransport([_resp(503), _resp(503), _resp(503)])
    transport = SyncRetryTransport(
        inner, RetryConfig(max_retries=2, base_delay_ms=1, max_delay_ms=5)
    )
    with httpx.Client(transport=transport) as client:
        r = client.get("https://example.test/")
    assert r.status_code == 503
    assert inner.calls == 3


# ─── Async transport ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_async_returns_immediately_on_2xx() -> None:
    inner = _SequenceAsyncTransport([_resp(200)])
    transport = AsyncRetryTransport(inner, RetryConfig(base_delay_ms=1, max_delay_ms=5))
    async with httpx.AsyncClient(transport=transport) as client:
        r = await client.get("https://example.test/")
    assert r.status_code == 200
    assert inner.calls == 1


@pytest.mark.asyncio
async def test_async_retries_429_then_succeeds() -> None:
    inner = _SequenceAsyncTransport([_resp(429, {"retry-after": "0"}), _resp(200)])
    transport = AsyncRetryTransport(inner, RetryConfig(base_delay_ms=1, max_delay_ms=5))
    async with httpx.AsyncClient(transport=transport) as client:
        r = await client.get("https://example.test/")
    assert r.status_code == 200
    assert inner.calls == 2


# ─── Header parsing ──────────────────────────────────────────────


def test_parse_retry_after_seconds() -> None:
    assert _parse_retry_after("30") == 30000.0


def test_parse_retry_after_invalid_returns_none() -> None:
    assert _parse_retry_after(None) is None
    assert _parse_retry_after("never") is None


def test_parse_retry_after_http_date() -> None:
    # An HTTP-date in the past should clamp to 0, not negative.
    result = _parse_retry_after("Mon, 01 Jan 2000 00:00:00 GMT")
    assert result == 0.0
