"""Astroway / AsyncAstroway — sync + async clients wrapping httpx with auth,
retry, error mapping, and identification headers.
"""

from __future__ import annotations

import platform
import sys
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

import httpx
from pydantic import BaseModel

if TYPE_CHECKING:
    from ._pagination import AsyncPaginator, SyncPaginator
    from ._streaming import AsyncSSEStream, SyncSSEStream

from ._cache import (
    CacheEntry,
    ResolvedCache,
    build_cache_key,
    is_deterministic_path,
    is_expired,
    resolve_cache_option,
)
from ._idempotency import (
    IdempotencyMode,
    resolve_key_generator,
    should_attach_idempotency,
)
from ._retry import AsyncRetryTransport, RetryConfig, SyncRetryTransport
from ._version import SDK_VERSION
from .errors import (
    APIConnectionError,
    ApiError,
    APITimeoutError,
    classify_http_error,
)

DEFAULT_BASE_URL = "https://api.astroway.info/v1"
AuthScheme = Literal["header", "bearer"]
TransportBackend = Literal["httpx", "aiohttp"]


def _resolve_sync_transport(
    transport: "httpx.BaseTransport | str | None",
    *,
    limits: httpx.Limits | None,
) -> httpx.BaseTransport:
    if transport is None:
        return httpx.HTTPTransport(limits=limits) if limits is not None else httpx.HTTPTransport()
    if isinstance(transport, str):
        raise ValueError(
            f"transport={transport!r} is not supported on the sync client. "
            "Pass an httpx.BaseTransport instance, or use AsyncAstroway with transport='aiohttp'."
        )
    return transport


def _resolve_async_transport(
    transport: "httpx.AsyncBaseTransport | TransportBackend | None",
    *,
    limits: httpx.Limits | None,
) -> httpx.AsyncBaseTransport:
    if transport is None or transport == "httpx":
        return (
            httpx.AsyncHTTPTransport(limits=limits)
            if limits is not None
            else httpx.AsyncHTTPTransport()
        )
    if transport == "aiohttp":
        try:
            from httpx_aiohttp import AiohttpTransport  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover — exercised in extras tests
            raise ImportError(
                "transport='aiohttp' requires the optional aiohttp backend: "
                "`pip install astroway[aiohttp]` (installs httpx-aiohttp)."
            ) from exc
        return AiohttpTransport()
    if isinstance(transport, str):
        raise ValueError(
            f"Unknown transport={transport!r}. Expected 'httpx', 'aiohttp', or an httpx.AsyncBaseTransport."
        )
    return transport


@dataclass(frozen=True)
class RawResponse:
    """Result envelope returned by ``request_with_response()`` / ``post_with_response()``.

    Carries the unwrapped ``data`` (same value the regular method would return)
    plus AstroWay metadata for support tickets and credit dashboards.
    """

    data: Any
    request_id: str | None
    credits_remaining: int | None
    headers: httpx.Headers
    status_code: int


def _serialize_body(body: Any) -> Any:
    """Convert Pydantic models to dict; pass through dicts/lists/None unchanged.

    Uses ``by_alias=True`` so camelCase field aliases hit the wire (`timezoneOffset`,
    not `timezone_offset`), and ``exclude_none=True`` to drop optional fields the
    user didn't set so server-side defaults apply.
    """
    if body is None:
        return None
    if isinstance(body, BaseModel):
        return body.model_dump(by_alias=True, exclude_none=True)
    return body


def _user_agent() -> str:
    py = f"Python/{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    plat = f"{platform.system().lower()}-{platform.machine().lower()}"
    return f"astroway-sdk-python/{SDK_VERSION} ({py}; {plat})"


def _default_headers(api_key: str, auth_scheme: AuthScheme) -> dict[str, str]:
    headers: dict[str, str] = {
        "User-Agent": _user_agent(),
        "X-Astroway-Channel": "sdk-py",
        "Content-Type": "application/json",
    }
    if auth_scheme == "bearer":
        headers["Authorization"] = f"Bearer {api_key}"
    else:
        headers["X-Api-Key"] = api_key
    return headers


