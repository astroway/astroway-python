"""Framework integrations — Django settings binding + FastAPI lifespan injection."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

import pytest


# ─── Django integration ────────────────────────────────────────────────────


def _configure_django(api_key: str = "aw_test_x") -> None:
    """Lazy Django settings setup — `astroway[django]` extra ships Django,
    but importing it without configure() is a hard error."""
    import django  # type: ignore[import-not-found]
    from django.conf import settings  # type: ignore[import-not-found]
    if settings.configured:
        return
    settings.configure(
        DEBUG=True,
        DATABASES={},
        ASTROWAY_API_KEY=api_key,
        ASTROWAY_TIMEOUT=15.0,
        INSTALLED_APPS=[],
    )
    django.setup()


def test_django_get_astroway_returns_singleton() -> None:
    _configure_django()
    from astroway.integrations.django import get_astroway

    a = get_astroway()
    b = get_astroway()
    assert a is b, "lru_cache must keep one instance per process"
    assert a.api_key == "aw_test_x"
    # Reset after test so other tests can re-configure if needed.
    get_astroway.cache_clear()


def test_django_missing_api_key_raises_improperly_configured() -> None:
    """If ASTROWAY_API_KEY is unset, the factory must surface a clear error
    pointing at Django's standard misconfig signal — not a generic ValueError."""
    import django  # noqa: F401  # ensure django is loaded
    from django.conf import settings  # type: ignore[import-not-found]
    from django.core.exceptions import ImproperlyConfigured  # type: ignore[import-not-found]
    from astroway.integrations.django import get_astroway

    # Drop the key on the live settings object.
    original = getattr(settings, "ASTROWAY_API_KEY", None)
    try:
        settings.ASTROWAY_API_KEY = ""
        get_astroway.cache_clear()
        with pytest.raises(ImproperlyConfigured, match="ASTROWAY_API_KEY"):
            get_astroway()
    finally:
        settings.ASTROWAY_API_KEY = original
        get_astroway.cache_clear()


# ─── FastAPI integration ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fastapi_lifespan_yields_async_client() -> None:
    from astroway import AsyncAstroway
    from astroway.integrations.fastapi import astroway_lifespan

    async with astroway_lifespan(api_key="aw_test_x") as aw:
        assert isinstance(aw, AsyncAstroway)
        assert aw.api_key == "aw_test_x"


@pytest.mark.asyncio
async def test_fastapi_lifespan_passes_through_kwargs() -> None:
    from astroway.integrations.fastapi import astroway_lifespan

    async with astroway_lifespan(
        api_key="aw_test_x",
        timeout=12.5,
        base_url="https://staging.api.astroway.info/v1",
    ) as aw:
        assert aw.timeout == 12.5
        assert aw.base_url == "https://staging.api.astroway.info/v1"


def test_fastapi_get_astroway_raises_when_lifespan_missing() -> None:
    """If the user forgets to wire up the lifespan, ``Depends(get_astroway)``
    must give them a clear runtime error pointing at the docstring — not a
    cryptic AttributeError."""
    from fastapi import FastAPI  # type: ignore[import-not-found]
    from astroway.integrations.fastapi import get_astroway

    app = FastAPI()

    # Build a Request stub mimicking what FastAPI passes in.
    class _Req:
        def __init__(self, app):
            self.app = app

    with pytest.raises(RuntimeError, match="astroway_lifespan"):
        get_astroway(_Req(app))  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_fastapi_get_astroway_returns_lifespan_client() -> None:
    from fastapi import FastAPI  # type: ignore[import-not-found]
    from astroway.integrations.fastapi import astroway_lifespan, get_astroway

    app = FastAPI()

    class _Req:
        def __init__(self, app):
            self.app = app

    async with astroway_lifespan(api_key="aw_test_x") as aw:
        app.state.astroway = aw
        out = get_astroway(_Req(app))  # type: ignore[arg-type]
        assert out is aw
