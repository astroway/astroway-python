"""Reads openapi.json and emits src/astroway/_namespaces.py — typed resource
namespaces (sync + async) over the AstroWay client.

Naming rule (matches the TypeScript SDK):
  * `_` is the namespace separator (`vedic_dashas_vimshottari_maha`).
  * `-` is a word separator within a part (`aspect-grid`).
  * Single-segment opIds get the `compute` method.

Methods use Python snake_case (`aspect_grid`, not `aspectGrid`).

Only POST operations are namespaced. Path-template endpoints (`/webhooks/{id}/test`)
are skipped — use `aw.request("POST", path, body=...)` for those.
"""

from __future__ import annotations

import json
import keyword
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SPEC = ROOT / "openapi.json"
OUT = ROOT / "src" / "astroway" / "_namespaces.py"


def dash_to_snake(s: str) -> str:
    """`aspect-grid` → `aspect_grid`."""
    parts = re.split(r"[-]+", s)
    parts = [re.sub(r"[^a-zA-Z0-9]", "", p).lower() for p in parts]
    parts = [p for p in parts if p]
    return "_".join(parts)


def safe(name: str) -> str:
    if keyword.iskeyword(name) or name in {"None", "True", "False"}:
        return name + "_"
    return name


# Map common typographic Unicode to ASCII so ruff RUF001/RUF002 don't fire
# in the generated namespaces module. Built from chr() to avoid embedding
# the raw glyphs into this source file.
_AMBIGUOUS = {
    chr(0x00D7): "x",    # MULTIPLICATION SIGN
    chr(0x2014): "-",    # EM DASH
    chr(0x2013): "-",    # EN DASH
    chr(0x2018): "'",    # LEFT SINGLE QUOTATION MARK
    chr(0x2019): "'",    # RIGHT SINGLE QUOTATION MARK
    chr(0x201C): '"',    # LEFT DOUBLE QUOTATION MARK
    chr(0x201D): '"',    # RIGHT DOUBLE QUOTATION MARK
}


def sanitize_doc(s: str) -> str:
    """Strip docstring-breaking + ruff-flagged characters from a summary."""
    for k, v in _AMBIGUOUS.items():
        s = s.replace(k, v)
    return s.replace('"""', '"" "')


def derive_names(op_id: str) -> tuple[str, str] | None:
    parts = op_id.split("_")
    parts = [re.sub(r"[{}]", "", p) for p in parts]
    parts = [p for p in parts if p]
    if not parts:
        return None
    ns = dash_to_snake(parts[0])
    if not ns:
        return None
    rest = parts[1:]
    method = "compute" if not rest else "_".join(dash_to_snake(p) for p in rest)
    if not method:
        return None
    return safe(ns), safe(method)


