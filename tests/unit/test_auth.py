"""Тесты OAuth2-провайдера: кэш токена, гонки, ошибки авторизации."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest
import respx

from cdekx import AuthError, ConfigError, StaticTokenProvider, TransportError
from cdekx._auth import OAuth2ClientCredentials
from conftest import BASE_URL, TOKEN_URL


async def test_token_is_requested_with_query_params(oauth: Any) -> None:
    with respx.mock(base_url=BASE_URL) as router:
        route = router.post("/v2/oauth/token").mock(
            return_value=httpx.Response(200, json={"access_token": "abc", "expires_in": 1200})
        )
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            token = await oauth.get_token(client)

    assert token == "abc"
    request = route.calls.last.request
    # Спецификация СДЭК: grant_type/client_id/client_secret — query-параметры,
    # а не форма в теле. Пустое тело — защита от регресса на data=.
    assert request.url.params["grant_type"] == "client_credentials"
    assert request.url.params["client_id"] == "test-account"
    assert request.url.params["client_secret"] == "test-secret"
    assert request.read() == b""


async def test_token_is_cached_between_calls(oauth: Any) -> None:
    with respx.mock(base_url=BASE_URL) as router:
        route = router.post("/v2/oauth/token").mock(
            return_value=httpx.Response(200, json={"access_token": "abc", "expires_in": 1200})
        )
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            first = await oauth.get_token(client)
            second = await oauth.get_token(client)

    assert first == second == "abc"
    assert route.call_count == 1


async def test_concurrent_requests_trigger_single_token_call(oauth: Any) -> None:
    """Гонка за токеном: N конкурентных запросов не должны плодить N обращений за токеном."""
    with respx.mock(base_url=BASE_URL) as router:
        route = router.post("/v2/oauth/token").mock(
            return_value=httpx.Response(200, json={"access_token": "abc", "expires_in": 1200})
        )
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            tokens = await asyncio.gather(*(oauth.get_token(client) for _ in range(25)))

    assert set(tokens) == {"abc"}
    assert route.call_count == 1


async def test_expired_token_is_refreshed(oauth: Any) -> None:
    oauth._expires_at = 0.0  # имитируем истёкший токен
    with respx.mock(base_url=BASE_URL) as router:
        route = router.post("/v2/oauth/token").mock(
            return_value=httpx.Response(200, json={"access_token": "abc", "expires_in": 1200})
        )
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            await oauth.get_token(client)
            oauth._expires_at = 0.0  # токен «протух»
            await oauth.get_token(client)

    assert route.call_count == 2


async def test_expiry_margin_creates_safety_buffer() -> None:
    """Токен считается истёкшим раньше фактического срока — без гонок в полёте."""
    provider = OAuth2ClientCredentials(
        client_id="a", client_secret="b", token_url=TOKEN_URL, expiry_margin=30
    )
    with respx.mock(base_url=BASE_URL) as router:
        router.post("/v2/oauth/token").mock(
            return_value=httpx.Response(200, json={"access_token": "abc", "expires_in": 40})
        )
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            await provider.get_token(client)
            # 40 - 30 = 10 секунд запаса, токен ещё жив
            assert provider.cached_token == "abc"

    provider.expiry_margin = 39
    provider._expires_at = 0.0
    with respx.mock(base_url=BASE_URL) as router:
        route = router.post("/v2/oauth/token").mock(
            return_value=httpx.Response(200, json={"access_token": "new", "expires_in": 40})
        )
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            await provider.get_token(client)
            await provider.get_token(client)
    assert route.call_count == 1


async def test_invalidate_forces_refresh(oauth: Any) -> None:
    with respx.mock(base_url=BASE_URL) as router:
        route = router.post("/v2/oauth/token").mock(
            return_value=httpx.Response(200, json={"access_token": "abc", "expires_in": 1200})
        )
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            await oauth.get_token(client)
            await oauth.invalidate()
            await oauth.get_token(client)

    assert route.call_count == 2
    assert oauth.cached_token == "abc"


async def test_invalid_credentials_raise_auth_error(oauth: Any) -> None:
    with respx.mock(base_url=BASE_URL) as router:
        router.post("/v2/oauth/token").mock(
            return_value=httpx.Response(401, json={"message": "Неверный логин или пароль"})
        )
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            with pytest.raises(AuthError) as exc_info:
                await oauth.get_token(client)

    assert exc_info.value.status_code == 401
    assert "Неверный логин" in str(exc_info.value)


async def test_oauth_error_message_fallback(oauth: Any) -> None:
    with respx.mock(base_url=BASE_URL) as router:
        router.post("/v2/oauth/token").mock(return_value=httpx.Response(500, text="oops"))
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            with pytest.raises(AuthError) as exc_info:
                await oauth.get_token(client)

    assert "oops" in str(exc_info.value)


async def test_network_failure_raises_transport_error(oauth: Any) -> None:
    with respx.mock(base_url=BASE_URL) as router:
        router.post("/v2/oauth/token").mock(side_effect=httpx.ConnectError("no network"))
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            with pytest.raises(TransportError):
                await oauth.get_token(client)


async def test_on_token_hook_is_called(oauth: Any) -> None:
    captured: list[tuple[str, float]] = []

    async def hook(token: str, expires_in: float) -> None:
        captured.append((token, expires_in))

    oauth.on_token = hook
    with respx.mock(base_url=BASE_URL) as router:
        router.post("/v2/oauth/token").mock(
            return_value=httpx.Response(200, json={"access_token": "abc", "expires_in": 600})
        )
        async with httpx.AsyncClient(base_url=BASE_URL) as client:
            await oauth.get_token(client)

    assert captured == [("abc", 600.0)]


def test_missing_credentials_raise_config_error() -> None:
    with pytest.raises(ConfigError):
        OAuth2ClientCredentials(client_id="", client_secret="")


def test_token_url_defaults_to_oauth_endpoint() -> None:
    provider = OAuth2ClientCredentials(client_id="a", client_secret="b")
    assert provider.token_url == "/v2/oauth/token"


async def test_static_token_provider() -> None:
    provider = StaticTokenProvider(token="static")
    async with httpx.AsyncClient() as client:
        assert await provider.get_token(client) == "static"
    await provider.invalidate()
    async with httpx.AsyncClient() as client:
        assert await provider.get_token(client) == "static"


def test_token_url_constant_points_to_oauth_path() -> None:
    from cdekx._auth import TOKEN_PATH

    assert TOKEN_PATH == "/v2/oauth/token"
    assert TOKEN_URL.endswith(TOKEN_PATH)
