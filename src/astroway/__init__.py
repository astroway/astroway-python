"""astroway — Official Python SDK for the AstroWay API.

Quick start::

    from astroway import Astroway

    aw = Astroway(api_key="aw_live_...")
    chart = aw.post("/chart", body={
        "date": "1990-07-14", "time": "14:30:00", "timezoneOffset": 3,
        "latitude": 50.45, "longitude": 30.52,
    })
    print(chart["angles"]["asc"])

For async workloads use :class:`AsyncAstroway` with the same surface.

Errors thrown by the SDK live in :mod:`astroway.errors` — catch
``RateLimitError`` / ``AuthenticationError`` / ``BadRequestError`` /
``ApiError`` for the common cases.
"""

from __future__ import annotations

from ._cache import (
    DETERMINISTIC_PATH_PREFIXES,
    NON_DETERMINISTIC_PATH_PREFIXES,
    CacheEntry,
    CacheStore,
    DiskCache,
    MemoryCache,
    ResolvedCache,
    build_cache_key,
    is_deterministic_path,
)
from ._client import Astroway, AsyncAstroway, RawResponse, TransportBackend
from ._idempotency import IdempotencyMode, generate_idempotency_key
from ._pagination import AsyncPage, AsyncPaginator, SyncPage, SyncPaginator
from ._retry import RetryConfig
from ._streaming import (
    AsyncSSEStream,
    SSEEvent,
    StreamChunk,
    StreamDone,
    StreamError,
    StreamEvent,
    SyncSSEStream,
    TextDelta,
)
from ._version import SDK_VERSION
from .errors import (
    APIConnectionError,
    ApiError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    CalculationError,
    InternalServerError,
    NotFoundError,
    PermissionDeniedError,
    QuotaExceededError,
    RateLimitError,
    UnprocessableEntityError,
)
from .models import BirthData, SynastryRequest, TransitsRequest, VedicDashaRequest

__version__ = SDK_VERSION

__all__ = [
    "DETERMINISTIC_PATH_PREFIXES",
    "NON_DETERMINISTIC_PATH_PREFIXES",
    "SDK_VERSION",
    "APIConnectionError",
    "APITimeoutError",
    "ApiError",
    "Astroway",
    "AsyncAstroway",
    "AsyncPage",
    "AsyncPaginator",
    "AsyncSSEStream",
    "AuthenticationError",
    "BadRequestError",
    "BirthData",
    "CacheEntry",
    "CacheStore",
    "CalculationError",
    "DiskCache",
    "IdempotencyMode",
    "InternalServerError",
    "MemoryCache",
    "NotFoundError",
    "PermissionDeniedError",
    "QuotaExceededError",
    "RateLimitError",
    "RawResponse",
    "ResolvedCache",
    "RetryConfig",
    "SSEEvent",
    "StreamChunk",
    "StreamDone",
    "StreamError",
    "StreamEvent",
    "SynastryRequest",
    "SyncPage",
    "SyncPaginator",
    "SyncSSEStream",
    "TextDelta",
    "TransitsRequest",
    "TransportBackend",
    "UnprocessableEntityError",
    "VedicDashaRequest",
    "build_cache_key",
    "generate_idempotency_key",
    "is_deterministic_path",
]