def _parse_int_header(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def _raise_on_error(response: httpx.Response) -> None:
    if response.is_success:
        return
    request_id = response.headers.get("x-request-id")
    retry_after_seconds = _parse_int_header(response.headers.get("retry-after"))
    credits_remaining = _parse_int_header(response.headers.get("x-credits-remaining"))

    body: Any = None
    code: str | None = None
    message = f"{response.status_code} {response.reason_phrase}"
    try:
        body = response.json()
        err = body.get("error") if isinstance(body, dict) else None
        if isinstance(err, dict):
            if err.get("code"):
                code = str(err["code"])
            if err.get("message"):
                message = str(err["message"])
    except Exception:
        pass

    raise classify_http_error(
        status=response.status_code,
        message=message,
        code=code,
        body=body,
        request_id=request_id,
        retry_after_seconds=retry_after_seconds,
        credits_remaining=credits_remaining,
    )


class _BaseAstroway:
    """Shared constructor logic + property accessors for sync and async clients."""

    base_url: str
    api_key: str
    auth_scheme: AuthScheme
    timeout: float
    retry: RetryConfig
    idempotency: IdempotencyMode
    cache: ResolvedCache | None

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str | None = None,
        auth_scheme: AuthScheme = "header",
        timeout: float = 30.0,
        retry: dict | RetryConfig | None = None,
        default_headers: Mapping[str, str] | None = None,
        idempotency: IdempotencyMode | None = None,
        cache: Any = None,
        lang: str | None = None,
    ) -> None:
        if not api_key:
            raise ApiError(
                "Astroway: api_key is required. Get one at "
                "https://api.astroway.info/dashboard/sign-up — 10,000 credits/month free."
            )
        self.api_key = api_key
        self.base_url = base_url or DEFAULT_BASE_URL
        self.auth_scheme = auth_scheme
        self.idempotency = idempotency if idempotency is not None else "auto"
        self._idempotency_generator = resolve_key_generator(self.idempotency)
        self.timeout = timeout
        self.lang = lang
        self.retry = (
            retry if isinstance(retry, RetryConfig) else RetryConfig.from_dict(retry)
        )
        # Inject Accept-Language into base headers if lang is set; caller-supplied
        # default_headers wins. Server (api-calc v2.30.0+) resolves the header
        # against 21 active langs and routes into AI prompt instructions for
        # /horoscope/* + /interpret/*. Numeric fields stay canonical.
        lang_header = {"Accept-Language": lang} if lang else {}
        self._headers: dict[str, str] = {
            **_default_headers(api_key, auth_scheme),
            **lang_header,
            **(dict(default_headers) if default_headers else {}),
        }
        self.cache = resolve_cache_option(cache)


