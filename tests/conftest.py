"""Общие фикстуры: загрузка JSON-фикстур, respx-роутер и фабрика клиентов."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
import respx

from cdekx import CdekClient, Environment, RetryPolicy, Timeouts
from cdekx._auth import OAuth2ClientCredentials

if TYPE_CHECKING:
    from collections.abc import Callable

FIXTURES_DIR = Path(__file__).parent / "fixtures"

TEST_CLIENT_ID = "test-account"
TEST_CLIENT_SECRET = "test-secret"
BASE_URL = Environment.PRODUCTION.base_url
TOKEN_URL = f"{BASE_URL}/v2/oauth/token"
TOKEN_RESPONSE = {"access_token": "test-token", "expires_in": 1200, "token_type": "Bearer"}


def load_fixture(*parts: str) -> Any:
    """Загрузить JSON-фикстуру из ``tests/fixtures``.

    Example:
        >>> data = load_fixture("orders", "get.json")  # doctest: +SKIP
    """
    return json.loads(FIXTURES_DIR.joinpath(*parts).read_text(encoding="utf-8"))


@pytest.fixture
def token_route() -> Any:
    """respx-роутер с настроенным ответом OAuth-эндпоинта.

    Все маршруты API добавляются внутри теста через этот же роутер, поэтому
    вложенных ``respx.mock`` не возникает.
    """
    with respx.mock(base_url=BASE_URL, assert_all_called=False) as router:
        router.post("/v2/oauth/token").mock(
            return_value=respx.MockResponse(200, json=TOKEN_RESPONSE)
        )
        yield router


@pytest.fixture
def make_client(token_route: Any) -> Callable[..., CdekClient]:
    """Фабрика клиентов, работающих через ``token_route``.

    Ретраи отключены, чтобы тесты были детерминированными; для проверки
    политики повторов создавайте клиент с явным ``retry=``.
    """

    def factory(**kwargs: Any) -> CdekClient:
        kwargs.setdefault("retry", RetryPolicy.none())
        kwargs.setdefault("timeouts", Timeouts(connect=1.0, read=5.0))
        return CdekClient(TEST_CLIENT_ID, TEST_CLIENT_SECRET, **kwargs)

    return factory


@pytest.fixture
async def client(make_client: Callable[..., CdekClient]) -> Any:
    """Готовый клиент по умолчанию (транспорт закрывается автоматически)."""
    instance = make_client()
    try:
        yield instance
    finally:
        await instance.aclose()


@pytest.fixture
def oauth() -> OAuth2ClientCredentials:
    """Чистый OAuth-провайдер для unit-тестов (без запаса до истечения токена)."""
    return OAuth2ClientCredentials(
        client_id=TEST_CLIENT_ID,
        client_secret=TEST_CLIENT_SECRET,
        token_url=TOKEN_URL,
        expiry_margin=0,
    )
