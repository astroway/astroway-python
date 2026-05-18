"""Astroway client behavior — auth headers, error mapping, response unwrap."""

from __future__ import annotations

import json

import httpx
import pytest

from astroway import (
    ApiError,
    Astroway,
    AsyncAstroway,
    AuthenticationError,
    BadRequestError,
    RateLimitError,
)


class _RecordingTransport(httpx.BaseTransport):
    """Captures the latest request, returns a scripted response."""

    def __init__(self, response: httpx.Response) -> None:
        self.response = response
        self.last_request: httpx.Request | None = None

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.last_request = request
        return self.response


class _RecordingAsyncTransport(httpx.AsyncBaseTransport):
    def __init__(self, response: httpx.Response) -> None:
        self.response = response
        self.last_request: httpx.Request | None = None

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.last_request = request
        return self.response


def _ok_response(payload: object) -> httpx.Response:
    return httpx.Response(
        status_code=200,
        content=json.dumps({"ok": True, "data": payload}).encode("utf-8"),
        headers={"content-type": "application/json"},
    )


def _error_response(status: int, code: str, message: str, headers: dict | None = None) -> httpx.Response:
    return httpx.Response(
        status_code=status,
        content=json.dumps({"ok": False, "error": {"code": code, "message": message}}).encode(
            "utf-8"
        ),
        headers={"content-type": "application/json", **(headers or {})},
    )


# ─── Constructor + defaults ──────────────────────────────────────


def test_constructor_requires_api_key() -> None:
    with pytest.raises(ApiError):
        Astroway(api_key="")


def test_default_base_url() -> None:
    aw = Astroway(api_key="aw_test_x")
    assert aw.base_url == "https://api.astroway.info/v1"
    aw.close()


def test_custom_base_url() -> None:
    aw = Astroway(api_key="aw_test_x", base_url="http://localhost:3101/api/v1")
    assert aw.base_url == "http://localhost:3101/api/v1"
    aw.close()


def test_default_auth_scheme_is_header() -> None:
    aw = Astroway(api_key="aw_test_x")
    assert aw.auth_scheme == "header"
    aw.close()


# ─── Header propagation ──────────────────────────────────────────


def test_x_api_key_header_by_default() -> None:
    inner = _RecordingTransport(_ok_response({"ok": True}))
    aw = Astroway(api_key="aw_test_secret", transport=inner)
    aw.post(
        "/chart",
        body={
            "date": "1990-07-14",
            "time": "14:30:00",
            "timezoneOffset": 3,
            "latitude": 50.45,
            "longitude": 30.52,
        },
    )
    aw.close()
    assert inner.last_request is not None
    assert inner.last_request.headers["x-api-key"] == "aw_test_secret"
    assert inner.last_request.headers.get("authorization") is None
    assert inner.last_request.headers["x-astroway-channel"] == "sdk-py"
    assert inner.last_request.headers["user-agent"].startswith("astroway-sdk-python/")


def test_bearer_when_auth_scheme_bearer() -> None:
    inner = _RecordingTransport(_ok_response({}))
    aw = Astroway(api_key="aw_test_bearer", auth_scheme="bearer", transport=inner)
    aw.post("/chart", body={})
    aw.close()
    assert inner.last_request is not None
    assert inner.last_request.headers["authorization"] == "Bearer aw_test_bearer"
    assert inner.last_request.headers.get("x-api-key") is None


def test_lang_option_sets_accept_language() -> None:
    inner = _RecordingTransport(_ok_response({}))
    aw = Astroway(api_key="aw_test", lang="hi", transport=inner)
    aw.post("/horoscope/daily", body={"sign": "leo"})
    aw.close()
    assert inner.last_request is not None
    assert inner.last_request.headers["accept-language"] == "hi"
    assert aw.lang == "hi"


