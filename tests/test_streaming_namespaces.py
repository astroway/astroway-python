"""The two `/mcp/*` endpoints that answer `text/event-stream`.

They were generated as ordinary JSON methods, so `aw.mcp.streaming()` asked
`request()` to parse `data: {"type":"token"...}` as a body. Nobody hit it: no
README or example ever showed the method. When api-calc corrected the declared
media type, the JSON filter in the generator dropped them instead, which would
have removed two methods from the published surface.

They are streaming methods now, and the normaliser understands the frames our
own endpoints send.
"""

from __future__ import annotations

import astroway
from astroway._streaming import SSEEvent, StreamDone, StreamEvent, TextDelta, _normalise


def test_streaming_methods_return_a_stream_not_a_body() -> None:
    aw = astroway.Astroway(api_key="aw_test_x")
    for name in ("streaming", "tool_call_stream"):
        method = getattr(aw.mcp, name)
        assert callable(method)
        assert "SSEStream" in str(method.__annotations__.get("return", ""))


def test_a_json_sibling_in_the_same_namespace_keeps_its_shape() -> None:
    aw = astroway.Astroway(api_key="aw_test_x")
    assert "SSEStream" not in str(aw.mcp.rag_search.__annotations__.get("return", ""))


def test_normalise_understands_the_mcp_frame_shape() -> None:
    """No event name, the kind sits in the payload."""
    chunk = _normalise(SSEEvent(
        event="message",
        data={"type": "token", "text": "A stellium "},
        raw_data='{"type":"token","text":"A stellium "}',
        id=None,
        retry=None,
    ))
    assert isinstance(chunk, TextDelta)
    assert chunk.text == "A stellium "


def test_normalise_understands_the_dev_assistant_frame_shape() -> None:
    """`event: token` with a `delta` field."""
    chunk = _normalise(SSEEvent(
        event="token", data={"delta": "Hi"}, raw_data='{"delta":"Hi"}', id=None, retry=None,
    ))
    assert isinstance(chunk, TextDelta)
    assert chunk.text == "Hi"


def test_a_known_event_name_still_wins_over_the_payload() -> None:
    chunk = _normalise(SSEEvent(
        event="done", data={"type": "token", "text": "ignored"},
        raw_data='{"type":"token"}', id=None, retry=None,
    ))
    assert isinstance(chunk, StreamDone)


def test_anything_else_still_falls_through() -> None:
    chunk = _normalise(SSEEvent(
        event="ping", data={"type": "heartbeat"}, raw_data="{}", id=None, retry=None,
    ))
    assert isinstance(chunk, StreamEvent)
