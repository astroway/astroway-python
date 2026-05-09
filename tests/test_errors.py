"""Error hierarchy + classify_http_error invariants."""

from __future__ import annotations

import pytest

from astroway import (
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
from astroway.errors import classify_http_error


def test_every_subclass_extends_api_error() -> None:
    cases: list[ApiError] = [
        APIConnectionError("x"),
        APITimeoutError("x"),
        BadRequestError("x"),
        AuthenticationError("x"),
        PermissionDeniedError("x"),
        NotFoundError("x"),
        UnprocessableEntityError("x"),
        RateLimitError("x"),
        InternalServerError("x"),
    ]
    for err in cases:
        assert isinstance(err, ApiError)


def test_timeout_extends_connection() -> None:
    assert isinstance(APITimeoutError("x"), APIConnectionError)


def test_attributes_are_preserved() -> None:
    err = BadRequestError(
        "bad", status=400, code="INVALID", body={"x": 1}, request_id="req_123"
    )
    assert err.status == 400
    assert err.code == "INVALID"
    assert err.body == {"x": 1}
    assert err.request_id == "req_123"


def test_rate_limit_carries_retry_after() -> None:
    err = RateLimitError("slow", status=429, retry_after_seconds=30)
    assert err.retry_after_seconds == 30


@pytest.mark.parametrize(
    ("status", "klass"),
    [
        (400, BadRequestError),
        (401, AuthenticationError),
        (403, PermissionDeniedError),
        (404, NotFoundError),
        (422, UnprocessableEntityError),
        (429, RateLimitError),
        (500, InternalServerError),
        (502, InternalServerError),
        (503, InternalServerError),
        (504, InternalServerError),
    ],
)
def test_classify_status(status: int, klass: type[ApiError]) -> None:
    err = classify_http_error(status=status, message=f"{status}")
    assert isinstance(err, klass)
    assert err.status == status


def test_classify_429_with_retry_after() -> None:
    err = classify_http_error(status=429, message="slow", retry_after_seconds=60)
    assert isinstance(err, RateLimitError)
    assert err.retry_after_seconds == 60


def test_classify_unknown_4xx_falls_back_to_api_error() -> None:
    err = classify_http_error(status=418, message="teapot")
    assert isinstance(err, ApiError)
    assert not isinstance(err, BadRequestError)
    assert not isinstance(err, InternalServerError)
