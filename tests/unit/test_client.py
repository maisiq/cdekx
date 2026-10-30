"""Тесты клиента, конфигурации и жизненного цикла."""

from __future__ import annotations

import logging

import httpx
import pytest
import respx

from cdekx import (
    CdekClient,
    ClientConfig,
    ConfigError,
    Environment,
    RetryPolicy,
    Settings,
    StaticTokenProvider,
)
from cdekx.endpoints import OrdersEndpoint
from conftest import BASE_URL


def test_default_environment_is_production() -> None:
    client = CdekClient("id", "secret")
    assert client.environment is Environment.PRODUCTION
    assert client.base_url == "https://api.cdek.ru"


def test_sandbox_environment() -> None:
    client = CdekClient("id", "secret", environment=Environment.SANDBOX)
    assert client.base_url == "https://api.edu.cdek.ru"

    shortcut = CdekClient("id", "secret", sandbox=True)
    assert shortcut.base_url == "https://api.edu.cdek.ru"


def test_environment_accepts_string() -> None:
    client = CdekClient("id", "secret", environment="sandbox")
    assert client.environment is Environment.SANDBOX


def test_base_url_override() -> None:
    client = CdekClient("id", "secret", base_url="https://proxy.internal/cdek")
    assert client.base_url == "https://proxy.internal/cdek"


def test_invalid_base_url_raises_config_error() -> None:
    with pytest.raises(ConfigError):
        CdekClient("id", "secret", base_url="api.cdek.ru")


def test_missing_credentials_raise_config_error() -> None:
    with pytest.raises(ConfigError):
        CdekClient(None, None)  # type: ignore[arg-type]


def test_custom_auth_provider_is_used() -> None:
    client = CdekClient(auth=StaticTokenProvider(token="static"))
    assert client.base_url == BASE_URL


def test_resources_are_cached() -> None:
    client = CdekClient("id", "secret")
    assert client.orders is client.orders
    assert isinstance(client.orders, OrdersEndpoint)


def test_resource_aliases() -> None:
    client = CdekClient("id", "secret")
    assert client.tariffs is client.calculator
    assert client.points is client.delivery_points
    assert client.courier is client.intakes


def test_settings_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CDEKX_CLIENT_ID", "env-id")
    monkeypatch.setenv("CDEKX_CLIENT_SECRET", "env-secret")
    monkeypatch.setenv("CDEKX_ENVIRONMENT", "sandbox")
    monkeypatch.setenv("CDEKX_TIMEOUT", "12")

    client = CdekClient.from_env()

    assert client.base_url == "https://api.edu.cdek.ru"
    assert client.environment is Environment.SANDBOX


