"""cdekx — a modern asynchronous client for the CDEK API (v2).

Quick start::

    import asyncio
    from cdekx import CdekClient
    from cdekx.models import CalculatorLocation, CalculatorPackage, TariffRequest


    async def main() -> None:
        async with CdekClient.sandbox() as client:
            tariff = await client.calculator.tariff(
                TariffRequest(
                    tariff_code=136,
                    from_location=CalculatorLocation(code=44),   # Moscow
                    to_location=CalculatorLocation(code=270),    # Yekaterinburg
                    packages=[CalculatorPackage(weight=1000, length=30, width=20, height=10)],
                )
            )
            print(tariff.delivery_sum, tariff.period_min, tariff.period_max)


    asyncio.run(main())

Public API:
    * :class:`CdekClient` — the entry point;
    * ``cdekx.models`` — pydantic models for requests and responses;
    * ``cdekx.types.enums`` — enumerations (tariffs, statuses, services, webhooks);
    * ``cdekx.exceptions`` — the error hierarchy;
    * ``cdekx.webhooks`` — receiving and parsing inbound webhooks.
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any

from ._auth import AuthProvider, OAuth2ClientCredentials, StaticTokenProvider
from ._http import HttpClient, HttpMethod, Response, RetryPolicy, Timeouts
from ._version import __version__
from .client import CdekClient
from .config import ENV_PREFIX, ClientConfig, Settings
from .exceptions import (
    ApiError,
    AuthError,
    CdekxError,
    ConfigError,
    NotFoundError,
    RateLimitError,
    ServerError,
    TimeoutExceeded,
    TransportError,
    ValidationError,
)
from .pagination import Paginator
from .types import ApiErrorDetail, Environment, Page

if TYPE_CHECKING:
    from . import endpoints, models, types, webhooks

__author__ = "maisiq"
__email__ = "maisiq@users.noreply.github.com"

__all__ = [
    "ENV_PREFIX",
    "ApiError",
    "ApiErrorDetail",
    "AuthError",
    "AuthProvider",
    # the client
    "CdekClient",
    # exceptions
    "CdekxError",
    "ClientConfig",
    "ConfigError",
    "Environment",
    # HTTP layer (for custom transports and tests)
    "HttpClient",
    "HttpMethod",
    "NotFoundError",
    "OAuth2ClientCredentials",
    "Page",
    # pagination
    "Paginator",
    "RateLimitError",
    "Response",
    "RetryPolicy",
    "ServerError",
    "Settings",
    "StaticTokenProvider",
    "TimeoutExceeded",
    "Timeouts",
    "TransportError",
    "ValidationError",
    "__version__",
    "endpoints",
    # lazy submodules
    "models",
    "types",
    "webhooks",
]

#: Submodules imported on first access (PEP 562).
_LAZY_SUBMODULES = frozenset({"models", "endpoints", "types", "webhooks"})


def __getattr__(name: str) -> Any:
    """Import submodules lazily: ``cdekx.models`` is loaded on demand."""
    if name in _LAZY_SUBMODULES:
        module = importlib.import_module(f"{__name__}.{name}")
        globals()[name] = module
        return module
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    """Completion hints include the lazy submodules."""
    return sorted({*globals(), *_LAZY_SUBMODULES})
