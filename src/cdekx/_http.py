"""HTTP layer: transport, timeouts, retries, response parsing.

This is the only place in the library that knows about ``httpx``. Endpoints work
exclusively with :class:`HttpClient`, so swapping the transport (for
``aiohttp``, say) does not touch the public API.
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

import httpx

from ._auth import AuthProvider
from .exceptions import (
    TimeoutExceeded,
    TransportError,
    raise_for_status,
)
from .types import QueryParams

__all__ = [
    "HttpClient",
    "HttpMethod",
    "Response",
    "RetryPolicy",
    "Timeouts",
]

logger = logging.getLogger("cdekx.http")

HttpMethod = Literal["GET", "POST", "PUT", "PATCH", "DELETE"]

#: Statuses worth retrying.
DEFAULT_RETRY_STATUSES: frozenset[int] = frozenset({408, 425, 429, 500, 502, 503, 504})
#: Methods that are safe to retry by default (idempotent ones).
DEFAULT_RETRY_METHODS: frozenset[str] = frozenset({"GET", "PUT", "PATCH", "DELETE", "HEAD"})


@dataclass(frozen=True, slots=True)
class Timeouts:
    """Request timeouts.

    The defaults are tuned for CDEK: most methods answer quickly, but printing
    forms and tariff calculations can take seconds.
    """

    connect: float = 5.0
    read: float = 30.0
    write: float = 10.0
    pool: float = 5.0

    def as_httpx(self) -> httpx.Timeout:
        """Convert to an ``httpx.Timeout``."""
        return httpx.Timeout(self.read, connect=self.connect, write=self.write, pool=self.pool)


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Retry policy with exponential backoff and jitter.

    Retried: network errors, read/connect timeouts and the listed HTTP statuses.
    When the response carries a ``Retry-After`` header, it is respected.

    ``max_attempts = 1`` disables retries entirely.
    """

    max_attempts: int = 3
    backoff_base: float = 0.5
    backoff_max: float = 8.0
    jitter: float = 0.2
    statuses: frozenset[int] = field(default_factory=lambda: DEFAULT_RETRY_STATUSES)
    methods: frozenset[str] = field(default_factory=lambda: DEFAULT_RETRY_METHODS)
    respect_retry_after: bool = True

    #: A no-retry policy — for tests and latency-sensitive scenarios.
    @classmethod
    def none(cls) -> RetryPolicy:
        """Return a policy that disables retries."""
        return cls(max_attempts=1)

    def allows_retry(self, attempt: int, method: str, status: int | None) -> bool:
        """Whether the request may be retried after attempt number ``attempt``."""
        if attempt >= self.max_attempts - 1:
            return False
        if method.upper() not in self.methods:
            return False
        return status is None or status in self.statuses

    def delay(self, attempt: int, retry_after: float | None = None) -> float:
        """Delay before attempt ``attempt + 1``, in seconds."""
        if retry_after is not None and self.respect_retry_after:
            return float(min(retry_after, self.backoff_max))
        raw: float = self.backoff_base * (2**attempt)
        capped: float = min(raw, self.backoff_max)
        return float(capped + random.uniform(0, self.jitter * capped))


@dataclass(slots=True)
class Response:
    """A normalised API response.

    The body is kept as bytes and is **not parsed eagerly**: for typed responses
    the endpoints hand the bytes to ``model_validate_json``/``validate_json``
    (pydantic's Rust parser), and ``json.loads`` runs only where a raw ``dict``
    or an error body needs parsing.
    """

    status_code: int
    content: bytes = b""
    headers: Mapping[str, str] = field(default_factory=dict)
    _json: Any = field(default=None, init=False, repr=False)
    _json_loaded: bool = field(default=False, init=False, repr=False)

    @property
    def json(self) -> Any:
        """Lazily parsed JSON response (``dict``/``list``), or text/``None``."""
        if not self._json_loaded:
            self._json = _try_parse_json(self.content)
            self._json_loaded = True
        return self._json


