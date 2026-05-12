"""FastAPI integration — Depends-based dependency injection + lifespan client.

Install: ``pip install 'astroway[fastapi]'``

Quick setup::

    from contextlib import asynccontextmanager
    from fastapi import Depends, FastAPI
    from astroway import AsyncAstroway
    from astroway.integrations.fastapi import (
        astroway_lifespan,
        get_astroway,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with astroway_lifespan(api_key=os.environ['ASTROWAY_API_KEY']) as aw:
            app.state.astroway = aw
            yield

    app = FastAPI(lifespan=lifespan)

    @app.post('/chart')
    async def chart(body: dict, aw: AsyncAstroway = Depends(get_astroway)):
        return await aw.chart.compute(body)

The ``astroway_lifespan`` context manager creates the AsyncAstroway client at
startup and closes it on shutdown — so you don't leak HTTP connections per
request and don't pay handshake cost on the hot path.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

try:
    from fastapi import Request  # type: ignore[import-not-found]
except ImportError as exc:  # pragma: no cover — exercised only in extras tests
    raise ImportError(
        "astroway.integrations.fastapi requires FastAPI. "
        "Install via: pip install 'astroway[fastapi]'"
    ) from exc

from .. import AsyncAstroway

__all__ = ["astroway_lifespan", "get_astroway"]


@asynccontextmanager
async def astroway_lifespan(
    *,
    api_key: str,
    base_url: str | None = None,
    timeout: float = 30.0,
    **kwargs: Any,
) -> AsyncIterator[AsyncAstroway]:
    """Lifespan helper — creates one AsyncAstroway, closes it on shutdown.

    Use inside a ``lifespan`` context manager registered on ``FastAPI(lifespan=...)``;
    the yielded client should be stored on ``app.state.astroway`` so request
    handlers can pull it via ``get_astroway`` / ``Depends(get_astroway)``.

    Extra kwargs are forwarded to ``AsyncAstroway`` so users keep access to
    ``http_client=``, ``transport=`` (e.g. ``'aiohttp'``), ``limits=``, etc.
    """
    aw = AsyncAstroway(api_key=api_key, base_url=base_url, timeout=timeout, **kwargs)
    try:
        yield aw
    finally:
        await aw.aclose()


def get_astroway(request: Request) -> AsyncAstroway:
    """``Depends()`` source — returns the lifespan-managed client.

    Raises a clear RuntimeError if you forgot to register ``astroway_lifespan``
    in the FastAPI lifespan, instead of an opaque AttributeError.
    """
    aw = getattr(request.app.state, "astroway", None)
    if aw is None:
        raise RuntimeError(
            "astroway client not in app.state — did you forget to register "
            "astroway_lifespan() in FastAPI(lifespan=...)? See module docstring."
        )
    return aw
