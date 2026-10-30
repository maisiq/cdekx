"""Тесты эндпоинта заказов (пути и конверты — по OpenAPI-спецификации СДЭК)."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from cdekx import ApiError, CdekClient, NotFoundError, TimeoutExceeded, ValidationError
from cdekx.models import Contact, Location, OrderCreate, Package
from conftest import load_fixture


def sample_order() -> OrderCreate:
    """Минимально валидный заказ для тестов."""
    return OrderCreate(
        type=1,
        number="ORDER-0001",
        tariff_code=136,
        from_location=Location(code=44, address="ул. Тестовая, 1"),
        to_location=Location(code=270, address="ул. Проверочная, 2"),
        sender=Contact(name="Иван Петров", phones=["+79001234567"]),
        recipient=Contact(name="Мария Смирнова", phones=["+79007654321"]),
        packages=[Package(number="PKG-1", weight=1500)],
    )


async def test_create_order_returns_202_envelope(token_route: Any, make_client: Any) -> None:
    create_route = token_route.post("/v2/orders").mock(
        return_value=httpx.Response(202, json=load_fixture("orders", "create.json"))
    )
    client: CdekClient = make_client()

    task = await client.orders.create(sample_order())

    assert task.uuid == "8dea00e3-9aab-4d8e-887c-ef2aaa546456"
    assert task.state == "ACCEPTED"
    assert task.last_request is not None
    assert task.last_request.type == "CREATE"
    assert create_route.calls.last.request.headers["Authorization"] == "Bearer test-token"


async def test_create_order_sends_phones_as_objects(token_route: Any, make_client: Any) -> None:
    """Главная деталь API v2: phones — список объектов {number, additional}."""
    create_route = token_route.post("/v2/orders").mock(
        return_value=httpx.Response(202, json=load_fixture("orders", "create.json"))
    )
    client = make_client()

    await client.orders.create(sample_order())

    body = create_route.calls.last.request.read().decode()
    assert '"phones": [{"number": "+79001234567"}]' in body.replace("  ", " ") or (
        '"phones":[{"number":"+79001234567"}]' in body.replace(" ", "")
    )
    assert '"comment"' not in body.replace(" ", "")  # None не сериализуется


async def test_get_order_unwraps_entity(token_route: Any, make_client: Any) -> None:
    token_route.get("/v2/orders/u1").mock(
        return_value=httpx.Response(200, json=load_fixture("orders", "get.json"))
    )
    client = make_client()

    order = await client.orders.get("u1")

    assert order.cdek_number == "1234567890"
    assert order.status_code == "IN_TRANSIT"
    assert order.barcodes == ["00001234567"]


async def test_get_order_envelope_exposes_requests_and_related(
    token_route: Any, make_client: Any
) -> None:
    """Ответ содержит requests и related_entities — их нельзя терять."""
    token_route.get("/v2/orders/u1").mock(
        return_value=httpx.Response(200, json=load_fixture("orders", "get.json"))
    )
    client = make_client()

    envelope = await client.orders.get_envelope("u1")

    assert envelope.state == "SUCCESSFUL"
    assert envelope.is_successful
    assert envelope.requests is not None and len(envelope.requests) == 1
    assert envelope.related_entities is not None and len(envelope.related_entities) == 2
    assert envelope.related("reverse_order")[0].cdek_number == "1234567891"
    assert envelope.related("waybill")[0].url is not None


async def test_get_order_not_found(token_route: Any, make_client: Any) -> None:
    token_route.get("/v2/orders/unknown").mock(
        return_value=httpx.Response(404, json=load_fixture("orders", "errors.json"))
    )
    client = make_client()

    with pytest.raises(NotFoundError):
        await client.orders.get("unknown")


async def test_create_order_validation_error(token_route: Any, make_client: Any) -> None:
    token_route.post("/v2/orders").mock(
        return_value=httpx.Response(400, json=load_fixture("orders", "errors.json"))
    )
    client = make_client()

    with pytest.raises(ValidationError) as exc_info:
        await client.orders.create(sample_order())

    error = exc_info.value
    assert error.has_code("v2_order_invalid")
    assert error.errors[0].additional_code == "SUP-42"
    assert error.errors[1].code == "v2_number_items_is_more_126"


async def test_get_order_by_number_uses_query(token_route: Any, make_client: Any) -> None:
    """GET /v2/orders — это поиск ОДНОГО заказа по номеру, а не список."""
    route = token_route.get("/v2/orders").mock(
        return_value=httpx.Response(200, json=load_fixture("orders", "get.json"))
    )
    client = make_client()

    order = await client.orders.get_by_number("1234567890")

    assert order.cdek_number == "1234567890"
    assert "cdek_number=1234567890" in str(route.calls.last.request.url)


async def test_get_order_by_client_number(token_route: Any, make_client: Any) -> None:
    route = token_route.get("/v2/orders").mock(
        return_value=httpx.Response(200, json=load_fixture("orders", "get.json"))
    )
    client = make_client()

    order = await client.orders.get_by_client_number("ORDER-0001")

    assert order.number == "ORDER-0001"
    assert "im_number=ORDER-0001" in str(route.calls.last.request.url)


async def test_get_order_by_number_raises_when_no_entity(
    token_route: Any, make_client: Any
) -> None:
    token_route.get("/v2/orders").mock(
        return_value=httpx.Response(200, json={"entity": None, "requests": []})
    )
    client = make_client()

    with pytest.raises(NotFoundError):
        await client.orders.get_by_number("0000000000")


async def test_update_uses_patch_with_body_identifier(token_route: Any, make_client: Any) -> None:
    """Изменение заказа — PATCH /v2/orders, идентификатор в теле (не в пути)."""
    patch_route = token_route.patch("/v2/orders").mock(
        return_value=httpx.Response(202, json=load_fixture("orders", "update.json"))
    )
    client = make_client()

    task = await client.orders.update(
        {
            "uuid": "u1",
            "type": 1,
            "recipient": {"name": "Иван", "phones": [{"number": "+79001234567"}]},
        }
    )

    assert patch_route.called
    body = patch_route.calls.last.request.read().decode()
    assert '"uuid": "u1"' in body.replace("  ", " ") or '"uuid":"u1"' in body.replace(" ", "")
    assert task.state == "ACCEPTED"
    assert [w.code for w in task.warnings] == ["v2_cost_change_by_tariff"]


async def test_delete_uses_path_uuid(token_route: Any, make_client: Any) -> None:
    delete_route = token_route.delete("/v2/orders/u1").mock(
        return_value=httpx.Response(202, json=load_fixture("orders", "create.json"))
    )
    client = make_client()

    task = await client.orders.delete("u1")

    assert delete_route.called
    assert task.uuid == "8dea00e3-9aab-4d8e-887c-ef2aaa546456"


async def test_wait_order_polls_until_successful(token_route: Any, make_client: Any) -> None:
    responses = [
        httpx.Response(
            200,
            json={
                "entity": {
                    "uuid": "u1",
                    "is_return": False,
                    "is_reverse": False,
                    "is_client_return": False,
                    "tariff_code": 136,
                    "recipient": {"name": "x", "phones": []},
                    "statuses": [],
                },
                "requests": [{"state": "ACCEPTED", "type": "CREATE"}],
            },
        ),
        httpx.Response(200, json=load_fixture("orders", "get.json")),
    ]
    route = token_route.get("/v2/orders/u1").mock(side_effect=responses)
    client = make_client()

    order = await client.wait_order("u1", timeout=5, interval=0.001)

    assert order.cdek_number == "1234567890"
    assert route.call_count == 2


async def test_wait_order_raises_on_invalid(token_route: Any, make_client: Any) -> None:
    token_route.get("/v2/orders/u1").mock(
        return_value=httpx.Response(200, json=load_fixture("orders", "invalid_task.json"))
    )
    client = make_client()

    with pytest.raises(ApiError) as exc_info:
        await client.wait_order("u1", timeout=1, interval=0.001)

    assert exc_info.value.has_code("v2_outdated_tariff")


async def test_wait_order_times_out_while_accepted(token_route: Any, make_client: Any) -> None:
    token_route.get("/v2/orders/u1").mock(
        return_value=httpx.Response(
            200,
            json={
                "entity": None,
                "requests": [
                    {"state": "ACCEPTED", "type": "CREATE", "date_time": "2026-05-05T10:00:00+0300"}
                ],
            },
        )
    )
    client = make_client()

    with pytest.raises(TimeoutExceeded):
        await client.wait_order("u1", timeout=0.05, interval=0.02)


async def test_client_return_and_refusal(token_route: Any, make_client: Any) -> None:
    return_route = token_route.post("/v2/orders/u1/clientReturn").mock(
        return_value=httpx.Response(202, json=load_fixture("orders", "create.json"))
    )
    refusal_route = token_route.post("/v2/orders/u1/refusal").mock(
        return_value=httpx.Response(202, json=load_fixture("orders", "create.json"))
    )
    client = make_client()

    await client.orders.client_return("u1", {"comment": "возврат"})
    await client.orders.refuse("u1", {"comment": "отказ"})

    assert return_route.called and refusal_route.called


async def test_order_intakes(token_route: Any, make_client: Any) -> None:
    route = token_route.get("/v2/orders/u1/intakes").mock(
        return_value=httpx.Response(200, json=[load_fixture("intakes", "info.json")["entity"]])
    )
    client = make_client()

    intakes = await client.orders.intakes("u1")

    assert route.called
    assert intakes[0].intake_number == "40000001"