class Astroway(_BaseAstroway):
    """Synchronous Astroway client.

    Example::

        from astroway import Astroway
        aw = Astroway(api_key="aw_live_...")
        chart = aw.post("/chart", body={
            "date": "1990-07-14", "time": "14:30:00", "timezoneOffset": 3,
            "latitude": 50.45, "longitude": 30.52,
        })
        print(chart["angles"]["asc"])
    """

    _http: httpx.Client

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str | None = None,
        auth_scheme: AuthScheme = "header",
        timeout: float = 30.0,
        retry: dict | RetryConfig | None = None,
        default_headers: Mapping[str, str] | None = None,
        transport: httpx.BaseTransport | str | None = None,
        limits: httpx.Limits | None = None,
        http_client: httpx.Client | None = None,
        idempotency: IdempotencyMode | None = None,
        cache: Any = None,
        lang: str | None = None,
    ) -> None:
        super().__init__(
            api_key=api_key,
            base_url=base_url,
            auth_scheme=auth_scheme,
            timeout=timeout,
            retry=retry,
            default_headers=default_headers,
            idempotency=idempotency,
            cache=cache,
            lang=lang,
        )
        if http_client is not None:
            if transport is not None or limits is not None:
                raise ValueError(
                    "Pass either http_client OR (transport / limits), not both. "
                    "When you bring your own httpx.Client we don't override its transport."
                )
            # User-supplied client: SDK identification + auth headers always win
            # (User-Agent, X-Astroway-Channel, X-Api-Key/Authorization, Content-Type)
            # so analytics/server logs stay accurate regardless of how the client was built.
            for k, v in self._headers.items():
                http_client.headers[k] = v
            self._http = http_client
            self._owns_http = False
        else:
            inner = _resolve_sync_transport(transport, limits=limits)
            wrapped = SyncRetryTransport(inner, self.retry)
            self._http = httpx.Client(
                base_url=self.base_url,
                headers=self._headers,
                timeout=self.timeout,
                transport=wrapped,
            )
            self._owns_http = True
        from ._namespaces import _attach_sync
        _attach_sync(self)

    def _send(
        self,
        method: str,
        path: str,
        *,
        body: Any | None = None,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        idempotency_key: str | None = None,
        cache_override: bool | None = None,
    ) -> RawResponse:
        body = _serialize_body(body)

        # Cache lookup pre-flight.
        cache_key: str | None = None
        if self.cache is not None and cache_override is not False:
            should_cache = cache_override is True or is_deterministic_path(path)
            if should_cache:
                cache_key = build_cache_key(method, path, body)
                hit = self.cache.store.get(cache_key)
                if hit is not None and not is_expired(hit):
                    return RawResponse(
                        data=hit.value,
                        request_id=None,
                        credits_remaining=None,
                        headers=httpx.Headers({"x-astroway-cache": "hit"}),
                        status_code=200,
                    )

        merged_headers: dict[str, str] = dict(headers) if headers else {}
        if idempotency_key is not None:
            merged_headers["Idempotency-Key"] = idempotency_key
        elif (
            should_attach_idempotency(self.idempotency, method)
            and "idempotency-key" not in {k.lower() for k in merged_headers}
        ):
            merged_headers["Idempotency-Key"] = self._idempotency_generator()
        try:
            response = self._http.request(
                method,
                path,
                json=body,
                params=params,
                headers=merged_headers or None,
            )
        except httpx.TimeoutException as exc:
            raise APITimeoutError(
                f"Request to {path} timed out after {self.timeout}s"
            ) from exc
        except httpx.HTTPError as exc:
            raise APIConnectionError(
                f"Network error calling {path}: {exc!s}. Check connection or base_url."
            ) from exc

        _raise_on_error(response)
        try:
            payload = response.json()
        except Exception:
            payload = response.text
        # Unwrap `{ ok, data, error }` envelope when present.
        data = payload["data"] if isinstance(payload, dict) and "data" in payload else payload

        if self.cache is not None and cache_key is not None and response.is_success:
            self.cache.store.set(
                cache_key,
                CacheEntry(value=data, expires_at=time.time() + self.cache.default_ttl_seconds),
            )

        return RawResponse(
            data=data,
            request_id=response.headers.get("x-request-id"),
            credits_remaining=_parse_int_header(response.headers.get("x-credits-remaining")),
            headers=response.headers,
            status_code=response.status_code,
        )

    def request(
        self,
        method: str,
        path: str,
        *,
        body: Any | None = None,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        idempotency_key: str | None = None,
        cache: bool | None = None,
    ) -> Any:
        return self._send(
            method, path,
            body=body, params=params, headers=headers,
            idempotency_key=idempotency_key, cache_override=cache,
        ).data

    def request_with_response(
        self,
        method: str,
        path: str,
        *,
        body: Any | None = None,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        idempotency_key: str | None = None,
    ) -> RawResponse:
        """Same as :meth:`request` but returns :class:`RawResponse` with metadata."""
        return self._send(
            method, path,
            body=body, params=params, headers=headers, idempotency_key=idempotency_key,
        )

    def get(self, path: str, *, params: Mapping[str, Any] | None = None) -> Any:
        return self.request("GET", path, params=params)

    def post(
        self,
        path: str,
        *,
        body: Any | None = None,
        params: Mapping[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> Any:
        return self.request(
            "POST", path, body=body, params=params, idempotency_key=idempotency_key,
        )

    def post_with_response(
        self,
        path: str,
        *,
        body: Any | None = None,
        params: Mapping[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> RawResponse:
        """POST and return :class:`RawResponse` with request_id + credits_remaining + headers."""
        return self.request_with_response(
            "POST", path, body=body, params=params, idempotency_key=idempotency_key,
        )

    def put(self, path: str, *, body: Any | None = None) -> Any:
        return self.request("PUT", path, body=body)

    def delete(self, path: str) -> Any:
        return self.request("DELETE", path)

    def paginate(
        self,
        method: str,
        path: str,
        *,
        body: Any | None = None,
        params: Mapping[str, Any] | None = None,
    ) -> SyncPaginator[Any]:
        """Return a cursor-based auto-paginator for a list endpoint.

        Iterate to walk every item across all pages; ``.pages()`` for raw pages.
        Endpoints not yet paginated yield a single page with the whole payload.
        """
        from ._pagination import SyncPaginator
        return SyncPaginator(
            self, method, path, body=body, params=dict(params) if params else None,
        )

    def stream_sse(
        self,
        path: str,
        *,
        body: Any | None = None,
        params: Mapping[str, Any] | None = None,
        method: str = "POST",
        idempotency_key: str | None = None,
    ) -> SyncSSEStream:
        """Open a Server-Sent Events stream against an SSE-capable endpoint.

        Iterate to walk normalised chunks::

            for chunk in aw.stream_sse("/horoscope/daily", body={"date": "2026-05-10"}):
                if chunk.type == "text_delta":
                    print(chunk.text, end="", flush=True)
                elif chunk.type == "done":
                    break
        """
        from ._streaming import SyncSSEStream
        return SyncSSEStream(
            self, method, path,
            body=_serialize_body(body),
            params=dict(params) if params else None,
            idempotency_key=idempotency_key,
        )

    def close(self) -> None:
        # Only close clients we created; user-supplied http_client lifecycles are theirs.
        if self._owns_http:
            self._http.close()

    def __enter__(self) -> Astroway:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


class AsyncAstroway(_BaseAstroway):
    """Async counterpart of :class:`Astroway`. Same surface, awaitable methods.

    Example::

        from astroway import AsyncAstroway
        async with AsyncAstroway(api_key="aw_live_...") as aw:
            chart = await aw.post("/chart", body={...})
    """

    _http: httpx.AsyncClient

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str | None = None,
        auth_scheme: AuthScheme = "header",
        timeout: float = 30.0,
        retry: dict | RetryConfig | None = None,
        default_headers: Mapping[str, str] | None = None,
        transport: "httpx.AsyncBaseTransport | TransportBackend | None" = None,
        limits: httpx.Limits | None = None,
        http_client: httpx.AsyncClient | None = None,
        idempotency: IdempotencyMode | None = None,
        cache: Any = None,
        lang: str | None = None,
    ) -> None:
        super().__init__(
            api_key=api_key,
            base_url=base_url,
            auth_scheme=auth_scheme,
            timeout=timeout,
            retry=retry,
            default_headers=default_headers,
            idempotency=idempotency,
            cache=cache,
            lang=lang,
        )
        if http_client is not None:
            if transport is not None or limits is not None:
                raise ValueError(
                    "Pass either http_client OR (transport / limits), not both. "
                    "When you bring your own httpx.AsyncClient we don't override its transport."
                )
            for k, v in self._headers.items():
                http_client.headers.setdefault(k, v)
            self._http = http_client
            self._owns_http = False
        else:
            inner = _resolve_async_transport(transport, limits=limits)
            wrapped = AsyncRetryTransport(inner, self.retry)
            self._http = httpx.AsyncClient(
                base_url=self.base_url,
                headers=self._headers,
                timeout=self.timeout,
                transport=wrapped,
            )
            self._owns_http = True
        from ._namespaces import _attach_async
        _attach_async(self)

    async def _send(
        self,
        method: str,
        path: str,
        *,
        body: Any | None = None,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        idempotency_key: str | None = None,
        cache_override: bool | None = None,
    ) -> RawResponse:
        body = _serialize_body(body)

        cache_key: str | None = None
        if self.cache is not None and cache_override is not False:
            should_cache = cache_override is True or is_deterministic_path(path)
            if should_cache:
                cache_key = build_cache_key(method, path, body)
                hit = self.cache.store.get(cache_key)
                if hit is not None and not is_expired(hit):
                    return RawResponse(
                        data=hit.value,
                        request_id=None,
                        credits_remaining=None,
                        headers=httpx.Headers({"x-astroway-cache": "hit"}),
                        status_code=200,
                    )

        merged_headers: dict[str, str] = dict(headers) if headers else {}
        if idempotency_key is not None:
            merged_headers["Idempotency-Key"] = idempotency_key
        elif (
            should_attach_idempotency(self.idempotency, method)
            and "idempotency-key" not in {k.lower() for k in merged_headers}
        ):
            merged_headers["Idempotency-Key"] = self._idempotency_generator()
        try:
            response = await self._http.request(
                method,
                path,
                json=body,
                params=params,
                headers=merged_headers or None,
            )
        except httpx.TimeoutException as exc:
            raise APITimeoutError(
                f"Request to {path} timed out after {self.timeout}s"
            ) from exc
        except httpx.HTTPError as exc:
            raise APIConnectionError(
                f"Network error calling {path}: {exc!s}. Check connection or base_url."
            ) from exc

        _raise_on_error(response)
        try:
            payload = response.json()
        except Exception:
            payload = response.text
        data = payload["data"] if isinstance(payload, dict) and "data" in payload else payload

        if self.cache is not None and cache_key is not None and response.is_success:
            self.cache.store.set(
                cache_key,
                CacheEntry(value=data, expires_at=time.time() + self.cache.default_ttl_seconds),
            )

        return RawResponse(
            data=data,
            request_id=response.headers.get("x-request-id"),
            credits_remaining=_parse_int_header(response.headers.get("x-credits-remaining")),
            headers=response.headers,
            status_code=response.status_code,
        )

    async def request(
        self,
        method: str,
        path: str,
        *,
        body: Any | None = None,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        idempotency_key: str | None = None,
        cache: bool | None = None,
    ) -> Any:
        result = await self._send(
            method, path,
            body=body, params=params, headers=headers,
            idempotency_key=idempotency_key, cache_override=cache,
        )
        return result.data

    async def request_with_response(
        self,
        method: str,
        path: str,
        *,
        body: Any | None = None,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
        idempotency_key: str | None = None,
    ) -> RawResponse:
        """Async :meth:`Astroway.request_with_response`."""
        return await self._send(
            method, path,
            body=body, params=params, headers=headers, idempotency_key=idempotency_key,
        )

    async def get(self, path: str, *, params: Mapping[str, Any] | None = None) -> Any:
        return await self.request("GET", path, params=params)

    async def post(
        self,
        path: str,
        *,
        body: Any | None = None,
        params: Mapping[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> Any:
        return await self.request(
            "POST", path, body=body, params=params, idempotency_key=idempotency_key,
        )

    async def post_with_response(
        self,
        path: str,
        *,
        body: Any | None = None,
        params: Mapping[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> RawResponse:
        """Async POST returning :class:`RawResponse` with metadata."""
        return await self.request_with_response(
            "POST", path, body=body, params=params, idempotency_key=idempotency_key,
        )

    async def put(self, path: str, *, body: Any | None = None) -> Any:
        return await self.request("PUT", path, body=body)

    async def delete(self, path: str) -> Any:
        return await self.request("DELETE", path)

    def paginate(
        self,
        method: str,
        path: str,
        *,
        body: Any | None = None,
        params: Mapping[str, Any] | None = None,
    ) -> AsyncPaginator[Any]:
        """Return a cursor-based async auto-paginator. Use ``async for`` to walk items.

        Endpoints not yet paginated yield a single page with the whole payload.
        """
        from ._pagination import AsyncPaginator
        return AsyncPaginator(
            self, method, path, body=body, params=dict(params) if params else None,
        )

    def stream_sse(
        self,
        path: str,
        *,
        body: Any | None = None,
        params: Mapping[str, Any] | None = None,
        method: str = "POST",
        idempotency_key: str | None = None,
    ) -> AsyncSSEStream:
        """Open an async Server-Sent Events stream. Use ``async for`` to walk chunks::

            async for chunk in aw.stream_sse("/horoscope/daily", body={...}):
                if chunk.type == "text_delta":
                    print(chunk.text, end="")
        """
        from ._streaming import AsyncSSEStream
        return AsyncSSEStream(
            self, method, path,
            body=_serialize_body(body),
            params=dict(params) if params else None,
            idempotency_key=idempotency_key,
        )

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    async def __aenter__(self) -> AsyncAstroway:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()