class HttpClient:
    """A thin wrapper over ``httpx.AsyncClient`` with authentication and retries.

    An instance keeps a single pooled connection for its whole lifetime, unlike
    the "new session per request" approach.
    """

    def __init__(
        self,
        *,
        base_url: str,
        auth: AuthProvider | None = None,
        client: httpx.AsyncClient | None = None,
        timeouts: Timeouts | None = None,
        retry: RetryPolicy | None = None,
        headers: Mapping[str, str] | None = None,
        limits: httpx.Limits | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._auth = auth
        self._timeouts = timeouts or Timeouts()
        self._retry = retry or RetryPolicy()
        self._owns_client = client is None
        if client is not None:
            self._client = client
        else:
            client_kwargs: dict[str, Any] = {
                "base_url": self._base_url,
                "timeout": self._timeouts.as_httpx(),
                "headers": {"User-Agent": _user_agent(), **dict(headers or {})},
            }
            if limits is not None:
                client_kwargs["limits"] = limits
            self._client = httpx.AsyncClient(**client_kwargs)
        self._closed = False

    # -- lifecycle ----------------------------------------------------------
    @property
    def base_url(self) -> str:
        """Base URL of the API."""
        return self._base_url

    @property
    def is_closed(self) -> bool:
        """Whether the transport is closed."""
        return self._closed

    async def aclose(self) -> None:
        """Close the connection (only if we created the client ourselves)."""
        if self._closed:
            return
        self._closed = True
        if self._owns_client:
            await self._client.aclose()

    # -- public API ---------------------------------------------------------
    async def request_raw(
        self,
        method: HttpMethod,
        path: str,
        *,
        params: QueryParams | None = None,
        json_body: Any = None,
        headers: Mapping[str, str] | None = None,
        auth: bool = True,
    ) -> Response:
        """Perform a request and return the **unparsed** response.

        This is the main path for typed responses: the bytes go straight into
        ``Model.model_validate_json()`` / ``TypeAdapter.validate_json()``, so the
        JSON is parsed exactly once, inside pydantic's Rust parser. ``json.loads``
        is never called here.

        The error body is parsed lazily — only inside :func:`raise_for_status`.

        Raises:
            ApiError: the API answered with a status >= 400.
            TransportError: the network is unreachable or a timeout expired.

        """
        response = await self._send(
            method, path, params=params, json_body=json_body, headers=headers, auth=auth
        )
        if response.status_code >= 400:
            raise_for_status(response.status_code, response.json, headers=response.headers)
        return response

    async def request_json(
        self,
        method: HttpMethod,
        path: str,
        *,
        params: QueryParams | None = None,
        json_body: Any = None,
        headers: Mapping[str, str] | None = None,
        auth: bool = True,
    ) -> Any:
        """Perform a request and return the parsed JSON (``dict``/``list``).

        For typed responses prefer :meth:`request_raw` + ``model_validate_json``:
        this method additionally pays for ``json.loads``. It is kept for escape
        hatches (``misc.raw``) and raw directory data.

        Raises:
            ApiError: the API answered with a status >= 400.
            TransportError: the network is unreachable or a timeout expired.

        """
        response = await self.request_raw(
            method, path, params=params, json_body=json_body, headers=headers, auth=auth
        )
        return response.json

    async def request_bytes(
        self,
        method: HttpMethod,
        path: str,
        *,
        params: QueryParams | None = None,
        json_body: Any = None,
        headers: Mapping[str, str] | None = None,
        auth: bool = True,
    ) -> bytes:
        """Perform a request and return the binary body (PDF, ZIP, XLSX)."""
        response = await self.request_raw(
            method, path, params=params, json_body=json_body, headers=headers, auth=auth
        )
        return response.content

    # -- internals ----------------------------------------------------------
    async def _send(
        self,
        method: HttpMethod,
        path: str,
        *,
        params: QueryParams | None,
        json_body: Any,
        headers: Mapping[str, str] | None,
        auth: bool,
    ) -> Response:
        if not path.startswith("/"):
            raise ValueError(f"path must start with '/': {path!r}")

        url = path if path.startswith(self._base_url) else self._base_url + path
        attempt = 0
        reauth_done = False

        while True:
            request_headers = dict(headers or {})
            if auth and self._auth is not None:
                token = await self._auth.get_token(self._client)
                if token:
                    request_headers["Authorization"] = f"Bearer {token}"

            try:
                raw = await self._client.request(
                    method,
                    url,
                    params=_clean_params(params),
                    json=json_body,
                    headers=request_headers,
                )
            except httpx.TimeoutException as exc:
                if self._retry.allows_retry(attempt, method, None):
                    delay = self._retry.delay(attempt)
                    logger.warning(
                        "timeout %s %s (attempt %d), retrying in %.2fs",
                        method,
                        url,
                        attempt + 1,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    attempt += 1
                    continue
                raise TimeoutExceeded(f"timeout on {method} {url}: {exc}", cause=exc) from exc
            except httpx.HTTPError as exc:
                if self._retry.allows_retry(attempt, method, None):
                    delay = self._retry.delay(attempt)
                    logger.warning(
                        "transport error %s %s: %s (attempt %d), retrying in %.2fs",
                        method,
                        url,
                        exc,
                        attempt + 1,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    attempt += 1
                    continue
                raise TransportError(
                    f"transport error on {method} {url}: {exc}", cause=exc
                ) from exc

            content = raw.content
            retry_after = _retry_after(raw.headers)

            if raw.status_code >= 400 and self._retry.allows_retry(
                attempt, method, raw.status_code
            ):
                delay = self._retry.delay(attempt, retry_after)
                logger.warning(
                    "retryable status %d for %s %s (attempt %d), retrying in %.2fs",
                    raw.status_code,
                    method,
                    url,
                    attempt + 1,
                    delay,
                )
                await asyncio.sleep(delay)
                attempt += 1
                continue

            if raw.status_code == 401 and auth and self._auth is not None and not reauth_done:
                # The token may have been revoked early — invalidate the cache
                # and retry the request exactly once (guards against an infinite
                # loop when the credentials are wrong).
                reauth_done = True
                await self._auth.invalidate()
                attempt += 1
                continue

            logger.debug("%s %s -> %d", method, url, raw.status_code)
            return Response(
                status_code=raw.status_code,
                content=content,
                headers=dict(raw.headers),
            )


def _clean_params(params: QueryParams | None) -> dict[str, Any] | None:
    """Drop ``None`` values and stringify the ones that need it."""
    if not params:
        return None
    cleaned: dict[str, Any] = {}
    for key, value in params.items():
        if value is None:
            continue
        if isinstance(value, bool):
            cleaned[key] = "true" if value else "false"
        elif isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
            cleaned[key] = ",".join(str(v) for v in value)
        else:
            cleaned[key] = value
    return cleaned or None


def _try_parse_json(content: bytes) -> Any:
    """Parse JSON, falling back to text (or ``None``) on failure."""
    if not content:
        return None
    try:
        import json

        return json.loads(content)
    except ValueError:
        return content.decode("utf-8", errors="replace")


def _retry_after(headers: Mapping[str, str]) -> float | None:
    raw = headers.get("retry-after") or headers.get("Retry-After")
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _user_agent() -> str:
    from ._version import __version__

    return f"cdekx/{__version__} httpx/{httpx.__version__}"


def iter_status_codes() -> Sequence[int]:
    """Return the list of retried statuses (internal helper for tests and docs)."""
    return sorted(DEFAULT_RETRY_STATUSES)