def test_lang_default_unset_emits_no_accept_language() -> None:
    inner = _RecordingTransport(_ok_response({}))
    aw = Astroway(api_key="aw_test", transport=inner)
    aw.post("/horoscope/daily", body={"sign": "leo"})
    aw.close()
    assert inner.last_request is not None
    # httpx adds its own default Accept-Language; SDK should not inject one.
    assert "accept-language" not in {k.lower() for k in inner.last_request.headers if k.lower() == "accept-language" and inner.last_request.headers[k] in ("hi", "de", "uk")}
    assert aw.lang is None


def test_default_headers_accept_language_wins() -> None:
    inner = _RecordingTransport(_ok_response({}))
    aw = Astroway(
        api_key="aw_test",
        lang="hi",
        default_headers={"Accept-Language": "de"},
        transport=inner,
    )
    aw.post("/horoscope/daily", body={"sign": "leo"})
    aw.close()
    assert inner.last_request is not None
    assert inner.last_request.headers["accept-language"] == "de"


# ─── Error mapping ───────────────────────────────────────────────


def test_raises_authentication_error_on_401() -> None:
    inner = _RecordingTransport(_error_response(401, "INVALID_KEY", "API key is invalid"))
    aw = Astroway(api_key="aw_test_x", transport=inner, retry={"max_retries": 0})
    with pytest.raises(AuthenticationError) as ei:
        aw.post("/chart", body={})
    aw.close()
    assert ei.value.status == 401
    assert ei.value.code == "INVALID_KEY"
    assert "invalid" in str(ei.value).lower()


def test_raises_rate_limit_with_retry_after() -> None:
    inner = _RecordingTransport(
        _error_response(429, "RATE_LIMITED", "Slow down", headers={"retry-after": "15"})
    )
    aw = Astroway(api_key="aw_test_x", transport=inner, retry={"max_retries": 0})
    with pytest.raises(RateLimitError) as ei:
        aw.post("/chart", body={})
    aw.close()
    assert ei.value.retry_after_seconds == 15


def test_raises_bad_request_on_400() -> None:
    inner = _RecordingTransport(_error_response(400, "BAD_REQUEST", "missing field"))
    aw = Astroway(api_key="aw_test_x", transport=inner, retry={"max_retries": 0})
    with pytest.raises(BadRequestError):
        aw.post("/chart", body={})
    aw.close()


def test_request_id_captured_from_x_request_id() -> None:
    response = httpx.Response(
        status_code=500,
        content=b'{"ok":false,"error":{"message":"oops"}}',
        headers={"content-type": "application/json", "x-request-id": "req_xyz"},
    )
    inner = _RecordingTransport(response)
    aw = Astroway(api_key="aw_test_x", transport=inner, retry={"max_retries": 0})
    with pytest.raises(ApiError) as ei:
        aw.post("/chart", body={})
    aw.close()
    assert ei.value.request_id == "req_xyz"


# ─── Response unwrap ─────────────────────────────────────────────


def test_unwraps_data_envelope_on_success() -> None:
    payload = {"angles": {"asc": {"sign": "leo", "degree": 12.34}}}
    inner = _RecordingTransport(_ok_response(payload))
    aw = Astroway(api_key="aw_test_x", transport=inner)
    result = aw.post("/chart", body={})
    aw.close()
    assert result == payload


# ─── Async client ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_async_x_api_key_header() -> None:
    inner = _RecordingAsyncTransport(_ok_response({"async": True}))
    async with AsyncAstroway(api_key="aw_test_async", transport=inner) as aw:
        result = await aw.post("/chart", body={})
    assert result == {"async": True}
    assert inner.last_request is not None
    assert inner.last_request.headers["x-api-key"] == "aw_test_async"
    assert inner.last_request.headers["x-astroway-channel"] == "sdk-py"


@pytest.mark.asyncio
async def test_async_raises_auth_error() -> None:
    inner = _RecordingAsyncTransport(_error_response(401, "INVALID_KEY", "bad key"))
    async with AsyncAstroway(api_key="aw_test_x", transport=inner, retry={"max_retries": 0}) as aw:
        with pytest.raises(AuthenticationError):
            await aw.post("/chart", body={})
