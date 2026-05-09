"""httpx retry transports — sync + async. Default: 2 retries, exponential
backoff with full jitter, on connection errors / 408 / 409 / 429 / 5xx.
Honors ``Retry-After`` (seconds or HTTP-date) when present on 429.
"""

from __future__ import annotations

import asyncio
import email.utils
import random
import time
from collections.abc import Iterable
from dataclasses import dataclass

import httpx

DEFAULT_RETRYABLE: frozenset[int] = frozenset({408, 409, 429, 500, 502, 503, 504})


@dataclass(frozen=True)
class RetryConfig:
    """Retry knobs for the SDK transport. ``max_retries=0`` disables retries entirely."""

    max_retries: int = 2
    base_delay_ms: int = 250
    max_delay_ms: int = 30_000
    retryable_statuses: frozenset[int] = DEFAULT_RETRYABLE

    @classmethod
    def from_dict(cls, value: dict | None) -> RetryConfig:
        if value is None:
            return cls()
        kwargs: dict = {}
        if "max_retries" in value:
            kwargs["max_retries"] = int(value["max_retries"])
        if "base_delay_ms" in value:
            kwargs["base_delay_ms"] = int(value["base_delay_ms"])
        if "max_delay_ms" in value:
            kwargs["max_delay_ms"] = int(value["max_delay_ms"])
        if "retryable_statuses" in value:
            kwargs["retryable_statuses"] = frozenset(value["retryable_statuses"])
        return cls(**kwargs)


def _parse_retry_after(value: str | None) -> float | None:
    """Returns delay in milliseconds, or None when header absent / unparseable."""
    if not value:
        return None
    try:
        seconds = float(value)
        if seconds >= 0:
            return seconds * 1000
    except ValueError:
        pass
    try:
        when = email.utils.parsedate_to_datetime(value)
        delta = (when.timestamp() - time.time()) * 1000
        return max(0.0, delta)
    except (TypeError, ValueError):
        return None


def _jitter_delay_ms(attempt: int, base: int, cap: int) -> float:
    upper = min(cap, base * (2**attempt))
    return random.random() * upper


_RetryableExceptions: tuple[type[BaseException], ...] = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadError,
    httpx.WriteError,
    httpx.PoolTimeout,
    httpx.ReadTimeout,
)


class SyncRetryTransport(httpx.BaseTransport):
    """Wraps a sync transport with retry semantics."""

    def __init__(self, inner: httpx.BaseTransport, config: RetryConfig) -> None:
        self._inner = inner
        self._config = config

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        last_exc: BaseException | None = None
        for attempt in range(self._config.max_retries + 1):
            try:
                response = self._inner.handle_request(request)
                if (
                    response.status_code not in self._config.retryable_statuses
                    or attempt == self._config.max_retries
                ):
                    return response
                # Drain response body before retry — httpx requires this so
                # the connection can be returned to the pool cleanly.
                response.read()
                response.close()
                retry_after_ms = _parse_retry_after(response.headers.get("retry-after"))
                delay = retry_after_ms or _jitter_delay_ms(
                    attempt, self._config.base_delay_ms, self._config.max_delay_ms
                )
                time.sleep(delay / 1000)
            except _RetryableExceptions as exc:
                last_exc = exc
                if attempt == self._config.max_retries:
                    raise
                delay = _jitter_delay_ms(
                    attempt, self._config.base_delay_ms, self._config.max_delay_ms
                )
                time.sleep(delay / 1000)
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("retry loop exhausted without response or exception")

    def close(self) -> None:
        self._inner.close()


class AsyncRetryTransport(httpx.AsyncBaseTransport):
    """Async counterpart of :class:`SyncRetryTransport`."""

    def __init__(self, inner: httpx.AsyncBaseTransport, config: RetryConfig) -> None:
        self._inner = inner
        self._config = config

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        last_exc: BaseException | None = None
        for attempt in range(self._config.max_retries + 1):
            try:
                response = await self._inner.handle_async_request(request)
                if (
                    response.status_code not in self._config.retryable_statuses
                    or attempt == self._config.max_retries
                ):
                    return response
                await response.aread()
                await response.aclose()
                retry_after_ms = _parse_retry_after(response.headers.get("retry-after"))
                delay = retry_after_ms or _jitter_delay_ms(
                    attempt, self._config.base_delay_ms, self._config.max_delay_ms
                )
                await asyncio.sleep(delay / 1000)
            except _RetryableExceptions as exc:
                last_exc = exc
                if attempt == self._config.max_retries:
                    raise
                delay = _jitter_delay_ms(
                    attempt, self._config.base_delay_ms, self._config.max_delay_ms
                )
                await asyncio.sleep(delay / 1000)
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("retry loop exhausted without response or exception")

    async def aclose(self) -> None:
        await self._inner.aclose()
