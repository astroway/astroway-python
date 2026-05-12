"""SSE streaming for AI endpoints — sync + async iterators."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from astroway import (
    Astroway,
    AsyncAstroway,
    AuthenticationError,
    SSEEvent,
    StreamDone,
    StreamError,
    StreamEvent,
    TextDelta,
)
from astroway._streaming import _normalise


def _sse_response(body: str | bytes) -> httpx.Response:
    return httpx.Response(
        status_code=200,
        content=body if isinstance(body, bytes) else body.encode("utf-8"),
        headers={"content-type": "text/event-stream"},
    )


def _err_response(status: int, code: str, message: str) -> httpx.Response:
    return httpx.Response(
        status_code=status,
        content=json.dumps({"ok": False, "error": {"code": code, "message": message}}).encode(),
        headers={"content-type": "application/json"},
    )


class _ScriptedTransport(httpx.BaseTransport):
    def __init__(self, response: httpx.Response) -> None:
        self.response = response
        self.last_request: httpx.Request | None = None

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.last_request = request
        return self.response


class _AsyncScriptedTransport(httpx.AsyncBaseTransport):
    def __init__(self, response: httpx.Response) -> None:
        self.response = response
        self.last_request: httpx.Request | None = None

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.last_request = request
        return self.response


# ─── normalise ───────────────────────────────────────────────────


def test_normalise_text_delta_string() -> None:
    chunk = _normalise(SSEEvent(event="text_delta", data="hi", raw_data="hi"))
    assert isinstance(chunk, TextDelta)
    assert chunk.text == "hi"


def test_normalise_text_delta_object() -> None:
    chunk = _normalise(SSEEvent(event="text_delta", data={"text": "hello"}, raw_data='{"text":"hello"}'))
    assert isinstance(chunk, TextDelta)
    assert chunk.text == "hello"


def test_normalise_done_aliases() -> None:
    for name in ("done", "end", "message_stop"):
        chunk = _normalise(SSEEvent(event=name, data="", raw_data=""))
        assert isinstance(chunk, StreamDone)


def test_normalise_error_with_code() -> None:
    chunk = _normalise(
        SSEEvent(event="error", data={"message": "bad", "code": "E_BAD"}, raw_data=""),
    )
    assert isinstance(chunk, StreamError)
    assert chunk.message == "bad"
    assert chunk.code == "E_BAD"


def test_normalise_unknown_event_passthrough() -> None:
    chunk = _normalise(SSEEvent(event="custom", data={"x": 1}, raw_data='{"x":1}'))
    assert isinstance(chunk, StreamEvent)
    assert chunk.event == "custom"
    assert chunk.data == {"x": 1}


# ─── Sync streaming ──────────────────────────────────────────────


def test_sync_stream_yields_normalised_chunks() -> None:
    body = (
        'event: text_delta\ndata: {"text":"Hello "}\n\n'
        'event: text_delta\ndata: {"text":"world"}\n\n'
        'event: done\ndata: {}\n\n'
    )
    transport = _ScriptedTransport(_sse_response(body))
    aw = Astroway(api_key="aw_test_x", transport=transport)
    try:
        chunks = list(aw.stream_sse("/horoscope/daily", body={"date": "2026-05-10"}))
    finally:
        aw.close()
    assert [c.type for c in chunks] == ["text_delta", "text_delta", "done"]
    text = "".join(c.text for c in chunks if isinstance(c, TextDelta))
    assert text == "Hello world"


def test_sync_stream_sends_accept_sse_header() -> None:
    transport = _ScriptedTransport(_sse_response("event: done\ndata: {}\n\n"))
    aw = Astroway(api_key="aw_test_x", transport=transport)
    try:
        list(aw.stream_sse("/horoscope/daily", body={}))
    finally:
        aw.close()
    assert transport.last_request is not None
    assert transport.last_request.headers["accept"] == "text/event-stream"
    assert transport.last_request.headers["x-api-key"] == "aw_test_x"
    assert transport.last_request.method == "POST"


def test_sync_stream_auto_attaches_idempotency_key_on_post() -> None:
    transport = _ScriptedTransport(_sse_response("event: done\ndata: {}\n\n"))
    aw = Astroway(api_key="aw_test_x", transport=transport)
    try:
        list(aw.stream_sse("/horoscope/daily", body={}))
    finally:
        aw.close()
    assert transport.last_request is not None
    assert "idempotency-key" in transport.last_request.headers


def test_sync_stream_honours_user_supplied_idempotency_key() -> None:
    transport = _ScriptedTransport(_sse_response("event: done\ndata: {}\n\n"))
    aw = Astroway(api_key="aw_test_x", transport=transport)
    try:
        list(aw.stream_sse("/horoscope/daily", body={}, idempotency_key="fixed-123"))
    finally:
        aw.close()
    assert transport.last_request is not None
    assert transport.last_request.headers["idempotency-key"] == "fixed-123"


def test_sync_stream_classifies_http_error() -> None:
    transport = _ScriptedTransport(_err_response(401, "INVALID_API_KEY", "bad"))
    aw = Astroway(api_key="aw_test_x", transport=transport)
    try:
        with pytest.raises(AuthenticationError):
            list(aw.stream_sse("/horoscope/daily", body={}))
    finally:
        aw.close()


def test_sync_stream_handles_multiline_data() -> None:
    body = "data: line1\ndata: line2\n\nevent: done\ndata: {}\n\n"
    transport = _ScriptedTransport(_sse_response(body))
    aw = Astroway(api_key="aw_test_x", transport=transport)
    try:
        chunks = list(aw.stream_sse("/anything", body={}))
    finally:
        aw.close()
    # First event has unknown name "message" → falls through as StreamEvent
    assert isinstance(chunks[0], StreamEvent)
    assert chunks[0].raw.raw_data == "line1\nline2"


def test_sync_stream_skips_comments() -> None:
    body = ": keep-alive\nevent: text_delta\ndata: hi\n\nevent: done\ndata: {}\n\n"
    transport = _ScriptedTransport(_sse_response(body))
    aw = Astroway(api_key="aw_test_x", transport=transport)
    try:
        chunks = list(aw.stream_sse("/anything", body={}))
    finally:
        aw.close()
    assert [c.type for c in chunks] == ["text_delta", "done"]


# ─── Async streaming ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_async_stream_yields_chunks() -> None:
    body = (
        'event: text_delta\ndata: {"text":"async "}\n\n'
        'event: text_delta\ndata: {"text":"works"}\n\n'
        'event: done\ndata: {}\n\n'
    )
    transport = _AsyncScriptedTransport(_sse_response(body))
    aw = AsyncAstroway(api_key="aw_test_x", transport=transport)
    try:
        chunks: list[Any] = []
        async for chunk in aw.stream_sse("/horoscope/daily", body={"date": "2026-05-10"}):
            chunks.append(chunk)
    finally:
        await aw.aclose()
    assert [c.type for c in chunks] == ["text_delta", "text_delta", "done"]
    text = "".join(c.text for c in chunks if isinstance(c, TextDelta))
    assert text == "async works"


@pytest.mark.asyncio
async def test_async_stream_classifies_http_error() -> None:
    transport = _AsyncScriptedTransport(_err_response(401, "INVALID_API_KEY", "bad"))
    aw = AsyncAstroway(api_key="aw_test_x", transport=transport)
    try:
        with pytest.raises(AuthenticationError):
            async for _ in aw.stream_sse("/horoscope/daily", body={}):
                pass
    finally:
        await aw.aclose()
