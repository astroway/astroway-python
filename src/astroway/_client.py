"""Astroway / AsyncAstroway — sync + async clients wrapping httpx with auth,
retry, error mapping, and identification headers.
"""

from __future__ import annotations

import platform
import sys
from collections.abc import Mapping
from typing import Any, Literal

import httpx

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


def _raise_on_error(response: httpx.Response) -> None:
    if response.is_success:
        return
    request_id = response.headers.get("x-request-id")
    retry_after_raw = response.headers.get("retry-after")
    retry_after_seconds: int | None = None
    if retry_after_raw is not None:
        try:
            retry_after_seconds = int(float(retry_after_raw))
        except ValueError:
            retry_after_seconds = None

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
    )


class _BaseAstroway:
    """Shared constructor logic + property accessors for sync and async clients."""

    base_url: str
    api_key: str
    auth_scheme: AuthScheme
    timeout: float
    retry: RetryConfig

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str | None = None,
        auth_scheme: AuthScheme = "header",
        timeout: float = 30.0,
        retry: dict | RetryConfig | None = None,
        default_headers: Mapping[str, str] | None = None,
    ) -> None:
        if not api_key:
            raise ApiError(
                "Astroway: api_key is required. Get one at "
                "https://api.astroway.info/dashboard/sign-up — 10,000 credits/month free."
            )
        self.api_key = api_key
        self.base_url = base_url or DEFAULT_BASE_URL
        self.auth_scheme = auth_scheme
        self.timeout = timeout
        self.retry = (
            retry if isinstance(retry, RetryConfig) else RetryConfig.from_dict(retry)
        )
        self._headers: dict[str, str] = {
            **_default_headers(api_key, auth_scheme),
            **(dict(default_headers) if default_headers else {}),
        }


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
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        super().__init__(
            api_key=api_key,
            base_url=base_url,
            auth_scheme=auth_scheme,
            timeout=timeout,
            retry=retry,
            default_headers=default_headers,
        )
        inner = transport if transport is not None else httpx.HTTPTransport()
        wrapped = SyncRetryTransport(inner, self.retry)
        self._http = httpx.Client(
            base_url=self.base_url,
            headers=self._headers,
            timeout=self.timeout,
            transport=wrapped,
        )

    def request(
        self,
        method: str,
        path: str,
        *,
        body: Any | None = None,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        try:
            response = self._http.request(
                method,
                path,
                json=body,
                params=params,
                headers=dict(headers) if headers else None,
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
            return response.text
        # Endpoints wrap responses as { ok, data, error } — unwrap data when present.
        if isinstance(payload, dict) and "data" in payload:
            return payload["data"]
        return payload

    def get(self, path: str, *, params: Mapping[str, Any] | None = None) -> Any:
        return self.request("GET", path, params=params)

    def post(
        self,
        path: str,
        *,
        body: Any | None = None,
        params: Mapping[str, Any] | None = None,
    ) -> Any:
        return self.request("POST", path, body=body, params=params)

    def put(self, path: str, *, body: Any | None = None) -> Any:
        return self.request("PUT", path, body=body)

    def delete(self, path: str) -> Any:
        return self.request("DELETE", path)

    def close(self) -> None:
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
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(
            api_key=api_key,
            base_url=base_url,
            auth_scheme=auth_scheme,
            timeout=timeout,
            retry=retry,
            default_headers=default_headers,
        )
        inner = transport if transport is not None else httpx.AsyncHTTPTransport()
        wrapped = AsyncRetryTransport(inner, self.retry)
        self._http = httpx.AsyncClient(
            base_url=self.base_url,
            headers=self._headers,
            timeout=self.timeout,
            transport=wrapped,
        )

    async def request(
        self,
        method: str,
        path: str,
        *,
        body: Any | None = None,
        params: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        try:
            response = await self._http.request(
                method,
                path,
                json=body,
                params=params,
                headers=dict(headers) if headers else None,
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
            return response.text
        if isinstance(payload, dict) and "data" in payload:
            return payload["data"]
        return payload

    async def get(self, path: str, *, params: Mapping[str, Any] | None = None) -> Any:
        return await self.request("GET", path, params=params)

    async def post(
        self,
        path: str,
        *,
        body: Any | None = None,
        params: Mapping[str, Any] | None = None,
    ) -> Any:
        return await self.request("POST", path, body=body, params=params)

    async def put(self, path: str, *, body: Any | None = None) -> Any:
        return await self.request("PUT", path, body=body)

    async def delete(self, path: str) -> Any:
        return await self.request("DELETE", path)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> AsyncAstroway:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()
