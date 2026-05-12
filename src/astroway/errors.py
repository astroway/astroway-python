"""Error hierarchy mirroring the Stainless template (OpenAI / Anthropic / Cloudflare SDKs).

Catch order recommendation in user code::

    try:
        ...
    except RateLimitError as e:
        # short-window throttling — back off using e.retry_after_seconds
    except QuotaExceededError as e:
        # ran out of credits — top up; e.credits_remaining shows how many are left (often 0)
    except AuthenticationError:
        # rotate the API key
    except CalculationError as e:
        # ephemeris boundary / unsupported house system / dataset gap — inspect e.body
    except ApiError as e:
        # generic 4xx/5xx, inspect e.status / e.code / e.body / e.request_id
    except Exception:
        raise

Every ``ApiError`` carries ``request_id``, ``credits_remaining``, and (when applicable)
``retry_after_seconds`` so user code can build support tickets and debug uniformly.
"""

from __future__ import annotations

from typing import Any


class ApiError(Exception):
    """Base class for every error raised by the SDK on top of Python's built-ins."""

    status: int | None
    code: str | None
    body: Any | None
    request_id: str | None
    credits_remaining: int | None
    retry_after_seconds: int | None

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        code: str | None = None,
        body: Any | None = None,
        request_id: str | None = None,
        credits_remaining: int | None = None,
        retry_after_seconds: int | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.body = body
        self.request_id = request_id
        self.credits_remaining = credits_remaining
        self.retry_after_seconds = retry_after_seconds


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
    """HTTP 429 — short-window throttling. ``retry_after_seconds`` from ``Retry-After`` if present."""


class QuotaExceededError(ApiError):
    """Account ran out of credits / quota for the current period.

    HTTP 402 or ``code: OUT_OF_CREDITS`` / ``QUOTA_EXCEEDED`` / ``CREDIT_LIMIT_REACHED``.
    Distinct from :class:`RateLimitError` — backing off won't help; you need to top up
    the account or wait until the period resets.
    """


class CalculationError(ApiError):
    """Server-side calculation failure for an otherwise-valid request.

    Typically means a Swiss Ephemeris boundary, missing dataset, or unsupported house
    system for high latitudes. ``code: CALCULATION_ERROR`` / ``EPHEMERIS_ERROR``.
    """


class InternalServerError(ApiError):
    """HTTP 5xx — server-side failure. Retried by default unless ``retry={"max_retries": 0}``."""


_QUOTA_CODES = frozenset({"OUT_OF_CREDITS", "QUOTA_EXCEEDED", "CREDIT_LIMIT_REACHED"})
_CALCULATION_CODES = frozenset({"CALCULATION_ERROR", "EPHEMERIS_ERROR"})


def classify_http_error(
    *,
    status: int,
    message: str,
    code: str | None = None,
    body: Any | None = None,
    request_id: str | None = None,
    retry_after_seconds: int | None = None,
    credits_remaining: int | None = None,
) -> ApiError:
    """Maps an HTTP status (and optional server error code) to the most specific subclass."""
    init: dict[str, Any] = {
        "status": status,
        "code": code,
        "body": body,
        "request_id": request_id,
        "credits_remaining": credits_remaining,
        "retry_after_seconds": retry_after_seconds,
    }
    # Code-first dispatch — quota/calculation errors may ride on multiple HTTP statuses.
    if code is not None:
        if code in _QUOTA_CODES:
            return QuotaExceededError(message, **init)
        if code in _CALCULATION_CODES:
            return CalculationError(message, **init)
    if status == 400:
        return BadRequestError(message, **init)
    if status == 401:
        return AuthenticationError(message, **init)
    if status == 402:
        return QuotaExceededError(message, **init)
    if status == 403:
        return PermissionDeniedError(message, **init)
    if status == 404:
        return NotFoundError(message, **init)
    if status == 422:
        return UnprocessableEntityError(message, **init)
    if status == 429:
        return RateLimitError(message, **init)
    if status >= 500:
        return InternalServerError(message, **init)
    return ApiError(message, **init)


__all__ = [
    "APIConnectionError",
    "APITimeoutError",
    "ApiError",
    "AuthenticationError",
    "BadRequestError",
    "CalculationError",
    "InternalServerError",
    "NotFoundError",
    "PermissionDeniedError",
    "QuotaExceededError",
    "RateLimitError",
    "UnprocessableEntityError",
    "classify_http_error",
]
