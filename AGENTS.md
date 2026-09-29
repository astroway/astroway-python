# AGENTS.md for `astroway` (Python)

Instructions for AI coding agents writing Python against the AstroWay API
through this package. Written to be executed, not summarised.

This file ships **inside the wheel and the sdist**, so after `pip install
astroway` it is already on disk beside the package. Point your agent at it, or
add the path to `CLAUDE.md` / `.cursor/rules/`.

Full language-agnostic playbook, always current:
<https://api.astroway.info/AGENTS.md>
Endpoint catalogue: <https://api.astroway.info/llms.txt>
OpenAPI 3.1: <https://api.astroway.info/v1/openapi.json>

## Rule 0: the API does not geocode

There is no endpoint that turns a city name into coordinates. Resolve the place
on your side and pass numbers. Every chart call needs `latitude`, `longitude`
and either a timezone offset or a `timezone` zone name, and getting the offset
wrong moves the houses, not just the clock.

## Install and construct

```bash
pip install astroway
```

```python
import os
from astroway import Astroway

aw = Astroway(api_key=os.environ["ASTROWAY_API_KEY"])
```

Async has the same surface and must be used as a context manager:

```python
from astroway import AsyncAstroway

async with AsyncAstroway(api_key=os.environ["ASTROWAY_API_KEY"]) as aw:
    chart = await aw.chart.compute({...})
```

Requires Python 3.9+. Never inline the key.

## Try it with no key at all before writing auth code

Nine endpoints answer without an account:

```bash
curl https://api.astroway.info/v1/public/moon-phase
curl -X POST https://api.astroway.info/v1/public/chart \
  -H 'Content-Type: application/json' \
  -d '{"date":"1990-07-14","time":"14:30:00","latitude":50.45,"longitude":30.52,"timezoneOffset":3}'
```

Public responses carry a `_footer` attribution string: strip it when parsing,
keep it when displaying.

## Calling an endpoint

The SDK generates a namespace per tag from the OpenAPI spec, roughly 103
namespaces and 623 methods. Method names are **snake_case**:

```python
chart      = aw.chart.compute({...})
grid       = aw.synastry.aspect_grid({...})
day_master = aw.bazi.day_master({...})
maha       = aw.vedic.dashas_vimshottari_maha({...})
```

**Do not guess a method name.** If unsure, use the escape hatch with any path
from the spec rather than inventing a namespace.

## The one thing unique to Python: two spellings, and they are not interchangeable

Request **models** accept Python naming, because they declare an alias and
`populate_by_name`:

```python
from astroway import BirthData

BirthData(date="1990-07-14", time="14:30:00",
          timezone_offset=3, latitude=50.45, longitude=30.52)   # works
BirthData(date="1990-07-14", time="14:30:00",
          timezoneOffset=3, latitude=50.45, longitude=30.52)    # also works
```

A raw **dict** goes to the API untouched, so it must use the API's spelling:

```python
aw.chart.compute({"date": "1990-07-14", "time": "14:30:00",
                  "timezoneOffset": 3, "latitude": 50.45, "longitude": 30.52})   # correct
aw.chart.compute({..., "timezone_offset": 3})                                    # 400, field not recognised
```

Models exist for the four busiest categories: `BirthData`, `SynastryRequest`,
`TransitsRequest`, `VedicDashaRequest`. Everywhere else, pass a dict with
camelCase keys.

## The four other things agents get wrong

1. **`time` is `HH:mm:ss`.** `"14:30"` returns `400 INVALID_INPUT`. Pad it.
2. **The offset is a number of hours from UTC**, `5.75` for Kathmandu, `-4` for
   New York in summer. It is the offset **at the birth moment**, so historical
   DST matters: Kyiv on 1990-05-15 was `+4`, not `+3`.
   **When you do not know that offset, send `timezone` instead** and the server
   works it out: `timezone="Europe/Kyiv"`, or `"auto"` to take it from the
   coordinates. It wins when both are sent. It is a zone name, never an offset:
   `"+03:00"` and `"EST"` are both `400`, and so is `""`, so leave the field out
   rather than sending an empty one.
3. **`/chart` returns positions, not labels.** `chart["houses"]["ascendant"]`
   and every `chart["planets"][i]["longitude"]` are ecliptic longitudes in
   degrees. The sign is `int(longitude // 30)` into the twelve and the degree
   within it is `longitude % 30`. There is no `sign` key on a planet; if you
   print one, you computed it.
4. **Do not retry by hand.** Retry on 408/409/429/5xx with exponential backoff
   is built in and honours `Retry-After`. Your own loop multiplies the spend.

## Sandbox and live

The key selects the environment, not the URL:

- `aw_live_…` spends credits.
- `aw_test_…` calls the same paths and spends nothing.

Switch the key, never the URL. Sandbox covers calculation. AI interpretation,
generated reports and rendering return `402 SANDBOX_ENDPOINT_UNAVAILABLE` on a
test key, because those cost real money per call.

## Errors

```python
from astroway.errors import BadRequestError, RateLimitError, AuthenticationError

try:
    aw.chart.compute(body)
except BadRequestError as e:
    ...   # the message names the field. Fix the body; do not retry.
except RateLimitError:
    ...   # already retried internally; back off or raise the plan
except AuthenticationError:
    ...   # key missing, revoked, or a sandbox key on a live-only endpoint
```

## Cost, before you loop

Endpoints cost 5 to 500 credits depending on what they compute. Free tier is
10 000 credits a month, no card. Before generating a loop, read the per-endpoint
cost from `GET /v1/public/endpoint-costs`, which needs no key, or
<https://api.astroway.info/pricing/>.

## What NOT to do

- Do not put a live key in anything served to a browser. There is no
  publishable key class yet; proxy through your own server.
- Do not invent endpoint paths. If it is not in `openapi.json`, it does not
  exist.
- Do not stitch a chart from several calls. Ask whether one endpoint already
  returns the whole thing; most do.
- Do not translate output yourself. Pass `lang` where supported; the API answers
  in 21 languages.
- Do not assume a sign order other than Aries first. Longitude zero is 0° Aries.
