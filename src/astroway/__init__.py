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

from ._client import AsyncAstroway, Astroway
from ._retry import RetryConfig
from ._version import SDK_VERSION
from .errors import (
    APIConnectionError,
    APITimeoutError,
    ApiError,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    UnprocessableEntityError,
)

__version__ = SDK_VERSION

__all__ = [
    "APIConnectionError",
    "APITimeoutError",
    "ApiError",
    "AsyncAstroway",
    "Astroway",
    "AuthenticationError",
    "BadRequestError",
    "InternalServerError",
    "NotFoundError",
    "PermissionDeniedError",
    "RateLimitError",
    "RetryConfig",
    "SDK_VERSION",
    "UnprocessableEntityError",
]
