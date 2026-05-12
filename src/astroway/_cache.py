"""Deterministic response cache.

Mirror of ``@astroway/sdk`` v0.1.0-beta.3 (TS) and ``astroway/sdk`` v0.1.0-beta.2 (PHP).

Charts are pure functions of ``(date, time, lat, lon, tz)``. Caching them
client-side saves credits and makes dev loops instant. None of the public
astrology APIs do this — pure differentiator vs Prokerala / Astrologer.

Three flavours of cache:

  - ``cache="memory"`` — in-process dict, fast for tests / short-lived processes
  - ``cache=DiskCache(path)`` — file-backed (uses stdlib ``shelve``)
  - bring-your-own — anything implementing the ``CacheStore`` protocol

Default policy: pure-function endpoints (chart/synastry/vedic/numerology/...) are
cached automatically; time-sensitive endpoints (transits/horoscope/interpret/...)
are skipped. Override per call via ``cache=True`` / ``cache=False``.
"""

from __future__ import annotations

import hashlib
import json
import shelve
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Protocol, Union, runtime_checkable

CACHE_KEY_PREFIX = "astroway_v1_"
DEFAULT_CACHE_TTL_SECONDS = 86_400  # 24h

DETERMINISTIC_PATH_PREFIXES: tuple[str, ...] = (
    "/chart",
    "/synastry",
    "/composite",
    "/midpoints",
    "/aspects",
    "/houses",
    "/planets",
    "/vedic/",
    "/numerology/",
    "/tarot/",
    "/hd/",
    "/human-design/",
    "/dasha/",
)

NON_DETERMINISTIC_PATH_PREFIXES: tuple[str, ...] = (
    "/transits",
    "/horoscope",
    "/interpret",
    "/ai/",
    "/mcp/",
    "/stream/",
    "/now",
    "/today",
)


def _strip_version_prefix(path: str) -> str:
    if path.startswith("/v") and len(path) >= 3 and path[2].isdigit():
        slash = path.find("/", 2)
        if slash == -1:
            return "/"
        return path[slash:]
    return path


def is_deterministic_path(path: str) -> bool:
    """Whether ``path`` is safe to cache by default.

    Denylist wins over allowlist — ``/horoscope/daily`` is never cached even if
    a user adds ``/horoscope`` to a custom allowlist.
    """
    normalised = _strip_version_prefix(path)
    for prefix in NON_DETERMINISTIC_PATH_PREFIXES:
        if normalised.startswith(prefix):
            return False
    for prefix in DETERMINISTIC_PATH_PREFIXES:
        if normalised.startswith(prefix):
            return True
    return False


def _canonicalise(value: Any) -> Any:
    """Recursively sort dict keys; preserve list order."""
    if isinstance(value, dict):
        return {k: _canonicalise(value[k]) for k in sorted(value.keys())}
    if isinstance(value, list):
        return [_canonicalise(item) for item in value]
    return value


def build_cache_key(method: str, path: str, body: Any) -> str:
    """Build a content-addressed cache key.

    Two semantically-equivalent calls produce the same key —
    ``{date, lat}`` and ``{lat, date}`` collide, by design.
    """
    canonical = _canonicalise({"m": method.upper(), "p": path, "b": body})
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return CACHE_KEY_PREFIX + digest


@dataclass
class CacheEntry:
    """In-store representation. ``expires_at`` is Unix seconds."""

    value: Any
    expires_at: float


@runtime_checkable
class CacheStore(Protocol):
    """Storage protocol. Sync-only — async backends should use a thread pool
    or just use this for the small per-request hot path."""

    def get(self, key: str) -> CacheEntry | None:
        ...

    def set(self, key: str, entry: CacheEntry) -> None:
        ...

    def delete(self, key: str) -> None:
        ...


class MemoryCache:
    """In-process dict-backed store. Thread-safe via a single lock."""

    def __init__(self) -> None:
        self._data: dict[str, CacheEntry] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> CacheEntry | None:
        with self._lock:
            return self._data.get(key)

    def set(self, key: str, entry: CacheEntry) -> None:
        with self._lock:
            self._data[key] = entry

    def delete(self, key: str) -> None:
        with self._lock:
            self._data.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)


class DiskCache:
    """File-backed store using ``shelve`` (stdlib, no extra deps).

    Suitable for dev loops and CLI tools. For production use, plug a Redis
    backend through the ``CacheStore`` protocol.
    """

    def __init__(self, path: str) -> None:
        self._path = path
        self._lock = threading.Lock()

    def get(self, key: str) -> CacheEntry | None:
        with self._lock, shelve.open(self._path) as db:
            try:
                raw = db.get(key)
            except Exception:
                return None
            if raw is None:
                return None
            if isinstance(raw, CacheEntry):
                return raw
            # Stored as dict pre-typing; reconstruct.
            try:
                return CacheEntry(value=raw["value"], expires_at=float(raw["expires_at"]))
            except (KeyError, TypeError, ValueError):
                return None

    def set(self, key: str, entry: CacheEntry) -> None:
        with self._lock, shelve.open(self._path) as db:
            db[key] = entry

    def delete(self, key: str) -> None:
        with self._lock, shelve.open(self._path) as db:
            try:
                del db[key]
            except KeyError:
                pass


CacheOption = Union[bool, str, "ResolvedCache", CacheStore, "ResolvedCache", None]


@dataclass
class ResolvedCache:
    store: CacheStore
    default_ttl_seconds: int = field(default=DEFAULT_CACHE_TTL_SECONDS)


def resolve_cache_option(option: Any) -> ResolvedCache | None:
    """Turn the user-facing ``cache`` option into ``(store, default_ttl)``.

    Accepts ``None`` / ``False`` (disabled), ``"memory"``, a ``CacheStore``,
    or a ``ResolvedCache``.
    """
    if option is None or option is False:
        return None
    if option == "memory":
        return ResolvedCache(store=MemoryCache())
    if isinstance(option, ResolvedCache):
        return option
    if isinstance(option, CacheStore):
        return ResolvedCache(store=option)
    raise TypeError(
        f"astroway: cache option must be None, False, 'memory', a CacheStore, "
        f"or a ResolvedCache; got {type(option).__name__}",
    )


def is_expired(entry: CacheEntry) -> bool:
    return entry.expires_at <= time.time()
