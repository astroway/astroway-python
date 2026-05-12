"""Deterministic response cache (sync + async) — mirror of TS beta.3 / PHP beta.2."""

from __future__ import annotations

import json
import time

import httpx
import pytest

from astroway import (
    Astroway,
    AsyncAstroway,
    CacheEntry,
    DiskCache,
    MemoryCache,
    build_cache_key,
    is_deterministic_path,
)


class _RecordingTransport(httpx.BaseTransport):
    def __init__(self, responses: list[httpx.Response]) -> None:
        self._queue = list(responses)
        self.requests: list[httpx.Request] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if not self._queue:
            raise AssertionError(f"transport ran out of scripted responses; {request.method} {request.url}")
        return self._queue.pop(0)


class _RecordingAsyncTransport(httpx.AsyncBaseTransport):
    def __init__(self, responses: list[httpx.Response]) -> None:
        self._queue = list(responses)
        self.requests: list[httpx.Request] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if not self._queue:
            raise AssertionError(f"transport ran out of scripted responses; {request.method} {request.url}")
        return self._queue.pop(0)


def _ok(payload: object) -> httpx.Response:
    return httpx.Response(
        status_code=200,
        content=json.dumps({"ok": True, "data": payload}).encode(),
        headers={"content-type": "application/json"},
    )


# ─── build_cache_key ─────────────────────────────────────────────


def test_cache_key_is_order_insensitive_on_dict_keys() -> None:
    a = build_cache_key("POST", "/chart", {"date": "1990", "lat": 50.45})
    b = build_cache_key("POST", "/chart", {"lat": 50.45, "date": "1990"})
    assert a == b


def test_cache_key_differs_by_method() -> None:
    assert build_cache_key("POST", "/chart", {"x": 1}) != build_cache_key("GET", "/chart", {"x": 1})


def test_cache_key_differs_by_path() -> None:
    assert build_cache_key("POST", "/chart", {"x": 1}) != build_cache_key("POST", "/synastry", {"x": 1})


def test_cache_key_has_prefix() -> None:
    assert build_cache_key("POST", "/chart", {"x": 1}).startswith("astroway_v1_")


def test_cache_key_preserves_list_order() -> None:
    a = build_cache_key("POST", "/x", {"items": [1, 2, 3]})
    b = build_cache_key("POST", "/x", {"items": [3, 2, 1]})
    assert a != b


# ─── is_deterministic_path ───────────────────────────────────────


def test_is_deterministic_path_allows_pure_endpoints() -> None:
    assert is_deterministic_path("/chart")
    assert is_deterministic_path("/synastry")
    assert is_deterministic_path("/v1/chart")
    assert is_deterministic_path("/vedic/dasha")
    assert is_deterministic_path("/numerology/pythagorean")


def test_is_deterministic_path_denies_time_sensitive_endpoints() -> None:
    assert not is_deterministic_path("/transits")
    assert not is_deterministic_path("/horoscope/daily")
    assert not is_deterministic_path("/interpret/natal")
    assert not is_deterministic_path("/v1/transits")
    assert not is_deterministic_path("/now")


def test_is_deterministic_path_denies_unknown_by_default() -> None:
    assert not is_deterministic_path("/somethingNew")


# ─── MemoryCache ─────────────────────────────────────────────────


def test_memory_cache_round_trip() -> None:
    c = MemoryCache()
    entry = CacheEntry(value={"x": 1}, expires_at=time.time() + 100)
    c.set("k", entry)
    got = c.get("k")
    assert got is not None
    assert got.value == {"x": 1}
    assert len(c) == 1
    c.delete("k")
    assert c.get("k") is None


def test_memory_cache_clear() -> None:
    c = MemoryCache()
    c.set("a", CacheEntry(value=1, expires_at=time.time() + 100))
    c.set("b", CacheEntry(value=2, expires_at=time.time() + 100))
    c.clear()
    assert len(c) == 0


# ─── DiskCache ───────────────────────────────────────────────────


def test_disk_cache_round_trip(tmp_path) -> None:
    cache_path = str(tmp_path / "astroway-cache")
    c = DiskCache(cache_path)
    entry = CacheEntry(value={"asc": "Aries"}, expires_at=time.time() + 100)
    c.set("k", entry)
    # New instance, same file → still returns the value.
    c2 = DiskCache(cache_path)
    got = c2.get("k")
    assert got is not None
    assert got.value == {"asc": "Aries"}


