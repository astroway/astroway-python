# astroway

> Official Python SDK for the [AstroWay API](https://api.astroway.info) — natal charts, synastry, transits, Vedic dashas, Tarot, Numerology, Human Design, AI horoscopes. Sync + async, type-hinted, retry-aware.

[![PyPI version](https://img.shields.io/pypi/v/astroway.svg?style=flat&color=blue)](https://pypi.org/project/astroway/)
[![Python versions](https://img.shields.io/pypi/pyversions/astroway.svg)](https://pypi.org/project/astroway/)
[![license: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

700+ endpoints. Synchronous and asynchronous clients with the same surface. Built-in retry on 408/409/429/5xx with exponential backoff. Stainless-style error hierarchy (`AuthenticationError` / `RateLimitError` / `BadRequestError` / …). Just `httpx` + `pydantic` under the hood.

---

## Install

```bash
pip install astroway
# or with uv
uv add astroway
# or with poetry
poetry add astroway
```

Get an API key at <https://api.astroway.info/dashboard/sign-up> — **10 000 credits/month free**, no card required. Each endpoint costs 5–500 credits depending on what it computes ([pricing](https://api.astroway.info/pricing/)).

Requires Python 3.9+.

---

## Quick start

### Synchronous

```python
from astroway import Astroway

aw = Astroway(api_key="aw_live_...")

chart = aw.post("/chart", body={
    "date": "1990-07-14",
    "time": "14:30:00",
    "timezoneOffset": 3,
    "latitude": 50.45,
    "longitude": 30.52,
    "houseSystem": "P",
})

asc = chart["angles"]["asc"]
print(f"ASC: {asc['sign']} {asc['degree']:.2f}°")
```

### Asynchronous

```python
import asyncio
from astroway import AsyncAstroway

async def main() -> None:
    async with AsyncAstroway(api_key="aw_live_...") as aw:
        chart = await aw.post("/chart", body={
            "date": "1990-07-14",
            "time": "14:30:00",
            "timezoneOffset": 3,
            "latitude": 50.45,
            "longitude": 30.52,
        })
        print(chart["angles"]["asc"])

asyncio.run(main())
```

The two clients share an identical surface — same constructor params, same methods (`get`, `post`, `put`, `delete`, low-level `request`), same error types.

---

## Common workflows

### Synastry

```python
result = aw.post("/synastry", body={
    "chart1": {"date": "1990-07-14", "time": "14:30:00", "timezoneOffset": 3, "latitude": 50.45, "longitude": 30.52},
    "chart2": {"date": "1992-03-22", "time": "09:15:00", "timezoneOffset": 2, "latitude": 48.85, "longitude": 2.35},
})
print(f"Score: {result['compatibility']['score']}/100 ({result['compatibility']['label']})")
```

### Transits to natal

```python
transits = aw.post("/transits", body={
    "date": "1990-07-14", "time": "14:30:00", "timezoneOffset": 3, "latitude": 50.45, "longitude": 30.52,
    "targetDate": "2027-01-01",
})
```

### Vedic Vimshottari Mahadasha

```python
dasha = aw.post("/vedic/dashas/vimshottari/maha", body={
    "date": "1985-07-22", "time": "06:45:00", "timezoneOffset": 5.5,
    "latitude": 19.07, "longitude": 72.87,
})
```

### Tarot reading

```python
spread = aw.post("/tarot/rider-waite/spread", body={"spreadType": "three-card", "seed": 42})
```

### Human Design

```python
hd = aw.post("/human-design", body={
    "date": "1990-07-14", "time": "14:30:00", "timezoneOffset": 3, "latitude": 50.45, "longitude": 30.52,
})
print(f"{hd['type']} — {hd['strategy']} — {hd['authority']}")
```

---

## Error handling

The SDK raises typed subclasses of `ApiError`. Catch order matters — most specific first:

```python
from astroway import (
    Astroway, ApiError,
    AuthenticationError, RateLimitError, BadRequestError,
)

try:
    aw.post("/chart", body=body)
except RateLimitError as e:
    time.sleep(e.retry_after_seconds or 60)
    # retry once...
except AuthenticationError:
    raise RuntimeError("Rotate your AstroWay API key")
except BadRequestError as e:
    print("Validation failed:", e.body)
except ApiError as e:
    print(f"API error {e.status} ({e.code}): {e!s} [request_id={e.request_id}]")
```

Full hierarchy:

- `ApiError` (base)
  - `APIConnectionError`
    - `APITimeoutError`
  - `BadRequestError` (400)
  - `AuthenticationError` (401)
  - `PermissionDeniedError` (403)
  - `NotFoundError` (404)
  - `UnprocessableEntityError` (422)
  - `RateLimitError` (429) — carries `retry_after_seconds`
  - `InternalServerError` (5xx)

---

## Configuration

```python
aw = Astroway(
    api_key="aw_live_...",                  # required
    base_url="https://api.astroway.info/v1", # override for staging / self-hosted
    auth_scheme="header",                    # "header" (X-Api-Key, default) or "bearer" (Authorization: Bearer)
    timeout=30.0,                            # per-request timeout in seconds
    retry={
        "max_retries": 2,                    # total attempts = 1 + max_retries
        "base_delay_ms": 250,
        "max_delay_ms": 30_000,
        "retryable_statuses": frozenset({408, 409, 429, 500, 502, 503, 504}),
    },
    default_headers={"X-Trace-Id": "..."},
)
```

The default retry honors `Retry-After` (seconds or HTTP-date) on 429 responses.

Set `retry={"max_retries": 0}` to disable retries entirely.

---

## Authentication

Two equivalent auth schemes — pick whichever your stack prefers:

- **Header (default):** `X-Api-Key: aw_live_...` — same convention as `curl`/Postman examples.
- **Bearer:** `Authorization: Bearer aw_live_...` — same convention as Stripe/OpenAI/Anthropic SDKs.

Set via `auth_scheme="bearer"` in the constructor.

---

## Privacy

The SDK does **not** phone home. There is no telemetry, no analytics, no usage reporting. The only network traffic the SDK originates is the AstroWay API calls you ask it to make.

Outgoing requests carry two identifying headers so the AstroWay backend can distinguish SDK traffic from raw HTTP traffic in its own logs:

- `User-Agent: astroway-sdk-python/<version> (Python/<py-version>; <platform>)`
- `X-Astroway-Channel: sdk-py`

Neither carries a session ID, machine fingerprint, or anything personal.

---

## Stability

- **Public API stable inside a major version.** Methods/classes shipped under `1.x` won't be renamed or removed without a deprecation note in `CHANGELOG.md` and a one-minor parallel-availability window.
- **Body shape stable inside a minor version.** Tightening (constraints, enum) ships in patches; new required keys require a minor bump.
- **API version vs SDK version are independent.** SDK `0.x` follows its own semver; the API itself sits at `/v1/`.

---

## Links

- 📦 PyPI: <https://pypi.org/project/astroway/>
- 📘 API docs: <https://api.astroway.info/docs/api/>
- 🔑 Sign up & dashboard: <https://api.astroway.info/dashboard/>
- 💰 Pricing: <https://api.astroway.info/pricing/>
- 🟦 TypeScript SDK: [`@astroway/sdk`](https://www.npmjs.com/package/@astroway/sdk)
- 🤖 MCP server: [`@astroway/mcp`](https://www.npmjs.com/package/@astroway/mcp)
- 🌐 Website: <https://astroway.info>

---

## License

MIT — see [LICENSE](LICENSE).
