# astroway

> Official Python SDK for the [AstroWay API](https://api.astroway.info): natal charts, synastry, transits, Vedic dashas, Tarot, Numerology, Human Design, AI horoscopes. Sync + async, type-hinted, retry-aware.

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

Get an API key at <https://api.astroway.info/dashboard/sign-up>: **10 000 credits/month free**, no card required. Each endpoint costs 5–500 credits depending on what it computes ([pricing](https://api.astroway.info/pricing/)).

Requires Python 3.9+.

---

## Quick start

### Synchronous

```python
from astroway import Astroway, BirthData

aw = Astroway(api_key="aw_live_...")

chart = aw.chart.compute(BirthData(
    date="1990-07-14",
    time="14:30:00",
    timezone_offset=3,
    latitude=50.45,
    longitude=30.52,
    house_system="P",
))

SIGNS = ["Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
         "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"]

asc = chart["houses"]["ascendant"]                            # 212.0929
print(f"ASC: {SIGNS[int(asc // 30)]} {asc % 30:.2f}°")        # ASC: Scorpio 2.09°
print(f"Sun: {chart['planets'][0]['longitude']:.2f}°")        # Sun: 111.77°
```

`/chart` returns positions, not labels: `houses["ascendant"]` and every `planets[i]["longitude"]` are ecliptic longitudes in degrees, so the sign is `longitude // 30` into the list above and the degree within it is `longitude % 30`.

### Asynchronous

```python
import asyncio
from astroway import AsyncAstroway

async def main() -> None:
    async with AsyncAstroway(api_key="aw_live_...") as aw:
        chart = await aw.chart.compute({
            "date": "1990-07-14",
            "time": "14:30:00",
            "timezoneOffset": 3,
            "latitude": 50.45,
            "longitude": 30.52,
        })
        print(chart["houses"]["ascendant"])

asyncio.run(main())
```

The SDK exposes **103 typed namespaces / 623 methods** auto-generated from the OpenAPI spec: `aw.synastry.aspect_grid({...})`, `aw.bazi.day_master({...})`, `aw.vedic.dashas_vimshottari_maha({...})`, etc. The `{ ok, data, error }` envelope is unwrapped for you.

Top-4 categories (chart, synastry, transits, vedic dashas) ship **Pydantic v2 request models** for IDE autocomplete + validation: `BirthData`, `SynastryRequest`, `TransitsRequest`, `VedicDashaRequest`. Pass either a model or a `dict`, both work everywhere.

Sync and async clients share an identical surface: both expose the same namespaces, plus low-level `aw.request(method, path, body=…)` / `aw.post(path, body=…)` escape hatches.

---

## Common workflows

### Synastry

```python
from astroway import BirthData, SynastryRequest

result = aw.synastry.compute(SynastryRequest(
    chart1=BirthData(date="1990-07-14", time="14:30:00", timezone_offset=3, latitude=50.45, longitude=30.52),
    chart2=BirthData(date="1992-03-22", time="09:15:00", timezone_offset=2, latitude=48.85, longitude=2.35),
))
print(f"Score: {result['compatibility']['score']}/100 ({result['compatibility']['label']})")
```

### Transits to natal

```python
from astroway import TransitsRequest

transits = aw.transits.compute(TransitsRequest(
    date="1990-07-14", time="14:30:00", timezone_offset=3, latitude=50.45, longitude=30.52,
    target_date="2027-01-01",
))
```

### Vedic Vimshottari Mahadasha

```python
from astroway import VedicDashaRequest

dasha = aw.vedic.dashas_vimshottari_maha(VedicDashaRequest(
    date="1985-07-22", time="06:45:00", timezone_offset=5.5,
    latitude=19.07, longitude=72.87,
))
```

### Tarot daily card

```python
card = aw.tarot.rider_waite_daily({"seed": 42})
```

### Human Design

```python
hd = aw.human_design.compute({
    "date": "1990-07-14", "time": "14:30:00", "timezoneOffset": 3, "latitude": 50.45, "longitude": 30.52,
})
print(f"{hd['type']} - {hd['strategy']} - {hd['authority']}")
```

### White-label PDF report

`/reports/*` endpoints accept an inline `whitelabel` object (the `BrandingObject`
schema) to brand the generated PDF with your own logo, colours, and footer:

```python
report = aw.reports.natal({
    "chart": {
        "date": "1990-07-14", "time": "14:30:00",
        "timezoneOffset": 3, "latitude": 50.45, "longitude": 30.52,
    },
    "whitelabel": {
        "companyName": "Acme Astrology",
        "reportName": "Your Natal Blueprint",
        "themeColor": "#5b21b6",
        "footerText": "© Acme Astrology",
    },
})
print(report["url"])  # signed PDF URL
```

Pass `"whitelabel": True` instead of an object to pull branding from your
account's stored config (requires a wpUserId-bound key).

### Streaming

Two endpoints answer Server-Sent Events rather than JSON, and their namespace
methods return a stream:

```python
for chunk in aw.mcp.streaming({"message": "What is a stellium?"}):
    if chunk.type == "text_delta":
        print(chunk.text, end="", flush=True)
    elif chunk.type == "done":
        break
```

The async client returns the async variant, walked with `async for`. Any other
SSE-capable path goes through `aw.stream_sse(path, body=...)`, which yields the
same chunks.

---

## Error handling

The SDK raises typed subclasses of `ApiError`. Catch order matters, most specific first:

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
  - `RateLimitError` (429), carries `retry_after_seconds`
  - `InternalServerError` (5xx)

### The 400 you are most likely to hit first

Chart bodies take `latitude`, `longitude` and `timezone_offset` (`timezoneOffset` over the wire). The short spellings `lat`, `lon`, `lng`, `long`, `tz` and `timezone` are refused with a `BadRequestError` whose `e.code` is `INVALID_FIELD`, and `e.body["error"]["details"]` names every offending field at once as `{"path", "expected", "message"}`. They are not accepted and not deprecated: they were never in the spec, and before the API started refusing them they were silently ignored, which charted 0°N 0°E at UTC under a `200`. Details: <https://api.astroway.info/en/errors/#invalid_field>.

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

Two equivalent auth schemes, pick whichever your stack prefers:

- **Header (default):** `X-Api-Key: aw_live_...`, the same convention as `curl`/Postman examples.
- **Bearer:** `Authorization: Bearer aw_live_...`, the same convention as Stripe/OpenAI/Anthropic SDKs.

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

Since **`1.0.0` (2026-05-11)** this package follows strict SemVer:

- **Public names in `astroway.__all__` stable inside `1.x`.** Removing or narrowing requires a `2.0.0` major bump with deprecation period.
- **Method signatures stable inside `1.x`.** Adding a new keyword-only parameter (with default) is non-breaking; reordering or renaming is breaking.
- **Body shape stable inside `1.minor`.** Tightening (constraints, enum) ships in patches; new required keys require a minor bump.
- **API version vs SDK version are independent.** SDK `1.x` follows its own semver; the API itself sits at `/v1/`.
- **Python 3.10+ required** since `1.0.0`. Need 3.9? Stay on `0.x` (will receive critical security patches).

### Migration from `0.1.0a1` … `0.1.0rc1` to `0.1.0`

`0.1.0` freezes the public surface. **No breaking changes** vs `0.1.0rc1`: every export, namespace, error class, and option added across alphas / betas / RCs ships unchanged. The freeze means future `0.1.x` patches will not narrow types or remove names; that level of change requires a `0.2.0` minor bump.

| Coming from | Action |
|---|---|
| `0.1.0a1` (manual `aw.post('/chart', body=...)`) | Switch to typed namespaces: `aw.chart.compute(body)`, `aw.synastry.aspect_grid(body)`, etc. The escape hatch (`aw.request(...)`) still works. |
| `0.1.0a2` … `a3` (no idempotency / errors) | Pick up automatic `Idempotency-Key` on POSTs, `error.request_id` / `error.credits_remaining` getters, Pydantic models for top categories. |
| `0.1.0a4` … `a6` (no helpers) | `from astroway.helpers import BirthDateTime` for `from_city()` / `from_coordinates()`. |
| `0.1.0b1` … `b3` (no streaming / cache / mock) | `for chunk in aw.charts.compute(...).stream()`, `Astroway(cache=MemoryCache())`, `from astroway.testing import MockAstroway`. |
| `0.1.0rc1` (no bring-your-own httpx) | Optional: pass `http_client=httpx.Client(...)`, `limits=httpx.Limits(...)`, or `transport='aiohttp'` (with `pip install astroway[aiohttp]`). |

A type-stability test suite (`tests/test_types.py`) inspects constructor signatures, error subclass tree, dataclass fields, and Literal unions: any future PR that breaks the public surface fails CI before reaching PyPI.

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

MIT, see [LICENSE](LICENSE).
