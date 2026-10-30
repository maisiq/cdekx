"""OAuth 2.0 (client credentials) for the CDEK API.

``POST /v2/oauth/token``; ``grant_type/client_id/client_secret`` are passed as
**query parameters** (according to the CDEK OpenAPI specification all three are
declared ``in: query`` — the gateway does not accept them in a form body).
Response::

    {"access_token": "...", "expires_in": 1200, "token_type": "Bearer"}

Implementation notes:

* the token is cached in process memory and reused until it expires;
* the ``expiry_margin`` removes the "token expired mid-request" race;
* concurrent requests do not stampede: the refresh is guarded by ``asyncio.Lock``;
* for several clients (multiple contracts or legal entities) create one
  :class:`CdekClient` each — the provider does not share tokens between them.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

import httpx

from .exceptions import AuthError, ConfigError, TransportError

__all__ = [
    "AuthProvider",
    "OAuth2ClientCredentials",
    "StaticTokenProvider",
]

logger = logging.getLogger("cdekx.auth")

TOKEN_PATH = "/v2/oauth/token"


@runtime_checkable
class AuthProvider(Protocol):
    """Source of access tokens."""

    async def get_token(self, client: httpx.AsyncClient) -> str | None:
        """Return a valid token (or ``None`` when no authentication is needed)."""
        ...

    async def invalidate(self) -> None:
        """Drop the cache — for example after a 401 response."""
        ...


@dataclass(slots=True)
class StaticTokenProvider:
    """Provider with a token known in advance.

    Useful for tests, proxying services, and cases where the token is issued by
    another system.
    """

    token: str

    async def get_token(self, client: httpx.AsyncClient) -> str | None:
        """Return the fixed token."""
        return self.token

    async def invalidate(self) -> None:
        """Do nothing: the token is immutable."""


@dataclass(slots=True)
class OAuth2ClientCredentials:
    """OAuth2 client with an in-memory token cache."""

    client_id: str
    client_secret: str
    token_url: str = TOKEN_PATH
    #: Safety margin before the token expires, in seconds.
    expiry_margin: float = 30.0
    #: Timeout of the token request, in seconds.
    timeout: float = 10.0
    #: Hook for an external token cache (Redis and similar):
    #: ``(token, expires_in) -> Awaitable[None]``.
    on_token: Callable[[str, float], Awaitable[None]] | None = None

    _token: str | None = field(default=None, init=False, repr=False)
    _expires_at: float = field(default=0.0, init=False, repr=False)
    _lock: asyncio.Lock | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.client_id or not self.client_secret:
            raise ConfigError(
                "client_id and client_secret are required. "
                "Get them from your CDEK personal account (the Integration section) "
                "or set the CDEK_CLIENT_ID / CDEK_CLIENT_SECRET environment variables."
            )
        self._lock = asyncio.Lock()

    @property
    def cached_token(self) -> str | None:
        """The currently cached token (or ``None``)."""
        return self._token if time.monotonic() < self._expires_at else None

    async def get_token(self, client: httpx.AsyncClient) -> str | None:
        """Return a valid token, fetching a new one when necessary."""
        cached = self.cached_token
        if cached is not None:
            return cached

        assert self._lock is not None
        async with self._lock:
            cached = self.cached_token
            if cached is not None:  # someone else refreshed the token while we waited
                return cached
            return await self._fetch_token(client)

    async def invalidate(self) -> None:
        """Drop the cached token."""
        self._token = None
        self._expires_at = 0.0

    async def _fetch_token(self, client: httpx.AsyncClient) -> str:
        logger.debug("requesting new access token from %s", self.token_url)
        try:
            response = await client.post(
                self.token_url,
                # The specification requires query parameters, not a form body:
                # grant_type/client_id/client_secret are declared `in: query`.
                params={
                    "grant_type": "client_credentials",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
                timeout=self.timeout,
            )
        except httpx.TimeoutException as exc:
            raise TransportError(f"timeout while requesting OAuth token: {exc}", cause=exc) from exc
        except httpx.HTTPError as exc:
            raise TransportError(f"OAuth token request failed: {exc}", cause=exc) from exc

        payload: Any = _safe_json(response)

        if (
            response.status_code >= 400
            or not isinstance(payload, dict)
            or "access_token" not in payload
        ):
            raise AuthError(
                _oauth_error_message(payload),
                status_code=response.status_code,
                errors=(),
                body=payload,
            )

        token = str(payload["access_token"])
        expires_in = float(payload.get("expires_in") or 1200)
        self._token = token
        self._expires_at = time.monotonic() + max(expires_in - self.expiry_margin, 1.0)
        logger.debug("access token acquired, expires_in=%s", expires_in)

        if self.on_token is not None:
            await self.on_token(token, expires_in)
        return token


def _safe_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return response.text


def _oauth_error_message(payload: Any) -> str:
    if isinstance(payload, dict):
        for key in ("message", "error_description", "error"):
            if payload.get(key):
                return str(payload[key])
    if isinstance(payload, str) and payload.strip():
        return payload.strip()[:300]
    return "failed to obtain CDEK access token"
