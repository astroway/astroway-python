"""What the 1.5.0 spec resync brought, pinned so a later resync cannot drop it.

The bundled snapshot was frozen at api-calc 2.105.0 and is now 2.152.1: 24 new
paths, 74 new components, 22 new methods, nothing removed or renamed. The same
two numbers (112 namespaces, 709 methods) come out of the TypeScript and PHP
generators, which is the cheapest cross-check that the three still agree.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from astroway import Astroway, AsyncAstroway, BirthData

SPEC = json.loads((Path(__file__).resolve().parent.parent / "openapi.json").read_text(encoding="utf-8"))


def test_methods_added_by_the_resync_exist() -> None:
    aw = Astroway(api_key="aw_test_x")
    for ns, method in [
        ("vedic", "gemstones"),
        ("vedic", "varshaphal"),
        ("vedic", "bhavabala"),
        ("kabbalah", "gematria"),
        ("parans", "star"),
        ("reports", "relocation"),
        ("reports", "gemstone"),
        ("chinese", "solar_terms"),
        ("chinese", "feng_shui_flying_star"),
        ("wellness", "biorhythm"),
        ("ziwei", "four_transformations"),
        ("acg", "best_places"),
        ("agent", "tools_get"),
    ]:
        assert callable(getattr(getattr(aw, ns), method)), f"{ns}.{method}"


def test_async_surface_matches_sync() -> None:
    """Both generators walk the same list, so a method missing on one side means
    the emit loops have drifted."""
    sync = Astroway(api_key="aw_test_x")
    a_sync = AsyncAstroway(api_key="aw_test_x")
    for ns in ("vedic", "kabbalah", "parans", "reports", "chinese", "wellness", "ziwei", "acg", "agent"):
        sync_methods = {m for m in dir(getattr(sync, ns)) if not m.startswith("_")}
        async_methods = {m for m in dir(getattr(a_sync, ns)) if not m.startswith("_")}
        assert sync_methods == async_methods, ns


def test_html_widgets_and_keyless_mirror_stay_out() -> None:
    """/embed/* answers text/html and /public/* mirrors keyed endpoints. The
    explicit /embed/ skip went out with this resync: the content-type filter is
    enough now that every widget path declares text/html."""
    aw = Astroway(api_key="aw_test_x")
    assert not hasattr(aw, "embed")
    assert not hasattr(aw, "public")
    embed_paths = [p for p in SPEC["paths"] if p.startswith("/embed/")]
    assert len(embed_paths) == 14
    for p in embed_paths:
        op = SPEC["paths"][p].get("post") or SPEC["paths"][p].get("get")
        assert "application/json" not in op["responses"]["200"]["content"], p


def test_birth_data_will_not_send_a_chart_with_no_place() -> None:
    """The model defaulted latitude and longitude to 0, so a caller who omitted
    them sent a real request for 0N 0E rather than triggering the server's
    deprecation path. api-calc stopped defaulting them in 2.141.0."""
    with pytest.raises(ValueError):
        BirthData(date="1990-07-14", time="14:30:00")
    ok = BirthData(date="1990-07-14", time="14:30:00", latitude=50.45, longitude=30.52)
    assert ok.model_dump(by_alias=True)["latitude"] == 50.45


def test_spec_carries_the_typed_request_bodies() -> None:
    """246 paths published a bare {"type": "object"} body until api-calc
    2.152.0. A dynamic client cannot enforce them, but the docstrings and the
    error messages a caller sees both come from here."""
    untyped = []
    for path, item in SPEC["paths"].items():
        op = item.get("post") or item.get("put") or item.get("patch")
        schema = ((op or {}).get("requestBody", {}).get("content", {}).get("application/json", {}) or {}).get("schema")
        if schema and not any(k in schema for k in ("$ref", "properties", "allOf", "oneOf")):
            untyped.append(path)
    assert untyped == []
