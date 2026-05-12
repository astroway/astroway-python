"""Django integration — settings-driven Astroway client + cache backend.

Install: ``pip install 'astroway[django]'``

Add to ``settings.py``::

    INSTALLED_APPS = [
        # ...
        'astroway.integrations.django',
    ]
    ASTROWAY_API_KEY = os.environ['ASTROWAY_API_KEY']
    ASTROWAY_BASE_URL = 'https://api.astroway.info/v1'   # optional
    ASTROWAY_TIMEOUT = 30.0                               # optional, seconds

Use anywhere::

    from astroway.integrations.django import get_astroway

    def view(request):
        chart = get_astroway().chart.compute({'date': '1990-01-15', ...})
        return JsonResponse(chart)

The factory caches one Astroway instance per Django process, so you don't pay
PSR-18 discovery / TLS handshake on every request — same pattern Django itself
uses for ``django.core.cache.cache``.
"""

from __future__ import annotations

import functools
from typing import Any

try:
    from django.conf import settings  # type: ignore[import-not-found]
    from django.core.exceptions import ImproperlyConfigured  # type: ignore[import-not-found]
except ImportError as exc:  # pragma: no cover — exercised only in extras tests
    raise ImportError(
        "astroway.integrations.django requires Django. "
        "Install via: pip install 'astroway[django]'"
    ) from exc

from .. import Astroway, AsyncAstroway

__all__ = ["get_astroway", "get_async_astroway", "AstrowayConfig"]


class AstrowayConfig:
    """Default Django app config — picks up ``ASTROWAY_*`` settings.

    Setting it as an entry in ``INSTALLED_APPS`` is **not required** — the
    factories below work without app registration. The class exists for users
    who want Django to manage init order (e.g. before logging is configured).
    """
    name = "astroway.integrations.django"
    label = "astroway"
    verbose_name = "AstroWay API"


def _read_settings() -> dict[str, Any]:
    api_key = getattr(settings, "ASTROWAY_API_KEY", None)
    if not api_key:
        raise ImproperlyConfigured(
            "ASTROWAY_API_KEY is required in Django settings. "
            "Get one at https://api.astroway.info/dashboard/sign-up"
        )
    return {
        "api_key": api_key,
        "base_url": getattr(settings, "ASTROWAY_BASE_URL", None),
        "timeout": getattr(settings, "ASTROWAY_TIMEOUT", 30.0),
    }


@functools.lru_cache(maxsize=1)
def get_astroway() -> Astroway:
    """Return the process-wide sync Astroway client. Caches after first call."""
    cfg = _read_settings()
    return Astroway(
        api_key=cfg["api_key"],
        **{k: v for k, v in cfg.items() if k != "api_key" and v is not None},
    )


@functools.lru_cache(maxsize=1)
def get_async_astroway() -> AsyncAstroway:
    """Return the process-wide async client. Pair with Django's async views."""
    cfg = _read_settings()
    return AsyncAstroway(
        api_key=cfg["api_key"],
        **{k: v for k, v in cfg.items() if k != "api_key" and v is not None},
    )


# Django app registry hook — used when the integration is in INSTALLED_APPS.
default_app_config = "astroway.integrations.django.AstrowayConfig"
