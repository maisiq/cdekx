"""Entry point: :class:`CdekClient`."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

import httpx

from ._auth import AuthProvider, OAuth2ClientCredentials
from ._http import HttpClient, RetryPolicy, Timeouts
from .config import ClientConfig, Settings, build_auth
from .endpoints import (
    CalculatorEndpoint,
    DeliveryAgreementEndpoint,
    DeliveryPointsEndpoint,
    IntakesEndpoint,
    LocationsEndpoint,
    MiscEndpoint,
    OrdersEndpoint,
    PrintEndpoint,
    WebhooksEndpoint,
)
from .exceptions import ConfigError, NotFoundError
from .types import Environment, coerce_environment

__all__ = ["CdekClient"]

logger = logging.getLogger("cdekx")

EndpointT = TypeVar("EndpointT")

#: Arguments of :meth:`CdekClient.from_env` that belong to :class:`Settings`;
#: everything else is passed to the client constructor.
_SETTINGS_KEYS = frozenset({"client_id", "client_secret", "config", "prefix"})


class CdekClient:
    """Asynchronous CDEK API client (v2).

    The client owns the HTTP transport and authorisation; the methods are
    grouped by resources (``orders``, ``calculator``, ``locations``, etc.).

    Example:
        >>> async with CdekClient.from_env() as client:  # doctest: +SKIP
        ...     tariff = await client.calculator.tariff(TariffRequest(...))  # doctest: +SKIP

    Manual initialisation::

        client = CdekClient(client_id="...", client_secret="...", environment=Environment.SANDBOX)
        ...
        await client.aclose()

    Note:
        An instance is designed for a long lifetime and concurrent requests —
        do not create a client per request.

    """

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        *,
        environment: Environment | str | None = None,
        base_url: str | None = None,
        sandbox: bool = False,
        auth: AuthProvider | None = None,
        config: ClientConfig | None = None,
        http_client: httpx.AsyncClient | None = None,
        timeouts: Timeouts | None = None,
        retry: RetryPolicy | None = None,
        max_concurrency: int | None = None,
        extra_headers: dict[str, str] | None = None,
        settings: Settings | None = None,
    ) -> None:
        """Build the client: authorisation, transport, resources.

        Args:
            client_id: CDEK account identifier (the "Integration" section of the
                personal account).
            client_secret: account password.
            environment: ``production`` (api.cdek.ru) or ``sandbox`` (api.edu.cdek.ru).
            base_url: override of the base URL (a proxy, a local stand).
            sandbox: a shortcut for ``environment=Environment.SANDBOX``.
            auth: your own authorisation provider (tokens from Redis, etc.).
            config: a ready :class:`ClientConfig` (overrides environment/base_url).
            http_client: your own ``httpx.AsyncClient`` (e.g. with a custom transport).
            timeouts: request timeouts.
            retry: retry policy (``RetryPolicy.none()`` disables it).
            max_concurrency: limit on the number of concurrent requests.
            extra_headers: additional headers for all requests.
            settings: settings collected from the environment (:meth:`from_env`).

        """
        # Settings priority: an explicit `config` > constructor arguments
        # > `settings` (e.g. from from_env) > default values.
        if settings is None:
            settings = Settings(client_id=client_id, client_secret=client_secret)
        elif client_id or client_secret:
            settings = Settings(
                client_id=client_id or settings.client_id,
                client_secret=client_secret or settings.client_secret,
                config=settings.config,
            )

        base_cfg = config or settings.config or ClientConfig()
        resolved_env = (
            Environment.SANDBOX if sandbox else Environment(environment or base_cfg.environment)
        )
        self._settings = Settings(
            client_id=settings.client_id,
            client_secret=settings.client_secret,
            config=ClientConfig(
                environment=resolved_env,
                base_url=base_url or base_cfg.base_url,
                request_timeout=base_cfg.request_timeout,
                max_concurrency=max_concurrency or base_cfg.max_concurrency,
                language=base_cfg.language,
                extra_headers={**base_cfg.extra_headers, **(extra_headers or {})},
            ),
        )

        cfg = self._settings.config
        self._auth = build_auth(self._settings, auth)
        if self._auth is None:
            raise ConfigError(
                "Failed to configure authorisation: pass client_id/client_secret, "
                "the CDEKX_CLIENT_ID/CDEKX_CLIENT_SECRET environment variables "
                "or your own auth provider."
            )

        concurrency = cfg.max_concurrency
        limits = (
            httpx.Limits(max_connections=concurrency, max_keepalive_connections=concurrency)
            if concurrency
            else None
        )

        headers = dict(cfg.extra_headers)
        if cfg.language:
            headers.setdefault("Accept-Language", cfg.language)

        self._http = HttpClient(
            base_url=cfg.resolve_base_url(),
            auth=self._auth,
            client=http_client,
            timeouts=timeouts or Timeouts(read=cfg.request_timeout or 30.0),
            retry=retry or RetryPolicy(),
            headers=headers,
            limits=limits,
        )

        self._semaphore = asyncio.Semaphore(concurrency) if concurrency else None

        # resources are created lazily and cached
        self._orders: OrdersEndpoint | None = None
        self._calculator: CalculatorEndpoint | None = None
        self._locations: LocationsEndpoint | None = None
        self._delivery_points: DeliveryPointsEndpoint | None = None
        self._intakes: IntakesEndpoint | None = None
        self._print: PrintEndpoint | None = None
        self._webhooks: WebhooksEndpoint | None = None
        self._delivery_agreement: DeliveryAgreementEndpoint | None = None
        self._misc: MiscEndpoint | None = None

        # -- constructors -------------------------------------------------------

    @classmethod
    def from_env(cls, **overrides: Any) -> CdekClient:
        """Create a client from environment variables.

        ``CDEKX_CLIENT_ID``/``CDEK_CLIENT_ID``,
        ``CDEKX_CLIENT_SECRET``/``CDEK_CLIENT_SECRET``,
        ``CDEKX_ENVIRONMENT``, ``CDEKX_BASE_URL``, ``CDEKX_TIMEOUT`` are used.

        Args:
            **overrides: ``client_id``, ``client_secret``, ``config`` and ``prefix``
                override the values from the environment; the other arguments
                (``environment``, ``max_concurrency``, ``http_client``,
                ``timeouts``, ``retry``, ``extra_headers``, ``auth``, ``sandbox``)
                are passed to the :class:`CdekClient` constructor.

        Example:
            >>> client = CdekClient.from_env(max_concurrency=20)  # doctest: +SKIP

        """
        settings_overrides = {k: v for k, v in overrides.items() if k in _SETTINGS_KEYS}
        client_overrides = {k: v for k, v in overrides.items() if k not in _SETTINGS_KEYS}
        settings = Settings.from_env(**settings_overrides)
        settings.require_credentials()
        return cls(settings=settings, **client_overrides)

    @classmethod
    def sandbox(
        cls, client_id: str | None = None, client_secret: str | None = None, **kwargs: Any
    ) -> CdekClient:
        """Create a client for the ``api.edu.cdek.ru`` sandbox.

        Without arguments the publicly available CDEK test credentials are used
        (see apidoc.cdek.ru → "Connecting to the service"): orders in this
        environment are not delivered.
        """
        # Not a secret: these keys are published by CDEK in apidoc.cdek.ru as shared
        # keys for the sandbox; the official examples and third-party clients use
        # them too. Secret scanners may complain about them — that is expected.
        cid = client_id or "wqGwiQx0gg8mLtiEKsUinjVSICCjtTEP"
        secret = client_secret or "RmAmgvSgSl1yirlz9QupbzOJVqhCxcP5"
        kwargs.setdefault("environment", Environment.SANDBOX)
        return cls(cid, secret, **kwargs)

        # -- resources ----------------------------------------------------------

    @property
    def orders(self) -> OrdersEndpoint:
        """Orders: creation, modification, statuses, search."""
        return self._resource("_orders", OrdersEndpoint)

    @property
    def calculator(self) -> CalculatorEndpoint:
        """Calculation of the delivery cost and terms."""
        return self._resource("_calculator", CalculatorEndpoint)

    @property
    def locations(self) -> LocationsEndpoint:
        """Directories of cities and regions."""
        return self._resource("_locations", LocationsEndpoint)

    @property
    def delivery_points(self) -> DeliveryPointsEndpoint:
        """Offices, pickup points and parcel lockers."""
        return self._resource("_delivery_points", DeliveryPointsEndpoint)

    @property
    def intakes(self) -> IntakesEndpoint:
        """Courier pickup requests (intakes)."""
        return self._resource("_intakes", IntakesEndpoint)

    @property
    def printing(self) -> PrintEndpoint:
        """Print forms: waybills, barcodes, order copies."""
        return self._resource("_print", PrintEndpoint)

    @property
    def webhooks(self) -> WebhooksEndpoint:
        """Webhook subscriptions."""
        return self._resource("_webhooks", WebhooksEndpoint)

    @property
    def delivery_agreement(self) -> DeliveryAgreementEndpoint:
        """Delivery agreement: intervals and date coordination."""
        return self._resource("_delivery_agreement", DeliveryAgreementEndpoint)

    @property
    def misc(self) -> MiscEndpoint:
        """Reverse, receipts, prealerts, document photos and the ``raw()`` escape hatch."""
        return self._resource("_misc", MiscEndpoint)

        # --- convenient resource aliases ---------------------------------------

    @property
    def tariffs(self) -> CalculatorEndpoint:
        """Alias of :attr:`calculator`."""
        return self.calculator

    @property
    def points(self) -> DeliveryPointsEndpoint:
        """Alias of :attr:`delivery_points`."""
        return self.delivery_points

    @property
    def courier(self) -> IntakesEndpoint:
        """Alias of :attr:`intakes` — the historical name of the section."""
        return self.intakes

    @property
    def agreements(self) -> DeliveryAgreementEndpoint:
        """Alias of :attr:`delivery_agreement`."""
        return self.delivery_agreement

    @property
    def handbook(self) -> MiscEndpoint:
        """Alias of :attr:`misc` (for compatibility with early cdekx versions)."""
        return self.misc

    @property
    def http(self) -> HttpClient:
        """Access to the HTTP layer (debugging, non-standard requests)."""
        return self._http

    @property
    def environment(self) -> Environment:
        """The current API environment."""
        return coerce_environment(self._settings.config.environment, Environment.PRODUCTION)

    @property
    def base_url(self) -> str:
        """The base API URL."""
        return self._http.base_url

        # -- internals ----------------------------------------------------------

    async def wait_order(self, uuid: str, *, timeout: float = 60.0, interval: float = 2.0) -> Any:
        """Wait for the order processing and return it.

        CDEK answers ``POST /v2/orders`` with code 202 and the ``ACCEPTED``
        state: that is the state of the **request**, not of the order. The usual
        processing time is 200–500 ms, up to 30–60 s under peak load.

        Returns:
            :class:`cdekx.models.Order` after the request turns ``SUCCESSFUL``.

        Raises:
            ApiError: the order was rejected during processing (``INVALID``) —
                ``exc.errors`` will contain codes like ``v2_order_invalid``.
            TimeoutExceeded: the order stayed in processing.

        """
        envelope = await self.orders.wait(uuid, timeout=timeout, interval=interval)
        if envelope.entity is None:
            raise NotFoundError(f"order {uuid} processed without entity", status_code=404)
        return envelope.entity

    async def with_concurrency_limit(self, coro: Awaitable[Any]) -> Any:
        """Run a coroutine respecting ``max_concurrency`` (if it is set)."""
        if self._semaphore is None:
            return await coro
        async with self._semaphore:
            return await coro

    # -- lifecycle ----------------------------------------------------------
    async def aclose(self) -> None:
        """Close the transport. Called automatically in ``async with``."""
        await self._http.aclose()

    async def __aenter__(self) -> CdekClient:
        """Enter the context (``async with CdekClient(...) as client``)."""
        return self

    async def __aexit__(self, *_exc: object) -> None:
        """Exit the context and close the transport."""
        await self.aclose()

    # -- internals ----------------------------------------------------------
    def _resource(self, attr: str, factory: Callable[[HttpClient], EndpointT]) -> EndpointT:
        """Lazily create and cache a resource endpoint."""
        cached: EndpointT | None = getattr(self, attr)
        if cached is None:
            cached = factory(self._http)
            setattr(self, attr, cached)
        return cached

    def __repr__(self) -> str:  # pragma: no cover - debug output
        """Debug representation of the client."""
        return f"CdekClient(base_url={self.base_url!r}, environment={self.environment.value!r})"


def _ensure_auth(client: CdekClient) -> OAuth2ClientCredentials | None:
    """Return the OAuth provider of the client (a helper for tests)."""
    auth = client._auth
    return auth if isinstance(auth, OAuth2ClientCredentials) else None
