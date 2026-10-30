"""Client configuration: environment, timeouts, retries, environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from ._auth import AuthProvider
from .exceptions import ConfigError
from .types import Environment, coerce_environment

__all__ = ["ENV_PREFIX", "ClientConfig", "Settings"]

#: Prefix of the environment variables that supply default settings.
ENV_PREFIX = "CDEKX_"

#: Environment variables holding CDEK credentials (compatible with other integrations).
_ID_VARS = ("CDEKX_CLIENT_ID", "CDEK_CLIENT_ID")
_SECRET_VARS = ("CDEKX_CLIENT_SECRET", "CDEK_CLIENT_SECRET")


@dataclass(frozen=True, slots=True)
class ClientConfig:
    """Immutable configuration for :class:`cdekx.CdekClient`."""

    environment: Environment | str = Environment.PRODUCTION
    #: Overrides ``environment`` (useful for local setups and proxies).
    base_url: str | None = None
    #: Overall time budget for a single operation, in seconds. ``None`` means no limit.
    request_timeout: float | None = 30.0
    #: Maximum number of concurrent API requests. CDEK guarantees ~200 RPS per contract.
    max_concurrency: int | None = None
    #: Value for the ``Accept-Language`` header.
    language: str | None = None
    #: Extra headers (tracing, partner tags).
    extra_headers: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Normalise ``environment`` to an :class:`Environment`."""
        if not isinstance(self.environment, Environment):
            object.__setattr__(
                self, "environment", coerce_environment(self.environment, Environment.PRODUCTION)
            )

    def resolve_base_url(self) -> str:
        """Return the resolved base URL."""
        environment = coerce_environment(self.environment, Environment.PRODUCTION)
        url = self.base_url or environment.base_url
        if not url.startswith(("http://", "https://")):
            raise ConfigError(f"invalid base_url: {url!r}")
        return url.rstrip("/")


@dataclass(frozen=True, slots=True)
class Settings:
    """Credentials and configuration assembled from arguments and the environment."""

    client_id: str | None = None
    client_secret: str | None = None
    config: ClientConfig = field(default_factory=ClientConfig)

    @classmethod
    def from_env(cls, *, prefix: str = ENV_PREFIX, **overrides: object) -> Settings:
        """Build the settings from environment variables.

        Recognized env vars:
            ``CDEKX_CLIENT_ID`` / ``CDEK_CLIENT_ID`` — the account identifier;
            ``CDEKX_CLIENT_SECRET`` / ``CDEK_CLIENT_SECRET`` — the password;
            ``CDEKX_ENVIRONMENT`` — ``production`` or ``sandbox``;
            ``CDEKX_BASE_URL`` — overrides the base URL;
            ``CDEKX_TIMEOUT`` — request timeout in seconds.

        Args:
            prefix: prefix of the environment variables to read.
            **overrides: values with the highest priority.

        """
        env_client_id = _first_env(_ID_VARS)
        env_client_secret = _first_env(_SECRET_VARS)

        environment_raw = os.getenv(f"{prefix}ENVIRONMENT") or os.getenv("CDEK_ENVIRONMENT")
        environment = coerce_environment(environment_raw, Environment.PRODUCTION)

        base_url = os.getenv(f"{prefix}BASE_URL") or os.getenv("CDEK_BASE_URL")

        timeout_raw = os.getenv(f"{prefix}TIMEOUT")
        timeout = float(timeout_raw) if timeout_raw else 30.0

        config = ClientConfig(
            environment=environment,
            base_url=base_url,
            request_timeout=timeout,
        )

        values: dict[str, object] = {
            "client_id": env_client_id,
            "client_secret": env_client_secret,
            "config": config,
        }
        values.update({k: v for k, v in overrides.items() if v is not None})
        return cls(**values)  # type: ignore[arg-type]

    def require_credentials(self) -> tuple[str, str]:
        """Return ``(client_id, client_secret)`` or raise :class:`ConfigError`."""
        if not self.client_id or not self.client_secret:
            raise ConfigError(
                "CDEK credentials not found. Pass client_id/client_secret to the "
                "CdekClient constructor or set the CDEKX_CLIENT_ID and "
                "CDEKX_CLIENT_SECRET environment variables."
            )
        return self.client_id, self.client_secret


def _first_env(names: tuple[str, ...]) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return None


def build_auth(settings: Settings, auth: AuthProvider | None) -> AuthProvider | None:
    """Build the auth provider: explicit one, then settings, then ``None``."""
    if auth is not None:
        return auth
    if settings.client_id and settings.client_secret:
        from ._auth import OAuth2ClientCredentials

        return OAuth2ClientCredentials(
            client_id=settings.client_id,
            client_secret=settings.client_secret,
            token_url=f"{settings.config.resolve_base_url()}/v2/oauth/token",
        )
    return None