def test_settings_from_env_legacy_names(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CDEK_CLIENT_ID", "legacy-id")
    monkeypatch.setenv("CDEK_CLIENT_SECRET", "legacy-secret")
    monkeypatch.delenv("CDEKX_CLIENT_ID", raising=False)

    settings = Settings.from_env()

    assert settings.client_id == "legacy-id"
    assert settings.client_secret == "legacy-secret"


def test_from_env_without_credentials_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("CDEKX_CLIENT_ID", "CDEKX_CLIENT_SECRET", "CDEK_CLIENT_ID", "CDEK_CLIENT_SECRET"):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(ConfigError):
        CdekClient.from_env()


def test_from_env_forwards_client_kwargs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Аргументы конструктора не должны тонуть в ``Settings.from_env``."""
    monkeypatch.setenv("CDEKX_CLIENT_ID", "env-id")
    monkeypatch.setenv("CDEKX_CLIENT_SECRET", "env-secret")

    client = CdekClient.from_env(
        environment="sandbox", max_concurrency=20, extra_headers={"X-Trace": "1"}
    )

    assert client.environment is Environment.SANDBOX
    assert client._settings.config.max_concurrency == 20
    assert client._settings.config.extra_headers["X-Trace"] == "1"


async def test_from_env_accepts_custom_http_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """Рецепт ``from_env(http_client=...)`` действительно ходит через свой транспорт."""
    monkeypatch.setenv("CDEKX_CLIENT_ID", "env-id")
    monkeypatch.setenv("CDEKX_CLIENT_SECRET", "env-secret")

    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"entity": {"uuid": "1"}, "requests": []})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as raw:
        client = CdekClient.from_env(
            http_client=raw, auth=StaticTokenProvider(token="t"), retry=RetryPolicy.none()
        )
        order = await client.orders.get("1")

    assert order.uuid == "1"
    assert len(seen) == 1


def test_from_env_settings_overrides_still_win(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CDEKX_CLIENT_ID", "env-id")
    monkeypatch.setenv("CDEKX_CLIENT_SECRET", "env-secret")

    client = CdekClient.from_env(client_id="override-id")

    assert client._settings.client_id == "override-id"
    assert client._settings.client_secret == "env-secret"


def test_from_env_rejects_unknown_kwarg(monkeypatch: pytest.MonkeyPatch) -> None:
    """Опечатка в имени параметра должна падать явно, а не молча игнорироваться."""
    monkeypatch.setenv("CDEKX_CLIENT_ID", "env-id")
    monkeypatch.setenv("CDEKX_CLIENT_SECRET", "env-secret")

    with pytest.raises(TypeError, match="timeout"):
        CdekClient.from_env(timeout=5)


def test_explicit_credentials_win_over_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CDEKX_CLIENT_ID", "env-id")
    monkeypatch.setenv("CDEKX_CLIENT_SECRET", "env-secret")

    client = CdekClient("explicit-id", "explicit-secret")

    assert client._settings.client_id == "explicit-id"


def test_sandbox_factory_uses_public_test_keys() -> None:
    client = CdekClient.sandbox()
    assert client.environment is Environment.SANDBOX


def test_extra_headers_are_attached() -> None:
    client = CdekClient("id", "secret", extra_headers={"X-Partner": "acme"})
    assert client.http._client.headers["X-Partner"] == "acme"


def test_user_agent_contains_version() -> None:
    from cdekx import __version__

    client = CdekClient("id", "secret")
    assert client.http._client.headers["User-Agent"].startswith(f"cdekx/{__version__}")


async def test_async_context_manager_closes_transport() -> None:
    async with CdekClient("id", "secret") as client:
        assert not client.http.is_closed
    assert client.http.is_closed


async def test_aclose_is_idempotent() -> None:
    client = CdekClient("id", "secret")
    await client.aclose()
    await client.aclose()
    assert client.http.is_closed


async def test_client_can_accept_own_httpx_client() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"entity": {"uuid": "1"}, "requests": []})
    )
    async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as raw:
        client = CdekClient(
            auth=StaticTokenProvider(token="t"), http_client=raw, retry=RetryPolicy.none()
        )
        order = await client.orders.get("1")
        assert order.uuid == "1"

        # чужой клиент не закрывается нами
        await client.aclose()
        assert not raw.is_closed


def test_repr_is_informative() -> None:
    client = CdekClient("id", "secret", sandbox=True)
    assert "api.edu.cdek.ru" in repr(client)


def test_client_config_defaults() -> None:
    config = ClientConfig()
    assert config.environment is Environment.PRODUCTION
    assert config.request_timeout == 30.0
    assert config.resolve_base_url() == BASE_URL


def test_max_concurrency_sets_limits() -> None:
    client = CdekClient("id", "secret", max_concurrency=5)
    pool = client.http._client._transport._pool
    assert pool._max_connections == 5


def test_library_does_not_configure_logging_handlers() -> None:
    """Библиотека не должна навязывать обработчики логов приложению."""
    for name in ("cdekx", "cdekx.http", "cdekx.auth", "cdekx.webhooks"):
        logger = logging.getLogger(name)
        assert logger.handlers == []


def test_version_is_semver_like() -> None:
    from cdekx import __version__

    parts = __version__.split(".")
    assert len(parts) == 3
    assert all(p.isdigit() for p in parts)


async def test_end_to_end_flow_with_mocked_api() -> None:
    """Сквозной сценарий: токен → создание заказа → статус → чтение заказа."""
    with respx.mock(base_url=BASE_URL) as router:
        token_route = router.post("/v2/oauth/token")
        token_route.side_effect = [
            httpx.Response(200, json={"access_token": "tok-1", "expires_in": 1200})
        ]
        router.post("/v2/orders").mock(
            return_value=httpx.Response(200, json={"entity": {"uuid": "u-1"}})
        )
        router.get("/v2/orders/u-1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "entity": {
                        "uuid": "u-1",
                        "number": "ORDER-1",
                        "cdek_number": "111",
                        "is_return": False,
                        "is_reverse": False,
                        "is_client_return": False,
                        "tariff_code": 136,
                        "recipient": {"name": "x", "phones": [{"number": "+79001234567"}]},
                        "statuses": [],
                    },
                    "requests": [{"state": "SUCCESSFUL", "type": "CREATE"}],
                },
            )
        )

        async with CdekClient("id", "secret", retry=RetryPolicy.none()) as client:
            task = await client.orders.create(
                {
                    "number": "ORDER-1",
                    "type": 1,
                    "tariff_code": 136,
                    "recipient": {"name": "x", "phones": [{"number": "+79001234567"}]},
                    "packages": [{"number": "1", "weight": 1000}],
                }
            )
            envelope = await client.orders.wait(task.uuid, interval=0.001, timeout=1)
            order = await client.orders.get(task.uuid)

        assert envelope.state == "SUCCESSFUL"
        assert order.cdek_number == "111"
        assert token_route.call_count == 1  # токен получен один раз
