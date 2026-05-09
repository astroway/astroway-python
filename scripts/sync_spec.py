"""Fetches the production OpenAPI 3.1 spec to ./openapi.json so the
generator runs deterministically. Override the upstream URL via
ASTROWAY_OPENAPI_URL when developing against a local api-calc.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request

UPSTREAM = os.environ.get("ASTROWAY_OPENAPI_URL", "https://api.astroway.info/v1/openapi.json")


def main() -> int:
    req = urllib.request.Request(UPSTREAM, headers={"User-Agent": "astroway-sdk-build/0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        if resp.status != 200:
            print(f"sync-spec: {UPSTREAM} -> {resp.status}", file=sys.stderr)
            return 1
        spec = json.loads(resp.read().decode("utf-8"))

    paths = len(spec.get("paths") or {})
    with open("openapi.json", "w", encoding="utf-8") as f:
        json.dump(spec, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(
        f"sync-spec: openapi={spec.get('openapi', '?')} api={spec.get('info', {}).get('version', '?')} paths={paths}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
