"""Idempotency-Key auto-attachment + per-call override + custom generator."""

from __future__ import annotations

import json
import re

import httpx
import pytest

from astroway import Astroway, AsyncAstroway, generate_idempotency_key

_UUID4 = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)


class _Recorder(httpx.BaseTransport):
    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(
            200,
            content=json.dumps({"ok": True, "data": {}}).encode("utf-8"),
            headers={"content-type": "application/json"},
        )


class _AsyncRecorder(httpx.AsyncBaseTransport):
    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return httpx.Response(
            200,
            content=json.dumps({"ok": True, "data": {}}).encode("utf-8"),
            headers={"content-type": "application/json"},
        )


def test_generate_key_returns_uuid4_shape() -> None:
    for _ in range(5):
        assert _UUID4.match(generate_idempotency_key())


def test_generate_key_is_unique() -> None:
    seen = {generate_idempotency_key() for _ in range(50)}
    assert len(seen) == 50


def test_post_attaches_idempotency_key_by_default() -> None:
    transport = _Recorder()
    aw = Astroway(api_key="aw_test_x", transport=transport)
    aw.post("/chart", body={"date": "1990-07-14", "time": "14:30:00"})
    assert _UUID4.match(transport.requests[0].headers["idempotency-key"])


def test_get_does_not_attach_idempotency_key() -> None:
    transport = _Recorder()
    aw = Astroway(api_key="aw_test_x", transport=transport)
    aw.get("/health")
    assert "idempotency-key" not in transport.requests[0].headers


def test_per_call_idempotency_key_wins() -> None:
    transport = _Recorder()
    aw = Astroway(api_key="aw_test_x", transport=transport)
    aw.post("/chart", body={"date": "1990-07-14", "time": "14:30:00"}, idempotency_key="my-key-123")
    assert transport.requests[0].headers["idempotency-key"] == "my-key-123"


def test_idempotency_off_disables_auto_generation() -> None:
    transport = _Recorder()
    aw = Astroway(api_key="aw_test_x", transport=transport, idempotency="off")
    aw.post("/chart", body={"date": "1990-07-14", "time": "14:30:00"})
    assert "idempotency-key" not in transport.requests[0].headers


def test_custom_generator_callable() -> None:
    transport = _Recorder()
    counter = {"n": 0}

    def gen() -> str:
        counter["n"] += 1
        return f"test-{counter['n']}"

    aw = Astroway(api_key="aw_test_x", transport=transport, idempotency=gen)
    aw.post("/chart", body={})
    aw.post("/chart", body={})
    assert transport.requests[0].headers["idempotency-key"] == "test-1"
    assert transport.requests[1].headers["idempotency-key"] == "test-2"


def test_namespace_method_idempotency_key_kwarg() -> None:
    transport = _Recorder()
    aw = Astroway(api_key="aw_test_x", transport=transport)
    aw.synastry.aspect_grid({}, idempotency_key="replay-abc")  # type: ignore[attr-defined]
    assert transport.requests[0].headers["idempotency-key"] == "replay-abc"


def test_namespace_method_auto_attaches_when_no_kwarg() -> None:
    transport = _Recorder()
    aw = Astroway(api_key="aw_test_x", transport=transport)
    aw.synastry.aspect_grid({})  # type: ignore[attr-defined]
    assert _UUID4.match(transport.requests[0].headers["idempotency-key"])


@pytest.mark.asyncio
async def test_async_post_attaches_idempotency_key() -> None:
    transport = _AsyncRecorder()
    async with AsyncAstroway(api_key="aw_test_x", transport=transport) as aw:
        await aw.post("/chart", body={})
    assert _UUID4.match(transport.requests[0].headers["idempotency-key"])
