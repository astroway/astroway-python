# Changelog

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
