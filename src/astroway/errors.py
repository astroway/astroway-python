"""Error hierarchy mirroring the Stainless template (OpenAI / Anthropic / Cloudflare SDKs).

Catch order recommendation in user code::

    try:
        ...
    except RateLimitError as e:
        # respect e.retry_after_seconds
    except AuthenticationError:
        # rotate the API key
    except ApiError as e:
        # generic 4xx/5xx, inspect e.status / e.code / e.body / e.request_id
    except Exception:
        raise
"""

from __future__ import annotations

from typing import Any


class ApiError(Exception):
    """Base class for every error raised by the SDK on top of Python's built-ins."""

    status: int | None
    code: str | None
    body: Any | None
    request_id: str | None

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        code: str | None = None,
        body: Any | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.body = body
        self.request_id = request_id


class APIConnectionError(ApiError):
    """Network-level failure — DNS, connection refused, TLS, timeouts before bytes received."""


class APITimeoutError(APIConnectionError):
    """Request exceeded the configured timeout."""


class BadRequestError(ApiError):
    """HTTP 400 — request did not parse or violated a basic constraint."""


class AuthenticationError(ApiError):
    """HTTP 401 — API key missing, invalid, or revoked."""


class PermissionDeniedError(ApiError):
    """HTTP 403 — authenticated but not allowed to call this endpoint."""


class NotFoundError(ApiError):
    """HTTP 404 — resource (or endpoint) does not exist."""


class UnprocessableEntityError(ApiError):
    """HTTP 422 — payload parsed but failed schema validation."""


class RateLimitError(ApiError):
    """HTTP 429 — rate limit exceeded. ``retry_after_seconds`` from ``Retry-After`` if present."""

    retry_after_seconds: int | None

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        code: str | None = None,
        body: Any | None = None,
        request_id: str | None = None,
        retry_after_seconds: int | None = None,
    ) -> None:
        super().__init__(message, status=status, code=code, body=body, request_id=request_id)
        self.retry_after_seconds = retry_after_seconds


class InternalServerError(ApiError):
    """HTTP 5xx — server-side failure. Retried by default unless ``retry={"max_retries": 0}``."""


def classify_http_error(
    *,
    status: int,
    message: str,
    code: str | None = None,
    body: Any | None = None,
    request_id: str | None = None,
    retry_after_seconds: int | None = None,
) -> ApiError:
    """Maps an HTTP status to the most specific subclass."""
    init: dict[str, Any] = {"status": status, "code": code, "body": body, "request_id": request_id}
    if status == 400:
        return BadRequestError(message, **init)
    if status == 401:
        return AuthenticationError(message, **init)
    if status == 403:
        return PermissionDeniedError(message, **init)
    if status == 404:
        return NotFoundError(message, **init)
    if status == 422:
        return UnprocessableEntityError(message, **init)
    if status == 429:
        return RateLimitError(message, **init, retry_after_seconds=retry_after_seconds)
    if status >= 500:
        return InternalServerError(message, **init)
    return ApiError(message, **init)


__all__ = [
    "APIConnectionError",
    "APITimeoutError",
    "ApiError",
    "AuthenticationError",
    "BadRequestError",
    "InternalServerError",
    "NotFoundError",
    "PermissionDeniedError",
    "RateLimitError",
    "UnprocessableEntityError",
    "classify_http_error",
]
