# Changelog

## 1.0.0 — 2026-05-11

**Production guarantee.** Public API stable, SemVer commitment. Same code as `0.2.0` — every export, namespace, error class, integration ships unchanged. The major bump signals contractual commitment, not surface change.

### Changed

- **Python 3.10 minimum.** Dropped Python 3.9 — its EOL is 2025-10-31 and most reasonable production deployments are on 3.11+ by now. The `Programming Language :: Python :: 3.9` classifier is removed; `requires-python` is now `>=3.10`.
  - If you still need 3.9: pin to `astroway<1.0`. The `0.x` line will receive critical security patches.
- **SemVer commitment in README** — removing or narrowing any name in `astroway.__all__` requires a `2.0.0` major bump.

### Locked (same as 0.2.0, now contractual)

Sync `Astroway` + async `AsyncAstroway` with identical surface. 103 typed namespaces / 623 methods. 12-class error hierarchy. Pydantic request models. `BirthDateTime` helpers. Auto-pagination. SSE streaming (sync + async). Deterministic cache. `MockAstroway` testing. `http_client=` / `limits=` / `transport='aiohttp'` opt-ins. `astroway.integrations.django` + `.fastapi` extras.

### Migration from 0.x

`pip install --upgrade astroway` is a drop-in upgrade **if you're on Python 3.10+**. No code changes needed.

### Verification

161 pytest tests pass (same suite as 0.2.0).

## 0.2.0 — 2026-05-11

Framework integrations — `astroway[django]` and `astroway[fastapi]` extras. **No new package on PyPI** — same `astroway` distribution; the new modules sit under `astroway.integrations.*` and only import their framework when you opt in via the extra.

### Added

- **`astroway[django]`** extra → `astroway.integrations.django`:
  ```python
  # settings.py
  ASTROWAY_API_KEY = os.environ['ASTROWAY_API_KEY']
  ASTROWAY_BASE_URL = 'https://api.astroway.info/v1'  # optional
  ASTROWAY_TIMEOUT = 30.0                              # optional

  # views.py
  from astroway.integrations.django import get_astroway, get_async_astroway
  chart = get_astroway().chart.compute({...})
  ```
  - `get_astroway()` / `get_async_astroway()` — process-cached factories (one client per Django process, `lru_cache(maxsize=1)`).
  - `AstrowayConfig` Django app config — optional `INSTALLED_APPS` entry for users who want explicit init order.
  - Missing `ASTROWAY_API_KEY` raises `django.core.exceptions.ImproperlyConfigured` — matches Django's standard misconfig signal.

- **`astroway[fastapi]`** extra → `astroway.integrations.fastapi`:
  ```python
  from contextlib import asynccontextmanager
  from fastapi import Depends, FastAPI
  from astroway.integrations.fastapi import astroway_lifespan, get_astroway

  @asynccontextmanager
  async def lifespan(app):
      async with astroway_lifespan(api_key=...) as aw:
          app.state.astroway = aw
          yield

  app = FastAPI(lifespan=lifespan)

  @app.post('/chart')
  async def chart(body: dict, aw=Depends(get_astroway)):
      return await aw.chart.compute(body)
  ```
  - `astroway_lifespan(api_key=, **kwargs)` — async context manager; opens AsyncAstroway, closes on shutdown. Forwards `http_client=` / `transport='aiohttp'` / `limits=` / etc.
  - `get_astroway(request)` — `Depends()` source. Pulls the lifespan-managed client off `request.app.state.astroway`. Raises a clear `RuntimeError` pointing at the lifespan if you forgot to register it.

### Changed

- `pyproject.toml` `[project.optional-dependencies]` adds `django = ["django>=4.2"]` and `fastapi = ["fastapi>=0.110", "starlette>=0.36"]`.
- `astroway.integrations.__init__` documents the extras pattern.

### Migration from 0.1.0

No breaking changes. Existing code is unaffected. Adopt the integrations only if useful:

```bash
pip install --upgrade 'astroway[django]'   # Django apps
pip install --upgrade 'astroway[fastapi]'  # FastAPI apps
```

### Verification

161 pytest tests pass (155 from 0.1.0 baseline + 6 new in `tests/test_integrations.py` covering both extras).

### Reference

