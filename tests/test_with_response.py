"""with_response() metadata + refined error types (QuotaExceededError, CalculationError)."""

from __future__ import annotations

import json

import httpx
import pytest

from astroway import (
    Astroway,
    AsyncAstroway,
    CalculationError,
    QuotaExceededError,
    RateLimitError,
)


class _Recorder(httpx.BaseTransport):
    def __init__(self, response: httpx.Response) -> None:
        self.response = response

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        return self.response


class _AsyncRecorder(httpx.AsyncBaseTransport):
    def __init__(self, response: httpx.Response) -> None:
        self.response = response

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        return self.response


def _ok(data: object, headers: dict[str, str] | None = None) -> httpx.Response:
    return httpx.Response(
        200,
        content=json.dumps({"ok": True, "data": data}).encode("utf-8"),
        headers={"content-type": "application/json", **(headers or {})},
    )


def _err(status: int, code: str, headers: dict[str, str] | None = None) -> httpx.Response:
    return httpx.Response(
        status,
        content=json.dumps({"ok": False, "error": {"code": code, "message": code}}).encode("utf-8"),
        headers={"content-type": "application/json", **(headers or {})},
    )


# ─── Refined error classification ────────────────────────────────


def test_out_of_credits_code_classifies_as_quota_exceeded() -> None:
    aw = Astroway(api_key="aw_test_x", transport=_Recorder(_err(400, "OUT_OF_CREDITS")), retry={"max_retries": 0})
    with pytest.raises(QuotaExceededError):
        aw.post("/chart", body={})


def test_http_402_classifies_as_quota_exceeded() -> None:
    aw = Astroway(api_key="aw_test_x", transport=_Recorder(_err(402, "PAYMENT_REQUIRED")), retry={"max_retries": 0})
    with pytest.raises(QuotaExceededError):
        aw.post("/chart", body={})


def test_calculation_error_code_classifies_as_calculation_error() -> None:
    aw = Astroway(api_key="aw_test_x", transport=_Recorder(_err(422, "CALCULATION_ERROR")), retry={"max_retries": 0})
    with pytest.raises(CalculationError):
        aw.post("/chart", body={})


def test_rate_limit_with_retry_after_uses_uniform_field() -> None:
    aw = Astroway(
        api_key="aw_test_x",
        transport=_Recorder(_err(429, "RATE_LIMIT", headers={"retry-after": "30"})),
        retry={"max_retries": 0},
    )
    try:
        aw.post("/chart", body={})
        pytest.fail("expected RateLimitError")
    except RateLimitError as e:
        assert e.retry_after_seconds == 30


def test_credits_remaining_surfaced_on_error() -> None:
    aw = Astroway(
        api_key="aw_test_x",
        transport=_Recorder(_err(402, "OUT_OF_CREDITS", headers={"x-credits-remaining": "0", "x-request-id": "req_xyz"})),
        retry={"max_retries": 0},
    )
    try:
        aw.post("/chart", body={})
        pytest.fail("expected QuotaExceededError")
    except QuotaExceededError as e:
        assert e.credits_remaining == 0
        assert e.request_id == "req_xyz"


# ─── with_response() metadata ────────────────────────────────────


def test_post_with_response_returns_data_plus_metadata() -> None:
    aw = Astroway(
        api_key="aw_test_x",
        transport=_Recorder(_ok({"v": 1}, headers={"x-request-id": "req_abc", "x-credits-remaining": "4321"})),
    )
    raw = aw.post_with_response("/chart", body={})
    assert raw.data == {"v": 1}
    assert raw.request_id == "req_abc"
    assert raw.credits_remaining == 4321
    assert raw.status_code == 200


def test_post_with_response_metadata_undefined_when_headers_absent() -> None:
    aw = Astroway(api_key="aw_test_x", transport=_Recorder(_ok({"v": 2})))
    raw = aw.post_with_response("/chart", body={})
    assert raw.data == {"v": 2}
    assert raw.request_id is None
    assert raw.credits_remaining is None


def test_request_with_response_works_for_arbitrary_method() -> None:
    aw = Astroway(api_key="aw_test_x", transport=_Recorder(_ok([1, 2, 3])))
    raw = aw.request_with_response("POST", "/transits", body={})
    assert raw.data == [1, 2, 3]


@pytest.mark.asyncio
async def test_async_post_with_response() -> None:
    transport = _AsyncRecorder(_ok({"v": 3}, headers={"x-request-id": "req_async"}))
    async with AsyncAstroway(api_key="aw_test_x", transport=transport) as aw:
        raw = await aw.post_with_response("/chart", body={})
    assert raw.data == {"v": 3}
    assert raw.request_id == "req_async"