def main() -> int:
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    by_ns: dict[str, list[dict]] = {}

    for path, methods in spec.get("paths", {}).items():
        if not isinstance(methods, dict):
            continue
        # GET lookups get namespace methods too. Filtering on "post" alone
        # left the spec's GET-only paths reachable only through the raw client.
        op = methods.get("post") or methods.get("get")
        http_method = "POST" if methods.get("post") else "GET"
        if not op or not op.get("operationId"):
            continue
        if "{" in path:  # path-template endpoints — out of scope
            continue
        # Only endpoints answering with the JSON envelope get a typed method.
        # The /embed/* widgets serve HTML; api-calc declares text/html for them
        # since 2026-08-04, so this filter needs no per-path list. The explicit
        # /embed/ skip is belt and braces until openapi.json is resynced past
        # that date, because the frozen snapshot still claims JSON.
        responses = op.get("responses") or {}
        ok_content = ((responses.get("200") or {}).get("content") or {})
        if "application/json" not in ok_content:
            continue
        if path.startswith("/embed/"):
            continue
        # /public/* mirrors keyed endpoints the SDK already exposes.
        if path.startswith("/public/"):
            continue
        # System endpoints are hand-written on the client as health()/version().
        if "System" in (op.get("tags") or []):
            continue
        names = derive_names(op["operationId"])
        if not names:
            continue
        ns, method = names
        by_ns.setdefault(ns, []).append({
            "method": method,
            "path": path,
            "http_method": http_method,
            "summary": op.get("summary"),
        })

    # Detect collisions (same ns.method pointing to different paths).
    collisions = 0
    for ns, items in by_ns.items():
        seen: dict[str, str] = {}
        for it in items:
            if it["method"] in seen and seen[it["method"]] != it["path"]:
                print(
                    f"Collision: {ns}.{it['method']} → {seen[it['method']]} vs {it['path']}",
                    file=sys.stderr,
                )
                collisions += 1
            seen[it["method"]] = it["path"]
    if collisions:
        print(f"Aborting: {collisions} namespace collisions.", file=sys.stderr)
        return 1

    sorted_ns = sorted(by_ns)
    for ns in sorted_ns:
        by_ns[ns].sort(key=lambda x: x["method"])

    out: list[str] = []
    out.append('"""AUTO-GENERATED by scripts/generate_namespaces.py — DO NOT EDIT BY HAND.')
    out.append("")
    out.append("Run `python scripts/generate_namespaces.py` to refresh from openapi.json.")
    out.append('"""')
    out.append("")
    out.append("from __future__ import annotations")
    out.append("")
    out.append("from collections.abc import Mapping")
    out.append("from typing import TYPE_CHECKING, Any")
    out.append("")
    out.append("if TYPE_CHECKING:")
    out.append("    from ._client import AsyncAstroway  # noqa: I001")
    out.append("    from ._client import Astroway")
    out.append("")
    out.append("")

    # Sync namespace classes.
    for ns in sorted_ns:
        items = by_ns[ns]
        cls = "".join(p.title() for p in ns.split("_")) + "Namespace"
        out.append(f"class _{cls}:")
        out.append(f'    """Sync namespace for `{ns}.*` endpoints."""')
        out.append("")
        out.append('    __slots__ = ("_client",)')
        out.append("")
        out.append('    def __init__(self, client: Astroway) -> None:')
        out.append("        self._client = client")
        out.append("")
        for item in items:
            verb = item["http_method"]
            doc = sanitize_doc(item["summary"] or f"{verb} {item['path']}")
            if verb == "GET":
                # No body, and no idempotency key: neither means anything on a read.
                out.append(
                    f"    def {item['method']}(self, *, "
                    f"params: Mapping[str, Any] | None = None, "
                    f"headers: Mapping[str, str] | None = None) -> Any:"
                )
                out.append(f'        """{doc} (GET {item["path"]})"""')
                out.append(
                    f'        return self._client.request("GET", "{item["path"]}", '
                    f"params=params, headers=headers)"
                )
            else:
                out.append(
                    f"    def {item['method']}(self, body: Any = None, *, "
                    f"params: Mapping[str, Any] | None = None, "
                    f"headers: Mapping[str, str] | None = None, "
                    f'idempotency_key: str | None = None) -> Any:'
                )
                out.append(f'        """{doc} (POST {item["path"]})"""')
                out.append(
                    f'        return self._client.request("POST", "{item["path"]}", '
                    f"body=body, params=params, headers=headers, idempotency_key=idempotency_key)"
                )
            out.append("")
        out.append("")

    # Async namespace classes.
    for ns in sorted_ns:
        items = by_ns[ns]
        cls = "".join(p.title() for p in ns.split("_")) + "AsyncNamespace"
        out.append(f"class _{cls}:")
        out.append(f'    """Async namespace for `{ns}.*` endpoints."""')
        out.append("")
        out.append('    __slots__ = ("_client",)')
        out.append("")
        out.append('    def __init__(self, client: AsyncAstroway) -> None:')
        out.append("        self._client = client")
        out.append("")
        for item in items:
            verb = item["http_method"]
            doc = sanitize_doc(item["summary"] or f"{verb} {item['path']}")
            if verb == "GET":
                out.append(
                    f"    async def {item['method']}(self, *, "
                    f"params: Mapping[str, Any] | None = None, "
                    f"headers: Mapping[str, str] | None = None) -> Any:"
                )
                out.append(f'        """{doc} (GET {item["path"]})"""')
                out.append(
                    f'        return await self._client.request("GET", "{item["path"]}", '
                    f"params=params, headers=headers)"
                )
            else:
                out.append(
                    f"    async def {item['method']}(self, body: Any = None, *, "
                    f"params: Mapping[str, Any] | None = None, "
                    f"headers: Mapping[str, str] | None = None, "
                    f'idempotency_key: str | None = None) -> Any:'
                )
                out.append(f'        """{doc} (POST {item["path"]})"""')
                out.append(
                    f'        return await self._client.request("POST", "{item["path"]}", '
                    f"body=body, params=params, headers=headers, idempotency_key=idempotency_key)"
                )
            out.append("")
        out.append("")

    # Attach helpers.
    out.append("# Attach helpers used by the client constructors.")
    out.append("def _attach_sync(client: Astroway) -> None:")
    for ns in sorted_ns:
        cls = "".join(p.title() for p in ns.split("_")) + "Namespace"
        out.append(f'    client.{ns} = _{cls}(client)  # type: ignore[attr-defined]')
    out.append("")
    out.append("")
    out.append("def _attach_async(client: AsyncAstroway) -> None:")
    for ns in sorted_ns:
        cls = "".join(p.title() for p in ns.split("_")) + "AsyncNamespace"
        out.append(f'    client.{ns} = _{cls}(client)  # type: ignore[attr-defined]')
    out.append("")
    out.append("")
    out.append("__all__ = [")
    out.append('    "_attach_async",')
    out.append('    "_attach_sync",')
    out.append("]")
    out.append("")

    OUT.write_text("\n".join(out), encoding="utf-8")
    total_methods = sum(len(v) for v in by_ns.values())
    print(f"Wrote {OUT}")
    print(f"Namespaces: {len(sorted_ns)}, methods: {total_methods}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