- Django app config — [django.apps.AppConfig](https://docs.djangoproject.com/en/5.0/ref/applications/).
- FastAPI lifespan — [Lifespan events](https://fastapi.tiangolo.com/advanced/events/).
- The `lru_cache(maxsize=1)` pattern mirrors Django's own `django.core.cache.cache` global.

## 0.1.0 — 2026-05-11

**Stable surface commitment.** Public API frozen — every export shipped across alphas / betas / RC is now part of the `0.1.x` contract. No code changes vs `0.1.0rc1` — same `Astroway` / `AsyncAstroway` constructors, same 103 namespaces / 623 methods, same error hierarchy, same helpers / cache / streaming / mock / `http_client` / `limits` / `transport='aiohttp'` surface. Ready to be depended on.

### Locked

- **Public exports** — every name in `astroway.__all__` is part of the surface contract. Removing or narrowing requires `1.0.0`.
- **Constructor signatures** — `Astroway.__init__` and `AsyncAstroway.__init__` keep all keyword-only parameters from `0.1.0rc1`: `api_key`, `base_url`, `auth_scheme`, `timeout`, `retry`, `default_headers`, `transport`, `limits`, `http_client`, `idempotency`, `cache`. `api_key` stays the only required arg.
- **Error subclass tree** — 12-class hierarchy (`ApiError` + 11 subclasses) is the locked support contract. Users write `except RateLimitError:` / `except QuotaExceededError:` — collapsing branches breaks them silently.
- **`RawResponse` dataclass fields** — `data` / `request_id` / `credits_remaining` / `headers` / `status_code` won't be renamed.
- **`RetryConfig` fields** — `max_retries`, `base_delay_ms`, `max_delay_ms`, `retryable_statuses` locked.
- **Type-stability suite** — `tests/test_types.py` uses `inspect.signature` + `get_type_hints` + `issubclass` to enforce the above. PRs that break the surface fail CI before reaching PyPI.
- **`py.typed` marker** ships in the wheel — downstream `mypy` / `pyright` users see the SDK's types.

### Migration

`pip install --upgrade astroway` is a drop-in upgrade from any `0.1.0rcN`. README has a migration table covering each pre-release stage.

### Verification

155 pytest tests pass (140 from rc1 baseline + 15 new in `tests/test_types.py`). `ruff check` clean.

## 0.1.0rc1 — 2026-05-10

First **release candidate**. httpx customization + aiohttp transport opt-in. Heavy users who already maintain an `httpx.Client` (proxies, custom CA bundles, mTLS, telemetry middleware) want to drop it in instead of re-configuring through SDK options. High-concurrency workloads (1000+ in-flight) often outgrow httpx's connection model and benefit from the aiohttp backend, which OpenAI's Python SDK ships for the same reason.

### Added

- **`Astroway(http_client=httpx.Client(...))`** and **`AsyncAstroway(http_client=httpx.AsyncClient(...))`** — bring-your-own client. The SDK injects identification + auth headers (`User-Agent`, `X-Astroway-Channel`, `X-Api-Key`/`Authorization`, `Content-Type`) so analytics stay accurate, but everything else (transport, base_url, timeout, retries, proxy chain, event hooks) belongs to your client. `close()` / `aclose()` no-op for user-supplied clients — their lifecycle is yours.
- **`limits=httpx.Limits(...)`** on both classes — propagated to the default-built transport when `http_client` and `transport` aren't set. Useful for raising the keepalive count for batched workloads:
  ```python
  aw = Astroway(api_key=..., limits=httpx.Limits(max_keepalive_connections=50))
  ```
- **`AsyncAstroway(transport='aiohttp')`** — opt-in to the [`httpx-aiohttp`](https://pypi.org/project/httpx-aiohttp/) backend for async workloads with high concurrency. Install via the new extra:
  ```bash
  pip install 'astroway[aiohttp]'
  ```
  Without the extra you get a clear `ImportError` pointing to the install command. Sync `Astroway` rejects `transport='aiohttp'` with a helpful error.
- **`TransportBackend`** literal type exported from the package root for typed wrappers.

### Changed

- `transport=` parameter type widened on both classes from `httpx.[Async]BaseTransport | None` to `httpx.[Async]BaseTransport | str | None` (str only meaningful as `'aiohttp'` on async).
- `_owns_http` flag on the client tracks whether the SDK constructed the underlying client — used by `close()` / `aclose()` to avoid closing user-supplied clients.

### Migration from b3

No breaking changes. All new parameters default to `None`, which preserves the existing transport-only behaviour.

### Verification

140 pytest tests pass (132 baseline + 8 new in `tests/test_http_client.py`). `ruff check` clean.

### Reference

- OpenAI Python — [`http_client=` parameter](https://github.com/openai/openai-python#configuring-the-http-client) on `OpenAI()` / `AsyncOpenAI()`.
- OpenAI Python — [aiohttp transport](https://github.com/openai/openai-python/blob/main/CHANGELOG.md) since v1.74.
- httpx — [`Limits`](https://www.python-httpx.org/advanced/resource-limits/) for connection pooling.
- httpx-aiohttp — [`AiohttpTransport`](https://pypi.org/project/httpx-aiohttp/) — drop-in async transport using aiohttp for HTTP/1.1.

## 0.1.0b3 — 2026-05-10

Deterministic response cache. Mirror of `@astroway/sdk` v0.1.0-beta.3 (TS) and `astroway/sdk` v0.1.0-beta.2 (PHP). Charts are pure functions of `(date, time, lat, lon, tz)` — caching them client-side saves credits and makes dev loops instant.

### Added

- **`cache` constructor option** on both `Astroway` and `AsyncAstroway`:
  ```python
  Astroway(api_key="...", cache="memory")            # in-process dict
  Astroway(api_key="...", cache=DiskCache("/tmp/x")) # file-backed via stdlib shelve
  Astroway(api_key="...", cache=my_redis_store)      # BYO CacheStore protocol
  ```
- **`MemoryCache`** — thread-safe dict-backed; `get`/`set`/`delete`/`clear`/`__len__`.
- **`DiskCache(path)`** — file-backed via stdlib `shelve` (no extra deps). Suitable for dev loops and CLI tools.
- **`CacheStore` Protocol** — BYO Redis/IndexedDB/SQLite via `runtime_checkable` Protocol with `get`/`set`/`delete`.
- **`build_cache_key(method, path, body)` + `is_deterministic_path(path)` + `CacheEntry`** exposed for users who want to build their own caching layer.
- **Per-call `cache=True` / `cache=False`** override on `request()`:
  ```python
  aw.request("POST", "/transits", body={...}, cache=True)   # force-cache
  aw.request("POST", "/chart", body={...}, cache=False)     # force-skip
  ```
- **Default policy** matches TS / PHP — `/chart`, `/synastry`, `/composite`, `/midpoints`, `/aspects`, `/houses`, `/planets`, `/vedic/*`, `/numerology/*`, `/tarot/*`, `/hd/*`, `/human-design/*`, `/dasha/*` cached. `/transits`, `/horoscope`, `/interpret`, `/ai/*`, `/mcp/*`, `/stream/*`, `/now`, `/today` skipped. Unknown endpoints skipped.

### Cache key

`astroway_v1_<sha256(canonical-json(method, path, body))>` — order-insensitive on dict keys, order-preserving on lists. Bumping the `v1` prefix in a future release auto-invalidates stale entries; multi-SDK Redis backends never collide.

### Robustness

- 4xx/5xx never poison the cache — store happens **after** error classification.
- Expired entries (`expires_at <= time.time()`) refetched fresh.
- Cache hits return a `RawResponse` with `x-astroway-cache: hit` header for distinguishability.
- `cache=42` raises `TypeError` early — no silent fallback to no-cache.

### Migration from b2

No breaking changes. Existing code keeps working. Adding `cache="memory"` to your constructor is the only thing needed.

### Verification

- 132 pytest tests pass (20 new in `tests/test_cache.py`).
- `ruff check src tests` clean.
- Coverage: cache-key (order-insensitive on dict keys, list-order preserved, method/path differentiation, namespace prefix), `is_deterministic_path` (allowlist + denylist + unknown denied), `MemoryCache` round-trip + clear + size, `DiskCache` round-trip across instances, end-to-end sync (deterministic → 1 HTTP call across 2 invocations, order-insensitive end-to-end, non-deterministic skipped, force-cache `cache=True`, force-skip `cache=False`, no-cache config behaves like b2, expired refetched, invalid cache option raises), end-to-end async (deterministic → 1 HTTP call).

## 0.1.0b2 — 2026-05-10

Streaming for AI endpoints. Mirror of `@astroway/sdk` v0.1.0-beta.2 (TS). `for`/`async for` over normalised SSE chunks against `/horoscope/daily`, `/interpret/*`, `/mcp/streaming`, and any other endpoint that emits `text/event-stream`.

### Added

- **`Astroway.stream_sse(path, *, body, params, method, idempotency_key)`** — sync iterator. Returns a `SyncSSEStream` you can walk with a regular `for` loop:
  ```python
  for chunk in aw.stream_sse("/horoscope/daily", body={"date": "2026-05-10"}):
      if chunk.type == "text_delta":
          print(chunk.text, end="", flush=True)
      elif chunk.type == "done":
          break
  ```
- **`AsyncAstroway.stream_sse(...)`** — async sibling, `async for chunk in aw.stream_sse(...)`.
- **`StreamChunk`** discriminated union (`Union[TextDelta, StreamDone, StreamError, StreamEvent]`) — pattern-match on `chunk.type` for full narrowing. Each variant is a frozen `@dataclass`.
- **`SSEEvent`** raw event dataclass — `event`, `data` (auto-decoded JSON when possible), `raw_data`, optional `id` / `retry`. Lower-level `parse_sse_sync(response)` / `parse_sse_async(response)` helpers exposed via `astroway._streaming`.
- **HTTP errors before the stream classified normally** — 401 → `AuthenticationError`, 429 → `RateLimitError`, etc.
- **Idempotency-Key auto-attaches on POST streams** — a network blip + reconnect with the same key replays the same generation when the backend supports it; fails open otherwise. Override per-call via `idempotency_key=...`.

### Wire format

Standard [HTML5 SSE spec](https://html.spec.whatwg.org/multipage/server-sent-events.html). Multi-line `data:` is concatenated with `\n`. JSON-shaped data is auto-decoded. Comments (`:`-prefixed lines) and unknown fields silently skipped. CRLF line endings supported.

Known event names normalised to chunk types:
- `text_delta` → `TextDelta(text=...)`
- `done` / `end` / `message_stop` → `StreamDone()`
- `error` → `StreamError(message=..., code=...)`
- everything else → `StreamEvent(event=..., data=...)` passthrough

### Migration from b1

No breaking changes. Existing code keeps working. `stream_sse` and stream chunk classes are additive.

### Verification

- 112 pytest tests pass (14 new in `tests/test_streaming.py`).
- `ruff check src tests` clean.
- Coverage: chunk normalisation (text_delta string + object, done aliases, error code, unknown event passthrough), end-to-end sync (Accept header, X-Api-Key, auto-idempotency, per-call override, HTTP error → AuthenticationError, multiline data, comments), end-to-end async (chunks + HTTP error classification).

## 0.1.0b1 — 2026-05-10

First **beta**. Cursor-based auto-pagination iterators in the Stainless / OpenAI / Anthropic style. Endpoints not yet paginated keep working — they yield a single page with the whole payload.

### Added

- **`aw.paginate(method, path, *, body=None, params=None)`** on both `Astroway` and `AsyncAstroway`. Returns a paginator you can:
  - Iterate to walk every item across all pages: `for transit in aw.paginate("GET", "/transits/calendar", params={"start": "2026-01"}): ...`
  - Iterate page-by-page via `.pages()`: `for page in paginator.pages(): print(len(page), page.next_cursor)`
  - Short-circuit to first page only via `.first_page()`
- **`SyncPage` / `AsyncPage`** generic page objects exposing `items`, `next_cursor`, `has_next`, and the raw payload via `.raw`. Both `__iter__` walks items.
- **`SyncPaginator` / `AsyncPaginator`** generic iterator classes — exposed at the package root for type hints (`def list_transits() -> SyncPaginator[Transit]: ...`).
- API contract: list endpoints return `{ items: [...], next_cursor: "..." }` (`null` or missing means last page). Both `next_cursor` and `nextCursor` keys are accepted, so server-side casing churn doesn't break the SDK.

### Backend coordination

The contract is forward-compatible with the current api-calc surface: 95% of endpoints aren't paginated yet, and the iterator yields once with the whole response. As list endpoints add `items` + `next_cursor` (per `docs/PRODUCT-PLAN.md`), existing SDK code starts walking pages automatically.

### Verification

- 98 pytest tests pass (9 new in `tests/test_pagination.py`).
- `ruff check src tests` clean.
- Sync + async tested with multi-page scripts: cursor propagation, `nextCursor` casing, single-payload fallback, `first_page` short-circuit.

## 0.1.0a6 — 2026-05-10

`BirthDateTime` builder for the (date, time, lat, lon, tz) tuple every chart-style endpoint takes. Mirror of `@astroway/sdk` v0.1.0-alpha.6.

### Added

- **`astroway.helpers.BirthDateTime`** — frozen dataclass with three factories:
  ```python
  from astroway import Astroway
  from astroway.helpers import BirthDateTime

  birth = BirthDateTime.from_coordinates(
      date="1990-07-14", time="14:30:00",
      latitude=50.45, longitude=30.52, timezone_offset=3,
  )
  chart = aw.chart.compute(birth.to_body())
  ```
- **Three factories:**
  - `BirthDateTime.from_coordinates(date=, time=, ...)` — explicit canonical wire shape with eager validation.
  - `BirthDateTime.from_datetime(datetime, latitude=, longitude=, timezone_offset=)` — accepts a stdlib `datetime`; tz-aware datetimes are converted to UTC.
  - `BirthDateTime.parse(iso, latitude=, longitude=, timezone_offset=)` — accepts ISO 8601 strings like `1990-07-14T14:30:00`. Trailing `Z` / `+HH:MM` is stripped.
- **`.to_body()`** — wire shape for namespace methods.
- **`.to_datetime()`** — tz-aware UTC `datetime` for further computation.
- **Frozen dataclass** — immutable, hashable, comparable.
- **Sub-package import** — `from astroway.helpers import BirthDateTime` keeps the helper out of the core import path.

### Geocoding deferred

The roadmap originally included `BirthDateTime.from_city("Kyiv, UA", ...)` here, but the upstream `/v1/geo/search` endpoint isn't shipped yet. `from_city()` will land alongside that endpoint in api-calc — no SDK release is blocked on it.

### Migration from a5

No breaking changes. `BirthDateTime` is an additive helper.

### Verification

- 89 pytest tests pass (13 new).
- Ruff lint clean.

## 0.1.0a5 — 2026-05-10

`with_response()` for support tickets, plus refined error types for quota exhaustion and calculation failures. Mirror of `@astroway/sdk` v0.1.0-alpha.5.

### Added

- **`RawResponse` dataclass** + `request_with_response()` / `post_with_response()` methods (sync + async). Returns `data` plus AstroWay metadata: `request_id`, `credits_remaining`, `headers`, `status_code`.
- **`QuotaExceededError`** — distinguishes "you ran out of credits" from "you got rate-limited" (the latter resolves with backoff; the former needs a top-up). Triggered by HTTP 402 or `code: OUT_OF_CREDITS` / `QUOTA_EXCEEDED` / `CREDIT_LIMIT_REACHED`.
- **`CalculationError`** — for server-side calculation failures (Swiss Ephemeris boundaries, missing datasets, unsupported house systems for high latitudes). Triggered by `code: CALCULATION_ERROR` / `EPHEMERIS_ERROR`.
- **`credits_remaining`** field uniform across all `ApiError` subclasses, surfaced from `X-Credits-Remaining` response header.
- **`retry_after_seconds`** moved from `RateLimitError` to base `ApiError` — useful on quota-exceeded responses too, not just 429.

### Migration from a4

No breaking source changes. Existing code that catches `RateLimitError` and reads `retry_after_seconds` keeps working — the field just lives on the base `ApiError` now (also reachable as `e.retry_after_seconds`).

```python
from astroway import Astroway, RateLimitError, QuotaExceededError, CalculationError

aw = Astroway(api_key="aw_live_...")

# Existing call returns data:
data = aw.synastry.compute({...})

# New: pull request_id + credits_remaining for a support ticket
raw = aw.post_with_response("/synastry", body={...})
print(raw.request_id, raw.credits_remaining)

# Refined error handling:
try:
    aw.post("/chart", body={...})
except RateLimitError as e:
    time.sleep(e.retry_after_seconds or 60)
except QuotaExceededError as e:
    top_up_alert(e.credits_remaining)  # often 0
except CalculationError as e:
    skip_date(e.body)  # likely a Swiss Ephemeris boundary
```

### Internal

- Refactored `request()` into a private `_send()` that always returns `RawResponse`; `request()` returns `result.data`, `request_with_response()` returns the full `RawResponse`. Same for async.
- `_raise_on_error()` reads `X-Credits-Remaining` and threads `credits_remaining` into every classified error.
- 76 pytest tests pass (9 new). Ruff lint clean.

## 0.1.0a4 — 2026-05-10

Auto-attached `Idempotency-Key` (UUIDv4) on every credit-costing POST. Mirror of TS alpha.4 — a network-blip retry never double-bills now.

### Added

- **`Idempotency-Key` header on POST by default.** UUIDv4 per request via `uuid.uuid4()`. GET/HEAD untouched. User-supplied keys win.
- **`idempotency` constructor option:** `'auto'` (default), `'off'`, or a callable returning a string (custom generator: deterministic test keys, ULIDs, ...).
- **`idempotency_key` per-call kwarg** on every namespace method:
  ```python
  await aw.synastry.aspect_grid({...}, idempotency_key="replay-abc")
  ```
- **`idempotency_key=` on `aw.request()` / `aw.post()`** for manual control.
- **`generate_idempotency_key()` exported** for users who want the same generator standalone.
- **`IdempotencyMode` type exported** for typed config.

### Backend coordination

The header fails open. Older backend versions and self-hosted deployments without idempotency support simply ignore it — no breakage. As `api-calc` rolls out idempotency caching, existing SDK users get retry-safe POSTs automatically.

### Internal

- New `src/astroway/_idempotency.py` module: `generate_idempotency_key`, `should_attach_idempotency`, `resolve_key_generator`.
- 67 pytest tests pass (10 new — UUID v4 shape + uniqueness, default-on POST, GET skip, user override, `'off'` policy, custom generator, namespace per-call kwarg, async parity).

### Migration from a3

No breaking changes. Auto-attachment is additive on POSTs; servers that don't recognise the header ignore it. To suppress globally: `Astroway(api_key=…, idempotency="off")`.

## 0.1.0a3 — 2026-05-10

Pydantic v2 request models for the top-4 endpoint categories. IDE autocomplete + validation at the call site for the most common workflows.

### Added

- **`astroway.models`** module exporting:
  - `BirthData` — base for natal-style endpoints (date, time, timezone_offset, latitude, longitude, house_system, name, city, zodiac_type, ayanamsa_id, cosmogram).
  - `SynastryRequest` — `chart1: BirthData`, `chart2: BirthData`, `orb_factor`.
  - `TransitsRequest` — birth + `target_date` / `target_time` / `target_*` overrides.
  - `VedicDashaRequest` — birth + `ayanamsa_id` + `start_date` / `end_date` window.
- **Dual input on every namespace method** — pass a Pydantic model or a `dict`; `request()` calls `.model_dump(by_alias=True, exclude_none=True)` automatically.
- **`populate_by_name=True`** — accept either Python field names (`timezone_offset=3`) or wire aliases (`timezoneOffset=3`).
- **Format validation** — `date` (`YYYY-MM-DD`) and `time` (`HH:MM:SS`) patterns enforced at construction time, so bad input fails fast before the network round-trip.
- **`extra="allow"`** — passing additional fields not yet modeled is permitted (forward-compatible with new server-side parameters).

### Unchanged

- All a2 surface preserved: 103 namespaces / 623 methods, sync + async parity, escape hatches (`aw.request`, `aw.post`).
- Remaining 90+ namespaces still accept `dict` bodies — coverage will expand in a4–a5 to other request shapes.

### Migration from a2

No breaking changes. Models are additive — existing `dict` calls keep working unchanged. Add `from astroway import BirthData` and pass it for type-checked call sites.

```python
# Both work identically:
aw.chart.compute({"date": "1990-07-14", "time": "14:30:00", "timezoneOffset": 3})
aw.chart.compute(BirthData(date="1990-07-14", time="14:30:00", timezone_offset=3))
```

## 0.1.0a2 — 2026-05-10

Typed resource namespaces for both sync and async clients. `aw.synastry.aspect_grid({...})` (or `await aw.synastry.aspect_grid({...})` on the async client) instead of `aw.post('/synastry/aspect-grid', body={...})` — same typing, friendlier surface, automatic envelope unwrap.

### Added

- **103 namespaces / 623 methods** auto-generated from `openapi.json` for both `Astroway` and `AsyncAstroway`. Naming rule mirrors the TypeScript SDK: operationId split on `_` (namespace separator), then `-` per segment (snake_case). Single-segment opIds get `compute`.
  - `aw.transits.compute({...})` — POST `/transits`
  - `aw.synastry.aspect_grid({...})` — POST `/synastry/aspect-grid`
  - `aw.bazi.day_master({...})` — POST `/bazi/day-master`
  - `aw.vedic.dashas_vimshottari_maha({...})` — POST `/vedic/dashas/vimshottari/maha`
  - `aw.tarot.rider_waite_daily({...})` — POST `/tarot/rider-waite/daily`
  - `aw.human_design.compute({...})` — POST `/human-design`
- **`scripts/generate_namespaces.py`** runs as part of the build pipeline.

### Unchanged

- `aw.request(method, path, body=…)`, `aw.post(path, body=…)`, etc. escape hatches still work — useful for path-template endpoints (`/webhooks/{id}/test`) and anything not yet covered by namespaces.
- All a1 surface preserved: error hierarchy, retry, identification headers, auth schemes, sync + async parity, context-manager support.

### Deferred to a3

Pydantic models per endpoint (originally scoped here) move to a3 — generating ~3000 schemas via `datamodel-code-generator` in a single release would create a huge diff and slow imports for users not opting in. a3 will ship Pydantic models for the top categories (chart / synastry / transits / vedic dashas) with the rest landing across a4–a5.

### Migration from a1

No breaking changes. Namespaces are additive attributes on the client instance. Replace `aw.post('/x/y', body=…)` with `aw.x.y(…)` at your own pace — both still work.

## 0.1.0a1 — 2026-05-09

Initial alpha release. Public API may shift before `0.1.0` proper based on integrator feedback.

### What's in the box

- **Synchronous (`Astroway`) and asynchronous (`AsyncAstroway`) clients** — identical surface, share constructor, methods, error types.
- **Built on `httpx`** — modern Python HTTP, supports HTTP/1.1 + HTTP/2, sync + async natively.
- **Two auth schemes:** `X-Api-Key` (default, matches curl/Postman) or `Authorization: Bearer` (matches Stripe/OpenAI/Anthropic convention) via `auth_scheme="bearer"`.
- **Stainless-template error hierarchy:** `ApiError` → `BadRequestError` / `AuthenticationError` / `PermissionDeniedError` / `NotFoundError` / `UnprocessableEntityError` / `RateLimitError` / `InternalServerError` / `APIConnectionError` (→ `APITimeoutError`).
- **Built-in retry** with exponential backoff + full jitter on 408 / 409 / 429 / 5xx and connection errors. Default 2 retries; configurable via `retry={"max_retries": 0}` to disable. Honors `Retry-After` (seconds or HTTP-date) on 429.
- **Per-request timeout** via `httpx.Timeout`, default 30s.
- **Identification headers** — `User-Agent: astroway-sdk-python/<version> (Python/<py-version>; <platform>)` and `X-Astroway-Channel: sdk-py`. **No telemetry, no phone-home.**
- **Auto-unwrap of `{ ok, data, error }` envelope** — methods return the `data` payload directly so user code reads naturally.
- **Context manager support** — both `with Astroway(...) as aw:` (sync) and `async with AsyncAstroway(...) as aw:` (async) close the underlying httpx client cleanly.
- **PEP 561 typed package** — `py.typed` marker shipped, full type hints throughout.

### Stack

- Python 3.9+ (CPython tested on 3.9 / 3.10 / 3.11 / 3.12 / 3.13).
- `httpx >= 0.27` — sync + async HTTP.
- `pydantic >= 2.0` — model validation surface (used by integrators for typed bodies).
- 40 unit tests — error classification, retry semantics, header propagation, auth scheme switching, async client parity.

### Internal

- Build with `hatchling`. Tests with `pytest` + `pytest-asyncio` + `respx`.
- Wheel + sdist published via PyPI Trusted Publishers (OIDC, no long-lived tokens).
- Provenance attestation on every release (Sigstore via GitHub Actions).
