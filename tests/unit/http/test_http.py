"""Тесты HTTP-слоя: ретраи, обработка ошибок, нормализация параметров."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest
import respx

from cdekx import (
    ApiError,
    AuthError,
    NotFoundError,
    RateLimitError,
    RetryPolicy,
    ServerError,
    StaticTokenProvider,
    Timeouts,
    TransportError,
    ValidationError,
)
from cdekx._http import HttpClient
from conftest import BASE_URL


def make_http(**kwargs: Any) -> HttpClient:
    """Собрать HttpClient со статическим токеном."""
    kwargs.setdefault("auth", StaticTokenProvider(token="t"))
    kwargs.setdefault("timeouts", Timeouts(connect=1.0, read=2.0))
    return HttpClient(base_url=BASE_URL, **kwargs)


async def test_successful_json_request() -> None:
    with respx.mock(base_url=BASE_URL) as router:
        router.get("/v2/orders/1").mock(return_value=httpx.Response(200, json={"uuid": "1"}))
        http = make_http()
        data = await http.request_json("GET", "/v2/orders/1")
        await http.aclose()
    assert data == {"uuid": "1"}


async def test_authorization_header_is_attached() -> None:
    with respx.mock(base_url=BASE_URL) as router:
        route = router.get("/v2/orders/1").mock(return_value=httpx.Response(200, json={}))
        http = make_http()
        await http.request_json("GET", "/v2/orders/1")
        await http.aclose()
    assert route.calls.last.request.headers["Authorization"] == "Bearer t"


async def test_auth_can_be_skipped() -> None:
    with respx.mock(base_url=BASE_URL) as router:
        route = router.get("/public").mock(return_value=httpx.Response(200, json={}))
        http = make_http()
        await http.request_json("GET", "/public", auth=False)
        await http.aclose()
    assert "Authorization" not in route.calls.last.request.headers


async def test_4xx_raises_typed_error() -> None:
    with respx.mock(base_url=BASE_URL) as router:
        router.get("/v2/orders/1").mock(
            return_value=httpx.Response(
                404,
                json={"errors": [{"code": "not_found", "message": "Заказ не найден"}]},
                headers={"X-Request-Id": "req-42"},
            )
        )
        http = make_http()
        with pytest.raises(NotFoundError) as exc_info:
            await http.request_json("GET", "/v2/orders/1")
        await http.aclose()

    error = exc_info.value
    assert error.status_code == 404
    assert error.codes == ("not_found",)
    assert error.request_id == "req-42"
    assert error.has_code("not_found")
    assert "Заказ не найден" in str(error)


async def test_validation_error_body_is_parsed() -> None:
    with respx.mock(base_url=BASE_URL) as router:
        router.post("/v2/orders").mock(
            return_value=httpx.Response(
                400,
                json={
                    "errors": [
                        {
                            "code": "error_validate_im_dep_number_has_already_had_integration",
                            "message": "Заказ с таким номером уже существует",
                            "field": "number",
                        }
                    ]
                },
            )
        )
        http = make_http()
        with pytest.raises(ValidationError) as exc_info:
            await http.request_json("POST", "/v2/orders", json_body={})
        await http.aclose()

    assert exc_info.value.errors[0].field == "number"


async def test_text_error_body_is_preserved() -> None:
    with respx.mock(base_url=BASE_URL) as router:
        router.get("/v2/orders").mock(return_value=httpx.Response(500, text="Internal boom"))
        http = make_http()
        with pytest.raises(ServerError) as exc_info:
            await http.request_json("GET", "/v2/orders")
        await http.aclose()

    assert "Internal boom" in str(exc_info.value)
    assert exc_info.value.body == "Internal boom"


async def test_auth_error_on_401_after_single_retry() -> None:
    with respx.mock(base_url=BASE_URL) as router:
        route = router.get("/v2/orders/1").mock(return_value=httpx.Response(401, json={}))
        provider = StaticTokenProvider(token="t")
        http = HttpClient(base_url=BASE_URL, auth=provider, retry=RetryPolicy(max_attempts=2))
        with pytest.raises(AuthError):
            await http.request_json("GET", "/v2/orders/1")
        await http.aclose()
    # запрос повторён ровно один раз после инвалидации токена
    assert route.call_count == 2


async def test_retry_on_503_then_success() -> None:
    responses = [httpx.Response(503, json={}), httpx.Response(200, json={"ok": True})]
    with respx.mock(base_url=BASE_URL) as router:
        route = router.get("/v2/orders").mock(side_effect=responses)
        http = make_http(retry=RetryPolicy(max_attempts=3, backoff_base=0.001, jitter=0))
        data = await http.request_json("GET", "/v2/orders")
        await http.aclose()

    assert data == {"ok": True}
    assert route.call_count == 2


async def test_retry_respects_retry_after_header() -> None:
    policy = RetryPolicy(max_attempts=2, backoff_base=100.0, respect_retry_after=True)
    assert policy.delay(0, retry_after=0.01) == 0.01


async def test_post_is_not_retried_by_default() -> None:
    with respx.mock(base_url=BASE_URL) as router:
        route = router.post("/v2/orders").mock(return_value=httpx.Response(503, json={}))
        http = make_http(retry=RetryPolicy(max_attempts=3, backoff_base=0.001))
        with pytest.raises(ServerError):
            await http.request_json("POST", "/v2/orders", json_body={})
        await http.aclose()

    assert route.call_count == 1


async def test_retry_exhausted_raises_server_error() -> None:
    with respx.mock(base_url=BASE_URL) as router:
        route = router.get("/v2/orders").mock(return_value=httpx.Response(502, json={}))
        http = make_http(retry=RetryPolicy(max_attempts=3, backoff_base=0.001, jitter=0))
        with pytest.raises(ApiError) as exc_info:
            await http.request_json("GET", "/v2/orders")
        await http.aclose()

    assert route.call_count == 3
    assert exc_info.value.status_code == 502


async def test_rate_limit_error_exposes_retry_after() -> None:
    with respx.mock(base_url=BASE_URL) as router:
        router.get("/v2/orders").mock(
            return_value=httpx.Response(
                429, json={"message": "too many requests"}, headers={"Retry-After": "7"}
            )
        )
        http = make_http()
        with pytest.raises(RateLimitError) as exc_info:
            await http.request_json("GET", "/v2/orders")
        await http.aclose()

    assert exc_info.value.retry_after == 7.0


async def test_transport_error_on_connect_failure() -> None:
    with respx.mock(base_url=BASE_URL) as router:
        router.get("/v2/orders").mock(side_effect=httpx.ConnectError("boom"))
        http = make_http(retry=RetryPolicy.none())
        with pytest.raises(TransportError) as exc_info:
            await http.request_json("GET", "/v2/orders")
        await http.aclose()

    assert isinstance(exc_info.value.cause, httpx.ConnectError)


async def test_timeout_raises_timeout_exceeded() -> None:
    from cdekx import TimeoutExceeded

    with respx.mock(base_url=BASE_URL) as router:
        router.get("/v2/orders").mock(side_effect=httpx.ReadTimeout("slow"))
        http = make_http(retry=RetryPolicy.none())
        with pytest.raises(TimeoutExceeded):
            await http.request_json("GET", "/v2/orders")
        await http.aclose()


async def test_query_params_are_normalized() -> None:
    with respx.mock(base_url=BASE_URL) as router:
        route = router.get("/v2/deliverypoints").mock(return_value=httpx.Response(200, json=[]))
        http = make_http()
        await http.request_json(
            "GET",
            "/v2/deliverypoints",
            params={"city_code": 44, "have_cash": True, "code": None, "orders": ["a", "b"]},
        )
        await http.aclose()

    params = route.calls.last.request.url.params
    assert params["city_code"] == "44"
    assert params["have_cash"] == "true"
    assert "code" not in params  # None не попадает в query
    assert params["orders"] == "a,b"  # списки склеиваются через запятую


async def test_path_must_start_with_slash() -> None:
    http = make_http()
    with pytest.raises(ValueError, match="must start with"):
        await http.request_json("GET", "v2/orders")
    await http.aclose()


async def test_request_bytes_returns_raw_content() -> None:
    with respx.mock(base_url=BASE_URL) as router:
        router.get("/files/x.pdf").mock(
            return_value=httpx.Response(
                200, content=b"%PDF-1.7", headers={"Content-Type": "application/pdf"}
            )
        )
        http = make_http()
        data = await http.request_bytes("GET", "/files/x.pdf")
        await http.aclose()

    assert data == b"%PDF-1.7"


async def test_binary_endpoint_error_is_parsed() -> None:
    with respx.mock(base_url=BASE_URL) as router:
        router.get("/files/x.pdf").mock(
            return_value=httpx.Response(404, json={"errors": [{"code": "not_found"}]})
        )
        http = make_http()
        with pytest.raises(NotFoundError):
            await http.request_bytes("GET", "/files/x.pdf")
        await http.aclose()


async def test_aclose_is_idempotent() -> None:
    http = make_http()
    await http.aclose()
    await http.aclose()
    assert http.is_closed


def test_retry_policy_none_disables_retries() -> None:
    policy = RetryPolicy.none()
    assert policy.max_attempts == 1
    assert not policy.allows_retry(0, "GET", 503)


def test_retry_policy_delay_grows_exponentially() -> None:
    policy = RetryPolicy(backoff_base=0.5, backoff_max=8.0, jitter=0)
    assert policy.delay(0) == 0.5
    assert policy.delay(1) == 1.0
    assert policy.delay(10) == 8.0


async def test_concurrent_requests_share_single_client() -> None:
    """Проверяем, что пул соединений один: много конкурентных запросов — один клиент."""
    with respx.mock(base_url=BASE_URL) as router:
        route = router.get("/v2/orders/1").mock(
            return_value=httpx.Response(200, json={"uuid": "1"})
        )
        http = make_http()

        results = await asyncio.gather(
            *(http.request_json("GET", "/v2/orders/1") for _ in range(20))
        )
        await http.aclose()

        assert results == [{"uuid": "1"}] * 20
        assert route.call_count == 20
        assert len(router.calls) == 20
