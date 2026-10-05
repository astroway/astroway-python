"""Typed result for GET /natal-texts: pre-written natal interpretation
snippets keyed by planet+sign, planet+house or aspect pair.

Hand-written rather than generated: the path predates the frozen
``openapi.json`` snapshot this SDK resyncs from (see ROADMAP.md). Kept out of
``scripts/generate_namespaces.py`` for the same reason ``health()`` and
``version()`` are excluded by their ``System`` tag: the path-derived name
would also be ``natal_texts``, and a generated namespace of that name would
silently shadow the client method defined in ``_client.py``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

NatalTextKind = Literal["planet_in_sign", "planet_in_house", "aspect"]


@dataclass(frozen=True)
class NatalText:
    """One resolved text. ``title`` is null for the kinds the corpus writes untitled."""

    title: str | None
    body: str
    kind: NatalTextKind


@dataclass(frozen=True)
class NatalTextsResult:
    """Result of :meth:`Astroway.natal_texts`.

    ``texts`` holds one entry per requested key that has text in ``lang``.
    ``missing`` names the requested keys that do not, there is no fallback to
    another language.
    """

    lang: str
    texts: dict[str, NatalText]
    missing: list[str]


def natal_texts_params(keys: Sequence[str], lang: str) -> dict[str, str]:
    """Build the ``keys=<comma list>&lang=<code>`` query params from a Python list."""
    return {"keys": ",".join(keys), "lang": lang}


def parse_natal_texts_result(payload: Any) -> NatalTextsResult:
    """Parse the unwrapped ``{lang, texts, missing}`` body into a typed result."""
    texts_raw = payload.get("texts") if isinstance(payload, dict) else None
    texts = {
        key: NatalText(title=value.get("title"), body=value["body"], kind=value["kind"])
        for key, value in (texts_raw or {}).items()
    }
    missing = list(payload.get("missing") or []) if isinstance(payload, dict) else []
    lang = payload.get("lang", "") if isinstance(payload, dict) else ""
    return NatalTextsResult(lang=lang, texts=texts, missing=missing)