# ─── End-to-end ──────────────────────────────────────────────────


def test_cache_hit_skips_http_for_deterministic_endpoint() -> None:
    transport = _RecordingTransport([_ok({"asc": "Aries"})])
    aw = Astroway(api_key="aw_x", transport=transport, cache="memory")
    try:
        a = aw.post("/chart", body={"date": "1990"})
        b = aw.post("/chart", body={"date": "1990"})
    finally:
        aw.close()
    assert a == {"asc": "Aries"}
    assert b == {"asc": "Aries"}
    assert len(transport.requests) == 1


def test_cache_key_order_insensitive_end_to_end() -> None:
    transport = _RecordingTransport([_ok("cached")])
    aw = Astroway(api_key="aw_x", transport=transport, cache="memory")
    try:
        aw.post("/chart", body={"date": "1990", "lat": 50})
        second = aw.post("/chart", body={"lat": 50, "date": "1990"})
    finally:
        aw.close()
    assert second == "cached"
    assert len(transport.requests) == 1


def test_cache_skipped_for_non_deterministic_endpoint() -> None:
    transport = _RecordingTransport([_ok("a"), _ok("b")])
    aw = Astroway(api_key="aw_x", transport=transport, cache="memory")
    try:
        a = aw.post("/transits", body={"date": "now"})
        b = aw.post("/transits", body={"date": "now"})
    finally:
        aw.close()
    assert a == "a"
    assert b == "b"
    assert len(transport.requests) == 2


def test_per_call_cache_true_forces_cache_on_non_deterministic() -> None:
    transport = _RecordingTransport([_ok("forced")])
    aw = Astroway(api_key="aw_x", transport=transport, cache="memory")
    try:
        first = aw.request("POST", "/transits", body={"x": 1}, cache=True)
        second = aw.request("POST", "/transits", body={"x": 1}, cache=True)
    finally:
        aw.close()
    assert first == "forced"
    assert second == "forced"
    assert len(transport.requests) == 1


def test_per_call_cache_false_skips_cache_on_deterministic() -> None:
    transport = _RecordingTransport([_ok("fresh-1"), _ok("fresh-2")])
    aw = Astroway(api_key="aw_x", transport=transport, cache="memory")
    try:
        a = aw.request("POST", "/chart", body={"x": 1}, cache=False)
        b = aw.request("POST", "/chart", body={"x": 1}, cache=False)
    finally:
        aw.close()
    assert a == "fresh-1"
    assert b == "fresh-2"
    assert len(transport.requests) == 2


def test_no_cache_config_behaves_like_b2() -> None:
    transport = _RecordingTransport([_ok("1"), _ok("2")])
    aw = Astroway(api_key="aw_x", transport=transport)
    try:
        aw.post("/chart", body={"date": "1990"})
        aw.post("/chart", body={"date": "1990"})
    finally:
        aw.close()
    assert len(transport.requests) == 2


def test_expired_entry_not_served() -> None:
    transport = _RecordingTransport([_ok("fresh")])
    cache = MemoryCache()
    cache.set(
        build_cache_key("POST", "/chart", {"date": "1990"}),
        CacheEntry(value="stale", expires_at=time.time() - 10),
    )
    from astroway._cache import ResolvedCache
    aw = Astroway(api_key="aw_x", transport=transport, cache=ResolvedCache(store=cache))
    try:
        result = aw.post("/chart", body={"date": "1990"})
    finally:
        aw.close()
    assert result == "fresh"
    assert len(transport.requests) == 1


def test_invalid_cache_option_raises() -> None:
    with pytest.raises(TypeError):
        Astroway(api_key="aw_x", cache=42)


# ─── Async ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_async_cache_hit_skips_http() -> None:
    transport = _RecordingAsyncTransport([_ok({"asc": "Aries"})])
    aw = AsyncAstroway(api_key="aw_x", transport=transport, cache="memory")
    try:
        a = await aw.post("/chart", body={"date": "1990"})
        b = await aw.post("/chart", body={"date": "1990"})
    finally:
        await aw.aclose()
    assert a == {"asc": "Aries"}
    assert b == {"asc": "Aries"}
    assert len(transport.requests) == 1
