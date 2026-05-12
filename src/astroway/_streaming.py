"""Server-Sent Events streaming for AI horoscope / interpret endpoints.

Mirror of ``@astroway/sdk`` v0.1.0-beta.2. Public surface follows
`OpenAI`/`Anthropic` patterns — iterate over normalised chunks::

    for chunk in aw.stream_sse("/horoscope/daily", body={"date": "2026-05-10"}):
        if chunk.type == "text_delta":
            print(chunk.text, end="", flush=True)
        elif chunk.type == "done":
            break

Wire format follows the SSE spec
(`html.spec.whatwg.org/multipage/server-sent-events.html`). Each event is a
block of lines separated by ``\\n``, blocks separated by ``\\n\\n``. Lines
starting with ``event:`` set the event type, ``data:`` lines are concatenated
with ``\\n``.

The async client mirrors the sync API via ``async for chunk in
aw.stream_sse(...)``.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, Union

import httpx

from ._idempotency import resolve_key_generator, should_attach_idempotency
from .errors import APIConnectionError, ApiError, APITimeoutError, classify_http_error

if TYPE_CHECKING:
    from ._client import Astroway, AsyncAstroway


@dataclass(frozen=True)
class SSEEvent:
    """Raw SSE event after parsing — what the lower-level iterator yields."""

    event: str
    data: Any
    raw_data: str
    id: str | None = None
    retry: int | None = None


@dataclass(frozen=True)
class TextDelta:
    type: Literal["text_delta"]
    text: str
    raw: SSEEvent


@dataclass(frozen=True)
class StreamDone:
    type: Literal["done"]
    raw: SSEEvent


@dataclass(frozen=True)
class StreamError:
    type: Literal["error"]
    message: str
    raw: SSEEvent
    code: str | None = None


@dataclass(frozen=True)
class StreamEvent:
    """Catch-all for unknown event names — lets server-side additions land
    without breaking user code."""

    type: Literal["event"]
    event: str
    data: Any
    raw: SSEEvent


StreamChunk = Union[TextDelta, StreamDone, StreamError, StreamEvent]


def _decode_data(raw_data: str) -> Any:
    if raw_data == "":
        return raw_data
    try:
        return json.loads(raw_data)
    except (json.JSONDecodeError, ValueError):
        return raw_data


def _build_event(
    event_name: str,
    data_lines: list[str],
    event_id: str | None,
    retry: int | None,
) -> SSEEvent:
    raw_data = "\n".join(data_lines)
    return SSEEvent(
        event=event_name or "message",
        data=_decode_data(raw_data),
        raw_data=raw_data,
        id=event_id,
        retry=retry,
    )


def _process_line(
    line: str,
    state: dict[str, Any],
) -> None:
    if line.startswith(":"):
        return  # Comment.
    colon_idx = line.find(":")
    if colon_idx == -1:
        field, value = line, ""
    else:
        field = line[:colon_idx]
        value = line[colon_idx + 1 :]
        if value.startswith(" "):
            value = value[1:]
    if field == "event":
        state["event"] = value
    elif field == "data":
        state["data"].append(value)
    elif field == "id":
        state["id"] = value
    elif field == "retry":
        try:
            state["retry"] = int(value)
        except ValueError:
            pass
    # Unknown fields silently ignored per spec.


def _new_state() -> dict[str, Any]:
    return {"event": "", "data": [], "id": None, "retry": None}


def _normalise(event: SSEEvent) -> StreamChunk:
    if event.event == "text_delta":
        if isinstance(event.data, str):
            text = event.data
        elif isinstance(event.data, dict):
            text = str(event.data.get("text", event.raw_data))
        else:
            text = event.raw_data
        return TextDelta(type="text_delta", text=text, raw=event)
    if event.event in ("done", "end", "message_stop"):
        return StreamDone(type="done", raw=event)
    if event.event == "error":
        err = event.data if isinstance(event.data, dict) else {}
        return StreamError(
            type="error",
            message=str(err.get("message", "stream emitted error event")),
            code=str(err["code"]) if err.get("code") is not None else None,
            raw=event,
        )
    return StreamEvent(type="event", event=event.event, data=event.data, raw=event)


def parse_sse_sync(response: httpx.Response) -> Iterator[SSEEvent]:
    """Yield parsed SSE events from a streamed httpx response (sync)."""
    state = _new_state()
    buffer = ""
    for raw_chunk in response.iter_text():
        buffer += raw_chunk
        while "\n" in buffer:
            line, _, buffer = buffer.partition("\n")
            line = line.rstrip("\r")
            if line == "":
                if state["data"] or state["event"]:
                    yield _build_event(state["event"], state["data"], state["id"], state["retry"])
                state = _new_state()
            else:
                _process_line(line, state)
    if buffer:
        _process_line(buffer.rstrip("\r"), state)
    if state["data"] or state["event"]:
        yield _build_event(state["event"], state["data"], state["id"], state["retry"])


async def parse_sse_async(response: httpx.Response) -> AsyncIterator[SSEEvent]:
    """Yield parsed SSE events from a streamed httpx response (async)."""
    state = _new_state()
    buffer = ""
    async for raw_chunk in response.aiter_text():
        buffer += raw_chunk
        while "\n" in buffer:
            line, _, buffer = buffer.partition("\n")
            line = line.rstrip("\r")
            if line == "":
                if state["data"] or state["event"]:
                    yield _build_event(state["event"], state["data"], state["id"], state["retry"])
                state = _new_state()
            else:
                _process_line(line, state)
    if buffer:
        _process_line(buffer.rstrip("\r"), state)
    if state["data"] or state["event"]:
        yield _build_event(state["event"], state["data"], state["id"], state["retry"])


def _maybe_classify(response: httpx.Response) -> None:
    if response.is_success:
        return
    request_id = response.headers.get("x-request-id")
    retry_after = response.headers.get("retry-after")
    credits = response.headers.get("x-credits-remaining")
    body: Any = None
    code: str | None = None
    message = f"{response.status_code} {response.reason_phrase}"
    try:
        text = response.read().decode("utf-8")
        if text:
            body = json.loads(text)
            err = body.get("error") if isinstance(body, dict) else None
            if isinstance(err, dict):
                if err.get("code"):
                    code = str(err["code"])
                if err.get("message"):
                    message = str(err["message"])
    except Exception:
        pass

    raise classify_http_error(
        status=response.status_code,
        message=message,
        code=code,
        body=body,
        request_id=request_id,
        retry_after_seconds=int(retry_after) if retry_after and retry_after.isdigit() else None,
        credits_remaining=int(credits) if credits and credits.isdigit() else None,
    )


class SyncSSEStream:
    """Sync SSE stream. Iterate to walk normalised chunks; ``raw_events()`` for
    the underlying ``SSEEvent`` objects.
    """

    def __init__(
        self,
        client: Astroway,
        method: str,
        path: str,
        *,
        body: Any | None = None,
        params: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> None:
        self._client = client
        self._method = method.upper()
        self._path = path
        self._body = body
        self._params = params or {}
        self._idempotency_key = idempotency_key

    def __iter__(self) -> Iterator[StreamChunk]:
        for event in self.raw_events():
            yield _normalise(event)

    def raw_events(self) -> Iterator[SSEEvent]:
        headers = self._build_headers()
        try:
            with self._client._http.stream(
                self._method,
                self._path,
                json=self._body,
                params=self._params or None,
                headers=headers,
            ) as response:
                _maybe_classify(response)
                yield from parse_sse_sync(response)
        except httpx.TimeoutException as exc:
            raise APITimeoutError(f"Stream to {self._path} timed out") from exc
        except httpx.HTTPError as exc:
            if isinstance(exc, ApiError):
                raise
            raise APIConnectionError(
                f"Network error opening stream to {self._path}: {exc!s}"
            ) from exc

    def _build_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": "text/event-stream"}
        if self._idempotency_key is not None:
            headers["Idempotency-Key"] = self._idempotency_key
        elif should_attach_idempotency(self._client.idempotency, self._method):
            headers["Idempotency-Key"] = resolve_key_generator(self._client.idempotency)()
        return headers


class AsyncSSEStream:
    """Async SSE stream. Iterate via ``async for chunk in stream``;
    ``raw_events()`` for raw SSE events.
    """

    def __init__(
        self,
        client: AsyncAstroway,
        method: str,
        path: str,
        *,
        body: Any | None = None,
        params: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> None:
        self._client = client
        self._method = method.upper()
        self._path = path
        self._body = body
        self._params = params or {}
        self._idempotency_key = idempotency_key

    async def __aiter__(self) -> AsyncIterator[StreamChunk]:
        async for event in self.raw_events():
            yield _normalise(event)

    async def raw_events(self) -> AsyncIterator[SSEEvent]:
        headers = self._build_headers()
        try:
            async with self._client._http.stream(
                self._method,
                self._path,
                json=self._body,
                params=self._params or None,
                headers=headers,
            ) as response:
                _maybe_classify(response)
                async for event in parse_sse_async(response):
                    yield event
        except httpx.TimeoutException as exc:
            raise APITimeoutError(f"Stream to {self._path} timed out") from exc
        except httpx.HTTPError as exc:
            if isinstance(exc, ApiError):
                raise
            raise APIConnectionError(
                f"Network error opening stream to {self._path}: {exc!s}"
            ) from exc

    def _build_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": "text/event-stream"}
        if self._idempotency_key is not None:
            headers["Idempotency-Key"] = self._idempotency_key
        elif should_attach_idempotency(self._client.idempotency, self._method):
            headers["Idempotency-Key"] = resolve_key_generator(self._client.idempotency)()
        return headers
