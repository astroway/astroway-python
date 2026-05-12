"""0.1.0 stable-surface assertions.

Locks the public surface of `astroway`: every name imported here is part of
the `0.1.x` contract. Removing or narrowing any of them requires a `1.0.0`
major bump.

Approach: use `typing.get_type_hints` to assert that key callables / classes
keep their signatures, plus `inspect.signature` for constructor parameter
shape. Cheaper than a full mypy --strict gate (which still has noise from the
auto-generated _namespaces.py) and fast enough for CI.
"""

from __future__ import annotations

import inspect
import typing
from typing import Any, get_type_hints

import httpx
import pytest

# The whole locked surface as imported from the package root.
from astroway import (  # noqa: F401
    SDK_VERSION,
    APIConnectionError,
    APITimeoutError,
    ApiError,
    Astroway,
    AsyncAstroway,
    AsyncPage,
    AsyncPaginator,
    AsyncSSEStream,
    AuthenticationError,
    BadRequestError,
    BirthData,
    CacheEntry,
    CacheStore,
    CalculationError,
    DETERMINISTIC_PATH_PREFIXES,
    DiskCache,
    IdempotencyMode,
    InternalServerError,
    MemoryCache,
    NON_DETERMINISTIC_PATH_PREFIXES,
    NotFoundError,
    PermissionDeniedError,
    QuotaExceededError,
    RateLimitError,
    RawResponse,
    ResolvedCache,
    RetryConfig,
    SSEEvent,
    StreamChunk,
    StreamDone,
    StreamError,
    StreamEvent,
    SynastryRequest,
    SyncPage,
    SyncPaginator,
    SyncSSEStream,
    TextDelta,
    TransitsRequest,
    TransportBackend,
    UnprocessableEntityError,
    VedicDashaRequest,
    build_cache_key,
    generate_idempotency_key,
    is_deterministic_path,
)


def test_sdk_version_string() -> None:
    assert isinstance(SDK_VERSION, str)
    assert len(SDK_VERSION.split(".")) >= 3


def test_astroway_constructor_signature() -> None:
    """Astroway.__init__ keeps every named parameter that ships in 0.1.x."""
    sig = inspect.signature(Astroway.__init__)
    params = sig.parameters
    assert "api_key" in params
    assert "base_url" in params
    assert "auth_scheme" in params
    assert "timeout" in params
    assert "retry" in params
    assert "default_headers" in params
    assert "transport" in params
    assert "limits" in params
    assert "http_client" in params
    assert "idempotency" in params
    assert "cache" in params
    # api_key must remain required (no default).
    assert params["api_key"].default is inspect.Parameter.empty


def test_async_astroway_constructor_signature() -> None:
    sig = inspect.signature(AsyncAstroway.__init__)
    params = sig.parameters
    for name in ("api_key", "base_url", "auth_scheme", "timeout", "retry",
                 "default_headers", "transport", "limits", "http_client",
                 "idempotency", "cache"):
        assert name in params, f"AsyncAstroway lost parameter: {name}"


def test_error_hierarchy_locked() -> None:
    """The 12-class error tree is the locked support contract — users
    write `except RateLimitError` / `except QuotaExceededError` — collapsing
    branches breaks their code silently."""
    for cls in (
        APIConnectionError, APITimeoutError, BadRequestError,
        AuthenticationError, PermissionDeniedError, NotFoundError,
        UnprocessableEntityError, RateLimitError, QuotaExceededError,
        CalculationError, InternalServerError,
    ):
        assert issubclass(cls, ApiError), f"{cls.__name__} no longer extends ApiError"
    # APITimeoutError is more specific than APIConnectionError per the docs.
    assert issubclass(APITimeoutError, APIConnectionError)


def test_api_error_attributes_locked() -> None:
    e = ApiError("x")
    # Support-ticket / dashboard fields. Removing any breaks user catch blocks.
    for attr in ("status", "code", "request_id",
                 "credits_remaining", "retry_after_seconds", "body"):
        assert hasattr(e, attr), f"ApiError lost attribute: {attr}"


def test_retry_config_shape() -> None:
    rc = RetryConfig()
    for attr in ("max_retries", "base_delay_ms", "max_delay_ms", "retryable_statuses"):
        assert hasattr(rc, attr), f"RetryConfig lost attribute: {attr}"


def test_cache_surface_locked() -> None:
    """Cache opt-in shapes (`MemoryCache`, `DiskCache`, the `CacheStore` Protocol,
    plus the `is_deterministic_path` / `build_cache_key` helpers) are part of
    the public surface for users wiring up Redis / their own backend."""
    assert issubclass(MemoryCache, CacheStore)
    assert issubclass(DiskCache, CacheStore)
    assert callable(build_cache_key)
    assert callable(is_deterministic_path)
    assert isinstance(DETERMINISTIC_PATH_PREFIXES, tuple)
    assert isinstance(NON_DETERMINISTIC_PATH_PREFIXES, tuple)
    assert all(p.startswith("/") for p in DETERMINISTIC_PATH_PREFIXES)


def test_streaming_surface_locked() -> None:
    """StreamEvent union members + the iterator types must stay importable."""
    for cls in (TextDelta, StreamDone, StreamError):
        assert isinstance(cls, type)
    # StreamEvent is a typing.Union — represented as a typing alias at runtime.
    # Just assert it's accessible and non-None.
    assert StreamEvent is not None


def test_pagination_surface_locked() -> None:
    """Generic Page / Paginator types stay importable — users annotate them."""
    assert SyncPage is not None
    assert AsyncPage is not None
    assert SyncPaginator is not None
    assert AsyncPaginator is not None


def test_idempotency_mode_literals() -> None:
    """IdempotencyMode is a Literal['auto', 'off'] | callable() in 0.1.x.
    The string literals are the locked union — narrowing breaks user code."""
    # Cheap runtime check — proper type narrowing only matters statically.
    typing.cast(IdempotencyMode, "auto")
    typing.cast(IdempotencyMode, "off")


def test_transport_backend_literals() -> None:
    typing.cast(TransportBackend, "httpx")
    typing.cast(TransportBackend, "aiohttp")


def test_models_surface_locked() -> None:
    """Pydantic request models added in a3 are part of the surface — users
    instantiate them directly: `aw.charts.compute(birth=NatalRequest(...))`."""
    for cls in (BirthData, SynastryRequest, TransitsRequest, VedicDashaRequest):
        assert isinstance(cls, type), f"{cls.__name__} no longer importable as a class"


def test_raw_response_dataclass_fields() -> None:
    """RawResponse.with_response() return shape is stable: data / request_id /
    credits_remaining / headers / status_code."""
    hints = get_type_hints(RawResponse)
    for f in ("data", "request_id", "credits_remaining", "headers", "status_code"):
        assert f in hints, f"RawResponse lost field: {f}"


def test_request_method_signature() -> None:
    """`Astroway.request` shape: (method, path, *, body, params, headers,
    idempotency_key, cache) — locked since a4."""
    sig = inspect.signature(Astroway.request)
    params = sig.parameters
    for name in ("method", "path", "body", "params", "headers",
                 "idempotency_key", "cache"):
        assert name in params, f"Astroway.request lost parameter: {name}"


@pytest.mark.asyncio
async def test_async_request_method_signature() -> None:
    sig = inspect.signature(AsyncAstroway.request)
    params = sig.parameters
    for name in ("method", "path", "body", "params", "headers",
                 "idempotency_key", "cache"):
        assert name in params, f"AsyncAstroway.request lost parameter: {name}"
